"""Domínio do desafio — FLUXO (frente R): taxonomia da SPEC, planos, FALLBACK, regras do router.

Contrato lido pelo motor: PLANS, FALLBACK, ALLOWED, DEPENDS, NO_ESCALATION, DEFAULT_INTENT,
MULTI_PARTS, states_subject(), clause_intent(), combine().
Teste: tests/test_domain_router.py, tests/test_domain_supervisor.py.
"""
from __future__ import annotations

import re

# --- taxonomia e planos (SPEC: Taxonomia) ------------------------------------------------------------------
PLANS = {
    "knowledge": ["faq"],
    "general": ["faq"],  # dado ao vivo (clima/câmbio) ou busca web; nunca escala
    "support": ["records"],
    # lê terminal/transação; o manual (faq) entra pelo achado do records (`needs`), decidido pelo supervisor LLM
    # (rodada 11: no plano, o faq era passo do router e o achado só o antecipava — nenhum desvio era decisão do modelo)
    "troubleshoot": ["records"],
    "multi": ["faq", "records"],
    "human_request": ["escalation"],
}
# Status != ok/partial → próximo agente. Sem fonte ou ferramenta quebrada termina em humano.
FALLBACK = {"faq": "escalation", "records": "escalation"}
# Transições permitidas (de → para). None = início. records → faq cobre o NEEDS (terminal offline/recusa → manual).
ALLOWED = {None: {"faq", "records", "escalation"}, "faq": {"records", "escalation"},
           "records": {"faq", "escalation"}, "escalation": set()}
# troubleshoot: o manual (faq) precisa do modelo/estado do terminal ou do código de recusa (records).
DEPENDS: dict[str, set[str]] = {"faq": {"records"}}
NO_ESCALATION: set[str] = {"general"}
# Pergunta sobre a própria Getnet nunca fica no general (medido ao vivo: 3 perguntas sobre a empresa iam à web sem
# escalar).
OWN_COMPANY = r"\bgetnet\b|\bvoc[eê]s\b"  # "vocês" dirigido ao atendimento = a empresa
OWN_COMPANY_INTENT = "knowledge"
DEFAULT_INTENT = "knowledge"  # cláusula com assunto do domínio e sem regra
MULTI_PARTS = {"knowledge", "support"}  # o que um exemplo "multi" do k-NN soma às intenções da mensagem

# --- regras do router offline (SPEC: Desempates) ------------------------------------------------------------
_I = re.IGNORECASE
_HUMAN = re.compile(r"\b(atendente|humano|pessoa real|falar com (algu[eé]m|uma pessoa)|human|representative"
                    r"|real person|operador|operator|live agent)\b", _I)
# Desempate 4: clima, câmbio, cotação, notícia → general.
_GENERAL = re.compile(r"\b(clima|previs[aã]o do tempo|tempo (amanh\w*|hoje|em)|weather|forecast|temperatura"
                      r"|chuva|chover|rain\w*|c[aâ]mbio|cota[cç][aã]o|exchange rate|d[oó]lar|dollar|euro"
                      r"|ptax|not[ií]cias?|news)\b", _I)
# Ação de escrita sobre o dado do cliente (antecipar, abrir chamado) → support, mesmo com "offline".
_ACTION = re.compile(r"\b(quero antecipar|antecip[ae] (os )?meus|antecipar (os )?meus|advance my|please advance"
                     r"|abr\w* (um )?chamado|chamado t[eé]cnico|open (a )?(support |technical )?ticket)\b", _I)
# Desempate 1: sintoma (conexão ou recusa/erro) → troubleshoot, mesmo com "minha".
_SYMPTOM = re.compile(r"(n[aã]o (conecta|liga|funciona|passa|pega)|sem (sinal|internet|conex\w*)|\boffline\b"
                      r"|fora do ar|desconect\w*|perd\w* (a )?conex\w*|perd\w* (o )?sinal"
                      r"|losing (the )?connection|won'?t (connect|work)"
                      r"|can'?t connect|not connecting|no signal|keeps? disconnect\w*|reconect\w*|reconnect\w*"
                      r"|recusad\w*|recus[ao]u?\b|refused|declin\w*|negad\w*|\berros?\b|\berror\b|c[oó]digo \d{2}\b"
                      r"|code \d{2}\b)", _I)
_DECLINE = re.compile(r"(recus|declin|negad)", _I)
_WHY = re.compile(r"\b(por ?que|why|o que (significa|houve|fa[cç]o)|what (does|should)|como (evit|resolv)"
                  r"|how (do|can) i (fix|avoid)|maquininha|machine|terminal|reader)\b", _I)
