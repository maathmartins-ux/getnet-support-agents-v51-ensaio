"""Replanejamento por ACHADO (needs) e orçamento por turno (MAX_MODEL_CALLS, MAX_TURN_USD, NODE_TIMEOUT_S).

Caso "dependent" do domínio de exemplo: "Quando chega meu pedido 1002?" → o records vê "em separação" → a resposta
só fica completa com o prazo da política (faq). Sem o achado, o plano do router ([records]) para no status.
No motor de tabela o código insere o passo pedido; no motor LLM o achado é informação: o modelo decide, com UMA volta
de lembrete se encerrar sem chamar o agente pedido, e o achado ignorado de novo fica contado (`need_ignored`).
"""
import json
import threading
import time

from fakes import fake_llm, resp, text, tool_use

from app import supervisor
from app.agents import AgentResult, Context
from app.domain import example
from app.llm import LLMError
from app.observability import METRICS, new_trace_id, record_llm_usage
from app.pipeline import handle
from app.schemas import ChatRequest

ASK = "Quando chega meu pedido 1002?"  # records vê "em separação" e a pergunta é de prazo: achado → faq
WHY = example.NEEDS_BY_STATUS["em separação"]["why"]
HINT = example.NEEDS_BY_STATUS["em separação"]["hint"]


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


def _records_with_raw_need(monkeypatch, why="terminal offline", hint="manual"):
    """records cujo resultado de tool traz `needs` cru (o pedido 1002 "em separação" + um achado da própria tool)."""
    tool_out = {"ok": True, "data": {"record_id": "1002", "status": "em separação"},
                "needs": [{"agent": "faq", "why": why, "hint": hint}]}
    monkeypatch.setitem(supervisor.AGENTS, "records",
                        lambda c: AgentResult("records", "ok", text="em separação", evidence=[json.dumps(tool_out)]))
    seen = {}

    def faq(c):
        seen.update(ask=c.facts["ask"]["faq"], hints=list(c.facts["query_hints"]))
        return AgentResult("faq", "ok", text="manual")

    monkeypatch.setitem(supervisor.AGENTS, "faq", faq)
    return seen


def test_raw_tool_need_counts_when_the_domain_has_no_filter(monkeypatch):
    monkeypatch.delattr(example, "needs_for")  # domínio sem `needs_for`: vale o `needs` que a tool devolveu
    seen = _records_with_raw_need(monkeypatch)
    out = supervisor.run(["records"], ctx("meu terminal"))
    assert out.route == ["records", "faq"] and out.replans == ["records:need->faq (terminal offline)"]
    assert seen == {"ask": "manual", "hints": ["manual"]}


def test_domain_filter_decides_no_symptom_no_faq(monkeypatch):
    """Com `needs_for` o domínio é o filtro: o `needs` cru da tool não entra por fora dele. Medido no ensaio: lido cru,
    32 das 75 inserções por achado foram em mensagens sem palavra de sintoma ("Show me my last 5 transactions")."""
    _records_with_raw_need(monkeypatch, why="achado cru da tool", hint="dica crua")
    plain = supervisor.run(["records"], ctx("Onde está meu pedido 1002?"))  # sem pergunta de prazo: sem achado
    assert plain.route == ["records"] and plain.replans == [] and plain.results[0].needs == []
    asked = supervisor.run(["records"], ctx(ASK))  # com a pergunta de prazo, o achado é o do filtro, não o cru
    assert asked.route == ["records", "faq"] and asked.results[0].needs == [{"agent": "faq", "why": WHY, "hint": HINT}]
    assert "cru" not in " ".join(asked.replans)


def test_two_findings_for_the_same_agent_join_why_and_hint(monkeypatch):
    """No official-08 do ensaio (recusa com terminal offline) o 2º achado, o da recusa, era descartado e o faq trouxe o
    manual do chip. Agora os dois chegam juntos, cada parte uma vez só."""
    connection = {"agent": "faq", "why": "terminal offline", "hint": "manual de conexão"}
    decline = {"agent": "faq", "why": "transação recusada", "hint": "orientação de recusa"}
    result = AgentResult("records", "ok", text="x", needs=[connection, decline, dict(connection)])
    joined = {"agent": "faq", "why": "terminal offline; transação recusada",
              "hint": "manual de conexão; orientação de recusa"}
    assert supervisor.collect_needs(result, ctx("x")) == [joined]
    seen = {}
    monkeypatch.setitem(supervisor.AGENTS, "records", lambda c: AgentResult(
        "records", "ok", text="offline e recusa", needs=[connection, decline]))
    monkeypatch.setitem(supervisor.AGENTS, "faq", lambda c: seen.update(ask=c.facts["ask"]["faq"]) or AgentResult(
        "faq", "ok", text="manual"))
    out = supervisor.run(["records"], ctx("meu terminal recusou"))
    assert out.route == ["records", "faq"] and seen["ask"] == "manual de conexão; orientação de recusa"
    assert out.replans == ["records:need->faq (terminal offline; transação recusada)"]


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


