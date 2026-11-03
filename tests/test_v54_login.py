"""Login com senha sobre o mesmo JWT: erro genérico, limite de tentativas e logout que revoga o token."""
import pytest
from fastapi.testclient import TestClient

from app import auth
from app.api import app

client = TestClient(app)


@pytest.fixture
def creds(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setenv("CREDENTIALS_FILE", str(path))
    auth.set_password("u1", "senha-forte-1")
    return path


def test_password_is_stored_only_as_scrypt_hash(creds):
    text = creds.read_text(encoding="utf-8")
    assert "senha-forte-1" not in text and "scrypt$" in text
    stored = auth.load_credentials()["u1"]
    assert auth.verify_password(stored, "senha-forte-1") and not auth.verify_password(stored, "outra")
    assert not auth.verify_password("lixo", "senha-forte-1")


def test_login_returns_the_same_jwt_used_by_chat(creds):
    r = client.post("/auth/login", json={"user_id": "u1", "password": "senha-forte-1"})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer" and r.json()["expires_in"] > 0
    token = r.json()["access_token"]
    assert auth.verify_token(token) == "u1"
    chat = client.post("/chat", json={"message": "Onde está meu pedido 1002?"},
                       headers={"Authorization": f"Bearer {token}"})
    assert chat.status_code == 200 and chat.json()["identity_verified"] is True


def test_wrong_password_and_unknown_user_get_the_same_generic_error(creds):
    wrong = client.post("/auth/login", json={"user_id": "u1", "password": "errada"})
    ghost = client.post("/auth/login", json={"user_id": "ninguem", "password": "errada"})
    assert wrong.status_code == ghost.status_code == 401
    assert wrong.json() == ghost.json() == {"detail": "usuário ou senha inválidos"}


def test_login_is_rate_limited_per_ip_and_user(creds, monkeypatch):
    monkeypatch.setenv("LOGIN_RATE_PER_MIN", "3")
    for _ in range(3):
        assert client.post("/auth/login", json={"user_id": "u1", "password": "errada"}).status_code == 401
    blocked = client.post("/auth/login", json={"user_id": "u1", "password": "senha-forte-1"})
    assert blocked.status_code == 429 and blocked.headers["Retry-After"] == "60"
    # outro usuário no mesmo IP tem a sua própria janela
    assert client.post("/auth/login", json={"user_id": "u2", "password": "x"}).status_code == 401


def test_logout_revokes_the_token(creds):
    token = client.post("/auth/login", json={"user_id": "u1", "password": "senha-forte-1"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/auth/logout", headers=headers).json() == {"revoked": True}
    assert auth.verify_token(token) is None
    assert client.post("/chat", json={"message": "oi"}, headers=headers).status_code == 401


def test_seed_passwords_covers_the_domain_users_and_keeps_only_hashes(creds):
    users = auth.known_users()
    assert {"u1", "u2"} <= set(users)  # donos dos registros do domínio de exemplo
    plain = auth.seed_passwords()
    assert set(plain) == set(users)
    stored = auth.load_credentials()
    assert all(auth.verify_password(stored[u], pw) for u, pw in plain.items())
    assert not any(pw in creds.read_text(encoding="utf-8") for pw in plain.values())


def test_cli_seed_writes_passwords_outside_git(creds, tmp_path, capsys):
    out = tmp_path / "var" / "demo_passwords.txt"
    assert auth.main(["seed-passwords", "--out", str(out)]) == 0
    assert "u1\t" in out.read_text(encoding="utf-8") and "u1\t" in capsys.readouterr().out
    assert auth.main(["set-password", "u9", "--password", "curta"]) == 1  # < 8 caracteres
