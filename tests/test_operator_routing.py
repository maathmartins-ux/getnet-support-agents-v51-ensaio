"""Roteamento por especialidade: o caso nasce com a especialidade do agente que falhou (ou da intenção), a fila de
cada operador mostra a dele primeiro, SLA vencido re-roteia para qualquer operador, e tudo fica na auditoria."""
import hashlib
import time

import pytest
from fastapi.testclient import TestClient

from app import actions, domain, supervisor
from app.agents import AgentResult
from app.api import app
from app.auth import issue_token
from app.routing import specialty_for
from app.store import get_store

client = TestClient(app)
ADMIN = {"X-Operator-Token": "test-operator"}
ANA, BRUNO = {"X-Operator-Token": "chave-da-ana-1234567890"}, {"X-Operator-Token": "chave-do-bruno-123456789"}


@pytest.fixture(autouse=True)
def operators(monkeypatch):
    digest = lambda k: hashlib.sha256(k.encode()).hexdigest()  # noqa: E731
    monkeypatch.setenv("OPERATOR_KEYS", f"ana:{digest(ANA['X-Operator-Token'])},"
                                        f"bruno:{digest(BRUNO['X-Operator-Token'])}")
    monkeypatch.setenv("OPERATOR_SKILLS", "ana:records|approval,bruno:faq")
    monkeypatch.setenv("OPERATOR_SHARED_TOKEN", "on")  # o admin compartilhado convive com as chaves (migração)


def chat(message, user="u1"):
    r = client.post("/chat", json={"message": message}, headers={"Authorization": f"Bearer {issue_token(user)}"})
    assert r.status_code == 200, r.text
    return r.json()


def test_ticket_specialty_comes_from_the_failing_agent_or_the_intent(monkeypatch):
    monkeypatch.setitem(supervisor.AGENTS, "records", lambda ctx: AgentResult("records", "error", reason="tool_error"))
    t1 = get_store().get_ticket(chat("Onde está meu pedido 1002?")["handoff"]["ticket_id"])
    assert t1["reason"] == "records_tool_error" and t1["specialty"] == "records"
    t2 = get_store().get_ticket(chat("Quero falar com um atendente", user="u2")["handoff"]["ticket_id"])
    assert t2["specialty"] == "human_request"
    d = domain.active()  # o domínio traduz agente/intenção para a especialidade da operação
    monkeypatch.setattr(d, "SPECIALTY_BY_AGENT", {"records": "conta"}, raising=False)
    monkeypatch.setattr(d, "SPECIALTY_BY_INTENT", {"human_request": "geral"}, raising=False)
    assert specialty_for("records", "records_tool_error") == "conta"
    assert specialty_for("human_request", "user_request") == "geral"
    assert specialty_for("faq", "budget_exhausted") == "faq"
    entry = next(e for e in get_store().audit_entries(action="ticket_routed") if e["target"] == t1["id"])
    assert entry["actor"] == "system:routing" and entry["detail"] == {"specialty": "records", "kind": "handoff"}


def test_approval_ticket_goes_to_the_approval_specialty():
    aid = get_store().create_action("c-ap", "u1", "refund_record", {"record_id": "1001"}, risk="high")
    ticket = actions.confirm_action(aid, "u1")["ticket_id"]
    assert get_store().get_ticket(ticket)["specialty"] == "approval"


def _queue(headers):
    r = client.get("/handoffs", headers=headers)
    assert r.status_code == 200
    return [(t["specialty"], t["lane"]) for t in r.json()]


def test_each_operator_sees_own_specialty_first_and_still_sees_the_rest():
    store = get_store()
    store.open_ticket("c-f", "u1", "faq_no_source", "s", specialty="faq")
    store.open_ticket("c-r", "u2", "records_tool_error", "s", specialty="records")
    assert _queue(ANA) == [("records", "own"), ("faq", "other")]
    assert _queue(BRUNO) == [("faq", "own"), ("records", "other")]
    assert [s for s, _ in _queue(ADMIN)] == ["faq", "records"]  # sem especialidade: ordem do store (mais antigo)


def test_sla_expiry_reroutes_to_any_operator_with_audit():
    store = get_store()
    old = store.open_ticket("c-old", "u1", "faq_no_source", "s", specialty="faq")
    store.open_ticket("c-new", "u2", "records_tool_error", "s", specialty="records")
    assert _queue(ANA)[0] == ("records", "own")
    out = client.post("/handoffs/sla-check", params={"now": time.time() + 10 ** 6}, headers=ADMIN).json()
    assert {t["id"] for t in out["escalated"]} >= {old["id"]}
    assert store.get_ticket(old["id"])["routed_to"] == "any"
    assert _queue(ANA)[0][1] == "any" and _queue(BRUNO)[0][1] == "any"  # topo da fila de todos
    rerouted = [e for e in store.audit_entries(action="ticket_rerouted") if e["target"] == old["id"]]
    assert rerouted and rerouted[0]["actor"] == "system:sla" and rerouted[0]["detail"]["to"] == "any"
    # roteamento é ordem, não permissão: bruno responde um caso de records
    reply = client.post(f"/handoffs/{store.ticket_for('c-new')['id']}/reply", json={"answer": "Feito."},
                        headers=BRUNO)
    assert reply.status_code == 200 and reply.json()["ticket"]["answered_by"] == "bruno"


def test_skills_in_the_store_override_env_and_changes_are_audited():
    assert client.get("/operators", headers=ANA).json()["skills"] == ["approval", "records"]
    assert client.put("/operators/bruno/skills", json={"skills": ["records"]}, headers=ANA).status_code == 403
    r = client.put("/operators/ana/skills", json={"skills": ["faq", "faq"]}, headers=ANA)
    assert r.status_code == 200 and r.json()["skills"] == ["faq"]
    assert client.put("/operators/bruno/skills", json={"skills": ["records"]}, headers=ADMIN).status_code == 200
    ops = client.get("/operators", headers=ADMIN).json()["operators"]
    assert ops["ana"] == ["faq"] and ops["bruno"] == ["records"]
    entry = get_store().audit_entries(action="operator_skills_set")[0]
    assert entry["actor"] == "operator:admin" and entry["target"] == "bruno"
    assert client.get("/operators").status_code == 403
