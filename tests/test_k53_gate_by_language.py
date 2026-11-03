"""K53 (pós-morte V5, N2): a recusa do portão de cobertura lida por idioma, com o caminho de busca do agente.

V5: o piso 0,88 do denso foi calibrado sem perguntas em inglês e recusou 4 oficiais em inglês com a fonte no índice.
"""
import json

import pytest

from app.agents import gate_by_language, gate_rates_by_language
from app.rag import BM25Retriever, get_index

DOCS = [
    {"id": "conta", "title": "Como receber", "url": "https://example.com/receber",
     "text": "Para receber os pagamentos você precisa de uma conta corrente ou conta de pagamento."},
    {"id": "troca", "title": "Troca", "url": "https://example.com/troca",
     "text": "A troca do produto pode ser pedida em até 7 dias após o recebimento."},
]


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    (tmp_path / "kb.jsonl").write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in DOCS), encoding="utf-8")
    (tmp_path / "glossary.json").write_text(json.dumps({"conta corrente": ["bank account"], "receber": ["receive"],
                                                        "pagamentos": ["payments"], "troca": ["exchange"]}),
                                            encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def test_rates_by_language_are_pure_and_split_positives_from_negatives():
    rates = gate_rates_by_language([("en", True, False), ("en", True, True), ("pt", True, True),
                                    ("pt", False, False), ("en", False, True)])
    assert rates["en"] == {"positives": 2, "answered": 1, "negatives": 1, "refused": 0, "pos_answered": 0.5,
                           "pos_refused": 0.5, "neg_refused": 0.0}
    assert rates["pt"]["pos_refused"] == 0.0 and rates["pt"]["neg_refused"] == 1.0
    assert gate_rates_by_language([("pt", False, False)])["pt"]["pos_answered"] is None


CASES = [
    {"question": "Como receber os pagamentos na conta corrente?", "positive": True, "relevant": ["conta"]},
    {"question": "Do I need a bank account to receive payments?", "positive": True, "relevant": ["conta"]},
    {"question": "How do I exchange a product?", "positive": True, "relevant": ["troca"]},
    {"question": "Qual a capital da Mongólia?", "positive": False},
    {"question": "Who won the football world cup?", "positive": False},
]


def test_gate_by_language_runs_the_agent_search_per_case(corpus):
    rates = gate_by_language(CASES, retriever=BM25Retriever(get_index()))
    assert rates["en"]["positives"] == 2 and rates["en"]["pos_answered"] == 1.0  # traduzidas ao idioma do corpus
    assert rates["pt"]["pos_answered"] == 1.0
    assert rates["pt"]["neg_refused"] == 1.0 and rates["en"]["neg_refused"] == 1.0


def test_gate_override_is_the_calibration_sweep(corpus):
    rates = gate_by_language(CASES, retriever=BM25Retriever(get_index()), gate={"min_score": 1e9, "min_cosine": 2})
    assert rates["en"]["pos_refused"] == 1.0 and rates["pt"]["pos_refused"] == 1.0


def test_declared_language_wins_over_detection(corpus):
    rates = gate_by_language([{"question": "conta corrente", "positive": True, "language": "en"}],
                             retriever=BM25Retriever(get_index()))
    assert list(rates) == ["en"]
