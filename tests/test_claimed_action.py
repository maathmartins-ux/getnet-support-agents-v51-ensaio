"""Regras financeiras duras (kit v5): ação alegada sem execução, promessa de data futura e as regras no prompt.

"Reiniciei sua maquininha" sem tool de reinício no turno é mentira operacional: vira `risk_flags: claimed_action`,
uma reescrita com LLM e, se persistir (ou offline), a frase sai com o aviso de que nada foi feito. Ação proposta
(pendente de confirmação) não é execução. Medido nas 177 respostas ao vivo da v4: 0 falso positivo.
"""
import pytest
from fakes import fake_llm, resp, text

from app import domain, grounding, pipeline, supervisor
from app.agents import AgentResult
from app.grounding import claimed_actions, date_promises, risk_flags
from app.schemas import ChatRequest, Handoff, ToolCall


@pytest.mark.parametrize("answer", ["Pronto, reiniciei sua maquininha.", "Abri o chamado para você.",
                                    "Estornei a venda de ontem.", "I restarted your terminal.",
                                    "Your refund has been issued.", "I've passed your question to a human agent."])
def test_claim_without_execution_is_detected(answer):
    assert claimed_actions(answer, [], False, [])


def test_executed_tool_ticket_negation_and_source_are_not_claims():
    done = [ToolCall(name="restart_terminal", ok=True)]
    assert claimed_actions("Reiniciei sua maquininha T1.", done, False, []) == []
    assert claimed_actions("Encaminhei para um atendente (protocolo T-1).", [], True, []) == []
    assert claimed_actions("Ainda não reiniciei: confirme a ação A-1.", [], False, []) == []
    assert claimed_actions("I haven't cancelled anything yet.", [], False, []) == []
    # política copiada da fonte ("liberamos") não é alegação de ação deste turno
    assert claimed_actions("Liberamos o valor em até 2 dias.", [], False, ["Liberamos o valor em até 2 dias."]) == []


def test_pending_action_is_not_execution():
    pending = [ToolCall(name="cancel_record", ok=False)]  # needs_confirmation volta ok=False
    assert claimed_actions("Cancelei o pedido 1002.", pending, False, []) == ["Cancelei"]


def test_future_date_promise_needs_the_date_in_the_evidence():
    assert date_promises("O valor vai cair amanhã na sua conta.", ["crédito D+30"])
    assert date_promises("Your money will be credited by Friday.", [])
    assert date_promises("O valor será creditado em 2 dias úteis.", ["crédito em até 2 dias úteis"]) == []
    assert date_promises("Amanhã vai chover em Recife.", []) == []  # clima não é promessa financeira
    assert "promessa_data" in risk_flags("O valor vai cair amanhã.", [])


def _agent(answer, calls=(), handoff=None):
    def run(ctx):
        return AgentResult("faq", "ok", text=answer, tool_calls=list(calls), handoff=handoff, evidence=[answer[:0]])
    return run


def test_offline_claim_is_flagged_and_removed(monkeypatch):
    monkeypatch.setitem(supervisor.AGENTS, "faq", _agent("Reiniciei sua maquininha. Teste uma venda agora."))
    r = pipeline.handle(ChatRequest(message="Minha maquininha travou"), "u1")
    assert "claimed_action" in r.risk_flags
    assert "Reiniciei" not in r.answer and "não foi executada" in r.answer and "Teste uma venda" in r.answer


def test_claim_backed_by_ticket_passes(monkeypatch):
    ticket = Handoff(required=True, reason="user_request", ticket_id="T-abc")
    monkeypatch.setitem(supervisor.AGENTS, "faq", _agent("Abri o chamado T-abc para você.", handoff=ticket))
    r = pipeline.handle(ChatRequest(message="Minha maquininha travou"), "u1")
    assert "claimed_action" not in r.risk_flags and r.answer.startswith("Abri o chamado")


def test_claim_is_rewritten_once_with_llm(monkeypatch):
    llm, msgs = fake_llm([resp("end_turn", text("Posso propor o reinício; nada foi feito ainda."))])
    monkeypatch.setattr(grounding, "get_llm", lambda role="agent": llm)
    monkeypatch.setitem(supervisor.AGENTS, "faq", _agent("I restarted your terminal remotely."))
    r = pipeline.handle(ChatRequest(message="Minha maquininha travou"), "u1")
    assert r.answer == "Posso propor o reinício; nada foi feito ainda." and "claimed_action" in r.risk_flags
    assert "I restarted" in msgs.sent[0]["messages"][0]["content"] and len(msgs.sent) == 1


@pytest.mark.parametrize("name", ["faq.md", "records.md", "general.md", "supervisor.md"])
def test_hard_financial_rules_are_in_every_agent_prompt(name):
    prompt = (domain.KIT_PROMPTS / name).read_text(encoding="utf-8")
    assert "Regras financeiras duras" in prompt and "promessa de data futura" in prompt
    assert "Nunca diga que fez algo" in prompt
