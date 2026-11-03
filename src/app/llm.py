"""Provedores atrás da mesma interface: offline (determinístico, CI), Anthropic e replay (cassete gravado).

Quem usa LLM chama `get_llm(<papel>)` (router, guardrail, supervisor, agent, judge), checa `.enabled`
e trata `LLMError` caindo no caminho offline; ninguém importa o SDK. Modelo e effort vêm do papel
(config.ROLES, trocáveis por env). Toda chamada real registra tokens e custo.

Regras da API (skill claude-api, 30/10/2026): sem temperature/top_p/top_k (400 desde 21/10/2026);
effort explícito em output_config.effort; structured output em output_config.format; sem tool_choice
forçado (o padrão é auto; any/tool dão 400 no Sonnet 5.5 e no Opus 5.5); stop_reason "refusal"
checado antes do conteúdo; erros do SDK capturados do mais específico ao mais geral.

Cassete: com um gravador ativo (`start_recording`, usado pelo `run_evals --live`), cada resposta da API
(ou erro classificado) é guardada pela chave = hash de papel + modelo + system + mensagens + tools (+ schema).
`LLM_PROVIDER=replay` responde da gravação (`LLM_CASSETTE` = arquivo(s) separados por vírgula; padrão: todos em
evals/cassettes/), sem chave e sem rede; requisição não gravada levanta `CassetteMiss` ("grave de novo") e conta
em `replay_misses()`, porque o supervisor engole exceção de agente e a falta passaria calada.
"""
from __future__ import annotations

import contextlib
import contextvars
import copy
import gzip
import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import (
    ROLES,
    ROOT,
    effort_for,
    llm_api_key,
    llm_base_url,
    llm_first_timeout_s,
    llm_provider,
    model_for,
    thinking_for,
    thinking_param,
)
from .observability import METRICS, log, record_llm_usage, span


def is_quota_message(message: str) -> bool:
    """Erro de limite de gasto/crédito da conta (vem como 400): "reached your specified API usage limits"."""
    low = message.lower()
    return "usage limit" in low or "credit balance is too low" in low or "billing" in low and "limit" in low


class LLMError(RuntimeError):
    """Falha do provedor já classificada; o chamador cai no caminho offline."""

    def __init__(self, message: str, kind: str = "other") -> None:
        super().__init__(message)
        self.kind = kind  # rate_limited | auth | api_status | connection | refusal | max_tokens | config | other


@dataclass
class LLMReply:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    def json(self) -> dict:
        return json.loads(self.text)


class OfflineLLM:
    enabled = False
    model = "offline"
    effort = None

    def complete(self, system: str, messages: list[dict], max_tokens: int = 4096,
                 schema: dict | None = None) -> LLMReply:
        raise LLMError("modo offline: use o caminho determinístico", "offline")

    def create(self, system: str, messages: list, tools: list[dict], max_tokens: int = 8192):
        raise LLMError("modo offline: use o caminho determinístico", "offline")


