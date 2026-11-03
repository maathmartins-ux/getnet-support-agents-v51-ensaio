"""Roteamento de casos por especialidade do operador.

Por quê: com uma fila única, quem entende de antecipação pega um caso de maquininha e o caso certo espera. Regras:
- o caso nasce com uma ESPECIALIDADE: a do agente que falhou (motivo "<agente>_<status>", ex. records_tool_error →
  records) ou, sem agente, a da intenção do turno; o domínio traduz (SPECIALTY_BY_AGENT, SPECIALTY_BY_INTENT; ex.
  Getnet: {"records": "conta", "knowledge": "produto"}). Aprovação de ação de risco: especialidade "approval";
- o operador tem especialidades: OPERATOR_SKILLS="ana:records|approval,bruno:faq" (ambiente) e, por cima, o que
  estiver gravado no banco (PUT /operators/{nome}/skills, auditado);
- a fila de cada operador (GET /handoffs) mostra primeiro os casos da especialidade dele e os re-roteados para
  qualquer um; os outros vêm depois (ninguém fica sem ver nada, só a ordem muda). Qualquer operador pode responder
  qualquer caso: roteamento é ordem, não permissão;
- SLA vencido (store.escalate_overdue): o caso sobe para prioridade alta e `routed_to = "any"`, aparecendo no topo
  da fila de TODOS, com linha "ticket_rerouted" na auditoria. A criação grava "ticket_routed".
"""
from __future__ import annotations

import os

from . import domain

APPROVAL = "approval"


def _domain_map(name: str) -> dict[str, str]:
    return dict(getattr(domain.active(), name, None) or {})


def specialty_for(intent: str | None, reason: str | None) -> str:
    """Especialidade do caso a partir do motivo (agente que falhou) e da intenção."""
    from .agents import AGENTS

    agent = (reason or "").split("_", 1)[0]
    if agent in AGENTS and agent != "escalation":
        return _domain_map("SPECIALTY_BY_AGENT").get(agent, agent)
    intent = intent or "general"
    return _domain_map("SPECIALTY_BY_INTENT").get(intent, intent)


def approval_specialty() -> str:
    return _domain_map("SPECIALTY_BY_AGENT").get(APPROVAL, APPROVAL)


def _env_skills() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for item in os.getenv("OPERATOR_SKILLS", "").split(","):
        name, _, skills = item.partition(":")
        if name.strip():
            out[name.strip()] = sorted({s.strip() for s in skills.split("|") if s.strip()})
    return out


def skills_of(operator: str) -> list[str]:
    from .store import get_store

    stored = get_store().operator_skills()
    return stored[operator] if operator in stored else _env_skills().get(operator, [])


def all_skills() -> dict[str, list[str]]:
    from .store import get_store

    return {**_env_skills(), **get_store().operator_skills()}


def lane(ticket: dict, skills: list[str]) -> str:
    """own (da especialidade do operador) | any (re-roteado pelo SLA) | other."""
    if ticket.get("routed_to") == "any":
        return "any"
    return "own" if ticket.get("specialty") in skills else "other"


def queue_for(operator: str, tickets: list[dict]) -> list[dict]:
    """Fila do operador: re-roteados e da especialidade primeiro; dentro de cada faixa, prioridade alta e o mais
    antigo primeiro (a ordem do store)."""
    skills = skills_of(operator)
    rank = {"any": 0, "own": 0, "other": 1}
    annotated = [{**t, "lane": lane(t, skills)} for t in tickets]
    return sorted(annotated, key=lambda t: (rank[t["lane"]], t.get("priority") != "high", t.get("created_at", 0)))
