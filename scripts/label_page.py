"""Página de rotulagem para 2+ pessoas: gera o HTML que a sessão publica como Artifact privado do claude.ai.

  python scripts/label_page.py --n 10 --raters Matheus,Bianca [--out var/rotulagem.html]

`--heldout`: só o held-out cego (o passa/falha humano é a medida ponta a ponta; `evals.label --report` dá `heldout`).
`--perturb N`: além das `--n` reais, N respostas com um defeito plantado (evals/results/perturbed.json, de
evals/perturb.py; gera se faltar), equilibradas por tipo, embaralhadas com as reais, nunca ao lado da própria
original nem repetindo uma que alguém desta página já rotulou. Com elas, todo id da página vira cego
(evals.label.page_id, HMAC com sal novo da página em var/rotulagem_salt.json) e a escolha e a ordem das adulteradas
são sorteadas com o mesmo sal: nem a tela, nem o HTML, nem o texto de "Copiar minhas respostas" dizem qual é
adulterada. O sal protege o id e a posição (sem ele, o código não refaz nem um nem outro); o texto das adulteradas está
em evals/results/perturbed.json, e quem abre o arquivo vê quais são: quem rotula não abre o repositório. A saída do
script dá só quantas entraram, por tipo. Recusa (sai com 2) se alguma adulterada saiu de uma resposta ao vivo que
mudou depois (bateria nova): regenere com `python -m evals.perturb --force` e `python -m evals.judge --perturbed`.
A amostra é a MESMA de `python -m evals.label --export N` (mesma função, mesma seed): pergunta, resposta, o que o
redator consultou (`context`) e os links das fontes; nunca a nota automática nem o veredito do juiz.
`--suspects K`: até K das `--n` com falha suspeita, as da checagem automática antes das do juiz, e o resto sorteado
antes delas. Por que cada resposta real entrou (sorteio, checagem, juiz) vai para evals/human_selection.json pela
amostra da página, nunca para o HTML; a importação passa o motivo ao CSV de cada pessoa, e só o que não dependeu do
juiz valida o juiz (evals.judge.SELECTION_RULE): para a página 2 valer como validação, `--n` maior que `--suspects`
(parte sorteada) ou suspeitas da checagem. A saída diz quantas por motivo e avisa quando nenhuma independe do juiz.
A página congela, antes de alguém rotular, evals/validation/<amostra>.json (evals.label.freeze_page): o texto de cada
item, o veredito do juiz naquele momento, a bateria (git_sha) e o motivo da escolha; o `--report` compara juiz e
pessoas sobre esse conjunto, que continua valendo depois de bateria nova (evals.label.FROZEN_RULE). Vai para o git
com os rótulos e nunca para o HTML (traz o veredito do juiz e quais são adulteradas). A sessão publica
com `capabilities: {db: {rules: RULES}, user: {}, sample: {}}` (regras abaixo: cada pessoa grava e lê só a própria
ficha, o dono lê todas; sample = botão "Traduzir" em conversa em inglês),
cada pessoa faz os 2 exemplos de treino (gabarito na tela, fora da conta) e marca as situações no celular; a sessão
lê `rotulos` (ArtifactData list) para um JSON e roda
`python -m evals.label --import-page <json>`, que grava evals/human_labels.<nome>.csv de cada uma.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TEMPLATE = ROOT / "scripts" / "templates" / "rotulagem.html"
EVIDENCE_CHARS = 4000
# Cada ficha em rotulos/<id da pessoa>: só ela grava; a pasta inteira, só o dono (e quem edita) lê.
RULES = [{"path": "rotulos", "read": "admin", "write": "self"},
         {"path": "rotulos/{self}", "read": "view", "write": "interact"}]


# Rótulos em português para campos comuns de dados de lojista; campo fora da lista aparece com "_" virando espaço.
KEY_LABELS = {
    "transaction_id": "transação", "date": "data", "method": "forma de pagamento", "amount": "valor (R$)",
    "status": "situação", "terminal_id": "maquininha", "decline_code": "código de recusa",
    "decline_reason": "motivo da recusa", "contestable": "pode contestar", "model": "modelo", "connection": "conexão",
    "signal": "sinal", "online": "ligada e conectada", "last_contact_min": "último contato (minutos atrás)",
    "paper_roll": "bobina de papel", "blocked": "bloqueada", "count": "quantidade", "declined_count": "recusadas",
    "approved_count": "aprovadas", "approved_total": "total aprovado (R$)", "total": "total (R$)",
    "available": "disponível (R$)", "available_total": "disponível (R$)", "due_date": "data prevista",
    "net_amount": "valor líquido (R$)", "gross_amount": "valor bruto (R$)", "fee": "taxa", "fee_pct": "taxa (%)",
    "settlements": "recebimentos", "transactions": "vendas", "terminals": "maquininhas", "plan": "plano",
    "name": "nome", "merchant_id": "loja", "case_id": "protocolo", "protocol": "protocolo",
}
SKIP_KEYS = {"ok", "calculado_em_codigo", "nota_calculo"}
# Anotações que o pipeline põe no contexto (app/pipeline.py: memória da conversa) e não são fonte nem dado novo.
MEMORY_PREFIXES = ("[memória da conversa]", "Assunto atual:", "Registros vistos nas ferramentas",
                   # notas do próprio sistema (data de hoje, conferência de números, ids, textos-modelo do humano)
                   "Hoje é", "Today is", "Valores vistos em fontes", "IDs citados pelo cliente",
                   "Se quiser, posso encaminhar", "If you'd like, I can hand", "Encaminhei para um atendente",
                   "I've passed your question")
TEXT_CHARS = 1200


def _label(key: str) -> str:
    return KEY_LABELS.get(key, key.replace("_", " "))


def _value(v) -> str:
    if isinstance(v, bool):
        return "sim" if v else "não"
    if v is None or v == "":
        return "—"
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else f"{v:.2f}".replace(".", ",")
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)[:200]
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?", str(v))
    if m:  # data ISO → dd/mm/aaaa, como o lojista lê
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    return str(v).replace("_", " ")


def _data_block(obj: dict, title: str) -> dict:
    """Resultado de ferramenta (JSON) → campos soltos + tabelas, com rótulos em português."""
    body = obj.get("data", obj) if isinstance(obj.get("data", obj), dict) else {"dados": obj.get("data")}
    fields, tables = [], []
    for k, v in body.items():
        if k in SKIP_KEYS:
            continue
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            cols = list(dict.fromkeys(c for x in v for c in x if c not in SKIP_KEYS))
            tables.append({"caption": _label(k), "columns": [_label(c) for c in cols],
                           "rows": [[_value(x.get(c)) for c in cols] for x in v[:30]]})
        elif isinstance(v, dict):
            fields += [[f"{_label(k)} · {_label(k2)}", _value(v2)] for k2, v2 in v.items() if k2 not in SKIP_KEYS]
        else:
            fields.append([_label(k), _value(v)])
    if obj.get("ok") is False:
        fields.insert(0, ["resultado", "a consulta falhou"])
    return {"kind": "data", "title": title, "fields": fields, "tables": tables}


def evidence_blocks(row: dict) -> list[dict]:
    """O `context` do redator ("- " por item: JSON de ferramenta, "Título: texto" de fonte, memória, regras) em
    blocos legíveis para quem não é da área."""
    raw = row.get("context") or "\n".join(f"- {e}" for e in row.get("evidence") or [])
    items_, cur = [], None
    for line in str(raw).splitlines():
        if line.startswith("- "):
            cur = line[2:]
            items_.append(cur)
        elif items_:
            items_[-1] += "\n" + line
    tools = [t.get("name", "") if isinstance(t, dict) else str(t) for t in row.get("tool_calls") or []]
    urls = {s.get("title"): s.get("url") for s in row.get("sources") or [] if isinstance(s, dict)}
    out, extra, t, rules = [], [], 0, False
    for it in items_:
        it = it.strip()
        if it.startswith("[policy:capabilities]"):
            rules = True  # o cartão de capacidades fecha o contexto: tudo dali em diante são regras do sistema
            continue
        if rules:
            extra.append({"kind": "rules", "text": it})
            continue
        if it.startswith("{"):
            try:
                obj = json.loads(it)
            except ValueError:
                obj = None
            if isinstance(obj, dict):
                name = tools[t] if t < len(tools) else ""
                t += 1
                out.append(_data_block(obj, "Dados da loja do cliente" + (f" ({name})" if name else "")))
                continue
        if it.startswith(MEMORY_PREFIXES):
            body = it.split("]", 1)[1].strip() if it.startswith("[") else it
            extra.append({"kind": "memory", "text": body[:TEXT_CHARS]})
            continue
        title, _, text = it.partition(": ")
        if not text:
            title, text = "Informação", it
        out.append({"kind": "text", "title": title, "text": text[:TEXT_CHARS], "url": urls.get(title) or ""})
    return out[:10] + extra


def _before() -> dict[str, list[str]]:
    """Turnos anteriores de cada caso (casos de memória): sem eles "Por que ela foi recusada?" não se avalia."""
    try:
        from evals import run_evals

        return {c["id"]: [str(t) for t in c.get("before") or []] for c in run_evals.load_cases()}
    except (OSError, ValueError):
        return {}


def question_lang(row: dict) -> str:
    """Idioma da pergunta: o do caso (expect.language), senão o do texto da pergunta; "" = não detectado."""
    from evals.run_evals import detect_text_language

    return row.get("expected_language") or detect_text_language(row.get("message") or "", 1) or ""


def answer_lang(row: dict) -> str:
    """Idioma da resposta pelo TEXTO (o que o eval detectou), nunca o campo declarado; "" = não detectado."""
    from evals.run_evals import detect_text_language

    return row.get("language_detected") or detect_text_language(row.get("answer") or "", 1) or ""


class StalePerturbed(ValueError):
    """perturbed.json saiu de respostas ao vivo que mudaram depois: a cópia não é mais "a resposta real com um
    defeito", e juiz e rótulo dela falariam de outra resposta."""


