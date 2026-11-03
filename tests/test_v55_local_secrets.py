"""Sem AUTH_SECRET/OPERATOR_TOKEN não há segredo conhecido: cada instalação gera o seu e guarda em var/."""
import stat

from app import config, keys
from app.api import insecure_defaults


def test_unset_secrets_are_random_persisted_and_not_flagged(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    monkeypatch.delenv("OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("AUTH_KEYS", raising=False)
    first = config.auth_secret()
    assert len(first) >= 48 and config.auth_secret() == first  # a CLI e o servidor leem o mesmo arquivo
    assert config.operator_token() != first
    path = tmp_path / "local_secrets.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    keys._load.cache_clear()
    assert insecure_defaults() == []


def test_placeholder_from_env_example_is_flagged(monkeypatch):
    monkeypatch.setenv("OPERATOR_TOKEN", "troque-por-outro-segredo-longo")
    assert "OPERATOR_TOKEN" in insecure_defaults()


def test_metrics_token_and_shared_operator_token(monkeypatch):
    """/metrics com METRICS_TOKEN exige o token; com chave pessoal, o token compartilhado deixa de valer."""
    from fastapi.testclient import TestClient

    from app import auth
    from app.api import app

    c = TestClient(app)
    assert c.get("/metrics").status_code == 200  # sem METRICS_TOKEN: aberto (rede interna)
    monkeypatch.setenv("METRICS_TOKEN", "m" * 24)
    assert c.get("/metrics").status_code == 401
    assert c.get("/metrics", headers={"Authorization": "Bearer " + "m" * 24}).status_code == 200
    assert auth.operator_name("test-operator") == "admin"
    monkeypatch.setenv("OPERATOR_KEYS", f"ana:{auth._hash('k' * 20)}")
    assert auth.operator_name("test-operator") is None and auth.operator_name("k" * 20) == "ana"


def test_generated_operator_token_is_not_printed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.delenv("OPERATOR_TOKEN", raising=False)
    token = config.operator_token()
    assert token not in capsys.readouterr().err


def test_compose_example_passwords_count_as_insecure(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:change-me-in-env@postgres:5432/app")
    assert "POSTGRES_PASSWORD" in insecure_defaults()
