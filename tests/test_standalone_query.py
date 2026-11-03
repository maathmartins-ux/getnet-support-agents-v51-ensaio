"""Seguimento herda o assunto na busca do RAG; mensagem que se basta não é reescrita."""
from app import router


def hist(*texts):
    out = []
    for t in texts:
        out += [{"role": "user", "content": t, "intent": "faq"}, {"role": "assistant", "content": "resposta"}]
    return out


def test_followup_inherits_the_last_subject():
    h = hist("Como funciona o pedido de reembolso?")
    assert router.standalone_query("e o prazo?", h) == "Como funciona o pedido de reembolso?"
    assert router.standalone_query("E sobre cancelamento?", h) == "Como funciona o pedido de reembolso?"
    assert router.standalone_query("and how long does it take?", h) == "Como funciona o pedido de reembolso?"


def test_a_message_that_stands_alone_is_not_rewritten():
    h = hist("Como funciona o pedido de reembolso?")
    own = "Qual o prazo de entrega do pedido 1002 e como cancelar a compra de ontem?"
    assert router.standalone_query(own, h) is None


def test_single_message_conversation_is_never_rewritten():
    assert router.standalone_query("e o prazo?", []) is None


def test_confirmation_is_not_a_followup():
    assert router.standalone_query("ok, obrigado", hist("Como funciona o pedido de reembolso?")) is None


def test_followup_skips_other_followups_and_finds_the_real_subject():
    h = hist("Como funciona o pedido de reembolso?", "e o prazo?")
    assert router.standalone_query("e quanto custa?", h) == "Como funciona o pedido de reembolso?"
