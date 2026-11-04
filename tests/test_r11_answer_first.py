"""R11: "resposta primeiro" — a ressalva de abertura ("as fontes não dizem...") sai quando a frase seguinte, citada, já
responde e outra ausência fecha a resposta. Roda depois da última chamada ao LLM (pipeline.answer_first)."""
from app import pipeline, supervisor
from app.agents import AgentResult
from app.schemas import ChatRequest, Source
from evals.run_evals import opens_with_abstention

# Gravado no ensaio (rodada 10, evals/results/live_official.json, official-04, rodada 0 de 3): o único dos 626 textos
# gravados que a guarda muda. O eval marcava resolved=false só pela abertura.
OFFICIAL_04_RUN_0 = (
    "The sources don't say a bank account is mandatory. They do say Pix works with a checking, savings or prepaid "
    "payment account, at different banks [sup-duvidas-59]. Getnet also offers Get Conta, a free digital account for "
    "your business. With it you can send and receive money and sell through Pix [sup-duvidas-42].\n\n"
    "You receive Pix payments by generating a QR Code on the capture devices: physical terminals, TEF Auttar and "
    "Ecommerce [sup-duvidas-84].\n\n"
    "The sources don't state whether a specific account is required to receive Pix sales on Getnet. I can pass your "
    "question to a human agent if you'd like.")
OFFICIAL_04_IDS = {"sup-duvidas-59", "prod-pix-02", "sup-duvidas-84", "sup-duvidas-42", "prod-pix-01"}


def test_official_04_run_0_opens_with_the_cited_rule_and_keeps_the_closing_absence():
    out = pipeline.answer_first(OFFICIAL_04_RUN_0, OFFICIAL_04_IDS)
    assert out.startswith("Pix works with a checking, savings or prepaid payment account, at different banks "
                          "[sup-duvidas-59]. Getnet also offers Get Conta")  # "They do say" sem a frase de que dependia
    assert "The sources don't say a bank account is mandatory." not in out
    assert out.endswith("The sources don't state whether a specific account is required to receive Pix sales on "
                        "Getnet. I can pass your question to a human agent if you'd like.")  # o que falta continua
    assert opens_with_abstention(OFFICIAL_04_RUN_0) and not opens_with_abstention(out)
    assert out.count("[sup-") == OFFICIAL_04_RUN_0.count("[sup-")  # nenhuma frase citada saiu
    assert pipeline.answer_first(out, OFFICIAL_04_IDS) == out  # idempotente


def test_answer_without_a_cited_source_or_a_legit_refusal_never_changes():
    no_cite = ("As fontes não dizem se há taxa de adesão. Elas falam do prazo de entrega. "
               "As fontes não trazem o valor do frete.")
    assert pipeline.answer_first(no_cite, {"faq-entrega"}) == no_cite
    for refusal in (pipeline.NO_ANSWER["pt"], pipeline.NO_ANSWER["en"],
                    "The sources don't cover the Diamond plan. I can hand this to a human agent. Do you want me to?"):
        assert pipeline.answer_first(refusal, {"faq-entrega"}) == refusal
    cited_elsewhere = ("The sources don't say X. They do say Y [outro-id]. The sources don't cover Z.")
    assert pipeline.answer_first(cited_elsewhere, set()) == cited_elsewhere  # sem fonte do turno: nada a fazer
    assert pipeline.answer_first(cited_elsewhere, {"faq-entrega"}) == cited_elsewhere  # citação que não é do turno


def test_the_only_absence_is_the_direct_answer_and_stays_first():
    # memory-15 (ensaio): "conecta por Wi-Fi?" — não saber É a resposta; a frase seguinte depende dela ("They")
    text = ("The sources don't say whether the Get Smart connects over Wi-Fi. They describe it as an Android card "
            "machine that you can integrate with your business system [sup-a][sup-b], but they don't list its "
            "connection types.\n\nI can pass your question to a human agent if you want a definite answer.")
    assert pipeline.answer_first(text, {"sup-a", "sup-b"}) == text


def test_a_hedge_or_a_passage_caveat_keeps_the_opening():
    hedge = ("Não encontrei nas fontes nenhuma forma de ajustar o antifraude. Só achei a menção de que o link conta "
             "com o antifraude [d1]. As fontes não explicam como regular o bloqueio.")
    assert pipeline.answer_first(hedge, {"d1"}) == hedge  # "só achei" continua a 1ª: tirá-la deixaria a ressalva solta
    lead_in = ("Não encontrei a taxa de débito da maquininha nas fontes. O que as fontes trazem é isto:\n"
               "- débito de 1,89% no plano de 2 dias [d1].\n\nAs fontes não citam a maquininha nessa tabela.")
    assert pipeline.answer_first(lead_in, {"d1"}) == lead_in  # a 2ª frase não cita: é abertura da lista
    caveat = ("As fontes não trazem o prazo de um plano chamado padrão. Num trecho, o crédito parcelado tem "
              "recebimento em 31 dias [d4]. O trecho não diz a que plano essa regra pertence.")
    assert pipeline.answer_first(caveat, {"d4"}) == caveat  # ressalva de UM trecho não repete o que falta
    mixed = ("The passages don't name a single best machine, but they do describe features [d4]. One is described "
             "as the best to start [d4]. The sources don't say which model suits outdoor use.")
    assert pipeline.answer_first(mixed, {"d4"}) == mixed  # 1ª com conteúdo ("but they do") não é só ressalva


def test_a_records_answer_that_opens_with_not_found_is_not_a_source_absence():
    text = ("Não achei nenhum depósito de vendas de sexta na sua agenda dos últimos 7 dias. As vendas que aparecem "
            "são de 01/11 [d1]. As fontes não informam a taxa da antecipação manual pelo app.")
    assert pipeline.answer_first(text, {"d1"}) == text


def test_hedge_opening_goes_away_when_the_closing_says_what_is_missing():
    text = ("As passagens trazem só parte do procedimento de conexão. Para o chip, o passo a passo é este [d2]:\n"
            "- Com a máquina desligada, abra a tampa.\n\nAs fontes não trazem os passos para configurar o Wi-Fi.")
    assert pipeline.answer_first(text, {"d2"}) == (
        "Para o chip, o passo a passo é este [d2]:\n- Com a máquina desligada, abra a tampa.\n\n"
        "As fontes não trazem os passos para configurar o Wi-Fi.")


def test_the_guard_runs_on_the_final_answer_of_the_turn(monkeypatch):
    troca = Source(id="faq-troca", title="Troca e devolução", url="https://example.com/faq#troca")
    evidence = ["Troca e devolução: Você pode solicitar troca ou devolução em até 7 dias corridos após o recebimento, "
                "com o produto sem uso e na embalagem original."]
    text = ("As fontes não dizem se a troca tem custo. Elas dizem que a troca ou devolução pode ser pedida em até 7 "
            "dias corridos após o recebimento [faq-troca]. As fontes não trazem o custo do frete da troca.")
    monkeypatch.setitem(supervisor.AGENTS, "faq", lambda ctx: AgentResult("faq", "ok", text=text, sources=[troca],
                                                                          evidence=evidence))
    r = pipeline.handle(ChatRequest(message="Posso trocar um livro?"), "u1")
    assert r.answer == ("A troca ou devolução pode ser pedida em até 7 dias corridos após o recebimento [faq-troca]. "
                        "As fontes não trazem o custo do frete da troca.")
