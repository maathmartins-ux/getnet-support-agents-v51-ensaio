"""Medida offline (sem API) das partes determinísticas da checagem de frases sobre respostas reais já julgadas.

Uso:
  python -m evals.claims_proxy --repo <repositório julgado> [--labels evals/proxy/v4_judge_cited.json]
                               [--out <relatório>.json]

Lê as linhas do eval ao vivo (`evals/results/live_official.json`) e os vereditos do juiz (`judge.json`) de outro
repositório, e reproduz sobre cada resposta, com a evidência que a linha guardou e o cartão `policy:capabilities`
gerado do registro de ferramentas daquele repositório (metadados no arquivo de rótulos): checagem numérica
(app/grounding.py), fallback léxico de frases e checagem de ação oferecida (app/claims.py). O verificador LLM, que é
o caminho principal com chave, NÃO roda aqui: nada desta medida diz quanto ele acerta.

Saída: das frases que o juiz citou nas reprovações, quantas cada mecanismo aponta (`catch`) e quantas regras
verdadeiras deixam de ser apontadas com o cartão (`keep`); nas respostas aprovadas pelo juiz, quantas frases seriam
sinalizadas (fallback léxico: só flag) ou cortadas (ação oferecida indisponível, com CLAIMS_POLICY=remove).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
LABELS = HERE / "proxy" / "v4_judge_cited.json"


def _rows_and_verdicts(repo: Path) -> list[tuple[dict, dict]]:
    """Linha do eval + veredito, casados pela ordem (o juiz percorre as linhas com resposta na ordem do arquivo)."""
    results = repo / "evals" / "results"
    rows = [r for r in json.loads((results / "live_official.json").read_text(encoding="utf-8"))["rows"]
            if r.get("answer")]
    verdicts = [v for v in json.loads((results / "judge.json").read_text(encoding="utf-8"))["verdicts"]
                if v.get("source") == "live_official.json"]
    if [r["id"] for r in rows] != [v["id"] for v in verdicts]:
        raise SystemExit("linhas e vereditos fora de ordem: não dá para casar sem `run` no veredito")
    return list(zip(rows, verdicts, strict=True))


def _language(row: dict) -> str:
    return row.get("language_declared") or row.get("expected_language") or "pt"


def analyse(repo: Path, labels: dict) -> dict:
    from app import capabilities, claims, grounding

    tools = labels["tools"]
    pairs = _rows_and_verdicts(repo)
    by_case: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for c in labels["cited"]:
        by_case[(c["id"], c["run"])].append(c)
    out_rows, label_hits = [], []
    for row, verdict in pairs:
        lang = _language(row)
        card = capabilities.card(lang, tools=tools, extra=[])
        evidence = list(row.get("evidence") or [])
        sentences, with_card, _ = claims.check(row["answer"], evidence, row["message"], tools=tools, use_llm=False,
                                               card=card)
        _, no_card, _ = claims.check(row["answer"], evidence, row["message"], tools=tools, use_llm=False)
        flagged = {u["index"]: u for u in with_card}
        flagged_nc = {u["index"]: u for u in no_card}
        numbers = {s.index: grounding.unsupported_numbers(s.text, [*evidence, card], question=row["message"])
                   for s in sentences}
        cited = by_case.get((row["id"], row.get("run", 0)), [])
        matched: set[int] = set()
        for c in cited:
            hit = [s for s in sentences if claims.fold(c["sentence"]) in claims.fold(s.text)]
            idx = {s.index for s in hit}
            matched |= idx
            label_hits.append({**c, "found_sentence": bool(hit),
                               "numbers": any(numbers[i] for i in idx),
                               "lexical": any(flagged.get(i, {}).get("source") == "lexical" for i in idx),
                               "offer": any(flagged.get(i, {}).get("source") == "offer" for i in idx),
                               "lexical_no_card": any(flagged_nc.get(i, {}).get("source") == "lexical" for i in idx)})
        others = [s for s in sentences if s.index not in matched]
        out_rows.append({
            "id": row["id"], "run": row.get("run", 0), "judge_grounded": bool(verdict.get("grounded")),
            "sentences": len(sentences), "checkable": sum(s.checkable for s in sentences),
            "lexical_flags": sum(1 for s in others if flagged.get(s.index, {}).get("source") == "lexical"),
            "offer_cuts": sum(1 for s in others if flagged.get(s.index, {}).get("source") == "offer"),
            "number_flags": sum(1 for s in others if numbers[s.index]),
            "flagged_examples": [flagged[s.index]["sentence"][:120] for s in others if s.index in flagged][:3]})
    return {"rows": out_rows, "labels": label_hits, "summary": summarize(out_rows, label_hits)}


def summarize(rows: list[dict], labels: list[dict]) -> dict:
    catch = [x for x in labels if x["expect"] == "catch"]
    keep = [x for x in labels if x["expect"] == "keep"]
    accepted = [r for r in rows if r["judge_grounded"]]
    rejected = [r for r in rows if not r["judge_grounded"]]
    det = [x for x in catch if x["numbers"] or x["lexical"] or x["offer"]]
    non_number = [x for x in catch if x["type"] != "invented_number"]
    return {
        "official_answers": len(rows), "judge_rejected": len(rejected), "judge_accepted": len(accepted),
        "cited_catch": len(catch),
        "caught_by_numbers": sum(x["numbers"] for x in catch),
        "caught_by_lexical": sum(x["lexical"] for x in catch),
        "caught_by_offer": sum(x["offer"] for x in catch),
        "caught_any_deterministic": len(det),
        "cited_non_number": len(non_number),
        "non_number_caught_by_lexical": sum(x["lexical"] for x in non_number),
        "cited_keep": len(keep),
        "keep_flagged_with_card": sum(x["lexical"] or x["offer"] for x in keep),
        "keep_flagged_without_card": sum(x["lexical_no_card"] or x["offer"] for x in keep),
        "rejected_other_sentences_lexical_flags": sum(r["lexical_flags"] for r in rejected),
        "accepted_answers_with_lexical_flag": sum(1 for r in accepted if r["lexical_flags"]),
        "accepted_lexical_flags": sum(r["lexical_flags"] for r in accepted),
        "accepted_checkable_sentences": sum(r["checkable"] for r in accepted),
        "accepted_answers_cut_by_offer_check": sum(1 for r in accepted if r["offer_cuts"]),
        "accepted_number_flags": sum(r["number_flags"] for r in accepted),
        "labels_without_sentence": sum(not x["found_sentence"] for x in labels),
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True, help="repositório com evals/results/{live_official,judge}.json")
    ap.add_argument("--labels", type=Path, default=LABELS)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    # glossário pt<->en do repositório medido (ponte entre resposta en e fonte pt no fallback léxico)
    if (args.repo / "data" / "glossary.json").exists():
        os.environ["DATA_DIR"] = str(args.repo / "data")
    os.environ.setdefault("LLM_PROVIDER", "offline")
    report = analyse(args.repo, json.loads(args.labels.read_text(encoding="utf-8")))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
