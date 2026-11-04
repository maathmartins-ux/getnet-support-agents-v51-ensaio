"""Supervisor com o domínio do desafio (frente R): replan, dependent (records → faq) e partial, offline."""
import pytest

from app import supervisor
from app.agents import AgentResult, Context
from app.observability import new_trace_id


@pytest.fixture(autouse=True)
def _challenge(domain_data):
    new_trace_id()  # orçamento por turno zerado


def ctx(text="Minha maquininha não conecta", intent="troubleshoot"):
    return Context(text=text, language="pt", user_id="cliente1988", conversation_id="c-dom-sup", intent=intent)


def stub(monkeypatch, name, status, calls, seen=None, **kw):
    def agent(c):
        calls.append(name)
        if seen is not None:
            seen[name] = dict(c.facts)
        return AgentResult(name, status, **kw)
    monkeypatch.setitem(supervisor.AGENTS, name, agent)


def plan(intent):
    from app import domain
    return domain.active().PLANS[intent]


# --- replan: sem fonte → humano; general nunca escala -----------------------------------------------------------
def test_replan_knowledge_without_source_goes_to_the_human(monkeypatch):
    calls: list = []
    stub(monkeypatch, "faq", "insufficient", calls, reason="not_in_sources")
    stub(monkeypatch, "escalation", "ok", calls, text="Encaminhei a um atendente.")
    out = supervisor.run(plan("knowledge"), ctx("Vocês têm maquininha à prova d'água?", "knowledge"), confidence=0.9)
    assert out.route == ["faq", "escalation"] and out.replans


def test_general_without_data_never_escalates(monkeypatch):
    calls: list = []
    stub(monkeypatch, "faq", "insufficient", calls, reason="not_in_sources")
    stub(monkeypatch, "escalation", "ok", calls)
    out = supervisor.run(plan("general"), ctx("Vai chover amanhã?", "general"), confidence=0.9)
    assert "escalation" not in out.route and not any(r.handoff for r in out.results)


# --- dependent: troubleshoot lê o terminal; o achado dele traz o manual, com o fato do records -------------------
def test_troubleshoot_runs_records_then_faq_with_the_terminal_facts(monkeypatch):
    # rodada 11: o plano do troubleshoot é só o records; o manual (faq) entra pelo achado (`needs`)
    calls: list = []
    seen: dict = {}
    stub(monkeypatch, "records", "ok", calls, seen, text="T1988B offline (chip, sem sinal).",
         facts={"terminal_id": "T1988B", "connection": "chip"},
         needs=[{"agent": "faq", "why": "terminal offline: passos do manual", "hint": "maquininha não conecta"}])
    stub(monkeypatch, "faq", "ok", calls, seen, text="Manual: confira o chip e o sinal.")
    out = supervisor.run(plan("troubleshoot"), ctx(), confidence=0.85)
    assert plan("troubleshoot") == ["records"]
    assert calls == ["records", "faq"] and out.route == ["records", "faq"]
    assert seen["faq"].get("terminal_id") == "T1988B"  # o faq viu o achado do records


def test_need_from_records_brings_the_manual_when_the_plan_lacked_it(monkeypatch):
    calls: list = []
    stub(monkeypatch, "records", "ok", calls, text="T1988B está offline.", facts={"terminal_id": "T1988B"},
         needs=[{"agent": "faq", "why": "terminal offline: passos do manual", "hint": "maquininha não conecta"}])
    stub(monkeypatch, "faq", "ok", calls, text="Manual: reinicie e confira o chip.")
    out = supervisor.run(plan("support"), ctx("O T1988B está online?", "support"), confidence=0.85)
    assert out.route == ["records", "faq"]


def test_records_failure_defers_the_dependent_manual(monkeypatch):
    # sem o dado do records não há achado: o manual (que dependia dele) não roda e o caso vai ao humano
    calls: list = []
    stub(monkeypatch, "records", "error", calls, reason="tool_error")
    stub(monkeypatch, "faq", "ok", calls, text="Manual.")
    stub(monkeypatch, "escalation", "ok", calls, text="Encaminhei.")
    out = supervisor.run(plan("troubleshoot"), ctx(), confidence=0.85)
    assert "faq" not in calls and "escalation" in out.route


# --- partial do Knowledge é resposta, não humano ----------------------------------------------------------------
def test_partial_knowledge_is_the_answer_and_does_not_escalate(monkeypatch):
    calls: list = []
    stub(monkeypatch, "faq", "partial", calls, reason="partial",
         text="Há antecipação automática e pontual [doc-1]. A taxa exata depende do seu contrato.")
    stub(monkeypatch, "escalation", "ok", calls)
    out = supervisor.run(plan("knowledge"), ctx("Como funciona a antecipação?", "knowledge"), confidence=0.9)
    assert out.route == ["faq"] and "escalation" not in calls and not any(r.handoff for r in out.results)
    assert "depende do seu contrato" in out.results[0].text
