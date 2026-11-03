"""A imagem docker serve o MESMO buscador que o eval mede.

O padrão do kit é denso + cross; uma imagem sem fastembed cai no BM25 dentro do container e o eval via HTTP resolve
3 de 10 oficiais (9 de 10 em processo). Por isso o Dockerfile resolve EXTRAS=auto pela escolha do buscador.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import fetch_models

ROOT = Path(__file__).resolve().parents[1]


def test_kit_default_needs_embeddings_in_the_image(tmp_path, monkeypatch):
    for var in ("RETRIEVER", "RERANK", "EMBED_MODEL", "RERANK_MODEL"):
        monkeypatch.delenv(var, raising=False)
    assert fetch_models.needed_extras(tmp_path) == "hybrid"  # sem escolha gravada: denso + cross do kit


def test_bm25_choice_keeps_the_slim_image(tmp_path, monkeypatch):
    for var in ("RETRIEVER", "RERANK", "EMBED_MODEL", "RERANK_MODEL"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / "retriever.json").write_text(json.dumps({"choice": {"retriever": "bm25", "rerank": "off"}}),
                                             encoding="utf-8")
    assert fetch_models.needed_extras(tmp_path) == ""


def test_extras_flag_prints_without_downloading(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("RETRIEVER", raising=False)
    assert fetch_models.main(["--data", str(tmp_path), "--extras"]) == 0
    assert capsys.readouterr().out.strip() == "hybrid"


def test_dockerfile_resolves_auto_and_ships_corpus_vectors():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert 'ARG EXTRAS="auto"' in text and "fetch_models.py --data /tmp --extras" in text
    assert "EMBED_CACHE_DIR=/opt/vectors" in text  # 1º pedido não vetoriza o corpus
    assert "!var/embeddings" in (ROOT / ".dockerignore").read_text(encoding="utf-8")


def test_check_container_must_not_fall_back_and_ci_installs_the_retriever():
    check = (ROOT / "scripts" / "check.py").read_text(encoding="utf-8")
    assert 'not health.get("retriever_fallback")' in check
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = ci.split("  check:", 1)[1].split("\n  offline-tests:", 1)[0]
    assert "requirements-hybrid.lock" in job and "fetch_models.py" in job and "var/embeddings" in job
