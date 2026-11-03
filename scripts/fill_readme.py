"""Preenche o README com números lidos do eval, do juiz e do git log — nunca digitados à mão.

Uso: python scripts/fill_readme.py   (depois de `python -m evals.run_evals`; ao vivo e juiz são opcionais)

Blocos (texto entre <!-- tag:begin --> e <!-- tag:end -->):
  eval       obrigatório · evals/results/latest.json (offline, gate do CI)
  timeline   obrigatório · git log (minutos do primeiro ao último commit)
  eval-live  opcional    · evals/results/live_<split>.json, uma tabela por split
  judge      opcional    · evals/results/judge.json (juiz sobre o ao vivo + calibração, kappa)
  replan     opcional    · split `replan` do offline e do ao vivo + exemplos de replanejamento
  since      opcional    · "Desde a última avaliação": lacuna da correção v4 → mudança do kit → prova (chaves do
             placar de scripts/scorecard.py + teste do mecanismo)
  kit        opcional    · git: linhas do scaffold declarado × linhas escritas no relógio, por pasta
  quickstart obrigatório no --check · o `curl` do "Como rodar" com a 1ª mensagem do split `official` de
             evals/cases.jsonl (V5: o exemplo era "pedido 1002", sobra do domínio de exemplo do kit)
Arquivo ausente vira "não rodado" (declarado, não escondido). Idempotente: rodar duas vezes dá o mesmo arquivo.

`--check` (roda no scripts/check.py): NÃO escreve; falha se os blocos de número do README não forem exatamente o
que `evals/results/` COMMITADO gera, ou se a linha do tempo não tiver todos os commits (tolera só o último, o do
próprio README). Getnet v3: a §5 vinha de um eval não commitado (replan 80% no README, 10% no JSON) e a linha do
tempo parou antes do último commit ("50 min" em vez de 54). Também falha se faltar um dos títulos que o enunciado
pede que o README cubra (REQUIRED_HEADINGS) ou o bloco quickstart.
Linha do tempo: `{{`/`}}` e `|` dos títulos de commit são neutralizados (V5: um título com `{{N}}` virou marcador de
modelo no README e o check ficou vermelho).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evals.run_evals import fmt_cell, fmt_ci, to_markdown  # noqa: E402
from scripts import scorecard  # noqa: E402

REQUIRED = ("timeline",)  # o bloco `eval` pode ficar no README ou em docs/RESULTS.md (main confere)


def safe_subject(subject: str) -> str:
    """Título de commit seguro na tabela do README: `{{`/`}}` não viram marcador do modelo, `|` não abre coluna."""
    return subject.replace("{{", "{ {").replace("}}", "} }").replace("|", "\\|")


def timeline(root: Path = ROOT) -> str:
    r = subprocess.run(["git", "log", "--reverse", "--format=%aI|%s"], cwd=root, check=False, text=True,
                       capture_output=True, encoding="utf-8")
    rows = [line.split("|", 1) for line in r.stdout.splitlines() if "|" in line]
    if not rows:
        return "_Sem commits ainda._"
    first, last = datetime.fromisoformat(rows[0][0]), datetime.fromisoformat(rows[-1][0])
    lines = ["| hora (UTC; Brasília = UTC−3) | min | commit |", "|---|---:|---|"]
    for ts, subject in rows:
        t = datetime.fromisoformat(ts)
        lines.append(f"| {t:%H:%M:%S} | {(t - first).total_seconds() / 60:.0f} | {safe_subject(subject)} |")
    lines.append(f"\nDo primeiro ao último commit: **{(last - first).total_seconds() / 60:.0f} min**.")
    return "\n".join(lines)


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def offline_block(results: Path) -> str:
    report = _load(results / "latest.json")
    if not report:
        sys.exit("ERRO: rode `python -m evals.run_evals` antes; evals/results/latest.json não existe.")
    return f"Modo: `{report['mode']}` · provedor `{report.get('provider', 'offline')}`\n\n" + to_markdown(report)


def live_block(results: Path) -> str:
    files = sorted(results.glob("live_*.json"))
    if not files:
        return "_Eval ao vivo não rodado (sem chave no relógio ou cortado). Ver Limitações._"
    parts = []
    for f in files:
        r = _load(f)
        parts.append(f"### Split `{r.get('split', f.stem)}` — `{f.name}`\n\n"
                     f"Provedor `{r.get('provider')}` · status `{r.get('status')}` · "
                     f"gasto US$ {r.get('spent_usd')} (teto {r.get('max_usd')})\n\n" + to_markdown(r))
    return "\n\n".join(parts)


def judge_block(results: Path) -> str:
    j = _load(results / "judge.json")
    if not j:
        return "_Juiz não rodado._"
    if j.get("status") in ("skipped", "error"):
        return f"Juiz: status `{j['status']}` — {j.get('reason', '')}"
    cal = j.get("calibration", {})

    def ci(block: dict, key: str) -> str:  # juiz antigo (sem "ci") sai sem intervalo, não quebra
        found = (block.get("ci") or {}).get(key)
        return f" {fmt_ci(found)}" if found else ""

    lines = [f"Modelo `{j['model']}` · status `{j['status']}` · arquivos {', '.join(j.get('live_files', [])) or '—'}"
             f" · gasto US$ {j.get('spent_usd')}", "",
             "| split | casos | grounded | helpful | nota média |", "|---|---:|---:|---:|---:|"]
    for split, s in {**j.get("by_split", {}), "ALL": j}.items():
        lines.append(f"| {split} | {s['cases']} | {s['grounded_rate']}{ci(s, 'grounded_rate')} | "
                     f"{s['helpful_rate']}{ci(s, 'helpful_rate')} | {s['mean_score']} |")
    lines += ["", f"Calibração humana: {cal.get('cases')} rótulos · concordância **{cal.get('agreement')}**"
              f"{ci(cal, 'agreement')} · kappa de Cohen **{cal.get('cohen_kappa')}** · TPR {cal.get('tpr')}"
              f"{ci(cal, 'tpr')} ({cal.get('positives')} grounded) · TNR {cal.get('tnr')}{ci(cal, 'tnr')} "
              f"({cal.get('negatives')} não grounded) · discordâncias: {', '.join(cal.get('misses', [])) or '—'}"]
    for split, s in cal.get("by_split", {}).items():
        lines.append(f"- {split}: concordância {s['agreement']}{ci(s, 'agreement')} · kappa {s['cohen_kappa']} "
                     f"({s['cases']} rótulos)")
    return "\n".join(lines + _judge_trust(j))


def _judge_trust(j: dict) -> list[str]:
    """Canários (defeito conhecido que o juiz TEM de reprovar) e família juiz × gerador. Juiz antigo: nada."""
    out = []
    can = j.get("canaries")
    if can:
        missed = ", ".join(can.get("missed", [])) or "—"
        if j.get("judge_unreliable"):
            out.append(f"\n**Juiz NÃO confiável** (`judge_unreliable: true`): reprovou {can['caught']} de "
                       f"{can['cases']} canários com defeito conhecido ({can.get('ran', can['cases'])} rodados; "
                       f"deixou passar: {missed}). Os números do juiz acima não valem como evidência.")
        else:
            out.append(f"\nCanários: o juiz reprovou **{can['caught']}/{can['cases']}** registros sintéticos com "
                       "defeito conhecido (contradiz a evidência, afirma sem evidência, idioma errado, vaza dado de "
                       "outro cliente).")
    if j.get("judge_family"):
        same = "**mesma família**" if j.get("same_family") else "outra família"
        out.append(f"Família: juiz `{j['model']}` ({j['judge_family']}) × gerador "
                   f"{', '.join(f'`{m}`' for m in j.get('generator_models', []))} "
                   f"({', '.join(j.get('generator_families', []))}): {same}. {j.get('family_note', '')}".rstrip())
    return out


def human_block(results: Path) -> str:
    """Validação humana: o dono rotulou respostas ao vivo às cegas (evals/label.py); compara com a automática."""
    h = _load(results / "human_review.json")
    if not h:
        return "_Sem validação humana ainda (`python -m evals.label --export 30`)._"
    lines = [f"{h['rotulos']} respostas ao vivo rotuladas às cegas pelo dono: humano aprova {h['humano_passa']}/"
             f"{h['rotulos']}, checagem automática aprova {h['automatico_passa']}/{h['rotulos']}; concordância "
             f"**{h['concordancia']}**, kappa **{h['kappa']}**."]
    for name, r in (h.get("por_rotulador") or {}).items():
        lines.append(f"- rotulador `{name}`: {r['rotulos']} rótulos · humano × automático: concordância "
                     f"{r['concordancia']}, kappa {r['kappa']}")
    eh = h.get("entre_humanos")
    if eh:
        # AC1 ao lado do kappa: com quase toda resposta certa o kappa despenca mesmo com concordância alta
        lines.append(f"Entre humanos ({' × '.join(eh['rotuladores'])}, {eh['comuns']} respostas em comum, "
                     f"marcação independente): concordância **{eh['concordancia']}**, kappa **{eh['kappa']}**, "
                     f"AC1 de Gwet **{eh.get('ac1')}**; divergem: {', '.join(eh['divergem']) or '—'}.")
        names = {"c1": "responde o pedido", "c2": "algo sem base", "c3": "mesmo idioma"}
        per_q = (eh.get("antes") or {}).get("por_pergunta") or {}
        if per_q:
            lines.append("- por pergunta: " + "; ".join(
                f"{names.get(q, q)} {v['concordancia']} (kappa {v['kappa']}, AC1 {v['ac1']}, n={v['n']})"
                for q, v in per_q.items()))
        if after := eh.get("depois_do_consenso"):
            lines.append(f"- depois da rodada de consenso: concordância {after['concordancia']}, kappa "
                         f"{after['kappa']}, AC1 {after['ac1']}; resolvidas {len(after['resolvidas'])}, "
                         f"mantidas (divergência real) {', '.join(after['mantidas']) or '—'}.")
    elif h.get("rotuladores", 1) < 2:
        lines.append("Um rotulador só: a concordância entre humanos não foi medida.")
    if ho := h.get("heldout"):  # a medida ponta a ponta; a intenção nas mesmas linhas é diagnóstico
        lines.append(f"Held-out cego ponta a ponta: humano aprova **{ho['humano_passa']}/{ho['rotulos']}** "
                     f"({ho['taxa']}){' ' + fmt_ci(ho['ci']) if ho.get('ci') else ''}; diagnóstico: intenção certa "
                     f"em {ho['diagnostico_intencao']} das mesmas linhas; intenção errada com resposta aprovada: "
                     f"{', '.join(ho['intencao_errada_humano_passa']) or '—'}.")
    if h.get("aviso"):
        lines.append(f"Aviso: {h['aviso']}.")
    lines += [f"- `{d['id']}`: humano {d['humano']} × automático {d['automatico']} {d['nota']}".rstrip()
              for d in h.get("divergencias", [])[:8]]
    return "\n".join(lines)


def replan_block(results: Path) -> str:
    sources = [("offline", _load(results / "latest.json"))] + [
        (f"ao vivo ({f.name})", _load(f)) for f in sorted(results.glob("live_*.json"))] + [
        ("offline SEM replanejamento", _load(results / "ablation_replan.json")),
        ("ao vivo SEM replanejamento", _load(results / "ablation_replan_live.json"))]
    # rota (agentes certos, método do Skywalker) e desfecho ao lado do rótulo da intenção (diagnóstico)
    keys = ("replanned_acc", "handoff_acc", "handoff_outcome_acc", "route_acc", "intent_acc")
    lines = ["| fonte | casos | " + " | ".join(keys) + " |", "|---|---:|" + "---:|" * len(keys)]
    examples: list[str] = []
    for name, r in sources:
        m = (r or {}).get("metrics", {}).get("replan")
        if not m:
            continue
        lines.append(f"| {name} | {m['cases']} | " + " | ".join(fmt_cell(m, k) for k in keys) + " |")
        for row in r["rows"]:
            if row["split"] == "replan" and row.get("replans") and len(examples) < 5:
                examples.append(f"- `{row['id']}` ({name}): {' · '.join(row['replans'])}")
    if len(lines) == 2:
        return "_Sem split `replan` nos resultados._"
    gain = _ablation_gain(results)
    return "\n".join(lines + ([""] + examples if examples else []) + ([""] + gain if gain else []))


def _ablation_gain(results: Path) -> list[str]:
    """Quanto o replanejamento vale: handoff/desfecho certo COM × SEM, nos mesmos casos (ablação)."""
    out = []
    for name, with_f, without_f in (("offline", "latest.json", "ablation_replan.json"),
                                    ("ao vivo", None, "ablation_replan_live.json")):
        without = _load(results / without_f)
        live = [_load(f) or {} for f in sorted(results.glob("live_*.json"))]
        with_r = _load(results / with_f) if with_f else next((r for r in live if r.get("metrics", {}).get("replan")),
                                                              None)
        a = (with_r or {}).get("metrics", {}).get("replan")
        b = (without or {}).get("metrics", {}).get("replan")
        if a and b and a.get("handoff_outcome_acc") is not None and b.get("handoff_outcome_acc") is not None:
            out.append(f"Ablação ({name}): desfecho certo no split replan **{a['handoff_outcome_acc']:.1f}% com** × "
                       f"**{b['handoff_outcome_acc']:.1f}% sem** replanejamento (mesmos {a['cases']} casos).")
    return out


EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # hash do tree vazio do git: diff dele = conteúdo inteiro


def _numstat(root: Path, a: str, b: str) -> list[tuple[int, int, str]]:
    r = subprocess.run(["git", "diff", "--numstat", a, b], cwd=root, check=False, text=True,
                       capture_output=True, encoding="utf-8")
    rows = []
    for line in r.stdout.splitlines():
        add, rem, path = line.split("\t", 2)
        if add != "-":  # binário não tem linhas
            rows.append((int(add), int(rem), path))
    return rows


# Arquivos gerados não contam como "escrito no relógio": a v3 dizia 72% com 21.909 linhas de JSON de resultado.
GENERATED = ("evals/results/",)


def kit_block(root: Path = ROOT) -> str:
    """Quanto veio do kit declarado e quanto foi escrito no relógio, medido pelo git (pergunta 5 do feedback v2)."""
    r = subprocess.run(["git", "log", "--reverse", "--format=%H|%s"], cwd=root, check=False, text=True,
                       capture_output=True, encoding="utf-8")
    commits = [line.split("|", 1) for line in r.stdout.splitlines() if "|" in line]
    scaffold = next((h for h, subject in commits if subject.startswith("chore: scaffold")), None)
    if not scaffold:
        return "_Sem commit de scaffold declarado (`chore: scaffold ...`)._"
    kit = _numstat(root, EMPTY_TREE, scaffold)
    clock_all = _numstat(root, scaffold, "HEAD")
    clock = [row for row in clock_all if not row[2].startswith(GENERATED)]
    generated = sum(add for add, _, path in clock_all if path.startswith(GENERATED))
    kit_files = {path for _, _, path in kit}

    def top(path: str) -> str:
        parts = path.split("/")
        nested = parts[0] in ("src", "evals", "tests", "data", "docs") and len(parts) > 2
        return "/".join(parts[:2]) if nested else parts[0]

    table: dict[str, list[int]] = {}
    for add, _, path in kit:
        table.setdefault(top(path), [0, 0, 0, 0])[0] += add
    for add, rem, path in clock:
        row = table.setdefault(top(path), [0, 0, 0, 0])
        row[1] += add
        row[2] += rem
        row[3] += path in kit_files
    lines = ["| pasta | linhas do kit | + no relógio | − no relógio | arquivos do kit alterados |",
             "|---|---:|---:|---:|---:|"]
    for folder, (k, a, d, m) in sorted(table.items()):
        lines.append(f"| `{folder}` | {k} | {a} | {d} | {m} |")
    k_tot, a_tot = sum(x[0] for x in table.values()), sum(x[1] for x in table.values())
    share = a_tot / (k_tot + a_tot) if k_tot + a_tot else 0
    lines.append(f"\nTotal: **{k_tot}** linhas do kit (commit `{scaffold[:7]}`) e **{a_tot}** escritas no relógio "
                 f"({share:.0%} do total). Arquivos do kit alterados no relógio: "
                 f"{sum(x[3] for x in table.values())}. Fora da conta, por serem gerados: {generated} linhas "
                 f"em `{'`, `'.join(GENERATED)}`.")
    return "\n".join(lines)


def _shell_quote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def quickstart_block(results: Path | None = None) -> str:
    """Exemplo do "Como rodar": `curl` com a 1ª mensagem do split `official` (evals/cases.jsonl), com o token do login.

    Quem lê o README começa por aqui: o exemplo é o do enunciado, nunca sobra do domínio de exemplo do kit. Gerado, e
    o --check reprova se divergir.
    """
    from evals.run_evals import load_cases

    case = next((c for c in load_cases() if c["split"] == "official"), None)
    if case is None:
        return "_Sem caso no split `official` de evals/cases.jsonl: o exemplo sai do 1º caso oficial._"
    body = json.dumps({"message": case["message"]}, ensure_ascii=False)
    user = case.get("user_id", "u1")
    return "\n".join([
        "```bash",
        f"# 1º caso oficial ({case['id']}, evals/cases.jsonl), como o cliente {user}, com o $TOKEN do passo Entrar",
        f"# (atalho de teste, sem senha: TOKEN=$(python -m app.auth {user}))",
        'curl -s -X POST localhost:8000/chat -H "Authorization: Bearer $TOKEN" \\',
        f'     -H "Content-Type: application/json" -d {_shell_quote(body)}',
        "```"])


# O que o enunciado manda o README cobrir, com as palavras dele (títulos que não batem com o enunciado são risco
# gratuito de aderência ao desafio). Regex sem caixa sobre os títulos (#, ##, ###).
REQUIRED_HEADINGS = {
    "build, configure, run and test": r"build.*configure.*run.*test",
    "orchestration architecture": r"orchestration architecture",
    "design choices": r"design choices",
    "message workflow": r"message workflow",
    "RAG pipeline: ingestion → storage → retrieval → generation":
        r"rag pipeline.*ingestion.*storage.*retrieval.*generation",
    "how LLM tools were used": r"llm tools",
    "testing strategy": r"testing strategy",
}


def missing_headings(text: str) -> list[str]:
    heads = [line for line in text.splitlines() if re.match(r"^#{1,4} ", line)]
    return [name for name, rx in REQUIRED_HEADINGS.items()
            if not any(re.search(rx, h, re.IGNORECASE) for h in heads)]


def scorecard_block(results: Path) -> str:
    """Manchete do README: só as medidas do enunciado, valor e método (scripts/scorecard.headline_markdown)."""
    return scorecard.headline_markdown(results)


# "Desde a última avaliação": cada lacuna que a correção formal da v4 citou (nas palavras dela) → o que o kit mudou →
# a prova medida, lida das MESMAS chaves do placar (scripts/scorecard.py) e do teste que prova o mecanismo. Gerado:
# o número nunca é digitado, e o que não foi medido aparece como "não medido".
SINCE = (
    ("Respostas oficiais: fundamentadas 60%, números 80%, pass^3 70%",
     "manchete **oficiais resolvidas** (sem humano + todo fato + fonte); toda frase e todo número conferidos contra "
     "fonte, ferramenta e pergunta; juiz no mesmo processo",
     ("official_resolved", "official_grounded", "official_numbers", "official_pass_k"),
     "tests/test_e53_resolved.py"),
    ("Busca: Recall@3 0,49, MRR 0,61",
     "denso + cross-encoder decidido por medida antes do relógio; tabelas inteiras; placar no caminho do agente",
     ("recall3", "recall5", "mrr"), "tests/test_v54_retrieval_method.py"),
    ("Memória: pass@1 54%, números 64%",
     "especialistas sem estado (pergunta reescrita pelo router + livro de fatos); rota medida pelo resultado",
     ("memory_pass_1", "memory_numbers"), "tests/test_v54_stateless_specialists.py"),
    ("A resposta do humano era só a próxima mensagem; operação (especialidade, Postgres, JWKS)",
     "a resposta do operador vira evidência e os passos pendentes do plano rodam (no turno, com espera curta, ou na "
     "retomada); fila por especialidade; Postgres atrás da mesma interface; JWKS",
     ("resolved_fraction",), "tests/test_v54_hitl_sync.py"),
    ("Avaliação independente: um rotulador, held-out de 24",
     "2 rotuladores; held-out cego ≥ 80 ponta a ponta; juiz validado contra humanos com regra fixada antes",
     ("raters", "heldout_cases", "heldout_e2e", "judge_validated", "judge_kappa"),
     "tests/test_v54_judge_validation_real.py"),
)


def since_block(results: Path) -> str:
    """Tabela "Desde a última avaliação" com a prova medida de cada lacuna (chaves do placar)."""
    got = scorecard.measure(results)
    targets = {t.key: t for t in scorecard.TARGETS}
    lines = ["| Lacuna citada | O que mudou | Prova |", "|---|---|---|"]
    for gap, change, keys, test in SINCE:
        proof = " · ".join(f"{targets[k].label} **{scorecard._fmt(got.get(k), targets[k].unit)}**" for k in keys)
        lines.append(f"| {gap} | {change} | {proof}; `{test}` |")
    return "\n".join(lines)


def retrieval_block(results: Path, data: Path | None = None) -> str:
    """Tabela das configurações de retrieval medidas e a escolhida, lidas de data/retriever.json (o mesmo arquivo
    que o app usa como padrão e que o job `retrieval` do CI confere com --verify)."""
    from evals.retrieval_eval import markdown

    chosen = _load((data or ROOT / "data") / "retriever.json")
    if not chosen:
        return "_Não rodado: `python -m evals.run_evals --choose-retriever --apply` grava data/retriever.json._"
    budget = chosen.get("latency_budget_ms")
    return (f"Gold `{chosen.get('gold')}`, medido em {chosen.get('chosen_at')} (commit `{chosen.get('git_sha')}`), "
            f"CPU, sem LLM. Critério: {chosen.get('criterion')}; orçamento p95 {budget:g} ms.\n\n"
            + markdown(chosen.get("measured") or {}, chosen.get("chosen")))


def red_team_block(results: Path) -> str:
    """Red team por rótulo OWASP Agentic (ASI01–ASI10): fração SEGURA offline (gate) e ao vivo (guardrail + hard)."""
    def load(name: str) -> dict:
        try:
            return json.loads((results / name).read_text(encoding="utf-8")).get("gate_red_team") or {}
        except (OSError, ValueError):
            return {}

    offline = load("latest.json")
    live: dict[str, list[float]] = {}
    for name in ("live_guardrail.json", "live_hard.json"):
        for asi, v in (load(name).get("by_asi") or {}).items():
            live.setdefault(asi, []).extend([v["safe_rate"]] * v["cases"])
    if not offline and not live:
        return "_Não medido: `python -m evals.run_evals` grava o gate de red team em evals/results/latest.json._"
    rows = ["| ASI | casos (offline) | seguras offline | seguras ao vivo |", "|---|---:|---:|---:|"]
    for asi in sorted(set(offline.get("by_asi") or {}) | set(live)):
        o = (offline.get("by_asi") or {}).get(asi) or {}
        lv = live.get(asi)
        # id entre crases: a tabela do mapa (docs/SECURITY_ASI.md) é a dona das linhas "| ASI0N " e o teste conta as
        # categorias por elas (ensaio de 03/11: este bloco duplicava as linhas e o test_security_asi reprovava a CI)
        rows.append(f"| `{asi}` | {o.get('cases', '—')} | "
                    + (f"{o['safe_rate']:.0%}" if o else "—") + " | "
                    + (f"{sum(lv) / len(lv):.0%} (n={len(lv)})" if lv else "—") + " |")
    if not offline:
        head = "Offline: não medido."
    elif offline.get("enforced", True):
        head = (f"Gate: {offline['safe_rate']:.1%} seguras de {offline['cases']} (mínimo {offline['floor']:.0%}) → "
                f"{'PASS' if offline['passed'] else 'FAIL'}.")
    else:  # offline o guardrail é só a regex do motor: informa, não reprova (o gate vale ao vivo e no replay)
        head = (f"Offline (só a regex do motor, sem LLM; não reprova): {offline['safe_rate']:.1%} seguras de "
                f"{offline['cases']}. O gate de {offline['floor']:.0%} vale ao vivo e no replay da gravação.")
    return head + "\n\n" + "\n".join(rows)


BLOCKS = {"eval": offline_block, "eval-live": live_block, "judge": judge_block, "human": human_block,
          "replan": replan_block, "scorecard": scorecard_block, "retrieval": retrieval_block,
          "quickstart": quickstart_block, "red-team": red_team_block, "since": since_block}
# Os detalhes (tabelas por split com IC95) vão para docs/RESULTS.md; o README fica com o placar e o mapa.
EXTRA_FILES = ("docs/RESULTS.md", "docs/PROCEDENCIA.md", "docs/SECURITY_ASI.md")


def replace_block(text: str, tag: str, body: str) -> str:
    pattern = re.compile(rf"(<!-- {re.escape(tag)}:begin -->)(.*?)(<!-- {re.escape(tag)}:end -->)", re.DOTALL)
    return pattern.sub(lambda m: f"{m.group(1)}\n{body}\n{m.group(3)}", text)


def render(text: str, results: Path, root: Path = ROOT) -> str:
    for tag in REQUIRED:
        if f"<!-- {tag}:begin -->" not in text:
            sys.exit(f"ERRO: README sem os marcadores <!-- {tag}:begin --> e <!-- {tag}:end -->.")
    for tag, fn in BLOCKS.items():
        if f"<!-- {tag}:begin -->" in text:
            text = replace_block(text, tag, fn(results))
    if "<!-- kit:begin -->" in text:
        text = replace_block(text, "kit", kit_block(root))
    return replace_block(text, "timeline", timeline(root))


def _block(text: str, tag: str) -> str | None:
    m = re.search(rf"<!-- {re.escape(tag)}:begin -->(.*?)<!-- {re.escape(tag)}:end -->", text, re.DOTALL)
    return m.group(1).strip() if m else None


# o commit do próprio README pode não estar na linha do tempo
README_ONLY = {"README.md", "ESTADO.md", "docs/RESULTS.md", "docs/PROCEDENCIA.md", "docs/SECURITY_ASI.md"}


def check(readme: Path, results: Path, root: Path = ROOT) -> list[str]:
    """Divergências entre o README (e docs/RESULTS.md) e o que a evidência commitada gera. Vazia = honesto."""
    text = readme.read_text(encoding="utf-8")
    problems = []
    for extra in EXTRA_FILES:
        path = readme.parent / extra
        if path.exists():
            problems += [f"{extra}: {p}" for p in _check_blocks(path.read_text(encoding="utf-8"), results)]
    problems += _check_blocks(text, results)
    problems += [f"README sem o título que o enunciado pede: {name!r}" for name in missing_headings(text)]
    if "<!-- quickstart:begin -->" not in text:
        problems.append("README sem o bloco <!-- quickstart:begin --> (exemplo do 1º caso oficial)")
    return problems + _check_timeline(text, root)


def _check_blocks(text: str, results: Path) -> list[str]:
    problems = []
    for tag, fn in BLOCKS.items():
        current = _block(text, tag)
        if current is None:
            continue
        if not current:  # bloco vazio: nada afirmado ainda (kit antes do desafio)
            continue
        if tag == "eval" and not (results / "latest.json").exists():
            problems.append("bloco eval preenchido, mas evals/results/latest.json não está no repositório")
            continue
        if current != fn(results).strip():
            problems.append(f"bloco {tag} diferente do que evals/results/ gera: rode scripts/fill_readme.py e "
                            "commite README e resultados juntos")
    return problems


def _check_timeline(text: str, root: Path) -> list[str]:
    problems = []
    rows = _block(text, "timeline")
    if rows:
        r = subprocess.run(["git", "log", "--format=%s"], cwd=root, check=False, text=True,
                           capture_output=True, encoding="utf-8")
        commits = [c for c in r.stdout.splitlines() if c.strip()]
        listed = sum(1 for line in rows.splitlines() if re.match(r"^\| \d\d:\d\d:\d\d \|", line))
        last_files = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=root, check=False,
                                    text=True, capture_output=True, encoding="utf-8").stdout.split()
        readme_only = bool(last_files) and set(last_files) <= README_ONLY
        if listed < len(commits) - (1 if readme_only else 0):
            problems.append(f"linha do tempo com {listed} commits, o git tem {len(commits)} (o último mexeu em "
                            f"{', '.join(last_files[:4]) or 'nada'}): rode scripts/fill_readme.py como ÚLTIMO passo "
                            "e commite só README/ESTADO por cima")
    return problems


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # console cp1252 do Windows quebra acentos
        stream.reconfigure(encoding="utf-8")
    readme = ROOT / "README.md"
    if "--check" in sys.argv:
        problems = check(readme, ROOT / "evals" / "results")
        for p in problems:
            print(f"README ≠ evidência: {p}")
        print("OK: README bate com evals/results/ e com o git log." if not problems else "")
        return 1 if problems else 0
    raw = readme.read_text(encoding="utf-8")
    homes = [raw] + [(ROOT / x).read_text(encoding="utf-8") for x in EXTRA_FILES if (ROOT / x).exists()]
    if not any("<!-- eval:begin -->" in t for t in homes):
        sys.exit("ERRO: nem o README nem docs/RESULTS.md têm o bloco <!-- eval:begin --> (resultado offline).")
    text = render(raw, ROOT / "evals" / "results")
    readme.write_text(text, encoding="utf-8")
    for extra in EXTRA_FILES:  # sem marcadores de timeline: só os blocos de número
        path = ROOT / extra
        if path.exists():
            body = path.read_text(encoding="utf-8")
            for tag, fn in BLOCKS.items():
                if f"<!-- {tag}:begin -->" in body:
                    body = replace_block(body, tag, fn(ROOT / "evals" / "results"))
            if "<!-- kit:begin -->" in body:
                body = replace_block(body, "kit", kit_block(ROOT))
            path.write_text(body, encoding="utf-8")
    print("OK: README atualizado (eval, ao vivo, juiz, replan, linha do tempo).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
