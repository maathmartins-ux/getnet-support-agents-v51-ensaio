"""Especialistas. Cada um recebe o Context e devolve AgentResult com status explícito:
"ok", "partial" (só o faq: respondeu o que a fonte cobre e diz o que falta, em facts["missing"]), "insufficient"
(não tem base para responder) ou "error". O supervisor decide o que fazer com cada status — nenhum agente chama outro.

Regra para rodar em paralelo: agente só LÊ o Context; o que descobre volta em `facts` e o
supervisor junta depois, na ordem do plano. Nada de escrever em ctx dentro do agente.

- faq: RAG (retriever de rag.get_retriever) com fonte citada; "sem fonte, sem afirmação". Busca agentic: as
  consultas saem da pergunta autônoma do router (ctx.facts["standalone"]) no idioma do CORPUS, uma por item numa
  comparação, até FAQ_MAX_SEARCHES por turno, em paralelo e fundidas por rodada na ordem do plano (top FAQ_TOP_K ao
  redator); com LLM, o redator ainda pode chamar a tool `search` dentro do mesmo teto, e leva 1 busca corretiva
  quando o plano já gastou o teto (comparação). Glossário pt<->en (data/glossary.json) nas duas vias.
  Intent "general": com LLM, o MODELO escolhe a tool: `currency_rate` (PTAX) e `weather_forecast` (Open-Meteo),
  validadas e executadas no código (app/live_data.py, texto bruto da API como evidência), ou a busca web do servidor
  (resultados da busca como evidência e fonte, nunca a própria resposta). Sem LLM, o detector por regex decide.
- records: tools com identidade do servidor; escrita só propõe (action_id + confirmação).
- escalation: abre caso na fila persistida; operador responde em /operator (ou Telegram) e a conversa retoma.
"""
from __future__ import annotations

import contextvars
import json
import os
import re
import threading
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from . import capabilities, clock, domain, grounding, live_data, memory
from .actions import run_tool, tool_specs
from .config import (
    corpus_language_setting,
    coverage_gate,
    coverage_min_cosine,
    coverage_min_rerank,
    coverage_min_score,
    data_dir,
    faq_max_searches,
    faq_top_k,
)
from .llm import LLMError, get_llm
from .notify import notify_new_ticket
from .observability import METRICS
from .rag import get_retriever
from .schemas import Handoff, Source, ToolCall
from .store import get_store

# MIN_SCORE (portão sem fonte) e ELIGIBLE_STATUS são do DOMÍNIO; `agents.MIN_SCORE` segue valendo (__getattr__).
# Híbrido: trecho sem termo em comum (sinônimo) só conta como fonte com cosseno >= MIN_COSINE E perto do
# melhor cosseno da busca (COSINE_MARGIN). Medido no corpus de exemplo com o MiniLM multilíngue (30/10/2026):
# sinônimo certo 0,44; vizinhos de pergunta bem respondida 0,50–0,53 com o melhor em 0,75; pergunta sem
# fonte <= 0,19. O cosseno muda de escala com o modelo: recalibre no corpus real, com o eval.
MIN_COSINE = 0.4
COSINE_MARGIN = 0.15
MAX_TOOL_ROUNDS = 3
_PROMPTS = Path(__file__).parent / "prompts"
# Busca web do servidor da Anthropic (o modelo decide a consulta; a API executa e devolve com citação). No agente geral
# ela vai ao lado das tools de câmbio e clima (FX_TOOL, WEATHER_TOOL): o modelo escolhe entre as três.
# Variante 20260209 (filtro dinâmico) vale para Opus 5.5/Sonnet 5.5; modelo antigo ou Vertex: web_search_20250305.
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 2}


@dataclass
class Context:
    text: str
    language: str
    user_id: str
    conversation_id: str
    intent: str = "faq"
    history: list[dict] = field(default_factory=list)
    user_summary: str = ""
    conversation_digest: str = ""  # falas desta conversa que saíram da janela recente (pipeline._digest)
    ledger: str = ""  # "Fatos da conversa": ids, valores e assunto extraídos por código (app/memory.py)
    facts: dict = field(default_factory=dict)
    handoff_reason: str | None = None


@dataclass
class AgentResult:
    agent: str
    status: str
    text: str = ""
    sources: list[Source] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    facts: dict = field(default_factory=dict)
    reason: str | None = None
    pending_action: str | None = None
    handoff: Handoff | None = None
    evidence: list[str] = field(default_factory=list)  # base dos números: fonte, resultado de tool, template
    # Achados que pedem outro especialista: [{"agent": "faq", "why": "...", "hint": "..."}]. Vão ao supervisor LLM no
    # tool_result e ele decide (com um lembrete se ignorar); o motor de tabela insere o passo se a transição estiver
    # em ALLOWED e houver orçamento (replanejamento por achado, não só por falha).
    needs: list[dict] = field(default_factory=list)
    ms: float | None = None  # duração do passo (supervisor._invoke); entra na árvore de passos da resposta

    def for_supervisor(self) -> str:
        """O que o supervisor LLM enxerga como tool_result: status, texto e fatos — nada de dado bruto extra."""
        return json.dumps({"status": self.status, "reason": self.reason, "text": self.text, "facts": self.facts,
                           "sources": [s.id for s in self.sources], "pending_action": self.pending_action,
                           "needs": self.needs},
                          ensure_ascii=False)


def _t(ctx: Context, pt: str, en: str) -> str:
    return en if ctx.language == "en" else pt


def specialist_history() -> bool:
    """SPECIALIST_HISTORY=on devolve o histórico cru aos especialistas (desenho anterior)."""
    return os.getenv("SPECIALIST_HISTORY", "off").lower() == "on"


def llm_history(ctx: Context, final_user: str) -> list[dict]:
    """Memória curta dos especialistas.

    Só o router lê o histórico; os especialistas
    NÃO guardam estado e recebem a pergunta autossuficiente que o router reescreveu (`standalone`), mais o livro de
    fatos (ids e números vindos de resultado de ferramenta) e os resumos. Medido: com o especialista relendo 10 turnos
    crus, ele reinterpretava "e a outra?" do seu jeito (memória pass@1 0,72 → 0,84–0,875 só com a reescrita). Sem
    standalone (router offline, ou a mensagem já se basta) o histórico cru volta como antes.
    """
    standalone = str(ctx.facts.get("standalone") or "").strip()
    if not specialist_history() and ctx.history and standalone and standalone.casefold() != ctx.text.strip().casefold():
        final_user = (f"Pergunta completa (o roteador já resolveu as referências ao histórico; responda a ela): "
                      f"{standalone}\nMensagem original do cliente: {final_user}")
        if ctx.conversation_digest:
            final_user = f"[antes nesta conversa] {ctx.conversation_digest}\n\n{final_user}"
        if ctx.ledger:
            final_user = f"{ctx.ledger}\n\n{final_user}"
        if ctx.user_summary:
            final_user = f"[memória do usuário] {ctx.user_summary}\n\n{final_user}"
        return [{"role": "user", "content": final_user}]
    msgs: list[dict] = []
    for m in ctx.history[-10:]:
        role = "user" if m["role"] == "user" else "assistant"
        content = m["content"] if m["role"] != "human_agent" else f"[atendente humano] {m['content']}"
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"] += "\n" + content
        else:
            msgs.append({"role": role, "content": content})
    if msgs and msgs[0]["role"] == "assistant":
        msgs.pop(0)
    if ctx.conversation_digest:
        final_user = f"[antes nesta conversa] {ctx.conversation_digest}\n\n{final_user}"
    if ctx.ledger:
        final_user = f"{ctx.ledger}\n\n{final_user}"
    if ctx.user_summary:
        final_user = f"[memória do usuário] {ctx.user_summary}\n\n{final_user}"
    if msgs and msgs[-1]["role"] == "user":
        msgs[-1]["content"] += "\n" + final_user
    else:
        msgs.append({"role": "user", "content": final_user})
    return msgs


def latest_eligible(items: list[dict], tool: str, status_key: str = "status") -> dict | None:
    """O item mais recente (fim da lista) cujo status permite a ação; None = nenhum serve, não proponha nada."""
    allowed = domain.active().ELIGIBLE_STATUS.get(tool)
    fit = [i for i in items if allowed is None or i.get(status_key) in allowed]
    return fit[-1] if fit else None


def _today() -> str:
    d = clock.today()  # data do negócio (app/clock.py); o prompt não pode adivinhar o dia ("tomorrow (Oct 30)" num 31)
    return f"{d.isoformat()} ({d.strftime('%A')})"


# --- glossário: busca entre idiomas -----------------------------------------------------------
def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


@lru_cache(maxsize=4)
def _glossary_for(path: str, mtime: float) -> tuple[tuple[str, tuple[str, ...]], ...]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    # valor em lista ou texto: um glossário real veio com texto ("conta corrente": "bank account") e era ignorado
    # inteiro (nenhuma pergunta em inglês ganhava o termo em português)
    return tuple((pt, tuple([en] if isinstance(en, str) else en)) for pt, en in raw.items()
                 if not pt.startswith("_") and isinstance(en, (list, str)) and en)


