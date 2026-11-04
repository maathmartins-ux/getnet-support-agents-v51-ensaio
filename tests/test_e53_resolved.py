"""E53 — manchete "oficiais resolvidas": sem humano E todo `expect.facts` na resposta E fonte citada.

"Oficiais fundamentadas 1,00" não pode contar "passei para um humano" como acerto: com essa conta, a manchete
mostrava 1,00 enquanto o mesmo juiz dava helpful 0,733 no official, número que nem aparecia no placar.
"""
import json

import pytest

from evals import run_evals
from scripts import scorecard

SRC = [{"id": "faq-entrega", "title": "Prazo", "url": "https://loja.test/prazo"}]


def _case(**exp):
    return {"id": "official-01", "split": "official", "message": "Prazo?", "expect": {"intent": "faq", **exp}}


def test_resolved_needs_no_handoff_every_fact_and_a_source():
    case = _case(facts=["3 a 5 dias úteis", r"interior.*5 a 8"])
    ok = {"intent": "faq", "answer": "Capitais: 3 a 5 DIAS ÚTEIS. Interior: 5 a 8.", "sources": SRC,
          "route": ["router", "faq"]}
    assert run_evals.score(case, ok)["resolved"] is True and run_evals.score(case, ok)["facts"] is True
    # cada condição, sozinha, derruba a manchete
    handed = {**ok, "handoff": {"required": True}, "route": ["router", "faq", "escalation"]}
    missing = {**ok, "answer": "Capitais: 3 a 5 dias úteis."}
    no_source = {**ok, "sources": []}
    for got in (handed, missing, no_source):
        assert run_evals.score(case, got)["resolved"] is False
    assert run_evals.score(case, missing)["facts"] is False
    assert run_evals.score(case, handed)["facts"] is True  # o fato pode estar no texto e mesmo assim ir ao humano


def test_tool_data_counts_as_source_and_case_without_facts_has_no_headline():
    case = _case(facts=["em separação"])
    got = {"answer": "Pedido 1002: em separação.", "tool_calls": [{"name": "lookup_record", "ok": True}]}
    assert run_evals.score(case, got)["resolved"] is True
    assert run_evals.score(case, {**got, "tool_calls": [{"name": "lookup_record", "ok": False}]})["resolved"] is False
    assert "resolved" not in run_evals.score(_case(), got)  # humano esperado (sem fatos): fora da manchete


def test_invalid_fact_regex_fails_at_load(tmp_path, monkeypatch):
    bad = tmp_path / "cases.jsonl"
    bad.write_text(json.dumps(_case(facts=["R$ (79"])) + "\n", encoding="utf-8")
    monkeypatch.setattr(run_evals, "CASES", bad)
    with pytest.raises(ValueError, match="regex inválida"):
        run_evals.load_cases()


def test_case_whose_every_fact_echoes_the_question_fails_at_load(tmp_path, monkeypatch):
    """Rodada 10: o official-10 passava só repetindo a pergunta (fatos "whats ?app" e "payment link", os dois na
    própria mensagem). Fato que só ecoa a pergunta não mede a resposta: a carga recusa, com o casamento de cada
    checagem (regex sem caixa em expect.facts; valor/regex de memória em expects_fact)."""
    path = tmp_path / "cases.jsonl"
    monkeypatch.setattr(run_evals, "CASES", path)
    q = "Can I sell through WhatsApp using the Payment Link?"
    echo = {"id": "official-10", "split": "official", "message": q,
            "expect": {"intent": "knowledge", "facts": ["whats ?app", "link de pagamento|payment link"]}}
    memory = {"id": "q-mem-06", "split": "memory", "message": "E pelo WhatsApp funciona?", "before": ["O que é?"],
              "expect": {"intent": "knowledge", "expects_fact": ["whats ?app"]}}
    number = {"id": "m-07", "split": "memory", "message": "E a de R$ 129,90 parcela em quantas vezes?",
              "expect": {"intent": "knowledge", "expects_fact": ["129,90"]}}  # valor por número: 129,90 = 129.9
    for case, field in ((echo, "expect.facts"), (memory, "expect.expects_fact"), (number, "expect.expects_fact")):
        path.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match=f"caso {case['id']}: todo fato já está na pergunta \\({field}\\); eco não "
                                             "mede a resposta"):
            run_evals.load_cases()
    # basta um fato que só a resposta certa traz (o trecho da fonte), e o caso carrega; memória com o valor do turno
    # anterior, não o da pergunta, também
    echo["expect"]["facts"].append("redes? sociais|social (media|networks?)|remote (charges?|billing)")
    memory["expect"]["expects_fact"] = ["link de pagamento|payment link"]
    path.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in (echo, memory)) + "\n", encoding="utf-8")
    assert [c["id"] for c in run_evals.load_cases()] == ["official-10", "q-mem-06"]


def test_kit_fixture_cases_load_under_the_echo_guard():
    """A fixture do kit carrega com a guarda (os casos do domínio são conferidos pela própria carga no eval do CI)."""
    for path in (run_evals.CASES, run_evals.HERE.parent / "tests" / "fixtures" / "dependent_cases.jsonl"):
        assert all(run_evals.echo_facts(c) is None for c in run_evals.load_cases((path,)))


