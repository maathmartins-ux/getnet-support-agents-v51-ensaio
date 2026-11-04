"""Frente R12-D: janelas no índice denso (small-to-big / MaxP), sem modelo de verdade.

Defeito medido no ensaio (rodada 11): o trecho prod-taxas-02 junta a tabela de taxas do Get Tap e o cartão de
recursos da Get Clássica; o vetor do trecho inteiro puxa para a tabela e ele ficava em 12º–18º para "Get Clássica
recursos", fora dos 10 que o cross-encoder lê. Com janelas, a nota densa do trecho é a melhor entre ele e as janelas
dele; o redator continua recebendo o trecho inteiro e o cross-encoder lê a partir da janela que casou.
"""
import json

from fakes import ConceptEmbedder

from app import config, rag
from app.rag import CrossRerankRetriever, Doc, Hit, HybridRetriever, Index, cross_text, window_spans
from evals import retrieval_eval as rv

ENTREGA = ["O prazo de entrega para as capitais é de 3 a 5 dias úteis, contados da confirmação do pagamento.",
           "Para o interior do estado, o prazo de entrega fica entre 5 e 8 dias úteis após a postagem.",
           "A entrega expressa chega em até 2 dias úteis nas capitais; o prazo conta a partir do envio."]
TROCA = ["Troca e devolução: você pode pedir o reembolso em até 7 dias corridos após receber.",
         "O estorno do reembolso aparece na fatura seguinte do cartão usado na compra original.",
         "Para a troca, o produto deve estar sem uso e na embalagem original, com a nota fiscal."]
MISTO = Doc("misto", "Entregas e trocas", "https://example.com/misto", "\n".join(ENTREGA + TROCA))
# trecho curto (uma linha: nunca ganha janela) que, inteiro, casa melhor com "troca" que o misto inteiro
POLITICA = Doc("politica", "Política de troca", "https://example.com/politica",
               "Política de troca e devolução: o suporte orienta o envio.")
QUERY = "Quero troca ou reembolso"


def _dense(windows: bool) -> HybridRetriever:
    return HybridRetriever(Index([MISTO, POLITICA]), ConceptEmbedder(), "dense", windows=windows)


class RecordingScorer:
    """Cross-encoder falso: guarda o texto lido e dá nota = quantas vezes "reembolso" aparece nele (a palavra só
    existe na parte das trocas: nem no cabeçalho nem na parte da entrega)."""

    name = "recording"

    def __init__(self, model=None):
        self.read: list[str] = []

    def score(self, query, texts):
        self.read += texts
        return [float(t.lower().count("reembolso")) for t in texts]


# --- janelas ---------------------------------------------------------------------------------------------------
def test_windows_are_whole_lines_never_shorter_than_the_size_and_the_last_reaches_the_end():
    text = MISTO.text
    spans = window_spans(text)
    assert len(spans) >= 2
    for a, b in spans:
        assert b - a >= rag.WINDOW_CHARS  # nenhuma janela curta (a sobra do fim não vira janela sozinha)
        assert a == 0 or text[a - 1] == "\n"
        assert b == len(text) or text[b] == "\n"
        assert (a, b) != (0, len(text))  # janela igual ao trecho não entra: ele já está embutido
    assert spans[-1][1] == len(text)
    pairs = list(zip(spans, spans[1:], strict=False))
    assert all(a1 < a2 <= b1 for (a1, b1), (a2, _) in pairs)  # cada uma avança e se sobrepõe à anterior
    assert text[spans[-1][0]:] == "\n".join(TROCA)  # a do fim: só a parte das trocas


def test_short_or_single_line_chunks_get_no_window():
    assert window_spans(POLITICA.text) == []
    assert window_spans("x" * 700) == []  # uma linha só: a janela seria o trecho inteiro
    # sobra curta no fim ("Respondeu à sua dúvida?", 23 caracteres no ensaio) entra junto da linha anterior
    text = "a" * 300 + "\n" + "Respondeu à sua dúvida?"
    assert all(b - a >= rag.WINDOW_CHARS for a, b in window_spans(text))


# --- a janela que casa sobe o trecho -----------------------------------------------------------------------------
def test_a_matching_window_lifts_the_mixed_chunk_to_the_top():
    before = _dense(False).search(QUERY, k=2)
    assert [h.doc.id for h in before] == ["politica", "misto"]  # o vetor do misto inteiro puxa para a entrega
    after = _dense(True).search(QUERY, k=2)
    assert [h.doc.id for h in after] == ["misto", "politica"]
    top = after[0]
    assert top.window is not None and MISTO.text[top.window[0]:top.window[1]] == "\n".join(TROCA)
    assert top.cosine > before[1].cosine  # a nota densa do trecho é a da janela vencedora
    assert after[1].window is None  # trecho sem janela: a nota é a dele


