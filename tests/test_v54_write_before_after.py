"""Escrita executada mostra o antes e o depois do registro alterado."""
import json

from app import actions
from app.store import get_store


def test_record_change_lists_changed_and_unchanged():
    out = actions.record_change({"status": "enviado", "item": "fone"}, {"status": "cancel_requested", "item": "fone"})
    assert out["changed"] == {"status": ["enviado", "cancel_requested"]} and out["unchanged"] == ["item"]


def test_confirmed_write_returns_before_after_and_saves_it():
    result, call = actions.run_tool("cancel_record", {"record_id": "1002"}, "u1", "c-ba")
    assert result["needs_confirmation"] and not call.ok
    done = actions.confirm_action(result["action_id"], "u1")
    data = done["data"]
    assert done["ok"] and data["before"]["status"] != "cancel_requested"
    assert data["after"]["status"] == "cancel_requested"
    assert list(data["changed"]) == ["status"] and "status" not in data["unchanged"]
    saved = get_store().get_action(result["action_id"])
    assert saved["status"] == "done" and json.loads(saved["result"])["data"]["changed"] == data["changed"]


def test_write_without_before_after_is_left_alone():
    assert actions._with_change({"ok": True, "data": {"x": 1}}) == {"ok": True, "data": {"x": 1}}
