"""A medida da busca é guardada em var/ pela chave do que muda o resultado e só é refeita quando essa chave muda."""
from __future__ import annotations

import json

from evals import run_evals


def test_cache_returns_same_dict_and_key_follows_gold(tmp_path, monkeypatch):
    monkeypatch.setenv("RETRIEVAL_CACHE", "on")
    monkeypatch.setattr(run_evals, "_retrieval_cache_file", lambda: tmp_path / "cache.json")
    gold = tmp_path / "retrieval.jsonl"
    gold.write_text(json.dumps({"q": "a", "relevant": ["x"]}) + "\n", encoding="utf-8")
    k1 = run_evals._retrieval_cache_key(gold)
    assert k1 and run_evals._retrieval_cache_key(gold) == k1
    run_evals._retrieval_cache_put(k1, {"recall@3": 0.9})
    assert run_evals._retrieval_cache_get(k1) == {"recall@3": 0.9}
    gold.write_text(json.dumps({"q": "b", "relevant": ["y"]}) + "\n", encoding="utf-8")
    assert run_evals._retrieval_cache_key(gold) != k1


def test_cache_keeps_last_eight_and_off_disables(tmp_path, monkeypatch):
    monkeypatch.setattr(run_evals, "_retrieval_cache_file", lambda: tmp_path / "cache.json")
    for i in range(10):
        run_evals._retrieval_cache_put(f"k{i}", {"i": i})
    data = json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))
    assert len(data) == 8 and "k9" in data and "k0" not in data
    monkeypatch.setenv("RETRIEVAL_CACHE", "off")
    assert run_evals._retrieval_cache_key(tmp_path / "cache.json") is None
    assert run_evals._retrieval_cache_get(None) is None


def test_metrics_off_skips_measure(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_METRICS", "off")
    assert run_evals.retrieval_metrics() is None


def test_cache_key_follows_every_retrieval_knob(tmp_path, monkeypatch):
    """Cada botão que muda o resultado da busca muda a chave: a ordem do rerank, o pool e os caracteres lidos."""
    monkeypatch.setenv("RETRIEVAL_CACHE", "on")
    gold = tmp_path / "retrieval.jsonl"
    gold.write_text(json.dumps({"q": "a", "relevant": ["x"]}) + "\n", encoding="utf-8")
    keys = set()
    for env in ({}, {"RERANK_ORDER": "base"}, {"RERANK_ORDER": "cross"}, {"RERANK_POOL": "30"},
                {"RERANK_CHARS": "1500"}):
        for k in ("RERANK_ORDER", "RERANK_POOL", "RERANK_CHARS"):
            monkeypatch.delenv(k, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        keys.add(run_evals._retrieval_cache_key(gold))
    assert len(keys) == 4  # sem RERANK_ORDER vale a ordem padrão (cross): mesma chave de RERANK_ORDER=cross
