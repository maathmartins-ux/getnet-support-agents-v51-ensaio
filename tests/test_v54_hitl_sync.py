"""Consulta síncrona ao operador: o turno espera a resposta humana e o plano continua.

Operador simulado numa thread, pelo mesmo endpoint do console (/handoffs/{id}/reply). Dentro do prazo: a resposta e o
passo pendente (faq) saem NO MESMO turno e a retomada assíncrona não manda a mensagem de novo. Fora do prazo: nada
muda, o caso segue assíncrono e a retomada de sempre leva a resposta.
Com o supervisor LLM (cliente falso), a resposta do atendente volta ao laço como resultado do passo "human": o modelo
pode chamar um especialista com o que ele disse e redige a resposta final, que o código confere; sem LLM, template.
"""
import json
import re
import threading
import time
import uuid

from fakes import fake_llm, resp, text, tool_use
from fastapi.testclient import TestClient

from app import cases, hitl_sync, supervisor
from app.agents import AgentResult, Context, faq_agent
from app.api import app
from app.auth import issue_token
from app.domain import example
from app.llm import LLMError
from app.observability import new_trace_id
from app.store import get_store
from evals import operator_sim

client = TestClient(app)
OP = {"X-Operator-Token": "test-operator"}
ASK = "Qual o prazo de entrega? E onde está meu pedido 1002?"


def auth(user="u1"):
    return {"Authorization": f"Bearer {issue_token(user)}"}


def _slow_faq_once(monkeypatch):
    """1ª chamada do faq estoura o NODE_TIMEOUT_S (vai ao humano com o faq pendente); as seguintes respondem."""
    monkeypatch.setenv("NODE_TIMEOUT_S", "1")  # o 1º faq espera 5 s; 1 s deixa folga aos outros agentes
    release, calls = threading.Event(), []

    def faq(ctx):
        calls.append(1)
        if len(calls) == 1:
            release.wait(5)
            return AgentResult("faq", "ok", text="tarde demais")
        return faq_agent(ctx)

    monkeypatch.setitem(supervisor.AGENTS, "faq", faq)
    return release


def _operator(answer: str, after_s: float, seen: set, out: dict):
    """Responde o 1º caso de atendimento novo que aparecer na fila, `after_s` depois de vê-lo."""
    def run():
        deadline = time.time() + 10
        while time.time() < deadline:
            fresh = [t for t in get_store().list_tickets("open") if t["kind"] == "handoff" and t["id"] not in seen]
            if fresh:
                time.sleep(after_s)
                r = client.post(f"/handoffs/{fresh[0]['id']}/reply", json={"answer": answer}, headers=OP)
                out["reply"] = r.json()
                return
            time.sleep(0.02)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def test_answer_within_the_wait_continues_the_plan_in_the_same_turn(monkeypatch):
    monkeypatch.setenv("HITL_SYNC_WAIT_S", "3")
    monkeypatch.setenv("HITL_SYNC_POLL_S", "0.05")
    release = _slow_faq_once(monkeypatch)
    seen = {t["id"] for t in get_store().list_tickets("open")}
    got: dict = {}
    op = _operator("Verifiquei: seu pedido sai amanhã.", 0.1, seen, got)
    try:
        r = client.post("/chat", json={"message": ASK}, headers=auth()).json()
    finally:
        release.set()
    op.join(5)
    ticket = r["handoff"]["ticket_id"]
    assert "Consultei um atendente humano" in r["answer"] and ticket in r["answer"]
    assert "sai amanhã" in r["answer"] and "dias úteis" in r["answer"]  # resposta humana + faq retomado
    assert r["route"][-2:] == ["human", "faq"] and any("no mesmo turno" in p for p in r["replans"])
    assert cases.pending(ticket) is None
    # a retomada assíncrona viu que o turno ao vivo levou a resposta e não mandou nada
    assert got["reply"]["resumed"]["engine"] == "live_turn" and got["reply"]["resumed"]["answer"] is None
    msgs = client.get(f"/conversations/{r['conversation_id']}", headers=auth()).json()["messages"]
    assert [m["intent"] for m in msgs].count("resumed") == 0
    assert hitl_sync.live_owns(get_store().get_ticket(ticket))


