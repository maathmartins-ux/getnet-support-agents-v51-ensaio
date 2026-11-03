"""Retrieval medido sem LLM: denso/híbrido com cache em disco, cross-encoder local, dedupe, escolha por medida.

Ponto de partida medido: Recall@3 0,486 · MRR 0,61 em 50 perguntas, híbrido nunca medido (fastembed ausente no eval)
e rerank por LLM sem ganho. Tudo aqui roda com embedder/cross-encoder falsos: nenhum teste baixa ou carrega modelo.
"""
import json

import pytest
from fakes import ConceptEmbedder

from app import config, rag
from app.rag import (
    CrossRerankRetriever,
    Doc,
    Gold,
    HybridRetriever,
    Index,
    dedupe,
    doc_vectors,
    get_index,
    get_retriever,
)
from evals import retrieval_eval as rv
from evals import retrieval_review, run_evals


def ids(hits):
    return [h.doc.id for h in hits]


class KeywordScorer:
    name = "keyword"

    def __init__(self, model=None):
        self.calls = 0

    def score(self, query, texts):
        self.calls += 1
        terms = set(query.lower().split())
        return [float(len(terms & set(t.lower().replace("?", "").split()))) for t in texts]


class Broken:
    name = "broken"

    def score(self, query, texts):
        raise RuntimeError("onnx quebrou")


# --- denso, cache, cross-encoder -----------------------------------------------------------------------------
def test_dense_fusion_uses_only_the_embedding_order_but_keeps_bm25_for_the_gate():
    q = "Como peço reembolso?"
    hits = HybridRetriever(get_index(), ConceptEmbedder(), fusion="dense").search(q)
    assert hits[0].doc.id == "faq-troca" and hits[0].bm25 == 0 and hits[0].cosine > 0.9
    assert HybridRetriever(get_index(), ConceptEmbedder(), fusion="dense").name == "dense"


class CountingEmbedder(ConceptEmbedder):
    name = "counting/model"
    cacheable = True

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return super().embed(texts)


def test_doc_vectors_are_cached_on_disk_by_model_and_corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path / "emb"))
    e = CountingEmbedder()
    first = doc_vectors(e, ["a b", "c d"])
    again = doc_vectors(e, ["a b", "c d"])
    assert e.calls == 1 and [[round(x, 6) for x in v] for v in first] == again  # 2ª vez: do disco
    doc_vectors(e, ["a b", "c d mudou"])
    assert e.calls == 2  # corpus mudou → hash novo → recalcula
    assert len(list((tmp_path / "emb").glob("counting_model-*.json"))) == 2


def test_doc_vectors_survive_an_unwritable_cache(tmp_path, monkeypatch):
    blocker = tmp_path / "arquivo"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("EMBED_CACHE_DIR", str(blocker / "sub"))  # pai é arquivo: mkdir falha
    assert len(doc_vectors(CountingEmbedder(), ["a", "b"])) == 2


def test_e5_gets_role_prefixes(monkeypatch):
    seen = []

    class FakeTE:
        def __init__(self, name, **kw):
            pass

        def embed(self, texts, batch_size=256):
            seen.extend(texts)
            return [[1.0, 0.0] for _ in texts]

    fastembed = pytest.importorskip("fastembed")

    monkeypatch.setattr(fastembed, "TextEmbedding", FakeTE)
    e = rag.FastEmbedEmbedder("intfloat/multilingual-e5-large")
    e.embed(["trecho"])
    e.embed_query("pergunta")
    assert seen == ["passage: trecho", "query: pergunta"]


def test_cross_rerank_reorders_the_pool_and_keeps_base_scores():
    base = rag.BM25Retriever(get_index())
    q = "Que horas o atendimento funciona?"
    hits = CrossRerankRetriever(base, KeywordScorer(), pool=20).search(q, k=3)
    assert hits[0].doc.id == "faq-horario" and hits[0].bm25 > 0
    assert CrossRerankRetriever(base, KeywordScorer()).name == "bm25+cross"


def test_cross_rerank_falls_back_to_base_order_on_error():
    base = rag.BM25Retriever(get_index())
    q = "prazo de entrega troca"
    assert ids(CrossRerankRetriever(base, Broken(), pool=20).search(q)) == ids(base.search(q))


def test_fallback_reason_is_recorded_when_fastembed_is_missing(monkeypatch):
    def no_lib(*a, **k):
        raise ImportError("No module named 'fastembed'")

    rag._hybrid_for.cache_clear()
    rag._cross_for.cache_clear()
    monkeypatch.setattr(rag, "FastEmbedEmbedder", no_lib)
    monkeypatch.setattr(rag, "FastEmbedCrossEncoder", no_lib)
    monkeypatch.setenv("RETRIEVER", "dense")
    monkeypatch.setenv("RERANK", "cross")
    r = get_retriever()
    assert r.name == "bm25" and "dense indisponível" in r.fallback and "No module named" in r.fallback
    assert "rerank cross indisponível" in r.fallback
    m = run_evals.retrieval_metrics(retriever=r)
    assert "No module named" in m["fallback"]  # o eval diz o que mediu e por quê
    rag._hybrid_for.cache_clear()
    rag._cross_for.cache_clear()


