"""Dados ao vivo resolvidos no código para a intenção `general`: câmbio (PTAX do Banco Central) e clima (Open-Meteo).

Por que no código e não na busca web: a busca do provedor devolve o corpo da página cifrado, e a checagem numérica só
enxergava título e trecho citado (medido: números dos cenários oficiais 80% ao vivo, clima e câmbio sem base).
Aqui a pergunta dispara uma consulta montada por nós; o TEXTO bruto da API vira evidência do turno e a resposta cita
fonte e data. Fonte real com data é o que deixa a resposta conferível.

Detector estreito de propósito: câmbio exige palavra de cotação E uma moeda conhecida da PTAX; clima exige palavra de
clima E uma cidade que o geocoding encontre. Qualquer falha (sem moeda, cidade desconhecida, timeout de 3 s, HTTP,
JSON inesperado) devolve None e o agente cai na busca web. Flag `LIVE_DATA=on|off` (padrão on).

- PTAX: `CotacaoMoedaPeriodo` numa janela de 7 dias até a data pedida; usa o último boletim de "Fechamento" (ou o
  último do dia mais recente). Fim de semana e feriado caem sozinhos no último dia útil, numa chamada só.
- Open-Meteo: geocoding (nome → lat/lon/fuso) + previsão diária da data pedida (hoje, amanhã, depois de amanhã), com
  "hoje" no fuso da cidade.
"""
from __future__ import annotations

import contextvars
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .observability import METRICS, log, span

TIMEOUT_S = 3.0
# Teto da consulta INTEIRA (geocoding + previsão, com as novas tentativas). Medido: com timeout de conexão e 429 do
# Open-Meteo, o `live_data` de clima levou 5–11 s e ainda caiu na busca web; sucesso levou 1,3–2,3 s. Passou do teto, a
# busca web assume mais cedo. `LIVE_DATA_BUDGET_S` (env) troca; 0 desliga o teto.
BUDGET_S = 5.0
MIN_ATTEMPT_S = 0.3  # menos que isso não dá tempo de uma resposta HTTP: desiste em vez de tentar
_DEADLINE: contextvars.ContextVar[float | None] = contextvars.ContextVar("live_data_deadline", default=None)
PTAX = ("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoMoedaPeriodo("
        "moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)")
GEOCODING = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"


def enabled() -> bool:
    return os.getenv("LIVE_DATA", "on").lower() != "off"


@dataclass
class LiveResult:
    kind: str  # fx | weather
    source: str  # nome da fonte, citado na resposta
    url: str  # consulta feita (fonte da resposta)
    as_of: str  # data do dado (ISO)
    text_pt: str  # resposta pronta (template), também evidência
    text_en: str
    evidence: list[str] = field(default_factory=list)  # texto bruto da API + valores arredondados
    # valores que a resposta TEM de trazer (o prompt pede; o código confere): (rótulo pt, rótulo en, valor, tolerância
    # do arredondamento que o prompt permite). Clima: mínima, máxima e chance de chuva; câmbio: venda e compra.
    must: list[tuple[str, str, float, float]] = field(default_factory=list)

    def text(self, language: str) -> str:
        return self.text_en if language == "en" else self.text_pt

    def __post_init__(self) -> None:
        # o endereço da fonte é evidência: a resposta cita o link do BCB/Open-Meteo e, sem ele no texto, o juiz o
        # lia como inventado (medido: 6 reprovações do juiz só pelo link)
        line = f"Fonte consultada: {self.source} — {self.url}"
        if line not in self.evidence:
            self.evidence.append(line)


def budget_s() -> float:
    try:
        return float(os.getenv("LIVE_DATA_BUDGET_S", BUDGET_S))
    except ValueError:
        return BUDGET_S


_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_LOCK = __import__("threading").Lock()


def cache_s() -> float:
    """Validade das respostas boas da API (LIVE_DATA_CACHE_S, padrão 600 s; 0 desliga). Previsão do dia e geocoding
    não mudam em minutos, e cada pergunta de clima faz 2 chamadas: com o cache, uma falha de rede passageira (1 em
    ~6 chamadas, sondado) não derruba as perguntas seguintes, e o limite de taxa do provedor (429) aparece menos."""
    try:
        return max(0.0, float(os.getenv("LIVE_DATA_CACHE_S", "600")))
    except ValueError:
        return 600.0