_LIST = re.compile(r"\b(quais|which|list\w*|quantas vendas|how many sales)\b", _I)
# Desempate 3: "como funciona X" / "preciso de Y" sobre produto → knowledge, mesmo com "eu"/"minha loja".
_KNOW = re.compile(r"\b(como funciona|how does|how do(es)? .{0,40}work|preciso (de|ter|abrir)|do i need|posso|can i"
                   r"|o que [eé]|what is|what'?s the (difference|get)|qual a diferen\w*|diferen[cç]a|difference"
                   r"|quanto custa|how much does|parcel\w*|installments?)\b", _I)
_SUPPORT = re.compile(r"(\b(minhas? vendas|my sales|vendas (de )?ontem|yesterday'?s sales|dep[oó]sit\w*"
                      r"|cai o dinheiro|caem? na conta|be paid|get paid|agenda de (recebimento|dep[oó]sito)"
                      r"|liquida\w*|settlement\w*|meus terminais|my terminals?|terminais eu tenho|quais terminais"
                      r"|(est[aá]|is) (ela |ele |my machine |it )?online|minhas transa\w*|my transactions"
                      r"|vendi|did i sell)\b|\bT\d{4}[A-Z]\b|\bTX\d{4}\b)", _I)
_ID = re.compile(r"\b(T\d{4}[A-Z]|TX\d{4})\b", _I)
_REF = re.compile(r"\b(ele|ela|dela|dele|isso|essa|esse|o outro|a outra|o segundo|a segunda|it|its|that"
                  r"|the other|the second|this one)\b", _I)
FOLLOWUP_WORDS = 8


def _rule_intent(text: str) -> str | None:
    """Intenção por regra, sem histórico. Ordem = desempates da SPEC."""
    if _HUMAN.search(text):
        return "human_request"
    if _GENERAL.search(text):
        return "general"
    if _ACTION.search(text):
        return "support"
    if _SYMPTOM.search(text):
        only_decline = all(_DECLINE.search(m.group(0)) for m in _SYMPTOM.finditer(text))
        if only_decline and _LIST.search(text) and not _WHY.search(text):
            return "support"  # "quais vendas foram recusadas?" = consulta de dado, sem sintoma
        return "troubleshoot"
    if _KNOW.search(text) and not _ID.search(text):
        return "knowledge"
    if _SUPPORT.search(text):
        return "support"
    return None


def states_subject(text: str) -> bool:
    """A fala define assunto por REGRA (sem olhar vocabulário)? Usado para achar o assunto da conversa."""
    return _rule_intent(text) is not None and not _is_short_ref(text)


def _is_short_ref(text: str) -> bool:
    return len(text.split()) <= FOLLOWUP_WORDS and bool(_REF.search(text))


def clause_intent(text: str, history: list[dict], r) -> str | None:
    """Intenção de UMA cláusula. `r` = módulo app.router (topic_intent, knn_intent, has_subject, is_followup)."""
    rule = _rule_intent(text)
    if rule in ("human_request", "general") or (rule == "support" and _ACTION.search(text)):
        return rule
    # Seguimento curto herda a intenção do turno anterior (pós-morte N5). Depois de um troubleshoot, a pergunta
    # curta sobre a entidade citada ("and the other terminal?", "e qual foi o valor dela?") é consulta de dado.
    if history and (r.is_followup(text) or _is_short_ref(text)):
        last = r.topic_intent(history)
        if last == "troubleshoot":
            return "troubleshoot" if rule == "troubleshoot" else "support"
        if last in PLANS and last not in ("multi", "human_request", "general"):
            return rule if rule in ("troubleshoot", "support") and last == "support" else last
    if rule is not None:
        return rule
    if (near := r.knn_intent(text)) is not None:
        return near
    # Cláusula sem vocabulário do domínio ("Olá!") não vira pergunta: senão "Olá! Minhas vendas?" seria multi.
    return DEFAULT_INTENT if r.has_subject(text) else None


def combine(intents: set[str]) -> tuple[str, float]:
    """Intenções das cláusulas → (intent da mensagem, confiança)."""
    if "human_request" in intents:
        return "human_request", 0.95
    if "troubleshoot" in intents:  # o dado (records); o manual (faq) vem do achado, se o records trouxer
        return "troubleshoot", 0.85
    if "support" in intents and intents & {"knowledge", "general"}:
        return "multi", 0.8  # desempate 2: produto + dado meu
    for intent, conf in (("support", 0.85), ("general", 0.85), ("knowledge", 0.75)):
        if intent in intents:
            return intent, conf
    return DEFAULT_INTENT, 0.6
