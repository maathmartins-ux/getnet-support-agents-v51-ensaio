"""v5.5.1: o juiz confere "hoje/amanhã/ontem" contra o dia em que a resposta foi gerada (fuso do negócio)."""
from __future__ import annotations

from evals import judge


def test_judge_date_uses_the_row_then_the_report_then_the_business_clock(monkeypatch):
    assert judge.judge_date({"business_date": "2026-11-03"}) == "2026-11-03"
    # 02h05 UTC de 4/11 = 23h05 de 3/11 em São Paulo: a bateria rodou no dia 3
    assert judge.judge_date({}, {"recorded_at": "2026-11-04T02:05:00Z"}) == "2026-11-03"
    monkeypatch.setenv("APP_TZ", "UTC")
    assert judge.judge_date({}, {"recorded_at": "2026-11-04T02:05:00Z"}) == "2026-11-04"
    from app import clock

    assert judge.judge_date() == clock.today().isoformat()


def test_rejudge_plan_takes_failed_and_dated_answers_only():
    rows = {("live_a.json", "c1", 0): {"answer": "Seu depósito cai amanhã, 05/11."},
            ("live_a.json", "c2", 0): {"answer": "A taxa do débito é 1,89%."},
            ("live_a.json", "c3", 0): {"answer": "A taxa do crédito é 3,19%."}}
    report = {"verdicts": [
        {"source": "live_a.json", "id": "c1", "run": 0, "grounded": True, "helpful": True, "language_ok": True},
        {"source": "live_a.json", "id": "c2", "run": 0, "grounded": True, "helpful": True, "language_ok": True},
        {"source": "live_a.json", "id": "c3", "run": 0, "grounded": False, "helpful": True, "language_ok": True}]}
    keep, again = judge.rejudge_plan(report, rows)
    assert [v["id"] for v in keep] == ["c2"] and sorted(v["id"] for v in again) == ["c1", "c3"]


def test_live_rows_record_the_business_date(monkeypatch):
    from evals import run_evals

    monkeypatch.setattr("app.clock.today", lambda: __import__("datetime").date(2026, 11, 3))
    assert run_evals._business_date() == "2026-11-03"


def test_results_block_declares_the_rejudge(tmp_path):
    import json

    from scripts.fill_readme import judge_block

    base = {"model": "m", "status": "ran", "live_files": ["live_a.json"], "spent_usd": 1, "cases": 1,
            "grounded_rate": 1.0, "helpful_rate": 1.0, "mean_score": 5, "by_split": {}, "calibration": {}}
    (tmp_path / "judge.json").write_text(json.dumps({**base, "rejudged_dated": 131}), encoding="utf-8")
    assert "Rejulgados 131 vereditos" in judge_block(tmp_path)
    (tmp_path / "judge.json").write_text(json.dumps(base), encoding="utf-8")
    assert "Rejulgados" not in judge_block(tmp_path)
