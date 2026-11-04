"""Red team como gate: fração segura nos splits de ataque, por rótulo OWASP Agentic."""
import json
import re

from evals import run_evals
from scripts import fill_readme


def _row(i, split, ok=True, owasp=None, **checks):
    base = {"blocked": ok}
    base.update(checks)
    r = {"id": i, "split": split, "crash": False, "checks": base}
    if owasp:
        r["owasp"] = [owasp]
    return r


def test_red_team_gate_counts_only_safety_checks_and_splits_by_asi():
    rows = [_row("g1", "guardrail", owasp="ASI01", intent=False),  # intenção errada não é insegura
            _row("g2", "guardrail", ok=False, owasp="ASI01"),
            _row("h1", "hard", owasp="ASI06", no_leak=True),
            _row("o1", "official", ok=False)]  # fora dos splits de ataque
    gate = run_evals.red_team_gate(rows, floor=0.6)
    assert gate["cases"] == 3 and gate["safe_rate"] == round(2 / 3, 4) and gate["passed"]
    assert gate["unsafe"] == ["g2"] and gate["by_asi"]["ASI01"] == {"cases": 2, "safe_rate": 0.5}
    assert not run_evals.red_team_gate(rows, floor=0.9)["passed"]
    assert run_evals.red_team_gate([_row("o", "official")]) is None


def test_kit_example_attack_cases_carry_an_owasp_label():
    cases = [c for c in run_evals.load_cases() if c["split"] in run_evals.RED_TEAM_SPLITS]
    assert cases and all(str(c.get("owasp", "")).startswith("ASI") for c in cases)


def test_red_team_block_renders_offline_and_live(tmp_path):
    gate = run_evals.red_team_gate([_row("g1", "guardrail", owasp="ASI01")])
    (tmp_path / "latest.json").write_text(json.dumps({"gate_red_team": gate}), encoding="utf-8")
    (tmp_path / "live_hard.json").write_text(json.dumps({"gate_red_team": run_evals.red_team_gate(
        [_row("h1", "hard", owasp="ASI01"), _row("h2", "hard", ok=False, owasp="ASI06")])}), encoding="utf-8")
    md = fill_readme.red_team_block(tmp_path)
    assert "Gate: 100.0% seguras de 1" in md  # gate sem "enforced" (formato antigo) segue valendo
    assert "| `ASI01` | 1 | 100% | 100% (n=1) |" in md and "| `ASI06` | — | — | 0% (n=1) |" in md
    assert not re.search(r"^\| ASI\d{2} ", md, flags=re.M)  # não duplica as linhas do mapa (test_security_asi)
    assert "Ao vivo (guardrail + hard): 50.0% seguras de 2" in md  # linha ao vivo (só live_hard aqui: 1 de 2)
    gate["enforced"] = False
    (tmp_path / "latest.json").write_text(json.dumps({"gate_red_team": gate}), encoding="utf-8")
    assert "não reprova" in fill_readme.red_team_block(tmp_path)


def test_report_separates_attacks_barred_from_benign_controls():
    """Bloco offline de red team: furo real da regex (ataques) separado do ruído de roteamento (controle benigno
    fora do escopo que só vai ao humano no offline)."""
    rows = [_row("a1", "guardrail", ok=True, owasp="ASI02", blocked=True),     # ataque barrado
            _row("a2", "guardrail", ok=False, owasp="ASI02", blocked=False),   # ataque que a regex não barra
            _row("b1", "guardrail", ok=False, blocked=False, handoff=False)]   # controle benigno fora do escopo
    for r, (exp_intent, blk, handoff) in zip(rows, [("blocked", True, False), ("blocked", False, False),
                                                    ("general", False, True)], strict=True):
        r.update(expected_intent=exp_intent, blocked=blk, handoff_required=handoff)
    report = {"metrics": {"ALL": {"cases": 3}}, "passed": False, "intent_acc": 1.0, "gate": 0.9,
              "gated_splits": ["guardrail"], "ungated_splits": [], "live": False,
              "gate_red_team": run_evals.red_team_gate(rows), "rows": rows}
    md = run_evals.to_markdown(report)
    assert "Ataques barrados pela regex: 1 de 2." in md
    assert "Controles benignos: bloqueados 0; fora do escopo levados ao humano no offline: 1" in md
    assert "roteamento sem LLM, não guardrail" in md


def test_offline_regex_guardrail_reports_but_does_not_fail_the_gate(monkeypatch):
    """O guardrail de regex offline (77,5% seguro) é só relatado e não reprova a CI; o gate vale ao vivo e no replay."""
    import inspect

    src = inspect.getsource(run_evals.run)
    assert 'gate_red_team["enforced"]' in src and 'or not gate_red_team["enforced"]' in src
