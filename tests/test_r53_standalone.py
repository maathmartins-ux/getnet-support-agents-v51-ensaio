"""R53 item 1 — o router devolve a pergunta completa do turno (ctx.facts["standalone"]) e classifica ESSA pergunta.

V5 ao vivo: memória pass@1 0,72 com 90,6% dos fatos certos; as 18 perdas eram de rota em seguimento curto
("e a outra?"). Com LLM, a reescrita sai na mesma chamada que classifica e o código recusa a que inventa dado.
"""
import json

from fakes import fake_llm, resp, text

from app import pipeline, router, supervisor
from app.schemas import ChatRequest


def hist(*turns):
    """(fala do cliente, intenção[, resposta]) -> histórico."""
    out = []
    for turn in turns:
        said, intent, answer = (*turn, "resposta")[:3]
        out += [{"role": "user", "content": said, "intent": intent},
                {"role": "assistant", "content": answer, "intent": intent}]
    return out


def router_llm(monkeypatch, **decision):
    body = {"standalone": "", "intent": "faq", "plan": ["faq"], "language": "pt", "confidence": 0.9, **decision}
    llm, msgs = fake_llm([resp("end_turn", text(json.dumps(body)))], model="claude-haiku-5-5", effort="low")
    monkeypatch.setattr(router, "get_llm", lambda role="agent": llm)
    return msgs


# --- sem LLM: completação determinística ----------------------------------------------------------------------
def test_offline_followup_swapping_an_entity_becomes_the_topic_question_with_the_new_entity():
    h = hist(("Qual o status do pedido 1002?", "records"))
    d = router.route("E o pedido 1003?", h)
    assert d.standalone == "Qual o status do pedido 1003?" and d.intent == "records"


def test_offline_followup_without_swap_is_subject_plus_followup():
    h = hist(("Como funciona a troca de produto?", "faq"))
    assert router.route("e o prazo?", h).standalone == "Como funciona a troca de produto? e o prazo?"
    # seguimento depois de seguimento: o assunto é a última fala que DECLARA assunto
    h2 = h + hist(("e o prazo?", "faq"))
    assert router.route("e quanto custa?", h2).standalone == "Como funciona a troca de produto? e quanto custa?"


def test_offline_short_reference_back_is_completed_with_the_subject():
    h = hist(("Não reconheço a venda do pedido 1006 no meu extrato", "records"))
    assert router.route("Quero contestar essa venda.", h).standalone == (
        "Não reconheço a venda do pedido 1006 no meu extrato. Quero contestar essa venda.")
    h_en = hist(("Tell me about the gift card", "faq"))
    assert router.route("Can I use it online?", h_en).standalone == "Tell me about the gift card. Can I use it online?"
    # "that" solto é conjunção, não referência
    own = "I noticed that my order 1002 has not shipped yet"
    assert router.route(own, h_en).standalone == own


def test_offline_message_that_stands_alone_is_its_own_standalone():
    h = hist(("Como funciona a troca de produto?", "faq"))
    own = "Qual o prazo de entrega para o Nordeste?"
    assert router.route(own, h).standalone == own
    assert router.route("e o prazo?", []).standalone == "e o prazo?"  # sem histórico não há o que completar


def test_offline_swap_classifies_the_completed_question(monkeypatch):
    seen = []
    real = router.classify_offline
    monkeypatch.setattr(router, "classify_offline", lambda t, h: seen.append(t) or real(t, h))
    h = hist(("Qual o status do pedido 1002?", "records"))
    router.route("E o pedido 1003?", h)
    assert seen == ["E o pedido 1003?", "Qual o status do pedido 1003?"]  # a 2ª é a que decide


# --- com LLM: mesma chamada reescreve e classifica ------------------------------------------------------------
def test_schema_asks_for_the_standalone_first_and_the_prompt_classifies_it():
    s = router.schema()
    assert s["required"][0] == "standalone" and list(s["properties"])[0] == "standalone"
    prompt = (router.domain.KIT_PROMPTS / "router.md").read_text(encoding="utf-8")
    assert "standalone" in prompt and "PERGUNTA COMPLETA" in prompt


def test_llm_standalone_is_returned_and_its_classification_wins_over_inheritance(monkeypatch):
    # "E o pedido 1003?" troca o id do assunto: a herança mandaria faq; a pergunta completa é records e vale ela
    h = hist(("Meu pedido 1001 foi recusado e eu quero saber o que houve com ele", "faq"))
    msgs = router_llm(monkeypatch, standalone="Qual o status do pedido 1003?", intent="records", plan=["records"])
    d = router.route("E o pedido 1003?", h)
    assert d.standalone == "Qual o status do pedido 1003?" and d.intent == "records"
    sent = msgs.sent[0]["messages"][0]["content"]
    assert "Meu pedido 1001 foi recusado" in sent  # a fala do assunto vai ao modelo, base da reescrita


def test_llm_rewrite_with_invented_id_is_rejected_and_falls_back_to_inheritance(monkeypatch):
    h = hist(("Meu pedido 1001 foi recusado e eu quero saber o que houve com ele", "faq"))
    router_llm(monkeypatch, standalone="Por que o pedido 1002 e o pedido 1009 foram recusados?", intent="records",
               plan=["records"], confidence=0.85)
    d = router.route("E o pedido 1002?", h)
    assert d.standalone == ""  # 1009 não está na conversa
    assert d.intent == "faq"  # comportamento anterior: decisão do modelo + herança do seguimento (troca de id)


def test_llm_without_standalone_field_keeps_the_previous_behaviour(monkeypatch):
    router_llm(monkeypatch, standalone=None, intent="records", plan=["records"])
    d = router.route("Onde está meu pedido 1002?", [])
    assert d.standalone == "" and d.intent == "records"


def test_invented_checks_ids_amounts_dates_and_relative_days():
    h = hist(("A venda de R$ 210,00 de 02/11 foi recusada", "faq", "A maquininha T1988B está offline."))
    assert router.invented("Por que a venda de R$ 210 foi recusada?", "e ela?", h) == []  # mesmo valor
    assert router.invented("Qual o status da T1988B?", "e a outra?", h) == []  # id da resposta do assistente
    assert router.invented("Qual o status da T1988C?", "e a outra?", h) == ["T1988C"]
    assert router.invented("E a venda de R$ 300,00?", "e a outra?", h) == ["300,00"]
    assert router.invented("E a venda de 05/11?", "e a outra?", h) == ["05/11"]
    assert router.invented("E a venda de ontem?", "e a outra?", h) == ["ontem"]
    assert router.invented("E a venda de ontem?", "e a de ontem?", h) == []


def test_pipeline_puts_the_standalone_in_the_context(monkeypatch):
    seen = []
    real = supervisor.run
    monkeypatch.setattr(supervisor, "run", lambda plan, ctx, conf=1.0, **kw: seen.append(dict(ctx.facts))
                        or real(plan, ctx, conf, **kw))
    first = pipeline.handle(ChatRequest(message="Qual o status do pedido 1002?"), "u1")
    pipeline.handle(ChatRequest(message="E o pedido 1003?", conversation_id=first.conversation_id), "u1")
    assert seen[0]["standalone"] == "Qual o status do pedido 1002?"
    assert seen[1]["standalone"] == "Qual o status do pedido 1003?"
