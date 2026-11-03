"""Seguimento elíptico herda a intenção do assunto (app/followup.py): "E a TX1008?" depois de um diagnóstico."""
from app import followup, pipeline, router
from app.schemas import ChatRequest, RouterDecision


def dec(intent="records", conf=0.85, lang="pt"):
    from app import domain

    return RouterDecision(intent=intent, plan=list(domain.active().PLANS[intent]), language=lang, confidence=conf)


def hist(*turns):
    """(fala do cliente, intenção) -> histórico com a resposta do assistente no meio."""
    out = []
    for text, intent in turns:
        out += [{"role": "user", "content": text, "intent": intent},
                {"role": "assistant", "content": "resposta", "intent": intent}]
    return out


TOPIC = hist(("Meu pedido 1001 foi recusado e eu quero saber o que houve com ele", "faq"))


def test_swapping_an_id_of_the_same_shape_inherits_the_intent_even_with_high_confidence():
    got = followup.inherit(dec("records", 0.85), "E o pedido 1002?", TOPIC)
    assert got.intent == "faq" and got.plan == ["faq"] and got.language == "pt"
    assert got.confidence >= followup.INHERITED_MIN_CONFIDENCE


def test_relative_day_swap_inherits():
    h = hist(("Quando cai o dinheiro do pedido que eu fiz ontem na loja online?", "records"))
    assert followup.inherit(dec("faq"), "E a de anteontem?", h).intent == "records"
    assert followup.inherit(dec("faq"), "And the ones from the day before?", h).intent == "records"


def test_other_noun_inherits_only_when_the_topic_mentions_that_noun():
    h = hist(("Minha maquininha não conecta na internet.", "faq"))
    assert followup.inherit(dec("records"), "E a outra maquininha?", h).intent == "faq"
    assert followup.inherit(dec("records"), "E a outra loja?", h).intent == "records"  # a "loja" não estava no assunto


def test_low_confidence_inherits_without_an_entity_swap_and_does_not_escalate():
    h = hist(("Como funciona o reembolso?", "faq"))
    got = followup.inherit(dec("records", 0.3), "E a Get Clássica?", h)
    assert got.intent == "faq" and got.confidence >= 0.5  # acima do corte de escalação por baixa confiança


def test_high_confidence_different_entity_type_keeps_the_router_decision():
    h = hist(("Meu pedido 1001 foi recusado e eu quero saber o que houve com ele", "faq"))
    assert followup.inherit(dec("records", 0.85), "E a Get Clássica?", h).intent == "records"


def test_own_question_is_never_elliptical_even_with_low_confidence():
    h = TOPIC
    for text in ("E quanto custa?", "E por que foi recusado?", "and how long does it take?", "E posso cancelar?"):
        assert not followup.is_elliptical(text), text
        assert followup.inherit(dec("records", 0.2), text, h).intent == "records", text
    assert followup.is_elliptical("E a do dólar?") and followup.is_elliptical("TX1008?")


def test_human_request_is_never_overridden_or_inherited():
    assert followup.inherit(dec("human_request", 0.95), "E o pedido 1002?", TOPIC).intent == "human_request"
    h = hist(("Quero falar com um atendente", "human_request"))
    assert followup.inherit(dec("faq", 0.3), "E o pedido 1002?", h).intent == "faq"


def test_confirmation_and_empty_history_do_not_inherit():
    assert followup.inherit(dec("records", 0.2), "ok, obrigado", TOPIC).intent == "records"
    assert followup.inherit(dec("records", 0.2), "E o pedido 1002?", []).intent == "records"


def test_chain_of_followups_keeps_pointing_at_the_real_topic():
    h = TOPIC + hist(("E o pedido 1002?", "faq"))
    assert followup.topic_turn(h)[0].startswith("Meu pedido 1001")
    assert followup.inherit(dec("records"), "E o pedido 1003?", h).intent == "faq"


def test_inheritance_runs_inside_route_and_the_pipeline(monkeypatch):
    monkeypatch.setattr(router, "_route", lambda text, history: dec("records", 0.85))
    topic = "Meu pedido 1001 foi recusado e eu quero saber o que houve com ele"
    first = pipeline.handle(ChatRequest(message=topic), "u1")
    assert first.intent == "records"  # o stub do router manda records; o assunto fica gravado como records
    monkeypatch.setattr(router, "_route", lambda text, history: dec("faq", 0.85))
    second = pipeline.handle(ChatRequest(message="E o pedido 1002?", conversation_id=first.conversation_id), "u1")
    assert second.intent == "records" and second.route[1:] == ["records"]
