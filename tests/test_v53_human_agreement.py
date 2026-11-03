"""Concordância humano × humano: % simples, kappa, AC1, por pergunta, consenso."""
import json

from evals import label


def test_ac1_survives_the_kappa_paradox():
    # 18 aprovadas pelas duas, cada uma reprova 1 resposta diferente: concordância 0,90, kappa negativo, AC1 alto
    pairs = [(True, True)] * 18 + [(True, False), (False, True)]
    ag = label.agreement(pairs)
    assert ag["concordancia"] == 0.9
    assert ag["kappa"] == -0.053
    assert ag["ac1"] == 0.890


def test_ac1_known_balanced_case():
    # prevalência 50%: AC1 = kappa (acaso 0,5 nos dois) — 8 de 10 iguais → 0,6
    pairs = [(True, True)] * 4 + [(False, False)] * 4 + [(True, False), (False, True)]
    assert label.ac1(pairs) == 0.6 == label.kappa(pairs)
    assert label.ac1([]) is None


def _page(tmp_path, res, rater, marks):
    dump = tmp_path / f"{rater}.json"
    dump.write_text(json.dumps([{"data": {"rater": rater, "marks": marks}}]), encoding="utf-8")
    return label.import_page(dump, results=res, base=tmp_path)


def _setup(tmp_path):
    res = tmp_path / "results"
    res.mkdir()
    rows = [{"id": f"c{i}", "split": "official", "run": 0, "message": f"pergunta {i}", "answer": f"resposta {i}",
             "checks": {"numbers": True}} for i in range(4)]
    (res / "live_official.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    ok = {"c1": "sim", "c2": "nao", "c3": "sim"}
    bad = {"v": "fail", "tipo": "unsupported_claim", "c1": "sim", "c2": "sim", "c3": "sim"}
    _page(tmp_path, res, "ana", {"c0": {"v": "pass", **ok}, "c1": {"v": "pass", **ok},
                                 "c2": bad, "c3": {"v": "pass", **ok}})
    _page(tmp_path, res, "bia", {"c0": {"v": "pass", **ok}, "c1": {"v": "fail", "tipo": "wrong_language",
                                                               "c1": "sim", "c2": "nao", "c3": "nao"},
                                 "c2": bad, "c3": {"v": "pass", **ok}})
    return res


def test_per_question_answers_are_kept_and_reported(tmp_path):
    res = _setup(tmp_path)
    assert label.read_labels(label.csv_path("ana", tmp_path))[2]["c2"] == "sim"
    rep = label.report(results=res, out=tmp_path / "h.json", base=tmp_path)
    eh = rep["entre_humanos"]
    assert eh["divergem"] == ["c1"] and eh["concordancia"] == 0.75 and eh["ac1"] is not None
    pq = eh["antes"]["por_pergunta"]
    assert pq["c3"]["n"] == 4 and pq["c3"]["concordancia"] == 0.75 and pq["c2"]["concordancia"] == 1.0
    assert eh["depois_do_consenso"] is None


def test_divergences_then_consensus_gives_before_and_after(tmp_path):
    res = _setup(tmp_path)
    found = label.divergences(base=tmp_path)
    assert [d["id"] for d in found] == ["c1"] and found[0]["perguntas"] == {"c3": {"ana": "sim", "bia": "nao"}}
    md = (tmp_path / "human_divergences.md").read_text(encoding="utf-8")
    assert "c1=pass|fail|diverge" in md and "mesmo idioma" in md and "bia: errada" in md
    assert label.import_consensus("CONSENSO\nc1=pass\n", base=tmp_path)["resolvidas"] == 1
    eh = label.report(results=res, out=tmp_path / "h.json", base=tmp_path)["entre_humanos"]
    assert eh["antes"]["concordancia"] == 0.75  # a medida independente não muda
    after = eh["depois_do_consenso"]
    assert after["concordancia"] == 1.0 and after["resolvidas"] == ["c1"] and after["mantidas"] == []


def test_consensus_keeps_real_disagreement(tmp_path):
    res = _setup(tmp_path)
    label.import_consensus("c1=diverge", base=tmp_path)
    after = label.report(results=res, out=tmp_path / "h.json", base=tmp_path)["entre_humanos"]["depois_do_consenso"]
    assert after["concordancia"] == 0.75 and after["mantidas"] == ["c1"]


def test_plan_b_text_carries_the_questions(tmp_path):
    res = tmp_path / "results"
    res.mkdir()
    (res / "live_official.json").write_text(json.dumps({"rows": [
        {"id": "c0", "split": "official", "run": 0, "message": "q", "answer": "a", "checks": {}}]}), encoding="utf-8")
    label.import_text("CONFERENCIA abc bia\nc0=fail:wrong_language c1=sim c2=nao c3=nao\n", results=res, base=tmp_path)
    row = label.read_labels(label.csv_path("bia", tmp_path))[0]
    assert row["humano"] == "fail" and row["c3"] == "nao" and row["c1"] == "sim"


def test_page_ships_practice_with_answer_key_and_concrete_questions():
    from scripts import label_page

    html = label_page.render([{"id": "c0", "question": "q", "answer": "a", "blocks": []}], ["Ana", "Bia"])
    data = json.loads(html.split('<script id="data" type="application/json">', 1)[1].split("</script>", 1)[0])
    assert [p["id"] for p in data["practice"]] == ["treino-1", "treino-2"]
    assert {p["expected"] for p in data["practice"]} == {"pass", "fail"}
    assert all(set(p["key"]) == {"c1", "c2", "c3"} for p in data["practice"])
    assert data["practice"][0]["lang"] == "en"  # armadilha de propósito: resposta em inglês e correta
    for text in ("NÃO aparece no que o assistente tinha em mãos", "Ver um exemplo de Sim e de Não",
                 "Gabarito deste treino", "bad: \"sim\"", "<mark>"):
        assert text in html
    assert [p["id"] for p in label_page.PRACTICE] == ["treino-1", "treino-2"]
