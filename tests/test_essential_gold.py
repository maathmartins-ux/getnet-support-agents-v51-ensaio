"""Gold essencial cego: export sem ordem da busca, import com consenso, concordância e regras de texto."""
import json

import pytest

from evals import essential_gold, run_evals


def test_export_hides_ids_and_rank_then_import_writes_passage_text(tmp_path):
    gold = tmp_path / "gold.jsonl"
    gold.write_text(run_evals.RETRIEVAL.read_text("utf-8"), encoding="utf-8")
    res = essential_gold.export(k=3, out_dir=tmp_path, gold=gold)
    pool = [json.loads(x) for x in (tmp_path / "pool.jsonl").read_text("utf-8").splitlines()]
    assert res["questions"] == len(pool) > 0
    assert all(set(c) == {"cid", "title", "text"} for p in pool for c in p["candidates"])  # sem id, nota ou ordem
    key = json.loads((tmp_path / "key.json").read_text("utf-8"))
    a, b = tmp_path / "A.jsonl", tmp_path / "B.jsonl"
    a.write_text("".join(json.dumps({"qid": p["qid"], "essential": ["c0"]}) + "\n" for p in pool), "utf-8")
    b.write_text("".join(json.dumps({"qid": p["qid"], "essential": ["c0", "c1"][: len(p["candidates"])]}) + "\n"
                         for p in pool), "utf-8")
    with pytest.raises(ValueError):
        essential_gold.import_labels([a], out=tmp_path / "x.jsonl", out_dir=tmp_path, gold=gold)
    rep = essential_gold.import_labels([a, b], out=tmp_path / "ess.jsonl", out_dir=tmp_path, gold=gold)
    assert rep["questions_labelled"] == len(pool) and rep["unmatched_rules"] == []
    assert 0 < rep["agreement"]["A×B"]["jaccard_mean"] <= 1
    rows = [json.loads(x) for x in (tmp_path / "ess.jsonl").read_text("utf-8").splitlines()]
    first = next(r for r in rows if r.get("passage_text"))
    assert len(first["passage_text"]) == 1 and first["essential_by"] == ["A", "B"]  # consenso = interseção (c0)
    assert gold.read_text("utf-8") != (tmp_path / "ess.jsonl").read_text("utf-8")
    assert key  # o rotulador não precisa dele; o import usa


def test_anchor_takes_the_answer_sentence_and_survives_spacing():
    import re

    text = "Quais são as taxas da Loja Virtual? A Loja Virtual conta com plano único de taxas e recebimento em 31 dias."
    rule = essential_gold.anchor(text)
    assert re.search(rule, text.replace(" ", "  "), re.IGNORECASE)
    assert not rule.startswith("Quais")


def test_copies_of_the_same_fact_are_one_unit_and_consensus_matches_by_overlap():
    a = [frozenset({"x1", "x2"}), frozenset({"y"})]  # rotulador A: fato 1 em duas páginas; fato 2
    b = [frozenset({"x2"}), frozenset({"z"})]          # rotulador B: fato 1 (uma cópia); outro fato
    assert essential_gold.consensus([a, b]) == [frozenset({"x1", "x2"})]
    assert essential_gold.consensus([[frozenset({"y"})], [frozenset({"z"})]]) == [frozenset({"y"}), frozenset({"z"})]
