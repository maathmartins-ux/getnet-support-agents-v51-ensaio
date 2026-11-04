"""Orquestração de um turno: guardrails → memória → router → supervisor → saída segura → persistência.

Os forks trocam agentes e regras do router; a assinatura de `handle` (ChatRequest, user_id
autenticado, identity_verified -> ChatResponse) não muda.

Latência: com LLM, o classificador de segurança (camada 2) e o router rodam em paralelo sobre o texto
já mascarado; se o guardrail bloquear, a decisão do router é descartada.
"""
from __future__ import annotations

import contextvars
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import capabilities, cases, casestate, claims, domain, grounding, memory, router, supervisor
from .agents import Context, escalation_agent
from .grounding import risk_flags, unsupported_numbers
from .guardrails import UNAVAILABLE, Verdict, llm_check, mask_output, pre_check
from .llm import get_llm
from .observability import METRICS, log, new_trace_id, prompt_versions, request_usage, span
from .rag import get_index
from .router import detect_language, route
from .schemas import ChatRequest, ChatResponse, Handoff, RouterDecision, Usage
from .store import get_store

REFUSAL = {
    "pt": "Não posso atender a esse pedido. Posso ajudar com dúvidas sobre o produto ou sua conta.",
    "en": "I can't help with that request. I can help with product or account questions.",
}
# Autoagressão não recebe a recusa seca: recebe apoio e o CVV (188, 24 h, gratuito, no Brasil). Texto fixo, sem LLM.
SELF_HARM_SUPPORT = {
    "pt": "Sinto muito que você esteja passando por isso. Você não precisa enfrentar sozinho: o CVV atende "
          "24 horas, de graça, pelo telefone 188 ou em cvv.org.br. Se houver risco imediato, ligue 192 (SAMU).",
    "en": "I'm sorry you're going through this. You don't have to face it alone: in Brazil, CVV answers 24/7, free, "
          "at 188 (cvv.org.br). If you are in immediate danger, call 192 (SAMU) or your local emergency number.",
}
NO_ANSWER = {
    "pt": "Não encontrei base para responder com segurança. Posso encaminhar para um atendente humano.",
    "en": "I couldn't find a reliable basis to answer. I can hand this to a human agent.",
}
SUMMARY_TURNS = 5
HISTORY_WINDOW = 20  # mensagens recentes inteiras no contexto (10 turnos)
DIGEST_ITEMS = 8  # falas antigas resumidas além da janela
# O roteador recebe a conversa INTEIRA: o assunto do turno 1 decide "e ele já saiu?" no turno 14 (medido: com só
# 20 mensagens, o 1º turno de uma conversa de 26 sumia). Fora da janela, só falas do cliente, cortadas e com teto.
ROUTER_OLDER_CHARS = 120
ROUTER_OLDER_MAX = 200  # 200 x 120 caracteres: teto de memória; o prompt do LLM usa só intenções e as 4 últimas


def _router_history(store, conversation_id: str, history: list[dict]) -> list[dict]:
    older = [{"role": "user", "content": m["content"][:ROUTER_OLDER_CHARS], "intent": m["intent"]}
             for m in store.older_messages(conversation_id, skip_last=HISTORY_WINDOW) if m["role"] == "user"]
    return older[-ROUTER_OLDER_MAX:] + history


def _update_summary(store, user_id: str, intent: str, text: str) -> None:
    """Memória de longo prazo determinística: últimos assuntos do usuário, entre conversas.

    Determinística de propósito: auditável, sem custo e sem PII (o texto já chega mascarado).
    """
    items = [i for i in store.user_summary(user_id).split(" | ") if i]
    items.append(f"{intent}: {text[:80]}")
    store.set_user_summary(user_id, " | ".join(items[-SUMMARY_TURNS:]))


_INTERNAL_NAMES = {"faq_agent": ("a base de conhecimento", "the knowledge base"),
                   "records_agent": ("os dados da sua conta", "your account data"),
                   "escalation_agent": ("o atendimento humano", "a human agent")}
_INTERNAL_RE = re.compile(r"(?:\b(?:o|a|the)\s+)?`?\b(" + "|".join(_INTERNAL_NAMES) + r")\b`?", re.IGNORECASE)


