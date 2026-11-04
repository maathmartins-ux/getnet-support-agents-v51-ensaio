"""Supervisor: executa o plano do router, observa o status de cada agente e replaneja.

Mapa do laço de um turno (`run` → `_run`):

1. `run`: caso aberto na conversa → modo espera (`_hold`: a mensagem entra no caso, leituras seguem, nenhuma escrita
   fica proposta). `prior` traz o que já existe antes do plano (na retomada, o resultado "human" do operador).
2. `_run` escolhe o caminho:
   - **atalho de 1 passo** (`fast_path`, DESLIGADO por padrão; `SUPERVISOR_FAST=on` liga): plano de um
     especialista, router confiante, sem resposta de operador; o passo roda direto e, se respondeu (ok/partial),
     a resposta é a dele (`_offer_human_on_gap` acrescenta a oferta do humano quando a fonte não cobre tudo).
     Se o especialista não resolve (insufficient), o resultado vai ao supervisor LLM (`run_llm`), que decide;
   - **supervisor LLM** (`run_llm`, papel "supervisor"): loop manual de tool use em que os especialistas são tools
     (faq_agent, records_agent, escalation_agent). O modelo lê cada status e decide o próximo passo; várias tool
     calls na mesma resposta rodam em paralelo;
   - **table** (offline/CI e fallback de qualquer LLMError): o mesmo laço com transições determinísticas do domínio
     (PLANS, FALLBACK, ALLOWED, DEPENDS) e MAX_STEPS. Passos independentes do plano rodam em paralelo.
3. `_enforce_escalation`: "o LLM propõe, o código dispõe". Turno em que um especialista não achou fonte, dado ou
   registro (NOT_RESOLVED) e ninguém respondeu nada termina no escalation, mesmo que o LLM só tenha oferecido.
4. `_continue_with_operator` (app/hitl_sync.py): caso aberto NESTE turno e espera ligada (`HITL_SYNC_WAIT_S` > 0, ou
   `hitl_sync.override` no contexto) → o turno espera o operador (teto 20 s); a resposta no prazo vira evidência e os
   passos pendentes rodam no mesmo turno; a resposta final não oferece nem nega o atendente (`without_handoff_talk`).
5. `_save_pending`: o que faltou fica no caso e roda quando o operador responder (app/resume.py).

Status de agente: ok | partial (respondeu o que a fonte cobre e diz o que falta: é RESPOSTA, nunca escala por si) |
insufficient | error.

Replanejamento em dois gatilhos (nos dois motores):
- FALHA: status insufficient/error → FALLBACK do domínio (ex.: escalation); no atalho com LLM ligado, o supervisor
  LLM decide (passo 2); offline vale a tabela;
- ACHADO: o agente devolve `needs` (ex.: records viu "pedido ainda não saiu" → precisa da política de prazo do
  faq). No motor llm o achado é INFORMAÇÃO, não passo imposto: chega ao modelo no tool_result e o modelo decide se
  chama o agente pedido. Se encerrar sem chamá-lo, UMA volta de lembrete diz qual achado ficou sem resposta; ignorado
  de novo, o passo que trouxe o achado sai com `outcome: ignored` na árvore de passos (`need_ignored` no log e em
  /metrics) e o turno segue. No motor de tabela (offline, queda do LLM e o atalho de 1 passo, que rodam sem
  consultar o modelo) o código insere o passo pedido se a transição estiver em ALLOWED e houver orçamento.
  Medido no ensaio (rodada 10): 75 de 396 passos ao vivo (19%) eram inseridos pelo código, 51 deles o faq que já
  estava no plano do router; no braço sem inserção o modelo chamou o faq sozinho em todos os casos com achado.
  Replanejamento é desvio do plano do router: o agente pedido que já estava no plano roda sem entrar em `replans`; o
  que não estava entra como "<de>:need-><para>", decidido pelo modelo (llm) ou pela tabela (code).
Ablação (SUPERVISOR_REPLAN): on (padrão) · no_needs (o achado não chega ao modelo, não há lembrete e a tabela não
insere: mede o ganho do achado como informação) · off (plano fixo).

Orçamento por turno (condição de parada): MAX_STEPS (chamadas de agente), MAX_MODEL_CALLS, MAX_TURN_USD (o turno
inteiro, router incluso) e NODE_TIMEOUT_S (cada agente). Estourou → entrega a parte já respondida, não roda o resto
e abre caso humano com motivo `budget_exhausted`; os passos que faltaram ficam no caso (passo 5).

Paralelismo: threads (os agentes fazem I/O — SQLite, HTTP do LLM). Cada thread recebe uma cópia do
contextvars (trace_id, custo do request, span OTel pai). O resultado entra SEMPRE na ordem do plano
(ou dos blocos tool_use), nunca na ordem de término: rota, resposta e eval ficam determinísticos.
Todo desvio do plano vai para `replans`.

Quem decidiu cada passo (`decided_by` na árvore de passos, `step_view`):
- "llm": o passo veio de uma tool call do supervisor LLM (o motivo é a própria tool call; sem `why`);
- "router": o agente veio do PLANO do router (um LLM ao vivo; as regras de palavra-chave sem LLM) e o supervisor
  LLM não foi consultado sobre ele; `why` diz por onde rodou (ROUTER_WHY: "fast_path" = o atalho de 1 passo,
  "plan" = o motor de tabela);
- "code": uma regra do código pôs o passo no turno, com a regra em `why` (CODE_WHY: achado no motor de tabela,
  escalada garantida, FALLBACK ou router incerto, orçamento, passo antecipado, aviso de caso aberto);
- "operator": a resposta do humano (passo "human"), que chega pronta como evidência (sem `why`).
A marca é gravada onde o passo é registrado (`_record`, com o motivo de cada chamada), não deduzida depois dos
replanos nem do motor do turno, que mistura passos de origens diferentes; passo sem marca sai sem os campos ("não
registrado"). Assim o leitor do trace separa o que cada modelo escolheu do que o código impôs.
"""
from __future__ import annotations

import contextvars
import copy
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field, replace

from . import capabilities, cases, claims, domain
from .agents import AGENTS, AgentResult, Context
from .config import supervisor_fast, supervisor_fast_min_confidence, supervisor_parallel, supervisor_replan
from .llm import LLMError, get_llm
from .observability import METRICS, log, request_model_calls, request_usage, span
from .schemas import Handoff

# PLANS, FALLBACK, ALLOWED, DEPENDS e NO_ESCALATION são do DOMÍNIO (app/domain/<ativo>.py), lidos em tempo de
# chamada: o desafio nunca edita este arquivo. `supervisor.PLANS` continua funcionando (ver __getattr__).
_DOMAIN_NAMES = ("PLANS", "FALLBACK", "ALLOWED", "DEPENDS", "NO_ESCALATION")


def __getattr__(attr: str):
    if attr in _DOMAIN_NAMES:
        return getattr(domain.active(), attr)
    raise AttributeError(attr)


def _d():
    return domain.active()


def no_escalation(ctx: Context) -> bool:
    """Este turno não pode abrir caso humano: intenção do domínio sem escalonamento, ou é a retomada de um caso que
    o humano acabou de responder (reabrir criaria um laço humano → retomada → humano)."""
    return ctx.intent in _d().NO_ESCALATION or bool(ctx.facts.get("resume_of"))


