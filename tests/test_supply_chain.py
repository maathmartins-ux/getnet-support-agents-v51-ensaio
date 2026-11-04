"""Cadeia de suprimento e produção, conferidas sem rede: actions por SHA, exceções do trivy com motivo e validade,
CI com rede cortada/SBOM/trivy, overlay endurecido (com memória que cabe no buscador e o Bearer do /metrics no
Prometheus) e volume nomeado no compose padrão."""
import datetime as dt
import json
import re

import yaml

from app.config import ROOT
from evals.retrieval_eval import RAM_BUDGET_MB

WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)(.*)$")
TRIVY_MAX_DAYS = 90
# Folga do mem_limit acima da RAM do buscador. Medido no container com o overlay (04/11/2026, denso + cross, LLM
# offline): cada FAQ simultânea somou ~180 MB ao processo (1 → 2678 MB, 10 → 4563 MB, 20 → 6111 MB; uma 2ª rajada
# de 20, 6708 MB). Com 2 CPUs, 20 simultâneas já levam 50–54 s cada: a CPU satura antes, então 20 é a concorrência
# que a memória precisa aguentar.
PER_CONCURRENT_FAQ_MB = 180
CONCURRENT_FAQS = 20


class ComposeLoader(yaml.SafeLoader):
    """Compose aceita `!override`/`!reset` (merge de overlay); o yaml puro não conhece as tags."""


ComposeLoader.add_constructor("!override", lambda loader, node: (
    loader.construct_sequence(node) if isinstance(node, yaml.SequenceNode) else loader.construct_mapping(node)
    if isinstance(node, yaml.MappingNode) else loader.construct_scalar(node)))
ComposeLoader.add_constructor("!reset", lambda loader, node: None)


def _compose(name: str) -> dict:
    return yaml.load((ROOT / name).read_text(encoding="utf-8"), Loader=ComposeLoader)


def test_every_action_is_pinned_by_commit_sha_with_version_comment():
    assert WORKFLOWS
    bad = []
    for wf in WORKFLOWS:
        for line in wf.read_text(encoding="utf-8").splitlines():
            m = USES.match(line)
            if not m or m.group(1).startswith(("./", "docker://")):
                continue
            ref, rest = m.group(1), m.group(2)
            if not re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref) or not re.search(r"#\s*v?\d", rest):
                bad.append(f"{wf.name}: {line.strip()}")
    assert not bad, "fixe por SHA com a versão em comentário (scripts/pin_actions.sh):\n" + "\n".join(bad)


def test_ci_has_offline_tests_sbom_and_trivy_gate():
    jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))["jobs"]
    steps = [s for job in jobs.values() for s in job["steps"]]
    runs = " ".join(s.get("run", "") for s in steps)
    assert "scripts/offline_tests.sh" in runs and "check.py --docker" in runs
    trivy = next(s for s in steps if "trivy-action" in s.get("uses", ""))["with"]
    assert trivy["severity"] == "CRITICAL" and str(trivy["exit-code"]) == "1"
    assert trivy["trivyignores"] == ".trivyignore"
    assert any("sbom-action" in s.get("uses", "") for s in steps)
    assert all("|| true" not in s.get("run", "") for s in steps), "etapa que nunca falha não é gate"


def test_trivyignore_entries_have_reason_and_valid_expiry():
    lines = (ROOT / ".trivyignore").read_text(encoding="utf-8").splitlines()
    today = dt.date.today()
    for i, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.fullmatch(r"((?:CVE|GHSA)-[\w-]+)\s+exp:(\d{4}-\d{2}-\d{2})", line.strip())
        assert m, f"linha {i + 1}: formato `<id> exp:AAAA-MM-DD`: {line!r}"
        exp = dt.date.fromisoformat(m.group(2))
        assert today <= exp <= today + dt.timedelta(days=TRIVY_MAX_DAYS), f"{m.group(1)}: validade {exp} fora da janela"
        assert i and lines[i - 1].lstrip().startswith("# motivo:"), f"{m.group(1)} sem `# motivo:` na linha de cima"


def test_default_compose_keeps_data_in_named_volume():
    base = _compose("docker-compose.yml")
    assert "appdata:/app/var" in base["services"]["api"]["volumes"] and "appdata" in base["volumes"]


