"""Fila de revisão dos candidatos a caso vindos do 👎 (app/candidates.py).

  python -m evals.candidates --review                  lista os pendentes (pergunta, resposta, comentário, versões)
  python -m evals.candidates --accept <id> --split <s> [--intent I] [--handoff yes|no] [--language pt|en]
                                                       leva o candidato REVISADO para evals/cases.d/<s>.jsonl
  python -m evals.candidates --reject <id>             descarta (fica registrado como rejeitado)

Kit v5.4 (ideia do Skywalker, nota 10: feedback como score no trace e fila de revisão). Nada entra num split sem uma
pessoa decidir a expectativa: o 👎 diz que a resposta foi ruim, não qual seria a certa.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
CASES_D = HERE / "cases.d"


def review(rows: list[dict]) -> str:
    pending = [r for r in rows if r.get("status") == "pending"]
    if not pending:
        return "nenhum candidato pendente"
    out = []
    for r in pending:
        versions = ", ".join(f"{k}={v}" for k, v in sorted((r.get("prompt_versions") or {}).items())) or "—"
        out.append(f"[{r['id']}] intenção {r.get('intent') or '—'} · prompts {versions}\n"
                   f"  cliente: {r.get('question', '')[:300]}\n  resposta: {r.get('answer', '')[:300]}\n"
                   f"  comentário: {r.get('comment') or '—'} · evidência: {len(r.get('evidence') or [])} trechos")
    return "\n".join(out)


def accept(rows: list[dict], cid: str, split: str, intent: str | None = None, handoff: str | None = None,
           language: str | None = None, cases_dir: Path | None = None) -> dict:
    row = next((r for r in rows if r.get("id") == cid), None)
    if row is None or row.get("status") != "pending":
        raise KeyError(f"candidato pendente {cid!r} não encontrado")
    if not row.get("question"):
        raise ValueError("candidato sem a pergunta do cliente: não dá para virar caso")
    expect: dict = {}
    if intent:
        expect["intent"] = intent
    if handoff in ("yes", "no"):
        expect["handoff"] = handoff == "yes"
    if language:
        expect["language"] = language
    case = {"id": cid, "split": split, "message": row["question"], "user_id": row.get("user_id") or "u1",
            "expect": expect, "origin": "feedback", "trace_id": row["trace_id"]}
    target = (cases_dir or CASES_D) / f"{split}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(case, ensure_ascii=False) + "\n")
    row["status"], row["accepted_to"] = "accepted", str(target)
    return case


def main(argv: list[str] | None = None) -> int:
    from app import candidates

    ap = argparse.ArgumentParser(prog="python -m evals.candidates")
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--accept")
    ap.add_argument("--reject")
    ap.add_argument("--split")
    ap.add_argument("--intent")
    ap.add_argument("--handoff", choices=["yes", "no"])
    ap.add_argument("--language", choices=["pt", "en"])
    args = ap.parse_args(argv)
    rows = candidates.read_all()
    if args.accept:
        if not args.split:
            ap.error("--accept pede --split")
        case = accept(rows, args.accept, args.split, args.intent, args.handoff, args.language)
        candidates.write_all(rows)
        print(f"{case['id']} → evals/cases.d/{args.split}.jsonl (expect {case['expect'] or 'vazio: preencha'})")
    elif args.reject:
        row = next((r for r in rows if r.get("id") == args.reject), None)
        if row is None:
            ap.error(f"candidato {args.reject!r} não encontrado")
        row["status"] = "rejected"
        candidates.write_all(rows)
        print(f"{args.reject} rejeitado")
    else:
        print(review(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