def test_table_engine_keeps_inserting_when_the_llm_is_down(monkeypatch):
    use_llm(monkeypatch, fake_llm([LLMError("api_status_529", "api_status")])[0])
    out = supervisor.run(["records"], ctx(ASK))
    assert out.engine == "table" and out.route == ["records", "faq"] and out.replans[0].startswith("records:need->faq")
    assert supervisor.step_view(out.results[0])["needs"] == [{"agent": "faq", "why": WHY, "outcome": "inserted"}]


# --- needs: LLM (cliente falso) ----------------------------------------------------------------------------
RECORDS_CALL = resp("tool_use", tool_use("records_agent", {"request": "quando chega o pedido 1002"}))
FAQ_CALL = resp("tool_use", tool_use("faq_agent", {"query": "prazo de entrega de pedido em separação"}, "tu2"))
FINAL = "Seu pedido 1002 está em separação; o prazo é de 3 a 5 dias úteis."


def _outcome(out) -> str | None:
    return (supervisor.step_view(out.results[0]).get("needs") or [{}])[0].get("outcome")


def test_llm_engine_the_model_decides_on_the_finding(monkeypatch):
    """O achado chega ao modelo no tool_result; o código não insere nada. O modelo chamou o faq: o passo é dele (llm) e
    o desvio do plano do router ([records]) é o replanejamento por achado."""
    new_trace_id()
    llm, msgs = fake_llm([RECORDS_CALL, FAQ_CALL, resp("end_turn", text(FINAL))])
    use_llm(monkeypatch, llm)
    out = supervisor.run(["records"], ctx(ASK))
    assert out.engine == "llm" and out.route == ["records", "faq"] and out.answer == FINAL
    assert [supervisor.step_view(r).get("decided_by") for r in out.results] == ["llm", "llm"]
    assert out.replans == [f"records:need->faq ({WHY})"] and _outcome(out) == "called"
    seen = msgs.sent[1]["messages"][-1]["content"]
    assert [b["type"] for b in seen] == ["tool_result"]  # só o resultado: nenhum passo inserido como texto
    assert json.loads(seen[0]["content"])["needs"] == [{"agent": "faq", "why": WHY, "hint": HINT}]
    assert len(msgs.sent) == 3 and "Achado sem resposta" not in json.dumps(msgs.sent[2]["messages"], default=str)


def test_llm_engine_reminds_once_when_the_model_ignores_the_finding(monkeypatch):
    new_trace_id()
    llm, msgs = fake_llm([RECORDS_CALL, resp("end_turn", text("Seu pedido 1002 está em separação.")), FAQ_CALL,
                          resp("end_turn", text(FINAL))])
    use_llm(monkeypatch, llm)
    out = supervisor.run(["records"], ctx(ASK))
    reminder = msgs.sent[2]["messages"][-1]
    assert reminder["role"] == "user" and "Achado sem resposta" in reminder["content"]
    assert "records_agent pediu faq_agent" in reminder["content"] and WHY in reminder["content"]
    assert f"dica: {HINT}" in reminder["content"]
    assert msgs.sent[2]["messages"][-2]["role"] == "assistant"  # a resposta ignorada fica na conversa, append-only
    assert out.route == ["records", "faq"] and out.answer == FINAL and _outcome(out) == "reminded"
    assert out.replans == [f"records:need->faq ({WHY})"]
    assert [supervisor.step_view(r).get("decided_by") for r in out.results] == ["llm", "llm"]


def test_llm_engine_ignored_finding_is_counted_and_the_turn_goes_on(monkeypatch, caplog):
    new_trace_id()
    before = METRICS.get("needs_ignored_total", agent="records", need="faq")
    llm, msgs = fake_llm([RECORDS_CALL, resp("end_turn", text("Em separação.")),
                          resp("end_turn", text("Seu pedido 1002 está em separação."))])
    use_llm(monkeypatch, llm)
    with caplog.at_level("INFO", logger="app"):
        out = supervisor.run(["records"], ctx(ASK))
    assert len(msgs.sent) == 3  # UMA volta de lembrete, não um laço
    assert out.route == ["records"] and out.replans == [] and out.answer == "Seu pedido 1002 está em separação."
    assert _outcome(out) == "ignored"
    assert METRICS.get("needs_ignored_total", agent="records", need="faq") == before + 1
    assert any(r.getMessage() == "need_ignored" for r in caplog.records)


