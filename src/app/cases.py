"""Caso de atendimento além do ticket: plano pendente, mensagens anexadas enquanto espera e estado do caso.

- Plano pendente: o turno terminou com o humano e passos do plano não rodaram (orçamento estourado, ou o
  supervisor LLM escalou antes). Os passos ficam aqui e `resume.resume_after_human` os executa depois da
  resposta do operador. Retomada uma vez só (UPDATE condicional pending → running → done), também entre réplicas.
- Notas: mensagem que chega com o caso aberto é anexada ao caso (o operador e a retomada leem).

Tabelas próprias no MESMO banco do store. No SQLite são criadas sob demanda (o store continua dono do arquivo); no
Postgres entram nas migrações versionadas de `store_pg` (DDL de tipos diferentes, aplicada uma vez por esquema).
"""
from __future__ import annotations

import json
import threading
import time

from .store import get_store

SCHEMA = """
CREATE TABLE IF NOT EXISTS case_plans (
  ticket_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS case_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT NOT NULL, content TEXT NOT NULL, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_case_notes ON case_notes(ticket_id, id);
CREATE TABLE IF NOT EXISTS case_state (
  conversation_id TEXT PRIMARY KEY, state TEXT NOT NULL, cycles INTEGER NOT NULL DEFAULT 0,
  steps TEXT NOT NULL DEFAULT '[]', proof TEXT, updated_at REAL NOT NULL);
"""
_READY: set[str] = set()
_LOCK = threading.Lock()


def _db():
    store = get_store()
    key = str(store.path)
    if key not in _READY:
        with _LOCK:
            if key not in _READY and store.dialect == "sqlite":
                with store._db() as conn:
                    for statement in filter(str.strip, SCHEMA.split(";")):
                        conn.execute(statement)
            _READY.add(key)
    return store._db()


# --- caso aberto e notas ------------------------------------------------------------------------------------
def open_case(conversation_id: str) -> dict | None:
    """Caso de atendimento humano aberto nesta conversa (aprovação de ação não conta)."""
    return get_store().ticket_for(conversation_id, "open", kind="handoff")


def attach_note(ticket_id: str, content: str) -> None:
    with _db() as conn:
        conn.execute("INSERT INTO case_notes (ticket_id, content, ts) VALUES (?, ?, ?)",
                     (ticket_id, content[:2000], time.time()))


def notes(ticket_id: str) -> list[str]:
    with _db() as conn:
        rows = conn.execute("SELECT content FROM case_notes WHERE ticket_id = ? ORDER BY id", (ticket_id,))
        return [r["content"] for r in rows]


# --- plano pendente -----------------------------------------------------------------------------------------
def save_pending(ticket_id: str, ctx, steps: list[str]) -> None:
    """Guarda os passos que faltaram + o que o agente precisa para rodá-los depois (texto, sub-perguntas)."""
    payload = {"steps": steps, "text": ctx.text, "intent": ctx.intent, "language": ctx.language,
               "ask": dict(ctx.facts.get("ask", {})), "query_hints": list(ctx.facts.get("query_hints", []))}
    with _db() as conn:
        row = conn.execute("SELECT payload FROM case_plans WHERE ticket_id = ? AND status = 'pending'",
                           (ticket_id,)).fetchone()
        if row:  # o mesmo caso recebeu outro turno pendente: soma os passos, mantém o 1º pedido
            old = json.loads(row["payload"])
            payload = {**old, "steps": list(dict.fromkeys(old["steps"] + steps))}
        conn.execute("INSERT INTO case_plans (ticket_id, conversation_id, payload, status, created_at) "
                     "VALUES (?, ?, ?, 'pending', ?) ON CONFLICT (ticket_id) DO UPDATE SET "
                     "conversation_id = excluded.conversation_id, payload = excluded.payload, status = 'pending', "
                     "created_at = excluded.created_at",
                     (ticket_id, ctx.conversation_id, json.dumps(payload), time.time()))


def pending(ticket_id: str) -> dict | None:
    with _db() as conn:
        row = conn.execute("SELECT payload FROM case_plans WHERE ticket_id = ? AND status = 'pending'",
                           (ticket_id,)).fetchone()
    return json.loads(row["payload"]) if row else None


def take_pending(ticket_id: str) -> dict | None:
    """Reivindica o plano pendente (uma vez só). None = não há, ou outro processo já retomou."""
    with _db() as conn:
        won = conn.execute("UPDATE case_plans SET status = 'running' WHERE ticket_id = ? AND status = 'pending'",
                           (ticket_id,)).rowcount == 1
        row = conn.execute("SELECT payload FROM case_plans WHERE ticket_id = ?", (ticket_id,)).fetchone()
    return json.loads(row["payload"]) if won and row else None


def finish_pending(ticket_id: str, status: str = "done") -> None:
    with _db() as conn:
        conn.execute("UPDATE case_plans SET status = ? WHERE ticket_id = ?", (status, ticket_id))
