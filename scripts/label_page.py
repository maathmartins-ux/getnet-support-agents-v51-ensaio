"""Página de rotulagem para 2+ pessoas: gera o HTML que a sessão publica como Artifact privado do claude.ai.

  python scripts/label_page.py --n 10 --raters Matheus,Bianca [--out var/rotulagem.html]

`--heldout`: só o held-out cego (o passa/falha humano é a medida ponta a ponta; `evals.label --report` dá `heldout`).
A amostra é a MESMA de `python -m evals.label --export N` (mesma função, mesma seed): pergunta, resposta, o que o
redator consultou (`context`) e os links das fontes; nunca a nota automática nem o veredito do juiz. A sessão publica
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


def items(n: int, seed: int = 7, results: Path | None = None, splits: set[str] | None = None) -> list[dict]:
    """Mesma amostra do `evals.label --export` (com `splits`, a mesma função sobre as linhas desses splits)."""
    from evals import label

    rows = label.load_rows(results or label.RESULTS)
    if splits:
        rows = [r for r in rows if r.get("split") in splits]
    before = _before()
    out = []
    for r in label.sample(rows, n, seed):
        seen, sources = set(), []
        for s in r.get("sources") or []:
            if isinstance(s, dict) and s.get("url") and s["url"] not in seen:
                seen.add(s["url"])
                sources.append({"title": s.get("title") or s["url"], "url": s["url"]})
        ctx = r.get("context") or "\n".join(r.get("evidence") or [])
        ids = {str(s.get("id")): s.get("url") for s in r.get("sources") or [] if isinstance(s, dict) and s.get("id")}
        out.append({"id": r["id"], "question": r.get("message") or "", "answer": r.get("answer") or "",
                    "before": before.get(r["id"], []), "source_urls": ids,
                    "evidence": str(ctx)[:EVIDENCE_CHARS], "blocks": evidence_blocks(r), "sources": sources,
                    # pergunta 3 da página: o idioma da pergunta e o da resposta lado a lado (sem os dois à vista,
                    # quem rotula marca resposta em inglês certa como idioma errado)
                    "lang": question_lang(r), "answer_lang": answer_lang(r)})
    return out


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
    sample = hashlib.sha256(json.dumps([r["id"] for r in rows]).encode()).hexdigest()[:12]
    data = json.dumps({"items": rows, "raters": raters, "sample": sample,
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
    ap.add_argument("--raters", required=True, help="nomes separados por vírgula (ex.: Matheus,Bianca)")
    ap.add_argument("--out", type=Path, default=ROOT / "var" / "rotulagem.html")
    args = ap.parse_args(argv)
    raters = [r.strip() for r in args.raters.split(",") if r.strip()]
    if len(raters) < 2:
        ap.error("a avaliação independente pede 2+ pessoas")
    splits = {"heldout"} if args.heldout else ({x.strip() for x in args.splits.split(",")} if args.splits else None)
    rows = items(args.n, args.seed, splits=splits)
    if args.heldout and not rows:
        ap.error("sem linhas do held-out em evals/results/live_heldout.json: rode o held-out ao vivo antes")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(rows, raters), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "items": len(rows), "raters": raters,
                      "capabilities": {"db": {"rules": RULES}, "user": {}, "sample": {}}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
