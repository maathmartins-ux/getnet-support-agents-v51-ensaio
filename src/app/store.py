"""Estado persistido em SQLite: conversa, fila humana, ações, tokens revogados, limite de uso e analytics.

Sobrevive a restart e é compartilhado por todos os processos que leem o mesmo volume (WAL + busy timeout).
Toda transição de estado disputada é um UPDATE condicional (`... WHERE status = 'x'`, rowcount == 1): a
resposta do operador, a aprovação, a confirmação e o re-escalonamento por SLA acontecem uma vez só, também
entre réplicas. Várias máquinas: DATABASE_URL=postgresql://... troca o backend por `store_pg.PgStore`, a mesma
interface sobre Postgres (docs/adr/0003-postgres-opcional.md). O SQL daqui é o subconjunto comum aos dois
(placeholders `?`, upsert `ON CONFLICT`); o que difere (esquema, trava, LIMIT sem teto) fica nos ganchos da classe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sqlite3
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from .config import action_ttl_min, database_url, db_path, sla_minutes

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, user_id TEXT NOT NULL,
  role TEXT NOT NULL, content TEXT NOT NULL, intent TEXT, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_messages_conv ON messages(conversation_id, id);
CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, user_id TEXT NOT NULL, reason TEXT NOT NULL,
  summary TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', answer TEXT,
  created_at REAL NOT NULL, answered_at REAL);
CREATE TABLE IF NOT EXISTS user_memory (
  user_id TEXT PRIMARY KEY, summary TEXT NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS conversation_facts (
  conversation_id TEXT PRIMARY KEY, facts TEXT NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS actions (
  id TEXT PRIMARY KEY, conversation_id TEXT, user_id TEXT NOT NULL, tool TEXT NOT NULL,
  args TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', result TEXT, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS revoked_tokens (jti TEXT PRIMARY KEY, exp REAL NOT NULL);
CREATE TABLE IF NOT EXISTS rate_hits (key TEXT NOT NULL, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_rate_key ON rate_hits(key, ts);
CREATE TABLE IF NOT EXISTS requests (
  trace_id TEXT PRIMARY KEY, conversation_id TEXT, user_id TEXT, intent TEXT, route TEXT, handoff INTEGER,
  blocked INTEGER, ungrounded INTEGER, cost_usd REAL, ms REAL, message TEXT, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS feedback (
  trace_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, rating INTEGER NOT NULL, comment TEXT, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS response_snapshots (
  trace_id TEXT PRIMARY KEY, conversation_id TEXT, evidence TEXT NOT NULL, prompt_versions TEXT NOT NULL,
  ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
  target TEXT, detail TEXT);
CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
  BEGIN SELECT RAISE(ABORT, 'audit_log é só de inclusão'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
  BEGIN SELECT RAISE(ABORT, 'audit_log é só de inclusão'); END;
CREATE TABLE IF NOT EXISTS operator_skills (
  operator TEXT PRIMARY KEY, skills TEXT NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS ready_probe (id INTEGER PRIMARY KEY CHECK (id = 1), ts REAL NOT NULL);
"""
# Migração aditiva (banco de uma versão anterior no volume): coluna nova entra sem perder histórico.
COLUMNS = {
    "tickets": {"answered_by": "TEXT", "priority": "TEXT NOT NULL DEFAULT 'normal'",
                "kind": "TEXT NOT NULL DEFAULT 'handoff'", "action_id": "TEXT", "due_at": "REAL",
                "escalation_level": "INTEGER NOT NULL DEFAULT 0",
                # roteamento por especialidade (app/routing.py): especialidade do caso e para quem ele está
                "specialty": "TEXT", "routed_to": "TEXT NOT NULL DEFAULT 'specialty'"},
    "actions": {"risk": "TEXT NOT NULL DEFAULT 'normal'", "expires_at": "REAL", "approved_by": "TEXT",
                "ticket_id": "TEXT"},
}

# Trocar o modo de journal para WAL pede lock exclusivo e o SQLite NÃO chama o busy handler nesse PRAGMA:
# com outra conexão aberta no mesmo arquivo novo, ele devolve "database is locked" na hora. Medido:
# 4 threads do eval ao vivo criaram o banco juntas e 7 respostas caíram. Retry curto resolve
# também entre processos (réplicas), onde a trava de thread de get_store() não alcança.
WAL_DEADLINE_S = 5.0


