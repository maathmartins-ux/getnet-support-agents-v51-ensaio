"""Rotação de chaves do JWT: `kid` no cabeçalho, conjunto em AUTH_KEYS, uma chave ativa, EdDSA/RS256/HS256, JWKS.

Ciclo de rotação provado aqui: token da chave antiga continua válido enquanto ela está no conjunto (só validando);
sai do conjunto → 401. Chave de operador não muda (OPERATOR_KEYS).
"""
import base64
import json

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app import auth, keys
from app.api import app

client = TestClient(app)


def _entry(alg, kid):
    pem, entry = keys.generate(alg, kid)
    if pem:
        entry = {"kid": kid, "alg": alg, "private_key": pem}
    return entry


def _set(monkeypatch, entries, active):
    monkeypatch.setenv("AUTH_KEYS", json.dumps(entries))
    monkeypatch.setenv("AUTH_ACTIVE_KID", active)


def _header(token):
    return json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=="))


@pytest.mark.parametrize("alg", ["EdDSA", "RS256", "HS256"])
def test_rotation_old_kid_valid_until_removed(monkeypatch, alg):
    old, new = _entry(alg, "old"), _entry("EdDSA", "new")
    _set(monkeypatch, [old], "old")
    t_old = auth.issue_token("u1")
    assert _header(t_old) == {"alg": alg, "typ": "JWT", "kid": "old"} and auth.verify_token(t_old) == "u1"

    _set(monkeypatch, [new, {**old}], "new")  # chave nova assina; a antiga fica só validando
    t_new = auth.issue_token("u1")
    assert _header(t_new)["kid"] == "new"
    assert auth.verify_token(t_old) == "u1" and auth.verify_token(t_new) == "u1"
    h = {"Authorization": f"Bearer {t_old}"}
    assert client.post("/chat", json={"message": "oi"}, headers=h).status_code == 200

    _set(monkeypatch, [new], "new")  # a antiga sai do conjunto
    assert auth.verify_token(t_old) is None and auth.verify_token(t_new) == "u1"
    assert client.post("/chat", json={"message": "oi"}, headers=h).status_code == 401


def test_verify_only_public_key_validates_but_cannot_sign(monkeypatch):
    signer_entry = _entry("EdDSA", "api")
    _set(monkeypatch, [signer_entry], "api")
    token = auth.issue_token("u1")
    public = keys.lookup("api").public.public_bytes(keys.serialization.Encoding.PEM,
                                                    keys.serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    _set(monkeypatch, [{"kid": "hs", "alg": "HS256", "secret": "s" * 40}, {"kid": "api", "alg": "EdDSA",
                                                                             "public_key": public}], "hs")
    assert auth.verify_token(token) == "u1"
    monkeypatch.setenv("AUTH_ACTIVE_KID", "api")  # só pública: não pode ser a ativa
    with pytest.raises(keys.KeyConfigError):
        keys.keyset()
    assert auth.verify_token(token) is None  # configuração inválida falha fechado


def test_algorithm_confusion_is_rejected(monkeypatch):
    ed = _entry("EdDSA", "ed")
    _set(monkeypatch, [ed], "ed")
    token = auth.issue_token("u1")
    head, body, _ = token.split(".")
    public_pem = keys.lookup("ed").public.public_bytes(keys.serialization.Encoding.PEM,
                                                       keys.serialization.PublicFormat.SubjectPublicKeyInfo)
    # HS256 "assinado" com a chave PÚBLICA como segredo (ataque clássico de confusão de algoritmo)
    forged_head = keys._b64e(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "ed"}).encode())
    import hashlib
    import hmac

    mac = keys._b64e(hmac.new(public_pem, f"{forged_head}.{body}".encode(), hashlib.sha256).digest())
    assert auth.verify_token(f"{forged_head}.{body}.{mac}") is None
    assert auth.verify_token(f"{keys._b64e(json.dumps({'alg': 'none', 'kid': 'ed'}).encode())}.{body}.") is None
    unknown = keys._b64e(json.dumps({"alg": "EdDSA", "typ": "JWT", "kid": "fantasma"}).encode())
    assert auth.verify_token(f"{unknown}.{body}.{token.split('.')[2]}") is None


def test_jwks_publishes_only_public_keys_and_any_jwt_library_verifies(monkeypatch):
    ed, rs = _entry("EdDSA", "ed-2026-11"), _entry("RS256", "rs-2026-10")
    _set(monkeypatch, [ed, rs, {"kid": "hs", "alg": "HS256", "secret": "z" * 40}], "ed-2026-11")
    r = client.get("/.well-known/jwks.json")
    assert r.status_code == 200 and "max-age" in r.headers["cache-control"]
    jwks = r.json()
    assert {k["kid"] for k in jwks["keys"]} == {"ed-2026-11", "rs-2026-10"}  # o segredo HS256 nunca sai
    assert all("d" not in k and "secret" not in k for k in jwks["keys"])  # sem parte privada
    for active in ("ed-2026-11", "rs-2026-10"):
        monkeypatch.setenv("AUTH_ACTIVE_KID", active)
        token = auth.issue_token("u7")
        jwk = next(k for k in jwks["keys"] if k["kid"] == pyjwt.get_unverified_header(token)["kid"])
        claims = pyjwt.decode(token, pyjwt.PyJWK(jwk).key, algorithms=[jwk["alg"]], audience="app-api", issuer="app")
        assert claims["sub"] == "u7"  # outra biblioteca valida só com o JWKS público


def test_health_shows_the_keyset_and_bad_config_is_reported(monkeypatch):
    _set(monkeypatch, [_entry("EdDSA", "k1")], "k1")
    health = client.get("/health").json()
    assert health["jwt"] == {"ok": True, "active_kid": "k1", "alg": "EdDSA", "kids": ["k1"]}
    assert not any(n.startswith("AUTH") for n in health["insecure_defaults"])  # sem HS256 no conjunto
    monkeypatch.setenv("AUTH_KEYS", "[{\"kid\": \"x\", \"alg\": \"HS512\"}]")
    assert client.get("/health").json()["jwt"]["ok"] is False


def test_weak_hs256_secret_in_keyset_is_flagged(monkeypatch):
    _set(monkeypatch, [{"kid": "curta", "alg": "HS256", "secret": "curta"}], "curta")
    assert "AUTH_KEYS[curta]" in client.get("/health").json()["insecure_defaults"]


def test_keygen_cli_prints_a_usable_entry(capsys, monkeypatch):
    assert auth.main(["keygen", "--alg", "EdDSA", "--kid", "2026-12"]) == 0
    out = capsys.readouterr().out
    pem = out.split("(grave")[0]
    assert pem.startswith("-----BEGIN PRIVATE KEY-----") and '"kid": "2026-12"' in out
    _set(monkeypatch, [{"kid": "2026-12", "alg": "EdDSA", "private_key": pem}], "2026-12")
    assert auth.verify_token(auth.issue_token("u1")) == "u1"


def test_operator_keys_are_unchanged_by_the_jwt_keyset(monkeypatch):
    _set(monkeypatch, [_entry("EdDSA", "k1")], "k1")
    assert auth.operator_name("test-operator") == "admin"