def glossary() -> tuple[tuple[str, tuple[str, ...]], ...]:
    path = data_dir() / "glossary.json"
    try:
        return _glossary_for(str(path), path.stat().st_mtime)  # recarrega se o arquivo mudar
    except FileNotFoundError:
        return ()


def _has(folded_text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(_fold(term))}(?!\w)", folded_text) is not None


def expand_query(text: str) -> str:
    """Acrescenta à consulta os termos do outro idioma (glossário pt<->en), por palavra ou expressão inteira.

    Medido: "How many installments in Crediário?" não achava o documento em português; a mesma
    pergunta em português trazia o relevante em 1º. O texto original vem primeiro e fica intacto; termo que não
    existe no corpus não muda o score BM25 dos documentos. Mesma expansão com e sem LLM (a busca vem antes).
    """
    folded = _fold(text)
    extra: list[str] = []
    for pt, ens in glossary():
        if _has(folded, pt):
            extra += [e for e in ens if not _has(folded, e)]
        elif any(_has(folded, e) for e in ens):
            extra.append(pt)
    extra = list(dict.fromkeys(extra))
    return f"{text} {' '.join(extra)}" if extra else text


# --- faq -------------------------------------------------------------------------------------
def rerank_threshold(gate: dict | None = None) -> float | None:
    """Limiar da nota do cross-encoder no portão sem fonte, na mesma ordem dos outros limiares: COVERAGE_MIN_RERANK
    (env) → `gate` do buscador escolhido (calibrado PARA ele; o rag só o entrega se nada caiu e a busca é a mesma:
    modelo, ordem, pool e caracteres) → MIN_RERANK do domínio (`run_evals --calibrate-rerank-gate --apply`, que
    também atualiza o da escolha) → None (vale o portão BM25/cosseno)."""
    own = (gate or {}).get("min_rerank")
    if own is None:
        own = getattr(domain.active(), "MIN_RERANK", None)
    return coverage_min_rerank(own)


def covered_hits(found: list, min_score: float | None = None, min_cosine: float | None = None,
                 gate: dict | None = None) -> list:
    """Portão de cobertura: trechos que contam como fonte. Mesma função no agente e na calibração do eval.

    Limiar: argumento (calibração) → COVERAGE_MIN_SCORE / COVERAGE_MIN_COSINE (env) → `gate` (limiares que o
    --choose-retriever calibrou PARA o retriever escolhido; o rag só o entrega se nada caiu) → MIN_SCORE/MIN_COSINE.
    """
    gate = gate or {}
    if min_score is None and min_cosine is None and (rr := rerank_threshold(gate)) is not None:
        scores = [h.rerank for h in found if h.rerank is not None]
        if scores:  # buscador com rerank: a nota do cross-encoder decide (separa com × sem fonte melhor que o BM25)
            return list(found) if max(scores) >= rr else []
    threshold = min_score if min_score is not None else coverage_min_score(
        gate.get("min_score", domain.active().MIN_SCORE))
    floor = min_cosine if min_cosine is not None else coverage_min_cosine(gate.get("min_cosine", MIN_COSINE))
    best = max((h.cosine for h in found if h.cosine is not None), default=0.0)
    return [h for h in found if h.bm25 >= threshold
            or (h.cosine is not None and h.cosine >= max(floor, best - COSINE_MARGIN))]


def _web_evidence(content) -> tuple[list[str], list[Source]]:
    """Evidência e fontes da busca web: trechos citados (cited_text) e título/data de cada resultado.

    O corpo da página vem cifrado (encrypted_content) e não é legível; o que dá para conferir são as citações
    dos blocos de texto e os metadados dos resultados. Erro da busca chega como objeto, não lista: sem evidência.
    """
    evidence: list[str] = []
    sources: dict[str, Source] = {}
    for block in content:
        kind = getattr(block, "type", None)
        if kind == "web_search_tool_result" and isinstance(getattr(block, "content", None), list):
            for r in block.content:
                if getattr(r, "type", None) == "web_search_result" and getattr(r, "url", None):
                    sources.setdefault(r.url, Source(id=r.url, title=getattr(r, "title", "") or r.url, url=r.url))
                    evidence.append(f"{getattr(r, 'title', '')} ({getattr(r, 'page_age', '') or 's/ data'})")
        elif kind == "text":
            for c in getattr(block, "citations", None) or []:
                if getattr(c, "cited_text", None):
                    evidence.append(f"{getattr(c, 'title', '')}: {c.cited_text}")
                if getattr(c, "url", None):
                    sources.setdefault(c.url, Source(id=c.url, title=getattr(c, "title", "") or c.url, url=c.url))
    return evidence, list(sources.values())


def _lang_tail(ctx: Context) -> str:
    """Diretiva de idioma no FIM da mensagem do turno (onde o modelo mais pesa), não só no prompt de sistema.

    Medido (4 chamadas reais): pergunta em inglês com um termo em português ou
    trechos do site em português saía em português ~50% das vezes; o prompt de sistema em português vencia.
    """
    tail = "\n\n" + grounding.DIRECTIVE.get(ctx.language, grounding.DIRECTIVE["pt"])
    # o que o sistema faz e o que exige confirmação/aprovação: fonte citável em vez de regra lembrada de memória
    tail = "\n\n" + capabilities.prompt_block(ctx.language) + tail
    if tried := ctx.facts.get("attempted_steps"):  # caso em andamento (app/casestate.py): não repetir conselho
        tail = ("\n\nPassos já tentados neste caso, sem sucesso (não repita o mesmo conselho: avance para o próximo "
                "passo ou diga que precisa de um humano): " + " | ".join(tried[-4:])) + tail
    return tail


_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


def live_missing(text: str, live, language: str) -> list[str]:
    """Rótulos dos valores obrigatórios (`live.must`, ou a própria lista) que a resposta não traz: número com a
    tolerância do arredondamento que o prompt permite ("19 °C" vale para 19,4). Vírgula ou ponto decimal."""
    must = getattr(live, "must", live) or []
    nums = [float(n.replace(",", ".")) for n in _NUM.findall(text or "")]
    return [en if language == "en" else pt for pt, en, value, tol in must
            if not any(abs(n - value) <= tol + 1e-9 for n in nums)]


def live_musts(got: list) -> list[tuple[str, str, float, float]]:
    """Valores obrigatórios do turno (`LiveResult.must`); com mais de uma consulta, o rótulo leva a moeda ou a cidade
    (o pedido de reparo diz de qual consulta é o valor que faltou)."""
    if len(got) == 1:
        return list(got[0].must)
    return [(f"{pt} ({live.subject})", f"{en} ({live.subject})", value, tol)
            for live in got for pt, en, value, tol in live.must]


def _live(ctx: Context, got: list, text: str | None = None, calls: list | None = None,
          facts: dict | None = None) -> AgentResult:
    """Resposta de câmbio/clima: o texto bruto da API é a evidência e a consulta é a fonte.

    Sem `text`, vale o texto pronto da consulta (motor sem LLM, LLM que caiu depois da consulta, ou redação que não
    trouxe os valores nem depois do reparo). `live_must` vai fora de `facts` (que vai ao contexto dos agentes): a
    resposta final do supervisor é conferida contra ele no pipeline."""
    evidence = [e for live in got for e in (*live.evidence, live.text_pt, live.text_en)] + [f"Hoje é {_today()}"]
    sources = list({live.url: Source(id=live.url, title=live.source, url=live.url) for live in got}.values())
    base = {"live_data": "+".join(dict.fromkeys(live.kind for live in got)), "web_search": False}
    result = AgentResult("faq", "ok", text=text or " ".join(live.text(ctx.language) for live in got), sources=sources,
                         evidence=evidence, facts={**base, **(facts or {})}, tool_calls=list(calls or []))
    result.live_must = live_musts(got)
    return result


