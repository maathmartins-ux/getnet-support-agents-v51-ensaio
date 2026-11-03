"""Memória × roteamento: separa, no split de memória, onde a conversa perde pontos.

Um caso de memória pode falhar por dois motivos independentes: o roteamento errou (intenção, ferramenta, handoff) ou a
memória falhou (o valor/id dito antes não chegou à resposta, ou o número da resposta não tem base). Somar tudo num
pass@1 esconde qual dos dois é. Aqui cada caso é classificado:

- roteamento: route, handoff, handoff_outcome, tools, pending_action, replanned, blocked (os que o caso declara).
  `route` (run_evals.route_equivalent) é a rota pelo RESULTADO: rótulo certo, ou rótulo vizinho que leva ao mesmo
  plano de especialistas e os chamou (support × troubleshoot → records). O rótulo (`intent`) sai à parte, em
  `intent_acc`, e não entra no pass@1 de memória quando a linha tem `route`: ensaio v5.3, 4 de 8 perdas eram só de
  rótulo com a resposta certa (nelsondell, 9,5: mede-se o resultado, não a taxonomia). Linha antiga, sem `route`,
  segue medida pelo rótulo;
- memória: `memory` (campo opcional `expect.expects_fact`: valores que vieram de turnos anteriores e a resposta deve
  conter; comparação por valor, "R$ 75,00" = 75.0) e `numbers` (a mesma checagem determinística de toda resposta,
  agora lendo também o histórico e o livro de fatos);
- idioma e demais checagens ficam fora das duas colunas e entram só no pass@1.

Caso sem `expects_fact` continua valendo: só não entra na taxa de fatos (compatível com os casos antigos).
"""
from __future__ import annotations

ROUTING = ("route", "handoff", "handoff_outcome", "tools", "pending_action", "replanned", "blocked")


def _routing_keys(r: dict) -> tuple[str, ...]:
    return ROUTING if "route" in r["checks"] else ("intent", *ROUTING[1:])


def _passes(r: dict) -> bool:
    """pass@1 de memória: todas as checagens, com a rota pelo resultado no lugar do rótulo (quando a linha tem)."""
    skip = {"intent"} if "route" in r["checks"] else set()
    return all(v for k, v in r["checks"].items() if k not in skip)
MEMORY = ("memory", "numbers")


def _pct(k: int, n: int) -> float | None:
    return round(100 * k / n, 1) if n else None


def facts_ok(expected: list[str], answer: str) -> bool:
    from app.memory import fact_present

    return all(fact_present(f, answer or "") for f in expected)


def memory_vs_routing(rows: list[dict]) -> dict:
    """{split: estatística} para o split `memory` e qualquer split com caso que declara `expects_fact`."""
    splits = sorted({r["split"] for r in rows if r["split"] == "memory" or "memory" in r["checks"]})
    out: dict = {}
    for split in splits:
        sel = [r for r in rows if r["split"] == split and not r["crash"]]
        if not sel:
            continue

        def ok(r: dict, keys: tuple[str, ...]) -> bool:
            return all(r["checks"][k] for k in keys if k in r["checks"])

        routing = [ok(r, _routing_keys(r)) for r in sel]
        labels = [r["checks"]["intent"] for r in sel if "intent" in r["checks"]]
        memory = [ok(r, MEMORY) for r in sel]
        facts = [r["checks"]["memory"] for r in sel if "memory" in r["checks"]]
        numbers = [r["checks"]["numbers"] for r in sel if "numbers" in r["checks"]]
        out[split] = {
            "n": len(sel), "pass_at_1": _pct(sum(_passes(r) for r in sel), len(sel)),
            "pass_at_1_label": _pct(sum(all(r["checks"].values()) for r in sel), len(sel)),
            "intent_acc": _pct(sum(labels), len(labels)),
            "routing_acc": _pct(sum(routing), len(sel)), "memory_acc": _pct(sum(memory), len(sel)),
            "facts_acc": _pct(sum(facts), len(facts)), "facts_n": len(facts),
            "numbers_acc": _pct(sum(numbers), len(numbers)), "numbers_n": len(numbers),
            "only_routing_fails": [r["id"] for r, a, b in zip(sel, routing, memory, strict=True) if not a and b],
            "only_memory_fails": [r["id"] for r, a, b in zip(sel, routing, memory, strict=True) if a and not b],
            "both_fail": [r["id"] for r, a, b in zip(sel, routing, memory, strict=True) if not a and not b],
        }
    return out


def lines(stats: dict) -> list[str]:
    """Linhas "memória" e "roteamento" do relatório em markdown."""
    out = []
    for split, s in stats.items():
        facts = f"fatos esperados {s['facts_acc']}% (n={s['facts_n']})" if s["facts_n"] else "fatos esperados: sem caso"
        nums = f"números {s['numbers_acc']}% (n={s['numbers_n']})" if s["numbers_n"] else "números: sem dado"
        out.append(f"- split `{split}` (n={s['n']}): **memória** {s['memory_acc']}% ({facts}; {nums}) · "
                   f"**roteamento** {s['routing_acc']}% (pelo resultado; rótulo da intenção "
                   f"{s.get('intent_acc')}%) · pass@1 {s['pass_at_1']}% (pelo rótulo "
                   f"{s.get('pass_at_1_label', s['pass_at_1'])}%) · perdas só de roteamento: "
                   f"{', '.join(s['only_routing_fails']) or '—'} · só de memória: "
                   f"{', '.join(s['only_memory_fails']) or '—'} · nas duas: {', '.join(s['both_fail']) or '—'}")
    return out
