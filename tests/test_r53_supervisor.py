"""R53 item 3 — supervisor: "partial" é resposta (nunca escala por si) e o insufficient do atalho vai ao LLM.

V5 ao vivo: 24 de 30 execuções oficiais usaram a tabela (atalho de plano de 1 passo) e o faq "insufficient" escalou
pelo FALLBACK fixo, sem decisão observada do supervisor LLM. Offline a tabela continua igual.
"""
import pytest
from fakes import fake_llm, resp, text, tool_use

from app import supervisor
from app.agents import AgentResult, Context
from app.llm import get_llm
from app.observability import new_trace_id, record_llm_usage


@pytest.fixture(autouse=True)
def _fast_path_on(monkeypatch):
    """Estes testes cobrem o atalho de 1 passo, desligado por padrão desde o kit v5.5 (perfil Skywalker)."""
    monkeypatch.setenv("SUPERVISOR_FAST", "on")


def ctx(text_="Qual a taxa do débito?", intent="faq", **facts):
    c = Context(text=text_, language="pt", user_id="u1", conversation_id="c-r53", intent=intent)
    c.facts.update(facts)
    return c


def use_llm(monkeypatch, llm):
    monkeypatch.setattr(supervisor, "get_llm", lambda role="agent": llm)


def stub(monkeypatch, name, status, calls=None, **kw):
    def agent(c):
        if calls is not None:
            calls.append(name)
        return AgentResult(name, status, **kw)
    monkeypatch.setitem(supervisor.AGENTS, name, agent)


PARTIAL = dict(text="A taxa do débito é 1,99% [doc-1]. A fonte não traz a taxa do crédito.", reason="partial")


@pytest.fixture(autouse=True)
def _fresh_turn():
    new_trace_id()  # orçamento por turno zerado


# --- partial é resposta ----------------------------------------------------------------------------------------
def test_partial_on_the_offline_table_is_not_escalated(monkeypatch):
    assert not get_llm("supervisor").enabled  # CI: sem LLM
    stub(monkeypatch, "faq", "partial", **PARTIAL)
    out = supervisor.run(["faq"], ctx(), confidence=0.95)
    assert out.route == ["faq"] and out.replans == [] and not any(r.handoff for r in out.results)


def test_partial_in_a_two_step_plan_keeps_the_plan_and_does_not_escalate(monkeypatch):
    stub(monkeypatch, "faq", "partial", **PARTIAL)
    stub(monkeypatch, "records", "ok", text="Pedido 1002: enviado.")
    out = supervisor.run(["faq", "records"], ctx("taxa e pedido 1002?", "multi"), confidence=0.8)
    assert out.route == ["faq", "records"] and out.replans == []


def test_partial_on_the_fast_path_is_the_answer_with_the_human_offer_and_no_llm_call(monkeypatch):
    llm, msgs = fake_llm([])  # qualquer chamada ao supervisor LLM quebraria o teste
    use_llm(monkeypatch, llm)
    stub(monkeypatch, "faq", "partial", **PARTIAL)
    out = supervisor.run(["faq"], ctx(), confidence=0.95)
    assert msgs.sent == [] and out.engine == "fast_path" and out.route == ["faq"]
    assert out.results[0].text.startswith("A taxa do débito é 1,99%")
    assert out.results[0].text.endswith(supervisor.OFFER_HUMAN["pt"])  # diz o que falta e oferece o humano


