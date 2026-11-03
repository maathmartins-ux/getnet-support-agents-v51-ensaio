"""/health diz que o processo está vivo; /ready diz se ele pode atender (503 com o motivo)."""
from fastapi.testclient import TestClient

from app import api
from app.api import app

client = TestClient(app)


def test_ready_ok_offline_declared():
    r = client.get("/ready")
    body = r.json()
    assert r.status_code == 200 and body["ready"] is True and body["failed"] == {}
    assert body["checks"]["llm"]["mode"] == "offline" and body["checks"]["index"]["docs"] > 0
    assert body["checks"]["db"]["ok"] is True and "budget" not in body["checks"]


def test_ready_503_when_llm_key_missing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    r = client.get("/ready")
    assert r.status_code == 503 and "sem chave" in r.json()["failed"]["llm"]
    assert client.get("/health").status_code == 200, "vivo continua 200: reiniciar não traz a chave"
    monkeypatch.setenv("APP_ANTHROPIC_API_KEY", "sk-test")
    assert client.get("/ready").status_code == 200


def test_ready_503_when_index_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    r = client.get("/ready")
    assert r.status_code == 503 and "índice vazio" in r.json()["failed"]["index"]


def test_ready_503_when_db_not_writable(monkeypatch):
    class Broken:
        def probe_write(self):
            raise OSError("read-only file system")

    monkeypatch.setattr(api, "get_store", lambda: Broken())
    r = client.get("/ready")
    assert r.status_code == 503 and "read-only" in r.json()["failed"]["db"]


def test_ready_reports_budget_when_llm_module_has_one(monkeypatch):
    monkeypatch.setattr(api.llm_module, "budget_status",
                        lambda: {"limit_usd": 5.0, "spent_usd": 5.0, "remaining_usd": 0.0}, raising=False)
    r = client.get("/ready")
    assert r.status_code == 503 and r.json()["failed"] == {"budget": "orçamento esgotado"}
    monkeypatch.setattr(api.llm_module, "budget_status", lambda: {"remaining_usd": 1.5}, raising=False)
    assert client.get("/ready").json()["checks"]["budget"]["remaining_usd"] == 1.5
