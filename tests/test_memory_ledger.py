"""Livro de fatos da conversa (app/memory.py): extração por código, sobrevivência ao resumo, base da checagem
numérica (só cliente e ferramenta, nunca o assistente), apagamento junto com a conversa e injeção no contexto."""
import json

from app import agents, memory, pipeline, supervisor
from app.agents import AgentResult, Context
from app.schemas import ChatRequest
from app.store import get_store

TX = json.dumps({"ok": True, "data": {"transactions": [
    {"transaction_id": "TX1008", "date": "2026-11-01", "amount": 75.0, "status": "recusada"},
    {"transaction_id": "TX1009", "date": "2026-11-01", "amount": 125.5, "status": "aprovada"}]}})


def _faq(answer, evidence=()):
    def run(ctx):
        return AgentResult("faq", "ok", text=answer, evidence=list(evidence))
    return run


def _say(monkeypatch, message, answer, evidence=(), conv=None, user="u1"):
    monkeypatch.setitem(supervisor.AGENTS, "faq", _faq(answer, evidence))
    return pipeline.handle(ChatRequest(message=message, conversation_id=conv), user)


# --- extração -------------------------------------------------------------------------------------------------------
def test_extracts_ids_money_dates_and_subject():
    ledger = memory.Ledger()
    said = "A venda TX1007 de R$ 300,00 em 01/11/2026 foi recusada na T1988A (caso T-f70e7d6e)"
    memory.update(ledger, user_text=said, intent="troubleshoot", evidence=[], states_subject=True)
    assert [f["v"] for f in ledger.of("id")] == ["TX1007", "T1988A", "T-f70e7d6e"]
    assert [f["v"] for f in ledger.of("money")] == ["R$ 300,00"]
    assert [f["v"] for f in ledger.of("date")] == ["01/11/2026"]
    assert ledger.subject["intent"] == "troubleshoot" and "TX1007" in ledger.subject["text"]
    text = ledger.render()
    assert text.startswith("Fatos da conversa") and "TX1007" in text and "R$ 300,00" in text


def test_lowercase_id_is_the_same_id_and_numbers_in_prose_are_not_ids():
    ledger = memory.Ledger()
    memory.extract_user(ledger, "o tx1007 e depois o TX1007; são 4g, 12 parcelas e 3 dias")
    assert [f["v"] for f in ledger.of("id")] == ["TX1007"]


def test_domain_can_extend_the_id_patterns(monkeypatch):
    from app import domain

    monkeypatch.setattr(domain.active(), "ID_PATTERNS", [r"\b(LJ-\d{2})\b"], raising=False)
    ledger = memory.Ledger()
    memory.extract_user(ledger, "loja LJ-42 sem sinal")
    assert [f["v"] for f in ledger.of("id")] == ["LJ-42"]


def test_tool_result_becomes_entities_with_masked_text_fields():
    ledger = memory.Ledger()
    memory.extract_evidence(ledger, [TX, json.dumps({"ok": True, "data": {"owner": "ana@loja.com", "id": "L9"}})])
    assert {e["v"] for e in ledger.of("entity")} >= {"TX1008", "TX1009", "L9"}
    tx = next(e for e in ledger.of("entity") if e["v"] == "TX1008")
    assert tx["f"]["amount"] == "75.0" and tx["s"] == "tool"
    assert "ana@loja.com" not in ledger.dumps()  # PII não vai para o livro


def test_failed_tool_result_adds_nothing():
    ledger = memory.Ledger()
    memory.extract_evidence(ledger, [json.dumps({"ok": False, "error": "not_found", "id": "X123"})])
    assert ledger.facts == []


def test_ledger_has_caps_and_corrupt_json_resets():
    ledger = memory.Ledger()
    for i in range(80):
        ledger.add("id", f"TX{1000 + i}", "user")
    ids = [f["v"] for f in ledger.of("id")]
    assert len(ids) == memory.CAPS["id"] and ids[-1] == "TX1079"  # o mais recente fica
    assert memory.Ledger.loads("{não é json").facts == [] and memory.Ledger.loads(None).turn == 0


