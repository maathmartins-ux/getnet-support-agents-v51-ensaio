"""O mesmo contrato do store nos dois backends (SQLite e Postgres; ver BACKEND_MODULES no conftest).

Réplicas = instâncias separadas de Store (open_store) sobre o MESMO banco, em threads: cada disputa tem um vencedor
só, a contagem do limite de uso é uma só e a escrita concorrente não perde linha.
"""
import threading
import time

import pytest

from app import auth, cases
from app.agents import Context
from app.store import get_store, open_store


def _run(n, fn):
    barrier, out, errors, lock = threading.Barrier(n), [], [], threading.Lock()

    def worker(i):
        try:
            barrier.wait()
            value = fn(i)
            with lock:
                out.append(value)
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert errors == []
    return out


def test_backend_follows_database_url(db_backend):
    from fastapi.testclient import TestClient

    from app.api import app

    assert get_store().dialect == db_backend
    health = TestClient(app).get("/health").json()
    assert health["store"] == db_backend and "postgresql://" not in str(health)  # a URL (com senha) não vaza


def test_two_replicas_escalating_the_same_conversation_open_one_ticket():
    replicas = [open_store(), open_store()]
    ids = _run(8, lambda i: replicas[i % 2].open_ticket("conv-1", "u1", "user_request", "quero um atendente")["id"])
    assert len(set(ids)) == 1 and len(replicas[0].list_tickets()) == 1


def test_concurrent_writers_lose_nothing():
    _run(4, lambda n: [open_store().add_message(f"c{n}", "u1", "user", f"m{i}") for i in range(25)])
    assert sum(len(get_store().history(f"c{n}", limit=100)) for n in range(4)) == 100


def test_rate_limit_is_one_count_across_replicas(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "5")
    replicas = [open_store(), open_store()]
    allowed = _run(12, lambda i: replicas[i % 2].rate_allow("k"))
    assert allowed.count(True) == 5  # 12 pedidos simultâneos em 2 réplicas: exatamente o limite passa
    assert replicas[0].rate_allow("outra") is True


def test_action_claim_has_one_winner_across_replicas():
    aid = get_store().create_action("c1", "u1", "cancel_record", {"record_id": "1001"})
    replicas = [open_store(), open_store()]
    assert _run(6, lambda i: replicas[i % 2].claim_action(aid)).count(True) == 1


def test_operator_reply_closes_once_across_replicas():
    ticket = get_store().open_ticket("c2", "u1", "user_request", "s")["id"]
    replicas = [open_store(), open_store()]
    won = _run(6, lambda i: replicas[i % 2].close_ticket(ticket, f"r{i}", f"op{i}"))
    assert sum(1 for t in won if t) == 1


def test_overdue_case_is_escalated_once_across_replicas():
    for i in range(5):
        get_store().open_ticket(f"c-sla-{i}", "u1", "user_request", "s")
    replicas = [open_store(), open_store()]
    later = time.time() + 10 ** 6
    batches = _run(4, lambda i: [t["id"] for t in replicas[i % 2].escalate_overdue(later)])
    flat = [t for b in batches for t in b]
    assert len(flat) == 5 and len(set(flat)) == 5  # cada caso sobe uma vez, em alguma réplica
    assert get_store().escalate_overdue(later) == []


def test_pending_plan_is_taken_once_under_race():
    ctx = Context(text="Qual o prazo?", language="pt", user_id="u1", conversation_id="c9", intent="faq")
    cases.save_pending("T-race", ctx, ["faq"])
    taken = _run(6, lambda i: cases.take_pending("T-race"))
    assert sum(1 for t in taken if t) == 1


def test_audit_log_rejects_update_on_both_backends():
    store = get_store()
    store.audit("operator:ana", "x", "T-1")
    with pytest.raises(store.IntegrityError), store._db() as conn:
        conn.execute("UPDATE audit_log SET actor = 'y'")
    assert store.audit_entries()[0]["actor"] == "operator:ana"


def test_postgres_migrations_are_versioned_and_idempotent(db_backend):
    if db_backend != "postgres":
        pytest.skip("migrações versionadas são do backend Postgres")
    from app.store_pg import MIGRATIONS

    first = get_store()
    assert first.schema_version() == MIGRATIONS[-1][0]
    replicas = _run(4, lambda i: open_store())  # 4 réplicas subindo juntas sobre o banco já migrado
    assert all(r.migrate() == [] for r in replicas)
    with first._db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == len(MIGRATIONS)


def test_rate_limit_fails_closed_when_postgres_is_unreachable(monkeypatch, db_backend):
    if db_backend != "postgres":
        pytest.skip("o caso SQLite está em test_identity.test_rate_limit_fails_closed")
    store = get_store()
    monkeypatch.setattr(store, "url", "postgresql://nobody@127.0.0.1:1/none?connect_timeout=1")
    store.close()  # sem conexão ociosa no pool: a próxima tenta abrir e falha
    assert auth.LIMITER.allow("k") is False


def test_postgres_upgrades_an_older_schema_in_place(db_backend, monkeypatch, pg_schema):
    if db_backend != "postgres":
        pytest.skip("migrações versionadas são do backend Postgres")
    from app import store_pg

    full = list(store_pg.MIGRATIONS)
    import psycopg

    schema = pg_schema.rsplit("%3D", 1)[1] + "_up"  # esquema novo e vazio, só para este cenário
    with psycopg.connect(pg_schema, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
    url = pg_schema.rsplit("%3D", 1)[0] + "%3D" + schema
    try:
        monkeypatch.setattr(store_pg, "MIGRATIONS", full[:1])
        old = store_pg.PgStore(url)  # banco de uma versão anterior, com dados
        old.add_message("c1", "u1", "user", "oi")
        monkeypatch.setattr(store_pg, "MIGRATIONS", full)
        new = store_pg.PgStore(url)
        assert new.schema_version() == full[-1][0] and new.history("c1")[0]["content"] == "oi"
        new.set_conversation_facts("c1", "{}")
        assert new.conversation_facts("c1") == "{}"
    finally:
        with psycopg.connect(pg_schema, autocommit=True) as conn:
            conn.execute(f"DROP SCHEMA {schema} CASCADE")
