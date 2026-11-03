"""Ao vivo com vários splits num processo só.

Com o buscador denso, cada processo do eval carrega e5-large + cross-encoder; um processo por split estoura a
memória. `run_evals --splits` roda os splits ao mesmo tempo, num processo, cada um
com a sua cota, o seu live_<split>.json e o seu cassete.
"""
import itertools
import json
import os
import shutil
import stat
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from fakes import resp, text

from app import llm as llm_mod
from app.llm import AnthropicLLM
from evals import run_evals

ROOT = Path(__file__).resolve().parents[1]


class PricedClient:
    def __init__(self, cost=0.4):
        self.calls, self.cost, self.lock = [], cost, threading.Lock()

    def send(self, message, user_id, conversation_id):
        with self.lock:
            self.calls.append(message)
        return {"intent": "faq", "conversation_id": "c", "answer": "ok", "replans": [], "route": ["router", "faq"],
                "usage": {"cost_usd": self.cost}}


def _ids(split):
    return {c["id"] for c in run_evals.load_cases() if c["split"] == split}


def test_each_split_gets_its_own_share_and_report():
    reports = run_evals.run_splits(["official", "replan"], max_usd=2.0, workers=2, client=PricedClient(0.4))
    spent = 0.0
    for split, share in (("official", round(2.0 * 4 / 7, 6)), ("replan", round(2.0 * 3 / 7, 6))):
        saved = json.loads((run_evals.RESULTS_DIR / f"live_{split}.json").read_text(encoding="utf-8"))
        assert saved["max_usd"] == share  # cota proporcional aos casos, não 2,0 / 2 splits
        assert saved["spent_usd"] <= saved["budget"]["limit"] + 1e-9  # cota + o que pegou da sobra
        assert {r["id"] for r in saved["rows"]} <= _ids(split)  # nenhum caso do outro split
        assert reports[split]["status"] == saved["status"] in ("complete", "aborted_max_usd")
        spent += saved["spent_usd"]
    assert spent <= 2.0 + 1e-9  # 7 casos de 0,4 = 2,8 não cabem: alguém para no teto, e o total nunca passa
    assert "aborted_max_usd" in {r["status"] for r in reports.values()}


def test_complete_splits_and_exit_code(monkeypatch, capsys):
    monkeypatch.setenv("APP_ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(run_evals, "run_splits", lambda names, *a, **k: {
        n: {"status": "complete", "spent_usd": 0.1, "max_usd": 1, "path": f"live_{n}.json"} for n in names})
    assert run_evals.main(["--live", "--splits", "official, replan"]) == 0
    monkeypatch.setattr(run_evals, "run_splits", lambda names, *a, **k: {
        "official": {"status": "complete"}, "replan": {"status": "aborted_max_usd"}})
    assert run_evals.main(["--live", "--splits", "official,replan"]) == 3
    assert run_evals.main(["--splits", "official"]) == 64  # só ao vivo
    assert "replan: status aborted_max_usd" in capsys.readouterr().out


def test_complete_run_writes_one_file_per_split():
    run_evals.run_splits(["official", "parallel"], max_usd=None, workers=3, client=PricedClient(0.01))
    for split in ("official", "parallel"):
        saved = json.loads((run_evals.RESULTS_DIR / f"live_{split}.json").read_text(encoding="utf-8"))
        assert saved["status"] == "complete" and {r["id"] for r in saved["rows"]} == _ids(split)
        assert saved["retrieval"]["retriever"] == "bm25"  # medidas offline, uma vez para todos os splits


class ScriptedAPI:
    def __init__(self):
        self.counter, self.lock = itertools.count(1), threading.Lock()
        self.messages = NS(create=self.create)

    def create(self, **kwargs):
        with self.lock:
            n = next(self.counter)
        if (kwargs.get("output_config") or {}).get("format"):
            return resp("end_turn", text("{}"))
        return resp("end_turn", text(f"Resposta gravada número {n}, de acordo com a fonte."))


def test_each_split_records_its_own_cassette_and_replays(monkeypatch):
    api = ScriptedAPI()
    monkeypatch.setattr(llm_mod, "_anthropic", lambda model, effort: AnthropicLLM(model, effort, client=api))
    reports = run_evals.run_splits(["official", "replan"], workers=2, repeat=1)
    for split in ("official", "replan"):
        assert reports[split]["status"] == "complete" and reports[split]["cassette"]["requests"] > 0
        lines = (run_evals.cassettes_dir() / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
        scopes = {json.loads(line)["scope"].split("#")[0] for line in lines}
        assert scopes <= _ids(split)  # o cassete de um split não leva gravação do outro
        assert reports[split]["llm_errors"] == 0
    summary = run_evals.run_replay()
    assert summary["passed"], summary


# --- o script: UM processo do run_evals para todos os splits ------------------------------------------------
BASH = shutil.which("bash")


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="sem bash POSIX")
def test_live_eval_sh_starts_one_eval_process_for_all_splits(tmp_path):
    root = tmp_path / "proj"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "live_eval.sh", root / "scripts" / "live_eval.sh")
    log = tmp_path / "calls.log"
    fake = tmp_path / "fakepy"
    # intérprete falso: registra cada `-m evals.run_evals`, grava o resultado ao vivo pedido e repassa o resto
    fake.write_text(f"""#!/usr/bin/env bash
if [[ "$1" == "-m" && "$2" == "evals.run_evals" ]]; then
  echo "$*" >> "{log}"
  if [[ " $* " == *" --live "* ]]; then
    mkdir -p evals/results
    IFS=',' read -r -a S <<< "$5"
    for s in "${{S[@]}}"; do echo '{{"status": "complete", "spent_usd": 0.1}}' > "evals/results/live_$s.json"; done
  fi
  exit 0
fi
[[ "$1" == "scripts/fill_readme.py" ]] && exit 0
exec "{sys.executable}" "$@"
""", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    out = subprocess.run([BASH, str(root / "scripts" / "live_eval.sh"), "--splits", "official,memory,replan",
                          "--max-usd", "10", "--repeat", "1", "--no-judge"], capture_output=True, text=True,
                         encoding="utf-8", timeout=120, env={**os.environ, "LIVE_EVAL_PY": str(fake)})
    assert out.returncode == 0, out.stdout + out.stderr
    live = [line for line in log.read_text(encoding="utf-8").splitlines() if "--live" in line]
    assert len(live) == 1, live  # antes: um processo por split
    assert "--splits official,memory,replan" in live[0] and "--max-usd 6.5" in live[0]  # 65% de 10
    assert "official: complete" in out.stdout and "replan: complete" in out.stdout
