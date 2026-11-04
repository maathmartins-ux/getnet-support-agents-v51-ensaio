"""Quem decidiu cada passo: `decided_by` ("llm" | "router" | "code" | "operator") e `why` na árvore de passos.

Quem lê o trace separa o que o supervisor LLM escolheu (tool call), o que veio do plano do router e rodou sem consultar
o supervisor LLM (atalho ou motor de tabela), o que uma regra do código impôs (achado `needs`, escalada garantida,
FALLBACK, orçamento, passo antecipado, aviso de caso aberto) e a resposta da operadora. Cada caminho do laço marca o
passo onde o registra; a marca não muda rota, contexto nem o que o modelo lê, e passo sem marca sai "não registrado".
O DEMO e a transcrição dizem "decidido por: ..." em cada passo, e a operadora simulada da transcrição responde com
chave pessoal (o nome dela vai para o passo e para a auditoria); o que a transcrição diz dela vem do POST, não do
roteiro.
"""
import ast
import importlib.util
import json
import os
import threading
import uuid
from pathlib import Path

import pytest
from fakes import fake_llm, resp, text, tool_use
from fastapi.testclient import TestClient

from app import domain, supervisor
from app.agents import AgentResult, Context, escalation_agent
from app.api import app
from app.auth import issue_token
from app.llm import LLMError, get_llm
from app.observability import new_trace_id, record_llm_usage
from app.resume import human_result
from app.store import get_store

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("demo_md", ROOT / "scripts" / "demo_md.py")
demo_md = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo_md)

NO_SOURCE = "Qual a capital da Mongólia?"
DECIDERS = {supervisor.DECIDED_LLM, supervisor.DECIDED_ROUTER, supervisor.DECIDED_CODE, supervisor.DECIDED_OPERATOR}


@pytest.fixture(autouse=True)
def _fresh_turn():
    new_trace_id()  # orçamento por turno zerado


def ctx(text_="Qual o prazo de entrega?", intent="faq", conv=None, **facts):
    """Conversa nova por padrão: o caso que um turno abre poria o turno seguinte da mesma conversa em espera."""
    c = Context(text=text_, language="pt", user_id="u1", conversation_id=conv or f"c-{uuid.uuid4().hex[:8]}",
                intent=intent)
    c.facts.update(facts)
    return c


def use_llm(monkeypatch, script, fast="off"):
    llm, msgs = fake_llm(script)
    monkeypatch.setattr(supervisor, "get_llm", lambda role="agent": llm)
    monkeypatch.setenv("SUPERVISOR_FAST", fast)
    return msgs


def stub(monkeypatch, name, status, **kw):
    monkeypatch.setitem(supervisor.AGENTS, name, lambda c: AgentResult(name, status, **kw))


def decisions(out) -> list[tuple]:
    """(agente, decided_by, why) de cada passo, pela mesma visão que vai em ChatResponse.steps."""
    views = [supervisor.step_view(r) for r in out.results]
    return [(v["agent"], v.get("decided_by"), v.get("why")) for v in views]


# --- supervisor LLM ------------------------------------------------------------------------------------------
def test_step_from_a_supervisor_tool_call_is_decided_by_the_llm(monkeypatch):
    use_llm(monkeypatch, [resp("tool_use", tool_use("faq_agent", {"query": "prazo"})), resp("end_turn", text("Ok."))])
    out = supervisor.run(["faq"], ctx())
    assert out.engine == "llm" and decisions(out) == [("faq", "llm", None)]


# --- achado (needs) ------------------------------------------------------------------------------------------
def test_step_inserted_by_a_finding_is_the_code_in_both_engines(monkeypatch):
    ask = "Quando chega meu pedido 1002?"  # records vê "em separação" → o prazo vem da política (faq)
    offline = supervisor.run(["records"], ctx(ask, "records"))
    assert offline.route == ["records", "faq"] and offline.replans[0].startswith("records:need->faq")
    assert decisions(offline) == [("records", "router", "plan"), ("faq", "code", "needs")]
    use_llm(monkeypatch, [resp("tool_use", tool_use("records_agent", {"request": "pedido 1002"})),
                          resp("end_turn", text("Ok."))])
    live = supervisor.run(["records"], ctx(ask, "records"))
    assert live.engine == "llm" and live.route == ["records", "faq"]
    assert decisions(live) == [("records", "llm", None), ("faq", "code", "needs")]  # o modelo não pediu o faq


