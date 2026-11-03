"""Custo por turno resolvido sem humano no placar (gasto ao vivo ÷ turnos sem handoff), medido, não suposto."""
import json

from scripts import scorecard


def _live(path, spent, rows, status="complete"):
    path.write_text(json.dumps({"status": status, "spent_usd": spent, "rows": rows}), encoding="utf-8")


def test_cost_per_resolved_turn_and_fraction(tmp_path):
    ok = {"answer": "x", "handoff_required": False}
    _live(tmp_path / "live_official.json", 0.30, [ok, ok, {"answer": "y", "handoff_required": True}])
    _live(tmp_path / "live_memory.json", 0.30, [ok, {"answer": "z", "crash": True}, ok])
    _live(tmp_path / "live_hard.aborted_max_usd.json", 9.0, [ok] * 10, status="aborted_max_usd")  # fora
    per, frac = scorecard.cost_per_resolved(tmp_path)
    assert per == 0.15 and frac == round(4 / 6, 4)
    md = scorecard.to_markdown(tmp_path)
    assert "Custo por turno resolvido sem humano" in md and "US$ 0.1500" in md


def test_without_live_files_it_is_not_measured(tmp_path):
    assert scorecard.cost_per_resolved(tmp_path) == (None, None)
