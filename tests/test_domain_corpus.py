"""Integridade do corpus COMMITADO do desafio (frente K). Pulado no kit puro (sem domínio do desafio)."""

import hashlib
import json
from collections import Counter

import pytest

from app.config import ROOT
from app.ingest import MAX_CHARS, MIN_CHARS, SHORT_PAGE, is_allowed, load_sources

CORPUS = ROOT / "data" / "knowledge"


def _corpus() -> list[dict]:
    return [json.loads(line) for f in sorted(CORPUS.rglob("*.jsonl")) for line in f.read_text("utf-8").splitlines()
            if line.strip()]


@pytest.fixture
def corpus(domain_data):
    docs = _corpus()
    if not docs:
        pytest.skip("corpus do desafio ainda não ingerido (frente K)")
    return docs


def test_corpus_is_literal_sized_hashed_and_from_allowed_hosts(corpus):
    hosts = load_sources(ROOT / "data" / "sources.json")["allowed_hosts"]
    ids = [d["id"] for d in corpus]
    assert len(ids) == len(set(ids)), "id duplicado no corpus"
    per_url = Counter(d["url"] for d in corpus)
    for d in corpus:
        assert is_allowed(d["url"], hosts), d["url"]
        # artigo curto de central de ajuda (ingest.build no modo artigo) é 1 trecho só, abaixo do mínimo
        low = SHORT_PAGE if per_url[d["url"]] == 1 else MIN_CHARS
        assert low <= len(d["text"]) <= MAX_CHARS, d["id"]
        assert d["sha256"] == hashlib.sha256(d["text"].encode("utf-8")).hexdigest(), d["id"]


def test_corpus_has_no_empty_page_file():
    """Arquivo de página com 0 trecho (0 byte) foi apontado na avaliação cega da rodada 11 (get-ajuda.jsonl e
    reserva-financeira.jsonl): página sem trecho sai de sources.json ou entra pela central de ajuda."""
    empty = [str(f.relative_to(ROOT)) for f in sorted(CORPUS.rglob("*.jsonl")) if not f.read_text("utf-8").strip()]
    assert not empty, empty


def test_retrieval_questions_point_to_existing_ids(corpus):
    """Todo gold resolve no corpus atual: id existe e cada regra (relevant_urls/relevant_text) casa algum trecho."""
    from app.jsonl import read_family
    from app.rag import Doc, Gold

    docs = [Doc(d["id"], d["title"], d["url"], d["text"]) for d in corpus]
    ids = {d.id for d in docs}
    rows = read_family(ROOT / "evals" / "retrieval.jsonl")
    assert rows, "sem perguntas de retrieval (evals/retrieval.d/)"
    missing = [(r["question"], sorted(set(r.get("relevant") or []) - ids)) for r in rows
               if set(r.get("relevant") or []) - ids]
    assert not missing, missing[:5]
    dead = [r["question"] for r in rows for rule in (Gold.from_row({"relevant_urls": r.get("relevant_urls")}),
                                                      Gold.from_row({"relevant_text": r.get("relevant_text")}))
            if rule.positive and not any(rule.matches(d) for d in docs)]
    assert not dead, f"regra de gold que não casa nenhum trecho: {dead[:5]}"