# --- sobrevive ao resumo -------------------------------------------------------------------------------------------
def test_ledger_survives_a_long_conversation_that_the_digest_drops(monkeypatch):
    first = _say(monkeypatch, "Meu pedido 4521 de R$ 300,00 chegou?", "Sem informação.")
    conv = first.conversation_id
    for i in range(25):  # bem além da janela de 20 mensagens e dos 8 itens do resumo
        _say(monkeypatch, f"Tem o horário de atendimento {i}?", "Atendemos em horário comercial.", conv=conv)
    store = get_store()
    assert "4521" not in pipeline._digest(store, conv)  # o resumo por regra perdeu o id...
    ledger = memory.load(store, conv)
    kept = pipeline._digest(store, conv, ledger)  # ...e o livro o devolve ao resumo
    assert "ids 4521" in kept and "R$ 300,00" in kept and "assunto: Tem o horário de atendimento 24" in kept
    assert not any("4521" in m["content"] for m in store.history(conv, limit=pipeline.HISTORY_WINDOW))
    assert "4521" in [f["v"] for f in ledger.of("id")] and "R$ 300,00" in [f["v"] for f in ledger.of("money")]


def test_agents_get_the_ledger_even_when_a_llm_summary_drops_the_values():
    ledger = memory.Ledger()
    memory.update(ledger, user_text="Pedido 4521 de R$ 300,00", intent="records", evidence=[], states_subject=True)
    lossy_summary = "O cliente perguntou sobre uma entrega (resumo gerado sem os valores)."
    ctx = Context(text="E o valor?", language="pt", user_id="u1", conversation_id="c",
                  conversation_digest=lossy_summary, ledger=ledger.render())
    sent = agents.llm_history(ctx, ctx.text)[-1]["content"]
    assert "Fatos da conversa" in sent and "4521" in sent and "R$ 300,00" in sent and lossy_summary in sent


def test_ledger_is_persisted_per_conversation_and_backfilled_for_old_conversations(monkeypatch):
    r = _say(monkeypatch, "Meu pedido 4521 chegou?", "ok")
    store = get_store()
    assert json.loads(store.conversation_facts(r.conversation_id))["v"] == memory.LEDGER_VERSION
    # conversa anterior ao livro: só há mensagens; o livro é reconstruído das falas do CLIENTE
    store.add_message("velha", "u1", "user", "Pedido 7788 atrasou", "records")
    store.add_message("velha", "u1", "assistant", "Pedido 9999 foi enviado, R$ 11,11", "records")
    ledger = memory.load(store, "velha")
    assert [f["v"] for f in ledger.of("id")] == ["7788"] and not ledger.of("money")


def test_ledger_is_erased_with_the_conversation(monkeypatch):
    r = _say(monkeypatch, "Meu pedido 4521 chegou?", "ok")
    store = get_store()
    assert store.conversation_facts(r.conversation_id)
    counts = store.delete_conversation(r.conversation_id, "u1")
    assert counts["conversation_facts"] == 1 and store.conversation_facts(r.conversation_id) is None


def test_store_without_the_ledger_methods_still_works():
    class Bare:
        def older_messages(self, *a, **k):
            return [{"role": "user", "content": "pedido 4521", "intent": "faq"}]

    ledger = memory.load(Bare(), "c")
    assert [f["v"] for f in ledger.of("id")] == ["4521"]
    memory.save(Bare(), "c", ledger)  # sem método: não grava e não quebra


# --- base da checagem numérica: cliente e ferramenta sim, assistente não ---------------------------------------------
def _fill(monkeypatch, n=25):
    first = _say(monkeypatch, "Meu pedido custou R$ 777,00 e o código é 4521", "Entendi.")
    for i in range(n):
        _say(monkeypatch, f"Tem o horário de atendimento {i}?", "Atendemos em horário comercial.",
             conv=first.conversation_id)
    return first.conversation_id


def test_value_the_customer_said_long_ago_is_a_valid_basis(monkeypatch):
    conv = _fill(monkeypatch)
    r = _say(monkeypatch, "Qual foi o valor que informei?", "Você informou R$ 777,00 no início da conversa.", conv=conv)
    assert r.unsupported_numbers == [] and "777,00" in r.answer


