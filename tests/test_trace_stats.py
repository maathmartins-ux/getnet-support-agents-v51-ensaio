"""Onde vai o tempo e quem decide (evals/trace_stats.py + bloco `trace` do fill_readme): percentis do turno, SLO por
split, fatia de cada agente e passos decididos pelo supervisor LLM × inseridos pelo código, com linhas sintéticas
com e sem `decided_by`."""
import json
from pathlib import Path

import pytest

from evals import run_evals, trace_stats
from scripts import fill_readme

ROOT = Path(__file__).resolve().parents[1]
TARGET = {"p50_s": 20.0, "p95_s": 45.0, "origin": {"SLO_P50_S": "padrão", "SLO_P95_S": "padrão"}}


@pytest.fixture(autouse=True)
def default_slo(monkeypatch):
    # SLO vem do env: um valor do shell de quem roda não pode mudar o que os testes esperam
    monkeypatch.delenv("SLO_P50_S", raising=False)
    monkeypatch.delenv("SLO_P95_S", raising=False)


def row(split, ms, steps=None, case_id=None):
    return {"id": case_id or f"{split}-{ms:g}", "split": split, "ms": ms, "steps": [] if steps is None else steps}


def step(agent, ms, decided_by=None, why=None):
    out = {"agent": agent, "status": "ok", "reason": None, "ms": ms, "tools": []}
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
    # mesmo critério de run_evals.summarize: a seção e a tabela ao vivo não se contradizem
    rows = [row("official", v) for v in (12000.0, 3000.0, 25000.0, 8000.0, 41000.0, 15000.0, 9000.0)]
    got = trace_stats.summarize(rows, target=TARGET)["by_split"]["official"]
    ref = run_evals.summarize([{**r, "checks": {}, "cost_usd": 0.0, "crash": None} for r in rows])["official"]
    assert (got["p50_ms"], got["p95_ms"]) == (ref["p50_ms"], ref["p95_ms"]) == (12000.0, 41000.0)
    assert got["turns_per_row"] == 1 and got["multi_turn_rows"] == 0 and got["conversation_p50_ms"] is None


def test_row_with_prior_turns_is_timed_per_turn_and_the_conversation_is_kept():
    rows = [row("memory", 30000.0, [step("faq", 6000.0)], "m1"), row("memory", 60000.0, [step("faq", 9000.0)], "m2"),
            row("memory", 12000.0, [step("faq", 3000.0)], "fora-dos-casos")]
    turns = trace_stats.turns_by_case([{"id": "m1", "before": ["oi"]}, {"id": "m2", "before": ["oi", "e aí"]}])
    assert turns == {"m1": 2, "m2": 3}
    s = trace_stats.summarize(rows, turns, TARGET)
    g = s["by_split"]["memory"]
    # por turno: 15 s, 20 s e 12 s (caso fora dos arquivos vale 1 turno: superestima, nunca esconde)
    assert (g["p50_ms"], g["p95_ms"]) == (15000.0, 20000.0)
    assert (g["conversation_p50_ms"], g["conversation_p95_ms"]) == (60000.0, 60000.0)
    assert g["turns_per_row"] == 2.0 and g["multi_turn_rows"] == 2
    assert g["agent_share"] == {"faq": round(18000 / 47000, 4)}
    md = trace_stats.markdown(s)
    assert "| `memory` | 3 | 2 | 15.0 s | 20.0 s | sim |" in md
    assert ("Em `memory` (2 turnos/linha; conversa: p50 60.0 s, p95 60.0 s) a linha cronometra a conversa inteira; "
            "ali o turno é ms ÷ turnos.") in md


def test_case_turns_reads_the_case_files_and_unreadable_files_count_one_turn(tmp_path):
    turns = trace_stats.case_turns()  # conftest aponta run_evals para os casos do kit
    assert turns["memory-01"] == 2 and all(t >= 1 for t in turns.values())
    dup = tmp_path / "dup.jsonl"
    case = json.dumps({"id": "x", "split": "official", "message": "oi", "expect": {}})
    dup.write_text(f"{case}\n{case}\n", encoding="utf-8")
    assert trace_stats.case_turns((dup,)) == {}  # ids duplicados: sem turnos, cada linha vale 1


