"""Medida de retrieval sem LLM: métricas por pergunta, comparativo de configurações e escolha com orçamento de latência.

Usado por `python -m evals.run_evals --compare-retrievers` (grava evals/results/retrieval_compare.json) e por
`--choose-retriever [--apply]` (grava data/retriever.json, que o app lê como padrão; o README lê os números dele).

Métricas (k=3, o agente usa as 3 primeiras passagens), por pergunta e na média:
- recall@3: passagens do gold achadas no top-3 / passagens do gold (rag.Gold.resolve_groups: dedupe e corpus
  re-chunkado não mudam o denominador);
- mrr: 1/posição do primeiro relevante no top-3 (MRR@3; 0 se nenhum);
- hit@3 (com IC de Wilson), ndcg@3 (ganho = passagens novas que o trecho cobre; ideal = melhor top-3);
- page: as mesmas por URL (independe de como a página foi cortada em trechos);
- latency_ms: p50/p95 da busca inteira por pergunta (embedding da consulta + rerank), em CPU, depois de 1 aquecimento.
"""
from __future__ import annotations

import datetime
import json
import math
import statistics
import time
from pathlib import Path

K = 3
# O redator recebe os 5 primeiros (faq_top_k), então a cobertura que
# importa é a do top-5; e o "rank do 1º gold por pergunta" (até DEPTH) diz onde a busca erra, não só se erra.
K_GEN = 5
DEPTH = 10
# Teto padrão de p95 por consulta na escolha: o agente ainda chama o LLM depois da busca, e um rerank de vários
# segundos em CPU dobraria o tempo de resposta de uma pergunta de FAQ. Troque com --latency-budget-ms.
LATENCY_BUDGET_MS = 1500.0
# Teto padrão de RAM residente por processo na escolha. Medido: o eval offline com e5-large + bge-m3-int8 teve pico
# de 2,5–2,9 GB; numa máquina de 15 GB rodam juntos a API, o eval ao vivo e outra sessão, e 4 GB por processo deixa
# API + eval em 8 GB, metade dela. Troque com --ram-budget-mb (0 = sem teto).
RAM_BUDGET_MB = 4096.0
BASELINE = "bm25"


def _query(question: str) -> str:
    from app.agents import expand_query

    return expand_query(question)  # a mesma consulta que o agente faz (pergunta + glossário pt↔en)


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return round(s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))], 1)


