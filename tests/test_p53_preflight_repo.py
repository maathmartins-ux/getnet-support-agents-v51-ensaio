"""Pré-voo confere o repositório da tentativa: ramo padrão `main` e kit vindo de `kit-fonte`.

Repositórios git temporários: um `origin` bare (com HEAD apontando para o ramo padrão) e o clone da sessão.
"""
import os
import subprocess

import pytest

from scripts import preflight

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.test", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t.test", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def git(cwd, *args):
    out = subprocess.run(["git", *args], cwd=cwd, env=ENV, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    for k in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(k, ENV[k])
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)


def attempt_repo(tmp_path, default="main", kit=True, consume=True, delete_kit=False):
    """Repositório como a maestra deixa antes do relógio (kit-fonte + main com 1 commit) e o clone da sessão."""
    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "-q", "-b", "main")
    (seed / "README.md").write_text("tentativa\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "chore: repositório (antes do relógio)")
    if kit:
        git(seed, "checkout", "-q", "--orphan", "kit-fonte")
        git(seed, "rm", "-rq", "--cached", ".")
        (seed / "README.md").unlink()
        for rel in ("scripts/preflight.py", "src/app/rag.py", "docs/kit/PLAYBOOK.md"):
            (seed / rel).parent.mkdir(parents=True, exist_ok=True)
            (seed / rel).write_text(f"# {rel}\n")
        git(seed, "add", "-A")
        git(seed, "commit", "-q", "-m", "kit v5.3")
        git(seed, "checkout", "-q", "main")
        git(seed, "clean", "-fdq")
    if default != "main":
        git(seed, "branch", "-q", default)
    origin = tmp_path / "origin.git"
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(origin))
    git(origin, "symbolic-ref", "HEAD", f"refs/heads/{default}")
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(origin), str(work))
    git(work, "checkout", "-q", "main")
    if kit and consume:
        git(work, "checkout", "origin/kit-fonte", "--", ".")
        git(work, "rm", "-rq", "--cached", "docs/kit")
        git(work, "commit", "-q", "-m", "chore: scaffold from entregar-desafio-cronometrado kit v5.3.0")
    if delete_kit:
        git(work, "push", "-q", "origin", "--delete", "kit-fonte")
        git(work, "fetch", "-q", "--prune")
    return work


def test_ready_repo_passes(tmp_path):
    assert preflight.check_repo(attempt_repo(tmp_path)) == []


def test_default_branch_not_main_fails_with_the_fix(tmp_path):
    [problem] = preflight.check_repo(attempt_repo(tmp_path, default="master"))
    assert "`master`" in problem and "Default branch" in problem


def test_default_branch_read_from_the_remote_when_origin_head_is_missing(tmp_path):
    work = attempt_repo(tmp_path)
    git(work, "remote", "set-head", "origin", "-d")
    assert preflight.default_branch(work) == "main"
    assert preflight.check_repo(work) == []


def test_kit_branch_not_consumed_fails(tmp_path):
    [problem] = preflight.check_repo(attempt_repo(tmp_path, consume=False))
    assert "não foi consumido" in problem and "scripts/preflight.py" in problem
    assert "docs/kit" in problem  # a instrução de conserto já tira docs/kit do índice


def test_kit_branch_missing_and_no_scaffold_fails(tmp_path):
    [problem] = preflight.check_repo(attempt_repo(tmp_path, kit=False))
    assert "`kit-fonte` não existe" in problem and "add_repo" in problem


def test_kit_branch_already_deleted_after_scaffold_passes(tmp_path):
    assert preflight.check_repo(attempt_repo(tmp_path, delete_kit=True)) == []


def test_kit_branch_only_on_the_remote_is_fetched(tmp_path):
    work = attempt_repo(tmp_path)
    git(work, "update-ref", "-d", "refs/remotes/origin/kit-fonte")
    assert preflight.check_repo(work) == []


def test_no_origin_and_not_a_repo_fail(tmp_path):
    work = attempt_repo(tmp_path)
    git(work, "remote", "remove", "origin")
    problems = preflight.check_repo(work)
    assert any("sem remoto `origin`" in p for p in problems)
    plain = tmp_path / "plain"
    plain.mkdir()
    assert "não é um repositório git" in preflight.check_repo(plain)[0]


def test_main_stops_before_touching_anything_when_the_repo_is_wrong(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(preflight, "ROOT", attempt_repo(tmp_path, default="master"))
    monkeypatch.setattr(preflight, "build", lambda dry: pytest.fail("build não pode rodar"))
    monkeypatch.setattr("sys.argv", ["preflight.py"])
    assert preflight.main() == 1
    assert "PRÉ-VOO FALHOU" in capsys.readouterr().out
