"""LGPD: apagamento pelo titular, retenção por idade e auditoria só de inclusão."""
import time

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.auth import issue_token
from app.store import get_store
from app.store import main as store_cli

client = TestClient(app)
OP = {"X-Operator-Token": "test-operator"}


def auth(user="u1"):
    return {"Authorization": f"Bearer {issue_token(user)}"}


def _chat(message, user="u1", conv=None):
    body = {"message": message, **({"conversation_id": conv} if conv else {})}
    return client.post("/chat", json=body, headers=auth(user)).json()


def test_owner_deletes_own_conversation_and_it_is_audited():
    r = _chat("Quero falar com um atendente")
    conv = r["conversation_id"]
    client.post("/feedback", json={"trace_id": r["trace_id"], "rating": 1}, headers=auth())
    store = get_store()
    assert store.history(conv) and store.ticket_for(conv)

    out = client.delete(f"/me/conversations/{conv}", headers=auth())
    assert out.status_code == 200 and out.json()["counts"]["messages"] >= 2
    assert out.json()["counts"]["tickets"] == 1 and out.json()["counts"]["feedback"] == 1
    assert store.history(conv) == [] and store.ticket_for(conv) is None and store.user_summary("u1") == ""
    assert client.get(f"/conversations/{conv}", headers=auth()).status_code == 404
    entry = client.get("/audit", params={"action": "conversation_deleted"}, headers=OP).json()[0]
    assert entry["actor"] == "user:u1" and entry["target"] == conv and entry["detail"]["messages"] >= 2
    assert "atendente" not in str(entry), "auditoria guarda contagens, nunca o conteúdo"


def test_other_user_cannot_delete_and_learns_nothing():
    conv = _chat("Qual o prazo de entrega?", user="u1")["conversation_id"]
    assert client.delete(f"/me/conversations/{conv}", headers=auth("u2")).status_code == 404
    assert client.delete("/me/conversations/nao-existe", headers=auth("u2")).status_code == 404
    assert get_store().history(conv), "a conversa do dono continua inteira"


def test_delete_requires_signed_token_even_in_demo_mode(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "demo")
    conv = client.post("/chat", json={"message": "oi", "user_id": "u7"}).json()["conversation_id"]
    assert client.delete(f"/me/conversations/{conv}", params={"user_id": "u7"}).status_code == 401
    assert get_store().history(conv)


def test_retention_purge_by_age_keeps_recent_and_open_cases():
    store = get_store()
    old = _chat("Qual o prazo de entrega?")["conversation_id"]
    waiting = _chat("Quero falar com um atendente", user="u2")["conversation_id"]  # caso humano aberto
    recent = _chat("Qual o horário de atendimento?", user="u3")["conversation_id"]
    future = time.time() + 40 * 86400
    with store._db() as conn:  # "envelhece" a conversa recente para ficar dentro da janela de 30 dias
        conn.execute("UPDATE messages SET ts = ? WHERE conversation_id = ?", (future - 86400, recent))

    totals = store.purge_older_than(30, actor="operator:test", now=future)
    assert totals["conversations"] == 1 and totals["kept_open_ticket"] == 1
    assert store.history(old) == [] and store.history(waiting) and store.history(recent)
    entry = store.audit_entries(action="retention_purge")[0]
    assert entry["actor"] == "operator:test" and entry["detail"]["days"] == 30


def test_retention_endpoint_uses_env_and_requires_operator(monkeypatch):
    _chat("oi")
    assert client.post("/admin/retention/purge", json={"days": 30}).status_code == 403
    assert client.post("/admin/retention/purge", headers=OP).status_code == 400  # sem dias e sem env
    monkeypatch.setenv("MEMORY_RETENTION_DAYS", "30")
    out = client.post("/admin/retention/purge", headers=OP).json()
    assert out["days"] == 30 and out["purged"]["conversations"] == 0  # nada tem 30 dias
    assert client.post("/admin/retention/purge", json={"days": 0}, headers=OP).status_code == 422
    assert get_store().audit_entries(action="retention_purge")[0]["actor"] == "operator:admin"


def test_retention_cli(monkeypatch, capsys):
    monkeypatch.delenv("MEMORY_RETENTION_DAYS", raising=False)
    assert store_cli(["purge"]) == 2
    monkeypatch.setenv("MEMORY_RETENTION_DAYS", "90")
    assert store_cli(["purge", "--actor", "cli:test"]) == 0
    assert '"conversations": 0' in capsys.readouterr().out
    assert get_store().audit_entries(action="retention_purge")[0]["actor"] == "cli:test"


def test_audit_log_is_append_only():
    store = get_store()
    store.audit("operator:ana", "handoff_reply", "T-1")
    with pytest.raises(store.IntegrityError, match="só de inclusão"), store._db() as conn:
        conn.execute("UPDATE audit_log SET actor = 'x'")
    with pytest.raises(store.IntegrityError, match="só de inclusão"), store._db() as conn:
        conn.execute("DELETE FROM audit_log")
    assert store.audit_entries()[0]["actor"] == "operator:ana"


def test_operator_reply_is_audited():
    ticket = _chat("Quero falar com um atendente")["handoff"]["ticket_id"]
    client.post(f"/handoffs/{ticket}/reply", json={"answer": "Resolvido."}, headers=OP)
    entry = client.get("/audit", headers=OP).json()[0]
    assert (entry["actor"], entry["action"], entry["target"]) == ("operator:admin", "handoff_reply", ticket)
    assert client.get("/audit").status_code == 403