# Status que é resposta: segue o plano sem FALLBACK. "partial" = cobriu parte e disse o que falta (contrato do faq).
ANSWERED = {"ok", "partial"}
SEQUENTIAL = {"escalation"}  # sempre sozinho e depois dos outros: lê o motivo de quem falhou
MAX_STEPS = 4  # teto de chamadas de agente por turno (plano de 2 + replan + escalonamento)
LOW_CONFIDENCE = 0.4
# Orçamento por turno (env). Turno típico ao vivo: ~6–10 chamadas e US$ 0,01 (medido); o teto pega o laço que
# desanda, não o turno normal. 0 desliga o teto correspondente.
MAX_MODEL_CALLS = 20
MAX_TURN_USD = 0.25
NODE_TIMEOUT_S = 60.0  # agente com LLM e 3 rodadas de tool leva ~10–25 s ao vivo
BUDGET_REASON = "budget_exhausted"
REPLAN_MODES = ("on", "no_needs", "off")
# Quem decidiu o passo (`decided_by`) e por quê (`why`), o vocabulário fechado que `_decide` grava:
#   DECIDED_LLM       tool call do supervisor LLM;
#   DECIDED_OPERATOR  a resposta do humano (passo "human"), na retomada (`prior`) ou na espera síncrona;
#   DECIDED_ROUTER    agente do plano do router rodado sem consultar o supervisor LLM, com o caminho em ROUTER_WHY:
#     fast_path   o passo único do atalho (`fast_path`);
#     plan        passo do plano rodado pelo motor de tabela (offline e queda do supervisor LLM); na retomada sem
#                 LLM o plano são os passos que o caso guardou para depois do humano (cases.save_pending);
#   DECIDED_CODE      regra do código, com a regra em CODE_WHY:
#     needs       achado de um especialista aceito por accept_need no motor de tabela (no motor LLM quem chama o
#                 agente pedido é o modelo: o passo sai DECIDED_LLM);
#     escalation  escalada garantida por _enforce_escalation (faltou fonte, dado ou registro e ninguém respondeu);
#     table       FALLBACK do domínio para um passo que falhou, ou router incerto (LOW_CONFIDENCE) → escalation;
#     budget      orçamento do turno esgotado (_exhaust, inclui NODE_TIMEOUT_S): o caso vai ao humano;
#     lead        1º passo do plano rodado antes da 1ª volta do supervisor LLM (lead_step, SUPERVISOR_LEAD=on): o
#                 agente é do plano, mas rodá-lo antes de consultar o modelo é a regra DEPENDS do código;
#     hold        aviso de caso aberto na conversa (_hold): não é escolha de agente, e a conta de quem decide
#                 (evals/trace_stats.py) o deixa de fora.
DECIDED_LLM = "llm"
DECIDED_ROUTER = "router"
DECIDED_CODE = "code"
DECIDED_OPERATOR = "operator"
ROUTER_WHY = ("fast_path", "plan")
CODE_WHY = ("needs", "escalation", "table", "budget", "lead", "hold")
# O que aconteceu com cada achado (`needs` na árvore de passos, no passo que o trouxe; `step_view`):
#   inserted  motor de tabela: o código pôs o passo pedido no turno (o passo sai decided_by code, why needs);
#   called    motor LLM: o modelo chamou o agente pedido depois do achado, sem lembrete;
#   reminded  motor LLM: o modelo chamou o agente pedido depois da volta de lembrete;
#   ignored   motor LLM: o modelo encerrou sem chamar o agente pedido depois da volta de lembrete (`need_ignored`);
#   planned   motor de tabela: o agente pedido já estava na fila do turno (o plano do router): roda sem passo novo;
#   ran       o agente pedido já tinha rodado no turno (antes ou no mesmo lote);
#   hidden    ablação no_needs: o achado não chegou ao modelo nem à tabela;
#   blocked   regra do turno: transição fora de ALLOWED, MAX_STEPS, orçamento, NO_ESCALATION ou plano fixo (off).
NEED_OUTCOMES = ("inserted", "called", "reminded", "ignored", "planned", "ran", "hidden", "blocked")
NEED_WHY_CHARS, NEED_HINT_CHARS = 200, 300  # teto de cada parte do achado (dois achados juntos somam as partes)
MAX_ROUNDS = MAX_STEPS + 2  # voltas do supervisor LLM por turno (a de lembrete inclusa)
TOOLS = [
    {"name": "faq_agent", "strict": True,
     "description": "Responde dúvidas sobre produto e políticas com RAG e fonte citada. "
                    "Devolve {status, text, sources}.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["query"],
                      "properties": {"query": {"type": "string", "description": "Pergunta + fatos já obtidos"}}}},
    {"name": "records_agent", "strict": True,
     "description": "Lê registros do PRÓPRIO usuário autenticado e propõe ações que exigem confirmação. "
                    "Pode devolver `needs` (achado que pede outro especialista).",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["request"],
                      "properties": {"request": {"type": "string"}}}},
    {"name": "escalation_agent", "strict": True,
     "description": "Abre caso para atendente humano. Use em pedido explícito, sem fonte, falha repetida ou risco.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["reason"],
                      "properties": {"reason": {"type": "string"}}}},
]
_TOOL_TO_AGENT = {"faq_agent": "faq", "records_agent": "records", "escalation_agent": "escalation"}
HOLD_TEXT = {
    "pt": "Seu caso {ticket} está com um atendente; anexei esta mensagem a ele. Ações na conta ficam suspensas "
          "até a resposta do atendente.",
    "en": "Your case {ticket} is with a human agent; I've attached this message to it. Account actions are on "
          "hold until the agent replies.",
}


# --- configuração (env lido a cada chamada: testes e eval trocam sem reimportar) ------------------------------
def replan_mode() -> str:
    """SUPERVISOR_REPLAN: "on" (padrão: falha e achado replanejam) · "no_needs" (ablação do achado: o `needs` não vai
    ao modelo, sem lembrete, a tabela não insere; a falha segue) · "off" (plano fixo do router)."""
    mode = os.getenv("SUPERVISOR_REPLAN", "on").lower()
    return mode if mode in REPLAN_MODES else "on"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def max_model_calls() -> int:
    return int(_env_float("MAX_MODEL_CALLS", MAX_MODEL_CALLS))


def max_turn_usd() -> float:
    return _env_float("MAX_TURN_USD", MAX_TURN_USD)


def node_timeout_s() -> float:
    return _env_float("NODE_TIMEOUT_S", NODE_TIMEOUT_S)


def budget_exceeded() -> str | None:
    """Qual teto do turno já foi atingido ("model_calls" | "usd"); None = ainda há orçamento."""
    calls, usd = max_model_calls(), max_turn_usd()
    if calls > 0 and request_model_calls() >= calls:
        return "model_calls"
    if usd > 0 and request_usage()["cost_usd"] >= usd:
        return "usd"
    return None


@dataclass
class Outcome:
    results: list[AgentResult] = field(default_factory=list)
    route: list[str] = field(default_factory=list)
    replans: list[str] = field(default_factory=list)
    answer: str | None = None  # resposta final redigida pelo supervisor LLM (None = juntar textos dos agentes)
    engine: str = "table"
    budget: str | None = None  # teto que parou o turno (model_calls | usd | node_timeout)
    deferred: list[str] = field(default_factory=list)  # passos do plano que ficaram para depois do humano
    handover: str | None = None  # atalho: agente cujo insufficient a tabela passou ao supervisor LLM
    # fila do motor determinístico: o motivo (ROUTER_WHY ou CODE_WHY) que pôs cada agente nela (plano do router,
    # achado, FALLBACK). A fila guarda só nomes (next_batch); o motivo vai ao passo quando ele roda (_table_loop →
    # _record) e é consumido ali: agente sem motivo na fila sai sem marca, nunca com um motivo presumido.
    queued_by: dict[str, str] = field(default_factory=dict)


# --- execução de um agente --------------------------------------------------------------------------------
def _tool_needs(result: AgentResult) -> list:
    """`needs` que as tools devolveram no próprio resultado (evidência JSON do passo), crus."""
    found: list = []
    for item in result.evidence:
        if item.startswith("{"):
            try:
                data = json.loads(item)
            except ValueError:
                continue
            if isinstance(data, dict) and isinstance(data.get("needs"), list):
                found += data["needs"]
    return found


