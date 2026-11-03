"""Seguimento elíptico: "E a TX1008?", "E a de anteontem?", "E a outra maquininha?" herdam a intenção do assunto.

O seguimento que só TROCA uma entidade ("TX1007" -> "TX1008", "ontem" -> "anteontem") não traz intenção própria: a
pergunta é a mesma, o objeto mudou. Classificado sozinho, ele cai na regra da entidade (um id vira "consulta de dado")
ou no k-NN de uma frase curta, e a conversa de diagnóstico vira consulta (ou, pior, confiança baixa e escalação).

Herda a intenção (e o plano do domínio) do último assunto declarado do cliente quando a fala é elíptica E
- a confiança do router é baixa (ele mesmo não sabe), ou
- troca uma entidade do mesmo tipo da do assunto: id com o mesmo formato (TX1007 -> TX1008), palavra de tempo
  relativo (ontem -> anteontem) ou "outra <substantivo>" quando o assunto cita esse substantivo.
Sem uma dessas provas a decisão do router fica: "E a Get Clássica?" depois de uma pergunta de saldo é produto novo,
não consulta. Fala com pergunta própria ("quanto custa?", "por que?") nunca é elíptica, e pedido de humano nunca é
sobrescrito nem herdado.
"""
from __future__ import annotations

import re
import unicodedata

from . import domain, memory, router
from .observability import METRICS
from .schemas import RouterDecision

FOLLOWUP_LOW_CONFIDENCE = 0.6  # abaixo disso o router, em seguimento curto, não sabe: vale o assunto da conversa
INHERITED_MIN_CONFIDENCE = 0.5  # acima do corte de escalação por baixa confiança (supervisor.LOW_CONFIDENCE)
_I = re.IGNORECASE
_CONNECTOR = re.compile(r"^\W*(?:and what about|what about|how about|e sobre|and|mas|but|e)\b", _I)
# Palavra de pergunta, modal ou verbo de intenção: a fala tem intenção própria e deixa de ser só troca de entidade.
_OWN_INTENT = re.compile(
    r"\b(quando|como|por ?que|porque|qual|quais|quanto|quantos?|quantas|onde|quem|posso|pode|podem|preciso|quero"
    r"|gostaria|vou|tenho|consigo|cad[eê]|how|why|when|what|which|where|who|can|could|should|would|will"
    r"|need|want|have|is|are|was|were)\b", _I)  # sem "do": em pt é "a do dólar"
_RELDAY = re.compile(r"\b(anteontem|ontem|hoje|amanh[ãa]|day before yesterday|day before|yesterday|today|tomorrow)\b",
                     _I)
_OTHER = re.compile(r"\b(?:outr[ao]s?|other|another)\s+(\w+)", _I)


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def _id_shape(raw: str) -> str:
    return "id:" + re.sub(r"\d+", lambda m: "9" * len(m.group(0)), re.sub(r"[A-Za-z]", "A", raw))


def entity_shapes(text: str) -> set[str]:
    """Tipos de entidade da fala, sem o valor: o formato do id, tempo relativo, dinheiro, data."""
    out = {_id_shape(i) for i in memory.ids_in(text)}
    if _RELDAY.search(text):
        out.add("relday")
    if memory.money_in(text):
        out.add("money")
    if memory.dates_in(text):
        out.add("date")
    return out


def is_elliptical(text: str) -> bool:
    """Curta, sem confirmação, sem pergunta/verbo próprio, e com conector ("e ...") ou só entidade."""
    if len(text.split()) > router.FOLLOWUP_MAX_WORDS or router._ACK.match(text):
        return False
    rest = _CONNECTOR.sub("", text, count=1)
    if _OWN_INTENT.search(rest):
        return False
    return bool(_CONNECTOR.match(text) or entity_shapes(text) or _OTHER.search(text))


def topic_turn(history: list[dict]) -> tuple[str, str] | None:
    """(fala, intenção) da última fala do cliente que declara assunto, pulando confirmação e seguimento."""
    for m in reversed(history):
        content = m.get("content") or ""
        if m.get("role") == "user" and m.get("intent") and router.has_stated_subject(content):
            return content, m["intent"]
    return None