# --- general: o MODELO escolhe a consulta ---------------------------------------------------------------------------
# Câmbio e clima são tools de cliente ao lado da busca web do servidor: o modelo decide qual chamar (ou nenhuma); o
# código valida a entrada (`live_args`), consulta a API (app/live_data.py) e devolve o texto bruto como tool_result.
# Antes um detector por regex decidia no código e errava a pergunta fora do padrão (ensaio, rodada 11: "quanto ta a
# libra hoje" e "weather like in Recife right now" foram à busca web e saíram sem o dado; "Bitcoin to US dollar" virou
# a PTAX do dólar). O detector fica só para o motor sem LLM.
FX_TOOL = {
    "name": "currency_rate",
    "description": ("Cotação oficial PTAX do Banco Central do Brasil: quanto vale 1 unidade de uma moeda estrangeira "
                    "em reais, na compra e na venda, com a data do boletim. Chame para pergunta de câmbio, cotação ou "
                    f"conversão para reais destas moedas: {', '.join(live_data.CURRENCIES)}. Sem `date` = hoje; fim "
                    "de semana e feriado voltam com o último dia útil que teve boletim. Outra moeda ou ativo (ex.: "
                    "bitcoin) não é desta tool: use a busca web."),
    "input_schema": {"type": "object", "additionalProperties": False, "required": ["currency"], "properties": {
        "currency": {"type": "string", "enum": list(live_data.CURRENCIES),
                     "description": "código ISO 4217 da moeda (ex.: USD = dólar, EUR = euro, GBP = libra)"},
        "date": {"type": "string", "description": "dia da cotação no formato AAAA-MM-DD, até hoje; omita para hoje"}}},
}
WEATHER_TOOL = {
    "name": "weather_forecast",
    "description": ("Previsão do tempo de uma cidade (Open-Meteo; wttr.in quando a primeira não responde): mínima, "
                    "máxima, chance de chuva e o céu do dia. Chame para pergunta de clima, chuva ou temperatura de "
                    "uma cidade hoje, amanhã ou depois de amanhã."),
    "input_schema": {"type": "object", "additionalProperties": False, "required": ["city"], "properties": {
        "city": {"type": "string", "description": "nome da cidade, sem estado nem país (ex.: Porto Alegre)"},
        "day": {"type": "string", "enum": list(live_data.DAYS), "description": "dia da previsão; omita para hoje"}}},
}
LIVE_TOOLS = (FX_TOOL, WEATHER_TOOL)
MAX_LIVE_CALLS = 3  # consultas ao vivo por turno ("dólar, euro e libra"); além disso, o modelo responde com o que tem
GENERAL_ROUNDS = 5  # voltas do loop: escolha, consulta, redação e 1 reparo, com folga para 2 voltas de tool
MAX_CITY = 80
_CITY_NAME = re.compile(r"[^\W\d_]+(?:[ '’.-]+[^\W\d_]+)*\.?")  # letras de qualquer idioma: nada que mude a URL
_DAY_ALIASES = {**{_fold(day): offset for day, offset in live_data.DAYS.items()},
                "agora": 0, "today": 0, "now": 0, "tomorrow": 1, "day after tomorrow": 2}
_NO_DATA = {"empty": {"fx": "a PTAX não publicou boletim dessa moeda na semana até a data pedida",
                      "weather": "a fonte de clima não achou essa cidade (confira o nome) ou não trouxe o dia pedido"},
            "error": "a fonte não respondeu a tempo ou deu erro", "off": "a consulta ao vivo está desligada"}


def _only(args: dict, allowed: set[str]) -> None:
    extra = sorted(str(k) for k in set(args) - allowed)
    if extra:
        raise ValueError(f"campo fora do schema: {', '.join(extra)[:80]}")


def live_args(name: str, args) -> dict:
    """Entrada de `currency_rate`/`weather_forecast` validada no servidor (o schema orienta o modelo; quem confere é o
    código). Devolve os argumentos normalizados; ValueError com o motivo, que volta ao modelo como tool_result de erro.
    """
    if not isinstance(args, dict):
        raise ValueError("passe um objeto JSON com os campos da tool")
    if name == FX_TOOL["name"]:
        _only(args, {"currency", "date"})
        code = str(args.get("currency") or "").strip().upper()
        if code not in live_data.CURRENCIES:
            raise ValueError(f"currency deve ser um destes códigos ISO 4217: {', '.join(live_data.CURRENCIES)} "
                             "(outra moeda: use a busca web)")
        out: dict = {"currency": code}
        raw = str(args.get("date") or "").strip()
        if raw and _DAY_ALIASES.get(_fold(raw)) != 0:  # "hoje"/"today" no lugar da data = omitida
            try:
                wanted = date.fromisoformat(raw)
            except ValueError:
                raise ValueError("date no formato AAAA-MM-DD (ou omita para hoje)") from None
            if wanted > clock.today():
                raise ValueError("date no futuro: a PTAX só tem cotação já publicada (omita para hoje)")
            out["date"] = wanted.isoformat()
        return out
    if name == WEATHER_TOOL["name"]:
        _only(args, {"city", "day"})
        city = " ".join(str(args.get("city") or "").split(",")[0].split())  # "Porto Alegre, RS" → a cidade
        if not city:
            raise ValueError("city vazia: passe o nome da cidade")
        if len(city) > MAX_CITY:
            raise ValueError(f"city com mais de {MAX_CITY} caracteres: passe só o nome da cidade")
        if not _CITY_NAME.fullmatch(city):
            raise ValueError("city só com letras, espaço, hífen, apóstrofo ou ponto (o nome da cidade, sem número)")
        day = " ".join(_fold(str(args.get("day") or "hoje")).split())
        offset = _DAY_ALIASES.get(day)
        if offset is None:  # data AAAA-MM-DD no lugar do dia: vale se cair em hoje, amanhã ou depois de amanhã
            try:
                offset = (date.fromisoformat(day) - clock.today()).days
            except ValueError:
                offset = None
        if offset not in live_data.DAYS.values():
            raise ValueError(f"day deve ser um destes: {', '.join(live_data.DAYS)} (ou omita para hoje)")
        return {"city": city, "day": next(d for d, n in live_data.DAYS.items() if n == offset)}
    raise ValueError(f"tool desconhecida: {name}")


def _shown(raw) -> dict:
    """Argumentos recusados como chegaram, curtos: vão ao caminho do caso."""
    return {str(k)[:40]: str(v)[:80] for k, v in list(raw.items())[:4]} if isinstance(raw, dict) else {}


@dataclass
class _Turn:
    """O que o loop do agente geral já trouxe; sobrevive a uma queda do LLM no meio do loop."""
    got: list = field(default_factory=list)  # dados ao vivo consultados (LiveResult), na ordem
    order: list = field(default_factory=list)  # tools na ordem em que o modelo chamou: ToolCall ou o server_tool_use
    blocks: list = field(default_factory=list)  # conteúdo de todas as voltas: a evidência da busca web

    def calls(self) -> list[ToolCall]:
        """Tools do turno para o caminho do caso: as de dado ao vivo (executadas aqui) e a busca web do servidor, com
        `ok` pelo resultado da busca (lista de páginas = ok; objeto de erro = falhou)."""
        found = {getattr(b, "tool_use_id", None): isinstance(getattr(b, "content", None), list)
                 for b in self.blocks if getattr(b, "type", None) == "web_search_tool_result"}
        out = []
        for c in self.order:
            if isinstance(c, ToolCall):
                out.append(c)
                continue
            query = c.input.get("query", "") if isinstance(getattr(c, "input", None), dict) else ""
            out.append(ToolCall(name=WEB_SEARCH["name"], args={"query": str(query)[:200]}, ok=found.get(c.id, False)))
        return out

    def facts(self) -> dict:
        """`live_tool`: o que o modelo escolheu (nomes na ordem, "+" entre eles; "none" = respondeu sem tool)."""
        names = [c.name for c in self.calls()]
        return {"web_search": WEB_SEARCH["name"] in names, "live_tool": "+".join(dict.fromkeys(names)) or "none"}


def _live_tool_result(block, language: str, turn: _Turn) -> dict:
    """Executa a tool de dado ao vivo que o modelo chamou: valida, consulta e devolve o tool_result (o texto bruto da
    API entre <untrusted_content>, ou o motivo do erro com is_error)."""
    name = str(getattr(block, "name", "") or "?")
    raw = getattr(block, "input", None)
    try:
        if sum(isinstance(c, ToolCall) for c in turn.order) >= MAX_LIVE_CALLS:
            raise ValueError(f"limite de {MAX_LIVE_CALLS} consultas ao vivo por turno: responda com o que já tem")
        args = live_args(name, raw)
    except ValueError as exc:
        turn.order.append(ToolCall(name=name, args=_shown(raw), ok=False))
        METRICS.inc("live_tool_calls_total", tool=name, outcome="invalid")
        return {"type": "tool_result", "tool_use_id": block.id, "content": f"Entrada inválida: {exc}.",
                "is_error": True}
    if name == FX_TOOL["name"]:
        kind = "fx"
        live, outcome = live_data.fx_quote(args["currency"],
                                           date.fromisoformat(args["date"]) if "date" in args else None)
    else:
        kind = "weather"
        live, outcome = live_data.forecast(args["city"], live_data.DAYS[args["day"]])
    turn.order.append(ToolCall(name=name, args=args, ok=live is not None))
    METRICS.inc("live_tool_calls_total", tool=name, outcome=outcome)
    if live is None:
        why = _NO_DATA.get(outcome, _NO_DATA["error"])
        why = why[kind] if isinstance(why, dict) else why
        return {"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                "content": f"Sem dado: {why}. Não invente número: use a busca web ou diga ao cliente que não "
                           "conseguiu o dado agora."}
    turn.got.append(live)
    # mesma moldura da redação de antes: o texto bruto (e o arredondado) da API, mais a frase pronta da consulta
    return {"type": "tool_result", "tool_use_id": block.id, "is_error": False,
            "content": f"<untrusted_content>\n{chr(10).join(live.evidence)}\n{live.text(language)}\n"
                       "</untrusted_content>"}


