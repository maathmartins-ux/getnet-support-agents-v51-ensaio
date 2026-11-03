"""Especialistas sem estado recebem a pergunta reescrita pelo router, completa, em vez do histórico da conversa."""
from app import agents
from app.agents import Context
from app.domain import prompt


def _ctx(text, standalone=None, history=None):
    c = Context(text=text, language="pt", user_id="u1", conversation_id="c1", intent="records")
    c.history = history if history is not None else [
        {"role": "user", "content": "Minhas maquininhas estão funcionando?"},
        {"role": "assistant", "content": "A T1988A está online. A T1988B está offline."},
    ]
    if standalone:
        c.facts["standalone"] = standalone
    return c


def test_specialist_gets_the_standalone_question_not_the_raw_history():
    c = _ctx("E a outra?", standalone="A maquininha T1988B está offline há quanto tempo?")
    msgs = agents.llm_history(c, c.text)
    assert len(msgs) == 1 and msgs[0]["role"] == "user"
    assert "Pergunta completa" in msgs[0]["content"] and "T1988B" in msgs[0]["content"]
    assert "Minhas maquininhas estão funcionando?" not in msgs[0]["content"]


def test_ledger_still_reaches_the_specialist():
    c = _ctx("E qual foi o valor dela?", standalone="Qual foi o valor da venda TX1006?")
    c.ledger = "[fatos da conversa] TX1006: amount 900,00"
    assert "TX1006: amount 900,00" in agents.llm_history(c, c.text)[0]["content"]


def test_without_standalone_or_with_flag_the_raw_history_comes_back(monkeypatch):
    c = _ctx("E a outra?")
    assert len(agents.llm_history(c, c.text)) >= 2
    monkeypatch.setenv("SPECIALIST_HISTORY", "on")
    c2 = _ctx("E a outra?", standalone="A T1988B está offline há quanto tempo?")
    assert len(agents.llm_history(c2, c2.text)) >= 2


def test_message_that_stands_alone_keeps_the_normal_path():
    c = _ctx("Quanto vendi hoje?", standalone="Quanto vendi hoje?")
    assert len(agents.llm_history(c, c.text)) >= 2


def test_router_prompt_carries_the_demonstratives_rule():
    text = prompt("router.md")
    assert "ÚLTIMA resposta do atendimento" in text and "a outra" in text
