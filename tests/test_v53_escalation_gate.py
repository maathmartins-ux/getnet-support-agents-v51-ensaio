"""Escalada só com motivo real (kit v5.3 final): falta parcial ou de um só especialista vira OFERTA do humano.

Pós-morte V5: 40 de 49 falhas de handoff eram escalada sem precisar; Skywalker (nota 10) só leva ao humano decisão de
caso, risco ou pedido do cliente. Ensaio v5.3: heldout 7, memory 8 e dependent 3 linhas ainda escalavam por
faq_not_in_sources / records_no_data.
"""
import pytest

from app import agents, supervisor
from app.agents import AgentResult, Context
from app.store import get_store


def ctx(text_, intent="faq", conv="c-gate"):
    return Context(text=text_, language="pt", user_id="u1", conversation_id=conv, intent=intent)


@pytest.mark.parametrize("reason", ["faq_partial_coverage"])
def test_missing_piece_offers_human_and_opens_no_case(reason):
    c = ctx("E qual foi o valor dela?", conv=f"c-{reason}")
    c.handoff_reason = reason
    out = agents.escalation_agent(c)
    assert out.handoff is None and out.status == "ok"
    assert "atendente humano" in out.text and out.facts["escalation_offered"] == reason
    assert get_store().ticket_for(c.conversation_id, "open") is None


def test_no_source_and_nothing_answered_still_goes_to_human():
    # enunciado: humano quando o sistema não consegue resolver (split replan: produto que não existe)
    c = ctx("A Getnet tem maquininha que aceita criptomoeda?", conv="c-none")
    c.handoff_reason = "faq_not_in_sources"
    assert agents.escalation_agent(c).handoff.required


def test_faq_without_manual_after_records_answered_offers_instead():
    # official-08: records trouxe o diagnóstico da recusa; o faq não tinha o manual
    c = ctx("Minha maquininha mostra erro de transação recusada", conv="c-08")
    c.handoff_reason = "faq_not_in_sources"
    c.facts["answered_by"] = ["records"]
    assert agents.escalation_agent(c).handoff is None


@pytest.mark.parametrize("reason", ["user_request", "records_tool_error", "budget_exhausted", "supervisor_decision",
                                    "unsupported_numbers", "records_no_data"])
def test_real_reasons_still_open_a_case(reason):
    c = ctx("Quero falar com um atendente", conv=f"c-real-{reason}")
    c.handoff_reason = reason
    out = agents.escalation_agent(c)
    assert out.handoff and out.handoff.required and out.handoff.ticket_id


def test_customer_asking_for_human_beats_the_gap_reason():
    c = ctx("Me passa para um humano", intent="human_request", conv="c-ask")
    c.handoff_reason = "faq_partial_coverage"
    assert agents.escalation_agent(c).handoff.required


def test_domain_hook_beats_the_gap_reason(monkeypatch):
    c2 = ctx("Não reconheço essa venda", conv="c-hook")
    c2.handoff_reason = "faq_partial_coverage"
    monkeypatch.setattr(agents.domain.active(), "must_escalate", lambda cx: "reconhe" in cx.text, raising=False)
    assert agents.escalation_agent(c2).handoff.required


def test_gate_off_restores_the_old_behaviour(monkeypatch):
    monkeypatch.setenv("ESCALATION_GATE", "off")
    c = ctx("E qual foi o valor dela?", conv="c-off")
    c.handoff_reason = "faq_partial_coverage"
    assert agents.escalation_agent(c).handoff.required


def test_table_fallback_records_no_data_goes_to_human(monkeypatch):
    # replan (venda que não existe): não resolver = humano
    monkeypatch.setenv("SUPERVISOR_FAST", "off")
    monkeypatch.setattr(supervisor, "get_llm", lambda role="agent": type("Off", (), {"enabled": False})())
    no_data = AgentResult("records", "insufficient", reason="no_data")
    monkeypatch.setitem(supervisor.AGENTS, "records", lambda c: no_data)
    out = supervisor.run(["records"], ctx("Quando cai a TX8888?", intent="records", conv="c-table"))
    assert out.route[-1] == "escalation" and out.results[-1].handoff.required


def test_code_escalates_when_llm_only_offered_and_nobody_answered():
    c = ctx("A Getnet tem maquininha de criptomoeda?", conv="c-enf")
    out = supervisor.Outcome(engine="llm")
    supervisor._record("faq", AgentResult("faq", "insufficient", reason="not_in_sources"), c, out)
    out.answer = "Não encontrei. Posso encaminhar a um atendente."
    supervisor._enforce_escalation(out, c)
    assert out.route == ["faq", "escalation"] and out.results[-1].handoff.required
    assert "->escalation (código" in out.replans[-1]


def test_code_does_not_escalate_when_someone_answered():
    c = ctx("Minha maquininha mostra erro de recusa", conv="c-enf2")
    out = supervisor.Outcome(engine="llm")
    supervisor._record("records", AgentResult("records", "ok", text="TX1007 recusada, código 51"), c, out)
    supervisor._record("faq", AgentResult("faq", "insufficient", reason="not_in_sources"), c, out)
    supervisor._enforce_escalation(out, c)
    assert out.route == ["records", "faq"]


def test_supervisor_records_who_answered():
    c = ctx("x", conv="c-ans")
    supervisor._record("records", AgentResult("records", "ok", text="T1988B offline"), c, supervisor.Outcome())
    supervisor._record("faq", AgentResult("faq", "insufficient", reason="not_in_sources"), c, supervisor.Outcome())
    assert c.facts["answered_by"] == ["records"]
