"""Nenhum docker-compose*.yml traz segredo literal, e o teste de réplicas sobe sem configurar nada.

Variável de segredo num compose vem do ambiente (`${X}`, `${X:?motivo}`) ou, no máximo, de um marcador `change-me...`
que o portão de produção recusa (api.insecure_defaults). O compose de réplicas trazia um AUTH_SECRET padrão "só para
o smoke": quem subisse o arquivo fora do smoke ficava com um JWT forjável por quem lesse o repositório. Agora o
scripts/scale_smoke.py gera um segredo aleatório a cada execução e o passa às réplicas por SCALE_AUTH_SECRET.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import jwt
import pytest
import yaml
from test_production_ops import _ComposeLoader  # aceita `!override` / `!reset` (o overlay endurecido usa)

from app.config import ROOT

# O último pedaço do nome diz que é segredo: OPERATOR_TOKEN, AUTH_KEYS e *_PASSWORD são; TOKEN_TTL_MIN não é.
SECRET_NAME = re.compile(r"(?:^|_)(?:SECRET|TOKEN|PASSWORD|PASSWD|KEY|KEYS)$")
INTERP = re.compile(r"\$\{(\w+)(:?[-+?])?([^}]*)\}")  # ${X}, ${X:-padrão}, ${X-padrão}, ${X:+troca}, ${X:?motivo}
PLACEHOLDER = "change-me"  # marcador que o portão recusa em produção (tests/test_v55_local_secrets.py)
SWITCH = {"", "on", "off", "true", "false", "0", "1"}  # chave liga/desliga (OPERATOR_SHARED_TOKEN=off) não é segredo


def _scalars(node) -> list[str]:
    """Todo texto do compose, já sem os comentários (o YAML os descarta): environment, command, healthcheck..."""
    if isinstance(node, dict):
        return [s for k, v in node.items() for s in (*_scalars(k), *_scalars(v))]
    if isinstance(node, list):
        return [s for item in node for s in _scalars(item)]
    return [] if node is None else [str(node)]


def _environment(svc: dict) -> list[tuple[str, str | None]]:
    env = svc.get("environment") or {}
    if isinstance(env, dict):
        return [(str(k), None if v is None else str(v)) for k, v in env.items()]
    return [(item.partition("=")[0], item.partition("=")[2] if "=" in item else None) for item in map(str, env)]


def literal_secrets(text: str) -> list[str]:
    """O que o compose usaria como segredo sem vir do ambiente: padrão ou troca não vazia (`${X:-...}`, `${X:+...}`)
    numa variável de segredo, fora o marcador `change-me`; ou, no `environment`, valor de variável de segredo que não
    é uma interpolação só."""
    compose = yaml.load(text, Loader=_ComposeLoader) or {}  # noqa: S506 — SafeLoader
    found = [f"${{{var}{op}{value}}}" for s in _scalars(compose) for var, op, value in INTERP.findall(s)
             if SECRET_NAME.search(var) and op[-1:] in ("-", "+") and value and not value.startswith(PLACEHOLDER)]
    for name, svc in (compose.get("services") or {}).items():
        for key, value in _environment(svc or {}):
            if SECRET_NAME.search(key) and value is not None and value.strip().lower() not in SWITCH \
                    and not INTERP.fullmatch(value.strip()):
                found.append(f"{name}.{key}={value}")
    return found


def test_no_compose_file_ships_a_literal_secret():
    files = sorted(ROOT.glob("docker-compose*.yml"))
    assert len(files) >= 4, f"nada varrido: {files}"
    found = {f.name: bad for f in files if (bad := literal_secrets(f.read_text(encoding="utf-8")))}
    assert not found, f"segredo literal em compose (use ${{VAR:?motivo}} e gere no script): {found}"


def test_literal_secret_is_caught():
    text = """
services:
  api:
    environment:
      AUTH_SECRET: ${SCALE_AUTH_SECRET:-scale-secret-de-exemplo}
      OPERATOR_TOKEN: abc123
      METRICS_TOKEN: ${METRICS_TOKEN:?defina METRICS_TOKEN}
      TOKEN_TTL_MIN: "60"
      OPERATOR_SHARED_TOKEN: "off"
      DATABASE_URL: postgresql://postgres:${POSTGRES_PASSWORD:-change-me-in-env}@db:5432/app
  worker:
    # comentário com ${AUTH_SECRET:-exemplo} não conta: o YAML descarta
    environment:
      - TELEGRAM_BOT_TOKEN=123:abc
      - AUTH_KEYS
"""
    assert literal_secrets(text) == ["${SCALE_AUTH_SECRET:-scale-secret-de-exemplo}", "api.OPERATOR_TOKEN=abc123",
                                     "worker.TELEGRAM_BOT_TOKEN=123:abc"]


def _scale_smoke_module(env: dict) -> dict:
    """Carrega o scripts/scale_smoke.py (sem rodar o main: nada de Docker) num processo à parte, que o script põe
    scripts/ no sys.path e importa o check.py; devolve o segredo, o que vai ao compose e um token do teste."""
    code = ("import json, runpy; m = runpy.run_path('scripts/scale_smoke.py', run_name='scale_smoke'); "
            "print(json.dumps({'secret': m['SECRET'], 'compose': m['ENV'].get('SCALE_AUTH_SECRET'), "
            "'token': m['token']('scale-user')}))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env={**env, "PYTHONPATH": str(ROOT / "src")},
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_scale_smoke_generates_the_secret_that_the_compose_and_the_token_use():
    """Sem configurar nada, cada execução tem um segredo aleatório e forte (RFC 7518 §3.2: 32+ bytes no HS256): o
    mesmo nas réplicas (o compose só o lê de SCALE_AUTH_SECRET, sem padrão) e no token que o teste assina, mesmo com
    AUTH_KEYS no ambiente de quem roda. Com SCALE_AUTH_SECRET no ambiente, vale o dele."""
    env = {k: v for k, v in os.environ.items() if k != "SCALE_AUTH_SECRET"}
    env.update(AUTH_KEYS='[{"kid":"k1","alg":"HS256","secret":"' + "h" * 48 + '"}]', AUTH_ACTIVE_KID="k1")
    first, second = _scale_smoke_module(env), _scale_smoke_module(env)
    assert first["secret"] != second["secret"] and len(first["secret"]) >= 32
    assert first["compose"] == first["secret"]
    claims = jwt.decode(first["token"], first["secret"], algorithms=["HS256"], options={"verify_aud": False})
    assert claims["sub"] == "scale-user"
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(first["token"], second["secret"], algorithms=["HS256"], options={"verify_aud": False})
    compose = yaml.load((ROOT / "docker-compose.scale.yml").read_text(encoding="utf-8"), Loader=_ComposeLoader)  # noqa: S506
    var, op, _ = INTERP.fullmatch(compose["services"]["api"]["environment"]["AUTH_SECRET"]).groups()
    assert (var, op) == ("SCALE_AUTH_SECRET", ":?")  # sem padrão: sem a variável o compose recusa subir
    assert _scale_smoke_module({**env, "SCALE_AUTH_SECRET": "s" * 48})["secret"] == "s" * 48
