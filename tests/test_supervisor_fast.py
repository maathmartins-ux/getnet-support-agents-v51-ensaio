"""Atalho do supervisor: plano de 1 passo com router confiante não chama o supervisor LLM (2 chamadas a menos)."""
from fakes import fake_llm, resp, text, tool_use

from app import supervisor
from app.agents import AgentResult, Context


def ctx(text_, intent="knowledge", **facts):
    c = Context(text=text_, language="pt", user_id="u1", conversation_id="c-fast", intent=intent)
    c.facts.update(facts)
    return c


def use_llm(monkeypatch, llm):
    monkeypatch.setattr(supervisor, "get_llm", lambda role="agent": llm)


def faq_ok(c):
    return AgentResult("faq", "ok", text="Resposta do agente [doc-1].")


def test_single_step_confident_plan_skips_the_supervisor_llm(monkeypatch):
    llm, msgs = fake_llm([])  # roteiro vazio: qualquer chamada ao supervisor quebraria o teste
    use_llm(monkeypatch, llm)
    monkeypatch.setitem(supervisor.AGENTS, "faq", faq_ok)
    out = supervisor.run(["faq"], ctx("Qual a taxa do débito?"), confidence=0.9)
    assert msgs.sent == [] and out.engine == "fast_path" and out.route == ["faq"]
    assert out.answer is None and out.results[0].text == "Resposta do agente [doc-1]."  # o texto do agente é a resposta


def test_fast_path_insufficient_goes_to_the_llm_and_keeps_the_table_fallback_if_it_fails(monkeypatch):
    # kit v5.3: o insufficient do atalho vai ao supervisor LLM (tests/test_r53_supervisor.py); se o LLM falha, a
    # tabela aplica o FALLBACK de antes, sem rodar o faq de novo
    from app.llm import LLMError

    llm, msgs = fake_llm([LLMError("api_status_529", "api_status")])
    use_llm(monkeypatch, llm)
    calls = []
    monkeypatch.setitem(supervisor.AGENTS, "faq", lambda c: calls.append(1) or AgentResult("faq", "insufficient",
                                                                                         reason="no_source"))
    out = supervisor.run(["faq"], ctx("Qual a capital da Mongólia?"), confidence=0.95)
    assert len(msgs.sent) == 1 and len(calls) == 1 and out.route == ["faq", "escalation"] and out.engine == "table"
    assert out.replans == ["faq:no_source->escalation"] and out.results[-1].handoff.reason == "faq_no_source"


def _llm_answers():
    return fake_llm([resp("tool_use", tool_use("faq_agent", {"query": "q"})), resp("end_turn", text("Do LLM."))])


def test_uncertain_router_multi_step_plan_resume_and_flag_off_still_use_the_llm(monkeypatch):
    monkeypatch.setitem(supervisor.AGENTS, "faq", faq_ok)
    monkeypatch.setitem(supervisor.AGENTS, "records", lambda c: AgentResult("records", "ok", text="dados"))
    cases = [
        (["faq"], ctx("talvez taxa?"), 0.6),  # abaixo de SUPERVISOR_FAST_MIN_CONFIDENCE (0.8)
        (["records", "faq"], ctx("maquininha não liga", "troubleshoot"), 0.95),  # 2 passos: compor partes
        (["faq"], ctx("e agora?", operator_answer="o prazo é 2 dias"), 0.95),  # retomada com resposta humana
    ]
    for plan, c, conf in cases:
        llm, msgs = _llm_answers()
        use_llm(monkeypatch, llm)
        out = supervisor.run(plan, c, confidence=conf)
        assert out.engine == "llm" and out.answer == "Do LLM." and len(msgs.sent) == 2, (plan, conf)
    monkeypatch.setenv("SUPERVISOR_FAST", "off")
    llm, msgs = _llm_answers()
    use_llm(monkeypatch, llm)
    assert supervisor.run(["faq"], ctx("Qual a taxa?"), confidence=0.99).engine == "llm"
    monkeypatch.setenv("SUPERVISOR_FAST", "on")
    monkeypatch.setenv("SUPERVISOR_FAST_MIN_CONFIDENCE", "0.99")
    llm, msgs = _llm_answers()
    use_llm(monkeypatch, llm)
    assert supervisor.run(["faq"], ctx("Qual a taxa?"), confidence=0.95).engine == "llm"


