"""R11-C1 — juiz honesto.

Rejulgamento só pela data, nunca pelo veredito (rodada 10: a regra antiga levava junto os reprovados sem data, e o
oficial 19/30 do resumo commitado virava 30/30 sem antes → depois à vista): cada rejulgado guarda a 1ª passada, o
judge.json traz o bloco `rejudge` e o resumo de cada live_*.json é reescrito, com o antigo em `judge_first_pass`.
Validação contra pessoas sobre o MESMO texto: a página congela o texto, o veredito e a bateria, e o rótulo de outro
texto sai da conta, listado (35 dos 37 rótulos da rodada 10 eram de outra bateria). Held-out sem `reason`."""
import json
from pathlib import Path

import pytest

from app.llm import LLMError, LLMReply
from evals import judge, label, run_evals
from scripts import fill_readme, label_page

# 02h02 UTC de 4/11 = 23h02 de 3/11 em São Paulo: a bateria é do dia 3 (o juiz com o relógio UTC lia o dia 4)
RECORDED = "2026-11-04T02:02:50Z"
ROWS = [
    {"id": "d1", "split": "official", "run": 0, "message": "Quando cai o depósito?",
     "answer": "Seu depósito cai amanhã, 04/11.", "context": "- Agenda: depósito em 2026-11-04.",
     "checks": {"numbers": True}},
    {"id": "d2", "split": "official", "run": 0, "message": "E a venda de anteontem?",
     "answer": "A venda de 01/11 foi aprovada.", "context": "- Vendas: 2026-11-01 aprovada.",
     "checks": {"numbers": True}},
    {"id": "u1", "split": "official", "run": 0, "message": "Qual a taxa do crédito?",
     "answer": "A taxa do crédito é 3,19%.", "context": "- Taxas: crédito 3,15%.", "checks": {"numbers": False}},
    {"id": "u2", "split": "official", "run": 0, "message": "Qual a taxa do débito?",
     "answer": "A taxa do débito é 1,89%.", "context": "- Taxas: débito 1,89%.", "checks": {"numbers": True}},
]
CANARY_ANSWERS = {c["answer"] for c in judge.CANARIES}


class Fake:
    """Juiz falso: reprova a resposta com um dos trechos de `bad` (e os canários), recusa a de `refuse`."""

    model = "claude-opus-5-5"

    def __init__(self, bad=(), refuse=()):
        self.bad, self.refuse, self.answers = tuple(bad), tuple(refuse), []

    def complete(self, system, messages, max_tokens=1024, schema=None):
        answer = messages[0]["content"].split("Resposta: ", 1)[-1]
        self.answers.append(answer)
        if any(s in answer for s in self.refuse):
            raise LLMError("refusal: o modelo não julga este caso", kind="refusal")
        bad = answer in CANARY_ANSWERS or any(s in answer for s in self.bad)
        return LLMReply(json.dumps({"grounded": not bad, "helpful": True, "language_ok": True,
                                    "leaks_other_customer": False, "score": 2 if bad else 5,
                                    "failure_type": "unsupported_claim" if bad else "none",
                                    "reason": f"motivo de {answer[:12]}"}), self.model)


def _live(res, rows=ROWS, sha="aaa1111"):
    path = res / "live_official.json"
    path.write_text(json.dumps({"git_sha": sha, "recorded_at": RECORDED, "rows": rows}), encoding="utf-8")
    return path


def _first_pass(tmp_path):
    """A bateria julgada junto (o resumo `judge` do live_*.json, como evals.run_evals grava), por um juiz de antes do
    registro da data: d1 e u1 reprovados, e nenhum veredito diz que dia o juiz usou."""
    res = tmp_path / "results"
    res.mkdir(parents=True, exist_ok=True)
    live = _live(res)
    rep = judge.judge_into(Fake(bad=("amanhã", "3,19%")), live, out=res / "judge.json")
    rep["verdicts"] = [{k: v for k, v in x.items() if k != "judge_date"} for x in rep["verdicts"]]
    (res / "judge.json").write_text(json.dumps(rep), encoding="utf-8")
    data = json.loads(live.read_text(encoding="utf-8"))
    data["judge"] = judge.split_summary(rep, live.name)
    live.write_text(json.dumps(data), encoding="utf-8")
    return res, rep


