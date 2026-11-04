"""Onde vai o tempo e quem decide (evals/trace_stats.py + bloco `trace` do fill_readme): percentis do turno, SLO por
split, fatia de cada agente sobre o tempo do turno a que os passos pertencem (`turn_ms`), paralelo detectado por
linha, crash fora dos percentis, e passos decididos pelo supervisor LLM × vindos do plano do router × postos por regra
do código, no formato que o supervisor grava (llm sem `why`, router e code com `why`, operator fora da conta)."""
import json
import uuid
from pathlib import Path

import pytest
from fakes import fake_llm, resp, text, tool_use

from evals import run_evals, trace_stats
from scripts import fill_readme

ROOT = Path(__file__).resolve().parents[1]
TARGET = {"p50_s": 20.0, "p95_s": 45.0, "origin": {"SLO_P50_S": "padrão", "SLO_P95_S": "padrão"}}
SCOPE = "passos do turno, fora a resposta da operadora e o aviso de caso aberto"


@pytest.fixture(autouse=True)
def default_slo(monkeypatch):
    # SLO vem do env: um valor do shell de quem roda não pode mudar o que os testes esperam
    monkeypatch.delenv("SLO_P50_S", raising=False)
    monkeypatch.delenv("SLO_P95_S", raising=False)


def row(split, ms, steps=None, case_id=None, turn_ms=None, crash=None, blocked=False, load=None):
    return {"id": case_id or f"{split}-{ms:g}", "split": split, "ms": ms, "turn_ms": turn_ms, "crash": crash,
            "steps": [] if steps is None else steps, "blocked": blocked, "load": load}


# a carga da bateria integral do kit: 12 splits num processo, 8 workers, teto 8 (scripts/live_eval.sh), 4 CPUs
LOAD8 = {"cases_at_once": 8, "max_concurrent": 8, "workers": 8, "splits_in_process": 12, "cpus": 4}


def step(agent, ms, decided_by=None, why=None, **extra):
    """Um passo como `supervisor.step_view` o grava: `why` só quando veio (plano do router ou regra do código)."""
    out = {"agent": agent, "status": "ok", "reason": None, "ms": ms, "tools": [], **extra}
    if decided_by:
        out["decided_by"] = decided_by
    if why:
        out["why"] = why
    return out


def test_percentile_is_the_value_at_int_q_n_without_interpolation():
    assert trace_stats.percentile([], 0.5) is None
    assert trace_stats.percentile([4.0, 1.0, 3.0, 2.0], 0.5) == 3.0  # par: a posição n//2, um tempo que aconteceu
    assert trace_stats.percentile([float(v) for v in range(1, 21)], 0.95) == 20.0  # até 20 linhas o p95 é o máximo
    assert trace_stats.percentile([float(v) for v in range(1, 41)], 0.95) == 39.0


def test_single_turn_split_matches_the_p50_p95_of_the_live_block():
    # mesmo critério de run_evals.summarize: a seção e a tabela ao vivo não se contradizem (sem crash)
    rows = [row("official", v) for v in (12000.0, 3000.0, 25000.0, 8000.0, 41000.0, 15000.0, 9000.0)]
    got = trace_stats.summarize(rows, target=TARGET)["by_split"]["official"]
    ref = run_evals.summarize([{**r, "checks": {}, "cost_usd": 0.0} for r in rows])["official"]
    assert (got["p50_ms"], got["p95_ms"]) == (ref["p50_ms"], ref["p95_ms"]) == (12000.0, 41000.0)
    assert got["turns_per_row"] == 1 and got["multi_turn_rows"] == 0 and got["conversation_p50_ms"] is None


