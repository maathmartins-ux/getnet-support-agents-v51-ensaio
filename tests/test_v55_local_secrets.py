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