class AnthropicLLM:
    enabled = True
    role: str | None = None  # get_llm() devolve uma cópia rasa com o papel: entra na chave do cassete
    thinking: dict | None = None  # None = padrão do modelo (adaptativo); config.thinking_param desliga por papel

    def __init__(self, model: str, effort: str, client=None) -> None:
        import anthropic  # import tardio: o modo offline não depende do SDK

        self._sdk = anthropic
        # 60 s por tentativa e 2 retries do SDK (429/5xx/conexão): pior caso ~3 min por chamada.
        # chave e endereço do APP (config.llm_api_key/llm_base_url): na nuvem, nunca os do próprio Claude Code
        self.client = client or anthropic.Anthropic(api_key=llm_api_key(), base_url=llm_base_url(),
                                                    timeout=60.0, max_retries=2)
        self.model = model
        self.effort = effort

    def _fail(self, kind: str, message: str) -> LLMError:
        METRICS.inc("llm_errors_total", model=self.model, kind=kind)
        return LLMError(message, kind)

    def _call(self, **kwargs):
        rec = _RECORDER
        key = request_key(self.role, self.model, kwargs) if rec is not None else None
        try:
            resp = self._api(**kwargs)
        except LLMError as exc:
            if rec is not None:  # o erro também é gravado: o replay cai no mesmo caminho offline
                rec.record(key, self.role, self.model, error={"kind": exc.kind, "message": str(exc)})
            raise
        if rec is not None:
            rec.record(key, self.role, self.model, response=plain(resp))
        return self._checked(resp)

    def _api(self, **kwargs):
        sdk = self._sdk
        output_config = {"effort": self.effort, **kwargs.pop("output_config", {})}
        if self.thinking:
            kwargs["thinking"] = self.thinking
        # role no span: a latência por papel (supervisor, agent, claims...) sai direto do log, sem cruzar com o cassete
        with span("llm", model=self.model, effort=self.effort, role=self.role or "?") as fields:
            try:
                return self._hedged(sdk, fields, model=self.model, output_config=output_config, **kwargs)
            except sdk.RateLimitError as exc:
                raise self._fail("rate_limited", f"rate_limited: {exc}") from exc
            except sdk.APIStatusError as exc:
                kind = "auth" if exc.status_code in (401, 403) else "api_status"
                if is_quota_message(str(exc.message)):
                    kind = "quota"  # limite de gasto da conta: nada passa até renovar
                raise self._fail(kind, f"api_status_{exc.status_code}: {exc.message}") from exc
            except sdk.APIConnectionError as exc:
                raise self._fail("connection", f"connection: {exc}") from exc
            except sdk.APIError as exc:  # ex.: APIResponseValidationError
                raise self._fail("other", f"api_error: {type(exc).__name__}") from exc
            except TypeError as exc:  # SDK sem credencial resolvível levanta TypeError
                raise self._fail("auth", f"client_config: {exc}") from exc

    def _hedged(self, sdk, fields: dict | None = None, **kwargs):
        """1ª tentativa com prazo curto; estourou, 1 nova tentativa com o prazo cheio do cliente.

        Medido em 255 chamadas Sonnet (split de memória): mediana 1,7 s, mas chamadas isoladas de 19 a 46 s para
        ~150 tokens de saída levavam o p95 do caso a 57 s. Repetir a chamada lenta corta a cauda sem mudar a resposta
        esperada.
        Com busca web (tool do servidor, legitimamente lenta) o 1º prazo é maior.
        """
        first = llm_first_timeout_s(web="web_search" in str(kwargs.get("tools") or ""))
        if first <= 0 or not hasattr(self.client, "with_options"):
            return self.client.messages.create(**kwargs)
        try:
            return self.client.with_options(timeout=first, max_retries=0).messages.create(**kwargs)
        except sdk.APITimeoutError:
            METRICS.inc("llm_hedged_total", model=self.model)
            if fields is not None:  # a cauda que a 2ª tentativa cortou fica visível no span
                fields["hedged"] = True
            return self.client.messages.create(**kwargs)
        except (sdk.APIConnectionError, sdk.InternalServerError, sdk.RateLimitError) as exc:
            # A 1ª tentativa roda com max_retries=0 (prazo curto); sem isto, um 529/5xx/429 transitório virava
            # LLMError direto e as retentativas com backoff do SDK nunca aconteciam. Limite de gasto da conta não é
            # transitório: sobe como está.
            if is_quota_message(str(exc)):
                raise
            METRICS.inc("llm_retry_total", model=self.model, kind=type(exc).__name__)
            return self.client.messages.create(**kwargs)

    def _checked(self, resp):
        record_llm_usage(self.model, resp.usage.input_tokens, resp.usage.output_tokens)
        if resp.stop_reason == "refusal":
            raise self._fail("refusal", "refusal")
        return resp

    def complete(self, system: str, messages: list[dict], max_tokens: int = 4096,
                 schema: dict | None = None) -> LLMReply:
        extra = {"output_config": {"format": {"type": "json_schema", "schema": schema}}} if schema else {}
        resp = self._call(max_tokens=max_tokens, system=system, messages=messages, **extra)
        if resp.stop_reason == "max_tokens":
            raise self._fail("max_tokens", "resposta truncada em max_tokens")  # JSON cortado não é dado
        text = "".join(b.text for b in resp.content if b.type == "text")
        return LLMReply(text, self.model, resp.usage.input_tokens, resp.usage.output_tokens)

    def create(self, system: str, messages: list, tools: list[dict], max_tokens: int = 8192):
        """Uma volta do loop manual de tool use: devolve a resposta bruta (o chamador executa as tools)."""
        return self._call(max_tokens=max_tokens, system=system, messages=messages, tools=tools)