def _dcg(gains: list[int]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def _ideal_gains(units: list[set[str]]) -> list[int]:
    """Melhor top-k possível: guloso pelo trecho que cobre mais passagens ainda não cobertas (com dedupe, um trecho
    mantido pode valer por duas passagens do gold; o ideal não pode exigir dois trechos)."""
    left, gains = set(range(len(units))), []
    cands = set().union(*units) if units else set()
    for _ in range(K):
        best = max(sorted(cands), key=lambda i: len({n for n in left if i in units[n]}), default=None)
        cover = {n for n in left if best is not None and best in units[n]}
        if not cover:
            break
        gains.append(len(cover))
        left -= cover
    return gains


def score_question(got: list[str], got_urls: list[str], units: list[set[str]], rel_urls: set[str]) -> dict:
    """Métricas de uma pergunta. `units` = passagens do gold (cada uma satisfeita por qualquer id do conjunto)."""
    top, rel = got[:K], set().union(*units) if units else set()
    found = [any(i in u for i in top) for u in units]
    rr = next((1 / pos for pos, i in enumerate(top, 1) if i in rel), 0.0)
    gains, satisfied = [], set()
    for i in top:  # ganho = passagens do gold que o trecho cobre e ainda não estavam cobertas (cópia não pontua 2x)
        new = {n for n, u in enumerate(units) if i in u} - satisfied
        gains.append(len(new))
        satisfied |= new
    ideal = _dcg(_ideal_gains(units))
    pages = list(dict.fromkeys(got_urls))[:K]
    prr = next((1 / pos for pos, u in enumerate(pages, 1) if u in rel_urls), 0.0)
    top5 = got[:K_GEN]
    first = next((pos for pos, i in enumerate(got[:DEPTH], 1) if i in rel), None)
    return {"recall": sum(found) / len(units) if units else 0.0, "rr": rr, "hit": any(found),
            "recall5": sum(any(i in u for i in top5) for u in units) / len(units) if units else 0.0,
            "rr10": 1 / first if first else 0.0, "first": first,
            "ndcg": _dcg(gains) / ideal if ideal else 0.0,
            "page_recall": len(set(pages) & rel_urls) / len(rel_urls) if rel_urls else 0.0,
            "page_rr": prr, "page_hit": bool(set(pages) & rel_urls)}


GateHit = tuple[float, float | None, bool]  # (bm25, cosseno, é relevante)
# Limiar que desliga um caminho do portão (nenhum BM25 chega a 1e9; cosseno <= 1): número, não infinito, porque
# vai para data/retriever.json e o agents.covered_hits o usa como qualquer limiar.
BM25_OFF, COSINE_OFF = 1e9, 2.0


def _covers(hits: list[GateHit], t: float, c: float, margin: float) -> list[bool]:
    """Mesma regra de agents.covered_hits sobre tuplas: bm25 >= t OU cosseno >= max(c, melhor − margem)."""
    best = max((cos for _, cos, _ in hits if cos is not None), default=0.0)
    return [b >= t or (cos is not None and cos >= max(c, best - margin)) for b, cos, _ in hits]


def calibrate_gate(pos: list[list[GateHit]], neg: list[list[GateHit]]) -> dict | None:
    """Limiares (bm25, cosseno) do portão para ESTE retriever: mais positivos respondidos com a fonte certa entre os
    que recusam >= NEG_REFUSAL_MIN dos negativos; empate → mais recusa → limiares menores.

    O piso de cosseno do kit (0,4) foi medido com o MiniLM; com o e5-large todo trecho fica acima de 0,75 e o portão
    recusou 0 de 16 negativos num corpus real de FAQ. Por isso o par é calibrado junto com a escolha do retriever.
    """
    from app.agents import COSINE_MARGIN
    from evals.run_evals import NEG_REFUSAL_MIN, rate_ci

    if not pos or not neg:
        return None
    every = [h for q in pos + neg for h in q]
    ts = sorted({round(b, 3) for b, _, _ in every} | {BM25_OFF})
    cs = sorted({round(c, 3) for _, c, _ in every if c is not None} | {COSINE_OFF})
    best = None
    for c in cs:
        for t in ts:
            ok_pos = sum(any(cov and rel for cov, (_, _, rel) in zip(_covers(q, t, c, COSINE_MARGIN), q, strict=True))
                         for q in pos)
            ok_neg = sum(not any(_covers(q, t, c, COSINE_MARGIN)) for q in neg)
            a, b = ok_pos / len(pos), ok_neg / len(neg)
            key = (b >= NEG_REFUSAL_MIN - 1e-12, a, b, -t, -c)
            if best is None or key > best[0]:
                best = (key, {"min_score": t, "min_cosine": c, "pos_answered": round(a, 3),
                              "neg_refused": round(b, 3), "meets_floor": key[0], "pos_ci": rate_ci(ok_pos, len(pos)),
                              "neg_ci": rate_ci(ok_neg, len(neg))})
    out = best[1]
    return {**out, "positives": len(pos), "negatives": len(neg), "neg_refusal_min": NEG_REFUSAL_MIN}


def calibrate_rerank_gate(pos: list[float], neg: list[float]) -> dict | None:
    """Portão "sem fonte" pela nota do cross-encoder (o sinal que melhor separa com × sem fonte): o menor limiar que
    recusa >= NEG_REFUSAL_MIN das perguntas sem fonte, maximizando as com fonte respondidas (selective generation:
    cobertura máxima com piso de recusa). A nota do reranker não é probabilidade e muda com o modelo: recalibrar a cada
    troca de retriever. Pede >= 15 negativos para valer (`enough`)."""
    from evals.run_evals import NEG_REFUSAL_MIN, rate_ci

    if not pos or not neg:
        return None
    best = None
    for t in sorted(set(pos) | set(neg)):
        a = sum(x >= t for x in pos) / len(pos)
        b = sum(x < t for x in neg) / len(neg)
        key = (b >= NEG_REFUSAL_MIN - 1e-12, a, b, -t)
        if best is None or key > best[0]:
            best = (key, {"min_rerank": round(t, 4), "pos_answered": round(a, 3), "neg_refused": round(b, 3),
                          "meets_floor": key[0], "pos_ci": rate_ci(sum(x >= t for x in pos), len(pos)),
                          "neg_ci": rate_ci(sum(x < t for x in neg), len(neg))})
    return {**best[1], "positives": len(pos), "negatives": len(neg), "neg_refusal_min": NEG_REFUSAL_MIN,
            "enough": len(neg) >= 15}


def separation(pos: list[list[GateHit]], neg: list[list[GateHit]]) -> dict | None:
    """Quanto o sinal do portão separa perguntas COM fonte das SEM fonte ("gap" e AUC por embedder): melhor
    cosseno de cada pergunta; AUC = chance de uma pergunta com fonte superar uma sem fonte; gap = pior com fonte −
    melhor sem fonte (> 0 separa por completo).
    Sem cosseno (BM25 puro) usa o BM25. Pede >= 15 sem fonte para valer (`enough`)."""
    def best(hits: list[GateHit]) -> float:
        cos = [c for _, c, _ in hits if c is not None]
        return max(cos) if cos else max((b for b, _, _ in hits), default=0.0)

    p, n = [best(h) for h in pos if h], [best(h) for h in neg if h]
    if not p or not n:
        return None
    wins = sum((a > b) + 0.5 * (a == b) for a in p for b in n)
    return {"auc": round(wins / (len(p) * len(n)), 3), "gap": round(min(p) - max(n), 3),
            "positives": len(p), "negatives": len(n), "enough": len(n) >= 15}


def _by_origin(per_q: list[dict]) -> dict:
    """Recorte por origem da pergunta (campo `origin` do gold: page | official | real | ...). Sem o recorte,
    a média esconde o caso difícil: medido, a metade escrita a partir das páginas saturou (41/41) e toda a diferença
    veio das perguntas reais e oficiais (36/41)."""
    groups: dict[str, list[dict]] = {}
    for q in per_q:
        groups.setdefault(q.get("origin") or "sem_origem", []).append(q)
    return {o: {"cases": len(qs), f"recall@{K}": round(sum(q["recall"] for q in qs) / len(qs), 3),
                f"recall@{K_GEN}": round(sum(q["recall5"] for q in qs) / len(qs), 3),
                f"mrr@{DEPTH}": round(sum(q["rr10"] for q in qs) / len(qs), 3)} for o, qs in sorted(groups.items())}


def evaluate(path: Path, retriever, warmup: bool = True) -> dict:
    """Mede `retriever` nas perguntas positivas de `path` (família .jsonl + .d/) e calibra o portão de cobertura
    deste retriever com as negativas que o router manda ao agente de conhecimento (as outras só entram na conta)."""
    from app.rag import MEMO_READS

    token = MEMO_READS.set(False)  # latência de verdade: sem vetor de consulta nem score vindos do memo
    try:
        return _evaluate(path, retriever, warmup)
    finally:
        MEMO_READS.reset(token)


def _evaluate(path: Path, retriever, warmup: bool) -> dict:
    from app.jsonl import read_family
    from app.rag import Gold, get_index
    from evals.run_evals import rate_ci

    index = get_index()
    docs, known = index.docs, {d.id for d in index.docs}
    url_of = {d.id: d.url for d in docs}
    all_rows = read_family(path)
    rows = [(r, g) for r in all_rows if (g := Gold.from_row(r)).positive]
    if warmup and rows:
        retriever.search(_query(rows[0][0]["question"]), k=K)  # 1ª chamada ONNX aloca sessão: fora da latência
    per_q, unresolved, gate_pos, rerank_pos = [], [], [], []
    related_q: list[dict] = []  # gold com essenciais E "todo relacionado": o 2º medido à parte, nunca no lugar
    for r, gold in rows:
        units = gold.resolve_groups(docs, index.aliases)
        rel = set().union(*units) if units else set()
        rel_urls = {url_of[i] for i in rel if i in url_of}
        if not rel_urls or any(not (u & known) for u in units):
            unresolved.append(r["question"])
        t0 = time.perf_counter()
        hits = retriever.search(_query(r["question"]), k=DEPTH)
        ms = (time.perf_counter() - t0) * 1000
        got = [h.doc.id for h in hits]
        gate_pos.append([(h.bm25, h.cosine, h.doc.id in rel) for h in hits[:K]])
        rerank_pos.append(max((h.rerank for h in hits[:K_GEN] if h.rerank is not None), default=None))
        m = score_question(got, [h.doc.url for h in hits], units, rel_urls)
        per_q.append({"question": r["question"], "passages": len(units), "top3": got[:K], "latency_ms": round(ms, 1),
                      "origin": r.get("origin") or "sem_origem",
                      **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()}})
        if gold.passages and gold.related:
            all_units = gold.resolve_groups(docs, index.aliases, related=True)
            all_rel = set().union(*all_units) if all_units else set()
            related_q.append(score_question(got, [h.doc.url for h in hits], all_units,
                                            {url_of[i] for i in all_rel if i in url_of}))
    from evals.run_evals import _reaches_knowledge

    negatives = [r["question"] for r in all_rows if not Gold.from_row(r).positive]
    neg_hits = [retriever.search(_query(q), k=K_GEN) for q in negatives if _reaches_knowledge(q)]
    gate_neg = [[(h.bm25, h.cosine, False) for h in hits[:K]] for hits in neg_hits]
    rerank_neg = [max((h.rerank for h in hits if h.rerank is not None), default=None) for hits in neg_hits]
    n = len(per_q) or 1

    def mean(key: str) -> float:
        return round(sum(q[key] for q in per_q) / n, 3)

    lat = [q["latency_ms"] for q in per_q]
    hits_n, phits_n = sum(q["hit"] for q in per_q), sum(q["page_hit"] for q in per_q)
    return {"cases": len(per_q), "positives": len(per_q), "negatives": len(all_rows) - len(per_q),
            f"recall@{K}": mean("recall"), "mrr": mean("rr"), f"hit@{K}": mean("hit"),
            f"recall@{K_GEN}": mean("recall5"), f"mrr@{DEPTH}": mean("rr10"),
            "first_gold_rank": {q["question"]: q["first"] for q in per_q},
            "by_origin": _by_origin(per_q),
            f"hit@{K}_ci": rate_ci(hits_n, len(per_q)), f"ndcg@{K}": mean("ndcg"),
            "page": {f"recall@{K}": mean("page_recall"), "mrr": mean("page_rr"), f"hit@{K}": mean("page_hit"),
                     f"hit@{K}_ci": rate_ci(phits_n, len(per_q))},
            "latency_ms": {"p50": _pct(lat, 0.5), "p95": _pct(lat, 0.95),
                           "mean": round(statistics.fmean(lat), 1) if lat else None},
            "gate": calibrate_gate(gate_pos, gate_neg),
            "separation": separation(gate_pos, gate_neg),
            # com rerank, a nota do cross-encoder separa melhor que o cosseno (medido num gold real: AUC 0,84 × 0,78)
            "separation_rerank": separation([[(0.0, x, True)] for x in rerank_pos if x is not None],
                                            [[(0.0, x, False)] for x in rerank_neg if x is not None]),
            "rerank_gate": calibrate_rerank_gate([x for x in rerank_pos if x is not None],
                                                 [x for x in rerank_neg if x is not None]),
            "essential": sum(1 for _, g in rows if g.passages),
            **({"related": {"cases": len(related_q),
                            f"recall@{K}": round(sum(q["recall"] for q in related_q) / len(related_q), 3),
                            "mrr": round(sum(q["rr"] for q in related_q) / len(related_q), 3)}} if related_q else {}),
            "gold_unresolved": unresolved, "dedupe_aliases": len(index.aliases),
            "retriever": retriever.name, "fallback": getattr(retriever, "fallback", ""), "questions": per_q}