# 1. rejulgamento só pela data -----------------------------------------------------------------------------------------
def test_rejudge_by_date_only_keeps_every_undated_verdict_and_saves_the_first_pass(tmp_path):
    res, first = _first_pass(tmp_path)
    today = Fake()  # o juiz de agora aprova tudo: quem decide o que volta é a data, nunca o veredito
    rep = judge.rejudge_dated(today, out=res / "judge.json", results=res)
    assert sorted(today.answers) == sorted([ROWS[0]["answer"], ROWS[1]["answer"]])  # só as datadas; confiança reusada
    by, old = {v["id"]: v for v in rep["verdicts"]}, {v["id"]: v for v in first["verdicts"]}
    assert by["u1"] == old["u1"] and by["u1"]["grounded"] is False  # reprovado sem data: não ganha 2ª chance
    assert by["u2"] == old["u2"]  # aprovado sem data: não muda
    assert by["d1"]["grounded"] is True and by["d1"]["first_pass"]["grounded"] is False
    assert by["d2"]["first_pass"]["grounded"] is True  # o aprovado com data também volta (simétrico)
    assert (by["d1"]["rejudge_reason"], by["d2"]["rejudge_reason"]) == ("data_relativa", "data_explicita")
    assert by["d1"]["judge_date"] == "2026-11-03" and "judge_date" not in by["d1"]["first_pass"]
    rj = json.loads((res / "judge.json").read_text(encoding="utf-8"))["rejudge"]
    assert (rj["rejulgados"], rj["mantidos"], rj["mantidos_reprovados"]) == (2, 2, 1)
    assert rj["por_motivo"] == {"data_relativa": 1, "data_explicita": 1}
    assert rj["primeira_passada"] == {"aprovados": 1, "reprovados": 1}
    assert rj["viraram"] == {"reprovado_para_aprovado": 1, "aprovado_para_reprovado": 0}
    assert rj["por_split"]["official"] == {"rejulgados": 2, "antes": {"casos": 4, "grounded": 2, "helpful": 4},
                                           "depois": {"casos": 4, "grounded": 3, "helpful": 4}}
    assert rj["ALL"] == rj["por_split"]["official"] and "só pela data, nunca pelo veredito" in rj["regra"]
    live = json.loads((res / "live_official.json").read_text(encoding="utf-8"))
    assert live["judge"] == {**judge.split_summary(rep, "live_official.json"), "rejulgados": 2}
    fp = live["judge_first_pass"]
    assert (fp["grounded"], fp["verdicts"]) == (2, 4) and fp["data_do_juiz"].startswith("não gravada")
    assert "--rejudge-dated" in fp["trocado_por"]
    assert judge.coherence_problems(res) == []
    again = Fake()
    judge.rejudge_dated(again, out=res / "judge.json", results=res)
    assert again.answers == []  # já julgados com o dia do negócio: rejulgar seria só um novo sorteio
    assert json.loads((res / "live_official.json").read_text(encoding="utf-8"))["judge_first_pass"] == fp


def test_rejudge_never_drops_a_verdict_the_judge_refuses_or_the_budget_cuts(tmp_path):
    res, first = _first_pass(tmp_path)
    rep = judge.rejudge_dated(Fake(refuse=("amanhã",)), out=res / "judge.json", results=res)
    by = {v["id"]: v for v in rep["verdicts"]}
    assert len(rep["verdicts"]) == 4 and rep["judge_refused"] == []  # o denominador não muda
    assert by["d1"]["rejudge_refused"] is True and by["d1"]["grounded"] is False and "first_pass" not in by["d1"]
    res2, _ = _first_pass(tmp_path / "b")
    rep = judge.rejudge_dated(Fake(), out=res2 / "judge.json", results=res2, max_usd=0.0)
    assert rep["status"] == "aborted_max_usd" and rep["cases"] == 4 and "rejudge" not in rep


def test_live_summary_is_the_one_run_evals_writes(tmp_path, monkeypatch):
    res, first = _first_pass(tmp_path)
    monkeypatch.setattr(judge, "judge_into", lambda llm, path, out=None, max_usd=None: first)
    got = run_evals.judge_after_split(lambda: None, res / "live_official.json", out=res / "judge.json")
    assert got == judge.split_summary(first, "live_official.json")  # o mesmo resumo nos dois caminhos