def collect_needs(result: AgentResult, ctx: Context) -> list[dict]:
    """Achados do passo: `AgentResult.needs` do próprio agente + `domain.needs_for(result, ctx)` (opcional) OU, sem
    ele, o `needs` que as tools devolveram no resultado (evidência JSON).

    O caminho com LLM do records não monta AgentResult.needs: o achado sai do resultado das tools. Quando o domínio
    define `needs_for`, ele é o filtro (ex.: só com sintoma na pergunta) e o `needs` cru das tools não entra por fora
    dele. Medido no ensaio (rodada 10): lido cru, 32 das 75 inserções por achado foram em mensagens sem nenhuma
    palavra de sintoma ("Show me my last 5 transactions"; pergunta de taxa que levou a dica de recusa).
    Um achado por agente pedido; dois achados para o mesmo agente JUNTAM why e hint (partes iguais uma vez só). Antes
    o 2º era descartado: no official-08 a dica de recusa caiu e o faq trouxe o manual do chip.
    """
    found = list(result.needs or [])
    hook = getattr(_d(), "needs_for", None)
    found += (hook(result, ctx) or []) if hook is not None else _tool_needs(result)
    merged: dict[str, dict[str, list[str]]] = {}
    for need in found:
        if not isinstance(need, dict) or not need.get("agent"):
            continue
        parts = merged.setdefault(str(need["agent"]), {"why": [], "hint": []})
        for key, limit in (("why", NEED_WHY_CHARS), ("hint", NEED_HINT_CHARS)):
            piece = str(need.get(key) or "").strip()[:limit]
            if piece and piece not in parts[key]:
                parts[key].append(piece)
    return [{"agent": agent, "why": "; ".join(p["why"]), "hint": "; ".join(p["hint"])} for agent, p in merged.items()]


def _mark_need(result: AgentResult, agent: str, outcome: str) -> None:
    """Grava no passo o que aconteceu com o achado que pede `agent` (NEED_OUTCOMES). Como `decided`, é atributo
    próprio do AgentResult, fora de `facts` e de `for_supervisor`: só `step_view` lê."""
    if outcome in NEED_OUTCOMES:
        marks = getattr(result, "need_outcomes", None)
        if marks is None:
            marks = result.need_outcomes = {}
        marks[agent] = outcome


def _invoke(name: str, ctx: Context) -> AgentResult:
    t0 = time.perf_counter()
    with span("agent", agent=name) as fields:
        try:
            result = AGENTS[name](ctx)
        except Exception as exc:  # agente quebrado vira status "error": o supervisor replaneja
            result = AgentResult(name, "error", reason=f"exception:{type(exc).__name__}")
        try:
            result.needs = collect_needs(result, ctx)
        except Exception as exc:  # noqa: BLE001 — regra de domínio quebrada não derruba o turno
            log.warning("needs_failed", extra={"extra_fields": {"agent": name, "error": type(exc).__name__}})
            result.needs = []
        fields.update(status=result.status, reason=result.reason)  # quem desistiu e por quê, no log
        result.ms = round((time.perf_counter() - t0) * 1000, 1)
        return result


PREVIEW_CHARS = 200


def _decide(result: AgentResult, by: str | None) -> AgentResult:
    """Grava no passo quem o decidiu. `by`: DECIDED_LLM ou DECIDED_OPERATOR (sem `why`), um caminho de ROUTER_WHY
    (decided_by "router") ou uma regra de CODE_WHY (decided_by "code"). None, ou valor fora do vocabulário, não
    marca nada: o passo sai "não registrado", nunca com uma decisão presumida.

    A decisão é do supervisor, não do especialista: vai num atributo próprio do AgentResult (`decided`), fora de
    `facts` (que acumulam no contexto dos agentes) e de `for_supervisor` (o que o modelo lê). Marcar não muda
    contexto, rota nem resposta; só `step_view` lê a marca.
    """
    if by in (DECIDED_LLM, DECIDED_OPERATOR):
        result.decided = {"decided_by": by}
    elif by in ROUTER_WHY:
        result.decided = {"decided_by": DECIDED_ROUTER, "why": by}
    elif by in CODE_WHY:
        result.decided = {"decided_by": DECIDED_CODE, "why": by}
    return result


def step_view(result: AgentResult, mask=lambda text: text) -> dict:
    """Um passo da árvore de passos (o trace legível por caso): agente → status/motivo → ms →
    ferramentas com args, ok e prévia do resultado (mascarada por `mask`) → antes/depois de escrita executada →
    quem decidiu o passo (`decided_by`, e `why` quando foi o plano do router ou o código). Passo sem marca sai sem os
    dois campos: quem lê conta "não registrado", nunca uma decisão presumida.
    Passo que trouxe achado sai com `needs`: o agente pedido, o motivo (curto, mascarado) e `outcome` (NEED_OUTCOMES;
    sem marca, sem o campo). É daqui que se conta onde o achado disparou e quantas vezes o modelo o ignorou."""
    evidence = result.evidence if len(result.evidence) == len(result.tool_calls) else []
    tools = []
    for i, call in enumerate(result.tool_calls):
        tool = {"name": call.name, "args": call.args, "ok": call.ok}
        if evidence:
            tool["preview"] = mask(" ".join(str(evidence[i]).split()))[:PREVIEW_CHARS]
        tools.append(tool)
    view = {"agent": result.agent, "status": result.status, "reason": result.reason, "ms": result.ms,
            "tools": tools, **(getattr(result, "decided", None) or {})}
    if result.needs:
        marks = getattr(result, "need_outcomes", None) or {}
        view["needs"] = [{"agent": n["agent"], "why": mask(str(n.get("why") or ""))[:PREVIEW_CHARS],
                          **({"outcome": marks[n["agent"]]} if n["agent"] in marks else {})} for n in result.needs]
    for key in ("operator", "answered_live", "from_memory"):
        if result.facts.get(key):
            view[key] = result.facts[key]
    if result.pending_action:
        view["pending_action"] = result.pending_action
    if result.handoff and result.handoff.ticket_id:
        view["ticket_id"] = result.handoff.ticket_id
    return view


def _invoke_timed(name: str, ctx: Context) -> AgentResult:
    """Agente com teto de tempo (NODE_TIMEOUT_S). Estourou → status error, reason node_timeout.

    A thread do agente não é morta (Python não cancela thread): o resultado tardio é descartado. Agente não
    escreve no ctx e escrita de tool só propõe; o pior efeito do atraso é custo, que o teto de US$ limita.
    """
    limit = node_timeout_s()
    if limit <= 0:
        return _invoke(name, ctx)
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(contextvars.copy_context().run, _invoke, name, ctx)
    try:
        return future.result(timeout=limit)
    except FutureTimeout:
        METRICS.inc("node_timeouts_total", agent=name)
        return AgentResult(name, "error", reason="node_timeout")
    finally:
        pool.shutdown(wait=False)


def run_batch(names: list[str], ctx: Context) -> list[AgentResult]:
    """Executa os agentes; em paralelo quando há mais de um. Devolve na ordem de `names`."""
    if len(names) == 1 or not supervisor_parallel():
        return [_invoke_timed(n, ctx) for n in names]
    METRICS.inc("parallel_batches_total", size=str(len(names)))
    with span("parallel", agents=",".join(names)), ThreadPoolExecutor(max_workers=len(names)) as pool:
        futures = [pool.submit(contextvars.copy_context().run, _invoke_timed, n, ctx) for n in names]
        return [f.result() for f in futures]


def _record(name: str, result: AgentResult, ctx: Context, out: Outcome, by: str | None = None) -> None:
    """Registra o passo no turno. `by`: quem o decidiu (ver `_decide`), vindo de quem chama: cada caminho do laço
    sabe por que o passo entrou."""
    _decide(result, by)
    out.route.append(name)
    out.results.append(result)
    if result.status in ANSWERED and result.text and name != "escalation":  # quem já respondeu algo no turno
        ctx.facts.setdefault("answered_by", []).append(name)
    for key, value in result.facts.items():  # fatos acumulam entre agentes, na ordem do plano
        if isinstance(value, dict) and isinstance(ctx.facts.get(key), dict):
            ctx.facts[key].update(value)
        elif isinstance(value, list) and isinstance(ctx.facts.get(key), list):
            ctx.facts[key].extend(value)
        else:
            ctx.facts[key] = value


def next_batch(queue: list[str], budget: int) -> list[str]:
    """Primeiro da fila + os seguintes que não dependem de ninguém do lote. Remove-os da fila."""
    batch = [queue.pop(0)]
    while queue and len(batch) < budget and batch[0] not in SEQUENTIAL and queue[0] not in SEQUENTIAL \
            and not (_d().DEPENDS.get(queue[0], set()) & set(batch)):
        batch.append(queue.pop(0))
    return batch


