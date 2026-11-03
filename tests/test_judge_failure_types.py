"""Juiz com tipo de defeito (`failure_type`) e o antes/depois por caso (evals/judge_diff.py).

O tipo separa "o modelo inventou um número" de "afirmou regra sem fonte" de "ofereceu ação que não existe": cada um
aponta para uma checagem diferente do motor. A calibração ganha `human_failure_type` (opcional) e o relatório dá
TPR/TNR do juiz por tipo; rótulo antigo sem o campo segue valendo só para o kappa.
"""
import json

from evals import judge, judge_diff


class ScriptedJudge:
    """Veredito por palavra da resposta: 'inventado' → número; 'janela' → frase; resto → ok."""

    model = "scripted"

    def complete(self, system, messages, max_tokens=1024, schema=None):
        from app.llm import LLMReply

        assert "failure_type" in schema["required"]
        content = messages[0]["content"].split("Resposta: ", 1)[1]
        kind = "invented_number" if "inventado" in content else "unsupported_claim" if "janela" in content else "none"
        return LLMReply(json.dumps({"grounded": kind == "none", "helpful": True, "language_ok": True,
                                    "leaks_other_customer": False, "score": 4, "failure_type": kind,
                                    "reason": kind}), self.model)


def _files(tmp_path, cal_rows):
    live = tmp_path / "live_official.json"
    live.write_text(json.dumps({"rows": [
        {"id": "o1", "split": "official", "message": "q", "answer": "valor inventado 99", "run": 0},
        {"id": "o2", "split": "official", "message": "q", "answer": "coloque perto da janela", "run": 0},
        {"id": "o3", "split": "official", "message": "q", "answer": "tudo certo", "run": 0}]}), encoding="utf-8")
    cal = tmp_path / "cal.jsonl"
    cal.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in cal_rows), encoding="utf-8")
    return live, cal


def test_report_counts_failure_types_and_tpr_tnr_per_type(tmp_path):
    live, cal = _files(tmp_path, [
        {"id": "c1", "question": "q", "answer": "valor inventado", "human_grounded": False,
         "human_failure_type": "invented_number"},
        {"id": "c2", "question": "q", "answer": "perto da janela", "human_grounded": False,
         "human_failure_type": "unsupported_claim"},
        {"id": "c3", "question": "q", "answer": "ok", "human_grounded": True, "human_failure_type": "none"},
        {"id": "c4", "question": "q", "answer": "valor inventado", "human_grounded": False,
         "human_failure_type": "stale_source"},  # juiz diz invented_number: erra o tipo
        {"id": "c5", "question": "q", "answer": "sem tipo", "human_grounded": True}])  # rótulo antigo
    rep = judge.run(ScriptedJudge(), [live], calibration=cal)
    assert rep["failure_types"]["ALL"] == {"invented_number": 1, "unsupported_claim": 1}
    by = rep["calibration"]["by_failure_type"]
    assert by["invented_number"] == {"positives": 1, "negatives": 3, "tpr": 1.0, "tnr": 0.667}
    assert by["stale_source"]["tpr"] == 0.0 and by["unsupported_claim"]["tpr"] == 1.0
    assert rep["calibration"]["cases"] == 5  # o rótulo sem tipo entra no kappa
    assert {c["id"]: c["failure_type"] for c in rep["canaries"]["details"]}["canary-vazamento"] == "none"
    assert all(c["expected_failure_type"] for c in rep["canaries"]["details"])


def test_calibration_without_types_is_backward_compatible(tmp_path):
    live, cal = _files(tmp_path, [{"id": "c1", "question": "q", "answer": "ok", "human_grounded": True}])
    rep = judge.run(ScriptedJudge(), [live], calibration=cal)
    assert rep["calibration"]["by_failure_type"] == {} and rep["calibration"]["agreement"] == 1.0


def test_judge_diff_table_matches_by_case_and_run(tmp_path):
    before = {"verdicts": [  # formato antigo: sem `run`, sem failure_type → ordem de aparição
        {"id": "official-05", "split": "official", "source": "live_official.json", "grounded": False,
         "reason": "remote restart unsupported"},
        {"id": "official-05", "split": "official", "source": "live_official.json", "grounded": True, "reason": "ok"},
        {"id": "official-01", "split": "official", "source": "live_official.json", "grounded": True, "reason": "ok"}]}
    after = {"verdicts": [
        {"id": "official-05", "split": "official", "source": "live_official.json", "run": 0, "grounded": True,
         "failure_type": "none", "reason": "restart is in policy:capabilities"},
        {"id": "official-05", "split": "official", "source": "live_official.json", "run": 1, "grounded": False,
         "failure_type": "unsupported_claim", "reason": "near a | window"},
        {"id": "official-01", "split": "official", "source": "live_official.json", "run": 0, "grounded": True,
         "failure_type": "none", "reason": "ok"}]}
    a, b, out = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "docs" / "JUDGE_DIFF.md"
    a.write_text(json.dumps(before), encoding="utf-8")
    b.write_text(json.dumps(after), encoding="utf-8")
    assert judge_diff.main([str(a), str(b), "--out", str(out)]) == 0
    md = out.read_text(encoding="utf-8")
    assert "| official | 2/3 (67%) | 2/3 (67%) | 1 | 1 |" in md
    assert "| official-05 | 0 | **não** → sim | ? → none | melhorou | restart is in policy:capabilities |" in md
    assert "| official-05 | 1 | sim → **não** | none → unsupported_claim | piorou | near a \\| window |" in md
