"""Antes/depois do juiz por caso: `python -m evals.judge_diff A.json B.json --out docs/JUDGE_DIFF.md`.

A e B são relatórios de evals/judge.py (judge.json). Cada veredito é casado por (arquivo, id, rodada); relatório
antigo sem `run` usa a ordem de aparição do id no arquivo (o juiz percorre as linhas na ordem da rodada). A tabela
mostra grounded, failure_type e o motivo de B, com o resumo por split; serve para publicar a melhora (ou a piora)
caso a caso, não só a taxa. Sem LLM e sem rede: só lê os dois JSON.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REASON_CHARS = 160


def _key_verdicts(report: dict) -> dict[tuple, dict]:
    seen: dict[tuple, int] = defaultdict(int)
    out: dict[tuple, dict] = {}
    for v in report.get("verdicts", []):
        base = (v.get("source", "?"), v["id"])
        run = v.get("run")
        if run is None:
            run = seen[base]
        seen[base] += 1
        out[(*base, int(run))] = v
    return out


def _mark(v: dict | None) -> str:
    if v is None:
        return "—"
    return "sim" if v.get("grounded") else "**não**"


def _type(v: dict | None) -> str:
    if v is None:
        return "—"
    return v.get("failure_type") or ("none" if v.get("grounded") else "?")


def _cell(text: str | None) -> str:
    text = " ".join((text or "").split()).replace("|", "\\|")
    return text if len(text) <= REASON_CHARS else text[: REASON_CHARS - 1] + "…"


def _rate(vs: list[dict]) -> str:
    if not vs:
        return "—"
    k = sum(bool(v.get("grounded")) for v in vs)
    return f"{k}/{len(vs)} ({100 * k / len(vs):.0f}%)"


def diff(a: dict, b: dict, split: str | None = None) -> dict:
    ka, kb = _key_verdicts(a), _key_verdicts(b)
    keys = sorted(set(ka) | set(kb), key=lambda k: (k[0], k[1], k[2]))
    rows = []
    for k in keys:
        va, vb = ka.get(k), kb.get(k)
        sp = (vb or va or {}).get("split", "?")
        if split and sp != split:
            continue
        change = ("melhorou" if va and vb and not va.get("grounded") and vb.get("grounded") else
                  "piorou" if va and vb and va.get("grounded") and not vb.get("grounded") else
                  "igual" if va and vb else "só A" if va else "só B")
        rows.append({"source": k[0], "id": k[1], "run": k[2], "split": sp, "a": va, "b": vb, "change": change})
    by_split: dict[str, dict] = {}
    for sp in sorted({r["split"] for r in rows}):
        group = [r for r in rows if r["split"] == sp]
        by_split[sp] = {"a": _rate([r["a"] for r in group if r["a"]]), "b": _rate([r["b"] for r in group if r["b"]]),
                        "melhorou": sum(r["change"] == "melhorou" for r in group),
                        "piorou": sum(r["change"] == "piorou" for r in group)}
    return {"rows": rows, "by_split": by_split}


def to_markdown(result: dict, name_a: str, name_b: str) -> str:
    out = [f"# Juiz: antes × depois por caso\n\nA = `{name_a}` · B = `{name_b}`. Gerado por "
           "`python -m evals.judge_diff`; grounded e failure_type são do juiz (evals/judge.py), o motivo é o de B "
           "(ou o de A, se B não tem o caso).\n",
           "| split | grounded A | grounded B | melhorou | piorou |", "|---|---|---|---:|---:|"]
    out += [f"| {sp} | {s['a']} | {s['b']} | {s['melhorou']} | {s['piorou']} |"
            for sp, s in result["by_split"].items()]
    out += ["", "| caso | rodada | grounded A → B | failure_type A → B | mudança | motivo |",
            "|---|---:|---|---|---|---|"]
    for r in result["rows"]:
        reason = (r["b"] or r["a"] or {}).get("reason")
        out.append(f"| {r['id']} | {r['run']} | {_mark(r['a'])} → {_mark(r['b'])} | {_type(r['a'])} → {_type(r['b'])}"
                   f" | {r['change']} | {_cell(reason)} |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    ap.add_argument("--split", default=None, help="só um split (ex.: official)")
    ap.add_argument("--out", type=Path, default=None, help="grava o markdown (padrão: imprime)")
    args = ap.parse_args(argv)
    a = json.loads(args.before.read_text(encoding="utf-8"))
    b = json.loads(args.after.read_text(encoding="utf-8"))
    md = to_markdown(diff(a, b, args.split), args.before.as_posix(), args.after.as_posix())
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md, encoding="utf-8")
        print(f"gravado {args.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
