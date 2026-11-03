"""Placar honesto: cada número que pesa na nota, ao lado da referência que a avaliação usa, os ruins junto com os bons.

Kit v5.4 (metodologia do nelsondell, 9,5): sem ícone de "falhou" e sem meta própria. Cada referência é a que a
correção formal da v4 citou como faixa de finalista; o que fica abaixo aparece com a palavra "abaixo da referência"
e a causa vai na seção de limites do README, com o mecanismo e o número (o avaliador lê ❌ como "falhou").

1ª linha = oficiais resolvidas (sem humano E todo `expect.facts` na resposta E fonte citada, contrato da SPEC), e
"helpful" do juiz ao lado de "grounded": fundamentada sozinha aprova a resposta que só passa para um humano.

Uso: python scripts/scorecard.py            (imprime a tabela; o README a recebe pelo bloco `scorecard`)

Lê só o que está commitado em evals/results/ (offline, ao vivo por split, juiz, rótulos humanos). Métrica sem
arquivo sai "não medido", nunca some: quem lê vê o buraco. As metas são as que a avaliação usa para a faixa de
finalista (qualidade semântica: groundedness ≥ 90% nos cenários oficiais; busca: Recall@3 ≥ 0,85 e MRR ≥ 0,80;
memória: pass@1 ≥ 85%; avaliação independente: 2 rotuladores e held-out com ≥ 80 casos).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results"


@dataclass(frozen=True)
class Target:
    key: str
    label: str
    goal: float
    unit: str  # "%" (0–100), "frac" (0–1), "n" (contagem) ou "usd"
    where: str  # arquivo e campo de onde o número vem
    diagnostic: bool = False  # mostrado, sem status de meta: explica outro número, não é a medida


TARGETS = (
    # manchete (1ª linha): resposta certa, não só fundamentada. V5: "fundamentadas 1,00" contava "passei para um
    # humano" como acerto; o mesmo juiz dava helpful 0,733 e esse número não estava no placar.
    Target("official_resolved", "Oficiais resolvidas (sem humano + todo fato + fonte)", 0.90, "frac",
           "live_official.json resolved"),
    Target("official_resolved_k", "Oficiais resolvidas: pass^k (todas as rodadas)", 0.90, "frac",
           "live_official.json resolved"),
    Target("official_helpful", "Juiz: respostas oficiais úteis (helpful)", 0.90, "frac",
           "judge.json by_split.official"),
    Target("official_grounded", "Juiz: respostas oficiais fundamentadas", 0.90, "frac", "judge.json by_split.official"),
    Target("official_numbers", "Oficiais: números com base na evidência", 95.0, "%", "live_official.json numbers_acc"),
    Target("official_pass_k", "Oficiais: pass^k (todas as rodadas passam)", 0.90, "frac", "live_official.json"),
    Target("memory_pass_1", "Memória ao vivo: pass@1", 0.85, "frac", "live_memory.json stability"),
    Target("memory_numbers", "Memória ao vivo: números com base", 95.0, "%", "live_memory.json numbers_acc"),
    Target("recall3", "Busca: Recall@3", 0.85, "frac", "latest.json retrieval"),
    Target("mrr", "Busca: MRR", 0.80, "frac", "latest.json retrieval"),
    # o redator lê os 5 primeiros (faq_top_k): cobertura que importa para a resposta (método do nelsondell)
    Target("recall5", "Busca: Recall@5 (o que o redator lê)", 0.90, "frac", "latest.json retrieval", diagnostic=True),
    Target("heldout_cases", "Held-out cego: casos", 80, "n", "latest.json metrics.heldout"),
    # ponta a ponta: o humano diz se a resposta serve; a intenção (taxonomia) é diagnóstico (estudo nelsondell §3.4)
    Target("heldout_e2e", "Held-out cego: ponta a ponta (humano passa)", 0.80, "frac", "human_review.json heldout"),
    Target("heldout_intent", "Held-out cego: intenção (diagnóstico)", 85.0, "%", "latest.json metrics.heldout",
           diagnostic=True),
    Target("raters", "Rotuladores humanos independentes", 2, "n", "human_review.json"),
    # Ensaio v5.4: o rótulo dizia "humano" para o gabarito de calibração escrito pela frente Q (agente) e a ENTREGA
    # saiu com "juiz × humano kappa 1,00" sem nenhum humano. Concordância com pessoas é o juiz_x_humano do label.py.
    Target("judge_kappa", "Juiz × gabarito de calibração (rótulos da SPEC, não humanos): kappa", 0.80, "frac",
           "judge.json calibration"),
    # regra fixada antes de medir (nelsondell): 1 = validado (>= 10 por classe, TPR e TNR >= 0,8); 0 = só regressão
    Target("judge_validated", "Juiz validado contra o gabarito de calibração (1 = sim, regra fixada antes)", 1, "n",
           "judge.json calibration.validation"),
    # custo de operação medido, não suposto: gasto total ao vivo ÷ turnos resolvidos sem humano (todos os splits
    # completos), e a fração resolvida (método do nelsondell: "custo por turno resolvido" no README)
    Target("cost_per_resolved", "Custo por turno resolvido sem humano (ao vivo)", 0.05, "usd",
           "live_*.json spent_usd ÷ linhas sem handoff", diagnostic=True),
    Target("resolved_fraction", "Turnos resolvidos sem humano (ao vivo, todos os splits)", 0.80, "frac",
           "live_*.json linhas sem handoff", diagnostic=True),
)


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _complete(report: dict | None) -> dict | None:
    """Rodada degradada ou abortada não conta como medida (fica no arquivo `.degraded.json` à parte)."""
    return report if report and report.get("status") in (None, "complete", "ran") else None


def official_resolved(report: dict) -> tuple[float | None, float | None]:
    """(taxa por execução, pass^k) das oficiais resolvidas; relatório antigo sem o bloco `resolved` é recontado das
    linhas (checagem `resolved`); sem nenhuma linha com ela (caso sem expect.facts) = não medido."""
    s = ((report.get("resolved") or {}).get("by_split") or {}).get("official")
    if s:
        return s.get("rate"), s.get("pass_hat_k")
    by_case: dict[str, list[bool]] = {}
    for r in report.get("rows") or []:
        if r.get("split") == "official" and "resolved" in (r.get("checks") or {}):
            by_case.setdefault(r["id"], []).append(bool(r["checks"]["resolved"]) and not r.get("crash"))
    runs = [v for vs in by_case.values() for v in vs]
    if not runs:
        return None, None
    return round(sum(runs) / len(runs), 4), round(sum(all(vs) for vs in by_case.values()) / len(by_case), 4)


def cost_per_resolved(results: Path = RESULTS) -> tuple[float | None, float | None]:
    """(US$ por turno resolvido sem humano, fração resolvida) sobre todos os live_*.json completos.

    Resolvido = a linha respondeu, não pediu humano e não quebrou. O denominador do custo é o que o negócio compra
    (atendimento que não precisou de gente); o gasto inclui os turnos que escalaram e os de histórico."""
    spent, resolved, total = 0.0, 0, 0
    for path in sorted(results.glob("live_*.json")):
        rep = _complete(_load(path))
        if not rep or path.name.count(".") > 1:  # live_x.aborted_max_usd.json e afins ficam fora
            continue
        rows = rep.get("rows") or []
        spent += float(rep.get("spent_usd") or 0.0)
        total += len(rows)
        resolved += sum(1 for r in rows if r.get("answer") and not r.get("handoff_required") and not r.get("crash"))
    if not total:
        return None, None
    return (round(spent / resolved, 5) if resolved else None), round(resolved / total, 4)


def measure(results: Path = RESULTS) -> dict[str, float | None]:
    latest = _load(results / "latest.json") or {}
    official = _complete(_load(results / "live_official.json")) or {}
    memory = _complete(_load(results / "live_memory.json")) or {}
    judge = _load(results / "judge.json") or {}
    human = _load(results / "human_review.json") or {}
    ret = latest.get("retrieval") or {}
    held = (latest.get("metrics") or {}).get("heldout") or {}
    jo = (judge.get("by_split") or {}).get("official") or {}
    om = (official.get("metrics") or {}).get("official") or {}
    mm = (memory.get("metrics") or {}).get("memory") or {}
    resolved, resolved_k = official_resolved(official)
    per_resolved, resolved_frac = cost_per_resolved(results)
    trusted = not judge.get("judge_unreliable")
    return {
        "official_resolved": resolved,
        "official_resolved_k": resolved_k,
        "official_helpful": jo.get("helpful_rate") if trusted else None,
        "official_grounded": jo.get("grounded_rate") if trusted else None,
        "official_numbers": om.get("numbers_acc"),
        "official_pass_k": (official.get("stability") or {}).get("pass_hat_k"),
        "memory_pass_1": (memory.get("stability") or {}).get("pass_at_1"),
        "memory_numbers": mm.get("numbers_acc"),
        "recall3": ret.get("recall@3"),
        "mrr": ret.get("mrr"),
        "recall5": ret.get("recall@5"),
        "heldout_cases": held.get("cases"),
        "heldout_e2e": (human.get("heldout") or {}).get("taxa"),
        "heldout_intent": held.get("intent_acc"),
        "raters": human.get("rotuladores") or (1 if human.get("rotulos") else None),
        "judge_kappa": (judge.get("calibration") or {}).get("cohen_kappa"),
        "judge_validated": (None if not (judge.get("calibration") or {}).get("validation") else
                            float(judge["calibration"]["validation"]["validated"])),
        "cost_per_resolved": per_resolved,
        "resolved_fraction": resolved_frac,
    }


def _fmt(value: float | None, unit: str) -> str:
    if value is None:
        return "não medido"
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "n":
        return f"{value:.0f}"
    if unit == "usd":
        return f"US$ {value:.4f}"
    return f"{value:.2f}"


def rows(results: Path = RESULTS) -> list[dict]:
    got = measure(results)
    out = []
    for t in TARGETS:
        v = got.get(t.key)
        status = "não medido" if v is None else ("atinge" if v >= t.goal else "abaixo")
        if t.diagnostic and v is not None:
            status = "diagnóstico"
        out.append({"key": t.key, "label": t.label, "value": v, "shown": _fmt(v, t.unit),
                    "goal": "—" if t.diagnostic else _fmt(t.goal, t.unit), "status": status, "where": t.where})
    return out


ICON = {"atinge": "na referência", "abaixo": "abaixo da referência (causa nos limites)", "não medido": "não medido",
        "diagnóstico": "diagnóstico"}


def to_markdown(results: Path = RESULTS) -> str:
    table = rows(results)
    lines = ["| métrica | valor | referência da avaliação | situação | de onde vem |", "|---|---:|---:|---|---|"]
    lines += [f"| {r['label']} | {r['shown']} | {r['goal']} | {ICON[r['status']]} | `{r['where']}` |" for r in table]
    weak = [r for r in table if r["status"] not in ("atinge", "diagnóstico")]
    if weak:
        lines += ["", f"**Abaixo da referência ou sem medida ({len(weak)} de {len(table)}), com a causa nos limites:** "
                  + "; ".join(f"{r['label']} ({r['shown']})" for r in weak) + "."]
    else:
        lines += ["", f"Todas as {len(table)} referências atingidas nas medidas commitadas."]
    return "\n".join(lines)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print(to_markdown(Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