def _general_llm(ctx: Context, llm, turn: _Turn) -> AgentResult | None:
    """Loop manual de tool use do agente geral: o modelo escolhe câmbio, clima, a busca web ou nenhuma tool.

    pause_turn (busca web do servidor parada no meio) reenvia a volta, sem mensagem nova. Na resposta final com dado
    ao vivo, o código confere os valores obrigatórios (`live_missing`): faltou, 1 volta a mais pede o que faltou;
    ainda faltando, vale o texto pronto da consulta (`live_repair` no passo). Medido: uma resposta em inglês omitiu a
    chance de chuva que estava no resultado, e o prompt já a pedia. None = o modelo não fechou a resposta."""
    tools = [*LIVE_TOOLS, WEB_SEARCH] if live_data.enabled() else [WEB_SEARCH]
    system = domain.prompt("general.md").format(language=ctx.language, today=_today())
    messages: list = llm_history(ctx, ctx.text + _lang_tail(ctx))
    repair = None
    for _ in range(GENERAL_ROUNDS):
        resp = llm.create(system, messages, tools, max_tokens=4096)
        if resp.stop_reason == "max_tokens":
            raise LLMError("resposta truncada em max_tokens", "max_tokens")
        turn.blocks += list(resp.content)
        turn.order += [b for b in resp.content
                       if b.type == "server_tool_use" and getattr(b, "name", None) == WEB_SEARCH["name"]]
        uses = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason == "pause_turn" or (resp.stop_reason == "tool_use" and uses):
            messages.append({"role": "assistant", "content": resp.content})  # conteúdo inteiro, sem editar
            if uses:  # todos os resultados numa mensagem só
                messages.append({"role": "user", "content": [_live_tool_result(b, ctx.language, turn) for b in uses]})
            continue
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if not text:
            return None
        if not turn.got:  # busca web (ou nenhuma tool): a evidência é o resultado da busca, nunca a própria resposta
            evidence, sources = _web_evidence(turn.blocks)
            if evidence:  # a data vai no prompt (general.md): dado nosso; busca com erro segue sem evidência
                evidence.append(f"Hoje é {_today()}")
            return AgentResult("faq", "ok", text=text, sources=sources, facts=turn.facts(), evidence=evidence,
                               tool_calls=turn.calls())
        missing = live_missing(text, live_musts(turn.got), ctx.language)
        if missing and repair is None:
            repair = "llm"
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": "Sua resposta anterior deixou de fora: " + ", ".join(missing)
                             + ". Responda de novo trazendo esses valores do resultado da consulta."})
            continue
        if missing:
            text, repair = None, "template"
        return _general_live(ctx, turn, text, repair)
    # voltas esgotadas: com o reparo pedido, vale o texto pronto da consulta; sem dado, o chamador decide
    return _general_live(ctx, turn, None, "template") if turn.got and repair else None


def _general_live(ctx: Context, turn: _Turn, text: str | None, repair: str | None = None) -> AgentResult:
    """Resposta com dado ao vivo do loop: a da consulta (`_live`) mais o que a busca web do mesmo turno trouxe."""
    facts = turn.facts()
    if repair:
        facts["live_repair"] = repair
        METRICS.inc("live_data_repair_total", kind="+".join(dict.fromkeys(live.kind for live in turn.got)),
                    outcome=repair)
    result = _live(ctx, turn.got, text=text, calls=turn.calls(), facts=facts)
    evidence, sources = _web_evidence(turn.blocks)
    result.evidence = [*evidence, *result.evidence]
    result.sources += [s for s in sources if s.id not in {x.id for x in result.sources}]
    return result


def _general(ctx: Context) -> AgentResult:
    """Pergunta geral (clima, câmbio, notícia). Com LLM, o modelo escolhe a tool (`_general_llm`).

    Sem LLM (offline, ou o LLM caiu antes de trazer dado), o detector por regex escolhe a consulta e vale o texto
    pronto dela; sem dado ao vivo, resposta honesta sem número inventado."""
    llm = get_llm("agent")
    if llm.enabled:
        turn = _Turn()
        try:
            result = _general_llm(ctx, llm, turn)
            if result is not None:
                return result
        except LLMError:
            pass
        if turn.got:  # o LLM caiu depois da consulta que ele escolheu: o texto pronto dela, sem detector
            return _general_live(ctx, turn, None)
    previous = next((m.get("content") for m in reversed(ctx.history or []) if m.get("role") == "user"
                     and (m.get("content") or "").strip() != ctx.text.strip()), None)
    live = live_data.lookup(ctx.text, previous=previous)
    if live:
        return _live(ctx, [live])
    text = _t(ctx, "Não tenho acesso a dados em tempo real (clima, câmbio, notícias) neste modo, então não vou "
                   "chutar um número. Consulte uma fonte oficial.",
              "I don't have real-time data (weather, exchange rates, news) in this mode, so I won't guess a "
              "number. Please check an official source.")
    return AgentResult("faq", "ok", text=text, facts={"web_search": False}, evidence=[text])  # template nosso


_PASSAGE_REF = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def cite_ids(text: str, hits: list) -> str:
    """"[1]" / "[1, 2]" (número da passagem no prompt) viram "[<id do documento>]".

    O número só tem sentido dentro do prompt do agente. Quando a resposta do agente vai direto ao cliente (atalho do
    supervisor, plano de 1 passo) ela precisa citar a fonte como a lista `sources` da resposta a nomeia; antes era o
    supervisor LLM que fazia essa troca ao redigir. Número fora do intervalo fica como está.
    """
    def swap(m: re.Match) -> str:
        nums = [int(n) for n in re.split(r"\s*,\s*", m.group(1))]
        if not all(1 <= n <= len(hits) for n in nums):
            return m.group(0)
        return "[" + ", ".join(dict.fromkeys(hits[n - 1].doc.id for n in nums)) + "]"

    return _PASSAGE_REF.sub(swap, text)


# Só o plural, que é como o agente se refere ao conjunto do prompt; "passagem" no singular é palavra comum em pt
# (passagem aérea) e trocá-la mudaria o sentido.
_PROMPT_TERMS = {"passagens": "fontes", "passages": "sources"}
_PROMPT_TERM_RE = re.compile(r"\b(" + "|".join(_PROMPT_TERMS) + r")\b", re.IGNORECASE)


def customer_terms(text: str) -> str:
    """"passagens"/"passages" é o nome que o PROMPT dá aos trechos; para o cliente são as fontes.

    Sem esta troca, com o atalho do supervisor ligado, 15 respostas do faq diziam "The passages don't say..." direto ao
    cliente (no caminho normal é a redação final do supervisor que troca o termo). Mesmo gênero em pt (as passagens →
    as fontes); maiúscula preservada.
    """
    def swap(m: re.Match) -> str:
        new = _PROMPT_TERMS[m.group(1).lower()]
        return new.capitalize() if m.group(1)[0].isupper() else new

    return _PROMPT_TERM_RE.sub(swap, text)


# --- consultas do faq: idioma do corpus, uma por item -------------------------------------------
# Medido: "What's the difference between <produto A> and <produto B>?" ia CRU ao denso; o trecho
# com os dois preços estava no corpus e fora do top-3, o faq dizia NOT_IN_SOURCES e o supervisor escalava (40 das 49
# falhas de escalada medidas foram escaladas sem precisar). A busca agora parte da pergunta autônoma do router, no
# idioma do corpus, com uma consulta por item comparado.
LANG_NAMES = {"pt": "português", "en": "inglês"}


@lru_cache(maxsize=4)
def _index_language(directory: str, stamp: tuple) -> str:
    from .rag import get_index
    from .router import detect_language

    votes = Counter(detect_language(f"{d.title}. {d.text}") for d in get_index().docs)
    return "en" if votes["en"] > votes["pt"] else "pt"


def corpus_language() -> str:
    """Idioma das consultas: CORPUS_LANGUAGE (env) → CORPUS_LANGUAGE do domínio → maioria dos trechos do índice."""
    setting = corpus_language_setting()
    if setting != "auto":
        return setting
    own = getattr(domain.active(), "CORPUS_LANGUAGE", None)
    if own in ("pt", "en"):
        return own
    from .rag import _stamp

    d = data_dir()
    return _index_language(str(d), _stamp(d)) if d.is_dir() else "pt"