# Citação do cartão de capacidades ("[policy:capabilities]") é para o verificador, não para o cliente. Sem esta
# limpeza, 19 de 69 respostas ao vivo (3 das 10 oficiais) mostravam o código ao cliente.
# "Conforme [policy:x], o..." vira "O..."; no fim de frase, some com o espaço e os parênteses em volta.
_POLICY_LEAD_RE = re.compile(r"\b(?:per|according to|as per|by|under|conforme|segundo|de acordo com|pelo|pela|"
                             r"pelas|pelos|na|no)\s+"
                             r"\(?\[policy:[\w.-]+\]\)?,?\s*(\w)?", re.IGNORECASE)
_POLICY_REF_RE = re.compile(r"\s*\(?\[policy:[\w.-]+\]\)?")


def _scrub_internal(answer: str, language: str) -> str:
    """Nome interno de agente (ex.: "faq_agent") e código do cartão de capacidades não chegam ao
    cliente."""
    i = 1 if language == "en" else 0
    answer = _INTERNAL_RE.sub(lambda m: _INTERNAL_NAMES[m.group(1)][i], answer)
    answer = _POLICY_LEAD_RE.sub(lambda m: (m.group(1) or "").upper(), answer)
    answer = _POLICY_REF_RE.sub("", answer)
    # o que sobrou da citação tirada: "atendente, ." → "atendente."; ", ," → ","; espaço antes de pontuação
    answer = re.sub(r"\s*,\s*(?=[.;:!?])", "", answer)
    return re.sub(r"[ \t]+([,.;:!?])", r"\1", answer)


def _digest(store, conversation_id: str, ledger: memory.Ledger | None = None) -> str:
    """Resumo rolante e determinístico do que saiu da janela recente (o turno 15 ainda sabe do turno 1).

    Guarda as falas do cliente e do atendente (com a intenção), já mascaradas; sem LLM, sem custo, auditável.
    Cortar cada fala em 120 caracteres e manter só as últimas perde id, valor e data de conversa longa: a linha
    final do livro de fatos devolve ao resumo o que o cliente disse (app/memory.py), para qualquer leitor dele.
    """
    older = store.older_messages(conversation_id, skip_last=HISTORY_WINDOW)
    if not older:
        return ""
    items = [f"[{m['intent'] or m['role']}] {m['content'][:120]}" for m in older if m["role"] != "assistant"]
    kept = " | ".join(items[-DIGEST_ITEMS:])
    return f"{kept} | {facts}" if ledger and (facts := ledger.digest_line()) else kept


@dataclass
class _Check:
    unsupported: list[str]
    claims: list[str]

    def size(self) -> int:
        return len(self.unsupported) + len(self.claims)


def _log_prompts(trace_id: str) -> dict[str, str]:
    """Versões das instruções deste request, no log (uma linha por request) e na resposta."""
    versions = prompt_versions()
    if versions:
        log.info("prompt_versions", extra={"extra_fields": {"trace_id": trace_id, "prompts": versions}})
    return versions


def _check(answer: str, evidence: list[str], said: str, outcome, handoff: Handoff) -> _Check:
    calls = [c for r in outcome.results for c in r.tool_calls]
    ticket = handoff.required or any(r.handoff and r.handoff.ticket_id for r in outcome.results)
    return _Check(unsupported_numbers(answer, evidence, question=said),
                  grounding.claimed_actions(answer, calls, ticket, evidence))


LANGUAGE_MIN_WORDS = 8  # resposta curta ("Ok", um nome, um número) não tem como o detector decidir


def wrong_language(answer: str, language: str) -> bool:
    """A resposta está claramente no outro idioma (vantagem de >= 2 palavras do idioma errado)?"""
    return len(answer.split()) >= LANGUAGE_MIN_WORDS and router.clear_language(answer) not in (None, language)