def test_row_with_prior_turns_is_timed_per_turn_and_its_steps_over_the_last_turn():
    rows = [row("memory", 30000.0, [step("faq", 6000.0)], "m1", turn_ms=12000.0),
            row("memory", 60000.0, [step("faq", 9000.0)], "m2"),  # sem turn_ms: fora da fatia, segue na latência
            row("memory", 8000.0, [step("faq", 3000.0)], "fora-dos-casos")]
    turns = trace_stats.turns_by_case([{"id": "m1", "before": ["oi"]}, {"id": "m2", "before": ["oi", "e aí"]}])
    assert turns == {"m1": 2, "m2": 3}
    s = trace_stats.summarize(rows, turns, TARGET)
    g = s["by_split"]["memory"]
    # latência por turno: 15 s, 20 s e 8 s (caso fora dos arquivos vale 1 turno: superestima, nunca esconde)
    assert (g["p50_ms"], g["p95_ms"]) == (15000.0, 20000.0)
    assert (g["conversation_p50_ms"], g["conversation_p95_ms"]) == (60000.0, 60000.0)
    assert g["turns_per_row"] == 2.0 and g["multi_turn_rows"] == 2
    # os passos são do último turno: 6 s em 12 s (turn_ms) + 3 s em 8 s (turno único), não 6 s em 15 s (ms ÷ turnos)
    assert g["agent_share"] == {"faq": round(9000 / 20000, 4)} and g["rest_share"] == pytest.approx(0.55)
    assert g["share_rows"] == 2 and g["share_left_out"] == {"multi_turn_without_turn_ms": 1}
    md = trace_stats.markdown(s)
    assert "| `memory` | 3 | 2 | 15.0 s | 20.0 s | sim | 45% | 55% |" in md
    assert "Fora da fatia: 1 linha de mais de um turno sem `turn_ms` (segue na latência)." in md
    assert ("Em `memory` (2 turnos/linha; conversa: p50 60.0 s, p95 60.0 s) a linha cronometra a conversa inteira; "
            "ali a latência do turno é ms ÷ turnos.") in md


def test_case_turns_reads_the_case_files_and_unreadable_files_count_one_turn(tmp_path):
    turns = trace_stats.case_turns()  # conftest aponta run_evals para os casos do kit
    assert turns["memory-01"] == 2 and all(t >= 1 for t in turns.values())
    dup = tmp_path / "dup.jsonl"
    case = json.dumps({"id": "x", "split": "official", "message": "oi", "expect": {}})
    dup.write_text(f"{case}\n{case}\n", encoding="utf-8")
    assert trace_stats.case_turns((dup,)) == {}  # ids duplicados: sem turnos, cada linha vale 1


def test_slo_has_explicit_defaults_and_env_overrides_show_the_kit_default(monkeypatch):
    assert trace_stats.slo() == TARGET
    monkeypatch.setenv("SLO_P50_S", "8")
    monkeypatch.setenv("SLO_P95_S", "abc")
    got = trace_stats.slo()
    assert (got["p50_s"], got["p95_s"]) == (8.0, 45.0)
    assert got["origin"] == {"SLO_P50_S": "env", "SLO_P95_S": "padrão (valor do env inválido)"}
    md = trace_stats.markdown(trace_stats.summarize([row("official", 9000.0)]))
    assert "p50 ≤ **8 s**" in md
    assert "`SLO_P50_S`: env (padrão do kit 20 s); `SLO_P95_S`: padrão (valor do env inválido)" in md
    assert "`official` (p50 9.0 s)" in md


def test_each_split_meets_the_slo_or_is_named_with_the_measured_value():
    rows = ([row("rapido", 5000.0)] * 3 + [row("lento", 26000.0)] * 3
            + [row("cauda", 10000.0), row("cauda", 10000.0), row("cauda", 50000.0)]
            + [row("limite", 20000.0), row("limite", 20000.0), row("limite", 45000.0)])
    s = trace_stats.summarize(rows, target=TARGET)
    by = s["by_split"]
    assert by["rapido"]["slo_ok"] and by["limite"]["slo_ok"]  # no alvo exato cumpre (≤)
    assert (by["lento"]["slo_ok"], by["lento"]["slo_misses"]) == (False, ["p50"])
    assert (by["cauda"]["slo_ok"], by["cauda"]["slo_misses"]) == (False, ["p95"])
    md = trace_stats.markdown(s)
    assert "Cumprem **2 de 4** splits; não cumprem: `cauda` (p95 50.0 s), `lento` (p50 26.0 s)." in md
    assert "| `lento` | 3 | 1 | 26.0 s | 26.0 s | **não** |" in md
    assert "p50 ≤ **20 s** e p95 ≤ **45 s** (padrão do kit; muda por env `SLO_P50_S`/`SLO_P95_S`)" in md


