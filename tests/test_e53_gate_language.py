"""E53 — `--calibrate-gate` por idioma.

Um piso de cosseno (0,88) calibrado sem perguntas em inglês não separa nada no denso: com e sem fonte, as perguntas
em inglês ficavam em 0,82–0,88, e 4 oficiais em inglês com fonte foram recusadas pelo portão. Por isso a calibração
mostra responde/recusa por idioma e avisa quando um idioma dos clientes não tem pergunta no gold.
"""
import json
from types import SimpleNamespace as NS

from evals import run_evals
from evals.run_evals import calibrate_gate


class FakeRetriever:
    name = "fake"

    def __init__(self, table):
        self.table = table

    def search(self, question, k=3):  # o agente expande a consulta (agents.expand_query): casa pelo começo
        hits = next(v for q, v in sorted(self.table.items(), key=lambda kv: -len(kv[0])) if question.startswith(q))
        return [NS(doc=NS(id=d), bm25=s, cosine=None) for d, s in hits][:k]


def _gold(tmp_path, rows, table):
    path = tmp_path / "retrieval.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return path, FakeRetriever(table)


def test_rates_per_language_show_the_threshold_that_refuses_english(tmp_path):
    rows, table = [], {}
    for i in range(6):  # português com fonte: BM25 alto; inglês com fonte: BM25 baixo (o caso que a taxa única esconde)
        rows.append({"question": f"qual o prazo da maquininha {i}?", "relevant": ["doc"]})
        table[rows[-1]["question"]] = [("doc", 20.0)]
    for i in range(3):
        rows.append({"question": f"what is the fee of the card reader {i}?", "relevant": ["doc"], "language": "en"})
        table[rows[-1]["question"]] = [("doc", 6.0)]
    for i in range(4):
        rows.append({"question": f"qual a capital da mongólia {i}?", "relevant": []})
        table[rows[-1]["question"]] = [("x", 1.0)]
    rows.append({"question": "what is the capital of mongolia?", "relevant": []})
    table[rows[-1]["question"]] = [("x", 1.0)]
    cal = calibrate_gate(*_gold(tmp_path, rows, table))
    assert cal["customer_languages"] == ["en", "pt"]  # os casos do kit têm pt e en
    best = cal["by_language"]["best"]
    assert best["pt"]["positives"] == 6 and best["en"]["positives"] == 3 and best["en"]["negatives"] == 1
    assert best["en"]["pos_answered"] == 1.0  # o melhor limiar (6,0) responde os 3 em inglês
    assert cal["warnings"] == []
    md = run_evals.to_markdown({"metrics": {"ALL": {"cases": 0}}, "passed": True, "intent_acc": 1.0, "gate": 0.9,
                                "gate_calibration": cal})
    assert "por idioma (limiar em uso): en responde" in md


def test_language_without_questions_is_warned(tmp_path, capsys):
    rows = [{"question": "qual o prazo de entrega?", "relevant": ["doc"]},
            {"question": "qual a capital da mongólia?", "relevant": []}]
    table = {rows[0]["question"]: [("doc", 9.0)], rows[1]["question"]: [("x", 1.0)]}
    cal = calibrate_gate(*_gold(tmp_path, rows, table))
    assert any("sem perguntas em en" in w for w in cal["warnings"])
    md = run_evals.to_markdown({"metrics": {"ALL": {"cases": 0}}, "passed": True, "intent_acc": 1.0, "gate": 0.9,
                                "gate_calibration": cal})
    assert "AVISO do portão: sem perguntas em en" in md


def test_missing_positives_or_negatives_in_one_language_is_warned():
    by = {"pt": {"positives": 3, "negatives": 2}, "en": {"positives": 2, "negatives": 0},
          "es": {"positives": 0, "negatives": 1}}
    warns = run_evals.language_warnings(by, {"pt", "en", "es"})
    assert warns == ["sem perguntas SEM fonte em en: não se sabe se o portão recusa o que não tem fonte",
                     "sem perguntas COM fonte em es: não se sabe quanto o portão recusa de respondível"]


def test_cli_prints_the_language_table_and_the_warning(capsys):
    assert run_evals.main(["--calibrate-gate"]) == 0  # gold do kit: só português; os casos têm inglês
    out = capsys.readouterr().out
    assert "| idioma | em uso | melhor |" in out and "| pt |" in out
    assert "AVISO: sem perguntas em en no gold de calibração" in out


def test_question_language_prefers_the_declared_field():
    assert run_evals.question_language({"question": "qual o prazo?", "language": "en"}) == "en"
    assert run_evals.question_language({"question": "What is the fee?"}) == "en"
    assert run_evals.question_language({"question": "Pix?"}) == "?"
