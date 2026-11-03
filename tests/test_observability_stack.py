"""Painel do Grafana, Prometheus e /ui (v5): o dashboard só usa métricas que o código EMITE, o compose tem o perfil
`observability` e a tela do lojista é estática, sem CDN e sem token embutido."""
import json
import re

import yaml
from fastapi.testclient import TestClient

from app.api import app
from app.config import ROOT

DASH = ROOT / "ops" / "grafana" / "dashboards" / "support.json"
EMITTED_EXTRA = {"span_latency_ms_sum", "span_latency_ms_count"}  # linhas de latência do Metrics.render()


def emitted_metrics() -> set[str]:
    names = set(EMITTED_EXTRA)
    for path in (ROOT / "src" / "app").rglob("*.py"):
        names |= set(re.findall(r"METRICS\.(?:inc|add)\(\s*\"([a-z_]+)\"", path.read_text(encoding="utf-8")))
    return names


def test_every_dashboard_metric_is_emitted_by_the_code():
    dash = json.loads(DASH.read_text(encoding="utf-8"))
    assert len(dash["panels"]) >= 10 and dash["uid"] and dash["title"]
    used: set[str] = set()
    for p in dash["panels"]:
        assert p["targets"], p["title"]
        for t in p["targets"]:
            used |= set(re.findall(r"\b([a-z]+(?:_[a-z]+)+)\b(?=[\[{ (]|$)", t["expr"]))
    metrics = {m for m in used if m.endswith(("_total", "_sum", "_count"))}
    assert metrics, "nenhuma métrica encontrada nas expressões"
    ghosts = sorted(metrics - emitted_metrics())
    assert not ghosts, f"painel usa métrica que o código não emite: {ghosts}"


def test_compose_has_observability_profile_bound_to_loopback():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    for name in ("prometheus", "grafana"):
        svc = compose["services"][name]
        assert svc["profiles"] == ["observability"] and ":" in svc["image"] and "latest" not in svc["image"]
        assert all(port.startswith("127.0.0.1:") for port in svc["ports"])  # só loopback
    assert "profiles" not in compose["services"]["api"]  # o padrão continua subindo só a API


def test_prometheus_scrapes_the_api_and_grafana_is_provisioned():
    prom = yaml.safe_load((ROOT / "ops" / "prometheus.yml").read_text(encoding="utf-8"))
    sd = prom["scrape_configs"][0]["dns_sd_configs"][0]  # um alvo por réplica (ver test_production_ops)
    assert "api" in sd["names"] and sd["port"] == 8000
    assert (ROOT / "ops" / "alerts.yml").exists() and "/etc/prometheus/alerts.yml" in prom["rule_files"]
    ds = yaml.safe_load((ROOT / "ops/grafana/provisioning/datasources/prometheus.yml").read_text(encoding="utf-8"))
    assert ds["datasources"][0]["uid"] == "prometheus"
    assert json.loads(DASH.read_text(encoding="utf-8"))["panels"][0]["datasource"]["uid"] == "prometheus"


def test_merchant_ui_is_static_without_cdn_or_embedded_token():
    r = TestClient(app).get("/ui")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    html = r.text
    assert 'fetch("/chat"' in html and 'type="password"' in html
    assert not re.search(r"<script[^>]+src=|<link[^>]+href=\"https?://|https?://cdn", html)  # sem recurso externo
    assert "Bearer eyJ" not in html and "localStorage" not in html  # token fica só na aba
