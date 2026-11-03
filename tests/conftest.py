import os
import uuid
from pathlib import Path

import pytest

# Domínio do kit ANTES de importar qualquer módulo do app: os testes do kit nunca enxergam o domínio do desafio
# (app/domain/challenge.py). Getnet v3: o domínio trocou o código e 59 testes do kit quebraram (CI vermelho).
os.environ["DOMAIN"] = "example"
# Buscador BM25 também para fixtures de módulo/sessão (rodam antes do isolated_env): o padrão do app é o denso + cross
# (config.KIT_RETRIEVER, ~2,8 GB de modelos) e o servidor do test_mcp montava os dois na subida.
os.environ["RETRIEVER"] = "bm25"
os.environ.setdefault("RETRIEVAL_CACHE", "off")  # testes trocam buscador/embedder por monkeypatch
os.environ.setdefault("JUDGE_WORKERS", "1")  # ordem determinística nos testes de teto; o paralelo tem teste próprio

from app import notify, observability
from app.auth import LIMITER
from app.config import ROOT
from app.observability import configure_otel
from evals import judge, run_evals

# Dados do kit: os testes do kit nunca leem o que o domínio troca no relógio (data/, retrieval, calibração).
# Getnet v3 (31/10/2026): trocar só os dados quebrava 24 de 187 testes e atrasou o G1 em 17 min (regra D2).
KIT_DATA = Path(__file__).parent / "fixtures" / "kit_data"

# Backends do store: os módulos abaixo rodam cada teste em SQLite E em Postgres (marcador `postgres`). O Postgres só
# roda com TEST_DATABASE_URL (ex.: postgresql://postgres@127.0.0.1:5432/postgres; job `postgres` do CI); sem ela, a
# variante é pulada, nunca falha. Cada teste ganha um esquema próprio (search_path), apagado no fim.
PG_URL = os.getenv("TEST_DATABASE_URL", "")
BACKEND_MODULES = {"test_hitl", "test_hitl_resume_plan", "test_memory_and_handoff", "test_privacy",
                   "test_store_backends", "test_resume_human_evidence", "test_operator_routing", "test_risk_policy",
                   "test_memory_ledger"}


def pytest_generate_tests(metafunc):
    if metafunc.module.__name__.rsplit(".", 1)[-1] in BACKEND_MODULES and "db_backend" in metafunc.fixturenames:
        metafunc.parametrize("db_backend", [
            "sqlite",
            pytest.param("postgres", marks=[pytest.mark.postgres,
                                            pytest.mark.skipif(not PG_URL, reason="sem TEST_DATABASE_URL")])],
            indirect=True)


@pytest.fixture
def db_backend(request):
    return getattr(request, "param", "sqlite")


def _pg_schema_url(schema: str) -> str:
    return f"{PG_URL}{'&' if '?' in PG_URL else '?'}options=-csearch_path%3D{schema}"


@pytest.fixture
def pg_schema(db_backend):
    """Esquema Postgres próprio do teste (None no SQLite). Apagado no fim, com as conexões do pool fechadas."""
    if db_backend != "postgres":
        yield None
        return
    import psycopg

    schema = "t_" + uuid.uuid4().hex[:12]
    with psycopg.connect(PG_URL, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
    yield _pg_schema_url(schema)
    from app import store as store_mod

    store_mod._store_for.cache_clear()
    with psycopg.connect(PG_URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch, pg_schema):
    # Cada teste com banco próprio, modo offline, sem rede e segredos conhecidos: nada vaza entre testes.
    monkeypatch.setenv("DOMAIN", "example")
    monkeypatch.setenv("DATA_DIR", str(KIT_DATA / "data"))
    monkeypatch.setattr(run_evals, "CASES", KIT_DATA / "cases.jsonl")
    monkeypatch.setattr(run_evals, "HELDOUT", KIT_DATA / "heldout_blind.jsonl")  # o kit não tem held-out
    monkeypatch.setattr(run_evals, "RETRIEVAL", KIT_DATA / "retrieval.jsonl")
    # Nenhum teste grava em evals/results/: lá mora a evidência commitada que o README cita (Getnet v3: rodar o
    # pytest sobrescrevia latest.json com números da loja de exemplo).
    monkeypatch.setattr(run_evals, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(run_evals, "RESULTS", tmp_path / "results" / "latest.json")
    monkeypatch.setattr(judge, "CALIBRATION", KIT_DATA / "judge_calibration.jsonl")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    if pg_schema:
        monkeypatch.setenv("DATABASE_URL", pg_schema)
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "offline")
    monkeypatch.setenv("AUTH_MODE", "required")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("OPERATOR_TOKEN", "test-operator")
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    monkeypatch.setenv("RETRIEVER", "bm25")
    monkeypatch.setenv("SLA_CHECK_SECONDS", "0")  # sem laço de SLA em segundo plano nos servidores de teste
    monkeypatch.setenv("LIVE_DATA", "off")  # câmbio/clima ao vivo fazem HTTP: teste liga e troca o _get_json
    # chaves e chaves de comportamento do ambiente real (na nuvem, APP_ANTHROPIC_API_KEY vem do ambiente) nunca
    # entram nos testes: offline é offline, e a ablação do replanejamento não vaza para outros testes
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_WEBHOOK_SECRET", "OTEL_EXPORTER",
                "SUPERVISOR_PARALLEL", "SUPERVISOR_REPLAN", "APP_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY",
                "APP_ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(notify, "_transport", None)
    # Orçamento do turno mora em contextvars da thread principal: um teste que chamou new_trace_id() (pipeline direto,
    # eval em processo) deixava o contador de chamadas/US$ vivo para o próximo teste do mesmo worker, e um teste de
    # supervisor com LLM falso estourava MAX_MODEL_CALLS conforme a ORDEM dos testes (falha intermitente no xdist).
    observability._usage.set(None)
    observability._calls.set(None)
    LIMITER.reset()
    yield
    LIMITER.reset()
    configure_otel(None)  # desliga o exportador se algum teste ligou


@pytest.fixture
def domain_data(monkeypatch):
    """Para testes do DOMÍNIO (escritos no relógio): domínio `challenge`, data/ e evals/ reais.

    Sem `app/domain/challenge.py` (kit antes do pré-voo), o teste de domínio é pulado, nunca roda no exemplo.
    """
    import importlib.util

    if importlib.util.find_spec("app.domain.challenge") is None:
        pytest.skip("sem app/domain/challenge.py: rode scripts/preflight.py")
    monkeypatch.setenv("DOMAIN", "challenge")
    monkeypatch.setenv("DATA_DIR", str(ROOT / "data"))
    monkeypatch.setattr(run_evals, "CASES", ROOT / "evals" / "cases.jsonl")
    monkeypatch.setattr(run_evals, "HELDOUT", ROOT / "evals" / "heldout_blind.jsonl")
    monkeypatch.setattr(run_evals, "RETRIEVAL", ROOT / "evals" / "retrieval.jsonl")
    monkeypatch.setattr(judge, "CALIBRATION", ROOT / "evals" / "judge_calibration.jsonl")