def test_answer_after_the_wait_goes_the_async_way(monkeypatch):
    monkeypatch.setenv("HITL_SYNC_WAIT_S", "0.3")
    monkeypatch.setenv("HITL_SYNC_POLL_S", "0.05")
    release = _slow_faq_once(monkeypatch)
    try:
        r = client.post("/chat", json={"message": ASK}, headers=auth()).json()
    finally:
        release.set()
    ticket = r["handoff"]["ticket_id"]
    assert "A resposta aparece nesta conversa" in r["answer"] and cases.pending(ticket)["steps"] == ["faq"]
    out = client.post(f"/handoffs/{ticket}/reply", json={"answer": "Seu pedido sai amanhã."}, headers=OP).json()
    assert out["resumed"]["engine"] != "live_turn" and out["resumed"]["resumed_steps"] == ["faq"]
    assert not hitl_sync.live_owns(get_store().get_ticket(ticket))


def test_wait_is_off_by_default(monkeypatch):
    monkeypatch.delenv("HITL_SYNC_WAIT_S", raising=False)
    assert hitl_sync.wait_s() == 0 and hitl_sync.wait_answer("T-nada") is None


def test_approval_case_is_not_waited_on(monkeypatch):
    from app.agents import Context
    from app.schemas import Handoff

    monkeypatch.setenv("HITL_SYNC_WAIT_S", "5")
    monkeypatch.setattr(hitl_sync, "wait_answer", lambda *a, **k: (_ for _ in ()).throw(AssertionError("esperou")))
    t = get_store().open_ticket("c-appr", "u1", "approval", "aprovar", kind="approval", action_id="A-1")
    out = supervisor.Outcome()
    esc = AgentResult("escalation", "ok", text="x",
                      handoff=Handoff(required=True, reason="approval", ticket_id=t["id"]))
    ctx = Context(text="estorno", language="pt", user_id="u1", conversation_id="c-appr", intent="records")
    supervisor._record("escalation", esc, ctx, out)
    assert supervisor._continue_with_operator(["records"], ctx, out) is out and out.route == ["escalation"]


def test_wait_answer_with_fake_clock_times_out_and_audits_the_deadline():
    store = get_store()
    t = store.open_ticket("c-sync", "u1", "faq_not_in_sources", "teste")
    now = [1000.0]

    def sleep(s):
        now[0] += s

    assert hitl_sync.wait_answer(t["id"], seconds=1.0, sleep=sleep, clock=lambda: now[0]) is None
    assert hitl_sync.deadline_of(t["id"]) == 1001.0


def test_final_answer_after_the_operator_drops_the_offer_and_the_repeated_step():
    """Depois da resposta do atendente: sem "posso encaminhar ao atendente" e sem o texto do passo que rodou de novo."""
    assert supervisor.without_handoff_talk(
        "A T1988A está online. Posso encaminhar o seu caso a um atendente humano, se quiser. Mais algo?"
    ) == "A T1988A está online. Mais algo?"
    offer = "Status ok.\n\nI can hand this to a human agent if you'd like."
    assert supervisor.without_handoff_talk(offer) == "Status ok."
    assert supervisor.without_handoff_talk("Sem oferta aqui.") == "Sem oferta aqui."


def test_operator_answer_turn_keeps_each_step_once(monkeypatch):
    """Plano com um passo que roda antes e depois do atendente: o texto de antes sai (o de depois o substitui)."""
    monkeypatch.setenv("HITL_SYNC_WAIT_S", "3")
    monkeypatch.setenv("HITL_SYNC_POLL_S", "0.05")
    release = _slow_faq_once(monkeypatch)
    seen = {t["id"] for t in get_store().list_tickets("open")}
    got: dict = {}
    op = _operator("Verifiquei: seu pedido sai amanhã.", 0.1, seen, got)
    try:
        r = client.post("/chat", json={"message": ASK}, headers=auth()).json()
    finally:
        release.set()
    op.join(5)
    answer = r["answer"]
    assert answer.count("Consultei um atendente humano") == 1 and "tarde demais" not in answer
    assert not supervisor._OFFERS_HUMAN.search(answer.split("Consultei um atendente humano", 1)[1])


