"""Garantia dos cenários oficiais ANTES do merge da frente K.

Um fato pode estar no corpus e mesmo assim a resposta sair com "não está nas fontes": official-01 (Clássica × Smart)
e official-04 (Pix sem conta) já caíram assim com o trecho certo ingerido (`prod-todas-maquininhas-04`: R$ 79,90 ×
R$ 129,90), mas fora do top-3 do denso. Sem esta checagem isso só aparece na rodada ao vivo; ela mede no fork K, em
segundos e sem API:

(a) cobertura do corpus: cada nome de `expect.entities` dos casos oficiais aparece em pelo menos um trecho ingerido
    (título ou texto, sem caixa nem acento); e, quando `data/sources.json` lista uma página daquela entidade (slug ou
    último segmento da URL contém o nome em forma de slug, ex. "Get Smart" → `get-smart`), a página foi ingerida
    (há trecho com aquela URL);
(b) fato no top-k: para cada caso oficial de CONHECIMENTO, cada regex de `expect.facts` casa (sem caixa; também sem
    acento) um trecho do top-k (padrão 5) do buscador ATIVO para a mensagem do caso, com a mesma expansão de
    glossário do agente; e, se o caso traz a pergunta autônoma (`standalone`, no caso ou em `ctx`), também para ela.
    Caso de conhecimento = intenção cujo plano é só o agente `faq` (fora `general`), ou as de `--intents`.

Saída: uma linha por checagem; FALHA diz o caso, o fato e onde o fato está no corpus (fora do top-k = problema de
busca; em nenhum trecho = problema de corpus). Código de saída 1 se algo falhou.

Uso:
  python scripts/official_check.py                      # evals/cases.jsonl (+ cases.d/), data/ e o buscador ativo
  python scripts/official_check.py --k 5 --json var/official_check.json
  python scripts/official_check.py --intents knowledge  # força as intenções de conhecimento

Para o check.py (frente E53): `from scripts.official_check import check` → `Report` (`.ok`, `.lines()`).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "src", ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

DEFAULT_K = 5


def fold(text: str) -> str:
    """Minúsculas e sem acento ("Clássica" → "classica"); preserva a sintaxe de regex."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch)).lower()


def slug(name: str) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", fold(name)))


def entity_pattern(name: str) -> re.Pattern:
    """Nome inteiro, sem caixa nem acento, espaço/hífen opcionais entre as palavras ("Get Smart" casa "GetSmart")."""
    words = re.findall(r"[a-z0-9]+", fold(name))
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-_]*".join(map(re.escape, words)) + r"(?![a-z0-9])")


def fact_matches(rule: str, text: str) -> bool:
    return bool(re.search(rule, text, re.IGNORECASE) or re.search(fold(rule), fold(text), re.IGNORECASE))


@dataclass
class Failure:
    kind: str  # cases | entity | page | facts_missing | fact | retriever
    case: str
    detail: str

    def line(self) -> str:
        return f"FALHA [{self.kind}] {self.case}: {self.detail}"


@dataclass
class Report:
    retriever: str = ""
    k: int = DEFAULT_K
    failures: list[Failure] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def lines(self) -> list[str]:
        head = f"official_check (buscador {self.retriever or '?'}, top-{self.k})"
        tail = ("OFICIAIS OK" if self.ok else f"OFICIAIS FALHARAM: {len(self.failures)} problema(s)")
        return [head, *(f"ok   {p}" for p in self.passed), *(f.line() for f in self.failures), tail]

    def to_json(self) -> dict:
        return {"ok": self.ok, "retriever": self.retriever, "k": self.k, "passed": self.passed,
                "failures": [asdict(f) for f in self.failures]}


def _intents(case: dict) -> set[str]:
    value = (case.get("expect") or {}).get("intent")
    return {value} if isinstance(value, str) else set(value or ())


def knowledge_intents() -> set[str]:
    """Intenções cujo plano é só o Knowledge (`faq`); `general` usa o mesmo agente, mas responde por dado ao vivo."""
    from app import domain

    plans = getattr(domain.active(), "PLANS", {})
    return {i for i, plan in plans.items() if list(plan) == ["faq"] and i != "general"}


def standalone_of(case: dict) -> str:
    """Pergunta autônoma do caso (contrato R53 → K53: `ctx.facts["standalone"]`), se o caso a traz."""
    ctx = case.get("ctx") or {}
    facts = ctx.get("facts") if isinstance(ctx.get("facts"), dict) else {}
    expect = case.get("expect") or {}
    return str(case.get("standalone") or expect.get("standalone") or ctx.get("standalone") or facts.get("standalone")
               or "").strip()


def _norm_url(url: str) -> str:
    return url.strip().rstrip("/")


def entity_pages(name: str, sources: dict) -> list[str]:
    """URLs de sources.json que são a página da entidade: slug da página ou último segmento da URL contém o slug."""
    target = f"-{slug(name)}-"
    found = []
    for group in (sources.get("groups") or {}).values():
        for page_slug, url in (group.get("pages") or {}).items():
            last = _norm_url(url).rsplit("/", 1)[-1]
            if target in f"-{slug(page_slug)}-" or target in f"-{slug(last)}-":
                found.append(url)
    return found


def check_entities(cases: list[dict], docs: list, sources: dict, report: Report) -> None:
    urls = {_norm_url(d.url) for d in docs}
    texts = [(d.id, fold(f"{d.title}\n{d.text}")) for d in docs]
    for case in cases:
        for name in (case.get("expect") or {}).get("entities") or ():
            pat = entity_pattern(name)
            named = [doc_id for doc_id, text in texts if pat.search(text)]
            if not named:
                report.failures.append(Failure("entity", case["id"], f"nenhum trecho ingerido cita {name!r}: "
                                               "falta a página dessa entidade em data/sources.json (ou o ingest)"))
                continue
            missing = [u for u in entity_pages(name, sources) if _norm_url(u) not in urls]
            if missing:
                report.failures.append(Failure("page", case["id"], f"página de {name!r} listada em sources.json e "
                                               f"sem trecho ingerido: {', '.join(missing)} (python -m app.ingest)"))
                continue
            report.passed.append(f"{case['id']} entidade {name!r} em {len(named)} trecho(s), ex.: {named[0]}")


