"""`context` da linha do eval: o texto da evidência que quem redigiu viu, com teto de tamanho, para o juiz ler.

Por quê: quando a linha guardava as fontes web só como título/endereço, o juiz não via o número que a resposta
citava (medido nos cenários oficiais: 6 das 12 reprovações diziam "as fontes só têm título e URL"). Aqui a linha
carrega a evidência do turno como a API devolve (trechos do RAG com texto, resultado bruto das tools, texto da API de
dado ao vivo, trechos citados da web e o cartão `policy:capabilities`), cortada em CONTEXT_CHARS. O cartão nunca sai por
causa do teto: é a política que sustenta as frases sobre confirmação e aprovação.
"""
from __future__ import annotations

CONTEXT_CHARS = 16000
ITEM_CHARS = 4000
CARD_PREFIX = "[policy:capabilities]"
CUT = " […]"


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split()) if "\n" not in text else text.strip()
    return text if len(text) <= limit else text[: max(0, limit - len(CUT))] + CUT


def build(evidence: list[str] | None, sources: list[dict] | None = None, limit: int = CONTEXT_CHARS) -> str:
    """Evidência (na ordem do turno) + fontes externas sem texto próprio, em até `limit` caracteres."""
    items = [e for e in (evidence or []) if e and e.strip()]
    cards = [e for e in items if e.lstrip().startswith(CARD_PREFIX)]
    rest = [e for e in items if e not in cards]
    reserved = sum(len(c) + 3 for c in cards)
    lines: list[str] = []
    used = 0
    for e in rest:
        line = "- " + _clip(e, ITEM_CHARS)
        if used + len(line) + 1 > limit - reserved:
            room = limit - reserved - used - 3
            if room > 80:
                lines.append("- " + _clip(e, room))
            lines.append(f"(+{len(rest) - len(lines)} item(ns) de evidência fora do teto de {limit} caracteres)")
            break
        lines.append(line)
        used += len(line) + 1
    lines += ["- " + c.strip() for c in cards]
    joined = "\n".join(e for e in items)
    external = [s for s in sources or [] if (s.get("url") or "").startswith("http")
                and (s.get("title") or "") not in joined]
    if external:
        lines.append("Fontes externas citadas sem trecho legível (só título e endereço): " + "; ".join(
            f"{s.get('title') or s.get('id')} ({s.get('url')})" for s in external[:10]))
    return "\n".join(lines)
