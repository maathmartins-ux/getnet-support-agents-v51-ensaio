"""Router: intenção + plano inicial + idioma + confiança.

Com LLM: papel "router" (Haiku 5.5, effort low) com saída em JSON schema (output_config.format).
Offline (CI) e em qualquer falha do LLM (erro, recusa, JSON inválido): regras determinísticas abaixo.
O plano é só o ponto de partida — quem decide os passos seguintes é o supervisor.

Pergunta completa (contrato `ctx.facts["standalone"]`): na MESMA chamada que classifica, o router LLM
reescreve o turno como pergunta autônoma ("e a outra?" → "Qual o status da maquininha T1988B?") e a intenção é a
DESSA pergunta, não a do fragmento. O código confere a reescrita (`invented`): id, valor ou data que não está na
mensagem nem no histórico derruba a reescrita (standalone = "") e a classificação volta ao comportamento anterior
(intenção do modelo + herança de `followup.inherit`). Sem LLM: completação determinística (`followup.complete`).
Medido ao vivo sem a reescrita: memória pass@1 0,72 com 90,6% dos fatos certos; as 18 perdas eram de rota em
seguimento curto.

As regras e a taxonomia são do DOMÍNIO (app/domain/<ativo>.py: clause_intent, combine, states_subject, PLANS);
este arquivo é motor e não muda no desafio. A interface `route(text, history) -> RouterDecision` fica.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

from . import domain
from .config import data_dir
from .llm import LLMError, get_llm
from .observability import METRICS
from .rag import get_index, tokenize
from .schemas import RouterDecision


def _plans() -> dict[str, list[str]]:
    return domain.active().PLANS


class RoutedDecision(RouterDecision):
    """Decisão + a pergunta completa do turno (vai para ctx.facts["standalone"]; "" = reescrita recusada)."""

    standalone: str = ""
    search_queries: list[str] = []


STANDALONE_MAX_CHARS = 400
SEARCH_QUERIES_MAX = 3
SEARCH_QUERY_MAX_CHARS = 200
_STANDALONE_DOC = ("A mensagem reescrita como pergunta completa e autônoma, no idioma do cliente, com as referências "
                   "ao histórico resolvidas; se ela já se basta, repita-a. Nunca acrescente id, valor ou data que "
                   "não esteja na mensagem ou no histórico.")


def _search_queries_doc() -> str:
    from .agents import corpus_language

    lang = {"pt": "português", "en": "inglês"}.get(corpus_language(), corpus_language())
    return (f"Consultas para a base de conhecimento, escritas em {lang} (o idioma da base), com os termos que o site "
            "usaria: uma por produto ou item quando a pergunta compara ou lista vários (até 3); uma só nos outros "
            "casos; [] quando a pergunta não precisa da base. Nunca acrescente id, valor ou data que o cliente não "
            "disse.")


def schema() -> dict:
    """JSON schema da saída do router: o enum de intents vem do domínio ativo.

    `standalone` vem PRIMEIRO: o modelo escreve a pergunta completa antes de escolher a intenção dela.
    `search_queries`: as consultas do RAG no idioma da base, na MESMA chamada —
    sem LLM, a troca de termos pelo glossário gerava "Do I need a conta corrente to receber my vendas via Pix?" e o
    trecho com a resposta ficava fora do top-5.
    """
    return {
        "type": "object", "additionalProperties": False,
        "required": ["standalone", "search_queries", "intent", "plan", "language", "confidence"],
        "properties": {
            "standalone": {"type": "string", "description": _STANDALONE_DOC},
            "search_queries": {"type": "array", "items": {"type": "string"}, "description": _search_queries_doc()},
            "intent": {"type": "string", "enum": sorted(_plans())},
            "plan": {"type": "array", "items": {"type": "string", "enum": ["faq", "records", "escalation"]}},
            "language": {"type": "string", "enum": ["pt", "en"]},
            "confidence": {"type": "number"},
        },
    }

# Confirmação no começo da fala ("Ok, vou tentar...", "Beleza, obrigado!"): não muda o assunto da conversa.
_ACK = re.compile(r"^\W*(ok(ay)?|t[aá] bom|certo|beleza|blz|valeu|obrigad[oa]|entendi|show|perfeito|combinado"
                  r"|thanks|thank you|got it|sure|alright|fine|cool)\b", re.IGNORECASE)
# Palavras funcionais frequentes de cada idioma; nenhuma de uma letra só ("a" existe nos dois).
_EN = re.compile(r"\b(the|what|how|why|when|my|is|are|can|you|please|want|to|talk|with|it|do|does"
                 r"|of|and|for|this|that|me|need|help|where|order)\b", re.IGNORECASE)
_PT = re.compile(r"\b(os|as|um|uma|de|do|da|que|como|com|para|por|não|meu|minha|quero|está"
                 r"|falar|ajuda|preciso|sem|no|na|qual|onde|posso|pedido)\b", re.IGNORECASE)
_ACCENT = re.compile(r"[ãõáéíóúâêôç]", re.IGNORECASE)
# Fronteira de cláusula: pontuação, ":" (não em "9:30"), conjunção que emenda outra pergunta (", and",
# " e aproveita", " e também", "also", "além disso"). " e "/" and " soltos NÃO dividem ("troca e devolução").
# Medido: "... e aproveita: ...?" e "two questions: ..., and ...?" viravam uma intenção só.
_CLAUSE = re.compile(r"[?.!;]+|:(?!\d)|,\s*(?:and|e)\s+|,?\s+e\s+(?:aproveita|tamb[eé]m)\b"
                     r"|,?\s*\balso\b|,?\s*\bal[eé]m disso\b", re.IGNORECASE)
# Quem anuncia "duas perguntas" avisou que há duas: aí " e "/" and " e vírgula também dividem.
_TWO_QUESTIONS = re.compile(r"\b(?:duas|2)\s+(?:perguntas|d[uú]vidas|coisas)\b|\b(?:two|2)\s+(?:questions|things)\b",
                            re.IGNORECASE)
_AND = re.compile(r",|\s+(?:e|and)\s+", re.IGNORECASE)
# Conversa que não é assunto: sai do vocabulário antes da checagem ("Bom dia" casaria com "dias úteis").
_SMALLTALK = set(tokenize("oi olá ola bom boa dia tarde noite tudo bem hoje obrigado obrigada valeu enfim nossa "
                          "hello hi hey good morning afternoon evening thanks thank please"))


def split_clauses(text: str) -> list[str]:
    parts = [c for c in _CLAUSE.split(text) if c and c.strip()]
    if _TWO_QUESTIONS.search(text):
        parts = [p for c in parts for p in _AND.split(c) if p.strip()]
    if ask := _disambiguation().get("ask_words"):
        parts = [p for c in parts for p in split_asks(c, ask)]
    return parts or [text]


# --- desempates do domínio : o domínio dá as palavras, o motor dá o mecanismo ------------------------
# Held-out cego medido (offline): intenção 67,5%; as confusões foram multi→support 7, troubleshoot→support 5,
# knowledge→support 3. O domínio declara (opcional, ver os testes de desempate):
#   DISAMBIGUATION = {
#     "ask_words": ["qual", "quanto", "como", "posso", "what", "how", ...],  # marca de pedido próprio
#     "rules": [  # em ordem; a 1ª que casa vale
#       {"from": ["support"], "to": "troubleshoot", "words": ["nao liga", "trav*", "erro"],   # sintoma
#        "unless": ["quais vendas", "list*"]},                                              # consulta/lista
#       {"from": ["support"], "to": "knowledge", "words": ["como funciona", "posso"], "unless_id": True},
#     ],
#   }
# - "ask_words": "X e Y?" em que os DOIS lados têm pedido próprio vira duas cláusulas; cada uma é classificada e
#   o `combine` do domínio junta (as partes de MULTI_PARTS viram multi). " e "/" and " sem pedido do lado direito
#   não divide ("troca e devolução").
# - "rules": a intenção de UMA cláusula muda de `from` para `to` quando a cláusula tem uma das `words` e nenhuma das
#   `unless` (e nenhum id, com unless_id). Palavras sem acento nem caixa; "*" no fim = prefixo ("trav*").
# Valem nas regras offline; com LLM, as mesmas listas vão ao modelo como desempates (o modelo decide).
def _disambiguation() -> dict:
    return getattr(domain.active(), "DISAMBIGUATION", None) or {}


@lru_cache(maxsize=64)
def _phrases(words: tuple[str, ...]) -> re.Pattern | None:
    alts = []
    for w in words:
        n = normalize(w.rstrip("*"))
        if n:
            alts.append(re.escape(n) + (r"\w*" if w.endswith("*") else ""))
    return re.compile(r"\b(?:" + "|".join(alts) + r")\b") if alts else None


def mentions(text: str, words) -> bool:
    """A fala cita alguma das palavras/expressões (sem acento nem caixa; "*" final = prefixo)?"""
    pattern = _phrases(tuple(words or ()))
    return bool(pattern and pattern.search(normalize(text)))


_ASK_JOIN = re.compile(r"(,\s*|\s+(?:e|and)\s+)", re.IGNORECASE)
ASK_LEAD_WORDS = 3  # o pedido do lado direito tem de estar nas primeiras palavras ("e quanto eu paguei...")


def split_asks(clause: str, ask_words) -> list[str]:
    """Divide "Qual a taxa X e quanto eu paguei Y?" em dois pedidos; cada lado precisa de pedido próprio."""
    pieces = _ASK_JOIN.split(clause)
    if len(pieces) < 3:
        return [clause]
    out = [pieces[0]]
    for sep, piece in zip(pieces[1::2], pieces[2::2], strict=True):
        lead = " ".join(normalize(piece).split()[:ASK_LEAD_WORDS])
        if mentions(lead, ask_words) and mentions(out[-1], ask_words):
            out.append(piece)
        else:
            out[-1] += sep + piece
    return [o for o in out if o.strip()]


def disambiguate(intent: str | None, clause: str) -> str | None:
    """Intenção de UMA cláusula depois dos desempates do domínio (DISAMBIGUATION["rules"])."""
    plans = _plans()
    for rule in _disambiguation().get("rules", ()):
        to = rule.get("to")
        if intent not in set(rule.get("from", ())) or to not in plans or to == intent:
            continue
        if not mentions(clause, rule.get("words")) or mentions(clause, rule.get("unless")):
            continue
        if rule.get("unless_id"):
            from . import memory

            if memory.ids_in(clause):
                continue
        METRICS.inc("router_disambiguated_total", frm=intent, to=to)
        return to
    return intent


def disambiguation_block() -> str:
    """As mesmas listas, em texto, para o router LLM (desempates; quem decide é o modelo)."""
    lines = []
    for rule in _disambiguation().get("rules", ()):
        if rule.get("to") not in _plans():
            continue
        line = f"- {'/'.join(rule.get('from', ()))} → {rule['to']} quando a pergunta tiver: {', '.join(rule['words'])}"
        if rule.get("unless"):
            line += f" (exceto com: {', '.join(rule['unless'])})"
        if rule.get("unless_id"):
            line += " (exceto quando cita um id)"
        lines.append(line)
    if _disambiguation().get("ask_words"):
        lines.append("- duas perguntas ligadas por \"e\"/\"and\", cada uma com seu pedido, são duas partes: "
                     "classifique cada uma e junte (multi quando as partes forem de intents diferentes)")
    return "Desempates do domínio:\n" + "\n".join(lines) if lines else ""


def _stamp(d: Path) -> tuple:
    # o domínio ativo entra na chave dos caches: exemplos com intent fora da taxonomia dele são descartados
    return (domain.name(),) + tuple((p.name, p.stat().st_mtime_ns) for p in sorted(d.rglob("*.jsonl")))


EXAMPLES_FILE = "intent_examples.jsonl"  # {"text", "intent"}; o domínio preenche no relógio. NUNCA o held-out.


@lru_cache(maxsize=4)
def _examples_for(directory: str, stamp: tuple) -> tuple[tuple[str, str], ...]:
    from app.jsonl import read_family

    rows = read_family(Path(directory) / EXAMPLES_FILE)  # base + intent_examples.d/*.jsonl
    return tuple((r["text"], r["intent"]) for r in rows if r.get("text") and r.get("intent") in _plans())


@lru_cache(maxsize=4)
def _vocab_for(directory: str, stamp: tuple) -> frozenset[str]:
    """Vocabulário do domínio = base de conhecimento (título + texto) + exemplos rotulados, sem conversa."""
    texts = [f"{d.title} {d.text}" for d in get_index().docs] + [t for t, _ in _examples_for(directory, stamp)]
    return frozenset(w for t in texts for w in tokenize(t)) - _SMALLTALK


def has_subject(text: str) -> bool:
    """A cláusula fala de algo do domínio? "Hoje tá frio, né?" não; "qual o prazo?" sim."""
    d = data_dir()
    return bool((set(tokenize(text)) - _SMALLTALK) & _vocab_for(str(d), _stamp(d)))


# --- k-NN offline: recurso de quando nenhuma regra casa -------------------------------------------------
# TF-IDF de n-gramas de caractere (3 a 5) sobre texto normalizado, cosseno, k vizinhos com voto ponderado pela
# similaridade. Caractere (e não palavra) pega flexão e erro de digitação: "maquininha"/"maquinha", "ontm".
KNN_K = 5
KNN_NGRAMS = (3, 5)
# Limiar mínimo de similaridade do vizinho MAIS próximo; abaixo dele, o k-NN se cala e vale o padrão de sempre.
# 0,15 medido em 31/10/2026, nunca no held-out:
# - leave-one-out em 78 casos de desenvolvimento (sem multi/blocked): acerto 88,5%,
#   precisão 91,4% acima do limiar, cobertura 90%. Em 0,10: 91,0% de acerto, mas 4 de 12 frases de conversa
#   passavam; em 0,25: 78,2% de acerto.
# - conversa genuína ("Ok, entendi.", "What a rainy day, right?", "Tudo bem com você?") ficou ≤ 0,117 nos
#   dois conjuntos; a paráfrase certa mais fraca do fixture do kit, 0,195.
# Exemplo de treino deve ser UMA cláusula de UMA intenção: "Oi! Hoje tá frio, né? Enfim, quanto vendi..." como
# exemplo puxou "Hoje tá frio, né?" para 0,54. Remeça quando o domínio trocar os exemplos.
KNN_MIN_SIM = 0.15
FEW_SHOT_K = 8  # exemplos mais parecidos no prompt do router com LLM


def normalize(text: str) -> str:
    """Minúsculas, sem acento, só letras e dígitos separados por espaço."""
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", plain))


def _ngrams(text: str) -> Counter:
    t = f" {normalize(text)} "
    lo, hi = KNN_NGRAMS
    return Counter(t[i:i + n] for n in range(lo, hi + 1) for i in range(len(t) - n + 1))


class KNN:
    """k-NN determinístico sobre exemplos rotulados; só biblioteca padrão."""

    def __init__(self, examples: list[tuple[str, str]] | tuple[tuple[str, str], ...]):
        self.examples = list(examples)
        grams = [_ngrams(t) for t, _ in self.examples]
        df = Counter(g for c in grams for g in c)
        n = len(self.examples)
        self.idf = {g: math.log((1 + n) / (1 + d)) + 1 for g, d in df.items()}  # idf suavizado
        self.idf_unseen = math.log(1 + n) + 1  # n-grama nunca visto pesa como o mais raro: frase alheia fica longe
        self.vectors = [self._vector(c) for c in grams]

    def _vector(self, counts: Counter) -> dict[str, float]:
        v = {g: (1 + math.log(c)) * self.idf.get(g, self.idf_unseen) for g, c in counts.items()}
        norm = math.sqrt(sum(x * x for x in v.values()))
        return {g: x / norm for g, x in v.items()} if norm else {}

    def neighbors(self, text: str, k: int) -> list[tuple[float, int]]:
        """(similaridade, índice do exemplo), do mais parecido ao menos; empate desfeito pela ordem do arquivo."""
        q = self._vector(_ngrams(text))
        sims = [(sum(w * vec.get(g, 0.0) for g, w in q.items()), i) for i, vec in enumerate(self.vectors)]
        return sorted(sims, key=lambda s: (-s[0], s[1]))[:k]

    def predict(self, text: str, k: int = KNN_K, min_sim: float = KNN_MIN_SIM) -> str | None:
        top = self.neighbors(text, k)
        if not top or top[0][0] < min_sim:
            return None
        votes: Counter = Counter()
        for sim, i in top:
            votes[self.examples[i][1]] += sim
        return min(votes, key=lambda intent: (-votes[intent], intent))  # maior soma; empate: ordem alfabética


@lru_cache(maxsize=8)
def _knn_for(directory: str, stamp: tuple, clause_level: bool) -> KNN:
    examples = _examples_for(directory, stamp)
    # O classificador roda por CLÁUSULA: multi nasce da soma de cláusulas, não de um vizinho. Medido no fixture:
    # com exemplos multi no voto, "cadê minha encomenda" virava multi (0,76 contra 0,62 de records).
    return KNN([e for e in examples if e[1] != "multi"] if clause_level else examples)


def get_knn(clause_level: bool = True) -> KNN:
    """clause_level=True: classificador offline (sem exemplos multi). False: few-shot do LLM (todos)."""
    d = data_dir()
    return _knn_for(str(d), _stamp(d), clause_level)


def knn_intent(text: str) -> str | None:
    return get_knn().predict(text)


def _language_votes(text: str) -> tuple[int, int]:
    # Acento vale 1 ponto para pt, não decide sozinho (nome próprio acentuado em frase inglesa).
    return len(_EN.findall(text)), len(_PT.findall(text)) + min(1, len(_ACCENT.findall(text)))


def detect_language(text: str) -> str:
    en, pt = _language_votes(text)
    return "en" if en > pt else "pt"


def clear_language(text: str, margin: int = 2) -> str | None:
    """Idioma quando as palavras não deixam dúvida (vantagem >= margin); None quando é mistura e o LLM decide.

    Medido ao vivo: o Router LLM respondeu "pt" para "How does receivables advance (antecipação)
    work with Getnet?" em 2 de 3 rodadas; o detector acerta 137 de 140 frases dos casos (pt e en).
    """
    en, pt = _language_votes(text)
    return "en" if en - pt >= margin else "pt" if pt - en >= margin else None


def _states_subject(text: str) -> bool:
    """Fala que define assunto: casa uma regra ou tem vocabulário do domínio, e não é só confirmação."""
    if domain.active().states_subject(text):
        return True
    return not _ACK.match(text) and has_subject(text)


_FOLLOW = re.compile(r"^\W*(e|and|what about|how about|e quanto|e sobre|e se|but|mas)\b", re.IGNORECASE)
FOLLOWUP_MAX_WORDS = 8


def is_followup(text: str) -> bool:
    """Seguimento: curto e ("e a Get Clássica?" | sem assunto próprio: "e quanto custa?"), não só uma confirmação."""
    return len(text.split()) <= FOLLOWUP_MAX_WORDS and not _ACK.match(text) and (
        bool(_FOLLOW.match(text)) or not has_subject(text))


def has_stated_subject(text: str) -> bool:
    """A fala define o assunto da conversa: tem assunto próprio, não é só confirmação e não é seguimento."""
    return _states_subject(text) and not is_followup(text)


def standalone_query(text: str, history: list[dict]) -> str | None:
    """Dica de busca para um seguimento: a última fala do cliente que TEM assunto (e não é seguimento ela mesma).

    "E quanto custa?" depois de "Como funciona a Get Smart?" busca "e quanto custa? como funciona a get smart?".
    Mensagem que se basta sozinha, ou conversa sem histórico, devolve None: nada é reescrito (teste cobre).
    Medido: o RAG buscava só o texto do turno e o seguimento não achava a página do assunto anterior.
    """
    if not history or not is_followup(text):
        return None
    for m in reversed(history):
        prev = (m.get("content") or "").strip() if m.get("role") == "user" else ""
        if prev and _states_subject(prev) and not is_followup(prev):
            return prev[:300]
    return None


def topic_intent(history: list[dict]) -> str | None:
    """Intenção da última fala do cliente COM ASSUNTO, pulando confirmação e conversa ("Ok, vou tentar...").

    Olhar só a última fala quebrava a cadeia: um seguimento perdia o problema depois de um "Ok".
    Pergunta de seguimento ("e ele?") também é pulada: o assunto dela é o de antes, que o laço acha.
    """
    for m in reversed(history):
        if m.get("role") == "user" and m.get("intent") and _states_subject(m.get("content") or ""):
            return m["intent"]
    return None


def _clause_intent(text: str, history: list[dict]) -> str | None:
    import sys

    return domain.active().clause_intent(text, history, sys.modules[__name__])


def classify_offline(text: str, history: list[dict]) -> RouterDecision:
    """Uma intenção por cláusula; o domínio junta as cláusulas (`combine`): intenções diferentes viram `multi`."""
    d = domain.active()
    lang = detect_language(text)
    intents: set[str] = set()
    for clause in split_clauses(text):
        found = disambiguate(_clause_intent(clause, history), clause)
        intents |= set(d.MULTI_PARTS) if found == "multi" else ({found} if found else set())
    intent, conf = d.combine(intents or {d.DEFAULT_INTENT})
    return RouterDecision(intent=intent, plan=d.PLANS[intent], language=lang, confidence=conf)


def few_shot(text: str, k: int = FEW_SHOT_K) -> list[tuple[str, str]]:
    """Os k exemplos rotulados mais parecidos (mesmo k-NN, com multi), do MENOS ao MAIS parecido.

    O mais parecido vai por último, colado na mensagem: é o que o modelo pesa mais (efeito de recência).
    """
    knn = get_knn(clause_level=False)
    return [knn.examples[i] for _, i in reversed(knn.neighbors(text, k))]


def _llm_input(text: str, history: list[dict]) -> str:
    from . import followup

    parts = []
    if topic := topic_intent(history):  # a conversa inteira, resumida: o 1º turno vale mesmo fora das 4 recentes
        said = followup.topic_turn(history)  # a fala do assunto: base da reescrita mesmo fora das 4 recentes
        parts.append(f"Assunto da conversa (última fala com assunto): {topic}"
                     + (f" — {json.dumps(said[0][:200], ensure_ascii=False)}" if said else ""))
    recent = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in history[-4:])
    parts.append(f"Histórico recente:\n{recent or '(vazio)'}")
    if shots := few_shot(text):
        lines = "\n".join(f"- {json.dumps(t, ensure_ascii=False)} -> {i}" for t, i in shots)
        parts.append(f"Exemplos rotulados (do menos ao mais parecido com a mensagem):\n{lines}")
    if block := disambiguation_block():
        parts.append(block)
    parts.append(f"Mensagem: {text}")
    return "\n\n".join(parts)


# --- conferência da reescrita: id, valor ou data inventados ------------------------------------------------
# Token com dígito (TX1008, 1002, R$ 210,00, 02/11, 2026-11-01) ou palavra de dia relativo ("ontem"). O núcleo
# ignora caixa, separador e centavos zerados: "R$ 210,00" na reescrita confere com "210" na conversa.
_NUM_TOKEN = re.compile(r"[A-Za-z]*\d[A-Za-z\d]*(?:[.,/:-]\d+)*[A-Za-z]?")
_RELDAY_WORD = re.compile(r"\b(anteontem|ontem|hoje|amanh[ãa]|yesterday|today|tomorrow)\b", re.IGNORECASE)


def _core(token: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"[.,]0+$", "", token.lower()))


def invented(rewrite: str, text: str, history: list[dict]) -> list[str]:
    """Ids, valores, datas e dias relativos da reescrita que NÃO estão na mensagem nem no histórico (vazio = ok)."""
    known_text = " ".join([text, *(str(m.get("content") or "") for m in history or [])])
    known = {_core(t) for t in _NUM_TOKEN.findall(known_text)}
    days = {d.lower() for d in _RELDAY_WORD.findall(known_text)}
    out = [t for t in _NUM_TOKEN.findall(rewrite) if _core(t) not in known]
    out += [d for d in _RELDAY_WORD.findall(rewrite) if d.lower() not in days]
    return list(dict.fromkeys(out))


def check_standalone(rewrite: str | None, text: str, history: list[dict]) -> str:
    """A reescrita do LLM, limpa; "" quando vazia ou quando traz id/valor/data inventado (métrica conta)."""
    rewrite = " ".join(str(rewrite or "").split())[:STANDALONE_MAX_CHARS]
    if not rewrite:
        return ""
    if invented(rewrite, text, history):
        METRICS.inc("router_standalone_rejected_total")
        return ""
    return rewrite


def check_search_queries(queries, text: str, history: list[dict]) -> list[str]:
    """Consultas do LLM, limpas: até SEARCH_QUERIES_MAX, sem repetição; cai a que traz id/valor/data inventado."""
    out: list[str] = []
    for q in queries if isinstance(queries, list) else []:
        q = " ".join(str(q or "").split())[:SEARCH_QUERY_MAX_CHARS]
        if not q or q.lower() in {x.lower() for x in out}:
            continue
        if invented(q, text, history):
            METRICS.inc("router_search_query_rejected_total")
            continue
        out.append(q)
    return out[:SEARCH_QUERIES_MAX]


class _Decided(RouterDecision):
    """Saída interna de `_route`: a decisão + de onde veio (llm | rules) + a reescrita crua do LLM."""

    source: str = "rules"
    rewrite: str | None = None
    queries: list | None = None


def route(text: str, history: list[dict]) -> RoutedDecision:
    """Decisão do router (LLM ou regras) + pergunta completa do turno.

    Reescrita do LLM aceita: a intenção já é a da pergunta completa, a herança de seguimento não se aplica.
    Reescrita recusada ou ausente: comportamento anterior, decisão + `followup.inherit` (seguimento elíptico).
    Sem LLM: `followup.complete` completa o seguimento com o último assunto; quando a completação é TROCA de
    entidade ("e a TX1008?" → a pergunta do assunto com TX1008), as regras classificam a pergunta completa.
    """
    from . import followup

    decided = _route(text, history)
    source, rewrite = getattr(decided, "source", None), getattr(decided, "rewrite", None)
    decision = RouterDecision(intent=decided.intent, plan=decided.plan, language=decided.language,
                              confidence=decided.confidence)
    if source == "llm":
        standalone = check_standalone(rewrite, text, history)
        if not standalone:
            decision = followup.inherit(decision, text, history)
        queries = check_search_queries(getattr(decided, "queries", None), text, history)
        return RoutedDecision(**decision.model_dump(), standalone=standalone, search_queries=queries)
    standalone, swapped = followup.complete(text, history)
    if swapped and source == "rules":
        decision = classify_offline(standalone, history).model_copy(update={"language": decision.language})
    decision = followup.inherit(decision, text, history)
    return RoutedDecision(**decision.model_dump(), standalone=standalone)


def _route(text: str, history: list[dict]) -> RouterDecision:
    """Decisão crua (`_Decided`): LLM com a reescrita, ou regras. Falha do LLM → regras, sem reescrita."""
    llm = get_llm("router")
    if not llm.enabled:
        return _Decided(**classify_offline(text, history).model_dump())
    try:
        raw = llm.complete(domain.prompt("router.md"), [{"role": "user", "content": _llm_input(text, history)}],
                           max_tokens=2048, schema=schema()).json()
        rewrite = raw.pop("standalone", None)
        queries = raw.pop("search_queries", None)
        raw["confidence"] = min(1.0, max(0.0, float(raw["confidence"])))
        if lang := clear_language(text):
            raw["language"] = lang  # frase sem ambiguidade: a contagem de palavras manda, não o histórico em pt
        decision = RouterDecision(**raw)
        if decision.intent not in _plans():
            raise ValueError(f"intent fora do contrato: {decision.intent}")
        return _Decided(**decision.model_dump(), source="llm", rewrite=rewrite if isinstance(rewrite, str) else None,
                        queries=queries if isinstance(queries, list) else None)
    except (LLMError, ValueError, KeyError, TypeError, AttributeError):  # pydantic.ValidationError é ValueError
        METRICS.inc("router_fallback_total")
        return _Decided(**classify_offline(text, history).model_dump())


def __getattr__(attr: str):
    # compatibilidade: `router.PLANS` e `router.SCHEMA` refletem o domínio ativo
    if attr == "PLANS":
        return _plans()
    if attr == "SCHEMA":
        return schema()
    raise AttributeError(attr)
