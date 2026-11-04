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


# --- import: rótulo velho, união e arquivos escritos (rodada 10: real.jsonl:1-2, q069/q078/q079, k.jsonl vazio) ---
def _gold_family(tmp_path, rows: list[dict]):
    gold = tmp_path / "retrieval.jsonl"
    gold.write_text("", "utf-8")  # no ensaio a raiz da família tinha 0 bytes: o gold mora nos arquivos por origem
    (tmp_path / "retrieval.d").mkdir()
    (tmp_path / "retrieval.d" / "real.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    return gold


def _labels_file(path, essentials: dict[str, list]):
    path.write_text("".join(json.dumps({"qid": q, "essential": e}) + "\n" for q, e in essentials.items()), "utf-8")
    return path


def test_import_clears_stale_labels_lists_only_who_marked_and_leaves_no_empty_file(tmp_path):
    stale = {"passage_text": ["regra de um import anterior"], "essential_by": ["A", "B"]}
    gold = _gold_family(tmp_path, [
        {"question": "Por que a taxa está tão alta?", "origin": "real", **stale},  # ninguém marca agora
        {"question": "E o reembolso?", "origin": "real", "relevant": ["faq-troca"], **stale},  # ninguém; tem ids
        {"question": "Qual o prazo de entrega?", "origin": "real", **stale}])  # só o rotulador A marca
    out_dir = tmp_path / "essential"
    out_dir.mkdir()
    (out_dir / "key.json").write_text(json.dumps({
        "q000": {"question": "Por que a taxa está tão alta?", "cids": {"c0": "faq-horario"}},
        "q001": {"question": "E o reembolso?", "cids": {"c0": "faq-troca"}},
        "q002": {"question": "Qual o prazo de entrega?", "cids": {"c0": "faq-entrega"}}}), "utf-8")
    a = _labels_file(tmp_path / "A.jsonl", {"q000": [], "q001": [], "q002": [["c0"]]})
    b = _labels_file(tmp_path / "B.jsonl", {"q000": [], "q001": [], "q002": []})
    k = tmp_path / "retrieval.d" / "k.jsonl"
    k.write_text("", "utf-8")  # o --out de 0 bytes para o qual o report.json e o RESULTS apontavam
    drafts = tmp_path / "drafts"
    rep = essential_gold.import_labels([a, b], out=k, out_dir=out_dir, gold=gold, drafts=drafts)
    real_path = tmp_path / "retrieval.d" / "real.jsonl"
    rows = {r["question"]: r for r in map(json.loads, real_path.read_text("utf-8").splitlines())}
    # sem gold nenhum a linha leria como "sem fonte": sai do gold e volta a rascunho (não vira negativa calada)
    assert "Por que a taxa está tão alta?" not in rows
    assert [json.loads(x) for x in (drafts / "real.jsonl").read_text("utf-8").splitlines()] == [
        {"question": "Por que a taxa está tão alta?", "origin": "real"}]
    # com outro gold (ids), fica no arquivo, sem a regra e sem o "rotulado por A e B" que ninguém sustenta mais
    assert rows["E o reembolso?"] == {"question": "E o reembolso?", "origin": "real", "relevant": ["faq-troca"]}
    one = rows["Qual o prazo de entrega?"]
    assert one["essential_by"] == ["A"] and one["passage_text"] != stale["passage_text"]  # união: só quem marcou
    assert not k.exists()  # nada próprio para o --out: não fica um arquivo vazio na família
    assert rep["gold"] == [str(real_path)] and rep["removed"] == [str(k)]
    assert rep["drafts"] == [str(drafts / "real.jsonl")]
    assert rep["back_to_drafts"] == ["Por que a taxa está tão alta?"]
    assert rep["no_agreement"] == ["Qual o prazo de entrega?"]
    assert set(rep["no_essential"]) == {"Por que a taxa está tão alta?", "E o reembolso?"}
    assert json.loads((out_dir / "report.json").read_text("utf-8"))["gold"] == rep["gold"]


def test_import_does_not_create_an_empty_out_nor_touch_explicit_negatives(tmp_path):
    gold = _gold_family(tmp_path, [{"question": "Vocês vendem carros?", "origin": "real", "relevant": []}])
    out_dir = tmp_path / "essential"
    out_dir.mkdir()
    (out_dir / "key.json").write_text(json.dumps({
        "q000": {"question": "Vocês vendem carros?", "cids": {"c0": "faq-troca"}}}), "utf-8")
    a = _labels_file(tmp_path / "A.jsonl", {"q000": []})
    b = _labels_file(tmp_path / "B.jsonl", {"q000": []})
    new = tmp_path / "retrieval.d" / "novo.jsonl"
    rep = essential_gold.import_labels([a, b], out=new, out_dir=out_dir, gold=gold, drafts=tmp_path / "drafts")
    assert not new.exists() and rep["gold"] == [] and rep["back_to_drafts"] == []
    assert json.loads((tmp_path / "retrieval.d" / "real.jsonl").read_text("utf-8")) == {
        "question": "Vocês vendem carros?", "origin": "real", "relevant": []}  # negativa explícita fica como está
    assert essential_gold._rel(essential_gold.HERE / "retrieval.d" / "real.jsonl") == "evals/retrieval.d/real.jsonl"
