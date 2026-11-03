"""Produção: compose padrão seguro, override demo, perfil postgres com réplicas sem arquivo compartilhado,
Prometheus raspando CADA réplica e painel/alertas somando entre elas, job do CI com Postgres de verdade."""
import json
import re

import yaml

from app.config import ROOT

DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


class _ComposeLoader(yaml.SafeLoader):
    """Aceita as tags do compose (`!override`, `!reset`) como o valor puro."""


_ComposeLoader.add_multi_constructor("!", lambda loader, _tag, node: loader.construct_object(
    yaml.SequenceNode("tag:yaml.org,2002:seq", node.value) if isinstance(node, yaml.SequenceNode) else node))


def _yaml(name):
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def _app_services() -> dict[str, int]:
    """Serviço da API (não o balanceador) → réplicas, em todos os arquivos de compose."""
    found: dict[str, int] = {}
    for path in sorted(ROOT.glob("docker-compose*.yml")):
        compose = yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader)  # noqa: S506 — SafeLoader
        for name, svc in (compose.get("services") or {}).items():
            is_app = ("build" in svc or "SCALE_IMAGE" in str(svc.get("image", ""))) and "lb.py" not in str(svc)
            if is_app:
                found[name] = max(found.get(name, 1), (svc.get("deploy") or {}).get("replicas", 1))
    return found


def test_default_compose_requires_a_signed_token_and_demo_is_an_explicit_override():
    api = _yaml("docker-compose.yml")["services"]["api"]
    assert api["environment"]["AUTH_MODE"] == "${AUTH_MODE:-required}"
    demo = _yaml("docker-compose.demo.yml")
    assert demo["services"] == {"api": {"environment": {"AUTH_MODE": "demo"}}}  # muda só o modo, nada mais
    text = (ROOT / "docker-compose.demo.yml").read_text(encoding="utf-8")
    assert '"user_id"' in text and "identity_verified=false" in text


def test_postgres_profile_runs_two_replicas_sharing_only_the_database():
    services = _yaml("docker-compose.yml")["services"]
    pg, api, lb = services["postgres"], services["api-pg"], services["lb-pg"]
    assert {s["profiles"][0] for s in (pg, api, lb)} == {"postgres"}
    assert DIGEST.search(pg["image"]) and pg["image"].startswith("postgres:16@")
    assert api["deploy"]["replicas"] == 2
    assert api["environment"]["DATABASE_URL"].startswith("postgresql://") and "@postgres:5432/" in \
        api["environment"]["DATABASE_URL"]
    assert "volumes" not in api  # nenhum arquivo compartilhado: só a rede até o banco (vários hosts)
    assert api["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert lb["environment"]["LB_BACKEND"] == "api-pg" and all(p.startswith("127.0.0.1:") for p in lb["ports"])


def test_prometheus_discovers_every_replica_of_every_api_service():
    prom = _yaml("ops/prometheus.yml")
    job = next(j for j in prom["scrape_configs"] if j["job_name"] == "app")
    assert "static_configs" not in job  # alvo fixo no nome do serviço = uma réplica por coleta, contadores pulam
    names = {n for sd in job["dns_sd_configs"] for n in sd["names"]}
    services = _app_services()
    assert set(services) == names, (services, names)
    assert sum(services.values()) >= 4 and all(sd["type"] == "A" and sd["port"] == 8000 for sd in job["dns_sd_configs"])


def _unsummed(expr: str) -> list[str]:
    """Funções rate()/increase() fora de qualquer sum(...) aberto — ficariam uma série por réplica."""
    bad: list[str] = []
    stack: list[bool] = []  # para cada "(" aberto: é o parêntese de um sum?
    i = 0
    while i < len(expr):
        agg = re.match(r"sum(?:\s+by\s*\([^)]*\))?\s*\(", expr[i:])
        fn = re.match(r"(rate|increase)\(", expr[i:])
        if agg:
            stack.append(True)
            i += agg.end()
        elif fn:
            if not any(stack):
                bad.append(fn.group(1))
            stack.append(False)
            i += fn.end()
        else:
            if expr[i] == "(":
                stack.append(False)
            elif expr[i] == ")" and stack:
                stack.pop()
            i += 1
    return bad


def test_unsummed_detector_flags_per_series_rates():
    assert _unsummed("rate(a[5m]) / rate(b[5m]) > 8000") == ["rate", "rate"]
    assert _unsummed("sum(rate(a[1m])) + increase(b[1m])") == ["increase"]
    assert _unsummed("sum by (x) (rate(a[5m])) / sum(increase(b[1h]))") == []


def test_dashboard_and_alerts_sum_across_replicas():
    dash = json.loads((ROOT / "ops/grafana/dashboards/support.json").read_text(encoding="utf-8"))
    exprs = [t["expr"] for p in dash["panels"] for t in p["targets"]]
    exprs += [r["expr"] for g in _yaml("ops/alerts.yml")["groups"] for r in g["rules"]]
    bad = {e: _unsummed(e) for e in exprs if _unsummed(e)}
    assert not bad, bad
    assert any("by (service, instance)" in e for e in exprs)  # e um painel mostra cada réplica


def test_ci_runs_the_postgres_variants_against_a_pinned_postgres_service():
    job = _yaml(".github/workflows/ci.yml")["jobs"]["postgres"]
    image = job["services"]["postgres"]["image"]
    assert image.startswith("postgres:16@") and DIGEST.search(image)
    assert job["services"]["postgres"]["image"] == _yaml("docker-compose.yml")["services"]["postgres"]["image"]
    assert job["env"]["TEST_DATABASE_URL"].startswith("postgresql://")
    run = " ".join(s.get("run", "") for s in job["steps"])
    assert "-m postgres" in run and 'grep -q "SKIPPED"' in run and "scripts/pg_replicas_smoke.py" in run
