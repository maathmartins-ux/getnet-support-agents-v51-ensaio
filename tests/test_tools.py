"""Frente T: ferramentas do domínio challenge (identidade do servidor, isolamento, contas no código, needs)."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest


@pytest.fixture
def d(domain_data):
    from app import domain

    return domain.active()


def _ctx(text, lang="pt", history=None, facts=None):
    from app.agents import Context

    return Context(text=text, language=lang, user_id="cliente1988", conversation_id="c-t",
                   history=history or [], facts=facts or {})


def test_names_schemas_and_risk(d):
    assert set(d.TOOLS) == {"get_settlements", "get_transactions", "get_terminal_status",
                            "request_receivables_advance", "open_support_ticket"}
    for tool in d.TOOLS.values():
        schema = tool["input_schema"]
        assert schema["additionalProperties"] is False
        assert "user_id" not in schema["properties"]
    assert d.TOOLS["request_receivables_advance"]["write"] and d.TOOLS["request_receivables_advance"]["risk"] == "high"
    assert d.TOOLS["open_support_ticket"]["write"] and "risk" not in d.TOOLS["open_support_ticket"]
    assert not any(n.endswith("_record") for n in d.TOOLS)
    assert set(d.ELIGIBLE_STATUS) <= set(d.TOOLS)


def test_users_come_from_crm(d):
    from app.auth import known_users

    assert d.users() == ["cliente1988", "cliente2024"] == known_users()


def test_isolation_other_merchant_is_not_found(d):
    fn = d.TOOLS["get_transactions"]["fn"]
    other = fn(transaction_id="TX2001", user_id="cliente1988")
    missing = fn(transaction_id="TX9999", user_id="cliente1988")
    assert other == missing == {"ok": False, "error": "not_found"}
    assert d.TOOLS["get_terminal_status"]["fn"](terminal_id="T1988A", user_id="cliente2024") == missing
    assert "T1988" not in json.dumps(d.TOOLS["get_terminal_status"]["fn"](user_id="cliente2024"))


def test_settlements_totals_and_dates_computed(d):
    r = d.TOOLS["get_settlements"]["fn"](user_id="cliente1988")
    data = r["data"]
    assert data["total"] == 814.40 and data["count"] == 5  # 120 + 80,50 + 350 + 199,90 + 64
    by = {g["method"]: g for g in data["items"]}
    yesterday = date.today() - timedelta(days=1)
    assert by["pix"]["deposit_date"]["date"] == yesterday.isoformat()
    assert by["debito"]["total"] == 200.50 and date.fromisoformat(by["debito"]["deposit_date"]["date"]).weekday() < 5
    assert by["credito"]["total_brl"] == "R$ 549,90"
    assert by["credito"]["sale_date"]["relative_pt"] == "ontem"


def test_declines_with_meaning_and_needs(d):
    r = d.TOOLS["get_transactions"]["fn"](status="declined", user_id="cliente1988")
    items = {i["transaction_id"]: i for i in r["data"]["items"]}
    assert items["TX1007"]["decline_code"] == "51" and items["TX1007"]["amount_brl"] == "R$ 210,00"
    assert "insuficiente" in items["TX1007"]["decline_meaning"]["pt"]
    assert items["TX1008"]["decline_code"] == "05" and items["TX1008"]["amount"] == 75.0
    assert r["data"]["declined_count"] == 2 and r["data"]["declined_total"] == 285.0
    assert r["needs"][0]["agent"] == "faq"


def test_terminal_offline_emits_manual_need(d):
    r = d.TOOLS["get_terminal_status"]["fn"](user_id="cliente1988")
    assert r["data"]["offline"] == ["T1988B"] and r["needs"][0]["agent"] == "faq"
    assert "needs" not in d.TOOLS["get_terminal_status"]["fn"](terminal_id="T1988A", user_id="cliente1988")


def test_offline_records_language_and_needs(d):
    from app import agents

    res = d.records_offline(_ctx("My card machine won't connect to the internet, what should I do?", "en"), agents)
    assert "T1988B" in res.text and "is offline" in res.text and res.needs and res.needs[0]["agent"] == "faq"
    res = d.records_offline(_ctx("Apareceu código 51 numa venda minha, o que significa?"), agents)
    assert "TX1007" in res.text and "R$ 210,00" in res.text and "TX1008" not in res.text and res.needs
    res = d.records_offline(_ctx("When will the money from yesterday's sales be deposited?", "en"), agents)
    assert "R$ 814,40" in res.text and not res.needs and res.tool_calls[0].name == "get_settlements"


def test_offline_memory_other_terminal(d):
    from app import agents

    hist = [{"role": "user", "content": "My card machine won't connect"},
            {"role": "assistant", "content": "T1988B (Get Clássica, chip) is offline"}]
    res = d.records_offline(_ctx("And the other terminal?", "en", history=hist), agents)
    assert "T1988A" in res.text and "T1988B" not in res.text


def test_writes_stay_pending(d):
    from app import agents

    res = d.records_offline(_ctx("Quero antecipar meus recebíveis de crédito"), agents)
    assert res.pending_action and res.tool_calls[-1].name == "request_receivables_advance"
    res = d.records_offline(_ctx("Open a support ticket for my offline terminal", "en"), agents)
    assert res.pending_action and "T1988B" in res.text