# --- com o supervisor LLM: a resposta do atendente volta ao laço ------------------------------------------------
FACT = "Verifiquei: o pedido atrasado é o 1002, que ainda está em separação."
TICKET = re.compile(r"T-[0-9a-f]{8}")
ESCALATE = resp("tool_use", tool_use("escalation_agent", {"reason": "o cliente pediu um atendente"}))
HANDED = resp("end_turn", text("Encaminhei seu caso a um atendente humano."))  # a redação de antes da resposta dele


def _ticket(kwargs: dict) -> str:
    return TICKET.search(json.dumps(kwargs["messages"], ensure_ascii=False, default=str)).group()


def _writes(final: str):
    """Volta do modelo que redige a resposta final com o protocolo que leu na réplica do laço."""
    return lambda kwargs: resp("end_turn", text(final.format(ticket=_ticket(kwargs))))


def _with_operator(monkeypatch, script: list, plan: tuple = ("escalation",), intent: str = "human_request",
                   message: str = "Quero falar com um atendente: um pedido meu atrasou"):
    """Turno com o supervisor LLM falso (os especialistas seguem offline) e a operadora simulada no prazo."""
    new_trace_id()
    llm, msgs = fake_llm(script)
    monkeypatch.setattr(supervisor, "get_llm", lambda role="agent": llm)
    monkeypatch.setenv("SUPERVISOR_FAST", "off")
    ctx = Context(text=message, language="pt", user_id="u1", conversation_id=f"c-{uuid.uuid4().hex[:8]}",
                  intent=intent)
    sim = operator_sim.Operator(FACT, 0.1, operator_sim.reply_direct(), seen=operator_sim.open_handoffs()).start()
    with hitl_sync.override(5, 0.05):
        out = supervisor.run(list(plan), ctx)
    ticket = next(r.handoff.ticket_id for r in out.results if r.handoff and r.handoff.ticket_id)
    state = sim.finish(ticket)
    assert state["status"] == 200 and state["clock"] == "wait"  # respondeu durante a espera do turno
    return out, msgs, ticket


def test_with_the_llm_the_operator_answer_returns_to_the_loop_and_feeds_a_step(monkeypatch):
    """O cliente não diz qual pedido; o atendente diz. O modelo lê a resposta dele como resultado do passo human,
    chama o records com esse id (passo do modelo, desvio "human->records") e redige a resposta final, com o dado do
    records e o protocolo. Antes: a resposta ia colada no template e o modelo nunca a lia."""
    asked = {}

    def records(c):
        asked["request"] = c.facts["ask"]["records"]
        rid = re.search(r"\d{4}", asked["request"]).group()
        found = example._lookup(rid, c.user_id)
        return AgentResult("records", "ok", text=f"Pedido {rid}: {found['data']['status']}.",
                           evidence=[json.dumps(found, ensure_ascii=False)], facts={"record_id": rid})

    monkeypatch.setitem(supervisor.AGENTS, "records", records)
    lookup = resp("tool_use", tool_use("records_agent", {"request": "status do pedido 1002"}, "tu2"))
    final = "Consultei um atendente humano (protocolo {ticket}): o pedido atrasado é o 1002, que segue em separação."
    out, msgs, ticket = _with_operator(monkeypatch, [ESCALATE, HANDED, lookup, _writes(final)])
    assert len(msgs.sent) == 4 and asked == {"request": "status do pedido 1002"}
    note = msgs.sent[2]["messages"][0]["content"]  # 1ª mensagem da réplica do laço
    assert "- escalation_agent → " in note and "- human → " in note and FACT in note and ticket in note
    assert "Rode só os passos que faltam" not in note  # o bloco da retomada assíncrona fica para a retomada
    assert operator_sim.EVAL_OPERATOR not in note  # a identidade do operador é da auditoria, não do texto ao cliente
    assert [t["name"] for t in msgs.sent[2]["tools"]] == [t["name"] for t in supervisor.TOOLS]
    assert out.route == ["escalation", "human", "records"]
    assert [(v["agent"], v.get("decided_by")) for v in map(supervisor.step_view, out.results)] == [
        ("escalation", "llm"), ("human", "operator"), ("records", "llm")]
    assert out.replans == ["escalation->human (resposta em 5s de espera)", "human->records (plano: [])"]
    assert out.answer == final.format(ticket=ticket) and "Resposta do atendente:" not in out.answer
    assert supervisor.step_view(out.results[0])["answered_live"] is True


