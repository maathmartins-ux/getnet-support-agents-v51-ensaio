"""Respostas com um defeito plantado, declaradas, para medir o juiz (e quem rotula) em negativos conhecidos.

Por quê: nas respostas reais quase nada é ruim (1 falha em 37 rótulos humanos), e sem >= 10 negativos humanos o TNR
do juiz contra pessoas não se mede (regra fixada antes de medir, evals.judge.validation). A prática é misturar à
amostra humana cópias de respostas reais com um defeito plantado — conferido contra a PRÓPRIA evidência, que o juiz e
a pessoa veem igual à da original — e declarar quantas entraram e de que tipo (nunca quais, na página). Plantado não
substitui negativo real: o total juiz × pessoas só vale como validado com um mínimo de negativos de respostas reais
que o juiz reprove (evals.judge.VALIDATION_MIN_REAL_NEGATIVES, PLANTED_RULE).

Tipos (campo `perturbation` de cada linha; `perturbation_detail` diz o que mudou):
- numero_trocado: um número da resposta que está na evidência vira outro valor plausível, no mesmo formato;
- afirmacao_sem_base: entra uma frase genérica de atendimento (prazo, taxa, isenção, garantia) sobre o assunto da
  PERGUNTA, no idioma da resposta, com um número que a evidência não tem; nunca em resposta que diz que a fonte não
  cobre o assunto da frase, nem ao lado de frase de ausência ou de valor do mesmo tipo (dito com número ou sem:
  "amanhã", "agendado para 02/12", "não cobra taxa"), e, se a resposta fala do assunto, só numa linha de prosa sobre
  ele (contradizer a própria resposta seria negativo fácil demais: o defeito tem de aparecer só contra a evidência);
- fato_removido: sai a frase (ou as frases) com um fato de referência do caso (expect.facts dos casos).
Os dois primeiros contradizem ou extrapolam a evidência; o terceiro deixa a resposta incompleta, e por isso não é
negativo garantido (sem o fato, a resposta pode continuar servindo: quem rotula decide). Candidata só fica se a
checagem determinística do próprio motor disser que ela ficou errada: o número novo é "sem base" para
app.grounding.unsupported_numbers (nem na evidência, nem na pergunta, nem nos turnos anteriores, nem como soma,
diferença ou contagem) e não acende em amarelo na página; o fato removido falta para run_evals.facts_missing.

Determinístico: seed fixa e linhas ordenadas por id (mesma entrada, mesmo arquivo). Uma cópia por resposta original
(duas variantes da mesma resposta na página entregariam a adulteração). Grava evals/results/perturbed.json
({"rows": [...]}) e nunca um live_*.json: load_rows, as métricas ao vivo e o judge.json da manchete leem só
live_*.json; o juiz das adulteradas grava à parte (python -m evals.judge --perturbed → judge_perturbed.json). Cada
linha leva `original_sha` (id, resposta e contexto da original): uma bateria ao vivo nova muda a original, e a página
recusa misturar cópia de resposta que não é mais a do sistema (stale; regenere com --force).

Uso: python -m evals.perturb [--per-type 10] [--seed 7] [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))  # o src/ desta pasta (worktree de fork), como evals/run_evals.py
RESULTS = HERE / "results"
FILE = "perturbed.json"
SPLIT = "perturbed"
SEP = "~p"  # id da adulterada: f"{id da original}~p{k}", k = posição do tipo em TYPES (1, 2, 3)
TYPES = ("numero_trocado", "afirmacao_sem_base", "fato_removido")
SEED = 7
# A página usa ~5 por tipo; a sobra deixa escolher originais fora da amostra real e que ninguém viu ainda (medido no
# ensaio: com 8 por tipo, 3 das 15 da página vinham de resposta já rotulada; com 10, nenhuma). Custo do juiz: ~30
# chamadas, com canários e gabarito reaproveitados do judge.json.
PER_TYPE = 10
# Splits de ataque: a resposta certa é recusa ou bloqueio; frase ou número enxertado numa recusa não parece resposta.
SKIP_SPLITS = frozenset({"guardrail", "hard"})
# O que a adulterada leva da original: o que o juiz e a página mostram (pergunta, cliente, evidência, fontes,
# ferramentas, idioma esperado). Checagens, custo, rota e números sem base ficam de fora: foram medidos sobre a
# resposta original e mentiriam sobre a adulterada.
KEEP = ("message", "user_id", "context", "evidence", "sources", "source_ids", "tool_calls", "expected_language")

# --- números -------------------------------------------------------------------------------------------------------
# Número solto: nada de letra, hífen, barra, dois-pontos ou colchete colado (ids, datas, horas e citações ficam fora).
_NUMBER = re.compile(r"(?<![\w.,/:\-\[])\d+(?:[.,]\d+)*(?![\w/:\-\]]|[.,]\d)")
_CURRENCY = re.compile(r"(?:R\$|US\$|U\$|€|£|\$)\s?$")
# Formatos aceitos para trocar, do mais específico ao mais geral: (regex, separador decimal, separador de milhar).
_FORMATS = ((r"\d{1,3}(?:\.\d{3})+,\d{1,2}", ",", "."), (r"\d{1,3}(?:,\d{3})+\.\d{1,2}", ".", ","),
            (r"\d+,\d{1,2}", ",", ""), (r"\d+\.\d{1,2}", ".", ""),
            (r"\d{1,3}(?:\.\d{3})+", "", "."), (r"\d{1,3}(?:,\d{3})+", "", ","), (r"\d+", "", ""))


def _parse(token: str) -> tuple[Decimal, int, str, str] | None:
    """(valor, casas decimais, separador decimal, separador de milhar) no formato em que o número foi escrito."""
    for rx, dec, th in _FORMATS:
        if re.fullmatch(rx, token):
            body = token.replace(th, "") if th else token
            places = len(body.rsplit(dec, 1)[1]) if dec else 0
            try:
                return Decimal(body.replace(dec, ".") if dec else body), places, dec, th
            except InvalidOperation:
                return None
    return None


def _format(value: Decimal, places: int, dec: str, th: str) -> str:
    """O valor novo no formato do original ("1.049,90" continua com ponto de milhar e vírgula decimal). Valor com
    decimal que passa de mil ganha o separador de milhar do idioma ("549,90" → "1.099,80", nunca "1099,80", que
    destoaria dos outros valores da mesma resposta)."""
    q = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    whole, _, frac = f"{q:f}".partition(".")
    th = th or {",": ".", ".": ","}.get(dec, "")
    if th:
        whole = f"{int(whole):,}".replace(",", th)
    return whole + (dec + frac if places else "")


def _alternatives(value: Decimal, places: int, rng: random.Random) -> list[Decimal]:
    """Valores plausíveis no lugar do original: mesma escala, mesmas casas, nunca ele. Valor com centavos anda em
    passos redondos (R$ 129,90 → R$ 149,90), que é como um preço errado costuma aparecer; inteiro pequeno, em passos
    de 1 a 10; o resto, por fatores."""
    factors = [Decimal(x) for x in ("1.5", "2", "0.5", "3", "0.75", "4")]
    if places == 2:
        steps = [Decimal(s) * sign for s in (10, 20, 50, 100) for sign in (1, -1)]
    elif places == 0 and value < 100:
        steps = [Decimal(s) for s in (1, 2, 3, 5, 10)]
    else:
        steps = []
    unit = Decimal(1).scaleb(-places)
    out = [(value * f).quantize(unit, rounding=ROUND_HALF_UP) for f in factors] + [value + s for s in steps]
    out = [v for v in dict.fromkeys(out) if v > 0 and v != value]
    rng.shuffle(out)
    return out


def _known(texts: list[str], question: str) -> set[str]:
    from app.grounding import numbers

    return numbers(question).union(*(numbers(t) for t in texts))


def _invented(answer: str, raw: str, texts: list[str], question: str) -> bool:
    """O número `raw` da resposta é sem base para a checagem do motor E não acende em amarelo na página.

    A página destaca na evidência o mesmo texto do número da resposta (rotulagem.html, answerNumbers/hl): um "30"
    dentro de um id ("T30B") acenderia e faria a pessoa achar que o número tem fonte. Por isso as duas conferências.
    """
    from app.grounding import unsupported_numbers

    if raw not in unsupported_numbers(answer, texts, question):
        return False
    lit = re.compile(rf"(?<![\d.,]){re.escape(raw)}(?!\d)")
    return not any(lit.search(t) for t in texts)


def numero_trocado(row: dict, texts: list[str], rng: random.Random) -> tuple[str, dict] | None:
    """Troca um número que a resposta tirou da evidência por outro valor plausível que a evidência não tem.

    Prefere valor (moeda antes ou centavos), depois número de 2+ dígitos: é o erro que custa caro ao cliente."""
    from app.grounding import numbers

    answer, question = row.get("answer") or "", row.get("message") or ""
    evidence = _known(texts, "")
    spots = []
    for m in _NUMBER.finditer(answer):
        token = m.group(0)
        line = answer[answer.rfind("\n", 0, m.start()) + 1:m.start()]
        if not line.strip() and answer[m.end():m.end() + 1] in (".", ")"):
            continue  # marcador de lista ("1. ", "2) ")
        parsed = _parse(token)
        if parsed is None or (parsed[1] == 0 and 1900 <= parsed[0] <= 2100):
            continue  # formato estranho ou ano
        if not numbers(token) & evidence:
            continue  # só troca o que estava certo: número que a evidência sustenta
        money = bool(_CURRENCY.search(answer[max(0, m.start() - 5):m.start()])) or parsed[1] > 0
        spots.append((0 if money else 1 if len(token) >= 2 else 2, m, parsed))
    rng.shuffle(spots)
    spots.sort(key=lambda s: s[0])  # estável: dentro da mesma classe, a ordem sorteada
    for _, m, (value, places, dec, th) in spots:
        for new in _alternatives(value, places, rng):
            raw = _format(new, places, dec, th)
            text = answer[:m.start()] + raw + answer[m.end():]
            if _invented(text, raw, texts, question):
                return text, {"de": m.group(0), "para": raw}
    return None


# --- afirmação sem base ----------------------------------------------------------------------------------------------
class Claim(NamedTuple):
    """Frase genérica de atendimento com um número (é o que torna a falta de base verificável sem LLM).

    `ask`: o assunto na PERGUNTA do cliente, por termos estritos (pt e en); `near`: termos largos do mesmo assunto, que
    com `ask` dizem se a resposta fala dele e qual linha a frase pode receber; `about`: o mais que a própria frase
    afirma (a de garantia fala de troca; a de prazo, de abertura, liberação, data) — a checagem de ausência casa
    `ask`, `near` e `about`; `same`: valor do mesmo tipo do da frase, com número ou sem (taxa: percentual, "sem
    juros", "não cobra taxa", isenção; prazo: duração, D+N, "na hora", "amanhã", "próximo dia útil", data da agenda),
    que nem a linha que recebe a frase nem as vizinhas podem trazer; `values`: os números da frase (vazio = taxa, de
    RATES)."""

    ask: str
    near: str
    about: str
    same: str
    text: dict[str, str]
    values: tuple[int, ...] = ()


# Quantidade com unidade de tempo, em algarismo ou por extenso ("2 dias úteis", "24h", "um dia", "1 business day").
_QTY = (r"(?:\d+(?:[.,]\d+)?|um|uma|dois|duas|tr[êe]s|quatro|cinco|seis|sete|oito|nove|dez|quinze|vinte|trinta"
        r"|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty)\s*(?:(?:business|working|calendar"
        r"|bank)\s+)?")


def _span(units: str) -> str:
    """Quantidade de tempo nas `units`, menos o tempo decorrido ("offline há 5 horas", "nos últimos 7 dias", "2 days
    ago"): isso não é prazo nem duração de benefício, e não barra a linha."""
    return (r"(?<!h[áa] )(?<!faz )(?<![úu]ltimos )(?<![úu]ltimas )(?<!last )(?<!past )"
            rf"\b{_QTY}(?:{units})\b(?!\s+(?:atr[áa]s|ago)\b)")


_MONTHS = _span(r"meses|m[êe]s|months?|anos?|years?")
_DURATION = _span(r"dias?|days?|horas?|hours?|h|minutos?|minutes?|min|semanas?|weeks?|meses|m[êe]s|months?|anos?"
                  r"|years?")
# Prazo sem número também é valor de prazo: "é feita na hora" ao lado de "leva 3 dias úteis" é contradição na cara.
_IMMEDIATE = (r"\bna (?:mesma )?hora\b|\bno mesmo dia\b|\bimediat|\binstant[âa]ne|\bem tempo real\b"
              r"|\bno dia seguinte\b|\bsame[- ]day\b|\bimmediate|\binstant(?:ly)?\b|\bright away\b|\breal[- ]time\b"
              r"|\bnext (?:business )?day\b")
# E o dia dito pelo nome ou pela data da agenda: "cai no próximo dia útil" ou "agendado para 02/12" ao lado de "leva
# 5 dias úteis" é a resposta contra ela mesma. Data com ou sem o ano (a agenda do app mostra "02/12"); "24/7" e "3/4"
# também casam, e só tiram lugar da frase (barrar a mais nunca gera contradição).
_NAMED_DAY = (r"\bpr[óo]xim[oa] dia [úu]til\b|\bdia [úu]til seguinte\b|\bamanh[ãa]\b|\bhoje\b"
              r"|\b(?:next|following) (?:business |working |bank )?day\b|\btomorrow\b|\btoday\b")
_DATE = (r"(?<![\d/])(?:0?[1-9]|[12]\d|3[01])/(?:0?[1-9]|1[0-2])(?:/(?:\d{4}|\d{2}))?(?![\d/])"
         r"|\b\d{4}-\d{2}-\d{2}\b|\bagendad[oa]s? para\b|\bprevist[oa]s? para\b|\bscheduled (?:for|on)\b")
# Taxa negada ou dispensada também é valor de taxa: "não cobra taxa" ao lado de "tem uma taxa de 1,49%" idem.
_NO_FEE = (r"\bn[ãa]o (?:se )?(?:paga|pagam|cobra|cobram|tem|t[êe]m|h[áa])(?: (?:nenhuma|qualquer))?"
           r" (?:taxas?|tarifas?)\b|\b(?:taxas?|tarifas?) nenhuma\b|\bnenhuma (?:taxa|tarifa)\b|\bisen[çc][ãa]o\b"
           r"|\bisent[ao]s?\b|\bexempt\b|\bwaived?\b|\bat no (?:extra )?cost\b|\bno (?:extra )?cost\b"
           r"|\b(?:doesn't|does not|don't|do not|won't|will not) (?:charge|pay|have)(?: (?:any|a))?"
           r" (?:fees?|charges?)\b")


# O assunto sai só da pergunta e por termo estrito: casado também na resposta ou por termo largo ("rate", "receber",
# "price"), o enxerto vira non sequitur (cotação de criptomoeda com "taxa de 1,49% sobre o valor"), negativo fácil
# demais de ver, que nenhum redator produziria e que inflaria o TNR do juiz. Termo de dois sentidos fica de fora:
# "há quanto tempo" / "how long has" é tempo decorrido, não prazo; "cobrança" / "charge" é a conta cobrada, não uma
# taxa sobre o valor. Os números ficam na faixa em que o erro passaria por verdade (prazo de 2 a 15 dias, isenção de
# 3 a 12 meses). `about` é largo de propósito: a resposta que diz que a fonte não cobre a troca ("as fontes não dizem
# se você tem direito a troca") nunca recebe "Há garantia de 18 meses para troca sem custo", que a desmentiria.
CLAIMS = (
    Claim(r"\bprazos?\b|\bquantos dias\b|\bdias? [úu]t(?:il|eis)\b|\bquando (?:cai|caem|chega|libera|liberam)\b"
          r"|\bca(?:i|iu|ir|irá) na (?:minha )?conta\b|\bn[ãa]o caiu\b|(?<!h[áa] )(?<!faz )\bquanto tempo\b|\bdemora"
          r"|\bhow long\b(?!\s+(?:has|have|had|ago)\b)|\bhow many days\b|\bbusiness days?\b|\bdeadlines?\b"
          r"|\bwhen\b[^.?!]{0,60}\b(?:deposit|payout|paid|settle|released?)",
          r"\bprazo|dias? [úu]t|cai na conta|dep[óo]sit|receb[ei]|liquida|antecipa|deadline|business days?|deposit"
          r"|settle|receivabl|advance|payout",
          r"\bprazos?\b|\bquanto tempo\b|\bdemora|\babertura|\babrir\b|\blibera|\bativa[çc][ãa]o|\baprova[çc][ãa]o"
          r"|\bquando\b|\bdatas?\b|\bhow long\b|\bopening\b|\brelease|\bactivation\b|\bapproval\b|\bwhen\b|\bdates?\b",
          rf"{_DURATION}|\bD\s?\+\s?\d+|{_IMMEDIATE}|{_NAMED_DAY}|{_DATE}",
          {"pt": "Esse processo leva {n} dias úteis para ser concluído.",
           "en": "This process takes {n} business days to complete."}, (2, 3, 5, 7, 10, 15)),
    # "monthly fee" é a mensalidade (frase de isenção), não uma taxa sobre o valor
    Claim(r"\btaxas?\b|\btarifas?\b|\bjuros\b|\bmdr\b|(?<!monthly )\bfees?\b|\binterest\b",
          r"\btaxas?\b|tarifa|\bcustos?\b|pre[çc]o|cobran|\bjuros|\bfees?\b|\brates?\b|\bcosts?\b|price|charge"
          r"|interest",
          r"\bcusta\b|\bcobra|\bpercentua|\bpercent",
          # "sem juros", "grátis" e "não cobra taxa" são a taxa dita sem número, como "na hora" é o prazo
          r"\d+(?:[.,]\d+)?\s?%|\bpor cento\b|\bpercent|\bsem (?:juros|taxas?|tarifas?|custos?|cobran[çc]a)\b"
          r"|\btaxa zero\b|\bgr[áa]tis\b|\bgratuit|\bno (?:fees?|interest|charges?)\b|\binterest[- ]free\b"
          rf"|\bfree of charge\b|\bwithout (?:fees?|interest|charges?)\b|\bfee[- ]free\b|{_NO_FEE}",
          {"pt": "Essa operação tem uma taxa de {p}% sobre o valor.",
           "en": "This operation has a fee of {p}% of the amount."}),
    # isenção sem prazo ("fica isento acima de R$ 60 mil") não é valor do mesmo tipo: "também fica isento por 6 meses"
    # soma um benefício, não desmente
    Claim(r"\bmensalidades?\b|\baluguel\b|\bisen[çc][ãa]o\b|\bisent[oa]s?\b|\bassinatura\b|\bmonthly fees?\b"
          r"|\brental\b|\bexempt(?:ion)?\b|\bsubscription\b",
          r"mensalidade|aluguel|isen[çc]|isent|assinatura|monthly|rental|exempt|subscription",
          r"\bgratuit|\bgr[áa]tis\b|\bdescontos?\b|\bfree\b|\bwaive|\bdiscounts?\b",
          _MONTHS,
          {"pt": "Você também fica isento da mensalidade por {n} meses.",
           "en": "You are also exempt from the monthly fee for {n} months."}, (3, 6, 12)),
    Claim(r"\bgarantia\b|\bdefeito|\bquebr(?:ou|ada|ado)\b|\bparou de funcionar\b|\bwarrant(?:y|ies)\b|\bdefect"
          r"|\bbroken\b|\bguarantee|\bstopped working\b",
          r"garantia|defeito|equipamento|aparelho|warranty|defect|equipment|device",
          r"\btroc(?:a|ar|am|as|ada|adas|ado|ados|ou)\b|\bsubstitu|\breposi[çc]|\breparo|\bconsert|\bdevolu"
          r"|\bsem custo\b|\breplac|\brepair|\bswap|\bexchang|\bnew (?:one|machine|terminal|device)\b"
          r"|\bfree of charge\b|\bat no cost\b",
          _span(r"meses|m[êe]s|months?|anos?|years?|dias?|days?"),
          {"pt": "Há garantia de {n} meses para troca sem custo.",
           "en": "There is a warranty of {n} months for a free replacement."}, (6, 12, 18, 24)),
)
RATES = {"pt": ("0,99", "1,49", "2,39", "3,19", "4,99"), "en": ("0.99", "1.49", "2.39", "3.19", "4.99")}
# Pergunta sobre dado de fora (câmbio, cotação, cripto, clima) não recebe frase de serviço: "taxa de câmbio" e
# "exchange rate" não são taxa cobrada, e prazo, mensalidade ou garantia ali não são o assunto.
_EXTERNAL = re.compile(r"c[âa]mbio|cota[çc][ãa]o|\bexchange rates?\b|\bcurrenc(?:y|ies)\b|bitcoin|cripto|crypto"
                       r"|\bptax\b|\bd[óo]lar|\bdollars?\b|\beuros?\b|\bclima\b|weather|temperatura|forecast"
                       r"|previs[ãa]o do tempo", re.IGNORECASE)
# Início de linha que não é prosa: item de lista, título, citação ou tabela.
_NOT_PROSE = re.compile(r"^\s*(?:[-*•]\s|#|>|\||\d+[.)]\s)")
# Menção ao atendimento humano ou a proposta à espera de confirmação: "Se quiser, encaminho você a um atendente" e
# "Só abro se você confirmar" não começam com "posso"/"I can" e escapam do detector de oferta do motor.
_HANDS_OFF = re.compile(r"\b(?:atendentes?|humanos?|human|agents?|agentes?|especialistas?|specialists?)\b"
                        r"|\bpropo|\bpropus|\bconfirm", re.IGNORECASE)
# Ausência que o detector do motor (app.claims.states_absence) não pega e que aqui decide: "As fontes não falam de
# reposição", "The sources don't address it", "no information about". Fica aqui, não no motor: lá ela mudaria o que
# a checagem de frases da resposta considera checável.
_ABSENT_MORE = re.compile(
    r"\bn[ãa]o\s+(?:\w+\s+){0,2}?(?:fal|cit|mencion|trat|detalh|especific|explic|esclarec|abord)(?:a|am|e|em)\b"
    r"|\b(?:doesn't|does not|don't|do not|didn't|did not)\s+(?:\w+\s+){0,1}?(?:address|discuss|talk|state|tell)\b"
    r"|\bno information\b", re.IGNORECASE)


# Frase que retoma o assunto de antes por pronome ("Isso não consta na base", "Não encontrei essa informação", "I
# couldn't find that"): sem assunto próprio, a ausência é a do assunto da frase anterior. Frase de ausência sem pronome
# fala de outra coisa ("As fontes não dizem se outra conta serve") e não barra o assunto vizinho.
_ANAPHORA = re.compile(
    r"\b(?:isso|isto|aquilo)\b|\btal informa[çc][ãa]o\b|\b(?:ess|est|aquel)[ea]s? (?:informa[çc](?:[ãa]o|[õo]es)|dados?"
    r"|pontos?|detalhes?|casos?|regras?|valor(?:es)?|op[çc](?:[ãa]o|[õo]es))\b|\b(?:this|that|these|those|it)\b",
    re.IGNORECASE)


def _absent(text: str) -> bool:
    """O texto diz que a fonte não cobre algo: o detector do motor mais os casos de _ABSENT_MORE."""
    from app.claims import states_absence

    return states_absence(text) or bool(_ABSENT_MORE.search(text))


def _topic(claim: Claim) -> str:
    """Tudo que diz que um texto fala do assunto da frase (o da pergunta, o largo e o que a frase afirma)."""
    return f"{claim.ask}|{claim.near}|{claim.about}"


def _language(row: dict) -> str:
    from evals.run_evals import detect_text_language

    lang = detect_text_language(row.get("answer") or "", 1) or row.get("expected_language") or "pt"
    return lang if lang in RATES else "pt"


def _blocked(line: str) -> bool:
    """Linha depois da qual a frase enxertada leria como apêndice fora de lugar: pergunta, oferece algo (atendente,
    ação, ajuda), propõe ação à espera de confirmação, diz que encaminhou ou fez algo, cita o atendimento humano ou
    diz que a fonte não cobre algo ("as fontes não trazem a taxa aplicada. Essa operação tem uma taxa de 0,99%").
    Oferta pelo detector do motor (app.claims), ausência por _absent, ação alegada pelo app.grounding."""
    from app.claims import offered_action
    from app.grounding import claimed_actions

    return ("?" in line or bool(_HANDS_OFF.search(line)) or _absent(line)
            or offered_action(line, [], False) is not None or bool(claimed_actions(line, [], False, [])))


def _beside(lines: list[str], i: int) -> list[str]:
    """A linha e as vizinhas não vazias, a de antes e a de depois: o que se lê colado à frase enxertada no fim dela.
    Vizinha que é tabela vem inteira (a linha de cabeçalho sozinha não diz nada; o leitor vê a tabela como um bloco)."""

    def table(j: int) -> bool:
        return 0 <= j < len(lines) and lines[j].lstrip().startswith("|")

    out = [lines[i]]
    for step in (-1, 1):
        j = i + step
        while 0 <= j < len(lines) and not lines[j].strip():
            j += step
        if 0 <= j < len(lines):
            out.append(lines[j])
            while table(j) and table(j + step):
                j += step
                out.append(lines[j])
    return out


def _insert(answer: str, sentence: str, claim: Claim, rng: random.Random) -> str | None:
    """A frase entra no fim de uma linha de prosa que termina em ponto e não está bloqueada (_blocked), sorteada entre
    as que servem: lê como parte da resposta e não fica sempre na 1ª linha, onde todo leitor olha. Nunca na linha que
    traz valor do mesmo tipo da frase (`same`) ou diz que a fonte não cobre algo, nem ao lado dela: "taxa de 3,19%"
    logo depois de "começa em 1,69%", ou "leva 5 dias úteis" ao lado de "não encontrei o prazo", é contradição
    colada, negativo fácil demais.

    Se a resposta fala do assunto (`ask` ou `near` em qualquer linha, inclusive item de lista, tabela ou linha
    bloqueada), a frase só entra numa linha de PROSA sobre ele; sem nenhuma que sirva, None: levada para outra linha,
    ela ficaria longe do assunto ("A taxa do débito é de 1,99%. Esse processo leva 5 dias úteis", com o prazo numa
    lista abaixo) e ainda perto do valor que a resposta deu. Só a resposta que não fala do assunto recebe a frase em
    qualquer linha, e nunca se ela traz, em qualquer lugar, valor do mesmo tipo ou frase de ausência (ali, "não
    encontrei essa informação" é sobre o que a pergunta pediu)."""
    lines = answer.split("\n")
    topic, same = re.compile(f"{claim.ask}|{claim.near}", re.IGNORECASE), re.compile(claim.same, re.IGNORECASE)
    prose = [i for i, line in enumerate(lines)
             if line.strip().endswith(".") and not _NOT_PROSE.match(line) and not _blocked(line)]
    clean = [i for i in prose if not any(same.search(t) or _absent(t) for t in _beside(lines, i))]
    if any(topic.search(line) for line in lines):
        spots = [i for i in clean if topic.search(lines[i])]
    elif any(same.search(line) or _absent(line) for line in lines):
        return None
    else:
        spots = clean
    if not spots:
        return None
    i = rng.choice(spots)
    lines[i] = lines[i].rstrip() + " " + sentence
    return "\n".join(lines)


def afirmacao_sem_base(row: dict, texts: list[str], rng: random.Random) -> tuple[str, dict] | None:
    """Enxerta uma frase de prazo, taxa, isenção ou garantia sobre o assunto da pergunta, com número que a evidência
    não tem. Sem assunto compatível na pergunta (ou com pergunta sobre dado de fora), a resposta não recebe este tipo;
    nem a frase cujo assunto (o da pergunta, o da linha e o que a própria frase afirma: `ask`, `near`, `about`) a
    resposta diz que a fonte não cobre: "as fontes não dizem se você tem direito a troca" seguido de "Há garantia de 18
    meses para troca sem custo" contradiria a resposta na cara. Frase de ausência sem assunto próprio que retoma algo
    por pronome (_ANAPHORA) é sobre o assunto da frase de antes ("A troca depende do contrato. Isso não consta na base
    que consultei") ou, se abre a resposta, sobre o que a pergunta pediu."""
    from app.claims import split_sentences

    answer, question = row.get("answer") or "", row.get("message") or ""
    if _EXTERNAL.search(question):
        return None
    lang = _language(row)
    sentences = [s.text for s in split_sentences(answer)]
    absent = []
    for k, text in enumerate(sentences):
        if _absent(text):
            absent.append(text)
            if _ANAPHORA.search(text) and not any(re.search(_topic(c), text, re.IGNORECASE) for c in CLAIMS):
                absent.append(sentences[k - 1] if k else question)  # anáfora: o assunto é o de antes
    claims = [c for c in CLAIMS if re.search(c.ask, question, re.IGNORECASE)
              and not any(re.search(_topic(c), s, re.IGNORECASE) for s in absent)]
    rng.shuffle(claims)
    for claim in claims:
        values = [str(n) for n in claim.values] or list(RATES[lang])
        rng.shuffle(values)
        for raw in values:
            sentence = claim.text[lang].format(n=raw, p=raw)
            text = _insert(answer, sentence, claim, rng)
            if text is None:
                break  # nenhuma linha recebe esta frase (o lugar depende do valor dela): tenta o próximo assunto
            if _invented(text, raw, texts, question):
                return text, {"frase": sentence}
    return None


# --- fato removido ---------------------------------------------------------------------------------------------------
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_BULLET = re.compile(r"^\s*[-*•]\s")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s")


def _units(text: str) -> list[tuple[int, int]]:
    """Trechos removíveis (início, fim): cada frase de cada linha; item de lista é um trecho só (sai inteiro, sem
    deixar marcador órfão)."""
    spans, pos = [], 0
    for line in text.split("\n"):
        if _BULLET.match(line) or _NUMBERED.match(line):
            spans.append((pos, pos + len(line)))
        else:
            last = 0
            for m in _SENTENCE_END.finditer(line):
                spans.append((pos + last, pos + m.start()))
                last = m.end()
            spans.append((pos + last, pos + len(line)))
        pos += len(line) + 1
    return [(a, b) for a, b in spans if text[a:b].strip()]


def _drop(text: str, spans: list[tuple[int, int]]) -> str:
    """Tira os trechos linha a linha: linha que fica vazia sai com a quebra (nada de buraco entre itens de lista);
    parágrafo inteiro que some não deixa duas linhas em branco seguidas."""
    out, pos = [], 0
    for line in text.split("\n"):
        start, end = pos, pos + len(line)
        cuts = sorted(((a - start, b - start) for a, b in spans if a < end and b > start), reverse=True)
        pos = end + 1
        if not cuts:
            out.append(line)
            continue
        for a, b in cuts:
            line = line[:max(a, 0)] + line[b:]
        if line.strip():
            out.append(re.sub(r"[ \t]{2,}", " ", line).rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def remove_fact(answer: str, pattern: str) -> str | None:
    """A resposta sem os trechos em que o fato aparece (o fato pode cruzar frases: sai todo trecho que a ocorrência
    toca, até não sobrar ocorrência); None se o fato não some ou se sairia item de lista numerada (a numeração com
    buraco entregaria a edição, e renumerar mudaria número que pode ser dado, como a opção 4 de um menu)."""
    text = answer
    for _ in range(8):
        m = re.search(pattern, text, re.IGNORECASE)
        if m is None:
            return text
        end = max(m.end(), m.start() + 1)
        hit = [(a, b) for a, b in _units(text) if a < end and b > m.start()]
        if not hit or any(_NUMBERED.match(text[a:b]) for a, b in hit):
            return None
        text = _drop(text, hit)
    return None if re.search(pattern, text, re.IGNORECASE) else text


def fato_removido(row: dict, facts: list[str], rng: random.Random) -> tuple[str, dict] | None:
    """Tira a frase com um fato de referência do caso; a resposta que sobra continua uma resposta (>= 60 caracteres
    e >= 1/4 da original), só que sem o fato que o caso exige."""
    from evals.run_evals import facts_missing

    answer = row.get("answer") or ""
    present = [p for p in facts if not facts_missing({"facts": [p]}, answer)]
    rng.shuffle(present)
    for pattern in present:
        text = remove_fact(answer, pattern)
        if text and text != answer and len(text) >= max(60, len(answer) / 4) \
                and facts_missing({"facts": [pattern]}, text) == [pattern]:
            removed = [s for s in (answer[a:b].strip() for a, b in _units(answer)) if s and s not in text]
            return text, {"fato": pattern, "removido": removed}
    return None


# --- conjunto -------------------------------------------------------------------------------------------------------
def _cases() -> dict[str, dict]:
    from evals.run_evals import load_cases

    try:
        return {c["id"]: c for c in load_cases()}
    except (OSError, ValueError):
        return {}


def original_sha(row: dict) -> str:
    """Impressão digital da original (id, resposta, contexto): a cópia com defeito só vale enquanto a resposta do
    sistema for essa."""
    blob = json.dumps([str(row.get("id")), row.get("answer") or "", str(row.get("context") or "")], ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def stale(rows: list[dict], live: list[dict]) -> list[str]:
    """Adulteradas cuja original mudou ou sumiu das linhas ao vivo desde a geração (bateria nova regrava live_*.json).
    Sem `original_sha` (arquivo de antes da impressão digital) também conta: não há como provar que é a mesma."""
    now = {str(r["id"]): original_sha(r) for r in live}
    return [r["id"] for r in rows
            if not r.get("original_sha") or now.get(str(r.get("original_id"))) != r["original_sha"]]


def _row(orig: dict, kind: str, answer: str, detail: dict) -> dict:
    return {"id": f"{orig['id']}{SEP}{TYPES.index(kind) + 1}", "split": SPLIT, "run": 0,
            **{k: orig[k] for k in KEEP if k in orig}, "answer": answer,
            "perturbation": kind, "perturbation_detail": detail,
            "original_id": orig["id"], "original_split": orig.get("split"), "original_sha": original_sha(orig)}


def _order(rows: list[dict], seed: int) -> list[dict]:
    """Ordem de tentativa: um split por vez (a adulteração se espalha pelos splits) e, dentro dele, primeiro as
    respostas que passaram nas checagens automáticas (o defeito da cópia é só o enxertado)."""
    from evals.label import auto_pass

    rng = random.Random(seed)
    by_split: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["id"]):
        by_split[str(r.get("split", "?"))].append(r)
    for lst in by_split.values():
        rng.shuffle(lst)
        lst.sort(key=lambda r: not auto_pass(r))
    out: list[dict] = []
    while any(by_split.values()):
        for split in sorted(by_split):
            if by_split[split]:
                out.append(by_split[split].pop(0))
    return out


def generate(rows: list[dict], cases: dict[str, dict] | None = None, per_type: int = PER_TYPE,
             seed: int = SEED) -> list[dict]:
    """Até `per_type` adulteradas de cada tipo, uma por original. O tipo com menos respostas que o aceitam escolhe
    primeiro, contado nesta entrada: a afirmação sem base só cabe em pergunta com assunto de serviço e linha sem valor
    do mesmo tipo; o fato removido, em caso com expect.facts; o número trocado, em quase toda resposta com número da
    evidência. Numa ordem fixa, o tipo raro perderia para outro a original que só ele aceita.

    Fora: resposta sem `context` (o juiz leria trechos do índice que a conferência daqui não vê), bloqueada, que
    quebrou ou que passou para um humano (frase enxertada num "encaminhei para um atendente" não parece resposta)."""
    cases = _cases() if cases is None else cases
    pool = [r for r in rows if r.get("answer") and r.get("context") and r.get("split") not in SKIP_SPLITS
            and str(r.get("run", 0)) in ("0", "") and not r.get("blocked") and not r.get("crash")
            and not r.get("handoff_required") and SEP not in str(r["id"])]
    order = _order(pool, seed)
    made: dict[str, dict[str, tuple[str, dict]]] = {kind: {} for kind in TYPES}
    for r in order:
        case = cases.get(r["id"]) or {}
        texts = [t for t in [str(r.get("context") or ""), *map(str, r.get("evidence") or []),
                             *map(str, case.get("before") or [])] if t]
        for kind in TYPES:  # semente própria de cada (resposta, tipo): o resultado não depende da ordem
            rng = random.Random(f"{seed}:{r['id']}:{kind}")
            if kind == "fato_removido":
                got = fato_removido(r, list((case.get("expect") or {}).get("facts") or []), rng)
            elif kind == "numero_trocado":
                got = numero_trocado(r, texts, rng)
            else:
                got = afirmacao_sem_base(r, texts, rng)
            if got:
                made[kind][r["id"]] = got
    used: set[str] = set()
    out = []
    for kind in sorted(TYPES, key=lambda k: (len(made[k]), TYPES.index(k))):
        picked = [r for r in order if r["id"] in made[kind] and r["id"] not in used][:per_type]
        used |= {r["id"] for r in picked}
        out += [_row(r, kind, *made[kind][r["id"]]) for r in picked]
    return sorted(out, key=lambda r: r["id"])


def rows_sha(rows: list[dict]) -> str:
    """Impressão digital das adulteradas (id + resposta): veredito e rótulo só valem para a versão que viram."""
    blob = json.dumps(sorted((str(r["id"]), r.get("answer") or "") for r in rows), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def load(results: Path = RESULTS) -> list[dict]:
    try:
        return json.loads((results / FILE).read_text(encoding="utf-8")).get("rows") or []
    except (OSError, ValueError):
        return []


def build(results: Path = RESULTS, per_type: int = PER_TYPE, seed: int = SEED,
          cases: dict[str, dict] | None = None, write_empty: bool = True) -> dict:
    """Gera das linhas ao vivo (1ª rodada, evals.label.load_rows) e grava evals/results/perturbed.json. Com
    `write_empty=False`, conjunto vazio não é gravado: um arquivo vazio de antes do ao vivo travaria a geração
    depois (o arquivo que existe nunca é regerado sem --force)."""
    from evals.label import load_rows

    live = load_rows(results)
    rows = generate(live, cases, per_type, seed)
    report = {"generated_by": "evals.perturb", "seed": seed, "per_type": per_type, "types": list(TYPES),
              "por_tipo": {t: sum(r["perturbation"] == t for r in rows) for t in TYPES},
              "linhas_ao_vivo": len(live), "sha": rows_sha(rows), "rows": rows}
    if rows or write_empty:
        results.mkdir(parents=True, exist_ok=True)
        (results / FILE).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def ensure(results: Path = RESULTS, per_type: int = PER_TYPE, seed: int = SEED) -> list[dict]:
    """As adulteradas gravadas; gera só se o arquivo faltar. Regerar por cima trocaria respostas que alguém pode já
    ter rotulado (o relatório confere a resposta rotulada com a gravada e descarta a que mudou)."""
    if (results / FILE).exists():
        return load(results)
    return build(results, per_type, seed, write_empty=False)["rows"]


def pick(rows: list[dict], n: int, seed: int = SEED, exclude_originals: set[str] | frozenset = frozenset(),
         exclude: set[str] | frozenset = frozenset(), avoid_originals: set[str] | frozenset = frozenset(),
         salt: str | None = None) -> list[dict]:
    """Até n adulteradas para a página: um tipo por vez, em rodízio; no máximo uma por original; nunca de original
    que já está na amostra (as duas lado a lado entregariam a troca) nem id em `exclude` (a página passa sempre as
    que as pessoas dela já rotularam: a 2ª vez da mesma adulterada não é rótulo independente). Originais em
    `avoid_originals` (já vistas por alguém) só entram se faltar: quem viu a certa reconheceria a diferença.
    `salt`: o sal da página (evals.label.new_salt) entra no sorteio: com a seed só, quem tem o código e
    perturbed.json refaria quais adulteradas entraram."""
    rng = random.Random(f"{seed}:{salt}:pick" if salt else f"{seed}:pick")
    by_type: dict[str, list[dict]] = {t: [] for t in TYPES}
    for r in sorted(rows, key=lambda r: str(r["id"])):
        if r.get("perturbation") in by_type and r.get("original_id") not in exclude_originals \
                and r["id"] not in exclude:
            by_type[r["perturbation"]].append(r)
    for lst in by_type.values():
        rng.shuffle(lst)
        lst.sort(key=lambda r: r.get("original_id") in avoid_originals)
    out: list[dict] = []
    used: set[str] = set()
    while len(out) < n and any(by_type.values()):
        for kind in TYPES:
            lst = by_type[kind]
            while lst and lst[0].get("original_id") in used:
                lst.pop(0)
            if lst and len(out) < n:
                r = lst.pop(0)
                used.add(str(r.get("original_id")))
                out.append(r)
    return out


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # console cp1252 do Windows quebra acentos
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-type", type=int, default=PER_TYPE, help="adulteradas por tipo (no máximo)")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--force", action="store_true",
                    help="regera por cima (rótulo e veredito da versão anterior deixam de valer)")
    args = ap.parse_args(argv)
    from evals.label import load_rows

    if (RESULTS / FILE).exists() and not args.force:
        rows = load(RESULTS)
        # quantas saíram de resposta que mudou (nunca quais): com alguma, a página recusa até regerar com --force
        print(json.dumps({"arquivo": str(RESULTS / FILE), "linhas": len(rows), "ja_existia": True,
                          "desatualizadas": len(stale(rows, load_rows(RESULTS)))}, ensure_ascii=False))
        return 0
    if not load_rows(RESULTS):
        print("ERRO: sem linhas ao vivo em evals/results/live_*.json: rode o ao vivo antes", file=sys.stderr)
        return 2
    report = build(RESULTS, args.per_type, args.seed)
    # só contagens: quem roda pode ser quem rotula, e a página não diz qual resposta é adulterada
    print(json.dumps({"arquivo": str(RESULTS / FILE), "linhas": len(report["rows"]), "por_tipo": report["por_tipo"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