def next_step(result: AgentResult, done: list[str], intent: str | None = None) -> str | None:
    if not supervisor_replan():  # ablação: plano fixo, falha não desvia
        return None
    d = _d()
    nxt = d.FALLBACK.get(result.agent, "escalation")
    if nxt == "escalation" and intent in d.NO_ESCALATION:
        return None
    return None if nxt in done or nxt not in d.ALLOWED.get(result.agent, set()) else nxt


def accept_need(frm: str, need: dict, ctx: Context, out: Outcome, scheduled: list[str]) -> str | None:
    """Motor de tabela (offline, queda do LLM e o atalho de 1 passo): o passo pedido por um achado entra no plano?
    Regras do código; no motor LLM quem decide é o modelo (`_note_needs`).

    Entra se: modo "on"; agente existe e a transição frm→agente está em ALLOWED; ainda não rodou nem está na fila;
    cabe em MAX_STEPS; há orçamento; escalation respeita NO_ESCALATION. A dica vira sub-pergunta do agente.
    """
    agent = need["agent"]
    d = _d()
    if replan_mode() != "on" or agent not in AGENTS or agent not in d.ALLOWED.get(frm, set()) \
            or agent in out.route or agent in scheduled or len(out.route) + len(scheduled) >= MAX_STEPS \
            or (agent == "escalation" and no_escalation(ctx)) or budget_exceeded():
        return None
    _hint_to(agent, need, ctx)
    ctx.facts.setdefault("needs", []).append({"from": frm, **need})
    _need_replan(frm, agent, need.get("why"), out, out.engine)
    return agent


def _hint_to(agent: str, need: dict, ctx: Context, replace_ask: bool = True) -> None:
    """A dica do achado vira a sub-pergunta do agente pedido (e consulta a mais do faq). `replace_ask=False`: o
    agente já estava na fila e mantém a sub-pergunta que tinha."""
    ask = need.get("hint") or need.get("why")
    if not ask:
        return
    asks = ctx.facts.setdefault("ask", {})
    if replace_ask or agent not in asks:
        asks[agent] = ask
    if agent in ("faq", "knowledge"):
        ctx.facts.setdefault("query_hints", []).append(ask)


def _need_replan(frm: str, agent: str, why: str | None, out: Outcome, engine: str) -> None:
    """O achado de `frm` desviou o plano do router para `agent` ("<de>:need-><para>", nos dois motores)."""
    out.replans.append(f"{frm}:need->{agent}" + (f" ({why[:80]})" if why else ""))
    METRICS.inc("replans_total", agent=frm, reason="need", engine=engine)


def _unaccepted(agent: str, out: Outcome, queue: list[str]) -> str:
    """Por que a tabela não inseriu o passo pedido (NEED_OUTCOMES): ablação, já na fila, já rodou ou regra do turno."""
    if replan_mode() == "no_needs":
        return "hidden"
    if agent in queue:
        return "planned"
    return "ran" if agent in out.route else "blocked"


def _exhaust(what: str, pending: list[str], ctx: Context, out: Outcome) -> None:
    """Orçamento estourou: guarda o que faltou e leva o caso ao humano (escalation não chama modelo)."""
    out.budget = what
    out.deferred = list(dict.fromkeys(p for p in pending if p != "escalation" and p in AGENTS))
    out.replans.append(f"budget:{what}->escalation")
    METRICS.inc("budget_exhausted_total", kind=what)
    log.warning("budget_exhausted", extra={"extra_fields": {"kind": what, "deferred": out.deferred,
                                                            "calls": request_model_calls()}})
    if "escalation" in out.route or no_escalation(ctx):
        return
    ctx.handoff_reason = BUDGET_REASON
    ctx.facts["escalation_note"] = f"orçamento do turno esgotado ({what}); pendente: {out.deferred or '[]'}"
    _record("escalation", _invoke("escalation", ctx), ctx, out, "budget")


# --- motor determinístico ----------------------------------------------------------------------------------
def run_table(plan: list[str], ctx: Context, confidence: float = 1.0, handover: bool = False) -> Outcome:
    """Motor determinístico. `handover=True` (atalho com LLM ligado): o insufficient que iria ao FALLBACK para o laço
    e fica em `out.handover` para o supervisor LLM decidir (ver `_run`)."""
    out = Outcome()
    queue = list(plan)
    # os agentes do plano são escolha do router; a tabela só os executa, sem consultar o supervisor LLM: no atalho
    # (handover) o passo único, fora dele o plano inteiro
    out.queued_by.update(dict.fromkeys(queue, "fast_path" if handover else "plan"))
    if confidence < LOW_CONFIDENCE and queue and "escalation" not in queue \
            and not no_escalation(ctx) and supervisor_replan():
        queue.append("escalation")
        out.queued_by["escalation"] = "table"
        ctx.handoff_reason = "low_confidence"
        out.replans.append(f"router:low_confidence({confidence:.2f})->escalation")
    return _table_loop(queue, ctx, out, handover)


def _table_loop(queue: list[str], ctx: Context, out: Outcome, handover: bool = False) -> Outcome:
    while queue and len(out.route) < MAX_STEPS:
        if (what := budget_exceeded()) is not None:
            _exhaust(what, queue, ctx, out)
            return out
        batch = next_batch(queue, MAX_STEPS - len(out.route))
        results = run_batch(batch, ctx)
        for name, result in zip(batch, results, strict=True):
            _record(name, result, ctx, out, out.queued_by.pop(name, None))  # sem motivo na fila: sem marca
        timed_out = [n for n, r in zip(batch, results, strict=True) if r.reason == "node_timeout"]
        if timed_out:
            _exhaust("node_timeout", timed_out + queue, ctx, out)
            return out
        for name, result in zip(batch, results, strict=True):
            accepted = []
            for need in result.needs:
                agent = accept_need(name, need, ctx, out, queue)
                outcome = "inserted" if agent else _unaccepted(need["agent"], out, queue)
                if outcome == "planned" and replan_mode() == "on":
                    # o passo já estava na fila (plano do router): não há passo novo nem replanejamento, mas a
                    # informação do achado chega a ele. Medido no exemplo: sem a dica, o faq planejado depois do
                    # records não achou fonte para "Quando chega meu pedido 1002?" e o turno escalou.
                    _hint_to(need["agent"], need, ctx, replace_ask=False)
                _mark_need(result, need["agent"], outcome)
                accepted += [agent] if agent else []
            for agent in reversed(accepted):  # o passo pedido roda logo a seguir
                queue.insert(0, agent)
                out.queued_by[agent] = "needs"
            if result.status in ANSWERED or accepted:  # achado atendido substitui o fallback da falha
                continue
            if handover and result.status == "insufficient" and not queue and _fallback_of(name, result, ctx, out):
                out.handover = name  # o supervisor LLM decide no lugar do FALLBACK fixo
                return out
            _apply_fallback(name, result, ctx, out, queue)
    return out


def _fallback_of(name: str, result: AgentResult, ctx: Context, out: Outcome) -> str | None:
    """O passo que o FALLBACK do domínio daria a esta falha (None = a tabela não desviaria)."""
    nxt = next_step(result, out.route, ctx.intent)
    return None if nxt == "escalation" and no_escalation(ctx) else nxt


def _answered_by_another(name: str, out: Outcome) -> AgentResult | None:
    """O último resultado de OUTRO especialista que já respondeu parte da pergunta neste turno (humano não conta)."""
    return next((r for r in reversed(out.results)
                 if r.status in ANSWERED and r.agent not in (name, "escalation", "human")), None)


