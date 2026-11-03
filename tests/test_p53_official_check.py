"""scripts/official_check.py: cobertura do corpus por entidade oficial e fato oficial no top-k do buscador ativo.

Estar no corpus não basta: um fato oficial pode ficar fora do top-3 e só aparecer como erro na rodada ao vivo.
O script mede isso antes da rodada.
Corpus fictício (domínio próprio, sem API): BM25, o buscador que o conftest fixa nos testes.
"""
import json

import pytest

from scripts import official_check as oc

HOST = "https://loja-ficticia.test"
CHUNKS = {
    "produtos/maquinas.jsonl": [
        ("prod-maquinas-01", "Todas as máquinas", f"{HOST}/maquinas/",
         "Comparativo: a Máquina Alfa custa R$ 79,90 e imprime comprovante; a Máquina Beta custa R$ 129,90 e "
         "roda aplicativos de gestão."),
    ],
    "produtos/maquina-alfa.jsonl": [
        ("prod-maquina-alfa-01", "Máquina Alfa", f"{HOST}/maquina-alfa/",
         "A Maquina Alfa aceita chip e Wi-Fi e imprime o comprovante na hora."),
    ],
    "suporte/parcelado.jsonl": [
        ("sup-parcelado-01", "Crediário", f"{HOST}/duvidas/parcelado/",
         "No crediário a venda pode ser dividida em até 48x no boleto."),
        ("sup-parcelado-02", "Crediário", f"{HOST}/duvidas/parcelado/",
         "O crediário tem análise de crédito do comprador feita pela financeira parceira."),
    ],
}
SOURCES = {"allowed_hosts": ["loja-ficticia.test"], "groups": {
    "produtos": {"prefix": "prod", "pages": {"maquinas": f"{HOST}/maquinas/", "maquina-alfa": f"{HOST}/maquina-alfa/",
                                             "maquina-beta": f"{HOST}/maquina-beta/"}},
    "suporte": {"prefix": "sup", "pages": {"parcelado": f"{HOST}/duvidas/parcelado/"}}}}


