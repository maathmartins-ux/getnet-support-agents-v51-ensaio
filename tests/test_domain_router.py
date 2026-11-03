"""Router do desafio (frente R): taxonomia e desempates da SPEC, offline, sobre os casos commitados."""
import json
import re

import pytest

from app.config import ROOT

CASES = [json.loads(line) for line in (ROOT / "evals" / "cases.jsonl").read_text("utf-8").splitlines()
         if line.strip()]
ROUTED = [c for c in CASES if c["split"] in ("official", "replan", "dependent", "parallel", "approval")]
MEMORY = [c for c in CASES if c["split"] == "memory"]
_ENTITY = re.compile(r"\b(T\d{4}[A-Z]|TX\d{4}|Get Cl[aá]ssica|Get Smart|Get Conta)\b", re.IGNORECASE)


@pytest.fixture
def router(domain_data):
    from app import router as r
    return r


def history_of(router, before: list[str], extra: str = "") -> list[dict]:
    """Turnos anteriores como o pipeline grava: fala do cliente com a intenção classificada + resposta."""
    hist: list[dict] = []
    for msg in before:
        intent = router.classify_offline(msg, hist).intent
        hist += [{"role": "user", "content": msg, "intent": intent},
                 {"role": "assistant", "content": extra}]
    return hist


@pytest.mark.parametrize("case", ROUTED, ids=lambda c: c["id"])
def test_offline_intent_and_plan_of_every_committed_case(router, case):
    from app import domain
    got = router.classify_offline(case["message"], [])
    assert got.intent == case["expect"]["intent"]
    assert got.plan == domain.active().PLANS[case["expect"]["intent"]]


@pytest.mark.parametrize("case", MEMORY, ids=lambda c: c["id"])
def test_memory_followup_inherits_or_resolves_the_intent(router, case):
    hist = history_of(router, case["before"])
    assert router.classify_offline(case["message"], hist).intent == case["expect"]["intent"]


@pytest.mark.parametrize("case", MEMORY, ids=lambda c: c["id"])
def test_memory_standalone_is_accepted_when_its_entities_were_in_the_conversation(router, case):
    expected = case["expect"]["standalone"]
    cited = ", ".join(dict.fromkeys(m.group(0) for m in _ENTITY.finditer(expected)))  # a última resposta citou
    hist = history_of(router, case["before"], extra=f"Itens citados: {cited}." if cited else "")
    assert router.check_standalone(expected, case["message"], hist) == expected


def test_standalone_with_an_invented_id_is_rejected(router):
    hist = history_of(router, ["Minha maquininha não conecta na internet"])
    assert router.check_standalone("O terminal T9999Z está offline?", "E o outro?", hist) == ""


def test_spec_tiebreaks(router):
    c = router.classify_offline
    assert c("Minha maquininha dá erro ao passar o cartão", []).intent == "troubleshoot"  # 1: sintoma com "minha"
    assert c("Quais vendas minhas foram recusadas ontem?", []).intent == "support"  # consulta, sem sintoma
    assert c("O que é a Get Smart? E quanto vendi ontem?", []).intent == "multi"  # 2: produto + dado meu
    assert c("Como funciona o Pix para a minha loja?", []).intent == "knowledge"  # 3: como funciona, com "minha"
    assert c("Qual a cotação do dólar hoje?", []).intent == "general"  # 4: câmbio → general
    assert c("Quero falar com um atendente", []).intent == "human_request"


def test_general_never_escalates_and_troubleshoot_waits_for_records(domain_data):
    from app import domain
    d = domain.active()
    assert d.NO_ESCALATION == {"general"} and d.DEPENDS["faq"] == {"records"}
    assert d.PLANS["troubleshoot"] == ["records", "faq"] and "faq" in d.ALLOWED["records"]