def _apply_fallback(name: str, result: AgentResult, ctx: Context, out: Outcome, queue: list[str]) -> None:
    nxt = _fallback_of(name, result, ctx, out)
    if not nxt or nxt in queue:  # já agendado por outro agente do mesmo lote
        return
    if nxt == "escalation" and result.status == "insufficient" and (answered := _answered_by_another(name, out)):
        # A regra do supervisor LLM (prompt: "se OUTRO já respondeu parte da pergunta, responda com ela e ofereça o
        # humano"), que a tabela não seguia: escalava o turno inteiro. Medido na rodada 11 (offline): o faq pedido pelo
        # achado de recusa não achou orientação no corpus e o official-08 ia ao humano com os códigos já respondidos
        # pelo records. Erro (status error) continua indo ao FALLBACK.
        target = result if result.text else answered
        if not _MENTIONS_HUMAN.search(target.text or ""):
            offer = OFFER_HUMAN.get(ctx.language, OFFER_HUMAN["pt"])
            target.text = f"{(target.text or '').rstrip()}\n\n{offer}".strip()
            target.evidence = [*target.evidence, offer]  # template nosso, como o texto do escalation
        return
    ctx.handoff_reason = f"{name}_{result.reason or result.status}"
    if nxt == "escalation":
        _defer_dependents(name, queue, out)
    queue.insert(0, nxt)
    out.queued_by[nxt] = "table"
    out.replans.append(f"{name}:{result.reason or result.status}->{nxt}")
    METRICS.inc("replans_total", agent=name, reason=result.reason or result.status, engine="table")


def resume_table(out: Outcome, ctx: Context) -> Outcome:
    """O supervisor LLM falhou depois do atalho: a tabela aplica o FALLBACK que tinha passado adiante e segue."""
    name, out.handover = out.handover, None
    result = next(r for r in reversed(out.results) if r.agent == name)
    queue: list[str] = []
    _apply_fallback(name, result, ctx, out, queue)
    return _table_loop(queue, ctx, out)


def _defer_dependents(failed: str, queue: list[str], out: Outcome) -> None:
    """O passo `failed` vai ao humano: quem DEPENDE dele (DEPENDS do domínio, direta ou indiretamente) sai da fila e
    espera a resposta do operador, que entra como evidência na retomada (resume.py). Rodar agora seria responder sem
    o fato que faltou (ex.: manual do terminal sem saber o modelo do terminal)."""
    blocked = {failed}
    changed = True
    while changed:
        changed = False
        for step in queue:
            if step not in blocked and _d().DEPENDS.get(step, set()) & blocked:
                blocked.add(step)
                changed = True
    waiting = [q for q in queue if q in blocked and q != failed]
    if waiting:
        queue[:] = [q for q in queue if q not in waiting]
        out.deferred = list(dict.fromkeys([*out.deferred, *waiting]))
        out.replans.append(f"{failed}:escalated->defer{waiting}")


# --- motor LLM ---------------------------------------------------------------------------------------------
def lead_step(plan: list[str], ctx: Context) -> str | None:
    """1º passo do plano que o código roda antes da 1ª volta do supervisor LLM, ou None.

    Vale quando um passo seguinte DEPENDE dele (DEPENDS do domínio) e ele não depende de ninguém: a ordem já está
    decidida e o modelo só a confirmaria. Medido: em 48 de 48 turnos de plano
    ["records", "faq"] a 1ª volta do supervisor chamou exatamente records_agent (~1,7 s de Sonnet sequencial).
    Retomada de caso fica com o modelo (a resposta do humano muda o que falta).
    Opt-in (SUPERVISOR_LEAD=on): ao vivo, o faq "sem fonte" virou escalonamento em 3 de 6 casos com o passo
    antecipado contra 1 de 4 sem ele (amostra pequena demais para decidir), e o ganho de parede não apareceu com a
    CPU disputada.
    """
    if os.getenv("SUPERVISOR_LEAD", "off").lower() != "on":
        return None
    if len(plan) < 2 or ctx.facts.get("operator_answer") or plan[0] in SEQUENTIAL or plan[0] not in AGENTS:
        return None
    deps = _d().DEPENDS
    first = plan[0]
    if deps.get(first) or not any(first in deps.get(step, set()) for step in plan[1:]):
        return None
    return first if first in _d().ALLOWED.get(None, set()) else None


def _for_model(result: AgentResult) -> str:
    """O tool_result que o supervisor LLM lê do passo. Ablação no_needs: sem o achado (o modelo decide só com status,
    texto e fatos, como se o especialista não tivesse apontado nada)."""
    if result.needs and replan_mode() == "no_needs":
        return replace(result, needs=[]).for_supervisor()
    return result.for_supervisor()


def _note_needs(frm: str, result: AgentResult, ctx: Context, out: Outcome, pending: dict[str, dict]) -> None:
    """Motor LLM: o achado de `frm` é informação. Já foi ao modelo no tool_result e fica pendente até o modelo chamar
    o agente pedido; nenhum passo é inserido pelo código. Fora do modo "on", ou se o agente pedido não pode vir depois
    de `frm` (ALLOWED, NO_ESCALATION) ou já rodou, o achado só fica marcado no passo."""
    mode = replan_mode()
    for need in result.needs:
        agent = need["agent"]
        if mode != "on":
            _mark_need(result, agent, "hidden" if mode == "no_needs" else "blocked")
        elif agent in out.route:
            _mark_need(result, agent, "ran")
        elif agent not in AGENTS or agent not in _d().ALLOWED.get(frm, set()) \
                or (agent == "escalation" and no_escalation(ctx)):
            _mark_need(result, agent, "blocked")
        else:
            entry = pending.setdefault(agent, {"from": frm, "why": [], "hint": [], "results": []})
            for key in ("why", "hint"):
                if need.get(key) and need[key] not in entry[key]:
                    entry[key].append(need[key])
            entry["results"].append(result)
            _mark_need(result, agent, "blocked")  # até o modelo decidir: o turno pode parar antes (orçamento, teto)


def _open_needs(pending: dict[str, dict], last: str | None, ctx: Context, out: Outcome) -> dict[str, dict]:
    """Achados pendentes que o modelo ainda pode atender agora: o agente pedido não rodou, vem depois do último
    passo em ALLOWED, cabe em MAX_STEPS e há orçamento."""
    if len(out.route) >= MAX_STEPS or budget_exceeded() is not None:
        return {}
    allowed = _d().ALLOWED.get(last, set())
    return {agent: need for agent, need in pending.items() if agent not in out.route and agent in allowed}


def _need_reminder(open_needs: dict[str, dict]) -> str:
    """A volta de lembrete (o mesmo padrão do `nudged` do records): quais achados ficaram sem o agente pedido."""
    lines = []
    for agent, need in open_needs.items():
        detail = "; ".join(need["why"] + [f"dica: {h}" for h in need["hint"]])
        lines.append(f"- {need['from']}_agent pediu {agent}_agent" + (f" ({detail})" if detail else ""))
    return ("[supervisor] Achado sem resposta: um especialista devolveu `needs` pedindo outro especialista, que não "
            "foi chamado:\n" + "\n".join(lines) + "\nChame agora o especialista pedido, com a dica na consulta. Se o "
            "achado não muda a resposta ao cliente, responda de novo sem citar este lembrete.")


def _need_ignored(agent: str, need: dict) -> None:
    """O modelo encerrou sem chamar o agente pedido, mesmo com o lembrete: conta no passo, no log e em /metrics."""
    for result in need["results"]:
        _mark_need(result, agent, "ignored")
    METRICS.inc("needs_ignored_total", agent=need["from"], need=agent)
    log.info("need_ignored", extra={"extra_fields": {"from": need["from"], "need": agent,
                                                     "why": "; ".join(need["why"])[:200]}})


