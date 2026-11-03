"""Replanejamento por ACHADO (needs) e orçamento por turno (MAX_MODEL_CALLS, MAX_TURN_USD, NODE_TIMEOUT_S).

Caso "dependent" do domínio de exemplo: "Quando chega meu pedido 1002?" → o records vê "em separação" → a resposta
só fica completa com o prazo da política (faq). Sem o achado, o plano do router ([records]) para no status.
"""
import json
import threading
import time

from fakes import fake_llm, resp, text, tool_use

from app import supervisor
from app.agents import AgentResult, Context
from app.observability import new_trace_id, record_llm_usage
from app.pipeline import handle
from app.schemas import ChatRequest


def ctx(text_, intent="records", user="u1", conv="c1"):
    return Context(text=text_, language="pt", user_id=user, conversation_id=conv, intent=intent)


def use_llm(monkeypatch, llm):
    monkeypatch.setattr(supervisor, "get_llm", lambda role="agent": llm)
    # estes testes exercitam o laço do supervisor LLM: sem o atalho de plano de 1 passo (test_supervisor_fast.py)
    monkeypatch.setenv("SUPERVISOR_FAST", "off")


# --- needs: tabela ------------------------------------------------------------------------------------------
def test_table_inserts_the_step_a_finding_asks_for():
    out = supervisor.run(["records"], ctx("Quando chega meu pedido 1002?"))
    assert out.route == ["records", "faq"]
    assert out.replans[0].startswith("records:need->faq")
    assert out.results[0].needs[0]["agent"] == "faq"
    assert "dias úteis" in out.results[1].text  # a parte que só o 2º agente tinha


def test_no_finding_no_extra_step():
    assert supervisor.run(["records"], ctx("Quando chega meu pedido 1001?")).route == ["records"]  # já entregue
    assert supervisor.run(["records"], ctx("Onde está meu pedido 1002?")).route == ["records"]  # não pediu prazo


