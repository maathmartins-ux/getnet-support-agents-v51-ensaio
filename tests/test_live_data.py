"""Dado ao vivo resolvido no código (PTAX do Banco Central e Open-Meteo), com HTTP trocado por mock.

Pela busca web, que cifra o corpo da página, o número de clima ou câmbio não aparece na evidência e a checagem
numérica o acusa (numbers_acc ficava em 64-80% ao vivo). Aqui a resposta e a evidência vêm da mesma chamada de API,
então todo número da resposta tem base.
"""
from datetime import date

import pytest

from app import grounding, live_data

PTAX_ROWS = {"value": [
    {"cotacaoCompra": 6.0270, "cotacaoVenda": 6.0275, "dataHoraCotacao": "2026-10-30 13:06:00.0",
     "tipoBoletim": "Fechamento PTAX"},
    {"cotacaoCompra": 6.0100, "cotacaoVenda": 6.0105, "dataHoraCotacao": "2026-10-30 10:05:00.0",
     "tipoBoletim": "Abertura"},
]}
GEO = {"results": [{"name": "Porto Alegre", "admin1": "Rio Grande do Sul", "country": "Brasil", "latitude": -30.03,
                    "longitude": -51.23, "timezone": "America/Sao_Paulo"}]}
FORECAST = {"daily": {"time": ["2026-11-02"], "temperature_2m_max": [31.4], "temperature_2m_min": [19.6],
                      "precipitation_probability_max": [60], "weather_code": [95]}}


@pytest.fixture(autouse=True)
def live_on(monkeypatch):
    monkeypatch.setenv("LIVE_DATA", "on")


def fake_api(monkeypatch, calls=None):
    def get(url, params):
        if calls is not None:
            calls.append(url)
        if url == live_data.PTAX:
            return PTAX_ROWS
        if url == live_data.GEOCODING:
            return GEO
        return FORECAST

    monkeypatch.setattr(live_data, "_get_json", get)


def test_fx_uses_last_business_day_and_says_so(monkeypatch):
    fake_api(monkeypatch)
    r = live_data.lookup("What's the euro exchange rate today?", today=date(2026, 11, 1))  # domingo
    assert r and r.kind == "fx" and r.as_of == "2026-10-30"
    assert "R$ 6.0275" in r.text("en") and "last business day" in r.text("en")
    assert "6,0275" in r.text("pt") and "último dia útil" in r.text("pt")
    assert "Fechamento" in r.evidence[0]  # a evidência é o texto bruto da API, não a nossa frase


def test_weather_for_a_city_and_day(monkeypatch):
    calls: list = []
    fake_api(monkeypatch, calls)
    r = live_data.lookup("What's the weather forecast in Porto Alegre tomorrow?")
    assert r and r.kind == "weather" and r.source == "Open-Meteo"
    assert live_data.GEOCODING in calls and live_data.FORECAST in calls
    assert "Porto Alegre" in r.text("en") and "31.4" in r.text("en") and "60%" in r.text("en")


@pytest.mark.parametrize("question,lang", [
    ("What's the euro exchange rate today?", "en"),
    ("Qual a cotação do dólar hoje?", "pt"),
    ("What's the weather forecast in Porto Alegre tomorrow?", "en"),
    ("Qual a previsão do tempo em Porto Alegre amanhã?", "pt"),
])
def test_answer_passes_the_numbers_check(monkeypatch, question, lang):
    """O ponto da mudança: nenhum número da resposta fica sem base na evidência da mesma chamada."""
    fake_api(monkeypatch)
    r = live_data.lookup(question, today=date(2026, 11, 1))
    assert r, question
    assert grounding.unsupported_numbers(r.text(lang), r.evidence, question) == []


def test_api_failure_falls_back_to_web_search(monkeypatch):
    def boom(url, params):
        raise TimeoutError("sem rede")

    monkeypatch.setattr(live_data, "_get_json", boom)
    assert live_data.lookup("What's the euro exchange rate today?") is None


def test_flag_off_and_unrelated_questions_skip_the_api(monkeypatch):
    calls: list = []
    fake_api(monkeypatch, calls)
    assert live_data.lookup("Como funciona a antecipação?") is None
    monkeypatch.setenv("LIVE_DATA", "off")
    assert live_data.lookup("What's the euro exchange rate today?") is None
    assert calls == []


@pytest.mark.parametrize("text,previous,expect", [
    ("E a do dólar?", "Qual a cotação do euro hoje?", "USD"),
    ("And the dollar?", "How much is the euro worth in reais today?", "USD"),
    ("E em Curitiba?", "Vai chover em Porto Alegre amanhã?", "Curitiba amanhã"),
    ("And in Curitiba?", "Is it going to rain in Porto Alegre tomorrow?", "Curitiba amanhã"),
])
def test_elliptical_followup_keeps_the_live_source(text, previous, expect):
    """Seguimento elíptico de câmbio/clima ("E a do dólar?") continua na API oficial e não cai na busca web."""
    q = live_data.followup_query(text, previous)
    assert q and expect in q


