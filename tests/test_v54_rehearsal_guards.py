"""Ensaio pré-produção de 03/11: guardas de processo que o relógio pediu."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_live_eval_refuses_when_another_heavy_process_holds_the_ram():
    sh = (ROOT / "scripts" / "live_eval.sh").read_text(encoding="utf-8")
    assert "MemAvailable" in sh and "LIVE_EVAL_MIN_RAM_GB:-6" in sh and "DRY == 0" in sh


def test_prompt_forbids_untracked_background_work_at_turn_end():
    path = ROOT / "docs" / "kit" / "V5_PROMPT_M.md"
    if not path.exists():  # na tentativa docs/kit fica fora do repositório (scaffold)
        import pytest

        pytest.skip("docs/kit fora do repositório da tentativa")
    prompt = path.read_text(encoding="utf-8")
    assert "run_in_background" in prompt and "nunca encerre o turno" in prompt


def test_iso_datetime_from_a_tool_supports_the_hour_in_the_answer():
    """memory-07/08 do ensaio: "às 09:16" virava "às [valor não confirmado]:16" (o T colava na hora ISO)."""
    from app.grounding import unsupported_numbers

    ev = ['{"terminal": "T1988B", "last_contact": "2026-11-03T09:16:00", "offline_hours": 5}']
    assert unsupported_numbers("Offline há 5 horas; último contato em 03/11/2026 às 09:16.", ev) == []
    assert unsupported_numbers("Last contact: 2026-11-03 at 09:16", ev) == []
    assert unsupported_numbers("Último contato às 10:16", ev) == ["10"]  # hora que a tool não deu segue sem base


def test_expects_fact_accepts_literal_and_regex_like_expect_facts():
    """q-mem-01..06 do ensaio: regex no expects_fact reprovava resposta certa (memória 0,67 → 0,94 no remedido)."""
    from evals.memory_metrics import facts_ok

    assert facts_ok(["129[,.]90"], "A Get Smart custa R$ 129,90/mês")
    assert facts_ok(["whats ?app"], "dá para vender pelo WhatsApp")
    assert facts_ok(["T1988A"], "o terminal T1988A está online")
    assert facts_ok(["R$ 75,00"], "o total foi 75.0")
    assert not facts_ok(["129[,.]90"], "A Get Smart custa R$ 79,90/mês")
    assert not facts_ok(["(unclosed"], "qualquer coisa")


def test_delivery_clock_starts_at_scaffold_and_names_the_commit(tmp_path, monkeypatch):
    """Ensaio de 03/11: "41 min" (mensagem gerada no T+41) com o relógio fechando no T+47; e sem tag o início era o
    1º commit do repositório (antes do relógio)."""
    import subprocess

    from scripts import delivery_message

    def git(*a, date=None):
        env = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {}
        import os
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True, env={**os.environ, **env})

    git("init", "-q")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "chore: repositório",
        date="2026-11-03T12:00:00+00:00")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "chore: scaffold kit",
        date="2026-11-03T13:45:00+00:00")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "readme: final",
        date="2026-11-03T14:32:00+00:00")
    assert delivery_message.minutes(tmp_path) == 47
    final = (ROOT / "scripts" / "final.sh").read_text(encoding="utf-8")
    assert "var/ENTREGA_final.md" in final and final.index("git push") < final.index("ENTREGA_final")
    from scripts import fill_readme  # tudo o que o fill_readme gera entra no commit final (PROCEDENCIA conta o git)

    assert all(f in final for f in fill_readme.README_ONLY)


def test_check_and_live_eval_refuse_a_retriever_in_fallback():
    """Ensaio de 03/11: só [dev] instalado → BM25 do fallback na tentativa × denso + cross no CI/docker."""
    check = (ROOT / "scripts" / "check.py").read_text(encoding="utf-8")
    assert "buscador = o configurado (sem fallback)" in check and "requirements-hybrid.lock" in check
    sh = (ROOT / "scripts" / "live_eval.sh").read_text(encoding="utf-8")
    assert "LIVE_EVAL_ALLOW_FALLBACK" in sh and "fallback" in sh


def test_supervisor_llm_decides_every_turn_by_default(monkeypatch):
    """Kit v5.5 (perfil Skywalker): sem atalho de tabela por padrão; o supervisor LLM decide e o DEMO mostra."""
    from app import config

    monkeypatch.delenv("SUPERVISOR_FAST", raising=False)
    assert config.supervisor_fast() is False
    monkeypatch.setenv("SUPERVISOR_FAST", "on")
    assert config.supervisor_fast() is True


def test_readme_headline_has_no_self_targets(tmp_path):
    """Kit v5.5 (perfil Skywalker): manchete do README sem meta própria nem status "abaixo"."""
    import json

    from scripts import scorecard

    (tmp_path / "latest.json").write_text(json.dumps({"retrieval": {"recall@3": 0.84, "mrr": 0.82}}), encoding="utf-8")
    md = scorecard.headline_markdown(tmp_path)
    assert "Busca: Recall@3 | 0.84" in md and "abaixo" not in md and "referência" not in md