def _fix_language(answer: str, final: _Check, *, ctx: Context, evidence: list[str], said: str, outcome,
                  handoff: Handoff, public: str) -> tuple[str, _Check]:
    """Idioma errado na saída: UMA reescrita (só com LLM) que não pode piorar número nem ação alegada."""
    if not wrong_language(answer, ctx.language):
        return answer, final
    METRICS.inc("language_mismatch_total", expected=ctx.language)
    name = grounding.LANGUAGE_NAME.get(ctx.language, ctx.language)
    fixed = grounding.rewrite(answer, [f"idioma: o cliente escreveu em {name}; reescreva a resposta INTEIRA em {name}, "
                                       "sem mudar nenhum fato nem número"],
                              language=ctx.language, evidence=evidence, question=ctx.text)
    if not fixed:
        return answer, final
    fixed = mask_output(fixed, public=public)
    after = _check(fixed, evidence, said, outcome, handoff)
    ok = (not wrong_language(fixed, ctx.language) and len(after.unsupported) <= len(final.unsupported)
          and len(after.claims) <= len(final.claims))
    METRICS.inc("language_rewrites_total", outcome="accepted" if ok else "rejected")
    return (fixed, after) if ok else (answer, final)


def _lost_live_values(before: str, after: str, outcome, language: str) -> bool:
    """A checagem de frases cortou um valor obrigatório do dado ao vivo que a resposta trazia antes dela?"""
    from .agents import live_missing

    for r in outcome.results:
        must = getattr(r, "live_must", None)
        if must and len(live_missing(after, must, language)) > len(live_missing(before, must, language)):
            return True
    return False


def _drops_live_values(outcome, language: str) -> bool:
    """A resposta redigida pelo supervisor deixou de fora um valor obrigatório (mínima, máxima, chance de chuva; venda
    e compra) que o texto do especialista de dado ao vivo traz?"""
    from .agents import live_missing

    for r in outcome.results:
        must = getattr(r, "live_must", None)
        if must and r.text and not live_missing(r.text, must, language) and live_missing(outcome.answer, must,
                                                                                       language):
            return True
    return False


def _enforce(answer: str, *, evidence: list[str], said: str, ctx: Context, outcome, handoff: Handoff,
             route: list[str], public: str) -> tuple[str, list[str], str, list[str], Handoff]:
    """Saída segura da resposta final: (resposta, números sem base, numbers_action, rótulos de risco, handoff).

    1) detecta no rascunho: número sem base e ação alegada sem execução (tool/caso do turno);
    2) com LLM, UMA reescrita com a mesma evidência, a lista dos números proibidos e as frases a corrigir; vale se
       não piorar nada e melhorar algo;
    3) o que sobrar: números seguem NUMBERS_POLICY (flag só sinaliza; redact troca por "[valor não confirmado]" e
       oferece o humano; escalate troca e abre o caso; intenção sem escalonamento, ex. clima, cai em redact);
       ação alegada sai da resposta com o aviso de que nada foi feito. Ação alegada sempre vira `claimed_action`.
    """
    lang = ctx.language
    policy = grounding.numbers_policy()
    draft = _check(answer, evidence, said, outcome, handoff)
    risks = ["claimed_action"] if draft.claims else []
    if draft.unsupported:
        METRICS.inc("numeric_ungrounded_total")
        log.warning("numeric_ungrounded", extra={"extra_fields": {"numbers": draft.unsupported, "policy": policy}})
    if draft.claims:
        METRICS.inc("claimed_action_total")
        log.warning("claimed_action", extra={"extra_fields": {"claims": draft.claims}})
    problems: list[str] = []
    if draft.unsupported and policy != "flag":
        problems.append("números sem base na evidência (proibidos): " + ", ".join(draft.unsupported))
    if draft.claims:
        problems.append("alega ação que nenhuma ferramenta executou neste turno: " + "; ".join(draft.claims))
    final = draft
    if problems:
        fixed = grounding.rewrite(answer, problems, language=lang, evidence=evidence, question=ctx.text)
        if fixed:
            fixed = mask_output(fixed, public=public)
            after = _check(fixed, evidence, said, outcome, handoff)
            if len(after.unsupported) <= len(draft.unsupported) and len(after.claims) <= len(draft.claims) \
                    and after.size() < draft.size():
                answer, final = fixed, after
            METRICS.inc("answer_rewrites_total", outcome="accepted" if final is after else "rejected")
    answer, final = _fix_language(answer, final, ctx=ctx, evidence=evidence, said=said, outcome=outcome,
                                  handoff=handoff, public=public)
    action = "regenerated" if draft.unsupported and not final.unsupported else "none"
    if final.unsupported:
        if policy == "flag":
            action = "flagged"
        else:
            answer = grounding.redact(answer, final.unsupported, lang)
            escalate = policy == "escalate" and not handoff.required \
                and ctx.intent not in domain.active().NO_ESCALATION
            if escalate:
                ctx.handoff_reason = "unsupported_numbers"
                esc = escalation_agent(ctx)
                answer = f"{answer}\n\n{esc.text}"
                handoff = esc.handoff or handoff
                route.append("escalation")
                action = "escalated"
            else:
                answer = f"{answer}\n\n{grounding.OFFER.get(lang, grounding.OFFER['pt'])}"
                action = "redacted"
    if final.claims:
        answer = grounding.drop_claims(answer, final.claims, lang)
    if action != "none":
        METRICS.inc("numeric_enforced_total", action=action)
    return answer, final.unsupported, action, risks, handoff


