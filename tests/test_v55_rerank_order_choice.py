"""v5.5.1: o comparativo do buscador mede a ordem do denso com a nota do cross só no portão, e a escolha automática
desempata pela cobertura do portão (no domínio Getnet a ordem do denso venceu: Recall@3 0,898 × 0,856, MRR igual)."""
from __future__ import annotations

import json

from app import agents, rag
from app.rag import Doc, Hit
from evals import retrieval_eval as rv


class _Base:
    name = "dense"

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, k=3):
        return self.hits[:k]


class _Scorer:
    def __init__(self, scores):
        self.scores = scores

    def score(self, query, texts):
        return self.scores[:len(texts)]


def _hits(n=3):
    return [Hit(Doc(f"d-{i}", f"t{i}", f"u{i}", f"texto {i}"), 1.0 - i / 10, bm25=1.0, cosine=0.9 - i / 100)
            for i in range(n)]


def test_cross_reranker_order_is_fixed_per_instance_and_ignores_the_environment(monkeypatch):
    """O comparativo mede as duas ordens; um RERANK_ORDER=base no shell não pode contaminar a ordem do cross."""
    monkeypatch.setenv("RERANK_ORDER", "base")
    scores = [0.1, 0.9, 0.5]  # o cross prefere d-1
    cross = rag.CrossRerankRetriever(_Base(_hits()), _Scorer(scores), pool=3, order="cross")
    assert [h.doc.id for h in cross.search("q", k=3)][0] == "d-1"
    base = rag.CrossRerankRetriever(_Base(_hits()), _Scorer(scores), pool=3, order="base")
    out = base.search("q", k=3)
    assert [h.doc.id for h in out] == ["d-0", "d-1", "d-2"] and [h.rerank for h in out] == scores
    monkeypatch.delenv("RERANK_ORDER")
    runtime = rag.CrossRerankRetriever(_Base(_hits()), _Scorer(scores), pool=3)  # app: vale a escolha/ambiente
    assert runtime.search("q", k=3)[0].doc.id == "d-1"


def test_build_passes_the_measured_order_and_names_it(monkeypatch):
    class Fx:
        def cross(self, model):
            return _Scorer([0.1, 0.9, 0.5])

    monkeypatch.setattr(rag, "get_index", lambda: None)
    monkeypatch.setattr(rag, "BM25Retriever", lambda index: _Base(_hits()))
    cfg = {"retriever": "bm25", "rerank": "cross", "rerank_model": "m", "rerank_pool": 3, "rerank_order": "base"}
    assert rv.build(cfg, Fx()).order == "base"
    assert rv.build({**cfg, "rerank_order": None}, Fx()).order == "cross"
    assert rv.config_name(cfg) == "bm25+cross:base" and rv.config_name({**cfg, "rerank_order": None}) == "bm25+cross"
    assert [rv.config_name(c) for c in rv.FAST_CONFIGS] == ["bm25", "dense", "dense+cross", "dense+cross:base"]


def _row(mrr, recall, p95, gate=None, rerank_gate=None, **config):
    out = {"mrr": mrr, "recall@3": recall, "latency_ms": {"p95": p95}, "config": {"retriever": "dense", **config}}
    if gate:
        out["gate"] = gate
    if rerank_gate:
        out["rerank_gate"] = rerank_gate
    return out


COS = {"meets_floor": True, "min_score": 9.0, "min_cosine": 0.83, "pos_answered": 0.9, "neg_refused": 0.86}
NOTE = {"meets_floor": True, "min_rerank": -5.5, "pos_answered": 0.98, "neg_refused": 0.86}