def test_slo_has_explicit_defaults_and_env_overrides(monkeypatch):
    assert trace_stats.slo() == TARGET
    monkeypatch.setenv("SLO_P50_S", "8")
    monkeypatch.setenv("SLO_P95_S", "abc")
    got = trace_stats.slo()
    assert (got["p50_s"], got["p95_s"]) == (8.0, 45.0)
    assert got["origin"] == {"SLO_P50_S": "env", "SLO_P95_S": "padrão (valor do env inválido)"}
    md = trace_stats.markdown(trace_stats.summarize([row("official", 9000.0)]))
    assert "p50 ≤ **8 s**" in md and "`SLO_P50_S`: env; `SLO_P95_S`: padrão (valor do env inválido)" in md
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


def test_agent_share_is_agent_ms_over_turn_ms_and_the_rest_is_what_has_no_step():
    rows = [row("official", 10000.0, [step("faq", 4000.0), step("records", 1000.0)]),
            row("official", 10000.0, [step("faq", 2000.0)]),
            row("guardrail", 14.0)]  # bloqueado antes do supervisor: o turno inteiro é "resto"
    s = trace_stats.summarize(rows, target=TARGET)
    g = s["by_split"]["official"]
    assert g["agent_share"] == {"faq": 0.3, "records": 0.05}
    assert g["rest_share"] == pytest.approx(0.65) and g["parallel_overlap"] is False
    assert s["by_split"]["guardrail"]["rest_share"] == 1.0 and s["agents"] == ["faq", "records"]
    md = trace_stats.markdown(s)
    assert "| `official` | 2 | 1 | 10.0 s | 10.0 s | sim | 30% | 5% | 65% |" in md
    assert "| `guardrail` | 1 | 1 | 14 ms | 14 ms | sim | — | — | 100% | — |" in md
    assert "Onde vai o tempo (total): faq **30%** · records **5%** · resto **65%** = router, supervisor" in md


def test_parallel_steps_add_up_and_the_rest_is_declared_not_truncated():
    s = trace_stats.summarize([row("parallel", 10000.0, [step("faq", 8000.0), step("records", 7000.0)])],
                              target=TARGET)
    g = s["by_split"]["parallel"]
    assert g["parallel_overlap"] and g["rest_share"] is None
    md = trace_stats.markdown(s)
    assert "| 80% | 70% | — (paralelo) |" in md and "resto sem valor (passos paralelos" in md


def test_row_without_steps_has_latency_but_no_share():
    s = trace_stats.summarize([{"id": "x", "split": "official", "ms": 9000.0}], target=TARGET)  # gravação antiga
    g = s["by_split"]["official"]
    assert g["p50_ms"] == 9000.0 and g["agent_share"] == {} and g["rest_share"] is None
    assert "as linhas não trazem `steps`; só a latência do turno foi medida" in trace_stats.markdown(s)


def test_who_decides_splits_llm_code_and_not_recorded_by_why():
    rows = [
        row("replan", 20000.0, [step("faq", 5000.0, "llm", "tool_use"), step("records", 3000.0, "code", "needs")]),
        row("replan", 18000.0, [step("records", 4000.0, "code", "needs"),
                                step("escalation", 100.0, "code", "enforced_escalation")]),
        row("replan", 15000.0, [step("faq", 5000.0)]),  # gravado antes do campo decided_by
        row("replan", 9000.0, [step("human", None, "code", "operator"), step("faq", 3000.0, "llm", "tool_use")]),
    ]
    s = trace_stats.summarize(rows, target=TARGET)
    d = s["by_split"]["replan"]["decisions"]
    assert d["steps"] == 6  # a resposta do operador (human) chega pronta: não é passo decidido
    assert d["by"] == {"llm": 2, "code": 3, "não registrado": 1}
    assert d["why"]["code"] == {"needs": 2, "enforced_escalation": 1} and d["why"]["llm"] == {"tool_use": 2}
    assert "human" not in s["agents"]  # sem tempo medido, não vira coluna de 0%
    md = trace_stats.markdown(s)
    assert ("Quem decide (6 passos de especialista): supervisor LLM **33%** (`tool_use` 2) · código **50%** "
            "(`needs` 2, `enforced_escalation` 1) · não registrado **17%** (passo gravado sem `decided_by`).") in md
    assert "| 33% · 50% · 17% (n=6) |" in md