def perturbed_pool(results: Path, splits: set[str] | None) -> list[dict]:
    """As adulteradas de perturbed.json (gera se faltar) dos splits pedidos. StalePerturbed se alguma saiu de resposta
    que mudou depois da geração (perturb.stale): conferido antes de criar o sal, para não deixar sal órfão."""
    from evals import label, perturb

    rows = perturb.ensure(results)
    if old := perturb.stale(rows, label.load_rows(results)):
        raise StalePerturbed(f"{len(old)} de {len(rows)} respostas de {perturb.FILE} saíram de uma resposta ao vivo "
                             "que mudou depois da geração (ou de arquivo sem a impressão digital da original): rode "
                             "`python -m evals.perturb --force` e `python -m evals.judge --perturbed` antes da página")
    return [r for r in rows if not splits or r.get("original_split") in splits]


def mix_perturbed(picked: list[dict], pool: list[dict], k: int, salt: str, seed: int = 7, fresh: bool = False,
                  raters: list[str] | None = None, base: Path | None = None) -> list[dict]:
    """As reais sorteadas + até k adulteradas do `pool` (evals.perturb.pick), embaralhadas. A amostra real não muda (a
    mesma do `--export`); a adulterada nunca vem de uma original que já está na página, nunca é uma que alguém de
    `raters` já rotulou (sem `raters`, qualquer pessoa), e prefere original que ninguém rotulou ainda (quem viu a
    resposta certa reconheceria a diferença de memória). A escolha e a mistura são sorteadas com o `salt` da página:
    com a seed só (fixa, no código), a posição de cada adulterada se refaria sem o sal, e o id cego não esconderia
    nada."""
    from evals import label, perturb

    base = base or label.HERE
    seen = label.labeled_ids(base)
    mine = label.labeled_by(raters, base) if raters else seen
    extra = perturb.pick(pool, k, seed, exclude_originals={r["id"] for r in picked},
                         exclude=mine | (seen if fresh else set()), avoid_originals=seen, salt=salt)
    out = picked + extra
    random.Random(f"{salt}:mistura").shuffle(out)
    return out