def swaps_entity(text: str, topic: str) -> bool:
    """A fala troca uma entidade do mesmo tipo da do assunto (prova de que a pergunta é a mesma)?"""
    if entity_shapes(text) & entity_shapes(topic):
        return True
    words = set(re.findall(r"\w+", _fold(topic)))
    return any(_fold(m.group(1)) in words for m in _OTHER.finditer(text))


def inherit(decision: RouterDecision, text: str, history: list[dict]) -> RouterDecision:
    plans = domain.active().PLANS
    if not history or decision.intent not in plans or plans[decision.intent] == ["escalation"]:
        return decision
    if not is_elliptical(text) or not (topic := topic_turn(history)):
        return decision
    content, intent = topic
    plan = plans.get(intent)
    if intent == decision.intent or not plan or plan == ["escalation"]:
        return decision
    if not (decision.confidence < FOLLOWUP_LOW_CONFIDENCE or swaps_entity(text, content)):
        return decision
    METRICS.inc("followup_inherited_total", intent=intent)
    return RouterDecision(intent=intent, plan=list(plan), language=decision.language,
                          confidence=max(decision.confidence, INHERITED_MIN_CONFIDENCE))


# --- completação determinística (modo sem LLM do contrato ctx.facts["standalone"]) ----------------------------
def _swap(text: str, topic: str) -> str | None:
    """A pergunta do assunto com a entidade nova no lugar da antiga do mesmo tipo; None se não há o que trocar."""
    for new in memory.ids_in(text):
        for old in memory.ids_in(topic):
            if _id_shape(old) == _id_shape(new) and old.upper() != new.upper():
                return re.sub(re.escape(old), new, topic, count=1, flags=_I)
    for finder in (memory.money_in, memory.dates_in):
        new, old = finder(text), finder(topic)
        if new and old and new[0] != old[0]:
            return topic.replace(old[0], new[0], 1)
    new_day, old_day = _RELDAY.search(text), _RELDAY.search(topic)
    if new_day and old_day and _fold(new_day.group(0)) != _fold(old_day.group(0)):
        return topic[:old_day.start()] + new_day.group(0) + topic[old_day.end():]
    return None


# Referência ao que já foi dito (pronome/demonstrativo): "Por que ela foi recusada?", "Quero contestar essa venda",
# "Can I use it on WhatsApp?". Língua, não domínio. Sem "that"/"this" soltos (conjunção em "I saw that my...").
_REFERENCE = re.compile(r"\b(?:ela|ele|dela|dele|nela|nele|isso|disso|nisso|ess[ae]s?|dess[ae]s?|ness[ae]s?"
                        r"|it|its|them|that one|this one)\b", _I)
REFERENCE_MAX_WORDS = 12


def refers_back(text: str) -> bool:
    """Fala curta que aponta para algo dito antes (pronome ou demonstrativo)."""
    return len(text.split()) <= REFERENCE_MAX_WORDS and bool(_REFERENCE.search(text))


def complete(text: str, history: list[dict], max_chars: int = 400) -> tuple[str, bool]:
    """(pergunta completa, foi troca de entidade?) para o turno, sem LLM.

    - Mensagem que se basta, ou conversa sem assunto anterior: a própria mensagem.
    - Seguimento que troca entidade do mesmo tipo ("e a TX1008?" depois de "por que a TX1007 foi recusada?"):
      a pergunta do assunto com a entidade nova ("por que a TX1008 foi recusada?"), e True.
    - Outro seguimento ("e quanto custa?", "e a outra maquininha?") ou fala curta com pronome/demonstrativo
      ("Quero contestar essa venda"): assunto + fala, na ordem da conversa.
    Nunca cria id, valor ou data: só copia da mensagem e do histórico (mesma garantia da conferência do LLM).
    """
    text = " ".join(text.split())
    if not history or not (is_elliptical(text) or router.is_followup(text) or refers_back(text)):
        return text, False
    topic = topic_turn(history)
    subject = topic[0] if topic else router.standalone_query(text, history)
    if not subject:
        return text, False
    subject = " ".join(subject.split())
    if swapped := _swap(text, subject):
        return swapped[:max_chars], True
    joiner = " " if subject[-1:] in ".?!" else ". "  # "Fale do Link" + "Can I use it?" → duas frases
    return f"{subject}{joiner}{text}"[:max_chars], False