def test_ids_texts_and_citations_stay_those_of_the_whole_chunk():
    from app.agents import _listing

    hits = _dense(True).search(QUERY, k=2)
    assert hits[0].doc is MISTO  # o mesmo trecho do índice (id, título, URL e texto inteiro)
    listing = _listing(hits)
    assert "[1] Entregas e trocas (https://example.com/misto):" in listing
    assert ENTREGA[0] in listing and TROCA[-1] in listing  # o redator lê o trecho inteiro, não a janela
    assert "#" not in "".join(h.doc.id for h in hits)  # nenhum id de janela vaza para fonte ou citação


def test_windows_off_is_the_search_of_before():
    r = _dense(False)
    assert r.name == "dense" and r._spans == [] and all(h.window is None for h in r.search(QUERY, k=2))
    assert _dense(True).name == "dense+windows"


def test_numpy_and_python_window_scores_rank_the_same():
    r = _dense(True)
    with_np = [(h.doc.id, h.window) for h in r.search(QUERY, k=2)]
    bias_np = dict(r._wbias)
    r._matrix = r._wmatrix = None
    assert [(h.doc.id, h.window) for h in r.search(QUERY, k=2)] == with_np
    assert {n: round(v, 9) for n, v in r._window_bias().items()} == {n: round(v, 9) for n, v in bias_np.items()}


# --- a janela só conta quando se destaca: ganho típico do trecho descontado, fatia de cima da consulta ------------
def test_a_chunk_whose_windows_always_gain_is_not_lifted():
    """Ganho típico do trecho (medido com os outros trechos como sondas) sai do ganho da janela: trecho cuja janela
    ganha para qualquer consulta não sobe (no ensaio, sup-antecipacao-04 ganhava ~0,025 até para "Get Clássica")."""
    r = _dense(True)
    assert set(r._wbias) == {0}  # só o misto tem janela; a política (uma linha) não
    r._wbias = {0: 10.0}  # típico enorme: nenhum ganho desta consulta passa dele
    assert [h.doc.id for h in r.search(QUERY, k=2)] == ["politica", "misto"]
    r._wbias = {0: 0.0}
    assert [h.doc.id for h in r.search(QUERY, k=2)] == ["misto", "politica"]


def _many(n: int) -> HybridRetriever:
    docs = [Doc(f"d{i:02d}", f"Item {i}", f"https://example.com/{i}", "\n".join([f"linha {j} " + "x" * 100
                                                                              for j in range(4)])) for i in range(n)]
    r = HybridRetriever(Index(docs), ConceptEmbedder(), "dense", windows=True)
    r._wbias = {d: 0.0 for d, _, _ in r._spans}
    return r


def test_only_the_top_slice_of_window_gains_counts():
    n = 100 // (100 - rag.WINDOW_GAIN_PCT) + 4  # trechos com janela de sobra para a fatia de cima ter um trecho
    r = _many(n)
    cos = [0.5] * n
    gain = {d: (0.05 if d == 7 else 0.01) for d in range(n)}
    first = {}
    for w, (d, _, _) in enumerate(r._spans):
        first.setdefault(d, w)
    values = [cos[d] + gain[d] if first[d] == w else 0.0 for w, (d, _, _) in enumerate(r._spans)]
    r._window_cosines = lambda qv: values
    best, won = r._best_windows([1.0, 0.0, 0.0], cos)
    assert [d for d, span in enumerate(won) if span] == [7]  # os outros ganhos são iguais: o corte fica neles
    assert best[7] == 0.55 and best[0] == 0.5
    small = _many(5)  # poucos trechos com janela: não há fatia de cima, vale ganho descontado > 0
    small._window_cosines = lambda qv: [0.51] * len(small._spans)
    assert all(small._best_windows([1.0, 0.0, 0.0], [0.5] * 5)[1])


def test_percentile_is_numpy_linear():
    import numpy as np

    values = [0.3, -0.1, 0.07, 0.2, 0.011, 0.5, 0.0]
    for pct in (0, 10, 50, 90, 95, 100):
        assert abs(rag._percentile(values, pct) - float(np.percentile(values, pct))) < 1e-12


def test_window_bias_probes_are_capped(monkeypatch):
    monkeypatch.setattr(rag, "WINDOW_PROBES", 3)
    r = _many(12)
    assert set(r._window_bias()) == {d for d, _, _ in r._spans}  # 3 sondas bastam para o cálculo, sem erro


