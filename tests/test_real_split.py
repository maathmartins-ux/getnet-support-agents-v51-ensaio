"""Perguntas reais de lojistas (split `real`): cada uma com a fonte pública, sem gabarito de rota, sem contaminar."""
import json
from pathlib import Path

import pytest

from evals.run_evals import score

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / "evals" / "real_questions.jsonl", ROOT / "evals" / "cases.jsonl"]


def _real_rows():
    rows = []
    for path in FILES:
        if path.exists():
            rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in rows if r.get("split") == "real"]


def test_case_without_intent_is_scored_without_route_check():
    checks = score({"expect": {"language": "pt"}}, {"intent": "faq", "answer": "Olá, o prazo é de dois dias úteis."})
    assert "intent" not in checks


def test_every_real_question_has_a_public_source():
    rows = _real_rows()
    if not rows:
        pytest.skip("sem split real neste repositório (o kit não traz perguntas do desafio)")
    for r in rows:
        assert str(r.get("source_url", "")).startswith("http"), r["id"]
        assert "intent" not in r.get("expect", {}), f"{r['id']}: pergunta real não tem gabarito de rota"
