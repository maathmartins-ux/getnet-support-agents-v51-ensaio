"""Idioma da resposta final: diretiva em todo pedido de agente e UMA reescrita quando a saída vem no idioma errado.

Medido com LLM real e sem esta regra: pergunta em inglês com um termo em português ("receivables advance
(antecipação)") e o câmbio do euro saíam em português; language_acc ao vivo 100% → 76,7%.
"""
from fakes import fake_llm, resp, text

from app import agents, grounding, pipeline, supervisor
from app.agents import AgentResult
from app.observability import METRICS
from app.schemas import ChatRequest

PT = "Com a antecipação de vendas você recebe antes o valor das vendas no crédito, à vista ou parceladas."
EN = "With sales advance you receive the money from your credit sales earlier, either upfront or in installments."
Q = "How does receivables advance (antecipação) work with Getnet?"


def _ask(monkeypatch, answer, evidence=("Antecipação de vendas: receba antes.",)):
    monkeypatch.setitem(supervisor.AGENTS, "faq", lambda ctx: AgentResult("faq", "ok", text=answer,
                                                                           evidence=list(evidence)))
    return pipeline.handle(ChatRequest(message=Q), "u1")


def test_wrong_language_detector():
    assert pipeline.wrong_language(PT, "en") and not pipeline.wrong_language(PT, "pt")
    assert pipeline.wrong_language(EN, "pt") and not pipeline.wrong_language(EN, "en")
    assert not pipeline.wrong_language("Ok, obrigado", "en")  # curta demais para decidir
    assert not pipeline.wrong_language("Your Get Smart (T1988A) is online and the signal is good.", "en")


def test_portuguese_answer_to_an_english_question_is_rewritten_once(monkeypatch):
    llm, msgs = fake_llm([resp("end_turn", text(EN))])
    monkeypatch.setattr(grounding, "get_llm", lambda role="agent": llm)
    before = METRICS.get("language_rewrites_total", outcome="accepted")
    r = _ask(monkeypatch, PT)
    assert r.answer == EN and r.language == "en"
    sent = msgs.sent[0]["messages"][0]["content"]
    assert len(msgs.sent) == 1 and "English" in sent  # uma reescrita só, no idioma pedido
    assert METRICS.get("language_rewrites_total", outcome="accepted") == before + 1


def test_a_rewrite_that_is_still_wrong_or_adds_a_number_is_rejected(monkeypatch):
    llm, _ = fake_llm([resp("end_turn", text(PT.replace("antes", "antes e em 3 dias")))])
    monkeypatch.setattr(grounding, "get_llm", lambda role="agent": llm)
    r = _ask(monkeypatch, PT)
    assert r.answer == PT  # mantém o original: a reescrita não pode piorar nem trazer número novo


def test_correct_language_costs_no_extra_call(monkeypatch):
    llm, msgs = fake_llm([])
    monkeypatch.setattr(grounding, "get_llm", lambda role="agent": llm)
    r = _ask(monkeypatch, EN)
    assert r.answer == EN and msgs.sent == []


def test_every_agent_request_ends_with_the_language_directive(monkeypatch):
    seen = []

    class Spy:
        enabled = True

        def complete(self, system, messages, **kw):
            seen.append(messages[-1]["content"])
            reply = "Delivery takes three to five business days after the order is shipped to you."
            return type("R", (), {"text": reply, "usage": None})()

    monkeypatch.setattr(agents, "get_llm", lambda role="agent": Spy())
    from app.agents import Context, faq_agent

    ctx = Context(text="Qual o prazo de entrega?", language="en", user_id="u1", conversation_id="c1",
                  intent="faq", history=[], user_summary="", conversation_digest="")
    faq_agent(ctx)
    assert seen and seen[-1].rstrip().endswith(grounding.DIRECTIVE["en"])