def test_step_others_depend_on_runs_before_the_first_llm_round(monkeypatch):
    """Plano ["records", "faq"] com faq DEPENDENDO de records: o código roda records e o modelo já começa no faq."""
    from app import domain

    monkeypatch.setattr(domain.active(), "DEPENDS", {"faq": {"records"}})
    assert supervisor.lead_step(["records", "faq"], ctx("x", "troubleshoot")) is None  # opt-in: padrão desligado
    monkeypatch.setenv("SUPERVISOR_LEAD", "on")
    order: list[str] = []
    monkeypatch.setitem(supervisor.AGENTS, "records",
                        lambda c: order.append("records") or AgentResult("records", "ok", text="T1 offline"))
    monkeypatch.setitem(supervisor.AGENTS, "faq", lambda c: order.append("faq") or faq_ok(c))
    llm, msgs = fake_llm([
        lambda kw: order.append("llm") or resp("tool_use", tool_use("faq_agent", {"query": "T1 offline"})),
        lambda kw: order.append("llm") or resp("end_turn", text("Resposta composta.")),
    ])
    use_llm(monkeypatch, llm)
    out = supervisor.run(["records", "faq"], ctx("maquininha não conecta", "troubleshoot"), confidence=0.9)
    assert order == ["records", "llm", "faq", "llm"] and len(msgs.sent) == 2  # uma volta do supervisor a menos
    first = msgs.sent[0]["messages"][0]["content"]
    assert "records_agent →" in first and "T1 offline" in first  # o modelo vê o resultado antes de decidir
    assert out.engine == "llm" and out.route == ["records", "faq"] and out.answer == "Resposta composta."
    assert out.replans == []  # seguir o plano não é desvio

    # sem dependência (passos independentes), ou na retomada, o modelo decide desde a 1ª volta
    monkeypatch.setattr(domain.active(), "DEPENDS", {})
    assert supervisor.lead_step(["records", "faq"], ctx("x", "troubleshoot")) is None
    monkeypatch.setattr(domain.active(), "DEPENDS", {"faq": {"records"}})
    assert supervisor.lead_step(["records", "faq"], ctx("x", "troubleshoot", operator_answer="ok")) is None
    assert supervisor.lead_step(["records"], ctx("x", "support")) is None


def test_fast_path_offers_a_human_when_the_answer_says_the_sources_do_not_cover_it(monkeypatch):
    llm, msgs = fake_llm([])
    use_llm(monkeypatch, llm)
    gap = "The passages don't say whether a bank account is required [doc-1]."
    monkeypatch.setitem(supervisor.AGENTS, "faq", lambda c: AgentResult("faq", "ok", text=gap))
    en = ctx("Do I need a bank account for Pix?")
    en.language = "en"
    out = supervisor.run(["faq"], en, confidence=0.9)
    assert out.results[0].text == f"{gap}\n\n{supervisor.OFFER_HUMAN['en']}"
    # a oferta casa com o encaminhamento humano: o verificador de claims não a corta
    from app import claims
    assert not [u for u in claims.check(out.results[0].text, ["x"], use_llm=False)[1] if u["source"] == "offer"]

    # resposta completa, resposta que já oferece o humano e intenção que nunca escala: nada muda
    monkeypatch.setitem(supervisor.AGENTS, "faq", faq_ok)
    assert supervisor.run(["faq"], ctx("Qual a taxa?"), confidence=0.9).results[0].text == "Resposta do agente [doc-1]."
    offered = "Não encontrei isso nas fontes. Posso encaminhar a um atendente humano."
    monkeypatch.setitem(supervisor.AGENTS, "faq", lambda c: AgentResult("faq", "ok", text=offered))
    assert supervisor.run(["faq"], ctx("x?"), confidence=0.9).results[0].text == offered
    monkeypatch.setattr(supervisor.domain.active(), "NO_ESCALATION", {"general"})
    monkeypatch.setitem(supervisor.AGENTS, "faq", lambda c: AgentResult("faq", "ok", text="Não encontrei a previsão."))
    out = supervisor.run(["faq"], ctx("chove?", "general"), confidence=0.9)
    assert out.results[0].text == "Não encontrei a previsão."