@lru_cache(maxsize=16)
def _anthropic(model: str, effort: str) -> AnthropicLLM:
    return AnthropicLLM(model, effort)  # um cliente (pool HTTP) por modelo/effort, não um por chamada


def get_llm(role: str = "agent") -> OfflineLLM | AnthropicLLM:
    provider = llm_provider()
    if provider == "anthropic":
        llm = copy.copy(_anthropic(model_for(role), effort_for(role)))  # mesmo cliente HTTP, papel próprio
        llm.role = role
        llm.thinking = thinking_param(llm.model, thinking_for(role), llm.effort)
        return llm
    if provider == "replay":
        return ReplayLLM(role, model_for(role), effort_for(role), load_cassette())
    return OfflineLLM()


def warmup() -> int:
    """Cria na subida um cliente por (modelo, effort) dos papéis; devolve quantos ficaram prontos.

    `import anthropic` levou ~7 s no Windows do smoke de 31/10/2026 e caía dentro do 1º request de cada
    processo (p50 do split official 22,8 s, ~10 s antes da 1ª chamada). Falha aqui só loga: aquecer é
    otimização, nunca motivo para não subir.
    """
    if llm_provider() != "anthropic":
        return 0
    pairs = {(model_for(role), effort_for(role)) for role in ROLES}
    try:
        for model, effort in pairs:
            _anthropic(model, effort)
    except Exception as exc:  # noqa: BLE001 — qualquer falha de import/config vira aviso, não queda
        log.warning("llm_warmup_failed", extra={"extra_fields": {"error": type(exc).__name__}})
        return 0
    return len(pairs)


# --- cassete: gravar o ao vivo e reproduzir sem chave nem rede -------------------------------------------------
CASSETTE_DIR = ROOT / "evals" / "cassettes"
CASSETTE_GZ_BYTES = 1_000_000  # acima disto o cassete vai comprimido (.jsonl.gz): o diff do git fica pequeno
# Partes voláteis do pedido que não mudam o sentido e mudariam a chave entre a gravação e o replay: data de hoje
# (prompt do agente geral), ids de ticket/ação, conversation_id e carimbos de tempo. Saem só da CHAVE.
_VOLATILE = [
    (re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?"
                r"(?: \((?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\))?"), "<DATA>"),
    (re.compile(r"\b\d{2}/\d{2}/\d{4}\b"), "<DATA>"),
    (re.compile(r"\b[A-Z]-[0-9a-f]{8}\b"), "<ID>"),
    (re.compile(r"\b[0-9a-f]{12,32}\b"), "<HEX>"),
    (re.compile(r"\b1\d{9}\.\d+\b"), "<TS>"),
]


# Escopo da chamada (o eval põe "<caso>#<rodada>"): com casos em paralelo na gravação, a mesma chave pode aparecer em
# dois casos em ordem qualquer; o escopo devolve a cada caso a SUA resposta. Sem escopo (ou sem achar), vale a chave.
CASSETTE_SCOPE: contextvars.ContextVar[str | None] = contextvars.ContextVar("cassette_scope", default=None)


class CassetteMiss(RuntimeError):
    """Pedido sem resposta gravada: o código ou os dados mudaram desde a gravação. Grave de novo."""