def test_choice_file_sets_the_defaults_and_env_wins(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "retriever.json").write_text(json.dumps({"choice": {
        "retriever": "dense", "embed_model": "m/e", "rerank": "cross", "rerank_model": "m/r", "rerank_pool": 12}}),
        encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.delenv("RETRIEVER", raising=False)
    assert (config.retriever_name(), config.embed_model(), config.rerank_mode(), config.rerank_model(),
            config.rerank_pool()) == ("dense", "m/e", "cross", "m/r", 12)
    monkeypatch.setenv("RETRIEVER", "bm25")
    monkeypatch.setenv("RERANK", "off")
    assert (config.retriever_name(), config.rerank_mode()) == ("bm25", "off")


# --- dedupe ---------------------------------------------------------------------------------------------------
LONG = "Para receber o desconto no aluguel da maquininha é preciso faturar o mínimo combinado todo mês na conta"


def test_near_duplicate_chunk_is_dropped_and_aliased_to_the_kept_one():
    docs = [Doc("hub-07", "Dúvidas", "https://s/duvidas", LONG + "."),
            Doc("hub-08", "Dúvidas", "https://s/duvidas", "Outro assunto qualquer da página de dúvidas gerais."),
            Doc("aluguel-02", "Aluguel", "https://s/aluguel", LONG + " vigente.")]
    kept, aliases = dedupe(docs)
    assert aliases == {"hub-07": "aluguel-02"}  # o maior (contém o menor) fica
    assert [d.id for d in kept] == ["hub-08", "aluguel-02"]
    same = [Doc("hub-1", "D", "https://s/duvidas", LONG), Doc("hub-2", "D", "https://s/duvidas", "x y z w v u t"),
            Doc("page-1", "A", "https://s/aluguel", LONG)]
    assert dedupe(same)[1] == {"hub-1": "page-1"}  # empate: fica o da página com menos trechos


def test_recall_keeps_the_original_denominator_through_aliases():
    docs = [Doc("b", "t", "u2", "x")]
    g = Gold.from_row({"relevant": ["a", "b"]})
    units = g.resolve_groups(docs, {"a": "b"})
    assert units == [{"b"}, {"b"}]  # 2 passagens do gold continuam 2 unidades
    m = rv.score_question(["b"], ["u2"], units, {"u2"})
    assert m["recall"] == 1.0 and m["ndcg"] == 1.0  # o trecho mantido cobre as 2 passagens: é o top ideal


def test_index_dedupes_by_default_and_flag_turns_it_off(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    rows = [{"id": "a", "title": "t", "url": "u1", "text": LONG}, {"id": "b", "title": "t", "url": "u2", "text": LONG}]
    (d / "k.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(d))
    assert len(get_index().docs) == 1 and get_index().aliases
    monkeypatch.setenv("RAG_DEDUPE", "off")
    assert len(get_index().docs) == 2 and not get_index().aliases


# --- métricas, comparativo, escolha -----------------------------------------------------------------------------
def test_score_question_metrics():
    units = [{"a"}, {"b"}, {"c"}]
    m = rv.score_question(["x", "a", "b"], ["u", "ua", "ub"], units, {"ua", "ub", "uc"})
    assert m["recall"] == pytest.approx(2 / 3) and m["rr"] == 0.5 and m["hit"]
    assert m["ndcg"] == pytest.approx((1 / 1.585 + 1 / 2) / (1 + 1 / 1.585 + 1 / 2), rel=1e-3)
    assert m["page_rr"] == 0.5 and m["page_recall"] == pytest.approx(2 / 3)


def test_compare_writes_per_question_diff_and_latency(tmp_path):
    out = tmp_path / "retrieval_compare.json"
    configs = [{"retriever": "bm25"}, {"retriever": "dense", "embed_model": "fake"},
               {"retriever": "dense", "embed_model": "fake", "rerank": "cross", "rerank_model": "kw"}]
    rep = rv.compare(run_evals.RETRIEVAL, configs, embedder=ConceptEmbedder(), scorer=KeywordScorer, out=out)
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert set(saved["results"]) == {"bm25", "dense", "dense+cross"}
    dense = saved["results"]["dense"]
    assert dense["latency_ms"]["p95"] is not None and len(dense["questions"]) == dense["cases"]
    assert {"top3", "recall", "rr", "ndcg", "page_hit"} <= set(dense["questions"][0])
    diff = rep["diff_vs_baseline"]["dense"]
    assert diff["improved"] and all(r["recall"][1] >= r["recall"][0] for r in diff["improved"])  # sinônimos
    assert "ndcg@3" in dense and "hit@3" in dense["page"]


def test_unavailable_config_is_a_row_with_the_reason():
    def boom(model):
        raise ImportError("sem fastembed")

    rep = rv.compare(run_evals.RETRIEVAL, [{"retriever": "bm25"}, {"retriever": "hybrid", "embed_model": "m"}],
                     embedder=boom)
    assert rep["results"]["hybrid"]["status"] == "unavailable" and "sem fastembed" in rep["results"]["hybrid"]["reason"]


def _res(mrr, recall, p95):
    return {"mrr": mrr, "recall@3": recall, "latency_ms": {"p95": p95}, "config": {"retriever": "x"}}


def test_choose_by_mrr_within_latency_budget():
    results = {"bm25": _res(0.6, 0.5, 1), "dense": _res(0.9, 0.7, 50), "dense+cross": _res(0.95, 0.75, 4000),
               "hybrid": {"status": "unavailable", "reason": "sem modelo"}}
    picked = rv.choose(results, budget_ms=1500)
    assert picked["name"] == "dense" and "4000" in picked["rejected"]["dense+cross"]
    assert "sem modelo" in picked["rejected"]["hybrid"]
    assert rv.choose(results, budget_ms=10000)["name"] == "dense+cross"
    assert rv.choose({"x": _res(0.9, 0.9, 99)}, budget_ms=1)["name"] == "bm25"  # nada no orçamento → bm25


def test_choose_retriever_apply_writes_the_choice_the_app_reads(tmp_path, monkeypatch):
    from conftest import KIT_DATA

    data = tmp_path / "data"
    data.mkdir()
    (data / "sample.jsonl").write_text((KIT_DATA / "data" / "sample.jsonl").read_text("utf-8"), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(data))
    fake = {"retriever": "bm25"}
    monkeypatch.setattr(rv, "default_configs", lambda e, r, pool=None: [fake])
    assert run_evals.main(["--choose-retriever", "--apply"]) == 0
    saved = json.loads((data / "retriever.json").read_text(encoding="utf-8"))
    assert saved["chosen"] == "bm25" and saved["choice"]["retriever"] == "bm25" and "mrr" in saved["measured"]["bm25"]
    assert saved["choice"]["gate"]["min_score"] == saved["measured"]["bm25"]["gate"]["min_score"]  # portão calibrado
    assert config.retriever_name() == "bm25"
    assert (run_evals.RESULTS_DIR / "retrieval_compare.json").exists()


def test_markdown_table_marks_the_choice():
    md = rv.markdown({"bm25": {"recall@3": 0.5, "mrr": 0.6, "hit@3": 0.7, "ndcg@3": 0.5, "page": {"hit@3": 0.9},
                               "latency_ms": {"p50": 1, "p95": 2}}}, "bm25")
    assert "**← escolhida**" in md and "| 0.5 | 0.6 | 0.7 |" in md


# --- revisão do gold e mapeamento -------------------------------------------------------------------------------
def test_review_export_then_apply_writes_a_separate_reviewed_gold(tmp_path):
    review = retrieval_review.export(k=3, out=tmp_path / "review.jsonl")
    rows = [json.loads(line) for line in review.read_text("utf-8").splitlines()]
    assert rows and all(len(r["candidates"]) <= 3 and r["reviewer"] is None for r in rows)
    assert all({"id", "text", "in_gold", "label"} <= set(c) for r in rows for c in r["candidates"])
    first = rows[0]
    for c in first["candidates"]:
        c["label"] = c["id"] == "faq-horario" or c["in_gold"]  # revisor acha um relevante novo
    review.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    with pytest.raises(ValueError):
        retrieval_review.apply(review, "", out=tmp_path / "reviewed.jsonl")
    res = retrieval_review.apply(review, "Ana", out=tmp_path / "reviewed.jsonl", today="2026-11-02")
    assert res["reviewed"] == 1 and len(res["skipped"]) == len(rows) - 1  # revisão parcial não entra
    (got,) = [json.loads(x) for x in (tmp_path / "reviewed.jsonl").read_text("utf-8").splitlines()]
    assert got["reviewer"] == "Ana" and got["reviewed_at"] == "2026-11-02"
    assert set(got["relevant"]) >= set(first["gold"]) and run_evals.RETRIEVAL.read_text("utf-8")  # original intacto


def test_map_gold_follows_the_text_not_the_old_id(tmp_path, monkeypatch):
    old = tmp_path / "old"
    old.mkdir()
    text = "A taxa de débito é de 1,89% no plano de 2 dias úteis e 1,95% no plano receba conforme suas vendas"
    (old / "k.jsonl").write_text(json.dumps({"id": "sup-taxas-05", "title": "T", "url": "u", "text": text}),
                                 encoding="utf-8")
    new = tmp_path / "new"
    new.mkdir()
    rows = [{"id": "sup-taxas-05", "title": "T", "url": "u", "text": "Texto completamente diferente agora aqui."},
            {"id": "sup-taxas-09", "title": "T", "url": "u", "text": "Tabela de taxas. " + text + "."}]
    (new / "k.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    gold = tmp_path / "gold.jsonl"
    gold.write_text(json.dumps({"question": "Qual a taxa de débito?", "relevant": ["sup-taxas-05"]}) + "\n"
                    + json.dumps({"question": "neg", "relevant": []}) + "\n", encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(new))
    res = retrieval_review.map_gold(old, tmp_path / "mapped.jsonl", gold=gold)
    mapped = [json.loads(x) for x in (tmp_path / "mapped.jsonl").read_text("utf-8").splitlines()]
    assert mapped[0]["relevant_groups"] == [["sup-taxas-09"]] and mapped[0]["relevant"] == []  # id velho não vale
    assert res["lost"] == [] and "relevant_groups" not in mapped[1]
    assert Gold.from_row(mapped[0]).resolve_groups(Index([]).docs) == [{"sup-taxas-09"}]


def test_fetch_models_follows_the_choice_file(tmp_path, monkeypatch):
    from app.config import embed_model, rerank_model
    from scripts import fetch_models

    for var in ("RETRIEVER", "RERANK", "EMBED_MODEL", "RERANK_MODEL"):
        monkeypatch.delenv(var, raising=False)
    # sem escolha: o pacote padrão do kit (app.config.KIT_RETRIEVER, denso + cross), os mesmos modelos do app
    assert fetch_models.models(tmp_path) == (embed_model(), rerank_model()) == (fetch_models.FAST_EMBED,
                                                                                fetch_models.FAST_CROSS)
    (tmp_path / "retriever.json").write_text(json.dumps({"choice": {"retriever": "bm25"}}), encoding="utf-8")
    assert fetch_models.models(tmp_path) == (None, None)  # escolha bm25: nada a baixar
    (tmp_path / "retriever.json").write_text(json.dumps({"choice": {"retriever": "dense", "rerank": "cross"}}),
                                             encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "vazio"))  # padrões do app, sem arquivo de escolha
    assert fetch_models.models(tmp_path) == (embed_model(), rerank_model())  # padrões iguais aos do app


def test_verify_flags_drift_between_recorded_choice_and_new_measure():
    recorded = {"chosen": "dense", "measured": {
        "dense": {"mrr": 0.9, "recall@3": 0.7, "config": {"retriever": "dense", "embed_model": "e5", "gate": {}}},
        "bm25": {"mrr": 0.6, "recall@3": 0.5, "config": {"retriever": "bm25"}}}}
    same = {"dense": {"mrr": 0.905, "recall@3": 0.7}, "bm25": {"mrr": 0.6, "recall@3": 0.5}}
    assert rv.verify(recorded, same) == []
    assert rv.verify({}, same) == []  # sem escolha gravada: nada a conferir
    drift = rv.verify(recorded, {"dense": {"mrr": 0.8, "recall@3": 0.7}, "bm25": {"status": "unavailable",
                                                                                   "reason": "x"}})
    assert any("mrr de dense" in p for p in drift) and any("bm25 indisponível" in p for p in drift)
    assert rv.verify_configs(recorded) == {"dense": {"retriever": "dense", "embed_model": "e5"},
                                           "bm25": {"retriever": "bm25"}}  # só a escolhida e o baseline
    assert rv.recorded_models(recorded) == (["e5"], [])


def test_verify_cli_remeasures_only_the_recorded_choice(tmp_path, monkeypatch):
    from conftest import KIT_DATA

    data = tmp_path / "data"
    data.mkdir()
    (data / "sample.jsonl").write_text((KIT_DATA / "data" / "sample.jsonl").read_text("utf-8"), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(data))
    assert run_evals.main(["--choose-retriever", "--verify"]) == 0  # sem escolha gravada: passa
    monkeypatch.setattr(rv, "default_configs", lambda e, r, pool=None: [{"retriever": "bm25"}])
    assert run_evals.main(["--choose-retriever", "--apply"]) == 0
    assert run_evals.main(["--choose-retriever", "--verify"]) == 0
    saved = json.loads((data / "retriever.json").read_text("utf-8"))
    saved["measured"]["bm25"]["mrr"] = 0.01  # gravado diferente do que se mede: deriva
    (data / "retriever.json").write_text(json.dumps(saved), encoding="utf-8")
    assert run_evals.main(["--choose-retriever", "--verify"]) == 1


def test_readme_retrieval_block_reads_the_choice_file(tmp_path):
    from scripts.fill_readme import retrieval_block

    assert "Não rodado" in retrieval_block(tmp_path, data=tmp_path)
    (tmp_path / "retriever.json").write_text(json.dumps({
        "gold": "k.jsonl", "chosen_at": "2026-11-02", "git_sha": "abc", "criterion": "maior MRR",
        "latency_budget_ms": 1500, "chosen": "bm25", "measured": {"bm25": {
            "recall@3": 0.5, "mrr": 0.6, "hit@3": 0.7, "ndcg@3": 0.5, "page": {"hit@3": 0.9},
            "latency_ms": {"p50": 1, "p95": 2}}}}), encoding="utf-8")
    block = retrieval_block(tmp_path, data=tmp_path)
    assert "bm25 **← escolhida**" in block and "1500 ms" in block


def test_gate_is_calibrated_per_retriever_with_both_thresholds():
    """e5: positivos e negativos com cosseno 0,8–0,9; o piso fixo 0,4 deixava passar todo negativo."""
    pos = [[(0.0, 0.90, True), (0.0, 0.84, False)], [(0.0, 0.88, True)]]
    neg = [[(0.0, 0.83, False)], [(0.0, 0.85, False)]]
    gate = rv.calibrate_gate(pos, neg)
    assert gate["min_cosine"] == 0.88 and gate["pos_answered"] == 1.0 and gate["neg_refused"] == 1.0
    assert gate["min_score"] == rv.BM25_OFF  # caminho do BM25 desligado: nenhum score separa os dois grupos
    from app.agents import covered_hits
    from app.rag import Hit

    hits = [Hit(Doc("n", "t", "u", "x"), 0.0, bm25=0.0, cosine=0.85)]
    assert covered_hits(hits)  # piso padrão 0,4: o negativo passaria
    assert not covered_hits(hits, gate={"min_cosine": 0.88})  # limiar da escolha: recusa


def test_choose_rejects_a_config_whose_gate_cannot_refuse_negatives():
    bad = {**_res(0.99, 0.9, 10), "gate": {"meets_floor": False, "neg_refused": 0.0, "neg_refusal_min": 0.85}}
    good = {**_res(0.6, 0.5, 1), "gate": {"meets_floor": True, "min_score": 8.5, "min_cosine": rv.COSINE_OFF}}
    picked = rv.choose({"dense": bad, "bm25": good})
    assert picked["name"] == "bm25" and "portão" in picked["rejected"]["dense"]
    assert picked["config"]["gate"] == {"min_score": 8.5, "min_cosine": 2.0}


def test_retriever_carries_the_choice_gate_only_without_fallback(tmp_path, monkeypatch):
    from conftest import KIT_DATA

    data = tmp_path / "data"
    data.mkdir()
    (data / "sample.jsonl").write_text((KIT_DATA / "data" / "sample.jsonl").read_text("utf-8"), encoding="utf-8")
    (data / "retriever.json").write_text(json.dumps({"choice": {"retriever": "bm25", "gate": {"min_score": 99}}}),
                                         encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.delenv("RETRIEVER", raising=False)
    assert get_retriever().gate == {"min_score": 99}
    monkeypatch.setenv("RETRIEVER", "hybrid")  # ambiente trocou o retriever: o limiar calibrado não vale
    monkeypatch.setattr(rag, "_hybrid_for", lambda *a, **k: None)
    assert get_retriever().gate == {}


def test_choose_reuse_repicks_from_the_saved_compare_without_measuring(tmp_path, monkeypatch):
    from conftest import KIT_DATA

    data = tmp_path / "data"
    data.mkdir()
    (data / "sample.jsonl").write_text((KIT_DATA / "data" / "sample.jsonl").read_text("utf-8"), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setattr(rv, "default_configs", lambda e, r, pool=None: [{"retriever": "bm25"}])
    assert run_evals.main(["--choose-retriever"]) == 0

    def no_measure(*a, **k):
        raise AssertionError("--reuse não deveria medir de novo")

    monkeypatch.setattr(rv, "compare", no_measure)
    assert run_evals.main(["--choose-retriever", "--reuse", "--apply", "--latency-budget-ms", "999"]) == 0
    saved = json.loads((data / "retriever.json").read_text(encoding="utf-8"))
    assert saved["latency_budget_ms"] == 999 and saved["chosen"] == "bm25"


def test_first_run_and_cached_vectors_are_identical(tmp_path, monkeypatch):
    """Vetor arredondado já na 1ª vez: a ordem da busca não muda entre a subida que calcula e a que lê do disco."""
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path))

    class Noisy(CountingEmbedder):
        def embed(self, texts):
            return [[0.1234567891, 0.9876543219] for _ in texts]

    assert doc_vectors(Noisy(), ["x"]) == doc_vectors(Noisy(), ["x"]) == [[0.123457, 0.987654]]
    assert not list(tmp_path.glob("*.tmp"))  # o temporário por processo some no replace


def test_grid_crosses_pool_sizes():
    cfgs = rv.default_configs(["e"], ["r"], [5, 20])
    pools = sorted(c["rerank_pool"] for c in cfgs if c.get("rerank"))
    assert pools == [5, 5, 5, 20, 20, 20] and len(cfgs) == 9  # 3 bases + 3 x 2 pools


# --- R2: memória e tempo do denso no relógio --------------------------------------------------------------------
class RecordingTE:
    """TextEmbedding falso: guarda opções de sessão, lotes e quantas vezes o modelo rodou."""

    def __init__(self, name, **kw):
        self.kw, self.batches, self.calls = kw, [], 0

    def embed(self, texts, batch_size=256):
        self.calls += 1
        self.batches.append((list(texts), batch_size))
        return [[float(len(t)), 1.0] for t in texts]


def test_corpus_embedding_uses_small_length_sorted_batches_without_arena(monkeypatch):
    fastembed = pytest.importorskip("fastembed")

    monkeypatch.setattr(fastembed, "TextEmbedding", RecordingTE)
    e = rag.FastEmbedEmbedder("m")
    out = e.embed(["ccc", "a", "bb"])
    assert out == [[3.0, 1.0], [1.0, 1.0], [2.0, 1.0]]  # ordem de entrada
    texts, size = e._model.batches[0]
    assert texts == ["a", "bb", "ccc"] and size == rag.EMBED_BATCH  # por tamanho: lote quase sem enchimento
    assert e._model.kw == {"enable_cpu_mem_arena": False}
    monkeypatch.setenv("RAG_ONNX_ARENA", "on")
    assert rag.onnx_options() == {}


def test_query_vectors_are_memoized_in_process_and_on_disk(monkeypatch, tmp_path):
    fastembed = pytest.importorskip("fastembed")

    monkeypatch.setattr(fastembed, "TextEmbedding", RecordingTE)
    e = rag.FastEmbedEmbedder("m")
    first = e.embed_query("taxa do pix")
    assert e.embed_query("taxa do pix") == first and e._model.calls == 1
    assert not list(tmp_path.glob("*.jsonl"))  # sem RAG_QUERY_CACHE=disk nada vai para disco
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("RAG_QUERY_CACHE", "disk")
    a = rag.FastEmbedEmbedder("m")
    va = a.embed_query("prazo do débito")
    (tmp_path / "q-m.jsonl").open("a", encoding="utf-8").write("{cortada\n")  # gravação concorrente cortada
    b = rag.FastEmbedEmbedder("m")  # outro processo: lê do disco, não roda o modelo
    assert b.embed_query("prazo do débito") == va and b._model.calls == 0


def test_cross_scores_only_new_pairs(monkeypatch, tmp_path):
    cross_encoder = pytest.importorskip("fastembed.rerank.cross_encoder")

    class FakeCross:
        def __init__(self, name, **kw):
            self.pairs = []

        def rerank(self, query, texts, batch_size=64):
            self.pairs += [(query, t) for t in texts]
            return [float(len(t)) for t in texts]

    monkeypatch.setattr(cross_encoder, "TextCrossEncoder", FakeCross)
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("RAG_QUERY_CACHE", "disk")
    c = rag.FastEmbedCrossEncoder("x")
    assert c.score("q", ["aa", "b"]) == [2.0, 1.0]
    assert c.score("q", ["b", "cccc", "aa"]) == [1.0, 4.0, 2.0]
    assert c._model.pairs == [("q", "aa"), ("q", "b"), ("q", "cccc")]  # só o par novo foi ao modelo
    assert rag.FastEmbedCrossEncoder("x").score("q", ["cccc"]) == [4.0]  # do disco


def test_numpy_and_python_cosines_rank_the_same():
    r = HybridRetriever(get_index(), ConceptEmbedder(), fusion="dense")
    q = "Que horas o atendimento funciona?"
    with_np = [h.doc.id for h in r.search(q, k=5)]
    r._matrix = None
    assert [h.doc.id for h in r.search(q, k=5)] == with_np


def test_latency_measurement_never_reads_the_memo(monkeypatch, tmp_path):
    """O comparativo mede várias configurações com o MESMO embedder: memo lido faria a 2ª parecer mais rápida."""
    fastembed = pytest.importorskip("fastembed")

    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path))

    from evals.retrieval_eval import evaluate
    from evals.run_evals import RETRIEVAL

    monkeypatch.setattr(fastembed, "TextEmbedding", RecordingTE)
    e = rag.FastEmbedEmbedder("m")
    r = HybridRetriever(get_index(), e, fusion="dense")
    evaluate(RETRIEVAL, r)
    calls = e._model.calls
    evaluate(RETRIEVAL, r)
    assert e._model.calls == 2 * calls - 1  # cada consulta rodou o modelo de novo (o corpus, só na 1ª vez)


def test_choose_rejects_a_config_over_the_ram_budget():
    results = {"bm25": {**_res(0.6, 0.5, 1), "memory_mb": 300.0},
               "dense+cross": {**_res(0.95, 0.75, 800), "memory_mb": 2700.0},
               "dense": {**_res(0.9, 0.7, 90), "memory_mb": 2100.0}}
    picked = rv.choose(results, budget_ms=1500, ram_budget_mb=2500)
    assert picked["name"] == "dense" and "RAM 2700 MB > orçamento 2500 MB" in picked["rejected"]["dense+cross"]
    assert rv.choose(results, budget_ms=1500, ram_budget_mb=None)["name"] == "dense+cross"  # sem teto
    assert rv.choose({"x": _res(0.9, 0.9, 1)}, ram_budget_mb=1)["name"] == "x"  # RAM não medida não reprova


def test_compare_measures_ram_per_config_from_model_loads(monkeypatch):
    rag._embedder_for.cache_clear()  # processo sem modelo carregado (senão a RAM sai None, de propósito)
    rag._cross_for.cache_clear()
    rss = iter([500.0, 500.0, 2500.0, 2500.0, 3100.0])  # bm25 (sem modelo); e5 antes/depois; cross antes/depois

    class Cross:
        name = "x"

        def score(self, q, texts):
            return [0.0] * len(texts)

    cfgs = [{"retriever": "bm25"}, {"retriever": "dense", "embed_model": "e"},
            {"retriever": "dense", "embed_model": "e", "rerank": "cross", "rerank_model": "x", "rerank_pool": 5}]
    rep = rv.compare(run_evals.RETRIEVAL, cfgs, embedder=ConceptEmbedder(), scorer=Cross(), rss=lambda: next(rss))
    mem = {n: r["memory_mb"] for n, r in rep["results"].items()}
    assert mem == {"bm25": 500.0, "dense": 2500.0, "dense+cross": 3100.0}


def test_fast_choice_measures_only_the_preselected_configs(tmp_path, monkeypatch):
    from conftest import KIT_DATA

    data = tmp_path / "data"
    data.mkdir()
    (data / "sample.jsonl").write_text((KIT_DATA / "data" / "sample.jsonl").read_text("utf-8"), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(data))
    seen = []

    def fake_compare(path, configs, **kw):
        seen.extend(configs)
        row = {**_res(0.6, 0.5, 1), "hit@3": 0.7, "page": {"hit@3": 0.9}, "config": configs[0]}
        return {"recorded_at": "t", "gold": "g", "results": {"bm25": row}, "diff_vs_baseline": {}}

    monkeypatch.setattr(rv, "compare", fake_compare)
    assert run_evals.main(["--choose-retriever", "--fast", "--apply", "--ram-budget-mb", "3000"]) == 0
    assert seen == list(rv.FAST_CONFIGS) and len(seen) == 3
    saved = json.loads((data / "retriever.json").read_text(encoding="utf-8"))
    assert saved["ram_budget_mb"] == 3000 and "RAM <= 3000 MB" in saved["criterion"]


def test_fetch_models_fast_downloads_what_the_fast_choice_measures(monkeypatch, capsys):
    """T+0 do relógio: o fetch_models --fast baixa em 2º plano os modelos que o --choose-retriever --fast vai medir."""
    fastembed = pytest.importorskip("fastembed")
    cross_encoder = pytest.importorskip("fastembed.rerank.cross_encoder")

    from scripts import fetch_models

    loaded = []
    monkeypatch.setattr(fastembed, "TextEmbedding", lambda name: loaded.append(name))
    monkeypatch.setattr(cross_encoder, "TextCrossEncoder", lambda name: loaded.append(name))
    assert fetch_models.main(["--fast"]) == 0
    measured = {c.get("embed_model") for c in rv.FAST_CONFIGS} | {c.get("rerank_model") for c in rv.FAST_CONFIGS}
    assert set(loaded) == measured - {None} and "MODELOS PRONTOS" in capsys.readouterr().out


def test_essential_passage_rule_is_one_unit_satisfied_by_any_copy():
    """Gold do relógio: uma regex por fato necessário; a mesma FAQ copiada em várias páginas é UMA passagem."""
    docs = [Doc("a-1", "t", "u1", "Pessoa física pode ter até 5 chaves Pix"),
            Doc("b-7", "t", "u2", "Até 5 chaves Pix por conta, pessoa física"),
            Doc("a-2", "t", "u1", "Informe uma chave de sua escolha à Getnet")]
    g = Gold.from_row({"passage_text": [r"5 chaves Pix", r"uma chave de sua escolha"], "relevant": ["a-1", "a-2"]})
    assert g.positive and g.related
    assert g.resolve_groups(docs) == [{"a-1", "b-7"}, {"a-2"}]  # essenciais: qualquer cópia satisfaz
    assert g.resolve_groups(docs, related=True) == [{"a-1"}, {"a-2"}]  # "todo relacionado", à parte
    only = Gold.from_row({"passage_text": "chave de sua escolha"})
    assert only.positive and not only.related and only.matches(docs[2]) and not only.matches(docs[0])


def test_evaluate_reports_essential_and_related_side_by_side(tmp_path):
    from evals.retrieval_eval import evaluate

    q = "Que horas o atendimento funciona?"
    gold = tmp_path / "g.jsonl"
    gold.write_text(json.dumps({"question": q, "passage_text": ["(?i)hor[aá]rio|atendimento"],
                                "relevant": ["faq-horario", "nao-existe"]}) + "\n", encoding="utf-8")
    out = evaluate(gold, rag.BM25Retriever(get_index()))
    assert out["essential"] == 1 and out["related"]["cases"] == 1
    assert out["recall@3"] == 1.0 and out["related"]["recall@3"] == 0.5  # o id inexistente só pesa no relacionado


def test_reingested_corpus_only_embeds_new_passages(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path))
    seen = []

    class E(CountingEmbedder):
        def embed(self, texts):
            seen.append(list(texts))
            return super().embed(texts)

    first = doc_vectors(E(), ["a b", "c d"])
    again = doc_vectors(E(), ["c d", "e f", "a b"])  # corpus re-ingerido: 1 trecho novo, ordem trocada
    assert seen == [["a b", "c d"], ["e f"]]
    assert again[0] == first[1] and again[2] == first[0]


