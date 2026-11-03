"""ops/alerts.yml: regras válidas, com histerese e ação, e só com métricas que o app de fato emite."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def emitted_metrics() -> set[str]:
    code = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src" / "app").glob("*.py"))
    names = set(re.findall(r'METRICS\.(?:inc|add)\("([a-z_]+)"', code))
    return names | {"span_latency_ms_sum", "span_latency_ms_count"}  # render() de observability.py


def test_alert_rules_are_valid_and_actionable():
    rules = yaml.safe_load((ROOT / "ops" / "alerts.yml").read_text(encoding="utf-8"))["groups"][0]["rules"]
    assert len(rules) >= 5
    known = emitted_metrics()
    for rule in rules:
        assert rule["alert"] and rule["expr"] and rule["for"], rule
        assert rule["annotations"]["action"], f"{rule['alert']} sem ação: alerta sem ação vira ruído"
        used = set(re.findall(r"\b([a-z_]+_(?:total|sum|count))\b", rule["expr"]))
        assert used and used <= known, f"{rule['alert']} usa métrica que o app não emite: {used - known}"


def test_every_alert_has_a_runbook_section():
    """Alerta sem runbook não diz a quem é chamado o que fazer (método nelsondell: um runbook por alerta)."""
    rules = yaml.safe_load((ROOT / "ops" / "alerts.yml").read_text(encoding="utf-8"))["groups"][0]["rules"]
    runbook = (ROOT / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
    sections = {m.group(1).lower(): m.start() for m in re.finditer(r"^## (\w+)\s*$", runbook, re.MULTILINE)}
    for rule in rules:
        name = rule["alert"]
        assert rule["annotations"].get("runbook_url") == f"docs/RUNBOOK.md#{name.lower()}", name
        assert name.lower() in sections, f"{name} sem seção em docs/RUNBOOK.md"
        start = sections[name.lower()]
        nxt = min([v for v in sections.values() if v > start] or [len(runbook)])
        block = runbook[start:nxt]
        for part in ("O que significa", "Como confirmar", "O que fazer", "Quando escalar"):
            assert part in block, f"{name}: falta '{part}' no runbook"