def test_followup_without_new_entity_or_unrelated_previous_is_none():
    assert live_data.followup_query("E amanhã?", "Qual o prazo da Get Smart?") is None
    assert live_data.followup_query("Obrigado!", "Qual a cotação do euro hoje?") is None


def test_followup_lookup_calls_the_api(monkeypatch):
    calls: list = []
    fake_api(monkeypatch, calls)
    r = live_data.lookup("E em Curitiba?", previous="Vai chover em Porto Alegre amanhã?")
    assert r and r.kind == "weather" and live_data.FORECAST in calls


def test_source_url_is_part_of_the_evidence(monkeypatch):
    fake_api(monkeypatch)
    r = live_data.lookup("What's the euro exchange rate today?", today=date(2026, 11, 1))
    assert any(r.url in e for e in r.evidence)


def test_transient_errors_are_retried(monkeypatch):
    import httpx

    calls = {"n": 0}

    def flaky(url, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectTimeout("timeout")
        return httpx.Response(200, json={"ok": 1}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", flaky)
    assert live_data._get_json("https://example.invalid/x", {}) == {"ok": 1} and calls["n"] == 3


def test_rate_limit_is_not_retried_and_the_whole_lookup_has_a_deadline(monkeypatch):
    """429 não se repete (o limite não some em ms) e a consulta inteira tem teto: a busca web assume mais cedo.

    Sem o teto, clima com timeout/429 levava o live_data a 5–11 s antes de cair na busca web.
    """
    import httpx

    calls: list[float] = []

    def limited(url, params=None, timeout=None):
        calls.append(timeout)
        return httpx.Response(429, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", limited)
    with pytest.raises(httpx.HTTPStatusError):
        live_data._get_json("https://example.invalid/x", {})
    assert len(calls) == 1

    clock = {"t": 1000.0}
    monkeypatch.setattr(live_data.time, "monotonic", lambda: clock["t"])
    timeouts: list[float] = []

    def hanging(url, params=None, timeout=None):
        timeouts.append(timeout)
        clock["t"] += timeout  # cada tentativa consome o próprio timeout
        raise httpx.ConnectTimeout("timeout")

    monkeypatch.setattr(httpx, "get", hanging)
    monkeypatch.setenv("LIVE_DATA_BUDGET_S", "4")
    monkeypatch.setenv("LIVE_DATA_CACHE_S", "0")  # sem a resposta boa de outro teste no cache
    assert live_data.lookup("Vai chover amanhã em Curitiba?") is None  # falhou dentro do teto: busca web
    # clima: 60% do teto para o Open-Meteo, o resto para a segunda fonte
    assert sum(timeouts) <= 4.0 + 1e-9 and timeouts == pytest.approx([2.4, 1.6])
    assert live_data._DEADLINE.get() is None  # o teto não vaza para a próxima consulta


def test_good_responses_are_cached_and_a_later_network_failure_does_not_lose_them(monkeypatch):
    """Previsão e geocoding não mudam em minutos: a 2ª pergunta igual não depende da rede."""
    from app import live_data

    calls = []

    def fake(url, params):
        calls.append(url)
        if len(calls) > 1:
            raise TimeoutError("rede caiu")
        return {"ok": 1}

    monkeypatch.setenv("LIVE_DATA_CACHE_S", "600")
    monkeypatch.setattr(live_data, "_get_json", fake)
    monkeypatch.setattr(live_data, "_CACHE", {})
    assert live_data._fetch("https://x.test/a", {"q": 1}) == {"ok": 1}
    assert live_data._fetch("https://x.test/a", {"q": 1}) == {"ok": 1} and len(calls) == 1
    monkeypatch.setenv("LIVE_DATA_CACHE_S", "0")
    import pytest

    with pytest.raises(TimeoutError):
        live_data._fetch("https://x.test/a", {"q": 1})


def test_weather_falls_back_to_second_source_when_open_meteo_fails(monkeypatch):
    """Open-Meteo com 429/timeout: a previsão vem da segunda fonte, citada pelo nome, em vez da recusa."""
    def fake(url, params):
        if "open-meteo" in url:
            raise TimeoutError("429")
        assert "wttr.in/Porto+Alegre" in url
        return {"weather": [{"date": "2026-11-03", "mintempC": "19", "maxtempC": "28", "hourly": []},
                            {"date": "2026-11-04", "mintempC": "18", "maxtempC": "24",
                             "hourly": [{"chanceofrain": "40"}, {"chanceofrain": "88"}]}]}

    monkeypatch.setattr(live_data, "_get_json", fake)
    monkeypatch.setenv("LIVE_DATA_CACHE_S", "0")
    r = live_data.lookup("What's the weather forecast in Porto Alegre tomorrow?")
    assert r is not None and r.source == "wttr.in" and r.as_of == "2026-11-04"
    assert "18 °C" in r.text("en") and "24 °C" in r.text("en") and "88%" in r.text("en")