def run_llm(plan: list[str], ctx: Context, llm, done: Outcome | None = None) -> Outcome:
    """Motor LLM. `done`: passos que o atalho já rodou (o último devolveu insufficient); o modelo começa daí.

    Achado (`needs`) de um passo é informação para o modelo, que decide se chama o agente pedido (`_note_needs`); se
    ele encerrar com achado pendente, uma volta de lembrete (`_need_reminder`) e, ignorado de novo, `need_ignored`."""
    out = Outcome(engine="llm")
    standalone = str(ctx.facts.get("standalone") or "")
    asked = f"\nPergunta completa (router): {standalone}" if standalone and standalone != ctx.text else ""
    user = (f"Mensagem do usuário: {ctx.text}{asked}\nIntent: {ctx.intent}\nPlano sugerido pelo router: {plan}\n"
            f"Memória do usuário: {ctx.user_summary or '(nenhuma)'}\n\n{capabilities.prompt_block(ctx.language)}")
    if ctx.facts.get("operator_answer"):  # retomada: a resposta humana é evidência e autoridade, não pergunta nova
        user += (f"\nResposta do atendente humano (evidência; vale mais que qualquer suposição): "
                 f"{ctx.facts['operator_answer']}\nRode só os passos que faltam do plano; não escale de novo.")
    last: str | None = None
    lead = None if done else lead_step(plan, ctx)
    pending: dict[str, dict] = {}  # achados que o modelo ainda não atendeu: agente pedido → achado (_note_needs)
    if done:
        out.route, out.results, out.replans = list(done.route), list(done.results), list(done.replans)
        last = done.handover or (done.route[-1] if done.route else None)
        result = next(r for r in reversed(out.results) if r.agent == last)
        ctx.handoff_reason = f"{last}_{result.reason or result.status}"
        out.replans.append(f"{last}:{result.reason or result.status}->supervisor_llm")
        METRICS.inc("supervisor_handover_total", agent=str(last))
        user += (f"\n\nJá executado pelo código (atalho do plano de 1 passo): {last}_agent → "
                 f"{_for_model(result)}\nO resultado não cobriu a pergunta. Decida com ele: chamar outro "
                 "especialista que possa responder; se ninguém responder nada, escalation_agent com o motivo. "
                 f"Não chame {last}_agent de novo.")
    if lead:
        result = run_batch([lead], ctx)[0]
        _record(lead, result, ctx, out, "lead")
        last = lead
        if result.reason == "node_timeout":
            _exhaust("node_timeout", [p for p in plan if p not in out.route], ctx, out)
            return out
        if result.status not in ANSWERED:
            ctx.handoff_reason = f"{lead}_{result.reason or result.status}"
        user += (f"\n\nJá executado pelo código (passo do plano de que os outros dependem): {lead}_agent → "
                 f"{_for_model(result)}\nNão chame {lead}_agent de novo; decida o próximo passo com esse "
                 "resultado.")
        _note_needs(lead, result, ctx, out, pending)  # o achado do passo antecipado também é do modelo decidir
    messages: list = [{"role": "user", "content": user}]
    reminded = False  # a volta de lembrete do turno (uma só) já foi usada
    # Teto de voltas do modelo separado do teto de agentes: transição recusada não faz a rota crescer,
    # e um modelo insistente prenderia o worker.
    for round_ in range(MAX_ROUNDS):
        if len(out.route) >= MAX_STEPS:
            break
        if (what := budget_exceeded()) is not None:
            _exhaust(what, [p for p in plan if p not in out.route], ctx, out)
            return out
        resp = llm.create(domain.prompt("supervisor.md").format(language=ctx.language), messages, TOOLS,
                          max_tokens=8192)
        if resp.stop_reason != "tool_use":
            out.answer = "".join(b.text for b in resp.content if b.type == "text").strip() or None
            open_needs = _open_needs(pending, last, ctx, out)
            if open_needs and not reminded and round_ < MAX_ROUNDS - 1 and resp.content:
                # Achado pendente: uma volta a mais diz qual ficou sem resposta; quem decide ainda é o modelo.
                reminded = True
                for need in open_needs.values():
                    need["reminded"] = True
                messages.append({"role": "assistant", "content": resp.content})
                messages.append({"role": "user", "content": _need_reminder(open_needs)})
                METRICS.inc("needs_reminded_total", need=",".join(open_needs))
                continue
            for agent, need in (open_needs if reminded else {}).items():
                _need_ignored(agent, need)
            break
        out.answer = None  # tool call depois do lembrete: a resposta da volta anterior não vale mais
        messages.append({"role": "assistant", "content": resp.content})  # conteúdo inteiro (append-only)
        blocks = [b for b in resp.content if b.type == "tool_use"]
        verdicts: dict[str, dict] = {}
        approved: list[tuple] = []  # (bloco, agente)
        for block in blocks:
            name = _TOOL_TO_AGENT.get(block.name)
            if name is None or name not in _d().ALLOWED[last] or len(out.route) + len(approved) >= MAX_STEPS \
                    or (name == "escalation" and no_escalation(ctx)) \
                    or (not supervisor_replan() and name not in plan):  # ablação: só o plano do router
                verdicts[block.id] = {"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                      "content": f"transição não permitida: {last}->{block.name}"}
                continue
            approved.append((block, name))
        # escalation (terminal) roda depois dos outros do mesmo turno, sozinha
        batches = [[a for a in approved if a[1] not in SEQUENTIAL], [a for a in approved if a[1] in SEQUENTIAL]]
        remaining = [p for p in plan if p not in out.route]
        for batch in (b for b in batches if b):
            for block, name in batch:
                if name == "escalation":
                    # Motivo livre do modelo vai só para o ticket; métrica usa rótulo fixo (cardinalidade limitada).
                    ctx.handoff_reason = ctx.handoff_reason or (
                        "user_request" if name in remaining else "supervisor_decision")
                    ctx.facts["escalation_note"] = str(block.input.get("reason", ""))[:200]
                elif name == "faq" and block.input.get("query"):
                    ctx.facts.setdefault("query_hints", []).append(str(block.input["query"])[:300])
                # sub-pergunta por agente: em pergunta composta, cada um responde só a sua parte
                ask = block.input.get("query") or block.input.get("request")
                if ask:
                    ctx.facts.setdefault("ask", {})[name] = str(ask)[:300]
                need = pending.pop(name, None)  # o modelo atendeu o achado que pedia este agente
                for asked_by in (need or {}).get("results", []):
                    _mark_need(asked_by, name, "reminded" if need.get("reminded") else "called")
                if name in remaining:
                    continue  # passo do plano do router: não é replanejamento, mesmo vindo de um achado
                if need is not None:
                    _need_replan(need["from"], name, "; ".join(need["why"]), out, "llm")
                else:
                    out.replans.append(f"{last or 'start'}->{name} (plano: {remaining or '[]'})")
                    METRICS.inc("replans_total", agent=last or "start", reason="llm_decision", engine="llm")
            results = run_batch([name for _, name in batch], ctx)
            for (block, name), result in zip(batch, results, strict=True):
                _record(name, result, ctx, out, DECIDED_LLM)  # o modelo pediu a tool; o código só aprovou
                verdicts[block.id] = {"type": "tool_result", "tool_use_id": block.id, "content": _for_model(result)}
                last = name
                if result.status not in ANSWERED and name != "escalation":
                    ctx.handoff_reason = f"{name}_{result.reason or result.status}"
            timed_out = [n for n, r in zip([n for _, n in batch], results, strict=True) if r.reason == "node_timeout"]
            if timed_out:
                _exhaust("node_timeout", timed_out + [p for p in plan if p not in out.route], ctx, out)
                return out
            for (_, name), result in zip(batch, results, strict=True):
                _note_needs(name, result, ctx, out, pending)  # achado → informação; o modelo decide na próxima volta
        # todos os tool_result numa mensagem só, na ordem dos blocos
        messages.append({"role": "user", "content": [verdicts[b.id] for b in blocks]})
    return out


# --- caso com o humano e plano pendente ------------------------------------------------------------------------
def _hold(ctx: Context, ticket: dict, out: Outcome) -> None:
    """Caso aberto na conversa: anexa a mensagem, anula proposta de escrita do turno e avisa o cliente."""
    from .store import get_store

    cases.attach_note(ticket["id"], ctx.text)
    store = get_store()
    for result in out.results:
        if result.pending_action:  # escrita não fica proposta com o caso no humano: confirmar depois falha
            store.claim_action(result.pending_action, frm="pending", to="on_hold")
            METRICS.inc("actions_on_hold_total")
            result.pending_action, result.text = None, ""
    text = HOLD_TEXT.get(ctx.language, HOLD_TEXT["pt"]).format(ticket=ticket["id"])
    # required=False de propósito: `required` diz "ESTE turno escalou". Caso aberto de turno anterior é só aviso
    # (reason + ticket_id). Com True, toda pergunta depois de uma escalação virava "handoff" e inflava a taxa de
    # escalonamento: medido, split memory, handoff 92,3% → 76,9%.
    notice = AgentResult("hold", "ok", text=text, evidence=[text],
                         handoff=Handoff(required=False, reason="case_open", ticket_id=ticket["id"]))
    out.results.append(_decide(notice, "hold"))
    if out.answer is not None:
        out.answer = f"{out.answer}\n\n{text}"


def _save_pending(plan: list[str], ctx: Context, out: Outcome) -> None:
    """Turno terminou com o humano e passos do plano não rodaram: ficam no caso para depois da resposta."""
    ticket = next((r.handoff.ticket_id for r in out.results if r.handoff and r.handoff.ticket_id), None)
    if not ticket:
        return
    steps = out.deferred or [p for p in plan if p != "escalation" and p in AGENTS and p not in out.route]
    if steps:
        out.deferred = list(dict.fromkeys(steps))
        cases.save_pending(ticket, ctx, out.deferred)


def run(plan: list[str], ctx: Context, confidence: float = 1.0, prior: list[AgentResult] | None = None) -> Outcome:
    """Um turno. Caso aberto na conversa → modo espera (_hold); caso aberto NESTE turno → guarda o que faltou.

    `prior`: resultados que já existem antes do plano (retomada: o AgentResult "human" com a resposta do operador).
    Os fatos deles entram no contexto dos agentes e eles abrem a rota e os resultados do Outcome; na árvore de
    passos são do operador (DECIDED_OPERATOR): a resposta humana chega pronta, nenhum modelo nem regra a escolheu.
    """
    held = cases.open_case(ctx.conversation_id)
    seeded = Outcome()
    for result in prior or []:
        _record(result.agent, result, ctx, seeded, DECIDED_OPERATOR)
    out = _run(plan, ctx, confidence)
    if seeded.results:
        out.route[:0], out.results[:0] = seeded.route, seeded.results
    if held:
        _hold(ctx, held, out)
    else:
        out = _continue_with_operator(plan, ctx, out)
    _save_pending(plan, ctx, out)
    return out


CONSULTED = {"pt": "Consultei um atendente humano (protocolo {ticket}), que respondeu agora.",
             "en": "I checked with a human agent (ticket {ticket}), who replied just now."}
# Com o atendente já respondido no turno, só CONSULTED diz se houve encaminhamento. Saem do texto dos outros agentes:
# - a OFERTA de passar ao atendente ou de abrir o caso ("posso encaminhar a um atendente", "quer que eu encaminhe?",
#   "would you like me to hand this to a human");
# - a NEGAÇÃO do encaminhamento ou da abertura do caso, escrita por um especialista que não sabia do escalation do
#   mesmo turno (régua da rodada 10: a vitrine dizia "ele não foi encaminhado por mim" e, logo abaixo, "Consultei um
#   atendente humano"). Negação a até 4 palavras do verbo, sem vírgula no meio ("Não houve atraso, o pedido foi
#   encaminhado" fica); o imperativo "encaminhe" é instrução ao cliente e fica.
# Ficam: "a decisão é de um atendente humano", a ação pendente ("o chamado ainda não foi aberto": sem "caso"), o
# "Encaminhei" e as outras negações ("não tenho ferramenta para cancelar o contrato").
_HUMAN_WORDS = r"(?:atendente|humano|human agent|a human|an agent)"
_HANDOFF_OTHER = (r"|escalat\w*|forward(?:ed|ing)?\b|hand(?:ed|ing)?(?:\s+\S+){0,3}?\s+(?:off|over)\b"
                  r"|pass(?:ed|ing)?(?:\s+\S+){0,3}?\s+(?:on|along)\s+to\b"
                  r"|transfer\w*(?=(?:\s+\S+){0,3}?\s+(?:a|para|ao|à|pra|to)\s+(?:um\s+|uma\s+|o\s+|a\s+|an?\s+"
                  r"|the\s+)?(?:atendente|humano|human|agent|operador|operator|pessoa|person|representative)))")
# na negação, o imperativo/subjuntivo ("encaminhe", "escale") é instrução ao cliente e não conta; na oferta conta
# ("quer que eu encaminhe?")
_HANDOFF_VERB = rf"(?:encaminh(?!em?\b)\w*|escal(?:on)?(?:ad[oa]s?|ar|ei|ou|amos|aram|amento)\b{_HANDOFF_OTHER}"
_OFFER_VERB = rf"(?:encaminh\w*|escal(?:on)?(?:ad[oa]s?|ar|ei|ou|amos|aram|amento|em?)\b{_HANDOFF_OTHER}"
# "caso" com determinante: o substantivo ("esse caso", "a new case"), não a conjunção ("Caso o chamado não seja
# aberto", "in case")
_CASE = (r"(?:(?:um|uma|o|esse|este|seu|novo|outro|nenhum|the|an?|this|your|new|another|no)\s+){1,2}"
         r"(?:caso|case)\b")
_OPENS_CASE = rf"(?:abrir|abri|abro|abertura|open|opened|opening|create|created|raise|raised)(?:\s+d[eo])?\s+{_CASE}"
_OPENED = r"(?:abert[oa]|opened|created|raised)\b"
_OFFERS_HUMAN = re.compile(
    r"(?i)\b(?:posso|podemos|quer que eu|gostaria que eu|se quiser|se preferir|I can|we can|would you like me to|"
    rf"shall I|if you'd like|if you want)\b.{{0,160}}?(?:\b{_HUMAN_WORDS}\b|\b{_OFFER_VERB}|\b{_OPENS_CASE})")
_NEGATION = r"\b(?:n[ãa]o|nunca|jamais|nem|nenhum|nenhuma|not|never|no|cannot|unable|\w+n[’']t)\b"
_GAP = r"(?:\s+[^\s.,;:!?]+){0,4}?\s+"  # até 4 palavras, sem pontuação no meio
_DENIES_HANDOFF = re.compile(
    rf"(?i){_NEGATION}{_GAP}(?:{_HANDOFF_VERB}|{_OPENS_CASE})"  # "não foi encaminhado", "não tenho como abrir um caso"
    # "No case was opened", "nenhum caso foi aberto", "não há caso aberto"
    rf"|{_NEGATION}(?:\s+[^\s.,;:!?]+)?\s+(?:caso|case)\b[^.!?\n]{{0,30}}?\b{_OPENED}"
    rf"|\b{_CASE}[^.!?\n]{{0,30}}?{_NEGATION}(?:\s+\S+){{0,2}}?\s+{_OPENED}")  # "o caso não foi aberto"
_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n+")


def without_handoff_talk(text: str) -> str:
    """O texto sem as frases que oferecem ou negam a passagem ao atendente (o resto fica na ordem, linha a linha)."""
    lines = []
    for line in (text or "").split("\n"):
        kept = [s for s in _SENTENCES.split(line)
                if s.strip() and not _OFFERS_HUMAN.search(s) and not _DENIES_HANDOFF.search(s)]
        if kept or not line.strip():
            lines.append(" ".join(kept))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _continue_with_operator(plan: list[str], ctx: Context, out: Outcome) -> Outcome:
    """Espera síncrona pelo operador (app/hitl_sync.py): o caso aberto NESTE turno espera a
    resposta por até HITL_SYNC_WAIT_S; se ela chega, vira evidência ("human") e os passos que ficaram para depois do
    humano rodam agora, no mesmo turno. Sem resposta no prazo, nada muda: o caso segue assíncrono e a retomada de
    sempre (resume.py) leva a resposta quando ela chegar. Caso de aprovação (quatro olhos) não passa por aqui."""
    from . import hitl_sync
    from .resume import LABEL, human_result
    from .store import get_store

    if hitl_sync.wait_s() <= 0 or ctx.facts.get("resume_of") or ctx.facts.get("operator_answer"):
        return out
    esc = next((r for r in out.results if r.agent == "escalation" and r.handoff and r.handoff.required
                and r.handoff.ticket_id), None)
    ticket = get_store().get_ticket(esc.handoff.ticket_id) if esc else None
    if not ticket or ticket.get("kind") != "handoff":
        return out
    answered = hitl_sync.wait_answer(ticket["id"])
    if not answered:
        return out
    answer, operator = answered.get("answer") or "", answered.get("answered_by") or "operador"
    lang = ctx.language if ctx.language in LABEL else "pt"
    before = [r for r in out.results if r is not esc]  # o que o turno respondeu antes do atendente
    human = human_result(answer, operator)
    human.text = f"{LABEL[lang]}: {answer}"
    esc.text = CONSULTED[lang].format(ticket=ticket["id"])
    esc.evidence = [esc.text]
    esc.facts = {**esc.facts, "answered_live": True, "operator": operator}  # o DEMO e o eval leem daqui
    _record("human", human, ctx, out, DECIDED_OPERATOR)
    out.replans.append(f"escalation->human (resposta em {hitl_sync.wait_s():g}s de espera)")
    steps = out.deferred or [p for p in plan if p != "escalation" and p in AGENTS and p not in out.route]
    out.deferred = []
    ctx.facts["resume_of"] = ticket["id"]  # o passo retomado não reabre o caso (no_escalation)
    resumed, rerun = "", set()
    if steps:
        with span("resume_live", ticket=ticket["id"], steps=",".join(steps)):
            sub = _run(steps, ctx)
        out.route += sub.route
        out.results += sub.results
        out.replans += [f"human->{','.join(steps)} (no mesmo turno)", *sub.replans]
        rerun = {r.agent for r in sub.results}
        resumed = sub.answer or "\n\n".join(r.text for r in sub.results if r.text)
    # Resposta final: o que o turno já tinha respondido (sem oferecer nem negar o atendente, que agora respondeu; sem
    # o texto de quem rodou de novo depois dele) → a consulta e a resposta do atendente → os passos retomados. Juntar
    # todos os textos repetia o agente que rodou duas vezes e mantinha "posso encaminhar ao atendente" (ou "não foi
    # encaminhado por mim") ao lado de "Consultei um atendente humano".
    earlier = [without_handoff_talk(r.text) for r in before if r.text and r.agent not in rerun and r.agent != "human"]
    parts = [*earlier, esc.text, human.text, without_handoff_talk(resumed)]
    out.answer = "\n\n".join(p for p in parts if p and p.strip())
    METRICS.inc("plan_resumed_total", steps=str(len(steps)))
    return out


def fast_path(plan: list[str], ctx: Context, confidence: float) -> bool:
    """Plano de UM passo com router confiante: a tabela roda o passo e, se ele respondeu (ok/partial), a resposta é a
    do próprio agente. Insufficient NÃO cai no FALLBACK fixo: vai ao supervisor LLM (`_run`; medido: 24 de
    30 oficiais ao vivo usavam a tabela e o faq "sem fonte" escalava por regra, sem decisão observada).

    No motor LLM esse turno custa 2 chamadas sequenciais do supervisor (escolher a tool e redigir a resposta final),
    ~4 s por turno (medido), e a redação final só reescrevia o texto do agente (às vezes com frase a mais que o
    verificador de claims cortava depois). Com um passo só não há o que coordenar: falha segue FALLBACK e o achado
    segue a tabela (ALLOWED: o código insere o passo pedido, `decided_by: code`; no motor LLM quem decide é o modelo).
    Ficam no LLM: plano de 2+ passos (compor partes), router incerto e a retomada de caso (a resposta do humano muda o
    que falta fazer).
    """
    return supervisor_fast() and len(plan) == 1 and confidence >= supervisor_fast_min_confidence() \
        and not ctx.facts.get("operator_answer")


OFFER_HUMAN = {"pt": "Se quiser, posso encaminhar sua dúvida a um atendente humano.",
               "en": "If you'd like, I can hand this question to a human agent."}
_MENTIONS_HUMAN = re.compile(r"\b(?:humano|human|atendente|atendimento humano)\b", re.IGNORECASE)


def _offer_human_on_gap(out: Outcome, ctx: Context) -> None:
    """Atalho: resposta do faq que diz que a fonte não cobre parte da pergunta (ou resultado "partial", que diz o que
    falta) termina oferecendo o humano.

    No motor LLM era a redação final do supervisor que acrescentava a oferta. Sem ela, medido, 1 de 30 respostas
    oficiais do atalho foi julgada não útil exatamente por isso ("não responde nem oferece humano").
    Texto fixo, sem LLM; não vale onde o domínio nunca escala (clima/câmbio) nem quando o turno já abriu caso.
    """
    if no_escalation(ctx) or any(r.handoff for r in out.results):
        return
    for result in out.results:
        gap = result.status == "partial" or (result.agent == "faq" and result.status == "ok"
                                             and claims.states_absence(result.text))
        if gap and result.text and not _MENTIONS_HUMAN.search(result.text):
            offer = OFFER_HUMAN.get(ctx.language, OFFER_HUMAN["pt"])
            result.text = f"{result.text.rstrip()}\n\n{offer}"
            result.evidence = [*result.evidence, offer]  # template nosso, como o texto do escalation


NOT_RESOLVED = ("not_in_sources", "no_data", "not_found")


def _enforce_escalation(out: Outcome, ctx: Context) -> Outcome:
    """"O LLM propõe, o código dispõe": turno em que um especialista não achou fonte/registro e NINGUÉM respondeu nada
    termina com o escalation, mesmo que o supervisor LLM tenha preferido só oferecer (medido, split
    replan: 9 de 12 perguntas sem fonte terminaram em "posso encaminhar" sem caso aberto; o enunciado pede humano
    quando o sistema não resolve). O escalation_agent ainda aplica a regra da oferta (agents.escalation_offer_only)."""
    if not supervisor_replan() or no_escalation(ctx) or "escalation" in out.route or len(out.route) >= MAX_STEPS:
        return out
    if any(r.handoff for r in out.results) or ctx.facts.get("answered_by"):
        return out
    failed = next((r for r in out.results if r.status not in ANSWERED and r.reason in NOT_RESOLVED), None)
    if failed is None:
        return out
    ctx.handoff_reason = f"{failed.agent}_{failed.reason}"
    result = run_batch(["escalation"], ctx)[0]
    _record("escalation", result, ctx, out, "escalation")
    out.replans.append(f"{failed.agent}:{failed.reason}->escalation (código: ninguém respondeu)")
    METRICS.inc("replans_total", agent=failed.agent, reason="enforced_escalation", engine=out.engine)
    if out.answer is not None:
        # a redação do supervisor LLM oferecia o atendente ("posso encaminhar"); o código encaminhou de fato: o
        # cliente não lê as duas coisas. A resposta volta a ser a junção dos textos dos agentes (como na retomada).
        out.answer = None
    return out


def _run(plan: list[str], ctx: Context, confidence: float = 1.0) -> Outcome:
    llm = get_llm("supervisor")
    if llm.enabled and plan and fast_path(plan, ctx, confidence):
        METRICS.inc("supervisor_fast_path_total", agent=plan[0])
        out = run_table(plan, ctx, confidence, handover=True)
        out.engine = "fast_path"  # atalho com LLM ligado (não é o motor determinístico do offline)
        if out.handover:  # insufficient: o supervisor LLM decide, dentro do mesmo orçamento e de MAX_STEPS
            entry = copy.deepcopy(ctx.facts)
            try:
                return _enforce_escalation(run_llm(plan, ctx, llm, done=out), ctx)
            except LLMError:
                METRICS.inc("supervisor_fallback_total")
                ctx.facts.clear()
                ctx.facts.update(entry)
                out = resume_table(out, ctx)
                out.engine = "table"  # o LLM caiu: quem terminou foi o motor determinístico
        _offer_human_on_gap(out, ctx)
        return out
    if llm.enabled and plan:
        entry = copy.deepcopy(ctx.facts)  # o que o turno trouxe (dicas, tentativas, resposta humana na retomada)
        try:
            return _enforce_escalation(run_llm(plan, ctx, llm), ctx)
        except LLMError:
            METRICS.inc("supervisor_fallback_total")
            # recomeça limpo no motor determinístico: some só o que o motor LLM acumulou, não o que veio de fora
            ctx.facts.clear()
            ctx.facts.update(entry)
            ctx.handoff_reason = None
    return run_table(plan, ctx, confidence)
