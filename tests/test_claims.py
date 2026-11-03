"""Checagem de frases (app/claims.py): afirmação sem base e ação oferecida que nenhuma ferramenta faz.

Getnet v4, juiz nos 10 cenários oficiais: "turn it off and on" e "move near a window" sem fonte (conselho genérico) e
a oferta de um reinício remoto. Com LLM, um verificador barato aponta as frases e a política remove; sem LLM, o
fallback léxico só sinaliza. Oferta de ação é determinística: casa com o registro de ferramentas ou sai.
"""
import json

import pytest
from fakes import fake_llm, resp, text

from app import capabilities, claims, pipeline, supervisor
from app.agents import AgentResult
from app.schemas import ChatRequest

TERMINALS = json.dumps({"ok": True, "data": {"terminals": [
    {"terminal_id": "T1988B", "model": "Get Clássica", "connection": "chip", "signal": "sem_sinal", "online": False}]}})
FAQ = ("Como insiro o chip na minha máquina? Com a máquina desligada, abra a tampa na parte de trás, insira o chip "
       "no local sinalizado com SIM1 ou SIM2 e faça um teste de comunicação.")
GETNET_TOOLS = {
    "get_terminal_status": {"description": "Maquininhas do lojista autenticado: modelo, conexão, sinal.",
                            "write": False},
    "restart_terminal": {"description": "Reinicia remotamente uma maquininha do lojista. Escrita: só propõe.",
                         "write": True},
    "request_anticipation": {"description": "Solicita antecipação de recebíveis de crédito. Exige confirmação do "
                                            "lojista e aprovação de um atendente.", "write": True, "risk": "high"},
}


def _verifier(monkeypatch, payload):
    llm, msgs = fake_llm([resp("end_turn", text(json.dumps(payload)))], model="claude-haiku-5-5")
    monkeypatch.setattr(claims, "get_llm", lambda role="agent": llm)
    return msgs


# --- frases ------------------------------------------------------------------------------------------------------
def test_sentences_skip_tables_headings_questions_and_absence():
    s = claims.split_sentences("**O que tentar:**\n| TX1 | R$ 10,00 |\n1. Abra a tampa traseira da máquina. Insira "
                               "o chip no slot.\nQuer que eu abra um chamado?\nNão encontrei o pedido na sua conta.")
    checkable = [x.text for x in s if x.checkable]
    assert checkable == ["Abra a tampa traseira da máquina.", "Insira o chip no slot."]


def test_lexical_fallback_flags_but_never_cuts(monkeypatch):
    monkeypatch.setenv("CLAIMS_POLICY", "remove")
    answer = ("Com a máquina desligada, abra a tampa e insira o chip no SIM1. "
              "Coloque perto de uma janela, longe de metal.")
    out, rep = claims.enforce(answer, evidence=[FAQ])
    assert rep.method == "lexical" and out == answer  # só sinaliza
    assert [u["sentence"] for u in rep.unsupported] == ["Coloque perto de uma janela, longe de metal."]
    assert rep.unsupported[0]["action"] == "flagged" and rep.action == "flagged"


def test_glossary_bridges_english_answer_and_portuguese_source():
    stems = claims.evidence_stems(["Política de entrega: prazo de 3 a 5 dias úteis."])
    assert claims.support_ratio("The delivery deadline is 3 to 5 business days.", stems) >= 0.5


# --- verificador LLM ---------------------------------------------------------------------------------------------
def test_llm_verifier_removes_unsupported_sentence_with_one_small_call(monkeypatch):
    msgs = _verifier(monkeypatch, {"unsupported": [{"index": 1, "reason": "generic_advice"}]})
    answer = "Abra a tampa e confira o chip no SIM1. Coloque a máquina perto de uma janela, longe de paredes grossas."
    out, rep = claims.enforce(answer, evidence=[FAQ, TERMINALS], question="Minha máquina não conecta")
    assert rep.method == "llm" and rep.policy == "remove" and rep.action == "removed"
    assert out == "Abra a tampa e confira o chip no SIM1."
    assert rep.unsupported == [{"index": 1, "sentence": "Coloque a máquina perto de uma janela, longe de paredes "
                                "grossas.", "reason": "generic_advice", "source": "llm", "action": "removed"}]
    assert len(msgs.sent) == 1 and msgs.sent[0]["model"] == "claude-haiku-5-5"
    schema = msgs.sent[0]["output_config"]["format"]["schema"]
    assert schema["properties"]["unsupported"]["items"]["properties"]["reason"]["enum"] == list(claims.REASONS)
    assert "[1] Coloque a máquina" in msgs.sent[0]["messages"][0]["content"]