def test_partial_in_the_llm_engine_does_not_mark_a_handoff_reason(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_FAST", "off")
    llm, _ = fake_llm([resp("tool_use", tool_use("faq_agent", {"query": "taxa"})), resp("end_turn", text("ok"))])
    use_llm(monkeypatch, llm)
    stub(monkeypatch, "faq", "partial", **PARTIAL)
    c = ctx()
    out = supervisor.run(["faq"], c, confidence=0.95)
    assert out.route == ["faq"] and c.handoff_reason is None


# --- insufficient no atalho vai ao supervisor LLM -------------------------------------------------------------
def test_fast_path_insufficient_is_decided_by_the_llm_supervisor_with_the_result_in_view(monkeypatch):
    llm, msgs = fake_llm([resp("end_turn", text("Não achei isso na base. Posso encaminhar a um atendente."))])
    use_llm(monkeypatch, llm)
    calls: list = []
    stub(monkeypatch, "faq", "insufficient", calls, reason="no_source", text="")
    out = supervisor.run(["faq"], ctx("Qual a capital da Mongólia?", standalone="Qual a capital da Mongólia?"),
                         confidence=0.95)
    assert calls == ["faq"] and len(msgs.sent) == 1  # o faq não roda de novo; o modelo decide uma vez
    assert out.engine == "llm" and out.route == ["faq"] and out.answer.startswith("Não achei")
    assert out.replans == ["faq:no_source->supervisor_llm"] and not any(r.handoff for r in out.results)
    first = msgs.sent[0]["messages"][0]["content"]
    assert "faq_agent →" in first and '"status": "insufficient"' in first and "Não chame faq_agent" in first


def test_llm_supervisor_may_still_escalate_after_the_fast_path(monkeypatch):
    llm, msgs = fake_llm([resp("tool_use", tool_use("escalation_agent", {"reason": "sem fonte"})),
                          resp("end_turn", text("Abri um caso."))])
    use_llm(monkeypatch, llm)
    stub(monkeypatch, "faq", "insufficient", reason="no_source")
    c = ctx("Qual a capital da Mongólia?")
    out = supervisor.run(["faq"], c, confidence=0.95)
    assert out.route == ["faq", "escalation"] and out.results[-1].handoff.reason == "faq_no_source"
    assert out.engine == "llm" and c.facts["escalation_note"] == "sem fonte"


def test_llm_supervisor_cannot_rerun_the_failed_agent(monkeypatch):
    llm, msgs = fake_llm([resp("tool_use", tool_use("faq_agent", {"query": "de novo"})),
                          resp("end_turn", text("Sem resposta na base."))])
    use_llm(monkeypatch, llm)
    calls: list = []
    stub(monkeypatch, "faq", "insufficient", calls, reason="no_source")
    out = supervisor.run(["faq"], ctx(), confidence=0.95)
    assert calls == ["faq"] and out.route == ["faq"]  # faq → faq não está em ALLOWED: o código recusa
    refused = msgs.sent[1]["messages"][-1]["content"][0]
    assert refused["is_error"] and "transição não permitida" in refused["content"]


def test_handover_is_bounded_by_the_turn_budget(monkeypatch):
    monkeypatch.setenv("MAX_MODEL_CALLS", "1")
    llm, msgs = fake_llm([])
    use_llm(monkeypatch, llm)

    def faq(c):
        record_llm_usage("claude-sonnet-5-5", 10, 10)  # o próprio faq gastou a chamada do turno
        return AgentResult("faq", "insufficient", reason="no_source")
    monkeypatch.setitem(supervisor.AGENTS, "faq", faq)
    out = supervisor.run(["faq"], ctx(), confidence=0.95)
    assert msgs.sent == [] and out.budget == "model_calls" and out.route == ["faq", "escalation"]
    assert out.results[-1].handoff.reason == "budget_exhausted"


def test_offline_insufficient_keeps_the_table_fallback(monkeypatch):
    assert not get_llm("supervisor").enabled  # CI: sem LLM, a tabela de sempre
    stub(monkeypatch, "faq", "insufficient", reason="no_source")
    out = supervisor.run(["faq"], ctx("Qual a capital da Mongólia?"), confidence=0.95)
    assert out.engine == "table" and out.route == ["faq", "escalation"]
    assert out.replans == ["faq:no_source->escalation"] and out.results[-1].handoff.reason == "faq_no_source"


def test_error_on_the_fast_path_and_ablation_off_stay_on_the_table(monkeypatch):
    llm, msgs = fake_llm([])
    use_llm(monkeypatch, llm)
    stub(monkeypatch, "faq", "error", reason="tool_error")
    out = supervisor.run(["faq"], ctx(), confidence=0.95)  # error não é insufficient: FALLBACK da tabela
    assert msgs.sent == [] and out.route == ["faq", "escalation"]
    monkeypatch.setenv("SUPERVISOR_REPLAN", "off")  # ablação: plano fixo, sem desvio nem decisão do LLM
    new_trace_id()
    stub(monkeypatch, "faq", "insufficient", reason="no_source")
    out = supervisor.run(["faq"], ctx(), confidence=0.95)
    assert msgs.sent == [] and out.route == ["faq"]


def test_no_escalation_intent_on_the_fast_path_is_not_handed_over(monkeypatch):
    from app import domain

    monkeypatch.setattr(domain.active(), "NO_ESCALATION", {"faq"})
    llm, msgs = fake_llm([])
    use_llm(monkeypatch, llm)
    stub(monkeypatch, "faq", "insufficient", reason="no_source")
    out = supervisor.run(["faq"], ctx(), confidence=0.95)  # a tabela não desviaria: nada a decidir
    assert msgs.sent == [] and out.route == ["faq"]


def test_llm_supervisor_sees_the_standalone_question(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_FAST", "off")
    llm, msgs = fake_llm([resp("end_turn", text("ok"))])
    use_llm(monkeypatch, llm)
    supervisor.run(["faq"], ctx("e a outra?", standalone="Qual a taxa da Get Smart?"), confidence=0.95)
    assert "Pergunta completa (router): Qual a taxa da Get Smart?" in msgs.sent[0]["messages"][0]["content"]
