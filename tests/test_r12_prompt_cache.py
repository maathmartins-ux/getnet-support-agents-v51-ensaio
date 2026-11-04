"""R12-H: cache de prompt nos pedidos ao LLM. Cada papel tem tools e system fixos, então a marca no fim do system
deixa tools + system no cache entre conversas; no laço de tool use, a marca automática no fim da conversa deixa
cada volta ler a anterior. O custo conta a escrita (1,25× a entrada) e a leitura (preço do modelo), e a chave do
cassete não muda (a gravação continua valendo no replay)."""
from types import SimpleNamespace as NS

import pytest
from fakes import fake_llm, resp, text

from app import llm as llm_mod
from app import observability
from app.observability import METRICS, llm_cost, new_trace_id, record_llm_usage, request_usage

SYSTEM = "Você é o supervisor. " * 40


def test_marks_go_on_the_system_end_and_on_the_conversation_end_only_in_the_tool_loop(monkeypatch):
    monkeypatch.delenv("LLM_PROMPT_CACHE", raising=False)
    loop = llm_mod.with_prompt_cache({"system": SYSTEM, "messages": [{"role": "user", "content": "oi"}],
                                      "tools": [{"name": "faq"}]})
    assert loop["system"] == [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]
    assert loop["cache_control"] == {"type": "ephemeral"}
    single = llm_mod.with_prompt_cache({"system": SYSTEM, "messages": [{"role": "user", "content": "oi"}]})
    assert single["system"][0]["cache_control"] == {"type": "ephemeral"} and "cache_control" not in single
    assert "system" not in llm_mod.with_prompt_cache({"messages": []})  # sem system, nada de bloco vazio
    assert llm_mod.with_prompt_cache({"system": " ", "messages": []})["system"] == " "
    monkeypatch.setenv("LLM_PROMPT_CACHE", "off")
    off = {"system": SYSTEM, "messages": [], "tools": [{"name": "faq"}]}
    assert llm_mod.with_prompt_cache(off) == off


def test_the_sdk_receives_the_marks_and_the_cassette_key_does_not_change(monkeypatch):
    monkeypatch.delenv("LLM_PROMPT_CACHE", raising=False)
    model, sent = fake_llm([resp("end_turn", text("ok")), resp("end_turn", text("ok")), resp("end_turn", text("ok"))])
    keys = []
    for flag in ("on", "off"):
        monkeypatch.setenv("LLM_PROMPT_CACHE", flag)
        rec = llm_mod.start_recording()
        try:
            model.create(SYSTEM, [{"role": "user", "content": "oi"}], [{"name": "faq", "input_schema": {}}])
        finally:
            llm_mod.stop_recording()
        keys.append(rec.entries[0]["key"])
    assert keys[0] == keys[1]  # a chave do cassete vem do pedido antes das marcas
    on, off = sent.sent
    assert on["system_raw"][0]["cache_control"] == {"type": "ephemeral"}
    assert on["cache_control"] == {"type": "ephemeral"} and on["system"] == SYSTEM  # o texto que o modelo lê
    assert off["system"] == SYSTEM and "cache_control" not in off and "system_raw" not in off
    monkeypatch.setenv("LLM_PROMPT_CACHE", "on")
    model.complete(SYSTEM, [{"role": "user", "content": "oi"}])
    assert "cache_control" not in sent.sent[-1] and sent.sent[-1]["system_raw"][0]["text"] == SYSTEM


def test_cost_counts_the_cache_write_premium_and_the_cheap_read():
    # Sonnet 5.5: 100 sem cache × 2 + 1000 escritos × 2 × 1,25 + 10 000 lidos × 0,20 + 50 de saída × 10 (por MTok)
    assert llm_cost("claude-sonnet-5-5", 100, 50, cache_write=1000, cache_read=10_000) == pytest.approx(0.0052)
    # Opus 5.5 lê a 0,05× (US$ 0,20/MTok); sem cache, a conta é a de sempre
    assert llm_cost("claude-opus-5-5", 0, 0, cache_read=1_000_000) == pytest.approx(0.20)
    assert llm_cost("claude-haiku-5-5", 1000, 100) == pytest.approx((1000 * 0.10 + 100 * 0.50) / 1e6)
    assert llm_cost("modelo-sem-preco", 1000, 100, cache_read=10) == 0.0


def test_usage_and_metrics_carry_the_cache_tokens_only_when_there_was_cache():
    new_trace_id()
    record_llm_usage("claude-sonnet-5-5", 100, 10)
    assert set(request_usage()) == {"input_tokens", "output_tokens", "cost_usd"}  # formato antigo sem cache
    before = METRICS.counters.get(("llm_tokens_total", (("kind", "cache_read"), ("model", "claude-sonnet-5-5"))), 0)
    record_llm_usage("claude-sonnet-5-5", 100, 10, cache_write=50, cache_read=900)
    usage = request_usage()
    assert (usage["cache_read_tokens"], usage["cache_write_tokens"]) == (900, 50)
    after = METRICS.counters.get(("llm_tokens_total", (("kind", "cache_read"), ("model", "claude-sonnet-5-5"))), 0)
    assert after - before == 900


def test_the_response_cache_fields_reach_the_cost():
    model, _ = fake_llm([NS(stop_reason="end_turn", content=[text("ok")],
                            usage=NS(input_tokens=10, output_tokens=5, cache_creation_input_tokens=0,
                                     cache_read_input_tokens=2000))])
    new_trace_id()
    model.complete(SYSTEM, [{"role": "user", "content": "oi"}])
    assert request_usage()["cache_read_tokens"] == 2000
    assert request_usage()["cost_usd"] == pytest.approx(round(llm_cost("claude-sonnet-5-5", 10, 5, 0, 2000), 6))
    assert observability.request_model_calls() >= 1
