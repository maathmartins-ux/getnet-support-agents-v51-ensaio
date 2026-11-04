"""HITL que retoma o PLANO: depois da resposta do operador, os passos pendentes do plano original rodam.

Ponta a ponta (TestClient): pedido composto; a parte de Knowledge (faq) estoura o tempo do nó → o cliente recebe a
parte respondida (pedido) e o caso vai ao humano com budget_exhausted. Enquanto espera, nova mensagem é anexada ao
caso e escrita não fica proposta. O operador responde → o faq roda na hora e a mensagem traz as duas partes.
"""
import threading

from fastapi.testclient import TestClient

from app import actions, cases, supervisor
from app.agents import AgentResult, faq_agent
from app.api import app
from app.auth import issue_token
from app.store import get_store

client = TestClient(app)
OP = {"X-Operator-Token": "test-operator"}


def auth(user="u1"):
    return {"Authorization": f"Bearer {issue_token(user)}"}


def chat(message, conv=None, user="u1"):
    r = client.post("/chat", json={"message": message, "conversation_id": conv}, headers=auth(user))
    assert r.status_code == 200, r.text
    return r.json()


def test_operator_reply_runs_the_pending_knowledge_step(monkeypatch):
    # só o 1º faq é lento (espera 5 s): 1 s de teto estoura ele e deixa folga ao records do mesmo turno; com 0,2 s, a
    # máquina carregada (check e outra suíte juntos) estourou também o records do 3º turno e o caso escalou
    monkeypatch.setenv("NODE_TIMEOUT_S", "1")
    release, calls = threading.Event(), []

    def faq_slow_once(ctx):
        calls.append(1)
        if len(calls) == 1:
            release.wait(5)
            return AgentResult("faq", "ok", text="tarde demais")
        return faq_agent(ctx)

    monkeypatch.setitem(supervisor.AGENTS, "faq", faq_slow_once)
    try:
        r1 = chat("Qual o prazo de entrega? E onde está meu pedido 1002?")
    finally:
        release.set()
    monkeypatch.delenv("NODE_TIMEOUT_S")  # dali em diante, o teto padrão: o resto do teste não mede tempo
    conv, ticket = r1["conversation_id"], r1["handoff"]["ticket_id"]
    assert r1["handoff"]["reason"] == "budget_exhausted" and "budget:node_timeout->escalation" in r1["replans"]
    assert "em separação" in r1["answer"] and "dias úteis" not in r1["answer"]  # entrega a parte respondida
    assert cases.pending(ticket)["steps"] == ["faq"]

    # enquanto o caso está com o humano: mensagem anexada, escrita não fica proposta
    r2 = chat("E pode cancelar o pedido 1002?", conv)
    assert r2["pending_action"] is None and r2["handoff"] == {"required": False, "reason": "case_open",
                                                                "ticket_id": ticket}
    assert ticket in r2["answer"] and "Para cancelar" not in r2["answer"]
    assert cases.notes(ticket) == ["E pode cancelar o pedido 1002?"]
    held = [a for a in _actions(conv) if a["tool"] == "cancel_record"]
    assert held and all(a["status"] == "on_hold" for a in held)
    assert actions.confirm_action(held[0]["id"], "u1") == {"ok": False, "error": "already_on_hold"}

    # operador responde → o plano retoma: o faq pendente roda agora
    out = client.post(f"/handoffs/{ticket}/reply", json={"answer": "Verifiquei: seu pedido sai amanhã."},
                      headers=OP).json()
    resumed = out["resumed"]
    assert resumed["resumed_steps"] == ["faq"] and resumed["route"] == ["human", "faq"]
    assert "sai amanhã" in resumed["answer"] and "dias úteis" in resumed["answer"]
    msgs = client.get(f"/conversations/{conv}", headers=auth()).json()["messages"]
    assert msgs[-1]["intent"] == "resumed" and "dias úteis" in msgs[-1]["content"]
    assert cases.pending(ticket) is None  # retomado uma vez só

    # caso respondido: a conversa volta ao normal (escrita volta a ser proposta)
    r3 = chat("Pode cancelar o pedido 1002?", conv)
    assert r3["pending_action"] and not r3["handoff"]["required"]


def test_resume_without_pending_plan_only_drafts_the_message():
    r0 = chat("Quero falar com um atendente")
    out = client.post(f"/handoffs/{r0['handoff']['ticket_id']}/reply", json={"answer": "Olá, posso ajudar."},
                      headers=OP).json()
    assert out["resumed"]["resumed_steps"] == [] and out["resumed"]["answer"].endswith("Olá, posso ajudar.")


def test_pending_plan_is_taken_once():
    from app.agents import Context

    ctx = Context(text="Qual o prazo?", language="pt", user_id="u1", conversation_id="c9", intent="faq")
    cases.save_pending("T-x", ctx, ["faq"])
    cases.save_pending("T-x", ctx, ["records"])  # outro turno pendente no mesmo caso soma os passos
    assert cases.pending("T-x")["steps"] == ["faq", "records"]
    assert cases.take_pending("T-x")["steps"] == ["faq", "records"] and cases.take_pending("T-x") is None


def test_llm_escalating_before_the_knowledge_part_leaves_it_pending(monkeypatch):
    from fakes import fake_llm, resp, text, tool_use

    llm, _ = fake_llm([resp("tool_use", tool_use("escalation_agent", {"reason": "cliente irritado"})),
                       resp("end_turn", text("Encaminhei."))])
    monkeypatch.setattr(supervisor, "get_llm", lambda role="agent": llm)
    r = chat("Qual o prazo de entrega? E onde está meu pedido 1002?")
    assert r["route"] == ["router", "escalation"]
    assert cases.pending(r["handoff"]["ticket_id"])["steps"] == ["faq", "records"]


def _actions(conv):
    with get_store()._db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM actions WHERE conversation_id = ?", (conv,))]
