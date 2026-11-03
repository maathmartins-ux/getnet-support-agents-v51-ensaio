"""E53 — held-out ponta a ponta: a página cega sorteia o held-out, o passa/falha humano é a medida e a intenção vira
linha de diagnóstico: medida sozinha, a intenção (67,5%) punia resposta certa dada com rótulo de taxonomia
diferente."""
import json

import pytest

from evals import label
from scripts import delivery_message, fill_readme, label_page, scorecard


def _row(i, split, intent_ok=True):
    return {"id": i, "split": split, "run": 0, "message": f"pergunta {i}?", "answer": "Resposta.",
            "checks": {"intent": intent_ok}, "sources": [], "source_ids": []}


@pytest.fixture
def results(tmp_path):
    d = tmp_path / "results"
    d.mkdir()
    held = [_row("h1", "heldout"), _row("h2", "heldout", intent_ok=False), _row("h3", "heldout"),
            _row("h4", "heldout", intent_ok=False)]
    (d / "live_heldout.json").write_text(json.dumps({"rows": held}), encoding="utf-8")
    (d / "live_official.json").write_text(json.dumps({"rows": [_row("o1", "official")]}), encoding="utf-8")
    return d


def test_blind_page_can_sample_only_the_heldout(results, tmp_path, monkeypatch):
    got = label_page.items(10, results=results, splits={"heldout"})
    assert sorted(r["id"] for r in got) == ["h1", "h2", "h3", "h4"]
    out = tmp_path / "page.html"
    monkeypatch.setattr(label, "RESULTS", results)
    assert label_page.main(["--heldout", "--raters", "Ana,Bia", "--out", str(out)]) == 0
    data = out.read_text(encoding="utf-8")
    assert '"id": "h1"' in data and '"id": "o1"' not in data
    assert '"checks"' not in data and "intent" not in data  # cego: nem checagem nem intenção esperada


def test_heldout_page_without_heldout_rows_says_so(tmp_path, monkeypatch):
    empty = tmp_path / "vazio"
    empty.mkdir()
    monkeypatch.setattr(label, "RESULTS", empty)
    with pytest.raises(SystemExit):
        label_page.main(["--heldout", "--raters", "Ana,Bia", "--out", str(tmp_path / "p.html")])


def test_report_gives_heldout_end_to_end_with_intent_as_diagnostic(results, tmp_path):
    path = label.csv_path("dono", tmp_path)
    assert label.export(10, results, path, splits={"heldout"}) == 4
    label.mark(["h1=pass", "h2=pass", "h3=fail:unsupported_claim", "h4=pass"], path=path)
    rep = label.report(results=results, path=path, out=tmp_path / "h.json")
    ho = rep["heldout"]
    assert (ho["rotulos"], ho["humano_passa"], ho["taxa"]) == (4, 3, 0.75)
    assert ho["diagnostico_intencao"] == 0.5 and ho["intencao_errada_humano_passa"] == ["h2", "h4"]
    assert ho["ci"]["n"] == 4
    text = fill_readme.human_block(tmp_path)  # o bloco lê human_review.json do diretório, ainda ausente
    assert "Sem validação humana" in text  # sem human_review.json aqui: declarado
    (tmp_path / "human_review.json").write_text(json.dumps(rep), encoding="utf-8")
    text = fill_readme.human_block(tmp_path)
    assert "Held-out cego ponta a ponta: humano aprova **3/4** (0.75)" in text and "h2, h4" in text


def test_scorecard_measures_heldout_by_the_human_and_shows_intent_as_diagnostic(tmp_path):
    (tmp_path / "latest.json").write_text(json.dumps({"metrics": {"heldout": {"cases": 80, "intent_acc": 67.5}}}),
                                          encoding="utf-8")
    (tmp_path / "human_review.json").write_text(json.dumps({"rotulos": 80, "heldout": {"taxa": 0.79}}),
                                                encoding="utf-8")
    table = {r["key"]: r for r in scorecard.rows(tmp_path)}
    assert table["heldout_e2e"]["value"] == 0.79 and table["heldout_e2e"]["status"] == "abaixo"
    assert table["heldout_intent"]["status"] == "diagnóstico" and table["heldout_intent"]["goal"] == "—"
    md = scorecard.to_markdown(tmp_path)
    weak = md.split("Abaixo da referência ou sem medida")[1]
    assert "intenção (diagnóstico)" not in weak and "ponta a ponta (humano passa) (0.79)" in weak
    msg = delivery_message.render("https://x.test/r", None, tmp_path, None)
    assert "intenção (diagnóstico)" not in msg  # só as medidas pedidas no enunciado vão à mensagem de entrega