def test_crash_rows_stay_out_of_the_percentiles_and_the_share_and_are_counted():
    rows = [row("official", 5000.0, [step("faq", 2000.0, "llm")]), row("official", 6000.0, [step("faq", 3000.0)]),
            row("official", 180000.0, crash="ReadTimeout: timed out")]  # o tempo de uma falha, não de um turno
    s = trace_stats.summarize(rows, target=TARGET)
    g = s["by_split"]["official"]
    assert (g["rows"], g["crashes"], g["p50_ms"], g["p95_ms"], g["slo_ok"]) == (2, 1, 6000.0, 6000.0, True)
    assert g["share_left_out"] == {"crash": 1} and g["agent_share"] == {"faq": round(5000 / 11000, 4)}
    md = trace_stats.markdown(s)
    assert "| `official` | 2 (+1 crash) | 1 | 6.0 s | 6.0 s | sim | 45% | 55% |" in md
    assert "Total: p50 6.0 s, p95 6.0 s em 2 linhas (1 crash fora do p50/p95)." in md
    assert "Fora da fatia: 1 linha com crash (fora também do p50/p95)." in md


def test_agent_share_is_agent_ms_over_turn_ms_and_the_rest_is_what_has_no_step():
    rows = [row("official", 10000.0, [step("faq", 4000.0), step("records", 1000.0)]),
            row("official", 10000.0, [step("faq", 2000.0)]),
            row("guardrail", 14.0)]  # bloqueado antes do supervisor: o turno inteiro é "resto"
    s = trace_stats.summarize(rows, target=TARGET)
    g = s["by_split"]["official"]
    assert g["agent_share"] == {"faq": 0.3, "records": 0.05}
    assert g["rest_share"] == pytest.approx(0.65) and g["parallel_rows"] == 0
    assert s["by_split"]["guardrail"]["rest_share"] == 1.0 and s["agents"] == ["faq", "records"]
    md = trace_stats.markdown(s)
    assert "| `official` | 2 | 1 | 10.0 s | 10.0 s | sim | 30% | 5% | 65% |" in md
    assert "| `guardrail` | 1 | 1 | 14 ms | 14 ms | sim | — | — | 100% | — |" in md
    assert "Onde vai o tempo (total): faq **30%** · records **5%** · resto **65%** = router, supervisor" in md
    assert "Fora da fatia" not in md


def test_parallel_is_detected_per_row_and_the_rest_comes_from_the_rows_without_it():
    rows = [row("parallel", 10000.0, [step("faq", 8000.0), step("records", 7000.0)]),  # 15 s de passos em 10 s
            row("parallel", 10000.0, [step("faq", 4000.0)])]
    s = trace_stats.summarize(rows, target=TARGET)
    g = s["by_split"]["parallel"]
    assert g["parallel_rows"] == 1 and g["share_rows"] == 2
    assert g["agent_share"] == {"faq": 0.6, "records": 0.35}  # cada passo paralelo soma o seu tempo
    assert g["rest_share"] == pytest.approx(0.6)  # só a linha sem sobreposição: 1 − 4 s ÷ 10 s
    md = trace_stats.markdown(s)
    assert "| 60% | 35% | 60% (fora 1 linha com paralelo) |" in md
    assert ("resto **60%** = router, supervisor, guardrails e checagens, que não têm passo próprio (calculado na 1 "
            "linha sem paralelo; em 1 linha a soma dos passos passa do tempo do turno)") in md
    alone = trace_stats.summarize(rows[:1], target=TARGET)
    only_parallel = trace_stats.markdown(alone)
    assert alone["ALL"]["rest_share"] is None and "| 80% | 70% | — (paralelo) |" in only_parallel
    assert "resto sem valor (em todas as linhas a soma dos passos passa do tempo do turno" in only_parallel


def test_row_without_steps_has_latency_but_no_share():
    s = trace_stats.summarize([{"id": "x", "split": "official", "ms": 9000.0}], target=TARGET)  # gravação antiga
    g = s["by_split"]["official"]
    assert g["p50_ms"] == 9000.0 and g["agent_share"] == {} and g["rest_share"] is None
    assert g["share_left_out"] == {"no_steps": 1}
    md = trace_stats.markdown(s)
    assert "nenhuma linha com `steps` e o tempo do turno deles; só a latência do turno foi medida" in md
    assert "Fora da fatia: 1 linha sem `steps` (segue na latência)." in md