def _cases_with_facts(tmp_path, monkeypatch, facts_01):
    cases = [json.loads(line) for line in run_evals.CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    for c in cases:
        if c["id"] == "official-01":
            c["expect"]["facts"] = facts_01
        if c["id"] == "official-02":
            c["expect"]["facts"] = ["7 dias"]
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8")
    monkeypatch.setattr(run_evals, "CASES", path)


def test_report_has_resolved_per_split_and_case_and_markdown_leads_with_it(tmp_path, monkeypatch):
    _cases_with_facts(tmp_path, monkeypatch, ["3 a 5 dias úteis"])
    rep = run_evals.run(out=tmp_path / "r.json", split="official")
    off = rep["resolved"]["by_split"]["official"]
    assert (off["k"], off["n"], off["rate"], off["unresolved"]) == (2, 2, 1.0, [])
    assert set(off["cases"]) == {"official-01", "official-02"}  # official-03/04 sem fatos: fora da conta
    assert rep["metrics"]["official"]["resolved_acc"] == 100.0
    row = next(r for r in rep["rows"] if r["id"] == "official-01")
    assert row["facts_missing"] == []
    md = run_evals.to_markdown(rep)
    # 1ª linha: como ler (gerada, sem número); a 1ª linha de dado é a manchete das resolvidas
    head, data = md.split("\n\n", 1)
    assert head.startswith("**Como ler:**") and data.startswith("**Resolvidas**") and "official **100.0%**" in md


def test_offline_gate_blocks_when_resolved_below_target(tmp_path, monkeypatch):
    _cases_with_facts(tmp_path, monkeypatch, ["um fato que a resposta não tem"])
    assert run_evals.run(out=tmp_path / "a.json", split="official")["passed"] is True  # sem alvo: só informa
    rep = run_evals.run(out=tmp_path / "b.json", split="official", min_resolved=0.9)
    assert rep["passed"] is False
    assert rep["gate_resolved"] == {"target": 0.9, "split": "official", "rate": 0.5, "passed": False,
                                    "unresolved": ["official-01"]}
    assert "Gate de resolvidas (official ≥ 90%): **FAIL**" in run_evals.to_markdown(rep)
    assert run_evals.main(["--split", "official", "--min-resolved", "0.9", "--out", str(tmp_path / "c.json")]) == 1


def test_gate_without_facts_is_not_a_silent_pass(tmp_path):
    rep = run_evals.run(out=tmp_path / "r.json", split="official", min_resolved=0.5)  # fixture do kit: sem fatos
    assert rep["passed"] is False and "expect.facts" in rep["gate_resolved"]["reason"]


def test_memory_case_cost_includes_previous_turns():
    class Priced:
        def send(self, message, user_id, conversation_id):
            return {"conversation_id": "c", "answer": "ok", "usage": {"cost_usd": 0.1}}

    case = {"id": "m", "split": "memory", "message": "e a outra?", "before": ["a", "b"], "expect": {}}
    assert run_evals.run_case(Priced(), case)["cost_usd"] == pytest.approx(0.3)


def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_scorecard_first_row_is_resolved_and_helpful_sits_next_to_grounded(tmp_path):
    _write(tmp_path / "live_official.json", {"status": "complete", "resolved": {"by_split": {"official": {
        "rate": 0.6, "pass_hat_k": 0.4}}}, "stability": {"pass_hat_k": 0.7}, "metrics": {"official": {}}})
    _write(tmp_path / "judge.json", {"by_split": {"official": {"grounded_rate": 1.0, "helpful_rate": 0.733}}})
    table = scorecard.rows(tmp_path)
    assert table[0]["key"] == "official_resolved" and table[0]["shown"] == "0.60"
    by = {r["key"]: r for r in table}
    assert by["official_resolved_k"]["value"] == 0.4 and by["official_helpful"]["status"] == "abaixo"
    keys = [r["key"] for r in table]
    assert keys.index("official_helpful") + 1 == keys.index("official_grounded")
    assert scorecard.to_markdown(tmp_path).splitlines()[2].startswith("| Oficiais resolvidas")


def test_scorecard_recounts_resolved_from_rows_of_an_old_report(tmp_path):
    rows = [{"id": "o1", "split": "official", "checks": {"resolved": True}},
            {"id": "o1", "split": "official", "checks": {"resolved": False}},
            {"id": "o2", "split": "official", "checks": {"resolved": True}},
            {"id": "o3", "split": "official", "checks": {"intent": True}}]  # sem fatos: fora
    _write(tmp_path / "live_official.json", {"status": "complete", "rows": rows})
    got = scorecard.measure(tmp_path)
    assert got["official_resolved"] == pytest.approx(0.6667, abs=1e-4) and got["official_resolved_k"] == 0.5
    _write(tmp_path / "live_official.json", {"status": "complete", "rows": rows[3:]})
    assert scorecard.measure(tmp_path)["official_resolved"] is None  # sem medida: aparece como buraco


def test_every_blind_heldout_lot_stays_out_of_the_intent_gate():
    """Lote cego novo (heldout_h3) não entra no gate de intenção, como o heldout: o nome é por prefixo."""
    from evals.run_evals import ungated

    assert ungated("heldout") and ungated("heldout_h3") and ungated("real") and ungated("hard")
    assert not ungated("official") and not ungated("hitl")
