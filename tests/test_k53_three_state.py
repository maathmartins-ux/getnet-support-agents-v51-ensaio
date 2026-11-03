"""K53: resposta do faq em três estados: ok | partial | insufficient.

Com só dois estados, 40 das 49 falhas de escalada foram escaladas sem precisar: a resposta que cobria parte da
pergunta virava NOT_IN_SOURCES e ia ao humano inteira. partial responde o que a fonte cobre e diz o que falta
(não escala por si); NOT_IN_SOURCES fica para "nada coberto".
"""
import json
from typing import get_args

import pytest
from fakes import fake_llm, resp, text

from app import agents, domain
from app.agents import Context, coverage_of, missing_when_present
from app.schemas import AgentStatus

DOCS = [
    {"id": "alfa-preco", "title": "Plano Alfa", "url": "https://example.com/alfa",
     "text": "O Plano Alfa custa R$ 10 por mês e inclui entrega grátis para capitais."},
    {"id": "beta-preco", "title": "Plano Beta", "url": "https://example.com/beta",
     "text": "O Plano Beta custa R$ 20 por mês e inclui atendimento prioritário."},
]


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    (tmp_path / "kb.jsonl").write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in DOCS), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def ctx(message, language="pt"):
    return Context(text=message, language=language, user_id="u1", conversation_id="c1", intent="faq")


def with_reply(monkeypatch, reply):
    llm, msgs = fake_llm([resp("end_turn", text(reply))], effort="medium")
    monkeypatch.setattr(agents, "get_llm", lambda role="agent": llm)
    return msgs


def test_contract_has_the_three_states():
    assert {"ok", "partial", "insufficient"} <= set(get_args(AgentStatus))


@pytest.mark.parametrize("reply, expected", [
    ("O Plano Alfa custa R$ 10 [1].", ("ok", "O Plano Alfa custa R$ 10 [1].", None)),
    ("Alfa: R$ 10 [1]. As fontes não trazem o preço do Gama.\nMISSING: preço do Plano Gama",
     ("partial", "Alfa: R$ 10 [1]. As fontes não trazem o preço do Gama.", "preço do Plano Gama")),
    ("Alfa: R$ 10 [1].\n**MISSING:** preço do Gama.", ("partial", "Alfa: R$ 10 [1].", "preço do Gama")),
    ("NOT_IN_SOURCES", ("insufficient", "", None)),
    ("  NOT_IN_SOURCES.\n", ("insufficient", "", None)),
    # o modelo marcou a falta de um item e respondeu o resto com citação: é parcial, não "nada coberto"
    ("Alfa: R$ 10 [1]. NOT_IN_SOURCES", ("partial", "Alfa: R$ 10 [1].", None)),
])
def test_coverage_of_maps_the_reply_markers(reply, expected):
    assert coverage_of(reply) == expected


def test_partial_answer_keeps_what_is_covered_and_says_what_is_missing(corpus, monkeypatch):
    with_reply(monkeypatch, "O Plano Alfa custa R$ 10 [1]. As fontes não trazem o preço do Plano Gama.\n"
                            "MISSING: preço do Plano Gama")
    r = agents.faq_agent(ctx("Quanto custam o Plano Alfa e o Plano Gama?"))
    assert r.status == "partial" and r.reason == "partial_coverage"
    assert r.facts["missing"] == "preço do Plano Gama"
    assert "MISSING" not in r.text and "[alfa-preco]" in r.text and "não trazem o preço do Plano Gama" in r.text
    assert r.sources and r.evidence  # partial responde com fonte: não é "sem fonte"


def test_partial_without_the_sentence_gets_it_from_the_template(corpus, monkeypatch):
    with_reply(monkeypatch, "The Plano Alfa costs R$ 10 [1].\nMISSING: Plano Gama price")
    r = agents.faq_agent(ctx("How much are Plano Alfa and Plano Gama?", language="en"))
    assert r.status == "partial" and r.text.endswith("The sources don't cover: Plano Gama price.")


def test_not_in_sources_alone_is_insufficient(corpus, monkeypatch):
    with_reply(monkeypatch, "NOT_IN_SOURCES")
    r = agents.faq_agent(ctx("Quanto custa o Plano Alfa?"))
    assert r.status == "insufficient" and r.reason == "not_in_sources" and r.text == ""


def test_complete_answer_stays_ok(corpus, monkeypatch):
    with_reply(monkeypatch, "Alfa R$ 10 [1]; Beta R$ 20 [2].")
    r = agents.faq_agent(ctx("Qual a diferença entre o Plano Alfa e o Plano Beta?"))
    assert r.status == "ok" and "missing" not in r.facts


def test_offline_comparison_with_an_unknown_item_is_partial(corpus):
    r = agents.faq_agent(ctx("Qual a diferença entre o Plano Alfa e o Plano Zeta?"))
    assert r.status == "partial" and r.facts["missing"] == "Plano Zeta"
    assert "R$ 10" in r.text and r.text.endswith("As fontes não trazem: Plano Zeta.")


def test_offline_nothing_covered_is_insufficient(corpus):
    r = agents.faq_agent(ctx("Qual a capital da Mongólia?"))
    assert r.status == "insufficient" and r.reason == "no_source"


def test_prompt_reserves_not_in_sources_for_nothing_covered():
    prompt = (domain.KIT_PROMPTS / "faq.md").read_text(encoding="utf-8")
    assert "MISSING:" in prompt and "Nenhuma passagem trata" in prompt and "NOT_IN_SOURCES" in prompt
    assert "{language}" in prompt and prompt.format(language="en")  # só o placeholder de sempre


# --- checagem para o eval: "disse que falta, e o fato estava num trecho recuperado" ---------------------------------
PASSAGES = ["Planos: Plano Alfa · R$ 10/mês · Plano Beta · R$ 20/mês", "Entrega em 3 dias úteis."]


def test_flags_not_in_sources_when_a_passage_has_the_reference_fact():
    assert missing_when_present("NOT_IN_SOURCES", PASSAGES, [r"R\$ ?10", r"R\$ ?20"], "insufficient") == [
        r"R\$ ?10", r"R\$ ?20"]


def test_flags_only_the_fact_the_partial_answer_said_was_missing():
    answer = "O Alfa custa R$ 10 [1]. As fontes não trazem o preço do Beta."
    assert missing_when_present(answer, PASSAGES, [r"R\$ ?10", r"R\$ ?20"], "partial") == [r"R\$ ?20"]


def test_does_not_flag_when_the_fact_is_not_in_any_passage_or_the_answer_did_not_say_missing():
    assert missing_when_present("NOT_IN_SOURCES", PASSAGES, [r"R\$ ?99"], "insufficient") == []
    assert missing_when_present("Alfa R$ 10, Beta R$ 20.", PASSAGES, [r"R\$ ?10"], "ok") == []


def test_absence_sentence_counts_as_saying_missing_and_bad_regex_is_literal():
    assert missing_when_present("Não encontrei o preço nas fontes.", PASSAGES, [r"R\$ ?20"]) == [r"R\$ ?20"]
    assert missing_when_present("NOT_IN_SOURCES", ["custa (R$ 10"], ["(R$ 10"]) == ["(R$ 10"]
