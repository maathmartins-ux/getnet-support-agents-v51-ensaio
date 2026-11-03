"""Análise de erros do eval ao vivo: agrupa as falhas por modo e escreve docs/FAILURE_MODES.md.

Uso: python -m evals.failure_modes [--out docs/FAILURE_MODES.md]

Lê evals/results/live_*.json (linhas com alguma checagem False) e agrupa pela PRIMEIRA checagem que falhou e pelo
split, com contagem, os casos afetados e 1 exemplo (pergunta, resposta curta, números sem base). É o passo
"olhar os traces antes de medir": cada modo vira uma correção ou uma checagem binária própria.
Getnet v4 (01/11/2026): numbers (clima/câmbio e soma do LLM), language (termo pt numa pergunta en) e handoff
(resposta direta onde se esperava humano) explicavam todas as falhas do official; foram corrigidas ou declaradas.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = HERE / "results"
ORDER = ("intent", "handoff", "handoff_outcome", "tools", "numbers", "claims", "language", "blocked", "no_leak",
         "replanned")


def first_failed(checks: dict) -> str | None:
    bad = [k for k, v in checks.items() if v is False]
    if not bad:
        return None
    return next((k for k in ORDER if k in bad), bad[0])


def collect(results: Path = RESULTS) -> dict[str, dict]:
    """{modo: {"casos": {id: n_falhas}, "runs": total, "exemplo": linha, "splits": {split: n}}}"""
    modes: dict[str, dict] = {}
    for path in sorted(results.glob("live_*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        for row in report.get("rows", []):
            mode = first_failed(row.get("checks") or {})
            if not mode:
                continue
            m = modes.setdefault(
                mode, {"casos": defaultdict(int), "runs": 0, "exemplo": row, "splits": defaultdict(int)}
            )
            m["casos"][row["id"]] += 1
            m["runs"] += 1
            m["splits"][row.get("split", "?")] += 1
    return modes


def _tools(row: dict) -> list[str]:
    return [t.get("name", "?") if isinstance(t, dict) else str(t) for t in row.get("tool_calls") or []]


def _short(text: str, n: int = 260) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def render(modes: dict[str, dict], total_rows: int) -> str:
    out = [
        "# Modos de falha (eval ao vivo)",
        "",
        "Gerado por `python -m evals.failure_modes` a partir de `evals/results/live_*.json`. Cada falha conta uma "
        "vez, pela primeira checagem que falhou. Para cada modo: o que fazer é decisão humana; o que foi feito fica "
        "no commit que cita o modo.",
        "",
    ]
    if not modes:
        return "\n".join(out + ["Nenhuma falha nas linhas lidas.", ""])
    total_fail = sum(m["runs"] for m in modes.values())
    out += [
        f"{total_fail} falhas em {total_rows} execuções ({total_fail / max(total_rows, 1):.1%}).",
        "",
        "| modo | falhas | casos distintos | splits |",
        "|---|---:|---:|---|",
    ]
    for mode, m in sorted(modes.items(), key=lambda kv: -kv[1]["runs"]):
        splits = ", ".join(f"{s} ({n})" for s, n in sorted(m["splits"].items()))
        out.append(f"| `{mode}` | {m['runs']} | {len(m['casos'])} | {splits} |")
    for mode, m in sorted(modes.items(), key=lambda kv: -kv[1]["runs"]):
        ex = m["exemplo"]
        worst = sorted(m["casos"].items(), key=lambda kv: -kv[1])[:5]
        out += [
            "",
            f"## `{mode}`",
            "",
            "Casos que mais falham: " + ", ".join(f"`{i}` ({n}x)" for i, n in worst),
            "",
            f"- exemplo `{ex['id']}`: “{_short(ex.get('message', ''), 120)}”",
            f"- esperado: intent `{ex.get('expected_intent')}`; obtido: `{ex.get('got_intent')}`; "
            f"rota {ex.get('route')}; ferramentas {_tools(ex)}",
            f"- números sem base: {ex.get('unsupported_numbers') or 'nenhum'}",
            f"- resposta: {_short(ex.get('answer', ''))}",
        ]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "FAILURE_MODES.md")
    ap.add_argument("--results", type=Path, default=RESULTS)
    args = ap.parse_args(argv)
    files = sorted(args.results.glob("live_*.json"))
    if not files:
        print(f"Sem {args.results}/live_*.json: rode o eval ao vivo antes (scripts/live_eval.sh).", file=sys.stderr)
        return 1
    total = sum(len(json.loads(p.read_text(encoding="utf-8")).get("rows", [])) for p in files)
    text = render(collect(args.results), total)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(
        f"{args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}: "
        f"{sum(m['runs'] for m in collect(args.results).values())} falhas em {total} execuções"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
