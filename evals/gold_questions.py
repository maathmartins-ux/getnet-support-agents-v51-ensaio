"""Perguntas do gold de busca POR ORIGEM, em segundos e sem LLM.

  python -m evals.gold_questions                 # rascunhos + negativas → contagem por origem
  python -m evals.gold_questions --check         # reprova gold sem as origens ou com < 15 sem fonte

Origens (o recorte que o placar de busca publica em `by_origin`):
- `official`: a mensagem de cada caso `official` e `official-var` (evals/cases.jsonl e cases.d/);
- `real`: perguntas reais de clientes (evals/real_questions.jsonl e .d/);
- `page`: a pergunta do próprio site, tirada dos trechos de FAQ do corpus (frase que termina em "?");
- `no_source` (>= 15): perguntas fora do domínio de um atendimento — produto que não existe, concorrente, assunto
  pessoal, outro serviço — a partir de modelos fixos do kit.

Por quê: num gold medido assim, a metade das perguntas escritas a partir das páginas saturou (41/41) e toda a
diferença de busca veio da metade das perguntas reais e oficiais (36/41); sem o recorte, um gold só de páginas
mede o caso fácil. E a separação com × sem fonte (AUC, gap) pede >= 15 sem fonte para valer.

Onde grava:
- `page`, `official`, `real` → `evals/retrieval.drafts/<origem>.jsonl` (`question`, `origin`, sem rótulo). Fora da
  família `evals/retrieval.d/`: pergunta sem rótulo leria como "sem fonte" no eval. Viram gold só pelo rótulo
  essencial às cegas de 2 rotuladores (`python -m evals.essential_gold --export` lê os rascunhos; `--import` grava
  cada uma em `evals/retrieval.d/<origem>.jsonl` com `passage_text` e `origin`).
- `no_source` → `evals/retrieval.d/no_source.jsonl` já como negativa (`relevant: []`): é fora do domínio por
  construção; quem monta o domínio apaga a linha que o corpus de fato responde.
Pergunta que já está no gold não é repetida.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

ORIGINS = ("official", "real", "page", "no_source")
MIN_NO_SOURCE = 15
PAGE_MAX = 40  # perguntas de FAQ por rodada de rótulo: o pool às cegas de 2 rotuladores cabe em ~5 min
OFFICIAL_SPLITS = ("official", "official-var")

# Fora do domínio de um atendimento de empresa, em pt e en (o portão é lido por idioma). Sem clima/câmbio/notícia:
# isso o router manda à busca web (`general`), não à base. Produto inexistente é genérico de propósito; quem monta o
# domínio pode trocar por um nome que pareça do domínio e não exista no corpus.
NO_SOURCE_TEMPLATES = (
    "Vocês vendem seguro de viagem para clientes?",
    "Vocês fazem empréstimo imobiliário para comprar a minha loja?",
    "Qual o preço do plano Platinum Ultra Max?",
    "Vocês aceitam pagamento em criptomoeda pelo aplicativo?",
    "Quanto a concorrência cobra pelo mesmo serviço?",
    "Qual empresa do ramo tem a menor taxa do mercado?",
    "Pode me ajudar a escrever um poema de aniversário para a minha mãe?",
    "Qual a melhor dieta para emagrecer rápido?",
    "Vocês vendem passagens aéreas com desconto?",
    "Tem plano de saúde para os clientes de vocês?",
    "Qual o telefone da filial de vocês em Lisboa?",
    "Vocês pagam dividendos para quem é cliente?",
    "Do you sell car insurance for your customers?",
    "How much does the Diamond Infinity plan cost?",
    "Which competitor has the lowest fees?",
    "Can you help me plan my wedding?",
    "Do you offer airline miles for every purchase?",
    "Do you have an office in Tokyo?",
    "Can I buy stocks of other companies through you?",
    "What is the best laptop to buy this year?",
)

_FAQ = re.compile(r"(?:(?<=[.!?\s])|^)([A-ZÁÉÍÓÚÂÊÔÃÕÇ¿][^.!?]{12,160}\?)")


# Início de pergunta (pt/en): corta a trilha de navegação colada antes ("AVANÇAR · Get Conta O que é a Getnet?").
_QSTART = re.compile(r"\b(?:Como|O que|Qual|Quais|Quanto|Quantas|Quantos|Posso|Pode|Podem|Há|Existe|Onde|Quando|"
                     r"Por que|É possível|Preciso|Tenho|Consigo|Devo|Can|How|What|Which|Do|Does|Is|Are|Where|When|"
                     r"Why)\b")


def _clean_question(q: str) -> str:
    q = re.sub(r"\s+", " ", q).split("·")[-1].strip()
    m = _QSTART.search(q)
    return q[m.start():] if m else q


def _norm(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip()).casefold()


def _rows(path: Path) -> list[dict]:
    from app.jsonl import read_family

    return read_family(path)


# Intenção do caso cuja resposta não vem da base (dado do cliente, web, humano, recusa): fora do gold de busca, para
# não gastar o tempo dos rotuladores com pergunta que não tem trecho a marcar. Nomes do domínio de exemplo e do desafio.
NOT_KNOWLEDGE = {"general", "support", "records", "human_request", "blocked"}
# Cabeçalho, tela ou chamada do site que termina em "?" não é pergunta de cliente. Medido no ensaio (rodada 10): 9 das
# 39 perguntas de origem `page` eram isso ("Qual a sua máquina?", "Como você prefere continuar?", "Já é nosso
# cliente?", "Dúvidas sobre Get Tap?") e os "essenciais" delas apontavam para a tela do simulador ou um depoimento.
GENERIC = re.compile(r"^(?:est[áa] com d[úu]vidas?|ficou com (?:alguma )?d[úu]vida|precisa de ajuda|"
                     r"quer saber mais|vamos conversar|como (?:voc[êe] )?prefere continuar|qual (?:[ée] )?a sua "
                     r"m[áa]quina|j[áa] [ée] (?:nosso |nossa )?cliente|d[úu]vidas sobre)\b", re.IGNORECASE)
# Chamada colada no meio de outro texto da página: "Gestão na palma da sua mão Já tem a sua Get Conta?", "R$ 129,90/mês
# Venda mais Já é cliente?", "... Plataforma Digital Dúvidas sobre as maquininhas?". A maiúscula no meio da frase é o
# título seguinte grudado; "Quem já tem conta pode...?" (minúscula) é pergunta e fica.
BANNER = re.compile(r"\S\s+(?:J[áa]\s+(?:tem|[ée])|D[úu]vidas\s+sobre)\b")


def generic(question: str) -> bool:
    """Cabeçalho, tela ou chamada do site (GENERIC no começo, BANNER no meio): fora do gold de busca."""
    return bool(GENERIC.match(question) or BANNER.search(question))


def official_questions(cases: Path) -> list[str]:
    out = []
    for c in _rows(cases):
        msg = c.get("message")
        intent = (c.get("expect") or {}).get("intent")
        if c.get("split") in OFFICIAL_SPLITS and isinstance(msg, str) and msg.strip() and intent not in NOT_KNOWLEDGE:
            out.append(msg.strip())
    return out


def real_questions(real: Path) -> list[str]:
    return [r["message"].strip() for r in _rows(real) if isinstance(r.get("message"), str) and r["message"].strip()]


def faq_questions(knowledge: Path, limit: int = PAGE_MAX) -> list[str]:
    """A pergunta do próprio site: frases de FAQ ("...?") dos trechos, uma por página por rodada até `limit`."""
    by_url: dict[str, list[str]] = {}
    for f in sorted(knowledge.rglob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            doc = json.loads(line)
            text = str(doc.get("text") or "")
            found = [_clean_question(q) for q in _FAQ.findall(text)]
            # FAQ do site repete a pergunta (título do acordeão + corpo): a repetida vem primeiro
            found.sort(key=lambda q: -found.count(q))
            for q in found:
                if 4 <= len(q.split()) <= 20 and not generic(q):
                    by_url.setdefault(str(doc.get("url") or f.name), []).append(q)
    seen, out = set(), []
    queues = [list(dict.fromkeys(qs)) for _, qs in sorted(by_url.items())]
    while queues and len(out) < limit:
        for q in queues:
            while q:
                cand = q.pop(0)
                if _norm(cand) not in seen:
                    seen.add(_norm(cand))
                    out.append(cand)
                    break
            if len(out) >= limit:
                break
        queues = [q for q in queues if q]
    return out


def build(knowledge: Path, cases: Path, real: Path, gold: Path, page_max: int = PAGE_MAX) -> dict[str, list[str]]:
    known = {_norm(r["question"]) for r in _rows(gold) if r.get("question")}
    out: dict[str, list[str]] = {}
    sources = {"official": official_questions(cases), "real": real_questions(real),
               "page": faq_questions(knowledge, page_max), "no_source": list(NO_SOURCE_TEMPLATES)}
    taken = set(known)
    for origin in ORIGINS:
        fresh = []
        for q in sources[origin]:
            if _norm(q) not in taken:
                taken.add(_norm(q))
                fresh.append(q)
        out[origin] = fresh
    return out


def write(built: dict[str, list[str]], drafts: Path, gold: Path) -> dict[str, str]:
    paths = {}
    drafts.mkdir(parents=True, exist_ok=True)
    for origin in ("official", "real", "page"):
        p = drafts / f"{origin}.jsonl"
        p.write_text("".join(json.dumps({"question": q, "origin": origin}, ensure_ascii=False) + "\n"
                             for q in built[origin]), encoding="utf-8")
        paths[origin] = str(p)
    neg = gold.parent / f"{gold.stem}.d" / "no_source.jsonl"
    neg.parent.mkdir(parents=True, exist_ok=True)
    old = neg.read_text(encoding="utf-8") if neg.exists() else ""
    neg.write_text(old + "".join(json.dumps({"question": q, "relevant": [], "origin": "no_source"},
                                            ensure_ascii=False) + "\n" for q in built["no_source"]),
                   encoding="utf-8")
    paths["no_source"] = str(neg)
    return paths


def check(gold: Path, min_no_source: int = MIN_NO_SOURCE) -> list[str]:
    """O que falta no gold para o placar por origem e a separação com × sem fonte valerem; [] = ok."""
    from app.rag import Gold

    rows = _rows(gold)
    pos = [r for r in rows if Gold.from_row(r).positive]
    neg = [r for r in rows if not Gold.from_row(r).positive]
    origins = {r.get("origin") for r in pos}
    missing = []
    if len(neg) < min_no_source:
        missing.append(f"{len(neg)} perguntas sem fonte (relevant: []); pede >= {min_no_source} "
                       "(python -m evals.gold_questions grava os modelos em retrieval.d/no_source.jsonl)")
    if "page" not in origins:
        missing.append("nenhuma pergunta com fonte de origem `page` (FAQ do próprio site)")
    if not origins & {"official", "real"}:
        missing.append("nenhuma pergunta com fonte de origem `official` ou `real` (a metade que separa buscadores)")
    return missing


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="só confere o gold (sai 1 com o que falta)")
    ap.add_argument("--knowledge", type=Path, default=ROOT / "data" / "knowledge")
    ap.add_argument("--cases", type=Path, default=HERE / "cases.jsonl")
    ap.add_argument("--real", type=Path, default=HERE / "real_questions.jsonl")
    ap.add_argument("--gold", type=Path, default=HERE / "retrieval.jsonl")
    ap.add_argument("--drafts", type=Path, default=HERE / "retrieval.drafts")
    ap.add_argument("--page-max", type=int, default=PAGE_MAX)
    ap.add_argument("--dry-run", action="store_true", help="conta sem gravar")
    args = ap.parse_args(argv)
    if args.check:
        missing = check(args.gold)
        for m in missing:
            print(f"GOLD INCOMPLETO: {m}")
        if not missing:
            print("GOLD OK: origens page × official/real e >= 15 sem fonte")
        return 1 if missing else 0
    t0 = time.perf_counter()
    built = build(args.knowledge, args.cases, args.real, args.gold, args.page_max)
    paths = {} if args.dry_run else write(built, args.drafts, args.gold)
    print(json.dumps({"por_origem": {o: len(v) for o, v in built.items()}, "arquivos": paths,
                      "segundos": round(time.perf_counter() - t0, 2)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
