"""API HTTP.

Cliente: POST /chat · GET /conversations/{id} · POST /actions/{id}/confirm · POST /feedback · POST /auth/revoke
  AUTH_MODE=required → identidade só do Bearer JWT assinado (corpo ignorado).
  AUTH_MODE=demo     → Bearer válido vence; sem ele, user_id do corpo (identity_verified=false,
                       rate limit por IP). Ver docs/adr/0001-auth-mode-demo.md.
Operador (X-Operator-Token = chave pessoal ou token compartilhado "admin"):
  GET /operator (console) · GET /handoffs · POST /handoffs/{id}/reply (retoma a conversa na hora)
  POST /actions/{id}/approve | /reject (ação de risco alto) · POST /handoffs/sla-check · GET /analytics
MCP (JWT obrigatório): /mcp — ferramentas ask, search_knowledge e crm_tool para qualquer cliente MCP.
Telegram (opcional): POST /telegram/webhook — resposta do operador pelo chat volta para a conversa.
LGPD: DELETE /me/conversations/{id} (titular, pelo token) · POST /admin/retention/purge (operador) · GET /audit
Infra: GET /health (vivo, com contagem de dados) · GET /ready (pronto: índice, banco gravável, LLM, orçamento; 503
  com o motivo) · GET /metrics
"""
from __future__ import annotations

import asyncio
import hmac
import os
import socket
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import __version__, keys, mcp_server, notify
from . import llm as llm_module
from .actions import confirm_action, decide_action
from .analytics import summarize
from .auth import LIMITER, login, operator_auth_mode, operator_name, revoke_token, verify_token
from .config import (
    auth_mode,
    data_dir,
    llm_api_key,
    llm_provider,
    login_rate_per_min,
    operator_token,
    retriever_name,
    token_ttl_min,
)
from .llm import warmup
from .observability import METRICS, configure_otel, log, otel_enabled
from .pipeline import handle
from .rag import get_index, get_retriever
from .resume import resume_after_human
from .routing import all_skills, queue_for, skills_of
from .schemas import ChatRequest, ChatResponse
from .store import get_store, retention_days

OPERATOR_HTML = (Path(__file__).parent / "static" / "operator.html").read_text(encoding="utf-8")
UI_HTML = (Path(__file__).parent / "static" / "ui.html").read_text(encoding="utf-8")
MCP_APP = mcp_server.http_app()  # uma vez: cria o session manager que o lifespan abre


def insecure_defaults() -> list[str]:
    """Segredo padrão ou curto torna o token forjável. Visível no /health e no log."""
    weak = keys.weak_secrets()  # HS256 do conjunto de chaves do JWT (AUTH_SECRET sem AUTH_KEYS)
    token = operator_token()
    weak += ["OPERATOR_TOKEN"] if token.startswith(("dev-", "troque-")) or len(token) < 16 else []
    # senha de exemplo do compose (Postgres/Grafana) também conta: APP_ENV=production não sobe com ela
    if "change-me" in os.getenv("DATABASE_URL", ""):
        weak.append("POSTGRES_PASSWORD")
    if "change-me" in os.getenv("GF_SECURITY_ADMIN_PASSWORD", ""):
        weak.append("GRAFANA_ADMIN_PASSWORD")
    return weak


def sla_check(now: float | None = None) -> list[dict]:
    """Re-escalona uma vez os casos com SLA vencido e avisa de novo o canal humano."""
    escalated = get_store().escalate_overdue(now)
    for ticket in escalated:
        METRICS.inc("sla_escalations_total", kind=ticket["kind"])
        notify.notify_new_ticket({**ticket, "reason": f"SLA vencido ({ticket['reason']})"})
    return escalated


async def _sla_loop(seconds: int) -> None:
    while True:
        await asyncio.sleep(seconds)
        with suppress(Exception):  # o laço de SLA nunca derruba a API
            await asyncio.to_thread(sla_check)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    keys.keyset()  # AUTH_KEYS/AUTH_ACTIVE_KID inválidos: a API não sobe (melhor que 401 em todo request)
    bad = insecure_defaults()
    if bad and os.getenv("APP_ENV") == "production":
        raise RuntimeError(f"segredos padrão em produção: {bad}")  # falha alto em vez de subir forjável
    if bad:
        log.warning("insecure_defaults", extra={"extra_fields": {"vars": bad}})
    configure_otel()
    warmup()  # SDK e clientes prontos antes do 1º request (o import custa segundos; ver llm.warmup)
    get_retriever()  # índice (e embeddings, no híbrido) prontos antes do 1º request e do healthcheck
    seconds = int(os.getenv("SLA_CHECK_SECONDS", "60"))  # 0 desliga (ex.: réplica sem responsabilidade de SLA)
    task = asyncio.create_task(_sla_loop(seconds)) if seconds > 0 else None
    # o app MCP montado não tem lifespan próprio sob o FastAPI: sem isto, "Task group is not initialized"
    async with mcp_server.server.session_manager.run():
        yield
    if task:
        task.cancel()


