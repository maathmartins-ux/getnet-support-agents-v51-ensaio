"""Placar honesto, mensagem de entrega e rotulagem por mais de um humano."""
import json

from evals import label
from scripts import delivery_message, scorecard


def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _results(tmp_path, *, grounded=0.6, recall=0.49, official_status="complete"):
    _write(tmp_path / "latest.json", {"retrieval": {"recall@3": recall, "mrr": 0.61},
                                      "metrics": {"heldout": {"cases": 24, "intent_acc": 75.0}}})
    _write(tmp_path / "live_official.json", {"status": official_status, "stability": {"pass_hat_k": 0.7},
                                             "metrics": {"official": {"numbers_acc": 80.0}}})
    _write(tmp_path / "judge.json", {"by_split": {"official": {"grounded_rate": grounded}},
                                     "calibration": {"cohen_kappa": 0.96}})
    return tmp_path


def test_scorecard_shows_bad_numbers_next_to_good(tmp_path):
    table = {r["key"]: r for r in scorecard.rows(_results(tmp_path))}
    assert table["official_grounded"]["status"] == "abaixo"
    assert table["judge_kappa"]["status"] == "atinge"
    assert table["memory_pass_1"]["status"] == "não medido"  # sem arquivo: aparece como buraco, não some
    md = scorecard.to_markdown(tmp_path)
    assert "Abaixo da referência ou sem medida" in md and "Busca: Recall@3 (0.49)" in md


def test_degraded_or_unreliable_runs_do_not_count(tmp_path):
    _results(tmp_path, official_status="degraded")
    _write(tmp_path / "judge.json", {"judge_unreliable": True, "by_split": {"official": {"grounded_rate": 0.99}}})
    got = scorecard.measure(tmp_path)
    assert got["official_numbers"] is None and got["official_grounded"] is None


def test_delivery_message_always_lists_the_weak_metrics(tmp_path):
    text = delivery_message.render("https://github.com/o/r", None, _results(tmp_path), 57)
    good, weak = text.split("Onde ainda está abaixo da referência")
    assert "fundamentadas: 0.60" in weak and "Recall@3: 0.49" in weak
    assert "kappa" not in text  # diagnóstico interno fica no docs/RESULTS.md, não na mensagem de entrega
    assert "docs/PROCEDENCIA.md" in text and "57 min" in text


def _labels(path, verdicts):
    rows = [{"id": i, "split": "official", "pergunta": "q", "resposta": "a", "fontes": "", "ferramentas": "",
             "humano": "", "nota": "", "tipo_falha": ""} for i in verdicts]
    with path.open("w", encoding="utf-8", newline="") as fh:
        import csv
        w = csv.DictWriter(fh, fieldnames=label.FIELDS)
        w.writeheader()
        w.writerows(rows)
    label.mark([f"{i}={v}" for i, v in verdicts.items()], path=path)


def test_two_raters_give_inter_human_agreement(tmp_path):
    res = tmp_path / "results"
    res.mkdir()
    rows = [{"id": f"c{i}", "split": "official", "run": 0, "checks": {"numbers": i % 2 == 0}} for i in range(4)]
    _write(res / "live_official.json", {"rows": rows})
    _labels(label.csv_path("ana", tmp_path), {"c0": "pass", "c1": "fail:invented_number 1,2", "c2": "pass",
                                               "c3": "pass"})
    _labels(label.csv_path("bia", tmp_path), {"c0": "pass", "c1": "fail", "c2": "pass", "c3": "fail"})
    rep = label.report(results=res, out=tmp_path / "h.json", base=tmp_path)
    assert rep["rotuladores"] == 2
    eh = rep["entre_humanos"]
    assert eh["comuns"] == 4 and eh["concordancia"] == 0.75 and eh["divergem"] == ["c3"]
    assert label.read_labels(label.csv_path("ana", tmp_path))[1]["tipo_falha"] == "invented_number"


def test_rater_name_cannot_escape_the_folder(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        label.csv_path("../x", tmp_path)