# --- configurações -------------------------------------------------------------------------------------------
def default_configs(embed_models: list[str], rerank_models: list[str],
                    pool: int | list[int] | None = None) -> list[dict]:
    """bm25, hybrid e dense por modelo de embedding, e cada um deles + cross-encoder por modelo de rerank e por
    tamanho do pool (o custo do cross-encoder é linear no pool: pool menor cabe no orçamento de latência)."""
    pools = pool if isinstance(pool, list) else [pool or 20]
    bases = [{"retriever": "bm25"}]
    bases += [{"retriever": r, "embed_model": m} for m in embed_models for r in ("hybrid", "dense")]
    out = list(bases)
    out += [{**b, "rerank": "cross", "rerank_model": rm, "rerank_pool": p} for b in bases
            for rm in rerank_models for p in pools]
    return out


# --choose-retriever --fast: só as configurações que venceram a grade completa (21 configurações; o denso e5-large
# bateu o híbrido e o MiniLM, e o bge-m3-int8 o jina com o mesmo pool), mais o bm25 de base. Medidas abaixo numa
# máquina compartilhada (load 2–7,6). A grade inteira não cabe em 10 min; estas 3 medem em minutos (o tempo maior é
# vetorizar o corpus com o e5-large, uma vez; o cache em var/embeddings serve depois a API e o eval).
FAST_EMBED = "intfloat/multilingual-e5-large"
FAST_CROSS = "BAAI/bge-reranker-v2-m3-int8"
FAST_CONFIGS = (
    {"retriever": "bm25"},
    {"retriever": "dense", "embed_model": FAST_EMBED},
    # pool 10 lendo 600 caracteres por trecho: Recall@3 0,754 / MRR 0,947 / p95 1130 ms, contra
    # 0,734 / 0,937 / 896 ms do pool 5 com 1500 caracteres; pool 20 subiu a 0,777 com p95 de 4,7 s (fora do teto)
    {"retriever": "dense", "embed_model": FAST_EMBED, "rerank": "cross", "rerank_model": FAST_CROSS, "rerank_pool": 10,
     "rerank_chars": 600},
)


