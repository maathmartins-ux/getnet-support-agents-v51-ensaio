"""Revisão humana do gold de retrieval e mapeamento do gold quando o corpus é re-cortado.

  python -m evals.retrieval_review --export [--k 5] [--out evals/review/retrieval_review.jsonl]
      top-k do retriever escolhido (data/retriever.json / RETRIEVER) para cada pergunta do gold, com o texto de cada
      trecho e se ele já está no gold. Quem revisa marca `label` (true/false) em cada candidato.
  python -m evals.retrieval_review --apply evals/review/retrieval_review.jsonl --reviewer "Nome"
      junta os rótulos num gold REVISADO separado (evals/retrieval_reviewed.jsonl), com quem revisou e quando.
      O gold original nunca é tocado; o eval mede os dois em separado (`run_evals --choose-retriever --gold ...`).
  python -m evals.retrieval_review --map-gold --from <corpus antigo> --out <gold mapeado>
      depois de re-cortar o corpus (ingest novo), cada trecho do gold vira o grupo de trechos NOVOS que contêm o
      texto dele (`relevant_groups`): o denominador do Recall@3 continua sendo o número de passagens do gold.

Só pergunta com TODOS os candidatos rotulados entra no revisado (revisão parcial não se mistura com o original).
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
REVIEW = HERE / "review" / "retrieval_review.jsonl"
REVIEWED = HERE / "retrieval_reviewed.jsonl"
MAP_MIN = 0.5  # fração dos 5-gramas em comum (do trecho velho OU do novo) para o trecho novo herdar o rótulo


def _gold_path() -> Path:
    from evals import run_evals

    return run_evals.RETRIEVAL  # lido na chamada: o conftest troca pela fixture do kit


def export(k: int = 5, out: Path | None = None, retriever=None, gold: Path | None = None) -> Path:
    from app.jsonl import read_family
    from app.rag import Gold, get_index, get_retriever
    from evals.retrieval_eval import _query

    retriever = retriever or get_retriever(rerank=None)
    index = get_index()
    out = out or REVIEW
    rows = []
    for r in read_family(gold or _gold_path()):
        g = Gold.from_row(r)
        units = g.resolve_groups(index.docs, index.aliases) if g.positive else []
        rel = set().union(*units) if units else set()
        cands = [{"id": h.doc.id, "url": h.doc.url, "title": h.doc.head, "text": h.doc.text,
                  "in_gold": h.doc.id in rel, "label": None}
                 for h in retriever.search(_query(r["question"]), k=k)]
        rows.append({"question": r["question"], "gold": sorted(rel), "retriever": retriever.name,
                     "candidates": cands, "reviewer": None, "reviewed_at": None})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    return out


def apply(review: Path, reviewer: str, out: Path | None = None, gold: Path | None = None,
          today: str | None = None) -> dict:
    """Gold revisado = original + candidatos marcados true − itens do gold marcados false, só p/ perguntas revisadas."""
    from app.jsonl import read_family

    if not reviewer.strip():
        raise ValueError("--reviewer é obrigatório: o gold revisado diz quem revisou")
    original = {r["question"]: r for r in read_family(gold or _gold_path())}
    out = out or REVIEWED
    date = today or datetime.date.today().isoformat()
    merged, skipped = [], []
    for line in review.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        labels = [c.get("label") for c in row.get("candidates", [])]
        if not labels or any(not isinstance(v, bool) for v in labels):
            skipped.append(row["question"])
            continue
        base = set((original.get(row["question"]) or {}).get("relevant") or row.get("gold") or [])
        added = sorted(c["id"] for c in row["candidates"] if c["label"] and c["id"] not in base)
        removed = sorted(c["id"] for c in row["candidates"] if c["label"] is False and c["id"] in base)
        merged.append({"question": row["question"], "relevant": sorted((base | set(added)) - set(removed)),
                       "added": added, "removed": removed, "reviewer": row.get("reviewer") or reviewer,
                       "reviewed_at": row.get("reviewed_at") or date, "retriever": row.get("retriever")})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in merged), encoding="utf-8")
    return {"path": str(out), "reviewed": len(merged), "skipped": skipped,
            "added": sum(len(x["added"]) for x in merged), "removed": sum(len(x["removed"]) for x in merged)}


def _shingles(text: str, n: int = 5) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", text.lower())
    return {tuple(words[i:i + n]) for i in range(max(1, len(words) - n + 1))} if words else set()


def map_gold(old_corpus: Path, out: Path, gold: Path | None = None) -> dict:
    """Gold por id do corpus antigo → `relevant_groups` no índice atual, por texto (sem tocar no gold original).

    Trecho novo entra no grupo da passagem velha se tem >= MAP_MIN dos 5-gramas dela (a passagem está nele) ou se
    >= MAP_MIN dos 5-gramas DELE vêm da passagem (a passagem foi dividida). O id antigo nunca é reaproveitado:
    "sup-duvidas-40" do corpus novo é outro texto.
    """
    from app.jsonl import read_family
    from app.rag import get_index, load_docs

    old = {d.id: d for d in load_docs(old_corpus)}
    new = get_index().docs
    new_sh = [(d.id, _shingles(d.text)) for d in new]
    rows, lost = [], []
    for r in read_family(gold or _gold_path()):
        groups = []
        for gid in r.get("relevant") or []:
            sh = _shingles(old[gid].text) if gid in old else set()
            group = sorted(i for i, s in new_sh if sh and s and (len(sh & s) / len(sh) >= MAP_MIN
                                                                    or len(sh & s) / len(s) >= MAP_MIN))
            if not group:
                lost.append(gid)
            groups.append(group)
        row = {"question": r["question"], "relevant": [], "relevant_groups": groups,
               "mapped_from": sorted(r.get("relevant") or [])}
        if not r.get("relevant"):
            row.pop("relevant_groups")
        rows.append(row)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    return {"path": str(out), "questions": len(rows), "passages": sum(len(r.get("mapped_from", [])) for r in rows),
            "lost": lost}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--export", action="store_true", help="top-k por pergunta para revisão humana")
    mode.add_argument("--apply", type=Path, help="arquivo de revisão preenchido → gold revisado separado")
    mode.add_argument("--map-gold", action="store_true", help="gold do corpus antigo → grupos no corpus atual")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--gold", type=Path, help="gold de origem (padrão evals/retrieval.jsonl + .d/)")
    ap.add_argument("--reviewer", default="", help="nome de quem revisou (obrigatório com --apply)")
    ap.add_argument("--from", dest="old", type=Path, help="pasta do corpus antigo (com --map-gold)")
    args = ap.parse_args(argv)
    if args.export:
        print(f"Para revisar: {export(args.k, args.out, gold=args.gold)} (marque `label` true/false em cada candidato)")
        return 0
    if args.apply:
        print(json.dumps(apply(args.apply, args.reviewer, args.out, args.gold), ensure_ascii=False))
        return 0
    if not args.old or not args.out:
        ap.error("--map-gold precisa de --from <corpus antigo> e --out <gold mapeado>")
    print(json.dumps(map_gold(args.old, args.out, args.gold), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
