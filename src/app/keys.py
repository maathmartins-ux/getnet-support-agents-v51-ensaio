"""Chaves de assinatura do JWT do cliente: conjunto com `kid`, uma chave ativa que assina, as outras só validam.

Por quê: com um segredo HS256 único, trocar o segredo derruba todas as sessões ao mesmo tempo e qualquer serviço que
valide o token precisa do segredo (que também assina). Com o conjunto:
- rotação sem queda: a chave nova entra como ativa, a antiga continua no conjunto só validando até o último token
  dela expirar (TOKEN_TTL_MIN), e então sai. Token de `kid` fora do conjunto → 401;
- assimétrica (EdDSA/Ed25519 ou RS256): só a API guarda a privada; quem só valida (gateway, outro serviço) lê as
  públicas em GET /.well-known/jwks.json (RFC 7517) e não consegue emitir token;
- HS256 continua aceito (segredo compartilhado, nunca publicado no JWKS).

Configuração (lida a cada chamada, com cache pelo valor das variáveis):
  AUTH_KEYS='[{"kid":"2026-11","alg":"EdDSA","private_key_file":"/run/secrets/jwt-2026-11.pem"},
              {"kid":"2026-10","alg":"HS256","secret":"<32+ bytes>"},
              {"kid":"parceiro","alg":"RS256","public_key_file":"/run/secrets/parceiro.pub.pem"}]'
  AUTH_ACTIVE_KID=2026-11      (padrão: a 1ª chave que pode assinar)
Material: `secret` (HS256), `private_key`/`private_key_file` (PEM PKCS8; a pública sai dela) ou
`public_key`/`public_key_file` (só valida). Sem AUTH_KEYS: uma chave HS256 `default` com AUTH_SECRET (compatível com
o kit anterior). Token sem `kid` é validado só pela chave `default`, se ela estiver no conjunto.
Chave nova: `python -m app.auth keygen --alg EdDSA --kid 2026-11`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

from .config import auth_secret

ALGS = ("HS256", "EdDSA", "RS256")
MIN_RSA_BITS = 2048  # abaixo disso a RFC 7518 não recomenda RS256
MIN_HS_BYTES = 32  # HS256 com segredo menor que o hash (256 bits) perde força contra força bruta
DEFAULT_KID = "default"


class KeyConfigError(ValueError):
    """AUTH_KEYS/AUTH_ACTIVE_KID inválidos. ValueError: decode_token trata como token inválido (falha fechado)."""


@dataclass(frozen=True)
class Key:
    kid: str
    alg: str
    secret: bytes | None = None
    private: object | None = None
    public: object | None = None

    @property
    def can_sign(self) -> bool:
        return self.secret is not None or self.private is not None


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _pem(entry: dict, name: str) -> bytes | None:
    if entry.get(name):
        return str(entry[name]).encode()
    if entry.get(f"{name}_file"):
        return Path(entry[f"{name}_file"]).read_bytes()
    return None


def _parse(entry: dict) -> Key:
    kid, alg = str(entry.get("kid") or ""), str(entry.get("alg") or "")
    if not kid or alg not in ALGS:
        raise KeyConfigError(f"chave sem kid ou com alg fora de {ALGS}: {kid or '?'}")
    if alg == "HS256":
        secret = str(entry.get("secret") or "").encode()
        if not secret:
            raise KeyConfigError(f"{kid}: HS256 precisa de secret")
        return Key(kid, alg, secret=secret)
    private_pem, public_pem = _pem(entry, "private_key"), _pem(entry, "public_key")
    private = serialization.load_pem_private_key(private_pem, password=None) if private_pem else None
    public = private.public_key() if private else (serialization.load_pem_public_key(public_pem) if public_pem
                                                    else None)
    if public is None:
        raise KeyConfigError(f"{kid}: {alg} precisa de private_key ou public_key")
    want = ed25519.Ed25519PublicKey if alg == "EdDSA" else rsa.RSAPublicKey
    if not isinstance(public, want):
        raise KeyConfigError(f"{kid}: a chave não é do tipo de {alg}")  # impede confusão de algoritmo
    if alg == "RS256" and public.key_size < MIN_RSA_BITS:
        raise KeyConfigError(f"{kid}: RSA com {public.key_size} bits (mínimo {MIN_RSA_BITS})")
    return Key(kid, alg, private=private, public=public)


@lru_cache(maxsize=8)
def _load(raw: str, active: str, secret: str) -> tuple[dict[str, Key], str]:
    if not raw.strip():
        keys = {DEFAULT_KID: Key(DEFAULT_KID, "HS256", secret=secret.encode())}
    else:
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise KeyConfigError(f"AUTH_KEYS não é JSON: {exc.msg}") from exc
        if not isinstance(entries, list) or not entries:
            raise KeyConfigError("AUTH_KEYS deve ser uma lista não vazia de chaves")
        keys = {}
        for entry in entries:
            key = _parse(entry if isinstance(entry, dict) else {})
            if key.kid in keys:
                raise KeyConfigError(f"kid repetido: {key.kid}")
            keys[key.kid] = key
    kid = active or next((k.kid for k in keys.values() if k.can_sign), "")
    if kid not in keys or not keys[kid].can_sign:
        raise KeyConfigError(f"AUTH_ACTIVE_KID={kid or '?'} não está no conjunto ou não tem material para assinar")
    return keys, kid


def keyset() -> tuple[dict[str, Key], str]:
    """(chaves por kid, kid ativo). Levanta KeyConfigError se a configuração é inválida."""
    return _load(os.getenv("AUTH_KEYS", ""), os.getenv("AUTH_ACTIVE_KID", "").strip(), auth_secret())


def signer() -> Key:
    keys, kid = keyset()
    return keys[kid]


def lookup(kid: str | None) -> Key | None:
    keys, _ = keyset()
    return keys.get(kid or DEFAULT_KID)


def sign(key: Key, data: bytes) -> bytes:
    if key.alg == "HS256":
        return hmac.new(key.secret, data, hashlib.sha256).digest()
    if key.alg == "EdDSA":
        return key.private.sign(data)
    return key.private.sign(data, padding.PKCS1v15(), hashes.SHA256())


def verify(key: Key, data: bytes, signature: bytes) -> bool:
    if key.alg == "HS256":
        return key.secret is not None and hmac.compare_digest(sign(key, data), signature)
    try:
        if key.alg == "EdDSA":
            key.public.verify(signature, data)
        else:
            key.public.verify(signature, data, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        return False
    return True


def _jwk(key: Key) -> dict:
    base = {"kid": key.kid, "alg": key.alg, "use": "sig"}
    if key.alg == "EdDSA":
        raw = key.public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return {**base, "kty": "OKP", "crv": "Ed25519", "x": _b64e(raw)}
    numbers = key.public.public_numbers()
    size = lambda n: n.to_bytes((n.bit_length() + 7) // 8, "big")  # noqa: E731
    return {**base, "kty": "RSA", "n": _b64e(size(numbers.n)), "e": _b64e(size(numbers.e))}


def jwks() -> dict:
    """Só as chaves PÚBLICAS (assimétricas). Segredo HS256 nunca sai daqui: quem o tem também emite token."""
    keys, _ = keyset()
    return {"keys": [_jwk(k) for k in keys.values() if k.alg != "HS256"]}


def weak_secrets() -> list[str]:
    """Segredos HS256 fracos ou de desenvolvimento no conjunto (aparecem no /health e barram APP_ENV=production)."""
    try:
        keys, _ = keyset()
    except KeyConfigError:
        return ["AUTH_KEYS"]
    label = (lambda k: "AUTH_SECRET") if not os.getenv("AUTH_KEYS", "").strip() else (lambda k: f"AUTH_KEYS[{k}]")
    return [label(k.kid) for k in keys.values()
            if k.alg == "HS256" and (k.secret.startswith(b"dev-") or len(k.secret) < MIN_HS_BYTES)]


def generate(alg: str, kid: str) -> tuple[str, dict]:
    """(PEM da privada, entrada do AUTH_KEYS sem o PEM). Para HS256 o segredo vai na própria entrada."""
    if alg == "HS256":
        return "", {"kid": kid, "alg": alg, "secret": base64.urlsafe_b64encode(os.urandom(48)).decode()}
    private = ed25519.Ed25519PrivateKey.generate() if alg == "EdDSA" else rsa.generate_private_key(65537, 3072)
    pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    return pem, {"kid": kid, "alg": alg, "private_key_file": f"/run/secrets/jwt-{kid}.pem"}