def config_name(cfg: dict, verbose: bool = False) -> str:
    """"hybrid+cross"; com `verbose` (mais de um modelo no comparativo), com os modelos: "dense[e5]+cross[jina@20]"."""
    name = cfg["retriever"]
    if verbose and cfg.get("embed_model"):
        name += f"[{cfg['embed_model'].split('/')[-1]}]"
    if cfg.get("rerank"):
        name += f"+{cfg['rerank']}"
        if verbose and cfg.get("rerank_model"):
            chars = f"/{cfg['rerank_chars']}c" if cfg.get("rerank_chars") else ""
            name += f"[{cfg['rerank_model'].split('/')[-1]}@{cfg.get('rerank_pool', 20)}{chars}]"
    return name


def _make(given, model: str, default, method: str):
    """`given` pode ser uma instância (usada para todo modelo), uma fábrica `f(model)` ou None (o padrão real)."""
    if given is None:
        return default(model)
    return given if hasattr(given, method) and not isinstance(given, type) else given(model)


def rss_mb() -> float | None:
    """RAM residente deste processo agora (Linux: /proc/self/status). Sem /proc (Windows, macOS): None."""
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        pass
    return None


class _Factories:
    """Um embedder/cross-encoder por modelo (carregar o e5-large 2x custaria minutos); injetável nos testes.

    `model_mb`: RAM que cada modelo somou ao processo ao carregar (RSS depois − antes); `base_mb`: o processo antes do
    1º modelo (app, índice BM25). RAM de uma configuração = base + os modelos dela: estimativa do processo que a
    serve (medido: 2359 MB estimados para e5-large + bge-m3-int8; pico medido do processo, 2909 MB, com os
    vetores do corpus e o eval). `rss` é injetável (testes)."""

    def __init__(self, embedder=None, scorer=None, rerank_llm=None, rss=rss_mb) -> None:
        self._embedders: dict[str, object] = {}
        self._scorers: dict[str, object] = {}
        self.embedder, self.scorer, self.rerank_llm = embedder, scorer, rerank_llm
        self.rss = rss
        self.base_mb: float | None = None  # processo com app e índice carregados, antes do 1º modelo
        self.model_mb: dict[str, float | None] = {}
        from app.rag import _cross_for, _embedder_for

        # processo que já carregou modelo (o app aquecido do `make eval`): o RSS de hoje não separa o que é de cada
        # configuração, então a RAM não é medida (None) em vez de sair errada
        self.preloaded = bool(_embedder_for.cache_info().currsize or _cross_for.cache_info().currsize)

    def _load(self, model: str, factory):
        before = self.rss()
        if not self.model_mb:
            self.base_mb = before
        obj = factory()
        after = self.rss()
        self.model_mb[model] = round(after - before, 1) if before is not None and after is not None else None
        return obj

    def _shared(self, model: str, cached, kind: str):
        """O modelo do PROCESSO (rag._embedder_for / _cross_for), não uma 2ª cópia. Sem isto, `make eval` com o
        app já aquecido carregava e5-large + bge-m3-int8 duas vezes e o processo chegou a 4951 MB. Se o modelo já
        estava carregado, a RAM dele não é medida aqui (None): o delta seria zero e mentiria na escolha."""
        misses = cached.cache_info().misses
        before = self.rss()
        if not self.model_mb:
            self.base_mb = before
        obj = cached(model)
        if obj is None:
            from app.rag import _FALLBACKS

            raise RuntimeError(f"{kind} {model} indisponível: {_FALLBACKS.get(('cross', model), '?')}")
        after = self.rss()
        fresh = cached.cache_info().misses > misses  # carregou agora (não veio do cache do processo)
        self.model_mb[model] = round(after - before, 1) if fresh and before is not None and after is not None else None
        return obj

    def embed(self, model: str):
        if model not in self._embedders:
            if self.embedder is None:
                from app.rag import _embedder_for

                self._embedders[model] = self._shared(model, _embedder_for, "embedding")
            else:
                self._embedders[model] = self._load(model, lambda: _make(self.embedder, model, None, "embed"))
        return self._embedders[model]

    def cross(self, model: str):
        if model not in self._scorers:
            if self.scorer is None:
                from app.rag import _cross_for

                self._scorers[model] = self._shared(model, _cross_for, "cross-encoder")
            else:
                self._scorers[model] = self._load(model, lambda: _make(self.scorer, model, None, "score"))
        return self._scorers[model]

    def memory_mb(self, cfg: dict) -> float | None:
        """RAM estimada de um processo que serve `cfg`: o processo sem modelo + o que cada modelo dele somou."""
        models = [m for m in (cfg.get("embed_model"), cfg.get("rerank_model") if cfg.get("rerank") == "cross" else None)
                  if m]
        if self.preloaded:
            return None
        parts = [self.model_mb.get(m) for m in models]
        base = self.base_mb if self.model_mb else self.rss()  # sem modelo carregado ainda: o processo agora
        if base is None or any(v is None for v in parts):
            return None
        return round(base + sum(parts), 1)


