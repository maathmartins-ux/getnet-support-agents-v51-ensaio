"""Rodada 11 (frente C2): documentos que se geram sozinhos e guardas de avaliação.

A régua da rodada 10 leu os docs como contraditórios com o placar: FAILURE_MODES com "42 falhas em 281 execuções" (de
outra bateria; os resultados commitados davam 5 em 315), TIMESHEET parado em "446 min, 0 depois" (o git seguia por
mais 47 commits), o §0 sem o custo por turno resolvido que o próprio README promete, e as tabelas do RESULTS sem
explicação. Aqui: cada um desses arquivos sai de um gerador, o `fill_readme --check` reprova o que divergir, e o
scripts/final.sh os gera e commita por último.
"""
import json
import os
import re
import shutil
import stat
import subprocess
from itertools import count
from pathlib import Path

import pytest

from evals import error_analysis, failure_modes, run_evals
from scripts import delivery_message, fill_readme, scorecard, timesheet

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
_files = count()


def _live(results: Path, split: str, rows: list[dict], name: str | None = None, **extra) -> None:
    results.mkdir(parents=True, exist_ok=True)
    report = {"split": split, "status": "complete", "provider": "anthropic", "spent_usd": 0.3, "rows": rows, **extra}
    (results / (name or f"live_{split}.json")).write_text(json.dumps(report), encoding="utf-8")


def _row(i: int, split: str, ok: bool = True, **extra) -> dict:
    return {"id": f"{split}-{i:02d}", "split": split, "run": 0, "message": f"pergunta {i} do {split}",
            "answer": f"resposta {i}", "checks": {"intent": True, "numbers": ok},
            "unsupported_numbers": [] if ok else ["99"], "route": ["router", "faq"], "tool_calls": [], **extra}