# --- o cross-encoder do portão lê a janela -----------------------------------------------------------------------
def test_the_gate_cross_encoder_reads_from_the_matching_window():
    head = f"{MISTO.head}. "
    for windows in (False, True):
        scorer = RecordingScorer()
        hits = CrossRerankRetriever(_dense(windows), scorer, pool=5, chars=300, order="base").search(QUERY, k=2)
        read = next(t for t in scorer.read if t.startswith(head))
        misto = next(h for h in hits if h.doc.id == "misto")
        if windows:
            assert read.startswith(head + TROCA[0]) and ENTREGA[0] not in read
            assert misto.rerank == 2  # a nota mede a parte que casou
        else:
            assert read == (head + MISTO.text)[:300]  # sem janela: os primeiros caracteres, como antes
            assert misto.rerank == 0


def test_cross_text_falls_back_to_the_old_cut_and_fills_the_budget_at_the_end():
    hit = Hit(MISTO, 1.0)
    assert cross_text(hit, 300) == f"{MISTO.head}. {MISTO.text}"[:300]
    assert cross_text(Hit(MISTO, 1.0, window=(0, 10)), 2000) == f"{MISTO.head}. {MISTO.text}"  # cabe inteiro
    start = MISTO.text.index(TROCA[-1])  # janela na última linha: recua por linhas inteiras até encher o corte
    text = cross_text(Hit(MISTO, 1.0, window=(start, len(MISTO.text))), 300)
    assert text.endswith(TROCA[-1]) and len(text) <= 300
    assert text[len(f"{MISTO.head}. "):] in {MISTO.text[s:] for s in (MISTO.text.index(t) for t in ENTREGA + TROCA)}


# --- cache e RAM -------------------------------------------------------------------------------------------------
class CountingEmbedder(ConceptEmbedder):
    name = "counting/windows"
    cacheable = True

    def __init__(self):
        self.texts = 0

    def embed(self, texts):
        self.texts += len(texts)
        return super().embed(texts)


def test_window_vectors_are_cached_on_disk_by_text(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path / "emb"))
    e = CountingEmbedder()
    HybridRetriever(Index([MISTO, POLITICA]), e, "dense", windows=False)
    assert e.texts == 2
    r = HybridRetriever(Index([MISTO, POLITICA]), e, "dense", windows=True)
    assert e.texts == 2 + len(r._spans)  # só as janelas foram ao modelo (os trechos vieram do disco)
    HybridRetriever(Index([MISTO, POLITICA]), e, "dense", windows=True)
    assert e.texts == 2 + len(r._spans)  # 2ª montagem: tudo do disco
    assert not hasattr(r, "_wvectors") and len(r._wunits) == len(r._spans)  # vetor cru da janela não fica na RAM


# --- configuração: escolha gravada, ambiente, portão -------------------------------------------------------------
def _choice(tmp_path, monkeypatch, choice: dict | None):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    (data / "sample.jsonl").write_text(json.dumps(POLITICA.__dict__, ensure_ascii=False) + "\n", encoding="utf-8")
    if choice is not None:
        (data / "retriever.json").write_text(json.dumps({"choice": choice}), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(data))
    for k in ("RETRIEVER", "RERANK", "RERANK_ORDER", "RERANK_POOL", "RERANK_CHARS", "EMBED_MODEL", "RERANK_MODEL",
              "RAG_WINDOWS"):
        monkeypatch.delenv(k, raising=False)


DENSE = {"retriever": "dense", "embed_model": "intfloat/multilingual-e5-large", "rerank": "cross",
         "rerank_model": "BAAI/bge-reranker-v2-m3-int8", "rerank_pool": 10, "rerank_chars": 600,
         "rerank_order": "base"}


def test_a_recorded_choice_without_the_key_keeps_the_search_it_measured(tmp_path, monkeypatch):
    _choice(tmp_path, monkeypatch, {**DENSE, "gate": {"min_rerank": -4.9}})
    assert config.rag_windows() is False  # medida sem janelas: o README e o --verify descrevem essa busca
    assert config.choice_gate() == {"min_rerank": -4.9}
    monkeypatch.setenv("RAG_WINDOWS", "on")  # o ambiente liga: o limiar medido sem janelas não vale
    assert config.rag_windows() is True and config.choice_gate() == {}


def test_a_choice_with_windows_carries_its_gate_only_with_windows(tmp_path, monkeypatch):
    _choice(tmp_path, monkeypatch, {**DENSE, "windows": True, "gate": {"min_rerank": -4.2}})
    assert config.rag_windows() is True and config.choice_gate() == {"min_rerank": -4.2}
    monkeypatch.setenv("RAG_WINDOWS", "off")
    assert config.rag_windows() is False and config.choice_gate() == {}


def test_without_a_choice_the_kit_default_decides(tmp_path, monkeypatch):
    _choice(tmp_path, monkeypatch, None)
    assert config.rag_windows() is bool(config.KIT_RETRIEVER.get("windows"))
    monkeypatch.setenv("RAG_WINDOWS", "1")
    assert config.rag_windows() is True


