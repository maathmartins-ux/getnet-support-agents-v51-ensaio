"""Kit v5.4: placar de busca pelo método do nelsondell (top-5 do redator, rank do 1º gold, origem, caminho)."""
from evals import retrieval_eval, run_evals


def test_score_question_has_recall5_mrr10_and_first_gold_rank():
    got = ["a", "b", "c", "d", "gold", "f"]
    m = retrieval_eval.score_question(got, [""] * 6, [{"gold"}], set())
    assert m["recall"] == 0.0 and m["recall5"] == 1.0 and m["first"] == 5 and abs(m["rr10"] - 0.2) < 1e-9


def test_by_origin_splits_the_score():
    rows = [{"origin": "page", "recall": 1.0, "recall5": 1.0, "rr10": 1.0},
            {"origin": "real", "recall": 0.0, "recall5": 1.0, "rr10": 0.25}]
    out = retrieval_eval._by_origin(rows)
    assert out["page"]["recall@5"] == 1.0 and out["real"]["recall@3"] == 0.0 and out["real"]["mrr@10"] == 0.25


def test_published_retrieval_is_the_agent_path_with_the_base_beside_it():
    ret = run_evals.retrieval_metrics()
    assert ret["path"] == "agente" and "recall@5" in ret and "mrr@10" in ret and "first_gold_rank" in ret
    assert {"retriever", "recall@3", "mrr"} <= set(ret["base"])
    line = run_evals._retrieval_line(ret)
    assert "Recall@5 (o que o redator lê)" in line and "buscador base sem rerank" in line


def test_bm25_only_fuses_when_the_query_is_in_the_corpus_language(monkeypatch):
    from app import agents, rag

    monkeypatch.setattr(agents, "corpus_language", lambda: "pt")
    assert rag.lexical_fits("Preciso de conta bancária para receber vendas pelo Pix?")
    assert not rag.lexical_fits("Do I need a bank account to receive my sales via Pix?")
    monkeypatch.setenv("HYBRID_LANG_GATE", "off")
    assert rag.lexical_fits("Do I need a bank account to receive my sales via Pix?")


def test_offline_plan_also_searches_the_customer_words_first():
    from app import agents

    seen = []

    class Fake:
        name, gate = "fake", None

        def search(self, query, k=3):
            seen.append(query)
            return []

    agents.retrieve("Do I need a bank account to receive my sales via Pix?", retriever=Fake(), k=5)
    assert seen[0] == "Do I need a bank account to receive my sales via Pix?"


def test_separation_reports_auc_and_gap():
    pos = [[(0.0, 0.9, True)], [(0.0, 0.8, True)]]
    neg = [[(0.0, 0.5, False)]] * 15
    sep = retrieval_eval.separation(pos, neg)
    assert sep["auc"] == 1.0 and sep["gap"] == 0.3 and sep["enough"]
    assert retrieval_eval.separation(pos, [[(0.0, 0.85, False)]])["auc"] == 0.5


def test_judge_validation_rule_is_fixed_before_measuring():
    from evals import judge

    assert judge.validation({"positives": 12, "negatives": 11, "tpr": 0.9, "tnr": 0.85})["validated"]
    few = judge.validation({"positives": 5, "negatives": 30, "tpr": 1.0, "tnr": 0.9})
    assert not few["validated"] and "tem 5 e 30" in few["missing"][0]
    weak = judge.validation({"positives": 20, "negatives": 20, "tpr": 0.95, "tnr": 0.6})
    assert not weak["validated"] and "TNR" in weak["missing"][0]


def test_rerank_hits_carry_the_cross_score():
    from app import rag

    class Base:
        name = "b"

        def search(self, q, k=3):
            return [rag.Hit(rag.Doc(id=f"d{i}", title="t", text=f"texto {i}", url=f"u{i}"), 1.0) for i in range(3)]

    class Scorer:
        name = "s"

        def score(self, q, texts):
            return [0.1, 2.5, -1.0]

    hits = rag.CrossRerankRetriever(Base(), Scorer(), pool=3, chars=100).search("q", k=3)
    assert [h.doc.id for h in hits] == ["d1", "d0", "d2"] and hits[0].rerank == 2.5


def test_offline_run_removes_its_temporary_case_databases(tmp_path, monkeypatch):
    import glob
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    run_evals.run(split="guardrail")
    assert glob.glob(str(tmp_path / "eval-*")) == []
