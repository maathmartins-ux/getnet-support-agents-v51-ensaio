"""Onde vai o tempo do turno e quem decide cada passo, lido das respostas ao vivo (evals/results/live_*.json).

Uso: python -m evals.trace_stats [--results DIR] [--cases ARQUIVO ...] [--json]

Um p50 sem orçamento declarado não diz se a latência está boa, e sozinho não diz onde cortar. Por isso este módulo
junta, por split e no total:

- **p50 e p95 do turno**, pelo mesmo critério de run_evals.summarize (o valor na posição int(q·n) da lista
  ordenada, sem interpolação): num split de turno único e sem crash os números batem com os do bloco ao vivo. Linha
  com crash fica fora dos percentis (o tempo dela é o de uma falha, não o de um turno) e sai contada à parte. A
  linha de um caso com turnos anteriores (`before`, casos de memória) cronometra a conversa inteira; o turno dela
  vale ms ÷ turnos (a média dos turnos daquela conversa) e a conversa sai à parte, para não esconder a cauda. Caso
  que não está nos arquivos de casos conta como 1 turno: o erro possível superestima a latência, nunca a esconde;
- **SLO declarado** por env, com padrão fixo aqui (SLO_P50_S=20, SLO_P95_S=45, em segundos, por turno): cada split
  cumpre ou não (p50 ≤ alvo e p95 ≤ alvo), e os que não cumprem saem nomeados com o valor medido;
- **fatia de cada agente** = soma dos `ms` dos passos dele ÷ soma do tempo dos turnos a que esses passos pertencem.
  Os `steps` de uma linha são só do último turno da conversa: o denominador é o `turn_ms` da linha (o run_evals
  cronometra esse turno à parte) ou, sem ele, o `ms` da linha de turno único. Ficam fora da fatia, contadas no texto:
  a linha de mais de um turno sem `turn_ms` e a linha sem `steps` (gravação antiga), que seguem na latência, e a
  linha com crash. Router, supervisor, guardrails e as checagens de número e de afirmação não têm passo próprio na
  árvore: são o "resto". Passos em paralelo somam cada um o seu tempo; a linha em que a soma dos passos passa do
  tempo do turno teve paralelo, e o resto do grupo sai calculado só nas linhas sem essa sobreposição (paralelo que
  não passa do tempo do turno não é detectável sem o início de cada passo: o resto daquela linha sai menor, nunca
  maior);
- **quem decide**: cada passo traz `decided_by` ("llm": o supervisor LLM chamou a tool, e o motivo é a própria tool
  call, sem `why`; "router": o agente veio do plano do router e rodou sem consultar o supervisor LLM, com o caminho
  em `why`; "code": uma regra do código pôs o passo, com a regra em `why`, como o achado `needs`, a escalada
  garantida ou o FALLBACK). Passo gravado sem o campo conta como "não registrado", nunca como decisão de alguém. A
  resposta da operadora (agente `human`, decided_by "operator") chega pronta como evidência, e o aviso de caso
  aberto (agente `hold`) não escolhe agente nenhum: os dois ficam fora da conta.

Sem LLM e sem rede: só lê JSON. O bloco `trace` de scripts/fill_readme.py escreve a seção em docs/RESULTS.md; o
`--check` regenera com o mesmo env, então um SLO fora do padrão precisa estar também no env de quem confere.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
SLO_ENV = (("SLO_P50_S", 20.0), ("SLO_P95_S", 45.0))  # (variável, padrão em segundos por turno)
DECIDERS = ("llm", "router", "code")  # supervisor.DECIDED_LLM, DECIDED_ROUTER e DECIDED_CODE
DECIDER_NAMES = {"llm": "supervisor LLM", "router": "plano do router", "code": "código"}
NOT_RECORDED = "não registrado"
OPERATOR = "operator"  # supervisor.DECIDED_OPERATOR
NOT_ROUTING = frozenset({"human", "hold"})  # resposta da operadora e aviso de caso aberto: nenhum escolhe agente
SCOPE = "passos do turno, fora a resposta da operadora e o aviso de caso aberto"
LLM_MOTIVE = "tool call"  # o passo do supervisor LLM não grava `why`: o motivo é a tool call
LEFT_OUT = (("multi_turn_without_turn_ms", "de mais de um turno sem `turn_ms`"),
            ("no_steps", "sem `steps`"), ("crash", "com crash"))  # linhas fora da fatia, na ordem do texto
WHY_CHARS = 40  # `why` pode trazer texto livre do modelo: rótulo curto, sem caractere que quebre o markdown
TOP_WHY = 4
_UNSAFE = re.compile(r"[<>|`\[\]]")


def slo() -> dict:
    """Alvos em segundos, do env ou do padrão; `origin` diz de onde veio cada um (sai escrito na seção)."""
    values, origin = {}, {}
    for name, default in SLO_ENV:
        raw = os.getenv(name, "").strip()
        try:
            value = float(raw) if raw else None
        except ValueError:
            value = None
        ok = value is not None and value > 0
        values[name] = value if ok else default
        origin[name] = "env" if ok else ("padrão (valor do env inválido)" if raw else "padrão")
    return {"p50_s": values["SLO_P50_S"], "p95_s": values["SLO_P95_S"], "origin": origin}


def percentile(values: list[float], q: float) -> float | None:
    """Valor na posição int(q·n) da lista ordenada (o critério de run_evals.summarize e de app.analytics): sempre um
    tempo que aconteceu, e o p95 de até 20 linhas é o máximo, sem interpolação que o suavize."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def load_rows(results: Path = RESULTS) -> list[dict]:
    """Só o que a conta usa de cada linha ao vivo: id, split, ms (a conversa), turn_ms (o último turno), crash e
    steps (None = linha sem árvore de passos)."""
    rows = []
    for path in sorted(Path(results).glob("live_*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        for row in report.get("rows") or []:
            rows.append({"id": row.get("id"), "split": row.get("split") or report.get("split") or path.stem[5:],
                         "ms": row.get("ms"), "turn_ms": row.get("turn_ms"), "crash": row.get("crash"),
                         "steps": row.get("steps")})
    return rows


def turns_by_case(cases: list[dict]) -> dict[str, int]:
    """Turnos que a linha de cada caso cronometra: os anteriores (`before`) mais o turno avaliado."""
    return {c["id"]: 1 + len(c.get("before") or []) for c in cases if c.get("id")}


def case_turns(paths: tuple[Path, ...] | None = None) -> dict[str, int]:
    """Turnos por id, lidos dos arquivos de casos (run_evals.load_cases). Arquivos ilegíveis → {}: cada linha vale
    1 turno, o lado que superestima a latência."""
    from evals.run_evals import load_cases

    try:
        return turns_by_case(load_cases(paths))
    except (OSError, ValueError):
        return {}


def _label(text: object) -> str:
    clean = " ".join(_UNSAFE.sub(" ", str(text)).split())
    return clean if len(clean) <= WHY_CHARS else clean[: WHY_CHARS - 1] + "…"


def _number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def decider(step: dict) -> str:
    """"llm", "router", "code", outro valor gravado (mantido como veio) ou "não registrado" sem o campo."""
    return _label(step.get("decided_by") or "").lower() or NOT_RECORDED


def routing_step(step: dict) -> bool:
    """O passo entra na conta de quem decide? A resposta da operadora e o aviso de caso aberto não escolhem agente:
    ficam fora pelo nome do agente (`human`, `hold`), que todo passo traz, e pela marca "operator"."""
    return step.get("agent") not in NOT_ROUTING and decider(step) != OPERATOR


def _motive(step: dict, who: str) -> str:
    return _label(step.get("why") or "") or (LLM_MOTIVE if who == "llm" else "sem motivo")


def turn_time(row: dict, n_turns: int) -> float | None:
    """Tempo do turno a que os `steps` da linha pertencem (o último): o `turn_ms` gravado ou, na linha de turno único,
    o `ms`. None = a linha não tem um denominador coerente para a fatia."""
    if _number(row.get("turn_ms")) and row["turn_ms"] > 0:
        return float(row["turn_ms"])
    return float(row["ms"]) if n_turns == 1 else None


def _group(rows: list[dict], turns: dict[str, int], target: dict) -> dict:
    """Medidas de um conjunto de linhas (um split ou todas): latência por turno, SLO, fatias e decisões."""
    crashed = sum(1 for r in rows if r.get("crash"))
    timed = [r for r in rows if not r.get("crash") and _number(r.get("ms"))]
    n_turns = [max(1, int(turns.get(r.get("id"), 1))) for r in timed]
    per_turn = [r["ms"] / t for r, t in zip(timed, n_turns, strict=True)]
    p50, p95 = percentile(per_turn, 0.5), percentile(per_turn, 0.95)
    misses = [name for name, value, limit in (("p50", p50, target["p50_s"]), ("p95", p95, target["p95_s"]))
              if value is not None and value > limit * 1000]
    multi = sum(t > 1 for t in n_turns)
    conversation = [r["ms"] for r, t in zip(timed, n_turns, strict=True) if t > 1]

    left_out = Counter(crash=crashed)
    sliced: list[tuple[float, Counter]] = []  # (tempo do turno, ms por agente) das linhas que entram na fatia
    for r, t in zip(timed, n_turns, strict=True):
        if r.get("steps") is None:  # gravação antiga, sem árvore de passos
            left_out["no_steps"] += 1
            continue
        turn = turn_time(r, t)
        if turn is None:  # os passos são do último turno, e o tempo dele não foi gravado
            left_out["multi_turn_without_turn_ms"] += 1
            continue
        by_agent: Counter = Counter()
        for st in r["steps"]:
            ms = st.get("ms")
            # passo sem tempo medido (a resposta do operador chega pronta, ms None) não vira coluna de 0%
            if _number(ms) and ms > 0:
                by_agent[_label(st.get("agent") or "?")] += ms
        sliced.append((turn, by_agent))
    total_turn = sum(turn for turn, _ in sliced)
    agent_ms = sum((c for _, c in sliced), Counter())
    ranked = sorted(agent_ms.items(), key=lambda kv: (-kv[1], kv[0]))  # do agente mais demorado ao menos
    share = {a: v / total_turn for a, v in ranked} if total_turn else {}
    alone = [(turn, c) for turn, c in sliced if sum(c.values()) <= turn]  # linhas sem sobreposição de passos
    alone_turn = sum(turn for turn, _ in alone)
    rest = 1 - sum(sum(c.values()) for _, c in alone) / alone_turn if alone_turn else None

    decided: Counter = Counter()
    why: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        for st in r.get("steps") or []:
            if not routing_step(st):
                continue
            who = decider(st)
            decided[who] += 1
            if who != NOT_RECORDED:
                why[who][_motive(st, who)] += 1
    return {
        "rows": len(timed),
        "crashes": crashed,
        "turns_per_row": round(sum(n_turns) / len(timed), 2) if timed else None,
        "multi_turn_rows": multi,
        "p50_ms": round(p50, 1) if p50 is not None else None,
        "p95_ms": round(p95, 1) if p95 is not None else None,
        "conversation_p50_ms": round(percentile(conversation, 0.5), 1) if conversation else None,
        "conversation_p95_ms": round(percentile(conversation, 0.95), 1) if conversation else None,
        "slo_ok": None if p50 is None else not misses,
        "slo_misses": misses,
        "share_rows": len(sliced),
        "share_left_out": {key: left_out[key] for key, _ in LEFT_OUT if left_out[key]},
        "agent_share": {a: round(v, 4) for a, v in share.items()},
        "rest_share": round(rest, 4) if rest is not None else None,
        "parallel_rows": len(sliced) - len(alone),
        "decisions": {"steps": sum(decided.values()), "by": dict(decided),
                      "why": {who: dict(c) for who, c in sorted(why.items())}},
    }


def summarize(rows: list[dict], turns: dict[str, int] | None = None, target: dict | None = None) -> dict:
    """{"slo", "by_split": {split: medidas}, "ALL": medidas, "agents": agentes do mais ao menos demorado}.

    `turns`: id → turnos da linha (case_turns()); sem ele, cada linha vale 1 turno. `target`: slo() por padrão."""
    turns, target = turns or {}, target or slo()
    by_split: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_split[str(r.get("split") or "?")].append(r)
    total = _group(rows, turns, target)
    return {"slo": target, "by_split": {s: _group(items, turns, target) for s, items in sorted(by_split.items())},
            "ALL": total, "agents": list(total["agent_share"])}


def _s(ms: float | None) -> str:
    if ms is None:
        return "—"
    return f"{ms:.0f} ms" if ms < 1000 else f"{ms / 1000:.1f} s"  # bloqueio no guardrail leva ms, não 0.0 s


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.0%}"


def _decision_cell(d: dict) -> str:
    n = d["steps"]
    if not n:
        return "—"
    by = d["by"]
    columns = (*DECIDERS, NOT_RECORDED)
    known = sum(by.get(k, 0) for k in columns)
    cell = " · ".join(_pct(by.get(k, 0) / n) for k in columns)
    return cell + (f" · outro {_pct((n - known) / n)}" if n - known else "") + f" (n={n})"


def _rows_cell(g: dict) -> str:
    return str(g["rows"]) + (f" (+{g['crashes']} crash)" if g["crashes"] else "")


def _lines(n: int) -> str:
    return f"{n} linha" if n == 1 else f"{n} linhas"


def _rest_cell(g: dict) -> str:
    if g["rest_share"] is None:
        return "— (paralelo)" if g["parallel_rows"] else "—"
    return _pct(g["rest_share"]) + (f" (fora {_lines(g['parallel_rows'])} com paralelo)" if g["parallel_rows"] else "")


def _motives(counter: dict, who: str) -> str:
    if who == "llm" and set(counter) <= {LLM_MOTIVE}:
        return LLM_MOTIVE
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    shown = ", ".join(f"`{w}` {n}" for w, n in items[:TOP_WHY])
    others = sum(n for _, n in items[TOP_WHY:])
    return shown + (f", outros {others}" if others else "")


def _origin(target: dict) -> str:
    """De onde veio cada alvo; o que veio do env sai ao lado do padrão do kit, para quem lê comparar os dois."""
    origin, defaults = target["origin"], dict(SLO_ENV)
    if set(origin.values()) == {"padrão"}:
        return "padrão do kit; muda por env `SLO_P50_S`/`SLO_P95_S`"
    return "; ".join(f"`{k}`: {v}" + (f" (padrão do kit {defaults[k]:g} s)" if v == "env" else "")
                     for k, v in origin.items())


def _slo_line(summary: dict) -> str:
    target, splits, total = summary["slo"], summary["by_split"], summary["ALL"]
    judged = {s: g for s, g in splits.items() if g["slo_ok"] is not None}
    misses = [f"`{s}` (" + ", ".join(f"{m} {_s(g[f'{m}_ms'])}" for m in g["slo_misses"]) + ")"
              for s, g in judged.items() if not g["slo_ok"]]
    verdict = f"Cumprem **{len(judged) - len(misses)} de {len(judged)}** splits"
    verdict += f"; não cumprem: {', '.join(misses)}." if misses else "."
    crash = f" ({total['crashes']} crash fora do p50/p95)" if total["crashes"] else ""
    return (f"SLO declarado, por turno: p50 ≤ **{target['p50_s']:g} s** e p95 ≤ **{target['p95_s']:g} s** "
            f"({_origin(target)}). {verdict} Total: p50 {_s(total['p50_ms'])}, p95 {_s(total['p95_ms'])} em "
            f"{total['rows']} linhas{crash}.")


def _left_out_text(left_out: dict) -> str:
    """As linhas fora da fatia, por motivo; as que seguem na latência separadas das com crash, que saem de tudo."""
    kept = [f"{_lines(left_out[k])} {label}" for k, label in LEFT_OUT if k != "crash" and left_out.get(k)]
    text = ""
    if kept:
        n_kept = sum(left_out.get(k, 0) for k, _ in LEFT_OUT if k != "crash")
        text = " e ".join(kept) + (" (segue na latência)" if n_kept == 1 else " (seguem na latência)")
    if left_out.get("crash"):
        text += ("; " if text else "") + f"{_lines(left_out['crash'])} com crash (fora também do p50/p95)"
    return text


def _time_line(summary: dict) -> str:
    total, splits = summary["ALL"], summary["by_split"]
    left = _left_out_text(total["share_left_out"])
    if not total["share_rows"]:
        line = ("Onde vai o tempo: nenhuma linha com `steps` e o tempo do turno deles; só a latência do turno foi "
                "medida.")
        return line + (f" Fora da fatia: {left}." if left else "")
    parts = [f"{a} **{_pct(v)}**" for a, v in total["agent_share"].items()]
    if total["rest_share"] is None:
        parts.append("resto sem valor (em todas as linhas a soma dos passos passa do tempo do turno: paralelo)")
    else:
        rest = (f"resto **{_pct(total['rest_share'])}** = router, supervisor, guardrails e checagens, que não têm "
                "passo próprio")
        if total["parallel_rows"]:
            alone = total["share_rows"] - total["parallel_rows"]
            rest += (f" (calculado {'na' if alone == 1 else 'nas'} {_lines(alone)} sem paralelo; em "
                     f"{_lines(total['parallel_rows'])} a soma dos passos passa do tempo do turno)")
        parts.append(rest)
    line = (f"Onde vai o tempo (total): {' · '.join(parts)}. Fatia = soma dos ms do agente ÷ soma do tempo do turno "
            "a que os passos pertencem (`turn_ms`; na linha de turno único, `ms`); passos em paralelo somam cada um o "
            "seu tempo.")
    if left:
        line += f" Fora da fatia: {left}."
    multi = [f"`{s}` ({round(g['turns_per_row'], 1):g} turnos/linha; conversa: p50 {_s(g['conversation_p50_ms'])}, "
             f"p95 {_s(g['conversation_p95_ms'])})" for s, g in splits.items() if g["multi_turn_rows"]]
    if multi:
        line += (f" Em {' e '.join(multi)} a linha cronometra a conversa inteira; ali a latência do turno é ms ÷ "
                 "turnos.")
    return line


def _decision_line(summary: dict) -> str:
    d = summary["ALL"]["decisions"]
    n, by = d["steps"], d["by"]
    if not n:
        return f"Quem decide: nenhum passo nas linhas lidas ({SCOPE})."
    if by.get(NOT_RECORDED, 0) == n:
        return (f"Quem decide: os {n} {SCOPE}, foram gravados sem `decided_by` (não registrado); a divisão "
                "supervisor LLM × plano do router × código não é medível nestas respostas.")
    order = [*DECIDERS, *sorted(k for k in by if k not in (*DECIDERS, NOT_RECORDED)), NOT_RECORDED]
    parts = []
    for who in (k for k in order if by.get(k)):
        name = NOT_RECORDED if who == NOT_RECORDED else DECIDER_NAMES.get(who, f"`{who}`")
        part = f"{name} **{_pct(by[who] / n)}**"
        if who == NOT_RECORDED:
            part += " (passo gravado sem `decided_by`)"
        elif motives := _motives(d["why"].get(who) or {}, who):
            part += f" ({motives})"
        parts.append(part)
    return f"Quem decide ({n} {SCOPE}): " + " · ".join(parts) + "."


def markdown(summary: dict) -> str:
    """Seção curta do docs/RESULTS.md: a linha do SLO, uma tabela por split e duas linhas (tempo e decisão)."""
    if not summary["by_split"]:
        return "_Eval ao vivo não rodado: sem `evals/results/live_*.json`, não há tempo nem decisão a medir._"
    agents = summary["agents"]
    cols = ["split", "linhas", "turnos/linha", "p50", "p95", "SLO", *agents, "resto",
            "quem decide (LLM · router · código · não registrado)"]
    align = ["---", "---:", "---:", "---:", "---:", ":---:", *["---:"] * len(agents), "---:", "---"]
    table = ["| " + " | ".join(cols) + " |", "|" + "|".join(align) + "|"]
    for name, g in [*((f"`{s}`", g) for s, g in summary["by_split"].items()), ("**total**", summary["ALL"])]:
        turns = "—" if g["turns_per_row"] is None else f"{round(g['turns_per_row'], 1):g}"
        verdict = "—" if g["slo_ok"] is None else ("sim" if g["slo_ok"] else "**não**")
        cells = [name, _rows_cell(g), turns, _s(g["p50_ms"]), _s(g["p95_ms"]), verdict,
                 *(_pct(g["agent_share"].get(a)) for a in agents), _rest_cell(g), _decision_cell(g["decisions"])]
        table.append("| " + " | ".join(cells) + " |")
    return "\n".join([_slo_line(summary), "", *table, "", _time_line(summary), "", _decision_line(summary)])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tempo por agente, SLO por split e quem decide cada passo (ao vivo).")
    ap.add_argument("--results", type=Path, default=RESULTS, help="pasta com os live_*.json")
    ap.add_argument("--cases", type=Path, nargs="+", default=None,
                    help="arquivos de casos para contar os turnos (padrão: os do run_evals)")
    ap.add_argument("--json", action="store_true", help="imprime o JSON em vez do markdown")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # console cp1252 do Windows quebra acentos
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    rows = load_rows(args.results)
    if not rows:
        print(f"Sem linhas em {args.results}/live_*.json: rode o eval ao vivo antes (scripts/live_eval.sh).",
              file=sys.stderr)
        return 1
    summary = summarize(rows, case_turns(tuple(args.cases) if args.cases else None))
    print(json.dumps(summary, ensure_ascii=False, indent=2) if args.json else markdown(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