def build(cfg: dict, fx: _Factories):
    from app.rag import BM25Retriever, CrossRerankRetriever, HybridRetriever, RerankRetriever, get_index

    base = BM25Retriever(get_index())
    if cfg["retriever"] in ("hybrid", "dense"):
        base = HybridRetriever(get_index(), fx.embed(cfg["embed_model"]),
                               "dense" if cfg["retriever"] == "dense" else "rrf")
    if cfg.get("rerank") == "cross":
        return CrossRerankRetriever(base, fx.cross(cfg["rerank_model"]), cfg.get("rerank_pool"),
                                    cfg.get("rerank_chars"))
    if cfg.get("rerank") == "llm":
        if fx.rerank_llm is None:
            raise RuntimeError("rerank llm só com --rerank (chama o LLM)")
        return RerankRetriever(base, llm=fx.rerank_llm)
    return base


def per_question_diff(results: dict[str, dict], baseline: str = BASELINE) -> dict:
    """Para cada configuração: perguntas que melhoraram/pioraram contra o baseline (recall@3, depois MRR)."""
    base = results.get(baseline) or {}
    bq = {q["question"]: q for q in base.get("questions", [])}
    out = {}
    for name, res in results.items():
        if name == baseline or "questions" not in res:
            continue
        better, worse = [], []
        for q in res["questions"]:
            b = bq.get(q["question"])
            if not b:
                continue
            delta = (round(q["recall"] - b["recall"], 3), round(q["rr"] - b["rr"], 3))
            row = {"question": q["question"], "recall": [b["recall"], q["recall"]], "rr": [b["rr"], q["rr"]]}
            if delta > (0, 0):
                better.append(row)
            elif delta < (0, 0):
                worse.append(row)
        out[name] = {"improved": better, "regressed": worse, "same": len(res["questions"]) - len(better) - len(worse)}
    return out