def test_who_decides_counts_llm_router_code_and_not_recorded_in_the_recorded_format():
    rows = [
        row("replan", 20000.0, [step("faq", 5000.0, "llm"), step("records", 3000.0, "code", "needs")]),
        row("replan", 18000.0, [step("records", 4000.0, "router", "plan"), step("faq", 1000.0, "code", "needs"),
                                step("escalation", 100.0, "code", "escalation")]),
        row("replan", 15000.0, [step("faq", 5000.0)]),  # gravado sem o campo decided_by
        row("replan", 9000.0, [step("human", None, "operator", operator="ana"), step("faq", 3000.0, "llm")]),
        row("replan", 7000.0, [step("faq", 2000.0, "router", "fast_path"), step("hold", None, "code", "hold")]),
        row("replan", 8000.0, [step("faq", 2500.0, "llm")]),
        row("replan", 6000.0, [step("human", None, "code", "operator")]),  # gravação anterior à marca "operator"
    ]
    s = trace_stats.summarize(rows, target=TARGET)
    d = s["by_split"]["replan"]["decisions"]
    assert d["steps"] == 9  # a resposta da operadora e o aviso de caso aberto não escolhem agente
    assert d["by"] == {"llm": 3, "router": 2, "code": 3, "não registrado": 1}
    assert d["why"] == {"code": {"needs": 2, "escalation": 1}, "llm": {"tool call": 3},
                        "router": {"plan": 1, "fast_path": 1}}  # passo LLM sem why: o motivo é a tool call
    assert "human" not in s["agents"] and "hold" not in s["agents"]  # sem tempo medido, não viram coluna de 0%
    md = trace_stats.markdown(s)
    assert (f"Quem decide (9 {SCOPE}): supervisor LLM **33%** (tool call) · plano do router **22%** (`fast_path` 1, "
            "`plan` 1) · código **33%** (`needs` 2, `escalation` 1) · não registrado **11%** (passo gravado sem "
            "`decided_by`).") in md
    assert "| 33% · 22% · 33% · 11% (n=9) |" in md and "sem motivo" not in md
    assert "quem decide (LLM · router · código · não registrado)" in md


def test_who_decides_reads_what_the_supervisor_records(monkeypatch):
    from app import supervisor
    from app.agents import Context, escalation_agent
    from app.observability import new_trace_id
    from app.resume import human_result

    def ctx(text_="Qual o prazo de entrega?", intent="faq", conv=None, **facts):
        c = Context(text=text_, language="pt", user_id="u1", intent=intent,
                    conversation_id=conv or f"c-{uuid.uuid4().hex[:8]}")
        c.facts.update(facts)
        return c

    outs = []
    new_trace_id()
    outs.append(supervisor.run(["records"], ctx("Quando chega meu pedido 1002?", "records")))  # plano + achado
    new_trace_id()
    outs.append(supervisor.run(["faq"], ctx(resume_of="T-1"), prior=[human_result("O prazo é de 2 dias.", "ana")]))
    opener = ctx("Quero um atendente", "human_request", conv="c-hold")
    opener.handoff_reason = "user_request"
    escalation_agent(opener)
    new_trace_id()
    outs.append(supervisor.run(["faq"], ctx(conv="c-hold")))  # caso aberto: aviso "hold"
    llm, _ = fake_llm([resp("tool_use", tool_use("faq_agent", {"query": "prazo"})), resp("end_turn", text("Ok."))])
    monkeypatch.setattr(supervisor, "get_llm", lambda role="agent": llm)
    monkeypatch.setenv("SUPERVISOR_FAST", "off")
    new_trace_id()
    outs.append(supervisor.run(["faq"], ctx()))  # tool call do supervisor LLM
    rows = [{"id": f"r{i}", "split": "official", "ms": 1000.0, "turn_ms": 1000.0, "crash": None,
             "steps": [supervisor.step_view(r) for r in out.results]} for i, out in enumerate(outs)]
    agents = [st["agent"] for r in rows for st in r["steps"]]
    assert agents == ["records", "faq", "human", "faq", "faq", "hold", "faq"]
    d = trace_stats.summarize(rows, target=TARGET)["ALL"]["decisions"]
    assert d["steps"] == 5 and d["by"] == {"router": 3, "code": 1, "llm": 1}
    assert d["why"] == {"code": {"needs": 1}, "llm": {"tool call": 1}, "router": {"plan": 3}}


