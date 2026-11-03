"""Scripts de evidência do v5: FAILURE_MODES, validação humana, DEMO.md e TIMESHEET (dados falsos, sem rede)."""

import json
import subprocess
from datetime import datetime, timedelta, timezone

from app.config import ROOT


def _row(i, split="official", ok=True, run=0, **extra):
    checks = {"intent": True, "numbers": ok, "language": True}
    return {
        "id": f"{split}-{i:02d}",
        "split": split,
        "message": f"pergunta {i}",
        "answer": f"resposta {i}\nlinha 2",
        "checks": checks,
        "run": run,
        "got_intent": "knowledge",
        "expected_intent": "knowledge",
        "route": ["router", "faq"],
        "tool_calls": [{"name": "get_settlements", "args": {}, "ok": True}],
        "unsupported_numbers": [] if ok else ["99"],
        "source_ids": ["s1"],
        "sources": [{"id": "s1", "url": "https://x/y"}],
        "cost_usd": 0.01,
        "ms": 1000.0,
        **extra,
    }


def _write(results, name, rows, **extra):
    results.mkdir(parents=True, exist_ok=True)
    (results / name).write_text(
        json.dumps({"rows": rows, "provider": "anthropic", "status": "complete", "spent_usd": 0.1, **extra}),
        encoding="utf-8",
    )


def test_failure_modes_groups_by_first_failed_check(tmp_path):
    from evals import failure_modes

    rows = [_row(1, ok=False), _row(1, ok=False, run=1), _row(2), _row(3, ok=False)]
    _write(tmp_path, "live_official.json", rows)
    modes = failure_modes.collect(tmp_path)
    assert set(modes) == {"numbers"} and modes["numbers"]["runs"] == 3 and len(modes["numbers"]["casos"]) == 2
    text = failure_modes.render(modes, len(rows))
    assert "`numbers`" in text and "3 falhas em 4 execuções" in text and "99" in text


def test_human_label_roundtrip_and_kappa(tmp_path):
    from evals import label

    rows = [_row(i, ok=i % 2 == 0) for i in range(10)]
    _write(tmp_path, "live_official.json", rows)
    csv_path, out = tmp_path / "labels.csv", tmp_path / "human_review.json"
    assert label.export(10, results=tmp_path, path=csv_path) == 10
    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert "numbers" not in header and "automatico" not in header  # rotulagem às cegas: sem o veredito automático
    # o dono concorda com o automático em 8 de 10
    pairs = [f"official-{i:02d}={'pass' if i % 2 == 0 else 'fail'}" for i in range(8)] + [
        "official-08=fail:número errado",
        "official-09=pass:estava certo",
    ]
    assert label.mark(pairs, path=csv_path) == 10
    rep = label.report(results=tmp_path, path=csv_path, out=out)
    assert rep["rotulos"] == 10 and rep["concordancia"] == 0.8 and rep["kappa"] == 0.6
    assert {d["id"] for d in rep["divergencias"]} == {"official-08", "official-09"} and out.exists()
    assert "abaixo de 20" in rep["aviso"]


def test_label_sample_is_reproducible_and_stratified():
    from evals import label

    rows = [_row(i, split=s) for s in ("official", "memory", "replan") for i in range(6)]
    a, b = label.sample(rows, 6), label.sample(rows, 6)
    assert [r["id"] for r in a] == [r["id"] for r in b]
    assert {r["split"] for r in a} == {"official", "memory", "replan"}


def test_demo_md_is_generated_from_live_json(tmp_path):
    from scripts import demo_md

    report = {
        "rows": [_row(1), _row(1, run=1), _row(2, ok=False)],
        "provider": "anthropic",
        "status": "complete",
        "spent_usd": 0.5,
        "stability": {"runs": 3, "pass_at_1": 0.5, "pass_hat_k": 0.3, "unstable": ["official-02"]},
    }
    text = demo_md.render(report, "official", "abc1234", "01/11/2026 20:00 UTC")
    assert text.count("## official-") == 2  # 1ª rodada de cada caso, sem repetir
    assert "abc1234" in text and "> resposta 1" in text and "falhou: numbers" in text and "99" in text


def test_timesheet_marks_post_clock_commits(tmp_path):
    from scripts import timesheet

    t = datetime(2026, 11, 1, 20, 0, 0, tzinfo=timezone(timedelta(hours=0)))
    rows = [
        {"sha": f"c{i}", "full": f"c{i}", "t": t + timedelta(minutes=m), "author": "dev", "subject": s, "files": 2}
        for i, (m, s) in enumerate([(0, "chore: scaffold"), (10, "feat: x"), (30, "readme"), (45, "fix: depois")])
    ]
    text = timesheet.render(rows, rows[0]["t"], rows[2]["t"], "tags clock-start/clock-end")
    assert "30 min" in text and text.count("pós-relógio") >= 2 and "Maior rajada" in text
    n, _ = timesheet.biggest_burst(rows, minutes=15)
    assert n == 2


