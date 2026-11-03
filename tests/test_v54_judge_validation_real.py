"""Juiz × humanos em respostas reais e calibração pelo veredito completo (idioma conta, data de hoje no prompt)."""
import json

from evals import judge, label


def test_judge_vs_humans_uses_consensus_then_agreement(tmp_path):
    (tmp_path / "judge.json").write_text(json.dumps({"verdicts": [
        {"id": "a", "run": 0, "grounded": True, "language_ok": True},
        {"id": "b", "run": 0, "grounded": True, "language_ok": False},
        {"id": "c", "run": 0, "grounded": False},
        {"id": "a", "run": 1, "grounded": False}]}), encoding="utf-8")
    by_rater = {"bianca": {"a": True, "b": False, "c": True}, "matheus": {"a": True, "b": False, "c": False}}
    out = label.judge_vs_humans(by_rater, {"c": {"v": "fail"}}, tmp_path)
    assert out["casos"] == 3 and out["concordancia"] == 1.0  # b: idioma errado reprova; c: consenso diz falha
    assert out["validacao"]["validated"] is False  # 3 casos: abaixo de 10 por classe
    assert label.judge_vs_humans({"x": {"z": True}}, None, tmp_path) is None


def test_calibration_compares_the_full_verdict_and_the_prompt_has_today():
    seen = []

    class Lang:
        model = "claude-x"

        def complete(self, system, messages, max_tokens=1024, schema=None):
            seen.append(messages[-1]["content"])

            class R:
                @staticmethod
                def json():
                    return {"grounded": True, "helpful": True, "language_ok": False, "leaks_other_customer": False,
                            "score": 2, "reason": "idioma", "failure_type": "wrong_language"}
            return R()

    from pathlib import Path

    cal = Path(__file__).parent / "_cal_tmp.jsonl"
    cal.write_text(json.dumps({"id": "c1", "question": "How many?", "answer": "Até 48x.", "evidence": ["48x"],
                               "human_grounded": False}) + "\n", encoding="utf-8")
    try:
        out = judge.run(Lang(), [], calibration=cal)
    finally:
        cal.unlink()
    assert out["calibration_pairs"][0]["judge"] is False  # o juiz reprovou pelo idioma: concorda com o humano
    assert seen and seen[-1].startswith("Data de hoje: ")