def _search(retriever, text: str, k: int, standalone: str | None = None) -> list:
    """O MESMO caminho do faq_agent (agents.retrieve: consultas no idioma do corpus, uma por entidade, portão em cada
    uma, fusão por rodada): o que este teste aprova é o que o agente recebe."""
    from app.agents import retrieve

    return list(retrieve(text, standalone=standalone, retriever=retriever, k=k).hits)


def check_facts(cases: list[dict], docs: list, retriever, k: int, report: Report, require_facts: bool,
                intents: set[str]) -> None:
    corpus = [(d.id, f"{d.title}\n{d.text}") for d in docs]
    for case in cases:
        if not _intents(case) & intents:
            continue
        facts = list((case.get("expect") or {}).get("facts") or ())
        if not facts:
            if require_facts:
                report.failures.append(Failure("facts_missing", case["id"], "caso oficial de conhecimento sem "
                                               "expect.facts (a SPEC grava 1 regex por fato de referência)"))
            continue
        queries = [("mensagem", case.get("message", ""), None)]
        if standalone_of(case):
            queries.append(("standalone", case.get("message", ""), standalone_of(case)))
        for label, text, standalone in queries:
            hits = _search(retriever, text, k, standalone)
            top = [(h.doc.id, f"{h.doc.title}\n{h.doc.text}") for h in hits]
            for rule in facts:
                rank = next((i for i, (_, t) in enumerate(top, 1) if fact_matches(rule, t)), None)
                if rank:
                    report.passed.append(f"{case['id']} fato /{rule}/ ({label}) no rank {rank}: {top[rank - 1][0]}")
                    continue
                where = [doc_id for doc_id, t in corpus if fact_matches(rule, t)]
                hint = (f"está no corpus em {', '.join(where[:3])} mas fora do top-{k} (busca)" if where
                        else "não está em nenhum trecho (corpus: página que falta ou regex que não casa a fonte)")
                report.failures.append(Failure("fact", case["id"], f"fato /{rule}/ fora do top-{k} da {label} "
                                               f"{(standalone or text)!r}; {hint}"))


def check(cases_path: Path | None = None, data: Path | None = None, sources_path: Path | None = None,
          k: int = DEFAULT_K, intents: set[str] | None = None, retriever=None, require_facts: bool = True,
          allow_fallback: bool = False) -> Report:
    """Roda (a) e (b) e devolve o relatório. Sem efeito colateral: não grava nada nem chama API.

    `data` troca o DATA_DIR só durante a chamada (o buscador lê o índice de lá).
    """
    import os

    old = os.environ.get("DATA_DIR")
    if data is not None:
        os.environ["DATA_DIR"] = str(data)
    try:
        return _check(cases_path, sources_path, k, intents, retriever, require_facts, allow_fallback)
    finally:
        if data is not None:
            if old is None:
                os.environ.pop("DATA_DIR", None)
            else:
                os.environ["DATA_DIR"] = old


def _check(cases_path, sources_path, k, intents, retriever, require_facts, allow_fallback) -> Report:
    from app.config import data_dir
    from app.jsonl import read_family
    from app.rag import get_retriever, load_docs

    data = data_dir()
    cases_path = cases_path or ROOT / "evals" / "cases.jsonl"
    sources_path = sources_path or data / "sources.json"
    report = Report(k=k)
    cases = [c for c in read_family(cases_path) if c.get("split") == "official"]
    if not cases:
        report.failures.append(Failure("cases", str(cases_path), "nenhum caso com split official"))
        return report
    sources = json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.exists() else {}
    docs = load_docs(data)
    check_entities(cases, docs, sources, report)
    retriever = retriever or get_retriever()
    report.retriever = str(getattr(retriever, "name", type(retriever).__name__))
    if getattr(retriever, "fallback", "") and not allow_fallback:
        report.failures.append(Failure("retriever", report.retriever, f"o buscador ativo caiu ({retriever.fallback}): "
                                       "a garantia não vale para o que roda; baixe o modelo ou use --allow-fallback"))
    check_facts(cases, docs, retriever, k, report, require_facts,
                knowledge_intents() if intents is None else set(intents))
    return report


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cases", type=Path, default=None, help="evals/cases.jsonl (lê também cases.d/)")
    ap.add_argument("--data", type=Path, default=None, help="diretório de dados (padrão: DATA_DIR ou data/)")
    ap.add_argument("--sources", type=Path, default=None, help="padrão: <data>/sources.json")
    ap.add_argument("--k", type=int, default=DEFAULT_K)
    ap.add_argument("--intents", default="", help="intenções de conhecimento, separadas por vírgula")
    ap.add_argument("--no-require-facts", action="store_true", help="caso oficial sem expect.facts não reprova")
    ap.add_argument("--allow-fallback", action="store_true", help="aceita buscador que caiu para outro")
    ap.add_argument("--json", type=Path, default=None, help="grava o relatório em JSON")
    args = ap.parse_args(argv)
    intents = {i.strip() for i in args.intents.split(",") if i.strip()} or None
    report = check(args.cases, args.data, args.sources, args.k, intents, require_facts=not args.no_require_facts,
                   allow_fallback=args.allow_fallback)
    print("\n".join(report.lines()))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report.to_json(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