def _fetch(url: str, params: dict) -> dict:
    ttl = cache_s()
    key = url + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
    if ttl:
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
        if hit and time.monotonic() - hit[0] < ttl:
            METRICS.inc("live_data_cache_hits_total")
            return hit[1]
    data = _get_json(url, params)
    if ttl:
        with _CACHE_LOCK:
            _CACHE[key] = (time.monotonic(), data)
            if len(_CACHE) > 256:  # teto de memória: some a entrada mais antiga
                _CACHE.pop(min(_CACHE, key=lambda k: _CACHE[k][0]))
    return data


def _get_json(url: str, params: dict) -> dict:
    """Único ponto de rede do módulo (os testes trocam esta função). Timeout curto: a resposta não pode esperar."""
    import httpx

    last: Exception | None = None
    deadline = _DEADLINE.get()
    # 3 tentativas: numa VM de nuvem o Open-Meteo deu timeout de conexão ou 5xx em ~1 de 6 chamadas (sondado
    # com curl) e 8 perguntas de clima caíram na busca web. 4xx de pedido errado não se repete; 429 também não: o
    # limite de taxa não some em milissegundos e repetir só gasta o teto (sondado: 3 x 429 seguidos no forecast).
    for _ in range(3):
        timeout = TIMEOUT_S
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining < MIN_ATTEMPT_S:
                last = last or TimeoutError("live_data: teto da consulta esgotado")
                break
            timeout = min(TIMEOUT_S, remaining)
        try:
            resp = httpx.get(url, params=params, timeout=timeout)
            if resp.status_code >= 500:
                last = httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.TransportError as exc:
            last = exc
    raise last  # type: ignore[misc]


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


# --- datas relativas -------------------------------------------------------------------------------------------------
def _day_offset(text: str) -> int:
    t = _fold(text)
    if re.search(r"depois de amanha|day after tomorrow", t):
        return 2
    if re.search(r"\bamanha\b|\btomorrow\b", t):
        return 1
    return 0


# --- câmbio (PTAX) ---------------------------------------------------------------------------------------------------
# Moedas que a PTAX publica (boletim tipo A/B). Ordem importa: "dólar canadense" antes de "dólar".
_CURRENCIES = [
    ("CAD", r"dolar(es)? canadense|canadian dollar|\bcad\b"),
    ("AUD", r"dolar(es)? australiano|australian dollar|\baud\b"),
    ("USD", r"\bdolar(es)?\b|\bdollars?\b|\busd\b|\bus\$"),
    ("EUR", r"\beuros?\b|\beur\b"),
    ("GBP", r"\blibras?( esterlinas?)?\b|\bpounds?( sterling)?\b|\bgbp\b"),
    ("JPY", r"\bienes?\b|\byens?\b|\bjpy\b"),
    ("CHF", r"franco suico|swiss franc|\bchf\b"),
    ("DKK", r"coroa dinamarquesa|danish krone|\bdkk\b"),
    ("NOK", r"coroa norueguesa|norwegian krone|\bnok\b"),
    ("SEK", r"coroa sueca|swedish krona|\bsek\b"),
]
_FX_WORDS = re.compile(r"\bcambio\b|\bcotac(ao|oes)\b|exchange rate|\bfx\b|\brate\b|quanto (esta|ta|vale|custa) o"
                       r"|how much is (the|one|1)|\bconver(t|ter|sao)\b")


def currency_of(text: str) -> str | None:
    """Código da moeda quando a pergunta é de câmbio (palavra de cotação + moeda da PTAX); None no resto."""
    t = _fold(text)
    if not _FX_WORDS.search(t):
        return None
    return next((code for code, pattern in _CURRENCIES if re.search(pattern, t)), None)


