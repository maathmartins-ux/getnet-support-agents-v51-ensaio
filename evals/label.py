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

Adulteradas (evals/perturb.py; `scripts/label_page.py --perturb N`): respostas reais com um defeito plantado
(número trocado ou afirmação sem base contra a evidência; fato de referência removido), em
evals/results/perturbed.json, entram na página misturadas às reais; com elas, TODO id da página é cego (page_id:
HMAC com um sal aleatório da página, guardado em var/rotulagem_salt.json, fora do git), a mistura é embaralhada com o
mesmo sal, e a importação volta ao id do caso por ele (id que nenhum sal guardado explica sai listado, nunca
descartado em silêncio). O sal protege o id e a posição; o texto das adulteradas está em perturbed.json, e por isso
quem rotula não abre o repositório. Sem elas o TNR do juiz contra pessoas não se mede (quase toda resposta real
passa). O relatório separa: humano × automático e humano × humano só nas reais (a adulterada não é resposta do sistema
nem passou pelas checagens); juiz × humano no total (com a composição: negativos reais + plantados), só nas reais e
só nas adulteradas, com a mesma regra de validação — e o total só sai validado se, além do resto, houver >=
evals.judge.VALIDATION_MIN_REAL_NEGATIVES negativos reais e o juiz os reprovar com TNR >=
evals.judge.VALIDATION_MIN_RATE (evals.judge.PLANTED_RULE; senão é "validado só com negativos plantados", que com
respostas reais é não validado); quanto cada pessoa e o juiz reprovaram das adulteradas (o juiz no conjunto todo, por
tipo, sem depender de rótulo). Rótulo de adulterada cuja resposta não bate com a de perturbed.json (arquivo regerado
depois) fica fora da conta, listado.

"Juiz reprova" (judge_passes) segue as 3 perguntas da página: não fundamentada, idioma errado, vazamento OU não útil.
A parte do "não útil" entrou depois de uma medida, e o relatório traz as duas leituras lado a lado, nas respostas
reais (`leituras_reais`) e nas adulteradas (`leituras_plantadas`, e por tipo): antes = só evals.judge.verdict_fails
(judge_passes_before); depois = + helpful, a em vigor.

Motivo da escolha (coluna `selecao` do CSV): por que cada resposta real entrou na amostra — `aleatoria` (sorteio),
`checagem` (uma checagem automática falhou) ou `juiz` (o juiz a reprovou: `--suspects` da página). A exportação grava
no CSV; a página grava em evals/human_selection.json (por amostra, fora do HTML: quem rotula não sabe o que o juiz
achou) e a importação passa para o CSV de cada pessoa. O juiz × humano só valida com o que não dependeu do juiz
(evals.judge.SELECTION_RULE): o juiz reprova por construção o negativo que ele mesmo escolheu. Rótulo sem o motivo
(de antes do registro) é `desconhecida` e também fica fora, à parte, com o escolhido pelo juiz (`fora_da_validacao`).

Mesmo texto (FROZEN_RULE): o rótulo de uma pessoa só se compara — com o juiz, com as checagens ou com outra pessoa —
sobre o texto que ela leu. A página congela, antes de alguém rotular, evals/validation/<amostra>.json (freeze_page): o
texto e a entrada do juiz de cada item, o veredito do juiz sobre esse texto, a bateria (git_sha) e o motivo da escolha.
O --report casa cada rótulo pelo id E pelo texto: com o conjunto congelado (vale depois de bateria nova; se o juiz de
hoje é outro, `python -m evals.judge --validation` julga de novo só esses textos) ou, sem ele (página de antes), com a
resposta de hoje em evals/results. O rótulo de outro texto sai de toda conta e é listado (`rotulos_de_outra_bateria`);
o relatório diz de que bateria são os rótulos (`bateria`). Medido na rodada 10: 35 dos 37 rótulos eram de uma
bateria anterior e eram comparados, em silêncio, com o veredito da resposta nova.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import datetime
import hashlib
import hmac
import json
import os
import random
import secrets
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path

from evals.judge import (
    SELECTED_CHECK,
    SELECTED_JUDGE,
    SELECTED_PLANTED,
    SELECTED_RANDOM,
    SELECTED_UNKNOWN,
    judge_date,
    text_sha,
    verdict_core,
)

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
CSV_PATH = HERE / "human_labels.csv"
OUT = RESULTS / "human_review.json"
# Sais das páginas cegas: fora do git (var/ está no .gitignore) e de tudo que a página mostra.
SALT_FILE = HERE.parent / "var" / "rotulagem_salt.json"
# Motivo da escolha de cada resposta real, por página (record_selection): no git, com os rótulos; nunca na página.
SELECTION_FILE = HERE / "human_selection.json"
# Conjunto congelado de cada página (freeze_page): no git, com os rótulos; nunca na página (traz o veredito do juiz).
VALIDATION_DIR = HERE / "validation"
FROZEN_RULE = ("rótulo de pessoa só se compara com veredito do juiz, checagem ou outra pessoa sobre o MESMO texto: o "
               "da página congelada (evals/validation/<amostra>.json) ou, sem ela, a resposta de hoje em "
               "evals/results; rótulo de outro texto sai de toda conta e é listado")
# O que o juiz lê de uma linha (evals.judge.run): congelado com o texto, para julgar de novo o MESMO item depois
JUDGE_INPUT = ("message", "answer", "context", "source_ids", "sources", "evidence", "tool_calls", "user_id")
FIELDS = ["id", "split", "pergunta", "resposta", "fontes", "ferramentas", "humano", "nota", "tipo_falha",
          "c1", "c2", "c3",  # c1..c3: resposta de cada pergunta da página (sim/nao/naosei), vazio no --mark
          "selecao"]  # por que a resposta entrou na amostra (SELECTED_*); vazio = rótulo de antes do registro
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


