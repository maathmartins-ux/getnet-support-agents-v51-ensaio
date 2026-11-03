"""Chamada lenta ao LLM é repetida uma vez (a cauda do p95 vinha de chamadas isoladas de 19–46 s)."""
import anthropic
import httpx

from app.llm import AnthropicLLM


class _Messages:
    def __init__(self, owner, slow):
        self.owner, self.slow = owner, slow

    def create(self, **kwargs):
        self.owner.calls.append(self.slow)
        if self.slow:
            raise anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
        return "ok"


class _Client:
    def __init__(self):
        self.calls: list[bool] = []
        self.messages = _Messages(self, slow=False)
        self.timeouts: list[float] = []

    def with_options(self, timeout, max_retries):
        self.timeouts.append(timeout)
        c = _Client.__new__(_Client)
        c.calls, c.timeouts = self.calls, self.timeouts
        c.messages = _Messages(self, slow=True)
        return c


def test_slow_first_attempt_is_retried_with_the_full_timeout(monkeypatch):
    monkeypatch.setenv("LLM_FIRST_TIMEOUT_S", "15")
    client = _Client()
    llm = AnthropicLLM("claude-sonnet-5-5", "low", client=client)
    assert llm._hedged(anthropic, model="m", messages=[]) == "ok"
    assert client.calls == [True, False] and client.timeouts == [15.0]


def test_web_search_gets_a_longer_first_deadline_and_zero_disables(monkeypatch):
    monkeypatch.setenv("LLM_FIRST_TIMEOUT_S", "15")
    client = _Client()
    llm = AnthropicLLM("claude-sonnet-5-5", "low", client=client)
    llm._hedged(anthropic, model="m", messages=[], tools=[{"type": "web_search_20250305"}])
    assert client.timeouts == [30.0]
    monkeypatch.setenv("LLM_FIRST_TIMEOUT_S", "0")
    client2 = _Client()
    AnthropicLLM("claude-sonnet-5-5", "low", client=client2)._hedged(anthropic, model="m", messages=[])
    assert client2.calls == [False] and client2.timeouts == []


def test_llm_span_names_the_role_and_marks_the_hedged_call(monkeypatch, caplog):
    """A latência por papel sai do log: o span `llm` leva o papel e diz quando a 2ª tentativa entrou."""
    import logging
    from types import SimpleNamespace

    monkeypatch.setenv("LLM_FIRST_TIMEOUT_S", "15")
    client = _Client()
    llm = AnthropicLLM("claude-sonnet-5-5", "low", client=client)
    llm.role = "claims"
    resp = SimpleNamespace(stop_reason="end_turn", content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    client.messages = SimpleNamespace(create=lambda **kw: resp)
    with caplog.at_level(logging.INFO, logger="app"):
        llm._api(messages=[], max_tokens=10, system="s")
    spans = [getattr(r, "extra_fields", {}) for r in caplog.records]
    llm_spans = [s for s in spans if s.get("span") == "llm"]
    assert llm_spans and llm_spans[-1]["role"] == "claims" and llm_spans[-1].get("hedged") is True


def test_thinking_off_is_per_role_and_never_sends_a_combination_the_api_rejects(monkeypatch):
    """CLAIMS_THINKING=off etc.: Haiku 5.5 usa disabled, Sonnet 5.5 between_tools, Opus 5.5 e xhigh/max nada (400)."""
    from types import SimpleNamespace

    from app import llm as llm_mod
    from app.config import thinking_for, thinking_param

    assert thinking_for("claims") == "adaptive"  # padrão: medido, desligar mudou o veredito (changelog da frente L)
    monkeypatch.setenv("CLAIMS_THINKING", "off")
    assert thinking_for("claims") == "off"
    assert thinking_param("claude-haiku-5-5", "off", "low") == {"type": "disabled"}
    assert thinking_param("claude-sonnet-5-5", "off", "medium") == {"type": "between_tools"}
    assert thinking_param("claude-opus-5-5", "off", "low") is None
    assert thinking_param("claude-haiku-5-5", "off", "xhigh") is None
    assert thinking_param("claude-haiku-5-5", "adaptive", "low") is None

    sent = {}
    resp = SimpleNamespace(stop_reason="end_turn", content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: sent.update(kw) or resp))
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_mod, "_anthropic", lambda m, e: AnthropicLLM(m, e, client=client))
    llm_mod.get_llm("claims").complete("s", [{"role": "user", "content": "x"}])
    assert sent["thinking"] == {"type": "disabled"} and sent["output_config"] == {"effort": "low"}
    sent.clear()
    llm_mod.get_llm("router").complete("s", [{"role": "user", "content": "x"}])
    assert "thinking" not in sent  # papel sem a variável: padrão do modelo
