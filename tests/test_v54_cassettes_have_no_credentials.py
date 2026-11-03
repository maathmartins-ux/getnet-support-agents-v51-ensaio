"""Ensaio v5.4: as gravações ao vivo (evals/cassettes/) saem da varredura do gitleaks (falsos positivos aos milhares:
hash do pedido e assinaturas do thinking). Em troca, este teste varre as gravações atrás de credencial de verdade."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CREDENTIAL = re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|xox[bp]-[A-Za-z0-9-]{20,}")


def test_cassettes_have_no_real_credentials():
    leaks = [f"{p.relative_to(ROOT)}:{n}" for p in sorted((ROOT / "evals" / "cassettes").glob("**/*.jsonl"))
             for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
             if CREDENTIAL.search(line)]
    assert not leaks, f"credencial em gravação: {leaks[:5]}"


def test_gitleaks_skips_only_tests_and_cassettes():
    text = (ROOT / ".gitleaks.toml").read_text(encoding="utf-8")
    assert "'''^evals/cassettes/'''" in text and "useDefault = true" in text
