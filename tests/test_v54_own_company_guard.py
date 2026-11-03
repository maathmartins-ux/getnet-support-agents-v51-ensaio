"""Ensaio de 03/11 (replan ao vivo, padrão A): pergunta sobre a própria empresa ia ao `general` (sem escalada)."""
from __future__ import annotations

from app import domain, router


def _decision(intent: str, standalone: str = "") -> router.RoutedDecision:
    return router.RoutedDecision(intent=intent, plan=list(router._plans()[intent]), language="en", confidence=0.9,
                                 standalone=standalone)


def test_company_question_in_a_no_escalation_intent_goes_to_knowledge(monkeypatch):
    d = domain.active()
    monkeypatch.setattr(d, "NO_ESCALATION", {"records"}, raising=False)
    monkeypatch.setattr(d, "OWN_COMPANY", r"\bloja exemplo\b", raising=False)
    got = router._own_company_guard(_decision("records"), "Qual o salário de um vendedor da Loja Exemplo?")
    assert got.intent == d.OWN_COMPANY_INTENT and got.plan == list(router._plans()[d.OWN_COMPANY_INTENT])
    # sem o nome da empresa (clima, câmbio): fica onde estava
    same = router._own_company_guard(_decision("records"), "Vai chover amanhã em Porto Alegre?")
    assert same.intent == "records"


def test_guard_reads_the_standalone_and_is_off_without_the_domain_field(monkeypatch):
    d = domain.active()
    monkeypatch.setattr(d, "NO_ESCALATION", {"records"}, raising=False)
    monkeypatch.setattr(d, "OWN_COMPANY", r"\bloja exemplo\b", raising=False)
    got = router._own_company_guard(_decision("records", "Quanto ganha um vendedor da Loja Exemplo?"), "E ele?")
    assert got.intent == d.OWN_COMPANY_INTENT
    monkeypatch.setattr(d, "OWN_COMPANY", None, raising=False)
    assert router._own_company_guard(_decision("records"), "salário na Loja Exemplo").intent == "records"


def test_contract_prompt_states_the_rule():
    text = (domain.KIT_PROMPTS / "contract" / "router.md").read_text(encoding="utf-8")
    assert "PRÓPRIA empresa" in text and "FORA" in text
