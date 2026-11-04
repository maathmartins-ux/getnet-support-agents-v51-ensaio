"""Resposta final sem artefato de texto, sem nome interno e sem conclusão que o dado não traz (rodada 12, frente A).

Frases literais das respostas ao vivo do ensaio (rodada 11): a limpeza do código do cartão deixava a oração pela
metade ("Segundo a,", "confirmar (."), o valor interno de enum chegava ao cliente ("sem_sinal"), o aviso da decisão
do operador saía só em português e com o nome da tool, e o redator tirava conclusão que o dado não trazia.
"""
import hashlib

import pytest
from fastapi.testclient import TestClient

from app import actions, capabilities, domain
from app.api import app
from app.auth import issue_token
from app.pipeline import _scrub_internal
from app.store import get_store

TICKET_TOOLS = {"open_support_ticket": {"description": "Abre chamado técnico.", "write": True, "input_schema": {
    "type": "object", "properties": {
        "terminal_id": {"type": "string"},
        "reason": {"type": "string", "enum": ["sem_conexao", "sem_sinal", "erro_transacao", "outro"]}}}},
    "get_settlements": {"description": "Agenda de depósitos.", "input_schema": {"type": "object", "properties": {
        "period": {"type": "string", "enum": ["yesterday", "today", "last_7_days"], "default": "yesterday"}}}}}
LABELS = {"sem_conexao": {"pt": "sem conexão", "en": "no connection"},
          "sem_sinal": {"pt": "sem sinal", "en": "no signal"},
          "erro_transacao": {"pt": "erro de transação", "en": "transaction error"},
          "last_7_days": {"pt": "últimos 7 dias", "en": "last 7 days"}, "yesterday": {"pt": "ontem", "en": "yesterday"},
          "today": {"pt": "hoje", "en": "today"}, "reason": {"pt": "motivo", "en": "reason"}}


# --- 1. a limpeza do código do cartão nunca deixa fragmento -------------------------------------------------------
@pytest.mark.parametrize("language, raw, clean", [
    # hitl-07: o artigo ficava sem o nome ("Segundo a, a antecipação")
    ("pt", "Você tem 3 vendas.\n\nSegundo a [policy:capabilities], a antecipação é uma ação de risco alto.",
     "Você tem 3 vendas.\n\nA antecipação é uma ação de risco alto."),
    # memory-16: o parêntese de abertura ficava ("confirmar (.")
    ("pt", "O chamado só é aberto depois que você confirmar (conforme [policy:capabilities]). Quer que eu proponha?",
     "O chamado só é aberto depois que você confirmar. Quer que eu proponha?"),
    # dependent-04: a preposição que a lista antiga não tinha ("From, I can")
    ("en", "A human agent decides that.\n\nFrom [policy:capabilities], I can look up your recent declines.",
     "A human agent decides that.\n\nI can look up your recent declines."),
    # o parêntese engolia a quebra de parágrafo e ficava aberto ("proponha? (Não encontrei")
    ("pt", "Quer que eu proponha? (conforme [policy:capabilities])\n\nNão encontrei um passo a passo.",
     "Quer que eu proponha?\n\nNão encontrei um passo a passo."),
    ("pt", "Posso encaminhar para um atendente humano.\n\nFonte: [policy:capabilities]",
     "Posso encaminhar para um atendente humano."),
    ("pt", "Segundo a [policy:capabilities] a antecipação é uma ação de risco alto.",
     "A antecipação é uma ação de risco alto."),
    ("en", "As stated in [policy:capabilities], nothing runs until you confirm.", "Nothing runs until you confirm."),
    ("pt", "Abri o chamado (ver [policy:capabilities]).", "Abri o chamado."),
    # entre vírgulas: sai o par de vírgulas, e a maiúscula não aparece no meio da frase
    ("pt", "A antecipação, segundo a [policy:capabilities], precisa de aprovação.",
     "A antecipação precisa de aprovação."),
    ("pt", "O chamado , conforme [policy:capabilities], só abre depois.", "O chamado só abre depois."),
    ("pt", "Prazo (15 minutos, conforme [policy:capabilities]) e confirmação.", "Prazo (15 minutos) e confirmação."),
    ("pt", "Prazo ([policy:capabilities], 15 minutos) e confirmação.", "Prazo (15 minutos) e confirmação."),
    ("pt", "Atenção: segundo a [policy:capabilities], nada é executado.", "Atenção: nada é executado."),
    ("pt", "- Segundo a [policy:capabilities], a proposta expira.\n- Outro item.",
     "- A proposta expira.\n- Outro item."),
    ("pt", "De acordo com o [policy:capabilities] e [policy:hitl], a proposta expira em 15 minutos.",
     "A proposta expira em 15 minutos."),
    # a frase que só apontava a citação sai inteira; a que responde fica
    ("pt", "Isso vale. Veja [policy:capabilities]. Depois disso, confirme.", "Isso vale. Depois disso, confirme."),
    ("pt", "Você pode ver [policy:capabilities]. Depois disso, confirme.", "Depois disso, confirme."),
    ("pt", "Sim, conforme [policy:capabilities]. Depois disso, confirme.", "Sim. Depois disso, confirme."),
    ("en", "Yes per [policy:capabilities]. Then confirm it.", "Yes. Then confirm it."),
    ("en", "Nothing is opened until you confirm. [policy:capabilities] If you prefer, I can help.",
     "Nothing is opened until you confirm. If you prefer, I can help."),
    ("pt", "Total: R$ 1.049,90 conforme [policy:capabilities].", "Total: R$ 1.049,90."),
])
def test_citation_scrub_never_leaves_a_fragment(language, raw, clean):
    out = _scrub_internal(raw, language)
    assert out == clean
    assert "Segundo a," not in out and "(." not in out and "( )" not in out and " ," not in out


