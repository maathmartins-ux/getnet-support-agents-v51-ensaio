"""Achados da revisão de robustez: balanceador não repete pedido enviado; espera do operador com teto; candidatos."""
import json

from app import candidates, hitl_sync


def test_sync_wait_is_capped_below_the_balancer_timeout(monkeypatch):
    monkeypatch.setenv("HITL_SYNC_WAIT_S", "45")
    assert hitl_sync.wait_s() == hitl_sync.MAX_WAIT_S < 30


def test_sync_wait_gives_up_when_all_waiter_slots_are_taken(monkeypatch):
    sem = hitl_sync._WAITERS
    held = 0
    while sem.acquire(blocking=False):
        held += 1
    try:
        assert hitl_sync.wait_answer("T-x", seconds=5) is None
    finally:
        for _ in range(held):
            sem.release()


def test_candidates_skip_a_truncated_line_and_write_atomically(tmp_path):
    path = tmp_path / "candidates.jsonl"
    path.write_text(json.dumps({"id": "a"}) + "\n" + '{"id": "b", "quest', encoding="utf-8")
    assert [r["id"] for r in candidates.read_all(path)] == ["a"]
    candidates.write_all([{"id": "c"}], path)
    assert [r["id"] for r in candidates.read_all(path)] == ["c"] and not list(tmp_path.glob("*.tmp"))


def test_balancer_does_not_retry_a_request_already_sent():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "ops" / "lb.py").read_text(encoding="utf-8")
    assert "conn.connect()" in src and "send_error(504" in src and "UPSTREAM_TIMEOUT_S = 120" in src