def _br(value: float, places: int) -> str:
    return f"{value:,.{places}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fx(code: str, wanted: date) -> LiveResult | None:
    start = wanted - timedelta(days=7)
    params = {"@moeda": f"'{code}'", "@dataInicial": f"'{start:%m-%d-%Y}'",
              "@dataFinalCotacao": f"'{wanted:%m-%d-%Y}'", "$format": "json",
              "$select": "cotacaoCompra,cotacaoVenda,dataHoraCotacao,tipoBoletim"}
    rows = [r for r in _fetch(PTAX, params).get("value", []) if r.get("cotacaoVenda") is not None]
    if not rows:
        return None
    last_day = max(r["dataHoraCotacao"][:10] for r in rows)
    day_rows = [r for r in rows if r["dataHoraCotacao"][:10] == last_day]
    row = next((r for r in reversed(day_rows) if str(r.get("tipoBoletim", "")).startswith("Fechamento")),
               day_rows[-1])
    buy, sell, kind = float(row["cotacaoCompra"]), float(row["cotacaoVenda"]), row.get("tipoBoletim", "")
    day = date.fromisoformat(last_day)
    shown = f"{day:%d/%m/%Y}"
    note_pt = "" if day == wanted else f" (último dia útil com cotação; {wanted:%d/%m/%Y} não teve boletim)"
    note_en = "" if day == wanted else f" (last business day with a quote; none on {wanted.isoformat()})"
    boletim_pt = "fechamento" if kind.startswith("Fechamento") else (kind.lower() or "boletim")
    text_pt = (f"Cotação PTAX do Banco Central ({boletim_pt}) em {shown}{note_pt}: 1 {code} = R$ {_br(sell, 4)} "
               f"na venda e R$ {_br(buy, 4)} na compra. Fonte: Banco Central do Brasil (PTAX).")
    text_en = (f"Central Bank of Brazil PTAX rate ({'closing' if kind.startswith('Fechamento') else 'bulletin'}) "
               f"on {day.isoformat()}{note_en}: 1 {code} = R$ {sell:.4f} (sell) and R$ {buy:.4f} (buy). "
               "Source: Banco Central do Brasil (PTAX).")
    rounded = f"Arredondado: venda R$ {_br(sell, 2)}, compra R$ {_br(buy, 2)} ({sell:.2f} / {buy:.2f})"
    must = [("a venda", "the sell rate", sell, 0.0051), ("a compra", "the buy rate", buy, 0.0051)]
    return LiveResult("fx", "Banco Central do Brasil (PTAX)", "https://www.bcb.gov.br/estabilidadefinanceira/"
                      "historicocotacoes", last_day, text_pt, text_en, must=must,
                      evidence=[f"PTAX {code} (API do Banco Central): cotacaoCompra {buy:.4f}; "
                                f"cotacaoVenda {sell:.4f}; dataHoraCotacao {row.get('dataHoraCotacao')}; "
                                f"tipoBoletim {kind}",
                                f"Cotação de 1 {code}: venda {sell:.4f}, compra {buy:.4f} (dia {last_day})",
                                f"Data consultada: {wanted.isoformat()} ({wanted:%d/%m/%Y})", rounded])


# --- clima (Open-Meteo) ----------------------------------------------------------------------------------------------
_WEATHER_WORDS = re.compile(r"\bclima\b|previsao (?:do tempo|para|pra|em|no|na)"
                            r"|\btempo (em|no|na|para|pra|de|hoje|amanha)|\bweather\b|\bforecast\b"
                            r"|vai chover|\bchuva\b|temperatura|\btemperature\b|\brain\b")
_STOP = {"hoje", "amanha", "agora", "today", "tomorrow", "now", "semana", "week", "depois"}
# palavra que encerra o nome da cidade (outra preposição, verbo, palavra de clima)
_BREAK = {"em", "no", "na", "para", "pra", "in", "for", "at", "on", "tempo", "clima", "weather", "forecast",
          "previsao", "like", "e", "and", "esta", "vai", "is", "will", "be"}
_CITY_AFTER = re.compile(r"(?=\b(?:em|no|na|para|pra|de|in|for|at)\s+([^\s,?!.;:]+(?:\s+[^\s,?!.;:]+){0,3}))",
                         re.IGNORECASE)
_CONNECT = {"de", "do", "da", "dos", "das", "del", "los", "las"}


def is_weather(text: str) -> bool:
    return bool(_WEATHER_WORDS.search(_fold(text)))


def city_of(text: str) -> str | None:
    """Cidade depois de "em/no/na/in/for": prefere a que começa com maiúscula ("Rio de Janeiro"); senão a última.

    O geocoding confirma: nome que não é cidade volta vazio e a pergunta cai na busca web.
    """
    if not is_weather(text):
        return None
    return _city_in(text)


def _city_in(text: str) -> str | None:
    cands: list[list[str]] = []
    for m in _CITY_AFTER.finditer(text):
        words: list[str] = []
        for w in m.group(1).split():
            if _fold(w) in _STOP or _fold(w) in _BREAK or _fold(w) in ("do", "tempo"):
                break
            words.append(w)
        while words and _fold(words[-1]) in _CONNECT:
            words.pop()
        if words and _fold(words[0]) not in _CONNECT:
            cands.append(words)
    caps = [c for c in cands if c[0][:1].isupper()]
    pick = caps[0] if caps else (cands[-1] if cands else None)
    return " ".join(pick) if pick else None


