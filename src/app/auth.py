"""Identidade, operadores e limite de uso.

Cliente: JWT padrão (sub, iat, exp, jti, iss, aud) com `kid` no cabeçalho, assinado pela chave ATIVA do conjunto
(app/keys.py: HS256, EdDSA ou RS256; rotação sem queda; públicas em GET /.well-known/jwks.json). Qualquer biblioteca
JWT valida o mesmo token, e trocar por OIDC/JWKS do provedor de identidade mantém a interface
(verify_token -> user_id). Recusa: `kid` fora do conjunto, `alg` diferente do da chave daquele `kid` (inclui "none" e
HS256 assinado com a chave pública), assinatura errada, expirado (folga de LEEWAY_S), `iss`/`aud` diferentes e `jti`
revogado (POST /auth/revoke).

Operador: chave pessoal; a configuração guarda só o sha256 (OPERATOR_KEYS="ana:<hash>,bruno:<hash>").
O nome entra em cada resposta e aprovação (auditoria). OPERATOR_TOKEN compartilhado continua aceito
como "admin" para demo, e o /health o sinaliza como "shared".

Login com senha (o fluxo que um usuário reconhece: entra com senha e recebe o token): POST /auth/login troca usuário +
senha pelo MESMO JWT acima (mesmo emissor, `kid`, JWKS);
POST /auth/logout revoga o `jti`. Senha guardada só como hash scrypt (stdlib, sem dependência nova) em
`var/credentials.json`, ao lado do banco e fora do git (CREDENTIALS_FILE); cada ambiente semeia as suas senhas de
teste (`seed-passwords`), então nenhuma senha nem hash entra no repositório; comparação em tempo constante, e
usuário inexistente custa o mesmo hash (não revela quem existe). Limite próprio por IP+usuário (LOGIN_RATE_PER_MIN,
429 com Retry-After).

Uso:
  python -m app.auth seed-passwords [--users a,b] [--out var/demo_passwords.txt]
                                         → senha aleatória para cada usuário de teste do domínio; grava só o hash e
                                           imprime a senha uma vez (o arquivo --out fica fora do git, em var/)
  python -m app.auth set-password u1 [--password X]  → define a senha de um usuário (sem --password: lê do stdin)
  python -m app.auth u1 [--ttl 60]       → token de desenvolvimento para u1 (atalho de teste; padrão TOKEN_TTL_MIN)
  python -m app.auth operator-key ana    → chave nova para a operadora + linha "ana:<sha256>" do OPERATOR_KEYS
  python -m app.auth keygen --alg EdDSA --kid 2026-11 → par de chaves novo + entrada do AUTH_KEYS
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from pathlib import Path

from . import keys
from .config import (
    auth_audience,
    auth_issuer,
    credentials_file,
    operator_keys,
    operator_token,
    rate_limit_per_min,
    token_ttl_min,
)
from .observability import METRICS, log

LEEWAY_S = 30  # relógios de cliente e servidor raramente batem; 30 s é a folga usual de JWT


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(user_id: str, ttl_min: int | None = None) -> str:
    now = int(time.time())
    key = keys.signer()
    header = _b64e(json.dumps({"alg": key.alg, "typ": "JWT", "kid": key.kid}, separators=(",", ":")).encode())
    claims = {"sub": user_id, "iat": now, "exp": now + 60 * (ttl_min or token_ttl_min()),
              "jti": secrets.token_hex(8), "iss": auth_issuer(), "aud": auth_audience()}
    body = _b64e(json.dumps(claims, separators=(",", ":")).encode())
    return f"{header}.{body}.{_b64e(keys.sign(key, f'{header}.{body}'.encode()))}"


def decode_token(token: str | None) -> dict | None:
    """Claims se o token é válido agora; None em qualquer falha (sem dizer qual: não ajuda quem forja)."""
    try:
        head, body, sig = (token or "").split(".")
        header = json.loads(_b64d(head))
        key = keys.lookup(header.get("kid"))  # kid removido do conjunto → None → 401
        # o alg é o da CHAVE, nunca o que o token declara: "none" ou HS256 com a pública como segredo não passam
        if key is None or header.get("alg") != key.alg:
            return None
        if not keys.verify(key, f"{head}.{body}".encode(), _b64d(sig)):
            return None
        claims = json.loads(_b64d(body))
    except (ValueError, TypeError, AttributeError):  # inclui keys.KeyConfigError: configuração ruim falha fechado
        return None
    now = time.time()
    if not claims.get("sub") or claims.get("exp", 0) + LEEWAY_S < now or claims.get("iat", 0) - LEEWAY_S > now:
        return None
    if claims.get("iss") != auth_issuer() or claims.get("aud") != auth_audience():
        return None
    from .store import get_store  # import tardio: store não depende de auth

    if get_store().is_revoked(claims.get("jti", "")):
        return None
    return claims


def verify_token(token: str | None) -> str | None:
    claims = decode_token(token)
    return claims["sub"] if claims else None


def revoke_token(token: str) -> bool:
    claims = decode_token(token)
    if not claims:
        return False
    from .store import get_store

    get_store().revoke(claims["jti"], claims["exp"])
    return True


# --- senha (login) ----------------------------------------------------------------------------------
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1  # parâmetros interativos recomendados para scrypt (~50 ms, 16 MB)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64e(salt)}${_b64e(digest)}"


def verify_password(stored: str, password: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=_b64d(salt), n=int(n), r=int(r), p=int(p), dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, _b64d(digest))


_DUMMY = hash_password(secrets.token_urlsafe(12))  # usuário inexistente paga o mesmo scrypt


def load_credentials(path: Path | None = None) -> dict[str, str]:
    path = path or credentials_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    users = data.get("users", {}) if isinstance(data, dict) else {}
    return {str(k): str(v) for k, v in users.items() if isinstance(v, str)}


def save_credentials(users: dict[str, str], path: Path | None = None) -> Path:
    path = path or credentials_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"_doc": "Hashes scrypt das senhas de teste (python -m app.auth seed-passwords). Nunca a senha.",
           "users": dict(sorted(users.items()))}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def set_password(user_id: str, password: str, path: Path | None = None) -> None:
    users = load_credentials(path)
    users[user_id] = hash_password(password)
    save_credentials(users, path)


def known_users() -> list[str]:
    """Usuários de teste do domínio: `users()` do domínio, se houver; senão os donos/clientes dos registros."""
    from . import domain

    d = domain.active()
    hook = getattr(d, "users", None)
    if callable(hook):
        return sorted({str(u) for u in hook()})
    found: set[str] = set()

    def walk(node, key: str = "") -> None:
        if isinstance(node, dict):
            if key in ("customers", "users", "merchants"):
                found.update(str(k) for k in node if not str(k).startswith("_"))
            for k, v in node.items():
                if k in ("owner", "user_id", "merchant_id") and isinstance(v, str):
                    found.add(v)
                walk(v, str(k))
        elif isinstance(node, list):
            for item in node:
                walk(item, key)

    try:
        walk(d.records())
    except Exception:  # noqa: BLE001 — domínio sem registros: sem usuários de teste
        return []
    return sorted(found)


def seed_passwords(users: list[str] | None = None, path: Path | None = None) -> dict[str, str]:
    """Senha aleatória para cada usuário; grava só o hash. Devolve {usuário: senha} para mostrar UMA vez."""
    users = users or known_users()
    stored = load_credentials(path)
    plain = {u: secrets.token_urlsafe(9) for u in users}
    stored.update({u: hash_password(pw) for u, pw in plain.items()})
    save_credentials(stored, path)
    return plain


def login(user_id: str, password: str) -> str | None:
    """Token para usuário + senha certos; None em qualquer falha (mesmo custo para usuário inexistente)."""
    stored = load_credentials().get(user_id)
    ok = verify_password(stored or _DUMMY, password)
    if not (stored and ok):
        METRICS.inc("login_failures_total")
        return None
    METRICS.inc("logins_total")
    return issue_token(user_id)


# --- operadores ------------------------------------------------------------------------------------
def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def operator_name(token: str | None) -> str | None:
    """Nome do operador dono da chave; "admin" para o token compartilhado; None se não autorizado."""
    if not token:
        return None
    digest = _hash(token)
    for name, expected in operator_keys().items():
        if hmac.compare_digest(digest.encode(), expected.lower().encode()):
            return name
    # Com chave pessoal configurada, o token compartilhado deixa de valer (toda aprovação tem dono na auditoria),
    # salvo OPERATOR_SHARED_TOKEN=on (migração: os dois juntos por um tempo).
    shared_ok = not operator_keys() or os.getenv("OPERATOR_SHARED_TOKEN", "off").lower() == "on"
    if shared_ok and hmac.compare_digest(token.encode(), operator_token().encode()):
        return "admin"
    return None


def operator_auth_mode() -> str:
    return "personal" if operator_keys() else "shared"


# --- limite de uso -----------------------------------------------------------------------------------
class RateLimiter:
    """Janela deslizante de 60 s por chave, no SQLite: vale para todos os processos que leem o mesmo volume.

    Falha fechado: se o contador não responde, recusa (429) em vez de liberar tráfego sem limite.
    """

    def allow(self, key: str) -> bool:
        from .store import get_store

        try:
            return get_store().rate_allow(key, rate_limit_per_min())
        except Exception as exc:  # noqa: BLE001 — qualquer falha do contador vira recusa, nunca liberação
            METRICS.inc("rate_limit_store_errors_total")
            log.warning("rate_limit_store_error", extra={"extra_fields": {"error": type(exc).__name__}})
            return False

    def reset(self) -> None:
        from .store import get_store

        try:
            get_store().rate_reset()
        except Exception:  # noqa: BLE001 — reset é para testes; banco ausente não é erro aqui
            pass


LIMITER = RateLimiter()


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["keygen"]:
        gen = argparse.ArgumentParser(prog="python -m app.auth keygen")
        gen.add_argument("--alg", choices=keys.ALGS, default="EdDSA")
        gen.add_argument("--kid", required=True)
        opts = gen.parse_args(argv[1:])
        pem, entry = keys.generate(opts.alg, opts.kid)
        if pem:
            print(f"{pem}(grave o PEM acima em {entry['private_key_file']}; ele não é guardado)")
        print(f"AUTH_KEYS entry: {json.dumps(entry)}\nrotação: ponha a entrada no AUTH_KEYS, AUTH_ACTIVE_KID="
              f"{opts.kid}, e só tire a chave antiga depois de TOKEN_TTL_MIN")
        return 0
    if argv[:1] == ["seed-passwords"]:
        seed = argparse.ArgumentParser(prog="python -m app.auth seed-passwords")
        seed.add_argument("--users", default="", help="lista separada por vírgula (padrão: usuários do domínio)")
        seed.add_argument("--out", default="var/demo_passwords.txt", help="onde anotar as senhas (fora do git)")
        opts = seed.parse_args(argv[1:])
        plain = seed_passwords([u.strip() for u in opts.users.split(",") if u.strip()] or None)
        if not plain:
            print("nenhum usuário de teste encontrado no domínio; use --users a,b")
            return 1
        lines = [f"{u}\t{pw}" for u, pw in plain.items()]
        out = Path(opts.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines) + f"\n(hashes em {credentials_file()}; senhas anotadas em {out}, fora do git)")
        return 0
    if argv[:1] == ["set-password"]:
        sp = argparse.ArgumentParser(prog="python -m app.auth set-password")
        sp.add_argument("user_id")
        sp.add_argument("--password", default=None)
        opts = sp.parse_args(argv[1:])
        password = opts.password if opts.password is not None else sys.stdin.readline().rstrip("\n")
        if len(password) < 8:
            print("senha com menos de 8 caracteres recusada")
            return 1
        set_password(opts.user_id, password)
        print(f"senha de {opts.user_id} gravada (só o hash) em {credentials_file()}")
        return 0
    if argv[:1] == ["operator-key"]:
        name = argv[1] if len(argv) > 1 else "operador"
        key = secrets.token_urlsafe(24)
        print(f"chave: {key}\n(entregue só ao operador; ela não é guardada)\n"
              f"OPERATOR_KEYS entry: {name}:{_hash(key)}")
        return 0
    ap = argparse.ArgumentParser(prog="python -m app.auth")
    ap.add_argument("user_id", nargs="?", default="u1")
    ap.add_argument("--ttl", type=int, default=None, help="minutos (padrão TOKEN_TTL_MIN)")
    args = ap.parse_args(argv)
    print(issue_token(args.user_id, args.ttl))
    return 0


if __name__ == "__main__":
    sys.exit(main())
