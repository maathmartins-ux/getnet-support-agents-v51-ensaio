"""Gold de retrieval por regra (regex de URL / regex do texto) além do id, e métricas por página.

Getnet v4 (01/11/2026): o re-ingest renomeou os ids e o gold por id quebrou; Recall@3 0,486 por trecho era lido
como fraco sem o número por página ao lado.
"""
import json

from app.rag import Doc, Gold, Hit, pages
from evals import run_evals


def _doc(i, url, text="x"):
    return Doc(i, "t", url, text)


def test_trecho_relevante_por_id_ou_regra():
    g = Gold.from_row({"relevant": ["a"], "relevant_urls": [r"/troca"], "relevant_text": r"prazo de \d+ dias"})
    assert g.matches(_doc("a", "https://x/outra"))
    assert g.matches(_doc("b", "https://x/troca/"))
    assert g.matches(_doc("c", "https://x/z", "O PRAZO de 7 dias vale"))
    assert not g.matches(_doc("d", "https://x/z", "nada a ver"))
    assert not Gold.from_row({"relevant": []}).positive
    assert Gold.from_row({"relevant_urls": "/troca"}).positive  # regra sozinha (string ou lista) já é positiva


def test_regra_sobrevive_a_re_ingest():
    """O id antigo some depois do re-ingest; a regra acha o trecho novo, e a URL resolve a página."""
    g = Gold.from_row({"relevant": ["old-01"], "relevant_text": "devolução em 7 dias"})
    docs = [_doc("new-03", "https://x/troca", "A devolução em 7 dias é grátis."), _doc("new-04", "https://x/y")]
    ids, urls = g.resolve(docs)
    assert ids == {"old-01", "new-03"} and urls == {"https://x/troca"}


def test_pages_dedup_na_ordem_do_ranking():
    hits = [Hit(_doc(i, u), 1.0) for i, u in [("1", "u1"), ("2", "u1"), ("3", "u2")]]
    assert pages(hits) == ["u1", "u2"]


class _Fixed:
    name = "fixo"

    def __init__(self, docs):
        self.docs = docs

    def search(self, q, k=3):
        return [Hit(d, 1.0, bm25=1.0) for d in self.docs[:k]]


def test_metricas_por_trecho_e_por_pagina(tmp_path, monkeypatch):
    from app import rag

    docs = [_doc("p1-a", "https://s/p1", "alfa"), _doc("p1-b", "https://s/p1", "beta"),
            _doc("p2-a", "https://s/p2", "gama")]
    monkeypatch.setattr(rag, "get_index", lambda: rag.Index(docs))
    path = tmp_path / "retrieval.jsonl"
    rows = [{"question": "q1", "relevant_text": "gama"},  # trecho certo só no 3º lugar
            {"question": "q2", "relevant_urls": [r"/p1$"]},  # página certa no 1º lugar, 2 trechos dela
            {"question": "q3", "relevant": ["sumiu-01"]},  # id que não existe mais
            {"question": "neg", "relevant": []}]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    m = run_evals.retrieval_metrics(path, retriever=_Fixed(docs))
    assert m["positives"] == 3 and m["negatives"] == 1
    assert m["recall@3"] == round((1 + 1 + 0) / 3, 3) and m["mrr"] == round((1 / 3 + 1 + 0) / 3, 3)
    # por página: q1 acha p2 na 2ª página distinta; q2 na 1ª
    assert m["page"]["recall@3"] == round(2 / 3, 3) and m["page"]["mrr"] == round((1 / 2 + 1) / 3, 3)
    assert m["gold_unresolved"] == ["q3"]
    assert "por página" in run_evals._retrieval_line(m)


def test_calibracao_do_portao_aceita_gold_por_regra(tmp_path):
    path = tmp_path / "retrieval.jsonl"
    rows = [{"question": "Qual o prazo de entrega?", "relevant_text": "dias úteis"},
            {"question": "Posso devolver um produto?", "relevant_urls": ["troca"]},
            {"question": "Qual a capital da Mongólia?", "relevant": []}]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    cal = run_evals.calibrate_gate(path)
    assert cal["positives"] == 2 and cal["best"]["pos_answered"] > 0