def _mb(value) -> float:
    """mem_limit do compose em MB (MiB, como o RSS do /proc que o kit mede): bytes ou número com b/k/m/g."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([bkmg]?)b?", str(value).strip().lower())
    assert m, f"mem_limit ilegível: {value!r}"
    return float(m.group(1)) * {"": 2 ** -20, "b": 2 ** -20, "k": 2 ** -10, "m": 1.0, "g": 1024.0}[m.group(2)]


def retriever_ram_mb(root=ROOT) -> float:
    """RAM do buscador que a imagem serve: o maior entre a medida do escolhido (data/retriever.json, gravado por
    `--choose-retriever --apply` no domínio) e o teto de RAM da escolha (choose() reprova o que passa dele, então
    qualquer buscador escolhido cabe); sem escolha gravada (o kit antes do relógio), o teto padrão."""
    try:
        rec = json.loads((root / "data" / "retriever.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    chosen = ((rec.get("measured") or {}).get(rec.get("chosen")) or {}).get("memory_mb")
    values = [v for v in (chosen, rec.get("ram_budget_mb", RAM_BUDGET_MB)) if v]
    return max(values) if values else RAM_BUDGET_MB


def test_hardened_overlay():
    api = _compose("docker-compose.hardened.yml")["services"]["api"]
    assert api["read_only"] is True and api["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in api["security_opt"]
    assert api["mem_limit"] and api["cpus"] and api["pids_limit"] and any(t.startswith("/tmp") for t in api["tmpfs"])
    assert all(p.startswith("127.0.0.1:") for p in api["ports"]), "porta só no loopback"
    assert api["logging"]["options"]["max-size"] and "/ready" in " ".join(api["healthcheck"]["test"])
    assert not str(api.get("user", "")).startswith("0"), "nunca root"
    # o limite acompanha o buscador medido: com 1g o cgroup matava o processo ao carregar o denso + cross (2,4 GB)
    need = retriever_ram_mb() + CONCURRENT_FAQS * PER_CONCURRENT_FAQ_MB
    assert _mb(api["mem_limit"]) >= need, f"mem_limit {api['mem_limit']} < {need:.0f} MB (buscador + simultâneas)"
    assert float(api["cpus"]) >= 2, "com 1 CPU a FAQ do denso + cross leva 7–11 s (medido); 2 CPUs, 2,9–4,7 s"


def test_hardened_overlay_memory_rule_follows_the_recorded_choice(tmp_path):
    (tmp_path / "data").mkdir()
    assert retriever_ram_mb(tmp_path) == RAM_BUDGET_MB  # kit: sem escolha gravada, o teto padrão da escolha
    rec = {"chosen": "dense+cross", "ram_budget_mb": 4096.0, "measured": {"dense+cross": {"memory_mb": 2381.8}}}
    (tmp_path / "data" / "retriever.json").write_text(json.dumps(rec), encoding="utf-8")
    assert retriever_ram_mb(tmp_path) == 4096.0  # o teto vale: o domínio pode reescolher sem mexer no overlay
    rec.update(ram_budget_mb=None, measured={"dense+cross": {"memory_mb": 5100.0}})  # teto desligado (0)
    (tmp_path / "data" / "retriever.json").write_text(json.dumps(rec), encoding="utf-8")
    assert retriever_ram_mb(tmp_path) == 5100.0
    assert _mb("8g") == 8192 and _mb("6144m") == 6144 and _mb(str(2 ** 30)) == 1024


def test_hardened_prometheus_scrapes_with_the_metrics_token():
    """Em produção o /metrics exige METRICS_TOKEN (src/app/api.py): o Prometheus do overlay manda o Bearer lido do
    segredo do compose, e o resto da configuração é a do perfil padrão (os dois arquivos não descolam)."""
    base = yaml.safe_load((ROOT / "ops" / "prometheus.yml").read_text(encoding="utf-8"))
    hardened = yaml.safe_load((ROOT / "ops" / "prometheus.hardened.yml").read_text(encoding="utf-8"))
    auths = [job.pop("authorization", None) for job in hardened["scrape_configs"]]
    assert hardened == base, "ops/prometheus.hardened.yml = ops/prometheus.yml + Bearer: mude os dois juntos"
    assert auths == [{"type": "Bearer", "credentials_file": "/run/secrets/metrics_token"}] * len(auths)
    overlay = _compose("docker-compose.hardened.yml")
    prom = overlay["services"]["prometheus"]
    assert "./ops/prometheus.hardened.yml:/etc/prometheus/prometheus.yml:ro" in prom["volumes"]
    assert "metrics_token" in prom["secrets"]
    assert overlay["secrets"]["metrics_token"] == {"environment": "METRICS_TOKEN"}  # o mesmo valor que a API lê