def test_no_needs_mode_only_reacts_to_failure(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_REPLAN", "no_needs")
    out = supervisor.run(["records"], ctx("Quando chega meu pedido 1002?"))
    assert out.route == ["records"] and out.replans == []
    failed = supervisor.run(["faq"], ctx("Qual a capital da Mongólia?", "faq"))
    assert failed.route == ["faq", "escalation"]  # falha continua replanejando


def test_need_outside_allowed_or_unknown_is_ignored(monkeypatch):
    monkeypatch.setitem(supervisor.AGENTS, "records", lambda c: AgentResult(
        "records", "ok", text="x", needs=[{"agent": "bogus"}, {"agent": "records", "why": "de novo"}]))
    out = supervisor.run(["records"], ctx("pedido 1002"))
    assert out.route == ["records"] and out.replans == []


def test_need_from_tool_result_and_hint_reaches_the_agent(monkeypatch):
    seen = {}
    tool_out = {"ok": True, "data": {}, "needs": [{"agent": "faq", "why": "terminal offline", "hint": "manual"}]}
    monkeypatch.setitem(supervisor.AGENTS, "records",
                        lambda c: AgentResult("records", "ok", text="offline", evidence=[json.dumps(tool_out)]))

    def faq(c):
        seen.update(ask=c.facts["ask"]["faq"], hints=list(c.facts["query_hints"]))
        return AgentResult("faq", "ok", text="manual")

    monkeypatch.setitem(supervisor.AGENTS, "faq", faq)
    out = supervisor.run(["records"], ctx("meu terminal"))
    assert out.route == ["records", "faq"] and out.replans == ["records:need->faq (terminal offline)"]
    assert seen == {"ask": "manual", "hints": ["manual"]}


def test_insufficient_with_need_takes_the_need_instead_of_escalating(monkeypatch):
    monkeypatch.setitem(supervisor.AGENTS, "faq", lambda c: AgentResult(
        "faq", "insufficient", reason="depends_on_model", needs=[{"agent": "records", "why": "regra por modelo"}]))
    monkeypatch.setitem(supervisor.AGENTS, "records", lambda c: AgentResult("records", "ok", text="modelo X"))
    out = supervisor.run(["faq"], ctx("x", "faq"))
    assert out.route == ["faq", "records"] and "escalation" not in out.route


def test_needs_respect_max_steps(monkeypatch):
    for name, nxt in (("faq", "records"), ("records", "faq")):
        monkeypatch.setitem(supervisor.AGENTS, name, lambda c, n=name, x=nxt: AgentResult(
            n, "ok", text=n, needs=[{"agent": x}]))
    out = supervisor.run(["faq"], ctx("x", "faq"))
    assert out.route == ["faq", "records"]  # records pede faq, que já rodou: não há laço


def test_pipeline_dependent_case_end_to_end():
    r = handle(ChatRequest(message="Quando chega meu pedido 1002?"), "u1")
    assert r.route == ["router", "records", "faq"] and any(x.startswith("records:need->faq") for x in r.replans)
    assert "em separação" in r.answer and "dias úteis" in r.answer and not r.handoff.required


# --- needs: LLM (cliente falso) ----------------------------------------------------------------------------
def test_llm_engine_inserts_needed_step_even_if_model_does_not_ask(monkeypatch):
    new_trace_id()
    llm, msgs = fake_llm([
        resp("tool_use", tool_use("records_agent", {"request": "quando chega o pedido 1002"})),
        resp("end_turn", text("Seu pedido 1002 está em separação; o prazo é de 3 a 5 dias úteis.")),
    ])
    use_llm(monkeypatch, llm)
    out = supervisor.run(["records"], ctx("Quando chega meu pedido 1002?"))
    assert out.engine == "llm" and out.route == ["records", "faq"]
    assert any(r.startswith("records:need->faq") for r in out.replans)
    last_user = msgs.sent[1]["messages"][-1]["content"]
    assert last_user[0]["type"] == "tool_result" and json.loads(last_user[0]["content"])["needs"][0]["agent"] == "faq"
    assert last_user[-1]["type"] == "text" and "faq_agent" in last_user[-1]["text"]  # texto só depois dos results


def test_llm_engine_no_needs_mode_does_not_insert(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_REPLAN", "no_needs")
    llm, _ = fake_llm([resp("tool_use", tool_use("records_agent", {"request": "1002"})),
                       resp("end_turn", text("Em separação."))])
    use_llm(monkeypatch, llm)
    assert supervisor.run(["records"], ctx("Quando chega meu pedido 1002?")).route == ["records"]


# --- orçamento por turno -----------------------------------------------------------------------------------
def test_model_call_budget_delivers_the_answered_part_and_hands_off_the_rest(monkeypatch):
    new_trace_id()
    monkeypatch.setenv("MAX_MODEL_CALLS", "1")
    llm, msgs = fake_llm([resp("tool_use", tool_use("faq_agent", {"query": "prazo de entrega"})),
                          resp("end_turn", text("nunca chamado"))])
    use_llm(monkeypatch, llm)
    out = supervisor.run(["faq", "records"], ctx("Qual o prazo? E o pedido 1002?", "multi"))
    assert len(msgs.sent) == 1 and out.budget == "model_calls" and out.deferred == ["records"]
    assert out.route == ["faq", "escalation"] and out.answer is None  # pipeline junta a parte respondida
    assert "dias úteis" in out.results[0].text
    assert out.results[-1].handoff.reason == "budget_exhausted" and "budget:model_calls->escalation" in out.replans


def test_usd_budget_stops_the_llm_loop(monkeypatch):
    new_trace_id()
    monkeypatch.setenv("MAX_TURN_USD", "0.0001")
    llm, msgs = fake_llm([resp("tool_use", tool_use("faq_agent", {"query": "prazo"}), i=10_000)])
    use_llm(monkeypatch, llm)
    out = supervisor.run(["faq"], ctx("Qual o prazo de entrega?", "faq"))
    assert out.budget == "usd" and len(msgs.sent) == 1 and out.route[-1] == "escalation"


def test_table_budget_checked_before_each_step(monkeypatch):
    new_trace_id()
    monkeypatch.setenv("MAX_MODEL_CALLS", "1")
    record_llm_usage("claude-haiku-5-5", 10, 10)  # o router já gastou a chamada do turno
    out = supervisor.run(["faq"], ctx("Qual o prazo de entrega?", "faq"))
    assert out.route == ["escalation"] and out.deferred == ["faq"]


def test_node_timeout_keeps_the_fast_part(monkeypatch):
    monkeypatch.setenv("NODE_TIMEOUT_S", "0.2")
    release, finished = threading.Event(), threading.Event()

    def slow(c):
        release.wait(5)
        finished.set()
        return AgentResult("faq", "ok", text="tarde demais")

    monkeypatch.setitem(supervisor.AGENTS, "faq", slow)
    t0 = time.perf_counter()
    out = supervisor.run(["faq", "records"], ctx("Qual o prazo? E o pedido 1002?", "multi"))
    assert time.perf_counter() - t0 < 1.2
    assert out.budget == "node_timeout" and out.deferred == ["faq"]
    assert out.route == ["faq", "records", "escalation"] and "em separação" in out.results[1].text
    assert out.results[0].reason == "node_timeout" and out.results[-1].handoff.reason == "budget_exhausted"
    release.set()  # a thread abandonada termina antes do fim do teste (sem log em stream fechado)
    assert finished.wait(5)


def test_budget_without_escalation_for_no_escalation_intents(monkeypatch):
    from app.domain import example

    new_trace_id()
    monkeypatch.setattr(example, "NO_ESCALATION", {"general"})
    monkeypatch.setenv("MAX_MODEL_CALLS", "1")
    record_llm_usage("claude-haiku-5-5", 10, 10)
    out = supervisor.run(["faq"], ctx("Vai chover?", "general"))
    assert out.route == [] and out.budget == "model_calls"


def test_budget_defaults_are_sane(monkeypatch):
    assert supervisor.max_model_calls() >= 10 and 0 < supervisor.max_turn_usd() <= 1
    assert supervisor.node_timeout_s() >= 30
    monkeypatch.setenv("MAX_TURN_USD", "abc")
    assert supervisor.max_turn_usd() == supervisor.MAX_TURN_USD