def test_worktree_shares_the_main_repository_cache(tmp_path, monkeypatch):
    from app import config as cfg

    main = tmp_path / "main"
    (main / ".git" / "worktrees" / "k").mkdir(parents=True)
    wt = tmp_path / "main-k"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'k'}\n", encoding="utf-8")
    assert cfg._main_root(wt) == main
    assert cfg._main_root(main) == main  # repositório normal (.git é pasta)
    assert cfg._main_root(tmp_path / "sem-git") == tmp_path / "sem-git"  # container
    monkeypatch.setattr(cfg, "ROOT", wt)
    monkeypatch.delenv("EMBED_CACHE_DIR", raising=False)
    assert cfg.embed_cache_dir() == main / "var" / "embeddings"


def test_make_eval_compares_only_the_choice_its_base_and_bm25(tmp_path, monkeypatch):
    """`make eval` com o denso escolhido media 3 linhas de cross@20 (> 2,7 s de p95 por consulta): fora do relógio."""
    from conftest import KIT_DATA

    data = tmp_path / "data"
    data.mkdir()
    (data / "sample.jsonl").write_text((KIT_DATA / "data" / "sample.jsonl").read_text("utf-8"), encoding="utf-8")
    choice = {"retriever": "dense", "embed_model": "e", "rerank": "cross", "rerank_model": "x", "rerank_pool": 5,
              "gate": {"min_score": 1}}
    (data / "retriever.json").write_text(json.dumps({"choice": choice}), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(data))
    assert run_evals._chosen_configs() == [
        {"retriever": "bm25"}, {"retriever": "dense", "embed_model": "e"},
        {"retriever": "dense", "embed_model": "e", "rerank": "cross", "rerank_model": "x", "rerank_pool": 5}]
    (data / "retriever.json").write_text(json.dumps({"choice": {"retriever": "bm25"}}), encoding="utf-8")
    assert run_evals._chosen_configs() == [{"retriever": "bm25"}]