def test_answer_that_was_only_the_citation_never_comes_back_empty():
    assert _scrub_internal("[policy:capabilities]", "pt").startswith("Não encontrei base")


def test_agent_names_keep_article_and_contraction():
    assert _scrub_internal("A resposta veio do faq_agent e pelo escalation_agent; enviei ao records_agent.", "pt") == (
        "A resposta veio da base de conhecimento e pelo atendimento humano; enviei aos dados da sua conta.")
    assert _scrub_internal("O faq_agent não achou.", "pt") == "A base de conhecimento não achou."
    assert _scrub_internal("I asked the records_agent.", "en") == "I asked your account data."


def test_text_without_internal_code_is_left_alone(monkeypatch):
    monkeypatch.setattr(capabilities, "_tools", lambda: TICKET_TOOLS)
    text = ("Ontem: R$ 1.049,90 (3 vendas) [sup-duvidas-06]. Veja https://site.com/minha_pagina e o campo user_id.\n\n"
            "- T1988B: sem sinal.")
    assert _scrub_internal(text, "pt") == text


# --- 3. valor interno de enum nunca chega cru ao cliente ----------------------------------------------------------
def test_enum_value_in_the_answer_becomes_the_readable_label(monkeypatch):
    monkeypatch.setattr(capabilities, "_tools", lambda: TICKET_TOOLS)
    # official-05 (en): 'with the reason "sem_sinal" or "sem_conexao"'
    raw = 'I can propose a support ticket for T1988B with the reason "sem_sinal" or "sem_conexao".'
    assert _scrub_internal(raw, "en") == 'I can propose a support ticket for T1988B with the reason "sem sinal" or ' \
                                         '"sem conexao".'  # sem rótulo do domínio: o valor sem "_"
    monkeypatch.setattr(domain.active(), "LABELS", LABELS, raising=False)
    assert _scrub_internal(raw, "en") == ('I can propose a support ticket for T1988B with the reason "no signal" or '
                                          '"no connection".')
    assert _scrub_internal("com motivo `sem_conexao`, `sem_sinal` ou `erro_transacao`", "pt") == (
        "com motivo sem conexão, sem sinal ou erro de transação")
    # a tradução que o modelo já pôs entre parênteses não repete
    assert _scrub_internal('with the reason "sem_conexao" (no connection).', "en") == 'with the reason "no connection".'
    assert _scrub_internal("Período consultado: last_7_days.", "pt") == "Período consultado: últimos 7 dias."
    assert _scrub_internal("Pagamento: today, pix.", "en") == "Pagamento: today, pix."  # valor de uma palavra fica


def test_capability_card_shows_the_label_of_each_option(monkeypatch):
    plain = capabilities.card("pt", tools=TICKET_TOOLS, extra=[])
    line = next(ln for ln in plain.splitlines() if ln.startswith("- Valores que as consultas"))
    # sem rótulo do domínio: o valor sem "_" (o valor cru fica no schema da tool, para a chamada)
    assert "reason: sem conexao | sem sinal | erro transacao | outro" in line
    assert "period (padrão yesterday): yesterday | today | last 7 days" in line
    assert "sem_sinal" not in line and "last_7_days" not in line
    monkeypatch.setattr(domain.active(), "LABELS", LABELS, raising=False)
    pt = capabilities.card("pt", tools=TICKET_TOOLS, extra=[])
    assert "open_support_ticket — motivo: sem conexão | sem sinal | erro de transação | outro" in pt
    assert "get_settlements — period (padrão ontem): ontem | hoje | últimos 7 dias" in pt
    en = capabilities.card("en", tools=TICKET_TOOLS, extra=[])
    assert "open_support_ticket — reason: no connection | no signal | transaction error | outro" in en
    assert "period (default yesterday): yesterday | today | last 7 days" in en
    assert "sem_sinal" not in pt + en and "last_7_days" not in pt + en