def test_check_flags_a_contradicting_summary_and_verdicts_of_another_text(tmp_path, monkeypatch):
    res, _ = _first_pass(tmp_path)
    assert judge.coherence_problems(res) == []
    live = res / "live_official.json"
    data = json.loads(live.read_text(encoding="utf-8"))
    data["judge"]["grounded"] = 4  # o resumo diz 4/4; o judge.json, 2/4
    live.write_text(json.dumps(data), encoding="utf-8")
    probs = judge.coherence_problems(res)
    assert len(probs) == 1 and "live_official.json" in probs[0] and "4/4" in probs[0] and "2/4" in probs[0]
    monkeypatch.setattr(judge, "RESULTS_DIR", res)
    assert judge.main(["--check"]) == 1
    data["judge"]["grounded"] = 2
    head = json.loads((res / "judge.json").read_text(encoding="utf-8"))
    head["verdicts"][0]["first_pass"] = dict(head["verdicts"][0])  # rejulgado, sem o resumo da 1ª passada guardado
    (res / "judge.json").write_text(json.dumps(head), encoding="utf-8")
    live.write_text(json.dumps(data), encoding="utf-8")
    assert any("judge_first_pass" in p for p in judge.coherence_problems(res))
    # bateria nova sem juiz: d1 mudou de texto e u2 sumiu
    _live(res, [{**ROWS[0], "answer": "Outro texto."}, *ROWS[1:3]])
    probs = judge.coherence_problems(res)
    assert any("sobre outro texto" in p and "d1" in p for p in probs)
    assert any("não existe mais" in p and "u2" in p for p in probs)
    assert '"evals.judge", "--check"' in (Path(__file__).resolve().parents[1] / "scripts" / "check.py").read_text(
        encoding="utf-8")  # o check.py roda esta conferência


def test_restore_first_pass_redoes_an_old_asymmetric_rejudge_without_llm(tmp_path, monkeypatch):
    res, first = _first_pass(tmp_path)
    # o rejulgamento antigo: rejulgou os reprovados E os datados (d1, d2, u1) e aprovou os três
    redone = [{**v, "grounded": True, "score": 5, "failure_type": "none", "reason": "rejulgado"}
              for v in first["verdicts"] if v["id"] != "u2"]
    old = {**first, "verdicts": [v for v in first["verdicts"] if v["id"] == "u2"] + redone,
           "resumed_verdicts": 1, "rejudged_dated": 3}
    rep = judge.restore_first_pass(old, first, results=res)
    by = {v["id"]: v for v in rep["verdicts"]}
    assert by["u1"]["grounded"] is False and "first_pass" not in by["u1"]  # sem data: volta a 1ª passada
    assert by["d1"]["grounded"] is True and by["d1"]["first_pass"]["grounded"] is False
    assert by["d1"]["judge_date"] == "2026-11-03"  # o dia que o rejulgamento usou (o do negócio)
    assert (rep["rejudge"]["rejulgados"], rep["rejudge"]["mantidos_reprovados"], rep["grounded_rate"]) == (2, 1, 0.75)
    wrong = {**first, "verdicts": [{**v, "grounded": not v["grounded"]} if v["id"] == "u2" else v
                                   for v in first["verdicts"]]}
    with pytest.raises(ValueError, match="não é a 1ª passada"):
        judge.restore_first_pass(old, wrong, results=res)
    (res / "judge.json").write_text(json.dumps(old), encoding="utf-8")
    (tmp_path / "first.json").write_text(json.dumps(first), encoding="utf-8")
    monkeypatch.setattr(judge, "RESULTS_DIR", res)
    monkeypatch.setattr(judge, "OUT", res / "judge.json")
    assert judge.main(["--restore-first-pass", str(tmp_path / "first.json")]) == 0
    live = json.loads((res / "live_official.json").read_text(encoding="utf-8"))
    assert live["judge"]["grounded"] == 3 and live["judge_first_pass"]["grounded"] == 2
    assert judge.coherence_problems(res) == []


def test_results_judge_block_shows_first_pass_to_rejudged_by_split_with_the_rule(tmp_path):
    res, _ = _first_pass(tmp_path)
    judge.rejudge_dated(Fake(), out=res / "judge.json", results=res)
    text = fill_readme.judge_block(res)
    assert "Regra: só pela data, nunca pelo veredito" in text
    assert "1 aprovados e 1 reprovados na 1ª passada" in text and ": 2, 1 deles reprovados" in text
    assert "| official | 4 | 2 | 2/4 → 3/4 | 4/4 → 4/4 |" in text and "| ALL | 4 | 2 | 2/4 → 3/4 |" in text
    assert "os reprovados e os de resposta com data" not in text  # a frase da regra antiga só no judge.json antigo


