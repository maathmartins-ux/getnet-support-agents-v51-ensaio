"""R53 item 2 — desempates do domínio no router: o domínio dá as palavras, o motor dá o mecanismo.

Sem desempate, um held-out cego (offline) mediu intenção em 67,5%, com as confusões multi→support 7 (duas perguntas
independentes viravam uma consulta), troubleshoot→support 5 (sintoma lido como consulta de dado) e knowledge→support 3
(pergunta de regra com palavra de dado). Aqui com o domínio de EXEMPLO (faq/records/multi) + listas de teste;
"troubleshoot" entra só neste teste para o desempate de sintoma.
"""
import json

import pytest
from fakes import fake_llm, resp, text

from app import domain, router

ASK = ["qual", "quais", "quanto", "quantos", "como", "quando", "onde", "posso", "pode",
       "what", "which", "how", "when", "where", "can"]
RULES = [
    # sintoma → diagnóstico, exceto lista/consulta
    {"from": ["records"], "to": "troubleshoot", "words": ["nao chegou", "atrasad*", "erro", "trav*"],
     "unless": ["quais pedidos", "list*", "show me"]},
    # pergunta de regra/funcionamento → faq, exceto quando cita um registro
    {"from": ["records"], "to": "faq", "words": ["como funciona", "posso", "politica", "how does"], "unless_id": True},
]


@pytest.fixture
def lists(monkeypatch):
    d = domain.active()
    monkeypatch.setattr(d, "DISAMBIGUATION", {"ask_words": ASK, "rules": RULES}, raising=False)
    monkeypatch.setitem(d.PLANS, "troubleshoot", ["records", "faq"])
    return d


def intent(text_, history=()):
    return router.classify_offline(text_, list(history)).intent


# --- multi × uma intenção só: dois pedidos independentes --------------------------------------------------------
def test_two_independent_asks_joined_by_and_become_multi(lists):
    assert router.split_asks("Qual o prazo de entrega e qual o status do pedido 1002?", ASK) == [
        "Qual o prazo de entrega", "qual o status do pedido 1002?"]
    assert intent("Qual o prazo de entrega e qual o status do pedido 1002?") == "multi"
    assert intent("How long does delivery take, and where is my order 1002?") == "multi"


def test_and_without_an_own_ask_on_the_right_does_not_split(lists):
    assert router.split_asks("Qual o prazo de troca e devolução?", ASK) == ["Qual o prazo de troca e devolução?"]
    assert router.split_asks("Meu pedido 1002 atrasou, como resolvo?", ASK) == [
        "Meu pedido 1002 atrasou, como resolvo?"]  # o lado esquerdo não tem pedido próprio
    assert intent("Qual o prazo de troca e devolução?") == "faq"


def test_without_domain_lists_nothing_changes(monkeypatch):
    monkeypatch.setattr(domain.active(), "DISAMBIGUATION", None, raising=False)
    assert intent("Qual o prazo de entrega e qual o status do pedido 1002?") == "records"  # comportamento de antes
    assert router.disambiguate("records", "meu pedido 1002 atrasou") == "records"
    assert router.disambiguation_block() == ""


# --- sintoma × consulta ----------------------------------------------------------------------------------------
def test_symptom_words_turn_a_lookup_into_troubleshoot_unless_it_is_a_listing(lists):
    assert intent("Meu pedido 1002 está atrasado") == "troubleshoot"
    assert intent("O app dá erro quando abro o pedido 1002") == "troubleshoot"
    assert intent("Quais pedidos estão atrasados?") == "records"  # lista é consulta de dado
    assert intent("Onde está meu pedido 1002?") == "records"  # sem sintoma: consulta


# --- regra/funcionamento × consulta ----------------------------------------------------------------------------
def test_rule_question_with_a_data_word_is_knowledge_unless_it_cites_a_record(lists):
    assert intent("Como funciona o cancelamento de pedido?") == "faq"
    assert intent("Posso cancelar um pedido depois de pago?") == "faq"
    assert intent("Posso cancelar o pedido 1002?") == "records"  # cita o registro: é ação sobre ele


def test_words_ignore_accent_and_case_and_star_is_a_prefix(lists):
    assert router.mentions("Política de TROCA", ["politica"])
    assert router.mentions("a maquininha está travando", ["trav*"])
    assert not router.mentions("travessa", ["trava"])  # sem "*" a palavra é inteira


def test_rule_to_an_intent_the_domain_does_not_have_is_ignored(monkeypatch):
    monkeypatch.setattr(domain.active(), "DISAMBIGUATION",
                        {"rules": [{"from": ["records"], "to": "inexistente", "words": ["atrasad*"]}]}, raising=False)
    assert router.disambiguate("records", "pedido 1002 atrasado") == "records"


def test_llm_router_receives_the_same_lists_as_tiebreaks(lists, monkeypatch):
    body = {"standalone": "Meu pedido 1002 está atrasado", "intent": "records", "plan": ["records"],
            "language": "pt", "confidence": 0.9}
    llm, msgs = fake_llm([resp("end_turn", text(json.dumps(body)))], model="claude-haiku-5-5", effort="low")
    monkeypatch.setattr(router, "get_llm", lambda role="agent": llm)
    d = router.route("Meu pedido 1002 está atrasado", [])
    sent = msgs.sent[0]["messages"][0]["content"]
    assert "Desempates do domínio" in sent and "records → troubleshoot" in sent and "nao chegou" in sent
    assert d.intent == "records"  # com LLM o código não sobrescreve: o modelo decide com os desempates à vista