def test_cross_rerank_reads_only_the_configured_passage_length(monkeypatch):
    seen = []

    class Spy:
        name = "spy"

        def score(self, query, texts):
            seen.extend(texts)
            return [0.0] * len(texts)

    r = rag.CrossRerankRetriever(rag.BM25Retriever(get_index()), Spy(), pool=5, chars=40)
    r.search("prazo de entrega, troca e horário de atendimento", k=3)
    assert seen and max(map(len, seen)) <= 40
    monkeypatch.setenv("RERANK_CHARS", "600")
    assert rag.CrossRerankRetriever(rag.BM25Retriever(get_index()), Spy(), pool=5).chars == 600
    assert rv.config_name({"retriever": "dense", "embed_model": "a/e5", "rerank": "cross", "rerank_model": "b/bge",
                           "rerank_pool": 20, "rerank_chars": 600}, True) == "dense[e5]+cross[bge@20/600c]"


def test_compare_reuses_the_process_models_instead_of_a_second_copy(monkeypatch):
    """`make eval` com o app aquecido: o comparativo usava outra cópia do e5-large e do bge (4951 MB no processo)."""
    loads = []

    class E(ConceptEmbedder):
        name = "e"
        cacheable = False

        def __init__(self, model=None):
            loads.append(model)

    monkeypatch.setattr(rag, "FastEmbedEmbedder", E)
    rag._embedder_for.cache_clear()
    try:
        app_model = rag._embedder_for("e")  # o que o app carregou no aquecimento
        fx = rv._Factories(rss=lambda: 100.0)
        assert fx.embed("e") is app_model and loads == ["e"]
        assert fx.model_mb["e"] is None  # já estava carregado: RAM não medida aqui, em vez de um delta zero
        assert fx.memory_mb({"retriever": "dense", "embed_model": "e"}) is None
        assert rv._Factories(rss=lambda: 100.0).memory_mb({"retriever": "bm25"}) is None  # processo já com modelo
    finally:
        rag._embedder_for.cache_clear()