def test_choose_breaks_a_ranking_tie_by_gate_coverage_before_latency():
    """Mesma ordem (MRR e Recall@3 iguais): vence o portão que responde mais perguntas com fonte no piso de recusa,
    mesmo mais lento; o min_rerank calibrado vai junto na escolha (o app usa a nota quando o trecho a traz)."""
    results = {"dense": _row(0.842, 0.898, 40, gate=COS),
               "dense+cross:base": _row(0.842, 0.898, 1100, gate=COS, rerank_gate=NOTE, rerank="cross",
                                        rerank_order="base"),
               "dense+cross": _row(0.842, 0.856, 1100, gate=COS, rerank_gate=NOTE, rerank="cross")}
    picked = rv.choose(results, budget_ms=1500)
    assert picked["name"] == "dense+cross:base" and "cobertura do portão" in picked["reason"]
    assert picked["config"]["rerank_order"] == "base" and picked["config"]["gate"]["min_rerank"] == -5.5
    worse_note = {**NOTE, "pos_answered": 0.8}  # nota pior que o cosseno: o mais rápido vence
    results["dense+cross:base"]["rerank_gate"] = worse_note
    assert rv.choose(results, budget_ms=1500)["name"] == "dense"


def test_choose_checks_the_floor_of_the_gate_the_app_uses():
    """Com cross-encoder o app decide pela nota: um portão de cosseno sem piso não reprova a configuração se a nota
    recusa o bastante (e uma nota sem piso reprova, mesmo com o cosseno bom)."""
    bad_cos = {**COS, "meets_floor": False, "neg_refused": 0.3, "neg_refusal_min": 0.85}
    bad_note = {**NOTE, "meets_floor": False, "neg_refused": 0.4, "neg_refusal_min": 0.85}
    ok = rv.choose({"dense+cross": _row(0.9, 0.9, 10, gate=bad_cos, rerank_gate=NOTE, rerank="cross")})
    assert ok["name"] == "dense+cross"
    no = rv.choose({"dense+cross": _row(0.9, 0.9, 10, gate=COS, rerank_gate=bad_note, rerank="cross")})
    assert no["name"] == "bm25" and "portão" in no["rejected"]["dense+cross"]


def test_rerank_threshold_falls_back_to_the_choice_gate(monkeypatch):
    """Ambiente → MIN_RERANK do domínio → min_rerank da escolha gravada (o rag só entrega o gate sem queda)."""
    monkeypatch.delenv("COVERAGE_MIN_RERANK", raising=False)
    dom = type("D", (), {"MIN_SCORE": 0.5})()
    monkeypatch.setattr(agents.domain, "active", lambda: dom)
    assert agents.rerank_threshold() is None and agents.rerank_threshold({"min_rerank": -3.0}) == -3.0
    dom.MIN_RERANK = -5.5
    assert agents.rerank_threshold({"min_rerank": -3.0}) == -5.5
    monkeypatch.setenv("COVERAGE_MIN_RERANK", "-1")
    assert agents.rerank_threshold({"min_rerank": -3.0}) == -1.0
    monkeypatch.delenv("COVERAGE_MIN_RERANK")
    del dom.MIN_RERANK
    found = [Hit(Doc("a", "t", "u", "x"), 1.0, bm25=0.0, cosine=0.1, rerank=-4.0)]
    assert agents.covered_hits(found, gate={"min_rerank": -4.5}) == found  # a nota passa do limiar da escolha
    assert agents.covered_hits(found, gate={"min_rerank": -3.5}) == []


def test_readme_block_tolerates_a_choice_without_budget_and_shows_the_gate(tmp_path):
    from scripts.fill_readme import retrieval_block

    (tmp_path / "retriever.json").write_text(json.dumps({
        "_doc": "ordem do denso medida no gold do domínio", "gold": "g", "chosen_at": "t", "git_sha": "abc",
        "chosen": "dense+cross:base", "choice": {"retriever": "dense", "gate": {"min_rerank": -5.5017}},
        "measured": {"dense+cross:base": {"recall@3": 0.898, "mrr": 0.842, "rerank_gate": NOTE}}}), encoding="utf-8")
    block = retrieval_block(tmp_path, data=tmp_path)
    assert "Escolha do domínio: ordem do denso" in block and "nota do cross-encoder >= -5.5017" in block
    assert "dense+cross:base **← escolhida** | 0.898 | 0.842" in block and "98% / 86% (nota do cross)" in block
    assert "`:base` = a ordem fica a do buscador base" in block