def to_language(text: str, target: str) -> str:
    """Troca, numa passada, os termos do glossário pelos do idioma `target` (pt = chave; en = 1º valor).

    Expressão mais longa primeiro ("opening hours" antes de "hours"); sem caixa e sem acento, por palavra inteira.
    O resto (nomes de produto, números) fica como está: sem LLM, é a consulta no idioma do corpus que dá para fazer.
    """
    pairs: dict[str, str] = {}
    for pt, ens in glossary():
        if target == "pt":
            pairs.update({_fold(e): pt for e in ens})
        elif ens:
            pairs[_fold(pt)] = ens[0]
    if not pairs:
        return text
    folded = _fold(text)
    if len(folded) != len(text):  # caractere que muda de tamanho ao dobrar: troca sobre o texto dobrado
        text = folded
    alt = "|".join(re.escape(t) for t in sorted(pairs, key=len, reverse=True))
    out, last = [], 0
    for m in re.finditer(rf"(?<!\w)(?:{alt})(?!\w)", folded):
        out += [text[last:m.start()], pairs[m.group(0)]]
        last = m.end()
    return "".join([*out, text[last:]])


# Palavras de função que abrem ou fecham uma sequência com maiúscula ("Do I", "What's the") e não são nome de nada.
_FUNCTION = set("""a an and are as at be by can could do does for from has have how i if in is it of on or
should than that the their there this to was we what what's whats which who why will with would you your
o os as um uma de do da dos das e é em no na nos nas para por com que como qual quais quanto quanta meu minha
eu posso preciso tem existe ou vs versus x""".split())
_RUN = re.compile(r"(?<![\w])[A-ZÀ-Ý0-9][\w'’\-]*(?:\s+[A-ZÀ-Ý0-9][\w'’\-]*)*")
_LINK = re.compile(r"^\s*(?:,|and|or|e|ou|vs\.?|versus|x|&)\s*(?:(?:the|a|o|as|os)\s+)?$", re.IGNORECASE)
_COMPARE = re.compile(r"\b(?:differen\w*|compar\w*|versus|vs|between|better|cheaper|diferen\w*|entre|melhor"
                      r"|mais\s+barat\w*)\b", re.IGNORECASE)
_BETWEEN = re.compile(r"\b(?:between|entre)\s+(.+?)\s+(?:and|e)\s+(.+?)\s*(?:[?.!;]|$)", re.IGNORECASE)
_ARTICLE = re.compile(r"^(?:the|a|an|o|a|os|as)\s+", re.IGNORECASE)


def _entity_spans(text: str) -> list[tuple[int, int, str]]:
    """Nomes próprios: sequências de palavras com maiúscula/dígito, sem as palavras de função nas pontas; palavra solta
    no começo da frase ("Qual", "Does") não conta."""
    spans = []
    for m in _RUN.finditer(text):
        words = list(re.finditer(r"\S+", m.group(0)))
        while words and words[0].group(0).lower().strip("'’") in _FUNCTION:
            words.pop(0)
        while words and words[-1].group(0).lower().strip("'’") in _FUNCTION:
            words.pop()
        if not words:
            continue
        a, b = m.start() + words[0].start(), m.start() + words[-1].end()
        if len(words) == 1 and re.search(r"(?:^|[.!?]\s*)$", text[:a]):
            continue
        spans.append((a, b, text[a:b]))
    return spans


def split_entities(text: str, limit: int = 3) -> list[str]:
    """Itens de uma comparação ou lista ("diferença entre X e Y", "X vs Y", "X, Y e Z"); [] quando não é.

    Dois ou mais nomes próprios ligados por e/ou/vírgula/vs, ou com palavra de comparação na frase; sem nomes com
    maiúscula, o padrão "entre X e Y" / "between X and Y". Até `limit` itens (o teto de buscas do turno).
    """
    return _split(text, limit)[0]


def _split(text: str, limit: int) -> tuple[list[str], bool]:
    """(itens, achados por nome próprio). Nomes ligados entre si (e/ou/vírgula/vs) são os itens; um nome solto fora
    da ligação ("... qual é mais barato para o Boleto?") fica no assunto, não vira item."""
    spans = _entity_spans(text)
    links = [i for i in range(len(spans) - 1) if _LINK.match(text[spans[i][1]:spans[i + 1][0]])]
    linked = {n for i in links for n in (spans[i][2], spans[i + 1][2])}
    names = list(dict.fromkeys(n for _, _, n in spans if not linked or n in linked))
    if len(names) >= 2 and (linked or _COMPARE.search(text)):
        return names[:limit], True
    m = _BETWEEN.search(text)
    if m:
        items = [_ARTICLE.sub("", g.strip()).strip() for g in m.groups()]
        if all(items) and items[0].lower() != items[1].lower():
            return items[:limit], False
    return [], False


def _aspect(text: str, entities: list[str]) -> str:
    """O que a pergunta quer saber de cada item: a frase sem os itens, sem comparação e sem palavra de função."""
    rest = text
    for e in entities:
        rest = re.sub(re.escape(e), " ", rest, flags=re.IGNORECASE)
    rest = _COMPARE.sub(" ", rest)
    words = [w for w in re.findall(r"[\w'’\-]+", rest) if w.lower().strip("'’") not in _FUNCTION and len(w) > 1]
    return " ".join(words)


@dataclass
class QueryPlan:
    queries: list[str]  # consultas no idioma do corpus, na ordem em que rodam
    entities: list[str]  # itens comparados ([] = pergunta única)
    language: str  # idioma do corpus
    translated: list[bool]  # a consulta foi trocada de idioma (vai crua à busca; as outras passam pelo glossário)


def plan_queries(text: str, standalone: str | None = None, hints: list[str] | tuple = (),
                 corpus_lang: str | None = None, max_searches: int | None = None) -> QueryPlan:
    """Consultas do turno, sem LLM: parte de `standalone` (contrato do router) quando existe, senão da mensagem.

    - idioma: a pergunta noutro idioma que o do corpus tem os termos do glossário trocados (to_language);
    - comparação/lista: uma consulta por item, "<item> <o que se quer saber>", até o teto de buscas;
    - senão uma consulta só (com as dicas do supervisor, `query_hints`).
    """
    from .router import detect_language

    lang = corpus_lang or corpus_language()
    cap = max_searches or faq_max_searches()
    base = (standalone or "").strip() or text.strip()
    other = detect_language(base) != lang

    def render(q: str) -> tuple[str, bool]:
        out = to_language(q, lang) if other else q
        return out, out != q

    entities, named = _split(base, cap)
    if len(entities) >= 2:
        aspect = _aspect(base, entities)
        rendered = [render(f"{e} {aspect}".strip()) for e in entities]
        if not named and len(rendered) < cap:  # "entre x e y" sem nome próprio: o corte pode errar, a frase vai junto
            rendered.append(render(" ".join([base, *[h for h in hints if h]])))
    else:
        entities = []
        rendered = [render(" ".join([base, *[h for h in hints if h]]))]
    return QueryPlan([q for q, _ in rendered], entities, lang, [t for _, t in rendered])


@dataclass
class Retrieval:
    plan: QueryPlan
    rankings: list[list]  # trechos que passaram no portão, por consulta
    hits: list  # fundidos por rodada, sem repetição, top-k

    @property
    def covered(self) -> bool:
        return bool(self.hits)


def covered_search(retriever, query: str, k: int, gate: dict | None = None) -> list:
    """Uma busca + o portão de cobertura ("sem fonte, sem afirmação"): só trechos que contam como fonte.

    `gate` (calibração) troca os limiares calibrados do buscador ({"min_score", "min_cosine"})."""
    found = retriever.search(query, k=k)
    gate = gate if gate is not None else getattr(retriever, "gate", None)
    hits = covered_hits(found, gate=gate)
    reranked = rerank_threshold(gate) is not None and any(h.rerank is not None for h in found)
    if not hits and found and not reranked and coverage_gate() == "bm25" and not str(retriever.name).startswith("bm25"):
        # O portão do buscador escolhido (cosseno do denso) recusou; o BM25 com o limiar do domínio tem a última
        # palavra antes de "sem fonte". Só o portão do denso fazia o eval de ponta a ponta perder handoff (90,2% →
        # 84,0% num domínio real: pergunta de código de recusa ia ao humano com a fonte no índice).
        from .rag import BM25Retriever, get_index

        hits = found if covered_hits(BM25Retriever(get_index()).search(query, k=k)) else []
    return hits


# Buscas do plano (2 ou 3 por turno) em paralelo. Medido no ensaio (rodada 10): com o denso + cross-encoder cada busca
# leva ~0,95 s de p50 em CPU e o faq as fazia em série. A fusão depende da ordem do plano (as palavras do cliente
# primeiro), então o resultado volta na ordem das consultas. Teto do PROCESSO para as buscas a mais
# (FAQ_SEARCH_PARALLEL, padrão 2; 0 = tudo em série): sem vaga (bateria com várias conversas ao mesmo tempo), a busca
# roda em série na thread do agente, sem fila e sem pico de RAM a mais (frente R2: 20 inferências ONNX simultâneas
# chegaram a 5,8 GB). O BM25 puro (~1 ms por busca) fica em série: a thread custaria mais que a busca.
def search_parallel() -> int:
    try:
        return max(0, int(os.getenv("FAQ_SEARCH_PARALLEL", "2")))
    except ValueError:
        return 2