def page_id(case_id: str, salt: str) -> str:
    """Id cego da página com adulteradas: HMAC-SHA256 do id do caso com o sal da página. Real e adulterada ganham o
    mesmo formato (nada no id, nem no texto de "Copiar minhas respostas", diz qual é qual) e, sem o sal, o código não
    refaz o caminho de volta do id (com hash sem segredo, bastava aplicar a função aos ids de perturbed.json); a ordem
    da mistura é sorteada com o mesmo sal (scripts/label_page.py). O sal protege o id e a posição, não o texto: quem
    abre evals/results/perturbed.json vê as adulteradas, e por isso quem rotula não abre o repositório. Sal aleatório
    por página (new_salt), fora do que o rotulador vê; a importação usa o mesmo."""
    return "r" + hmac.new(salt.encode("utf-8"), case_id.encode("utf-8"), hashlib.sha256).hexdigest()[:10]


def _salts(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in data.get("salts") or [] if isinstance(e, dict) and e.get("salt")]


def new_salt(use: str, path: Path | None = None) -> str:
    """Sal novo para uma página ou rodada de consenso (`use` diz qual), acrescentado aos guardados: a importação de
    uma página antiga continua achando o dela. Arquivo só do dono (0600) desde o primeiro byte, gravado de uma vez:
    num temporário criado já com 0600 e trocado por os.replace (atômico). Gravar no lugar e só depois dar chmod
    deixaria o sal legível pelos outros entre as duas chamadas, e uma queda no meio truncaria os sais das páginas
    antigas (a importação delas perderia o caminho de volta)."""
    path = path or SALT_FILE
    salt = secrets.token_hex(16)
    when = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    entries = [*_salts(path), {"salt": salt, "uso": use, "em": when}]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"salts": entries}, ensure_ascii=False, indent=1))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    return salt


def unblind(ids: Iterable[str], path: Path | None = None) -> dict[str, str]:
    """{id cego: id do caso} com cada sal guardado (cada página tem o seu)."""
    ids = list(ids)
    return {page_id(i, e["salt"]): i for e in _salts(path or SALT_FILE) for i in ids}


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


def _check_failed(row: dict) -> bool:
    return bool(row.get("crash")) or any(v is False for v in (row.get("checks") or {}).values())


def suspected_ids(rows: list[dict], judge_path: Path | None = None) -> set[str]:
    """Casos com falha suspeita (alguma checagem automática falhou ou o juiz reprovou). Servem para enriquecer a
    amostra humana com negativos: com 1 falha em 18 rótulos, o TNR do juiz não se mede (pede ~20 de cada classe). Só
    os da checagem validam o juiz: o que entrou porque o juiz reprovou, ele reprova por construção (_suspect_reason)."""
    out = {r["id"] for r in rows if _check_failed(r)}
    jp = judge_path or (RESULTS / "judge.json")
    if jp.exists():
        for v in json.loads(jp.read_text(encoding="utf-8")).get("verdicts", []):
            if not v.get("grounded", True) or not v.get("helpful", True):
                out.add(v["id"])
    return out


def _suspect_reason(row: dict) -> str:
    """Por que a suspeita entrou: checagem automática que falhou (entraria sem o juiz) ou, senão, o juiz."""
    return SELECTED_CHECK if _check_failed(row) else SELECTED_JUDGE


def pick_sample(rows: list[dict], n: int, seed: int = 7, suspects: int = 0, exclude: set[str] | None = None,
                suspect_ids: set[str] | None = None) -> list[tuple[dict, str]]:
    """(linha, motivo da escolha) de até `n` casos: até `suspects` com falha suspeita e o resto sorteado por split, sem
    os `exclude`; a ordem é embaralhada e a página nunca mostra o motivo (quem rotula não vê o veredito automático).

    O sorteio vem primeiro, entre todas as linhas: sorteado depois, ele perderia justo as que o juiz reprovou e
    mediria o juiz numa amostra limpa delas (o TPR subiria pela escolha). As suspeitas saem do que sobrou, as da
    checagem automática antes das do juiz (só aquelas validam o juiz, evals.judge.SELECTION_RULE); suspeita que o
    sorteio já trouxe conta como sorteada. Se o sorteio levou suspeitas, o resto da página sai de outro sorteio."""
    rows = [r for r in rows if r["id"] not in (exclude or set())]
    bad = suspect_ids if suspect_ids is not None else suspected_ids(rows)
    size = min(n, len(rows))
    k = min(suspects, size, sum(r["id"] in bad for r in rows))
    drawn = sample(rows, size - k, seed)
    got = [(r, SELECTED_RANDOM) for r in drawn]
    taken = {r["id"] for r in drawn}
    rng = random.Random(seed)
    pool = [r for r in rows if r["id"] in bad and r["id"] not in taken]
    rng.shuffle(pool)
    pool.sort(key=lambda r: _suspect_reason(r) != SELECTED_CHECK)  # estável: dentro de cada motivo, a ordem sorteada
    got += [(r, _suspect_reason(r)) for r in pool[:k]]
    if len(got) < size:
        taken |= {r["id"] for r, _ in got}
        got += [(r, SELECTED_RANDOM) for r in sample([r for r in rows if r["id"] not in taken], size - len(got),
                                                     seed + 1)]
    rng.shuffle(got)
    return got


def labeled_ids(base: Path = HERE) -> set[str]:
    """Ids já rotulados por alguém (qualquer human_labels*.csv): a amostra nova não os repete."""
    out: set[str] = set()
    for path in base.glob("human_labels*.csv"):
        out |= {r["id"] for r in read_labels(path) if r.get("id")}
    return out


def labeled_by(raters: Iterable[str], base: Path = HERE) -> set[str]:
    """Ids que estas pessoas já viram (o arquivo de cada uma; "dono" é o arquivo sem nome)."""
    files = label_files(base)
    out: set[str] = set()
    for name in raters:
        if path := files.get(name.strip().lower()):
            out |= {r["id"] for r in read_labels(path) if r.get("id")}
    return out


def enriched_sample(rows: list[dict], n: int, seed: int = 7, suspects: int = 0, exclude: set[str] | None = None,
                    suspect_ids: set[str] | None = None) -> list[dict]:
    """As linhas de pick_sample, sem o motivo."""
    return [r for r, _ in pick_sample(rows, n, seed, suspects, exclude, suspect_ids)]


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
    picked = sample(rows, n, seed)
    return _write_csv(path, picked, {r["id"]: SELECTED_RANDOM for r in picked})