def sample_id(rows: list[dict]) -> str:
    """A `sample` da página (o que ela grava em cada ficha e o nome do conjunto congelado): impressão digital dos ids
    e dos textos, na ordem em que aparecem. Só com os ids, a mesma amostra sorteada numa bateria nova (outros textos)
    sobrescrevia o conjunto congelado da página de antes, e os rótulos dela perdiam o texto que as pessoas leram."""
    from evals.judge import text_sha

    return hashlib.sha256(json.dumps([[r["id"], text_sha(r.get("answer"))] for r in rows]).encode()).hexdigest()[:12]


def items(n: int, seed: int = 7, results: Path | None = None, splits: set[str] | None = None,
          suspects: int = 0, fresh: bool = False, perturb: int = 0, raters: list[str] | None = None,
          salt: str | None = None, base: Path | None = None) -> list[dict]:
    """Os itens de build, sem o motivo da escolha."""
    return build(n, seed, results, splits, suspects, fresh, perturb, raters, salt, base)[0]


def build(n: int, seed: int = 7, results: Path | None = None, splits: set[str] | None = None,
          suspects: int = 0, fresh: bool = False, perturb: int = 0, raters: list[str] | None = None,
          salt: str | None = None, base: Path | None = None) -> tuple[list[dict], dict[str, str]]:
    """(itens da página, {id do caso: motivo da escolha} das reais). Mesma amostra do `evals.label --export` (com
    `splits`, a mesma função sobre as linhas desses splits). `suspects`: até N casos com falha suspeita na amostra
    (negativos para medir o TNR do juiz; evals.label.pick_sample); `fresh`: sem os já rotulados; `perturb`: mais até N
    adulteradas declaradas (mix_perturbed), e então todo id é cego e a mistura é sorteada com `salt` ou um sal novo
    guardado (evals.label.new_salt): o mesmo sal dá a mesma página; `base`: onde ficam os human_labels*.csv. O motivo
    fica registrado pela `sample` da página (evals.label.record_selection) antes de alguém rotular, fora do HTML."""
    from evals import label

    results = results or label.RESULTS
    base = base or label.HERE
    rows = label.load_rows(results)
    if splits:
        rows = [r for r in rows if r.get("split") in splits]
    before = _before()
    out = []
    if suspects or fresh:  # as suspeitas pelo judge.json desta pasta de resultados
        chosen = label.pick_sample(rows, n, seed, suspects, label.labeled_ids(base) if fresh else None,
                                   label.suspected_ids(rows, results / "judge.json"))
    else:
        chosen = [(r, label.SELECTED_RANDOM) for r in label.sample(rows, n, seed)]
    picked = [r for r, _ in chosen]
    reasons = {r["id"]: why for r, why in chosen}
    if perturb:
        pool = perturbed_pool(results, splits)
        salt = salt or label.new_salt("página")  # só depois da conferência: página recusada não deixa sal órfão
        picked = mix_perturbed(picked, pool, perturb, salt, seed, fresh, raters, base)
    for r in picked:
        seen, sources = set(), []
        for s in r.get("sources") or []:
            if isinstance(s, dict) and s.get("url") and s["url"] not in seen:
                seen.add(s["url"])
                sources.append({"title": s.get("title") or s["url"], "url": s["url"]})
        ctx = r.get("context") or "\n".join(r.get("evidence") or [])
        ids = {str(s.get("id")): s.get("url") for s in r.get("sources") or [] if isinstance(s, dict) and s.get("id")}
        # adulterada: os turnos anteriores são os da original (é a mesma conversa, com a resposta trocada)
        out.append({"id": label.page_id(r["id"], salt) if salt else r["id"], "question": r.get("message") or "",
                    "answer": r.get("answer") or "", "before": before.get(r.get("original_id") or r["id"], []),
                    "source_urls": ids,
                    "evidence": str(ctx)[:EVIDENCE_CHARS], "blocks": evidence_blocks(r), "sources": sources,
                    # pergunta 3 da página: o idioma da pergunta e o da resposta lado a lado (sem os dois à vista,
                    # quem rotula marca resposta em inglês certa como idioma errado)
                    "lang": question_lang(r), "answer_lang": answer_lang(r)})
    if out:
        label.record_selection(sample_id(out), reasons)
        # o texto de cada item, o veredito do juiz sobre ele e a bateria, antes de alguém rotular: a validação juiz ×
        # pessoas sai daqui e não envelhece com bateria nova (evals.label.FROZEN_RULE)
        label.freeze_page(sample_id(out), picked, reasons, results)
    return out, reasons


