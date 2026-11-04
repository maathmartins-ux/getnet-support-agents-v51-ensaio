"""R12-E: câmbio e clima são tools que o MODELO escolhe (`currency_rate`, `weather_forecast`, a busca web ou nenhuma).

Antes, clima e câmbio eram escolhidos por um detector regex no código, não por uma tool call do modelo, e o detector
errava: no ensaio, "quanto ta a libra hoje" e "weather like in Recife right now" foram à
busca web e saíram sem o dado; "Bitcoin to US dollar" virou a PTAX do dólar. Aqui, com LLM falso e a rede trocada:
o modelo chama a tool → a API recebe os parâmetros DELE e a resposta traz os valores; o modelo vai à busca web →
nenhuma API ao vivo; entrada inválida → tool_result de erro; sem LLM, o detector por regex segue igual (texto pronto).
"""
from datetime import datetime, timedelta
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

import pytest
from fakes import fake_llm, resp, text, tool_use

from app import agents, clock, domain, live_data, supervisor
from app.agents import Context
from app.grounding import unsupported_numbers
from app.llm import LLMError
from app.schemas import ToolCall

PTAX_ROWS = {"value": [
    {"cotacaoCompra": 6.0270, "cotacaoVenda": 6.0275, "dataHoraCotacao": "2026-10-30 13:06:00.0",
     "tipoBoletim": "Fechamento PTAX"},
]}
GEO = {"results": [{"name": "Porto Alegre", "admin1": "Rio Grande do Sul", "country": "Brasil", "latitude": -30.03,
                    "longitude": -51.23, "timezone": "America/Sao_Paulo"}]}
FORECAST = {"daily": {"time": ["2026-11-05"], "temperature_2m_max": [31.4], "temperature_2m_min": [19.6],
                      "precipitation_probability_max": [60], "weather_code": [95]}}


@pytest.fixture(autouse=True)
def live_on(monkeypatch):
    monkeypatch.setenv("LIVE_DATA", "on")


def fake_api(monkeypatch) -> list:
    calls: list = []

    def get(url, params):
        calls.append((url, dict(params)))
        return PTAX_ROWS if url == live_data.PTAX else GEO if url == live_data.GEOCODING else FORECAST

    monkeypatch.setattr(live_data, "_get_json", get)
    return calls


def no_api(monkeypatch) -> None:
    def boom(url, params):
        raise AssertionError(f"API ao vivo chamada sem o modelo pedir: {url}")

    monkeypatch.setattr(live_data, "_get_json", boom)


def ask(monkeypatch, script, question, language="pt", history=None):
    llm, msgs = fake_llm(script)
    monkeypatch.setattr(agents, "get_llm", lambda role="agent": llm)
    ctx = Context(text=question, language=language, user_id="u1", conversation_id="c-r12e", intent="general",
                  history=history or [])
    return agents.faq_agent(ctx), msgs.sent