def test_new_battery_of_a_split_is_judged_where_the_old_one_was_refused(tmp_path):
    live = _live(tmp_path, ROWS[3:])
    rep = judge.judge_into(Fake(refuse=("1,89%",)), live, out=tmp_path / "judge.json")
    assert rep["judge_refused"] and not rep["verdicts"]
    _live(tmp_path, [{**ROWS[3], "answer": "A taxa do débito é 1,99%."}])
    rep = judge.judge_into(Fake(), live, out=tmp_path / "judge.json")
    assert [v["id"] for v in rep["verdicts"]] == ["u2"] and rep["judge_refused"] == []


def test_the_judge_prompt_text_did_not_change():
    """O texto do prompt saiu para PROMPT (que dá a identidade do juiz) sem mudar um caractere: replay e cassetes
    continuam valendo."""
    got = judge.PROMPT.format(today="2026-11-03", question="Q?", who="Cliente autenticado: u1\n\n", sources="- a",
                              tools="(nenhum)", answer="R.")
    old = ("Data de hoje: 2026-11-03\n\nPergunta: Q?\n\nCliente autenticado: u1\n\n" "Fontes:\n- a\n\n"
           "Dados de ferramenta:\n(nenhum)\n\n" "Resposta: R.")
    assert got == old and len(judge.PROMPT_SHA) == 12


# 2. held-out sem `reason` --------------------------------------------------------------------------------------------
def test_heldout_verdicts_never_keep_the_reason(tmp_path):
    res = tmp_path / "results"
    res.mkdir()
    held = res / "live_heldout.json"
    held.write_text(json.dumps({"rows": [{"id": "h1", "split": "heldout", "run": 0, "message": "q?",
                                          "answer": "Resposta h1.", "context": "- x"}]}), encoding="utf-8")
    live = _live(res, ROWS[3:])
    judge.judge_into(Fake(), held, out=res / "judge.json")
    rep = judge.judge_into(Fake(), live, out=res / "judge.json")
    by = {v["id"]: v for v in rep["verdicts"]}
    assert "reason" not in by["h1"] and {"grounded", "helpful", "score", "failure_type"} <= set(by["h1"])
    assert by["u2"]["reason"]  # fora do held-out o motivo fica
    head = json.loads((res / "judge.json").read_text(encoding="utf-8"))
    for v in head["verdicts"]:
        if v["id"] == "h1":
            v["reason"] = "o erro do conjunto cego"  # gravado por um juiz de antes da regra
    (res / "judge.json").write_text(json.dumps(head), encoding="utf-8")
    assert any("held-out com `reason`" in p for p in judge.coherence_problems(res))
    rep = judge.judge_into(Fake(), live, out=res / "judge.json")  # o próximo julgamento já o regrava sem o motivo
    assert "reason" not in {v["id"]: v for v in rep["verdicts"]}["h1"]
    planted = {"id": "h1~p1", "split": "perturbed", "run": 0, "original_split": "heldout", "original_id": "h1",
               "message": "q?", "answer": "Resposta h1 com 9,99.", "context": "- x"}
    (res / "perturbed.json").write_text(json.dumps({"rows": [planted]}), encoding="utf-8")
    pr = judge.judge_perturbed(Fake(), res)  # a adulterada de uma resposta do held-out também é do held-out
    assert pr["verdicts"] and all("reason" not in v for v in pr["verdicts"])
    data = json.loads((res / "judge_perturbed.json").read_text(encoding="utf-8"))
    data["verdicts"] = [{k: v for k, v in x.items() if k != "original_split"} | {"reason": "x"}
                        for x in data["verdicts"]]  # veredito de antes: nem o original_split ele gravava
    (res / "judge_perturbed.json").write_text(json.dumps(data), encoding="utf-8")
    assert any("judge_perturbed.json:h1~p1" in p for p in judge.coherence_problems(res))
    assert judge.drop_blind_reasons(res) == {"judge_perturbed.json": 1}  # sem LLM
    assert judge.coherence_problems(res) == []


