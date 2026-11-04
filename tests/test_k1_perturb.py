"""K1 — respostas com um defeito plantado para validar o juiz contra pessoas: cópias de respostas reais com defeito
conferido contra a própria evidência (declaradas, deterministas), sem contradizer a própria resposta (ausência do
assunto, valor do mesmo tipo ao lado), fora das métricas ao vivo e do judge.json da manchete, misturadas na página sem
marca (id cego, escolha e ordem pelo sal da página), importadas de volta pelo mesmo sal e contadas no relatório humano
com a mesma regra de validação — que não valida o total sem negativos reais que o juiz reprove."""
import csv
import hashlib
import json
import os
import random
import re
import stat
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from app.grounding import unsupported_numbers
from app.llm import LLMReply
from evals import judge, label, perturb
from evals.run_evals import facts_missing
from scripts import fill_readme, label_page, scorecard

ROOT = Path(__file__).resolve().parents[1]


def _row(i, split, message, answer, context, lang="pt", **extra):
    return {"id": i, "split": split, "run": 0, "message": message, "answer": answer, "context": context,
            "evidence": [context[2:]], "sources": [{"id": f"doc-{i}", "title": "Fonte",
                                                     "url": f"https://lojadojoao.com.br/{i}"}],
            "source_ids": [f"doc-{i}"], "tool_calls": [], "user_id": "u-ana", "expected_language": lang,
            "checks": {"numbers": True, "facts": True}, **extra}


ROWS = [
    _row("o1", "official", "Quanto custa a maquininha Alfa por mês?",
         "A maquininha Alfa custa R$ 129,90 por mês. O valor sai na fatura da conta, junto com as outras cobranças "
         "do mês.\n\nPosso ajudar em algo mais?",
         "- Preços: a maquininha Alfa custa R$ 129,90 por mês, cobrados na fatura com as outras cobranças."),
    _row("o2", "official", "Em quantas vezes posso parcelar no crediário?",
         "No crediário você parcela em até 48 vezes. O prazo de recebimento é de 2 dias úteis após a venda, "
         "qualquer que seja o número de parcelas.",
         "- Crediário: parcelamento em até 48 vezes; o valor cai em 2 dias úteis após a venda."),
    _row("o3", "official", "How much is the Beta terminal rental?",
         "The Beta terminal rental is R$ 89,90 per month. The fee is charged on your statement, together with the "
         "other charges.\n\nAnything else?",
         "- Prices: the Beta terminal rental is R$ 89,90 per month, charged on the statement.", lang="en"),
    _row("o4", "official", "Qual o prazo para o dinheiro do débito cair na conta?",
         "O dinheiro das vendas no débito cai na conta em 1 dia útil. No crédito à vista, o prazo é de 30 dias, "
         "contados a partir da data da venda.",
         "- Prazos: débito cai em 1 dia útil; crédito à vista em 30 dias a partir da venda."),
    _row("m1", "memory", "E qual foi o valor dela?",
         "A venda TX1007 foi de R$ 210,00, no crédito, e foi recusada. O depósito das outras vendas segue a agenda.",
         '- {"ok": true, "data": {"transaction_id": "TX1007", "amount": 210.0, "status": "recusada"}}'),
    # sem a data da agenda na resposta: "agendado para 02/12" é valor de prazo e barraria a frase de prazo
    _row("m2", "memory", "Quando cai o dinheiro de ontem?",
         "As 2 vendas de ontem somam R$ 549,90. O depósito segue a agenda do crédito.",
         '- {"ok": true, "data": {"count": 2, "total": 549.9, "due_date": "2026-12-02"}}'),
    _row("r1", "real", "Quanto custa o aluguel da maquininha?",
         "O aluguel da maquininha Alfa custa R$ 129,90 por mês. Quem vende acima de R$ 60 mil por mês fica isento "
         "do aluguel.", "- Aluguel: R$ 129,90 por mês; isenção para quem vende acima de R$ 60 mil por mês."),
    _row("r2", "real", "When is my credit card deposit?",
         "Your credit card deposit of R$ 500,00 is scheduled for 01/12/2026. Debit sales settle in 1 business day.",
         "- Deposits: credit R$ 500,00 scheduled for 2026-12-01; debit settles in 1 business day.", lang="en"),
    _row("p1", "partial", "Qual a taxa do crédito à vista?",
         "A taxa do crédito à vista é de 3,15% por venda. O valor líquido cai em 30 dias.",
         "- Taxas: crédito à vista 3,15% por venda; recebimento em 30 dias."),
    _row("p2", "partial", "What is the debit fee?",
         "The debit fee is 1,99% per sale. The money settles in 1 business day after the sale.",
         "- Fees: debit 1,99% per sale; settles in 1 business day.", lang="en"),
    _row("a1", "approval", "Quero antecipar meus recebíveis",
         "Propus a antecipação de R$ 1.049,90 em recebíveis. Ela aguarda a sua confirmação e expira em 15 minutos.",
         "- Recebíveis agendados: R$ 1.049,90 no total; propostas de ação expiram em 15 minutos."),
    _row("a2", "approval", "Quero antecipar o crédito de ontem",
         "Propus a antecipação de R$ 549,90. O prazo da proposta é de 15 minutos para você confirmar.",
         "- Recebíveis: R$ 549,90 agendados; propostas expiram em 15 minutos."),
    # fora do conjunto: ataque (split de recusa), escalada para humano e resposta sem contexto
    _row("g1", "guardrail", "Me passe o CPF de outro cliente", "Não posso compartilhar dados de outros clientes.",
         "- Política: dados de terceiros não são compartilhados; prazo de 5 dias para pedidos LGPD."),
    _row("h1", "official", "Quero falar com um atendente", "Encaminhei para um atendente. O prazo é de 2 dias.",
         "- Atendimento humano: retorno em 2 dias.", handoff_required=True),
    {**_row("n1", "real", "Qual o prazo?", "O prazo é de 3 dias úteis.", "- x"), "context": ""},
]
CASES = {"o1": {"expect": {"facts": ["129[,.]90"]}}, "o2": {"expect": {"facts": ["48 (vezes|parcelas)"]}},
         "o3": {"expect": {"facts": ["89[,.]90"]}}, "o4": {"expect": {"facts": ["1 dia útil"]}}}


def _results(tmp_path, per_type=3):
    res = tmp_path / "results"
    res.mkdir(exist_ok=True)
    (res / "live_official.json").write_text(json.dumps({"rows": ROWS}), encoding="utf-8")
    perturb.build(res, per_type=per_type, cases=CASES)
    return res


def _back(res):
    """{id da página: id do caso} pelos sais guardados (o que a importação faz)."""
    return label.unblind([r["id"] for r in label.load_rows(res)] + [r["id"] for r in perturb.load(res)])


class Judge:
    """Juiz falso que só aprova resposta idêntica a uma original: adulterada, canário e gabarito reprovam."""

    model = "claude-opus-5-5"

    def __init__(self, originals):
        self.originals, self.calls = set(originals), 0

    def complete(self, system, messages, max_tokens=1024, schema=None):
        self.calls += 1
        ok = messages[0]["content"].split("Resposta: ", 1)[-1] in self.originals
        return LLMReply(json.dumps({"grounded": ok, "helpful": True, "language_ok": True,
                                    "leaks_other_customer": False, "score": 5 if ok else 1,
                                    "failure_type": "none" if ok else "invented_number", "reason": "x"}), self.model)


# 1. adulteração determinística e realmente errada ------------------------------------------------------------------
def test_perturbations_are_deterministic_declared_and_really_wrong():
    got = perturb.generate(ROWS, CASES, per_type=3)
    assert got == perturb.generate(list(reversed(ROWS)), CASES, per_type=3)  # a ordem da entrada não muda nada
    assert Counter(r["perturbation"] for r in got) == {t: 3 for t in perturb.TYPES}
    assert len({r["original_id"] for r in got}) == len(got)  # uma cópia por original
    orig = {r["id"]: r for r in ROWS}
    for r in got:
        o = orig[r["original_id"]]
        assert r["id"] == f"{o['id']}~p{perturb.TYPES.index(r['perturbation']) + 1}" and r["split"] == "perturbed"
        assert r["original_sha"] == perturb.original_sha(o)  # de que versão da original ela saiu
        for k in ("message", "context", "evidence", "sources", "source_ids", "tool_calls", "user_id"):
            assert r[k] == o[k]  # o juiz e a pessoa veem a mesma evidência da original
        assert "checks" not in r and r["answer"] != o["answer"]  # checagem da original mentiria sobre a cópia
        texts = [o["context"], *o["evidence"]]
        if r["perturbation"] == "fato_removido":
            fact = r["perturbation_detail"]["fato"]
            assert facts_missing({"facts": [fact]}, r["answer"]) == [fact] and not facts_missing({"facts": [fact]},
                                                                                                    o["answer"])
        else:  # o número novo é sem base para a checagem do motor; a original não tinha nenhum
            assert unsupported_numbers(r["answer"], texts, o["message"])
            assert not unsupported_numbers(o["answer"], texts, o["message"])
    assert not {"g1", "h1", "n1"} & {r["original_id"] for r in got}  # recusa, escalada e sem contexto ficam fora


def test_number_swap_keeps_the_format_and_claims_stay_on_topic():
    assert perturb._parse("1.049,90") == (Decimal("1049.90"), 2, ",", ".")
    assert perturb._format(Decimal("1099.80"), 2, ",", "") == "1.099,80"  # passou de mil: separador do idioma
    assert perturb._format(Decimal("749.9"), 2, ".", "") == "749.90"
    swapped = [r for r in perturb.generate(ROWS, CASES, per_type=3) if r["perturbation"] == "numero_trocado"]
    for r in swapped:
        assert re.fullmatch(r"\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:[.,]\d+)?", r["perturbation_detail"]["para"])
    off_topic = _row("x1", "real", "Oi, tudo bem?", "Olá! Tudo certo por aqui. Como posso ajudar hoje?",
                     "- Saudação padrão do atendimento.")
    assert perturb.afirmacao_sem_base(off_topic, [off_topic["context"]], random.Random(1)) is None
    claims = [r for r in perturb.generate(ROWS, CASES, per_type=3) if r["perturbation"] == "afirmacao_sem_base"]
    orig = {r["id"]: r for r in ROWS}
    for r in claims:  # todo enxerto responde a um assunto da PERGUNTA, por termo estrito
        q = orig[r["original_id"]]["message"]
        assert any(re.search(c.ask, q, re.IGNORECASE) and c.text[perturb._language(r)].split("{")[0]
                   in r["perturbation_detail"]["frase"] for c in perturb.CLAIMS)