# --- escalada garantida --------------------------------------------------------------------------------------
def test_escalation_the_code_guarantees_is_the_code(monkeypatch):
    use_llm(monkeypatch, [resp("tool_use", tool_use("faq_agent", {"query": "carros"})),
                          resp("end_turn", text("Não achei isso. Posso encaminhar?"))])
    stub(monkeypatch, "faq", "insufficient", reason="not_in_sources")
    out = supervisor.run(["faq"], ctx("A loja vende carros?"))
    assert out.route == ["faq", "escalation"] and out.replans[-1].endswith("(código: ninguém respondeu)")
    assert decisions(out) == [("faq", "llm", None), ("escalation", "code", "escalation")]


def test_escalation_the_llm_asks_for_is_the_llm(monkeypatch):
    use_llm(monkeypatch, [resp("tool_use", tool_use("escalation_agent", {"reason": "pedido explícito"})),
                          resp("end_turn", text("Abri um caso."))])
    out = supervisor.run(["escalation"], ctx("Quero um atendente", "human_request"))
    assert decisions(out) == [("escalation", "llm", None)]


# --- motor de tabela: o plano é do router, o FALLBACK é do código ---------------------------------------------
def test_table_engine_runs_the_router_plan_and_its_fallback_is_the_code(monkeypatch):
    assert not get_llm("supervisor").enabled  # CI: sem LLM, a tabela
    stub(monkeypatch, "faq", "insufficient", reason="no_source")
    out = supervisor.run(["faq"], ctx(NO_SOURCE))
    assert out.replans == ["faq:no_source->escalation"]
    assert decisions(out) == [("faq", "router", "plan"), ("escalation", "code", "table")]
    # o supervisor LLM cai: o motor de tabela refaz o turno com o plano do router
    use_llm(monkeypatch, [LLMError("api_status_529", "api_status")])
    out = supervisor.run(["faq"], ctx(NO_SOURCE))
    assert out.engine == "table" and decisions(out) == [("faq", "router", "plan"), ("escalation", "code", "table")]


def test_router_plan_of_two_steps_is_the_router_in_the_table(monkeypatch):
    stub(monkeypatch, "faq", "ok", text="Prazo de 3 a 5 dias úteis [faq-entrega].")
    stub(monkeypatch, "records", "ok", text="Pedido 1002 em separação.")
    out = supervisor.run(["faq", "records"], ctx("Qual o prazo? E o pedido 1002?", "multi"))
    assert decisions(out) == [("faq", "router", "plan"), ("records", "router", "plan")]


def test_router_uncertain_escalation_is_the_code_table(monkeypatch):
    stub(monkeypatch, "faq", "ok", text="Talvez [faq-entrega].")
    out = supervisor.run(["faq"], ctx("talvez prazo?"), confidence=0.2)
    assert out.replans == ["router:low_confidence(0.20)->escalation"]
    assert decisions(out) == [("faq", "router", "plan"), ("escalation", "code", "table")]


# --- atalho de 1 passo ---------------------------------------------------------------------------------------
def test_fast_path_step_is_the_router_plan_and_the_handover_shows_both_sides(monkeypatch):
    use_llm(monkeypatch, [], fast="on")  # roteiro vazio: o atalho não chama o supervisor LLM
    stub(monkeypatch, "faq", "ok", text="Prazo de 3 a 5 dias úteis [faq-entrega].")
    out = supervisor.run(["faq"], ctx(), confidence=0.95)
    assert out.engine == "fast_path" and decisions(out) == [("faq", "router", "fast_path")]
    # insufficient no atalho: o supervisor LLM decide o passo seguinte
    use_llm(monkeypatch, [resp("tool_use", tool_use("escalation_agent", {"reason": "sem fonte"})),
                          resp("end_turn", text("Abri um caso."))], fast="on")
    stub(monkeypatch, "faq", "insufficient", reason="no_source")
    out = supervisor.run(["faq"], ctx(NO_SOURCE), confidence=0.95)
    assert out.engine == "llm" and decisions(out) == [("faq", "router", "fast_path"), ("escalation", "llm", None)]
    # o LLM cai depois do atalho: a tabela aplica o FALLBACK que tinha passado adiante
    use_llm(monkeypatch, [LLMError("api_status_529", "api_status")], fast="on")
    out = supervisor.run(["faq"], ctx(NO_SOURCE), confidence=0.95)
    assert out.engine == "table"
    assert decisions(out) == [("faq", "router", "fast_path"), ("escalation", "code", "table")]