@lru_cache(maxsize=4)
def _search_slots(n: int) -> threading.BoundedSemaphore:
    return threading.BoundedSemaphore(n)


def plan_rankings(retriever, queries: list[str], k: int, gate: dict | None = None) -> list[list]:
    """`covered_search` de cada consulta, na ordem de `queries`: a 1ª na thread de quem chama e as outras, ao mesmo
    tempo, em threads (com o contexto de quem chama: cassete, trace e o memo desligado da medida de latência)."""
    n = search_parallel()
    if n == 0 or len(queries) < 2 or str(getattr(retriever, "name", "")) == "bm25":
        return [covered_search(retriever, q, k, gate) for q in queries]
    slots = _search_slots(n)

    def one(q: str) -> list:
        try:
            return covered_search(retriever, q, k, gate)
        finally:
            slots.release()

    with ThreadPoolExecutor(max_workers=len(queries) - 1) as pool:
        futures = {}
        for i in range(1, len(queries)):
            if not slots.acquire(blocking=False):
                break  # sem vaga: esta e as seguintes rodam em série, aqui
            futures[i] = pool.submit(contextvars.copy_context().run, one, queries[i])
        return [futures[i].result() if i in futures else covered_search(retriever, q, k, gate)
                for i, q in enumerate(queries)]


def retrieve(text: str, standalone: str | None = None, hints: list[str] | tuple = (), retriever=None,
             k: int | None = None, gate: dict | None = None, queries: list[str] | None = None) -> Retrieval:
    """As buscas do plano, cada uma com o portão, fundidas por rodada (rag.merge_round_robin). Mesma função no agente
    e na calibração do portão por idioma (gate_by_language).

    `queries` (contrato do router, ctx.facts["search_queries"]): consultas já escritas pelo LLM no idioma da base;
    com elas o plano offline (glossário) não roda — é o caminho com LLM."""
    from .rag import merge_round_robin

    retriever = retriever or get_retriever()
    k = k or faq_top_k()
    clean = [q for q in (queries or []) if isinstance(q, str) and q.strip()][:faq_max_searches()]
    if clean:
        # As palavras do cliente são sempre a 1ª busca (medido: a pergunta em inglês achava o
        # trecho do fato em 1º; as consultas reescritas pelo LLM em português, não). Fundidas por rodada, o top-1
        # dela entra sempre no top-k.
        own = (standalone or text or "").strip()
        if own and own.casefold() not in {q.strip().casefold() for q in clean}:
            clean = [own, *clean]
    plan = (QueryPlan(clean, [], corpus_language(), [True] * len(clean)) if clean
            else plan_queries(text, standalone, hints))
    own = (standalone or text or "").strip()
    if not clean and not plan.entities and own and own.casefold() not in {q.strip().casefold() for q in plan.queries}:
        # Sem o router LLM (offline, ou o router não escreveu buscas) vale o mesmo: as palavras do cliente entram
        # cruas como 1ª busca. Medido: o plano offline trocava "bank account" por "conta corrente" no meio da
        # frase em inglês e o trecho do fato, 1º na pergunta crua, saía do top-5. Comparação fica com uma busca
        # por item (o orçamento de buscas é delas).
        plan = QueryPlan([own, *plan.queries], plan.entities, plan.language, [True, *plan.translated])
    rankings = plan_rankings(retriever, [q if done else expand_query(q)
                                         for q, done in zip(plan.queries, plan.translated, strict=True)], k, gate)
    return Retrieval(plan, rankings, merge_round_robin(rankings, k))


# --- portão por idioma ------------------------------------------------------------
# Medido: o piso de cosseno 0,88 calibrado sem perguntas em inglês e recusou 4 oficiais em inglês com a fonte no
# índice. A recusa tem de ser lida POR IDIOMA, com o mesmo caminho de busca do agente (o CLI do eval liga).
def gate_rates_by_language(outcomes: list[tuple[str, bool, bool]]) -> dict[str, dict]:
    """Taxas do portão por idioma a partir de (idioma, tem fonte esperada, respondeu).

    "respondeu" = o portão aceitou ao menos um trecho (com `relevant`, um trecho do gold). Por idioma: positives,
    answered, pos_answered, pos_refused (pergunta com fonte recusada), negatives, refused,
    neg_refused. Taxa sem denominador = None.
    """
    rows: dict[str, dict] = {}
    for lang, positive, answered in outcomes:
        row = rows.setdefault(lang, {"positives": 0, "answered": 0, "negatives": 0, "refused": 0})
        if positive:
            row["positives"] += 1
            row["answered"] += bool(answered)
        else:
            row["negatives"] += 1
            row["refused"] += not answered
    for row in rows.values():
        p, n = row["positives"], row["negatives"]
        row["pos_answered"] = round(row["answered"] / p, 3) if p else None
        row["pos_refused"] = round(1 - row["answered"] / p, 3) if p else None
        row["neg_refused"] = round(row["refused"] / n, 3) if n else None
    return dict(sorted(rows.items()))


def gate_by_language(cases: list[dict], retriever=None, gate: dict | None = None, k: int | None = None) -> dict:
    """Roda a busca do agente (retrieve: idioma do corpus, uma por item, portão) em cada caso e agrupa por idioma.

    Caso: {"question", "positive": bool, "language"? (senão detectado), "standalone"?, "relevant"? (ids do gold:
    só conta como respondido se um deles passar no portão)}. `gate` troca os limiares do buscador (varredura de
    calibração). Devolve gate_rates_by_language.
    """
    from .router import detect_language

    retriever = retriever or get_retriever()
    outcomes = []
    for case in cases:
        found = retrieve(case["question"], case.get("standalone"), retriever=retriever, k=k, gate=gate)
        relevant = set(case.get("relevant") or ())
        answered = bool({h.doc.id for h in found.hits} & relevant) if relevant else found.covered
        outcomes.append((case.get("language") or detect_language(case["question"]), bool(case.get("positive")),
                         answered))
    return gate_rates_by_language(outcomes)


SEARCH_TOOL = {
    "name": "search",
    "description": ("Busca trechos na base de conhecimento. Use só quando as passagens que você já tem não cobrem um "
                    "item da pergunta. Uma consulta curta por item, no idioma do corpus. Devolve passagens novas "
                    "numeradas, que você cita como [n]."),
    "input_schema": {"type": "object", "additionalProperties": False, "required": ["query"],
                     "properties": {"query": {"type": "string", "description": "consulta curta no idioma do corpus"}}},
}


def _listing(hits: list, start: int = 1) -> str:
    return "\n".join(f"[{i}] {h.doc.title} ({h.doc.url}): {h.doc.text}" for i, h in enumerate(hits, start))


def _faq_write(ctx: Context, llm, system: str, framed: str, hits: list, left: int, retriever,
               k: int, cap: int | None = None) -> tuple[str | None, list, list[str]]:
    """Redação com a tool `search` enquanto houver busca no teto do turno: (texto, passagens, consultas do LLM).

    Busca além do teto volta como erro de tool ("responda com o que tem"); o loop termina em `left + 2` voltas. Trecho
    novo só entra se passa no portão; texto None = o modelo não fechou a resposta (o chamador cai no extrativo).
    `cap` = buscas do turno (plano + `left`) que a mensagem de limite cita; padrão FAQ_MAX_SEARCHES.
    """
    messages: list = llm_history(ctx, framed)
    if left <= 0 or not hasattr(llm, "create"):  # sem teto sobrando (ou provedor sem tool use): só redige
        return llm.complete(system, messages, max_tokens=4096).text, hits, []
    used, asked = 0, []
    for _ in range(left + 2):
        resp = llm.create(system, messages, [SEARCH_TOOL], max_tokens=4096)
        if resp.stop_reason == "max_tokens":
            raise LLMError("resposta truncada em max_tokens", "max_tokens")
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text"), hits, asked
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            query = str((block.input or {}).get("query", "")).strip()[:300] if isinstance(block.input, dict) else ""
            error = True
            if block.name != "search" or not query:
                content = "consulta inválida: passe {\"query\": \"...\"}"
            elif used >= left:
                content = (f"limite de {cap or faq_max_searches()} buscas por turno atingido: responda com as "
                           "passagens que já tem (o que elas não cobrem, diga que falta)")
            else:
                used, error = used + 1, False
                asked.append(query)
                seen = {h.doc.id for h in hits}
                new = [h for h in covered_search(retriever, query, k) if h.doc.id not in seen][:k]
                content = (f"<untrusted_content>\n{_listing(new, len(hits) + 1)}\n</untrusted_content>" if new
                           else "Nenhuma passagem nova com fonte para esta consulta.")
                hits = [*hits, *new]
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": error})
        messages.append({"role": "user", "content": results})
    return None, hits, asked