# 3. validação sobre o mesmo texto ------------------------------------------------------------------------------------
def test_label_of_an_old_text_stays_out_of_every_count_and_is_listed(tmp_path):
    res = tmp_path / "results"
    res.mkdir()
    live = _live(res)
    path = label.csv_path("ana", tmp_path)
    assert label.export(4, res, path) == 4  # página de antes do congelamento: só o CSV
    label.mark(["d1=pass", "d2=pass", "u1=fail:invented_number", "u2=pass"], path=path)
    judge.judge_into(Fake(bad=("3,19%",)), live, out=res / "judge.json")
    rep = label.report(results=res, out=tmp_path / "h.json", base=tmp_path)
    assert rep["rotulos"] == 4 and rep["rotulos_de_outra_bateria"] is None
    assert rep["bateria"]["rotulos_por_bateria"] == {"aaa1111": 4} and rep["juiz_x_humano"]["negatives"] == 1
    _live(res, [{**r, "answer": r["answer"] + " Texto novo."} if r["id"] in ("d1", "u1") else r for r in ROWS],
          sha="bbb2222")  # bateria nova: d1 e u1 são outras respostas
    judge.judge_into(Fake(), live, out=res / "judge.json")
    rep = label.report(results=res, out=res / "human_review.json", base=tmp_path)
    assert rep["rotulos"] == 2 and rep["humano_passa"] == 2  # humano × automático: só o mesmo texto
    assert rep["rotulos_de_outra_bateria"] == {"rotulos": 2, "ids": ["d1", "u1"],
                                               "por_rotulador": {"ana": ["d1", "u1"]}}
    assert rep["bateria"]["rotulos_por_bateria"] == {"bbb2222": 2}
    jx = rep["juiz_x_humano"]
    assert (jx["casos"], jx["negatives"]) == (2, 0)  # a reprovação do u1 velho nunca encontra o veredito do u1 novo
    text = fill_readme.human_block(res)
    assert "Bateria das respostas rotuladas que contam, em rótulos: `bbb2222` 2; 0 de página congelada" in text
    assert "Rótulos de outra bateria: **2**" in text and "fora de toda conta: d1, u1." in text
    assert judge.coherence_problems(res, labels=tmp_path) == []
    label.mark(["u2=fail"], path=path)  # rótulo mudou e o --report não rodou: human_review.json velho
    assert any("human_review.json" in p for p in judge.coherence_problems(res, labels=tmp_path))


def _page_and_label(tmp_path, res, monkeypatch, rater="Ana", fail=("u1",)):
    monkeypatch.setattr(label, "RESULTS", res)
    got, _ = label_page.build(4, results=res, base=tmp_path)
    marks = {i["id"]: {"v": "fail" if i["id"] in fail else "pass"} for i in got}
    dump = tmp_path / f"{rater}.json"
    dump.write_text(json.dumps([{"data": {"rater": rater, "marks": marks, "sample": label_page.sample_id(got)}}]),
                    encoding="utf-8")
    return got, dump


def test_frozen_page_keeps_the_validation_after_a_new_battery(tmp_path, monkeypatch):
    res = tmp_path / "results"
    res.mkdir()
    live = _live(res)
    judge.judge_into(Fake(bad=("3,19%",)), live, out=res / "judge.json")  # o juiz rodou antes da página
    got, dump = _page_and_label(tmp_path, res, monkeypatch)
    frozen = json.loads((label.VALIDATION_DIR / f"{label_page.sample_id(got)}.json").read_text(encoding="utf-8"))
    items = {it["id"]: it for it in frozen["itens"]}
    assert set(items) == {r["id"] for r in ROWS} and frozen["baterias"] == ["aaa1111"]
    assert items["u1"]["veredito_do_juiz"]["grounded"] is False and "reason" not in items["u1"]["veredito_do_juiz"]
    assert items["u1"]["selecao"] == "aleatoria" and items["u1"]["juiz"]["prompt_sha"] == judge.PROMPT_SHA
    assert items["d1"]["entrada_do_juiz"]["answer"] == ROWS[0]["answer"]
    assert items["d1"]["entrada_do_juiz"]["business_date"] == "2026-11-03"
    html = label_page.render(got, ["Ana", "Bia"])
    assert "veredito_do_juiz" not in html and "aaa1111" not in html  # o congelado nunca vai para a página
    new = [{**r, "answer": r["answer"] + " Texto novo."} for r in ROWS]
    _live(res, new, sha="bbb2222")  # bateria nova ANTES da importação, com o juiz reprovando tudo
    judge.judge_into(Fake(bad=("Texto novo",)), live, out=res / "judge.json")
    assert label.import_page(dump, results=res, base=tmp_path) == {"Ana": 4}
    csv_rows = {r["id"]: r for r in label.read_labels(label.csv_path("Ana", tmp_path))}
    assert all(csv_rows[r["id"]]["resposta"] == r["answer"] for r in ROWS)  # o texto que a pessoa viu
    rep = label.report(results=res, out=tmp_path / "h.json", base=tmp_path)
    jx = rep["juiz_x_humano"]
    assert (jx["casos"], jx["concordancia"], jx["negatives"], jx["tnr"]) == (4, 1.0, 1, 1.0)  # o veredito congelado
    assert rep["rotulos_de_outra_bateria"] is None and rep["aviso_juiz"] is None
    assert rep["bateria"]["rotulos_por_bateria"] == {"aaa1111": 4} and rep["bateria"]["de_pagina_congelada"] == 4
    assert (rep["rotulos"], rep["automatico_passa"]) == (4, 3)  # as checagens congeladas (u1: número sem base)


