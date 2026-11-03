"""E53 — README: títulos do enunciado, quickstart do 1º caso oficial e linha do tempo sem `{{`.

V5: o quickstart trazia "pedido 1002" (sobra do domínio de exemplo); um título de commit com `{{N}}` foi para a linha do
tempo do README e a CI do último commit ficou vermelha (pós-morte N9); o README não tinha "message workflow", "RAG
pipeline ingestion → storage → retrieval → generation" nem "testing strategy" (estudo Skywalker §1.1).
"""
import json
import re
import subprocess
from pathlib import Path

from evals import run_evals
from scripts import check, fill_readme

ROOT = Path(__file__).resolve().parents[1]


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args], check=True,
                   capture_output=True)


def _repo(tmp_path, *subjects):
    _git(tmp_path, "init", "-b", "main")
    for i, subject in enumerate(subjects):
        (tmp_path / f"f{i}").write_text(str(i), encoding="utf-8")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-m", subject)
    return tmp_path


def test_quickstart_comes_from_the_first_official_case(tmp_path, monkeypatch):
    cases = [{"id": "memory-01", "split": "memory", "message": "e a outra?", "expect": {}},
             {"id": "official-01", "split": "official", "user_id": "lojista7",
              "message": "What's the difference between Smart and Pro?", "expect": {}}]
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(json.dumps(c) for c in cases), encoding="utf-8")
    monkeypatch.setattr(run_evals, "CASES", path)
    block = fill_readme.quickstart_block()
    assert "official-01" in block and "TOKEN=$(python -m app.auth lojista7)" in block
    # aspas simples do texto escapadas para o shell: o comando colado roda
    assert """-d '{"message": "What'\\''s the difference between Smart and Pro?"}'""" in block
    assert "pedido 1002" not in block


def test_check_rejects_a_quickstart_that_is_not_the_official_case(tmp_path):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    stale = re.sub(r"(<!-- quickstart:begin -->).*?(<!-- quickstart:end -->)",
                   lambda m: m.group(1) + '\ncurl -d \'{"message":"Onde está meu pedido 1002?"}\'\n' + m.group(2),
                   readme, flags=re.S)
    (tmp_path / "README.md").write_text(stale, encoding="utf-8")
    problems = fill_readme.check(tmp_path / "README.md", tmp_path / "results", root=tmp_path)
    assert any("bloco quickstart diferente" in p for p in problems)
    (tmp_path / "README.md").write_text(readme.replace("<!-- quickstart:begin -->", ""), encoding="utf-8")
    problems = fill_readme.check(tmp_path / "README.md", tmp_path / "results", root=tmp_path)
    assert any("sem o bloco <!-- quickstart:begin -->" in p for p in problems)


def test_readme_template_has_every_heading_the_challenge_asks_for():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert fill_readme.missing_headings(readme) == []
    old = "# P\n## 1. Como rodar\n## 2. Arquitetura\n## 4. Decisões e trade-offs\n"
    assert fill_readme.missing_headings(old) == list(fill_readme.REQUIRED_HEADINGS)
    assert fill_readme.quickstart_block() in readme  # o exemplo commitado é o do 1º caso oficial do kit


def test_timeline_neutralizes_template_markers_and_pipes(tmp_path):
    root = _repo(tmp_path, "chore: scaffold", "maestra: frente {{N}} integrada | ok")
    out = fill_readme.timeline(root)
    assert "{{" not in out and "}}" not in out and "frente { {N} } integrada \\| ok" in out
    assert not re.findall(r"\{\{[^}]{0,60}\}\}", out)  # o check de marcadores do README não dispara


def test_check_rejects_commit_titles_with_markers(tmp_path):
    name, ok, _, detail = check.commit_titles_clean(_repo(tmp_path, "chore: scaffold", "feat: ok"))
    assert ok and "{{" in name
    _git(tmp_path, "commit", "--allow-empty", "-m", "maestra: {{N}} frentes")
    _, ok, _, detail = check.commit_titles_clean(tmp_path)
    assert not ok and "{{N}} frentes" in detail and "amend" in detail
