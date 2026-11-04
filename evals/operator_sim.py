"""Operadora simulada: responde o caso de atendimento que o turno abriu, `after_s` segundos depois de o turno começar
a esperar por ela.

Uma implementação só para a medida e para a vitrine dizerem a mesma coisa:
- o split `hitl` do eval (evals/run_evals.py): caso com `"operator": {"answer": ..., "after_s": ...}` e `"wait_s"`;
  ela responde pela função que o console chama depois da autenticação (`reply_direct`: fecha o caso, audita com o
  nome dela e dispara a retomada), sem depender do OPERATOR_TOKEN/OPERATOR_KEYS do ambiente;
- a transcrição de vitrine (scripts/demo_md.py --transcript): ela responde pelo endpoint do console com chave pessoal
  (`reply_console`), e o nome dela vai para o passo e para a auditoria.

A thread roda numa CÓPIA do contexto de quem a cria (contextvars.copy_context): no eval, o banco do caso (`_CASE_DB`)
e o escopo do cassete valem para a resposta dela e para a retomada assíncrona que a resposta dispara.

Relógio dela: `after_s` conta do começo da espera síncrona do turno (o prazo que app/hitl_sync.py grava na auditoria
`sync_wait`), não da abertura do caso. Entre abrir o caso e esperar, o turno ainda roda o resto do plano (ao vivo, a
redação final do supervisor LLM, ~2 s): contando da abertura, um `after_s` curto respondia antes da espera e o caso
"no prazo" media outra coisa. Assim `after_s < wait_s` é no turno e `after_s > wait_s` é atrasado, como o caso diz.
Turno que não espera (sem `wait_s`, caso de aprovação, esperas no teto) não grava prazo: o relógio dela conta de
quando viu o caso, e a resposta segue pela retomada.
"""
from __future__ import annotations

import contextvars
import threading
import time

POLL_S = 0.05  # quanto ela demora para notar o caso novo e o começo da espera
PATIENCE_S = 60.0  # teto para achar o caso e o começo da espera (turno ao vivo: ~20 s no pior caso medido)
POST_TIMEOUT_S = 120.0  # a resposta dela dispara a retomada, que ao vivo chama o LLM e roda os passos pendentes
# Nos casos do eval o turno consulta o caso a cada 0,2 s (o padrão do produto é 2 s, HITL_SYNC_POLL_S): a resposta no
# prazo entra no turno sem até 2 s a mais de espera por caso. A consulta só muda QUANDO o turno vê a resposta; quem a
# leva (turno ou retomada) é decidido pelos carimbos de hitl_sync, iguais nos dois casos.
TURN_POLL_S = 0.2
EVAL_OPERATOR = "operadora_eval"


def reply_direct(name: str = EVAL_OPERATOR, channel: str = "eval"):
    """Resposta pela mesma função que o endpoint do console chama depois de autenticar (app.api._answer)."""
    def reply(ticket_id: str, answer: str) -> tuple[int, dict]:
        from app.api import _answer

        out = _answer(ticket_id, answer, name, channel)
        return (200, out) if out else (404, {})
    return reply


def reply_console(token: str):
    """Resposta pelo POST /handoffs/{id}/reply do app em processo, com a chave do operador (`X-Operator-Token`)."""
    def reply(ticket_id: str, answer: str) -> tuple[int, dict]:
        from fastapi.testclient import TestClient

        from app.api import app

        r = TestClient(app).post(f"/handoffs/{ticket_id}/reply", json={"answer": answer},
                                 headers={"X-Operator-Token": token})
        try:
            body = r.json()
        except ValueError:
            body = {}
        return r.status_code, body if isinstance(body, dict) else {}
    return reply


def open_handoffs() -> set[str]:
    """Casos de atendimento abertos agora (no banco do contexto): os que ela NÃO responde."""
    from app.store import get_store

    return {t["id"] for t in get_store().list_tickets("open") if t["kind"] == "handoff"}


class Operator:
    """A operadora de UM turno. `start()` antes do turno; `finish(ticket)` depois dele.

    `state`: ticket (o caso que ela achou), status (HTTP do POST; None = não respondeu), resumed (o que a retomada
    fez: `engine` "live_turn" quando o turno ao vivo levou a resposta), clock ("wait" = contou do começo da espera do
    turno; "seen" = de quando viu o caso), error.
    """

    def __init__(self, answer: str, after_s: float, reply, seen: set[str] | None = None,
                 patience_s: float = PATIENCE_S) -> None:
        self.answer, self.after_s, self.reply = answer, max(0.0, float(after_s)), reply
        self.seen, self.patience_s = set(seen or ()), patience_s
        self.turn_over = threading.Event()  # o turno acabou: sem caso visto até aqui, ela desiste
        self.state: dict = {"ticket": None, "status": None, "resumed": None, "clock": None, "error": None}
        self.thread: threading.Thread | None = None

    def start(self) -> Operator:
        ctx = contextvars.copy_context()  # banco do caso e escopo do cassete de quem a criou
        self.thread = threading.Thread(target=ctx.run, args=(self._run,), daemon=True, name="operator-sim")
        self.thread.start()
        return self

    def _fresh(self) -> str | None:
        fresh = sorted(open_handoffs() - self.seen)
        return fresh[0] if fresh else None

    def _wait_started(self, ticket: str) -> float | None:
        """Quando o turno começou a esperar este caso (prazo gravado − espera), ou None."""
        from app.hitl_sync import AUDIT_ACTION
        from app.store import get_store

        rows = get_store().audit_for(ticket, AUDIT_ACTION)
        if not rows:
            return None
        detail = rows[-1]["detail"]
        return float(detail.get("deadline", 0)) - float(detail.get("wait_s", 0))

    def _run(self) -> None:
        try:
            end = time.time() + self.patience_s
            while True:  # o caso novo do turno; "acabou" é lido ANTES da busca: há sempre uma busca depois do fim
                over = self.turn_over.is_set()
                ticket = self._fresh()
                if ticket or over or time.time() > end:
                    break
                self.turn_over.wait(POLL_S)
            if not ticket:
                return
            self.state["ticket"], seen_at = ticket, time.time()
            while True:  # o começo da espera do turno; sem espera (turno acabou, prazo nunca gravado) vale o "vi"
                over = self.turn_over.is_set()
                started = self._wait_started(ticket)
                if started is not None or over or time.time() > end:
                    break
                time.sleep(POLL_S)
            self.state["clock"] = "wait" if started is not None else "seen"
            delay = (started if started is not None else seen_at) + self.after_s - time.time()
            if delay > 0:
                time.sleep(delay)
            status, body = self.reply(ticket, self.answer)
            self.state.update(status=status, resumed=(body or {}).get("resumed"))
        except Exception as exc:  # noqa: BLE001 — operadora quebrada vira estado legível, não derruba o eval
            self.state["error"] = f"{type(exc).__name__}: {exc}"[:300]

    def finish(self, ticket: str | None = None, timeout_s: float = POST_TIMEOUT_S) -> dict:
        """Fim do turno. Sem caso (nem o do turno, `ticket`, nem um que ela viu), ela desiste na hora; com caso,
        espera a resposta dela sair (até `timeout_s` depois da hora dela) e devolve `state`."""
        self.turn_over.set()
        if self.thread is not None:
            pending = ticket or self.state["ticket"]
            self.thread.join(self.after_s + timeout_s if pending else 5.0)
            if self.thread.is_alive():
                self.state["error"] = self.state["error"] or "operadora sem resposta no prazo do eval"
        return self.state

    @property
    def posted(self) -> bool:
        return isinstance(self.state["status"], int) and 200 <= self.state["status"] < 300