def test_sentence_copied_from_policy_card_is_never_cut(monkeypatch):
    """O verificador nem recebe a frase que é cópia do cartão; índice inventado por ele é ignorado."""
    msgs = _verifier(monkeypatch, {"unsupported": [{"index": 0, "reason": "not_in_evidence"},
                                                   {"index": 1, "reason": "not_in_evidence"}]})
    card = capabilities.card("pt", tools=GETNET_TOOLS)
    answer = ("Ações de risco alto exigem a confirmação do cliente e a aprovação de um atendente humano. "
              "Seu saldo será liberado amanhã sem custo algum.")
    out, rep = claims.enforce(answer, evidence=[TERMINALS], card=card)
    assert "[0]" not in msgs.sent[0]["messages"][0]["content"]  # a cópia do cartão não foi ao verificador
    assert out.startswith("Ações de risco alto exigem a confirmação")
    assert [u["index"] for u in rep.unsupported] == [1]


def test_removal_that_would_empty_the_answer_keeps_original_and_flags(monkeypatch):
    _verifier(monkeypatch, {"unsupported": [{"index": 0, "reason": "not_in_evidence"}]})
    answer = "Seu saldo será liberado amanhã sem custo algum."
    out, rep = claims.enforce(answer, evidence=[TERMINALS])
    assert out == answer and rep.action == "kept_original"
    assert rep.unsupported[0]["action"] == "flagged"


def test_no_turn_evidence_means_no_verifier_call(monkeypatch):
    llm, msgs = fake_llm([])  # roteiro vazio: qualquer chamada quebraria o teste
    monkeypatch.setattr(claims, "get_llm", lambda role="agent": llm)
    out, rep = claims.enforce("Encaminhei para um atendente humano com protocolo.", evidence=[],
                              card=capabilities.card("pt"))
    assert rep.method == "skipped" and msgs.sent == []


def test_policy_off_and_flag(monkeypatch):
    monkeypatch.setenv("CLAIMS_POLICY", "off")
    assert claims.enforce("Posso enviar uma nova maquininha hoje.", evidence=[FAQ])[1].unsupported == []
    monkeypatch.setenv("CLAIMS_POLICY", "flag")
    out, rep = claims.enforce("Posso enviar uma nova maquininha hoje para você.", evidence=[FAQ])
    assert out.startswith("Posso enviar") and rep.action == "flagged"


def test_verifier_failure_falls_back_to_lexical(monkeypatch):
    from app.llm import LLMError

    llm, _ = fake_llm([LLMError("boom", "connection")])
    monkeypatch.setattr(claims, "get_llm", lambda role="agent": llm)
    _, found, method = claims.check("Coloque a máquina perto de uma janela, longe de metal.", [FAQ])
    assert method == "lexical" and found[0]["source"] == "lexical"


# --- ação oferecida ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("sentence,ok,tool", [
    ("If it still has no signal, I can propose a remote restart of T1988B.", True, "restart_terminal"),
    ("Posso reiniciar a sua maquininha remotamente.", True, "restart_terminal"),
    ("I can help you request an anticipation of your credit receivables if you'd like.", True,
     "request_anticipation"),
    ("Quer que eu abra um chamado com um atendente?", True, "escalation"),
    ("I can also open a case with a human agent.", True, "escalation"),
    ("Posso explicar como funciona o teste de comunicação.", True, None),
    ("Do you want me to propose it?", True, None),
    ("If you want to anticipate, tell me and I can start a request.", True, "request_anticipation"),
    ("I can send you a new card machine today.", False, None),
    ("Posso trocar o seu plano de taxas agora mesmo.", False, None),
])
def test_offered_action_maps_to_registry(sentence, ok, tool):
    caps = claims.capabilities(GETNET_TOOLS, overrides={})
    assert claims.offered_action(sentence, caps, has_read=True) == (ok, tool)


def test_statement_without_offer_is_not_an_offer():
    caps = claims.capabilities(GETNET_TOOLS, {})
    assert claims.offered_action("O terminal está offline há 190 minutos.", caps, True) is None
    assert claims.offered_action("The sources don't cover it, so I can't compare them.", caps, True) is None


def test_absence_statements_are_not_checkable_claims():
    s = claims.split_sentences("They don't describe features or hardware. Hardware details aren't in the sources. "
                               "Nothing has been done yet in your account.")
    assert not any(x.checkable for x in s)


def test_domain_keywords_extend_the_map(monkeypatch):
    from app import domain

    monkeypatch.setattr(domain.active(), "ACTION_KEYWORDS", {"cancel_record": ["desistir"]}, raising=False)
    caps = claims.capabilities()
    assert claims.offered_action("Posso desistir da compra por você.", caps, True) == (True, "cancel_record")


