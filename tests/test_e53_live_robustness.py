"""E53 — eval ao vivo robusto.

Cota: com 11 splits e cota igual (teto / nº de splits), dependent, real, official-var e heldout abortavam por teto com
o total sobrando. A cota é proporcional a casos × repeat × turnos e a sobra de quem terminou fica para os outros.
Juiz: num passo separado, ele pode ficar sem rodar quando o tempo acaba; por isso roda no mesmo processo, logo
depois de cada split.
"""
import json
import threading

import pytest

from app.llm import LLMReply
from evals import judge, run_evals


class PerTurnClient:
    """Cada mensagem (inclusive os turnos `before` dos casos de memória) custa `cost`."""

    def __init__(self, cost=0.2):
        self.cost, self.lock, self.calls = cost, threading.Lock(), []

    def send(self, message, user_id, conversation_id):
        with self.lock:
            self.calls.append(message)
        return {"intent": "faq", "conversation_id": "c", "answer": "Resposta com base na fonte.", "replans": [],
                "route": ["router", "faq"], "usage": {"cost_usd": self.cost}}


class FakeJudge:
    model = "claude-opus-5-5"

    def __init__(self):
        self.prompts, self.lock = [], threading.Lock()

    def complete(self, system, messages, max_tokens=1024, schema=None):
        with self.lock:
            self.prompts.append(messages[0]["content"])
        answer = messages[0]["content"].split("Resposta:")[-1]
        bad = any(s in answer for s in ("1 dia útil", "90 dias", "Bruno Lima", "Nosso atendimento"))
        return LLMReply(json.dumps({"grounded": not bad, "helpful": True, "language_ok": not bad,
                                    "leaks_other_customer": "Bruno Lima" in answer, "score": 4,
                                    "failure_type": "none", "reason": "ok"}), self.model)


def _saved(split):
    return json.loads((run_evals.RESULTS_DIR / f"live_{split}.json").read_text(encoding="utf-8"))


def test_shares_follow_cases_repeat_and_turns_so_no_split_aborts_when_total_suffices():
    # official 4 casos (0,8), replan 3 (0,6), memory 1 caso com 1 turno antes (0,4): 1,8 no total, teto 2,0.
    # Cota igual daria 0,667 a cada um e o official (0,8) abortaria.
    weights = run_evals.split_weights(["official", "replan", "memory"], {})
    assert weights == {"official": 4.0, "replan": 3.0, "memory": 2.0}
    reports = run_evals.run_splits(["official", "replan", "memory"], max_usd=2.0, workers=1,
                                   usd_per_case=0.2, client=PerTurnClient(0.2))
    assert {s: r["status"] for s, r in reports.items()} == {s: "complete" for s in ("official", "replan", "memory")}
    assert _saved("official")["max_usd"] == round(2.0 * 4 / 9, 6) > 2.0 / 3
    assert _saved("memory")["spent_usd"] == pytest.approx(0.4)  # o turno anterior entra no gasto


def test_repeat_by_split_weighs_the_share():
    run_evals.run_splits(["official", "replan"], max_usd=10.0, workers=4, client=PerTurnClient(0.01),
                         repeat_by={"official": 2})
    off, rep = _saved("official"), _saved("replan")
    assert len(off["rows"]) == 8 and len(rep["rows"]) == 3
    assert off["max_usd"] == round(10.0 * 8 / 11, 6) and off["stability"]["runs"] == 2
    assert run_evals.parse_repeat_by("official=3, memory=3") == {"official": 3, "memory": 3}
    with pytest.raises(ValueError):
        run_evals.parse_repeat_by("official:3")


def test_budget_lends_the_leftover_of_a_finished_split():
    b = run_evals._Budget(1.0, {"a": 1, "b": 1})
    assert b.shares == {"a": 0.5, "b": 0.5}
    assert b.limit("b", 0.4, 0.3) == 0.5  # sem sobra ainda: a cota
    b.release("a", 0.1)  # a terminou gastando 0,1: 0,4 vão para a sobra
    assert b.limit("b", 0.4, 0.3) == pytest.approx(0.7)  # pega só o que falta para a próxima leva
    assert b.state("b") == {"share": 0.5, "borrowed": 0.2, "limit": 0.7}
    assert b.pool == pytest.approx(0.2)