# --- 2. o aviso da decisão do operador: idioma da conversa e ação em palavras -------------------------------------
def _awaiting(conversation: str, said: str) -> str:
    store = get_store()
    store.add_message(conversation, "u1", "user", said, "records")
    aid = store.create_action(conversation, "u1", "refund_record", {"record_id": "1001"}, risk="high")
    assert actions.confirm_action(aid, "u1")["awaiting_operator"] is True
    return aid


def test_operator_decision_notice_speaks_the_customer_language_without_the_tool_name(monkeypatch):
    aid = _awaiting("c-en", "I want a refund for my order 1001, please")
    assert actions.decide_action(aid, "ana", approve=False, note="Out of policy.") is not None
    last = get_store().history("c-en")[-1]["content"]
    assert last == f"Your request ({aid}) was declined by an agent. Agent's note: Out of policy."
    monkeypatch.setattr(domain.active(), "LABELS", {"refund_record": {"pt": "estorno do pedido", "en": "order refund"}},
                        raising=False)
    aid = _awaiting("c-pt", "Quero o estorno do pedido 1001")
    actions.decide_action(aid, "ana", approve=False)
    assert get_store().history("c-pt")[-1]["content"] == f"Sua solicitação (estorno do pedido, {aid}) foi recusada " \
                                                          "por um atendente."


def test_approved_notice_in_portuguese_has_no_internal_name(monkeypatch):
    # aprovar risco alto exige chave pessoal (o token compartilhado não aprova): a da Ana, ao lado do compartilhado
    monkeypatch.setenv("OPERATOR_KEYS", "ana:" + hashlib.sha256(b"chave-pessoal-da-ana").hexdigest())
    monkeypatch.setenv("OPERATOR_SHARED_TOKEN", "on")
    client = TestClient(app)
    auth = {"Authorization": f"Bearer {issue_token('u1')}"}
    r = client.post("/chat", json={"message": "Quero o estorno do pedido 1001"}, headers=auth).json()
    aid = r["pending_action"]
    client.post(f"/actions/{aid}/confirm", headers=auth)
    ana = {"X-Operator-Token": "chave-pessoal-da-ana"}
    assert client.post(f"/actions/{aid}/approve", headers=ana).status_code == 200
    last = client.get(f"/conversations/{r['conversation_id']}", headers=auth).json()["messages"][-1]["content"]
    assert last == f"Sua solicitação ({aid}) foi aprovada por um atendente e executada."
    assert "refund_record" not in last


# --- 4. contrato do motor: dado sem conclusão inventada; sim/não começa pela resposta -----------------------------
RULES = {
    "records.md": ["não conclua causa, proporção (\"a maioria\") nem relação entre registros",
                   "Valor interno de lista fechada (motivo, período, status) não vai ao cliente"],
    "supervisor.md": ["não acrescente conclusão que eles não trazem", "a 1ª frase responde com o próprio dado"],
    "faq.md": ["a 1ª frase é a resposta direta, começa por sim, não ou \"depende de X\"",
               "o que o trecho da regra diz, com a citação", "nem por uma lista de opções"],
}


@pytest.mark.parametrize("name", sorted(RULES))
def test_engine_contract_rules_reach_domain_and_kit_prompts(tmp_path, monkeypatch, name):
    (tmp_path / name).write_text("Domínio.\n", encoding="utf-8")
    monkeypatch.setattr(domain.active(), "PROMPTS_DIR", tmp_path, raising=False)
    with_contract = " ".join(domain.prompt(name).split())
    monkeypatch.setattr(domain.active(), "PROMPTS_DIR", domain.KIT_PROMPTS, raising=False)
    kit = " ".join(domain.prompt(name).split())
    for rule in RULES[name]:
        assert rule in with_contract and rule in kit, rule


@pytest.mark.parametrize("name", ["faq.md", "records.md"])
def test_kit_prompt_carries_every_line_of_the_engine_contract(name):
    """O prompt do kit (domínio de exemplo e cópia do pré-voo) traz o contrato no texto: regra nova não fica só nele."""
    kit = " ".join((domain.KIT_PROMPTS / name).read_text(encoding="utf-8").split())
    lines = [" ".join(ln.strip().removeprefix("- ").split())
             for ln in (domain.CONTRACT / name).read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("Regras do motor")]
    assert [ln for ln in lines if ln not in kit] == []