_WMO = {0: ("céu limpo", "clear sky"), 1: ("predominantemente limpo", "mainly clear"),
        2: ("parcialmente nublado", "partly cloudy"), 3: ("nublado", "overcast"), 45: ("neblina", "fog"),
        48: ("neblina", "fog"), 51: ("garoa", "drizzle"), 53: ("garoa", "drizzle"), 55: ("garoa", "drizzle"),
        61: ("chuva fraca", "light rain"), 63: ("chuva", "rain"), 65: ("chuva forte", "heavy rain"),
        80: ("pancadas de chuva", "rain showers"), 81: ("pancadas de chuva", "rain showers"),
        82: ("pancadas fortes", "violent rain showers"), 95: ("trovoadas", "thunderstorm"),
        96: ("trovoadas com granizo", "thunderstorm with hail"),
        99: ("trovoadas com granizo", "thunderstorm with hail")}


def weather(city: str, offset: int) -> LiveResult | None:
    geo = _fetch(GEOCODING, {"name": city, "count": 1, "language": "pt", "format": "json"}).get("results") or []
    if not geo:
        return None
    place = geo[0]
    tz = place.get("timezone") or "UTC"
    try:
        today = datetime.now(ZoneInfo(tz)).date()
    except Exception:  # noqa: BLE001 — fuso desconhecido: data do servidor
        today = date.today()
    day = today + timedelta(days=offset)
    params = {"latitude": place["latitude"], "longitude": place["longitude"], "timezone": tz,
              "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
              "start_date": day.isoformat(), "end_date": day.isoformat()}
    daily = _fetch(FORECAST, params).get("daily") or {}
    if not daily.get("time"):
        return None
    # a data do texto é a que a API devolveu, não a que pedimos: com o relógio do servidor num fuso e a API noutro,
    # "amanhã" calculado aqui podia não bater com a evidência (teste falhava conforme o dia em que rodava).
    day = date.fromisoformat(str(daily["time"][0])[:10])
    tmax, tmin = float(daily["temperature_2m_max"][0]), float(daily["temperature_2m_min"][0])
    rain = (daily.get("precipitation_probability_max") or [None])[0]
    code = (daily.get("weather_code") or [None])[0]
    sky_pt, sky_en = _WMO.get(code, ("", "")) if code is not None else ("", "")
    name = ", ".join(x for x in (place.get("name"), place.get("admin1"), place.get("country")) if x)
    when_pt = {0: "hoje", 1: "amanhã", 2: "depois de amanhã"}[offset]
    when_en = {0: "today", 1: "tomorrow", 2: "the day after tomorrow"}[offset]
    rain_pt = f", chance de chuva de até {rain}%" if rain is not None else ""
    rain_en = f", up to {rain}% chance of rain" if rain is not None else ""
    text_pt = (f"Previsão para {name} {when_pt} ({day:%d/%m/%Y}): mínima de {_br(tmin, 1)} °C e máxima de "
               f"{_br(tmax, 1)} °C{rain_pt}{', ' + sky_pt if sky_pt else ''}. Fonte: Open-Meteo.")
    text_en = (f"Forecast for {name} {when_en} ({day.isoformat()}): low {tmin:.1f} °C, high {tmax:.1f} °C"
               f"{rain_en}{', ' + sky_en if sky_en else ''}. Source: Open-Meteo.")
    rounded = f"Arredondado: mínima {round(tmin)} °C, máxima {round(tmax)} °C"
    # Texto plano, um valor por campo: o JSON bruto tem listas de 1 elemento ("[60]") e a checagem numérica apaga
    # "[n]" como marca de citação, o que fazia a chance de chuva virar "número sem base" (teste: test_live_data).
    flat = "; ".join(f"{k} {v[0] if isinstance(v, list) and v else v}" for k, v in daily.items())
    where = f"{place.get('name')} (lat {place.get('latitude')}, lon {place.get('longitude')}, {tz})"
    return LiveResult("weather", "Open-Meteo", "https://open-meteo.com/", day.isoformat(), text_pt, text_en,
                      evidence=[f"Open-Meteo (API) para {where}: {flat}", rounded], must=weather_must(tmin, tmax, rain))


WTTR = "https://wttr.in/{where}"


def weather_must(tmin: float, tmax: float, rain) -> list[tuple[str, str, float, float]]:
    """Mínima e máxima (a resposta pode arredondar ao grau) e a chance de chuva, quando a fonte traz."""
    out = [("a mínima", "the low", tmin, 0.51), ("a máxima", "the high", tmax, 0.51)]
    if rain is not None:
        out.append(("a chance de chuva", "the chance of rain", float(rain), 0.0))
    return out