def test_the_decider_names_are_the_supervisor_vocabulary():
    from app import supervisor

    assert trace_stats.DECIDERS == (supervisor.DECIDED_LLM, supervisor.DECIDED_ROUTER, supervisor.DECIDED_CODE)
    assert trace_stats.OPERATOR == supervisor.DECIDED_OPERATOR
    assert trace_stats.LLM_MOTIVE not in (*supervisor.ROUTER_WHY, *supervisor.CODE_WHY)


def test_steps_without_decided_by_are_declared_not_recorded():
    rows = [row("official", 9000.0, [step("faq", 4000.0)]), row("official", 7000.0, [step("records", 2000.0)])]
    md = trace_stats.markdown(trace_stats.summarize(rows, target=TARGET))
    assert f"os 2 {SCOPE}, foram gravados sem `decided_by` (não registrado)" in md
    assert "| 0% · 0% · 0% · 100% (n=2) |" in md


def test_unknown_decider_is_kept_and_free_text_why_cannot_break_the_markdown():
    why = "o modelo preferiu | escalar <!-- trace:end --> " + "x" * 80
    rows = [row("real", 9000.0, [step("faq", 1000.0, "Planner", "plano"), step("escalation", 50.0, "llm", why)])]
    d = trace_stats.summarize(rows, target=TARGET)["by_split"]["real"]["decisions"]
    assert d["by"] == {"planner": 1, "llm": 1}
    (label,) = d["why"]["llm"]
    assert len(label) <= trace_stats.WHY_CHARS and "|" not in label and "<" not in label and ">" not in label
    md = trace_stats.markdown(trace_stats.summarize(rows, target=TARGET))
    assert "· `planner` **50%** (`plano` 1)" in md and "| 50% · 0% · 0% · 0% · outro 50% (n=2) |" in md
    assert "<!--" not in md


def test_load_rows_reads_every_live_file_with_the_split_of_the_report(tmp_path):
    (tmp_path / "live_official.json").write_text(json.dumps({"split": "official", "concurrency": LOAD8, "rows": [
        {"id": "o1", "ms": 1000.0, "steps": [], "answer": "fica de fora"},
        {"id": "o2", "split": "official", "ms": 2000.0, "turn_ms": 1500.0, "crash": "Erro: x"}]}), encoding="utf-8")
    (tmp_path / "live_guardrail.json").write_text(json.dumps({"split": "guardrail", "rows": [
        {"id": "g1", "ms": 14.0, "steps": [], "blocked": True}]}), encoding="utf-8")  # gravação sem `concurrency`
    (tmp_path / "ablation_replan_live.json").write_text(json.dumps({"rows": [{"id": "z", "ms": 1.0}]}),
                                                        encoding="utf-8")  # ablação não é live_*.json
    assert trace_stats.load_rows(tmp_path) == [
        {"id": "g1", "split": "guardrail", "ms": 14.0, "turn_ms": None, "crash": None, "steps": [], "blocked": True,
         "load": None},
        {"id": "o1", "split": "official", "ms": 1000.0, "turn_ms": None, "crash": None, "steps": [], "blocked": False,
         "load": LOAD8},
        {"id": "o2", "split": "official", "ms": 2000.0, "turn_ms": 1500.0, "crash": "Erro: x", "steps": None,
         "blocked": False, "load": LOAD8}]


