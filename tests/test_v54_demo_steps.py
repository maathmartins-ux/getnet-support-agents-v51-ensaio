"""Kit v5.4 — DEMO com árvore de passos e transcrição multi-turno (ideia do Skywalker: o trace legível por caso)."""
import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import app
from app.auth import issue_token

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("demo_md", ROOT / "scripts" / "demo_md.py")
demo_md = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo_md)


def test_chat_response_carries_the_step_tree():
    client = TestClient(app)
    got = client.post("/chat", json={"message": "Onde está meu pedido 1002?"},
                      headers={"Authorization": f"Bearer {issue_token('u1')}"}).json()
    step = got["steps"][0]
    assert step["agent"] == "records" and step["status"] == "ok" and step["ms"] is not None
    tool = step["tools"][0]
    assert tool["name"] == "lookup_record" and tool["args"] == {"record_id": "1002"}
    assert "em separação" in tool["preview"]


def test_step_tree_renders_agent_tool_args_preview_and_ms():
    lines = demo_md.step_tree([
        {"agent": "records", "status": "ok", "ms": 812.4, "tools": [
            {"name": "cancel_record", "args": {"record_id": "1001"}, "ok": False,
             "preview": '{"ok": false, "needs_confirmation": true, "action_id": "A-1"}'}], "pending_action": "A-1"},
        {"agent": "escalation", "status": "ok", "ms": 3.2, "ticket_id": "T-9", "answered_live": True, "tools": []},
        {"agent": "human", "status": "ok", "ms": None, "operator": "ana", "tools": []},
    ])
    text = "\n".join(lines)
    assert "1. **records** · ok · 812 ms · ação proposta `A-1`" in text
    assert "`cancel_record` {\"record_id\": \"1001\"} → proposta (aguarda a confirmação do cliente)" in text
    assert "caso T-9 · operador respondeu durante a espera" in text and "3. **human** · ok · operador `ana`" in text


def test_change_table_shows_before_after_and_unchanged():
    rows = demo_md.change_table({"before": {"status": "entregue", "item": "Livro A"},
                                 "after": {"status": "cancel_requested", "item": "Livro A"},
                                 "changed": {"status": ["entregue", "cancel_requested"]}, "unchanged": ["item"]})
    assert "| status | entregue | **cancel_requested** |" in rows and "| item | Livro A | (igual) |" in rows


def test_transcript_runs_memory_write_and_live_human(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join([
        '{"user": "u1"}',
        '{"say": "Onde está meu pedido 1002?"}',
        '{"say": "Pode cancelar o pedido 1001?"}',
        '{"confirm": true}',
        '{"say": "Quero falar com um atendente", "operator": "Posso ajudar: o prazo é de 3 a 5 dias úteis.", '
        '"wait_s": 5, "operator_after_s": 0.1}',
    ]), encoding="utf-8")
    md = demo_md.transcript(path, "abc1234", "hoje")
    assert "### Turno 1" in md and "`lookup_record`" in md
    assert "| status | entregue | **cancel_requested** |" in md  # antes/depois da escrita confirmada
    assert "operador respondeu durante a espera" in md and "Resposta do atendente: Posso ajudar" in md
