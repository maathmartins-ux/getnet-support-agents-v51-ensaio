"""R12: `expect.after_human` — o plano seguiu no mesmo turno DEPOIS da resposta do humano (nenhuma execução ao vivo
mostrava passo de agente depois do humano; a checagem mede isso por caso)."""
from evals import run_evals


def _got(route, answered=True):
    return {"route": route, "steps": [{"agent": "escalation", "answered_live": answered}], "answer": "ok"}


def _case(after):
    return {"id": "h", "expect": {"after_human": after}}


def test_agent_after_the_answered_escalation_passes():
    got = _got(["router", "escalation", "human", "records"])
    assert run_evals.agents_after_human(got) == {"human", "records"}
    assert run_evals.score(_case(["records"]), got)["after_human"] is True


def test_agent_only_before_the_human_or_unanswered_fails():
    before_only = _got(["router", "records", "escalation", "human"])
    assert run_evals.score(_case(["records"]), before_only)["after_human"] is False
    assert run_evals.score(_case(["records"]), _got(["escalation", "records"], answered=False))["after_human"] is False
    assert run_evals.score(_case(["faq"]), _got(["records", "faq"]))["after_human"] is False  # sem escalada


def test_after_human_is_counted_in_the_split_summary():
    rows = [{"split": "hitl", "id": "h", "checks": {"after_human": True}, "ms": 1.0, "cost_usd": 0.0, "crash": False},
            {"split": "hitl", "id": "i", "checks": {"after_human": False}, "ms": 1.0, "cost_usd": 0.0, "crash": False}]
    assert run_evals.summarize(rows)["hitl"]["after_human_acc"] == 50.0
