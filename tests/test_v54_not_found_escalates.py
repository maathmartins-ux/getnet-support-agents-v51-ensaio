"""Id citado pelo cliente que não existe na conta não resolve o pedido: vai ao humano (enunciado; split replan)."""
from app import agents, supervisor
from app.agents import AgentResult, Context
from app.schemas import ToolCall


def test_cited_id_not_found_in_every_lookup():
    calls = [ToolCall(name="get_transactions", args={"transaction_id": "TX8888"}, ok=False),
             ToolCall(name="get_settlements", args={"period": "all"}, ok=True)]
    evidence = ['{"ok": false, "error": "not_found"}', '{"ok": true, "data": {"items": []}}']
    assert agents.cited_not_found("Quando cai a TX8888?", calls, evidence) == ["TX8888"]


def test_id_found_by_some_lookup_or_not_cited_is_not_missing():
    calls = [ToolCall(name="get_transactions", args={"transaction_id": "TX1006"}, ok=False),
             ToolCall(name="get_transactions", args={"transaction_id": "TX1006", "period": "all"}, ok=True)]
    evidence = ['{"ok": false, "error": "not_found"}', '{"ok": true, "data": {"transactions": [1]}}']
    assert agents.cited_not_found("E a TX1006?", calls, evidence) == []
    assert agents.cited_not_found("Quanto vendi hoje?", calls, evidence) == []


def test_records_not_found_goes_to_human_on_the_table(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_FAST", "off")
    monkeypatch.setattr(supervisor, "get_llm", lambda role="agent": type("Off", (), {"enabled": False})())
    nf = AgentResult("records", "insufficient", reason="not_found", text="Não encontrei a TX8888.")
    monkeypatch.setitem(supervisor.AGENTS, "records", lambda c: nf)
    c = Context(text="Quando cai a TX8888?", language="pt", user_id="u1", conversation_id="c-nf", intent="records")
    out = supervisor.run(["records"], c)
    assert out.route[-1] == "escalation" and out.results[-1].handoff.required
    assert out.results[-1].handoff.reason == "records_not_found"


def test_not_found_is_read_from_the_result_not_from_any_text():
    calls = [ToolCall(name="lookup", args={"ids": "TX1006"}, ok=True)]
    evidence = ['{"ok": true, "data": {"found": ["TX1006"], "not_found": []}}']
    assert agents.cited_not_found("E a TX1006?", calls, evidence) == []


def test_forced_escalation_drops_the_llm_offer_text():
    c = Context(text="A Getnet tem maquininha de criptomoeda?", language="pt", user_id="u1", conversation_id="c-of",
                intent="faq")
    out = supervisor.Outcome(engine="llm")
    supervisor._record("faq", AgentResult("faq", "insufficient", reason="not_in_sources"), c, out)
    out.answer = "Não encontrei. Posso encaminhar a um atendente?"
    supervisor._enforce_escalation(out, c)
    assert out.answer is None and out.results[-1].handoff.required