def test_judge_runs_after_each_split_in_the_same_process_and_pays_trust_once():
    fake = FakeJudge()
    run_evals.run_splits(["official", "replan"], max_usd=None, workers=2, client=PerTurnClient(0.01),
                         judge=lambda: fake)
    out = json.loads((run_evals.RESULTS_DIR / "judge.json").read_text(encoding="utf-8"))
    assert sorted(out["live_files"]) == ["live_official.json", "live_replan.json"]
    assert {v["split"] for v in out["verdicts"]} == {"official", "replan"} and len(out["verdicts"]) == 7
    assert out["judge_unreliable"] is False and out["by_split"]["official"]["helpful_rate"] == 1.0
    warmup = len(judge.CANARIES) + len(judge.load_calibration())
    assert len(fake.prompts) == warmup + 7  # canários e calibração uma vez só, não por split
    assert _saved("official")["judge"]["verdicts"] == 4 and _saved("replan")["judge"]["status"] == "ran"


def test_cut_after_first_split_still_leaves_it_judged_and_partial_is_not_judged():
    fake = FakeJudge()
    first = run_evals.run(split="official", live=True, client=PerTurnClient(0.01), judge=lambda: fake)
    assert first["status"] == "complete" and first["judge"]["verdicts"] == 4
    cut = run_evals.run(split="replan", live=True, client=PerTurnClient(0.5), max_usd=0.6, usd_per_case=0.5,
                        judge=lambda: fake)
    assert cut["status"] == "aborted_max_usd" and "judge" not in cut  # parcial não é evidência
    out = json.loads((run_evals.RESULTS_DIR / "judge.json").read_text(encoding="utf-8"))
    assert out["live_files"] == ["live_official.json"] and len(out["verdicts"]) == 4


def test_rerun_of_a_split_replaces_its_verdicts_and_keeps_the_others(tmp_path):
    fake = FakeJudge()
    a, b = tmp_path / "live_a.json", tmp_path / "live_b.json"
    for path, n in ((a, 2), (b, 1)):
        path.write_text(json.dumps({"rows": [{"id": f"{path.stem}-{i}", "split": path.stem, "message": "q",
                                              "answer": "r"} for i in range(n)]}), encoding="utf-8")
    out = tmp_path / "judge.json"
    judge.judge_into(fake, a, out=out)
    judge.judge_into(fake, b, out=out)
    a.write_text(json.dumps({"rows": [{"id": "live_a-9", "split": "live_a", "message": "q", "answer": "r"}]}),
                 encoding="utf-8")
    rep = judge.judge_into(fake, a, out=out)
    assert sorted(v["id"] for v in rep["verdicts"]) == ["live_a-9", "live_b-0"]
    assert rep["trust_reused"] is True and rep["canaries"]["ran"] == 4


def test_judge_error_does_not_break_the_eval():
    def broken():
        raise RuntimeError("sem chave do juiz")

    rep = run_evals.run(split="official", live=True, client=PerTurnClient(0.01), judge=broken)
    assert rep["status"] == "complete" and rep["judge"]["status"] == "error"


def test_measured_cost_per_case_weighs_the_share(monkeypatch):
    """O replan (4–6 chamadas por caso) não aborta por cota: a cota pesa o custo medido por caso, não os turnos."""
    run_evals.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (run_evals.RESULTS_DIR / "live_replan.json").write_text(json.dumps(
        {"rows": [{}] * 3, "spent_usd": 0.6}), encoding="utf-8")  # US$ 0,20 por caso = 8 mensagens a 0,025
    monkeypatch.setenv("LIVE_USD_PER_TURN", "0.025")
    weights = run_evals.split_weights(["official", "replan"], {})
    assert weights["official"] == 4.0 and weights["replan"] == pytest.approx(3 * 0.2 / 0.025)
