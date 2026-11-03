"""Memória factual da conversa: o que o cliente e as ferramentas disseram, extraído por CÓDIGO e persistido.

O histórico além da janela vira um resumo curto (pipeline._digest) e qualquer resumo, de LLM ou de regra, perde
valor, id e data: a conversa de 15 turnos esquece o "TX1007" do turno 2. O livro de fatos (ledger) é independente do
resumo: guarda, por conversa, ids, valores em dinheiro, datas, o assunto vigente e o que as ferramentas devolveram, e
entra no contexto dos agentes como "Fatos da conversa" mesmo quando o resumo os omite.

Quem produziu o fato fica gravado (`s`): "user" (fala do cliente), "tool" (resultado de ferramenta) ou "source"
(trecho de fonte/busca). A fala do ASSISTENTE nunca entra: um número que o modelo inventou no turno 3 não pode virar
base do turno 8 só por ter sido dito antes. `known_text()` é o que a checagem numérica (grounding) lê como base.

Este módulo também calcula, em código, somas e contagens sobre listas devolvidas por ferramentas (`with_aggregates`):
o redator recebe o total pronto em vez de somar de cabeça, e a checagem numérica o reconhece como evidência.

Extensão por domínio (opcional, em app/domain/<ativo>.py): ID_PATTERNS = [regex, ...] com ids próprios do negócio.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from . import domain
from .guardrails import mask_pii

LEDGER_VERSION = 1
# Tetos por tipo: o livro vai no prompt de todo agente e no banco; conversa longa não pode inflar nenhum dos dois.
CAPS = {"id": 40, "money": 40, "date": 30, "entity": 24}
RENDER_CAPS = {"id": 12, "money": 10, "date": 8, "entity": 8, "source": 6}
SUBJECT_CHARS = 200
ENTITY_FIELDS = 8
FIELD_CHARS = 40
MAX_EVIDENCE_FACTS = 20  # fatos de fonte/busca por turno (texto livre é o mais ruidoso)

_FLAGS = re.IGNORECASE
# Id = 1-4 letras + 3 ou mais dígitos (TX1008, T1988A, ORD-1234) ou "T-" + hex (protocolo de caso). Não casa "R$300"
# (o cifrão separa), nem "4g" (poucos dígitos), nem "iphone15" (letras demais).
_ID_GENERIC = re.compile(r"(?<![\w-])(?:[A-Za-z]{1,4}-?\d{3,}[A-Za-z]?|[A-Za-z]-[0-9a-f]{6,})(?![\w-])")
_ID_LABELLED = re.compile(r"\b(?:pedido|order|protocolo|ticket|chamado|caso|case|id|c[óo]digo|code|n[ºo°]|#)"
                          r"\s*[:#]?\s*(\d{3,})\b", _FLAGS)
_MONEY = re.compile(r"(?:R\$|US\$|U\$S|€|£|\$)\s?\d[\d.,]*|\b\d[\d.,]*\s?(?:reais|d[óo]lares|dollars|euros|BRL|USD)\b",
                    _FLAGS)
_ISO_DATE = re.compile(r"(?<![\w-])\d{4}-\d{2}-\d{2}(?![\w-])")
_SLASH_DATE = re.compile(r"(?<![\w/])(\d{1,2})/(\d{1,2})(?:/(\d{4}|\d{2}))?(?![\w/])")
_ID_KEY = re.compile(r"^(?:id|protocol\w*|\w+_id)$", _FLAGS)


@dataclass
class Ledger:
    """Livro de fatos de UMA conversa. `facts`: lista de dicts {k, v, s, t[, c][, f]}, do mais antigo ao mais novo."""

    turn: int = 0
    subject: dict | None = None  # {"text", "intent", "t"}: a última fala do cliente que definiu o assunto
    facts: list[dict] = field(default_factory=list)

    # --- escrita --------------------------------------------------------------------------------------------
    def add(self, kind: str, value: str, source: str, *, context: str = "", fields: dict | None = None) -> None:
        """Insere ou atualiza um fato (chave: tipo + valor); o mais recente vai para o fim e o teto expulsa o antigo."""
        def norm(x: str) -> str:
            return x.upper() if kind in ("id", "entity") else x

        old = next((f for f in self.facts if f["k"] == kind and norm(f["v"]) == norm(value)), None)
        merged = {**(old.get("f") or {}), **(fields or {})} if old else (fields or {})
        if old:
            self.facts.remove(old)
            if old["s"] == "user" and source != "user":
                source = "user"  # o cliente disse primeiro: a origem mais forte fica
        item = {"k": kind, "v": value, "s": source, "t": self.turn}
        if context or (old and old.get("c")):
            item["c"] = context or old["c"]
        if merged:
            item["f"] = merged
        self.facts.append(item)
        same = [f for f in self.facts if f["k"] == kind]
        for extra in same[:max(0, len(same) - CAPS.get(kind, 40))]:
            self.facts.remove(extra)

    # --- leitura --------------------------------------------------------------------------------------------
    def of(self, kind: str, source: str | None = None) -> list[dict]:
        return [f for f in self.facts if f["k"] == kind and (source is None or f["s"] == source)]

    def known_text(self) -> str:
        """Tudo o que o cliente ou uma ferramenta/fonte produziu, como texto para a checagem numérica.

        Não existe fato de assistente no livro, então nada que o modelo disse sozinho é base.
        """
        parts = [f["v"] for f in self.facts]
        for f in self.facts:
            parts += [str(v) for v in (f.get("f") or {}).values()]
        return " ".join(parts)

    def render(self) -> str:
        """Bloco "Fatos da conversa" para o prompt dos agentes ("" se o livro está vazio)."""
        lines: list[str] = []
        if self.subject:
            lines.append(f"- Assunto atual: {self.subject['text']} (intenção: {self.subject['intent']})")
        ids = [f["v"] for f in self.of("id", "user")][-RENDER_CAPS["id"]:]
        if ids:
            lines.append("- IDs citados pelo cliente: " + ", ".join(ids))
        money = [f["v"] for f in self.of("money", "user")][-RENDER_CAPS["money"]:]
        if money:
            lines.append("- Valores citados pelo cliente: " + ", ".join(money))
        dates = [f["v"] for f in self.of("date", "user")][-RENDER_CAPS["date"]:]
        if dates:
            lines.append("- Datas citadas pelo cliente: " + ", ".join(dates))
        seen = self.of("entity")[-RENDER_CAPS["entity"]:]
        if seen:
            lines.append("- Registros vistos nas ferramentas (referência; consulte de novo o que muda): " + "; ".join(
                f"{e['v']} " + "{" + ", ".join(f"{k}={v}" for k, v in (e.get("f") or {}).items()) + "}"
                for e in seen))
        src = [f for f in self.facts if f["s"] == "source" and f["k"] == "money"][-RENDER_CAPS["source"]:]
        if src:
            lines.append("- Valores vistos em fontes: " + "; ".join(
                f"{f['v']} ({f['c']})" if f.get("c") else f["v"] for f in src))
        if not lines:
            return ""
        return ("Fatos da conversa (extraídos por código das falas do cliente e dos resultados de ferramentas; valem "
                "mesmo que o resumo os omita):\n" + "\n".join(lines))

    def digest_line(self) -> str:
        """Fatos do CLIENTE em uma linha, para o resumo rolante: ids, valores, datas e assunto nunca saem dele."""
        parts = []
        for label, kind, cap in (("ids", "id", 12), ("valores", "money", 8), ("datas", "date", 6)):
            values = [f["v"] for f in self.of(kind, "user")][-cap:]
            if values:
                parts.append(f"{label} {', '.join(values)}")
        if self.subject:
            parts.append(f"assunto: {self.subject['text'][:100]}")
        return "[fatos do cliente] " + "; ".join(parts) if parts else ""

    # --- persistência ---------------------------------------------------------------------------------------
    def dumps(self) -> str:
        return json.dumps({"v": LEDGER_VERSION, "turn": self.turn, "subject": self.subject, "facts": self.facts},
                          ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def loads(cls, raw: str | None) -> Ledger:
        try:
            data = json.loads(raw) if raw else {}
            if data.get("v") != LEDGER_VERSION:
                return cls()
            facts = [f for f in data.get("facts", []) if isinstance(f, dict) and {"k", "v", "s"} <= f.keys()]
            return cls(turn=int(data.get("turn", 0)), subject=data.get("subject"), facts=facts)
        except (ValueError, TypeError, AttributeError):
            return cls()  # livro corrompido não derruba o atendimento: recomeça (e o backfill reconstrói do cliente)


# --- extração -----------------------------------------------------------------------------------------------
def _id_patterns() -> list[re.Pattern]:
    extra = getattr(domain.active(), "ID_PATTERNS", ())
    return [re.compile(p, _FLAGS) if isinstance(p, str) else p for p in extra]


def _canon_id(raw: str) -> str:
    """TX1008/tx1008 são o mesmo id (maiúsculas); o protocolo "T-f70e7d6e" guarda a caixa em que o sistema o emitiu."""
    return raw.upper() if re.fullmatch(r"[A-Za-z]{1,4}-?\d{3,}[A-Za-z]?", raw) else raw


def ids_in(text: str) -> list[str]:
    out: list[str] = []
    for pattern in (_ID_GENERIC, _ID_LABELLED, *_id_patterns()):
        for m in pattern.finditer(text):
            value = _canon_id(m.group(1) if m.groups() else m.group(0))
            if value.upper() not in {o.upper() for o in out}:
                out.append(value)
    return out


def money_in(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(0).strip().rstrip(".,") for m in _MONEY.finditer(text)))


def dates_in(text: str) -> list[str]:
    out = list(_ISO_DATE.findall(text))
    for m in _SLASH_DATE.finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        if (1 <= a <= 31 and 1 <= b <= 12) or (1 <= b <= 31 and 1 <= a <= 12):
            out.append(m.group(0))
    return list(dict.fromkeys(out))


def _scalar(value) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str) and 0 < len(value) <= FIELD_CHARS:
        return mask_pii(value)[0]  # nome, e-mail ou documento dentro de um resultado de ferramenta não vai para o livro
    return None


def _entities(node, out: list[tuple[str, dict]]) -> None:
    """Dicts de um resultado de ferramenta com chave de id viram registros {id: campos escalares}."""
    if isinstance(node, list):
        for x in node:
            _entities(x, out)
    elif isinstance(node, dict):
        ident = next((str(node[k]) for k in node if _ID_KEY.match(k) and _scalar(node[k])), None)
        scalars = {k: s for k, v in node.items() if not _ID_KEY.match(k) and (s := _scalar(v)) is not None}
        if ident:
            out.append((ident, dict(list(scalars.items())[:ENTITY_FIELDS])))
        for v in node.values():
            if isinstance(v, (dict, list)):
                _entities(v, out)


def _json_of(text: str):
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        return None
    try:
        return json.loads(text[start:])
    except ValueError:
        return None


def extract_user(ledger: Ledger, text: str) -> None:
    for v in ids_in(text):
        ledger.add("id", v, "user")
    for v in money_in(text):
        ledger.add("money", v, "user")
    for v in dates_in(text):
        ledger.add("date", v, "user")


def extract_evidence(ledger: Ledger, evidence: list[str]) -> None:
    """Resultado de ferramenta (JSON) vira registros por id; texto de fonte/busca, valores em dinheiro com contexto."""
    free = 0
    for e in evidence:
        data = _json_of(e) if e.lstrip()[:1] in "{[" else None
        if isinstance(data, (dict, list)):
            if isinstance(data, dict) and data.get("ok") is False:
                continue
            body = data.get("data", data) if isinstance(data, dict) else data
            found: list[tuple[str, dict]] = []
            _entities(body, found)
            for ident, fields in found:
                ledger.add("entity", ident, "tool", fields=fields)
            if isinstance(body, dict):
                top = {k: s for k, v in body.items() if (s := _scalar(v)) is not None}
                if top:
                    ledger.add("entity", "resumo:" + ",".join(sorted(top)), "tool", fields=top)
            continue
        for m in _MONEY.finditer(e):
            if free >= MAX_EVIDENCE_FACTS:
                break
            value = m.group(0).strip().rstrip(".,")
            before = re.sub(r"\s+", " ", e[max(0, m.start() - 40):m.start()]).strip()
            ledger.add("money", value, "source", context=mask_pii(before[-30:])[0])
            free += 1


def record_subject(ledger: Ledger, text: str, intent: str) -> None:
    ledger.subject = {"text": text.strip()[:SUBJECT_CHARS], "intent": intent, "t": ledger.turn}


def update(ledger: Ledger, *, user_text: str, intent: str, evidence: list[str], states_subject: bool) -> Ledger:
    """Um turno: fala do cliente + evidência das ferramentas/fontes. `states_subject`: a fala define o assunto."""
    ledger.turn += 1
    extract_user(ledger, user_text)
    extract_evidence(ledger, evidence)
    if states_subject:
        record_subject(ledger, user_text, intent)
    return ledger


# --- persistência no store (aditiva: o Store sem o método segue funcionando, só sem persistir) ---------------------
def load(store, conversation_id: str) -> Ledger:
    """Livro da conversa; sem registro (conversa anterior ao livro), reconstrói das falas do CLIENTE no banco."""
    getter = getattr(store, "conversation_facts", None)
    ledger = Ledger.loads(getter(conversation_id)) if getter else Ledger()
    if not ledger.facts and ledger.turn == 0:
        for m in store.older_messages(conversation_id, skip_last=0):
            if m["role"] == "user":
                ledger.turn += 1
                extract_user(ledger, m["content"])
    return ledger


def save(store, conversation_id: str, ledger: Ledger) -> None:
    setter = getattr(store, "set_conversation_facts", None)
    if setter:
        setter(conversation_id, ledger.dumps())


# --- somas e contagens em código ------------------------------------------------------------------------------
MAX_ROWS = 500
GROUP_KEYS = ("status", "state", "method", "type", "category")
# Só coluna com cara de valor em dinheiro é somada: somar "installments" ou "last_contact_min" daria um número que
# parece resposta e não é. O domínio estende com AMOUNT_KEYS = [regex, ...] em app/domain/<ativo>.py.
_AMOUNT_KEY = re.compile(r"amount|valor|value|total|price|pre[cç]o|fee|taxa|net|gross|l[ií]quido|bruto|balance|saldo"
                         r"|cost|custo|sum", _FLAGS)
_NOT_AMOUNT = re.compile(r"(?:^|_)(?:id|code|count|year|ts|timestamp|page|offset|limit)$|^\w*code$", _FLAGS)


def _dec(value) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _money_columns(rows: list[dict]) -> dict[str, list[Decimal]]:
    cols: dict[str, list[Decimal]] = {}
    extra = [re.compile(p, _FLAGS) for p in getattr(domain.active(), "AMOUNT_KEYS", ())]
    for key in {k for r in rows for k in r}:
        if _NOT_AMOUNT.search(key) or not (_AMOUNT_KEY.search(key) or any(p.search(key) for p in extra)):
            continue
        vals = [_dec(r.get(key)) for r in rows]
        if all(v is not None for v in vals):
            cols[key] = vals  # type: ignore[assignment]
    return cols


def _fmt(value: Decimal) -> float | int:
    value = value.quantize(Decimal("0.01"))
    return int(value) if value == value.to_integral_value() else float(value)


def _summarize(rows: list[dict]) -> dict:
    cols = _money_columns(rows)
    out: dict = {"itens": len(rows)}
    if cols:
        out["soma"] = {k: _fmt(sum(v, Decimal(0))) for k, v in sorted(cols.items())}
    # Um agrupamento por chave de categoria E por chave de data: "quanto cai no dia 03/11" é soma de linhas de
    # modalidades diferentes (medido: o redator somou débito + Pix e o juiz não achou o total).
    date_keys = sorted({k for r in rows for k, v in r.items() if _DATE_KEY.search(k) and isinstance(v, str)})
    for key in (*GROUP_KEYS, *date_keys):
        groups: dict[str, list[dict]] = {}
        for r in rows:
            if isinstance(r.get(key), str):
                groups.setdefault(r[key], []).append(r)
        if 1 < len(groups) <= 8 and sum(len(g) for g in groups.values()) == len(rows):
            out[f"por_{key}"] = {name: _summarize_group(g, cols) for name, g in sorted(groups.items())}
    return out


_DATE_KEY = re.compile(r"date|data|_em$|_on$|_at$|dia", re.IGNORECASE)


def _summarize_group(rows: list[dict], cols: dict[str, list[Decimal]]) -> dict:
    out: dict = {"itens": len(rows)}
    amounts = {k: _fmt(sum((_dec(r.get(k)) or Decimal(0) for r in rows), Decimal(0))) for k in sorted(cols)}
    if amounts:
        out["soma"] = amounts
    return out


def _lists(node, path: str, out: list[tuple[str, list[dict]]]) -> None:
    if isinstance(node, list):
        rows = [x for x in node if isinstance(x, dict)]
        if rows and len(rows) == len(node):
            out.append((path or "lista", rows[:MAX_ROWS]))
    elif isinstance(node, dict):
        for k, v in node.items():
            _lists(v, f"{path}.{k}" if path else k, out)


def aggregates(result: dict) -> list[dict]:
    """Contagem e soma por coluna numérica de cada lista de objetos do resultado (e por status, se houver)."""
    found: list[tuple[str, list[dict]]] = []
    _lists(result.get("data", result) if isinstance(result, dict) else result, "", found)
    return [{"lista": path, **_summarize(rows)} for path, rows in found]


def with_aggregates(result: dict) -> dict:
    """Resultado de ferramenta + `calculado_em_codigo` (soma/contagem exatas). Sem lista, devolve o mesmo resultado."""
    if not isinstance(result, dict) or result.get("ok") is False:
        return result
    calc = aggregates(result)
    if not calc:
        return result
    return {**result, "calculado_em_codigo": calc,
            "nota_calculo": "Totais e contagens acima foram calculados em código: use-os, não some nem conte."}


# --- eval: o fato esperado apareceu na resposta? ------------------------------------------------------------------
def fact_present(fact: str, answer: str) -> bool:
    """Valor vindo de turno anterior presente na resposta: números por valor (R$ 75,00 = 75.0), o resto por texto."""
    from .grounding import numbers

    if re.search(r"\d", fact) and re.fullmatch(r"[\sR$US€£\d.,/:%-]+", fact):
        want = numbers(fact)
        return bool(want) and want <= numbers(answer)
    fold = lambda s: re.sub(r"\s+", " ", s).casefold()  # noqa: E731
    if fold(fact) in fold(answer):
        return True
    # Regex, como em `expect.facts`: com fatos escritos como "129[,.]90" e "whats ?app" e a resposta com "R$ 129,90",
    # o check literal reprovava 6 casos certos nas 3 rodadas (memória 0,67 em vez de 0,94).
    if re.search(r"[\[\]()?*+|\\{}^]", fact):
        try:
            return re.search(fact, answer, re.IGNORECASE) is not None
        except re.error:
            return False
    return False
