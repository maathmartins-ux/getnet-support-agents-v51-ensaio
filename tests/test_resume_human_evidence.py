"""Retomada com a resposta humana como EVIDÊNCIA (AgentResult "human") e o resto do plano continuando, também no
escalonamento simples por falha (não só orçamento estourado). Ponta a ponta com TestClient, nos dois backends.

Cenário: domínio em que o faq DEPENDE do records (como o manual do terminal depende do modelo do terminal). O records
falha → o caso vai ao humano e o faq, que precisaria do fato que faltou, espera. O operador responde → o "human" abre a
rota, o faq roda com a resposta nos fatos e nas dicas de busca, e a mensagem traz as duas partes. Uma vez só.
"""
from fakes import fake_llm, resp, text
from fastapi.testclient import TestClient

from app import cases, domain, supervisor
from app.agents import AgentResult, faq_agent
from app.api import app
from app.auth import issue_token
from app.llm import LLMError
from app.store import get_store

client = TestClient(app)
OP = {"X-Operator-Token": "test-operator"}
ASK = "Qual o prazo de entrega? E onde está meu pedido 1002?"


def auth(user="u1"):
    return {"Authorization": f"Bearer {issue_token(user)}"}


def chat(message, conv=None):
    r = client.post("/chat", json={"message": message, "conversation_id": conv}, headers=auth())
    assert r.status_code == 200, r.text
    return r.json()


def _faq_depends_on_records(monkeypatch, faq=None):
    d = domain.active()
    monkeypatch.setattr(d, "PLANS", {**d.PLANS, "multi": ["records", "faq"]})
    monkeypatch.setattr(d, "DEPENDS", {"faq": {"records"}})
    monkeypatch.setitem(supervisor.AGENTS, "records", lambda ctx: AgentResult("records", "error", reason="tool_error"))
    seen: list[dict] = []

    def faq_spy(ctx):
        seen.append(dict(ctx.facts))
        return (faq or faq_agent)(ctx)

    monkeypatch.setitem(supervisor.AGENTS, "faq", faq_spy)
    return seen


def test_plain_escalation_defers_dependents_and_the_human_answer_feeds_them(monkeypatch):
    seen = _faq_depends_on_records(monkeypatch)
    r1 = chat(ASK)
    ticket, conv = r1["handoff"]["ticket_id"], r1["conversation_id"]
    assert r1["handoff"]["required"] and r1["handoff"]["reason"] == "records_tool_error"
    assert r1["route"] == ["router", "records", "escalation"] and seen == []  # o faq NÃO rodou sem o fato
    assert "records:escalated->defer['faq']" in r1["replans"]
    assert cases.pending(ticket)["steps"] == ["faq"]

    out = client.post(f"/handoffs/{ticket}/reply", json={"answer": "Seu pedido 1002 sai do estoque amanhã."},
                      headers=OP)
    resumed = out.json()["resumed"]
    assert resumed["route"] == ["human", "faq"] and resumed["resumed_steps"] == ["faq"]
    assert seen[0]["operator_answer"] == "Seu pedido 1002 sai do estoque amanhã."  # evidência chegou ao agente
    assert "Seu pedido 1002 sai do estoque amanhã." in seen[0]["query_hints"]
    assert "sai do estoque amanhã" in resumed["answer"] and "dias úteis" in resumed["answer"]
    assert resumed["unsupported_numbers"] == []
    msgs = client.get(f"/conversations/{conv}", headers=auth()).json()["messages"]
    assert [m["role"] for m in msgs][-2:] == ["human_agent", "assistant"] and msgs[-1]["intent"] == "resumed"

    # uma retomada só: 2ª resposta recusada, plano já consumido, faq não roda de novo
    again = client.post(f"/handoffs/{ticket}/reply", json={"answer": "de novo"}, headers=OP)
    assert again.status_code == 404 and cases.pending(ticket) is None and len(seen) == 1


def test_resumed_step_that_still_fails_does_not_reopen_the_case(monkeypatch):
    _faq_depends_on_records(monkeypatch, faq=lambda ctx: AgentResult("faq", "insufficient", reason="no_source"))
    r1 = chat(ASK)
    ticket = r1["handoff"]["ticket_id"]
    resumed = client.post(f"/handoffs/{ticket}/reply", json={"answer": "Verifiquei o pedido."},
                          headers=OP).json()["resumed"]
    assert resumed["route"] == ["human", "faq"]  # sem "escalation": nada de laço humano → retomada → humano
    assert get_store().list_tickets("open") == [] and "Verifiquei o pedido." in resumed["answer"]


def test_llm_supervisor_sees_the_human_answer_and_fallback_keeps_it(monkeypatch):
    seen = _faq_depends_on_records(monkeypatch)
    ticket = chat(ASK)["handoff"]["ticket_id"]
    # retomada com supervisor LLM: 1ª chamada cai (LLMError) → motor de tabela, com a evidência humana preservada
    llm, msgs = fake_llm([LLMError("overloaded", kind="overloaded")])
    monkeypatch.setattr(supervisor, "get_llm", lambda role="agent": llm)
    resumed = client.post(f"/handoffs/{ticket}/reply", json={"answer": "Pedido sai amanhã."},
                          headers=OP).json()["resumed"]
    assert "Resposta do atendente humano" in msgs.sent[0]["messages"][0]["content"]
    assert "Pedido sai amanhã." in msgs.sent[0]["messages"][0]["content"]
    assert resumed["route"] == ["human", "faq"] and seen[-1]["operator_answer"] == "Pedido sai amanhã."
    assert get_store().list_tickets("open") == []  # fallback não perdeu o "resume_of": não reescalou


def test_llm_supervisor_answer_after_human_evidence(monkeypatch):
    _faq_depends_on_records(monkeypatch)
    ticket = chat(ASK)["handoff"]["ticket_id"]
    llm, _ = fake_llm([resp("end_turn", text("Com a confirmação do atendente: o pedido sai amanhã."))])
    monkeypatch.setattr(supervisor, "get_llm", lambda role="agent": llm)
    resumed = client.post(f"/handoffs/{ticket}/reply", json={"answer": "Pedido sai amanhã."},
                          headers=OP).json()["resumed"]
    assert resumed["route"] == ["human"] and "Com a confirmação do atendente" in resumed["answer"]


def test_escalation_without_remaining_steps_still_records_the_human_step():
    r0 = chat("Quero falar com um atendente")
    out = client.post(f"/handoffs/{r0['handoff']['ticket_id']}/reply", json={"answer": "Olá, posso ajudar."},
                      headers=OP).json()["resumed"]
    assert out["route"] == ["human"] and out["resumed_steps"] == []