WRITE_HELD = {"pt": "Não posso propor alterações agora: a verificação de segurança está indisponível. "
                    "Tente de novo em instantes.",
              "en": "I can't propose changes right now: the safety check is unavailable. Please try again shortly."}


def _hold_writes(store, outcome, language: str) -> None:
    """Sem o classificador LLM, a escrita proposta no turno é recusada (falha fechada para escrita)."""
    for result in outcome.results:
        if result.pending_action:
            store.claim_action(result.pending_action, frm="pending", to="expired")
            METRICS.inc("writes_held_total", reason=UNAVAILABLE)
            result.pending_action, result.text = None, WRITE_HELD.get(language, WRITE_HELD["pt"])
            outcome.answer = None  # a resposta é remontada dos resultados, já sem a proposta


def _guard_and_route(message: str, history: list[dict]) -> tuple[Verdict, RouterDecision | None]:
    with span("guardrails"):
        verdict = pre_check(message)
    if verdict.blocked:
        return verdict, None
    if not get_llm("guardrail").enabled:
        verdict = llm_check(verdict)  # sem classificador: a suspeita da camada 1 bloqueia (falha fechada)
        if verdict.blocked:
            return verdict, None
        with span("router"):
            return verdict, route(verdict.text, history)
    with ThreadPoolExecutor(max_workers=2) as pool:
        g = pool.submit(contextvars.copy_context().run, llm_check, verdict)
        r = pool.submit(contextvars.copy_context().run, route, verdict.text, history)
        with span("router"):
            decision = r.result()
        verdict = g.result()
    return verdict, (None if verdict.blocked else decision)


def handle(req: ChatRequest, user_id: str, identity_verified: bool = True) -> ChatResponse:
    t0 = time.perf_counter()
    resp = _handle(req, user_id, identity_verified)
    try:  # analytics é melhor esforço: falha ao registrar nunca derruba o atendimento
        get_store().log_request({
            "trace_id": resp.trace_id, "conversation_id": resp.conversation_id, "user_id": user_id,
            "intent": resp.intent, "route": resp.route, "handoff": resp.handoff.required, "blocked": resp.blocked,
            "ungrounded": bool(resp.unsupported_numbers), "cost_usd": resp.usage.cost_usd,
            "ms": round((time.perf_counter() - t0) * 1000, 1)})  # sem o texto: analytics não guarda conteúdo
        # evidência (mascarada) e versão das instruções: o 👎 desta resposta vira candidato a caso com elas
        get_store().save_snapshot(resp.trace_id, resp.conversation_id, list(resp.evidence), resp.prompt_versions)
    except Exception as exc:  # noqa: BLE001
        log.warning("analytics_log_failed", extra={"extra_fields": {"error": type(exc).__name__}})
    return resp


