"""Checagem numérica determinística da resposta: todo número precisa aparecer na evidência ou na pergunta.

Evidência = texto das fontes citadas, resultado bruto das tools e textos de template dos agentes. A checagem não
usa LLM: pega preço, prazo ou valor inventado mesmo quando o juiz aprova a resposta. Ela BLOQUEIA
(pipeline._enforce): 1 reescrita com a lista dos números proibidos quando há LLM; se persistir, NUMBERS_POLICY
(redact: "[valor não confirmado]" + oferta de humano; escalate: idem + caso aberto; flag: só sinaliza). Soma,
diferença e contagem sustentadas pela evidência passam (ver _Derived).

Formatos equivalentes viram o mesmo número: "R$ 79,90" = "79.9", "1.234,56" = "1234.56", "2,5%" = "2.5".
Com vírgula E ponto, o último separador é o decimal: "5,000.00" (en) = "5.000,00" (pt) = 5000. Só vírgula em
grupos de 3 ("5,000") vale pelas duas leituras (5 e 5000): o idioma da resposta não diz qual é.
Datas são um número só: "30/10/2026" = "2026-10-30"; "03/11" casa com qualquer data da evidência no mesmo dia
e mês; "10/30/2026" (mm/dd) vale quando a ordem só tem uma leitura possível. Dia, mês e ano de uma data da
evidência também contam sozinhos ("Oct 30"). Escala por extenso: "5 mil" vale 5 ou 5000. Número só por
extenso ("cinco mil") não tem dígito e não é conferido: a checagem nunca marca o que não está em dígitos.
Não são número: marcadores de citação "[1]", itens de lista "1." / "2)" no início da linha e dígitos colados
em letras (protocolo "T-f70e7d6e", id "a1b2c3"). "9h" e "3x" contam como 9 e 3.
Medido ao vivo: data dd/mm contra ISO e "R$ 5,000.00" eram os falsos positivos do eval ao vivo.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .llm import LLMError, get_llm

_CITATION = re.compile(r"\[\d+\]")
_LIST_MARK = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
# dígitos não colados em letra/hífen antes; depois, nem letra/hífen, exceto um sufixo h, x ou %
# "R$ 80mil" (sem espaço, como no site da Getnet) também é número: a escala colada entra pelo lookahead
_NUM = re.compile(r"(?<![\w-])\d+(?:[.,]\d+)*(?:(?![\w-])|(?=[hx%](?![\w]))"
                  r"|(?=(?:mil|milh|bilh|thousand|million|billion)\w*\b))", re.IGNORECASE)
_THOUSANDS = re.compile(r"\d{1,3}(?:\.\d{3})+")
_EN_THOUSANDS = re.compile(r"\d{1,3}(?:,\d{3})+")
_ISO_DATE = re.compile(r"(?<![\w-])(\d{4})-(\d{1,2})-(\d{1,2})(?=T\d|[^\w-]|$)")
_SLASH_DATE = re.compile(r"(?<![\w/])(\d{1,2})/(\d{1,2})(?:/(\d{4}|\d{2}))?(?![\w/])")
_SCALE = re.compile(r"\s*(mil|milh(?:ão|ões|ao|oes)|bilh(?:ão|ões|ao|oes)|thousand|million|billion)\b",
                    re.IGNORECASE)
_FULL_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# por prefixo, do mais longo ao mais curto: "milhões" começa com "mil" e não é mil
_SCALES = {"milh": 10**6, "million": 10**6, "bilh": 10**9, "billion": 10**9, "mil": 1000, "thousand": 1000}


@dataclass
class _Item:
    raw: str  # como está escrito no texto (é o que a checagem devolve)
    values: set[str]  # leituras possíveis; basta uma estar na evidência
    parts: tuple[str, ...] = ()  # dia e mês de "dd/mm" sem ano: soltos na evidência também sustentam


def _decimal(token: str) -> str | None:
    try:
        return format(Decimal(token).normalize(), "f")
    except InvalidOperation:
        return None


def _readings(token: str) -> set[str]:
    if "," in token and "." in token:  # os dois: o último separador é o decimal
        decimal_sep = "," if token.rfind(",") > token.rfind(".") else "."
        thousands = "." if decimal_sep == "," else ","
        cands = [token.replace(thousands, "").replace(decimal_sep, ".")]
    elif "," in token:  # pt-BR: vírgula é decimal; "5,000" também pode ser milhar en
        cands = [token.replace(",", ".")]
        if _EN_THOUSANDS.fullmatch(token):
            cands.append(token.replace(",", ""))
    elif _THOUSANDS.fullmatch(token):
        cands = [token.replace(".", "")]
    else:
        cands = [token]
    return {v for v in map(_decimal, cands) if v is not None}


def _date(year: int, month: int, day: int) -> str | None:
    return f"{year:04d}-{month:02d}-{day:02d}" if 1 <= month <= 12 and 1 <= day <= 31 else None


def _slash_values(a: str, b: str, year: str | None) -> set[str]:
    y = None if year is None else int(year) + (2000 if len(year) == 2 else 0)
    out = set()
    for day, month in ((int(a), int(b)), (int(b), int(a))):  # dd/mm (pt) e mm/dd (en); data impossível cai
        if 1 <= month <= 12 and 1 <= day <= 31:
            out.add(_date(y, month, day) if y is not None else f"--{month:02d}-{day:02d}")
    return out


# Data e hora ISO das tools ("2026-11-03T09:16:00"): o "T" colava na hora e o "09" não era lido como número; a resposta
# "às 09:16" virava "às [valor não confirmado]:16" (casos memory-07/08, nas 3 rodadas).
_ISO_T = re.compile(r"(\d{4}-\d{2}-\d{2})T(?=\d)")
# Número dentro de identificador da tool ("last_7_days", "d_plus_30"): o "_" colava o número na palavra e a resposta
# "últimos 7 dias" virava tarja (heldout H1-29/35/37 ao vivo).
_SNAKE_NUM = re.compile(r"(?<=[A-Za-z])_(\d+)(?=_|\b)")


def _items(text: str) -> list[_Item]:
    text = _SNAKE_NUM.sub(r" \1 ", _ISO_T.sub(r"\1 ", _LIST_MARK.sub(" ", _CITATION.sub(" ", text))))
    items: list[_Item] = []

    def take_date(m: re.Match, values: set[str]) -> str:
        # "24/7" ou "1/3" também casam o padrão sem ano: aí dia e mês soltos na evidência bastam (regra antiga).
        # Data com ano só vale inteira: 30, 10 e 2026 vindos de datas diferentes não sustentam "30/10/2026".
        no_year = m.re is _SLASH_DATE and m.group(3) is None
        parts = tuple(_decimal(g) for g in m.groups()[:2]) if no_year else ()
        items.append(_Item(m.group(0), values, parts))
        return " " * len(m.group(0))  # some da busca de número, sem colar vizinhos

    def iso(m: re.Match) -> str:
        full = _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return take_date(m, {full} if full else set())

    text = _ISO_DATE.sub(iso, text)
    text = _SLASH_DATE.sub(lambda m: take_date(m, _slash_values(*m.groups())), text)
    for m in _NUM.finditer(text):
        values = _readings(m.group(0))
        scale = _SCALE.match(text, m.end())
        if scale and values:
            word = scale.group(1).lower()
            mult = next(v for k, v in _SCALES.items() if word.startswith(k))
            values |= {_decimal(str(Decimal(v) * mult)) for v in values} - {None}
        items.append(_Item(m.group(0), values))
    return items


def numbers(text: str) -> set[str]:
    """Tudo o que o texto sustenta: leituras dos números e, de cada data inteira, "--mm-dd", dia, mês e ano."""
    out: set[str] = set()
    for item in _items(text):
        out |= item.values
        out.update(p for p in item.parts if p is not None)
        for v in item.values:
            if _FULL_DATE.fullmatch(v):
                year, month, day = v.split("-")
                out |= {f"--{month}-{day}", *(_decimal(x) for x in (year, month, day))}
    return out


# --- números derivados: soma/diferença e contagem que a evidência sustenta -----------------------------------------
# Medido (memória ao vivo, números 64%): "o total das 4 vendas é R$ 1.250,00" era acusado embora as 4 vendas
# estivessem no resultado da tool. Aceita, SÓ a partir de números da evidência (nunca da pergunta):
# - soma de 2..N números (todos os subconjuntos se houver até MAX_SUBSET operandos distintos; acima disso, pares e o
#   total de cada campo numérico de uma lista JSON, ex. a soma de "amount" de todas as vendas);
# - diferença de 2 números (valor bruto − taxa = líquido);
# - com tolerância de 1 centavo (arredondamento), e só para alvo com cara de valor: centavos escritos ("49,90") ou
#   moeda antes ("R$ 300"). Medido em 177 respostas ao vivo: "20" (°C) virava soma por acaso sem essa trava.
#   Prazo pequeno ("2 dias" de "3 a 5 dias": 5 − 3) NUNCA vira derivado: segue sinalizado;
# - contagem pequena (inteiro 1..50) quando alguma lista JSON da evidência tem exatamente esse tamanho ("4 vendas").
# Operandos: números da evidência que não são data nem ano (1900..2100).
MAX_SUBSET = 16
_CENTS = re.compile(r"[.,]\d{2}$")


def _cents(value: str) -> int | None:
    try:
        return int((Decimal(value) * 100).to_integral_value())
    except InvalidOperation:
        return None


def _operands(evidence: list[str]) -> list[int]:
    out: set[int] = set()
    for e in evidence:
        for item in _items(e):
            if item.parts or any(_FULL_DATE.fullmatch(v) or v.startswith("--") for v in item.values):
                continue
            for v in item.values:
                c = _cents(v)
                if c is not None and c != 0 and not (190000 <= c <= 210000 and c % 100 == 0):
                    out.add(c)
    return sorted(out)


def _json_lists(evidence: list[str]) -> tuple[set[int], list[list[int]]]:
    """Tamanhos das listas JSON da evidência e, por lista de objetos, os valores de cada campo numérico."""
    sizes: set[int] = set()
    columns: list[list[int]] = []

    def walk(node) -> None:
        if isinstance(node, list):
            sizes.add(len(node))
            dicts = [x for x in node if isinstance(x, dict)]
            for key in {k for d in dicts for k in d}:
                vals = [d[key] for d in dicts if isinstance(d.get(key), (int, float)) and not isinstance(d[key], bool)]
                if len(vals) >= 2:
                    columns.append([_cents(str(v)) or 0 for v in vals])
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            for x in node.values():
                walk(x)

    for e in evidence:
        start = e.find("{") if e.find("{") >= 0 else e.find("[")
        try:
            walk(json.loads(e[start:]) if start >= 0 else None)
        except (ValueError, TypeError):
            continue
    return sizes, columns


class _Derived:
    """Somas, diferenças e contagens que a evidência sustenta (calculadas uma vez por checagem, sob demanda)."""

    def __init__(self, evidence: list[str]) -> None:
        self.evidence = evidence
        self._sums: set[int] | None = None
        self._sizes: set[int] = set()

    def _build(self) -> set[int]:
        ops = _operands(self.evidence)
        sizes, columns = _json_lists(self.evidence)
        self._sizes = sizes
        sums: set[int] = {sum(col) for col in columns}
        if len(ops) <= MAX_SUBSET:
            one: set[int] = set()
            many: set[int] = set()
            for x in ops:
                many |= {a + x for a in one | many}
                one.add(x)
            sums |= many
        else:
            sums |= {a + b for i, a in enumerate(ops) for b in ops[i + 1:]}
        sums |= {abs(a - b) for i, a in enumerate(ops) for b in ops[i + 1:]}
        return sums

    def supports(self, item: _Item, money: bool) -> bool:
        if self._sums is None:
            self._sums = self._build()
        for v in item.values:
            c = _cents(v)
            if c is None or _FULL_DATE.fullmatch(v):
                continue
            if "." not in v and 1 <= c // 100 <= 50 and c % 100 == 0 and c // 100 in self._sizes:
                return True  # contagem: "4 vendas" e a tool devolveu a lista com 4
            near = any(s in self._sums for s in (c - 1, c, c + 1))  # tolerância de 1 centavo
            if (money or _CENTS.search(item.raw)) and near:
                return True
        return False


_MONTHS = (r"jan(?:eiro|uary)?|fev(?:ereiro)?|feb(?:ruary)?|mar(?:ço|co|ch)?|abr(?:il)?|apr(?:il)?|mai(?:o)?|may|"
           r"jun(?:ho|e)?|jul(?:ho|y)?|ago(?:sto)?|aug(?:ust)?|set(?:embro)?|sep(?:tember)?|out(?:ubro)?|oct(?:ober)?|"
           r"nov(?:embro|ember)?|dez(?:embro)?|dec(?:ember)?")


def is_calendar_day(raw: str, answer: str, today=None) -> bool:
    """Dia do mês de ontem, hoje ou amanhã escrito junto do nome do mês ("3 de novembro", "November 3"): o redator
    recebe a data de hoje (agents._today), então não é número inventado. Medido (pergunta de clima): a resposta
    saiu "tomorrow, [unconfirmed value] November" — o dia virou tarja na frente do lojista. Número solto não conta."""
    import datetime as _dt

    if not raw.isdigit():
        return False
    from . import clock

    base = today or clock.today()
    days = [base + _dt.timedelta(days=d) for d in (-1, 0, 1)]
    n = re.escape(raw)
    # "Nov 4, 2026" / "4 de novembro de 2026": o ano da data de ontem/hoje/amanhã escrito logo depois do dia e mês
    if int(raw) in {d.year for d in days}:
        dated = "|".join(str(d.day) for d in days)
        year_after = (rf"\b(?:{_MONTHS})\.?\s+(?:{dated})(?:st|nd|rd|th)?,?\s+{n}\b"
                      rf"|\b(?:{dated})\s+(?:de\s+)?(?:{_MONTHS})\.?,?\s+(?:de\s+)?{n}\b")
        return re.search(year_after, answer, re.IGNORECASE) is not None
    if int(raw) not in {d.day for d in days}:
        return False
    day_month = rf"(?<![\d,.])\b{n}(?:st|nd|rd|th)?\s+(?:de\s+)?(?:{_MONTHS})\b"
    month_day = rf"\b(?:{_MONTHS})\.?\s+{n}\b(?![\d.]|,\d)"
    return re.search(f"{day_month}|{month_day}", answer, re.IGNORECASE) is not None


def unsupported_numbers(answer: str, evidence: list[str], question: str = "", derived: bool = True) -> list[str]:
    """Números da resposta que não aparecem na evidência nem na pergunta, como escritos na resposta, sem repetir.

    derived=True (padrão) também aceita soma/diferença/contagem sustentada pela evidência (ver _Derived). Datas de
    ontem/hoje/amanhã junto do nome do mês contam como conhecidas (is_calendar_day).
    """
    known = numbers(question).union(*(numbers(e) for e in evidence))
    calc = _Derived(evidence) if derived else None
    out: list[str] = []
    for item in _items(answer):
        if not item.values and not item.parts:
            continue
        supported = bool(item.values & known) or (bool(item.parts) and set(item.parts) <= known)
        if not supported and calc is not None and not item.parts:
            money = re.search(rf"(?:R\$|US\$|U\$|€|£|\$)\s?{re.escape(item.raw)}(?![\d])", answer) is not None
            supported = calc.supports(item, money)
        if not supported and is_calendar_day(item.raw, answer):
            supported = True
        if not supported and item.raw not in out:
            out.append(item.raw)
    return out


# --- política para número sem base: flag | redact | escalate ---------------------------------------------------------
UNCONFIRMED = {"pt": "[valor não confirmado]", "en": "[unconfirmed value]"}
OFFER = {"pt": "Não consegui confirmar um dos valores; posso encaminhar para um atendente humano confirmar.",
         "en": "I couldn't confirm one of the values; I can hand this to a human agent to confirm it."}
_SUFFIX = r"(?:\s?%|[hx](?!\w)|\s?(?:mil\w*|milh\w*|bilh\w*|thousand|million|billion)\b)?"
_CURRENCY = r"(?:(?:R\$|US\$|U\$|€|£|\$)\s?)?"


def numbers_policy() -> str:
    """NUMBERS_POLICY: flag (só sinaliza) | redact (padrão) | escalate (troca e abre caso humano)."""
    value = os.getenv("NUMBERS_POLICY", "redact").lower()
    return value if value in ("flag", "redact", "escalate") else "redact"


def redact(answer: str, raws: list[str], language: str) -> str:
    """Troca cada número sem base (com moeda, % e escala colados) por "[valor não confirmado]"."""
    mark = UNCONFIRMED.get(language, UNCONFIRMED["pt"])
    for raw in sorted(set(raws), key=len, reverse=True):
        pattern = rf"{_CURRENCY}(?<![\w.,/]){re.escape(raw)}{_SUFFIX}(?![\w]|[.,/]\d)"
        answer = re.sub(pattern, mark, answer)
    return answer


# --- risco de fintech na saída: promessa e compromisso que a fonte não sustenta ------------------------------------
# Espelha a solução pública "Buzz" (Agent Swarm): promessa financeira, compromisso legal e garantia são os erros mais
# caros no atendimento de pagamentos. Sinaliza e mede (como os números): bloquear derrubaria resposta certa.
_RISK = {
    "promessa_financeira": re.compile(
        r"\b(garant(o|imos|ido|ida|ia)|com certeza (vai|cai|ser[áa])|sem (nenhum )?risco|100% (seguro|garantido)"
        r"|guarantee[ds]?|you will (definitely|certainly)|risk[- ]free|we promise|prometemos)\b", re.IGNORECASE),
    "compromisso_legal": re.compile(
        r"\b(isento de (multa|tarifa|responsabilidade)|n[ãa]o (h[áa]|haver[áa]) cobran[çc]a|reembolso integral"
        r"|full refund|no fees? (will|ever)|legalmente obrigad[oa]|legally (required|bound))\b", re.IGNORECASE),
}


def risk_flags(answer: str, evidence: list[str]) -> list[str]:
    """Rótulos de risco cuja frase aparece na resposta e NÃO aparece na evidência do turno. [] = nada a revisar."""
    support = " ".join(evidence)
    out = []
    for label, pattern in _RISK.items():
        said = {m.group(0).lower() for m in pattern.finditer(answer)}
        backed = {m.group(0).lower() for m in pattern.finditer(support)}
        if said - backed:
            out.append(label)
    if date_promises(answer, evidence):
        out.append("promessa_data")
    return out



# --- promessa de data futura sem base --------------------------------------------------------------------------------
# "O valor vai cair amanhã", "will be credited by Friday": dinheiro/entrega com data futura. Passa só se o tempo dito
# está na evidência ("em 2 dias úteis" com fonte "em até 2 dias úteis": os números batem) ou a palavra relativa
# ("amanhã") está lá. Clima não entra: os verbos são de dinheiro, entrega e caso.
_WEEKDAYS = (r"segunda|ter[çc]a|quarta|quinta|sexta|s[áa]bado|domingo|monday|tuesday|wednesday|thursday|friday"
             r"|saturday|sunday")
_PROMISE = re.compile(
    r"\b(?:vai|v[ãa]o|ir[áa]|ir[ãa]o|ser[áa]|ser[ãa]o|deve(?:r[áa])?|will|should|is going to|are going to)\s+"
    r"(?:(?:ser|estar|be|get|have been)\s+)?"
    r"(?:cair|creditad[oa]s?|chegar|liberad[oa]s?|depositad[oa]s?|estornad[oa]s?|reembolsad[oa]s?|pag[oa]s?"
    r"|resolvid[oa]s?|entregue|arrive|credited|released|deposited|refunded|paid|resolved|land|delivered)\b"
    r"[^.!?\n]{0,40}?\b(?P<when>amanh[ãa]|hoje|tomorrow|today|(?:at[ée] |no |na |by |on )?(?:o dia |dia |the )?\d{1,2}"
    r"(?:/\d{1,2}(?:/\d{2,4})?)?(?: de \w+)?|em \d+ (?:dias?|horas?)(?: [úu]teis)?|within \d+ (?:business )?"
    r"(?:days?|hours?)|in \d+ (?:business )?(?:days?|hours?)|(?:at[ée] |by |on |na |no )(?:" + _WEEKDAYS + r"))",
    re.IGNORECASE)
_FOLD_TABLE = str.maketrans("áãâàéêíóôõúç", "aaaaeeiooouc")


def date_promises(answer: str, evidence: list[str]) -> list[str]:
    """Frases de promessa de data (dinheiro/entrega/caso) cujo prazo não está na evidência."""
    support = " ".join(evidence).lower().translate(_FOLD_TABLE)
    known = numbers(" ".join(evidence))
    out = []
    for m in _PROMISE.finditer(answer):
        when = m.group("when").lower().translate(_FOLD_TABLE)
        nums = numbers(when)
        backed = (bool(nums) and nums <= known) or (not nums and re.search(rf"\b{re.escape(when)}\b", support))
        if not backed:
            out.append(m.group(0))
    return out


# --- ação alegada sem execução ---------------------------------------------------------------------------------------
# "Reiniciei sua maquininha", "abri o chamado", "estornei", "I restarted", "refund issued": o agente diz que FEZ algo
# que nenhuma tool fez neste turno. Cada categoria tem a frase (1ª pessoa no passado, ou passiva de conclusão) e o
# que conta como execução: tool_call ok cujo nome casa a categoria (ação pendente de confirmação NÃO conta) ou, para
# chamado, o handoff com protocolo. Frase copiada da evidência (política "liberamos em 2 dias") também passa.
# Negação logo antes ("não cancelei", "I haven't") não é alegação.
_I = r"(?:i|we)(?:'ve| have)?\s+(?:just\s+|already\s+)?"
_CLAIMS: dict[str, tuple[re.Pattern, re.Pattern]] = {
    "restart": (re.compile(rf"\b(?:reiniciei|reiniciamos|resetei|resetamos|{_I}(?:restarted|rebooted|reset))\b",
                           re.IGNORECASE), re.compile(r"restart|reboot|reset|reinici", re.IGNORECASE)),
    "ticket": (re.compile(rf"\b(?:(?:abri|abrimos|registrei|registramos|criei|criamos)\s+(?:\w+\s+){{0,2}}?"
                          r"(?:chamado|protocolo|ticket|caso|solicita[çc][ãa]o|reclama[çc][ãa]o)"
                          rf"|encaminhei|encaminhamos|{_I}(?:opened|created|filed|raised|escalated|logged)\s+"
                          r"(?:\w+\s+){0,2}?(?:ticket|case|request|complaint)"
                          r"|(?:transferi|passei|transferimos)\s+(?:\w+\s+){0,3}?para (?:um |uma |o |a )?"
                          r"(?:atendente|humano)"
                          rf"|{_I}(?:passed|handed|forwarded|transferred)\s+(?:\w+\s+){{0,3}}?to (?:a |an |the )?"
                          r"(?:human|agent|specialist|team)"
                          r"|ticket (?:has been |was )?(?:opened|created))\b", re.IGNORECASE),
               re.compile(r"ticket|escalat|handoff|chamado|caso", re.IGNORECASE)),
    "refund": (re.compile(rf"\b(?:estornei|estornamos|reembolsei|reembolsamos|{_I}refunded"
                          r"|refund (?:has been |was )?(?:issued|processed|completed)"
                          r"|estorno (?:foi )?(?:realizado|efetuado|feito|conclu[ií]do))\b", re.IGNORECASE),
               re.compile(r"refund|estorn|reembols|chargeback", re.IGNORECASE)),
    "cancel": (re.compile(rf"\b(?:cancelei|cancelamos|{_I}cancell?ed)\b", re.IGNORECASE),
               re.compile(r"cancel", re.IGNORECASE)),
    "change": (re.compile(rf"\b(?:alterei|atualizei|bloqueei|desbloqueei|liberei|antecipei|ativei|desativei"
                          rf"|{_I}(?:updated|changed|blocked|unblocked|released|activated|deactivated|anticipated))\b",
                          re.IGNORECASE),
               re.compile(r"update|change|alter|block|bloq|release|liber|anticip|antecip|activat|ativ",
                          re.IGNORECASE)),
}
_NEGATION = re.compile(r"(?:\bn[ãa]o|\bnunca|\bainda n[ãa]o|\bnot|n't|\bnever)\s+(?:\w+\s+){0,2}$", re.IGNORECASE)


def claimed_actions(answer: str, tool_calls: list, ticket: bool, evidence: list[str]) -> list[str]:
    """Frases do texto que alegam ação sem execução no turno (como escritas). [] = nada alegado sem base."""
    support = " ".join(evidence).lower()
    executed = [c.name for c in tool_calls if getattr(c, "ok", False)]
    out: list[str] = []
    for category, (said, done) in _CLAIMS.items():
        if (category == "ticket" and ticket) or any(done.search(name) for name in executed):
            continue
        for m in said.finditer(answer):
            if _NEGATION.search(answer[max(0, m.start() - 30):m.start()]) or m.group(0).lower() in support:
                continue
            out.append(m.group(0))
    return out


_SENTENCE = re.compile(r"[^.!?\n]*[.!?]?")
NOT_DONE = {"pt": "Atenção: essa ação ainda não foi executada nesta conversa; se quiser, posso encaminhar para um "
                  "atendente humano.",
            "en": "Note: that action has not been carried out in this conversation; I can hand this to a human "
                  "agent if you'd like."}


def drop_claims(answer: str, claims: list[str], language: str) -> str:
    """Último recurso (sem LLM ou a reescrita insistiu): tira as frases com a alegação e diz que nada foi feito."""
    kept = [s for s in _SENTENCE.findall(answer) if s.strip() and not any(c in s for c in claims)]
    body = " ".join(s.strip() for s in kept).strip()
    note = NOT_DONE.get(language, NOT_DONE["pt"])
    return f"{body}\n\n{note}" if body else note

# --- reescrita única (com LLM): números proibidos, ação alegada, idioma ---------------------------------------------
LANGUAGE_NAME = {"pt": "português do Brasil", "en": "English"}
DIRECTIVE = {"pt": "Responda estritamente em português do Brasil, mesmo que os trechos, as ferramentas ou o "
                   "histórico estejam em outro idioma.",
             "en": "Answer strictly in English, even if the passages, tool results or history are in another "
                   "language."}
EVIDENCE_CHARS = 12000


def rewrite(answer: str, problems: list[str], *, language: str, evidence: list[str], question: str) -> str | None:
    """Uma reescrita pelo papel `agent` com a MESMA evidência do turno; None sem LLM ou se o provedor falhar.

    Reescreve em vez de rodar o agente de novo: repetir o loop de tools duplicaria ação pendente e custo.
    """
    llm = get_llm("agent")
    if not llm.enabled or not problems:
        return None
    from . import domain

    joined = "\n".join(evidence)[:EVIDENCE_CHARS]
    user = (f"<untrusted_content>\n{joined}\n</untrusted_content>\n\nPergunta do cliente: {question}\n\n"
            f"Resposta a corrigir:\n{answer}\n\nProblemas:\n" + "\n".join(f"- {p}" for p in problems)
            + f"\n\n{DIRECTIVE.get(language, DIRECTIVE['pt'])}")
    try:
        reply = llm.complete(domain.prompt("rewrite.md").format(language=LANGUAGE_NAME.get(language, language)),
                             [{"role": "user", "content": user}], max_tokens=2048)
    except LLMError:
        return None
    return reply.text.strip() or None