def test_number_only_the_assistant_said_is_not_laundered(monkeypatch):
    first = _say(monkeypatch, "Quanto custa o frete?", "O frete custa R$ 49,90.", evidence=["Frete: R$ 59,90."])
    assert first.unsupported_numbers == ["49,90"]  # redigido no turno 1
    store = get_store()
    store.add_message(first.conversation_id, "u1", "assistant", "O frete custa R$ 49,90.", "faq")
    again = _say(monkeypatch, "E o frete mesmo?", "Como eu disse, R$ 49,90.", conv=first.conversation_id)
    assert again.unsupported_numbers == ["49,90"] and "49,90" not in again.answer
    assert "49,90" not in memory.load(store, first.conversation_id).known_text()


def test_tool_value_from_an_earlier_turn_is_a_valid_basis_in_that_conversation_only(monkeypatch):
    first = _say(monkeypatch, "Mostre minhas vendas", "Você teve 2 vendas.", evidence=[TX])
    conv = first.conversation_id
    later = _say(monkeypatch, "E o valor da primeira?", "A TX1008 foi de R$ 75,00.", conv=conv)
    assert later.unsupported_numbers == []
    other = _say(monkeypatch, "E o valor da primeira?", "A TX1008 foi de R$ 75,00.")  # outra conversa
    assert other.unsupported_numbers == ["75,00"]


def test_number_in_a_cited_source_url_is_not_flagged(monkeypatch):
    from app.schemas import Source

    def run(ctx):
        return AgentResult("faq", "ok", text="Veja https://prev.example.com/cidade/4106902 para o tempo.",
                           sources=[Source(id="u", title="Previsão", url="https://prev.example.com/cidade/4106902")],
                           evidence=["Previsão (0 days ago)"])

    monkeypatch.setitem(supervisor.AGENTS, "faq", run)
    r = pipeline.handle(ChatRequest(message="Como está o tempo?"), "u1")
    assert r.unsupported_numbers == []


# --- soma e contagem em código ---------------------------------------------------------------------------------------
def test_aggregates_count_sum_and_group_by_status():
    out = memory.with_aggregates(json.loads(TX))
    calc = out["calculado_em_codigo"][0]
    assert calc["lista"] == "transactions" and calc["itens"] == 2 and calc["soma"] == {"amount": 200.5}
    assert calc["por_status"]["recusada"] == {"itens": 1, "soma": {"amount": 75}}
    assert calc["por_status"]["aprovada"]["soma"] == {"amount": 125.5}


def test_aggregates_use_exact_decimal_arithmetic_and_skip_non_amount_columns():
    rows = [{"id": f"v{i}", "amount": 0.1, "decline_code": "05", "installments": 3} for i in range(10)]
    calc = memory.aggregates({"ok": True, "data": {"sales": rows}})[0]
    assert calc["soma"] == {"amount": 1} and calc["itens"] == 10  # 0.1 x 10 = 1 (float daria 0.9999999999999999)
    only = memory.aggregates({"ok": True, "data": [{"id": "a", "installments": 3}, {"id": "b", "installments": 2}]})[0]
    assert "soma" not in only and only["itens"] == 2


def test_result_without_lists_or_with_error_is_unchanged():
    ok = {"ok": True, "data": {"status": "enviado"}}
    assert memory.with_aggregates(ok) == ok
    err = {"ok": False, "error": "not_found"}
    assert memory.with_aggregates(err) is err


def test_writer_receives_the_totals_computed_in_code(monkeypatch):
    from fakes import fake_llm, resp, text, tool_use

    result = {"ok": True, "data": {"transactions": json.loads(TX)["data"]["transactions"]}}
    monkeypatch.setattr(agents, "run_tool", lambda name, args, user, conv: (result, agents.ToolCall(
        name=name, args=args, ok=True)))
    llm, msgs = fake_llm([resp("tool_use", tool_use("lookup_record", {"record_id": "1001"})),
                          resp("end_turn", text("O total é R$ 200,50 em 2 vendas."))], effort="medium")
    monkeypatch.setattr(agents, "get_llm", lambda role="agent": llm)
    r = agents.records_agent(Context(text="Quanto vendi?", language="pt", user_id="u1", conversation_id="c"))
    sent = json.loads(msgs.sent[1]["messages"][-1]["content"][0]["content"])
    assert sent["calculado_em_codigo"][0]["soma"] == {"amount": 200.5}
    from app.grounding import unsupported_numbers

    assert unsupported_numbers(r.text, r.evidence) == []  # o total calculado em código é evidência