def compare(path: Path, configs: list[dict], embedder=None, scorer=None, rerank_llm=None,
            out: Path | None = None, rss=rss_mb) -> dict:
    """Mede cada configuração no mesmo gold. Indisponível (sem fastembed, sem modelo) vira linha com o motivo."""
    fx = _Factories(embedder, scorer, rerank_llm, rss)
    results: dict[str, dict] = {}
    models = {(c.get("embed_model"), c.get("rerank_model"), c.get("rerank_pool"), c.get("rerank_chars"))
              for c in configs}
    verbose = any(len({m[i] for m in models if m[i]}) > 1 for i in range(4))
    for cfg in configs:
        name = config_name(cfg, verbose)
        try:
            res = evaluate(path, build(cfg, fx))
            res["memory_mb"] = fx.memory_mb(cfg)
        except Exception as exc:  # noqa: BLE001 — import/download/modelo: registra o motivo, não derruba o comparativo
            res = {"status": "unavailable", "reason": f"{type(exc).__name__}: {exc}"[:200]}
        res["config"] = cfg
        results[name] = res
    report = {"recorded_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
              "gold": str(path.name), "k": K, "results": results, "diff_vs_baseline": per_question_diff(results)}
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def choose(results: dict[str, dict], budget_ms: float = LATENCY_BUDGET_MS,
           ram_budget_mb: float | None = RAM_BUDGET_MB) -> dict:
    """Maior MRR entre as configurações com p95 <= orçamento de latência, RAM <= orçamento de memória e portão que
    recusa >= NEG_REFUSAL_MIN das perguntas sem fonte (calibrado por configuração); empate → maior Recall@3 → menor
    p95 → mais simples. RAM não medida (sem /proc) não reprova; `ram_budget_mb` None desliga o teto.

    Nenhuma dentro do orçamento → bm25 (sem dependência e sem modelo). Devolve {name, config, reason, rejected}.
    """
    ok, rejected = [], {}
    for name, res in results.items():
        if res.get("status") == "unavailable":
            rejected[name] = res["reason"]
            continue
        p95 = (res.get("latency_ms") or {}).get("p95") or 0.0
        gate = res.get("gate")
        if gate is not None and not gate.get("meets_floor"):
            rejected[name] = (f"portão não recusa {gate['neg_refusal_min']:.0%} dos sem fonte em nenhum limiar "
                              f"(máx. {gate['neg_refused']:.0%})")
            continue
        if p95 > budget_ms:
            rejected[name] = f"p95 {p95} ms > orçamento {budget_ms:g} ms"
            continue
        mem = res.get("memory_mb")
        if ram_budget_mb is not None and mem is not None and mem > ram_budget_mb:
            rejected[name] = f"RAM {mem:g} MB > orçamento {ram_budget_mb:g} MB"
            continue
        ok.append((name, res))
    if not ok:
        return {"name": BASELINE, "config": {"retriever": "bm25"}, "reason": "nenhuma dentro do orçamento",
                "rejected": rejected}
    name, res = max(ok, key=lambda x: (x[1]["mrr"], x[1][f"recall@{K}"], -(x[1]["latency_ms"]["p95"] or 0),
                                       -len(x[0])))
    gate = res.get("gate") or {}
    off = {"min_score": BM25_OFF, "min_cosine": COSINE_OFF}  # null de um comparativo antigo = caminho desligado
    config = {**res["config"], "gate": {k: off[k] if gate[k] is None else gate[k] for k in off if k in gate}}
    if not config["gate"]:
        config.pop("gate")
    ram = f" e RAM <= {ram_budget_mb:g} MB" if ram_budget_mb is not None else ""
    return {"name": name, "config": config, "rejected": rejected,
            "reason": f"maior MRR com p95 <= {budget_ms:g} ms{ram} (empate: Recall@3, depois p95)"}