def _csv_row(r: dict, reason: str = "") -> dict:
    """A linha do CSV de uma resposta, ainda sem rótulo (sem a nota automática: rotulagem às cegas)."""
    return {**{k: "" for k in FIELDS}, "id": r["id"], "split": r.get("split"), "pergunta": r.get("message"),
            "resposta": r.get("answer"), "fontes": " ".join(r.get("source_ids") or [])[:300],
            "ferramentas": " ".join(tool_names(r)), "selecao": reason}


def _write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def _write_csv(path: Path, rows: list[dict], reasons: dict[str, str] | None = None) -> int:
    _write_rows(path, [_csv_row(r, (reasons or {}).get(r["id"], "")) for r in rows])
    return len(rows)


# Do motivo que menos depende do juiz ao que mais: o caso rotulado em mais de uma página fica com o primeiro.
_RANK = {SELECTED_RANDOM: 0, SELECTED_CHECK: 1, SELECTED_PLANTED: 1, SELECTED_JUDGE: 2}


def best_reason(*reasons: str | None) -> str:
    """O motivo de um caso visto em mais de uma página ou por mais de uma pessoa: o que menos depende do juiz (sorteado
    numa página, entrou na amostra sem ele, ainda que outra o trouxesse pelo juiz); nenhum conhecido = desconhecida."""
    known = [r for r in reasons if r in _RANK]
    return min(known, key=_RANK.__getitem__) if known else SELECTED_UNKNOWN


def record_selection(sample_id: str, reasons: dict[str, str], path: Path | None = None) -> None:
    """Grava, antes de alguém rotular, por que cada resposta REAL da página `sample_id` (o `sample` que a página
    guarda em cada ficha) entrou nela: a importação passa o motivo para o CSV de cada pessoa. Fica fora da página (ela
    diria a quem rotula quais o juiz reprovou) e vai para o git com os rótulos; a mesma página gerada de novo troca só
    a entrada dela. Gravado num temporário trocado de uma vez: queda no meio não perde as páginas de antes."""
    path = path or SELECTION_FILE
    try:
        pages = json.loads(path.read_text(encoding="utf-8")).get("paginas") or []
    except (OSError, ValueError):
        pages = []
    when = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    pages = [p for p in pages if isinstance(p, dict) and p.get("amostra") != sample_id]
    pages.append({"amostra": sample_id, "em": when, "motivos": dict(sorted(reasons.items()))})
    write_json(path, {"paginas": pages})