def _enable_wal(conn: sqlite3.Connection) -> None:
    deadline = time.monotonic() + WAL_DEADLINE_S
    delay = 0.005
    while True:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) or time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.1)


def _upsert(table: str, key: str, *cols: str) -> str:
    """INSERT que substitui a linha da mesma chave. `ON CONFLICT ... DO UPDATE` vale no SQLite (>= 3.24) e no
    Postgres; `INSERT OR REPLACE` só existe no SQLite."""
    names = (key, *cols)
    return (f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join('?' * len(names))}) "
            f"ON CONFLICT ({key}) DO UPDATE SET " + ", ".join(f"{c} = excluded.{c}" for c in cols))


def _statements(sql: str) -> list[str]:
    """Divide o esquema em comandos completos (gatilho tem `;` dentro de BEGIN ... END: split(";") quebraria)."""
    out, buf = [], ""
    for line in sql.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            out.append(buf.strip())
            buf = ""
    return [s for s in out if s]


class Store:
    dialect = "sqlite"
    IntegrityError: type[Exception] = sqlite3.IntegrityError  # violação de unicidade/gatilho, nos dois backends
    NO_LIMIT = "-1"  # "sem teto" do LIMIT ... OFFSET (Postgres: ALL)

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as conn:
            _enable_wal(conn)  # leitores não bloqueiam o escritor (vários processos)
            # Esquema e migração numa transação IMMEDIATE: quem chega depois espera (busy_timeout) e já vê as
            # colunas; sem isso, dois processos leem "coluna falta" e o segundo ALTER quebra (duplicate column).
            conn.execute("BEGIN IMMEDIATE")
            for statement in _statements(SCHEMA):
                conn.execute(statement)
            for table, cols in COLUMNS.items():
                have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                for name, decl in cols.items():
                    if name not in have:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
            # Um caso de atendimento aberto por conversa, garantido PELO BANCO: com 2 réplicas, "existe? senão cria"
            # em dois passos deixava as duas criarem (achado ao montar o teste de réplicas, 01/11/2026).
            try:
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_open_handoff ON tickets(conversation_id) "
                             "WHERE status = 'open' AND kind = 'handoff'")
            except sqlite3.IntegrityError:  # banco antigo com duplicata: segue sem o índice (o código ainda checa)
                pass

    @contextmanager
    def _db(self):
        conn = sqlite3.connect(self.path, timeout=10)  # espera o lock de outro processo em vez de falhar
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA synchronous=NORMAL")  # padrão seguro com WAL: sem fsync por commit, sem corromper
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- conversa ---------------------------------------------------------------------
    def add_message(self, conversation_id: str, user_id: str, role: str, content: str,
                    intent: str | None = None) -> None:
        with self._db() as conn:
            conn.execute("INSERT INTO messages (conversation_id, user_id, role, content, intent, ts) "
                         "VALUES (?, ?, ?, ?, ?, ?)",
                         (conversation_id, user_id, role, content, intent, time.time()))

    def history(self, conversation_id: str, limit: int = 20) -> list[dict]:
        with self._db() as conn:
            rows = conn.execute("SELECT role, content, intent, ts FROM messages WHERE conversation_id = ? "
                                "ORDER BY id DESC LIMIT ?", (conversation_id, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def older_messages(self, conversation_id: str, skip_last: int) -> list[dict]:
        """Mensagens que já saíram da janela recente (para o resumo rolante da conversa)."""
        with self._db() as conn:
            rows = conn.execute("SELECT role, content, intent FROM messages WHERE conversation_id = ? "
                                f"ORDER BY id DESC LIMIT {self.NO_LIMIT} OFFSET ?",
                                (conversation_id, skip_last)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def conversation_facts(self, conversation_id: str) -> str | None:
        """Livro de fatos da conversa (JSON de app/memory.py); None = ainda não há."""
        with self._db() as conn:
            row = conn.execute("SELECT facts FROM conversation_facts WHERE conversation_id = ?",
                               (conversation_id,)).fetchone()
        return row["facts"] if row else None

    def set_conversation_facts(self, conversation_id: str, facts: str) -> None:
        with self._db() as conn:
            conn.execute("INSERT INTO conversation_facts (conversation_id, facts, updated_at) VALUES (?, ?, ?) "
                         "ON CONFLICT(conversation_id) DO UPDATE SET facts = excluded.facts, "
                         "updated_at = excluded.updated_at", (conversation_id, facts, time.time()))

    def conversation_owner(self, conversation_id: str) -> str | None:
        with self._db() as conn:
            row = conn.execute("SELECT user_id FROM messages WHERE conversation_id = ? ORDER BY id LIMIT 1",
                               (conversation_id,)).fetchone()
        return row["user_id"] if row else None

    # --- memória de longo prazo por usuário ------------------------------------------------
    # A coluna `summary` guarda o perfil (JSON de app/memory.py, com conversa de origem e data por item) ou, em banco
    # de versão anterior, a string antiga dos últimos assuntos: memory.Profile.loads lê as duas, sem migração.
    def user_summary(self, user_id: str) -> str:
        """O que está gravado para o usuário, como texto ("" = nada)."""
        with self._db() as conn:
            row = conn.execute("SELECT summary FROM user_memory WHERE user_id = ?", (user_id,)).fetchone()
        return row["summary"] if row else ""

    def set_user_summary(self, user_id: str, summary: str) -> None:
        """Formato antigo (texto com teto). O atendimento grava o perfil por `update_user_profile`."""
        with self._db() as conn:
            conn.execute("INSERT INTO user_memory (user_id, summary, updated_at) VALUES (?, ?, ?) "
                         "ON CONFLICT(user_id) DO UPDATE SET summary = excluded.summary, "
                         "updated_at = excluded.updated_at", (user_id, summary[:1000], time.time()))

    def user_profile(self, user_id: str) -> dict | None:
        """{"raw", "updated_at"} do perfil gravado, ou None."""
        with self._db() as conn:
            row = conn.execute("SELECT summary, updated_at FROM user_memory WHERE user_id = ?", (user_id,)).fetchone()
        return {"raw": row["summary"], "updated_at": row["updated_at"]} if row else None

    def update_user_profile(self, user_id: str, change) -> None:
        """Lê, muda e grava o perfil numa transação travada pelo usuário (SQLite: o arquivo; Postgres: só esta chave).

        `change(raw | None, updated_at | None)` devolve o texto novo, ou None para apagar a linha. Sem a trava, duas
        conversas do mesmo cliente em réplicas diferentes liam o mesmo perfil e a segunda gravação apagava a primeira.
        O texto vai inteiro (sem corte): o teto de itens é de app/memory.py, e JSON cortado seria perfil perdido.
        """
        with self._db() as conn:
            self._lock_key(conn, f"user_memory:{user_id}")
            row = conn.execute("SELECT summary, updated_at FROM user_memory WHERE user_id = ?", (user_id,)).fetchone()
            new = change(row["summary"] if row else None, row["updated_at"] if row else None)
            if new is None:
                if row:
                    conn.execute("DELETE FROM user_memory WHERE user_id = ?", (user_id,))
                return
            conn.execute(_upsert("user_memory", "user_id", "summary", "updated_at"), (user_id, new, time.time()))

    def _prune_profile(self, conn, user_id: str, *, lock: bool = True, **rule) -> tuple[int, int]:
        """Dentro de uma transação aberta: tira do perfil do usuário os itens que `rule` manda (memory.prune_profile).
        Devolve (linhas apagadas, itens tirados).

        Com `lock` (apagamento a pedido), a trava do usuário: um turno em outra conversa dele não regrava, depois, o
        que acabou de sair. Sem ela (retenção: passa por todos os perfis numa transação só, e no Postgres uma trava
        consultiva por usuário, presa até o fim da transação, esgotaria a tabela de travas), a gravação é condicional
        ao texto lido: se um turno gravou no meio, ele vence e o corte fica para a próxima purga."""
        from . import memory  # import tardio: memory não importa o store

        if lock:
            self._lock_open(conn, f"user_memory:{user_id}")
        row = conn.execute("SELECT summary, updated_at FROM user_memory WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return 0, 0
        kept, removed = memory.prune_profile(row["summary"], updated_at=row["updated_at"], **rule)
        if not removed:
            return 0, 0
        if kept is None:
            cur = conn.execute("DELETE FROM user_memory WHERE user_id = ? AND summary = ?", (user_id, row["summary"]))
            return (1, removed) if cur.rowcount == 1 else (0, 0)
        cur = conn.execute("UPDATE user_memory SET summary = ? WHERE user_id = ? AND summary = ?",
                           (kept, user_id, row["summary"]))
        return (0, removed) if cur.rowcount == 1 else (0, 0)

    # --- fila humana: handoff e aprovação -----------------------------------------------------
    def open_ticket(self, conversation_id: str, user_id: str, reason: str, summary: str,
                    priority: str = "normal", kind: str = "handoff", action_id: str | None = None,
                    specialty: str | None = None) -> dict:
        if kind == "handoff":
            existing = self.ticket_for(conversation_id, status="open", kind="handoff")
            if existing:  # idempotente: a mesma conversa não abre dois casos de atendimento
                return existing
        now = time.time()
        tid = "T-" + hashlib.sha1(f"{conversation_id}|{reason}|{action_id}|{now}".encode()).hexdigest()[:8]
        try:
            with self._db() as conn:
                conn.execute("INSERT INTO tickets (id, conversation_id, user_id, reason, summary, created_at, "
                             "priority, kind, action_id, due_at, specialty) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (tid, conversation_id, user_id, reason, summary, now, priority, kind, action_id,
                              now + 60 * sla_minutes(priority), specialty))
                # na mesma transação do insert: caso sem linha de roteamento não existe
                self._audit(conn, "system:routing", "ticket_routed", tid, {"specialty": specialty, "kind": kind})
        except self.IntegrityError:  # outra réplica abriu o caso desta conversa entre a checagem e o insert
            existing = self.ticket_for(conversation_id, status="open", kind="handoff")
            if existing:
                return existing
            raise
        return self.get_ticket(tid)

    def get_ticket(self, ticket_id: str) -> dict | None:
        with self._db() as conn:
            row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return dict(row) if row else None

    def ticket_for(self, conversation_id: str, status: str = "open", kind: str | None = None) -> dict | None:
        sql, args = "SELECT * FROM tickets WHERE conversation_id = ? AND status = ?", [conversation_id, status]
        if kind:
            sql, args = sql + " AND kind = ?", [*args, kind]
        with self._db() as conn:
            row = conn.execute(sql + " ORDER BY created_at DESC LIMIT 1", args).fetchone()
        return dict(row) if row else None

    def list_tickets(self, status: str = "open") -> list[dict]:
        with self._db() as conn:
            rows = conn.execute("SELECT * FROM tickets WHERE status = ? ORDER BY priority = 'high' DESC, created_at",
                                (status,)).fetchall()
        return [dict(r) for r in rows]

    def close_ticket(self, ticket_id: str, answer: str, operator: str, status: str = "answered") -> dict | None:
        """Fecha o caso uma vez só (UPDATE condicional): duas respostas simultâneas → uma vence, a outra None."""
        with self._db() as conn:
            cur = conn.execute("UPDATE tickets SET status = ?, answer = ?, answered_at = ?, answered_by = ? "
                               "WHERE id = ? AND status = 'open'", (status, answer, time.time(), operator, ticket_id))
        return self.get_ticket(ticket_id) if cur.rowcount == 1 else None

    def answer_ticket(self, ticket_id: str, answer: str, operator: str = "admin") -> dict | None:
        ticket = self.close_ticket(ticket_id, answer, operator)
        if ticket:  # a resposta humana entra no histórico da conversa do cliente
            self.add_message(ticket["conversation_id"], ticket["user_id"], "human_agent", answer)
        return ticket

    def escalate_overdue(self, now: float | None = None) -> list[dict]:
        """Casos abertos com SLA vencido sobem para prioridade alta UMA vez (atômico entre réplicas)."""
        now = now or time.time()
        with self._db() as conn:
            won = self._claim_overdue(conn, now)
            for tid in won:  # SLA vencido: sai da fila da especialidade e vai para qualquer operador
                conn.execute("UPDATE tickets SET routed_to = 'any' WHERE id = ?", (tid,))
                self._audit(conn, "system:sla", "ticket_rerouted", tid, {"to": "any", "reason": "sla_expired"})
        return [self.get_ticket(t) for t in won]

    @staticmethod
    def _claim_overdue(conn, now: float) -> list[str]:
        """Ids que ESTA chamada subiu de nível. SQLite: UPDATE condicional por id (o arquivo serializa escritores)."""
        ids = [r["id"] for r in conn.execute("SELECT id FROM tickets WHERE status = 'open' AND "
                                             "escalation_level = 0 AND due_at < ?", (now,))]
        return [tid for tid in ids if conn.execute(
            "UPDATE tickets SET escalation_level = 1, priority = 'high' WHERE id = ? AND escalation_level = 0",
            (tid,)).rowcount == 1]

    # --- ações que exigem confirmação (e aprovação, se risco alto) ------------------------------
    def create_action(self, conversation_id: str | None, user_id: str, tool: str, args: dict,
                      risk: str = "normal") -> str:
        aid = "A-" + uuid.uuid4().hex[:8]
        now = time.time()
        with self._db() as conn:
            conn.execute("INSERT INTO actions (id, conversation_id, user_id, tool, args, created_at, risk, expires_at) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (aid, conversation_id, user_id, tool, json.dumps(args, ensure_ascii=False), now, risk,
                          now + 60 * action_ttl_min()))
        return aid

    def get_action(self, action_id: str) -> dict | None:
        with self._db() as conn:
            row = conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
        if not row:
            return None
        action = dict(row)
        action["args"] = json.loads(action["args"])
        return action

    def claim_action(self, action_id: str, frm: str = "pending", to: str = "running") -> bool:
        """Muda o estado só se ainda estiver em `frm`. True = este chamador venceu a disputa."""
        with self._db() as conn:
            cur = conn.execute("UPDATE actions SET status = ? WHERE id = ? AND status = ?", (to, action_id, frm))
        return cur.rowcount == 1

    def update_action(self, action_id: str, **fields) -> None:
        if "result" in fields:
            fields["result"] = json.dumps(fields["result"], ensure_ascii=False)
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._db() as conn:
            conn.execute(f"UPDATE actions SET {cols} WHERE id = ?", (*fields.values(), action_id))

    def finish_action(self, action_id: str, status: str, result: dict) -> None:
        self.update_action(action_id, status=status, result=result)

    # --- especialidades dos operadores (roteamento; app/routing.py) ---------------------------------
    def operator_skills(self) -> dict[str, list[str]]:
        with self._db() as conn:
            return {r["operator"]: json.loads(r["skills"]) for r in conn.execute("SELECT * FROM operator_skills")}

    def set_operator_skills(self, operator: str, skills: list[str], actor: str) -> None:
        with self._db() as conn:
            conn.execute(_upsert("operator_skills", "operator", "skills", "updated_at"),
                         (operator, json.dumps(sorted(set(skills))), time.time()))
            self._audit(conn, actor, "operator_skills_set", operator, {"skills": sorted(set(skills))})

    # --- tokens revogados -----------------------------------------------------------------------
    def revoke(self, jti: str, exp: float) -> None:
        with self._db() as conn:
            conn.execute("INSERT INTO revoked_tokens (jti, exp) VALUES (?, ?) ON CONFLICT (jti) DO NOTHING", (jti, exp))
            conn.execute("DELETE FROM revoked_tokens WHERE exp < ?", (time.time() - 3600,))  # expirado não precisa

    def is_revoked(self, jti: str) -> bool:
        with self._db() as conn:
            return conn.execute("SELECT 1 FROM revoked_tokens WHERE jti = ?", (jti,)).fetchone() is not None

    # --- limite de uso compartilhado --------------------------------------------------------------
    def rate_allow(self, key: str, limit: int | None = None) -> bool:
        from .config import rate_limit_per_min

        limit = rate_limit_per_min() if limit is None else limit
        now = time.time()
        with self._db() as conn:
            self._lock_key(conn, key)  # contagem e inserção na mesma transação travada: sem corrida entre processos
            conn.execute("DELETE FROM rate_hits WHERE key = ? AND ts < ?", (key, now - 60))
            if random.random() < 0.01:  # chaves de uso único (cada IP) também saem: a tabela não cresce sem fim
                conn.execute("DELETE FROM rate_hits WHERE ts < ?", (now - 60,))
            used = conn.execute("SELECT COUNT(*) FROM rate_hits WHERE key = ?", (key,)).fetchone()[0]
            if used >= limit:
                return False
            conn.execute("INSERT INTO rate_hits (key, ts) VALUES (?, ?)", (key, now))
        return True

    @staticmethod
    def _begin(conn) -> None:
        conn.execute("BEGIN IMMEDIATE")  # SQLite: pega a trava de escrita já no início (sem upgrade que falha no meio)

    def _lock_key(self, conn, key: str) -> None:
        self._begin(conn)  # SQLite: trava o arquivo inteiro; o Postgres trava só a chave (store_pg)

    def _lock_open(self, conn, key: str) -> None:
        """Trava `key` numa transação JÁ aberta. SQLite: nada a fazer, o BEGIN IMMEDIATE dela já trava o arquivo."""

    def rate_reset(self) -> None:
        with self._db() as conn:
            conn.execute("DELETE FROM rate_hits")

    # --- analytics: sistema de trabalho (cada atendimento vira dado) -------------------------------
    def log_request(self, row: dict) -> None:
        with self._db() as conn:
            conn.execute(_upsert("requests", "trace_id", "conversation_id", "user_id", "intent", "route", "handoff",
                                 "blocked", "ungrounded", "cost_usd", "ms", "message", "ts"),
                         (row["trace_id"], row.get("conversation_id"), row.get("user_id"), row.get("intent"),
                          ",".join(row.get("route", [])), int(bool(row.get("handoff"))), int(bool(row.get("blocked"))),
                          int(bool(row.get("ungrounded"))), row.get("cost_usd", 0.0), row.get("ms", 0.0),
                          row.get("message", "")[:300], time.time()))

    def request_owner(self, trace_id: str) -> str | None:
        with self._db() as conn:
            row = conn.execute("SELECT user_id FROM requests WHERE trace_id = ?", (trace_id,)).fetchone()
        return row["user_id"] if row else None

    def save_snapshot(self, trace_id: str, conversation_id: str | None, evidence: list[str],
                      prompt_versions: dict[str, str]) -> None:
        """Evidência (já mascarada) e versão das instruções de uma resposta: o 👎 vira candidato a caso com elas."""
        with self._db() as conn:
            conn.execute(_upsert("response_snapshots", "trace_id", "conversation_id", "evidence", "prompt_versions",
                                 "ts"),
                         (trace_id, conversation_id, json.dumps(evidence[:20], ensure_ascii=False)[:20000],
                          json.dumps(prompt_versions, ensure_ascii=False), time.time()))

    def snapshot(self, trace_id: str) -> dict | None:
        """{question, answer, evidence, prompt_versions, conversation_id, intent} da resposta `trace_id`, ou None.

        Pergunta e resposta vêm das mensagens da conversa (gravadas mascaradas): a última resposta do assistente
        até o registro do atendimento e a fala do cliente logo antes dela."""
        with self._db() as conn:
            req = conn.execute("SELECT conversation_id, intent, ts FROM requests WHERE trace_id = ?",
                               (trace_id,)).fetchone()
            snap = conn.execute("SELECT evidence, prompt_versions FROM response_snapshots WHERE trace_id = ?",
                                (trace_id,)).fetchone()
            if not req:
                return None
            msgs = conn.execute("SELECT role, content FROM messages WHERE conversation_id = ? AND ts <= ? "
                                "ORDER BY id DESC LIMIT 2", (req["conversation_id"], req["ts"])).fetchall()
        pair = {m["role"]: m["content"] for m in msgs}
        return {"conversation_id": req["conversation_id"], "intent": req["intent"],
                "question": pair.get("user", ""), "answer": pair.get("assistant", ""),
                "evidence": json.loads(snap["evidence"]) if snap else [],
                "prompt_versions": json.loads(snap["prompt_versions"]) if snap else {}}

    def add_feedback(self, trace_id: str, user_id: str, rating: int, comment: str | None) -> None:
        with self._db() as conn:
            conn.execute(_upsert("feedback", "trace_id", "user_id", "rating", "comment", "ts"),
                         (trace_id, user_id, rating, (comment or "")[:500], time.time()))

    def analytics_rows(self) -> tuple[list[dict], list[dict]]:
        with self._db() as conn:
            reqs = [dict(r) for r in conn.execute("SELECT * FROM requests ORDER BY ts")]
            fb = [dict(r) for r in conn.execute("SELECT * FROM feedback")]
        return reqs, fb

    # --- auditoria (só inclusão: gatilhos recusam UPDATE e DELETE) ---------------------------------
    @staticmethod
    def _audit(conn, actor: str, action: str, target: str | None, detail: dict) -> None:
        # detalhe só com contagens e ids, nunca conteúdo da conversa: o log de auditoria não vira cópia dos dados
        conn.execute("INSERT INTO audit_log (ts, actor, action, target, detail) VALUES (?, ?, ?, ?, ?)",
                     (time.time(), actor, action, target, json.dumps(detail, ensure_ascii=False, sort_keys=True)))

    def audit(self, actor: str, action: str, target: str | None = None, **detail) -> None:
        with self._db() as conn:
            self._audit(conn, actor, action, target, detail)

    def audit_for(self, target: str, action: str) -> list[dict]:
        """Entradas da auditoria de um alvo e uma ação (ex.: o prazo de uma espera síncrona, hitl_sync)."""
        with self._db() as conn:
            rows = conn.execute("SELECT * FROM audit_log WHERE target = ? AND action = ? ORDER BY id",
                                (target, action)).fetchall()
        return [{**dict(r), "detail": json.loads(r["detail"] or "{}")} for r in rows]

    def audit_entries(self, limit: int = 100, action: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM audit_log", []
        if action:
            sql, args = sql + " WHERE action = ?", [action]
        with self._db() as conn:
            rows = conn.execute(sql + " ORDER BY id DESC LIMIT ?", (*args, limit)).fetchall()
        return [{**dict(r), "detail": json.loads(r["detail"] or "{}")} for r in rows]

    # --- LGPD: apagamento a pedido do titular e retenção por idade -----------------------------------
    @staticmethod
    def _delete_conversation_rows(conn, conversation_id: str) -> dict:
        counts = {"feedback": conn.execute(
            "DELETE FROM feedback WHERE trace_id IN (SELECT trace_id FROM requests WHERE conversation_id = ?)",
            (conversation_id,)).rowcount}
        conn.execute("DELETE FROM response_snapshots WHERE conversation_id = ?", (conversation_id,))
        for table in ("messages", "tickets", "actions", "requests", "conversation_facts"):
            counts[table] = conn.execute(f"DELETE FROM {table} WHERE conversation_id = ?", (conversation_id,)).rowcount
        return counts

    def delete_conversation(self, conversation_id: str, user_id: str, actor: str | None = None) -> dict | None:
        """Apaga a conversa do titular (mensagens, casos, ações, registros de atendimento e feedback).

        None se a conversa não existe ou é de outra pessoa (o chamador responde 404 nos dois casos). Da memória de
        longo prazo do usuário saem os itens que vieram desta conversa (cada item do perfil guarda a origem) e os de
        origem desconhecida (perfil no formato antigo, que não dá para separar por conversa); `user_memory` conta a
        linha apagada (perfil vazio) e `user_memory_items` os itens tirados. Tudo numa transação, com a auditoria.
        """
        with self._db() as conn:
            self._begin(conn)
            row = conn.execute("SELECT user_id FROM messages WHERE conversation_id = ? ORDER BY id LIMIT 1",
                               (conversation_id,)).fetchone()
            if not row or row["user_id"] != user_id:
                return None
            counts = self._delete_conversation_rows(conn, conversation_id)
            counts["user_memory"], counts["user_memory_items"] = self._prune_profile(
                conn, user_id, conversations={conversation_id}, unknown_origin=True)
            self._audit(conn, actor or f"user:{user_id}", "conversation_deleted", conversation_id, counts)
        return counts

    def purge_older_than(self, days: float, actor: str = "system:retention", now: float | None = None) -> dict:
        """Retenção: apaga conversas sem atividade há `days` dias (menos as que têm caso humano aberto),

        memória de longo prazo parada há `days` dias e registros soltos mais velhos que isso. Do perfil que segue em
        uso saem os itens mais velhos que o corte e os das conversas apagadas aqui. Auditado.
        """
        if days < 1:
            raise ValueError("retenção mínima de 1 dia (0 apagaria tudo por engano)")
        cutoff = (now or time.time()) - days * 86400
        with self._db() as conn:
            self._begin(conn)
            old = [r[0] for r in conn.execute(
                "SELECT conversation_id FROM messages GROUP BY conversation_id HAVING MAX(ts) < ? AND conversation_id "
                "NOT IN (SELECT conversation_id FROM tickets WHERE status = 'open')", (cutoff,))]
            kept = conn.execute("SELECT COUNT(DISTINCT conversation_id) FROM tickets WHERE status = 'open' AND "
                                "created_at < ?", (cutoff,)).fetchone()[0]
            totals = {"conversations": len(old), "kept_open_ticket": kept}
            for cid in old:
                for table, n in self._delete_conversation_rows(conn, cid).items():
                    totals[table] = totals.get(table, 0) + n
            # turnos bloqueados não gravam mensagem, só o registro do atendimento: saem pela idade
            totals["feedback"] = totals.get("feedback", 0) + conn.execute(
                "DELETE FROM feedback WHERE ts < ?", (cutoff,)).rowcount
            totals["requests"] = totals.get("requests", 0) + conn.execute(
                "DELETE FROM requests WHERE ts < ?", (cutoff,)).rowcount
            conn.execute("DELETE FROM response_snapshots WHERE ts < ?", (cutoff,))
            totals["tickets"] = totals.get("tickets", 0) + conn.execute(
                "DELETE FROM tickets WHERE status != 'open' AND COALESCE(answered_at, created_at) < ?",
                (cutoff,)).rowcount
            totals["actions"] = totals.get("actions", 0) + conn.execute(
                "DELETE FROM actions WHERE created_at < ? AND status != 'pending'", (cutoff,)).rowcount
            totals["user_memory"] = conn.execute("DELETE FROM user_memory WHERE updated_at < ?", (cutoff,)).rowcount
            totals["user_memory_items"] = 0
            for uid in [r["user_id"] for r in conn.execute("SELECT user_id FROM user_memory").fetchall()]:
                rows, items = self._prune_profile(conn, uid, lock=False, conversations=set(old), before=cutoff)
                totals["user_memory"] += rows
                totals["user_memory_items"] += items
            self._audit(conn, actor, "retention_purge", None, {"days": days, **totals})
        return totals

    # --- prontidão -------------------------------------------------------------------------------
    def probe_write(self) -> None:
        """Escrita real (e não só abrir o arquivo): volume cheio ou só leitura aparece aqui, não no 1º cliente."""
        with self._db() as conn:
            conn.execute("INSERT INTO ready_probe (id, ts) VALUES (1, ?) "
                         "ON CONFLICT(id) DO UPDATE SET ts = excluded.ts", (time.time(),))


def retention_days() -> float | None:
    """MEMORY_RETENTION_DAYS: idade máxima dos dados de conversa. Ausente ou 0 = sem purga automática."""
    value = float(os.getenv("MEMORY_RETENTION_DAYS", "0") or 0)
    return value if value > 0 else None


_STORE_LOCK = threading.Lock()
PG_SCHEMES = ("postgresql://", "postgres://")


def open_store(target: str | None = None) -> Store:
    """Instância NOVA do backend configurado (DATABASE_URL postgresql:// → Postgres; senão SQLite em DB_PATH).

    Nova instância = outro processo/réplica lendo o mesmo banco (testes de restart e de réplicas usam isto).
    """
    target = target or database_url() or str(db_path())
    if target.startswith(PG_SCHEMES):
        from .store_pg import PgStore  # import tardio: quem usa só SQLite não precisa do psycopg instalado

        return PgStore(target)
    return Store(Path(target))


@lru_cache(maxsize=8)
def _store_for(target: str) -> Store:
    return open_store(target)


def get_store() -> Store:
    # Cache por destino: testes trocam DB_PATH/DATABASE_URL e recebem um banco novo sem reiniciar o processo.
    # lru_cache não trava: sem o lock, N threads no 1º request criam N Stores do mesmo banco ao mesmo tempo.
    target = database_url() or str(db_path())
    with _STORE_LOCK:
        return _store_for(target)


def main(argv: list[str] | None = None) -> int:
    """Comando do operador: `python -m app.store purge [--days N]` (padrão MEMORY_RETENTION_DAYS)."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m app.store")
    sub = ap.add_subparsers(dest="cmd", required=True)
    purge = sub.add_parser("purge", help="apaga conversas e memória mais velhas que N dias (auditado)")
    purge.add_argument("--days", type=float, default=None, help="padrão: MEMORY_RETENTION_DAYS")
    purge.add_argument("--actor", default=os.getenv("USER") and f"cli:{os.getenv('USER')}" or "cli")
    args = ap.parse_args(argv)
    days = args.days or retention_days()
    if not days:
        print("defina --days ou MEMORY_RETENTION_DAYS", file=sys.stderr)
        return 2
    print(json.dumps(get_store().purge_older_than(days, actor=args.actor), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
