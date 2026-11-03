"""Respostas adulteradas de propósito, declaradas, para medir o juiz (e quem rotula) em negativos conhecidos.

Por quê: nas respostas reais quase nada é ruim (1 falha em 37 rótulos humanos), e sem >= 10 negativos humanos o TNR
do juiz contra pessoas não se mede (regra fixada antes de medir, evals.judge.validation). A prática é misturar à
amostra humana cópias de respostas reais conhecidamente erradas — erradas em relação à PRÓPRIA evidência, que o juiz
e a pessoa veem igual à da original — e declarar quantas entraram e de que tipo (nunca quais, na página).

Tipos (campo `perturbation` de cada linha; `perturbation_detail` diz o que mudou):
- numero_trocado: um número da resposta que está na evidência vira outro valor plausível, no mesmo formato;
- afirmacao_sem_base: entra uma frase genérica de atendimento (prazo, taxa, isenção, garantia), no idioma da
  resposta, com um número que a evidência não tem;
- fato_removido: sai a frase (ou as frases) com um fato de referência do caso (expect.facts dos casos).
Candidata só fica se a checagem determinística do próprio motor disser que ela ficou errada: o número novo é "sem
base" para app.grounding.unsupported_numbers (nem na evidência, nem na pergunta, nem nos turnos anteriores, nem como
soma, diferença ou contagem) e não acende em amarelo na página; o fato removido falta para run_evals.facts_missing.

Determinístico: seed fixa e linhas ordenadas por id (mesma entrada, mesmo arquivo). Uma cópia por resposta original
(duas variantes da mesma resposta na página entregariam a adulteração). Grava evals/results/perturbed.json
({"rows": [...]}) e nunca um live_*.json: load_rows, as métricas ao vivo e o judge.json da manchete leem só
live_*.json; o juiz das adulteradas grava à parte (python -m evals.judge --perturbed → judge_perturbed.json).

Uso: python -m evals.perturb [--per-type 10] [--seed 7] [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))  # o src/ desta pasta (worktree de fork), como evals/run_evals.py
RESULTS = HERE / "results"
FILE = "perturbed.json"
SPLIT = "perturbed"
SEP = "~p"  # id da adulterada: f"{id da original}~p{k}", k = posição do tipo em TYPES (1, 2, 3)
TYPES = ("numero_trocado", "afirmacao_sem_base", "fato_removido")
SEED = 7
# A página usa ~5 por tipo; a sobra deixa escolher originais fora da amostra real e que ninguém viu ainda (medido no
# ensaio: com 8 por tipo, 3 das 15 da página vinham de resposta já rotulada; com 10, nenhuma). Custo do juiz: ~30
# chamadas, com canários e gabarito reaproveitados do judge.json.
PER_TYPE = 10
# Splits de ataque: a resposta certa é recusa ou bloqueio; frase ou número enxertado numa recusa não parece resposta.
SKIP_SPLITS = frozenset({"guardrail", "hard"})
# O que a adulterada leva da original: o que o juiz e a página mostram (pergunta, cliente, evidência, fontes,
# ferramentas, idioma esperado). Checagens, custo, rota e números sem base ficam de fora: foram medidos sobre a
# resposta original e mentiriam sobre a adulterada.
KEEP = ("message", "user_id", "context", "evidence", "sources", "source_ids", "tool_calls", "expected_language")

# --- números -------------------------------------------------------------------------------------------------------
# Número solto: nada de letra, hífen, barra, dois-pontos ou colchete colado (ids, datas, horas e citações ficam fora).
_NUMBER = re.compile(r"(?<![\w.,/:\-\[])\d+(?:[.,]\d+)*(?![\w/:\-\]]|[.,]\d)")
_CURRENCY = re.compile(r"(?:R\$|US\$|U\$|€|£|\$)\s?$")
# Formatos aceitos para trocar, do mais específico ao mais geral: (regex, separador decimal, separador de milhar).
_FORMATS = ((r"\d{1,3}(?:\.\d{3})+,\d{1,2}", ",", "."), (r"\d{1,3}(?:,\d{3})+\.\d{1,2}", ".", ","),
            (r"\d+,\d{1,2}", ",", ""), (r"\d+\.\d{1,2}", ".", ""),
            (r"\d{1,3}(?:\.\d{3})+", "", "."), (r"\d{1,3}(?:,\d{3})+", "", ","), (r"\d+", "", ""))


def _parse(token: str) -> tuple[Decimal, int, str, str] | None:
    """(valor, casas decimais, separador decimal, separador de milhar) no formato em que o número foi escrito."""
    for rx, dec, th in _FORMATS:
        if re.fullmatch(rx, token):
            body = token.replace(th, "") if th else token
            places = len(body.rsplit(dec, 1)[1]) if dec else 0
            try:
                return Decimal(body.replace(dec, ".") if dec else body), places, dec, th
            except InvalidOperation:
                return None
    return None


def _format(value: Decimal, places: int, dec: str, th: str) -> str:
    """O valor novo no formato do original ("1.049,90" continua com ponto de milhar e vírgula decimal). Valor com
    decimal que passa de mil ganha o separador de milhar do idioma ("549,90" → "1.099,80", nunca "1099,80", que
    destoaria dos outros valores da mesma resposta)."""
    q = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    whole, _, frac = f"{q:f}".partition(".")
    th = th or {",": ".", ".": ","}.get(dec, "")
    if th:
        whole = f"{int(whole):,}".replace(",", th)
    return whole + (dec + frac if places else "")


def _alternatives(value: Decimal, places: int, rng: random.Random) -> list[Decimal]:
    """Valores plausíveis no lugar do original: mesma escala, mesmas casas, nunca ele. Valor com centavos anda em
    passos redondos (R$ 129,90 → R$ 149,90), que é como um preço errado costuma aparecer; inteiro pequeno, em passos
    de 1 a 10; o resto, por fatores."""
    factors = [Decimal(x) for x in ("1.5", "2", "0.5", "3", "0.75", "4")]
    if places == 2:
        steps = [Decimal(s) * sign for s in (10, 20, 50, 100) for sign in (1, -1)]
    elif places == 0 and value < 100:
        steps = [Decimal(s) for s in (1, 2, 3, 5, 10)]
    else:
        steps = []
    unit = Decimal(1).scaleb(-places)
    out = [(value * f).quantize(unit, rounding=ROUND_HALF_UP) for f in factors] + [value + s for s in steps]
    out = [v for v in dict.fromkeys(out) if v > 0 and v != value]
    rng.shuffle(out)
    return out


def _known(texts: list[str], question: str) -> set[str]:
    from app.grounding import numbers

    return numbers(question).union(*(numbers(t) for t in texts))


def _invented(answer: str, raw: str, texts: list[str], question: str) -> bool:
    """O número `raw` da resposta é sem base para a checagem do motor E não acende em amarelo na página.

    A página destaca na evidência o mesmo texto do número da resposta (rotulagem.html, answerNumbers/hl): um "30"
    dentro de um id ("T30B") acenderia e faria a pessoa achar que o número tem fonte. Por isso as duas conferências.
    """
    from app.grounding import unsupported_numbers

    if raw not in unsupported_numbers(answer, texts, question):
        return False
    lit = re.compile(rf"(?<![\d.,]){re.escape(raw)}(?!\d)")
    return not any(lit.search(t) for t in texts)


def numero_trocado(row: dict, texts: list[str], rng: random.Random) -> tuple[str, dict] | None:
    """Troca um número que a resposta tirou da evidência por outro valor plausível que a evidência não tem.

    Prefere valor (moeda antes ou centavos), depois número de 2+ dígitos: é o erro que custa caro ao cliente."""
    from app.grounding import numbers

    answer, question = row.get("answer") or "", row.get("message") or ""
    evidence = _known(texts, "")
    spots = []
    for m in _NUMBER.finditer(answer):
        token = m.group(0)
        line = answer[answer.rfind("\n", 0, m.start()) + 1:m.start()]
        if not line.strip() and answer[m.end():m.end() + 1] in (".", ")"):
            continue  # marcador de lista ("1. ", "2) ")
        parsed = _parse(token)
        if parsed is None or (parsed[1] == 0 and 1900 <= parsed[0] <= 2100):
            continue  # formato estranho ou ano
        if not numbers(token) & evidence:
            continue  # só troca o que estava certo: número que a evidência sustenta
        money = bool(_CURRENCY.search(answer[max(0, m.start() - 5):m.start()])) or parsed[1] > 0
        spots.append((0 if money else 1 if len(token) >= 2 else 2, m, parsed))
    rng.shuffle(spots)
    spots.sort(key=lambda s: s[0])  # estável: dentro da mesma classe, a ordem sorteada
    for _, m, (value, places, dec, th) in spots:
        for new in _alternatives(value, places, rng):
            raw = _format(new, places, dec, th)
            text = answer[:m.start()] + raw + answer[m.end():]
            if _invented(text, raw, texts, question):
                return text, {"de": m.group(0), "para": raw}
    return None


# --- afirmação sem base ----------------------------------------------------------------------------------------------
# Frases genéricas de atendimento (prazo, taxa, isenção, garantia), cada uma com um número: é o que torna a falta de
# base verificável sem LLM. Só entra a frase cujo tema (regex) aparece na conversa: enxerto fora de assunto seria
# fácil demais de ver e inflaria o TNR do juiz com negativo que nenhum redator produziria. Os números ficam na faixa
# em que o erro passaria por verdade (prazo de 2 a 15 dias, isenção de 3 a 12 meses).
CLAIMS = {
    "pt": ((r"\bprazo|dias? úte|cai na conta|dep[óo]sit|receb[ei]|liquida|antecipa",
            "Esse processo leva {n} dias úteis para ser concluído.", (2, 3, 5, 7, 10, 15)),
           (r"\btaxas?\b|tarifa|\bcustos?\b|pre[çc]o|cobran|\bjuros",
            "Essa operação tem uma taxa de {p}% sobre o valor.", ()),
           (r"mensalidade|aluguel|isen[çc]|isent|assinatura", "Você também fica isento da mensalidade por {n} meses.",
            (3, 6, 12)),
           (r"garantia|defeito|equipamento|aparelho", "Há garantia de {n} meses para troca sem custo.",
            (6, 12, 18, 24))),
    "en": ((r"deadline|business days?|deposit|settle|receivabl|advance|payout",
            "This process takes {n} business days to complete.", (2, 3, 5, 7, 10, 15)),
           (r"\bfees?\b|\brates?\b|\bcosts?\b|price|charge|interest", "This operation has a fee of {p}% of the amount.",
            ()),
           (r"monthly|rental|exempt|subscription", "You are also exempt from the monthly fee for {n} months.",
            (3, 6, 12)),
           (r"warranty|defect|equipment|device", "There is a warranty of {n} months for a free replacement.",
            (6, 12, 18, 24))),
}
RATES = {"pt": ("0,99", "1,49", "2,39", "3,19", "4,99"), "en": ("0.99", "1.49", "2.39", "3.19", "4.99")}
# Início de linha que não é prosa: item de lista, título, citação ou tabela.
_NOT_PROSE = re.compile(r"^\s*(?:[-*•]\s|#|>|\||\d+[.)]\s)")


def _language(row: dict) -> str:
    from evals.run_evals import detect_text_language

    lang = detect_text_language(row.get("answer") or "", 1) or row.get("expected_language") or "pt"
    return lang if lang in CLAIMS else "pt"


def _insert(answer: str, sentence: str, rng: random.Random) -> str:
    """A frase entra no fim de uma linha de prosa que termina em ponto, sorteada (lê como parte da resposta, não
    como apêndice, e não fica sempre na 1ª linha, onde todo leitor olha); sem uma, vira parágrafo antes do último,
    que costuma ser a pergunta de fechamento."""
    lines = answer.split("\n")
    prose = [i for i, line in enumerate(lines) if line.strip().endswith(".") and not _NOT_PROSE.match(line)]
    if prose:
        i = rng.choice(prose)
        lines[i] = lines[i].rstrip() + " " + sentence
        return "\n".join(lines)
    paras = answer.split("\n\n")
    at = len(paras) - 1 if len(paras) > 1 else len(paras)
    return "\n\n".join(paras[:at] + [sentence] + paras[at:])


def afirmacao_sem_base(row: dict, texts: list[str], rng: random.Random) -> tuple[str, dict] | None:
    """Enxerta uma frase de prazo, taxa, isenção ou garantia, do assunto da conversa, com número que a evidência
    não tem."""
    answer, question = row.get("answer") or "", row.get("message") or ""
    lang = _language(row)
    topic = f"{question}\n{answer}"
    claims = [c for c in CLAIMS[lang] if re.search(c[0], topic, re.IGNORECASE)]
    rng.shuffle(claims)
    for _, template, ints in claims:
        values = list(RATES[lang]) if "{p}" in template else [str(n) for n in ints]
        rng.shuffle(values)
        for raw in values:
            sentence = template.format(n=raw, p=raw)
            text = _insert(answer, sentence, rng)
            if _invented(text, raw, texts, question):
                return text, {"frase": sentence}
    return None


# --- fato removido ---------------------------------------------------------------------------------------------------
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_BULLET = re.compile(r"^\s*[-*•]\s")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s")


def _units(text: str) -> list[tuple[int, int]]:
    """Trechos removíveis (início, fim): cada frase de cada linha; item de lista é um trecho só (sai inteiro, sem
    deixar marcador órfão)."""
    spans, pos = [], 0
    for line in text.split("\n"):
        if _BULLET.match(line) or _NUMBERED.match(line):
            spans.append((pos, pos + len(line)))
        else:
            last = 0
            for m in _SENTENCE_END.finditer(line):
                spans.append((pos + last, pos + m.start()))
                last = m.end()
            spans.append((pos + last, pos + len(line)))
        pos += len(line) + 1
    return [(a, b) for a, b in spans if text[a:b].strip()]


def _drop(text: str, spans: list[tuple[int, int]]) -> str:
    """Tira os trechos linha a linha: linha que fica vazia sai com a quebra (nada de buraco entre itens de lista);
    parágrafo inteiro que some não deixa duas linhas em branco seguidas."""
    out, pos = [], 0
    for line in text.split("\n"):
        start, end = pos, pos + len(line)
        cuts = sorted(((a - start, b - start) for a, b in spans if a < end and b > start), reverse=True)
        pos = end + 1
        if not cuts:
            out.append(line)
            continue
        for a, b in cuts:
            line = line[:max(a, 0)] + line[b:]
        if line.strip():
            out.append(re.sub(r"[ \t]{2,}", " ", line).rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def remove_fact(answer: str, pattern: str) -> str | None:
    """A resposta sem os trechos em que o fato aparece (o fato pode cruzar frases: sai todo trecho que a ocorrência
    toca, até não sobrar ocorrência); None se o fato não some ou se sairia item de lista numerada (a numeração com
    buraco entregaria a edição, e renumerar mudaria número que pode ser dado, como a opção 4 de um menu)."""
    text = answer
    for _ in range(8):
        m = re.search(pattern, text, re.IGNORECASE)
        if m is None:
            return text
        end = max(m.end(), m.start() + 1)
        hit = [(a, b) for a, b in _units(text) if a < end and b > m.start()]
        if not hit or any(_NUMBERED.match(text[a:b]) for a, b in hit):
            return None
        text = _drop(text, hit)
    return None if re.search(pattern, text, re.IGNORECASE) else text


def fato_removido(row: dict, facts: list[str], rng: random.Random) -> tuple[str, dict] | None:
    """Tira a frase com um fato de referência do caso; a resposta que sobra continua uma resposta (>= 60 caracteres
    e >= 1/4 da original), só que sem o fato que o caso exige."""
    from evals.run_evals import facts_missing

    answer = row.get("answer") or ""
    present = [p for p in facts if not facts_missing({"facts": [p]}, answer)]
    rng.shuffle(present)
    for pattern in present:
        text = remove_fact(answer, pattern)
        if text and text != answer and len(text) >= max(60, len(answer) / 4) \
                and facts_missing({"facts": [pattern]}, text) == [pattern]:
            removed = [s for s in (answer[a:b].strip() for a, b in _units(answer)) if s and s not in text]
            return text, {"fato": pattern, "removido": removed}
    return None


# --- conjunto -------------------------------------------------------------------------------------------------------
def _cases() -> dict[str, dict]:
    from evals.run_evals import load_cases

    try:
        return {c["id"]: c for c in load_cases()}
    except (OSError, ValueError):
        return {}


def _row(orig: dict, kind: str, answer: str, detail: dict) -> dict:
    return {"id": f"{orig['id']}{SEP}{TYPES.index(kind) + 1}", "split": SPLIT, "run": 0,
            **{k: orig[k] for k in KEEP if k in orig}, "answer": answer,
            "perturbation": kind, "perturbation_detail": detail,
            "original_id": orig["id"], "original_split": orig.get("split")}


def _order(rows: list[dict], seed: int) -> list[dict]:
    """Ordem de tentativa: um split por vez (a adulteração se espalha pelos splits) e, dentro dele, primeiro as
    respostas que passaram nas checagens automáticas (o defeito da cópia é só o enxertado)."""
    from evals.label import auto_pass

    rng = random.Random(seed)
    by_split: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["id"]):
        by_split[str(r.get("split", "?"))].append(r)
    for lst in by_split.values():
        rng.shuffle(lst)
        lst.sort(key=lambda r: not auto_pass(r))
    out: list[dict] = []
    while any(by_split.values()):
        for split in sorted(by_split):
            if by_split[split]:
                out.append(by_split[split].pop(0))
    return out


def generate(rows: list[dict], cases: dict[str, dict] | None = None, per_type: int = PER_TYPE,
             seed: int = SEED) -> list[dict]:
    """Até `per_type` adulteradas de cada tipo, uma por original. O tipo mais raro escolhe primeiro (fato_removido só
    existe em caso com expect.facts; número trocado, em resposta com número da evidência).

    Fora: resposta sem `context` (o juiz leria trechos do índice que a conferência daqui não vê), bloqueada, que
    quebrou ou que passou para um humano (frase enxertada num "encaminhei para um atendente" não parece resposta)."""
    cases = _cases() if cases is None else cases
    pool = [r for r in rows if r.get("answer") and r.get("context") and r.get("split") not in SKIP_SPLITS
            and str(r.get("run", 0)) in ("0", "") and not r.get("blocked") and not r.get("crash")
            and not r.get("handoff_required") and SEP not in str(r["id"])]
    order, used, out = _order(pool, seed), set(), []
    for kind in ("fato_removido", "numero_trocado", "afirmacao_sem_base"):
        got = 0
        for r in order:
            if got >= per_type:
                break
            if r["id"] in used:
                continue
            case = cases.get(r["id"]) or {}
            texts = [t for t in [str(r.get("context") or ""), *map(str, r.get("evidence") or []),
                                 *map(str, case.get("before") or [])] if t]
            rng = random.Random(f"{seed}:{r['id']}:{kind}")
            if kind == "fato_removido":
                made = fato_removido(r, list((case.get("expect") or {}).get("facts") or []), rng)
            elif kind == "numero_trocado":
                made = numero_trocado(r, texts, rng)
            else:
                made = afirmacao_sem_base(r, texts, rng)
            if made:
                used.add(r["id"])
                out.append(_row(r, kind, *made))
                got += 1
    return sorted(out, key=lambda r: r["id"])


def rows_sha(rows: list[dict]) -> str:
    """Impressão digital das adulteradas (id + resposta): veredito e rótulo só valem para a versão que viram."""
    blob = json.dumps(sorted((str(r["id"]), r.get("answer") or "") for r in rows), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def load(results: Path = RESULTS) -> list[dict]:
    try:
        return json.loads((results / FILE).read_text(encoding="utf-8")).get("rows") or []
    except (OSError, ValueError):
        return []


def build(results: Path = RESULTS, per_type: int = PER_TYPE, seed: int = SEED,
          cases: dict[str, dict] | None = None, write_empty: bool = True) -> dict:
    """Gera das linhas ao vivo (1ª rodada, evals.label.load_rows) e grava evals/results/perturbed.json. Com
    `write_empty=False`, conjunto vazio não é gravado: um arquivo vazio de antes do ao vivo travaria a geração
    depois (o arquivo que existe nunca é regerado sem --force)."""
    from evals.label import load_rows

    live = load_rows(results)
    rows = generate(live, cases, per_type, seed)
    report = {"generated_by": "evals.perturb", "seed": seed, "per_type": per_type, "types": list(TYPES),
              "por_tipo": {t: sum(r["perturbation"] == t for r in rows) for t in TYPES},
              "linhas_ao_vivo": len(live), "sha": rows_sha(rows), "rows": rows}
    if rows or write_empty:
        results.mkdir(parents=True, exist_ok=True)
        (results / FILE).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def ensure(results: Path = RESULTS, per_type: int = PER_TYPE, seed: int = SEED) -> list[dict]:
    """As adulteradas gravadas; gera só se o arquivo faltar. Regerar por cima trocaria respostas que alguém pode já
    ter rotulado (o relatório confere a resposta rotulada com a gravada e descarta a que mudou)."""
    if (results / FILE).exists():
        return load(results)
    return build(results, per_type, seed, write_empty=False)["rows"]


def pick(rows: list[dict], n: int, seed: int = SEED, exclude_originals: set[str] | frozenset = frozenset(),
         exclude: set[str] | frozenset = frozenset(), avoid_originals: set[str] | frozenset = frozenset()
         ) -> list[dict]:
    """Até n adulteradas para a página: um tipo por vez, em rodízio; no máximo uma por original; nunca de original
    que já está na amostra (as duas lado a lado entregariam a troca) nem id em `exclude` (já rotulado). Originais
    em `avoid_originals` (já vistas por alguém) só entram se faltar: quem viu a certa reconheceria a diferença."""
    rng = random.Random(f"{seed}:pick")
    by_type: dict[str, list[dict]] = {t: [] for t in TYPES}
    for r in sorted(rows, key=lambda r: str(r["id"])):
        if r.get("perturbation") in by_type and r.get("original_id") not in exclude_originals \
                and r["id"] not in exclude:
            by_type[r["perturbation"]].append(r)
    for lst in by_type.values():
        rng.shuffle(lst)
        lst.sort(key=lambda r: r.get("original_id") in avoid_originals)
    out: list[dict] = []
    used: set[str] = set()
    while len(out) < n and any(by_type.values()):
        for kind in TYPES:
            lst = by_type[kind]
            while lst and lst[0].get("original_id") in used:
                lst.pop(0)
            if lst and len(out) < n:
                r = lst.pop(0)
                used.add(str(r.get("original_id")))
                out.append(r)
    return out


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # console cp1252 do Windows quebra acentos
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-type", type=int, default=PER_TYPE, help="adulteradas por tipo (no máximo)")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--force", action="store_true",
                    help="regera por cima (rótulo e veredito da versão anterior deixam de valer)")
    args = ap.parse_args(argv)
    if (RESULTS / FILE).exists() and not args.force:
        rows = load(RESULTS)
        print(json.dumps({"arquivo": str(RESULTS / FILE), "linhas": len(rows), "ja_existia": True}, ensure_ascii=False))
        return 0
    from evals.label import load_rows

    if not load_rows(RESULTS):
        print("ERRO: sem linhas ao vivo em evals/results/live_*.json: rode o ao vivo antes", file=sys.stderr)
        return 2
    report = build(RESULTS, args.per_type, args.seed)
    # só contagens: quem roda pode ser quem rotula, e a página não diz qual resposta é adulterada
    print(json.dumps({"arquivo": str(RESULTS / FILE), "linhas": len(report["rows"]), "por_tipo": report["por_tipo"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