def test_steps_without_decided_by_are_declared_not_recorded():
    rows = [row("official", 9000.0, [step("faq", 4000.0)]), row("official", 7000.0, [step("records", 2000.0)])]
    md = trace_stats.markdown(trace_stats.summarize(rows, target=TARGET))
    assert "os 2 passos de especialista foram gravados sem `decided_by` (não registrado)" in md
    assert "| 0% · 0% · 100% (n=2) |" in md


def test_unknown_decider_is_kept_and_free_text_why_cannot_break_the_markdown():
    why = "o modelo preferiu | escalar <!-- trace:end --> " + "x" * 80
    rows = [row("real", 9000.0, [step("faq", 1000.0, "Router", "plano"), step("escalation", 50.0, "llm", why)])]
    d = trace_stats.summarize(rows, target=TARGET)["by_split"]["real"]["decisions"]
    assert d["by"] == {"router": 1, "llm": 1}
    (label,) = d["why"]["llm"]
    assert len(label) <= trace_stats.WHY_CHARS and "|" not in label and "<" not in label and ">" not in label
    md = trace_stats.markdown(trace_stats.summarize(rows, target=TARGET))
    assert "· `router` **50%** (`plano` 1)" in md and "| 50% · 0% · 0% · outro 50% (n=2) |" in md
    assert "<!--" not in md


def test_load_rows_reads_every_live_file_with_the_split_of_the_report(tmp_path):
    (tmp_path / "live_official.json").write_text(json.dumps({"split": "official", "rows": [
        {"id": "o1", "ms": 1000.0, "steps": [], "answer": "fica de fora"},
        {"id": "o2", "split": "official", "ms": 2000.0}]}), encoding="utf-8")
    (tmp_path / "ablation_replan_live.json").write_text(json.dumps({"rows": [{"id": "z", "ms": 1.0}]}),
                                                        encoding="utf-8")  # ablação não é live_*.json
    assert trace_stats.load_rows(tmp_path) == [{"id": "o1", "split": "official", "ms": 1000.0, "steps": []},
                                               {"id": "o2", "split": "official", "ms": 2000.0, "steps": None}]


def test_no_live_rows_is_declared(tmp_path):
    assert trace_stats.load_rows(tmp_path) == []
    assert "Eval ao vivo não rodado" in trace_stats.markdown(trace_stats.summarize([], target=TARGET))
    assert "Eval ao vivo não rodado" in fill_readme.trace_block(tmp_path)


def test_fill_readme_trace_block_renders_is_idempotent_and_the_check_catches_edits(tmp_path):
    results = tmp_path / "results"
    results.mkdir()
    (results / "live_official.json").write_text(json.dumps({"split": "official", "rows": [
        row("official", 12000.0, [step("faq", 6000.0, "llm", "tool_use")]),
        row("official", 30000.0, [step("faq", 9000.0, "code", "needs")])]}), encoding="utf-8")
    template = "<!-- trace:begin -->\n<!-- trace:end -->\n<!-- timeline:begin -->\n<!-- timeline:end -->"
    once = fill_readme.render(template, results, root=tmp_path)
    assert once == fill_readme.render(once, results, root=tmp_path)
    assert "| `official` | 2 | 1 | 30.0 s | 30.0 s | **não** | 36% | 64% | 50% · 50% · 0% (n=2) |" in once
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
