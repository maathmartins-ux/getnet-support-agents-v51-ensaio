"""Gold de busca por origem (official/real/page/no_source) sem LLM, e rascunhos que viram gold pelo rótulo cego."""
import json
import time
from pathlib import Path

import pytest

from evals import essential_gold, gold_questions, run_evals

# domínio real opcional para medir o tempo do gerador (GOLD_DOMAIN_DIR = raiz de um repositório com corpus e casos)
REAL = Path(__import__("os").environ.get("GOLD_DOMAIN_DIR", "/nonexistent"))


def _write(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


def _bench(tmp_path: Path) -> dict[str, Path]:
    kn = tmp_path / "knowledge"
    _write(kn / "faq.jsonl", [
        {"id": "f1", "url": "u1",
         "text": "AVANÇAR · Entrega Qual o prazo de entrega? Qual o prazo de entrega? 5 dias."},
        {"id": "f2", "url": "u2", "text": "Posso trocar o produto depois de usar? Sim, em 7 dias. Está com dúvidas?"}])
    cases = _write(tmp_path / "cases.jsonl", [
        {"id": "o1", "split": "official", "message": "Como funciona a troca?", "expect": {"intent": "faq"}},
        {"id": "o2", "split": "official", "message": "Onde está o pedido 1002?", "expect": {"intent": "records"}},
        {"id": "m1", "split": "memory", "message": "E a outra?"}])
    real = _write(tmp_path / "real.jsonl", [{"id": "r1", "split": "real", "message": "Meu pedido atrasou, e agora?"}])
    gold = _write(tmp_path / "retrieval.jsonl", [{"question": "Qual o prazo de entrega?", "relevant": ["f1"]}])
    return {"knowledge": kn, "cases": cases, "real": real, "gold": gold}


def test_build_gives_four_origins_cleans_breadcrumbs_and_skips_gold(tmp_path):
    b = _bench(tmp_path)
    built = gold_questions.build(b["knowledge"], b["cases"], b["real"], b["gold"])
    assert built["official"] == ["Como funciona a troca?"]  # caso de dado do cliente (records) fica fora
    assert built["real"] == ["Meu pedido atrasou, e agora?"]
    assert built["page"] == ["Posso trocar o produto depois de usar?"]  # a do gold não repete; genérica sai
    assert len(built["no_source"]) >= gold_questions.MIN_NO_SOURCE


def test_site_headers_and_banners_are_not_customer_questions():
    # as 9 linhas-lixo do gold do ensaio (rodada 10, retrieval.d/page.jsonl:1,2,7,8,9,15,20,21,26)
    junk = ["Qual a sua máquina?", "Gestão na palma da sua mão Já tem a sua Get Conta?",
            "R$ 129,90/mês Venda mais na Black Friday Já é cliente Getnet?", "Dúvidas sobre Link de Pagamento?",
            "Como você prefere continuar?", "Já é nosso cliente?", "Gestão na palma da sua mão Já tem o seu Get Tap?",
            "Leroy Merlin Maquininhas e Plataforma Digital Dúvidas sobre as maquininhas?", "Dúvidas sobre Get Tap?"]
    assert all(gold_questions.generic(q) for q in junk)
    real = ["Quem já tem conta pode pedir outra máquina?", "Qual a sua taxa de débito?",
            "Já recebi a máquina, e agora?", "Como eu contrato o Crediário e qual a taxa?",
            "Tenho dúvidas sobre a taxa: ela muda por bandeira?"]
    assert not any(gold_questions.generic(q) for q in real)  # minúscula no meio é pergunta: fica


def test_write_puts_unlabelled_drafts_outside_the_eval_and_negatives_inside(tmp_path):
    b = _bench(tmp_path)
    paths = gold_questions.write(gold_questions.build(b["knowledge"], b["cases"], b["real"], b["gold"]),
                                 tmp_path / "drafts", b["gold"])
    page = [json.loads(x) for x in Path(paths["page"]).read_text("utf-8").splitlines()]
    assert page[0] == {"question": "Posso trocar o produto depois de usar?", "origin": "page"}
    neg = Path(paths["no_source"])
    assert neg.parent.name == "retrieval.d" and all(json.loads(x)["relevant"] == []
                                                     for x in neg.read_text("utf-8").splitlines())
    assert gold_questions.check(b["gold"]) == [  # 1 com fonte de origem desconhecida, 20 sem fonte
        "nenhuma pergunta com fonte de origem `page` (FAQ do próprio site)",
        "nenhuma pergunta com fonte de origem `official` ou `real` (a metade que separa buscadores)"]


def test_check_reports_too_few_negatives(tmp_path):
    gold = _write(tmp_path / "retrieval.jsonl", [{"question": "x?", "relevant": ["a"], "origin": "page"},
                                                 {"question": "y?", "relevant": ["b"], "origin": "real"},
                                                 {"question": "z?", "relevant": []}])
    missing = gold_questions.check(gold)
    assert len(missing) == 1 and "1 perguntas sem fonte" in missing[0]
    assert gold_questions.main(["--check", "--gold", str(gold)]) == 1


def test_drafts_become_gold_in_their_origin_file_through_blind_labels(tmp_path):
    gold = tmp_path / "gold.jsonl"
    gold.write_text(run_evals.RETRIEVAL.read_text("utf-8"), encoding="utf-8")
    drafts = _write(tmp_path / "drafts" / "page.jsonl", [{"question": "Qual o prazo de entrega para o interior?",
                                                          "origin": "page"}]).parent
    essential_gold.export(k=3, out_dir=tmp_path, gold=gold, drafts=drafts)
    key = json.loads((tmp_path / "key.json").read_text("utf-8"))
    draft_qid = next(q for q, v in key.items() if v.get("draft"))
    assert key[draft_qid]["origin"] == "page"
    pool = [json.loads(x) for x in (tmp_path / "pool.jsonl").read_text("utf-8").splitlines()]
    labels = "".join(json.dumps({"qid": p["qid"], "essential": ["c0"]}) + "\n" for p in pool)
    a, b = tmp_path / "A.jsonl", tmp_path / "B.jsonl"
    a.write_text(labels, "utf-8")
    b.write_text(labels, "utf-8")
    rep = essential_gold.import_labels([a, b], out=tmp_path / "ess.jsonl", out_dir=tmp_path, gold=gold, drafts=drafts)
    assert rep["drafts_labelled"] == {"page": 1}
    page = [json.loads(x) for x in (tmp_path / "gold.d" / "page.jsonl").read_text("utf-8").splitlines()]
    assert page[0]["origin"] == "page" and page[0]["passage_text"] and page[0]["essential_by"] == ["A", "B"]
    out = [json.loads(x)["question"] for x in (tmp_path / "ess.jsonl").read_text("utf-8").splitlines()]
    assert "Qual o prazo de entrega para o interior?" not in out  # mora no arquivo da origem (sem linha dupla)
    # re-import não duplica a linha da origem
    essential_gold.export(k=3, out_dir=tmp_path, gold=gold, drafts=drafts)
    essential_gold.import_labels([a, b], out=tmp_path / "ess.jsonl", out_dir=tmp_path, gold=gold, drafts=drafts)
    assert len((tmp_path / "gold.d" / "page.jsonl").read_text("utf-8").splitlines()) == 1


@pytest.mark.skipif(not (REAL / "data" / "knowledge").is_dir(), reason="GOLD_DOMAIN_DIR sem corpus")
def test_real_domain_builds_the_four_origins_in_seconds_without_writing():
    t0 = time.perf_counter()
    built = gold_questions.build(REAL / "data" / "knowledge", REAL / "evals" / "cases.jsonl",
                                 REAL / "evals" / "real_questions.jsonl", REAL / "evals" / "retrieval.jsonl")
    assert time.perf_counter() - t0 < 5
    assert all(built[o] for o in gold_questions.ORIGINS)
    assert len(built["no_source"]) >= 15 and len(built["page"]) >= 20
    assert not any("·" in q or q.startswith("AVANÇAR") for q in built["page"])