# Treino com gabarito: 2 exemplos antes das situações, um certo e um errado, que ensinam as duas armadilhas que
# derrubam a concordância entre pessoas (medido sem treino: kappa 0,054) — resposta em inglês certa marcada como
# idioma errado e número sem base que passa despercebido. `key` = a marcação esperada; não entram na conta nem no
# export.
PRACTICE = [
    {"id": "treino-1", "question": "How much did I sell yesterday on debit?", "lang": "en", "answer_lang": "en",
     "answer": "Yesterday you sold R$ 150,00 on debit, in 3 sales.",
     "blocks": [{"kind": "data", "title": "Dados da loja do cliente", "tables": [], "fields": [
         ["período", "ontem"], ["forma de pagamento", "débito"], ["quantidade", "3"], ["total (R$)", "150,00"]]}],
     "key": {"c1": "sim", "c2": "nao", "c3": "sim"}, "expected": "pass",
     "explain": "Responde o que foi perguntado; R$ 150,00 e 3 vendas aparecem nos dados (em amarelo); pergunta e "
                "resposta estão as duas em inglês, então o idioma está certo — não precisa ser português."},
    {"id": "treino-2", "question": "Em quantos dias cai o dinheiro de uma venda no crédito à vista?", "lang": "pt",
     "answer_lang": "pt", "answer": "No crédito à vista, o dinheiro cai na sua conta em 2 dias.",
     "blocks": [{"kind": "text", "title": "Prazos de recebimento", "url": "",
                 "text": "Vendas no crédito à vista: o valor cai na conta em 30 dias. Débito: 1 dia útil."}],
     "key": {"c1": "sim", "c2": "sim", "c3": "sim"}, "expected": "fail",
     "explain": "Responde o pedido e está em português, mas o \"2 dias\" não aparece em lugar nenhum do que ele "
                "tinha em mãos: a fonte diz 30 dias. Um número sem base basta para a resposta ser ERRADA."},
]


