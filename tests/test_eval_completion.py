"""Ablação por CONCLUSÃO de tarefa: completed_acc com × sem replanejamento por achado (split dependent).

Medida no split replan, a ablação (93% × 0%) dá 0 por construção: esse split só mede "escalou após falha". Aqui o modo
no_needs mantém a reação à falha e desliga só o achado; o caso de controle (pedido já entregue) completa nos dois.
"""
import json
from pathlib import Path

from evals import run_evals

DEPENDENT = Path(__file__).parent / "fixtures" / "dependent_cases.jsonl"


def test_completed_check_reads_agents_and_mentions():
    case = {"expect": {"intent": "records", "must_include_agents": ["records", "faq"], "must_mention": ["Prazo"]}}
    ok = {"intent": "records", "route": ["router", "records", "faq"], "answer": "o prazo é 3 dias"}
    assert run_evals.score(case, ok)["completed"] is True
    assert run_evals.score(case, {**ok, "route": ["router", "records"]})["completed"] is False
    assert run_evals.score(case, {**ok, "answer": "em separação"})["completed"] is False
    assert "completed" not in run_evals.score({"expect": {"intent": "faq"}}, ok)


def test_ablation_no_needs_measures_the_gain_of_finding_driven_replanning(tmp_path, monkeypatch):
    monkeypatch.setattr(run_evals, "CASES", DEPENDENT)
    on = run_evals.run(out=tmp_path / "on.json", split="dependent")["metrics"]["dependent"]
    monkeypatch.setenv("SUPERVISOR_REPLAN", "no_needs")
    off = run_evals.run(out=tmp_path / "off.json", split="dependent")["metrics"]["dependent"]
    assert on["completed_acc"] == 100.0 and off["completed_acc"] == 25.0  # só o controle completa sem o achado
    assert on["intent_acc"] == off["intent_acc"] == 100.0  # mesma rota de entrada: o ganho é do supervisor


def test_cli_ablate_replan_mode_no_needs_writes_its_own_file(tmp_path, monkeypatch):
    monkeypatch.setattr(run_evals, "CASES", DEPENDENT)
    monkeypatch.setattr(run_evals, "RESULTS_DIR", tmp_path)
    assert run_evals.main(["--ablate-replan", "--mode", "no_needs"]) == 0
    report = json.loads((tmp_path / "ablation_replan_no_needs.json").read_text("utf-8"))
    assert report["split"] == "dependent" and report["metrics"]["dependent"]["completed_acc"] == 25.0