def tool_results(request: dict) -> list[dict]:
    return [b for b in request["messages"][-1]["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]


def web_reply(query: str, answer: str):
    search = NS(type="server_tool_use", id="srv1", name="web_search", input={"query": query})
    results = NS(type="web_search_tool_result", tool_use_id="srv1", content=[NS(
        type="web_search_result", url="https://www.bcb.gov.br/copom", title="Copom", page_age="4 de novembro de 2026",
        encrypted_content="opaco")])
    cited = NS(type="text", text=answer, citations=[NS(
        type="web_search_result_location", url="https://www.bcb.gov.br/copom", title="Copom",
        cited_text="O Copom anuncia a decisão da Selic nesta quarta", encrypted_index="opaco")])
    return search, results, cited


# --- o modelo escolhe a tool; a API recebe os parâmetros dele ---------------------------------------------------------
def test_model_picks_the_fx_tool_and_the_api_gets_its_parameters(monkeypatch):
    calls = fake_api(monkeypatch)
    question = "Quanto valia o euro em 30/10?"
    answer = "Na PTAX de 30/10/2026 (fechamento), 1 EUR valia R$ 6,0270 na compra e R$ 6,0275 na venda."
    r, sent = ask(monkeypatch, [resp("tool_use", tool_use("currency_rate", {"currency": "EUR", "date": "2026-10-30"})),
                                resp("end_turn", text(answer))], question)
    assert [t["name"] for t in sent[0]["tools"]] == ["currency_rate", "weather_forecast", "web_search"]
    [(url, params)] = calls
    assert url == live_data.PTAX and params["@moeda"] == "'EUR'" and params["@dataFinalCotacao"] == "'10-30-2026'"
    [result] = tool_results(sent[1])  # o texto bruto da API volta como tool_result, em moldura de dado
    assert result["is_error"] is False and result["content"].startswith("<untrusted_content>")
    assert "cotacaoVenda 6.0275" in result["content"]
    assert r.text == answer and r.facts["live_tool"] == "currency_rate" and r.facts["live_data"] == "fx"
    assert r.tool_calls == [ToolCall(name="currency_rate", args={"currency": "EUR", "date": "2026-10-30"}, ok=True)]
    assert [s.title for s in r.sources] == ["Banco Central do Brasil (PTAX)"]
    assert unsupported_numbers(r.text, r.evidence, question) == []
    assert agents.live_missing(r.text, r.live_must, "pt") == []
    # o caminho do caso (árvore de passos) mostra a tool que o modelo escolheu
    assert supervisor.step_view(r)["tools"] == [{"name": "currency_rate",
                                                 "args": {"currency": "EUR", "date": "2026-10-30"}, "ok": True}]


def test_supervisor_step_shows_the_tool_the_agent_model_chose(monkeypatch):
    """Pelo caminho que o eval grava: o supervisor LLM chama o faq_agent (tool call dele) e o passo traz a tool que
    o modelo do agente escolheu; a resposta final do supervisor é conferida contra `live_must`."""
    from app.observability import new_trace_id

    new_trace_id()
    fake_api(monkeypatch)
    answer = "Na PTAX de 30/10/2026, 1 EUR valia R$ 6,0270 na compra e R$ 6,0275 na venda (Banco Central)."
    sup, _ = fake_llm([resp("tool_use", tool_use("faq_agent", {"query": "cotação do euro"})),
                       resp("end_turn", text(answer))])
    agent, _ = fake_llm([resp("tool_use", tool_use("currency_rate", {"currency": "EUR"})),
                         resp("end_turn", text(answer))])
    monkeypatch.setattr(supervisor, "get_llm", lambda role="agent": sup)
    monkeypatch.setattr(agents, "get_llm", lambda role="agent": agent)
    monkeypatch.setenv("SUPERVISOR_FAST", "off")
    out = supervisor.run(["faq"], Context(text="Quanto está o euro?", language="pt", user_id="u1",
                                          conversation_id="c-r12e-sup", intent="general"))
    view = supervisor.step_view(out.results[0])
    assert view["decided_by"] == supervisor.DECIDED_LLM
    assert view["tools"] == [{"name": "currency_rate", "args": {"currency": "EUR"}, "ok": True}]
    assert out.answer == answer and agents.live_missing(out.answer, out.results[0].live_must, "pt") == []


def test_model_picks_the_weather_tool_with_its_city_and_day(monkeypatch):
    calls = fake_api(monkeypatch)
    answer = ("Amanhã em Porto Alegre: mínima de 19,6 °C, máxima de 31,4 °C e até 60% de chance de chuva "
              "(Open-Meteo, 05/11/2026).")
    r, _ = ask(monkeypatch, [resp("tool_use", tool_use("weather_forecast", {"city": "Porto Alegre", "day": "amanhã"})),
                             resp("end_turn", text(answer))], "Vai chover amanhã em POA?")
    assert next(p for u, p in calls if u == live_data.GEOCODING)["name"] == "Porto Alegre"
    tomorrow = (datetime.now(ZoneInfo("America/Sao_Paulo")).date() + timedelta(days=1)).isoformat()
    assert next(p for u, p in calls if u == live_data.FORECAST)["start_date"] == tomorrow  # o dia que o modelo pediu
    assert r.text == answer and r.facts["live_tool"] == "weather_forecast" and r.facts["live_data"] == "weather"
    assert r.tool_calls[0].args == {"city": "Porto Alegre", "day": "amanhã"}
    assert agents.live_missing(r.text, r.live_must, "pt") == []


def test_web_search_for_something_else_runs_no_live_api(monkeypatch):
    """Notícia: o modelo vai à busca web e nenhuma API de câmbio/clima roda."""
    no_api(monkeypatch)
    r, sent = ask(monkeypatch, [resp("end_turn", *web_reply("decisão Copom Selic hoje", "O Copom decide a Selic "
                                                                                         "hoje (Banco Central)."))],
                  "Saiu a decisão da Selic hoje?")
    assert {t["name"] for t in sent[0]["tools"]} == {"currency_rate", "weather_forecast", "web_search"}
    assert r.facts == {"web_search": True, "live_tool": "web_search"} and getattr(r, "live_must", None) is None
    assert r.tool_calls == [ToolCall(name="web_search", args={"query": "decisão Copom Selic hoje"}, ok=True)]
    assert [s.url for s in r.sources] == ["https://www.bcb.gov.br/copom"]


def test_the_regex_detector_is_not_forced_when_the_model_chooses(monkeypatch):
    """"Bitcoin to US dollar": o detector casava "dollar" e respondia a PTAX do dólar (ensaio, rodada 11). Com LLM
    vale a escolha do modelo (aqui, a busca web), e o detector nem roda."""
    no_api(monkeypatch)
    monkeypatch.setattr(live_data, "lookup", lambda *a, **k: pytest.fail("detector por regex no modo LLM"))
    r, _ = ask(monkeypatch, [resp("end_turn", *web_reply("bitcoin dólar cotação", "Não achei a cotação agora."))],
               "What is the current Bitcoin to US dollar exchange rate?", language="en")
    assert r.facts["live_tool"] == "web_search" and "live_data" not in r.facts


def test_answer_without_tool_calls_no_api(monkeypatch):
    no_api(monkeypatch)
    r, _ = ask(monkeypatch, [resp("end_turn", text("Este atendimento cobre clima, câmbio e notícias; posso ajudar?"))],
               "Me passa uma receita de bolo?")
    assert r.facts == {"web_search": False, "live_tool": "none"} and r.tool_calls == [] and r.evidence == []


def test_pause_turn_resends_the_turn_without_a_new_user_message(monkeypatch):
    no_api(monkeypatch)
    search, results, cited = web_reply("q", "O Copom decide hoje.")
    r, sent = ask(monkeypatch, [resp("pause_turn", search), resp("end_turn", results, cited)], "E a Selic?")
    assert len(sent) == 2 and sent[1]["messages"][-1] == {"role": "assistant", "content": [search]}
    assert r.tool_calls == [ToolCall(name="web_search", args={"query": "q"}, ok=True)]


# --- entrada validada no servidor -------------------------------------------------------------------------------------
@pytest.mark.parametrize("name,args,why", [
    ("currency_rate", {"currency": "BTC"}, "currency deve ser um destes"),
    ("currency_rate", {"currency": "USD", "date": "30/10/2026"}, "AAAA-MM-DD"),
    ("currency_rate", {"currency": "USD", "date": "FUTURE"}, "date no futuro"),
    ("currency_rate", {"currency": "USD", "rate": 5}, "campo fora do schema: rate"),
    ("weather_forecast", {"city": "   "}, "city vazia"),
    ("weather_forecast", {"city": "Rio " * 30}, "mais de 80 caracteres"),
    ("weather_forecast", {"city": "Recife?format=j1"}, "só com letras"),
    ("weather_forecast", {"city": "Recife", "day": "semana que vem"}, "day deve ser um destes"),
    ("send_email", {"to": "x"}, "tool desconhecida"),
])
def test_invalid_input_is_an_error_tool_result_and_calls_no_api(monkeypatch, name, args, why):
    no_api(monkeypatch)
    if args.get("date") == "FUTURE":
        args = {**args, "date": (clock.today() + timedelta(days=3)).isoformat()}
    r, sent = ask(monkeypatch, [resp("tool_use", tool_use(name, args)),
                                resp("end_turn", text("Não consegui o dado agora; consulte a fonte oficial."))],
                  "Quanto está?")
    [result] = tool_results(sent[1])
    assert result["is_error"] is True and why in result["content"]
    assert [(c.name, c.ok) for c in r.tool_calls] == [(name, False)] and r.facts["live_tool"] == name
    assert getattr(r, "live_must", None) is None


def test_arguments_are_normalized_before_the_api():
    assert agents.live_args("currency_rate", {"currency": " eur "}) == {"currency": "EUR"}
    assert agents.live_args("weather_forecast", {"city": "Porto  Alegre, RS", "day": "Amanha"}) == {
        "city": "Porto Alegre", "day": "amanhã"}
    assert agents.live_args("weather_forecast", {"city": "St. John's", "day": "tomorrow"}) == {
        "city": "St. John's", "day": "amanhã"}
    assert agents.live_args("weather_forecast", {"city": "São Paulo"}) == {"city": "São Paulo", "day": "hoje"}
    # o que o modelo às vezes manda no lugar: "hoje" como data (= omitida) e a data ISO como dia
    assert agents.live_args("currency_rate", {"currency": "USD", "date": "today"}) == {"currency": "USD"}
    after = (clock.today() + timedelta(days=2)).isoformat()
    assert agents.live_args("weather_forecast", {"city": "Recife", "day": after})["day"] == "depois de amanhã"


def test_api_failure_goes_back_to_the_model_as_an_error(monkeypatch):
    def down(url, params):
        raise TimeoutError("sem rede")

    monkeypatch.setattr(live_data, "_get_json", down)
    r, sent = ask(monkeypatch, [resp("tool_use", tool_use("currency_rate", {"currency": "USD"})),
                                resp("end_turn", text("Não consegui a cotação agora; consulte o Banco Central."))],
                  "Quanto está o dólar?")
    [result] = tool_results(sent[1])
    assert result["is_error"] is True and "não respondeu a tempo" in result["content"]
    assert r.tool_calls == [ToolCall(name="currency_rate", args={"currency": "USD"}, ok=False)]


def test_live_calls_per_turn_are_capped(monkeypatch):
    fake_api(monkeypatch)
    codes = ["USD", "EUR", "GBP", "JPY"]
    many = [tool_use("currency_rate", {"currency": c}, bid=f"tu{i}") for i, c in enumerate(codes)]
    r, sent = ask(monkeypatch, [resp("tool_use", *many),
                                resp("end_turn", text("PTAX de 30/10/2026: R$ 6,0270 na compra e R$ 6,0275 na venda "
                                                      "para dólar, euro e libra."))], "Dólar, euro, libra e iene?")
    results = tool_results(sent[1])
    assert [x["is_error"] for x in results] == [False, False, False, True]
    assert f"limite de {agents.MAX_LIVE_CALLS} consultas" in results[-1]["content"]
    assert [c.ok for c in r.tool_calls] == [True, True, True, False] and len(r.live_must) == 6


def test_tool_names_do_not_read_as_a_write_action():
    """O verificador de ação alegada conta tool executada com "change" no nome como escrita: uma `exchange_rate`
    liberaria "atualizei"/"bloqueei" no mesmo turno. Por isso a tool de câmbio é `currency_rate`."""
    from app.grounding import claimed_actions

    said = "Atualizei seu cadastro e bloqueei a maquininha."
    assert claimed_actions(said, [ToolCall(name="exchange_rate", ok=True)], False, []) == []  # o defeito evitado
    for tool in (*agents.LIVE_TOOLS, agents.WEB_SEARCH):
        assert claimed_actions(said, [ToolCall(name=tool["name"], ok=True)], False, []) == ["Atualizei", "bloqueei"]


def test_two_lookups_label_the_missing_value_with_its_subject():
    usd = live_data.LiveResult("fx", "BCB", "u", "2026-11-03", "t", "t", subject="USD",
                               must=[("a venda", "the sell rate", 5.43, 0.0051)])
    eur = live_data.LiveResult("fx", "BCB", "u", "2026-11-03", "t", "t", subject="EUR",
                               must=[("a venda", "the sell rate", 6.14, 0.0051)])
    assert agents.live_missing("Venda R$ 5,43.", agents.live_musts([usd, eur]), "pt") == ["a venda (EUR)"]
    assert agents.live_musts([usd]) == usd.must  # uma consulta só: o rótulo de sempre


# --- sem LLM (offline ou queda): o detector por regex decide ----------------------------------------------------------
def test_without_llm_the_regex_detector_still_decides(monkeypatch):
    calls = fake_api(monkeypatch)
    ctx = Context(text="Qual a cotação do euro hoje?", language="pt", user_id="u1", conversation_id="c1",
                  intent="general")
    r = agents.faq_agent(ctx)  # LLM_PROVIDER=offline (conftest)
    want = live_data.lookup("Qual a cotação do euro hoje?")
    assert r.text == want.text_pt and r.facts == {"live_data": "fx", "web_search": False} and r.tool_calls == []
    assert r.live_must == want.must and calls[0][1]["@moeda"] == "'EUR'"
    followup = Context(text="E a do dólar?", language="pt", user_id="u1", conversation_id="c1", intent="general",
                       history=[{"role": "user", "content": "Qual a cotação do euro hoje?"},
                                {"role": "assistant", "content": want.text_pt}])
    calls.clear()
    assert agents.faq_agent(followup).facts["live_data"] == "fx" and calls[0][1]["@moeda"] == "'USD'"


def test_llm_down_after_the_tool_keeps_its_result_without_the_detector(monkeypatch):
    fake_api(monkeypatch)
    monkeypatch.setattr(live_data, "lookup", lambda *a, **k: pytest.fail("detector rodou com o dado da tool em mãos"))
    r, _ = ask(monkeypatch, [resp("tool_use", tool_use("weather_forecast", {"city": "Porto Alegre"})),
                             LLMError("api_status_529", "api_status")], "Como está o tempo em Porto Alegre?")
    assert r.text.startswith("Previsão para Porto Alegre") and r.facts["live_tool"] == "weather_forecast"
    assert r.tool_calls == [ToolCall(name="weather_forecast", args={"city": "Porto Alegre", "day": "hoje"}, ok=True)]
    assert agents.live_missing(r.text, r.live_must, "pt") == []


def test_llm_down_before_any_tool_falls_back_to_the_detector(monkeypatch):
    fake_api(monkeypatch)
    r, _ = ask(monkeypatch, [LLMError("api_status_529", "api_status")], "Qual a cotação do euro hoje?")
    assert r.facts == {"live_data": "fx", "web_search": False} and "PTAX" in r.text


# --- prompts ----------------------------------------------------------------------------------------------------------
def test_kit_prompt_lists_the_tools_and_a_domain_prompt_gets_the_contract(tmp_path, monkeypatch):
    kit = (domain.KIT_PROMPTS / "general.md").read_text(encoding="utf-8")
    assert all(t in kit for t in ("currency_rate", "weather_forecast", "web_search")) and "Regras do motor" not in kit
    # prompt de domínio antigo (só a busca web): o contrato do motor traz as tools e os valores obrigatórios
    (tmp_path / "general.md").write_text("Use a ferramenta web_search. Idioma {language}; hoje {today}.\n",
                                         encoding="utf-8")
    monkeypatch.setattr(domain.active(), "PROMPTS_DIR", tmp_path, raising=False)
    text_ = domain.prompt("general.md")
    assert "`currency_rate`" in text_ and "`weather_forecast`" in text_ and "chance de chuva" in text_
    assert text_.format(language="pt", today="2026-11-04")  # o contrato não traz chaves soltas
    assert not (domain.KIT_PROMPTS / "live_data.md").exists()  # a redação agora é a volta do loop de tools