def test_changed_judge_warns_and_validation_rejudges_only_the_frozen_texts(tmp_path, monkeypatch):
    res = tmp_path / "results"
    res.mkdir()
    live = _live(res)
    judge.judge_into(Fake(bad=("3,19%",)), live, out=res / "judge.json")
    got, dump = _page_and_label(tmp_path, res, monkeypatch)
    label.import_page(dump, results=res, base=tmp_path)
    page = label.VALIDATION_DIR / f"{label_page.sample_id(got)}.json"
    data = json.loads(page.read_text(encoding="utf-8"))
    for it in data["itens"]:
        it["juiz"]["prompt_sha"] = "antigo"  # a página foi congelada com outro prompt do juiz
    page.write_text(json.dumps(data), encoding="utf-8")
    _live(res, [{**r, "answer": r["answer"] + " Texto novo."} for r in ROWS], sha="bbb2222")
    rep = label.report(results=res, out=tmp_path / "h.json", base=tmp_path)
    assert "4 rótulo(s) comparados com o veredito de outro juiz" in rep["aviso_juiz"] and "--validation" in rep[
        "aviso_juiz"]
    fake = Fake(bad=("3,19%",))
    out = judge.judge_validation(fake, results=res)
    assert out["julgados"] == 4 and sorted(fake.answers) == sorted(r["answer"] for r in ROWS)  # os congelados, só
    rj = json.loads(page.read_text(encoding="utf-8"))["rejulgamentos"][-1]
    assert rj["prompt_sha"] == judge.PROMPT_SHA and set(rj["vereditos"]) == {r["id"] for r in ROWS}
    rep = label.report(results=res, out=tmp_path / "h.json", base=tmp_path)
    assert rep["aviso_juiz"] is None and rep["juiz_x_humano"]["casos"] == 4
    again = Fake()
    assert judge.judge_validation(again, results=res)["julgados"] == 0 and again.answers == []  # nada a pagar


def test_two_texts_of_the_same_case_are_two_items_never_one(tmp_path, monkeypatch):
    res = tmp_path / "results"
    res.mkdir()
    live = _live(res)
    judge.judge_into(Fake(), live, out=res / "judge.json")
    _, dump = _page_and_label(tmp_path, res, monkeypatch, "Ana", fail=())
    label.import_page(dump, results=res, base=tmp_path)
    _live(res, [{**r, "answer": r["answer"] + " Texto novo."} for r in ROWS], sha="bbb2222")
    judge.judge_into(Fake(), live, out=res / "judge.json")
    _, dump = _page_and_label(tmp_path, res, monkeypatch, "Bia", fail=("d1",))
    label.import_page(dump, results=res, base=tmp_path)
    rep = label.report(results=res, out=tmp_path / "h.json", base=tmp_path)
    assert rep["rotuladores"] == 2 and rep["rotulos_de_outra_bateria"] is None
    assert rep["entre_humanos"]["comuns"] == 0  # leram respostas diferentes: nada a comparar entre elas
    assert rep["juiz_x_humano"]["casos"] == 8 and rep["bateria"]["rotulos_por_bateria"] == {"aaa1111": 4,
                                                                                            "bbb2222": 4}
    assert label.divergences(base=tmp_path, results=res) == []  # e a rodada de consenso não as põe lado a lado