def plain(obj):
    """Objeto do SDK (pydantic), SimpleNamespace dos testes ou AttrDict do replay → JSON puro, sem campos None."""
    if isinstance(obj, dict):
        return {str(k): plain(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, (list, tuple)):
        return [plain(v) for v in obj]
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if hasattr(obj, "model_dump"):
        try:
            return plain(obj.model_dump(mode="json"))
        except Exception:  # noqa: BLE001 — modelo com campo não serializável: cai no dump padrão
            return plain(obj.model_dump())
    if hasattr(obj, "__dict__"):
        return plain(vars(obj))
    return str(obj)


class AttrDict(dict):
    """dict com acesso por atributo: `resp.content[0].text` e `dict(block.input)` funcionam no replay."""

    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


def attr(obj):
    if isinstance(obj, dict):
        return AttrDict({k: attr(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [attr(v) for v in obj]
    return obj


def request_key(role: str | None, model: str, kwargs: dict) -> str:
    """sha256 de papel + modelo + system + mensagens + tools + schema, com as partes voláteis normalizadas."""
    fmt = (kwargs.get("output_config") or {}).get("format")
    payload = json.dumps(plain({"role": role or "?", "model": model, "system": kwargs.get("system"),
                                "messages": kwargs.get("messages"), "tools": kwargs.get("tools"), "schema": fmt}),
                         ensure_ascii=False, sort_keys=True)
    for pattern, repl in _VOLATILE:
        payload = pattern.sub(repl, payload)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class Cassette:
    """Respostas gravadas por chave, na ordem em que aconteceram (a mesma chave pode repetir: pass^3)."""

    def __init__(self, entries: list[dict] | None = None, paths: list[str] | None = None) -> None:
        self.entries: list[dict] = []
        self.by_key: dict[str, list[dict]] = {}
        self.by_scope: dict[tuple[str, str], list[dict]] = {}
        self.cursor: dict = {}
        self.misses: list[str] = []
        self.paths = paths or []
        self._lock = threading.Lock()
        for e in entries or []:
            self._add(e)

    def _add(self, entry: dict) -> None:
        self.entries.append(entry)
        self.by_key.setdefault(entry["key"], []).append(entry)
        if entry.get("scope"):
            self.by_scope.setdefault((entry["scope"], entry["key"]), []).append(entry)

    def record(self, key: str, role: str | None, model: str, response: dict | None = None,
               error: dict | None = None) -> None:
        entry = {"key": key, "role": role, "model": model, "scope": CASSETTE_SCOPE.get()}
        entry.update({"response": response} if error is None else {"error": error})
        with self._lock:
            self._add(entry)

    def next(self, key: str, scope: str | None = None) -> dict | None:
        """Próxima gravação da chave (no escopo, se houver); depois da última, recomeça."""
        with self._lock:
            slot = (scope, key) if scope and (scope, key) in self.by_scope else key
            found = self.by_scope.get(slot) if isinstance(slot, tuple) else self.by_key.get(slot)
            if not found:
                return None
            i = self.cursor.get(slot, 0)
            self.cursor[slot] = i + 1
            return found[i % len(found)]

    def miss(self, key: str) -> None:
        with self._lock:
            self.misses.append(key)

    def save(self, path: Path) -> Path:
        """Grava JSONL (ou .jsonl.gz se grande, gzip sem data: o mesmo conteúdo dá os mesmos bytes)."""
        base = Path(str(path).removesuffix(".gz"))
        data = "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in self.entries).encode()
        base.parent.mkdir(parents=True, exist_ok=True)
        gz = Path(f"{base}.gz")
        target, stale = (gz, base) if len(data) > CASSETTE_GZ_BYTES else (base, gz)
        if target is gz:
            with open(gz, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as f:
                f.write(data)
        else:
            base.write_bytes(data)
        stale.unlink(missing_ok=True)  # nunca dois cassetes do mesmo split (um velho e um novo)
        return target

    @classmethod
    def load(cls, paths: list[Path]) -> Cassette:
        entries = []
        for p in paths:
            opener = gzip.open if str(p).endswith(".gz") else open
            with opener(p, "rt", encoding="utf-8") as f:
                entries += [json.loads(line) for line in f if line.strip()]
        return cls(entries, [str(p) for p in paths])


def cassette_files(directory: Path | None = None) -> list[Path]:
    directory = directory or CASSETTE_DIR
    return sorted([*directory.glob("*.jsonl"), *directory.glob("*.jsonl.gz")])


_RECORDER: Cassette | None = None
_LOADED: dict[tuple[str, ...], Cassette] = {}


def start_recording() -> Cassette:
    global _RECORDER
    _RECORDER = Cassette()
    return _RECORDER


def stop_recording() -> Cassette | None:
    global _RECORDER
    rec, _RECORDER = _RECORDER, None
    return rec


def load_cassette() -> Cassette:
    """Cassete do replay: LLM_CASSETTE (arquivos separados por vírgula) ou todos em evals/cassettes/."""
    raw = os.getenv("LLM_CASSETTE", "")
    paths = tuple(sorted(p.strip() for p in raw.split(",") if p.strip())) or tuple(map(str, cassette_files()))
    if paths not in _LOADED:
        _LOADED[paths] = Cassette.load([Path(p) for p in paths])
    return _LOADED[paths]


def reset_replay() -> None:
    """Esquece cassetes carregados (cursores e faltas): cada split do `run_evals --replay` começa do zero."""
    _LOADED.clear()


def replay_misses() -> int:
    return sum(len(c.misses) for c in _LOADED.values())


class ReplayLLM(AnthropicLLM):
    """Responde da gravação: mesma interface e mesmo pós-processamento do AnthropicLLM, sem SDK nem rede."""

    def __init__(self, role: str, model: str, effort: str, cassette: Cassette) -> None:
        self.role, self.model, self.effort, self.cassette = role, model, effort, cassette

    def _call(self, **kwargs):
        key = request_key(self.role, self.model, kwargs)
        entry = self.cassette.next(key, CASSETTE_SCOPE.get())
        if entry is None:
            self.cassette.miss(key)
            METRICS.inc("llm_replay_miss_total", model=self.model)
            raise CassetteMiss(f"requisição não gravada no cassete ({self.role}/{self.model}, chave {key[:12]}): "
                               "grave de novo com `python -m evals.run_evals --live --split <split>`")
        if "error" in entry:
            raise LLMError(entry["error"].get("message", "erro gravado"), entry["error"].get("kind", "other"))
        resp = attr(entry["response"])
        if resp.stop_reason == "refusal":
            raise LLMError("refusal", "refusal")
        return resp  # sem custo: o replay não gasta (os tokens gravados ficam no cassete)


@contextlib.contextmanager
def recording():
    """`with recording() as cassette:` grava as chamadas reais do bloco."""
    rec = start_recording()
    try:
        yield rec
    finally:
        stop_recording()


# --- juiz de outra família: cliente HTTP mínimo para /chat/completions compatível ------------------------------
class OpenAICompatLLM:
    """Só `complete` (o juiz não usa tools). JUDGE_BASE_URL, JUDGE_MODEL, JUDGE_API_KEY. Sem SDK: urllib da stdlib.

    Pede JSON pelo `response_format` json_schema; servidor que devolve o JSON entre texto ou cercas também serve.
    Custo: modelo fora da tabela de preços entra como "unpriced" (tokens contados, US$ 0).
    """

    enabled = True
    provider = "openai_compat"
    effort = None

    def __init__(self, base_url: str, model: str, api_key: str | None = None, post=None, timeout: float = 120.0):
        self.base_url, self.model, self.api_key, self.timeout = base_url.rstrip("/"), model, api_key, timeout
        self._post = post or self._urllib_post

    def _urllib_post(self, url: str, body: dict, headers: dict) -> tuple[int, dict]:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 — URL vem da config do dono
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read() or b"{}")
            except ValueError:
                payload = {}
            return exc.code, payload
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMError(f"connection: {exc}", "connection") from exc

    def complete(self, system: str, messages: list[dict], max_tokens: int = 4096,
                 schema: dict | None = None) -> LLMReply:
        body = {"model": self.model, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, *messages]}
        if schema:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "verdict", "schema": schema, "strict": True}}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        with span("llm", model=self.model, effort="n/a"):
            status, data = self._post(f"{self.base_url}/chat/completions", body, headers)
        if status != 200:
            kind = "auth" if status in (401, 403) else "rate_limited" if status == 429 else "api_status"
            METRICS.inc("llm_errors_total", model=self.model, kind=kind)
            raise LLMError(f"api_status_{status}: {str(data)[:200]}", kind)
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"resposta fora do formato: {str(data)[:200]}", "other") from exc
        if choice.get("finish_reason") == "length":
            raise LLMError("resposta truncada em max_tokens", "max_tokens")
        usage = data.get("usage") or {}
        tin, tout = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        record_llm_usage(self.model, tin, tout)
        if schema:  # JSON entre texto ou cercas ```json: fica só o objeto
            m = re.search(r"\{.*\}", text, re.DOTALL)
            text = m.group(0) if m else text
        return LLMReply(text, self.model, tin, tout)


def get_judge_llm():
    """Juiz: JUDGE_PROVIDER=openai_compat (outra família) ou o papel "judge" do provedor do app."""
    if os.getenv("JUDGE_PROVIDER", "anthropic") != "openai_compat":
        return get_llm("judge")
    base, model = os.getenv("JUDGE_BASE_URL"), os.getenv("JUDGE_MODEL")
    if not base or not model:
        raise LLMError("JUDGE_PROVIDER=openai_compat precisa de JUDGE_BASE_URL e JUDGE_MODEL", "config")
    return OpenAICompatLLM(base, model, (os.getenv("JUDGE_API_KEY") or "").strip() or None)
