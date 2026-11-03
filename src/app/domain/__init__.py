"""Pacote de domínio: TUDO o que muda de um desafio para outro mora aqui, nunca no motor.

Por quê: quando o domínio editou router.py, supervisor.py, tools.py e agents.py no relógio;
59 testes do kit, que dependiam do código de exemplo, quebraram, e o CI ficou vermelho do primeiro ao último
commit. Agora o motor (router, supervisor, agents, actions, tools) lê o domínio ATIVO em tempo de chamada:

- `example`  : o domínio de exemplo do kit (loja: pedidos, prazo de entrega). Os testes do kit SEMPRE usam este
               (tests/conftest.py fixa DOMAIN=example antes de importar qualquer módulo).
- `challenge`: o domínio do desafio, criado pelo pré-voo (`scripts/preflight.py`) como cópia de `example.py` e
               editado no relógio. Testes do domínio usam a fixture `domain_data` (DOMAIN=challenge).

Escolha: env DOMAIN; sem env, `challenge` se o módulo existir, senão `example`.
Contrato de um módulo de domínio (ver `example.py`): PLANS, FALLBACK, ALLOWED, DEPENDS, NO_ESCALATION,
DEFAULT_INTENT, MULTI_PARTS, MIN_SCORE, TOOLS, ELIGIBLE_STATUS, PROMPTS_DIR, clause_intent(), states_subject(),
combine(), records_offline(). Opcional: needs_for(result, ctx) (achado → outro especialista; ver example.py),
RISK_POLICY (limite de valor por ação; ver app/risk.py), SPECIALTY_BY_AGENT/SPECIALTY_BY_INTENT (app/routing.py).
"""
from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
from types import ModuleType

KIT_PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


def name() -> str:
    explicit = os.getenv("DOMAIN")
    if explicit:
        return explicit
    return "challenge" if importlib.util.find_spec(f"{__name__}.challenge") else "example"


def active() -> ModuleType:
    """O módulo do domínio ativo (importado uma vez; trocar DOMAIN entre chamadas troca o módulo)."""
    return importlib.import_module(f"{__name__}.{name()}")


CONTRACT = KIT_PROMPTS / "contract"


def prompt(file: str) -> str:
    """Prompt do domínio ativo; cai no prompt do kit se o domínio não tiver o arquivo.

    Prompt do DOMÍNIO ganha no fim o contrato do motor (prompts/contract/<file>): as regras de que o código depende
    (NOT_IN_SOURCES/MISSING, standalone, search_queries, partial). Medido: um domínio trocou o faq.md, o
    router.md e o supervisor.md do kit pelos seus e as três respostas (ok/partial/insufficient) nem rodaram — o
    redator recebeu o trecho do fato e escreveu "as fontes não dizem". O prompt do kit já traz o contrato no texto.
    """
    from ..observability import record_prompt

    own = Path(getattr(active(), "PROMPTS_DIR", None) or KIT_PROMPTS) / file
    if not own.exists() or own.resolve() == (KIT_PROMPTS / file).resolve():
        text = (KIT_PROMPTS / file).read_text(encoding="utf-8")
    else:
        text = own.read_text(encoding="utf-8")
        contract = CONTRACT / file
        if contract.exists() and "Regras do motor" not in text:
            text = text.rstrip("\n") + "\n" + contract.read_text(encoding="utf-8")
    record_prompt(file, text)  # o texto FINAL (domínio + contrato) é a versão que o modelo leu
    return text