# --- orçamento, passo antecipado, operador, espera ----------------------------------------------------------
def test_budget_escalation_is_the_code(monkeypatch):
    monkeypatch.setenv("MAX_MODEL_CALLS", "1")
    use_llm(monkeypatch, [], fast="on")

    def faq(c):
        record_llm_usage("claude-sonnet-5-5", 10, 10)  # o próprio faq gastou a chamada do turno
        return AgentResult("faq", "insufficient", reason="no_source")

    monkeypatch.setitem(supervisor.AGENTS, "faq", faq)
    out = supervisor.run(["faq"], ctx(), confidence=0.95)
    assert out.budget == "model_calls"
    assert decisions(out) == [("faq", "router", "fast_path"), ("escalation", "code", "budget")]


def test_step_run_before_the_first_llm_round_is_the_code(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_LEAD", "on")
    monkeypatch.setattr(domain.active(), "DEPENDS", {"faq": {"records"}})
    stub(monkeypatch, "records", "ok", text="T1 offline")
    use_llm(monkeypatch, [resp("tool_use", tool_use("faq_agent", {"query": "T1 offline"})),
                          resp("end_turn", text("Resposta composta."))])
    out = supervisor.run(["records", "faq"], ctx("maquininha não conecta", "troubleshoot"), confidence=0.9)
    assert decisions(out) == [("records", "code", "lead"), ("faq", "llm", None)]


def test_operator_answer_is_the_operator_and_the_hold_notice_is_the_code():
    out = supervisor.run(["faq"], ctx(resume_of="T-1"), prior=[human_result("O prazo é de 2 dias.", "ana")])
    assert out.route[:1] == ["human"]
    assert decisions(out) == [("human", "operator", None), ("faq", "router", "plan")]  # sem "code/operator"
    opener = ctx("Quero um atendente", "human_request", conv="c-hold")
    opener.handoff_reason = "user_request"
    escalation_agent(opener)  # caso aberto nesta conversa
    held = supervisor.run(["faq"], ctx(conv="c-hold"))
    assert decisions(held) == [("faq", "router", "plan"), ("hold", "code", "hold")]


# --- nenhum passo da tabela sai sem marca --------------------------------------------------------------------
def _plan(monkeypatch):
    return supervisor.run(["faq"], ctx())


def _parallel(monkeypatch):
    return supervisor.run(["faq", "records"], ctx("Qual o prazo? E o pedido 1002?", "multi"))


def _finding(monkeypatch):
    return supervisor.run(["records"], ctx("Quando chega meu pedido 1002?", "records"))


def _fallback(monkeypatch):
    stub(monkeypatch, "faq", "insufficient", reason="no_source")
    return supervisor.run(["faq"], ctx(NO_SOURCE))


def _uncertain(monkeypatch):
    return supervisor.run(["faq"], ctx("talvez prazo?"), confidence=0.2)


def _budget_before_the_step(monkeypatch):
    monkeypatch.setenv("MAX_MODEL_CALLS", "1")
    record_llm_usage("claude-haiku-5-5", 10, 10)  # o router já gastou a chamada do turno
    return supervisor.run(["faq"], ctx())


def _node_timeout(monkeypatch):
    monkeypatch.setenv("NODE_TIMEOUT_S", "1")  # o lento espera 2 s; 1 s deixa folga ao records com a máquina carregada
    release, finished = threading.Event(), threading.Event()

    def slow(c):
        release.wait(2)
        finished.set()
        return AgentResult("faq", "ok", text="tarde demais")

    monkeypatch.setitem(supervisor.AGENTS, "faq", slow)
    try:
        return supervisor.run(["faq", "records"], ctx("Qual o prazo? E o pedido 1002?", "multi"))
    finally:
        release.set()  # a thread abandonada termina antes do fim do teste (sem log em stream fechado)
        finished.wait(2)


def _fast_path_then_llm_down(monkeypatch):
    use_llm(monkeypatch, [LLMError("api_status_529", "api_status")], fast="on")
    stub(monkeypatch, "faq", "insufficient", reason="no_source")
    return supervisor.run(["faq"], ctx(NO_SOURCE), confidence=0.95)


def _resume(monkeypatch):
    return supervisor.run(["faq"], ctx(resume_of="T-1"), prior=[human_result("O prazo é de 2 dias.", "ana")])


TABLE_PATHS = [_plan, _parallel, _finding, _fallback, _uncertain, _budget_before_the_step, _node_timeout,
               _fast_path_then_llm_down, _resume]


@pytest.mark.parametrize("path", TABLE_PATHS, ids=lambda f: f.__name__.strip("_"))
def test_no_step_of_the_table_engine_leaves_without_a_mark(monkeypatch, path):
    out = path(monkeypatch)
    assert out.results
    for view in (supervisor.step_view(r) for r in out.results):
        assert view.get("decided_by") in DECIDERS, view
        assert ("why" in view) == (view["decided_by"] in (supervisor.DECIDED_ROUTER, supervisor.DECIDED_CODE)), view


def test_the_table_presumes_no_reason_for_an_unmarked_queue_entry():
    out = supervisor._table_loop(["faq"], ctx(), supervisor.Outcome())  # fila sem motivo registrado
    assert out.route == ["faq"] and decisions(out) == [("faq", None, None)]  # "não registrado", nada presumido


# --- a marca não muda comportamento --------------------------------------------------------------------------
def test_the_mark_reaches_neither_the_model_nor_the_agents_context(monkeypatch):
    msgs = use_llm(monkeypatch, [resp("tool_use", tool_use("records_agent", {"request": "pedido 1002"})),
                                 resp("end_turn", text("Ok."))])
    c = ctx("Quando chega meu pedido 1002?", "records")
    out = supervisor.run(["records"], c)
    assert [d[1] for d in decisions(out)] == ["llm", "code"]
    sent = json.dumps([m["messages"] for m in msgs.sent], ensure_ascii=False, default=str)
    assert "decided" not in sent and "decided" not in json.dumps(c.facts, ensure_ascii=False, default=str)
    assert all("decided" not in r.for_supervisor() for r in out.results)


def test_unmarked_step_carries_no_presumed_decision():
    view = supervisor.step_view(AgentResult("faq", "ok", text="x"))
    assert "decided_by" not in view and "why" not in view
    unknown = supervisor.step_view(supervisor._decide(AgentResult("faq", "ok"), "regra_que_nao_existe"))
    assert "decided_by" not in unknown  # fora do vocabulário também não vira decisão de alguém


def _rules_in(node) -> set[str]:
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _decided_names(node) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and n.id.startswith("DECIDED_")}