app = FastAPI(title="app", version=__version__, lifespan=lifespan)
app.mount("/mcp", MCP_APP)  # streamable HTTP; 401 sem JWT (mcp_server.require_bearer)
INSTANCE = os.getenv("INSTANCE_NAME") or socket.gethostname()


@app.middleware("http")
async def instance_header(request: Request, call_next):
    # Qual réplica atendeu: o teste de réplicas (scripts/scale_smoke.py) prova que a conversa continua entre elas.
    response = await call_next(request)
    response.headers["X-Instance"] = INSTANCE
    return response


class OperatorReply(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)


class Decision(BaseModel):
    answer: str = Field(default="", max_length=1000)


class Login(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class Feedback(BaseModel):
    trace_id: str = Field(min_length=1, max_length=64)
    rating: int = Field(ge=-1, le=1)  # 1 = 👍, -1 = 👎 (0 é recusado abaixo: sem opinião não é feedback)
    comment: str | None = Field(default=None, max_length=500)


def _bearer(authorization: str | None) -> str | None:
    return authorization.removeprefix("Bearer ").strip() if authorization else None


def _identity(authorization: str | None, fallback: str | None = None) -> tuple[str, bool]:
    """(user_id, identity_verified). Token presente e inválido é sempre 401, também no modo demo."""
    token = _bearer(authorization)
    if token:
        user_id = verify_token(token)
        if user_id:
            return user_id, True
    elif auth_mode() == "demo" and fallback:
        return fallback, False
    METRICS.inc("auth_failures_total")
    raise HTTPException(401, "token ausente, expirado ou inválido", headers={"WWW-Authenticate": "Bearer"})


def _require_operator(token: str | None) -> str:
    name = operator_name(token)
    if not name:
        METRICS.inc("operator_auth_failures_total")
        raise HTTPException(403, "operador não autorizado")
    return name


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request, authorization: str | None = Header(default=None)) -> ChatResponse:
    user_id, verified = _identity(authorization, req.user_id)
    # Sem identidade verificada, trocar o user_id do corpo não pode zerar o limite: a chave vira o IP.
    key = user_id if verified else f"ip:{request.client.host if request.client else 'unknown'}"
    if not LIMITER.allow(key):
        METRICS.inc("rate_limited_total")
        raise HTTPException(429, "muitas requisições; tente em 1 minuto", headers={"Retry-After": "60"})
    try:
        resp = handle(req, user_id, verified)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    # desfecho por intenção (painel "resolução por intenção"): resolvido = sem humano, sem bloqueio, sem pendência
    outcome = ("blocked" if resp.blocked else "handoff" if resp.handoff.required
               else "pending_action" if resp.pending_action else "resolved")
    METRICS.inc("chat_outcomes_total", intent=resp.intent, outcome=outcome)
    return resp


@app.post("/auth/login")
def auth_login(body: Login, request: Request) -> dict:
    """Usuário + senha → o mesmo JWT de /chat. Erro genérico (não diz se o usuário existe); limite por IP+usuário."""
    ip = request.client.host if request.client else "unknown"
    try:
        # por origem E por conta: só IP+usuário deixava força bruta distribuída em muitos IPs sem teto por conta
        allowed = (get_store().rate_allow(f"login:{ip}:{body.user_id}", login_rate_per_min())
                   and get_store().rate_allow(f"login:user:{body.user_id}", 4 * login_rate_per_min()))
    except Exception:  # noqa: BLE001 — banco fora: falha FECHADA, como o limitador do /chat
        allowed = False
    if not allowed:
        METRICS.inc("login_rate_limited_total")
        raise HTTPException(429, "muitas tentativas; tente em 1 minuto", headers={"Retry-After": "60"})
    token = login(body.user_id, body.password)
    if not token:
        raise HTTPException(401, "usuário ou senha inválidos", headers={"WWW-Authenticate": "Bearer"})
    get_store().audit(f"user:{body.user_id}", "login", body.user_id)
    return {"access_token": token, "token_type": "bearer", "expires_in": 60 * token_ttl_min()}


