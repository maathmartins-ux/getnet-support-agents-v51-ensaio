"""Identidade de produção: token com expiração, operador com chave pessoal e limite de uso fora da memória.

- token = JWT padrão (sub, iat, exp, jti, iss, aud) emitido e validado pelo PyJWT; sem AUTH_KEYS, HS256 com a chave
  `default` (AUTH_SECRET), verificável por qualquer biblioteca JWT;
- expirado, `nbf` no futuro, adulterado, `alg` diferente do da chave, `aud`/`iss` errados ou `jti` revogado → 401;
- token assinado com a chave certa mas com claim malformado (exp em texto, payload em lista, sem jti...) → 401, nunca
  500; `aud` em lista que contém a nossa API vale (RFC 7519 §4.1.3);
- operador com chave pessoal (só o hash fica na configuração) → nome dele em cada resposta (auditoria);
- limite de uso no SQLite: vale entre processos e réplicas no mesmo volume, e falha fechado.
"""
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app import auth, keys
from app.api import app
from app.auth import issue_token, verify_token
from app.store import Store, get_store

client = TestClient(app)
_DROP = object()  # marca o claim que sai do token


def _b64(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def _claims(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def _fresh(**changes) -> dict:
    """Claims válidos agora (os do issue_token); `changes` troca ou, com _DROP, tira um claim."""
    now = int(time.time())
    claims = {"sub": "u1", "iat": now, "exp": now + 300, "jti": secrets.token_hex(8), "iss": "app", "aud": "app-api"}
    claims.update(changes)
    return {k: v for k, v in claims.items() if v is not _DROP}


def _signed(payload, header=None) -> str:
    """JWS montado aqui, sem a biblioteca, e ASSINADO com a chave `default`. Conteúdo malformado que passa da assinatura
    (vindo de quem assina: nós, ou um parceiro cuja pública está no conjunto) tem de virar 401, não 500."""
    head = {"alg": "HS256", "typ": "JWT", "kid": "default"} if header is None else header
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    signing_input = f"{_b64(head)}.{base64.urlsafe_b64encode(body).rstrip(b'=').decode()}"
    sig = hmac.new(keys.lookup("default").secret, signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}"


# --- token ---------------------------------------------------------------------------------------
def test_token_is_a_standard_jwt_with_expiry():
    token = issue_token("u1", ttl_min=5)
    header = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=="))
    claims = _claims(token)
    assert header == {"alg": "HS256", "typ": "JWT", "kid": "default"}  # sem AUTH_KEYS: HS256 com AUTH_SECRET
    assert claims["sub"] == "u1" and claims["exp"] - claims["iat"] == 300 and claims["jti"]
    assert verify_token(token) == "u1"


def test_expired_token_is_rejected(monkeypatch):
    # Emitido no passado, vencido há mais que a folga. O relógio só é deslocado na EMISSÃO (auth._now): quem valida é
    # o PyJWT, que lê o relógio dele (datetime.now), e o teste não depende de como a biblioteca o lê.
    real = auth._now
    with monkeypatch.context() as past:  # context(): undo() desfaria também o AUTH_SECRET do conftest
        past.setattr(auth, "_now", lambda: real() - 60 - auth.LEEWAY_S - 5)
        token = issue_token("u1", ttl_min=1)
    assert _claims(token)["exp"] < real() - auth.LEEWAY_S
    assert verify_token(token) is None
    assert verify_token(issue_token("u1", ttl_min=1)) == "u1"  # o mesmo token emitido agora vale


def test_token_clock_is_the_validator_clock(monkeypatch):
    # Quem adianta time.time() para vencer outra coisa (TTL da ação pendente, SLA) não pode dessincronizar o JWT:
    # emissão e leitura usam o mesmo relógio, o do PyJWT. Com time.time() na emissão, o iat ia para o futuro → 401.
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 16 * 60)
    assert verify_token(issue_token("u1")) == "u1"


def test_tampered_alg_none_and_wrong_audience_are_rejected(monkeypatch):
    token = issue_token("u1")
    head, body, sig = token.split(".")
    forged_body = _b64({**_claims(token), "sub": "u2"})
    assert verify_token(f"{head}.{forged_body}.{sig}") is None  # trocou o sub, assinatura não bate
    assert verify_token(f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{body}.") is None
    monkeypatch.setenv("AUTH_AUDIENCE", "outra-api")
    assert verify_token(token) is None


def test_revoked_token_is_rejected_via_api():
    token = issue_token("u1")
    h = {"Authorization": f"Bearer {token}"}
    assert client.post("/chat", json={"message": "oi"}, headers=h).status_code == 200
    assert client.post("/auth/revoke", headers=h).status_code == 200
    assert client.post("/chat", json={"message": "oi"}, headers=h).status_code == 401
    assert verify_token(issue_token("u1")) == "u1"  # revoga o token, não o usuário


def test_legacy_signature_format_is_not_accepted():
    sig = hashlib.sha256(b"x").hexdigest()[:32]
    assert verify_token(f"u1.{sig}") is None


def test_not_before_and_expiry_respect_the_clock_leeway():
    now, half = int(time.time()), auth.LEEWAY_S // 2
    assert verify_token(_signed(_fresh())) == "u1"  # controle: o JWS montado à parte, com claims bons, passa
    assert verify_token(_signed(_fresh(nbf=now + 10 * auth.LEEWAY_S))) is None  # nbf no futuro: ainda não vale
    assert verify_token(_signed(_fresh(nbf=now + half))) == "u1"  # dentro da folga de relógio
    assert verify_token(_signed(_fresh(nbf=now - 60))) == "u1"
    assert verify_token(_signed(_fresh(iat=now - 600, exp=now - half))) == "u1"  # vencido há menos que a folga
    assert verify_token(_signed(_fresh(iat=now - 600, exp=now - 2 * auth.LEEWAY_S))) is None


def test_audience_list_is_accepted_when_it_names_this_api():
    assert verify_token(_signed(_fresh(aud=["outra-api", "app-api"]))) == "u1"  # RFC 7519 §4.1.3: aud pode ser lista
    assert verify_token(_signed(_fresh(aud=["outra-api"]))) is None
    assert verify_token(_signed(_fresh(aud="outra-api"))) is None


_HS = {"alg": "HS256", "typ": "JWT", "kid": "default"}
_FAR = 4_102_444_800  # 2100-01-01: no futuro sem depender do relógio da coleta
# Assinados com a chave certa e malformados. Antes, exp/iat fora de número ou payload que não é objeto davam
# TypeError/AttributeError fora do try (500 no /chat e no /mcp), e sem jti o token não podia ser revogado.
# O token é montado na hora do teste: na coleta ainda não valem a chave nem o relógio do conftest.
MALFORMED = {
    "exp-texto": ("claims", {"exp": "x"}),
    "exp-numero-em-texto": ("claims", {"exp": str(_FAR)}),  # o PyJWT aceitaria (faz int()); a denylist grava REAL
    "exp-lista": ("claims", {"exp": [_FAR]}),
    "exp-infinito": ("claims", {"exp": float("inf")}),
    "exp-nulo": ("claims", {"exp": None}),
    "exp-booleano": ("claims", {"exp": True}),
    "iat-texto": ("claims", {"iat": "x"}),
    "iat-no-futuro": ("claims", {"iat": _FAR}),
    "nbf-texto": ("claims", {"nbf": "x"}),
    "nbf-numero-em-texto": ("claims", {"nbf": "0"}),
    "sem-sub": ("claims", {"sub": _DROP}),
    "sub-vazio": ("claims", {"sub": ""}),
    "sub-numero": ("claims", {"sub": 7}),
    "sem-jti": ("claims", {"jti": _DROP}),
    "jti-vazio": ("claims", {"jti": ""}),
    "jti-numero": ("claims", {"jti": 7}),
    "sem-iss": ("claims", {"iss": _DROP}),
    "iss-lista": ("claims", {"iss": ["app"]}),
    "sem-aud": ("claims", {"aud": _DROP}),
    "aud-numero": ("claims", {"aud": 7}),
    "aud-lista-vazia": ("claims", {"aud": []}),
    "payload-lista": ("payload", [1, 2]),
    "payload-texto": ("payload", "u1"),
    "payload-nulo": ("payload", None),
    "payload-nao-json": ("payload", b"\xff{"),
    "cabecalho-lista": ("header", ["HS256"]),
    "sem-alg": ("header", {"typ": "JWT", "kid": "default"}),
    "alg-lista": ("header", {**_HS, "alg": ["HS256"]}),
    "kid-numero": ("header", {**_HS, "kid": 7}),
    "crit-desconhecido": ("header", {**_HS, "crit": ["exp"]}),
    "b64-falso": ("header", {**_HS, "b64": False, "crit": ["b64"]}),
}


@pytest.mark.parametrize("name", list(MALFORMED))
def test_signed_but_malformed_token_gets_401_not_500(name):
    kind, value = MALFORMED[name]
    token = (_signed(_fresh(**value)) if kind == "claims" else _signed(value) if kind == "payload"
             else _signed(_fresh(), header=value))
    assert verify_token(_signed(_fresh())) == "u1"  # controle: mesma chave e mesma montagem, claims bons
    assert verify_token(token) is None
    h = {"Authorization": f"Bearer {token}"}
    assert client.post("/chat", json={"message": "oi"}, headers=h).status_code == 401
    assert client.post("/auth/revoke", headers=h).status_code == 401


# --- operador ------------------------------------------------------------------------------------
def test_personal_operator_key_is_recorded_on_the_reply(monkeypatch):
    key = "chave-pessoal-da-ana-com-32-caracteres!"
    monkeypatch.setenv("OPERATOR_KEYS", f"ana:{hashlib.sha256(key.encode()).hexdigest()}")
    resp = client.post("/chat", json={"message": "Quero falar com um atendente"},
                       headers={"Authorization": f"Bearer {issue_token('u1')}"}).json()
    ticket = resp["handoff"]["ticket_id"]
    assert client.get("/handoffs", headers={"X-Operator-Token": "chave-errada"}).status_code == 403
    r = client.post(f"/handoffs/{ticket}/reply", json={"answer": "Oi, sou a Ana."},
                    headers={"X-Operator-Token": key})
    assert r.status_code == 200 and r.json()["ticket"]["answered_by"] == "ana"


def test_shared_operator_token_still_works_but_is_flagged():
    assert auth.operator_name("test-operator") == "admin"
    assert client.get("/health").json()["operator_auth"] == "shared"


def test_operator_key_cli_prints_hash_line(capsys):
    auth.main(["operator-key", "bruno"])
    out = capsys.readouterr().out
    key = out.split("chave:")[1].split()[0]
    assert f"bruno:{hashlib.sha256(key.encode()).hexdigest()}" in out


# --- rate limit compartilhado ---------------------------------------------------------------------
def test_rate_limit_is_shared_across_store_instances(monkeypatch, tmp_path):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    a, b = Store(tmp_path / "shared.db"), Store(tmp_path / "shared.db")  # dois processos, um volume
    assert [a.rate_allow("k"), b.rate_allow("k"), a.rate_allow("k"), b.rate_allow("k")] == [True, True, True, False]
    assert a.rate_allow("outra") is True


def test_rate_limit_fails_closed(monkeypatch):
    def broken(*_a, **_k):
        raise OSError("disco cheio")

    monkeypatch.setattr(Store, "_db", broken)
    assert auth.LIMITER.allow("k") is False  # contador indisponível → recusa, não libera


def test_sqlite_survives_concurrent_writers(tmp_path):
    path = tmp_path / "concurrent.db"
    Store(path)

    def write(n):
        s = Store(path)
        for i in range(25):
            s.add_message(f"c{n}", "u1", "user", f"m{i}")

    threads = [threading.Thread(target=write, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(len(Store(path).history(f"c{n}", limit=100)) for n in range(4)) == 100
    assert get_store() is not None