# --- três estados da resposta do faq ------------------------------------------------------------
# Com só "responde" ou NOT_IN_SOURCES, e a resposta que cobria metade da pergunta ia ao humano inteira.
# Agora: ok (tudo coberto), partial (responde o que tem e diz o que falta; não escala por si), insufficient (nada).
_MISSING_LINE = re.compile(r"^[ \t>*_`-]*MISSING[*_`]*\s*:[*_`]*\s*(.*?)[*_`]*\s*$", re.MULTILINE)
NOT_IN_SOURCES = "NOT_IN_SOURCES"
_SAYS_MISSING = {"pt": "As fontes não trazem: {}.", "en": "The sources don't cover: {}."}


def coverage_of(reply: str) -> tuple[str, str, str | None]:
    """(status, texto para o cliente, o que falta) a partir da resposta do redator (prompts/faq.md).

    `MISSING: x` na última linha → partial (a linha sai do texto). NOT_IN_SOURCES sozinho → insufficient; junto de
    uma resposta com citação [n] (o modelo marcou a falta de um item e respondeu o resto) → partial. Sem marca → ok.
    Prompt de domínio antigo (só NOT_IN_SOURCES) continua valendo: as marcas novas são opcionais.
    """
    found = [m.group(1).strip().rstrip(".") for m in _MISSING_LINE.finditer(reply)]
    missing = next((m for m in reversed(found) if m), None)
    body = _MISSING_LINE.sub("", reply).strip()
    if NOT_IN_SOURCES in body:
        rest = body.replace(NOT_IN_SOURCES, "").strip()
        if not _PASSAGE_REF.search(rest):
            return "insufficient", "", missing
        return "partial", rest, missing
    if found:
        return "partial", body, missing
    return "ok", body, None


def _say_missing(ctx: Context, text: str, missing: str | None) -> str:
    """O cliente lê o que falta: se o texto parcial não disse, a frase vai no fim (template nosso)."""
    from .claims import states_absence

    if not missing or states_absence(text):
        return text
    return f"{text.rstrip()}\n\n{_SAYS_MISSING.get(ctx.language, _SAYS_MISSING['pt']).format(missing)}"


def missing_when_present(answer: str, passages: list[str], facts: list[str], status: str | None = None) -> list[str]:
    """Checagem de eval: a resposta diz que falta e um trecho RECUPERADO traz o fato de referência.

    `facts` = `expect.facts` do caso (regex, sem caixa); `passages` = os trechos que o faq recebeu (`evidence`).
    A resposta "diz que falta" quando o status é partial/insufficient, quando traz NOT_IN_SOURCES ou uma frase de
    ausência (claims.states_absence). Devolve os fatos que estão em alguma passagem e NÃO estão na resposta; [] =
    nada a apontar. Modo de falha medido: o trecho estava lá e a resposta foi "não está nas fontes".
    Regex inválida vale como texto literal.
    """
    from .claims import states_absence

    said = status in ("partial", "insufficient") or NOT_IN_SOURCES in answer or states_absence(answer)
    if not said:
        return []
    out = []
    for fact in facts:
        try:
            rx = re.compile(fact, re.IGNORECASE)
        except re.error:
            rx = re.compile(re.escape(fact), re.IGNORECASE)
        if any(rx.search(p) for p in passages) and not rx.search(answer):
            out.append(fact)
    return out


def _offline_answer(ctx: Context, found: Retrieval) -> str:
    """Extrativo: o trecho de cada item comparado (ou o melhor da pergunta), no idioma da pergunta quando há."""
    from .router import detect_language

    def pick(hits: list):
        return next((h.doc for h in hits if detect_language(h.doc.text) == ctx.language), hits[0].doc)

    label = _t(ctx, "Fonte", "Source")
    if not found.plan.entities:
        top = pick(found.hits)
        return f"{top.text} ({label}: {top.title})"
    parts = [f"{e}: {(d := pick(r)).text} ({label}: {d.title})"
             for e, r in zip(found.plan.entities, found.rankings[:len(found.plan.entities)], strict=True) if r]
    if not parts:  # só a frase inteira achou fonte ("entre x e y" sem nome próprio)
        top = pick(found.hits)
        return f"{top.text} ({label}: {top.title})"
    return "\n".join(parts)


def faq_agent(ctx: Context) -> AgentResult:
    if ctx.intent == "general":
        return _general(ctx)
    retriever = get_retriever()
    k = faq_top_k()
    found = retrieve(ctx.text, ctx.facts.get("standalone"), ctx.facts.get("query_hints", []), retriever, k,
                     queries=ctx.facts.get("search_queries"))
    plan = found.plan
    facts = {"faq_queries": list(plan.queries)}
    if not found.covered:
        return AgentResult("faq", "insufficient", reason="no_source", facts=facts)
    hits = found.hits
    llm = get_llm("agent")
    if llm.enabled:
        try:
            part = ctx.facts.get("ask", {}).get("faq")
            question = (f"Mensagem do cliente: {ctx.text}\nParte que cabe a você: {part}"
                        if part and part != ctx.text else f"Pergunta: {ctx.text}")
            # Plano que gastou o teto (comparação: pergunta do cliente + uma busca por item) ainda deixa 1 busca
            # corretiva ao redator. Medido no ensaio (rodada 10): sem a tool, a comparação de 2 produtos marcou
            # "MISSING: recursos" de um deles nas 3 rodadas, com o trecho dos recursos a uma busca de distância.
            left = max(1, faq_max_searches() - len(plan.queries))
            note = (f"Buscas já feitas no corpus ({LANG_NAMES.get(plan.language, plan.language)}): "
                    f"{' | '.join(plan.queries)}. Se um item da pergunta não está nas passagens, chame `search` "
                    f"(até {left}x), com a consulta em {LANG_NAMES.get(plan.language, plan.language)}, uma por "
                    "item.\n\n")
            # passagens são dado, nunca instrução (injeção indireta): o prompt diz isso e as marca
            framed = (f"<untrusted_content>\n{_listing(hits)}\n</untrusted_content>\n\n{note}{question}"
                      f"{_lang_tail(ctx)}")
            system = domain.prompt("faq.md").format(language=ctx.language)
            text, hits, asked = _faq_write(ctx, llm, system, framed, hits, left, retriever, k,
                                           cap=len(plan.queries) + left)
            facts["faq_queries"] += asked
            sources = [Source(id=h.doc.id, title=h.doc.title, url=h.doc.url) for h in hits]
            evidence = [f"{h.doc.title}: {h.doc.text}" for h in hits]
            if text is not None:
                status, body, missing = coverage_of(text)
                if status == "insufficient":
                    return AgentResult("faq", "insufficient", sources=sources, reason="not_in_sources",
                                       evidence=evidence, facts=facts)
                body = customer_terms(cite_ids(body, hits))
                if status == "partial":
                    facts["missing"] = missing or ""
                    return AgentResult("faq", "partial", text=_say_missing(ctx, body, missing), sources=sources,
                                       evidence=evidence, facts=facts, reason="partial_coverage")
                return AgentResult("faq", "ok", text=body, sources=sources, evidence=evidence, facts=facts)
        except LLMError:
            pass  # cai no extrativo: resposta pior, mas fundamentada
    # Offline: entre os trechos que passaram no portão, prefere o do idioma da pergunta (site com versão en e pt).
    # Medido: a pergunta em inglês tinha language_acc 50% offline porque o 1º trecho era sempre o pt.
    sources = [Source(id=h.doc.id, title=h.doc.title, url=h.doc.url) for h in hits]
    evidence = [f"{h.doc.title}: {h.doc.text}" for h in hits]
    text = _offline_answer(ctx, found)
    # comparação sem trecho de algum item: responde os que têm e diz qual falta (partial), sem inventar o outro
    lacking = [e for e, r in zip(plan.entities, found.rankings[:len(plan.entities)], strict=True) if not r]
    if lacking:
        facts["missing"] = ", ".join(lacking)
        return AgentResult("faq", "partial", sources=sources, evidence=evidence, facts=facts,
                           reason="partial_coverage", text=_say_missing(ctx, text, facts["missing"]))
    return AgentResult("faq", "ok", sources=sources, evidence=evidence, facts=facts, text=text)