def write_json(path: Path, data: dict) -> None:
    """Grava num temporário e troca de uma vez (os.replace): queda no meio não deixa o arquivo pela metade."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def row_origins(results: Path = RESULTS) -> dict[str, dict]:
    """{id: arquivo, git_sha e recorded_at do live_*.json} da linha que load_rows devolve (a 1ª rodada, 1º arquivo)."""
    out: dict[str, dict] = {}
    for path in sorted(results.glob("live_*.json")):
        rep = json.loads(path.read_text(encoding="utf-8"))
        for row in rep.get("rows", []):
            if str(row.get("run", 0)) in ("0", "") and row["id"] not in out:
                out[row["id"]] = {"source": path.name, "git_sha": rep.get("git_sha"),
                                  "recorded_at": rep.get("recorded_at")}
    return out


def freeze_page(sample: str, rows: list[dict], reasons: dict[str, str], results: Path = RESULTS,
                directory: Path | None = None) -> Path:
    """Congela a página `sample` antes de alguém rotular (evals/validation/<sample>.json, FROZEN_RULE): de cada linha
    (real ou adulterada), o texto que a pessoa vê e a entrada que o juiz vê (pergunta, resposta, evidência e o dia em
    que a resposta foi gerada), as checagens automáticas, o veredito do juiz sobre ESSE texto naquele momento (se
    houver: judge.json para as reais, judge_perturbed.json da mesma versão para as adulteradas; veredito gravado de
    outro texto não entra), o juiz que o deu (modelo e prompt), a bateria (git_sha do live_*.json) e o motivo da
    escolha. Só ids de caso, nunca o id cego da página: o sal continua sendo o único caminho de volta."""
    from evals import judge, perturb

    head = judge._read(results / JUDGE_FILE) or {}
    real = _first_run_by_source(head)
    pert = {r["id"]: r for r in perturb.load(results)}
    fake, _ = perturbed_verdicts(results, pert)
    pj = judge._read(results / JUDGE_PERTURBED) or {}
    origin = row_origins(results)
    items = []
    for r in rows:
        planted = perturb.SEP in str(r["id"]) and r["id"] in pert
        o = origin.get(str(r.get("original_id") if planted else r["id"])) or {}
        sha = text_sha(r.get("answer"))
        v = fake.get(r["id"]) if planted else _verdict_of(real, o.get("source"), r["id"])
        if v is not None and v.get("answer_sha") not in (None, sha):
            v = None  # o juiz julgou outro texto com este id (bateria nova sem juiz): não é veredito deste
        who = pj if planted else head
        item = {"id": r["id"], "split": r.get("split"), "plantada": planted,
                "selecao": SELECTED_PLANTED if planted else reasons.get(r["id"], SELECTED_UNKNOWN),
                "texto_sha": sha, "bateria": o.get("git_sha"), "arquivo": o.get("source"),
                "checks": None if planted else r.get("checks"),
                "entrada_do_juiz": {**{k: r[k] for k in JUDGE_INPUT if k in r},
                                    "business_date": judge_date(r, {"recorded_at": o.get("recorded_at")})},
                "veredito_do_juiz": verdict_core(v) if v else None,
                "juiz": {"model": who.get("model"), "prompt_sha": v.get("prompt_sha") or who.get("prompt_sha")}
                if v else None}
        if planted:
            item |= {k: r.get(k) for k in ("perturbation", "original_id", "original_split")}
        items.append(item)
    data = {"amostra": sample, "em": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
            "regra": FROZEN_RULE, "baterias": sorted({i["bateria"] for i in items if i["bateria"]}), "itens": items}
    path = (directory or VALIDATION_DIR) / f"{sample}.json"
    write_json(path, data)
    return path


def _first_run_by_source(report: dict) -> dict[tuple, dict]:
    """{(arquivo, id): veredito da 1ª rodada}; o mesmo id em dois live_*.json são duas respostas."""
    out: dict[tuple, dict] = {}
    for v in report.get("verdicts") or []:
        if v.get("run", 0) == 0:
            out.setdefault((v.get("source"), v["id"]), v)
    return out


def _verdict_of(verdicts: dict[tuple, dict], source: str | None, case_id: str) -> dict | None:
    """O veredito da resposta de `source`; o veredito sem arquivo gravado (relatório antigo) vale pelo id."""
    return verdicts.get((source, case_id)) or verdicts.get((None, case_id))


def frozen_pages(directory: Path | None = None) -> dict[str, dict]:
    """{amostra: conjunto congelado} de evals/validation/*.json, do mais antigo ao mais novo (`em`)."""
    pages = []
    for path in sorted((directory or VALIDATION_DIR).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("itens"):
            pages.append((str(data.get("em") or ""), str(data.get("amostra") or path.stem), data))
    return {s: d for _, s, d in sorted(pages, key=lambda p: (p[0], p[1]))}


def _frozen_row(item: dict) -> dict:
    """O item congelado como linha ao vivo (o que _write_csv e o juiz leem)."""
    return {"id": item["id"], "split": item.get("split"), **(item.get("entrada_do_juiz") or {})}


def page_selection(sample_id: str | None, path: Path | None = None) -> dict[str, str]:
    """{id do caso: motivo} da página `sample_id`; vazio se ela não registrou (rótulo de seleção desconhecida)."""
    if not sample_id:
        return {}
    try:
        pages = json.loads((path or SELECTION_FILE).read_text(encoding="utf-8")).get("paginas") or []
    except (OSError, ValueError):
        return {}
    for p in reversed(pages):
        if isinstance(p, dict) and p.get("amostra") == sample_id:
            return {str(k): str(v) for k, v in (p.get("motivos") or {}).items()}
    return {}


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
    adulteradas) volta ao id do caso pelos sais guardados (unblind); a adulterada entra no CSV com a resposta
    adulterada, a que a pessoa viu. Devolve {pessoa: rótulos gravados}; marcação cujo id não é de caso nenhum (sal
    da página perdido, página de outra rodada) não some: vai listada em `nao_mapeados` ({pessoa: [ids]}) e no aviso.
    O motivo da escolha de cada resposta (coluna `selecao`) sai do registro da página pela `sample` da ficha
    (page_selection); ficha sem `sample` ou página sem registro dá `desconhecida`, que não valida o juiz.
    Página com conjunto congelado (freeze_page, pela `sample`): o CSV recebe o texto que a pessoa VIU, não o de hoje
    (com bateria nova entre a página e a importação, o de hoje é outra resposta), e o id que só existe no congelado
    (bateria nova, adulteradas regeradas) continua importável. A mesma pessoa numa 2ª página com outro texto do mesmo
    caso: a linha dela passa a ser a desta página (a marcação nova é sobre esse texto)."""
    from evals import perturb

    raw = json.loads(dump.read_text(encoding="utf-8"))
    docs = raw.get("documents", raw.get("docs", [])) if isinstance(raw, dict) else raw
    done: dict = {}
    unmapped: dict[str, list[str]] = {}
    live = {r["id"]: r for r in load_rows(results)}
    planted = {r["id"] for r in perturb.load(results)}
    live.update({r["id"]: r for r in perturb.load(results)})
    pages = frozen_pages()
    blind = unblind({*live, *(it["id"] for p in pages.values() for it in p["itens"])})
    for doc in docs:
        data = doc.get("data", doc) if isinstance(doc, dict) else {}
        rater, marks = str(data.get("rater") or "").strip(), data.get("marks") or {}
        if not rater or not marks:
            continue
        marks = {blind.get(k, k): m for k, m in marks.items()}
        shown = {it["id"]: it for it in (pages.get(str(data.get("sample") or "")) or {}).get("itens") or []}
        if lost := sorted(k for k in marks if k not in live and k not in shown):
            unmapped[rater] = lost
            marks = {k: m for k, m in marks.items() if k in live or k in shown}
            if not marks:
                done[rater] = 0
                continue
        chosen = page_selection(str(data.get("sample") or ""))
        rows = {i: _frozen_row(shown[i]) if i in shown else live[i] for i in marks}
        reasons = {i: SELECTED_PLANTED if (shown[i]["plantada"] if i in shown else i in planted)
                   else best_reason(chosen.get(i), (shown.get(i) or {}).get("selecao")) for i in marks}
        path = csv_path(rater, base)
        if not path.exists():  # o CSV nasce das linhas que a página mostrou (com --splits a amostra é outra)
            _write_csv(path, [rows[i] for i in marks], reasons)
        else:  # 2ª página da mesma pessoa: as respostas novas entram no CSV dela (antes eram ignoradas)
            current = read_labels(path)
            index = {r["id"]: r for r in current}
            for i in marks:
                if i in index and i in shown and not _same_text(index[i]["resposta"], rows[i].get("answer")):
                    index[i].update(_csv_row(rows[i], reasons[i]))
            _write_rows(path, current + [_csv_row(rows[i], reasons[i]) for i in marks if i not in index])
        pairs = []
        for case_id, m in marks.items():
            verdict = m.get("v")
            if verdict not in ("pass", "fail"):
                continue
            note = " ".join(x for x in (m.get("tipo") or "", (m.get("nota") or "").replace(":", " ")) if x)
            pairs.append(f"{case_id}={verdict}" + (f":{note}" if verdict == "fail" and note else ""))
        done[rater] = mark(pairs, path)
        _set_questions(path, {i: m for i, m in marks.items() if isinstance(m, dict)}, reasons)
    if unmapped:
        done["nao_mapeados"] = unmapped
        lost_n = sum(map(len, unmapped.values()))
        print(f"AVISO: {lost_n} marcação(ões) com id que não é de caso nenhum nem de página com sal guardado em "
              f"{SALT_FILE.name} (fora da conta, listadas em nao_mapeados): "
              + "; ".join(f"{r}: {', '.join(ids)}" for r, ids in unmapped.items()), file=sys.stderr)
    return done


def _set_questions(path: Path, marks: dict[str, dict], reasons: dict[str, str] | None = None) -> None:
    """Grava no CSV a resposta de cada pergunta da página (c1..c3): a concordância por pergunta sai daqui. Com
    `reasons`, também o motivo da escolha das respostas desta página (o que menos depende do juiz, se a pessoa já a
    viu em outra página: best_reason)."""
    rows = read_labels(path)
    for r in rows:
        m = marks.get(r["id"]) or {}
        for q in QUESTIONS:
            if m.get(q) in ("sim", "nao", "naosei"):
                r[q] = m[q]
        if reasons and r["id"] in reasons:
            r["selecao"] = best_reason(r.get("selecao"), reasons[r["id"]])
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
            parts = line.split(maxsplit=2)  # "CONFERENCIA <amostra> <nome>": a amostra acha o motivo da escolha
            cur = {"rater": parts[2] if len(parts) > 2 else "", "marks": {},
                   "sample": parts[1] if len(parts) > 1 else ""}
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
    Com adulterada entre as divergências, o arquivo usa id cego para todas (page_id, com sal novo guardado): o rótulo
    combinado entra no juiz × humano, e o "~p" no título diria às duas qual resposta foi plantada antes de decidirem."""
    from evals import perturb

    files = label_files(base)
    names = sorted(files)[:2]
    if len(names) < 2:
        return []
    rows = {n: {r["id"]: r for r in read_labels(files[n]) if r["humano"] in ("pass", "fail")} for n in names}
    a, b = rows[names[0]], rows[names[1]]
    found = []
    # só o mesmo texto: com o mesmo id de outra bateria, as duas leram respostas diferentes (FROZEN_RULE)
    for i in sorted(i for i in set(a) & set(b) if _same_text(a[i]["resposta"], b[i]["resposta"])):
        qs = {q: {names[0]: a[i].get(q), names[1]: b[i].get(q)} for q in QUESTIONS
              if a[i].get(q) in ("sim", "nao") and b[i].get(q) in ("sim", "nao") and a[i][q] != b[i][q]}
        if a[i]["humano"] != b[i]["humano"] or qs:
            found.append({"id": i, "pergunta": a[i]["pergunta"], "resposta": a[i]["resposta"],
                          "veredito": {names[0]: a[i]["humano"], names[1]: b[i]["humano"]}, "perguntas": qs})
    word = {"pass": "certa", "fail": "errada", "sim": "sim", "nao": "não"}
    planted = {r["id"] for r in perturb.load(results)}
    salt = new_salt("consenso") if any(d["id"] in planted for d in found) else None

    def shown(case_id: str) -> str:
        return page_id(case_id, salt) if salt else case_id

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
    volta ao id do caso pelos sais guardados."""
    from evals import perturb

    known = [r["id"] for r in load_rows(results)] + [r["id"] for r in perturb.load(results)]
    alias = unblind(known)
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
# As duas leituras do "juiz reprova", lado a lado nas respostas reais: o `helpful` entrou na definição depois de uma
# medida, e trocar o critério depois de ver o número sem mostrar o de antes é caminho bifurcado.
JUDGE_READINGS = {"antes": "não fundamentada, idioma errado ou vazamento (evals.judge.verdict_fails)",
                  "depois": "não fundamentada, idioma errado, vazamento ou não atende ao pedido (+ helpful=False: as "
                            "3 perguntas da página)"}
JUDGE_READING_WHY = ("a pessoa reprova se qualquer das 3 perguntas da página sai ruim, e a 1ª é se a resposta "
                     "atende ao pedido: sem o `helpful`, a resposta fundamentada que não atende contaria como erro do "
                     "juiz, quando é só critério diferente")


def judge_passes(v: dict) -> bool:
    """O juiz aprova pelo mesmo critério da pessoa. A página reprova se qualquer pergunta sai ruim: não responde ao
    pedido (c1), algo sem base (c2), idioma diferente (c3). O juiz responde as mesmas três em `helpful`, `grounded` e
    `language_ok` (mais o vazamento); deixar `helpful` de fora faria a resposta fundamentada que não atende ao pedido
    (ex.: fato_removido) aparecer como erro do juiz, quando é só critério diferente. Campo ausente não reprova. A
    leitura sem o `helpful` continua no relatório, ao lado (JUDGE_READINGS)."""
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


def judge_passes_before(v: dict) -> bool:
    """A leitura de antes do "juiz reprova" (JUDGE_READINGS["antes"]): só evals.judge.verdict_fails, sem o `helpful`."""
    from evals.judge import verdict_fails

    return not verdict_fails(v)


def judge_vs_humans(by_rater: dict[str, dict[str, bool]], consensus: dict | None,
                    results: Path = RESULTS, perturbed: dict[str, dict] | None = None,
                    selection: dict[str, str] | None = None, verdicts: dict[str, dict] | None = None,
                    warning: str | None = None) -> dict | None:
    """Juiz × humanos em respostas reais (método do rótulo em trace real) e nas adulteradas declaradas: o veredito
    do juiz pelo critério da pessoa (judge_passes) contra o humano — o consenso quando houver, senão a concordância dos
    dois, senão o 1º rotulador. Complementa a calibração em casos construídos (judge.json `calibration`), que mede
    outra coisa: casos escritos à mão, com a evidência escrita à mão. Mesma regra de validação, fixada antes de medir
    (evals.judge.validation), no total, só nas reais e só nas adulteradas (`perturbed`: {id: linha de
    perturbed.json}; o juiz delas vem de judge_perturbed.json, nunca do judge.json da manchete). Bloco com adulterada
    traz a composição dos negativos (`negativos_reais` + `negativos_plantados`) e o TNR do juiz nos reais
    (`tnr_nos_reais`), e só valida se o juiz reprovar o mínimo de negativos reais (evals.judge.PLANTED_RULE, a parte
    que entrou depois da revisão). As duas leituras do "juiz reprova" (JUDGE_READINGS: sem e com o `helpful`) saem
    lado a lado nas reais (`leituras_reais`) e nas adulteradas (`leituras_plantadas`; por tipo, `juiz_reprova_antes`
    ao lado de `juiz_reprova` em `adulteradas.por_tipo`): fato_removido é o tipo em que as duas mais se afastam.

    `selection` ({id: motivo da escolha}, do CSV: report): todo bloco de validação conta só resposta real escolhida
    sem depender do juiz (evals.judge.SELECTION_RULE) — positivos, negativos, `negativos_reais` e `tnr_nos_reais`. A
    escolhida porque o juiz reprovou e a sem motivo gravado (id fora de `selection`: `desconhecida`) saem em
    `fora_da_validacao`, por motivo, com o TNR do juiz nelas (diagnóstico, não validação); `selecao` dá a composição.

    `verdicts` ({id: veredito}, de report): o veredito sobre o MESMO texto de cada rótulo (FROZEN_RULE), já escolhido
    por quem chama, com o aviso das adulteradas em `warning`; sem ele, o do judge.json e do judge_perturbed.json de
    hoje, pelo id."""
    from evals.judge import INDEPENDENT_SELECTION, tpr_tnr, validation

    pert = perturbed or {}
    stale = warning
    if verdicts is None:
        verdicts = {i: v for i, v in (_first_run(results / JUDGE_FILE) or {}).items() if i not in pert}
        fake, stale = perturbed_verdicts(results, pert)
        verdicts.update(fake)
    human = _human_labels(by_rater, consensus)
    ids = [i for i in sorted(human) if i in verdicts]
    if not ids:
        return None
    chosen = {i: SELECTED_PLANTED if i in pert else best_reason((selection or {}).get(i)) for i in ids}
    kept = [i for i in ids if chosen[i] in INDEPENDENT_SELECTION]
    left = {m: [i for i in ids if chosen[i] == m] for m in (SELECTED_JUDGE, SELECTED_UNKNOWN)}

    def pairs(sub: list[str], passes: Callable[[dict], bool]) -> list[tuple[bool, bool]]:
        return [(passes(verdicts[i]), human[i]) for i in sub]

    def block(sub: list[str], passes: Callable[[dict], bool] = judge_passes, real_ones: bool = True) -> dict:
        ps = pairs(sub, passes)
        stats = tpr_tnr(ps)
        out = {"casos": len(ps), "concordancia": round(sum(a == b for a, b in ps) / len(ps), 3) if ps else None,
               **stats, "juiz_reprova": sum(not j for j, _ in ps)}
        real_stats = None
        if any(i in pert for i in sub):  # plantado não vale por real: a composição vai junto da validação
            real_stats = tpr_tnr([p for i, p in zip(sub, ps, strict=True) if i not in pert])
            out |= {"negativos_reais": real_stats["negatives"],
                    "negativos_plantados": stats["negatives"] - real_stats["negatives"],
                    "tnr_nos_reais": real_stats["tnr"]}
        # o que ficou fora pela escolha vai junto da regra, para o leitor ver que existe e não conta
        out_left = {m: tpr_tnr(pairs(s, passes)) for m, s in left.items() if s} if real_ones else None
        return {**out, "validacao": validation(stats, real_stats, out_left)}

    def readings(sub: list[str], real_ones: bool) -> dict:
        return {"em_vigor": "depois", "por_que": JUDGE_READING_WHY,
                "antes": {"regra": JUDGE_READINGS["antes"], **block(sub, judge_passes_before, real_ones)},
                "depois": {"regra": JUDGE_READINGS["depois"], **block(sub, real_ones=real_ones)}}

    real = [i for i in kept if i not in pert]
    out = {**block(kept), "veredito_do_juiz": JUDGE_VERDICT,
           "selecao": {m: n for m in (SELECTED_RANDOM, SELECTED_CHECK, SELECTED_PLANTED, SELECTED_JUDGE,
                                      SELECTED_UNKNOWN) if (n := sum(c == m for c in chosen.values()))}}
    if any(left.values()):
        out["fora_da_validacao"] = {
            m: {**block(s, real_ones=False), "humano_reprova": sum(not human[i] for i in s)}
            for m, s in left.items() if s}
        for b in out["fora_da_validacao"].values():
            b.pop("validacao", None)  # diagnóstico: não tem regra de validação
    if real:
        out["leituras_reais"] = readings(real, True)
    if pert:
        planted_ids = [i for i in kept if i in pert]
        out["reais"] = block(real) if real else None
        out["adulteradas"] = block(planted_ids, real_ones=False) if planted_ids else None
        if planted_ids:
            out["leituras_plantadas"] = readings(planted_ids, False)
            kinds: dict[str, list[str]] = defaultdict(list)
            for i in planted_ids:
                kinds[str(pert[i].get("perturbation"))].append(i)
            out["adulteradas"]["por_tipo"] = {
                k: {"casos": len(sub), "humano_reprova": sum(not human[i] for i in sub),
                    "juiz_reprova": sum(not judge_passes(verdicts[i]) for i in sub),
                    "juiz_reprova_antes": sum(not judge_passes_before(verdicts[i]) for i in sub)}
                for k, sub in sorted(kinds.items())}
        if stale:
            out["aviso"] = stale
    return out


def perturbed_summary(pert: dict[str, dict], by_rater: dict[str, dict[str, bool]], dropped: list[str],
                      results: Path = RESULTS, kinds_of: dict[str, str] | None = None) -> dict | None:
    """Quantas adulteradas existem e quantas entraram na rotulagem, de que tipos; quanto cada pessoa reprovou (a
    adulterada é também conferência de atenção de quem rotula) e quanto o juiz reprovou no conjunto inteiro, sem
    depender de rótulo (é o canário em resposta real, com a evidência real), nas duas leituras do "juiz reprova"
    (`reprovou` = a em vigor, judge_passes; `reprovou_antes` = só verdict_fails). `dropped`: rótulos de adulterada
    cuja resposta não é a de perturbed.json nem a de uma página congelada. `kinds_of` ({id: tipo}): o tipo das
    rotuladas que vêm de uma página congelada (podem não estar mais em perturbed.json)."""
    from evals.perturb import FILE, TYPES

    if not pert and not kinds_of:
        return None
    labeled = set().union(*(set(r) for r in by_rater.values())) if by_rater else set()
    kind = {**{i: r.get("perturbation") for i, r in pert.items()}, **(kinds_of or {})}

    def kinds(ids) -> dict[str, int]:
        return {t: sum(kind.get(i) == t for i in ids) for t in TYPES}

    fake, stale = perturbed_verdicts(results, pert)
    judge = None
    if fake:
        per = {t: {"julgadas": 0, "reprovou": 0, "reprovou_antes": 0} for t in TYPES}
        for i, v in fake.items():
            k = per.setdefault(str(pert[i].get("perturbation")), {"julgadas": 0, "reprovou": 0, "reprovou_antes": 0})
            k["julgadas"] += 1
            k["reprovou"] += not judge_passes(v)
            k["reprovou_antes"] += not judge_passes_before(v)
        judge = {"julgadas": len(fake), "reprovou": sum(not judge_passes(v) for v in fake.values()),
                 "reprovou_antes": sum(not judge_passes_before(v) for v in fake.values()), "por_tipo": per}
    return {"arquivo": FILE, "geradas": len(pert), "por_tipo": kinds(pert), "rotuladas": len(labeled),
            "rotuladas_por_tipo": kinds(labeled),
            "humano": {n: {"rotuladas": len(r), "reprovou": sum(not ok for ok in r.values())}
                       for n, r in sorted(by_rater.items())},
            "juiz": judge, "fora_da_conta": sorted(dropped), "aviso": stale}


def _same_text(a: str | None, b: str | None) -> bool:
    return " ".join((a or "").split()) == " ".join((b or "").split())


def _frozen_verdict(item: dict, page: dict, now: dict) -> tuple[dict | None, dict | None]:
    """(veredito, juiz que o deu) do texto congelado: o do rejulgamento com o juiz de hoje (`now`: modelo e
    prompt_sha do judge.json; evals.judge --validation), se houver; senão o congelado na página."""
    for rj in reversed(page.get("rejulgamentos") or []):
        if (rj.get("model"), rj.get("prompt_sha")) == (now.get("model"), now.get("prompt_sha")) \
                and item["id"] in (rj.get("vereditos") or {}):
            return rj["vereditos"][item["id"]], {"model": rj.get("model"), "prompt_sha": rj.get("prompt_sha")}
    return item.get("veredito_do_juiz"), item.get("juiz")


def _label_records(files: dict[str, Path], results: Path, frozen: Path | None) -> tuple[list[dict], dict, set, dict]:
    """Cada rótulo casado pelo id E pelo texto (FROZEN_RULE): (rótulos válidos, {pessoa: ids de outra bateria},
    adulteradas de outra versão, juiz de hoje). O válido traz o veredito sobre o mesmo texto (o da página congelada —
    o rejulgado com o juiz de hoje, se houver —, senão o de hoje se o texto de hoje for o rotulado), o juiz que o deu,
    a bateria, a página, o motivo da escolha e a linha (split e checagens) daquele texto."""
    from evals import judge, perturb

    live = {r["id"]: r for r in load_rows(results)}
    origin = row_origins(results)
    pert = {r["id"]: r for r in perturb.load(results)}
    head = judge._read(results / JUDGE_FILE) or {}
    pj = judge._read(results / JUDGE_PERTURBED) or {}
    now = {"model": head.get("model"), "prompt_sha": head.get("prompt_sha")}
    real_now = _first_run_by_source(head)
    fake_now, _ = perturbed_verdicts(results, pert)
    pages = frozen_pages(frozen)
    index = {(it["id"], it.get("texto_sha")): (it, s) for s, p in pages.items() for it in p["itens"]}

    def today(case_id: str, sha: str, planted: bool) -> tuple[dict | None, dict | None]:
        """O veredito de hoje, só se o texto de hoje for o rotulado (e, se o veredito gravou o texto, desse texto)."""
        row = (pert if planted else live).get(case_id)
        if not row or text_sha(row.get("answer")) != sha:
            return None, None
        v = fake_now.get(case_id) if planted else _verdict_of(real_now, (origin.get(case_id) or {}).get("source"),
                                                                  case_id)
        if v is None or v.get("answer_sha") not in (None, sha):
            return None, None
        who = pj if planted else head
        return v, {"model": who.get("model"), "prompt_sha": v.get("prompt_sha") or who.get("prompt_sha")}

    recs: list[dict] = []
    other: dict[str, list[str]] = defaultdict(list)
    dropped: set[str] = set()
    for name, f in files.items():
        for r in read_labels(f):
            if r["humano"] not in ("pass", "fail"):
                continue
            i, sha = r["id"], text_sha(r["resposta"])
            rec = {"rater": name, "id": i, "sha": sha, "human": r["humano"] == "pass", "csv": r, "page": None}
            if hit := index.get((i, sha)):
                it, sample = hit
                v, who = _frozen_verdict(it, pages[sample], now)
                if v is None:  # a página congelou antes do juiz rodar: o de hoje, se o texto de hoje for este
                    v, who = today(i, sha, it["plantada"])
                rec |= {"planted": it["plantada"], "kind": it.get("perturbation"), "verdict": v, "judge": who,
                        "battery": it.get("bateria"), "page": sample,
                        "row": {k: it.get(k) for k in ("split", "checks")},
                        "selecao": SELECTED_PLANTED if it["plantada"] else best_reason(r.get("selecao"),
                                                                                         it.get("selecao"))}
            elif i in pert and _same_text(r["resposta"], pert[i].get("answer")):
                v, who = today(i, sha, True)
                rec |= {"planted": True, "kind": pert[i].get("perturbation"), "verdict": v, "judge": who,
                        "battery": (origin.get(str(pert[i].get("original_id"))) or {}).get("git_sha"), "row": {},
                        "selecao": SELECTED_PLANTED}
            elif i in live and _same_text(r["resposta"], live[i].get("answer")):
                v, who = today(i, sha, False)
                rec |= {"planted": False, "kind": None, "verdict": v, "judge": who, "row": live[i],
                        "battery": (origin.get(i) or {}).get("git_sha"), "selecao": r.get("selecao")}
            elif i in pert or perturb.SEP in i:
                dropped.add(i)  # adulterada de outra versão de perturbed.json, sem página congelada que a guarde
                continue
            else:
                other[name].append(i)  # resposta que não é a de hoje nem a de uma página congelada
                continue
            recs.append(rec)
    texts: dict[str, set[str]] = defaultdict(set)
    for rec in recs:
        texts[rec["id"]].add(rec["sha"])
    for rec in recs:  # o mesmo caso rotulado em dois textos (duas baterias) são dois itens, nunca um
        rec["key"] = rec["id"] if len(texts[rec["id"]]) == 1 else f"{rec['id']}@{rec['sha'][:6]}"
    return recs, dict(other), dropped, {**now, "ran": bool(head.get("verdicts"))}


def report(results: Path = RESULTS, path: Path | None = None, out: Path = OUT, base: Path = HERE,
           frozen: Path | None = None) -> dict:
    """Humano × automático, humano × humano, held-out e juiz × humano, sempre sobre o texto que a pessoa leu
    (FROZEN_RULE, _label_records): o conjunto congelado da página (`frozen`, padrão evals/validation/) vale depois de
    bateria nova; sem ele, só o rótulo da resposta de hoje conta. O de outro texto sai de toda conta e vai listado em
    `rotulos_de_outra_bateria`; `bateria` diz de que bateria (git_sha) são os rótulos que contam, e `aviso_juiz` avisa
    o veredito de outro juiz (modelo ou prompt) e o rótulo sem veredito sobre o seu texto. Grava human_review.json."""
    from evals import perturb

    files = {"dono": path} if path else label_files(base)
    recs, other, dropped, now = _label_records(files, results, frozen)
    pert = {r["id"]: r for r in perturb.load(results)}
    by_rater: dict[str, dict[str, bool]] = {}
    fake_by_rater: dict[str, dict[str, bool]] = {}
    answers: dict[str, dict[str, dict]] = {}
    per: dict[str, dict] = {}
    held: dict[str, dict | None] = {}
    for name in files:
        real = [rec for rec in recs if rec["rater"] == name and not rec["planted"]]
        if real:
            labeled = [{**rec["csv"], "id": rec["key"]} for rec in real]
            rows = {rec["key"]: rec["row"] or {} for rec in real}
            by_rater[name] = {rec["key"]: rec["human"] for rec in real}
            answers[name] = {rec["key"]: {q: rec["csv"].get(q, "") for q in QUESTIONS} for rec in real}
            per[name] = _vs_auto(labeled, {k: auto_pass(r) for k, r in rows.items()})
            held[name] = heldout_e2e(labeled, rows)
        # adulterada: só com o texto que o juiz julgou (o de perturbed.json ou o da página congelada)
        if fake := {rec["key"]: rec["human"] for rec in recs if rec["rater"] == name and rec["planted"]}:
            fake_by_rater[name] = fake
    selection: dict[str, str] = {}  # motivo da escolha, o que menos depende do juiz entre as pessoas
    verdicts: dict[str, dict] = {}
    kinds: dict[str, str] = {}
    for rec in recs:
        selection[rec["key"]] = best_reason(selection.get(rec["key"]), rec["selecao"])
        if rec["verdict"] is not None:
            verdicts[rec["key"]] = rec["verdict"]
        if rec["planted"]:
            kinds[rec["key"]] = rec["kind"]
    first = per[sorted(per)[0]] if per else _vs_auto([], {})
    consensus = _load_consensus(base)
    every = {n: {**by_rater.get(n, {}), **fake_by_rater.get(n, {})} for n in sorted({*by_rater, *fake_by_rater})}
    _, fake_note = perturbed_verdicts(results, pert)
    notes = []
    if n := sum(rec["verdict"] is not None and (rec["judge"] or {}).get("model") is not None
                and ((rec["judge"] or {}).get("model"), (rec["judge"] or {}).get("prompt_sha"))
                != (now["model"], now["prompt_sha"]) for rec in recs):
        notes.append(f"{n} rótulo(s) comparados com o veredito de outro juiz (o modelo ou o prompt de quando a página "
                     "foi congelada, não o do judge.json de hoje): `python -m evals.judge --validation` julga de novo "
                     "só esses textos")
    if now["ran"] and (n := sum(rec["verdict"] is None for rec in recs)):
        notes.append(f"{n} rótulo(s) sem veredito do juiz sobre o texto rotulado (fora do juiz × humano): rode o juiz "
                     "na bateria ou, se a página foi congelada, `python -m evals.judge --validation`")
    rep = {
        **first,  # campos de sempre: o 1º rotulador (ordem alfabética) × automático, só nas respostas reais
        "rotuladores": len(per),
        "por_rotulador": {k: {x: v[x] for x in ("rotulos", "concordancia", "kappa")} | {"heldout": held.get(k)}
                          for k, v in per.items()},
        # held-out ponta a ponta do 1º rotulador (o dono): a medida; a intenção vira linha de diagnóstico
        "heldout": held.get(sorted(per)[0]) if per else None,
        # humano × humano só nas reais: negativo plantado (fácil de concordar) inflaria a concordância medida
        "entre_humanos": between_humans(by_rater, answers, consensus),
        "juiz_x_humano": judge_vs_humans(every, consensus, results, {**pert, **{k: {"perturbation": t}
                                                                                 for k, t in kinds.items()}},
                                         selection, verdicts,
                                         fake_note if any(r["planted"] and r["verdict"] is None for r in recs)
                                         else None),
        "adulteradas": perturbed_summary(pert, fake_by_rater, sorted(dropped), results, kinds),
        # de que bateria são os rótulos que contam (git_sha do live_*.json da resposta rotulada)
        "bateria": {"regra": FROZEN_RULE,
                    "rotulos_por_bateria": dict(sorted(Counter(r["battery"] or "desconhecida" for r in recs).items())),
                    "de_pagina_congelada": sum(r["page"] is not None for r in recs),
                    "do_texto_de_hoje": sum(r["page"] is None for r in recs),
                    "paginas": sorted({r["page"] for r in recs if r["page"]})} if recs else None,
        "rotulos_de_outra_bateria": {"rotulos": sum(map(len, other.values())),
                                     "ids": sorted({i for ids in other.values() for i in ids}),
                                     "por_rotulador": {k: sorted(v) for k, v in sorted(other.items())}}
        if other else None,
        "aviso_juiz": "; ".join(notes) or None,
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
