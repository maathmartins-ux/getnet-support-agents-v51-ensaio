"""Análise de erros em traces ao vivo: rascunho do modelo, revisão do dono linha a linha, modos com uma checagem cada.

Fluxo:
  python -m evals.error_analysis --export 60            # ~60 traces de evals/results/live_*.json, evidência inteira,
        # rascunho passa/falha + modo + motivo de uma linha (LLM juiz com os CRITÉRIOS abaixo; sem LLM: das checagens)
        # → evals/error_analysis.csv
  python -m evals.error_analysis --review official-01#0=ok official-02#0=fail:escalou_sem_precisar o fato estava
        # ok = aceita o rascunho; pass / fail:<modo> <motivo> = edição (só conta como edição se mudar algo)
  python -m evals.error_analysis --report     # edições, modos e checagem por modo → results/error_analysis.json
  python -m evals.error_analysis --checks --pattern "replay_*.json"   # as checagens dos modos sobre outra rodada
        # (gravação, replay offline do cassete): taxa de cada modo, sem LLM e sem rede

Separado da rotulagem cega (evals/label.py, scripts/label_page.py): estes traces são de AJUSTE (o rascunho do modelo
fica no CSV daqui e nunca entra em live_*.json, então a página cega não tem como mostrá-lo) e todo split `heldout*`
fica de fora (heldout, heldout_h3...: o held-out continua intocado; a régua da rodada 10 leu "o held-out deixou de ser
cego em 4 classes de erro", e um lote cego novo só serve se nenhuma ferramenta o ler). Cada modo tem nome de
comportamento e UMA checagem binária em MODE_CHECKS,
que roda sobre a linha gravada; modo que o dono criar sem checagem aparece no relatório como "sem checagem".
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
RESULTS = HERE / "results"
CSV_PATH = HERE / "error_analysis.csv"
OUT = RESULTS / "error_analysis.json"
# o held-out é a medida final: ajuste nele contamina. Por prefixo (evals.failure_modes.is_blind): um lote cego novo
# (heldout_h3) ficava dentro com a lista {"heldout"}
EXCLUDED_SPLITS = {"heldout*"}
FIELDS = ["chave", "id", "run", "split", "pergunta", "resposta", "humano_na_resposta", "fontes", "ferramentas",
          "contexto", "rascunho", "modo_rascunho", "motivo_rascunho", "origem_rascunho", "revisao", "final", "modo",
          "motivo"]
CRITERIA = (
    "Critérios (escritos antes de olhar os traces): PASSA quando a resposta atende ao que o cliente pediu, toda "
    "afirmação está nas fontes ou nos dados de ferramenta, está no idioma da pergunta e só passa para um humano "
    "quando nada na evidência responde ou a ação exige um atendente. FALHA no primeiro destes modos que aparecer: "
    "escalou_sem_precisar (foi ao humano com a resposta na evidência), diz_que_falta_o_que_a_evidencia_tem (diz que "
    "não há a informação e ela está nas fontes), fato_de_referencia_ausente (responde sem o fato pedido), "
    "numero_sem_base, afirmacao_sem_base, idioma_errado, sem_fonte_citada (responde sem citar fonte nem dado), "
    "rota_errada (agente errado para a pergunta). Se nenhum servir, use outro:<nome curto de comportamento>.")
SYSTEM = ("Você rascunha o rótulo de um trace de atendimento para o dono revisar. " + CRITERIA +
          " Devolva verdict (pass ou fail), mode (o modo, vazio quando passa) e reason (uma linha, em português).")
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["verdict", "mode", "reason"],
          "properties": {"verdict": {"type": "string", "enum": ["pass", "fail"]}, "mode": {"type": "string"},
                         "reason": {"type": "string"}}}
MISSING = re.compile(r"não (encontrei|tenho|há|consta)|nao encontrei|sem informaç|not (find|found|have)|"
                     r"no information|isn't in|não está n", re.IGNORECASE)


# ---------- checagens binárias por modo (True = a linha mostra a falha); rodam sobre a linha gravada ----------

def _facts(case: dict | None) -> list[str]:
    return ((case or {}).get("expect") or {}).get("facts") or []


def _all_in(patterns: list[str], text: str) -> bool:
    return bool(patterns) and all(re.search(p, text or "", re.IGNORECASE) for p in patterns)


def _handed(row: dict) -> bool:
    return bool(row.get("handoff_required")) or "escalation" in (row.get("route") or [])


def check_escalated(row: dict, case: dict | None) -> bool:
    """Foi ao humano num caso que esperava resposta (handoff errado, ou caso com fatos que não resolveu)."""
    checks = row.get("checks") or {}
    return _handed(row) and (checks.get("handoff") is False or "resolved" in checks)


def check_missing_when_present(row: dict, case: dict | None) -> bool:
    """Diz que falta (ou escala) e todos os fatos de referência estão no que o redator viu."""
    says_missing = _handed(row) or bool(MISSING.search(row.get("answer") or ""))
    return says_missing and _all_in(_facts(case), row.get("context") or "")


def check_fact_absent(row: dict, case: dict | None) -> bool:
    """Respondeu (sem humano) e algum fato de referência não está na resposta."""
    return bool(_facts(case)) and not _handed(row) and not _all_in(_facts(case), row.get("answer") or "")


def check_number(row: dict, case: dict | None) -> bool:
    return bool(row.get("unsupported_numbers"))


def check_claim(row: dict, case: dict | None) -> bool:
    return any(c.get("action") != "removed" for c in row.get("unsupported_claims") or [] if isinstance(c, dict))


def check_language(row: dict, case: dict | None) -> bool:
    exp, got = row.get("expected_language"), row.get("language_detected")
    return bool(exp and got and exp != got)


def check_no_source(row: dict, case: dict | None) -> bool:
    answered = bool((row.get("answer") or "").strip()) and not _handed(row) and not row.get("blocked")
    tools_ok = any(t.get("ok", True) for t in row.get("tool_calls") or [] if isinstance(t, dict))
    return answered and not row.get("sources") and not row.get("source_ids") and not tools_ok


def check_route(row: dict, case: dict | None) -> bool:
    return (row.get("checks") or {}).get("intent") is False


MODE_CHECKS: dict[str, Callable[[dict, dict | None], bool]] = {
    "escalou_sem_precisar": check_escalated,
    "diz_que_falta_o_que_a_evidencia_tem": check_missing_when_present,
    "fato_de_referencia_ausente": check_fact_absent,
    "numero_sem_base": check_number,
    "afirmacao_sem_base": check_claim,
    "idioma_errado": check_language,
    "sem_fonte_citada": check_no_source,
    "rota_errada": check_route,
}


def first_mode(row: dict, case: dict | None) -> str:
    """O 1º modo (na ordem de MODE_CHECKS) que a linha mostra; "" se nenhum."""
    return next((m for m, fn in MODE_CHECKS.items() if fn(row, case)), "")


# ---------- traces ----------

def key_of(row: dict) -> str:
    return f"{row['id']}#{row.get('run', 0)}"


def load_rows(results: Path = RESULTS, pattern: str = "live_*.json") -> list[dict]:
    """Todas as execuções (todas as rodadas) dos arquivos, menos o held-out. `.degraded`/`.aborted_*` ficam fora."""
    from evals.failure_modes import is_blind

    rows, seen = [], set()
    for path in sorted(results.glob(pattern)):
        if path.name.count(".") > 1:
            continue
        for row in json.loads(path.read_text(encoding="utf-8")).get("rows", []):
            if is_blind(row.get("split")) or key_of(row) in seen:
                continue
            seen.add(key_of(row))
            rows.append(row)
    return rows


def _cases() -> dict[str, dict]:
    try:
        from evals import run_evals

        return {c["id"]: c for c in run_evals.load_cases()}
    except (OSError, ValueError):
        return {}


def _tools(row: dict) -> str:
    return " ".join(t.get("name", "?") if isinstance(t, dict) else str(t) for t in row.get("tool_calls") or [])


def draft_from_checks(row: dict, case: dict | None) -> dict:
    """Rascunho sem LLM: o 1º modo cujas checagens a linha mostra, ou as checagens automáticas."""
    mode = first_mode(row, case)
    failed = [k for k, v in (row.get("checks") or {}).items() if v is False]
    if mode:
        return {"verdict": "fail", "mode": mode, "reason": (MODE_CHECKS[mode].__doc__ or mode).strip().split("\n")[0],
                "source": "checks"}
    if failed or row.get("crash"):
        why = row.get("crash") or f"checagem {failed[0]} falhou"
        return {"verdict": "fail", "mode": "outro:" + (failed[0] if failed else "crash"), "reason": why,
                "source": "checks"}
    return {"verdict": "pass", "mode": "", "reason": "todas as checagens passam", "source": "checks"}


def draft_with_llm(llm, row: dict, case: dict | None) -> dict:
    prompt = (f"Pergunta: {row.get('message')}\n\nFoi para um humano: {'sim' if _handed(row) else 'não'}\n\n"
              f"Fatos de referência do caso (regex): {_facts(case) or '—'}\n\n"
              f"O que o redator tinha (evidência inteira):\n{row.get('context') or '(nada)'}\n\n"
              f"Ferramentas: {_tools(row) or '—'}\n\nResposta: {row.get('answer')}")
    v = llm.complete(SYSTEM, [{"role": "user", "content": prompt}], max_tokens=1024, schema=SCHEMA).json()
    reason = " ".join(str(v.get("reason", "")).split())[:200]
    return {"verdict": v.get("verdict", "fail"), "mode": "" if v.get("verdict") == "pass" else v.get("mode", ""),
            "reason": reason, "source": getattr(llm, "model", "llm")}


def export(n: int = 60, results: Path = RESULTS, path: Path = CSV_PATH, seed: int = 7, llm=None) -> int:
    """Sorteia `n` traces (estratificado por split, seed fixa) e grava o CSV com o rascunho. Evidência inteira."""
    from evals.label import sample

    rows = sample(load_rows(results), n, seed)
    cases = _cases()
    out = []
    for r in rows:
        case = cases.get(r["id"])
        d = draft_with_llm(llm, r, case) if llm is not None else draft_from_checks(r, case)
        out.append({"chave": key_of(r), "id": r["id"], "run": r.get("run", 0), "split": r.get("split"),
                    "pergunta": r.get("message"), "resposta": r.get("answer"),
                    "humano_na_resposta": "sim" if _handed(r) else "não",
                    "fontes": " ".join(r.get("source_ids") or []), "ferramentas": _tools(r),
                    "contexto": r.get("context") or "", "rascunho": d["verdict"], "modo_rascunho": d["mode"],
                    "motivo_rascunho": d["reason"], "origem_rascunho": d["source"], "revisao": "", "final": "",
                    "modo": "", "motivo": ""})
    _write(path, out)
    return len(out)


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def read(path: Path = CSV_PATH) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return [{**{k: "" for k in FIELDS}, **row} for row in csv.DictReader(fh)]


def review(pairs: list[str], path: Path = CSV_PATH) -> dict:
    """`chave=ok` aceita o rascunho; `chave=pass` ou `chave=fail:<modo> <motivo>` grava a decisão do dono. Decisão igual
    ao rascunho (veredito e modo) conta como aceite, não como edição."""
    rows = read(path)
    index = {r["chave"]: r for r in rows}
    done, ignored = 0, []
    for pair in pairs:
        key, _, rest = pair.partition("=")
        key, rest = key.strip(), rest.strip()
        verdict, _, note = rest.partition(":")
        verdict = verdict.strip().lower()
        if key not in index or verdict not in ("ok", "pass", "fail"):
            ignored.append(pair)
            continue
        r = index[key]
        if verdict == "ok":
            final, mode, why = r["rascunho"], r["modo_rascunho"], r["motivo_rascunho"]
        elif verdict == "pass":
            final, mode, why = "pass", "", note.strip()
        else:
            mode, _, why = note.strip().partition(" ")
            final, why = "fail", why.strip()
        if not why and (final, mode) == (r["rascunho"], r["modo_rascunho"]):
            why = r["motivo_rascunho"]
        edited = (final, mode) != (r["rascunho"], r["modo_rascunho"])
        r.update(final=final, modo=mode, motivo=why, revisao="editado" if edited else "aceito")
        done += 1
    _write(path, rows)
    for pair in ignored:
        print(f"ignorado: {pair!r} (use CHAVE=ok | CHAVE=pass | CHAVE=fail:<modo> <motivo>)", file=sys.stderr)
    return {"reviewed": done, "ignored": len(ignored)}


def _rate(k: int, n: int) -> float | None:
    return round(k / n, 3) if n else None


def report(path: Path = CSV_PATH, results: Path = RESULTS, out: Path = OUT) -> dict:
    """Edições do dono, modos (pela decisão final) e, por modo com checagem, o acerto da checagem contra o dono."""
    rows = read(path)
    live = {key_of(r): r for r in load_rows(results)}
    cases = _cases()
    reviewed = [r for r in rows if r["revisao"] in ("aceito", "editado")]
    edits = sorted(r["chave"] for r in reviewed if r["revisao"] == "editado")
    fails = [r for r in reviewed if r["final"] == "fail"]
    modes: dict[str, dict] = {}
    for r in fails:
        m = modes.setdefault(r["modo"] or "sem_modo", {"count": 0, "keys": [], "example": r["motivo"]})
        m["count"] += 1
        m["keys"].append(r["chave"])
    for name, m in modes.items():
        fn = MODE_CHECKS.get(name)
        m["check"] = fn.__name__ if fn else None
        if fn is None:
            continue
        pairs = [(fn(live[r["chave"]], cases.get(r["id"])), r["final"] == "fail" and r["modo"] == name)
                 for r in reviewed if r["chave"] in live]
        pos, neg = [c for c, h in pairs if h], [c for c, h in pairs if not h]
        m.update(check_positives=len(pos), check_tpr=_rate(sum(pos), len(pos)),
                 check_tnr=_rate(sum(not c for c in neg), len(neg)))
    rep = {"traces": len(rows), "reviewed": len(reviewed), "pending": len(rows) - len(reviewed),
           "edits": len(edits), "edit_rate": _rate(len(edits), len(reviewed)), "edited": edits,
           "owner_pass": sum(r["final"] == "pass" for r in reviewed), "owner_fail": len(fails),
           "draft_source": sorted({r["origem_rascunho"] for r in rows if r["origem_rascunho"]}),
           "modes": dict(sorted(modes.items(), key=lambda kv: -kv[1]["count"])),
           "unchecked_modes": sorted(n for n, m in modes.items() if m["check"] is None),
           "excluded_splits": sorted(EXCLUDED_SPLITS)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


def run_checks(results: Path = RESULTS, pattern: str = "live_*.json") -> dict:
    """Taxa de cada modo (checagem binária) sobre as linhas dos arquivos: roda sobre a gravação ou o replay offline."""
    rows = load_rows(results, pattern)
    cases = _cases()
    out = {}
    for name, fn in MODE_CHECKS.items():
        hit = [key_of(r) for r in rows if fn(r, cases.get(r["id"]))]
        out[name] = {"rows": len(rows), "hits": len(hit), "rate": _rate(len(hit), len(rows)), "keys": hit[:20]}
    return {"pattern": pattern, "rows": len(rows), "modes": out}


def render(rep: dict) -> str:
    """Markdown curto do relatório (para docs/FAILURE_MODES.md ou o README)."""
    origin = ", ".join(rep["draft_source"])
    lines = [f"{rep['traces']} traces ao vivo de ajuste (held-out fora), rascunho de `{origin}`;"
             f" o dono revisou {rep['reviewed']} e editou **{rep['edits']}** ({rep['edit_rate']}); passa "
             f"{rep['owner_pass']}, falha {rep['owner_fail']}.", "",
             "| modo | falhas | checagem | TPR × dono | TNR × dono |", "|---|---:|---|---:|---:|"]
    for name, m in rep["modes"].items():
        lines.append(f"| {name} | {m['count']} | {('`' + m['check'] + '`') if m['check'] else 'sem checagem'} | "
                     f"{m.get('check_tpr', '—')} | {m.get('check_tnr', '—')} |")
    if rep["unchecked_modes"]:
        lines += ["", "Modo sem checagem (escreva uma em `evals/error_analysis.py::MODE_CHECKS`): "
                  + ", ".join(rep["unchecked_modes"]) + "."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", type=int, metavar="N", help="sorteia N traces ao vivo e grava o CSV com o rascunho")
    ap.add_argument("--draft", choices=("llm", "checks"), default="llm",
                    help="rascunho pelo LLM juiz (padrão; cai para as checagens sem LLM_PROVIDER=anthropic)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--review", nargs="+", metavar="CHAVE=ok|pass|fail:modo motivo")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--md", type=Path, help="com --report: grava também o markdown")
    ap.add_argument("--checks", action="store_true", help="taxa de cada modo sobre os arquivos de --pattern")
    ap.add_argument("--pattern", default="live_*.json")
    ap.add_argument("--results", type=Path, default=RESULTS)
    args = ap.parse_args(argv)
    if args.export:
        llm = None
        if args.draft == "llm":
            from app.config import llm_provider
            from app.llm import get_judge_llm

            llm = get_judge_llm() if llm_provider() == "anthropic" else None
            if llm is None:
                print("sem LLM_PROVIDER=anthropic: rascunho pelas checagens (origem 'checks')", file=sys.stderr)
        n = export(args.export, args.results, seed=args.seed, llm=llm)
        print(f"{n} traces em {CSV_PATH.name}: revise TODAS as linhas (--review CHAVE=ok ou a correção)")
    if args.review:
        print(json.dumps(review(args.review), ensure_ascii=False))
    if args.report:
        rep = report(results=args.results)
        print(json.dumps({k: v for k, v in rep.items() if k != "modes"}, ensure_ascii=False))
        if args.md:
            args.md.write_text(render(rep) + "\n", encoding="utf-8")
    if args.checks:
        print(json.dumps(run_checks(args.results, args.pattern), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
