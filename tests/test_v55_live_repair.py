"""v5.5.1: a resposta de clima/câmbio traz os valores obrigatórios que a consulta trouxe; o código confere.

R12-E: a consulta é a tool que o modelo chamou e a redação é a volta seguinte do loop; o reparo único vale igual."""
from __future__ import annotations

from fakes import fake_llm, resp, text, tool_use

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


def _run(monkeypatch, replies):
    """Turno de clima com LLM falso: o modelo chama `weather_forecast`, a consulta (trocada) devolve `_weather()` e
    `replies` são as redações do modelo, na ordem. Devolve o resultado e os pedidos enviados ao LLM."""
    monkeypatch.setenv("LIVE_DATA", "on")
    monkeypatch.setattr(live_data, "forecast", lambda city, offset=0: (_weather(), "ok"))
    script = [resp("tool_use", tool_use("weather_forecast", {"city": "Porto Alegre", "day": "amanhã"}))]
    llm, msgs = fake_llm(script + [resp("end_turn", text(r)) for r in replies])
    monkeypatch.setattr(agents, "get_llm", lambda role="agent": llm)
    ctx = Context(user_id="u1", conversation_id="c1", text="What's the weather in Porto Alegre tomorrow?",
                  language="en", intent="general")
    return agents.faq_agent(ctx), msgs.sent


def test_incomplete_answer_is_redone_once_with_what_was_missing(monkeypatch):
    out, sent = _run(monkeypatch, ["Low 19 °C, high 24 °C.", "Low 19 °C, high 24 °C, 81% chance of rain."])
    assert out.text.endswith("81% chance of rain.") and out.facts["live_repair"] == "llm" and len(sent) == 3
    assert "the chance of rain" in str(sent[2]["messages"][-1]["content"])  # o pedido diz o que faltou


def test_still_incomplete_falls_back_to_the_lookup_text(monkeypatch):
    out, _ = _run(monkeypatch, ["Low 19 °C, high 24 °C.", "It will be mild tomorrow."])
    assert out.text == _weather().text_en and out.facts["live_repair"] == "template"


def test_complete_answer_needs_no_repair_call(monkeypatch):
    out, sent = _run(monkeypatch, ["Low 19 °C, high 24 °C, up to 81% chance of rain (wttr.in, 2026-11-04)."])
    assert len(sent) == 2 and "live_repair" not in out.facts  # a escolha da tool e a redação, nada mais


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


def test_claims_cut_that_takes_a_live_value_is_detected():
    """A checagem de frases tirou a frase "78% de chuva, leve guarda-chuva": o valor obrigatório saiu junto."""
    from app.pipeline import _lost_live_values
    from app.supervisor import Outcome

    r = agents.AgentResult("faq", "ok", text="Low 19 °C, high 24 °C, up to 81% chance of rain.")
    r.live_must = _weather().must
    out = Outcome(engine="llm")
    out.results = [r]
    before = "Low 19 °C and high 24 °C. Up to 81% chance of rain, so take an umbrella."
    assert _lost_live_values(before, "Low 19 °C and high 24 °C.", out, "en")
    assert not _lost_live_values(before, before, out, "en")
    assert not _lost_live_values("Low 19 °C.", "Low 19 °C.", out, "en")  # já faltava antes: não foi a checagem