# --- records ---------------------------------------------------------------------------------
def _records_llm(ctx: Context, llm) -> AgentResult:
    """Loop manual de tool use: o modelo escolhe as tools; o servidor impõe a identidade."""
    part = ctx.facts.get("ask", {}).get("records")
    messages: list = llm_history(ctx, (f"Mensagem do cliente: {ctx.text}\nParte que cabe a você: {part}"
                                       if part and part != ctx.text else ctx.text) + _lang_tail(ctx))
    calls: list[ToolCall] = []
    evidence: list[str] = []
    pending = None
    nudged = False
    for _ in range(MAX_TOOL_ROUNDS):
        system = domain.prompt("records.md").format(user_id=ctx.user_id, language=ctx.language)
        resp = llm.create(system, messages, tool_specs())
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            if not calls and not pending and not nudged and ctx.ledger and memory.ids_in(ctx.ledger) and tool_specs():
                # Medido ("E qual foi o valor dela?" sobre uma venda já vista): o modelo respondeu do
                # livro de fatos sem consultar nada; sem tool no turno o resultado virava no_data e o caso ia ao
                # humano. Seguimento com registro já visto na conversa: uma volta a mais pede a consulta (o dado do
                # turno anterior pode ter mudado).
                nudged = True
                messages.append({"role": "assistant", "content": resp.content})
                messages.append({"role": "user", "content": _t(
                    ctx, "Você não consultou nenhuma ferramenta neste turno. Consulte agora a que traz o dado pedido "
                         "(o registro de um turno anterior pode ter mudado) e responda com o resultado.",
                    "You did not call any tool in this turn. Call the one that returns the requested data now (a "
                    "record from an earlier turn may have changed) and answer with its result.")})
                continue
            ok = any(c.ok for c in calls) or bool(pending)
            if not ok and _grounded_in_ledger(text, ctx.ledger):
                # Sem tool mesmo assim, mas cada id e número da resposta está no livro de fatos, que só guarda o que
                # veio de resultado de ferramenta: é resposta, com o livro como evidência (nada inventado).
                return AgentResult("records", "ok", text=text, tool_calls=calls,
                                   evidence=[f"[memória da conversa] {ctx.ledger}"], facts={"from_memory": True})
            missing = cited_not_found(ctx.text, calls, evidence)
            if missing and not pending:
                # O id que o CLIENTE citou não existe na conta: "não encontrei" não resolve o pedido (medido: venda
                # inexistente terminava sem humano porque outra consulta da mesma volta deu ok). Com o motivo
                # `not_found` o supervisor leva ao humano quando ninguém mais respondeu (supervisor.NOT_RESOLVED).
                return AgentResult("records", "insufficient", text=text, tool_calls=calls, reason="not_found",
                                   evidence=evidence, facts={"not_found": missing})
            return AgentResult("records", "ok" if ok else "insufficient", text=text, tool_calls=calls,
                               pending_action=pending, reason=None if ok else "no_data", evidence=evidence)
        messages.append({"role": "assistant", "content": resp.content})  # conteúdo inteiro, sem editar
        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            result, call = run_tool(block.name, dict(block.input), ctx.user_id, ctx.conversation_id)
            result = memory.with_aggregates(result)  # soma/contagem em código: o redator não faz conta
            calls.append(call)
            evidence.append(json.dumps(result, ensure_ascii=False))
            pending = result.get("action_id") or pending
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": json.dumps(result, ensure_ascii=False), "is_error": not call.ok})
        messages.append({"role": "user", "content": results})  # todos os resultados numa mensagem só
    return AgentResult("records", "error", tool_calls=calls, reason="tool_loop_limit", pending_action=pending,
                       evidence=evidence)


_ID_TOKEN = re.compile(r"\b[A-Z]{1,4}\d{3,}[A-Z]?\b")


def cited_not_found(text: str, calls: list, evidence: list[str]) -> list[str]:
    """Ids que o cliente escreveu nesta mensagem, foram consultados (estão nos args de uma tool) e voltaram
    `not_found` em TODA consulta que os levou. Id que alguma consulta achou não entra."""
    cited = set(_ID_TOKEN.findall(text or ""))
    if not cited:
        return []
    seen: dict[str, bool] = {}
    for call, raw in zip(calls, evidence, strict=False):
        args = " ".join(str(v) for v in (call.args or {}).values())
        try:
            result = json.loads(raw)
        except (TypeError, ValueError):
            result = {}
        missing = isinstance(result, dict) and result.get("ok") is False and result.get("error") == "not_found"
        for i in cited & set(_ID_TOKEN.findall(args)):
            seen[i] = seen.get(i, False) or not missing
    return sorted(i for i, found in seen.items() if not found)


def _grounded_in_ledger(text: str, ledger: str | None) -> bool:
    """A resposta cita um id do livro de fatos e todo número dela está no livro (que só guarda falas do cliente e
    resultados de ferramenta: memory.extract_user / extract_evidence)."""
    if not text or not ledger:
        return False
    cited = memory.ids_in(text)
    return bool(cited) and all(i.upper() in ledger.upper() for i in cited) \
        and not grounding.unsupported_numbers(text, [ledger])


def records_agent(ctx: Context) -> AgentResult:
    llm = get_llm("agent")
    if llm.enabled:
        try:
            return _records_llm(ctx, llm)
        except LLMError:
            pass  # provedor caiu: mesmo atendimento pelo caminho determinístico
    import sys

    return domain.active().records_offline(ctx, sys.modules[__name__])  # caminho determinístico é do domínio


# --- escalation ------------------------------------------------------------------------------
# Escalada só com motivo real. Medido: 40 de 49 falhas de handoff eram escalada sem precisar. Humano para decisão
# do caso, risco ou pedido do cliente; diagnóstico pronto sem manual não escala. O enunciado pede humano "quando o
# sistema não consegue resolver com confiança": pergunta SEM
# NENHUMA fonte e nada respondido no turno segue indo ao humano (split replan). Viram OFERTA do atendente, sem caso:
# - falta só parte da cobertura (`*_partial_coverage`);
# - a falta é de UM especialista e outro já respondeu no mesmo turno (records trouxe o diagnóstico, faq sem manual).
# Medido: com `*_no_data` também virando oferta, o split replan caiu de 85% para 30% de handoff certo
# (venda TX8888 que não existe, produto que a Getnet não tem): não resolver = humano, como o enunciado pede.
OFFER_SUFFIXES = ("_partial_coverage",)
GAP_SUFFIXES = ("_not_in_sources", "_insufficient", *OFFER_SUFFIXES)  # erro de tool, orçamento etc.: escala


def escalation_gate() -> bool:
    """ESCALATION_GATE=off desliga a regra (ablação: mede quantos casos ela tira do humano)."""
    return os.getenv("ESCALATION_GATE", "on").lower() != "off"


def escalation_offer_only(ctx: Context) -> bool:
    """True = oferece o humano em vez de abrir caso (regra acima). Abre caso sempre que o cliente pediu (intenção em
    `HUMAN_INTENTS` do domínio, padrão {"human_request"}), o domínio exige (`must_escalate(ctx)` opcional: veredito de
    caso individual, fraude)."""
    reason = ctx.handoff_reason or ""
    if not escalation_gate() or not reason.endswith(GAP_SUFFIXES):
        return False
    d = domain.active()
    if ctx.intent in getattr(d, "HUMAN_INTENTS", {"human_request"}):
        return False
    hook = getattr(d, "must_escalate", None)
    if callable(hook) and hook(ctx):
        return False
    failed = reason.split("_", 1)[0]
    answered = [a for a in ctx.facts.get("answered_by", []) if a not in (failed, "escalation")]
    return reason.endswith(OFFER_SUFFIXES) or bool(answered)


def escalation_agent(ctx: Context) -> AgentResult:
    reason = ctx.handoff_reason or "user_request"
    if escalation_offer_only(ctx):
        METRICS.inc("escalation_offered_total", reason=reason)
        text = _t(ctx, "Se quiser, posso encaminhar sua dúvida a um atendente humano; é só pedir.",
                  "If you'd like, I can hand this to a human agent; just ask.")
        return AgentResult("escalation", "ok", text=text, evidence=[text], facts={"escalation_offered": reason})
    summary = f"[{ctx.intent}] {ctx.text[:300]}"
    if ctx.facts.get("escalation_note"):
        summary += f" | supervisor: {ctx.facts['escalation_note']}"
    if ctx.user_summary:  # o operador vê o contexto de conversas anteriores, não só a frase solta
        summary += f" | memória: {ctx.user_summary[:300]}"
    store = get_store()
    is_new = store.ticket_for(ctx.conversation_id, "open") is None
    from .routing import specialty_for  # import tardio: routing lê AGENTS deste módulo

    ticket = store.open_ticket(ctx.conversation_id, ctx.user_id, reason, summary,
                               specialty=specialty_for(ctx.intent, reason))
    if is_new:
        notify_new_ticket(ticket)  # opcional (Telegram); a fila persistida é a fonte da verdade
    text = _t(ctx, f"Encaminhei para um atendente humano (protocolo {ticket['id']}). "
                   "A resposta aparece nesta conversa.",
              f"I've handed this to a human agent (ticket {ticket['id']}). "
              "The reply will show up in this conversation.")
    return AgentResult("escalation", "ok", handoff=Handoff(required=True, reason=reason, ticket_id=ticket["id"]),
                       text=text, evidence=[text])  # template nosso: base dos números citados


AGENTS = {"faq": faq_agent, "records": records_agent, "escalation": escalation_agent}


def __getattr__(attr: str):
    # compatibilidade: `agents.MIN_SCORE` e `agents.ELIGIBLE_STATUS` refletem o domínio ativo
    if attr in ("MIN_SCORE", "ELIGIBLE_STATUS"):
        return getattr(domain.active(), attr)
    raise AttributeError(attr)