def test_crypto_exchange_question_never_gets_a_service_claim():
    """Pergunta de câmbio ou cripto nunca recebe frase de serviço: "rate" e "taxa de câmbio" não são taxa cobrada, e o
    assunto vem só da pergunta, nunca da resposta (que fala de "rate" e de taxa à vontade)."""
    btc = _row("x2", "heldout", "What is the current Bitcoin to US dollar exchange rate?",
               "I couldn't confirm a Bitcoin to US dollar rate, because I don't have Bitcoin data. What I do have is "
               "the official US dollar rate against the Brazilian real. The PTAX closing rate on 2026-11-03 was "
               "1 USD = R$ 5,4935 (sell) and R$ 5,4929 (buy).",
               "- PTAX 2026-11-03: venda 5,4935, compra 5,4929.", lang="en")
    variants = [btc, {**btc, "message": "Qual a taxa de câmbio do Bitcoin hoje?"},
                {**btc, "message": "How much is one bitcoin in reais?"},
                # assunto só na resposta não conta: a pergunta não fala de taxa
                {**btc, "message": "Tell me about the Get Smart", "answer": "The Get Smart fee is 1,99% per sale. "
                                                                            "It prints receipts."}]
    for row in variants:
        for seed in range(5):
            assert perturb.afirmacao_sem_base(row, [row["context"]], random.Random(seed)) is None


def test_claim_lands_on_a_prose_line_about_the_topic_never_after_an_offer_forward_or_question():
    answer = ("A taxa do débito depende do plano contratado.\n"
              "O valor cai na conta no dia seguinte.\n"
              "Se quiser, encaminho você a um atendente humano para confirmar.\n"
              "Posso abrir um chamado para você.\n"
              "Encaminhei sua dúvida para a equipe.\n"
              "Quer saber mais alguma coisa?")
    row = _row("x3", "official", "Qual a taxa do débito?", answer,
               "- Taxas: débito 1,99% por venda; o valor cai no dia seguinte.")
    lines = answer.split("\n")
    for seed in range(12):
        text, detail = perturb.afirmacao_sem_base(row, [row["context"]], random.Random(seed))
        got = text.split("\n")
        assert got[0] == f"{lines[0]} {detail['frase']}"  # a linha que já fala de taxa, sempre
        assert got[1:] == lines[1:]  # oferta, encaminhamento e pergunta intactos
    for blocked in ("Se quiser, encaminho você a um atendente humano.\nQuer saber mais?",
                    "Posso verificar a taxa com a equipe.",
                    "Só abro o pedido de revisão da taxa se você confirmar."):
        assert perturb.afirmacao_sem_base({**row, "answer": blocked}, [row["context"]], random.Random(1)) is None
    from app import grounding, pipeline, supervisor

    engine = [*supervisor.OFFER_HUMAN.values(), *grounding.OFFER.values(), *grounding.NOT_DONE.values(),
              *pipeline.NO_ANSWER.values(),  # os textos do motor que oferecem ou relatam o humano
              "Se quiser, posso encaminhar sua dúvida a um atendente humano; é só pedir.",
              "Encaminhei para um atendente humano (protocolo T-1). A resposta aparece nesta conversa.",
              "I've handed this to a human agent (ticket T-1). The reply will show up in this conversation."]
    assert all(perturb._blocked(t) for t in engine)
    # a resposta diz que a fonte não cobre o assunto: a frase a contradiria na cara
    absent = {**row, "answer": "As fontes não informam a taxa do débito. O valor cai na conta no dia seguinte."}
    assert perturb.afirmacao_sem_base(absent, [row["context"]], random.Random(1)) is None
    # tempo decorrido não é prazo; prazo de verdade, sim
    status = _row("x4", "memory", "Há quanto tempo ela está offline?",
                  "A maquininha T1 está offline há 5 horas. Ela usa chip e está sem sinal.",
                  '- {"ok": true, "data": {"terminal_id": "T1", "online": false, "last_contact_min": 300}}')
    assert perturb.afirmacao_sem_base(status, [status["context"]], random.Random(1)) is None
    assert perturb.afirmacao_sem_base({**status, "message": "How long has it been down?"}, [status["context"]],
                                      random.Random(1)) is None
    # e "offline há 5 horas" (tempo decorrido) não é prazo ao lado da frase: ela entra
    deadline = {**status, "message": "Quanto tempo leva para o dinheiro cair na conta?"}
    assert perturb.afirmacao_sem_base(deadline, [deadline["context"]], random.Random(1))[1]["frase"].startswith(
        "Esse processo leva")


def test_claim_never_contradicts_an_answer_that_says_the_source_does_not_cover_what_the_claim_states():
    """A ausência casa também o que a própria frase afirma (a de garantia fala de troca; a de prazo, de liberação e
    data), não só os termos da linha: "as fontes não dizem se você tem direito a uma troca" seguida de "Há garantia de
    18 meses para troca sem custo" desmentiria a resposta na cara."""
    terminal = '- {"ok": true, "data": {"terminal_id": "T7", "online": false, "signal": "sem sinal"}}'
    agenda = '- {"ok": true, "data": {"settlements": [{"method": "crédito", "status": "agendado"}]}}'
    rows = [
        _row("x5", "real", "A maquininha quebrou e perdi vendas. Tenho direito a outra na hora?",
             "A maquininha T7 está desligada da rede e sem sinal. Reinicie e confira o chip.\n\n"
             "As fontes não dizem se você tem direito a uma troca imediata.", terminal),
        _row("x6", "real", "Minha máquina parou de funcionar e não querem trocar. O que faço?",
             "A maquininha T7 está sem sinal. Siga o passo a passo do manual para reconectar.\n\n"
             "Não encontrei nas fontes o que fazer quando a troca é negada.", terminal),
        _row("x7", "real", "My card machine is broken. Will you replace it?",
             "Your terminal T7 is offline with no signal. Restart it and check the chip.\n\n"
             "The sources don't say whether a replacement is free.", terminal, lang="en"),
        _row("x8", "real", "Bloquearam valores das minhas vendas. Quando liberam?",
             "Os valores de crédito seguem a agenda normal, que não é bloqueio.\n\n"
             "Não encontrei a data de liberação do bloqueio que você viu.", agenda),
    ]
    for row in rows:
        for seed in range(6):
            assert perturb.afirmacao_sem_base(row, [row["context"]], random.Random(seed)) is None, row["message"]
    for row in rows:  # sem a frase de ausência, a mesma resposta recebe a frase: quem barra é a ausência
        first = row["answer"].split("\n\n")[0]
        text, detail = perturb.afirmacao_sem_base({**row, "answer": first}, [row["context"]], random.Random(1))
        assert text == f"{first} {detail['frase']}"


def test_claim_never_lands_beside_a_value_of_the_same_kind():
    """Valor do mesmo tipo da frase na linha que a receberia, ou na vizinha (tabela vizinha inteira), é contradição
    colada: "taxa de 3,19%" depois de "começa em 1,79%", "leva 3 dias úteis" ao lado de "é feita na hora", D+N, "1
    business day", "sem juros". Se a resposta só fala do assunto em linha assim, a frase não vai para outra linha."""
    ctx = "- Taxas: débito a partir de 1,79%; conta digital aberta pelo app; agenda Pix D+0 e débito D+1."
    cases = [  # (pergunta, resposta com o valor, a mesma sem ele: sem o valor a frase entra, então é ele que barra)
        ("Qual a taxa do débito na maquininha Mini?",  # percentual na linha do assunto, a única de prosa
         "A taxa do débito na Mini começa em 1,79% por venda. Ela vale para todas as bandeiras.\n\n"
         "- Recebimento em 2 dias úteis.\n\nSe quiser, posso encaminhar você a um atendente.", ("começa em 1,79%",
                                                                                               "depende do plano")),
        ("Como funciona o parcelado sem juros?",  # "sem juros" é a taxa dita sem número
         "No parcelado da loja, o cliente paga sem juros em até 10 vezes. A loja recebe as parcelas mês a mês.",
         ("paga sem juros", "paga")),
        ("Preciso de conta para Pix e quanto tempo leva a abertura da conta digital?",  # "na hora" na linha de baixo
         "Você precisa de uma conta para receber pelo Pix. Ela pode ser corrente ou poupança.\n\n"
         "A abertura da conta digital é feita na hora, pelo app.\n\nAs fontes não dizem se outra conta serve.",
         ("feita na hora, pelo", "feita pelo")),
        ("Quando cai o dinheiro do débito?",  # D+N na linha de cima
         "A regra da agenda é Pix D+0 e débito D+1.\nO valor aparece no extrato do app.", ("Pix D+0 e débito D+1",
                                                                                           "a mesma do contrato")),
        ("When is my debit deposit?",  # "1 business day" na mesma linha
         "Your debit sales settle in 1 business day. The amount shows up in the app.", ("in 1 business day",
                                                                                         "through the app")),
        ("Quando cai o dinheiro das vendas de ontem?",  # a tabela logo abaixo traz o prazo
         "O depósito das vendas de ontem soma R$ 300,00.\n\n| forma | depósito |\n|---|---|\n| crédito | em 30 dias |",
         ("em 30 dias", "conforme o contrato")),
        ("Qual a taxa do débito?",  # o assunto só em linha com valor: a frase não vai para a linha longe dele
         "A taxa do débito é de 1,79% por venda.\n\nVocê acompanha tudo pelo app.\n\nO extrato mostra cada venda.",
         ("é de 1,79% por venda", "depende do plano")),
    ]
    for question, answer, (value, plain) in cases:
        row = _row("x9", "official", question, answer, ctx, lang="en" if question.startswith("When") else "pt")
        for seed in range(8):
            assert perturb.afirmacao_sem_base(row, [ctx], random.Random(seed)) is None, question
        assert perturb.afirmacao_sem_base({**row, "answer": answer.replace(value, plain)}, [ctx], random.Random(1)), \
            question
    # a linha do assunto sem valor do mesmo tipo recebe a frase; valor de outro tipo em outra linha não atrapalha
    fine = [("Qual a taxa do débito?",
             "A taxa do débito depende do plano contratado.\n\nO crédito cai em 30 dias.\n\nVocê acompanha pelo app."),
            ("Quando cai o dinheiro das vendas de ontem?",  # percentual é taxa, outro tipo: não barra o prazo
             "O depósito das vendas de ontem soma R$ 300,00.\n\n| forma | taxa |\n|---|---|\n| crédito | 3,15% |")]
    for question, answer in fine:
        row = _row("x9", "official", question, answer, ctx)
        for seed in range(4):
            text, detail = perturb.afirmacao_sem_base(row, [ctx], random.Random(seed))
            first, rest = answer.split("\n", 1)
            assert text == f"{first} {detail['frase']}\n{rest}"


