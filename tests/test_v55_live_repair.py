"""v5.5.1: a resposta de clima/câmbio traz os valores obrigatórios que a consulta trouxe; o código confere."""
from __future__ import annotations

from app import agents, live_data
from app.agents import Context, live_missing


def _weather(rain=81):
    must = live_data.weather_must(19.4, 24.0, rain)
    return live_data.LiveResult("weather", "wttr.in", "https://wttr.in/", "2026-11-04",
                                "Previsão: mínima de 19 °C e máxima de 24 °C, chance de chuva de até 81%.",
                                "Forecast: low 19 °C, high 24 °C, up to 81% chance of rain.", must=must)


def test_missing_values_follow_the_rounding_the_prompt_allows():
    live = _weather()
    assert live_missing("Low of 19 °C and high of 24 °C, 81% chance of rain.", live, "en") == []
    assert live_missing("Low of 19 °C and high of 24 °C.", live, "en") == ["the chance of rain"]
    assert live_missing("Mínima de 19,4 °C e máxima de 24 °C.", live, "pt") == ["a chance de chuva"]
    assert live_missing("Sem números.", _weather(rain=None), "pt") == ["a mínima", "a máxima"]
    fx = live_data.LiveResult("fx", "BCB", "u", "2026-11-03", "t", "t",
                              must=[("a venda", "the sell rate", 5.4321, 0.0051),
                                    ("a compra", "the buy rate", 5.4315, 0.0051)])
    assert live_missing("Venda R$ 5,43 e compra R$ 5,43.", fx, "pt") == []
    assert live_missing("Venda R$ 5,43.", fx, "pt") == []  # o mesmo arredondado cobre as duas: tolerância
    assert live_missing("Venda R$ 5,50.", fx, "pt") == ["a venda", "a compra"]


class _LLM:
    enabled = True

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def complete(self, system, messages, max_tokens=1024):
        self.calls.append(messages[-1]["content"] if isinstance(messages, list) and messages else messages)
        return type("R", (), {"text": self.replies.pop(0)})()


def _run(monkeypatch, replies):
    llm = _LLM(replies)
    monkeypatch.setattr(agents, "get_llm", lambda role: llm)
    ctx = Context(user_id="u1", conversation_id="c1", text="What's the weather in Porto Alegre tomorrow?",
                  language="en")
    return agents._live(ctx, _weather()), llm


def test_incomplete_answer_is_redone_once_with_what_was_missing(monkeypatch):
    out, llm = _run(monkeypatch, ["Low 19 °C, high 24 °C.", "Low 19 °C, high 24 °C, 81% chance of rain."])
    assert out.text.endswith("81% chance of rain.") and out.facts["live_repair"] == "llm" and len(llm.calls) == 2
    assert "the chance of rain" in str(llm.calls[1])


def test_still_incomplete_falls_back_to_the_lookup_text(monkeypatch):
    out, _ = _run(monkeypatch, ["Low 19 °C, high 24 °C.", "It will be mild tomorrow."])
    assert out.text == _weather().text_en and out.facts["live_repair"] == "template"


def test_complete_answer_costs_one_call(monkeypatch):
    out, llm = _run(monkeypatch, ["Low 19 °C, high 24 °C, up to 81% chance of rain (wttr.in, 2026-11-04)."])
    assert len(llm.calls) == 1 and "live_repair" not in out.facts


def test_final_answer_that_drops_a_live_value_falls_back_to_the_specialist_text():
    """A redação do supervisor LLM não pode perder o valor que o especialista entregou conferido."""
    from app.pipeline import _drops_live_values
    from app.supervisor import Outcome

    live = _weather()
    ok = agents.AgentResult("faq", "ok", text="Low 19 °C, high 24 °C, up to 81% chance of rain.")
    ok.live_must = live.must
    out = Outcome(engine="llm")
    out.results, out.answer = [ok], "Tomorrow: low 19 °C and high 24 °C."
    assert _drops_live_values(out, "en")
    out.answer = "Tomorrow: low 19 °C, high 24 °C, 81% chance of rain."
    assert not _drops_live_values(out, "en")
    plain = agents.AgentResult("faq", "ok", text="Texto sem dado ao vivo.")
    out.results, out.answer = [plain], "Qualquer coisa."
    assert not _drops_live_values(out, "pt")  # sem live_must: nada a conferir