def test_every_rule_the_supervisor_records_is_declared_and_named_in_the_demo():
    """Vocabulário fechado nos dois sentidos: o motivo que cada caminho passa a _record/_decide (argumento `by`) ou
    grava na fila (`queued_by`) é exatamente ROUTER_WHY + CODE_WHY, sem motivo morto nem motivo fora da lista; quem
    decide sem motivo (supervisor LLM, operadora) entra pela constante; e o DEMO tem palavras para cada motivo (motivo
    novo sem rótulo apareceria cru para quem lê)."""
    tree = ast.parse((ROOT / "src" / "app" / "supervisor.py").read_text(encoding="utf-8"))
    used: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("_record", "_decide"):
            position = 4 if node.func.id == "_record" else 1  # _record(name, result, ctx, out, by) · _decide(r, by)
            by = [*node.args[position:position + 1], *(k.value for k in node.keywords if k.arg == "by")]
            used |= set().union(*map(_rules_in, by))
            names |= set().union(*map(_decided_names, by))
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Subscript) and getattr(t.value, "attr", "")
                                                  == "queued_by" for t in node.targets):
            used |= _rules_in(node.value)
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "update" \
                and getattr(node.func.value, "attr", "") == "queued_by":
            used |= _rules_in(node)
    assert used == set(supervisor.CODE_WHY) | set(supervisor.ROUTER_WHY)
    assert not set(supervisor.CODE_WHY) & set(supervisor.ROUTER_WHY)  # um motivo, um dono
    assert names == {"DECIDED_LLM", "DECIDED_OPERATOR"}
    assert set(demo_md.WHY_LABEL) == set(supervisor.CODE_WHY)
    assert set(demo_md.ROUTER_LABEL) == set(supervisor.ROUTER_WHY)


def test_chat_steps_say_who_decided_each_step():
    got = TestClient(app).post("/chat", json={"message": "Quando chega meu pedido 1002?"},
                               headers={"Authorization": f"Bearer {issue_token('u1')}"}).json()
    assert [(s["agent"], s["decided_by"], s.get("why")) for s in got["steps"]] == [
        ("records", "router", "plan"), ("faq", "code", "needs")]