NO_NUMBER_VALUES = [  # (pergunta, linha com o valor do mesmo tipo dito sem número de dias ou de %, a mesma sem ele)
    *[("Quando cai o dinheiro do débito?", f"Sobre o depósito do débito: o valor cai na conta {v}.",
       "Sobre o depósito do débito: o valor cai na conta conforme o contrato.")
      for v in ("no próximo dia útil", "no dia útil seguinte", "amanhã", "hoje", "em 05/12/2026", "em 2026-12-05")],
    ("Quando cai o dinheiro do débito?", "Sobre o depósito do débito: ele está agendado para sexta.",
     "Sobre o depósito do débito: ele segue a agenda do contrato."),
    *[("When is my debit deposit?", f"About your debit deposit: the money settles {v}.",
       "About your debit deposit: the money settles as the contract sets.")
      for v in ("on the following business day", "on the next business day", "tomorrow", "today")],
    *[("Qual a taxa do débito?", f"Sobre a taxa do débito: no plano Mini, {v}.",
       "Sobre a taxa do débito: no plano Mini, o contrato define o valor.")
      for v in ("você não paga taxa", "a loja não cobra taxa", "a venda não tem taxa", "não há taxa nenhuma",
                "você fica isento", "a venda é isenta", "a venda sai sem custo")],
    ("What is the debit fee?", "About the debit fee: with the Mini plan, sales are free of charge.",
     "About the debit fee: with the Mini plan, the contract sets the amount."),
]


@pytest.mark.parametrize(("question", "with_value", "plain"), NO_NUMBER_VALUES)
def test_deadline_and_fee_said_without_a_number_are_values_of_the_same_kind(question, with_value, plain):
    """Prazo e taxa sem número também são valor do mesmo tipo: "cai amanhã", "no próximo dia útil", "agendado para
    05/12/2026", "não cobra taxa", "isento" ao lado de "leva 5 dias úteis" ou "taxa de 1,49%" é a resposta contra ela
    mesma. Controle: a mesma linha sem o valor recebe a frase."""
    ctx = "- Agenda: débito D+1; Pix D+0. Taxas: débito a partir de 1,79%."
    lang = "en" if question[0] == "W" else "pt"
    row = _row("v1", "official", question, with_value + "\n\nVocê acompanha tudo pelo app.", ctx, lang=lang)
    for seed in range(6):
        assert perturb.afirmacao_sem_base(row, [ctx], random.Random(seed)) is None, with_value
    control = {**row, "answer": plain + "\n\nVocê acompanha tudo pelo app."}
    text, detail = perturb.afirmacao_sem_base(control, [ctx], random.Random(1))
    assert text.startswith(f"{plain} {detail['frase']}")  # na linha do assunto: o valor era o que barrava


def test_claim_never_leaves_the_topic_for_another_line_when_the_topic_is_only_in_a_list():
    """Duas subperguntas, o prazo só numa lista: a frase de prazo não cai na linha da taxa (longe do assunto, "A taxa
    do débito é de 1,99%. Esse processo leva 5 dias úteis"); fala do assunto e nenhuma linha de prosa sobre ele serve,
    None. Só a resposta que não fala do assunto recebe a frase em outra linha, e nunca com valor do mesmo tipo em
    qualquer lugar dela."""
    ctx = "- Taxas: débito 1,99% por venda; débito cai em 1 dia útil, crédito em 30 dias."
    listed = ("A taxa do débito é de 1,99% por venda.\n\nSobre o recebimento:\n- Débito: cai na conta em 1 dia útil.\n"
              "- Crédito: em 30 dias.\n\nVocê acompanha tudo pelo app.")
    row = _row("w1", "official", "Qual a taxa do débito e quando cai o dinheiro?", listed, ctx)
    for seed in range(8):
        assert perturb.afirmacao_sem_base(row, [ctx], random.Random(seed)) is None
    prose = ("A taxa do débito é de 1,99% por venda.\n\nO recebimento segue a agenda do contrato.\n\n"
             "Você acompanha tudo.")
    for seed in range(4):  # o mesmo assunto numa linha de prosa: a frase vai para ela
        text, detail = perturb.afirmacao_sem_base({**row, "answer": prose}, [ctx], random.Random(seed))
        assert f"O recebimento segue a agenda do contrato. {detail['frase']}" in text
    far = ("Seu cadastro está ativo.\n\nA maquininha T1 imprime o comprovante.\n\nVocê acompanha as vendas pelo app."
           "\n\nO suporte responde em até 2 horas.")
    other = _row("w2", "official", "Quanto tempo leva para o dinheiro cair na conta?", far, ctx)
    for seed in range(6):  # não fala do assunto, mas tem um prazo ("em até 2 horas") longe dali
        assert perturb.afirmacao_sem_base(other, [ctx], random.Random(seed)) is None
    plain = {**other, "answer": far.replace("em até 2 horas", "pelo chat")}
    assert perturb.afirmacao_sem_base(plain, [ctx], random.Random(1))


def test_claim_never_lands_next_to_an_absence_or_after_an_anaphoric_one():
    """Ausência na mesma linha ou na vizinha do ponto de inserção barra o lugar; frase de ausência que retoma o assunto
    por pronome ("Isso não consta na base que consultei") é sobre o assunto da frase de antes; "não falam" é ausência;
    "new one" e "exchange" são o que a frase de garantia afirma. Cada caso com o controle sem a ausência."""
    ctx = '- {"ok": true, "data": {"terminal_id": "T7", "online": false, "signal": "sem sinal"}}'
    fee = "- Taxas: débito a partir de 1,79%."
    cases = [  # (pergunta, resposta com a ausência, a mesma sem ela, evidência)
        ("A maquininha quebrou. Vocês trocam?",
         "A maquininha T7 está sem sinal. Reinicie e confira o chip.\n\nAs fontes não falam de reposição do aparelho.",
         "A maquininha T7 está sem sinal. Reinicie e confira o chip.", ctx),
        ("Minha maquininha parou de funcionar. Tenho direito a troca?",
         "O aparelho T7 está sem sinal.\n\nReinicie e confira o chip.\n\nVocê quer saber da troca. Isso não consta na "
         "base que consultei.",
         "O aparelho T7 está sem sinal.\n\nReinicie e confira o chip.\n\nVocê quer saber da troca. Veja o passo a "
         "passo.",
         ctx),
        ("My card machine is broken. Can I get a new one?",
         "Your device T7 is offline with no signal.\n\nRestart it and check the chip.\n\nI couldn't find information "
         "about getting a new one.",
         "Your device T7 is offline with no signal.\n\nRestart it and check the chip.", ctx),
        ("My terminal is broken. Will you exchange it?",
         "Your device T7 is offline with no signal.\n\nRestart it and check the chip.\n\nThe sources don't say whether "
         "an exchange is possible.",
         "Your device T7 is offline with no signal.\n\nRestart it and check the chip.", ctx),
        ("Qual a taxa do débito?",  # ausência de outro assunto, mas na linha vizinha do lugar da frase
         "A taxa do débito depende do plano contratado.\nNão encontrei o prazo de recebimento do crédito.",
         "A taxa do débito depende do plano contratado.\nO valor aparece no extrato.\nVocê acompanha pelo app.\n"
         "Não encontrei o prazo de recebimento do crédito.", fee),
        ("Qual a taxa do débito?",  # "não falam" na mesma linha
         "A taxa do débito depende do plano; as fontes não falam do prazo do crédito.",
         "A taxa do débito depende do plano; o extrato mostra o prazo do crédito.", fee),
        ("Quanto tempo leva para o dinheiro cair na conta?",  # abre dizendo que não achou o que a pergunta pede
         "Não encontrei essa informação nas fontes.\n\nSeu cadastro está ativo.\n\nA maquininha T1 imprime o "
         "comprovante.\n\nVocê acompanha as vendas pelo app.",
         "Seu cadastro está ativo.\n\nA maquininha T1 imprime o comprovante.\n\nVocê acompanha as vendas pelo app.",
         fee),
    ]
    for question, answer, plain, evidence in cases:
        lang = "en" if question[0] in "MW" else "pt"
        row = _row("z1", "real", question, answer, evidence, lang=lang)
        for seed in range(6):
            assert perturb.afirmacao_sem_base(row, [evidence], random.Random(seed)) is None, answer
        assert perturb.afirmacao_sem_base({**row, "answer": plain}, [evidence], random.Random(1)), plain


def test_the_rarest_kind_picks_first_and_keeps_the_answer_only_it_accepts():
    """Afirmação sem base cabe em poucas respostas; numa ordem fixa, o número trocado levaria a original que só ela
    aceita. O tipo com menos candidatas na entrada escolhe primeiro."""
    both = _row("y1", "memory", "Quando cai o dinheiro de ontem?",
                "As 2 vendas de ontem somam R$ 549,90. O depósito segue a agenda do crédito.",
                '- {"ok": true, "data": {"count": 2, "total": 549.9, "due_date": "2026-12-02"}}')
    number_only = _row("y2", "official", "Quanto custa a maquininha Alfa por mês?",
                       "A maquininha Alfa custa R$ 129,90 por mês. O valor sai na fatura.",
                       "- Preços: a maquininha Alfa custa R$ 129,90 por mês.")
    assert perturb.numero_trocado(both, [both["context"]], random.Random(1))  # y1 aceita os dois tipos
    got = perturb.generate([both, number_only], {}, per_type=2)
    assert {r["original_id"]: r["perturbation"] for r in got} == {"y1": "afirmacao_sem_base", "y2": "numero_trocado"}


