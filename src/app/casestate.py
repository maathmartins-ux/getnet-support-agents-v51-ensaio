"""Estado do caso de suporte que só fecha com PROVA.

Um problema do cliente (ex.: "a maquininha não conecta") é um caso com estado, não uma pergunta solta:

    in_progress → awaiting_customer → resolved | escalated

- `awaiting_customer`: o sistema respondeu e espera o cliente dizer se funcionou. "Obrigado", "ok" e "entendi"
  NÃO resolvem nada (resolver por cortesia esconde o problema e infla a taxa de resolução automática).
- `resolved` só com prova: `customer_confirmed` (o cliente diz que funcionou) ou `tool_verified` (o domínio
  oferece `tool_confirms_resolution(tool_calls)` e uma ferramenta mostra o problema resolvido).
- Cada resposta registra os passos tentados; o agente recebe a lista e não repete o mesmo conselho.
- Dois ciclos em que o cliente diz que continua com o problema → humano, com as tentativas anexadas ao caso
  (`CASE_MAX_CYCLES`, padrão 2). HITL que "devolve ao agente" e memória que não repete.

Só vale para as intenções em `CASE_INTENTS` do domínio (padrão: "troubleshoot"). Mesmo banco do store.
"""
from __future__ import annotations

import json
import os
import re
import time

from . import cases, domain

DEFAULT_INTENTS = frozenset({"troubleshoot"})

_FOLD = re.compile(r"[^a-z0-9]+")
_RESOLVED = re.compile(
    r"\b(funcionou|resolveu|resolvido|deu certo|voltou a funcionar|ja (esta|ta) (funcionando|online|conectad\w+)"
    r"|consegui|it works|it worked|that fixed|fixed it|solved|working now|working again|got it working)\b")
_STILL = re.compile(
    r"\b(ainda nao|continua(m)?|nao funcionou|nao resolveu|nao adiantou|mesmo erro|segue (igual|sem)"
    r"|still (not|no|offline|failing|broken|the same)|didn t work|did not work|not working|same error|no luck)\b")


def _fold(text: str) -> str:
    import unicodedata

    plain = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return " " + _FOLD.sub(" ", plain).strip() + " "


def max_cycles() -> int:
    return max(1, int(os.getenv("CASE_MAX_CYCLES", "2")))


def case_intents() -> frozenset[str]:
    return frozenset(getattr(domain.active(), "CASE_INTENTS", DEFAULT_INTENTS))


def confirms_resolved(text: str) -> bool:
    t = _fold(text)
    return bool(_RESOLVED.search(t)) and not _STILL.search(t)


def reports_still_broken(text: str) -> bool:
    return bool(_STILL.search(_fold(text)))


def get(conversation_id: str) -> dict | None:
    with cases._db() as conn:
        row = conn.execute("SELECT * FROM case_state WHERE conversation_id = ?", (conversation_id,)).fetchone()
    if not row:
        return None
    return {"state": row["state"], "cycles": row["cycles"], "steps": json.loads(row["steps"]), "proof": row["proof"]}


def _save(conversation_id: str, state: str, cycles: int, steps: list[dict], proof: str | None = None) -> None:
    with cases._db() as conn:
        conn.execute("INSERT INTO case_state (conversation_id, state, cycles, steps, proof, updated_at) "
                     "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (conversation_id) DO UPDATE SET state = excluded.state, "
                     "cycles = excluded.cycles, steps = excluded.steps, proof = excluded.proof, "
                     "updated_at = excluded.updated_at",
                     (conversation_id, state, cycles, json.dumps(steps, ensure_ascii=False), proof, time.time()))


def observe(conversation_id: str, text: str) -> str | None:
    """A mensagem do cliente muda o caso que espera resposta dele? Devolve a ação ou None.

    "resolved": cliente confirmou. "another_cycle": continua com o problema, ainda há tentativas.
    "escalate": continua pela 2ª vez (ou `CASE_MAX_CYCLES`): o pipeline abre o caso humano.
    """
    row = get(conversation_id)
    # `in_progress` = o cliente disse que continua e o turno ainda não fechou o ciclo: segue observando a conversa
    if not row or row["state"] not in ("awaiting_customer", "in_progress"):
        return None
    if confirms_resolved(text):
        _save(conversation_id, "resolved", row["cycles"], row["steps"], proof="customer_confirmed")
        return "resolved"
    if reports_still_broken(text):
        cycles = row["cycles"] + 1
        if cycles >= max_cycles():
            _save(conversation_id, "escalated", cycles, row["steps"])
            return "escalate"
        _save(conversation_id, "in_progress", cycles, row["steps"])
        return "another_cycle"
    return None  # cortesia ou pergunta nova: o caso continua esperando


def attempts(conversation_id: str) -> list[str]:
    """Passos já tentados (texto curto), para o agente não repetir o conselho."""
    row = get(conversation_id)
    if not row or row["state"] in ("resolved", "escalated"):
        return []
    return [s["gist"] for s in row["steps"] if s.get("gist")]


def after_turn(conversation_id: str, intent: str, tool_calls: list, answer: str) -> str | None:
    """Registra o turno no caso. Devolve o estado final. Intenção fora de `CASE_INTENTS` não mexe em nada."""
    row = get(conversation_id)
    open_case = row is not None and row["state"] in ("in_progress", "awaiting_customer")
    proof_hook = getattr(domain.active(), "tool_confirms_resolution", None)
    if open_case and proof_hook and proof_hook(tool_calls):  # a ferramenta prova: vale para qualquer intenção
        _save(conversation_id, "resolved", row["cycles"], row["steps"], proof="tool_verified")
        return "resolved"
    # fora do conjunto de intenções só acompanha um caso que já está no meio de um ciclo (não abre caso novo)
    if intent not in case_intents() and not (row and row["state"] == "in_progress"):
        return None
    names = [getattr(c, "name", str(c)) for c in tool_calls]
    fresh = row is None or row["state"] in ("resolved", "escalated")  # problema novo depois de um caso fechado
    steps = [] if fresh else row["steps"]
    gist = " ".join(answer.split())[:160]
    steps = [*steps, {"tools": names, "gist": gist, "at": time.time()}][-6:]
    _save(conversation_id, "awaiting_customer", 0 if fresh else row["cycles"], steps)
    return "awaiting_customer"


def summary_for_operator(conversation_id: str) -> str:
    row = get(conversation_id)
    if not row or not row["steps"]:
        return ""
    tried = "; ".join(f"{i}) {s['gist'][:110]}" for i, s in enumerate(row["steps"], 1))
    return f"tentativas sem sucesso ({row['cycles']} ciclos): {tried}"