# --- eval: fato esperado ---------------------------------------------------------------------------------------------
def test_fact_present_compares_numbers_by_value_and_ids_by_text():
    assert memory.fact_present("R$ 75,00", "A venda foi de 75.0 reais")
    assert memory.fact_present("TX1007", "sobre a tx1007, recusada")
    assert not memory.fact_present("R$ 75,00", "A venda foi de R$ 750,00")
    assert not memory.fact_present("TX1007", "sobre a TX1008")


def test_aggregates_sum_by_date_across_methods():
    """Total por data de depósito vem do código (o redator somava débito + Pix do mesmo dia)."""
    from app.memory import aggregates
    rows = [{"method": "debito", "amount": 120.0, "expected_date": "2026-11-03"},
            {"method": "credito", "amount": 480.0, "expected_date": "2026-12-01"},
            {"method": "debito", "amount": 85.5, "expected_date": "2026-11-03"},
            {"method": "pix", "amount": 60.0, "expected_date": "2026-11-03"}]
    calc = aggregates({"items": rows})[0]
    assert calc["por_expected_date"]["2026-11-03"]["soma"]["amount"] == 265.5
    assert "por_method" in calc


# --- seguimento sem tool no turno (ensaio v5.3, q-memory-08/09: "E qual foi o valor dela?") -------------------------
LEDGER = ("Fatos da conversa:\n- IDs citados pelo cliente: TX1006\n- Registros vistos nas ferramentas: TX1006 "
          "{method=credito, amount=900.00, amount_brl=R$ 900,00, status=aprovada}")


def test_records_without_tool_call_is_asked_once_to_look_it_up(monkeypatch):
    from fakes import fake_llm, resp, text, tool_use

    result = {"ok": True, "data": {"transaction_id": "TX1006", "amount_brl": "R$ 900,00"}}
    monkeypatch.setattr(agents, "run_tool", lambda name, args, user, conv: (result, agents.ToolCall(
        name=name, args=args, ok=True)))
    llm, msgs = fake_llm([resp("end_turn", text("A TX1006 foi de R$ 900,00.")),
                          resp("tool_use", tool_use("lookup_record", {"record_id": "TX1006"})),
                          resp("end_turn", text("A TX1006 foi de R$ 900,00."))], effort="medium")
    monkeypatch.setattr(agents, "get_llm", lambda role="agent": llm)
    r = agents.records_agent(Context(text="E qual foi o valor dela?", language="pt", user_id="u1",
                                     conversation_id="c-nudge", ledger=LEDGER))
    assert r.status == "ok" and [c.name for c in r.tool_calls] == ["lookup_record"]
    assert "Consulte agora" in msgs.sent[1]["messages"][-1]["content"]


def test_records_answer_backed_only_by_the_ledger_is_an_answer(monkeypatch):
    from fakes import fake_llm, resp, text

    llm, _ = fake_llm([resp("end_turn", text("A TX1006 foi de R$ 900,00.")),
                       resp("end_turn", text("A TX1006 foi de R$ 900,00."))], effort="medium")
    monkeypatch.setattr(agents, "get_llm", lambda role="agent": llm)
    r = agents.records_agent(Context(text="E qual foi o valor dela?", language="pt", user_id="u1",
                                     conversation_id="c-ledger", ledger=LEDGER))
    assert r.status == "ok" and r.reason is None and r.facts["from_memory"] is True
    assert "R$ 900,00" in r.evidence[0]


def test_records_value_not_in_the_ledger_stays_no_data(monkeypatch):
    from fakes import fake_llm, resp, text

    llm, _ = fake_llm([resp("end_turn", text("A TX1006 foi de R$ 950,00.")),
                       resp("end_turn", text("A TX1006 foi de R$ 950,00."))], effort="medium")
    monkeypatch.setattr(agents, "get_llm", lambda role="agent": llm)
    r = agents.records_agent(Context(text="E qual foi o valor dela?", language="pt", user_id="u1",
                                     conversation_id="c-inv", ledger=LEDGER))
    assert r.status == "insufficient" and r.reason == "no_data"  # número inventado não vira resposta