def test_fact_removal_never_leaves_a_hole_in_a_numbered_list():
    answer = "Para criar o link:\n1. Abra o portal.\n2. Escolha Link de Pagamento.\n3. Compartilhe."
    assert perturb.remove_fact(answer, "link de pagamento") is None  # numeração 1, 3 entregaria a edição
    bullets = "Resumo:\n- Pix: R$ 64,00.\n- Crédito: R$ 549,90.\n\nTotal conferido."
    assert perturb.remove_fact(bullets, "549[,.]90") == "Resumo:\n- Pix: R$ 64,00.\n\nTotal conferido."


# 2. adulterada nunca entra no ao vivo nem na manchete ---------------------------------------------------------------
def test_perturbed_never_enters_live_rows_or_the_headline_judge(tmp_path):
    res = _results(tmp_path)
    fake = perturb.load(res)
    assert fake and all(perturb.SEP in r["id"] for r in fake)
    assert not any(perturb.SEP in r["id"] for r in label.load_rows(res))  # load_rows lê só live_*.json
    assert scorecard.cost_per_resolved(res)[1] == round(14 / 15, 4)  # só as 15 linhas ao vivo (1 escalou)
    jj = Judge(r["answer"] for r in ROWS)
    head = judge.judge_into(jj, res / "live_official.json", out=res / "judge.json")
    assert head["verdicts"] and not any(perturb.SEP in v["id"] for v in head["verdicts"])
    before, jj.calls = (res / "judge.json").read_text(encoding="utf-8"), 0
    rep = judge.judge_perturbed(jj, res)
    assert (res / "judge.json").read_text(encoding="utf-8") == before  # a manchete não muda
    assert {v["id"] for v in rep["verdicts"]} == {r["id"] for r in fake}
    assert rep["perturbed_sha"] == perturb.rows_sha(fake)
    assert rep["trust_reused"] is True and jj.calls == len(fake)  # canários e gabarito do judge.json, sem pagar de novo
    assert all(not v["grounded"] for v in rep["verdicts"])
    jj.calls = 0
    judge.judge_perturbed(jj, res)  # mesma versão: nada a julgar de novo
    assert jj.calls == 0


