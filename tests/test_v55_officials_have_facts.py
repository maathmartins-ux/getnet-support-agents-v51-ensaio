"""Oficial resolvido sem humano precisa de fato verificável; senão uma recusa educada conta como resolvida."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check  # noqa: E402


def _write(root, cases):
    (root / "evals").mkdir()
    (root / "evals" / "cases.jsonl").write_text("\n".join(json.dumps(c) for c in cases), encoding="utf-8")


def test_official_without_facts_fails_unless_it_expects_a_human(tmp_path):
    _write(tmp_path, [{"id": "o1", "split": "official", "expect": {"facts": ["48"]}},
                      {"id": "o2", "split": "official", "expect": {"handoff": True}},
                      {"id": "o3", "split": "official", "expect": {"intent": "general"}},
                      {"id": "m1", "split": "memory", "expect": {}}])
    _name, ok, _, detail = check.officials_have_facts(tmp_path)
    assert not ok and detail == "sem expect.facts: o3"
