"""Estado do caso de suporte que só fecha com prova (app/casestate.py), de ponta a ponta pela API."""
import pytest
from fastapi.testclient import TestClient

from app import cases, casestate, domain
from app.api import app
from app.auth import issue_token

client = TestClient(app)


@pytest.fixture(autouse=True)
def faq_is_a_case_intent(monkeypatch):
    # o domínio de exemplo não tem "troubleshoot"; o domínio do desafio declara CASE_INTENTS = {"troubleshoot"}
    monkeypatch.setattr(domain.active(), "CASE_INTENTS", frozenset({"faq"}), raising=False)


def say(text, conv=None):
    body = {"message": text, **({"conversation_id": conv} if conv else {})}
    return client.post("/chat", json=body, headers={"Authorization": f"Bearer {issue_token('u1')}"}).json()


def test_detectors_pt_and_en():
    assert casestate.confirms_resolved("Funcionou! Obrigado") and casestate.confirms_resolved("it works now, thanks")
    assert not casestate.confirms_resolved("obrigado") and not casestate.confirms_resolved("ok, entendi")
    assert casestate.reports_still_broken("ainda não funcionou") and casestate.reports_still_broken("still not working")
    assert not casestate.confirms_resolved("funcionou mas continua com erro")  # a negação vence


def test_a_turn_opens_the_case_and_thanks_never_resolve_it():
    r1 = say("Qual o prazo de entrega?")
    assert r1["case_state"] == "awaiting_customer"
    r2 = say("ok, obrigado", r1["conversation_id"])
    assert r2["case_state"] != "resolved"
    assert casestate.get(r1["conversation_id"])["state"] == "awaiting_customer"
    assert casestate.get(r1["conversation_id"])["proof"] is None


def test_customer_confirmation_resolves_with_proof():
    conv = say("Qual o prazo de entrega?")["conversation_id"]
    r = say("funcionou, deu certo!", conv)
    assert r["case_state"] == "resolved" and casestate.get(conv)["proof"] == "customer_confirmed"


def test_a_new_problem_after_resolution_starts_a_fresh_case():
    conv = say("Qual o prazo de entrega?")["conversation_id"]
    say("funcionou, deu certo!", conv)
    r = say("Como funciona a troca de produto?", conv)
    row = casestate.get(conv)
    assert r["case_state"] == "awaiting_customer" and row["cycles"] == 0 and len(row["steps"]) == 1


def test_two_cycles_still_broken_escalate_with_the_attempts_attached():
    conv = say("Qual o prazo de entrega?")["conversation_id"]
    r2 = say("ainda não funcionou", conv)
    assert not r2["handoff"]["required"] and casestate.get(conv)["cycles"] == 1
    r3 = say("continua igual, o mesmo erro", conv)
    assert r3["handoff"]["required"] and r3["case_state"] == "escalated" and "escalation" in r3["route"]
    note = cases.notes(r3["handoff"]["ticket_id"])
    assert note and "tentativas sem sucesso (2 ciclos)" in note[0]


def test_tried_steps_reach_the_agent_prompt_and_stop_after_close():
    conv = say("Qual o prazo de entrega?")["conversation_id"]
    assert casestate.attempts(conv)  # o 1º turno virou "passo tentado"
    from app.agents import Context, _lang_tail

    ctx = Context(text="x", language="pt", user_id="u1", conversation_id=conv, intent="faq", history=[],
                  user_summary="", conversation_digest="")
    ctx.facts["attempted_steps"] = casestate.attempts(conv)
    assert "não repita o mesmo conselho" in _lang_tail(ctx)
    say("funcionou!", conv)
    assert casestate.attempts(conv) == []  # caso fechado: nada a evitar


def test_a_tool_can_prove_resolution_when_the_domain_offers_the_hook(monkeypatch):
    monkeypatch.setattr(domain.active(), "tool_confirms_resolution", lambda calls: True, raising=False)
    conv = say("Qual o prazo de entrega?")["conversation_id"]
    r = say("ainda não funcionou", conv)  # outro ciclo, mas a ferramenta mostra o problema resolvido
    assert r["case_state"] == "resolved" and casestate.get(conv)["proof"] == "tool_verified"


def test_intents_outside_the_case_set_are_untouched(monkeypatch):
    monkeypatch.setattr(domain.active(), "CASE_INTENTS", frozenset({"troubleshoot"}), raising=False)
    r = say("Qual o prazo de entrega?")
    assert r["case_state"] is None and casestate.get(r["conversation_id"]) is None