def summary(res: dict) -> dict:
    """Linha enxuta de uma configuração (sem as perguntas): o que vai para data/retriever.json e o README."""
    keys = ("cases", f"recall@{K}", "mrr", f"hit@{K}", f"hit@{K}_ci", f"ndcg@{K}", "page", "latency_ms",
            "memory_mb", "dedupe_aliases", "fallback", "config", "gate")
    return {k: res[k] for k in keys if k in res} if res.get("status") != "unavailable" else dict(res)


def apply_choice(report: dict, picked: dict, target: Path, budget_ms: float, git_sha: str | None,
                 ram_budget_mb: float | None = RAM_BUDGET_MB) -> Path:
    """Grava a escolha e a tabela que a justifica. O app lê `choice` (config.retriever_choice); env vence."""
    payload = {"_doc": "gerado por `python -m evals.run_evals --choose-retriever --apply`; não edite à mão",
               "chosen_at": report["recorded_at"], "git_sha": git_sha, "gold": report["gold"],
               "criterion": picked["reason"], "latency_budget_ms": budget_ms, "ram_budget_mb": ram_budget_mb,
               "chosen": picked["name"],
               "choice": picked["config"], "rejected": picked["rejected"],
               "measured": {n: summary(r) for n, r in report["results"].items()}}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def markdown(measured: dict[str, dict], chosen: str | None = None) -> str:
    """Tabela das configurações medidas (README e saída do CLI)."""
    lines = ["| configuração | Recall@3 | MRR | hit@3 | nDCG@3 | URL hit@3 | p50 ms | p95 ms | RAM MB |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, r in measured.items():
        if r.get("status") == "unavailable":
            lines.append(f"| {name} | indisponível: {r['reason'][:80]} | | | | | | | |")
            continue
        lat = r.get("latency_ms") or {}
        mark = " **← escolhida**" if name == chosen else ""
        mem = r.get("memory_mb")
        lines.append(f"| {name}{mark} | {r[f'recall@{K}']} | {r['mrr']} | {r[f'hit@{K}']} | {r.get(f'ndcg@{K}', '—')} "
                     f"| {r['page'][f'hit@{K}']} | {lat.get('p50', '—')} | {lat.get('p95', '—')} "
                     f"| {'—' if mem is None else mem} |")
    return "\n".join(lines)


def load_choice(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def recorded_models(recorded: dict) -> tuple[list[str], list[str]]:
    """Modelos de embedding e de rerank que a escolha gravada mediu (para o --verify refazer a mesma grade)."""
    cfgs = [(r or {}).get("config") or {} for r in (recorded.get("measured") or {}).values()]
    embeds = list(dict.fromkeys(c["embed_model"] for c in cfgs if c.get("embed_model")))
    crosses = list(dict.fromkeys(c["rerank_model"] for c in cfgs if c.get("rerank_model")))
    return embeds, crosses


def pools_of(recorded: dict) -> list[int]:
    cfgs = [(r or {}).get("config") or {} for r in (recorded.get("measured") or {}).values()]
    return list(dict.fromkeys(c["rerank_pool"] for c in cfgs if c.get("rerank_pool")))


VERIFY_TOL = 0.01  # MRR medido de novo pode variar no 3º decimal entre CPUs (ONNX); mais que isso é deriva


def verify(recorded: dict, results: dict[str, dict]) -> list[str]:
    """Divergências de qualidade entre a escolha gravada (fonte do README) e a mesma configuração medida agora.

    Mede só a escolhida e o bm25 (a grade inteira leva quase 1 h em CPU); latência não entra: a máquina do CI não é
    a da escolha. Sem arquivo gravado: nada a conferir.
    """
    if not recorded:
        return []
    chosen = recorded.get("chosen")
    problems = []
    for name in dict.fromkeys([chosen, BASELINE]):
        old, new = (recorded.get("measured") or {}).get(name, {}), results.get(name, {})
        if new.get("status") == "unavailable":
            problems.append(f"{name} indisponível agora: {new.get('reason')}")
        for key in ("mrr", f"recall@{K}"):
            if key in old and key in new and abs(old[key] - new[key]) > VERIFY_TOL:
                problems.append(f"{key} de {name}: gravado {old[key]} × medido {new[key]}")
    return problems


def verify_configs(recorded: dict) -> dict[str, dict]:
    """{nome gravado: configuração} da escolhida e do bm25, sem os limiares do portão (não são parte da busca)."""
    measured = recorded.get("measured") or {}
    out = {}
    for name in dict.fromkeys([recorded.get("chosen"), BASELINE]):
        cfg = dict((measured.get(name) or {}).get("config") or ({"retriever": "bm25"} if name == BASELINE else {}))
        cfg.pop("gate", None)
        if cfg:
            out[name] = cfg
    return out


def choose_cli(args, gold: Path, results_dir: Path, sha: str | None) -> int:
    """--choose-retriever: comparativo completo (retrieval_compare.json) → escolha → (--apply) data/retriever.json."""
    from app.config import data_dir, embed_model, rerank_model

    def split(value: str | None, default: str) -> list[str]:
        return [v.strip() for v in (value or default).split(",") if v.strip()]

    recorded = load_choice(data_dir() / "retriever.json")
    if getattr(args, "verify", False):
        if not recorded:
            print("VERIFY: sem data/retriever.json, nada a conferir")
            return 0
        named = verify_configs(recorded)
        rep = compare(args.gold or gold, list(named.values()), out=results_dir / "retrieval_verify.json")
        by_cfg = {json.dumps(r.get("config"), sort_keys=True): r for r in rep["results"].values()}
        results = {n: by_cfg.get(json.dumps(c, sort_keys=True), {}) for n, c in named.items()}
        problems = verify(recorded, results)
        for n, r in results.items():
            print(f"- {n}: MRR {r.get('mrr')} (gravado {recorded['measured'].get(n, {}).get('mrr')}), "
                  f"Recall@3 {r.get(f'recall@{K}')} (gravado {recorded['measured'].get(n, {}).get(f'recall@{K}')})")
        print("VERIFY " + ("OK" if not problems else "FALHOU: " + "; ".join(problems)))
        return 1 if problems else 0
    budget = args.latency_budget_ms if args.latency_budget_ms is not None else (
        recorded.get("latency_budget_ms") or LATENCY_BUDGET_MS)
    ram_arg = getattr(args, "ram_budget_mb", None)
    ram_budget = ram_arg if ram_arg is not None else (recorded.get("ram_budget_mb") or RAM_BUDGET_MB)
    ram_budget = None if ram_budget <= 0 else ram_budget  # 0 = sem teto de RAM
    if getattr(args, "fast", False):
        configs = [dict(c) for c in FAST_CONFIGS]  # 3 configurações: cabe no relógio (a grade leva quase 1 h)
    else:
        embeds, crosses = recorded_models(recorded)  # --verify refaz as MESMAS configurações que a escolha gravada
        pools = [int(p) for p in split(getattr(args, "rerank_pools", None),
                                       ",".join(map(str, pools_of(recorded))) or "20")]
        configs = default_configs(split(args.embed_models, ",".join(embeds) or embed_model()),
                                  split(args.rerank_models, ",".join(crosses) or rerank_model()), pools)
    saved = results_dir / "retrieval_compare.json"
    report = load_choice(saved) if getattr(args, "reuse", False) else {}
    if not report or {config_name(c, True) for c in configs} - {config_name(r.get("config", {}), True)
                                                                for r in report.get("results", {}).values()}:
        report = compare(args.gold or gold, configs, out=saved)  # sem --reuse (ou faltando configuração): mede
    else:
        print(f"--reuse: escolha refeita sobre {saved} (medido em {report['recorded_at']}), sem medir de novo")
    picked = choose(report["results"], budget, ram_budget)
    print(markdown({n: summary(r) for n, r in report["results"].items()}, picked["name"]))
    print(f"\nEscolhida: {picked['name']} ({picked['reason']}). Rejeitadas: {picked['rejected'] or '—'}")
    for name, d in report["diff_vs_baseline"].items():
        print(f"- {name} × bm25: melhoraram {len(d['improved'])}, pioraram {len(d['regressed'])}, iguais {d['same']}")
    print(f"Por pergunta: {results_dir / 'retrieval_compare.json'}")
    if args.apply:
        target = apply_choice(report, picked, data_dir() / "retriever.json", budget, sha, ram_budget)
        print(f"Escolha gravada em {target} (o app lê como padrão; RETRIEVER/RERANK no ambiente vencem)")
    return 0
