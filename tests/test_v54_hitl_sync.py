"""Consulta síncrona ao operador: o turno espera a resposta humana e o plano continua.

Operador simulado numa thread, pelo mesmo endpoint do console (/handoffs/{id}/reply). Dentro do prazo: a resposta e o
passo pendente (faq) saem NO MESMO turno e a retomada assíncrona não manda a mensagem de novo. Fora do prazo: nada
muda, o caso segue assíncrono e a retomada de sempre leva a resposta.
"""
import threading
import time

from fastapi.testclient import TestClient

from app import cases, hitl_sync, supervisor
from app.agents import AgentResult, faq_agent
from app.api import app
from app.auth import issue_token
from app.store import get_store

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