def test_timesheet_reads_a_real_git_repo(tmp_path):
    from scripts import timesheet

    def git(*a):
        subprocess.run(
            ["git", *a],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            env={
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t",
                "PATH": "/usr/bin:/bin",
            },
        )

    git("init", "-q")
    (tmp_path / "a").write_text("1")
    git("add", ".")
    git("commit", "-qm", "um")
    git("tag", "clock-start")
    (tmp_path / "b").write_text("2")
    git("add", ".")
    git("commit", "-qm", "dois")
    rows = timesheet.commits(tmp_path)
    assert [r["subject"] for r in rows] == ["um", "dois"] and timesheet.tag_time("clock-start", tmp_path) is not None
    assert ROOT.exists()


def test_label_page_has_the_same_sample_and_import_writes_one_csv_per_rater(tmp_path):
    import importlib.util

    from evals import label

    spec = importlib.util.spec_from_file_location("label_page", ROOT / "scripts" / "label_page.py")
    page = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(page)
    rows = [_row(i, ok=i % 2 == 0, context=f"fonte {i}</script><b>x</b>") for i in range(6)]
    _write(tmp_path, "live_official.json", rows)
    items = page.items(6, results=tmp_path)
    assert [i["id"] for i in items] == [r["id"] for r in label.sample(label.load_rows(tmp_path), 6)]
    assert all("checks" not in i and "numbers" not in json.dumps(i) for i in items)  # sem veredito automático
    html = page.render(items, ["Matheus", "Bianca"])
    assert "</script><b>" not in html and "Conferência de respostas" in html  # dado não fecha o <script>
    dump = tmp_path / "rotulos.json"
    dump.write_text(json.dumps({"documents": [
        {"id": "u1", "data": {"rater": "Matheus", "marks": {i["id"]: {"v": "pass"} for i in items}}},
        {"id": "u2", "data": {"rater": "Bianca", "marks": {**{i["id"]: {"v": "pass"} for i in items[:5]},
                                                            items[5]["id"]: {"v": "fail", "tipo": "invented_number",
                                                                             "nota": "taxa: errada"}}}},
    ]}), encoding="utf-8")
    done = label.import_page(dump, results=tmp_path, base=tmp_path)
    assert done == {"Matheus": 6, "Bianca": 6}
    bia = {r["id"]: r for r in label.read_labels(label.csv_path("Bianca", tmp_path))}
    assert bia[items[5]["id"]]["humano"] == "fail" and bia[items[5]["id"]]["tipo_falha"] == "invented_number"
    assert set(label.label_files(tmp_path)) == {"matheus", "bianca"}


def test_label_page_turns_tool_json_into_tables_and_hides_system_notes():
    import importlib.util

    spec = importlib.util.spec_from_file_location("label_page", ROOT / "scripts" / "label_page.py")
    page = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(page)
    row = {"tool_calls": [{"name": "get_transactions"}], "sources": [{"title": "FAQ", "url": "https://x/faq"}],
           "context": "\n".join([
               '- {"ok": true, "data": {"count": 1, "transactions": [{"transaction_id": "TX1", "date": "2026-11-02",'
               ' "amount": 210.0, "contestable": false}]}, "nota_calculo": "x"}',
               "- FAQ: O prazo é de 2 dias úteis.",
               "- [memória da conversa] Fatos da conversa",
               "- [policy:capabilities] Capacidades",
               "- Ações que o assistente pode PROPOR: restart_terminal",
           ])}
    blocks = page.evidence_blocks(row)
    data, text, memory, rules = blocks
    assert data["tables"][0]["columns"] == ["transação", "data", "valor (R$)", "pode contestar"]
    assert data["tables"][0]["rows"] == [["TX1", "02/11/2026", "210", "não"]] and ["quantidade", "1"] in data["fields"]
    assert text == {"kind": "text", "title": "FAQ", "text": "O prazo é de 2 dias úteis.", "url": "https://x/faq"}
    assert memory["kind"] == "memory"
    assert rules == {"kind": "rules", "text": "Ações que o assistente pode PROPOR: restart_terminal"}


def test_copied_answers_text_becomes_the_raters_csv(tmp_path):
    from evals import label

    rows = [_row(i) for i in range(3)]
    _write(tmp_path, "live_official.json", rows)
    text = "CONFERENCIA abc123 Bianca\nofficial-00=pass\nofficial-01=fail:invented_number\nofficial-02=skip\n"
    assert label.import_text(text, results=tmp_path, base=tmp_path) == {"Bianca": 2}  # "skip" fica fora da conta
    got = {r["id"]: r for r in label.read_labels(label.csv_path("Bianca", tmp_path))}
    assert got["official-00"]["humano"] == "pass" and got["official-01"]["tipo_falha"] == "invented_number"
    assert got["official-02"]["humano"] == ""
