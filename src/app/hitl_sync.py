"""Consulta síncrona ao operador: o turno espera a resposta humana por até HITL_SYNC_WAIT_S e o plano continua.

O escalation espera a resposta e a devolve ao plano: "supervisor → humano → retoma" fica visível num turno só.
Aqui a espera é ANTES de virar ticket
assíncrono e mantém tudo o que já existe (fila persistida, especialidade, SLA, quatro olhos, Telegram):

1. o escalation abre o caso como sempre e avisa o operador (notify_new_ticket);
2. com HITL_SYNC_WAIT_S > 0 (padrão 0 no processo, para a suíte e o eval; 20 no
   docker-compose.yml; teto MAX_WAIT_S), o turno consulta o caso a cada
   HITL_SYNC_POLL_S (padrão 2 s) até o prazo. Cada turno espera só o próprio caso (o servidor atende outras
   conversas em paralelo);
3. resposta dentro do prazo → vira evidência (resume.human_result) e os passos pendentes do plano rodam NO MESMO
   turno (supervisor._continue_with_operator); fora do prazo → o caso segue assíncrono e a retomada de sempre
   (resume.resume_after_human) leva a resposta à conversa quando ela chegar.

Quem leva a resposta à conversa é decidido pela hora gravada da resposta (`answered_at`) contra o prazo gravado na
auditoria (`sync_wait`): respondeu até o prazo → o turno ao vivo; depois → a retomada assíncrona. Sem corrida: os
dois lados leem os mesmos dois carimbos, e só um deles cumpre a condição.
"""
from __future__ import annotations

import os
import threading
import time

from .observability import METRICS, span
from .store import get_store

AUDIT_ACTION = "sync_wait"


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except ValueError:
        return default


# Teto da espera abaixo do timeout do balanceador (ops/lb.py) e do cliente: o /chat é síncrono e cada espera prende
# uma thread do servidor; acima do teto, o caso segue assíncrono como sempre.
MAX_WAIT_S = 20.0
_WAITERS = threading.BoundedSemaphore(max(1, int(_env_float("HITL_SYNC_MAX_WAITERS", 8))))


def wait_s() -> float:
    return min(MAX_WAIT_S, _env_float("HITL_SYNC_WAIT_S", 0.0))


def poll_s() -> float:
    return max(0.01, _env_float("HITL_SYNC_POLL_S", 2.0))


def deadline_of(ticket_id: str) -> float | None:
    rows = get_store().audit_for(ticket_id, AUDIT_ACTION)
    return max((float(r["detail"].get("deadline", 0)) for r in rows), default=None) if rows else None


def live_owns(ticket: dict) -> bool:
    """O turno ao vivo leva esta resposta? (respondida até o prazo de uma espera síncrona)."""
    if not ticket or not ticket.get("answered_at"):
        return False
    deadline = deadline_of(ticket["id"])
    return deadline is not None and float(ticket["answered_at"]) <= deadline


def wait_answer(ticket_id: str, seconds: float | None = None, sleep=time.sleep, clock=time.time) -> dict | None:
    """Espera a resposta do operador ao caso. Devolve o ticket respondido (até o prazo) ou None."""
    seconds = min(MAX_WAIT_S, wait_s() if seconds is None else seconds)
    if seconds <= 0:
        return None
    if not _WAITERS.acquire(blocking=False):  # esperas simultâneas no teto: segue assíncrono, não trava o servidor
        METRICS.inc("hitl_sync_total", outcome="busy")
        return None
    try:
        return _wait(ticket_id, seconds, sleep, clock)
    finally:
        _WAITERS.release()


def _wait(ticket_id: str, seconds: float, sleep, clock) -> dict | None:
    store = get_store()
    deadline = clock() + seconds
    store.audit("system:hitl_sync", AUDIT_ACTION, ticket_id, deadline=round(deadline, 3), wait_s=seconds)
    with span("hitl_sync_wait", ticket=ticket_id, wait_s=seconds):
        while True:
            ticket = store.get_ticket(ticket_id)
            if ticket and ticket.get("status") == "answered" and ticket.get("answered_at"):
                won = float(ticket["answered_at"]) <= deadline
                METRICS.inc("hitl_sync_total", outcome="answered" if won else "late")
                return ticket if won else None
            if clock() >= deadline:
                # leitura final DEPOIS do prazo: resposta gravada até o prazo e vista só agora continua sendo deste
                # turno (live_owns diria o mesmo e a retomada assíncrona não a levaria)
                ticket = store.get_ticket(ticket_id)
                if ticket and ticket.get("answered_at") and float(ticket["answered_at"]) <= deadline:
                    METRICS.inc("hitl_sync_total", outcome="answered")
                    return ticket
                METRICS.inc("hitl_sync_total", outcome="timeout")
                return None
            sleep(min(poll_s(), max(0.0, deadline - clock())))
