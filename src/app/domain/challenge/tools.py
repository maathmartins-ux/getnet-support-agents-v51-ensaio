"""Domínio do desafio — FERRAMENTAS (frente T): registro TOOLS e caminho offline do records.

Contrato lido pelo motor: TOOLS, ELIGIBLE_STATUS, records(), users(), records_offline(), needs_for().
Teste em tests/test_tools.py. Toda conta (total, contagem, data de depósito, dia útil, significado do código de
recusa) é feita AQUI; o LLM só lê o resultado.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from functools import lru_cache

from app import clock
from app.config import data_dir

# --- adaptador do CRM -----------------------------------------------------------------------------------------


@lru_cache(maxsize=4)
def _crm(path: str) -> dict:
    return json.loads(open(path, encoding="utf-8").read())


def records() -> dict:
    """Adaptador do sistema de registro: hoje data/crm/merchants.json; em produção, a API do CRM."""
    return {k: v for k, v in _crm(str(data_dir() / "crm" / "merchants.json")).items() if not k.startswith("_")}


def users() -> list[str]:
    """Usuários de teste do login: os clientes do CRM."""
    return sorted(records())


def _merchant(user_id: str) -> dict:
    return records().get(user_id) or {"terminals": [], "transactions": []}


# --- datas relativas e dia útil ---------------------------------------------------------------------------------


def _today() -> date:
    return clock.today()  # dia do cliente (fuso do negócio), o mesmo do prompt e do dado ao vivo


def _business(d: date) -> date:
    while d.weekday() >= 5:  # sábado/domingo → próximo dia útil (feriados: fora do CRM de teste)
        d += timedelta(days=1)
    return d


def _add_business_days(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _relative(d: date) -> dict:
    delta = (d - _today()).days
    pt = {0: "hoje", 1: "amanhã", -1: "ontem"}.get(delta, f"em {delta} dias" if delta > 0 else f"há {-delta} dias")
    en = {0: "today", 1: "tomorrow", -1: "yesterday"}.get(delta,
                                                          f"in {delta} days" if delta > 0 else f"{-delta} days ago")
    return {"date": d.isoformat(), "relative_pt": pt, "relative_en": en}


# Regra de liquidação do CRM de teste: Pix D+0, débito D+1 dia útil, crédito D+30 (ajustado ao próximo dia útil).
def _deposit_date(sale: date, method: str) -> date:
    if method == "pix":
        return sale
    if method == "debito":
        return _add_business_days(sale, 1)
    return _business(sale + timedelta(days=30))


METHOD_LABEL = {"debito": ("débito", "debit"), "credito": ("crédito", "credit"), "pix": ("Pix", "Pix")}

# Significado dos códigos de recusa; o LLM não converte código, a tool devolve o texto.
DECLINE_CODES = {
    "51": {"pt": "saldo ou limite insuficiente no cartão do cliente",
           "en": "insufficient funds or credit limit on the customer's card",
           "action_pt": "peça outro cartão ou outra forma de pagamento",
           "action_en": "ask for another card or payment method"},
    "05": {"pt": "transação não autorizada pelo banco emissor (genérica)",
           "en": "transaction not authorized by the issuing bank (generic)",
           "action_pt": "o portador deve contatar o banco emissor; tente outro cartão",
           "action_en": "the cardholder should contact the issuing bank; try another card"},
    "14": {"pt": "número de cartão inválido", "en": "invalid card number",
           "action_pt": "confira o cartão e tente de novo", "action_en": "check the card and try again"},
}
_UNKNOWN_CODE = {"pt": "código não catalogado", "en": "uncatalogued code", "action_pt": "", "action_en": ""}


def _money(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# --- ferramentas ---------------------------------------------------------------------------------------------
# Contrato: argumentos do schema + `user_id` (do servidor, nunca do schema) → {ok, data} | {ok: False, error}.
# Registro de outro cliente e inexistente devolvem a MESMA resposta: not_found.
# Mesmo enum, padrão diferente por consulta (o código de cada tool usa o seu): o schema diz o padrão de cada uma,
# senão o modelo lia o padrão de recebimentos (ontem) também nas vendas (7 dias) e consultava o período errado.
_PERIODS = ["yesterday", "today", "last_7_days"]
_PERIOD_SETTLEMENTS = {"type": "string", "enum": _PERIODS, "default": "yesterday",
                       "description": "Período dos recebimentos (padrão: yesterday)"}
_PERIOD_TX = {"type": "string", "enum": _PERIODS, "default": "last_7_days",
              "description": "Período das vendas (padrão: last_7_days)"}
_METHOD = {"type": "string", "enum": ["debito", "credito", "pix"], "description": "Forma de pagamento"}
_TX_ID = {"type": "string", "pattern": r"^TX\d{4}$", "description": "Id da transação (ex.: TX1007)"}
_TERM_ID = {"type": "string", "pattern": r"^T\d{4}[A-Z]$", "description": "Id do terminal (ex.: T1988A)"}


def _in_period(days_ago: int, period: str) -> bool:
    return {"today": days_ago == 0, "yesterday": days_ago == 1}.get(period, 0 <= days_ago <= 7)


def _get_settlements(user_id: str, period: str = "yesterday", method: str | None = None) -> dict:
    sales = [t for t in _merchant(user_id)["transactions"] if t["status"] == "aprovada"
             and _in_period(t["days_ago"], period) and (method is None or t["method"] == method)]
    groups: dict[tuple, dict] = {}
    for t in sales:
        sale = _today() - timedelta(days=t["days_ago"])
        dep = _deposit_date(sale, t["method"])
        g = groups.setdefault((t["method"], dep), {
            "method": t["method"], "method_pt": METHOD_LABEL[t["method"]][0],
            "method_en": METHOD_LABEL[t["method"]][1], "count": 0, "total": 0.0, "sale_date": _relative(sale),
            "deposit_date": _relative(dep), "status": "pago" if dep <= _today() else "agendado"})
        g["count"] += 1
        g["total"] = round(g["total"] + t["amount"], 2)
    items = sorted(groups.values(), key=lambda g: g["deposit_date"]["date"])
    for g in items:
        g["total_brl"] = _money(g["total"])
    total = round(sum(g["total"] for g in items), 2)
    return {"ok": True, "data": {"period": period, "items": items, "count": sum(g["count"] for g in items),
                                 "total": total, "total_brl": _money(total),
                                 "rule": "Pix D+0, débito D+1 dia útil, crédito D+30 (próximo dia útil)"}}


def _get_transactions(user_id: str, status: str = "all", transaction_id: str | None = None,
                      period: str = "last_7_days") -> dict:
    txs = _merchant(user_id)["transactions"]
    if transaction_id:
        txs = [t for t in txs if t["transaction_id"] == transaction_id]
        if not txs:  # inexistente e de outro cliente: mesma resposta
            return {"ok": False, "error": "not_found"}
    else:
        txs = [t for t in txs if _in_period(t["days_ago"], period)]
    if status != "all":
        txs = [t for t in txs if t["status"] == {"approved": "aprovada", "declined": "recusada"}[status]]
    items = []
    for t in txs:
        item = {k: v for k, v in t.items() if k != "days_ago"}
        item["date"] = _relative(_today() - timedelta(days=t["days_ago"]))
        item["amount_brl"] = _money(t["amount"])
        item["method_pt"], item["method_en"] = METHOD_LABEL[t["method"]]
        if t.get("decline_code"):
            item["decline_meaning"] = DECLINE_CODES.get(t["decline_code"], _UNKNOWN_CODE)
        items.append(item)
    declined = [i for i in items if i["status"] == "recusada"]
    data = {"items": items, "count": len(items), "declined_count": len(declined),
            "approved_count": len(items) - len(declined),
            "approved_total": round(sum(i["amount"] for i in items if i["status"] == "aprovada"), 2),
            "declined_total": round(sum(i["amount"] for i in declined), 2)}
    data["approved_total_brl"] = _money(data["approved_total"])
    data["declined_total_brl"] = _money(data["declined_total"])
    out = {"ok": True, "data": data}
    if declined:
        out["needs"] = [dict(NEED_DECLINE)]
    return out


def _get_terminal_status(user_id: str, terminal_id: str | None = None) -> dict:
    terms = _merchant(user_id)["terminals"]
    if terminal_id:
        terms = [t for t in terms if t["terminal_id"] == terminal_id]
        if not terms:
            return {"ok": False, "error": "not_found"}
    now = clock.now().replace(microsecond=0, second=0)
    items = []
    for t in terms:
        item = {k: v for k, v in t.items() if k != "last_contact_hours_ago"}
        h = t["last_contact_hours_ago"]
        item["last_contact"] = (now - timedelta(hours=h)).isoformat(timespec="minutes")
        if t["status"] == "offline":  # online não leva o campo: com 0 o LLM escrevia "offline há 0 hora"
            item["offline_for_hours"] = h
        items.append(item)
    offline = [i["terminal_id"] for i in items if i["status"] == "offline"]
    out = {"ok": True, "data": {"items": items, "count": len(items), "online_count": len(items) - len(offline),
                                "offline_count": len(offline), "offline": offline}}
    if offline:
        out["needs"] = [dict(NEED_CONNECTION)]
    return out


def _request_advance(user_id: str, method: str = "credito") -> dict:
    found = _get_settlements(user_id, "last_7_days", method)
    sched = [g for g in found["data"]["items"] if g["status"] == "agendado"]
    if not sched:
        return {"ok": False, "error": "not_found"}
    total = round(sum(g["total"] for g in sched), 2)
    before = {"method": method, "status": "agendado", "total": total}
    return {"ok": True, "data": {"status": "antecipacao_solicitada", "total": total, "total_brl": _money(total),
                                 "before": before, "after": {**before, "status": "antecipacao_solicitada"}}}


def _open_ticket(user_id: str, terminal_id: str, reason: str = "sem_conexao") -> dict:
    found = _get_terminal_status(user_id, terminal_id)
    if not found["ok"]:
        return found
    before = {"terminal_id": terminal_id, "ticket": None}
    ticket = f"CH-{terminal_id}-{_today().strftime('%Y%m%d')}"
    return {"ok": True, "data": {"ticket_id": ticket, "terminal_id": terminal_id, "reason": reason,
                                 "status": "aberto", "before": before, "after": {**before, "ticket": ticket}}}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


TOOLS = {
    "get_settlements": {"description": "Agenda de depósitos das vendas aprovadas do cliente autenticado: datas de "
                                       "depósito (dia útil), totais e contagens já calculados.", "write": False,
                        "input_schema": _obj({"period": _PERIOD_SETTLEMENTS, "method": _METHOD}),
                        "fn": _get_settlements},
    "get_transactions": {"description": "Vendas e recusas do cliente autenticado, com o significado do código de "
                                        "recusa, contagens e totais calculados.", "write": False,
                         "input_schema": _obj({"status": {"type": "string", "enum": ["all", "approved", "declined"]},
                                               "transaction_id": _TX_ID, "period": _PERIOD_TX}),
                         "fn": _get_transactions},
    "get_terminal_status": {"description": "Terminais do cliente autenticado: conexão, sinal, último contato e há "
                                           "quanto tempo está offline.", "write": False,
                            "input_schema": _obj({"terminal_id": _TERM_ID}), "fn": _get_terminal_status},
    # risco alto: mexe em dinheiro → confirmação do dono E aprovação de um operador (actions.py)
    "request_receivables_advance": {"description": "Solicita antecipação dos recebíveis agendados. Exige confirmação "
                                                   "do cliente e aprovação de um atendente.", "write": True,
                                    "risk": "high", "input_schema": _obj({"method": _METHOD}),
                                    "fn": _request_advance},
    "open_support_ticket": {"description": "Abre chamado técnico para um terminal do cliente. Exige confirmação.",
                            "write": True,
                            "input_schema": _obj({"terminal_id": _TERM_ID,
                                                  "reason": {"type": "string",
                                                             "enum": ["sem_conexao", "sem_sinal", "erro_transacao",
                                                                      "outro"]}}, ["terminal_id"]),
                            "fn": _open_ticket},
}
# Palavras que o cliente lê no lugar dos valores internos das tools (app/capabilities.label): o cartão de capacidades e
# a resposta final mostram estas, nunca "sem_sinal" ou o nome da tool.
LABELS = {
    "sem_conexao": {"pt": "sem conexão", "en": "no connection"},
    "sem_sinal": {"pt": "sem sinal", "en": "no signal"},
    "erro_transacao": {"pt": "erro de transação", "en": "transaction error"},
    "outro": {"pt": "outro", "en": "other"},
    "last_7_days": {"pt": "últimos 7 dias", "en": "last 7 days"},
    "yesterday": {"pt": "ontem", "en": "yesterday"},
    "today": {"pt": "hoje", "en": "today"},
    "debito": {"pt": "débito", "en": "debit"},
    "credito": {"pt": "crédito", "en": "credit"},
    "reason": {"pt": "motivo", "en": "reason"},
    "period": {"pt": "período", "en": "period"},
    "request_receivables_advance": {"pt": "antecipação dos recebíveis", "en": "receivables advance"},
    "open_support_ticket": {"pt": "chamado técnico", "en": "support ticket"},
}
# Escrita → status do item em que faz sentido: só antecipa o que ainda está agendado; chamado para terminal offline.
ELIGIBLE_STATUS: dict[str, set[str]] = {"request_receivables_advance": {"agendado"},
                                        "open_support_ticket": {"offline"}}

# --- achados que pedem o Knowledge (replanejamento por ACHADO) -------------------------------------------------
NEED_CONNECTION = {"agent": "faq", "why": "terminal offline/sem sinal: o passo a passo vem do manual de conexão",
                   "hint": "manual de conexão da maquininha: chip, Wi-Fi, sinal"}
NEED_DECLINE = {"agent": "faq", "why": "transação recusada: a orientação vem do Knowledge",
                "hint": "transação recusada: orientação ao lojista"}
_SYMPTOM = re.compile(r"(n[aã]o (conecta|liga)|sem sinal|offline|erro|recus|negad|won'?t|no signal|declin|losing|"
                      r"reconnect|fix|what should|o que (eu )?fa[cç]o|resolv|evit|what now|significa|mean|why|"
                      r"por ?que|houve|ajuda|error)", re.IGNORECASE)


def needs_for(result, ctx) -> list[dict]:
    """Deriva needs dos resultados de tool do records (caminho com LLM): só com sintoma na pergunta."""
    if result.agent != "records" or not _SYMPTOM.search(ctx.text):
        return []
    found: list[dict] = []
    for item in result.evidence:
        try:
            data = json.loads(item)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("needs"):  # de TODOS os resultados (terminal E transação)
            found += [dict(n) for n in data["needs"]]
    return found


# --- caminho offline do agente records (sem LLM) ----------------------------------------------------------------
_TERM = re.compile(r"\b(T\d{4}[A-Z])\b", re.IGNORECASE)
_TXR = re.compile(r"\b(TX\d{4})\b", re.IGNORECASE)
_ADVANCE = re.compile(r"(antecip|advance)", re.IGNORECASE)
_TICKET = re.compile(r"(chamado|ticket)", re.IGNORECASE)
_TERMINAL_Q = re.compile(r"(terminal|maquininha|m[aá]quina|machine|reader|get smart|get cl[aá]ssica|conect|connect|"
                         r"wi-?fi|sinal|signal|chip|online|offline|fora|down)", re.IGNORECASE)
_TX_Q = re.compile(r"(recus|negad|declin|c[oó]digo|code|erro|error|transa|valor|amount)", re.IGNORECASE)
_OTHER = re.compile(r"\b(outr[oa]|other|segund[oa]|second)\b", re.IGNORECASE)
_DEBIT, _CREDIT = re.compile(r"d[eé]bit", re.IGNORECASE), re.compile(r"cr[eé]dit", re.IGNORECASE)


def _context_text(ctx) -> str:
    return " ".join([*(m["content"] for m in ctx.history[-4:]), ctx.facts.get("standalone") or ""])


def _norm(s: str) -> str:
    return s.lower().replace("á", "a")


def _offline_terminals(ctx, a, calls, ev) -> str:
    t = a._t
    text = ctx.facts.get("standalone") or ctx.text
    tid = (_TERM.search(text) or [None, None])[1]
    result, call = a.run_tool("get_terminal_status", {"terminal_id": tid.upper()} if tid else {}, ctx.user_id,
                              ctx.conversation_id)
    calls.append(call)
    ev.append(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        return t(ctx, f"Não encontrei o terminal {tid} na sua conta.",
                 f"I couldn't find terminal {tid} in your account.")
    items = result["data"]["items"]
    if not tid:
        model = re.search(r"get (smart|cl[aá]ssica)", ctx.text, re.IGNORECASE)
        if model:
            items = [i for i in items if _norm(model.group(1)) in _norm(i["model"])] or items
        elif _OTHER.search(ctx.text):  # "e o outro/segundo?": o terminal não citado na resposta anterior
            prev = {m.upper() for m in _TERM.findall(_context_text(ctx))}
            items = [i for i in items if i["terminal_id"] not in prev] or items[1:] or items
    pt, en = [], []
    for i in items:
        if i["status"] == "offline":
            pt.append(f"{i['terminal_id']} ({i['model']}, {i['connection']}) está offline, {i['signal']}, "
                      f"há {i['offline_for_hours']} h (último contato {i['last_contact']})")
            en.append(f"{i['terminal_id']} ({i['model']}, {i['connection']}) is offline with no signal for "
                      f"{i['offline_for_hours']} h (last contact {i['last_contact']})")
        else:
            pt.append(f"{i['terminal_id']} ({i['model']}, {i['connection']}) está online")
            en.append(f"{i['terminal_id']} ({i['model']}, {i['connection']}) is online")
    return t(ctx, "; ".join(pt) + ".", "; ".join(en) + ".")


def _offline_transactions(ctx, a, calls, ev) -> str:
    t = a._t
    text = ctx.facts.get("standalone") or ctx.text
    txid = (_TXR.search(text) or [None, None])[1]
    args = {"transaction_id": txid.upper()} if txid else {"status": "declined"}
    result, call = a.run_tool("get_transactions", args, ctx.user_id, ctx.conversation_id)
    calls.append(call)
    ev.append(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        return t(ctx, f"Não encontrei a transação {txid} na sua conta.",
                 f"I couldn't find transaction {txid} in your account.")
    items = result["data"]["items"]
    code = re.search(r"\b(?:c[oó]digo|code)\s*(\d{2})\b", ctx.text, re.IGNORECASE)
    if code:
        items = [i for i in items if i.get("decline_code") == code.group(1)] or items
    elif _DEBIT.search(ctx.text) and not txid:
        items = [i for i in items if i["method"] == "debito"] or items
    if not items:
        return t(ctx, "Não há vendas recusadas no período.", "There are no declined sales in the period.")
    pt, en = [], []
    for i in items:
        m = i.get("decline_meaning") or {}
        code_pt = f"recusada com código {i['decline_code']}: {m.get('pt')}; {m.get('action_pt')}"
        code_en = f"declined with code {i['decline_code']}: {m.get('en')}; {m.get('action_en')}"
        pt.append(f"{i['transaction_id']} ({i['method_pt']}, {i['amount_brl']}, {i['date']['relative_pt']}) "
                  + (code_pt if i.get("decline_code") else "aprovada"))
        en.append(f"{i['transaction_id']} ({i['method_en']}, {i['amount_brl']}, {i['date']['relative_en']}) "
                  + (code_en if i.get("decline_code") else "approved"))
    n = len(items)
    return t(ctx, f"{n} venda(s): " + "; ".join(pt) + ".", f"{n} sale(s): " + "; ".join(en) + ".")


def _offline_settlements(ctx, a, calls, ev) -> str:
    t = a._t
    method = "debito" if _DEBIT.search(ctx.text) else "credito" if _CREDIT.search(ctx.text) else None
    result, call = a.run_tool("get_settlements", {"period": "yesterday", **({"method": method} if method else {})},
                              ctx.user_id, ctx.conversation_id)
    calls.append(call)
    ev.append(json.dumps(result, ensure_ascii=False))
    d = result["data"]
    if not d["items"]:
        return t(ctx, "Não há vendas aprovadas ontem.", "There were no approved sales yesterday.")
    pt = [f"{g['method_pt']}: {g['total_brl']} ({g['count']} venda(s)) cai em {g['deposit_date']['date']} "
          f"({g['deposit_date']['relative_pt']})" for g in d["items"]]
    en = [f"{g['method_en']}: {g['total_brl']} ({g['count']} sale(s)) deposited on {g['deposit_date']['date']} "
          f"({g['deposit_date']['relative_en']})" for g in d["items"]]
    return t(ctx, f"Vendas de ontem, total {d['total_brl']}: " + "; ".join(pt) + ".",
             f"Yesterday's sales, total {d['total_brl']}: " + "; ".join(en) + ".")


def _offline_write(ctx, a, calls, ev):
    AgentResult, run_tool, t = a.AgentResult, a.run_tool, a._t
    text = ctx.text
    if _ADVANCE.search(text):
        tool, args = "request_receivables_advance", {"method": "credito"}
        what_pt, what_en = "antecipar os recebíveis de crédito agendados", "advance your scheduled credit receivables"
    else:
        status, call = run_tool("get_terminal_status", {}, ctx.user_id, ctx.conversation_id)
        calls.append(call)
        ev.append(json.dumps(status, ensure_ascii=False))
        tid = (_TERM.search(text) or [None, None])[1]
        if not tid:
            off = a.latest_eligible((status.get("data") or {}).get("items", []), "open_support_ticket")
            tid = off["terminal_id"] if off else None
        if not tid:
            return AgentResult("records", "ok", tool_calls=calls, evidence=ev,
                               text=t(ctx, "Qual terminal? Nenhum está offline.", "Which terminal? None is offline."))
        tid = tid.upper()
        tool, args = "open_support_ticket", {"terminal_id": tid, "reason": "sem_conexao"}
        what_pt = f"abrir um chamado técnico para o terminal {tid}"
        what_en = f"open a support ticket for terminal {tid}"
    result, call = run_tool(tool, args, ctx.user_id, ctx.conversation_id)
    calls.append(call)
    ev.append(json.dumps(result, ensure_ascii=False))
    if result.get("needs_confirmation"):
        aid = result["action_id"]
        high = result.get("risk") == "high"
        extra_pt = " Depois da sua confirmação, um atendente aprova." if high else ""
        extra_en = " After you confirm, a human agent approves it." if high else ""
        return AgentResult("records", "ok", tool_calls=calls, pending_action=aid, evidence=ev,
                           text=t(ctx, f"Para {what_pt}, confirme a ação {aid}.{extra_pt} Nada foi feito ainda.",
                                  f"To {what_en}, confirm action {aid}.{extra_en} Nothing has been done yet."))
    return AgentResult("records", "error", tool_calls=calls, reason="tool_error", evidence=ev)


def records_offline(ctx, a):
    """Atendimento determinístico do agente records. `a` = módulo app.agents (AgentResult, run_tool, _t...)."""
    AgentResult = a.AgentResult
    calls: list = []
    ev: list[str] = []
    text = ctx.text
    if _ADVANCE.search(text) or _TICKET.search(text):
        return _offline_write(ctx, a, calls, ev)
    probe = f"{text} {ctx.facts.get('standalone') or ''}"
    if _TERM.search(probe) or (_TERMINAL_Q.search(probe) and not _TX_Q.search(text)):
        answer = _offline_terminals(ctx, a, calls, ev)
    elif _TXR.search(probe) or _TX_Q.search(probe):
        answer = _offline_transactions(ctx, a, calls, ev)
    else:
        answer = _offline_settlements(ctx, a, calls, ev)
    last = json.loads(ev[-1])
    if not last.get("ok"):
        return AgentResult("records", "ok", tool_calls=calls, evidence=ev, facts={"record_not_found": True},
                           text=answer)
    needs = [dict(n) for n in last.get("needs", [])] if _SYMPTOM.search(text) else []
    return AgentResult("records", "ok", tool_calls=calls, evidence=ev, needs=needs, text=answer)