def test_step_already_in_the_router_plan_is_not_a_replan(monkeypatch):
    """O faq que o plano do router já tinha (troubleshoot = records → faq no ensaio) não é replanejamento, nos dois
    motores: medido, 51 dos 75 passos inseridos por achado ao vivo eram esse faq, contado como "replanejou"."""
    monkeypatch.setattr(example, "DEPENDS", {"faq": {"records"}})  # o faq lê o que o records trouxe
    new_trace_id()
    table = supervisor.run(["records", "faq"], ctx(ASK))
    assert table.route == ["records", "faq"] and table.replans == [] and _outcome(table) == "planned"
    llm, _ = fake_llm([RECORDS_CALL, FAQ_CALL, resp("end_turn", text(FINAL))])
    use_llm(monkeypatch, llm)
    new_trace_id()
    live = supervisor.run(["records", "faq"], ctx(ASK))
    assert live.route == ["records", "faq"] and live.replans == [] and _outcome(live) == "called"


def test_finding_of_the_step_run_before_the_model_is_also_the_model_to_decide(monkeypatch):
    """Passo antecipado (SUPERVISOR_LEAD=on): o achado dele vai ao modelo na 1ª mensagem; o código não insere o faq."""
    monkeypatch.setenv("SUPERVISOR_LEAD", "on")
    monkeypatch.setattr(example, "DEPENDS", {"faq": {"records"}})
    llm, msgs = fake_llm([resp("end_turn", text("Em separação.")), FAQ_CALL, resp("end_turn", text(FINAL))])
    use_llm(monkeypatch, llm)
    out = supervisor.run(["records", "faq"], ctx(ASK))
    first = msgs.sent[0]["messages"][0]["content"]
    assert '"needs": [{"agent": "faq"' in first and "passo inserido" not in first
    assert "Achado sem resposta" in msgs.sent[1]["messages"][-1]["content"]  # encerrou sem o faq: o lembrete
    assert out.route == ["records", "faq"] and out.replans == [] and _outcome(out) == "reminded"
    assert [supervisor.step_view(r).get("decided_by") for r in out.results] == ["code", "llm"]


def test_llm_engine_no_needs_mode_hides_the_finding_and_does_not_remind(monkeypatch):
    """Braço no_needs da ablação: o modelo não recebe o achado e não há lembrete (o passo marca `hidden`)."""
    monkeypatch.setenv("SUPERVISOR_REPLAN", "no_needs")
    llm, msgs = fake_llm([RECORDS_CALL, resp("end_turn", text("Em separação."))])
    use_llm(monkeypatch, llm)
    out = supervisor.run(["records"], ctx(ASK))
    assert out.route == ["records"] and len(msgs.sent) == 2 and _outcome(out) == "hidden"
    assert json.loads(msgs.sent[1]["messages"][-1]["content"][0]["content"])["needs"] == []
    assert out.results[0].needs  # o achado existiu (a árvore de passos mostra onde disparou); só não foi ao modelo


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
    monkeypatch.setenv("NODE_TIMEOUT_S", "1")  # o lento espera 5 s; 1 s deixa folga ao records com a máquina carregada
    release, finished = threading.Event(), threading.Event()

    def slow(c):
        release.wait(5)
        finished.set()
        return AgentResult("faq", "ok", text="tarde demais")

    monkeypatch.setitem(supervisor.AGENTS, "faq", slow)
    t0 = time.perf_counter()
    out = supervisor.run(["faq", "records"], ctx("Qual o prazo? E o pedido 1002?", "multi"))
    assert time.perf_counter() - t0 < 3  # entrega sem esperar os 5 s do lento
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


def test_table_does_not_escalate_a_partial_turn_when_another_specialist_answered(monkeypatch):
    """Tabela: o faq pedido pelo achado volta sem fonte, mas o records já respondeu → responde com o records e oferece
    o humano (a regra do supervisor LLM); sem ninguém ter respondido, o FALLBACK continua escalando."""
    from app.agents import AgentResult

    monkeypatch.setitem(supervisor.AGENTS, "records", lambda c: AgentResult(
        "records", "ok", text="A venda TX0001 foi recusada: código 51 (saldo insuficiente).",
        needs=[{"agent": "faq", "why": "transação recusada", "hint": "transação recusada: orientação"}]))
    monkeypatch.setitem(supervisor.AGENTS, "faq", lambda c: AgentResult("faq", "insufficient", text="",
                                                                       reason="not_in_sources"))
    out = supervisor.run(["records"], ctx("Por que minha venda foi recusada?", "troubleshoot"), confidence=0.9)
    assert out.route == ["records", "faq"] and "escalation" not in out.route
    assert "atendente humano" in out.results[0].text and "código 51" in out.results[0].text

    out = supervisor.run(["faq"], ctx("Qual a taxa do plano X?", "knowledge"), confidence=0.9)
    assert "escalation" in out.route  # ninguém respondeu: vai ao humano como antes