def test_guardrail_blocks_leave_the_percentiles_and_the_slo_and_are_counted_apart():
    """Ensaio: 39 bloqueios, que levam ms, baixavam o p50 do total de 17,6 s para 16,3 s; aqui eles viram o SLO."""
    rows = ([row("official", 21000.0, case_id=f"o{i}", load=LOAD8) for i in range(3)]
            + [row("guardrail", 14.0, case_id=f"g{i}", blocked=True, load=LOAD8) for i in range(5)]
            + [row("guardrail", 6000.0, case_id="g-ok", load=LOAD8)])
    s = trace_stats.summarize(rows, target=TARGET)
    total, guard = s["ALL"], s["by_split"]["guardrail"]
    # com os bloqueios, o p50 do total seria 14 ms (posição 4 de 9) e o total "cumpriria" o SLO
    assert trace_stats.percentile([r["ms"] for r in rows], 0.5) == 14.0
    assert (total["rows"], total["blocked"], total["p50_ms"], total["slo_ok"]) == (4, 5, 21000.0, False)
    assert (guard["rows"], guard["blocked"], guard["p50_ms"], guard["slo_ok"]) == (1, 5, 6000.0, True)
    md = trace_stats.markdown(s)
    assert ("Total: p50 21.0 s, p95 21.0 s em 4 linhas (5 bloqueios do guardrail fora do p50/p95: a recusa leva "
            "ms).") in md
    assert "| `guardrail` | 1 (+5 bloqueadas) | 1 | 6.0 s | 6.0 s | sim |" in md
    only_blocked = trace_stats.summarize([row("guardrail", 14.0, blocked=True)], target=TARGET)["by_split"]
    assert only_blocked["guardrail"]["slo_ok"] is None  # só recusas: o split não entra na conta do SLO
    crashed = trace_stats.markdown(trace_stats.summarize(
        [row("official", 5000.0), row("official", 9.0, blocked=True), row("official", 1.0, crash="x")], target=TARGET))
    assert "em 1 linha (1 bloqueio do guardrail fora do p50/p95: a recusa leva ms; 1 crash fora do p50/p95)." in crashed
    assert "| `official` | 1 (+1 crash, +1 bloqueada) |" in crashed


def test_slo_line_declares_the_load_it_was_measured_under():
    one = {"cases_at_once": 1, "max_concurrent": 12, "workers": 1, "splits_in_process": 1, "cpus": 4}
    md = trace_stats.markdown(trace_stats.summarize([row("official", 9000.0, load=LOAD8)] * 2, target=TARGET))
    assert ("Carga da medida: até **8** conversas ao mesmo tempo no processo (12 splits × 8 workers; teto "
            "`LIVE_MAX_CONCURRENT` 8), em 4 CPUs: o tempo do turno inclui a CPU dividida com as outras conversas "
            "(carga do eval, não a de uma conversa sozinha). Cumprem **1 de 1** splits.") in md
    mixed = trace_stats.markdown(trace_stats.summarize(
        [row("official", 9000.0, load=LOAD8), row("replan", 9000.0, load=LOAD8), row("partial", 9000.0, load=one),
         row("memory", 9000.0)], target=TARGET))
    assert ("Carga da medida: até **8** conversas ao mesmo tempo no processo (12 splits × 8 workers; teto "
            "`LIVE_MAX_CONCURRENT` 8), em 4 CPUs em `official`, `replan`; até **1** conversa ao mesmo tempo no "
            "processo (1 split × 1 worker; teto `LIVE_MAX_CONCURRENT` 12), em 4 CPUs em `partial`; não registrada em "
            "`memory` (gravação anterior ao campo `concurrency`): o tempo do turno inclui a CPU") in mixed
    alone = trace_stats.markdown(trace_stats.summarize([row("official", 9000.0, load=one)], target=TARGET))
    assert "até **1** conversa ao mesmo tempo" in alone and "CPU dividida" not in alone  # sozinha não divide
    old = trace_stats.markdown(trace_stats.summarize([row("official", 9000.0)], target=TARGET))
    assert "Carga da medida: não registrada nos live_*.json (gravação anterior ao campo `concurrency`)." in old


def test_live_report_records_the_load_it_ran_under(monkeypatch):
    class Client:
        def send(self, message, user_id, conversation_id):
            return {"conversation_id": "c1", "intent": "faq", "route": ["router", "faq"], "steps": [],
                    "usage": {"cost_usd": 0.0}}

    report = run_evals.run(split="official", workers=3, client=Client(), live=True)
    saved = json.loads(Path(report["path"]).read_text(encoding="utf-8"))
    cap = run_evals._MAX_CONCURRENT
    assert saved["concurrency"] == {"cases_at_once": min(cap, 3), "max_concurrent": cap, "workers": 3,
                                    "splits_in_process": 1, "cpus": run_evals.concurrency(1)["cpus"]}
    assert run_evals.concurrency(8, 12)["cases_at_once"] == min(cap, 96)  # o teto do processo vale sobre todos
    rows = trace_stats.load_rows(run_evals.RESULTS_DIR)
    assert rows and all(r["load"] == saved["concurrency"] for r in rows)


