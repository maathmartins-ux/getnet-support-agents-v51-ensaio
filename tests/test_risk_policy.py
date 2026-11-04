"""Limite de valor por ação (risk.py): até o limite só o dono confirma; acima, dono + operador (quatro olhos);
acima do teto, nada é proposto; valor desconhecido vai a quatro olhos. A regra aparece no texto da ferramenta."""
import hashlib

import pytest
from fastapi.testclient import TestClient

from app import actions, domain
from app.api import app
from app.auth import issue_token
from app.store import get_store

client = TestClient(app)
OP = {"X-Operator-Token": "test-operator"}
ANA = {"X-Operator-Token": "chave-pessoal-da-ana"}  # OPERATOR_KEYS do fixture `personal_key`


@pytest.fixture
def personal_key(monkeypatch):
    """Chave pessoal da Ana ao lado do token compartilhado (migração: os dois valem) — só ela aprova risco alto."""
    monkeypatch.setenv("OPERATOR_KEYS", "ana:" + hashlib.sha256(b"chave-pessoal-da-ana").hexdigest())
    monkeypatch.setenv("OPERATOR_SHARED_TOKEN", "on")
def u1():
    return {"Authorization": f"Bearer {issue_token('u1')}"}


@pytest.fixture
def anticipation(monkeypatch):
    d = domain.active()
    tool = {"description": "Antecipa recebíveis.", "write": True, "risk": "high",
            "input_schema": {"type": "object", "properties": {"amount": {"type": "number"}}, "required": ["amount"]},
            "fn": lambda amount, user_id: {"ok": True, "data": {"anticipated": amount}}}
    monkeypatch.setattr(d, "TOOLS", {**d.TOOLS, "anticipate": tool})
    monkeypatch.setattr(d, "RISK_POLICY", {"anticipate": {"amount": "amount", "four_eyes_above": 5000,
                                                          "block_above": 200000, "currency": "R$"}}, raising=False)


def propose(amount):
    result, _ = actions.run_tool("anticipate", {"amount": amount}, "u1", "conv-r")
    return result


def test_below_limit_needs_only_the_owner(anticipation):
    r = propose(4999.99)
    assert r["risk"] == "normal" and r["policy"] == {"amount": 4999.99, "four_eyes_above": 5000.0,
                                                      "block_above": 200000.0}
    done = client.post(f"/actions/{r['action_id']}/confirm", headers=u1()).json()
    assert done == {"ok": True, "data": {"anticipated": 4999.99}}


def test_limit_itself_is_owner_only_and_above_goes_to_four_eyes(anticipation, personal_key):
    assert propose(5000)["risk"] == "normal"
    r = propose(5000.01)
    assert r["risk"] == "high"
    first = client.post(f"/actions/{r['action_id']}/confirm", headers=u1()).json()
    assert first["awaiting_operator"] and get_store().get_action(r["action_id"])["status"] == "awaiting_operator"
    assert client.post(f"/actions/{r['action_id']}/approve", headers=OP).status_code == 403  # compartilhado
    approved = client.post(f"/actions/{r['action_id']}/approve", headers=ANA).json()
    assert approved["result"] == {"ok": True, "data": {"anticipated": 5000.01}}
    assert approved["action"]["approved_by"] == "ana"


def test_above_ceiling_is_not_proposed(anticipation):
    r = propose(250000)
    assert r["error"] == "above_limit" and "action_id" not in r
    with get_store()._db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0] == 0


def test_args_outside_the_schema_never_become_a_proposal(anticipation):
    """Valor ausente ou fora do tipo: o schema vale no servidor e nada é proposto (antes ia aos quatro olhos)."""
    from app.store import get_store

    for args in ({}, {"amount": "muito"}):
        result, _ = actions.run_tool("anticipate", args, "u1", "conv-r")
        assert result["ok"] is False and result["error"] == "invalid_args" and "action_id" not in result
    with get_store()._db() as conn:
        assert not conn.execute("SELECT 1 FROM actions WHERE conversation_id = 'conv-r'").fetchall()


def test_env_overrides_the_domain_limit(anticipation, monkeypatch):
    monkeypatch.setenv("RISK_LIMITS", "anticipate:100")
    assert propose(150)["risk"] == "high" and propose(100)["risk"] == "normal"


def test_capability_text_declares_the_rule(anticipation):
    spec = next(s for s in actions.tool_specs() if s["name"] == "anticipate")
    assert "até R$ 5.000,00, só a confirmação do cliente" in spec["description"]
    assert "quatro olhos" in spec["description"] and "acima de R$ 200.000,00" in spec["description"]


def test_tool_without_policy_keeps_its_fixed_risk():
    result, _ = actions.run_tool("refund_record", {"record_id": "1001"}, "u1", "c1")
    assert result["risk"] == "high" and "policy" not in result
    result, _ = actions.run_tool("cancel_record", {"record_id": "1001"}, "u1", "c1")
    assert result["risk"] == "normal"
    spec = next(s for s in actions.tool_specs() if s["name"] == "refund_record")
    assert spec["description"] == domain.active().TOOLS["refund_record"]["description"]


def test_amount_can_come_from_the_record(anticipation, monkeypatch):
    d = domain.active()
    monkeypatch.setattr(d, "RISK_POLICY", {"anticipate": {"amount": lambda args, user: 9000.0 if user == "u1"
                                                          else 10.0, "four_eyes_above": 5000}})
    assert propose(1)["risk"] == "high"  # o valor do registro manda, não o que o modelo escreveu no argumento


def test_capabilities_card_states_the_value_rule(anticipation):
    from app import capabilities

    card = capabilities.card("pt")
    line = next(x for x in card.splitlines() if "anticipate" in x)
    assert "até R$ 5.000,00, só a confirmação do cliente" in line