def weather_backup(city: str, offset: int) -> LiveResult | None:
    """Segunda fonte de clima (wttr.in, sem chave): o Open-Meteo devolve 429/timeout sob carga e o cenário oficial
    de clima caía na recusa. Mesmo formato de evidência; a fonte citada é a que respondeu."""
    data = _fetch(WTTR.format(where=city.replace(" ", "+")), {"format": "j1", "lang": "pt"})
    days = data.get("weather") or []
    if len(days) <= offset:
        return None
    d = days[offset]
    day = date.fromisoformat(str(d["date"])[:10])
    tmin, tmax = float(d["mintempC"]), float(d["maxtempC"])
    rain = max((int(h.get("chanceofrain", 0)) for h in d.get("hourly") or []), default=None)
    when_pt = {0: "hoje", 1: "amanhã", 2: "depois de amanhã"}[offset]
    when_en = {0: "today", 1: "tomorrow", 2: "the day after tomorrow"}[offset]
    rain_pt = f", chance de chuva de até {rain}%" if rain is not None else ""
    rain_en = f", up to {rain}% chance of rain" if rain is not None else ""
    text_pt = (f"Previsão para {city} {when_pt} ({day:%d/%m/%Y}): mínima de {_br(tmin, 0)} °C e máxima de "
               f"{_br(tmax, 0)} °C{rain_pt}. Fonte: wttr.in.")
    text_en = (f"Forecast for {city} {when_en} ({day.isoformat()}): low {tmin:.0f} °C, high {tmax:.0f} °C"
               f"{rain_en}. Source: wttr.in.")
    flat = f"date {day.isoformat()}; mintempC {d['mintempC']}; maxtempC {d['maxtempC']}; chanceofrain_max {rain}"
    return LiveResult("weather", "wttr.in", "https://wttr.in/", day.isoformat(), text_pt, text_en,
                      evidence=[f"wttr.in (API) para {city}: {flat}", "Fonte desta previsão: wttr.in."],
                      must=weather_must(tmin, tmax, rain))


def followup_query(text: str, previous: str | None) -> str | None:
    """Seguimento elíptico de câmbio/clima ("E a do dólar?", "And in Curitiba?") vira pergunta completa.

    O tipo vem da fala anterior do cliente; a entidade nova (moeda ou cidade), da fala atual; o dia, da atual se
    houver, senão da anterior. Sem entidade nova, ou fala anterior que não era câmbio/clima: None.
    """
    if not previous or currency_of(text) or city_of(text):
        return None
    t = _fold(text)
    if currency_of(previous):
        code = next((c for c, pattern in _CURRENCIES if re.search(pattern, t)), None)
        return f"cotação do {code} hoje ({text})" if code else None
    if is_weather(previous):
        city = _city_in(text)
        if not city:
            return None
        day = {0: "hoje", 1: "amanhã", 2: "depois de amanhã"}[_day_offset(text) or _day_offset(previous)]
        return f"previsão do tempo em {city} {day}"
    return None


def lookup(text: str, today: date | None = None, previous: str | None = None) -> LiveResult | None:
    """Dado ao vivo para a pergunta (ou para o seguimento dela, com a fala anterior do cliente), ou None."""
    full = followup_query(text, previous)
    if full:
        return _lookup(full, today)
    return _lookup(text, today)


def _lookup(text: str, today: date | None = None) -> LiveResult | None:
    """Dado ao vivo para a pergunta, ou None (não é câmbio/clima, flag off, ou a API falhou: use a busca web)."""
    if not enabled():
        return None
    code, city = currency_of(text), city_of(text)
    if not code and not city:
        return None
    kind = "fx" if code else "weather"
    budget = budget_s()
    token = _DEADLINE.set(time.monotonic() + budget if budget > 0 else None)
    try:
        with span("live_data", kind=kind):
            if code:
                result = fx(code, today or datetime.now(ZoneInfo("America/Sao_Paulo")).date())
            else:
                # 1ª fonte com 60% do teto; o resto fica para a segunda: a consulta inteira continua dentro do teto
                start = time.monotonic()
                if budget > 0:
                    _DEADLINE.set(start + budget * 0.6)
                try:
                    result = weather(city, _day_offset(text))
                except Exception:  # noqa: BLE001 — 429/timeout no Open-Meteo: a segunda fonte
                    METRICS.inc("live_data_total", kind=kind, outcome="backup")
                    if budget > 0:
                        _DEADLINE.set(start + budget)
                    result = weather_backup(city, _day_offset(text))
    except Exception as exc:  # noqa: BLE001 — timeout, HTTP, JSON: a busca web assume
        METRICS.inc("live_data_total", kind=kind, outcome="error")
        log.warning("live_data_failed", extra={"extra_fields": {"kind": kind, "error": type(exc).__name__}})
        return None
    finally:
        _DEADLINE.reset(token)
    METRICS.inc("live_data_total", kind=kind, outcome="ok" if result else "empty")
    return result
