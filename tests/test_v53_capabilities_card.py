"""Cartão de capacidades: regra do veredito humano e formato dos ids viram evidência (conferido no split real)."""
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


def test_card_lists_the_closed_values_each_tool_accepts():
    """O que a consulta aceita (período, status) vira evidência do turno: o juiz lê o cartão, não o schema da tool."""
    from app import capabilities

    tools = {
        "get_settlements": {"description": "Recebimentos do lojista", "input_schema": {"type": "object", "properties": {
            "period": {"type": "string", "enum": ["yesterday", "today", "last_7_days"], "description": "Período"},
            "method": {"type": "string"}}}},
        "get_transactions": {"description": "Vendas", "input_schema": {"type": "object", "properties": {
            "period": {"type": "string", "enum": ["yesterday", "today", "last_7_days"], "description": "Período"},
            "status": {"type": "string", "enum": ["approved", "declined"]}}}},
        "open_ticket": {"description": "Abre chamado", "write": True, "input_schema": {"type": "object", "properties": {
            "period": {"type": "string", "enum": ["now", "later"]}}}},
    }
    tools["get_transactions"]["input_schema"]["properties"]["period"]["default"] = "last_7_days"
    text = capabilities.card("pt", tools=tools, extra=[])
    line = next(ln for ln in text.splitlines() if ln.startswith("- Valores que as consultas"))
    assert "get_settlements — period: yesterday | today | last_7_days" in line
    assert "get_transactions — period (padrão last_7_days): yesterday | today | last_7_days; status: approved" in line
    assert "open_ticket — period: now | later" in line  # cada tool com a sua lista e o seu padrão
    assert "method" not in line  # parâmetro livre não entra
    assert "Values the lookups and actions accept" in capabilities.card("en", tools=tools, extra=[])