def corpus(tmp_path, chunks=CHUNKS, sources=SOURCES):
    data = tmp_path / "data"
    for rel, rows in chunks.items():
        path = data / "knowledge" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps({"id": i, "title": t, "url": u, "text": x}, ensure_ascii=False) + "\n"
                                for i, t, u, x in rows), encoding="utf-8")
    (data / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    return data


def cases(tmp_path, *rows):
    path = tmp_path / "cases.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


def case(cid, message, facts=(), entities=(), intent="faq", **extra):
    return {"id": cid, "split": "official", "user_id": "u1", "message": message,
            "expect": {"intent": intent, "facts": list(facts), "entities": list(entities)}, **extra}


def run(tmp_path, *rows, data=None, **kw):
    return oc.check(cases(tmp_path, *rows), data=data or corpus(tmp_path), **kw)


def test_passes_when_every_fact_is_in_the_top_k_and_every_entity_is_ingested(tmp_path):
    no_beta_page = json.loads(json.dumps(SOURCES))
    del no_beta_page["groups"]["produtos"]["pages"]["maquina-beta"]
    report = run(tmp_path,
                 case("official-01", "Qual a diferença entre a Máquina Alfa e a Máquina Beta?",
                      facts=[r"79,90", r"129,90"], entities=["Máquina Alfa", "Máquina Beta"]),
                 case("official-09", "Em quantas vezes posso parcelar no crediário?", facts=[r"48\s*x"]),
                 data=corpus(tmp_path, sources=no_beta_page))
    assert report.ok, report.lines()
    assert report.retriever == "bm25" and report.k == 5
    assert any("official-09 fato /48\\s*x/ (mensagem) no rank" in p for p in report.passed)


def test_fact_in_corpus_but_outside_the_top_k_fails_with_case_fact_and_where_it_is(tmp_path):
    # top-1: só o trecho mais parecido entra; o fato da análise de crédito fica fora (problema de BUSCA, não de corpus)
    report = run(tmp_path, case("official-09", "Em quantas vezes posso parcelar no crediário em 48x?",
                                facts=[r"an[aá]lise de cr[eé]dito"]), k=1)
    assert not report.ok
    [fail] = report.failures
    assert fail.kind == "fact" and fail.case == "official-09"
    assert "an[aá]lise de cr[eé]dito" in fail.detail and "sup-parcelado-02" in fail.detail
    assert "fora do top-1" in fail.detail


def test_fact_absent_from_every_chunk_is_reported_as_a_corpus_problem(tmp_path):
    report = run(tmp_path, case("official-04", "Preciso de conta para receber no crediário?",
                                facts=[r"conta (corrente|poupan[cç]a)"]))
    [fail] = report.failures
    assert fail.kind == "fact" and "não está em nenhum trecho" in fail.detail


def test_entity_not_named_by_any_chunk_fails(tmp_path):
    report = run(tmp_path, case("official-01", "E a Máquina Gama?", entities=["Máquina Gama"], intent="records"))
    [fail] = report.failures
    assert (fail.kind, fail.case) == ("entity", "official-01") and "Máquina Gama" in fail.detail


def test_entity_named_but_its_product_page_in_sources_was_not_ingested_fails(tmp_path):
    # "Máquina Beta" aparece no comparativo, mas a página dela (maquina-beta) está em sources.json e não foi ingerida
    report = run(tmp_path, case("official-01", "Quanto custa a Máquina Beta?", entities=["Maquina Beta"],
                                intent="records"))
    [fail] = report.failures
    assert fail.kind == "page" and f"{HOST}/maquina-beta/" in fail.detail


def test_entity_matching_ignores_accents_case_and_spacing(tmp_path):
    report = run(tmp_path, case("official-01", "alfa?", entities=["MAQUINA ALFA"], intent="records"))
    assert report.ok, report.lines()
    assert oc.entity_pattern("Get Smart").search(oc.fold("A GetSmart roda apps"))
    assert not oc.entity_pattern("Get Smart").search("a get smartphone")


def test_knowledge_case_without_facts_fails_unless_relaxed(tmp_path):
    row = case("official-09", "Em quantas vezes posso parcelar no crediário?")
    assert [f.kind for f in run(tmp_path, row).failures] == ["facts_missing"]
    assert run(tmp_path, row, require_facts=False).ok


def test_non_knowledge_intents_are_not_checked_for_facts_unless_forced(tmp_path):
    row = case("official-03", "Quando cai o dinheiro de ontem?", facts=[r"R\$ ?745,50"], intent="records")
    assert run(tmp_path, row).ok  # dado do cliente vem da tool, não do corpus
    assert [f.kind for f in run(tmp_path, row, intents={"records"}).failures] == ["fact"]


def test_standalone_question_is_checked_too(tmp_path):
    # a mensagem curta acha o crediário pelo próprio termo; a reescrita autônoma também tem de achar o fato
    row = case("memory-01", "e no crediário?", facts=[r"48\s*x"], split="official",
               ctx={"facts": {"standalone": "Em quantas vezes posso vender no crediário?"}})
    report = run(tmp_path, row)
    assert report.ok, report.lines()
    assert any("(standalone)" in p for p in report.passed)
    bad = case("memory-02", "e no crediário?", facts=[r"48\s*x"], standalone="Quanto custa a Máquina Alfa?")
    [fail] = run(tmp_path, bad).failures
    assert "standalone" in fail.detail and "Máquina Alfa" in fail.detail
    assert oc.standalone_of({"expect": {"standalone": " x "}}) == "x" and oc.standalone_of({}) == ""


def test_retriever_that_fell_back_is_a_failure(tmp_path):
    class Fallen:
        name, fallback = "bm25", "dense indisponível → bm25 (modelo ausente)"

        def search(self, query, k=3):
            return []

    report = run(tmp_path, case("official-01", "x", entities=["Máquina Alfa"], intent="records"), retriever=Fallen())
    assert [f.kind for f in report.failures] == ["retriever"]
    assert run(tmp_path, case("official-01", "x", entities=["Máquina Alfa"], intent="records"),
               retriever=Fallen(), allow_fallback=True).ok


def test_no_official_case_is_a_failure(tmp_path):
    report = run(tmp_path, {"id": "replan-01", "split": "replan", "message": "x", "expect": {}})
    assert [f.kind for f in report.failures] == ["cases"]


def test_data_dir_is_restored_after_the_call(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", "/antes")
    run(tmp_path, case("official-09", "crediário?", facts=[r"48\s*x"]))
    import os

    assert os.environ["DATA_DIR"] == "/antes"


def test_cli_exit_code_and_json(tmp_path, capsys):
    data = corpus(tmp_path)
    good = cases(tmp_path, case("official-09", "Em quantas vezes posso parcelar no crediário?", facts=[r"48\s*x"]))
    out = tmp_path / "r.json"
    assert oc.main(["--cases", str(good), "--data", str(data), "--json", str(out)]) == 0
    assert "OFICIAIS OK" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8"))["ok"] is True
    bad = cases(tmp_path, case("official-09", "crediário?", facts=[r"R\$ ?999"]))
    assert oc.main(["--cases", str(bad), "--data", str(data)]) == 1
    printed = capsys.readouterr().out
    assert "FALHA [fact] official-09" in printed and "OFICIAIS FALHARAM" in printed


@pytest.mark.parametrize("name,page,expected", [
    ("Get Smart", "get-smart", True), ("Get Smart", "maquininha-get-smart", True),
    ("Get Smart", "get-smartphone", False), ("Get Clássica", "get-classica", True)])
def test_entity_page_matching_by_slug(name, page, expected):
    sources = {"groups": {"g": {"pages": {page: f"{HOST}/{page}/"}}}}
    assert bool(oc.entity_pages(name, sources)) is expected