# --- DEMO e transcrição --------------------------------------------------------------------------------------
def test_step_tree_says_who_decided_each_step():
    lines = demo_md.step_tree([
        {"agent": "records", "status": "ok", "ms": 812.4, "tools": [], "decided_by": "llm"},
        {"agent": "faq", "status": "ok", "ms": 900.0, "tools": [], "decided_by": "router", "why": "fast_path"},
        {"agent": "faq", "status": "ok", "ms": 20.0, "tools": [], "decided_by": "router", "why": "plan"},
        {"agent": "faq", "status": "partial", "reason": "partial_coverage", "ms": 5.0, "tools": [],
         "decided_by": "code", "why": "needs"},
        {"agent": "escalation", "status": "ok", "ms": 3.2, "tools": [], "decided_by": "code", "why": "escalation"},
        {"agent": "human", "status": "ok", "ms": None, "operator": "ana", "tools": [], "decided_by": "operator"},
        {"agent": "faq", "status": "ok", "ms": 1.0, "tools": []},  # gravado sem o campo
        {"agent": "faq", "status": "ok", "ms": 1.0, "tools": [], "decided_by": "code", "why": "regra_nova"},
    ])
    assert lines[0] == "1. **records** · ok · 812 ms · decidido por: supervisor LLM (tool call)"
    assert lines[1].endswith("900 ms · decidido por: plano do router, rodado pelo atalho sem o supervisor")
    assert lines[2].endswith("20 ms · decidido por: plano do router, rodado pelo motor de tabela")
    assert lines[3].endswith("5.0 ms · decidido por: código (achado `needs` de outro especialista)")
    assert lines[4].endswith("decidido por: código (escalada garantida: ninguém resolveu)")
    assert lines[5] == "6. **human** · ok · decidido por: operadora `ana`"  # o nome sai uma vez só
    assert lines[6].endswith("decidido por: não registrado")  # nada presumido
    assert lines[7].endswith("decidido por: código (regra_nova)")
    rules = demo_md.step_tree([{"agent": "faq", "status": "ok", "tools": [], "decided_by": "router", "why": "plan"}],
                              demo_md.ROUTER_RULES)
    assert rules == ["1. **faq** · ok · decidido por: plano do router (regras, sem LLM), rodado pelo motor de tabela"]


def test_demo_page_explains_the_decision_and_shows_it_per_step():
    step = {"agent": "faq", "status": "ok", "ms": 40.0, "tools": [], "decided_by": "router", "why": "fast_path"}
    row = {"id": "official-01", "run": 0, "message": "Quando chega?", "route": ["router", "faq"],
           "steps": [step], "checks": {}}
    text = demo_md.render({"rows": [row], "provider": "anthropic"}, "official", "abc1234", "hoje")
    assert demo_md.DECIDED_LEGEND in text and demo_md.RULES_NOTE not in text
    legend = demo_md.DECIDED_LEGEND  # o plano pode vir do router LLM ou da regra que o substitui: o rótulo não diz LLM
    assert "a regra que o substitui" in legend and "o supervisor LLM não foi consultado" in legend
    assert "1. **faq** · ok · 40 ms · decidido por: plano do router, rodado pelo atalho sem o supervisor" in text
    assert demo_md.DECIDED_LEGEND not in demo_md.render({"rows": [{**row, "steps": []}]}, "official", "x", "hoje")
    offline = demo_md.render({"rows": [row], "provider": "offline"}, "official", "abc1234", "hoje")
    assert demo_md.RULES_NOTE in offline and "plano do router (regras, sem LLM), rodado pelo atalho" in offline