def test_app_retriever_follows_the_switch_without_a_stale_cache(tmp_path, monkeypatch):
    _choice(tmp_path, monkeypatch, None)
    monkeypatch.setattr(rag, "_embedder_for", lambda model: ConceptEmbedder())
    rag._hybrid_for.cache_clear()
    try:
        monkeypatch.setenv("RAG_WINDOWS", "on")
        assert rag.get_retriever("dense", rerank=False).name == "dense+windows"
        monkeypatch.setenv("RAG_WINDOWS", "off")
        assert rag.get_retriever("dense", rerank=False).name == "dense"  # outra chave no cache: não reaproveita
    finally:
        rag._hybrid_for.cache_clear()


# --- eval: a janela é parte da configuração medida -----------------------------------------------------------------
def test_fast_choice_measures_the_kit_package_and_windows_flag_measures_both(monkeypatch):
    from evals import run_evals

    seen: list[list[dict]] = []

    def fake_compare(path, configs, **kwargs):
        seen.append([dict(c) for c in configs])
        return {"recorded_at": "agora", "gold": "g", "diff_vs_baseline": {},
                "results": {rv.config_name(c): {"status": "unavailable", "reason": "teste", "config": c}
                            for c in configs}}

    monkeypatch.setattr(rv, "compare", fake_compare)
    assert run_evals.main(["--choose-retriever", "--fast"]) == 0
    # o --fast (as 2 com cross de sempre, o mesmo tempo de cross): o cross sobre o denso com janelas, o pacote do kit,
    # e o denso sem e com janelas como referência barata
    assert [rv.config_name(c) for c in seen[-1]] == ["bm25", "dense", "dense+windows", "dense+windows+cross",
                                                     "dense+windows+cross:base"]
    assert all(c.get("windows") == config.KIT_RETRIEVER["windows"] for c in seen[-1] if c.get("rerank"))
    assert run_evals.main(["--choose-retriever", "--fast", "--windows"]) == 0  # cada denso com e sem janelas
    names = [rv.config_name(c) for c in seen[-1]]
    assert sorted(names) == sorted(["bm25", "dense", "dense+windows", "dense+windows+cross", "dense+cross",
                                    "dense+windows+cross:base", "dense+cross:base"])
    assert len(names) == len(set(names))  # nenhuma configuração repetida



def test_readme_sentence_of_a_windowed_choice_keeps_the_without_cross_comparison(tmp_path):
    """A frase gerada do README compara a escolha com o mesmo buscador sem o cross (scripts/fill_readme.py): com
    janelas, é a linha dense+windows que o --fast mede."""
    from scripts.fill_readme import retriever_block

    note = {"min_rerank": -4.986, "meets_floor": True, "positives": 48, "negatives": 22}
    rec = {"chosen_at": "t", "git_sha": "abc1234", "gold": "retrieval.jsonl", "criterion": "maior Recall@5",
           "chosen": "dense+windows+cross:base", "choice": {**DENSE, "windows": True, "gate": {"min_rerank": -4.986}},
           "measured": {
               "dense+windows": {"recall@5": 0.938, "latency_ms": {"p50": 70.0}, "memory_mb": 1560.0,
                                 "gate": {"pos_answered": 0.917, "neg_refused": 0.864, "positives": 48,
                                          "negatives": 22}},
               "dense+windows+cross:base": {"recall@5": 0.938, "latency_ms": {"p50": 1050.0}, "memory_mb": 2400.0,
                                            "rerank_gate": {**note, "pos_answered": 1.0, "neg_refused": 0.909}}}}
    (tmp_path / "retriever.json").write_text(json.dumps(rec), encoding="utf-8")
    text = retriever_block(tmp_path, data=tmp_path)
    assert "`dense+windows+cross:base`" in text and "sem o cross, o do denso responde 92% e recusa 86%" in text
    assert "Custo a mais por busca: +980 ms no p50" in text
    assert {"dense+windows", "dense+windows+cross:base"} <= {rv.config_name(c) for c in rv.FAST_CONFIGS}


def test_eval_config_names_and_builds_windows_explicitly(monkeypatch):
    cfg = {**DENSE, "windows": True}
    assert rv.config_name(cfg) == "dense+windows+cross:base"
    assert rv.config_name(DENSE) == "dense+cross:base"
    monkeypatch.setenv("RAG_WINDOWS", "on")  # o ambiente não muda o que a configuração (gravada) mede
    fx = rv._Factories(embedder=ConceptEmbedder(), scorer=RecordingScorer())
    assert rv.build(DENSE, fx).base.windows is False
    built = rv.build(cfg, fx)
    assert built.base.windows is True and built.name == "dense+windows+cross:base"
