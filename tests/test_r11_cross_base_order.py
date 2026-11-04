"""R11-F: na ordem do base, o cross-encoder pontua só os k trechos que a busca devolve (o portão só lê a nota deles),
com a mesma saída do caminho antigo; e o cross-encoder pontua um par por chamada, para a nota de um trecho não mudar
com os outros trechos do lote (o modelo int8 quantiza a ativação com a escala do lote inteiro)."""
from dataclasses import replace

import pytest

from app import rag
from app.rag import Doc, Hit


class _Base:
    name = "dense"

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, k=3):
        return self.hits[:k]  # sem diversify: o buscador do kit aplica o teto por URL de novo, sobre o pool


class _CountingScorer:
    """Nota fixa por texto (a do par, não a da posição) e a conta de cada texto recebido."""

    name = "conta"

    def __init__(self):
        self.seen: list[str] = []

    @staticmethod
    def note(text: str) -> float:
        return round(int(text.rsplit(" ", 1)[1]) * 0.37 - 1.5, 4)  # "t3. texto 3" → 3 × 0,37 − 1,5

    def score(self, query, texts):
        self.seen += texts
        return [self.note(t) for t in texts]


def _pool(n=10):
    # d0, d1 e d2 na mesma página: com o teto de 2 por URL, d2 sai do top e volta só como sobra
    urls = ["u0", "u0", "u0", *(f"u{i}" for i in range(3, n))]
    return [Hit(Doc(f"d{i}", f"t{i}", url, f"texto {i}"), 1.0 - i / 100, bm25=1.0, cosine=0.9 - i / 100)
            for i, url in enumerate(urls)]


def _old_base_order(pool, k, scorer):
    """O caminho antigo da ordem do base: o pool inteiro pontuado, a nota em cada trecho, o mesmo diversify."""
    texts = [f"{h.doc.head}. {h.doc.text}"[:600] for h in pool]
    return rag.diversify([replace(h, rerank=float(s)) for h, s in zip(pool, scorer.score("q", texts), strict=True)], k)


def test_base_order_scores_only_the_k_returned_with_the_same_ids_and_notes():
    pool = _pool()
    scorer = _CountingScorer()
    got = rag.CrossRerankRetriever(_Base(pool), scorer, pool=10, chars=600, order="base").search("q", k=5)
    assert len(scorer.seen) == 5  # metade dos pares do pool de 10: o faq lê o top 5
    old = _old_base_order(pool, 5, _CountingScorer())
    assert [h.doc.id for h in got] == [h.doc.id for h in old] == ["d0", "d1", "d3", "d4", "d5"]  # teto por URL
    assert [h.rerank for h in got] == [h.rerank for h in old]  # a nota que o portão lê é a mesma
    assert scorer.seen == [f"{h.doc.head}. {h.doc.text}" for h in got]  # pontuou exatamente os devolvidos


def test_base_order_with_k_up_to_the_pool_and_cross_order_still_read_the_whole_pool():
    pool = _pool()
    every = _CountingScorer()
    got = rag.CrossRerankRetriever(_Base(pool), every, pool=10, chars=600, order="base").search("q", k=10)
    assert len(every.seen) == 10 and [h.rerank for h in got] == [h.rerank for h in _old_base_order(pool, 10, every)]
    cross = _CountingScorer()
    ranked = rag.CrossRerankRetriever(_Base(pool), cross, pool=10, chars=600, order="cross").search("q", k=5)
    assert len(cross.seen) == 10  # reordenar pela nota precisa da nota de todos
    assert ranked[0].doc.id == "d9"  # a maior nota (9 × 0,37 − 1,5) sobe para o topo


def test_broken_scorer_still_answers_in_the_base_order():
    class Broken:
        name = "quebrado"

        def score(self, query, texts):
            raise RuntimeError("onnx quebrou")

    pool = _pool()
    got = rag.CrossRerankRetriever(_Base(pool), Broken(), pool=10, order="base").search("q", k=5)
    assert [h.doc.id for h in got] == [h.doc.id for h in pool[:5]] and all(h.rerank is None for h in got)


def test_cross_encoder_scores_one_pair_per_call_so_a_note_does_not_depend_on_the_batch(monkeypatch):
    """Medido no int8 (DynamicQuantizeLinear): a nota de um par mudava até 0,51 entre o lote de 10 e o de 5. O modelo
    falso imita isso (a nota cresce com o tamanho do lote); o cross-encoder do kit tem de dar a nota do par sozinho."""
    cross_encoder = pytest.importorskip("fastembed.rerank.cross_encoder")

    class BatchSensitive:
        def __init__(self, name, **kw):
            self.batches: list[int] = []

        def rerank(self, query, texts, batch_size=64):
            self.batches.append(len(texts))
            return [len(t) + 0.01 * len(texts) for t in texts]

    monkeypatch.setattr(cross_encoder, "TextCrossEncoder", BatchSensitive)
    a, b = rag.FastEmbedCrossEncoder("x"), rag.FastEmbedCrossEncoder("x")  # memos separados: nada vem de cache
    assert a.score("q", ["aa", "bbbb", "c"]) == pytest.approx([2.01, 4.01, 1.01])  # em lote de 3 seria + 0,03
    assert b.score("q", ["aa"]) == pytest.approx([2.01])  # o mesmo par, sozinho ou com outros: a mesma nota
    assert set(a._model.batches) == {1} and set(b._model.batches) == {1}