def test_transcript_operator_answers_with_a_personal_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPERATOR_KEYS", raising=False)
    keys: list[tuple] = []
    real = demo_md.demo_operator_key
    monkeypatch.setattr(demo_md, "demo_operator_key", lambda: keys.append(real()) or keys[-1])
    path = tmp_path / "t.jsonl"
    path.write_text('{"user": "u1"}\n{"say": "Quero falar com um atendente sobre o prazo", "operator": '
                    '"O prazo é de 3 a 5 dias úteis.", "wait_s": 5, "operator_after_s": 0.1}\n', encoding="utf-8")
    md = demo_md.transcript(path, "abc1234", "hoje")
    assert "Quem responde o caso é a operadora simulada `operadora_demo`" in md
    assert ("*(a operadora simulada `operadora_demo` responde pelo console, com chave pessoal, durante a espera: "
            "\"O prazo é de 3 a 5 dias úteis.\")*") in md
    assert "2. **human** · ok · decidido por: operadora `operadora_demo`" in md
    assert "decidido por: plano do router (regras, sem LLM), rodado pelo motor de tabela" in md  # CI: sem LLM
    assert demo_md.RULES_NOTE in md
    assert "`admin`" not in md and "operador respondeu durante a espera" in md
    audit = get_store().audit_entries(10, "handoff_reply")
    assert [a["actor"] for a in audit] == ["operator:operadora_demo"]
    assert "registrado por `operator:operadora_demo` (canal console)" in md  # a transcrição mostra a auditoria
    key, entry = keys[0]
    assert key not in md and entry.split(":", 1)[1] not in md  # nem a chave nem o hash vão para o documento
    assert "OPERATOR_KEYS" not in os.environ  # a chave só valeu durante a transcrição


def test_transcript_says_the_operator_did_not_answer_when_the_post_failed(tmp_path, monkeypatch):
    monkeypatch.delenv("OPERATOR_KEYS", raising=False)
    _, entry = demo_md.demo_operator_key()
    monkeypatch.setattr(demo_md, "demo_operator_key", lambda: ("chave-que-nao-bate", entry))  # o console recusa
    path = tmp_path / "t.jsonl"
    path.write_text('{"user": "u1"}\n{"say": "Quero falar com um atendente", "operator": "Resposta.", "wait_s": 1, '
                    '"operator_after_s": 0.05}\n', encoding="utf-8")
    md = demo_md.transcript(path, "abc1234", "hoje")
    assert "*(a operadora simulada `operadora_demo` não respondeu: status 403)*" in md
    assert "responde pelo console" not in md and "decidido por: operadora" not in md
    assert not get_store().audit_entries(10, "handoff_reply")


def test_transcript_without_a_case_says_so_and_cites_the_operator_only_when_scripted(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text('{"user": "u1"}\n{"say": "Onde está meu pedido 1002?", "operator": "Resposta.", "wait_s": 1}\n',
                    encoding="utf-8")
    md = demo_md.transcript(path, "abc1234", "hoje")
    assert "*(a operadora simulada `operadora_demo` não respondeu: nenhum caso de atendimento novo na fila)*" in md
    assert "responde pelo console" not in md
    plain = tmp_path / "p.jsonl"
    plain.write_text('{"user": "u1"}\n{"say": "Onde está meu pedido 1002?"}\n', encoding="utf-8")
    assert "operadora simulada" not in demo_md.transcript(plain, "abc1234", "hoje")


def test_operator_note_reads_what_happened_not_the_script():
    live = [{"agent": "human", "decided_by": "operator"}]
    note = demo_md.operator_note
    assert "responde pelo console, com chave pessoal, durante a espera: \"ok\"" in note(
        {"ticket": "T-1", "status": 200}, "T-1", live, "ok")
    assert "depois da espera do turno" in note({"ticket": "T-1", "status": 200}, "T-1", [], "ok")
    assert "não respondeu ao caso deste turno: respondeu o caso T-2" in note({"ticket": "T-2", "status": 200}, "T-1",
                                                                              live, "ok")
    assert "não respondeu: o caso T-1 ficou na fila" in note({"ticket": "T-1", "status": None}, "T-1", [], "ok")
    assert "não respondeu: o caso T-9 ficou na fila" in note({"ticket": None, "status": None}, "T-9", [], "ok")
    assert "não respondeu: nenhum caso de atendimento" in note({"ticket": None, "status": None}, None, [], "ok")
    assert "não respondeu: status 404" in note({"ticket": "T-1", "status": 404}, "T-1", [], "ok")


def test_transcript_keeps_the_operator_keys_the_environment_already_had(tmp_path, monkeypatch):
    monkeypatch.setenv("OPERATOR_KEYS", "ana:" + "0" * 64)
    seen: list[str] = []
    monkeypatch.setattr(demo_md, "_transcript",
                        lambda path, sha, when, key: seen.append(os.environ["OPERATOR_KEYS"]) or "")
    demo_md.transcript(tmp_path / "t.jsonl", "abc1234", "hoje")
    assert seen[0].startswith("ana:" + "0" * 64 + ",operadora_demo:")
    assert os.environ["OPERATOR_KEYS"] == "ana:" + "0" * 64
