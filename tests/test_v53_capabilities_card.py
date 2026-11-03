"""Cartão de capacidades: regra do veredito humano e formato dos ids viram evidência (ensaio v5.3, split real)."""
from app import capabilities


def test_example_of_simple_patterns():
    assert capabilities.example_of(r"^T\d{4}[A-Z]$") == "T0000A"
    assert capabilities.example_of(r"^TX\d{4}$") == "TX0000"
    assert capabilities.example_of(r"^(a|b)+$") is None


def test_card_states_human_verdict_and_id_formats():
    tools = {"get_terminal_status": {"description": "status", "write": False, "input_schema": {
        "type": "object", "properties": {"terminal_id": {"type": "string", "pattern": r"^T\d{4}[A-Z]$",
                                                         "description": "Número da maquininha"}}}}}
    pt = capabilities.card("pt", tools=tools, extra=[])
    assert "liberação de valor retido) é de um atendente humano" in pt
    assert "terminal_id = Número da maquininha (ex.: T0000A)" in pt
    en = capabilities.card("en", tools=tools, extra=[])
    assert "belongs to a human agent" in en and "T0000A" in en