def test_unavailable_offer_is_removed_and_list_renumbered(monkeypatch):
    monkeypatch.setenv("CLAIMS_POLICY", "remove")
    answer = ("O que tentar:\n1. Desligue a máquina e abra a tampa.\n2. Posso reiniciar a máquina remotamente.\n"
              "3. Faça um teste de comunicação.")
    out, rep = claims.enforce(answer, evidence=[FAQ])  # domínio de exemplo: não há ferramenta de reinício
    assert "reiniciar" not in out and "2. Faça um teste de comunicação." in out
    assert any(u["source"] == "offer" and u["action"] == "removed" for u in rep.unsupported)


def test_list_header_goes_away_with_its_only_item():
    out = claims.remove_sentences("Você tem duas opções.\n\nO que posso fazer:\n- Posso enviar outra máquina.\n\n"
                                  "Fim do atendimento por aqui.", {"Posso enviar outra máquina."})
    assert out == "Você tem duas opções.\n\nFim do atendimento por aqui."


# --- pipeline ----------------------------------------------------------------------------------------------------
def _ask(monkeypatch, answer, evidence, message="Posso trocar um livro?"):
    monkeypatch.setitem(supervisor.AGENTS, "faq", lambda ctx: AgentResult("faq", "ok", text=answer,
                                                                          evidence=evidence))
    return pipeline.handle(ChatRequest(message=message), "u1")


def test_pipeline_records_claims_and_removes_with_llm(monkeypatch):
    _verifier(monkeypatch, {"unsupported": [{"index": 1, "reason": "generic_advice"}]})
    r = _ask(monkeypatch, "Abra a tampa e confira o chip no SIM1. Coloque a máquina perto de uma janela.", [FAQ])
    assert r.claims_action == "removed" and "janela" not in r.answer
    assert r.unsupported_claims[0]["reason"] == "generic_advice"
    assert any(e.startswith(f"[{capabilities.CARD_ID}]") for e in r.evidence)  # o cartão vai junto para o juiz


def test_pipeline_offline_default_only_flags(monkeypatch):
    r = _ask(monkeypatch, "Abra a tampa e confira o chip no SIM1. Coloque a máquina perto de uma janela.", [FAQ])
    assert r.claims_action == "flagged" and "janela" in r.answer
    assert r.unsupported_claims[0]["source"] == "lexical"


def test_write_offer_is_unavailable_while_the_case_is_with_a_human(monkeypatch):
    """Caso aberto: escrita suspensa (supervisor._hold); oferecer o reinício é oferecer o que não existe (ensaio
    v5.1, q-mem-03). Consulta e humano continuam ofertas válidas."""
    monkeypatch.setenv("CLAIMS_POLICY", "remove")
    answer = "A T1988B segue sem sinal. Posso reiniciar a sua maquininha remotamente. Quer que eu chame o atendente?"
    _, found, _ = claims.check(answer, [TERMINALS], tools=GETNET_TOOLS, use_llm=False, writes_blocked=True)
    assert [u["sentence"] for u in found if u["source"] == "offer"] == ["Posso reiniciar a sua maquininha remotamente."]
    _, found, _ = claims.check(answer, [TERMINALS], tools=GETNET_TOOLS, use_llm=False)
    assert not [u for u in found if u["source"] == "offer"]


def test_internal_agent_names_never_reach_the_customer():
    assert pipeline._scrub_internal("Consultei o `faq_agent` e o records_agent.", "pt") == (
        "Consultei a base de conhecimento e os dados da sua conta.")
    assert "escalation_agent" not in pipeline._scrub_internal("I'll call escalation_agent.", "en")


def test_capability_card_code_never_reaches_the_customer():
    from app.pipeline import _scrub_internal

    # ensaio v5.2: 19 de 69 respostas ao vivo mostravam "[policy:capabilities]" ao cliente
    assert _scrub_internal("A proposta expira em 15 minutos [policy:capabilities].", "pt") == \
        "A proposta expira em 15 minutos."
    assert _scrub_internal("Nada é executado antes da sua confirmação ([policy:capabilities]).", "pt") == \
        "Nada é executado antes da sua confirmação."
    assert _scrub_internal("Conforme [policy:capabilities], o reinício precisa de confirmação.", "pt") == \
        "O reinício precisa de confirmação."
    assert _scrub_internal("I can restart it. Per [policy:capabilities], nothing runs until you confirm.", "en") == \
        "I can restart it. Nothing runs until you confirm."