def render(rows: list[dict], raters: list[str], practice: list[dict] | None = None) -> str:
    data = json.dumps({"items": rows, "raters": raters, "sample": sample_id(rows),
                       "practice": PRACTICE if practice is None else practice}, ensure_ascii=False)
    data = data.replace("</", "<\\/")  # nada dentro do JSON fecha o <script>
    return TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/", data)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--splits", help="só estes splits (ex.: official,memory); padrão: todos os live_*.json")
    ap.add_argument("--heldout", action="store_true",
                    help="só o held-out (live_heldout.json): o passa/falha humano às cegas é a medida ponta a ponta")
    ap.add_argument("--suspects", type=int, default=0,
                    help="até N das --n com falha suspeita (checagem automática antes do juiz): negativos para o TNR "
                         "do juiz; só os da checagem e os sorteados validam o juiz (use --n maior que --suspects)")
    ap.add_argument("--fresh", action="store_true", help="sem os casos já rotulados (human_labels*.csv)")
    ap.add_argument("--perturb", type=int, default=0, metavar="N",
                    help="mais N respostas adulteradas de propósito (evals/results/perturbed.json; gera se faltar), "
                         "sem marca na página: negativos conhecidos para validar o juiz contra pessoas")
    ap.add_argument("--raters", required=True, help="nomes separados por vírgula (ex.: Matheus,Bianca)")
    ap.add_argument("--out", type=Path, default=ROOT / "var" / "rotulagem.html")
    args = ap.parse_args(argv)
    raters = [r.strip() for r in args.raters.split(",") if r.strip()]
    if len(raters) < 2:
        ap.error("a avaliação independente pede 2+ pessoas")
    splits = {"heldout"} if args.heldout else ({x.strip() for x in args.splits.split(",")} if args.splits else None)
    try:
        rows, reasons = build(args.n, args.seed, splits=splits, suspects=args.suspects, fresh=args.fresh,
                              perturb=args.perturb, raters=raters)
    except StalePerturbed as exc:  # nada é gravado: página com cópia de resposta velha não sai
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    if args.heldout and not rows:
        ap.error("sem linhas do held-out em evals/results/live_heldout.json: rode o held-out ao vivo antes")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(rows, raters), encoding="utf-8")
    from evals import label

    info = {"out": str(args.out), "items": len(rows), "raters": raters,
            "capabilities": {"db": {"rules": RULES}, "user": {}, "sample": {}},
            # o conjunto congelado vai para o git junto dos rótulos (o HTML não o traz)
            "congelado": str(label.VALIDATION_DIR / f"{sample_id(rows)}.json") if rows else None,
            # quantas reais por motivo da escolha (nunca quais: quem roda o script pode ser quem rotula)
            "selecao": {why: list(reasons.values()).count(why) for why in sorted(set(reasons.values()))}}
    if args.perturb:
        info["adulteradas"] = _perturbed_counts(rows)
    print(json.dumps(info, ensure_ascii=False))
    if args.suspects and not {label.SELECTED_RANDOM, label.SELECTED_CHECK} & set(reasons.values()):
        print("AVISO: nenhuma resposta real desta página entrou sem depender do juiz (sorteio ou checagem automática): "
              "os rótulos dela não validam o juiz, só servem de diagnóstico (evals.judge.SELECTION_RULE). Use --n "
              "maior que --suspects para ter uma parte sorteada.", file=sys.stderr)
    return 0


def _perturbed_counts(rows: list[dict]) -> dict:
    """Quantas adulteradas entraram, por tipo (nunca quais: quem roda o script pode ser quem rotula)."""
    from evals import label, perturb

    kinds = {r["id"]: r.get("perturbation") for r in perturb.load(label.RESULTS)}
    back = label.unblind(kinds)
    got = [kinds[back[r["id"]]] for r in rows if r["id"] in back]
    return {"total": len(got), "por_tipo": {t: got.count(t) for t in perturb.TYPES}}


if __name__ == "__main__":
    raise SystemExit(main())