@app.post("/auth/revoke")
def revoke(authorization: str | None = Header(default=None)) -> dict:
    token = _bearer(authorization)
    if not token or not revoke_token(token):
        raise HTTPException(401, "token ausente, expirado ou inválido")
    return {"revoked": True}


@app.post("/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    """Sair = revogar o `jti` do token (mesma denylist de /auth/revoke)."""
    return revoke(authorization)


@app.get("/conversations/{conversation_id}")
def conversation(conversation_id: str, user_id: str | None = None,
                 authorization: str | None = Header(default=None)) -> dict:
    # Demo: ?user_id= faz o papel do corpo do /chat; quem não é dono recebe 404 nos dois modos.
    store = get_store()
    owner = store.conversation_owner(conversation_id)
    user_id, _ = _identity(authorization, user_id)
    if owner != user_id:
        raise HTTPException(404, "conversa não encontrada")
    open_ticket = store.ticket_for(conversation_id, "open")
    return {"conversation_id": conversation_id, "messages": store.history(conversation_id, limit=100),
            "open_ticket": open_ticket["id"] if open_ticket else None}


@app.delete("/me/conversations/{conversation_id}")
def delete_my_conversation(conversation_id: str, authorization: str | None = Header(default=None)) -> dict:
    """LGPD (eliminação a pedido do titular): só o dono, identificado pelo Bearer — nunca pelo user_id do corpo,
    nem no modo demo. Quem não é dono recebe 404 (não revela que a conversa existe). Auditado."""
    user_id, _ = _identity(authorization)
    counts = get_store().delete_conversation(conversation_id, user_id)
    if counts is None:
        raise HTTPException(404, "conversa não encontrada")
    METRICS.inc("privacy_deletions_total", kind="conversation")
    log.info("conversation_deleted", extra={"extra_fields": {"conversation_id": conversation_id, **counts}})
    return {"deleted": True, "conversation_id": conversation_id, "counts": counts}


class Purge(BaseModel):
    days: float | None = Field(default=None, ge=1)


@app.post("/admin/retention/purge")
def retention_purge(body: Purge | None = None, x_operator_token: str | None = Header(default=None)) -> dict:
    """Retenção por idade (MEMORY_RETENTION_DAYS, ou `days` no corpo). Operador; auditado com o nome dele."""
    operator = _require_operator(x_operator_token)
    days = (body.days if body else None) or retention_days()
    if not days:
        raise HTTPException(400, "defina MEMORY_RETENTION_DAYS ou envie {\"days\": N}")
    totals = get_store().purge_older_than(days, actor=f"operator:{operator}")
    METRICS.inc("privacy_deletions_total", kind="retention")
    return {"days": days, "purged": totals}


@app.get("/audit")
def audit(limit: int = 100, action: str | None = None, x_operator_token: str | None = Header(default=None)) -> list:
    _require_operator(x_operator_token)
    return get_store().audit_entries(min(max(limit, 1), 1000), action)


@app.post("/actions/{action_id}/confirm")
def confirm(action_id: str, user_id: str | None = None, authorization: str | None = Header(default=None)) -> dict:
    user_id, _ = _identity(authorization, user_id)
    result = confirm_action(action_id, user_id)
    if not result.get("ok") and result.get("error") == "not_found":
        raise HTTPException(404, "ação não encontrada")
    if result.get("error") == "expired":
        raise HTTPException(410, "ação expirada; peça de novo")
    return result


@app.post("/actions/{action_id}/approve")
def approve(action_id: str, x_operator_token: str | None = Header(default=None)) -> dict:
    operator = _require_operator(x_operator_token)
    out = decide_action(action_id, operator, approve=True)
    if out is None:
        raise HTTPException(409, "ação inexistente ou já decidida")
    get_store().audit(f"operator:{operator}", "action_approved", action_id)
    return out


@app.post("/actions/{action_id}/reject")
def reject(action_id: str, body: Decision | None = None, x_operator_token: str | None = Header(default=None)) -> dict:
    operator = _require_operator(x_operator_token)
    out = decide_action(action_id, operator, approve=False, note=(body.answer if body else ""))
    if out is None:
        raise HTTPException(409, "ação inexistente ou já decidida")
    get_store().audit(f"operator:{operator}", "action_rejected", action_id)
    return out


@app.post("/feedback")
def feedback(body: Feedback, authorization: str | None = Header(default=None)) -> dict:
    user_id, _ = _identity(authorization)
    if body.rating == 0:
        raise HTTPException(422, "rating deve ser 1 ou -1")
    store = get_store()
    if store.request_owner(body.trace_id) != user_id:  # só o dono avalia a própria resposta
        raise HTTPException(404, "atendimento não encontrado")
    store.add_feedback(body.trace_id, user_id, body.rating, body.comment)
    METRICS.inc("feedback_total", rating=str(body.rating))
    if body.rating < 0:  # 👎 vira candidato a caso (revisão humana antes de entrar num split: evals/candidates.py)
        from .candidates import add_from_feedback

        add_from_feedback(body.trace_id, user_id, body.comment, store.snapshot(body.trace_id) or {})
        return {"ok": True, "candidate": f"cand-{body.trace_id}"}
    return {"ok": True}


@app.get("/analytics")
def analytics(x_operator_token: str | None = Header(default=None)) -> dict:
    _require_operator(x_operator_token)
    return summarize(*get_store().analytics_rows())


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/docs")  # quem abre o endereço cai na documentação interativa, não num 404


@app.get("/ui", response_class=HTMLResponse)
def merchant_ui() -> str:
    # Tela do lojista: rota de agentes, ferramentas, fontes, estado do caso e a resposta do operador chegando.
    # Página estática sem CDN; o token é digitado e fica só na aba (nunca embutido nem gravado).
    return UI_HTML


@app.get("/operator", response_class=HTMLResponse)
def operator_console() -> str:
    # Página estática; os dados vêm de /handoffs com o token digitado pelo operador (nunca embutido no HTML).
    return OPERATOR_HTML


@app.get("/handoffs")
def handoffs(status: str = "open", x_operator_token: str | None = Header(default=None)) -> list[dict]:
    operator = _require_operator(x_operator_token)
    store = get_store()
    # fila do operador: especialidade dele e re-roteados pelo SLA primeiro (app/routing.py)
    return [{**t, "messages": store.history(t["conversation_id"], limit=10)}
            for t in queue_for(operator, store.list_tickets(status))]


class Skills(BaseModel):
    skills: list[str] = Field(max_length=20)


@app.get("/operators")
def operators(x_operator_token: str | None = Header(default=None)) -> dict:
    me = _require_operator(x_operator_token)
    return {"me": me, "skills": skills_of(me), "operators": all_skills()}


@app.put("/operators/{name}/skills")
def set_skills(name: str, body: Skills, x_operator_token: str | None = Header(default=None)) -> dict:
    actor = _require_operator(x_operator_token)
    if actor not in (name, "admin"):  # cada um mexe nas próprias; o admin, em todas
        raise HTTPException(403, "só o próprio operador ou o admin")
    get_store().set_operator_skills(name, [s.strip()[:40] for s in body.skills if s.strip()], f"operator:{actor}")
    return {"operator": name, "skills": skills_of(name)}


@app.post("/handoffs/sla-check")
def handoffs_sla_check(now: float | None = None, x_operator_token: str | None = Header(default=None)) -> dict:
    _require_operator(x_operator_token)
    return {"escalated": sla_check(now)}


def _answer(ticket_id: str, answer: str, operator: str, channel: str) -> dict | None:
    ticket = get_store().answer_ticket(ticket_id, answer, operator)
    if not ticket:
        return None
    METRICS.inc("handoff_replies_total", channel=channel)
    get_store().audit(f"operator:{operator}", "handoff_reply", ticket_id, channel=channel)
    # Retomada: o assistente escreve a próxima mensagem ao cliente agora, a partir da resposta humana.
    return {"ticket": ticket, "resumed": resume_after_human(ticket, operator)}


@app.post("/handoffs/{ticket_id}/reply")
def reply(ticket_id: str, body: OperatorReply, x_operator_token: str | None = Header(default=None)) -> dict:
    out = _answer(ticket_id, body.answer, _require_operator(x_operator_token), "console")
    if not out:
        raise HTTPException(404, "ticket não encontrado ou já respondido")
    return out


@app.post("/telegram/webhook")
def telegram_webhook(update: dict,
                     x_telegram_bot_api_secret_token: str | None = Header(default=None)) -> dict:
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if not secret or not x_telegram_bot_api_secret_token or not hmac.compare_digest(
            x_telegram_bot_api_secret_token.encode(), secret.encode()):
        raise HTTPException(403, "webhook não autorizado")
    parsed = notify.parse_reply(update)
    if not parsed:
        return {"ok": True, "handled": False}  # 200 sempre: o Telegram reenvia update que recebeu erro
    who = ((update.get("message") or {}).get("from") or {}).get("username") or "telegram"
    out = _answer(parsed[0], parsed[1], f"tg:{who}", "telegram")
    return {"ok": True, "handled": bool(out), "ticket_id": parsed[0]}


@app.get("/.well-known/jwks.json")
def jwks() -> JSONResponse:
    # Públicas das chaves assimétricas (validam, não emitem). Cache curto: rotação aparece em minutos.
    return JSONResponse(keys.jwks(), headers={"Cache-Control": "public, max-age=300"})


@app.get("/health")
def health() -> dict:
    # data_files > 0 é o que o smoke do container confere: prova que o caminho dos dados
    # resolve dentro da imagem, não só na máquina de quem desenvolveu.
    files = [p for p in data_dir().rglob("*") if p.is_file() and p.name != ".gitkeep"]
    return {"status": "ok", "version": __version__, "mode": llm_provider(), "auth_mode": auth_mode(),
            "operator_auth": operator_auth_mode(), "retriever": (ret := get_retriever()).name,  # efetivo
            "retriever_requested": retriever_name(), "retriever_fallback": getattr(ret, "fallback", ""),
            "otel": otel_enabled(),
            "telegram": bool(notify.configured()), "insecure_defaults": insecure_defaults(),
            "store": get_store().dialect,  # sqlite | postgres (DATABASE_URL); a URL nunca aparece
            "jwt": _jwt_status(),
            "data_files": len(files)}


def _jwt_status() -> dict:
    try:
        ring, active = keys.keyset()
    except keys.KeyConfigError as exc:
        return {"ok": False, "reason": str(exc)[:200]}
    return {"ok": True, "active_kid": active, "alg": ring[active].alg, "kids": sorted(ring)}


def readiness() -> dict[str, dict]:
    """Cada dependência com ok e motivo. Separado do /health: o processo pode estar vivo e não pronto."""
    checks: dict[str, dict] = {}
    try:
        n = len(get_index().docs)
        checks["index"] = {"ok": n > 0, "docs": n, "reason": None if n else f"índice vazio em {data_dir()}"}
    except Exception as exc:  # noqa: BLE001 — prontidão relata a falha; não derruba o processo
        checks["index"] = {"ok": False, "reason": f"índice não carregou: {type(exc).__name__}"}
    try:
        get_store().probe_write()
        checks["db"] = {"ok": True, "reason": None}
    except Exception as exc:  # noqa: BLE001
        checks["db"] = {"ok": False, "reason": f"banco não aceita escrita: {type(exc).__name__}: {exc}"[:200]}
    provider = llm_provider()
    if provider == "offline":
        checks["llm"] = {"ok": True, "mode": "offline", "reason": None}  # modo declarado, determinístico
    else:
        has_key = bool(llm_api_key())
        checks["llm"] = {"ok": has_key, "mode": provider,
                         "reason": None if has_key else f"LLM_PROVIDER={provider} sem chave (APP_ANTHROPIC_API_KEY)"}
    status = getattr(llm_module, "budget_status", None)  # orçamento da instalação, se o módulo de LLM tiver um
    if callable(status):
        budget = dict(status() or {})
        remaining = budget.get("remaining_usd")
        ok = remaining is None or remaining > 0
        checks["budget"] = {"ok": ok, **budget, "reason": None if ok else "orçamento esgotado"}
    return checks


@app.get("/ready")
def ready() -> JSONResponse:
    checks = readiness()
    failed = {name: c["reason"] for name, c in checks.items() if not c["ok"]}
    if failed:
        METRICS.inc("ready_failures_total")
    return JSONResponse({"ready": not failed, "failed": failed, "checks": checks}, status_code=503 if failed else 200)


@app.get("/metrics", response_class=PlainTextResponse)
def metrics(authorization: str | None = Header(default=None)) -> str:
    """Prometheus. Com METRICS_TOKEN definido, exige `Authorization: Bearer <METRICS_TOKEN>` (o scrape manda)."""
    expected = os.getenv("METRICS_TOKEN", "")
    if expected and not hmac.compare_digest((authorization or "").encode(), f"Bearer {expected}".encode()):
        raise HTTPException(status_code=401, detail="metrics: token inválido")
    return METRICS.render()