def test_live_row_times_the_last_turn_apart_from_the_conversation(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(run_evals.time, "perf_counter", lambda: clock[0])

    class Client:
        def send(self, message, user_id, conversation_id):
            clock[0] += 5.0 if message == "antes" else 2.0  # o turno anterior leva 5 s, o avaliado 2 s
            return {"conversation_id": "c1", "intent": "faq", "route": ["router", "faq"], "steps": []}

    case = {"id": "m1", "split": "memory", "message": "agora", "before": ["antes"], "expect": {"intent": "faq"}}
    got = run_evals.run_case(Client(), case)
    assert (got["ms"], got["turn_ms"], got["crash"]) == (7000.0, 2000.0, None)

    class Broken:
        def send(self, message, user_id, conversation_id):
            raise RuntimeError("caiu")

    crashed = run_evals.run_case(Broken(), {"id": "o1", "split": "official", "message": "oi",
                                            "expect": {"intent": "faq"}})
    assert crashed["turn_ms"] is None and crashed["crash"] == "RuntimeError: caiu"


def test_no_live_rows_is_declared(tmp_path):
    assert trace_stats.load_rows(tmp_path) == []
    assert "Eval ao vivo não rodado" in trace_stats.markdown(trace_stats.summarize([], target=TARGET))
    assert "Eval ao vivo não rodado" in fill_readme.trace_block(tmp_path)


def test_fill_readme_trace_block_renders_is_idempotent_and_the_check_catches_edits(tmp_path):
    results = tmp_path / "results"
    results.mkdir()
    (results / "live_official.json").write_text(json.dumps({"split": "official", "rows": [
        row("official", 12000.0, [step("faq", 6000.0, "llm")]),
        row("official", 30000.0, [step("faq", 9000.0, "code", "needs")])]}), encoding="utf-8")
    template = "<!-- trace:begin -->\n<!-- trace:end -->\n<!-- timeline:begin -->\n<!-- timeline:end -->"
    once = fill_readme.render(template, results, root=tmp_path)
    assert once == fill_readme.render(once, results, root=tmp_path)
    assert "| `official` | 2 | 1 | 30.0 s | 30.0 s | **não** | 36% | 64% | 50% · 0% · 50% · 0% (n=2) |" in once
    assert not fill_readme._check_blocks(once, results)
    edited = once.replace("**não**", "sim", 1)
    assert [p for p in fill_readme._check_blocks(edited, results) if "bloco trace" in p]


def test_trace_is_one_more_block_and_the_others_keep_their_functions():
    assert fill_readme.BLOCKS["trace"] is fill_readme.trace_block
    for tag, fn in (("eval", "offline_block"), ("eval-live", "live_block"), ("judge", "judge_block"),
                    ("human", "human_block"), ("replan", "replan_block"), ("scorecard", "scorecard_block"),
                    ("retrieval", "retrieval_block"), ("quickstart", "quickstart_block"),
                    ("red-team", "red_team_block"), ("since", "since_block")):
        assert fill_readme.BLOCKS[tag] is getattr(fill_readme, fn)
    text = (ROOT / "docs" / "RESULTS.md").read_text(encoding="utf-8")
    assert text.count("<!-- trace:begin -->") == 1 and text.count("<!-- trace:end -->") == 1


def test_cli_prints_json_and_fails_without_live_rows(tmp_path, capsys):
    assert trace_stats.main(["--results", str(tmp_path)]) == 1
    (tmp_path / "live_official.json").write_text(json.dumps({"split": "official", "rows": [row("official", 5000.0)]}),
                                                 encoding="utf-8")
    assert trace_stats.main(["--results", str(tmp_path), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["by_split"]["official"]["p50_ms"] == 5000.0 and out["ALL"]["slo_ok"] is True