def test_with_the_llm_the_step_left_for_after_the_human_runs_in_the_loop(monkeypatch):
    """Plano de 2 passos em que o modelo escalou depois do records: o faq que ficou para depois do atendente roda na
    réplica do laço, pedido pelo modelo (o plano continuou: "human->faq (no mesmo turno)")."""
    script = [resp("tool_use", tool_use("records_agent", {"request": "pedido atrasado"})),
              resp("tool_use", tool_use("escalation_agent", {"reason": "atraso sem prazo"}, "tu2")), HANDED,
              resp("tool_use", tool_use("faq_agent", {"query": "prazo de entrega"}, "tu3")),
              _writes("Consultei um atendente humano (protocolo {ticket}). " + FACT)]
    out, msgs, ticket = _with_operator(monkeypatch, script, plan=("records", "faq"), intent="multi")
    note = msgs.sent[3]["messages"][0]["content"]
    assert "Plano sugerido pelo router: ['faq']" in note and "(faq_agent)" in note and "- records_agent → " in note
    assert out.route == ["records", "escalation", "human", "faq"]
    assert out.replans == ["records->escalation (plano: ['faq'])", "escalation->human (resposta em 5s de espera)",
                           "human->faq (no mesmo turno)"]
    assert [supervisor.step_view(r).get("decided_by") for r in out.results] == ["llm", "llm", "operator", "llm"]
    assert ticket in out.answer and FACT in out.answer


def test_with_the_llm_the_model_may_only_write_and_cannot_call_the_human_again(monkeypatch):
    final = "Consultei um atendente humano (protocolo {ticket}). " + FACT
    out, msgs, ticket = _with_operator(monkeypatch, [ESCALATE, HANDED, _writes(final)])
    assert len(msgs.sent) == 3 and out.route == ["escalation", "human"]
    assert out.replans == ["escalation->human (resposta em 5s de espera)"] and out.answer == final.format(ticket=ticket)
    again = resp("tool_use", tool_use("escalation_agent", {"reason": "de novo"}, "tu2"))
    out, msgs, ticket = _with_operator(monkeypatch, [ESCALATE, HANDED, again, _writes(final)])
    refused = msgs.sent[3]["messages"][-1]["content"][0]
    assert refused["is_error"] and "human->escalation_agent" in refused["content"]  # uma réplica, sem novo humano
    assert out.route == ["escalation", "human"] and out.answer == final.format(ticket=ticket)


def test_the_code_checks_the_written_answer_and_the_template_is_the_fallback(monkeypatch):
    """Sem o protocolo, a frase CONSULTED vem antes da redação; redação que oferece o atendente de novo, LLM caído na
    réplica ou orçamento do turno esgotado dão a composição por template, a mesma de sem LLM."""
    out, _, ticket = _with_operator(monkeypatch, [ESCALATE, HANDED, resp("end_turn", text(f"Segundo ele: {FACT}"))])
    assert out.answer == f"{supervisor.CONSULTED['pt'].format(ticket=ticket)}\n\nSegundo ele: {FACT}"
    offer = resp("end_turn", text(f"{FACT} Se quiser, posso encaminhar você a outro atendente."))
    for last in (offer, LLMError("api_status_529", "api_status")):
        out, msgs, ticket = _with_operator(monkeypatch, [ESCALATE, HANDED, last])
        assert out.answer == f"{supervisor.CONSULTED['pt'].format(ticket=ticket)}\n\nResposta do atendente: {FACT}"
        assert out.route == ["escalation", "human"] and len(msgs.sent) == 3
    monkeypatch.setenv("MAX_MODEL_CALLS", "2")  # o turno gastou as 2 chamadas antes do atendente
    out, msgs, ticket = _with_operator(monkeypatch, [ESCALATE, HANDED])
    assert len(msgs.sent) == 2 and out.answer.endswith(f"Resposta do atendente: {FACT}")
