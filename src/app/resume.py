"""Retomada depois do humano: a resposta do operador volta à conversa e o PLANO continua na hora.

Sem isto, a resposta humana só apareceria no próximo turno do cliente e o resto do plano se perderia. Ao
responder um caso (console, API ou Telegram):
1. o assistente redige a próxima mensagem ao cliente a partir da resposta humana, que é a autoridade
   (prompts/resume.md): com LLM, papel "agent", histórico curto + resposta humana; sem LLM, ou se ele falhar,
   a resposta humana literal, identificada;
2. a resposta do operador vira EVIDÊNCIA: um AgentResult do agente "human" (status ok, texto e evidência = a
   resposta, fatos `operator_answer`), que abre a rota do Outcome e cujos fatos os agentes leem (a resposta entra
   também nas dicas de busca do RAG);
3. os passos do plano original que ficaram pendentes rodam AGORA pelo supervisor, depois do "human". Pendente =
   orçamento estourado; supervisor LLM que escalou antes de rodar o resto; e escalonamento simples por falha, em
   que os passos que DEPENDEM do que falhou esperam o humano (supervisor._defer_dependents). O texto deles entra na
   mesma mensagem. Retomada uma vez só (cases.take_pending) e sem novo escalonamento (supervisor.no_escalation):
   se um passo retomado ainda falhar, a resposta humana chega e nada reabre o caso.
A mensagem passa pela máscara de PII e pela checagem numérica (evidência = resposta humana + evidência dos passos
retomados + falas do cliente) e entra no histórico com intent "resumed". O cliente vê sem escrever de novo.
"""
from __future__ import annotations

from . import cases, domain
from .grounding import unsupported_numbers
from .guardrails import mask_output
from .llm import LLMError, get_llm
from .observability import METRICS, log, new_trace_id, span
from .router import detect_language
from .store import get_store

LABEL = {"pt": "Resposta do atendente", "en": "Agent's reply"}


def human_result(answer: str, operator: str):
    """A resposta do operador como resultado de agente: o supervisor e a checagem numérica a tratam como evidência."""
    from .agents import AgentResult

    return AgentResult("human", "ok", text=answer, evidence=[answer],
                       facts={"operator_answer": answer, "operator": operator, "query_hints": [answer[:300]]})


def _resume_plan(ticket: dict, plan: dict, answer: str, operator: str):
    """Executa os passos pendentes do plano original depois do "human". Devolve o Outcome do supervisor."""
    from . import supervisor
    from .agents import Context

    store = get_store()
    conv = ticket["conversation_id"]
    ctx = Context(text=plan["text"], language=plan.get("language", "pt"), user_id=ticket["user_id"],
                  conversation_id=conv, intent=plan.get("intent", "faq"), history=store.history(conv, limit=20),
                  facts={"ask": dict(plan.get("ask", {})), "query_hints": list(plan.get("query_hints", [])),
                         "resume_of": ticket["id"]})
    with span("resume_plan", ticket=ticket["id"], steps=",".join(plan["steps"])):
        out = supervisor.run(list(plan["steps"]), ctx, prior=[human_result(answer, operator)])
    METRICS.inc("plan_resumed_total", steps=str(len(plan["steps"])))
    return out


def resume_after_human(ticket: dict, operator: str) -> dict:
    from . import hitl_sync

    if hitl_sync.live_owns(ticket):
        # respondido durante a espera síncrona do turno (hitl_sync): o turno ao vivo já leva a resposta e roda os
        # passos pendentes; retomar aqui também mandaria a mesma resposta duas vezes
        METRICS.inc("handoff_resumed_total", engine="live_turn")
        return {"answer": None, "engine": "live_turn", "unsupported_numbers": [], "resumed_steps": [],
                "route": [], "pending_action": None}
    store = get_store()
    conv, user, answer = ticket["conversation_id"], ticket["user_id"], ticket["answer"] or ""
    history = store.history(conv, limit=12)
    said = [m["content"] for m in history if m["role"] == "user"]
    language = detect_language(said[-1] if said else answer)
    text, engine = f"{LABEL[language]}: {answer}", "template"
    llm = get_llm("agent")
    new_trace_id()  # a retomada é um request próprio: custo e orçamento do turno começam do zero
    if llm.enabled:
        msgs = [{"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]}
                for m in history if m["role"] in ("user", "assistant")][-6:]
        msgs.append({"role": "user", "content": f"<resposta_do_atendente operador=\"{operator}\">\n{answer}\n"
                                                "</resposta_do_atendente>\nRedija a próxima mensagem ao cliente."})
        if msgs[0]["role"] != "user":  # a API exige começar pelo usuário
            msgs = msgs[1:]
        try:
            with span("resume", ticket=ticket["id"]):
                reply = llm.complete(domain.prompt("resume.md").format(language=language), msgs, max_tokens=1024)
            if reply.text.strip():
                text, engine = reply.text.strip(), "llm"
        except LLMError as exc:  # a resposta humana chega mesmo se o modelo cair
            log.warning("resume_llm_failed", extra={"extra_fields": {"kind": exc.kind}})
    evidence, public, steps, route, pending_action = [answer], answer, [], ["human"], None
    plan = cases.take_pending(ticket["id"])
    if plan:
        try:
            out = _resume_plan(ticket, plan, answer, operator)
            # o texto do "human" já está na mensagem redigida acima; aqui só o que os passos retomados acrescentam
            parts = out.answer or "\n\n".join(r.text for r in out.results if r.text and r.agent != "human")
            if parts.strip():
                text = f"{text}\n\n{parts}"
            evidence += [e for r in out.results if r.agent != "human" for e in r.evidence]
            public = "\n".join(evidence)
            steps, route = list(plan["steps"]), out.route
            pending_action = next((r.pending_action for r in out.results if r.pending_action), None)
            cases.finish_pending(ticket["id"])
        except Exception as exc:  # noqa: BLE001 — a resposta humana chega mesmo se a retomada falhar
            cases.finish_pending(ticket["id"], "failed")
            log.warning("resume_plan_failed", extra={"extra_fields": {"error": type(exc).__name__}})
    text = mask_output(text, public=public)
    flagged = unsupported_numbers(text, evidence, question=" ".join(said))
    store.add_message(conv, user, "assistant", text, "resumed")
    METRICS.inc("handoff_resumed_total", engine=engine)
    return {"answer": text, "engine": engine, "unsupported_numbers": flagged, "resumed_steps": steps,
            "route": route, "pending_action": pending_action}
