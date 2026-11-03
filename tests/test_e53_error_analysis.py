"""E53 — análise de erros em traces ao vivo: rascunho do modelo, revisão do dono com edições contadas, modos com uma
checagem binária cada (replay offline), separada da rotulagem cega."""
import json

import pytest

from app.llm import LLMReply
from evals import error_analysis as ea
from evals import label, run_evals
from scripts import label_page

LONG = "Tabela de planos: " + "linha de preço " * 200 + "Plano Ouro R$ 79,90."


def _row(i, split="official", **kw):
    base = {"id": i, "split": split, "run": 0, "message": f"pergunta {i}?", "answer": "Resposta com fonte.",
            "checks": {"intent": True}, "route": ["router", "faq"], "source_ids": ["d1"],
            "sources": [{"id": "d1", "title": "T", "url": "https://x.test/t"}], "tool_calls": [], "context": "",
            "handoff_required": False, "unsupported_numbers": [], "expected_language": "pt",
            "language_detected": "pt"}
    return {**base, **kw}


@pytest.fixture
def results(tmp_path, monkeypatch):
    cases = [{"id": "o1", "split": "official", "message": "q", "expect": {"intent": "faq", "facts": ["79,90"]}},
             {"id": "o2", "split": "official", "message": "q", "expect": {"intent": "faq"}},
             {"id": "o3", "split": "official", "message": "q", "expect": {"intent": "faq"}},
             {"id": "h1", "split": "heldout", "message": "q", "expect": {"intent": "faq"}}]
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(json.dumps(c) for c in cases), encoding="utf-8")
    monkeypatch.setattr(run_evals, "CASES", path)
    d = tmp_path / "results"
    d.mkdir()
    rows = [_row("o1", answer="Passei para um atendente humano.", handoff_required=True, context=LONG,
                 route=["router", "faq", "escalation"], checks={"intent": True, "resolved": False}),
            _row("o2"), _row("o3", unsupported_numbers=["42"], checks={"intent": True, "numbers": False})]
    (d / "live_official.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    (d / "live_heldout.json").write_text(json.dumps({"rows": [_row("h1", split="heldout")]}), encoding="utf-8")
    return d


class DraftLLM:
    model = "claude-opus-5-5"

    def __init__(self):
        self.prompts = []

    def complete(self, system, messages, max_tokens=1024, schema=None):
        p = messages[0]["content"]
        self.prompts.append(p)
        bad = "Passei para um atendente" in p
        return LLMReply(json.dumps({"verdict": "fail" if bad else "pass",
                                    "mode": "escalou_sem_precisar" if bad else "",
                                    "reason": "foi ao humano com o\npreço na evidência" if bad else "ok"}), self.model)


def test_export_drafts_with_full_evidence_and_leaves_heldout_out(results, tmp_path):
    fake, csv_path = DraftLLM(), tmp_path / "ea.csv"
    assert ea.export(60, results, csv_path, llm=fake) == 3  # o held-out não entra no ajuste
    rows = {r["chave"]: r for r in ea.read(csv_path)}
    assert set(rows) == {"o1#0", "o2#0", "o3#0"}
    assert rows["o1#0"]["rascunho"] == "fail" and rows["o1#0"]["motivo_rascunho"] == "foi ao humano com o preço na " \
                                                                                    "evidência"  # uma linha
    assert rows["o1#0"]["contexto"] == LONG  # evidência inteira, sem corte a 1.500 caracteres
    assert any("Plano Ouro R$ 79,90" in p and "79,90" in p.split("Fatos de referência")[1] for p in fake.prompts)
    assert rows["o1#0"]["origem_rascunho"] == "claude-opus-5-5" and rows["o1#0"]["revisao"] == ""


def test_draft_without_llm_comes_from_the_mode_checks(results, tmp_path):
    ea.export(60, results, tmp_path / "ea.csv")
    rows = {r["chave"]: r for r in ea.read(tmp_path / "ea.csv")}
    assert rows["o1#0"]["modo_rascunho"] == "escalou_sem_precisar"
    assert rows["o3#0"]["modo_rascunho"] == "numero_sem_base"
    assert rows["o2#0"]["rascunho"] == "pass" and rows["o2#0"]["origem_rascunho"] == "checks"


def test_owner_review_counts_edits_and_modes_get_one_check_each(results, tmp_path):
    csv_path, out = tmp_path / "ea.csv", tmp_path / "ea.json"
    ea.export(60, results, csv_path, llm=DraftLLM())
    got = ea.review(["o1#0=ok", "o2#0=fail:resposta_vaga não diz o valor",
                     "o3#0=fail:numero_sem_base o 42 não está na fonte", "zz#0=ok"], csv_path)
    assert got == {"reviewed": 3, "ignored": 1}
    rep = ea.report(csv_path, results, out)
    # o1 aceito; o2 editado (passa → falha); o3 editado (passa → falha com modo)
    assert (rep["reviewed"], rep["edits"], rep["edited"]) == (3, 2, ["o2#0", "o3#0"])
    assert rep["modes"]["escalou_sem_precisar"]["check"] == "check_escalated"
    assert rep["modes"]["escalou_sem_precisar"]["check_tpr"] == 1.0
    assert rep["modes"]["numero_sem_base"]["check_tpr"] == 1.0 and rep["modes"]["numero_sem_base"]["check_tnr"] == 1.0
    assert rep["unchecked_modes"] == ["resposta_vaga"]  # modo novo do dono sem checagem: declarado
    assert json.loads(out.read_text(encoding="utf-8"))["edits"] == 2
    md = ea.render(rep)
    assert "editou **2**" in md and "sem checagem" in md


def test_same_decision_as_the_draft_is_not_an_edit(results, tmp_path):
    csv_path = tmp_path / "ea.csv"
    ea.export(60, results, csv_path)
    ea.review(["o3#0=fail:numero_sem_base", "o2#0=pass"], csv_path)
    rows = {r["chave"]: r for r in ea.read(csv_path)}
    assert rows["o3#0"]["revisao"] == rows["o2#0"]["revisao"] == "aceito"
    assert rows["o3#0"]["motivo"] == rows["o3#0"]["motivo_rascunho"]


def test_mode_checks_replay_offline_over_another_recording(results):
    rows = [_row("o1", answer="Não encontrei essa informação.", context=LONG), _row("o2", language_detected="en")]
    (results / "replay_official.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    rep = ea.run_checks(results, "replay_*.json")
    assert rep["rows"] == 2
    assert rep["modes"]["diz_que_falta_o_que_a_evidencia_tem"]["keys"] == ["o1#0"]
    assert rep["modes"]["idioma_errado"]["keys"] == ["o2#0"]
    assert rep["modes"]["numero_sem_base"]["hits"] == 0
    assert ea.main(["--checks", "--results", str(results), "--pattern", "replay_*.json"]) == 0


def test_blind_label_page_never_carries_the_draft(results, tmp_path):
    csv_path = tmp_path / "ea.csv"
    ea.export(60, results, csv_path, llm=DraftLLM())
    page = label_page.render(label_page.items(10, results=results), ["Ana", "Bia"])
    assert "foi ao humano com o" not in page and "rascunho" not in page.lower()
    assert not {"rascunho", "modo_rascunho", "motivo_rascunho"} & set(label.FIELDS)
