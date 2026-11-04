"""Preenche o README com números lidos do eval, do juiz e do git log — nunca digitados à mão.

Uso: python scripts/fill_readme.py   (depois de `python -m evals.run_evals`; ao vivo e juiz são opcionais)

Blocos (texto entre <!-- tag:begin --> e <!-- tag:end -->):
  eval       obrigatório · evals/results/latest.json (offline, gate do CI)
  timeline   obrigatório · git log (minutos do primeiro ao último commit)
  eval-live  opcional    · evals/results/live_<split>.json, uma tabela por split
  judge      opcional    · evals/results/judge.json (juiz sobre o ao vivo + calibração, kappa)
  replan     opcional    · split `replan` do offline e do ao vivo + exemplos de replanejamento
  since      opcional    · "Desde a última avaliação": lacuna citada → o que mudou → prova (chaves do placar de
             scripts/scorecard.py + teste do mecanismo)
  kit        opcional    · git: linhas do scaffold declarado × linhas escritas no relógio, por pasta
  trace      opcional    · evals/results/live_*.json (evals/trace_stats.py): p50/p95 do turno e SLO por split, fatia
             de tempo de cada agente e quem decide cada passo (supervisor LLM × plano do router × código)
  quickstart obrigatório no --check · o `curl` do "Como rodar" com a 1ª mensagem do split `official` de
             evals/cases.jsonl (sem isso o exemplo fica "pedido 1002", sobra do domínio de exemplo do kit)
Arquivo ausente vira "não rodado" (declarado, não escondido). Idempotente: rodar duas vezes dá o mesmo arquivo.

`--check` (roda no scripts/check.py): NÃO escreve; falha se os blocos de número do README não forem exatamente o
que `evals/results/` COMMITADO gera, ou se a linha do tempo não tiver todos os commits (tolera só o último, o do
próprio README). Sem esta conferência a §5 já veio de um eval não commitado (replan 80% no README, 10% no JSON) e
a linha do tempo parou antes do último commit ("50 min" em vez de 54). Também falha se faltar um dos títulos que o
enunciado pede que o README cubra (REQUIRED_HEADINGS) ou o bloco quickstart, se docs/FAILURE_MODES.md não for o que
`python -m evals.failure_modes` gera dos live_*.json commitados, ou se docs/TIMESHEET.md tiver menos commits que o
git log (os dois saem do scripts/final.sh; rodada 10: os dois estavam velhos e a régua leu como contradição).
Blocos densos do docs/RESULTS.md abrem com uma linha "Como ler" gerada (HOW_TO_READ): o que mede, de onde vem, como
ler o IC.
Linha do tempo: `{{`/`}}` e `|` dos títulos de commit são neutralizados (sem isso, um título com `{{N}}` vira
marcador de modelo no README e o check fica vermelho).
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
from evals import failure_modes  # noqa: E402
from evals.run_evals import fmt_cell, fmt_ci, to_markdown  # noqa: E402
from scripts import scorecard  # noqa: E402

REQUIRED = ("timeline",)  # o bloco `eval` pode ficar no README ou em docs/RESULTS.md (main confere)


def safe_subject(subject: str) -> str:
    """Título de commit seguro na tabela do README: `{{`/`}}` não viram marcador do modelo, `|` não abre coluna."""
    return subject.replace("{{", "{ {").replace("}}", "} }").replace("|", "\\|")


# Linha do tempo no README: com muitos commits, só os marcos (scaffold, spec, eval, entrega) e o 1º e o último;
# a lista inteira já é o docs/TIMESHEET.md (gerado do mesmo git log). 90 linhas de commit escondiam o resto.
TIMELINE_MAX_ROWS = 20
MILESTONES = ("chore: scaffold", "preflight", "spec", "eval", "entrega", "final")


def timeline(root: Path = ROOT) -> str:
    r = subprocess.run(["git", "log", "--reverse", "--format=%aI|%s"], cwd=root, check=False, text=True,
                       capture_output=True, encoding="utf-8")
    rows = [line.split("|", 1) for line in r.stdout.splitlines() if "|" in line]
    if not rows:
        return "_Sem commits ainda._"
    first, last = datetime.fromisoformat(rows[0][0]), datetime.fromisoformat(rows[-1][0])
    lines = ["| hora (UTC; Brasília = UTC−3) | min | commit |", "|---|---:|---|"]
    shown = rows
    if len(rows) > TIMELINE_MAX_ROWS:  # no README só os marcos; a lista inteira fica em docs/TIMESHEET.md
        keep = {0, len(rows) - 1} | {i for i, (_, subj) in enumerate(rows) if subj.startswith(MILESTONES)}
        shown = [rows[i] for i in sorted(keep)][-TIMELINE_MAX_ROWS:]
        if rows[0] not in shown:
            shown = [rows[0], *shown[1:]]
    for ts, subject in shown:
        t = datetime.fromisoformat(ts)
        lines.append(f"| {t:%H:%M:%S} | {(t - first).total_seconds() / 60:.0f} | {safe_subject(subject)} |")
    lines.append(f"\nDo primeiro ao último commit: **{(last - first).total_seconds() / 60:.0f} min**, "
                 f"{len(rows)} commits" + ("" if shown is rows else
                                          f" (aqui os {len(shown)} marcos; todos em `docs/TIMESHEET.md`)") + ".")
    return "\n".join(lines)


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def offline_block(results: Path) -> str:
    report = _load(results / "latest.json")
    if not report:
        sys.exit("ERRO: rode `python -m evals.run_evals` antes; evals/results/latest.json não existe.")
    return f"Modo: `{report['mode']}` · provedor `{report.get('provider', 'offline')}`\n\n" + to_markdown(report)


# "Como ler" no topo de cada bloco denso do docs/RESULTS.md: o que mede, de onde vem e como ler o IC, em texto gerado
# e sem número (os números são os do bloco). A régua da rodada 10 leu "tabelas densas de IC95 por split no lugar de
# explicação". O do bloco offline sai de evals.run_evals.how_to_read (vale também para o console do run_evals).
HOW_TO_READ = {
    "eval-live": (
        "uma seção por split, de `evals/results/live_<split>.json` (LLM real; status `complete` = todos os casos "
        "rodaram, sem aborto por teto nem degradação). Cada taxa vem com o IC95 de Wilson entre colchetes e o n de "
        "execuções (casos × rodadas): com n pequeno o intervalo é largo, e taxas com intervalos que se sobrepõem não "
        "se distinguem. A causa de cada falha está em `docs/FAILURE_MODES.md`, agrupada pela primeira checagem que "
        "falhou; o held-out fica fora dela, por ser o conjunto cego."),
    "trace": (
        "as mesmas linhas ao vivo (`evals/results/live_<split>.json`, contadas por `evals/trace_stats.py`): a "
        "latência do turno por split contra o SLO declarado, a fatia do tempo de cada agente e quem decidiu cada "
        "passo. Percentis não têm IC: num split com poucas linhas, o p95 fica perto do pior caso e muda de uma "
        "bateria para outra."),
    "judge": (
        "um juiz LLM lê cada resposta ao vivo com a evidência que ela usou, fontes e dados de ferramenta "
        "(`evals/results/judge.json`): grounded = toda afirmação tem apoio nela; helpful = resolve o que foi pedido. "
        "Entre colchetes, o IC95 de Wilson com o n de respostas julgadas. A calibração abaixo é {calibration}; a "
        "validação contra pessoas é o bloco de validação humana e, enquanto ele não disser \"validado\", o juiz serve "
        "para comparar commits (regressão), não como medida absoluta."),
    "human": (
        "pessoas rotulam respostas ao vivo sem ver o veredito automático (`evals/label.py`, "
        "`evals/results/human_review.json`): a concordância e o kappa comparam a pessoa com a checagem automática e "
        "com o juiz. Com quase toda resposta aprovada, o kappa despenca mesmo com concordância alta (por isso o AC1 de "
        "Gwet ao lado, quando há dois rotuladores), e \"validado\" só sai pela regra fixada antes de medir."),
    "retrieval": (
        "a busca medida sem LLM no gold de perguntas rotuladas olhando a fonte, uma linha por configuração "
        "(`data/retriever.json`, o arquivo que o app usa como padrão): Recall@k = fração das passagens certas que "
        "aparecem entre as k primeiras; MRR = média do inverso da posição da primeira certa. As taxas da tabela não "
        "têm IC; a linha de busca do bloco offline traz o hit@3 com IC95 e o número de perguntas."),
    "replan": (
        "o split `replan` (pergunta em que o primeiro plano não basta e o supervisor troca de passo: outro agente ou "
        "o humano), no offline e ao vivo, ao lado das ablações SEM replanejamento nos mesmos casos, quando rodadas: a "
        "diferença com × sem é o que o replanejamento vale. Cada célula é a taxa em % com o n de casos; o IC95 de "
        "cada taxa fica no JSON (`ci`)."),
}


def with_how_to_read(tag: str, body: str, **facts: str) -> str:
    """O bloco com o "como ler" na 1ª linha (`facts` preenche o que vem do próprio resultado, ex.: a origem do
    gabarito do juiz); bloco vazio ou "não rodado" (texto em itálico) sai como está."""
    if tag not in HOW_TO_READ or not body.strip() or body.lstrip().startswith("_"):
        return body
    return f"**Como ler:** {HOW_TO_READ[tag].format(**facts)}\n\n{body}"


def live_block(results: Path) -> str:
    files = sorted(results.glob("live_*.json"))
    if not files:
        return "_Eval ao vivo não rodado (sem chave no relógio ou cortado). Ver Limitações._"
    parts = []
    for f in files:
        r = _load(f)
        parts.append(f"### Split `{r.get('split', f.stem)}` — `{f.name}`\n\n"
                     f"Provedor `{r.get('provider')}` · status `{r.get('status')}` · "
                     f"gasto US$ {r.get('spent_usd')} (teto {r.get('max_usd')})\n\n" + to_markdown(r, split_view=True))
    return with_how_to_read("eval-live", "\n\n".join(parts))


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
    if j.get("rejudged_dated") and not j.get("rejudge"):  # judge.json de antes do bloco `rejudge`: dito como foi
        lines[1:1] = ["", f"Rejulgados {j['rejudged_dated']} vereditos (os reprovados e os de resposta com data) com a "
                          "data em que cada resposta foi gerada, no fuso do negócio (`evals.judge --rejudge-dated`): o "
                          "juiz usava a data do relógio dele (UTC) e, numa bateria perto da meia-noite, julgava "
                          "\"hoje/amanhã/ontem\" contra o dia seguinte."]
    for split, s in {**j.get("by_split", {}), "ALL": j}.items():
        lines.append(f"| {split} | {s['cases']} | {s['grounded_rate']}{ci(s, 'grounded_rate')} | "
                     f"{s['helpful_rate']}{ci(s, 'helpful_rate')} | {s['mean_score']} |")
    if j.get("rejudge"):
        lines += ["", *_rejudge_lines(j["rejudge"])]
    lines += ["", f"Gabarito de calibração (rótulos da SPEC, não humanos salvo rotulagem): {cal.get('cases')} rótulos"
              f" · concordância **{cal.get('agreement')}**"
              f"{ci(cal, 'agreement')} · kappa de Cohen **{cal.get('cohen_kappa')}** · TPR {cal.get('tpr')}"
              f"{ci(cal, 'tpr')} ({cal.get('positives')} grounded) · TNR {cal.get('tnr')}{ci(cal, 'tnr')} "
              f"({cal.get('negatives')} não grounded) · discordâncias: {', '.join(cal.get('misses', [])) or '—'}"]
    for split, s in cal.get("by_split", {}).items():
        lines.append(f"- {split}: concordância {s['agreement']}{ci(s, 'agreement')} · kappa {s['cohen_kappa']} "
                     f"({s['cases']} rótulos)")
    # a origem do gabarito sai do relatório: rótulo de pessoa só quando a calibração diz isso (sem campo = SPEC)
    calibration = ("contra rótulos de pessoas" if cal.get("labels_origin") == "human"
                   else "contra o gabarito da SPEC, não contra pessoas")
    return with_how_to_read("judge", "\n".join(lines + _judge_trust(j)), calibration=calibration)


def _rejudge_lines(rj: dict) -> list[str]:
    """O rejulgamento pela data (`evals.judge --rejudge-dated`, bloco `rejudge` do judge.json) com a regra e, por
    split, fundamentadas e úteis da 1ª passada (o juiz que rodou junto da bateria, cujo resumo fica em
    `judge_first_pass` de cada live_*.json) → rejulgado. Sem isto, o 19/30 do resumo commitado e o 30/30 publicado
    pareciam uma contradição (rodada 10, as 3 réguas)."""
    from evals.judge import REJUDGE_REASONS

    first, flips = rj.get("primeira_passada") or {}, rj.get("viraram") or {}
    why = ", ".join(f"{REJUDGE_REASONS.get(k, k)} {n}" for k, n in (rj.get("por_motivo") or {}).items()) or "—"
    day = ", ".join(rj.get("data_da_1a_passada") or []) or "não gravada no veredito"
    out = [f"Rejulgamento pela data (`python -m evals.judge --rejudge-dated`). Regra: {rj['regra']}. Rejulgados "
           f"**{rj['rejulgados']}** vereditos, {first.get('aprovados', 0)} aprovados e {first.get('reprovados', 0)} "
           f"reprovados na 1ª passada (por motivo: {why}); mudaram {flips.get('reprovado_para_aprovado', 0)} de "
           f"reprovado para aprovado e {flips.get('aprovado_para_reprovado', 0)} de aprovado para reprovado. Julgados "
           f"uma vez só (sem data, ou já com o dia em que a resposta foi gerada): {rj['mantidos']}, "
           f"{rj.get('mantidos_reprovados', 0)} deles reprovados. 1ª passada = o juiz que rodou junto da bateria "
           f"(data que ele usou: {day}); o resumo dela fica em `judge_first_pass` de cada live_*.json.", "",
           "| split | casos | rejulgados | fundamentadas: 1ª passada → rejulgado | úteis: 1ª passada → rejulgado |",
           "|---|---:|---:|---:|---:|"]
    for split, b in {**(rj.get("por_split") or {}), "ALL": rj.get("ALL") or {}}.items():
        a, d = b.get("antes") or {}, b.get("depois") or {}
        out.append(f"| {split} | {d.get('casos')} | {b.get('rejulgados')} | {a.get('grounded')}/{a.get('casos')} → "
                   f"{d.get('grounded')}/{d.get('casos')} | {a.get('helpful')}/{a.get('casos')} → "
                   f"{d.get('helpful')}/{d.get('casos')} |")
    return out


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
    lines += _battery_lines(h)
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
    lines += _perturbed_lines(h.get("adulteradas")) + _judge_human_lines(h.get("juiz_x_humano"))
    if h.get("aviso"):
        lines.append(f"Aviso: {h['aviso']}.")
    lines += [f"- `{d['id']}`: humano {d['humano']} × automático {d['automatico']} {d['nota']}".rstrip()
              for d in h.get("divergencias", [])[:8]]
    return with_how_to_read("human", "\n".join(lines))


def _battery_lines(h: dict) -> list[str]:
    """De que bateria (git_sha) são os rótulos que contam, quantos de página congelada e quantos do texto de hoje; os
    de outra bateria, fora de toda conta e listados; o aviso de juiz diferente ou sem veredito do texto rotulado
    (evals.label.FROZEN_RULE). Relatório antigo, sem esses campos: nada."""
    out = []
    if b := h.get("bateria"):
        shas = "; ".join(f"`{sha}` {n}" for sha, n in (b.get("rotulos_por_bateria") or {}).items()) or "—"
        pages = f" (páginas {', '.join(f'`{p}`' for p in b['paginas'])})" if b.get("paginas") else ""
        out.append(f"Bateria das respostas rotuladas que contam, em rótulos: {shas}; {b.get('de_pagina_congelada', 0)} "
                   f"de página congelada{pages} e {b.get('do_texto_de_hoje', 0)} do texto de hoje. Regra: "
                   f"{b.get('regra', '')}.")
    if o := h.get("rotulos_de_outra_bateria"):
        out.append(f"Rótulos de outra bateria: **{o['rotulos']}** (a resposta rotulada não é a de hoje nem a de uma "
                   f"página congelada), fora de toda conta: {', '.join(o.get('ids') or []) or '—'}.")
    if h.get("aviso_juiz"):
        out.append(f"Aviso do juiz × humano: {h['aviso_juiz']}.")
    return out


def _kinds(counts: dict | None) -> str:
    return ", ".join(f"{k} {v}" for k, v in (counts or {}).items() if v) or "—"


PLANTED = ("Respostas com um defeito plantado (número trocado ou afirmação sem base contra a evidência; fato de "
           "referência removido)")
# As duas leituras do "juiz reprova" (evals.label.JUDGE_READINGS), na ordem em que entraram, numa linha só
READINGS = "antes (só não fundamentada, idioma ou vazamento) → depois (+ não atende ao pedido, a em vigor)"


def _two(before: int | None, after: int, n: int) -> str:
    """Antes → depois ("1/3 → 3/3"); relatório antigo, sem a leitura de antes, só a em vigor."""
    return f"{after}/{n}" if before is None else f"{before}/{n} → {after}/{n}"


def _perturbed_lines(ad: dict | None) -> list[str]:
    """Respostas com um defeito plantado, declaradas: quantas entraram na rotulagem e de que tipos, quanto cada pessoa
    reprovou e quanto o juiz reprovou de cada tipo (o total misturaria o tipo que é negativo garantido com o que não
    é), nas duas leituras do "juiz reprova" lado a lado. Relatório sem o bloco (antigo, ou sem adulteradas): nada."""
    if not ad:
        return []
    src = f"`evals/results/{ad.get('arquivo', 'perturbed.json')}`, geradas por `evals/perturb.py`"
    if ad.get("rotuladas"):
        who = "; ".join(f"`{n}` reprovou {r['reprovou']}/{r['rotuladas']}" for n, r in (ad.get("humano") or {}).items())
        kinds = _kinds(ad.get("rotuladas_por_tipo"))
        # a página pega um tipo por vez e, quando um acaba, os outros completam: a composição real vai escrita
        made, shown = ad.get("por_tipo") or {}, ad.get("rotuladas_por_tipo") or {}
        uneven = ""
        if made and len({v for v in shown.values()}) > 1:
            rare = min(made, key=lambda k: made[k])
            few = f"só {made[rare]} respostas aceitaram {rare}" if made[rare] else f"nenhuma resposta aceitou {rare}"
            uneven = f"; {few}, e os outros tipos completam a página"
        out = [f"{PLANTED}: **{ad['rotuladas']}** entraram na rotulagem misturadas às reais, sem marca na página "
               f"(composição real: {kinds}, de {ad.get('geradas', 0)} geradas: {_kinds(made)}{uneven}; declaradas em "
               f"{src}). Quem rotulou: {who}."]
    else:
        out = [f"{PLANTED}: {ad.get('geradas', 0)} geradas ({_kinds(ad.get('por_tipo'))}; {src}), ainda não rotuladas."]
    if jd := ad.get("juiz"):
        types = {k: v for k, v in (jd.get("por_tipo") or {}).items() if v.get("julgadas")}
        per = "; ".join(f"{k} {_two(v.get('reprovou_antes'), v['reprovou'], v['julgadas'])}" for k, v in types.items())
        both = any("reprovou_antes" in v for v in types.values())
        out.append(f"- juiz nas {jd['julgadas']} com defeito plantado (sem depender de rótulo), reprova por tipo"
                   f"{', ' + READINGS if both else ''}: {per}. fato_removido não é negativo garantido: sem o fato a "
                   "resposta pode continuar servindo, e quem decide é a pessoa.")
    if ad.get("fora_da_conta"):
        out.append(f"- fora da conta (resposta rotulada ≠ a de hoje em perturbed.json): "
                   f"{', '.join(ad['fora_da_conta'])}.")
    if ad.get("aviso"):
        out.append(f"- {ad['aviso']}.")
    return out


# Por que a resposta entrou na amostra (evals.judge SELECTED_*), como o RESULTS escreve
SELECTION_NAMES = {"aleatoria": "sorteio", "checagem": "checagem automática", "plantada": "defeito plantado"}
LEFT_NAMES = {"juiz": "escolhidas porque o juiz as reprovou",
              "desconhecida": "de seleção desconhecida (rótulos de antes do registro do motivo da escolha: não contam "
                              "para validar, nem para o mínimo de negativos reais)"}


def _judge_human_lines(jx: dict | None) -> list[str]:
    """Juiz × humano com a regra fixada antes de medir (e as partes acrescentadas depois das revisões, ditas como tal):
    no total (com a composição pela escolha e a dos negativos, e o TNR do juiz nos reais: plantado não vale por real)
    e, com adulteradas, só nas reais e só nelas; nas reais e nas plantadas, as duas leituras do "juiz reprova". O que
    entrou na amostra pelo juiz, ou sem o motivo gravado, sai numa linha à parte: diagnóstico, nunca validação."""
    if not jx:
        return []

    def one(b: dict, total: bool = False) -> str:
        v = b.get("validacao") or {}
        missing = "; ".join(v.get("missing", []))
        if v.get("validated"):
            verdict = "**validado**"
        elif v.get("planted_only"):  # passaria só com os plantados: nunca sai como validado
            verdict = f"validado só com negativos plantados (com respostas reais: não validado; falta: {missing})"
        else:
            verdict = f"não validado (falta: {missing})"
        if not b["casos"]:
            return f"nenhuma resposta rotulada entrou na amostra sem depender do juiz → {verdict}"
        neg, real_tnr, why = f"reprova {b['negatives']}", "", ""
        if total and b.get("negativos_plantados") is not None:
            neg += f": {b['negativos_reais']} reais + {b['negativos_plantados']} plantadas"
            if b.get("negativos_reais"):  # sem negativo real, o TNR deles nem existe
                real_tnr = f" (nos {b['negativos_reais']} negativos reais: {b.get('tnr_nos_reais')})"
        if total and (sel := b.get("selecao")):
            why = ", escolhidas sem depender do juiz (" + ", ".join(
                f"{name} {sel[k]}" for k, name in SELECTION_NAMES.items() if sel.get(k)) + ")"
        return (f"{b['casos']} respostas (a pessoa aprova {b['positives']} e {neg}){why} · "
                f"concordância {b['concordancia']} · TPR {b['tpr']} · TNR {b['tnr']}{real_tnr} → {verdict}")

    v = jx.get("validacao") or {}
    rule = v.get("rule", "")
    if v.get("planted_rule"):  # a parte das plantadas veio depois da medida: nunca sai como "fixada antes"
        rule += f"; acrescentada depois da revisão, mais estrita: {v['planted_rule']}"
    if v.get("selection_rule"):  # e a da escolha, na revisão seguinte
        rule += f"; acrescentada depois da 2ª revisão: {v['selection_rule']}"
    head = f"veredito do juiz: {jx['veredito_do_juiz']}; " if jx.get("veredito_do_juiz") else ""
    out = [f"Juiz × humano ({head}regra fixada antes: {rule}): {one(jx, total=True)}."]
    if left := jx.get("fora_da_validacao"):
        out.append("- fora da validação (diagnóstico, não validação): " + "; ".join(
            f"{b['casos']} {LEFT_NAMES.get(k, k)} — a pessoa reprova {b['negatives']} (TNR do juiz nelas {b['tnr']})"
            f" e aprova {b['positives']} (TPR {b['tpr']})" for k, b in left.items()) + ".")
    # sem adulterada rotulada, "só reais" repetiria o total
    for key, name in (("reais", "só reais"), ("adulteradas", "só as de defeito plantado")) \
            if jx.get("adulteradas") else ():
        if b := jx.get(key):
            kinds = "; ".join(f"{k}: a pessoa reprovou {t['humano_reprova']}/{t['casos']}, o juiz "
                              f"{t['juiz_reprova']}/{t['casos']}"
                              + (f" (antes {t['juiz_reprova_antes']}/{t['casos']})"
                                 if "juiz_reprova_antes" in t else "")
                              for k, t in (b.get("por_tipo") or {}).items())
            line = f"- {name}: {one(b)}" + (f" ({kinds})" if kinds else "")
            if key == "adulteradas" and (lp := jx.get("leituras_plantadas")):
                a, d = lp["antes"], lp["depois"]
                line += (f"; \"juiz reprova\" nas duas leituras: antes (só não fundamentada, idioma ou vazamento) "
                         f"{a['juiz_reprova']}/{a['casos']} · concordância {a['concordancia']} · TNR {a['tnr']}; "
                         f"depois (+ não atende ao pedido, a em vigor) {d['juiz_reprova']}/{d['casos']} · concordância "
                         f"{d['concordancia']} · TNR {d['tnr']}")
            out.append(line + ".")
    if lr := jx.get("leituras_reais"):  # a definição ganhou o `helpful` depois de uma medida: as duas, lado a lado
        a, d = lr["antes"], lr["depois"]
        out.append(f"- \"juiz reprova\" nas respostas reais, as duas leituras: antes, se {a['regra']} → juiz "
                   f"reprova {a['juiz_reprova']}/{a['casos']} · concordância {a['concordancia']} · TPR {a['tpr']} · "
                   f"TNR {a['tnr']}; depois, se {d['regra']} → juiz reprova {d['juiz_reprova']}/{d['casos']} · "
                   f"concordância {d['concordancia']} · TPR {d['tpr']} · TNR {d['tnr']}. Em vigor: a de "
                   f"{lr['em_vigor']}, porque {lr['por_que']}.")
    return out  # o aviso de juiz das adulteradas velho ou não rodado já sai nas linhas das adulteradas


def replan_block(results: Path) -> str:
    sources = [("offline", _load(results / "latest.json"))] + [
        (f"ao vivo ({f.name})", _load(f)) for f in sorted(results.glob("live_*.json"))] + [
        ("offline SEM replanejamento", _load(results / "ablation_replan.json")),
        ("ao vivo SEM replanejamento", _load(results / "ablation_replan_live.json"))]
    # rota (agentes certos) e desfecho ao lado do rótulo da intenção (diagnóstico)
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
    body = lines + ([""] + examples if examples else []) + ([""] + gain if gain else [])
    return with_how_to_read("replan", "\n".join(body))


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
    return out + _needs_ablation(results)


def _verdict_counts(path: Path, source: str) -> dict | None:
    """{verdicts, grounded, helpful} dos vereditos de `source` no arquivo do juiz (None sem arquivo ou sem veredito)."""
    mine = [v for v in (_load(path) or {}).get("verdicts", []) if v.get("source") == source]
    if not mine:
        return None
    return {"verdicts": len(mine), "grounded": sum(bool(v.get("grounded")) for v in mine),
            "helpful": sum(bool(v.get("helpful")) for v in mine)}


def _need_fired(row: dict) -> bool:
    """O achado `needs` disparou neste caso: algum passo traz `needs` (árvore de passos, supervisor.step_view) ou, em
    gravação anterior à marca na árvore, um replanejamento por achado ("<de>:need-><para>")."""
    return any(st.get("needs") for st in row.get("steps") or []) \
        or any(":need->" in str(r) for r in row.get("replans") or [])


def _p50_s(rows: list[dict]) -> float | None:
    """p50 em segundos pelo critério de run_evals.summarize (lat[n // 2] da lista ordenada)."""
    lat = sorted(r["ms"] for r in rows if isinstance(r.get("ms"), int | float))
    return lat[len(lat) // 2] / 1000 if lat else None


def _prompts_differ(a: dict, b: dict) -> list[str]:
    """Arquivos de prompt com hash diferente entre os dois braços ([] = iguais ou sem `prompt_versions` gravado)."""
    def hashes(report: dict) -> dict[str, set]:
        seen: dict[str, set] = {}
        for row in report.get("rows") or []:
            for name, digest in (row.get("prompt_versions") or {}).items():
                seen.setdefault(name, set()).add(digest)
        return seen

    ha, hb = hashes(a), hashes(b)
    return sorted(n for n in set(ha) & set(hb) if ha[n] != hb[n])


# Destino de cada achado no braço com `needs` (supervisor.NEED_OUTCOMES), na ordem em que sai na linha.
NEED_OUTCOME_LABEL = {"called": "o modelo chamou o agente pedido", "reminded": "chamou depois do lembrete",
                      "ignored": "ignorou mesmo com o lembrete (`need_ignored`)", "inserted": "a tabela inseriu",
                      "planned": "já estava no plano", "ran": "o agente já tinha rodado",
                      "blocked": "regra do turno barrou", "hidden": "não chegou ao modelo"}


def _need_outcomes(rows: list[dict]) -> str:
    """"N achados: o modelo chamou X, ..." do braço com `needs` ("" em gravação sem o destino na árvore)."""
    counts: dict[str, int] = {}
    for row in rows:
        for step in row.get("steps") or []:
            for need in step.get("needs") or []:
                if need.get("outcome"):
                    counts[need["outcome"]] = counts.get(need["outcome"], 0) + 1
    if not counts:
        return ""
    told = [f"{NEED_OUTCOME_LABEL[k]} {counts[k]}" for k in NEED_OUTCOME_LABEL if counts.get(k)]
    if other := sum(v for k, v in counts.items() if k not in NEED_OUTCOME_LABEL):
        told.append(f"outro {other}")
    return f"{sum(counts.values())} achados no braço com `needs`: " + ", ".join(told)


def _needs_ablation(results: Path) -> list[str]:
    """Ablação ao vivo SEM os achados `needs` num split sem rótulo de rota (ex.: perguntas reais), lado a lado com o
    MESMO split com `needs`: o juiz (vereditos num arquivo próprio, fora da manchete), números e frases sem base,
    latência e custo. Só compara rodadas completas com os mesmos casos.

    Braço sem `needs` (SUPERVISOR_REPLAN=no_needs): o modelo não recebe o achado, não há lembrete e a tabela não
    insere. Com `needs`, o achado é informação para o supervisor LLM, que decide (um lembrete se ignorar). Os dois
    braços em commits diferentes saem AVISADOS (a diferença mistura o código que mudou com o achado; os prompts dizem
    se ao menos as instruções eram as mesmas). O p50 sai também só nos casos em que o achado disparou no braço com
    `needs`: nos outros os dois braços fazem o mesmo caminho e a diferença de p50 é variação entre as rodadas."""
    out = []
    for abl_f in sorted(results.glob("ablation_replan_no_needs*live.json")):
        abl = _load(abl_f) or {}
        split = abl.get("split")
        base = _load(results / f"live_{split}.json") or {}
        if not split or not base:
            continue
        ma, mb = (base.get("metrics") or {}).get(split) or {}, (abl.get("metrics") or {}).get(split) or {}
        # contagem dos ARQUIVOS de veredito (judge.json e o da ablação), não do resumo gravado no relatório: depois de
        # um rejulgamento (--rejudge-dated) o resumo da bateria fica velho e a comparação mentiria
        ja = _verdict_counts(results / "judge.json", f"live_{split}.json") or base.get("judge") or {}
        jb = _verdict_counts(results / f"judge_{abl_f.stem}.json", abl_f.name) or abl.get("judge") or {}
        if abl.get("status") != "complete" or base.get("status") != "complete" or ma.get("cases") != mb.get("cases"):
            out.append(f"Ablação ao vivo sem `needs` ({split}): não comparável (status {abl.get('status')}, "
                       f"{mb.get('cases')} × {ma.get('cases')} casos).")
            continue
        sha_a, sha_b = base.get("git_sha"), abl.get("git_sha")
        if sha_a == sha_b:
            parts = [f"mesmos {ma['cases']} casos, mesmo commit `{sha_a}`"]
        else:
            differ = _prompts_differ(base, abl)
            parts = [f"mesmos {ma['cases']} casos; **AVISO: braços em commits diferentes** (`{sha_a}` × `{sha_b}`, "
                     + (f"prompts diferentes: {', '.join(differ)}" if differ else "mesmos prompts")
                     + "): a diferença mistura o código que mudou entre as rodadas com o achado"]
        if ja.get("verdicts") and jb.get("verdicts"):
            parts.append(f"fundamentadas pelo juiz **{ja['grounded']}/{ja['verdicts']} com** × "
                         f"**{jb['grounded']}/{jb['verdicts']} sem**; úteis {ja['helpful']}/{ja['verdicts']} × "
                         f"{jb['helpful']}/{jb['verdicts']}")
        for key, label in (("numbers_acc", "números com base"), ("claims_acc", "frases com base")):
            if ma.get(key) is not None and mb.get(key) is not None:
                parts.append(f"{label} {ma[key]:.1f}% × {mb[key]:.1f}%")
        if ma.get("p50_ms") and mb.get("p50_ms"):
            parts.append(f"p50 {ma['p50_ms'] / 1000:.1f} s × {mb['p50_ms'] / 1000:.1f} s")
        fired = {r.get("id") for r in base.get("rows") or [] if _need_fired(r)}
        pa = _p50_s([r for r in base.get("rows") or [] if r.get("id") in fired])
        pb = _p50_s([r for r in abl.get("rows") or [] if r.get("id") in fired])
        if pa is not None and pb is not None:
            parts.append(f"p50 só nos {len(fired)} casos em que o achado disparou {pa:.1f} s × {pb:.1f} s")
        if ma.get("cost_usd") and mb.get("cost_usd"):
            parts.append(f"US$ por caso {ma['cost_usd'] / ma['cases']:.3f} × {mb['cost_usd'] / mb['cases']:.3f}")
        if told := _need_outcomes(base.get("rows") or []):
            parts.append(told)
        out.append(f"Ablação ao vivo sem `needs` ({split}, com × sem): " + "; ".join(parts) + ".")
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


# Arquivos gerados não contam como "escrito no relógio": contadas, 21.909 linhas de JSON de resultado inflavam a
# fração para 72% (medido).
GENERATED = ("evals/results/",)


def kit_block(root: Path = ROOT) -> str:
    """Quanto veio do kit declarado e quanto foi escrito no relógio, medido pelo git."""
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
        # o token sai de DENTRO do container: no host, o segredo da CLI não é o da API (AUTH_SECRET vazio no
        # .env.example = segredo aleatório em cada lado, e o token do host dava 401); -T evita o \r do TTY no $TOKEN
        f"# (atalho de teste, sem senha: TOKEN=$(docker compose exec -T api python -m app.auth {user}))",
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


# Bloco `since`: cada lacuna (com o número de antes) → o que mudou → a prova medida, lida das MESMAS chaves do placar
# (scripts/scorecard.py) e do teste que prova o mecanismo. Gerado: o número nunca é digitado, e o que não foi medido
# aparece como "não medido".
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
     ("hitl_in_turn",), "tests/test_v54_hitl_sync.py"),
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


def _short(model: str | None) -> str:
    return (model or "?").split("/")[-1]


def retriever_block(results: Path, data: Path | None = None) -> str:
    """Frase do buscador em uso (o item "Retrieval" do README), gerada de data/retriever.json ou, sem ele, do
    KIT_RETRIEVER: modelo, ordem, papel do cross-encoder e, quando medidos, cobertura do portão e custo a mais por
    busca. Com o bloco no README, o --check reprova o texto que diverge da escolha gravada. Medido na rodada 10: o
    README dizia "denso + cross-encoder sobre o top-10" e "ninguém roda --choose-retriever", mas a escolha gravada era
    dense+cross:base (ordem do denso; a nota do cross só no portão), saída do --choose-retriever."""
    from app.config import KIT_RETRIEVER
    from evals.retrieval_eval import config_name

    rec = _load((data or ROOT / "data") / "retriever.json") or {}
    recorded = bool((rec.get("choice") or {}).get("retriever"))  # o app só usa a escolha que nomeia o buscador
    cfg = rec["choice"] if recorded else dict(KIT_RETRIEVER)
    name = (rec.get("chosen") if recorded else None) or config_name(cfg)
    measured = (rec.get("measured") or {}) if recorded else {}
    kind = cfg.get("retriever") or "bm25"
    base = {"bm25": "BM25", "dense": "denso", "hybrid": "híbrido"}.get(kind, kind)
    what = {"dense": f"denso `{_short(cfg.get('embed_model'))}`",
            "hybrid": f"híbrido BM25 + denso `{_short(cfg.get('embed_model'))}` (RRF)"}.get(kind, "BM25 (léxico)")
    min_rerank = (cfg.get("gate") or {}).get("min_rerank")
    threshold = f" (nota >= {min_rerank:g})" if min_rerank is not None else ""
    if cfg.get("rerank") == "cross":
        text = (f"`{name}`: {what} + cross-encoder `{_short(cfg.get('rerank_model'))}` (top-{cfg.get('rerank_pool')}, "
                f"{cfg.get('rerank_chars')} caracteres por trecho) — ")
        if (cfg.get("rerank_order") or "cross") == "base":  # sem rerank_order a escolha reordena (config.rerank_order)
            text += (f"ordem do {base}; nota do cross só no portão sem fonte{threshold}: o redator lê os trechos na "
                     f"ordem do {base}.")
        else:
            text += f"o cross reordena o top do {base}, e a nota decide o portão sem fonte{threshold}."
    elif cfg.get("rerank") == "llm":
        text = f"`{name}`: {what}; o LLM reordena o top do {base}, e o portão sem fonte é o BM25/cosseno."
    else:
        text = f"`{name}`: {what}, sem rerank; o portão sem fonte é o BM25/cosseno."
    me = measured.get(name) or {}
    plain = measured.get(config_name({k: v for k, v in cfg.items() if not k.startswith("rerank")})) or {}
    plain = {} if plain is me else plain  # a escolha já é o buscador sem rerank: nada a comparar
    gate, pgate = me.get("rerank_gate") or me.get("gate") or {}, plain.get("gate") or {}
    if gate.get("pos_answered") is not None and gate.get("neg_refused") is not None:
        text += (f" Portão medido: responde {gate['pos_answered']:.0%} das perguntas com fonte e recusa "
                 f"{gate['neg_refused']:.0%} das sem fonte ({gate.get('positives')} × {gate.get('negatives')})")
        if pgate.get("pos_answered") is not None and pgate.get("neg_refused") is not None:
            text += (f"; sem o cross, o do {base} responde {pgate['pos_answered']:.0%} e recusa "
                     f"{pgate['neg_refused']:.0%}")
        text += "."
    lat, plat = me.get("latency_ms") or {}, plain.get("latency_ms") or {}
    if lat.get("p50") is not None and plat.get("p50") is not None:
        text += (f" Custo a mais por busca: {lat['p50'] - plat['p50']:+.0f} ms no p50 ({lat['p50']:.0f} × "
                 f"{plat['p50']:.0f} ms)")
        if me.get("memory_mb") is not None and plain.get("memory_mb") is not None:
            text += f" e {me['memory_mb'] - plain['memory_mb']:+.0f} MB de RAM"
        text += "."
    if cfg.get("rerank") == "cross":  # as duas ordens medidas: o que reordenar pela nota fez com a leitura do redator
        if name.endswith(":base"):
            in_order, reorder = me, (measured.get(name.removesuffix(":base")) or {})
        else:
            in_order, reorder = (measured.get(f"{name}:base") or {}), me
        a, b = reorder.get("recall@5"), in_order.get("recall@5")
        if a is not None and b is not None:
            verdict = "ganhou" if a > b else ("empatou" if a == b else "não ganhou")
            text += f" Reordenar pela nota foi medido e {verdict}: Recall@5 {a} reordenando × {b} na ordem do {base}."
    if rec.get("criterion") and recorded:
        text += (f" Escolha gravada por `run_evals --choose-retriever --apply` em {rec.get('chosen_at')} (commit "
                 f"`{rec.get('git_sha')}`); vale sobre o `KIT_RETRIEVER` de `src/app/config.py`.")
        source = "`data/retriever.json`"
    elif recorded:
        text += f" Escolha do domínio em `data/retriever.json`: {rec.get('_doc') or 'sem motivo gravado'}."
        source = "`data/retriever.json`"
    else:
        text += (" Padrão do kit (`KIT_RETRIEVER` em `src/app/config.py`), sem medida no domínio: "
                 "`run_evals --choose-retriever --apply` mede e grava `data/retriever.json`.")
        source = "`KIT_RETRIEVER`"
    return f"- **Retrieval** (`src/app/rag.py`; frase gerada de {source} por `scripts/fill_readme.py`): {text}"


def retrieval_block(results: Path, data: Path | None = None) -> str:
    """Tabela das configurações de retrieval medidas e a escolhida, lidas de data/retriever.json (o mesmo arquivo
    que o app usa como padrão e que o job `retrieval` do CI confere com --verify)."""
    from evals.retrieval_eval import markdown

    chosen = _load((data or ROOT / "data") / "retriever.json")
    if not chosen:
        return "_Não rodado: buscador padrão do kit (denso + cross-encoder); `make compare` compara as alternativas._"
    budget = chosen.get("latency_budget_ms")
    head = (f"Gold `{chosen.get('gold')}`, medido em {chosen.get('chosen_at')} (commit `{chosen.get('git_sha')}`), "
            "CPU, sem LLM.")
    if chosen.get("criterion"):
        head += f" Critério: {chosen['criterion']}"
        head += f"; orçamento p95 {budget:g} ms." if isinstance(budget, (int, float)) else "."
    elif chosen.get("_doc"):  # escolha gravada à mão pelo domínio: o motivo no lugar do critério automático
        head += f" Escolha do domínio: {chosen['_doc']}"
    gate = (chosen.get("choice") or {}).get("gate") or {}
    if gate.get("min_rerank") is not None:
        head += (f" Portão sem fonte da escolha: nota do cross-encoder >= {gate['min_rerank']:g} (vale este enquanto "
                 "a busca for a mesma; sem ele, o MIN_RERANK do domínio).")
    table = markdown(chosen.get("measured") or {}, chosen.get("chosen"))
    return with_how_to_read("retrieval", head + "\n\n" + table)


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
        # categorias por elas (com "| ASI0N " aqui também, as linhas saem duplicadas e o test_security_asi reprova)
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
    # linha do red team AO VIVO (guardrail + hard), logo abaixo: é o guardrail com o classificador LLM de verdade
    live_gates = [g for g in (load("live_guardrail.json"), load("live_hard.json")) if g]
    if live_gates:
        cases = sum(g.get("cases", 0) for g in live_gates)
        safe = sum(round(g.get("safe_rate", 0) * g.get("cases", 0)) for g in live_gates)
        asi02 = [g["by_asi"]["ASI02"] for g in live_gates if (g.get("by_asi") or {}).get("ASI02")]
        asi02_txt = (f", ASI02 {sum(a['safe_rate'] * a['cases'] for a in asi02) / sum(a['cases'] for a in asi02):.0%}"
                     if asi02 else "")
        head += (f"\n\nAo vivo (guardrail + hard): {(safe / cases if cases else 0):.1%} seguras de {cases}{asi02_txt} "
                 f"→ {'PASS' if all(g.get('passed') for g in live_gates) else 'FAIL'}.")
    return head + "\n\n" + "\n".join(rows)


def trace_block(results: Path) -> str:
    """Onde vai o tempo e quem decide: SLO por split, fatia de cada agente e passos decididos pelo supervisor LLM ×
    vindos do plano do router × postos por regra do código, das linhas ao vivo (evals/trace_stats.py). Os turnos de
    cada caso saem dos arquivos de casos, para a linha de memória (conversa inteira) não passar por um turno só."""
    from evals import trace_stats

    summary = trace_stats.summarize(trace_stats.load_rows(results), trace_stats.case_turns())
    return with_how_to_read("trace", trace_stats.markdown(summary))


BLOCKS = {"eval": offline_block, "eval-live": live_block, "judge": judge_block, "human": human_block,
          "replan": replan_block, "scorecard": scorecard_block, "retrieval": retrieval_block,
          "retriever": retriever_block, "quickstart": quickstart_block, "red-team": red_team_block,
          "since": since_block, "trace": trace_block}
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


# Os arquivos gerados que o scripts/final.sh aceita sujos e commita por último (GENERATED lá): o commit do próprio
# README pode não estar na linha do tempo nem no TIMESHEET. FAILURE_MODES e TIMESHEET entraram na rodada 11: gerados à
# mão, ficavam velhos (rodada 10: "42 falhas em 281 execuções" e "446 min, 0 depois", com 5 em 315 e 910 min no git).
README_ONLY = {"README.md", "ESTADO.md", "docs/RESULTS.md", "docs/PROCEDENCIA.md", "docs/SECURITY_ASI.md",
               "docs/ENTREGA.md", "docs/FAILURE_MODES.md", "docs/TIMESHEET.md"}


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
    problems += _check_failure_modes(readme.parent / "docs" / "FAILURE_MODES.md", results)
    problems += _check_timesheet(readme.parent / "docs" / "TIMESHEET.md", root)
    return problems + _check_timeline(text, root)


def _check_failure_modes(path: Path, results: Path) -> list[str]:
    """docs/FAILURE_MODES.md é o que evals/failure_modes.py gera dos live_*.json commitados: nem velho, nem à mão."""
    want = failure_modes.generate(results)
    have = path.read_text(encoding="utf-8") if path.exists() else None
    if want is None:
        return [] if have is None else ["docs/FAILURE_MODES.md sem evals/results/live_*.json que o gere: commite a "
                                        "bateria ao vivo ou apague o arquivo"]
    if have is None:
        return ["docs/FAILURE_MODES.md ausente com eval ao vivo commitado: rode `python -m evals.failure_modes` (o "
                "scripts/final.sh já roda) e commite"]
    if have != want:
        return ["docs/FAILURE_MODES.md diferente do que evals/results/live_*.json gera: rode `python -m "
                "evals.failure_modes` e commite junto com os resultados"]
    return []


# linha de commit do docs/TIMESHEET.md: "| min | hh:mm:ss |" (min negativo = antes do relógio)
_TIMESHEET_ROW = re.compile(r"^\| -?\d+(?:\.\d+)? \| \d\d:\d\d:\d\d \|")


def _check_timesheet(path: Path, root: Path) -> list[str]:
    """Uma linha do docs/TIMESHEET.md por commit do git log (sem merges, como o scripts/timesheet.py), tolerando só o
    último commit quando ele leva só arquivos gerados: o do scripts/final.sh, que gera o TIMESHEET antes de commitar.
    Sem o arquivo (kit, ou antes do final.sh), nada a conferir; o README que aponta para ele cai no check de links."""
    if not path.exists():
        return []
    listed = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if _TIMESHEET_ROW.match(line))
    r = subprocess.run(["git", "rev-list", "--no-merges", "--count", "HEAD"], cwd=root, check=False, text=True,
                       capture_output=True, encoding="utf-8")
    total = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else 0
    last = _last_commit_files(root)
    if listed < total - (1 if last and set(last) <= README_ONLY else 0):
        return [f"docs/TIMESHEET.md com {listed} commits, o git tem {total} (o último mexeu em "
                f"{', '.join(last[:4]) or 'nada'}): rode scripts/final.sh, que gera o TIMESHEET e commita só os "
                "gerados por cima"]
    return []


def _last_commit_files(root: Path) -> list[str]:
    return subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=root, check=False, text=True,
                          capture_output=True, encoding="utf-8").stdout.split()


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
        # com mais de TIMELINE_MAX_ROWS commits a tabela mostra só os marcos: vale o total declarado na linha final
        declared = re.search(r"Do primeiro ao último commit: \*\*\d+ min\*\*, (\d+) commits", rows)
        listed = int(declared.group(1)) if declared else listed
        last_files = _last_commit_files(root)
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
