"""Getnet v4 (01/11/2026): scripts/live_eval.sh foi commitado sem o bit de execução e o eval ao vivo morreu com
"Permission denied" (código 126) no meio do relógio. Todo .sh do kit precisa ir executável para o git."""
import subprocess

from app.config import ROOT


def test_shell_scripts_are_executable_in_git():
    out = subprocess.run(["git", "ls-files", "-s", "--", "*.sh"], cwd=ROOT, capture_output=True, text=True, check=False)
    lines = [line for line in out.stdout.splitlines() if line.strip()]
    not_exec = [line.split("\t")[-1] for line in lines if not line.startswith("100755")]
    assert not not_exec, f"sem bit de execução no git (git update-index --chmod=+x): {not_exec}"