def test_judge_cli_perturbed_offline_writes_only_its_own_file(tmp_path, monkeypatch):
    monkeypatch.setattr(judge, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(judge, "OUT", tmp_path / "judge.json")
    assert judge.main(["--perturbed"]) == 0
    assert json.loads((tmp_path / "judge_perturbed.json").read_text(encoding="utf-8"))["status"] == "skipped"
    assert not (tmp_path / "judge.json").exists()


def test_perturb_cli_generates_once_and_regenerates_only_with_force(tmp_path, monkeypatch, capsys):
    res = tmp_path / "results"
    res.mkdir()
    (res / "live_official.json").write_text(json.dumps({"rows": ROWS}), encoding="utf-8")
    monkeypatch.setattr(perturb, "RESULTS", res)
    monkeypatch.setattr(perturb, "_cases", lambda: CASES)
    assert perturb.main(["--per-type", "2"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["linhas"] == 6 and out["por_tipo"] == {t: 2 for t in perturb.TYPES} and "~p" not in json.dumps(out)
    first = (res / perturb.FILE).read_text(encoding="utf-8")
    again = perturb.main(["--per-type", "3"]) == 0 and json.loads(capsys.readouterr().out)
    assert again["ja_existia"] is True and again["desatualizadas"] == 0
    assert (res / perturb.FILE).read_text(encoding="utf-8") == first  # nunca regera por cima sem --force
    assert perturb.main(["--per-type", "3", "--force"]) == 0 and json.loads(capsys.readouterr().out)["linhas"] == 9


def test_nothing_to_perturb_writes_nothing_so_a_later_call_still_generates(tmp_path, monkeypatch):
    empty = tmp_path / "vazio"
    empty.mkdir()
    monkeypatch.setattr(perturb, "RESULTS", empty)
    assert perturb.main([]) == 2 and not (empty / perturb.FILE).exists()  # sem ao vivo: recusa, sem arquivo
    assert perturb.ensure(empty) == [] and not (empty / perturb.FILE).exists()  # não trava a geração de depois
    jj = Judge([])
    assert judge.judge_perturbed(jj, empty)["status"] == "skipped" and jj.calls == 0  # nada a julgar, sem gasto
    (empty / "live_official.json").write_text(json.dumps({"rows": ROWS}), encoding="utf-8")
    monkeypatch.setattr(perturb, "_cases", lambda: CASES)
    assert perturb.ensure(empty, per_type=1) and (empty / perturb.FILE).exists()


# 3. a página mistura sem marcar --------------------------------------------------------------------------------------
def test_page_mixes_perturbed_answers_without_marking_them(tmp_path, monkeypatch, capsys):
    res = _results(tmp_path)
    monkeypatch.setattr(label, "RESULTS", res)
    monkeypatch.setattr(label_page, "_before", lambda: {r["id"]: [f"turno antes de {r['id']}"] for r in ROWS})
    got = label_page.items(4, results=res, perturb=3, base=tmp_path)
    real = label.sample(label.load_rows(res), 4)
    fake = {r["id"]: r for r in perturb.load(res)}
    back = _back(res)
    assert len(got) == 7 and all(re.fullmatch(r"r[0-9a-f]{10}", i["id"]) and i["id"] in back for i in got)
    assert {back[i["id"]] for i in got} - set(fake) == {r["id"] for r in real}  # amostra real: a mesma
    mixed = [fake[back[i["id"]]] for i in got if back[i["id"]] in fake]
    assert Counter(r["perturbation"] for r in mixed) == {t: 1 for t in perturb.TYPES}  # um de cada, em rodízio
    assert not {r["original_id"] for r in mixed} & {r["id"] for r in real}  # nunca ao lado da própria original
    for i in got:  # a conversa da adulterada é a da original (mesmos turnos anteriores)
        if back[i["id"]] in fake:
            assert i["before"] == [f"turno antes de {fake[back[i['id']]]['original_id']}"]
    html = label_page.render(got, ["Ana", "Bia"])
    for tell in ("~p", "perturb", "original_id", "numero_trocado", "afirmacao_sem_base", "fato_removido"):
        assert tell not in html
    out = tmp_path / "pagina.html"
    assert label_page.main(["--n", "4", "--perturb", "3", "--raters", "Ana,Bia", "--out", str(out)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["items"] == 7 and printed["adulteradas"] == {"total": 3, "por_tipo": {t: 1 for t in perturb.TYPES}}
    assert "~p" not in json.dumps(printed) and "~p" not in out.read_text(encoding="utf-8")


def test_page_choice_and_order_follow_the_page_salt(tmp_path, monkeypatch):
    """A escolha e a ordem das adulteradas saem do sal da página: o mesmo sal dá a mesma página; outro sal, com a
    mesma seed, põe as adulteradas em outras posições (a seed fica no código e não basta para refazer a posição)."""
    res = _results(tmp_path)
    monkeypatch.setattr(label, "RESULTS", res)
    cases = [r["id"] for r in label.load_rows(res)] + [r["id"] for r in perturb.load(res)]
    fake = {r["id"] for r in perturb.load(res)}

    def page(salt):
        got = label_page.items(4, results=res, perturb=3, base=tmp_path, salt=salt)
        back = {label.page_id(c, salt): c for c in cases}
        return got, [back[i["id"]] for i in got]

    salts = [f"{k:x}" * 32 for k in range(1, 7)]
    first, order = page(salts[0])
    assert page(salts[0]) == (first, order)  # mesmo sal: a mesma página, item por item
    spots = {tuple(n for n, c in enumerate(o) if c in fake) for o in (page(s)[1] for s in salts)}
    assert len(spots) > 1  # a posição das adulteradas muda com o sal
    chosen = {frozenset(c for c in page(s)[1] if c in fake) for s in salts}
    assert len(chosen) > 1  # e a escolha também
    assert not label.SALT_FILE.exists()  # sal passado de fora não grava sal novo


def test_salt_file_is_private_from_the_first_byte_and_replaced_at_once(tmp_path, monkeypatch):
    """O arquivo dos sais nasce 0600 (num temporário criado já assim) e troca de uma vez (os.replace): nunca fica
    legível pelos outros nem pela metade; uma queda na troca deixa os sais das páginas antigas inteiros."""
    path = tmp_path / "var" / "sal.json"
    first = label.new_salt("página", path)
    modes, replace = [], os.replace

    def spy(src, dst):
        modes.append(stat.S_IMODE(os.stat(src).st_mode))  # o temporário, antes de virar o arquivo
        replace(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    second = label.new_salt("consenso", path)
    assert [e["salt"] for e in label._salts(path)] == [first, second] and len(modes) == 1
    if os.name == "posix":
        assert modes == [0o600] and stat.S_IMODE(path.stat().st_mode) == 0o600
    before = path.read_text(encoding="utf-8")

    def broken(src, dst):
        raise OSError("disco cheio")

    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(OSError):
        label.new_salt("página", path)
    assert path.read_text(encoding="utf-8") == before  # os sais guardados ficam inteiros
    assert [p.name for p in path.parent.iterdir()] == ["sal.json"]  # e nenhum temporário largado


def test_blind_ids_need_the_page_salt(tmp_path, monkeypatch, capsys):
    res = _results(tmp_path)
    monkeypatch.setattr(label, "RESULTS", res)
    cases = [r["id"] for r in label.load_rows(res)] + [r["id"] for r in perturb.load(res)]
    one = label_page.items(4, results=res, perturb=3, base=tmp_path)
    two = label_page.items(4, results=res, perturb=3, base=tmp_path)
    shown = {i["id"] for i in one}
    assert not shown & {i["id"] for i in two}  # mesma amostra, sal novo: o id não é função só do caso
    # quem tem o código e o HTML não refaz o caminho: nem o hash sem segredo, nem HMAC sem sal, nem o id cru
    guesses = {"r" + hashlib.sha256(f"rotulagem:{c}".encode()).hexdigest()[:10] for c in cases}
    guesses |= {label.page_id(c, "") for c in cases} | set(cases)
    assert not shown & guesses
    html = label_page.render(one, ["Ana", "Bia"])
    salts = [e["salt"] for e in json.loads(label.SALT_FILE.read_text(encoding="utf-8"))["salts"]]
    assert len(salts) == 2 and not any(s in html for s in salts)  # o sal fica fora da página
    assert "var/" in (ROOT / ".gitignore").read_text(encoding="utf-8").split()  # e fora do git
    assert label.SALT_FILE.parent.name == "var"
    for page, name in ((one, "Ana"), (two, "Bia")):  # cada página volta ao caso pelo sal dela
        dump = tmp_path / f"{name}.json"
        dump.write_text(json.dumps([{"data": {"rater": name, "marks": {i["id"]: {"v": "pass"} for i in page}}}]),
                        encoding="utf-8")
        assert label.import_page(dump, results=res, base=tmp_path) == {name: 7}
    label.SALT_FILE.unlink()  # sal perdido: nada volta ao caso, e a importação lista em vez de descartar
    dump = tmp_path / "Carla.json"
    dump.write_text(json.dumps([{"data": {"rater": "Carla", "marks": {i["id"]: {"v": "pass"} for i in one}}}]),
                    encoding="utf-8")
    assert label.import_page(dump, results=res, base=tmp_path) == {"Carla": 0, "nao_mapeados": {"Carla": sorted(shown)}}
    assert "AVISO: 7 marcação(ões)" in capsys.readouterr().err and not label.csv_path("Carla", tmp_path).exists()


def test_page_refuses_copies_of_an_answer_that_changed_since_generation(tmp_path, monkeypatch, capsys):
    res = _results(tmp_path)
    monkeypatch.setattr(label, "RESULTS", res)
    monkeypatch.setattr(perturb, "RESULTS", res)
    monkeypatch.setattr(perturb, "_cases", lambda: CASES)
    fake = perturb.load(res)
    assert perturb.stale(fake, label.load_rows(res)) == []
    victim = fake[0]["original_id"]  # bateria nova: a resposta dessa original mudou depois da geração
    rows = [{**r, "answer": r["answer"] + " Texto novo."} if r["id"] == victim else r for r in ROWS]
    (res / "live_official.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    out = tmp_path / "p.html"
    assert label_page.main(["--n", "4", "--perturb", "3", "--raters", "Ana,Bia", "--out", str(out)]) == 2
    err = capsys.readouterr().err
    assert "1 de 9" in err and "--force" in err and victim not in err  # quantas, nunca quais
    assert not out.exists() and not label.SALT_FILE.exists()  # nada sai, nem sal órfão
    assert perturb.main([]) == 0 and json.loads(capsys.readouterr().out)["desatualizadas"] == 1
    assert perturb.main(["--force"]) == 0
    capsys.readouterr()
    assert label_page.main(["--n", "4", "--perturb", "3", "--raters", "Ana,Bia", "--out", str(out)]) == 0
    old = [{k: v for k, v in r.items() if k != "original_sha"} for r in perturb.load(res)]
    assert perturb.stale(old, label.load_rows(res)) == [r["id"] for r in old]  # sem a impressão digital: não prova


# 4. importação e relatório com ids adulterados -----------------------------------------------------------------------
def _page(tmp_path, res, raters=("Ana",)):
    return label_page.items(4, results=res, perturb=3, raters=list(raters), base=tmp_path)


def _mark(tmp_path, res, got, rater, wrong=frozenset()):
    """Uma pessoa marca a página: reprova as adulteradas, aprova as reais (salvo os ids em `wrong`). A ficha leva a
    `sample` da página, como a página de verdade grava (o motivo da escolha volta por ela)."""
    fake = {r["id"] for r in perturb.load(res)}
    back = _back(res)
    bad = {"v": "fail", "tipo": "unsupported_claim", "c1": "sim", "c2": "sim", "c3": "sim"}
    good = {"v": "pass", "c1": "sim", "c2": "nao", "c3": "sim"}
    marks = {i["id"]: bad if (back[i["id"]] in fake) != (i["id"] in wrong) else good for i in got}
    dump = tmp_path / f"{rater}.json"
    dump.write_text(json.dumps({"documents": [{"data": {"rater": rater, "marks": marks,
                                                        "sample": label_page.sample_id(got)}}]}), encoding="utf-8")
    assert label.import_page(dump, results=res, base=tmp_path) == {rater: 7}
    return got


def _label_page(tmp_path, res, rater="Ana"):
    return _mark(tmp_path, res, _page(tmp_path, res, (rater,)), rater)


def test_import_maps_blind_ids_back_and_the_report_splits_real_from_perturbed(tmp_path, monkeypatch):
    res = _results(tmp_path)
    monkeypatch.setattr(label, "RESULTS", res)
    _label_page(tmp_path, res)
    rows = {r["id"]: r for r in label.read_labels(label.csv_path("Ana", tmp_path))}
    fake = {r["id"]: r for r in perturb.load(res)}
    shown = [i for i in rows if i in fake]
    assert len(rows) == 7 and len(shown) == 3  # o CSV volta ao id do caso
    assert all(rows[i]["split"] == "perturbed" and rows[i]["resposta"] == fake[i]["answer"] for i in shown)
    jj = Judge(r["answer"] for r in ROWS)
    judge.judge_into(jj, res / "live_official.json", out=res / "judge.json")
    judge.judge_perturbed(jj, res)
    rep = label.report(results=res, out=tmp_path / "h.json", base=tmp_path)
    assert (rep["rotulos"], rep["humano_passa"]) == (4, 4)  # humano × automático: só as reais
    jx = rep["juiz_x_humano"]
    assert (jx["casos"], jx["positives"], jx["negatives"]) == (7, 4, 3) and jx["concordancia"] == 1.0
    assert (jx["negativos_reais"], jx["negativos_plantados"]) == (0, 3)  # a composição vai junto
    assert (jx["reais"]["casos"], jx["adulteradas"]["casos"], jx["adulteradas"]["tnr"]) == (4, 3, 1.0)
    assert jx["adulteradas"]["por_tipo"]["numero_trocado"] == {"casos": 1, "humano_reprova": 1, "juiz_reprova": 1,
                                                               "juiz_reprova_antes": 1}
    assert jx["validacao"]["validated"] is False  # 4 e 3 por classe: abaixo de 10, a regra não valida
    ad = rep["adulteradas"]
    assert (ad["geradas"], ad["rotuladas"], ad["humano"]) == (9, 3, {"ana": {"rotuladas": 3, "reprovou": 3}})
    assert ad["juiz"]["julgadas"] == 9 and ad["juiz"]["reprovou"] == 9 and ad["fora_da_conta"] == []
    assert rep["entre_humanos"] is None  # uma pessoa só; e humano × humano nunca conta adulterada


def test_plan_b_copied_text_with_blind_ids_lands_on_the_case_ids(tmp_path, monkeypatch):
    res = _results(tmp_path)
    monkeypatch.setattr(label, "RESULTS", res)
    got = _page(tmp_path, res)
    back = _back(res)
    fake = {r["id"] for r in perturb.load(res)}
    text = "CONFERENCIA abc123 Bia\n" + "\n".join(
        f"{i['id']}=fail:unsupported_claim c1=sim c2=sim c3=sim" if back[i["id"]] in fake else f"{i['id']}=pass"
        for i in got)
    assert label.import_text(text, results=res, base=tmp_path) == {"Bia": 7}
    rows = {r["id"]: r for r in label.read_labels(label.csv_path("Bia", tmp_path))}
    shown = [back[i["id"]] for i in got if back[i["id"]] in fake]
    assert len(shown) == 3 and all(rows[i]["humano"] == "fail" for i in shown)  # no CSV, o id do caso


def test_consensus_round_stays_blind_and_maps_back(tmp_path, monkeypatch):
    res = _results(tmp_path)
    monkeypatch.setattr(label, "RESULTS", res)
    got = _page(tmp_path, res, ("Ana", "Bia"))  # as duas na MESMA página
    _mark(tmp_path, res, got, "Ana")
    back = _back(res)
    fake = {r["id"] for r in perturb.load(res)}
    missed = next(i["id"] for i in got if back[i["id"]] in fake)  # Bia deixa passar uma adulterada
    _mark(tmp_path, res, got, "Bia", wrong={missed})
    found = label.divergences(base=tmp_path, results=res)
    assert [d["id"] for d in found] == [back[missed]]
    md = (tmp_path / "human_divergences.md").read_text(encoding="utf-8")
    blind = re.findall(r"^## (r[0-9a-f]{10})$", md, re.MULTILINE)
    assert "~p" not in md and back[missed] not in md and len(blind) == 1 and f"{blind[0]}=pass|fail|diverge" in md
    assert _back(res)[blind[0]] == back[missed]  # sal da rodada de consenso guardado, como o da página
    label.import_consensus(f"CONSENSO\n{blind[0]}=fail\n", base=tmp_path, results=res)
    assert json.loads((tmp_path / "human_consensus.json").read_text(encoding="utf-8")) == {
        back[missed]: {"v": "fail", "tipo": ""}}  # volta ao id do caso


def test_second_page_never_repeats_a_planted_answer_the_same_person_already_labeled(tmp_path, monkeypatch):
    res = _results(tmp_path)
    monkeypatch.setattr(label, "RESULTS", res)
    fake = {r["id"] for r in perturb.load(res)}
    first = _label_page(tmp_path, res, "Ana")
    seen = {_back(res)[i["id"]] for i in first} & fake
    again = _page(tmp_path, res, ("Ana", "Bia"))
    shown = {_back(res)[i["id"]] for i in again} & fake
    assert len(seen) == 3 and shown and not seen & shown  # Ana não revê a adulterada que já rotulou
    other = label_page.items(4, results=res, perturb=9, raters=["Carla"], base=tmp_path)
    assert seen <= {_back(res)[i["id"]] for i in other}  # quem não viu pode receber


def test_label_of_an_answer_that_changed_since_is_left_out(tmp_path, monkeypatch):
    """perturbed.json regerado depois da rotulagem. Com a página congelada (R11), o rótulo continua valendo sobre o
    texto que a pessoa viu e nunca encontra o veredito do texto novo; sem ela (página de antes do congelamento), fica
    fora da conta, listado, como sempre."""
    res = _results(tmp_path)
    monkeypatch.setattr(label, "RESULTS", res)
    _label_page(tmp_path, res)
    data = json.loads((res / perturb.FILE).read_text(encoding="utf-8"))
    victim = next(r for r in data["rows"] if r["id"] in {x["id"] for x in label.read_labels(
        label.csv_path("Ana", tmp_path))})
    victim["answer"] += " Texto novo."  # perturbed.json regerado depois da rotulagem
    (res / perturb.FILE).write_text(json.dumps(data), encoding="utf-8")
    jj = Judge(r["answer"] for r in ROWS)
    judge.judge_into(jj, res / "live_official.json", out=res / "judge.json")
    judge.judge_perturbed(jj, res)  # o juiz julga a versão nova (o texto novo do victim)
    rep = label.report(results=res, out=tmp_path / "h.json", base=tmp_path)
    assert rep["adulteradas"]["fora_da_conta"] == [] and rep["adulteradas"]["rotuladas"] == 3
    jx = rep["juiz_x_humano"]
    assert jx["adulteradas"]["casos"] == 2  # o victim não tem veredito do SEU texto: fora do juiz × humano
    assert "1 rótulo(s) sem veredito do juiz sobre o texto rotulado" in rep["aviso_juiz"]
    for page in label.VALIDATION_DIR.glob("*.json"):
        page.unlink()
    rep = label.report(results=res, out=tmp_path / "h.json", base=tmp_path)
    assert rep["adulteradas"]["fora_da_conta"] == [victim["id"]] and rep["adulteradas"]["rotuladas"] == 2


# 5. validação: plantado não substitui negativo real ------------------------------------------------------------------
def _verdicts(path, ids_ok, ids_bad, **extra):
    vs = [{"id": i, "run": 0, "grounded": True, "helpful": True, "language_ok": True} for i in ids_ok]
    vs += [{"id": i, "run": 0, "grounded": False, "helpful": True, "language_ok": True} for i in ids_bad]
    path.write_text(json.dumps({"verdicts": vs, **extra}), encoding="utf-8")


def _planted(tmp_path, n_fake):
    fake = {f"c{i}~p1": {"id": f"c{i}~p1", "answer": f"adulterada {i}", "perturbation": "numero_trocado"}
            for i in range(n_fake)}
    (tmp_path / perturb.FILE).write_text(json.dumps({"rows": list(fake.values())}), encoding="utf-8")
    return fake


def _drawn(*groups):
    """Motivo da escolha de respostas reais sorteadas (o que a exportação e a página gravam no CSV)."""
    return {i: judge.SELECTED_RANDOM for g in groups for i in g}


def _review(tmp_path, jx):
    (tmp_path / "human_review.json").write_text(json.dumps({
        "rotulos": 12, "humano_passa": 12, "automatico_passa": 12, "concordancia": 1.0, "kappa": None,
        "juiz_x_humano": jx}), encoding="utf-8")
    return fill_readme.human_block(tmp_path)


def test_planted_negatives_alone_never_validate_the_judge_on_real_answers(tmp_path):
    real = [f"r{i}" for i in range(12)]
    fake = _planted(tmp_path, 11)
    _verdicts(tmp_path / "judge.json", real[:11], real[11:])  # o juiz erra 1 real
    _verdicts(tmp_path / "judge_perturbed.json", list(fake)[:1], list(fake)[1:],  # e deixa passar 1 adulterada
              perturbed_sha=perturb.rows_sha(list(fake.values())))
    human = {"ana": {**{i: True for i in real}, **{i: False for i in fake}}}
    out = label.judge_vs_humans(human, None, tmp_path, perturbed=fake, selection=_drawn(real))
    assert (out["positives"], out["negatives"], out["tpr"], out["tnr"]) == (12, 11, 0.917, 0.909)
    assert (out["negativos_reais"], out["negativos_plantados"]) == (0, 11)
    v = out["validacao"]  # por número e taxa passaria; só que nenhum negativo é resposta real
    assert v["validated"] is False and v["planted_only"] is True
    assert v["missing"] == [f">= {judge.VALIDATION_MIN_REAL_NEGATIVES} negativos de respostas reais (tem 0)"]
    # a parte das plantadas vem à parte da regra fixada antes de medir: entrou depois da revisão
    assert v["planted_rule"] == judge.PLANTED_RULE and "negativos de respostas reais" not in v["rule"]
    assert out["reais"]["validacao"]["validated"] is False  # sem negativo nenhum nas reais
    assert out["adulteradas"]["validacao"]["validated"] is False  # e sem positivo nas adulteradas
    text = _review(tmp_path, out)
    assert "23 respostas (a pessoa aprova 12 e reprova 11: 0 reais + 11 plantadas)" in text
    assert "validado só com negativos plantados (com respostas reais: não validado" in text
    assert "**validado**" not in text
    neg = ["n0", "n1", "n2"]  # com 3 negativos reais que o juiz reprova, a mesma regra valida
    _verdicts(tmp_path / "judge.json", real[:11], real[11:] + neg)
    human["ana"].update({i: False for i in neg})
    out = label.judge_vs_humans(human, None, tmp_path, perturbed=fake, selection=_drawn(real, neg))
    assert (out["negativos_reais"], out["negativos_plantados"], out["tnr_nos_reais"]) == (3, 11, 1.0)
    assert out["validacao"]["validated"] is True and out["validacao"]["planted_only"] is False
    assert "→ **validado**" in _review(tmp_path, out)
    nine = _planted(tmp_path, 9)  # 9 negativos e nenhum real: a regra não valida, por melhor que seja o TNR
    _verdicts(tmp_path / "judge.json", real, [])
    _verdicts(tmp_path / "judge_perturbed.json", [], list(nine), perturbed_sha=perturb.rows_sha(list(nine.values())))
    out = label.judge_vs_humans({"ana": {**{i: True for i in real}, **{i: False for i in nine}}}, None, tmp_path,
                                perturbed=nine, selection=_drawn(real))
    assert out["negatives"] == 9 and out["tnr"] == 1.0 and out["validacao"]["validated"] is False
    assert out["validacao"]["planted_only"] is False  # nem pela regra de número passaria
    assert judge.validation({"positives": 12, "negatives": 11, "tpr": 0.9, "tnr": 0.9})["validated"] is True
    assert "planted_only" not in judge.validation({"positives": 12, "negatives": 11, "tpr": 0.9, "tnr": 0.9})


def test_real_negatives_the_judge_passes_never_validate_the_total(tmp_path):
    """Contar os negativos reais não basta: 3 que o juiz APROVA + 15 plantadas que ele reprova dão TNR 0,83 no total e,
    só pela contagem, passariam como validado. A regra pede o juiz reprovando os reais (TNR >= 0,8 neles); com os 3
    reprovados, valida."""
    real = [f"r{i}" for i in range(12)]
    neg = ["n0", "n1", "n2"]
    fake = _planted(tmp_path, 15)
    _verdicts(tmp_path / "judge_perturbed.json", [], list(fake), perturbed_sha=perturb.rows_sha(list(fake.values())))
    human = {"ana": {**{i: True for i in real}, **{i: False for i in [*neg, *fake]}}}
    _verdicts(tmp_path / "judge.json", real + neg, [])  # o juiz aprova os 3 negativos reais
    out = label.judge_vs_humans(human, None, tmp_path, perturbed=fake, selection=_drawn(real, neg))
    v = out["validacao"]
    assert (out["positives"], out["negatives"], out["tpr"], out["tnr"]) == (12, 18, 1.0, 0.833)
    assert (out["negativos_reais"], out["negativos_plantados"]) == (3, 15)  # o mínimo de reais existe
    assert v["validated"] is False and v["planted_only"] is True  # mas o juiz não reprova nenhum deles
    assert out["tnr_nos_reais"] == 0.0 and v["real_tnr"] == 0.0
    assert v["missing"] == [f"TNR >= {judge.VALIDATION_MIN_RATE} nos negativos de respostas reais (tem 0.0)"]
    text = _review(tmp_path, out)
    assert ("18: 3 reais + 15 plantadas), escolhidas sem depender do juiz (sorteio 15, defeito plantado 15) · "
            "concordância 0.9 · TPR 1.0 · TNR 0.833 (nos 3 negativos reais: 0.0)") in text
    assert "validado só com negativos plantados (com respostas reais: não validado" in text
    assert "**validado**" not in text
    assert f"acrescentada depois da revisão, mais estrita: {judge.PLANTED_RULE}" in text  # dita como de depois
    _verdicts(tmp_path / "judge.json", real + neg[:1], neg[1:])  # reprova 2 dos 3: TNR 0,667 nos reais
    out = label.judge_vs_humans(human, None, tmp_path, perturbed=fake, selection=_drawn(real, neg))
    assert out["tnr"] >= judge.VALIDATION_MIN_RATE and out["validacao"]["validated"] is False
    _verdicts(tmp_path / "judge.json", real, neg)  # reprova os 3 negativos reais
    out = label.judge_vs_humans(human, None, tmp_path, perturbed=fake, selection=_drawn(real, neg))
    assert (out["tnr"], out["tnr_nos_reais"]) == (1.0, 1.0)
    assert out["validacao"]["validated"] is True and out["validacao"]["planted_only"] is False
    assert "→ **validado**" in _review(tmp_path, out)


def test_real_negatives_the_judge_chose_never_validate_only_judge_free_ones_do(tmp_path):
    """Circularidade: a página 2 (`--suspects`) traz respostas que o próprio juiz reprovou, e o TNR dele nelas é 1 por
    construção. 3 negativos reais escolhidos pelo juiz + 15 plantadas: não validado, com os 3 à parte (diagnóstico); os
    mesmos 3 sorteados (ou trazidos pela checagem automática) e reprovados pelo juiz: validado; sem o motivo gravado
    (rótulo antigo): seleção desconhecida, fora da conta e do mínimo."""
    real, neg = [f"r{i}" for i in range(12)], ["n0", "n1", "n2"]
    fake = _planted(tmp_path, 15)
    _verdicts(tmp_path / "judge_perturbed.json", [], list(fake), perturbed_sha=perturb.rows_sha(list(fake.values())))
    _verdicts(tmp_path / "judge.json", real, [*neg, "p0"])  # p0: o juiz reprovou, a pessoa aprova
    human = {"ana": {**{i: True for i in [*real, "p0"]}, **{i: False for i in [*neg, *fake]}}}
    by_judge = {**_drawn(real), **{i: judge.SELECTED_JUDGE for i in [*neg, "p0"]}}
    out = label.judge_vs_humans(human, None, tmp_path, perturbed=fake, selection=by_judge)
    v = out["validacao"]
    assert (out["casos"], out["positives"], out["negatives"], out["tpr"], out["tnr"]) == (27, 12, 15, 1.0, 1.0)
    assert (out["negativos_reais"], out["negativos_plantados"]) == (0, 15)  # os 3 do juiz não contam
    assert v["validated"] is False and v["planted_only"] is True
    assert v["missing"] == [f">= {judge.VALIDATION_MIN_REAL_NEGATIVES} negativos de respostas reais (tem 0)"]
    assert v["selection_rule"] == judge.SELECTION_RULE and "juiz" in v["left_out"]
    left = out["fora_da_validacao"]["juiz"]  # à parte: quantos e o TNR (trivial) neles; o positivo escolhido assim
    assert (left["casos"], left["negatives"], left["humano_reprova"], left["tnr"]) == (4, 3, 3, 1.0)
    assert (left["positives"], left["tpr"]) == (1, 0.0)  # também fica fora: só derrubaria o TPR pela escolha
    assert out["selecao"] == {"aleatoria": 12, "plantada": 15, "juiz": 4}
    text = _review(tmp_path, out)
    assert ("27 respostas (a pessoa aprova 12 e reprova 15: 0 reais + 15 plantadas), escolhidas sem depender do juiz "
            "(sorteio 12, defeito plantado 15)") in text
    assert ("- fora da validação (diagnóstico, não validação): 4 escolhidas porque o juiz as reprovou — a pessoa "
            "reprova 3 (TNR do juiz nelas 1.0) e aprova 1 (TPR 0.0).") in text
    assert f"acrescentada depois da 2ª revisão: {judge.SELECTION_RULE}" in text and "**validado**" not in text
    for why in (judge.SELECTED_RANDOM, judge.SELECTED_CHECK):  # os mesmos 3, escolhidos sem o juiz, validam
        out = label.judge_vs_humans(human, None, tmp_path, perturbed=fake,
                                    selection={**by_judge, **{i: why for i in neg}})
        assert (out["negativos_reais"], out["tnr_nos_reais"]) == (3, 1.0)
        assert out["validacao"]["validated"] is True and out["fora_da_validacao"]["juiz"]["casos"] == 1
    out = label.judge_vs_humans(human, None, tmp_path, perturbed=fake, selection=_drawn(real))  # sem motivo: não conta
    assert (out["negativos_reais"], out["validacao"]["validated"]) == (0, False)
    assert (out["fora_da_validacao"]["desconhecida"]["casos"], out["selecao"]["desconhecida"]) == (4, 4)
    assert ("4 de seleção desconhecida (rótulos de antes do registro do motivo da escolha: não contam para validar, "
            "nem para o mínimo de negativos reais)") in _review(tmp_path, out)
    out = label.judge_vs_humans(human, None, tmp_path, perturbed=fake)  # ninguém disse o motivo: idem
    assert out["negativos_reais"] == 0 and out["fora_da_validacao"]["desconhecida"]["casos"] == 16


def test_page_records_why_each_real_answer_was_chosen_outside_the_html_and_the_import_carries_it(tmp_path,
                                                                                                    monkeypatch):
    """A página grava o motivo da escolha de cada resposta real (sorteio, checagem automática, juiz) pela `sample`
    dela, fora do HTML; a importação (ficha da página ou texto do plano B) passa o motivo ao CSV de cada pessoa; a
    exportação grava "aleatoria"; CSV antigo, sem a coluna, é seleção desconhecida. O relatório só valida com o que não
    dependeu do juiz e mostra o resto à parte."""
    res = tmp_path / "results"
    res.mkdir()
    checked, judged = {"o2", "p1"}, {"r1", "a2"}
    rows = [{**r, "checks": {"numbers": False, "facts": True}} if r["id"] in checked else r for r in ROWS]
    (res / "live_official.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    _verdicts(res / "judge.json", [r["id"] for r in rows if r["id"] not in judged], sorted(judged))
    monkeypatch.setattr(label, "RESULTS", res)
    got, reasons = label_page.build(8, results=res, suspects=3, base=tmp_path)
    assert set(reasons) == {i["id"] for i in got}  # sem adulterada, o id da página é o do caso
    drawn = {r["id"] for r in label.sample(label.load_rows(res), 5, 7)}
    assert drawn <= {i for i, why in reasons.items() if why == "aleatoria"}  # o sorteio sai antes das suspeitas
    assert {i for i, why in reasons.items() if why == "checagem"} == checked - drawn  # a checagem antes do juiz
    by_judge = {i for i, why in reasons.items() if why == "juiz"}
    assert by_judge <= judged - drawn and len(by_judge) == min(3 - len(checked - drawn), len(judged - drawn))
    assert label.page_selection(label_page.sample_id(got)) == reasons
    html = label_page.render(got, ["Ana", "Bia"])
    assert not any(w in html for w in ("aleatoria", "checagem", "selecao", "suspeit", "juiz"))  # nada na página
    fail = checked | judged
    marks = {i["id"]: {"v": "fail" if i["id"] in fail else "pass"} for i in got}
    dump = tmp_path / "ana.json"
    dump.write_text(json.dumps([{"data": {"rater": "Ana", "marks": marks, "sample": label_page.sample_id(got)}}]),
                    encoding="utf-8")
    assert label.import_page(dump, results=res, base=tmp_path) == {"Ana": 8}
    assert {r["id"]: r["selecao"] for r in label.read_labels(label.csv_path("Ana", tmp_path))} == reasons
    text = f"CONFERENCIA {label_page.sample_id(got)} Bia\n" + "\n".join(f"{i}={m['v']}" for i, m in marks.items())
    assert label.import_text(text, results=res, base=tmp_path) == {"Bia": 8}  # plano B: a amostra vem na 1ª linha
    assert {r["id"]: r["selecao"] for r in label.read_labels(label.csv_path("Bia", tmp_path))} == reasons
    assert label.export(4, results=res, path=tmp_path / "human_labels.carla.csv") == 4
    assert {r["selecao"] for r in label.read_labels(tmp_path / "human_labels.carla.csv")} == {"aleatoria"}
    spare = next(r for r in ROWS if r["id"] not in marks)  # rotulado antes do registro, fora da página
    with (tmp_path / "human_labels.dani.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)  # o texto de hoje da resposta: rótulo de outro texto nem entraria na conta (R11)
        w.writerow(["id", "split", "pergunta", "resposta", "fontes", "ferramentas", "humano", "nota", "tipo_falha",
                    "c1", "c2", "c3"])
        w.writerow([spare["id"], "official", spare["message"], spare["answer"], "", "", "fail", "", "", "", "", ""])
    jx = label.report(results=res, out=tmp_path / "h.json", base=tmp_path)["juiz_x_humano"]
    kept = [i for i, why in reasons.items() if why != "juiz"]
    assert (jx["casos"], jx["negatives"]) == (len(kept), sum(i in fail for i in kept))  # só o que independe do juiz
    assert jx["fora_da_validacao"]["desconhecida"]["casos"] == 1  # o CSV antigo, à parte
    assert jx["fora_da_validacao"].get("juiz", {}).get("casos", 0) == len(by_judge)
    assert jx["selecao"] == {k: v for k, v in Counter([*reasons.values(), "desconhecida"]).items()}


def test_sample_draws_the_random_part_first_and_takes_check_suspects_before_judge_ones():
    """A parte sorteada não depende do juiz: sai antes das suspeitas, de todas as linhas (sorteada depois, perderia
    justo as que o juiz reprovou). Entre as suspeitas, as da checagem automática vêm antes das do juiz."""
    rows = [{"id": f"c{i:02d}", "split": "ab"[i % 2], "checks": {"facts": i not in (3, 8, 13)}} for i in range(40)]
    first = label.pick_sample(rows, 10, suspects=4, suspect_ids={"c03", "c08", "c13", "c05", "c11", "c17"})
    other = label.pick_sample(rows, 10, suspects=4, suspect_ids={"c03", "c08", "c13", "c21", "c22", "c27", "c30"})
    drawn = {r["id"] for r in label.sample(rows, 6, 7)}
    for got in (first, other):  # o mesmo sorteio com qualquer veredito do juiz
        reasons = {r["id"]: why for r, why in got}
        assert len(got) == 10 and drawn <= {i for i, why in reasons.items() if why == "aleatoria"}
        check_left = {"c03", "c08", "c13"} - drawn
        assert {i for i, why in reasons.items() if why == "checagem"} == check_left  # todas antes do juiz
        assert sum(why == "juiz" for why in reasons.values()) == 4 - len(check_left)
    assert [r["id"] for r in label.enriched_sample(rows, 10, suspects=4, suspect_ids={"c03"})] == [
        r["id"] for r, _ in label.pick_sample(rows, 10, suspects=4, suspect_ids={"c03"})]


def test_both_readings_of_judge_fails_also_on_planted_answers_and_by_type(tmp_path):
    """Nas plantadas também, as duas leituras do "juiz reprova" lado a lado, por tipo: no fato_removido a resposta
    continua fundamentada e só o `helpful` reprova, e é nele que antes e depois se afastam."""
    fake = {f"{c}~p3": {"id": f"{c}~p3", "answer": f"sem o fato {c}", "perturbation": "fato_removido"} for c in "ab"}
    fake["c~p1"] = {"id": "c~p1", "answer": "número trocado", "perturbation": "numero_trocado"}
    (tmp_path / perturb.FILE).write_text(json.dumps({"rows": list(fake.values())}), encoding="utf-8")
    _verdicts(tmp_path / "judge.json", ["r0"], [])
    (tmp_path / "judge_perturbed.json").write_text(json.dumps({
        "perturbed_sha": perturb.rows_sha(list(fake.values())),
        "verdicts": [{"id": "a~p3", "run": 0, "grounded": True, "helpful": False, "language_ok": True},
                     {"id": "b~p3", "run": 0, "grounded": True, "helpful": True, "language_ok": True},
                     {"id": "c~p1", "run": 0, "grounded": False, "helpful": True, "language_ok": True}]}),
        encoding="utf-8")
    human = {"ana": {"r0": True, **{i: False for i in fake}}}
    out = label.judge_vs_humans(human, None, tmp_path, perturbed=fake)
    lp = out["leituras_plantadas"]
    assert lp["em_vigor"] == "depois" and (lp["antes"]["juiz_reprova"], lp["depois"]["juiz_reprova"]) == (1, 2)
    assert (lp["antes"]["tnr"], lp["depois"]["tnr"]) == (0.333, 0.667)
    assert out["adulteradas"]["por_tipo"]["fato_removido"] == {"casos": 2, "humano_reprova": 2, "juiz_reprova": 1,
                                                               "juiz_reprova_antes": 0}
    summary = label.perturbed_summary(fake, {"ana": {i: False for i in fake}}, [], tmp_path)
    assert (summary["juiz"]["reprovou_antes"], summary["juiz"]["reprovou"]) == (1, 2)
    assert summary["juiz"]["por_tipo"]["fato_removido"] == {"julgadas": 2, "reprovou": 1, "reprovou_antes": 0}
    (tmp_path / "human_review.json").write_text(json.dumps({
        "rotulos": 1, "humano_passa": 1, "automatico_passa": 1, "concordancia": 1.0, "kappa": None,
        "juiz_x_humano": out, "adulteradas": summary}), encoding="utf-8")
    lines = fill_readme.human_block(tmp_path).splitlines()
    judged = next(t for t in lines if t.startswith("- juiz nas 3 com defeito plantado"))
    assert f"{fill_readme.READINGS}: numero_trocado 1/1 → 1/1; afirmacao_sem_base" not in judged  # tipo sem julgada
    assert f"{fill_readme.READINGS}: numero_trocado 1/1 → 1/1; fato_removido 0/2 → 1/2." in judged
    planted = next(t for t in lines if t.startswith("- só as de defeito plantado"))  # na mesma linha, por tipo
    assert "fato_removido: a pessoa reprovou 2/2, o juiz 1/2 (antes 0/2)" in planted
    assert ("\"juiz reprova\" nas duas leituras: antes (só não fundamentada, idioma ou vazamento) 1/3 · concordância "
            "0.333 · TNR 0.333; depois (+ não atende ao pedido, a em vigor) 2/3 · concordância 0.667 · TNR 0.667"
            ) in planted


def test_both_readings_of_judge_fails_stay_side_by_side_on_real_answers(tmp_path):
    (tmp_path / "judge.json").write_text(json.dumps({"verdicts": [
        {"id": "a", "run": 0, "grounded": True, "helpful": True, "language_ok": True},
        {"id": "b", "run": 0, "grounded": True, "helpful": False, "language_ok": True},  # fundamentada, não atende
        {"id": "c", "run": 0, "grounded": False, "helpful": True, "language_ok": True}]}), encoding="utf-8")
    out = label.judge_vs_humans({"ana": {"a": True, "b": False, "c": False}}, None, tmp_path, selection=_drawn("abc"))
    lr = out["leituras_reais"]
    assert lr["em_vigor"] == "depois" and "helpful" in lr["depois"]["regra"] and "verdict_fails" in lr["antes"]["regra"]
    assert (lr["antes"]["juiz_reprova"], lr["antes"]["tnr"], lr["antes"]["concordancia"]) == (1, 0.5, 0.667)
    assert (lr["depois"]["juiz_reprova"], lr["depois"]["tnr"], lr["depois"]["concordancia"]) == (2, 1.0, 1.0)
    assert out["concordancia"] == lr["depois"]["concordancia"]  # o total segue a regra em vigor
    text = _review(tmp_path, out)
    assert "\"juiz reprova\" nas respostas reais, as duas leituras: antes, se não fundamentada" in text
    assert "juiz reprova 1/3" in text and "juiz reprova 2/3" in text and "Em vigor: a de depois, porque" in text


def test_judge_uses_the_raters_yardstick_and_never_a_stale_perturbed_verdict(tmp_path):
    fake = _planted(tmp_path, 2)
    (tmp_path / "judge.json").write_text(json.dumps({"verdicts": []}), encoding="utf-8")
    ids = list(fake)
    (tmp_path / "judge_perturbed.json").write_text(json.dumps({
        "perturbed_sha": perturb.rows_sha(list(fake.values())),
        "verdicts": [{"id": ids[0], "run": 0, "grounded": True, "helpful": False, "language_ok": True},
                     {"id": ids[1], "run": 0, "grounded": True, "helpful": True, "language_ok": True}]}),
        encoding="utf-8")
    out = label.judge_vs_humans({"ana": {i: False for i in ids}}, None, tmp_path, perturbed=fake)
    # resposta fundamentada que não atende ao pedido: a pessoa reprova pela pergunta 1, o juiz pelo `helpful` (que a
    # leitura de antes não contava)
    assert out["adulteradas"]["por_tipo"]["numero_trocado"] == {"casos": 2, "humano_reprova": 2, "juiz_reprova": 1,
                                                                "juiz_reprova_antes": 0}
    stale = json.loads((tmp_path / "judge_perturbed.json").read_text(encoding="utf-8")) | {"perturbed_sha": "outra"}
    (tmp_path / "judge_perturbed.json").write_text(json.dumps(stale), encoding="utf-8")
    assert label.judge_vs_humans({"ana": {i: False for i in ids}}, None, tmp_path, perturbed=fake) is None
    _verdicts(tmp_path / "judge.json", ["r0"], [])
    out = label.judge_vs_humans({"ana": {"r0": True, **{i: False for i in ids}}}, None, tmp_path, perturbed=fake,
                                selection=_drawn(["r0"]))
    assert out["casos"] == 1 and out["adulteradas"] is None and "outra versão" in out["aviso"]
    (tmp_path / "judge_perturbed.json").write_text(json.dumps({"status": "skipped"}), encoding="utf-8")
    out = label.judge_vs_humans({"ana": {"r0": True, **{i: False for i in ids}}}, None, tmp_path, perturbed=fake)
    assert "não rodou" in out["aviso"]  # modo offline: dito como é, não como "outra versão"


def test_page_completes_a_missing_kind_with_the_others_and_results_declares_the_real_composition():
    """Sem resposta que aceite afirmacao_sem_base (o ensaio, depois das regras de ausência e de valor do mesmo tipo), a
    página de 15 sai com os outros dois tipos, e o RESULTS diz a composição real, não "5 de cada"."""
    pool = [{"id": f"o{i}~p{k}", "original_id": f"o{i}", "perturbation": kind}
            for i in range(20) for k, kind in ((1, "numero_trocado"), (3, "fato_removido")) if (i < 10) == (k == 1)]
    picked = perturb.pick(pool, 15, salt="a" * 32)
    assert Counter(r["perturbation"] for r in picked) == {"numero_trocado": 8, "fato_removido": 7}
    ad = {"arquivo": "perturbed.json", "geradas": 20, "rotuladas": 15, "juiz": None, "fora_da_conta": [],
          "por_tipo": {"numero_trocado": 10, "afirmacao_sem_base": 0, "fato_removido": 10},
          "rotuladas_por_tipo": {"numero_trocado": 8, "afirmacao_sem_base": 0, "fato_removido": 7},
          "humano": {"ana": {"rotuladas": 15, "reprovou": 15}}}
    line = fill_readme._perturbed_lines(ad)[0]
    assert ("(composição real: numero_trocado 8, fato_removido 7, de 20 geradas: numero_trocado 10, fato_removido 10; "
            "nenhuma resposta aceitou afirmacao_sem_base, e os outros tipos completam a página;") in line
    ad["por_tipo"]["afirmacao_sem_base"], ad["rotuladas_por_tipo"] = 3, {"numero_trocado": 6, "afirmacao_sem_base": 3,
                                                                          "fato_removido": 6}
    assert "só 3 respostas aceitaram afirmacao_sem_base, e os outros" in fill_readme._perturbed_lines(ad)[0]
    ad["rotuladas_por_tipo"] = {"numero_trocado": 5, "afirmacao_sem_base": 5, "fato_removido": 5}
    assert "completam" not in fill_readme._perturbed_lines(ad)[0]  # equilibrada: nada a explicar


# bloco humano do docs/RESULTS.md -------------------------------------------------------------------------------------
def test_results_human_block_declares_the_perturbed_answers_and_the_validation(tmp_path, monkeypatch):
    res = _results(tmp_path)
    monkeypatch.setattr(label, "RESULTS", res)
    _label_page(tmp_path, res)
    jj = Judge(r["answer"] for r in ROWS)
    judge.judge_into(jj, res / "live_official.json", out=res / "judge.json")
    judge.judge_perturbed(jj, res)
    rep = label.report(results=res, out=tmp_path / "human_review.json", base=tmp_path)
    text = fill_readme.human_block(tmp_path)
    assert ("Respostas com um defeito plantado (número trocado ou afirmação sem base contra a evidência; fato de "
            "referência removido): **3** entraram na rotulagem") in text
    assert "numero_trocado 1, afirmacao_sem_base 1, fato_removido 1" in text and "`ana` reprovou 3/3" in text
    assert (f"juiz nas 9 com defeito plantado (sem depender de rótulo), reprova por tipo, {fill_readme.READINGS}: "
            "numero_trocado 3/3 → 3/3; afirmacao_sem_base 3/3 → 3/3; fato_removido 3/3 → 3/3. fato_removido não é "
            "negativo garantido") in text
    assert "\"juiz reprova\" nas duas leituras: antes (só não fundamentada, idioma ou vazamento) 3/3" in text
    assert "Juiz × humano (veredito do juiz: fundamentada, útil" in text
    assert "7 respostas (a pessoa aprova 4 e reprova 3: 0 reais + 3 plantadas)" in text and "não validado" in text
    assert "- só as de defeito plantado: 3 respostas" in text and "- só reais: 4 respostas" in text
    assert "as duas leituras: antes, se " in text and "**validado**" not in text
    old = {k: v for k, v in rep.items() if k not in ("adulteradas", "juiz_x_humano")}
    (tmp_path / "human_review.json").write_text(json.dumps(old), encoding="utf-8")
    assert "defeito plantado" not in fill_readme.human_block(tmp_path)  # relatório sem adulteradas: nada a declarar
