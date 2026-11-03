"""K53: o buscador padrão do kit é o denso e5-large + cross-encoder bge-m3-int8 (pool 10, 600
caracteres), decidido antes do relógio; data/retriever.json ou o ambiente trocam o pacote inteiro."""
import json

from app import config


def _no_choice(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))  # sem data/retriever.json
    for var in ("RETRIEVER", "RERANK", "EMBED_MODEL", "RERANK_MODEL", "RERANK_POOL", "RERANK_CHARS"):
        monkeypatch.delenv(var, raising=False)


def test_without_choice_the_kit_default_is_dense_e5_plus_bge_cross_pool_10_600_chars(tmp_path, monkeypatch):
    _no_choice(tmp_path, monkeypatch)
    assert (config.retriever_name(), config.embed_model(), config.rerank_mode(), config.rerank_model(),
            config.rerank_pool(), config.rerank_chars()) == (
        "dense", "intfloat/multilingual-e5-large", "cross", "BAAI/bge-reranker-v2-m3-int8", 10, 600)


def test_choice_file_replaces_the_whole_bundle(tmp_path, monkeypatch):
    _no_choice(tmp_path, monkeypatch)
    (tmp_path / "retriever.json").write_text(json.dumps({"choice": {"retriever": "hybrid"}}), encoding="utf-8")
    # escolha medida sem rerank = sem rerank; os modelos não citados seguem os padrões do kit
    assert (config.retriever_name(), config.rerank_mode(), config.embed_model()) == (
        "hybrid", "off", "intfloat/multilingual-e5-large")


def test_env_retriever_is_an_explicit_choice_without_the_bundled_rerank(tmp_path, monkeypatch):
    _no_choice(tmp_path, monkeypatch)
    monkeypatch.setenv("RETRIEVER", "bm25")
    assert (config.retriever_name(), config.rerank_mode()) == ("bm25", "off")
    monkeypatch.setenv("RETRIEVER", "dense")
    assert config.rerank_mode() == "off"
    monkeypatch.setenv("RERANK", "cross")  # pedido explícito liga o rerank, com os modelos do kit
    assert (config.rerank_mode(), config.rerank_model(), config.rerank_pool()) == (
        "cross", "BAAI/bge-reranker-v2-m3-int8", 10)


def test_env_overrides_each_part_of_the_default(tmp_path, monkeypatch):
    _no_choice(tmp_path, monkeypatch)
    monkeypatch.setenv("RERANK", "off")
    monkeypatch.setenv("RERANK_POOL", "20")
    monkeypatch.setenv("EMBED_MODEL", "m/e")
    assert (config.retriever_name(), config.rerank_mode(), config.rerank_pool(), config.embed_model()) == (
        "dense", "off", 20, "m/e")


def test_default_latency_comment_cites_its_source():
    import inspect

    src = inspect.getsource(config)
    # a medida fica no comentário (número e condição), sem apontar para docs/kit/, que não existe no repo entregue
    assert "1,1–1,25 s" in src and "measured[\"dense+cross\"]" in src and "docs/kit/" not in src


def test_get_retriever_builds_the_default_bundle(monkeypatch):
    from conftest import KIT_DATA
    from fakes import ConceptEmbedder

    from app import rag

    monkeypatch.setenv("DATA_DIR", str(KIT_DATA / "data"))  # sem retriever.json
    for var in ("RETRIEVER", "RERANK"):
        monkeypatch.delenv(var, raising=False)
    built = {}

    def hybrid(directory, stamp, model, fusion="rrf", dedup=True):
        built["embed"], built["fusion"] = model, fusion
        return rag.HybridRetriever(rag.get_index(), ConceptEmbedder(), fusion)

    class Scorer:
        name = "fake-cross"

        def score(self, query, texts):
            return [float(len(t)) for t in texts]

    def cross(model):
        built["cross"] = model
        return Scorer()

    monkeypatch.setattr(rag, "_hybrid_for", hybrid)
    monkeypatch.setattr(rag, "_cross_for", cross)
    r = rag.get_retriever()
    assert r.name == "dense+cross" and r.pool == 10 and r.chars == 600 and r.fallback == ""
    assert built == {"embed": "intfloat/multilingual-e5-large", "fusion": "dense",
                     "cross": "BAAI/bge-reranker-v2-m3-int8"}
