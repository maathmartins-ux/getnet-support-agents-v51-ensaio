"""Checagem numérica que BLOQUEIA: número sem base é reescrito (com LLM) e, se persistir, trocado por
"[valor não confirmado]" com oferta de humano (NUMBERS_POLICY=redact, padrão), aberto como caso (escalate) ou só
sinalizado (flag). Soma/diferença/contagem sustentada pela evidência passa.
"""
import json

from fakes import fake_llm, resp, text

from app import grounding, pipeline, supervisor
from app.agents import AgentResult
from app.grounding import redact, unsupported_numbers
from app.observability import METRICS
from app.schemas import ChatRequest

SALES = json.dumps({"ok": True, "data": [{"id": "v1", "amount": 250.0}, {"id": "v2", "amount": 300.5},
                                         {"id": "v3", "amount": 199.5}, {"id": "v4", "amount": 500.0}]})


def _agent(answer, evidence):
    def run(ctx):
        return AgentResult("faq", "ok", text=answer, evidence=evidence)
    return run


def _ask(monkeypatch, answer, evidence, message="Quanto custa o frete?"):
    monkeypatch.setitem(supervisor.AGENTS, "faq", _agent(answer, evidence))
    return pipeline.handle(ChatRequest(message=message), "u1")


# --- o que a checagem aceita --------------------------------------------------------------------------------------
def test_correct_sum_and_count_from_the_tool_pass():
    assert unsupported_numbers("Você teve 4 vendas, total de R$ 1.250,00.", [SALES]) == []
    assert unsupported_numbers("Você teve 5 vendas, total de R$ 1.300,00.", [SALES]) == ["5", "1.300,00"]


def test_difference_net_value_passes_but_small_term_does_not():
    assert unsupported_numbers("Líquido: R$ 976,10.", ["bruto R$ 1.000,00; taxa R$ 23,90"]) == []
    # "2 dias" de "3 a 5 dias" (5 - 3) não é derivado: prazo pequeno segue sinalizado
    assert unsupported_numbers("Chega em 2 dias.", ["Entrega em 3 a 5 dias úteis."]) == ["2"]


def test_glued_scale_passes():
    assert unsupported_numbers("Isento acima de R$ 80 mil por mês.", ["Acima de R$ 80mil por mês"]) == []
    assert unsupported_numbers("Free above R$ 80mil a month", ["Acima de R$ 80 mil por mês"]) == []


def test_redact_keeps_currency_percent_and_suffix_together():
    out = redact("Custa R$ 49,90, taxa de 3% e abre às 9h.", ["49,90", "3", "9"], "pt")
    assert out == ("Custa [valor não confirmado], taxa de [valor não confirmado] e abre às "
                   "[valor não confirmado].")
    assert redact("Fee is 2.5%.", ["2.5"], "en") == "Fee is [unconfirmed value]."


# --- política no pipeline -------------------------------------------------------------------------------------------
def test_invented_number_is_redacted_with_offer_by_default(monkeypatch):
    before = METRICS.get("numeric_enforced_total", action="redacted")
    r = _ask(monkeypatch, "O frete custa R$ 49,90.", ["Frete: R$ 59,90."])
    assert r.numbers_action == "redacted" and r.unsupported_numbers == ["49,90"]
    assert "49,90" not in r.answer and "[valor não confirmado]" in r.answer
    assert "atendente humano" in r.answer and not r.handoff.required  # oferta, não caso aberto
    assert METRICS.get("numeric_enforced_total", action="redacted") == before + 1


def test_correct_total_is_not_punished_in_the_pipeline(monkeypatch):
    r = _ask(monkeypatch, "Foram 4 vendas, total de R$ 1.250,00.", [SALES], message="Quanto vendi?")
    assert r.numbers_action == "none" and r.unsupported_numbers == [] and "1.250,00" in r.answer


def test_flag_policy_only_signals(monkeypatch):
    monkeypatch.setenv("NUMBERS_POLICY", "flag")
    r = _ask(monkeypatch, "O frete custa R$ 49,90.", ["Frete: R$ 59,90."])
    assert r.numbers_action == "flagged" and r.answer == "O frete custa R$ 49,90."


def test_escalate_policy_opens_a_case(monkeypatch):
    monkeypatch.setenv("NUMBERS_POLICY", "escalate")
    r = _ask(monkeypatch, "O frete custa R$ 49,90.", ["Frete: R$ 59,90."])
    assert r.numbers_action == "escalated" and r.handoff.required
    assert r.handoff.reason == "unsupported_numbers" and r.route[-1] == "escalation"
    assert "[valor não confirmado]" in r.answer


def test_one_regeneration_with_the_forbidden_list_when_there_is_llm(monkeypatch):
    llm, msgs = fake_llm([resp("end_turn", text("O frete custa R$ 59,90."))])
    monkeypatch.setattr(grounding, "get_llm", lambda role="agent": llm)
    r = _ask(monkeypatch, "O frete custa R$ 49,90.", ["Frete: R$ 59,90."])
    assert r.numbers_action == "regenerated" and r.answer == "O frete custa R$ 59,90."
    assert r.unsupported_numbers == []
    sent = msgs.sent[0]["messages"][0]["content"]
    assert "49,90" in sent and "Frete: R$ 59,90." in sent and len(msgs.sent) == 1  # uma reescrita só


def test_regeneration_that_still_invents_falls_back_to_redaction(monkeypatch):
    llm, _ = fake_llm([resp("end_turn", text("O frete custa R$ 39,90."))])
    monkeypatch.setattr(grounding, "get_llm", lambda role="agent": llm)
    r = _ask(monkeypatch, "O frete custa R$ 49,90.", ["Frete: R$ 59,90."])
    assert r.numbers_action == "redacted" and "49,90" not in r.answer and "39,90" not in r.answer
