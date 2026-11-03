"""Cadeia de suprimento e produção, conferidas sem rede: actions por SHA, exceções do trivy com motivo e validade,
CI com rede cortada/SBOM/trivy, overlay endurecido e volume nomeado no compose padrão."""
import datetime as dt
import re

import yaml

from app.config import ROOT

WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)(.*)$")
TRIVY_MAX_DAYS = 90


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


def test_hardened_overlay():
    api = _compose("docker-compose.hardened.yml")["services"]["api"]
    assert api["read_only"] is True and api["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in api["security_opt"]
    assert api["mem_limit"] and api["cpus"] and api["pids_limit"] and any(t.startswith("/tmp") for t in api["tmpfs"])
    assert all(p.startswith("127.0.0.1:") for p in api["ports"]), "porta só no loopback"
    assert api["logging"]["options"]["max-size"] and "/ready" in " ".join(api["healthcheck"]["test"])
    assert not str(api.get("user", "")).startswith("0"), "nunca root"
