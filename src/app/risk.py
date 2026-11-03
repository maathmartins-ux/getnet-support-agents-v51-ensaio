"""Política de risco por ação com limite de VALOR: quem precisa aprovar depende de quanto a ação move.

Por quê: `risk: "high"` fixo manda toda antecipação ao operador, até a de R$ 10, e a fila humana vira gargalo; sem
limite, a de R$ 500 mil sai só com o clique do cliente. Regra (por ferramenta de escrita):
- valor <= `four_eyes_above` → só a confirmação do dono (risco "normal");
- valor  > `four_eyes_above` → dono confirma E um operador aprova (risco "high", quatro olhos, actions.py);
- valor  > `block_above` (opcional) → nada é proposto: o atendimento explica e oferece o humano;
- valor desconhecido (argumento ausente ou não numérico) → "high": na dúvida, quatro olhos.
Sem política para a ferramenta, vale o `risk` fixo dela (comportamento anterior).

Domínio: `RISK_POLICY = {"anticipate": {"amount": "amount", "four_eyes_above": 5000, "block_above": 200000,
"currency": "R$"}}` — `amount` é o nome do argumento ou uma função (args, user_id) -> float | None (ex.: valor do
registro consultado). Ambiente: RISK_LIMITS="anticipate:3000,refund:500" troca o `four_eyes_above` sem mexer no
domínio. A regra entra na DESCRIÇÃO da ferramenta (o modelo e o cliente MCP leem o mesmo limite que o código aplica).
"""
from __future__ import annotations

import os

from . import domain


def _env_limits() -> dict[str, float]:
    out: dict[str, float] = {}
    for item in os.getenv("RISK_LIMITS", "").split(","):
        name, _, value = item.partition(":")
        try:
            out[name.strip()] = float(value)
        except ValueError:
            continue
    return out


def policy(name: str) -> dict | None:
    """Política efetiva da ferramenta (domínio + RISK_LIMITS); None = sem limite de valor."""
    base = dict((getattr(domain.active(), "RISK_POLICY", None) or {}).get(name) or {})
    env = _env_limits()
    if name in env:
        base["four_eyes_above"] = env[name]
    return base if "four_eyes_above" in base else None


def amount_of(rule: dict, args: dict, user_id: str) -> float | None:
    source = rule.get("amount", "amount")
    try:
        raw = source(args, user_id) if callable(source) else args.get(source)
        return None if raw is None or isinstance(raw, bool) else float(raw)
    except (TypeError, ValueError):
        return None


def classify(name: str, tool: dict, args: dict, user_id: str) -> dict:
    """{"risk": normal|high|blocked, "amount", "four_eyes_above", "block_above"} para ESTA proposta."""
    rule = policy(name)
    if rule is None:
        return {"risk": tool.get("risk", "normal")}
    value = amount_of(rule, args, user_id)
    limit, block = float(rule["four_eyes_above"]), rule.get("block_above")
    if value is not None and block is not None and value > float(block):
        risk = "blocked"
    else:
        risk = "normal" if value is not None and value <= limit else "high"
    out = {"risk": risk, "amount": value, "four_eyes_above": limit}
    if block is not None:
        out["block_above"] = float(block)
    return out


def _money(value: float, currency: str) -> str:
    whole = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{currency} {whole}".strip()


def describe(name: str, tool: dict) -> str:
    """Descrição da ferramenta com a regra de aprovação por valor (texto da capacidade)."""
    rule = policy(name)
    if rule is None:
        return tool["description"]
    cur = rule.get("currency", "R$")
    text = (f"{tool['description']} Aprovação por valor: até {_money(float(rule['four_eyes_above']), cur)}, só a "
            f"confirmação do cliente; acima disso, confirmação do cliente e aprovação de um atendente (quatro olhos)")
    if rule.get("block_above") is not None:
        text += f"; acima de {_money(float(rule['block_above']), cur)}, não é feito por aqui (atendimento humano)"
    return text + "."