def _git(root: Path, *args: str, date: str | None = None) -> str:
    env = {**os.environ, **GIT_ENV, **({"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {})}
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True,
                          env=env).stdout.strip()


def _commit(root: Path, subject: str, files: dict[str, str] | None = None, date: str | None = None) -> str:
    for name, text in (files or {f"f{next(_files)}.txt": subject}).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", subject, date=date)
    return _git(root, "rev-parse", "--short=7", "HEAD")


# --- 1. §0 do README: fração resolvida sem humano e custo por turno resolvido na manchete ----------------------------

def test_readme_headline_shows_resolved_fraction_and_cost_per_resolved_turn(tmp_path):
    ok = {"answer": "x", "handoff_required": False}
    _live(tmp_path, "official", [ok, ok, ok, {"answer": "y", "handoff_required": True}], spent_usd=0.4)
    md = scorecard.headline_markdown(tmp_path)
    assert "| Turnos resolvidos sem humano (ao vivo, todos os splits) | 0.75 |" in md
    assert "| Custo por turno resolvido sem humano (ao vivo) | US$ 0.1333 |" in md  # 0,40 ÷ 3 resolvidos
    keys = list(scorecard.HEADLINE)  # o "como" do custo aponta para a contagem da linha de cima
    assert keys.index("cost_per_resolved") == keys.index("resolved_fraction") + 1
    assert set(scorecard.HEADLINE) <= set(scorecard.HOW)
    assert "abaixo" not in md  # diagnósticas: sem meta própria nem status
    # na mensagem de entrega não viram "abaixo da referência" (não têm referência)
    weak = delivery_message.render("https://x.test/r", None, tmp_path, None).split("abaixo da referência")[1]
    assert "Custo por turno resolvido" not in weak and "Turnos resolvidos sem humano" not in weak


def test_headline_declares_the_cost_as_not_measured_without_live_results(tmp_path):
    md = scorecard.headline_markdown(tmp_path)
    missing = md.split("Não medido nesta entrega:")[1]
    assert "Custo por turno resolvido sem humano" in missing and "Turnos resolvidos sem humano" in missing


# --- 2. FAILURE_MODES gerado de verdade, sem o held-out --------------------------------------------------------------

def test_failure_modes_leaves_every_blind_split_and_side_file_out(tmp_path):
    res = tmp_path / "results"
    _live(res, "official", [_row(1, "official", ok=False), _row(2, "official")])
    _live(res, "heldout", [_row(1, "heldout", ok=False)])
    _live(res, "heldout_h3", [_row(1, "heldout_h3", ok=False), _row(2, "heldout_h3")])  # lote cego novo
    _live(res, "memory", [_row(1, "memory", ok=False)] * 5, name="live_memory.degraded.json")  # não é medida
    text = failure_modes.generate(res)
    assert "1 falha em 2 execuções (50.0%)" in text and set(failure_modes.collect(res)) == {"numbers"}
    assert "Fora da conta: `heldout` (1 execução), `heldout_h3` (2 execuções), o conjunto cego" in text
    assert "do heldout" not in text and "memory" not in text  # nem pergunta do held-out, nem a rodada degradada
    out = tmp_path / "FAILURE_MODES.md"
    assert failure_modes.main(["--results", str(res), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == text  # o que o main grava é o que o --check compara
    assert failure_modes.generate(tmp_path / "vazio") is None
    assert failure_modes.main(["--results", str(tmp_path / "vazio"), "--out", str(out)]) == 1


def test_error_analysis_leaves_every_blind_split_out(tmp_path):
    _live(tmp_path, "official", [_row(1, "official")])
    _live(tmp_path, "heldout", [_row(1, "heldout")])
    _live(tmp_path, "heldout_h3", [_row(1, "heldout_h3")])
    assert [r["split"] for r in error_analysis.load_rows(tmp_path)] == ["official"]
    assert failure_modes.is_blind("heldout_h3") and not failure_modes.is_blind("official")


def test_check_fails_when_failure_modes_is_stale_missing_or_without_results(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# P\n", encoding="utf-8")
    res, fm = tmp_path / "results", tmp_path / "docs" / "FAILURE_MODES.md"

    def problems() -> str:
        return " | ".join(p for p in fill_readme.check(readme, res, root=tmp_path) if "FAILURE_MODES" in p)

    assert problems() == ""  # kit: sem bateria ao vivo e sem o arquivo
    _live(res, "official", [_row(1, "official", ok=False)])
    assert "ausente com eval ao vivo commitado" in problems()
    fm.parent.mkdir()
    fm.write_text(failure_modes.generate(res), encoding="utf-8")
    assert problems() == ""
    fm.write_text(failure_modes.generate(res) + "\n42 falhas em 281 execuções (escrito à mão)\n", encoding="utf-8")
    assert "diferente do que evals/results/live_*.json gera" in problems()
    _live(res, "official", [_row(1, "official"), _row(2, "official", ok=False)])  # bateria nova, arquivo velho
    fm.write_text(failure_modes.generate(tmp_path / "vazio") or "velho", encoding="utf-8")
    assert "diferente" in problems()
    shutil.rmtree(res)
    assert "sem evals/results/live_*.json que o gere" in problems()


# --- 3. TIMESHEET gerado: --clock-end, antes do relógio e o --check contra o git log ---------------------------------

def test_timesheet_clock_end_by_sha_declares_pre_scaffold_and_post_clock_commits(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _commit(tmp_path, "chore: repositório", date="2026-11-03T12:00:00+00:00")
    _commit(tmp_path, "chore: scaffold from kit", date="2026-11-03T13:45:00+00:00")
    end = _commit(tmp_path, "readme: entrega | T+47", date="2026-11-03T14:32:00+00:00")
    _commit(tmp_path, "fix: rodada seguinte", date="2026-11-03T21:20:00+00:00")
    monkeypatch.setattr(timesheet, "ROOT", tmp_path)
    out = tmp_path / "docs" / "TIMESHEET.md"
    assert timesheet.main(["--clock-end", end]) == 0  # padrão: docs/TIMESHEET.md da raiz
    text = out.read_text(encoding="utf-8")
    assert "**47 min**" in text and f"ao commit {end} (--clock-end)" in text
    assert "2 commits dentro do relógio, 1 depois e 1 antes (declarados abaixo)" in text
    rows = [line for line in text.splitlines() if fill_readme._TIMESHEET_ROW.match(line)]
    assert [r.rsplit("|", 2)[1].strip() for r in rows] == ["antes do relógio", "dentro", "dentro", "pós-relógio"]
    assert "readme: entrega \\| T+47" in text  # `|` do título não abre coluna
    # sem --clock-end e sem tag: fecha no último commit (o relógio de verdade termina no commit do final.sh)
    assert timesheet.main(["--out", str(out)]) == 0
    assert "3 commits dentro do relógio, 0 depois e 1 antes" in out.read_text(encoding="utf-8")
    assert timesheet.main(["--clock-end", "nao-existe", "--out", str(out)]) == 2


def test_check_counts_timesheet_rows_against_git_log_tolerating_the_last_generated_commit(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _commit(tmp_path, "chore: repositório", date="2026-11-03T12:00:00+00:00")
    _commit(tmp_path, "chore: scaffold from kit", date="2026-11-03T13:45:00+00:00")
    _commit(tmp_path, "feat: domínio", files={"src/app.py": "x = 1\n"}, date="2026-11-03T14:00:00+00:00")
    readme = tmp_path / "README.md"

    def problems() -> str:
        return " | ".join(p for p in fill_readme.check(readme, tmp_path / "results", root=tmp_path)
                          if "TIMESHEET" in p)

    readme.write_text("# P\n", encoding="utf-8")
    assert problems() == ""  # sem o arquivo (kit, ou antes do final.sh): nada a conferir
    monkeypatch.setattr(timesheet, "ROOT", tmp_path)
    assert timesheet.main([]) == 0
    sheet = (tmp_path / "docs" / "TIMESHEET.md").read_text(encoding="utf-8")
    assert problems() == ""
    # o último commit só com gerados (o do final.sh, que gera o TIMESHEET antes de commitar) fica de fora
    _commit(tmp_path, "readme: números e linha do tempo", files={"README.md": "# P\nfim\n"},
            date="2026-11-03T14:30:00+00:00")
    assert problems() == ""
    # código depois dele: o TIMESHEET ficou velho
    _commit(tmp_path, "fix: depois do readme", files={"src/app.py": "x = 2\n"}, date="2026-11-03T14:40:00+00:00")
    assert "docs/TIMESHEET.md com 3 commits, o git tem 5 (o último mexeu em src/app.py)" in problems()
    assert sheet.count("| dentro |") == 2 and sheet.count("| antes do relógio |") == 1


def test_generated_docs_are_in_readme_only_and_in_final_sh():
    """O final.sh aceita sujos e commita por último exatamente os gerados do fill_readme (e os dois novos)."""
    assert {"docs/FAILURE_MODES.md", "docs/TIMESHEET.md"} <= fill_readme.README_ONLY
    final = (ROOT / "scripts" / "final.sh").read_text(encoding="utf-8")
    generated = re.search(r"^GENERATED='(.+)'$", final, re.M).group(1).replace("\\.", ".").split("|")
    assert set(generated) == fill_readme.README_ONLY
    added = re.search(r"^for f in (.+); do$", final, re.M).group(1).split()
    assert set(added) | {"README.md", "docs/ENTREGA.md"} == fill_readme.README_ONLY


def test_live_eval_ps1_generates_failure_modes_before_the_readme():
    ps1 = (ROOT / "scripts" / "live_eval.ps1").read_text(encoding="utf-8-sig")
    tail = ps1.split("if ($SemReadme) { exit 0 }")[1]  # o README e os docs gerados são da sessão principal
    assert tail.index("-m evals.failure_modes") < tail.index("scripts/fill_readme.py")


FAKE_PY = r"""#!/usr/bin/env bash
echo "$*" >> "{log}"
if [[ "$1" == "-m" && "$2" == "evals.failure_modes" ]]; then mkdir -p docs; echo "modos" > docs/FAILURE_MODES.md
elif [[ "$1" == "scripts/timesheet.py" ]]; then mkdir -p docs; echo "relógio: $*" > docs/TIMESHEET.md
elif [[ "$1" == "scripts/fill_readme.py" && "$2" == "--check" ]]; then :
elif [[ "$1" == "scripts/fill_readme.py" ]]; then echo "números" >> README.md; echo "tabelas" >> docs/RESULTS.md
elif [[ "$1" == "scripts/delivery_message.py" ]]; then out="${{@: -1}}"; mkdir -p "$(dirname "$out")"; echo ok > "$out"
fi
exit 0
"""


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="sem bash POSIX")
def test_final_sh_refuses_other_changes_and_commits_only_the_generated_docs_last(tmp_path):
    """A garantia do final.sh: só arquivos gerados podem estar sujos, e o último commit (enviado) leva só eles, agora
    com o FAILURE_MODES e o TIMESHEET gerados antes do README e o --clock-end repassado ao TIMESHEET."""
    origin, repo, log = tmp_path / "origin.git", tmp_path / "repo", tmp_path / "calls.log"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True, capture_output=True)
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "scripts").mkdir()
    shutil.copy(ROOT / "scripts" / "final.sh", repo / "scripts" / "final.sh")
    scaffold = _commit(repo, "chore: scaffold", files={"README.md": "# P\n", "src/app.py": "x = 1\n",
                                                       "docs/RESULTS.md": "r\n", "docs/FAILURE_MODES.md": "velho\n"})
    _git(repo, "remote", "add", "origin", str(origin))
    fake = tmp_path / "fakepy"
    fake.write_text(FAKE_PY.format(log=log), encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, **GIT_ENV, "PY": str(fake)}

    def final(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([BASH, str(repo / "scripts" / "final.sh"), *args], cwd=repo, capture_output=True,
                              text=True, encoding="utf-8", timeout=60, env=env)

    assert final("--clock-end").returncode != 0 and "precisa do sha" in final("--clock-end").stderr
    assert final("--xyz").returncode == 64 and not log.exists()  # argumento errado para antes de gerar qualquer coisa
    (repo / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")  # código sem commit: recusa
    out = final()
    assert out.returncode == 1 and "Commite antes" in out.stdout and "src/app.py" in out.stdout
    assert not log.exists() and _git(repo, "rev-list", "--count", "HEAD") == "1"
    (repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "docs" / "FAILURE_MODES.md").write_text("sujo de uma bateria\n", encoding="utf-8")  # gerado: pode
    out = final("--clock-end", scaffold)
    assert out.returncode == 0, out.stdout + out.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    order = ["-m evals.failure_modes", f"scripts/timesheet.py --clock-end {scaffold}", "scripts/fill_readme.py",
             "scripts/fill_readme.py --check"]
    assert [c for c in calls if c in order] == order  # gerados antes do commit; a conferência depois dele
    last = _git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert set(last) <= fill_readme.README_ONLY
    assert {"README.md", "docs/RESULTS.md", "docs/FAILURE_MODES.md", "docs/TIMESHEET.md"} <= set(last)
    assert _git(origin, "log", "-1", "--format=%s", "main") == _git(repo, "log", "-1", "--format=%s")
    assert (repo / "var" / "ENTREGA_final.md").exists() and not _git(repo, "status", "--porcelain",
                                                                      "--untracked-files=no")


# --- 5. "Como ler" gerado no topo de cada bloco denso do RESULTS, sem número à mão -----------------------------------

# nomes de métrica que carregam dígito (IC95, p95, hit@3, AC1...) não são número digitado
_METRIC_NAMES = re.compile(r"IC95|p50|p95|hit@\d|Recall@[\dk]|MRR@\d|AC1")


def _typed_numbers(text: str) -> list[str]:
    return re.findall(r"\d+", _METRIC_NAMES.sub("", text))


def test_how_to_read_texts_carry_no_hand_typed_number():
    reports = [{"live": True, "split": "official"}, {}, {"gate_resolved": {"target": 0.9}},
               {"gate_red_team": {"enforced": True}}]
    texts = [*fill_readme.HOW_TO_READ.values(), *(run_evals.how_to_read(r) for r in reports)]
    assert all(t and not _typed_numbers(t) for t in texts), [t for t in texts if _typed_numbers(t)]
    # o que reprova sai do relatório (a mesma conta de `passed`): o red team só entra quando vale
    assert "red team" not in run_evals.how_to_read({}) and "red team" in run_evals.how_to_read(reports[3])
    assert "oficiais resolvidas" in run_evals.how_to_read(reports[2])


def test_every_dense_results_block_opens_with_how_to_read_and_placeholders_do_not(tmp_path):
    results, data = tmp_path / "results", tmp_path / "data"
    empty = {tag: fn(tmp_path / "vazio") for tag, fn in
             (("eval-live", fill_readme.live_block), ("judge", fill_readme.judge_block),
              ("human", fill_readme.human_block), ("replan", fill_readme.replan_block),
              ("trace", fill_readme.trace_block))}
    empty["retrieval"] = fill_readme.retrieval_block(tmp_path / "vazio", data=tmp_path / "vazio")
    assert not [t for t, body in empty.items() if "Como ler" in body]  # "não rodado" fica como está

    report = run_evals.run(out=results / "latest.json")  # offline do kit (fixture)
    live = {**report, "live": True, "status": "complete", "spent_usd": 0.1, "max_usd": 1.0, "split": "replan"}
    live["rows"] = [{**r, "steps": [{"agent": "faq", "status": "ok", "ms": 900.0, "tools": []}], "ms": 1000.0}
                    for r in report["rows"]]
    (results / "live_replan.json").write_text(json.dumps(live), encoding="utf-8")
    (results / "judge.json").write_text(json.dumps({
        "status": "ran", "model": "m", "live_files": ["live_replan.json"], "spent_usd": 0.1, "cases": 1,
        "grounded_rate": 1.0, "helpful_rate": 1.0, "mean_score": 5.0, "by_split": {},
        "calibration": {"cases": 2, "agreement": 1.0, "cohen_kappa": 1.0, "misses": [], "by_split": {}}}),
        encoding="utf-8")
    (results / "human_review.json").write_text(json.dumps({
        "rotulos": 2, "humano_passa": 2, "automatico_passa": 2, "concordancia": 1.0, "kappa": None}),
        encoding="utf-8")
    data.mkdir()
    (data / "retriever.json").write_text(json.dumps({
        "gold": "g.jsonl", "chosen_at": "t", "git_sha": "abc", "chosen": "bm25", "measured": {"bm25": {
            "recall@3": 0.5, "mrr": 0.6, "hit@3": 0.7, "ndcg@3": 0.5, "page": {"hit@3": 0.9},
            "latency_ms": {"p50": 1, "p95": 2}}}}), encoding="utf-8")
    blocks = {"eval": fill_readme.offline_block(results), "eval-live": fill_readme.live_block(results),
              "trace": fill_readme.trace_block(results), "judge": fill_readme.judge_block(results),
              "human": fill_readme.human_block(results), "retrieval": fill_readme.retrieval_block(results, data=data),
              "replan": fill_readme.replan_block(results)}
    for tag, body in blocks.items():
        first = body.split("\n\n")[1 if tag == "eval" else 0]  # o offline abre com a linha do modo/provedor
        assert first.startswith("**Como ler:**"), (tag, body[:200])
    # a origem do gabarito do juiz sai do judge.json: sem `labels_origin` (ou "spec"), não se diz que é de pessoas
    assert "contra o gabarito da SPEC, não contra pessoas" in blocks["judge"]
    judge = json.loads((results / "judge.json").read_text(encoding="utf-8"))
    judge["calibration"]["labels_origin"] = "human"
    (results / "judge.json").write_text(json.dumps(judge), encoding="utf-8")
    assert "A calibração abaixo é contra rótulos de pessoas" in fill_readme.judge_block(results)
    # todo bloco que o docs/RESULTS.md hospeda tem o seu "como ler" (bloco novo lá pede a frase dele)
    template = (ROOT / "docs" / "RESULTS.md").read_text(encoding="utf-8")
    hosted = set(re.findall(r"<!-- ([\w-]+):begin -->", template))
    assert hosted <= set(fill_readme.HOW_TO_READ) | {"eval"} == set(blocks)
    # e o render continua idempotente com a linha nova (o --check compara o bloco inteiro)
    text = "\n".join(f"<!-- {t}:begin -->\n<!-- {t}:end -->" for t in ("eval", "eval-live", "judge", "replan",
                                                                        "timeline"))
    once = fill_readme.render(text, results, root=tmp_path)
    assert once == fill_readme.render(once, results, root=tmp_path) and once.count("**Como ler:**") == 4
    assert not fill_readme._check_blocks(once, results)
