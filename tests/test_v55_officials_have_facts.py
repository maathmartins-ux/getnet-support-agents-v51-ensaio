"""Oficial resolvido sem humano precisa de fato verificável; senão uma recusa educada conta como resolvida."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check  # noqa: E402


def _write(root, cases):
    (root / "evals").mkdir()
    (root / "evals" / "cases.jsonl").write_text("\n".join(json.dumps(c) for c in cases), encoding="utf-8")


def test_official_without_facts_fails_unless_it_expects_a_human(tmp_path):
    _write(tmp_path, [{"id": "o1", "split": "official", "expect": {"facts": ["48"]}},
                      {"id": "o2", "split": "official", "expect": {"handoff": True}},
                      {"id": "o3", "split": "official", "expect": {"intent": "general"}},
                      {"id": "m1", "split": "memory", "expect": {}}])
    _name, ok, _, detail = check.officials_have_facts(tmp_path)
    assert not ok and detail == "sem expect.facts: o3"


def test_offline_quote_engine_does_not_count_language():
    """Modo offline (motor `table`) cita a fonte em português sem tradução: o idioma do redator se mede com LLM."""
    from evals.run_evals import score

    case = {"expect": {"language": "en"}}
    quoted = {"engine": "table", "answer": "O Pix é um meio de pagamento criado pelo Banco Central do Brasil."}
    assert "language" not in score(case, quoted)
    assert score(case, {**quoted, "engine": "llm"})["language"] is False


def test_tomorrow_written_with_year_is_not_redacted():
    """"Wednesday, Nov 4, 2026" (amanhã) saía "Nov [unconfirmed value], 2026": dia e ano da data de amanhã contam."""
    import datetime as dt

    from app.grounding import is_calendar_day

    today = dt.date(2026, 11, 3)
    answer = "Tomorrow (Wednesday, Nov 4, 2026) in Porto Alegre"
    assert is_calendar_day("4", answer, today) and is_calendar_day("2026", answer, today)
    assert is_calendar_day("2026", "amanhã, 4 de novembro de 2026", today)
    assert not is_calendar_day("2026", "In 2026 we sold 4 units", today)
    assert not is_calendar_day("9", "Nov 9, 2026", today)


def test_number_inside_tool_identifier_supports_the_answer():
    from app.grounding import unsupported_numbers

    assert unsupported_numbers("Só aceita ontem, hoje ou os últimos 7 dias.", ['{"period": "last_7_days"}']) == []
    assert unsupported_numbers("Nos últimos 8 dias.", ['{"period": "last_7_days"}']) == ["8"]
