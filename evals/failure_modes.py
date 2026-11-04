"""Análise de erros do eval ao vivo: agrupa as falhas por modo e escreve docs/FAILURE_MODES.md.

Uso: python -m evals.failure_modes [--out docs/FAILURE_MODES.md]

Lê evals/results/live_*.json (linhas com alguma checagem False) e agrupa pela PRIMEIRA checagem que falhou e pelo
split, com contagem, os casos afetados e 1 exemplo (pergunta, resposta curta, números sem base). É o passo
"olhar os traces antes de medir": cada modo vira uma correção ou uma checagem binária própria.
Exemplo de saída: numbers (clima/câmbio e soma do LLM), language (termo pt numa pergunta en) e handoff (resposta
direta onde se esperava humano) explicavam todas as falhas do official; cada uma foi corrigida ou declarada.

Gerado, nunca à mão: scripts/live_eval.sh e scripts/final.sh rodam este módulo e o `fill_readme.py --check` reprova o
arquivo que diferir de `generate()` (rodada 10: o FAILURE_MODES dizia "42 falhas em 281 execuções", de outra bateria,
com os resultados commitados dando 5 em 315). Ficam fora: os splits `heldout*` (conjunto cego: ler as falhas dele
para corrigir o motor o contamina, mesma regra de evals/error_analysis.py) e os arquivos laterais
`live_<split>.degraded.json`/`.aborted_*.json` (não são medida).
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
BLIND_PREFIX = "heldout"  # heldout, heldout_h3, ...: todo split cego fica fora da análise de erros


def is_blind(split: str | None) -> bool:
    """Split cego (held-out): a medida final, que ninguém lê para ajustar o motor."""
    return str(split or "").startswith(BLIND_PREFIX)


def first_failed(checks: dict) -> str | None:
    bad = [k for k, v in checks.items() if v is False]
    if not bad:
        return None
    return next((k for k in ORDER if k in bad), bad[0])


def live_files(results: Path = RESULTS) -> list[Path]:
    """Os live_<split>.json da bateria; `.degraded`/`.aborted_*` ficam fora (a mesma regra do placar)."""
    return [p for p in sorted(results.glob("live_*.json")) if p.name.count(".") == 1]


def _rows(results: Path) -> tuple[list[dict], dict[str, int]]:
    """(linhas fora do held-out, {split cego: execuções deixadas de fora})."""
    rows: list[dict] = []
    blind: dict[str, int] = defaultdict(int)
    for path in live_files(results):
        for row in json.loads(path.read_text(encoding="utf-8")).get("rows", []):
            if is_blind(row.get("split")):
                blind[row["split"]] += 1
            else:
                rows.append(row)
    return rows, dict(sorted(blind.items()))


def collect(results: Path = RESULTS) -> dict[str, dict]:
    """{modo: {"casos": {id: n_falhas}, "runs": total, "exemplo": linha, "splits": {split: n}}}"""
    return _modes(_rows(results)[0])


def _modes(rows: list[dict]) -> dict[str, dict]:
    modes: dict[str, dict] = {}
    for row in rows:
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


def _runs(n: int) -> str:
    return f"{n} execução" if n == 1 else f"{n} execuções"


def render(modes: dict[str, dict], total_rows: int, blind: dict[str, int] | None = None) -> str:
    out = [
        "# Modos de falha (eval ao vivo)",
        "",
        "Gerado por `python -m evals.failure_modes` a partir de `evals/results/live_*.json`. Cada falha conta uma "
        "vez, pela primeira checagem que falhou. Para cada modo: o que fazer é decisão humana; o que foi feito fica "
        "no commit que cita o modo.",
        "",
    ]
    if blind:  # declarado: quem soma as linhas do RESULTS acha a diferença aqui, não um número que não bate
        out += ["Fora da conta: " + ", ".join(f"`{s}` ({_runs(n)})" for s, n in blind.items())
                + ", o conjunto cego: ler as falhas dele para corrigir o motor o contamina. A medida dele fica nos "
                "blocos ao vivo, do juiz e humano de `docs/RESULTS.md`.", ""]
    if not modes:
        return "\n".join(out + [f"Nenhuma falha em {_runs(total_rows)}: todas as checagens passam.", ""])
    total_fail = sum(m["runs"] for m in modes.values())
    out += [
        f"{total_fail} {'falha' if total_fail == 1 else 'falhas'} em {_runs(total_rows)} "
        f"({total_fail / max(total_rows, 1):.1%}).",
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


def generate(results: Path = RESULTS) -> str | None:
    """O texto de docs/FAILURE_MODES.md para estes resultados; None sem live_*.json (nada a analisar). É o que o
    `fill_readme.py --check` compara com o arquivo commitado."""
    if not live_files(results):
        return None
    rows, blind = _rows(results)
    return render(_modes(rows), len(rows), blind)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "FAILURE_MODES.md")
    ap.add_argument("--results", type=Path, default=RESULTS)
    args = ap.parse_args(argv)
    text = generate(args.results)
    if text is None:
        print(f"Sem {args.results}/live_*.json: rode o eval ao vivo antes (scripts/live_eval.sh).", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    rows, blind = _rows(args.results)
    print(
        f"{args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}: "
        f"{sum(m['runs'] for m in _modes(rows).values())} falhas em {len(rows)} execuções"
        + (f" (fora: {', '.join(blind)})" if blind else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
