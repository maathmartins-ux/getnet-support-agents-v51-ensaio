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


def test_answer_opening_with_abstention_is_not_resolved():
    from evals.run_evals import opens_with_abstention, resolved

    hedge = "I couldn't confirm whether you need a bank account. Getnet offers Get Conta [sup-42]."
    direct = "Yes: you receive into Get Conta, a free digital account [sup-42]. I couldn't confirm other banks."
    got = {"answer": hedge, "sources": [{"id": "sup-42"}], "route": ["router", "faq"]}
    assert opens_with_abstention(hedge) and not resolved(got, [])
    assert not opens_with_abstention(direct) and resolved({**got, "answer": direct}, [])
    assert opens_with_abstention("Não consegui confirmar a previsão.")


def test_policy_citation_scrub_leaves_no_broken_sentence():
    from app.pipeline import _scrub_internal

    assert _scrub_internal("Esse tipo de decisão é de um atendente, conforme [policy:capabilities].", "pt") == \
        "Esse tipo de decisão é de um atendente."
    assert _scrub_internal("Pelo [policy:capabilities], uma proposta não confirmada expira em 15 minutos.", "pt") == \
        "Uma proposta não confirmada expira em 15 minutos."
    assert _scrub_internal("Total: R$ 10,00 [policy:capabilities].", "pt") == "Total: R$ 10,00."


def test_rerank_gate_decides_when_the_retriever_reranks(monkeypatch):
    """Com rerank e limiar calibrado, a nota do cross-encoder decide "tem fonte"; sem rerank, vale o portão antigo."""
    from types import SimpleNamespace

    from app import agents

    monkeypatch.setenv("COVERAGE_MIN_RERANK", "-5.0")
    hit = lambda r: SimpleNamespace(rerank=r, bm25=9.0, cosine=None)  # noqa: E731
    assert agents.covered_hits([hit(-7.0), hit(-6.0)]) == []  # BM25 alto não salva: o rerank recusa
    assert len(agents.covered_hits([hit(-4.0), hit(-9.0)])) == 2
    assert len(agents.covered_hits([hit(None)])) == 1  # sem nota de rerank: o BM25 decide