def _handle(req: ChatRequest, user_id: str, identity_verified: bool = True) -> ChatResponse:
    trace_id = new_trace_id()
    store = get_store()
    conversation_id = req.conversation_id or uuid.uuid4().hex[:12]
    owner = store.conversation_owner(conversation_id)
    if owner and owner != user_id:
        raise PermissionError("conversation belongs to another user")
    language = detect_language(req.message)
    base = {"trace_id": trace_id, "conversation_id": conversation_id, "user_id": user_id,
            "identity_verified": identity_verified}
    if not identity_verified:
        log.info("unverified_identity", extra={"extra_fields": {"user_id": user_id, "auth_mode": "demo"}})

    history = store.history(conversation_id, limit=HISTORY_WINDOW)
    verdict, decision = _guard_and_route(req.message, _router_history(store, conversation_id, history))
    if verdict.blocked or decision is None:
        METRICS.inc("chat_requests_total", intent="blocked")
        METRICS.inc("guardrail_blocks_total", reason=verdict.reason or "unknown")
        answer = (SELF_HARM_SUPPORT if verdict.reason == "self_harm" else REFUSAL)[language]
        return ChatResponse(**base, answer=answer, intent="blocked", route=["guardrails"],
                            language=language, blocked=True, guardrails=verdict.flags, usage=Usage(**request_usage()))

    language = decision.language
    ledger = memory.load(store, conversation_id)  # fatos da conversa: sobrevivem ao resumo (app/memory.py)
    ctx = Context(text=verdict.text, language=language, user_id=user_id, conversation_id=conversation_id,
                  intent=decision.intent, history=history, user_summary=store.user_summary(user_id),
                  conversation_digest=_digest(store, conversation_id, ledger), ledger=ledger.render())
    case_action = casestate.observe(conversation_id, verdict.text)  # o cliente confirmou, ou continua com o problema
    if case_action == "escalate":
        ctx.facts["escalation_note"] = casestate.summary_for_operator(conversation_id)
    if tried := casestate.attempts(conversation_id):
        ctx.facts["attempted_steps"] = tried  # o agente não repete o mesmo conselho
    if hint := router.standalone_query(verdict.text, history):  # seguimento herda o assunto na busca do RAG
        ctx.facts.setdefault("query_hints", []).append(hint)
        METRICS.inc("query_followup_total")
    # contrato router → faq: a pergunta completa do turno ("" = reescrita recusada); o faq busca por ela quando houver
    ctx.facts["standalone"] = getattr(decision, "standalone", "") or ""
    ctx.facts["search_queries"] = list(getattr(decision, "search_queries", []) or [])  # consultas do RAG (LLM)
    outcome = supervisor.run(list(decision.plan), ctx, decision.confidence)
    if UNAVAILABLE in verdict.flags:
        _hold_writes(store, outcome, language)

    answer = outcome.answer or "\n\n".join(r.text for r in outcome.results if r.text)
    if outcome.answer and _drops_live_values(outcome, language):
        # a redação do supervisor LLM perdeu valor obrigatório do dado ao vivo que o especialista entregou conferido
        # (medido: a mínima e a máxima ficaram, a chance de chuva saiu): vale a junção dos textos dos especialistas
        METRICS.inc("supervisor_answer_dropped_live_total")
        outcome.answer = None
        answer = "\n\n".join(r.text for r in outcome.results if r.text)
    if not answer.strip():  # nunca 200 vazio: vazio no histórico vira 400 da API no turno seguinte
        answer = NO_ANSWER[language]
    docs = {d.id: d.text for d in get_index().docs}
    public = "\n".join(docs.get(s.id, "") for r in outcome.results for s in r.sources)
    answer = mask_output(answer, public=public)
    # número que não está em fonte, tool, template, pergunta nem fala anterior do cliente/operador → reescrita única
    # com LLM e, se persistir, a política NUMBERS_POLICY (flag | redact | escalate)
    # + fatos do cliente e das ferramentas de turnos anteriores (livro) e as URLs que o próprio sistema citou como
    # fonte; nunca a fala do assistente, para um número inventado antes não virar base depois
    said = " ".join([verdict.text, ctx.conversation_digest, ledger.known_text(),
                     *(s.url for r in outcome.results for s in r.sources if s.url),
                     *(m["content"] for m in history if m.get("role") != "assistant")])
    # cartão de capacidades (app/capabilities.py) é evidência do turno: regra de confirmação/aprovação e o TTL têm base
    card = capabilities.card(language)
    turn_evidence = [e for r in outcome.results for e in r.evidence]
    # o que o redator recebeu como "Fatos da conversa" também é base do turno, e vai para quem audita (juiz, eval):
    # sem isso, resposta que usa o status da maquininha lido 2 turnos antes parecia sem fonte
    remembered = [f"[memória da conversa] {mem}"] if (mem := ledger.render()) else []
    evidence = turn_evidence + remembered + [card]
    handoff = next((r.handoff for r in outcome.results if r.handoff), None) or Handoff()
    route = ["router", *outcome.route]
    answer, unsupported, numbers_action, extra_risks, handoff = _enforce(
        answer, evidence=evidence, said=said, ctx=ctx, outcome=outcome, handoff=handoff, route=route, public=public)
    # depois dos números: frase sem base e ação oferecida que não existe (CLAIMS_POLICY remove | flag | off)
    answer = _scrub_internal(answer, language)
    blocked = any(r.agent == "hold" for r in outcome.results)
    before_claims = answer
    answer, claim_report = claims.enforce(answer, evidence=evidence[:-1], question=verdict.text, card=card,
                                          writes_blocked=blocked)
    if _lost_live_values(before_claims, answer, outcome, language):
        # a checagem de frases tirou, junto com um conselho sem base ("leve guarda-chuva"), a frase que trazia um valor
        # obrigatório do dado ao vivo: vale o texto do especialista (que já passou pela conferência dos valores), com a
        # mesma checagem de frases
        METRICS.inc("claims_cut_live_value_total")
        specialist = "\n\n".join(r.text for r in outcome.results if r.text)
        answer, claim_report = claims.enforce(_scrub_internal(mask_output(specialist, public=public), language),
                                              evidence=evidence[:-1], question=verdict.text, card=card,
                                              writes_blocked=blocked)
    if case_action == "escalate":  # 2º ciclo sem sucesso: humano, com as tentativas, qualquer que seja o motivo
        if not handoff.required:
            ctx.handoff_reason = "unresolved_after_cycles"
            esc = escalation_agent(ctx)
            answer, handoff = f"{answer}\n\n{esc.text}", esc.handoff or handoff
            route.append("escalation")
        ticket = handoff.ticket_id or next((r.handoff.ticket_id for r in outcome.results
                                            if r.handoff and r.handoff.ticket_id), None)
        if ticket:  # o turno pode já ter escalado por outro motivo (sem fonte): o operador recebe as tentativas igual
            cases.attach_note(ticket, casestate.summary_for_operator(conversation_id))
        METRICS.inc("case_escalated_total", reason=handoff.reason or "unknown")
    case_state = {"resolved": "resolved", "escalate": "escalated"}.get(case_action) or casestate.after_turn(
        conversation_id, decision.intent, [c for r in outcome.results for c in r.tool_calls], answer)
    risks = risk_flags(answer, evidence) + extra_risks
    for label in risks:
        METRICS.inc("risk_flags_total", flag=label)
    if risks:
        log.warning("risk_flagged", extra={"extra_fields": {"trace_id": trace_id, "flags": risks}})
    store.add_message(conversation_id, user_id, "user", verdict.text, decision.intent)  # texto já mascarado
    store.add_message(conversation_id, user_id, "assistant", answer, decision.intent)
    _update_summary(store, user_id, decision.intent, verdict.text)
    memory.update(ledger, user_text=verdict.text, intent=decision.intent, evidence=turn_evidence + [card],
                  states_subject=router.has_stated_subject(verdict.text))
    memory.save(store, conversation_id, ledger)

    METRICS.inc("chat_requests_total", intent=decision.intent)
    if handoff.required:
        METRICS.inc("handoffs_total", reason=handoff.reason or "unknown")
    return ChatResponse(
        **base, answer=answer, intent=decision.intent, confidence=decision.confidence,
        route=route, replans=outcome.replans, engine=outcome.engine, language=language,
        sources=[s for r in outcome.results for s in r.sources],
        tool_calls=[c for r in outcome.results for c in r.tool_calls], handoff=handoff,
        pending_action=next((r.pending_action for r in outcome.results if r.pending_action), None),
        guardrails=verdict.flags, unsupported_numbers=unsupported, risk_flags=risks,
        numbers_action=numbers_action, case_state=case_state, usage=Usage(**request_usage()),
        prompt_versions=_log_prompts(trace_id),
        # mesma evidência da checagem de números (com o cartão), mascarada como a resposta: o eval grava e o juiz lê
        evidence=[mask_output(e, public=public) for e in evidence],
        unsupported_claims=claim_report.as_list(), claims_action=claim_report.action,
        steps=[supervisor.step_view(r, lambda t: mask_output(t, public=public)) for r in outcome.results])
