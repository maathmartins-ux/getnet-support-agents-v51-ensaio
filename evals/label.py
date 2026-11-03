"""Validação humana do eval ao vivo: o dono rotula respostas às cegas e o relatório compara com as checagens.

Fluxo (as checagens automáticas não medem a qualidade semântica; a pessoa que rotula mede):
  python -m evals.label --export 30   # sorteia (seed fixa, por split); grava evals/human_labels.csv SEM o veredito
  (o dono lê pergunta, resposta e fontes e responde passa/falha; a sessão grava:)
  python -m evals.label --mark official-01=pass official-02=fail:número sem fonte
  python -m evals.label --report           # humano × automático → evals/results/human_review.json

Dois ou mais rotuladores (avaliação independente): cada um rotula a MESMA amostra no seu arquivo, sem ver o do outro:
  python -m evals.label --export 30 --rater ana      # evals/human_labels.ana.csv (mesma seed = mesmas respostas)
  python -m evals.label --mark official-01=fail:numero_inventado --rater ana
O relatório soma: humano × automático por rotulador e humano × humano (concordância e kappa nos ids em comum).
Held-out ponta a ponta: `--export N --splits heldout` (ou a página com `--heldout`) sorteia só
o held-out; o relatório traz `heldout` = humano passa/falha nessas linhas (a medida), com a acurácia de intenção nas
mesmas linhas como diagnóstico (intenção errada com resposta certa = divergência de taxonomia, não falha).
A nota livre depois de ":" começando por um tipo de falha conhecido (FAILURE_TYPES) vira `tipo_falha`, que o juiz
usa para TPR/TNR por tipo.

Concordância entre humanos (já medida: kappa 0,054 entre o dono e a 2ª pessoa): o relatório traz, por
pergunta da página (c1 responde?, c2 tem algo sem base?, c3 mesmo idioma?) e no veredito, a % de concordância
simples, o kappa de Cohen e o AC1 de Gwet, ANTES e DEPOIS da rodada de consenso. Por que os três: com prevalência
alta (quase toda resposta certa) o kappa despenca mesmo com concordância alta — 18 de 20 iguais, cada pessoa reprovando
1 resposta diferente, dá concordância 0,90 e kappa −0,05 (o "paradoxo do kappa", Feinstein & Cicchetti 1990); o AC1
corrige o acaso pela prevalência média e dá 0,89 no mesmo caso. Publicar só o kappa esconde a concordância real;
publicar só a % esconde o acaso. "Antes" é a medida independente (a que vale como evidência); "depois" mostra quantas
divergências eram leitura errada que a conversa resolveu e quantas ficaram (divergência real).

Consenso: `--divergences` lista o que os dois rotuladores marcaram diferente (veredito e cada pergunta) em
evals/human_divergences.md; os dois conversam ~3 min e a sessão grava o resultado com `--consensus TXT` (uma linha
`id=pass|fail[:tipo]` por item resolvido, `id=diverge` quando continuam discordando) em evals/human_consensus.json.

Veredito automático de uma linha = todas as checagens True. Passa humano = a resposta é correta, fundamentada e no
idioma da pergunta (decisão do dono, sem ver a nota automática). Relatório: concordância, kappa de Cohen, e onde
humano e automático divergem (esses casos mostram o que a checagem automática não enxerga).

Adulteradas de propósito (evals/perturb.py; `scripts/label_page.py --perturb N`): respostas reais com um defeito
declarado (número trocado, afirmação sem base, fato removido), em evals/results/perturbed.json, entram na página
misturadas às reais; com elas, TODO id da página é cego (page_id), e a importação volta ao id do caso. Sem elas o
TNR do juiz contra pessoas não se mede (quase toda resposta real passa). O relatório separa: humano × automático e
humano × humano só nas reais (a adulterada não é resposta do sistema nem passou pelas checagens); juiz × humano no
total, só nas reais e só nas adulteradas, com a mesma regra de validação; e quanto cada pessoa e o juiz reprovaram
das adulteradas (o juiz no conjunto todo, sem depender de rótulo). Rótulo de adulterada cuja resposta não bate com a
de perturbed.json (arquivo regerado depois) fica fora da conta, listado.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
CSV_PATH = HERE / "human_labels.csv"
OUT = RESULTS / "human_review.json"
FIELDS = ["id", "split", "pergunta", "resposta", "fontes", "ferramentas", "humano", "nota", "tipo_falha",
          "c1", "c2", "c3"]  # c1..c3: resposta de cada pergunta da página (sim/nao/naosei), vazio no --mark
QUESTIONS = {"c1": "responde o que o cliente perguntou", "c2": "tem algo na resposta que não aparece no que ele tinha",
             "c3": "está no mesmo idioma da pergunta"}
CONSENSUS = HERE / "human_consensus.json"
DIVERGENCES = HERE / "human_divergences.md"
FAILURE_TYPES = ("invented_number", "unsupported_claim", "stale_source", "offered_unavailable_action",
                 "wrong_language", "leak", "wrong_route", "other")


def csv_path(rater: str | None = None, base: Path = HERE) -> Path:
    """Sem rotulador: o arquivo único de sempre. Com rotulador: um arquivo por pessoa."""
    if not rater:
        return base / "human_labels.csv"
    if not rater.replace("-", "").replace("_", "").isalnum():
        raise ValueError(f"nome de rotulador inválido: {rater!r} (use letras, números, - ou _)")
    return base / f"human_labels.{rater.lower()}.csv"


def page_id(case_id: str) -> str:
    """Id cego da página com adulteradas: real e adulterada ganham o mesmo formato (nada no id, nem no texto de
    "Copiar minhas respostas", diz qual é qual) e a importação volta ao id do caso pelo mesmo cálculo, sem tabela
    guardada fora do repositório."""
    return "r" + hashlib.sha256(f"rotulagem:{case_id}".encode()).hexdigest()[:10]


def tool_names(row: dict) -> list[str]:
    return [t.get("name", "?") if isinstance(t, dict) else str(t) for t in row.get("tool_calls") or []]


def auto_pass(row: dict) -> bool:
    checks = row.get("checks") or {}
    return bool(checks) and all(v is not False for v in checks.values())


def load_rows(results: Path = RESULTS) -> list[dict]:
    """Uma linha por caso (a 1ª rodada), de todos os live_*.json."""
    rows, seen = [], set()
    for path in sorted(results.glob("live_*.json")):
        for row in json.loads(path.read_text(encoding="utf-8")).get("rows", []):
            if str(row.get("run", 0)) in ("0", "") and row["id"] not in seen:
                seen.add(row["id"])
                rows.append(row)
    return rows


def suspected_ids(rows: list[dict], judge_path: Path | None = None) -> set[str]:
    """Casos com falha suspeita (alguma checagem automática falhou ou o juiz reprovou). Servem para enriquecer a
    amostra humana com negativos: com 1 falha em 18 rótulos, o TNR do juiz não se mede (pede ~20 de cada classe)."""
    out = {r["id"] for r in rows if r.get("crash") or any(v is False for v in (r.get("checks") or {}).values())}
    jp = judge_path or (RESULTS / "judge.json")
    if jp.exists():
        for v in json.loads(jp.read_text(encoding="utf-8")).get("verdicts", []):
            if not v.get("grounded", True) or not v.get("helpful", True):
                out.add(v["id"])
    return out


def labeled_ids(base: Path = HERE) -> set[str]:
    """Ids já rotulados por alguém (qualquer human_labels*.csv): a amostra nova não os repete."""
    out: set[str] = set()
    for path in base.glob("human_labels*.csv"):
        out |= {r["id"] for r in read_labels(path) if r.get("id")}
    return out


def enriched_sample(rows: list[dict], n: int, seed: int = 7, suspects: int = 0, exclude: set[str] | None = None,
                    suspect_ids: set[str] | None = None) -> list[dict]:
    """Até `suspects` casos com falha suspeita + o resto estratificado, sem os `exclude`. A página nunca mostra qual
    é qual (quem rotula não vê o veredito automático), e a ordem é embaralhada."""
    rows = [r for r in rows if r["id"] not in (exclude or set())]
    bad = suspect_ids if suspect_ids is not None else suspected_ids(rows)
    rng = random.Random(seed)
    pool = [r for r in rows if r["id"] in bad]
    rng.shuffle(pool)
    picked = pool[:min(suspects, n)]
    rest = sample([r for r in rows if r["id"] not in {p["id"] for p in picked}], n - len(picked), seed)
    out = picked + rest
    rng.shuffle(out)
    return out


def sample(rows: list[dict], n: int, seed: int = 7) -> list[dict]:
    """Amostra estratificada: uma passada por split até completar n (seed fixa = reproduzível)."""
    rng = random.Random(seed)
    by_split: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_split[r.get("split", "?")].append(r)
    for lst in by_split.values():
        rng.shuffle(lst)
    picked: list[dict] = []
    while len(picked) < min(n, len(rows)):
        for split in sorted(by_split):
            if by_split[split] and len(picked) < n:
                picked.append(by_split[split].pop())
    rng.shuffle(picked)
    return picked


def export(n: int, results: Path = RESULTS, path: Path = CSV_PATH, seed: int = 7,
           splits: set[str] | None = None) -> int:
    rows = [r for r in load_rows(results) if not splits or r.get("split") in splits]
    return _write_csv(path, sample(rows, n, seed))


def _write_csv(path: Path, rows: list[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:  # sem a nota automática: rotulagem às cegas
            w.writerow(
                {
                    "id": r["id"],
                    "split": r.get("split"),
                    "pergunta": r.get("message"),
                    "resposta": r.get("answer"),
                    "fontes": " ".join(r.get("source_ids") or [])[:300],
                    "ferramentas": " ".join(tool_names(r)),
                    "humano": "",
                    "nota": "",
                }
            )
    return len(rows)


def read_labels(path: Path = CSV_PATH) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return [{**{k: "" for k in FIELDS}, **row} for row in csv.DictReader(fh)]


def mark(pairs: list[str], path: Path = CSV_PATH) -> int:
    rows = read_labels(path)
    index = {r["id"]: r for r in rows}
    done = 0
    for pair in pairs:
        key, _, rest = pair.partition("=")
        verdict, _, note = rest.partition(":")
        verdict = verdict.strip().lower()
        if key not in index or verdict not in ("pass", "fail"):
            print(f"ignorado: {pair!r} (use ID=pass ou ID=fail[:nota]; ID tem de estar no CSV)", file=sys.stderr)
            continue
        note = note.strip()
        kind = note.split()[0].strip(".,;") if note else ""
        index[key]["humano"], index[key]["nota"] = verdict, note
        index[key]["tipo_falha"] = kind if verdict == "fail" and kind in FAILURE_TYPES else ""
        done += 1
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return done


def import_page(dump: Path, n: int | None = None, seed: int = 7, results: Path = RESULTS, base: Path = HERE) -> dict:
    """Fichas da página de rotulagem (scripts/label_page.py; a sessão lê `rotulos` com ArtifactData) → um CSV por
    pessoa, pelo mesmo caminho do --mark. Aceita a lista de documentos como vier ({"documents": [...]}, lista de
    {"data": {...}} ou de fichas). Nota: "fail:<tipo> <comentário>", como no --mark. Id cego (página com
    adulteradas) volta ao id do caso; a adulterada entra no CSV com a resposta adulterada, a que a pessoa viu."""
    from evals import perturb

    raw = json.loads(dump.read_text(encoding="utf-8"))
    docs = raw.get("documents", raw.get("docs", [])) if isinstance(raw, dict) else raw
    done: dict[str, int] = {}
    live = {r["id"]: r for r in load_rows(results)}
    live.update({r["id"]: r for r in perturb.load(results)})
    blind = {page_id(i): i for i in live}
    for doc in docs:
        data = doc.get("data", doc) if isinstance(doc, dict) else {}
        rater, marks = str(data.get("rater") or "").strip(), data.get("marks") or {}
        if not rater or not marks:
            continue
        marks = {blind.get(k, k): m for k, m in marks.items()}
        path = csv_path(rater, base)
        if not path.exists():  # o CSV nasce das linhas que a página mostrou (com --splits a amostra é outra)
            _write_csv(path, [live[i] for i in marks if i in live])
        else:  # 2ª página da mesma pessoa: as respostas novas entram no CSV dela (antes eram ignoradas)
            have = {r["id"] for r in read_labels(path)}
            new = [live[i] for i in marks if i in live and i not in have]
            if new:
                old_rows = read_labels(path)
                _write_csv(path, new)
                added = read_labels(path)
                with path.open("w", encoding="utf-8", newline="") as fh:
                    w = csv.DictWriter(fh, fieldnames=FIELDS)
                    w.writeheader()
                    w.writerows(old_rows + added)
        pairs = []
        for case_id, m in marks.items():
            verdict = m.get("v")
            if verdict not in ("pass", "fail"):
                continue
            note = " ".join(x for x in (m.get("tipo") or "", (m.get("nota") or "").replace(":", " ")) if x)
            pairs.append(f"{case_id}={verdict}" + (f":{note}" if verdict == "fail" and note else ""))
        done[rater] = mark(pairs, path)
        _set_questions(path, {i: m for i, m in marks.items() if isinstance(m, dict)})
    return done


def _set_questions(path: Path, marks: dict[str, dict]) -> None:
    """Grava no CSV a resposta de cada pergunta da página (c1..c3): a concordância por pergunta sai daqui."""
    rows = read_labels(path)
    for r in rows:
        m = marks.get(r["id"]) or {}
        for q in QUESTIONS:
            if m.get(q) in ("sim", "nao", "naosei"):
                r[q] = m[q]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def import_text(text: str, results: Path = RESULTS, base: Path = HERE) -> dict:
    """Plano B da página (quem não entrou com conta do claude.ai): o texto de "Copiar minhas respostas", colado no
    chat ("CONFERENCIA <amostra> <nome>" e uma linha "id=pass|fail|skip[:tipo]" por situação) → o CSV da pessoa."""
    docs, cur = [], None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("CONFERENCIA "):
            parts = line.split(maxsplit=2)
            cur = {"rater": parts[2] if len(parts) > 2 else "", "marks": {}}
            docs.append({"data": cur})
        elif cur is not None and "=" in line:
            head, *qs = line.split()  # "id=fail:tipo c1=sim c2=sim c3=sim" (a página escreve as perguntas também)
            case_id, _, rest = head.partition("=")
            verdict, _, kind = rest.partition(":")
            m = {"v": verdict.strip(), "tipo": kind.strip()}
            for tok in qs:
                q, _, val = tok.partition("=")
                if q in QUESTIONS:
                    m[q] = val
            cur["marks"][case_id.strip()] = m
    dump = base / ".import_text.json"
    dump.write_text(json.dumps({"documents": docs}, ensure_ascii=False), encoding="utf-8")
    try:
        return import_page(dump, results=results, base=base)
    finally:
        dump.unlink(missing_ok=True)


def ac1(pairs: list[tuple[bool, bool]]) -> float | None:
    """AC1 de Gwet (2 rotuladores, 2 categorias): acaso = 2·q·(1−q), q = prevalência média de "sim" dos dois.
    Não despenca com prevalência alta como o kappa (ver o docstring do módulo)."""
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    q = (sum(a for a, _ in pairs) + sum(b for _, b in pairs)) / (2 * n)
    pe = 2 * q * (1 - q)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def agreement(pairs: list[tuple[bool, bool]]) -> dict:
    """% simples, kappa de Cohen e AC1 de Gwet dos mesmos pares."""
    n = len(pairs)
    return {"n": n, "concordancia": round(sum(a == b for a, b in pairs) / n, 3) if n else None,
            "kappa": kappa(pairs), "ac1": ac1(pairs)}


def kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    pa = sum(a for a, _ in pairs) / n
    pb = sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def _vs_auto(labeled: list[dict], auto: dict[str, bool]) -> dict:
    pairs = [(r["humano"] == "pass", auto[r["id"]]) for r in labeled]
    return {
        "rotulos": len(pairs),
        "humano_passa": sum(a for a, _ in pairs),
        "automatico_passa": sum(b for _, b in pairs),
        "concordancia": round(sum(a == b for a, b in pairs) / len(pairs), 3) if pairs else None,
        "kappa": kappa(pairs),
        "divergencias": [
            {"id": r["id"], "humano": r["humano"], "automatico": "pass" if auto[r["id"]] else "fail", "nota": r["nota"]}
            for r in labeled
            if (r["humano"] == "pass") != auto[r["id"]]
        ],
    }


def label_files(base: Path = HERE) -> dict[str, Path]:
    """{rotulador: arquivo}. O arquivo sem nome conta como o rotulador "dono"."""
    files = {}
    if (base / "human_labels.csv").exists():
        files["dono"] = base / "human_labels.csv"
    for path in sorted(base.glob("human_labels.*.csv")):
        files[path.name.split(".")[1]] = path
    return files


def _question_pairs(a: dict[str, dict], b: dict[str, dict], ids: list[str]) -> dict[str, list[tuple[bool, bool]]]:
    """Pares por pergunta (só quem respondeu sim/não nas duas fichas; "não sei" fica fora)."""
    out: dict[str, list[tuple[bool, bool]]] = {}
    for q in QUESTIONS:
        pairs = [(a[i][q] == "sim", b[i][q] == "sim") for i in ids
                 if a[i].get(q) in ("sim", "nao") and b[i].get(q) in ("sim", "nao")]
        if pairs:
            out[q] = pairs
    return out


def between_humans(by_rater: dict[str, dict[str, bool]], answers: dict[str, dict[str, dict]] | None = None,
                   consensus: dict[str, dict] | None = None) -> dict | None:
    """Concordância entre os dois primeiros rotuladores, nos ids que ambos rotularam: % simples, kappa e AC1 no
    veredito e por pergunta (`answers`: {rotulador: {id: {c1, c2, c3}}}), antes e — com `consensus` — depois do
    consenso (item resolvido conta como concordância das duas no rótulo combinado; `diverge` fica como estava)."""
    names = sorted(by_rater)
    if len(names) < 2:
        return None
    a, b = by_rater[names[0]], by_rater[names[1]]
    common = sorted(set(a) & set(b))
    pairs = [(a[i], b[i]) for i in common]
    before = agreement(pairs)
    out = {"rotuladores": names[:2], "comuns": len(common), "concordancia": before["concordancia"],
           "kappa": before["kappa"], "ac1": before["ac1"], "divergem": [i for i in common if a[i] != b[i]],
           "antes": {**before, "por_pergunta": {}}, "depois_do_consenso": None}
    if answers and names[0] in answers and names[1] in answers:
        qa, qb = answers[names[0]], answers[names[1]]
        ids = [i for i in common if i in qa and i in qb]
        out["antes"]["por_pergunta"] = {q: agreement(p) for q, p in _question_pairs(qa, qb, ids).items()}
    if consensus:
        resolved = [i for i in out["divergem"] if (consensus.get(i) or {}).get("v") in ("pass", "fail")]
        after = [(consensus[i]["v"] == "pass",) * 2 if i in resolved else (a[i], b[i]) for i in common]
        out["depois_do_consenso"] = {**agreement(after), "resolvidas": resolved,
                                     "mantidas": [i for i in out["divergem"] if i not in resolved]}
    return out


def divergences(base: Path = HERE, out: Path | None = None, results: Path = RESULTS) -> list[dict]:
    """O que os dois primeiros rotuladores marcaram diferente (veredito ou qualquer pergunta), para a rodada de
    consenso; grava evals/human_divergences.md legível para quem não é da área, com o modelo das linhas de volta.
    Com adulterada entre as divergências, o arquivo usa o id cego da página para todas (page_id): o rótulo combinado
    entra no juiz × humano, e o "~p" no título diria às duas qual resposta foi plantada antes de elas decidirem."""
    from evals import perturb

    files = label_files(base)
    names = sorted(files)[:2]
    if len(names) < 2:
        return []
    rows = {n: {r["id"]: r for r in read_labels(files[n]) if r["humano"] in ("pass", "fail")} for n in names}
    a, b = rows[names[0]], rows[names[1]]
    found = []
    for i in sorted(set(a) & set(b)):
        qs = {q: {names[0]: a[i].get(q), names[1]: b[i].get(q)} for q in QUESTIONS
              if a[i].get(q) in ("sim", "nao") and b[i].get(q) in ("sim", "nao") and a[i][q] != b[i][q]}
        if a[i]["humano"] != b[i]["humano"] or qs:
            found.append({"id": i, "pergunta": a[i]["pergunta"], "resposta": a[i]["resposta"],
                          "veredito": {names[0]: a[i]["humano"], names[1]: b[i]["humano"]}, "perguntas": qs})
    word = {"pass": "certa", "fail": "errada", "sim": "sim", "nao": "não"}
    planted = {r["id"] for r in perturb.load(results)}
    blind = any(d["id"] in planted for d in found)

    def shown(case_id: str) -> str:
        return page_id(case_id) if blind else case_id

    lines = [f"# Rodada de consenso ({names[0]} × {names[1]})", "",
             f"{len(found)} situações com marcação diferente. Leiam juntos cada uma (~20 s cada) e digam o rótulo "
             "combinado. Se continuarem discordando, tudo bem: escrevam `diverge`.", ""]
    for d in found:
        lines += [f"## {shown(d['id'])}", f"- Cliente: {d['pergunta'][:300]}", f"- Assistente: {d['resposta'][:400]}",
                  "- Veredito: " + " · ".join(f"{n}: {word.get(v, v)}" for n, v in d["veredito"].items())]
        lines += [f"- Pergunta \"{QUESTIONS[q]}\": " + " · ".join(f"{n}: {word.get(v, v)}" for n, v in vs.items())
                  for q, vs in d["perguntas"].items()]
        lines.append("")
    lines += ["Respostas de volta (uma linha por situação):", "", "```", "CONSENSO",
              *[f"{shown(d['id'])}=pass|fail|diverge" for d in found], "```"]
    target = out or base / DIVERGENCES.name
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return found


def import_consensus(text: str, base: Path = HERE, results: Path = RESULTS) -> dict:
    """Linhas `id=pass|fail[:tipo]` ou `id=diverge` (a linha "CONSENSO" e o resto são ignorados) →
    evals/human_consensus.json, que o --report usa no "depois do consenso". Id cego (divergências com adulterada)
    volta ao id do caso."""
    from evals import perturb

    known = [r["id"] for r in load_rows(results)] + [r["id"] for r in perturb.load(results)]
    alias = {page_id(i): i for i in known}
    got: dict[str, dict] = {}
    for line in text.splitlines():
        line = line.strip().strip("`")
        if "=" not in line or line.startswith("#"):
            continue
        case_id, _, rest = line.partition("=")
        verdict, _, kind = rest.partition(":")
        verdict = verdict.strip().lower()
        if verdict in ("pass", "fail", "diverge") and case_id.strip():
            got[alias.get(case_id.strip(), case_id.strip())] = {"v": verdict, "tipo": kind.strip()}
    path = base / CONSENSUS.name
    path.write_text(json.dumps(got, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"itens": len(got), "resolvidas": sum(v["v"] != "diverge" for v in got.values()), "arquivo": str(path)}


HELDOUT_SPLIT = "heldout"


def heldout_e2e(labeled: list[dict], live: dict[str, dict]) -> dict | None:
    """Ponta a ponta no held-out: humano passa / rotulados (a medida), com IC; intenção nas mesmas linhas é
    diagnóstico. `intencao_errada_humano_passa` = taxonomia diverge mas a resposta serve."""
    from evals.run_evals import rate_ci

    rows = [r for r in labeled if (live.get(r["id"]) or {}).get("split", r.get("split")) == HELDOUT_SPLIT]
    if not rows:
        return None
    passed = sum(r["humano"] == "pass" for r in rows)
    intents = [(live[r["id"]].get("checks") or {}).get("intent") for r in rows if r["id"] in live]
    intents = [v for v in intents if v is not None]
    wrong_ok = [r["id"] for r in rows if r["humano"] == "pass"
                and (live.get(r["id"], {}).get("checks") or {}).get("intent") is False]
    return {"rotulos": len(rows), "humano_passa": passed, "taxa": round(passed / len(rows), 3),
            "ci": rate_ci(passed, len(rows)),
            "diagnostico_intencao": round(sum(intents) / len(intents), 3) if intents else None,
            "intencao_errada_humano_passa": sorted(wrong_ok)}


def _load_consensus(base: Path) -> dict | None:
    try:
        return json.loads((base / CONSENSUS.name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


JUDGE_FILE, JUDGE_PERTURBED = "judge.json", "judge_perturbed.json"
JUDGE_VERDICT = "fundamentada, útil, no idioma da pergunta e sem vazamento — as 3 perguntas da página"


def judge_passes(v: dict) -> bool:
    """O juiz aprova pela mesma régua da pessoa. A página reprova se qualquer pergunta sai ruim: não responde ao
    pedido (c1), algo sem base (c2), idioma diferente (c3). O juiz responde as mesmas três em `helpful`, `grounded` e
    `language_ok` (mais o vazamento); deixar `helpful` de fora faria a resposta fundamentada que não atende ao pedido
    (ex.: fato_removido) aparecer como erro do juiz, quando é só critério diferente. Campo ausente não reprova."""
    from evals.judge import verdict_fails

    return not verdict_fails(v) and v.get("helpful", True) is not False


def _first_run(path: Path) -> dict[str, dict] | None:
    """Veredito da 1ª rodada de cada caso (a amostra rotulada é a 1ª rodada); None se o arquivo não abre."""
    try:
        verdicts = json.loads(path.read_text(encoding="utf-8")).get("verdicts") or []
    except (OSError, ValueError):
        return None
    out: dict[str, dict] = {}
    for v in verdicts:
        if v.get("run", 0) == 0 and v["id"] not in out:
            out[v["id"]] = v
    return out


def perturbed_verdicts(results: Path, perturbed: dict[str, dict]) -> tuple[dict[str, dict], str | None]:
    """Vereditos do juiz nas adulteradas (judge_perturbed.json), só se ele julgou ESTA versão de perturbed.json
    (`perturbed_sha`): veredito de outra versão diria respeito a outra resposta. Devolve (vereditos, aviso)."""
    from evals import perturb

    path = results / JUDGE_PERTURBED
    if not perturbed or not path.exists():
        return {}, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, None
    if data.get("status") in ("skipped", "error"):
        return {}, f"o juiz das adulteradas não rodou ({JUDGE_PERTURBED}: status `{data['status']}`)"
    if data.get("perturbed_sha") != perturb.rows_sha(list(perturbed.values())):
        return {}, (f"{JUDGE_PERTURBED} julgou outra versão de {perturb.FILE}: "
                    "rode `python -m evals.judge --perturbed` de novo")
    return {i: v for i, v in (_first_run(path) or {}).items() if i in perturbed}, None


def _human_labels(by_rater: dict[str, dict[str, bool]], consensus: dict | None) -> dict[str, bool]:
    """Rótulo humano de cada id: o do consenso quando houver, senão o das pessoas que concordam (1 basta)."""
    resolved = {k: (c or {}).get("v") == "pass" for k, c in (consensus or {}).items()
                if isinstance(c, dict) and (c or {}).get("v") in ("pass", "fail")}
    human: dict[str, bool] = {}
    for i in set().union(*(set(r) for r in by_rater.values())) if by_rater else set():
        if i in resolved:
            human[i] = resolved[i]
        else:
            votes = {r[i] for r in by_rater.values() if i in r}
            if len(votes) == 1:
                human[i] = votes.pop()
    return human


def judge_vs_humans(by_rater: dict[str, dict[str, bool]], consensus: dict | None,
                    results: Path = RESULTS, perturbed: dict[str, dict] | None = None) -> dict | None:
    """Juiz × humanos em respostas reais (método do rótulo em trace real) e nas adulteradas declaradas: o veredito
    do juiz pela régua da pessoa (judge_passes) contra o humano — o consenso quando houver, senão a concordância dos
    dois, senão o 1º rotulador. Complementa a calibração em casos construídos (judge.json `calibration`), que mede
    outra coisa: casos escritos à mão, com a evidência escrita à mão. Mesma regra de validação, fixada antes de medir
    (evals.judge.validation), no total, só nas reais e só nas adulteradas (`perturbed`: {id: linha de
    perturbed.json}; o juiz delas vem de judge_perturbed.json, nunca do judge.json da manchete)."""
    from evals.judge import tpr_tnr, validation

    pert = perturbed or {}
    judge = {i: judge_passes(v) for i, v in (_first_run(results / JUDGE_FILE) or {}).items() if i not in pert}
    fake, stale = perturbed_verdicts(results, pert)
    judge.update({i: judge_passes(v) for i, v in fake.items()})
    human = _human_labels(by_rater, consensus)
    pairs = {i: (judge[i], h) for i, h in sorted(human.items()) if i in judge}
    if not pairs:
        return None

    def block(ids: list[str]) -> dict | None:
        ps = [pairs[i] for i in ids]
        if not ps:
            return None
        stats = tpr_tnr(ps)
        return {"casos": len(ps), "concordancia": round(sum(a == b for a, b in ps) / len(ps), 3), **stats,
                "validacao": validation(stats)}

    out = {**block(list(pairs)), "veredito_do_juiz": JUDGE_VERDICT}
    if pert:
        ids = [i for i in pairs if i in pert]
        out["reais"] = block([i for i in pairs if i not in pert])
        out["adulteradas"] = block(ids)
        if out["adulteradas"]:
            kinds: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
            for i in ids:
                kinds[str(pert[i].get("perturbation"))].append(pairs[i])
            out["adulteradas"]["por_tipo"] = {
                k: {"casos": len(ps), "humano_reprova": sum(not h for _, h in ps),
                    "juiz_reprova": sum(not j for j, _ in ps)} for k, ps in sorted(kinds.items())}
        if stale:
            out["aviso"] = stale
    return out


def perturbed_summary(pert: dict[str, dict], by_rater: dict[str, dict[str, bool]], dropped: list[str],
                      results: Path = RESULTS) -> dict | None:
    """Quantas adulteradas existem e quantas entraram na rotulagem, de que tipos; quanto cada pessoa reprovou (a
    adulterada é também conferência de atenção de quem rotula) e quanto o juiz reprovou no conjunto inteiro, sem
    depender de rótulo (é o canário em resposta real, com a evidência real). `dropped`: rótulos de adulterada cuja
    resposta não é mais a de perturbed.json."""
    from evals.perturb import FILE, TYPES

    if not pert:
        return None
    labeled = set().union(*(set(r) for r in by_rater.values())) if by_rater else set()

    def kinds(ids) -> dict[str, int]:
        return {t: sum(pert[i].get("perturbation") == t for i in ids) for t in TYPES}

    fake, stale = perturbed_verdicts(results, pert)
    judge = None
    if fake:
        per = {t: {"julgadas": 0, "reprovou": 0} for t in TYPES}
        for i, v in fake.items():
            k = per.setdefault(str(pert[i].get("perturbation")), {"julgadas": 0, "reprovou": 0})
            k["julgadas"] += 1
            k["reprovou"] += not judge_passes(v)
        judge = {"julgadas": len(fake), "reprovou": sum(not judge_passes(v) for v in fake.values()), "por_tipo": per}
    return {"arquivo": FILE, "geradas": len(pert), "por_tipo": kinds(pert), "rotuladas": len(labeled),
            "rotuladas_por_tipo": kinds(labeled),
            "humano": {n: {"rotuladas": len(r), "reprovou": sum(not ok for ok in r.values())}
                       for n, r in sorted(by_rater.items())},
            "juiz": judge, "fora_da_conta": sorted(dropped), "aviso": stale}


def _same_text(a: str | None, b: str | None) -> bool:
    return " ".join((a or "").split()) == " ".join((b or "").split())


def report(results: Path = RESULTS, path: Path | None = None, out: Path = OUT, base: Path = HERE) -> dict:
    from evals import perturb

    live = {r["id"]: r for r in load_rows(results)}
    auto = {i: auto_pass(r) for i, r in live.items()}
    pert = {r["id"]: r for r in perturb.load(results)}
    files = {"dono": path} if path else label_files(base)
    by_rater: dict[str, dict[str, bool]] = {}
    fake_by_rater: dict[str, dict[str, bool]] = {}
    dropped: set[str] = set()
    answers: dict[str, dict[str, dict]] = {}
    per: dict[str, dict] = {}
    held: dict[str, dict | None] = {}
    for name, f in files.items():
        marked = [r for r in read_labels(f) if r["humano"] in ("pass", "fail")]
        labeled = [r for r in marked if r["id"] in auto]
        if labeled:
            by_rater[name] = {r["id"]: r["humano"] == "pass" for r in labeled}
            answers[name] = {r["id"]: {q: r.get(q, "") for q in QUESTIONS} for r in labeled}
            per[name] = _vs_auto(labeled, auto)
            held[name] = heldout_e2e(labeled, live)
        # adulterada: só vale o rótulo da resposta que está em perturbed.json (a que o juiz julgou)
        fake = [r for r in marked if r["id"] in pert]
        old = {r["id"] for r in fake if not _same_text(r["resposta"], pert[r["id"]].get("answer"))}
        dropped |= old
        fake = [r for r in fake if r["id"] not in old]
        if fake:
            fake_by_rater[name] = {r["id"]: r["humano"] == "pass" for r in fake}
    first = per[sorted(per)[0]] if per else _vs_auto([], auto)
    consensus = _load_consensus(base)
    every = {n: {**by_rater.get(n, {}), **fake_by_rater.get(n, {})} for n in sorted({*by_rater, *fake_by_rater})}
    rep = {
        **first,  # campos de sempre: o 1º rotulador (ordem alfabética) × automático, só nas respostas reais
        "rotuladores": len(per),
        "por_rotulador": {k: {x: v[x] for x in ("rotulos", "concordancia", "kappa")} | {"heldout": held.get(k)}
                          for k, v in per.items()},
        # held-out ponta a ponta do 1º rotulador (o dono): a medida; a intenção vira linha de diagnóstico
        "heldout": held.get(sorted(per)[0]) if per else None,
        # humano × humano só nas reais: negativo plantado (fácil de concordar) inflaria a concordância medida
        "entre_humanos": between_humans(by_rater, answers, consensus),
        "juiz_x_humano": judge_vs_humans(every, consensus, results, pert),
        "adulteradas": perturbed_summary(pert, fake_by_rater, sorted(dropped), results),
        "aviso": None if first["rotulos"] >= 20 else f"só {first['rotulos']} rótulos: abaixo de 20 não dá para confiar",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", type=int, metavar="N")
    ap.add_argument("--mark", nargs="+", metavar="ID=pass|fail[:nota]")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--import-page", type=Path, metavar="JSON",
                    help="fichas da página de rotulagem (scripts/label_page.py) → um CSV por pessoa")
    ap.add_argument("--n", type=int, default=None, help="com --import-page: tamanho da amostra exportada")
    ap.add_argument("--import-text", type=Path, metavar="TXT",
                    help='texto de "Copiar minhas respostas" da página (plano B sem conta do claude.ai)')
    ap.add_argument("--divergences", action="store_true",
                    help="lista o que os 2 rotuladores marcaram diferente → evals/human_divergences.md (consenso)")
    ap.add_argument("--consensus", type=Path, metavar="TXT",
                    help="linhas id=pass|fail|diverge da rodada de consenso → evals/human_consensus.json")
    ap.add_argument("--rater", help="nome do rotulador (um arquivo por pessoa; mesma amostra para todos)")
    ap.add_argument("--splits", help="com --export: só estes splits (ex.: heldout = held-out ponta a ponta)")
    args = ap.parse_args(argv)
    target = csv_path(args.rater)
    if args.export:
        splits = {x.strip() for x in args.splits.split(",") if x.strip()} if args.splits else None
        n = export(args.export, path=target, seed=args.seed, splits=splits)
        print(f"{n} respostas em {target.name} (sem veredito automático)")
    if args.mark:
        print(f"{mark(args.mark, path=target)} rótulos gravados em {target.name}")
    if args.import_text:
        print(json.dumps(import_text(args.import_text.read_text(encoding="utf-8")), ensure_ascii=False))
    if args.import_page:
        print(json.dumps(import_page(args.import_page, args.n, args.seed), ensure_ascii=False))
    if args.divergences:
        found = divergences()
        print(f"{len(found)} situações com marcação diferente → {DIVERGENCES.name}")
    if args.consensus:
        print(json.dumps(import_consensus(args.consensus.read_text(encoding="utf-8")), ensure_ascii=False))
    if args.report:
        rep = report()
        print(json.dumps({k: v for k, v in rep.items() if k != "divergencias"}, ensure_ascii=False))
        for d in rep["divergencias"]:
            print(f"  diverge {d['id']}: humano {d['humano']} × automático {d['automatico']} {d['nota']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
