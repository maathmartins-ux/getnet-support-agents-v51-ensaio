"""Humano no laço medido no eval (split `hitl`) e resposta sem contradição depois do atendente (rodada 11, frente B).

- composição: com o atendente já respondido no turno, só o template CONSULTED diz se houve encaminhamento; a negação
  de um especialista que não sabia do escalation ("ele não foi encaminhado por mim", frase literal da vitrine) sai;
- operadora simulada (evals/operator_sim.py) num caso do eval: no prazo → a resposta dela sai no turno
  (`human_in_turn`) e chega uma vez só; atrasada → a retomada assíncrona entrega uma vez só e o eval lê a mensagem;
- a espera síncrona de um caso (hitl_sync.override) não vaza para o caso que roda ao lado;
- resposta do operador ANTES de o turno começar a esperar: sai uma vez só (pela retomada), nunca duas.
"""
import contextvars
import json
import os
import threading

from fastapi.testclient import TestClient

from app import hitl_sync, supervisor
from app.agents import AgentResult, Context
from app.api import app
from app.auth import issue_token
from app.store import get_store
from evals import operator_sim, run_evals
from scripts import scorecard

client = TestClient(app)
OP = {"X-Operator-Token": "test-operator"}
FACT = "Verifiquei: o prazo do seu pedido é de 3 a 5 dias úteis."
# texto do especialista records no turno 3 da vitrine (docs/DEMO_TRANSCRIPT.md do ensaio, rodada 10), literal
VITRINE = ("A T1988A está funcionando. Ela está online, conectada por Wi-Fi, com sinal bom. O último contato foi em "
           "2026-11-03 às 23:25.\n\nSobre a contestação do aluguel da T1988B, a decisão é de um atendente humano. Não "
           "tenho ferramenta para abrir esse caso nesta resposta, então ele não foi encaminhado por mim.")


def auth(user="u1"):
    return {"Authorization": f"Bearer {issue_token(user)}"}


# --- composição -----------------------------------------------------------------------------------------------
def test_denial_of_the_handoff_leaves_the_answer_and_the_rest_stays():
    out = supervisor.without_handoff_talk(VITRINE)
    assert "não foi encaminhado" not in out and "Não tenho ferramenta para abrir" not in out
    assert out.endswith("Sobre a contestação do aluguel da T1988B, a decisão é de um atendente humano.")
    assert out.startswith("A T1988A está funcionando.")
    for denial in ("I can't escalate this.", "I can’t escalate this.", "This hasn't been forwarded to a human agent.",
                   "I'm unable to open a case for you.", "O caso não foi aberto.", "Não consigo encaminhar você.",
                   "Quer que eu encaminhe?", "Se precisar de um atendente humano, posso encaminhar o seu caso."):
        assert supervisor.without_handoff_talk(f"A T1988A está online. {denial}") == "A T1988A está online.", denial
    for kept in ("Proposta o chamado técnico da T1988B (ação A-692b532b), mas **ele ainda não foi aberto**.",
                 "**It hasn't been opened yet.", "Encaminhei para um atendente humano (protocolo T-1).",
                 "Se não resolver, encaminhe o terminal para a assistência técnica.",
                 "Não houve atraso, o pedido foi encaminhado à transportadora ontem.",
                 "Não tenho ferramenta para cancelar o contrato nem para tratar cobranças.",
                 "Caso o chamado não seja aberto até amanhã, a proposta expira."):
        assert supervisor.without_handoff_talk(kept) == kept, kept


def test_operator_turn_answer_says_once_that_the_case_went_to_the_human(monkeypatch):
    """Ponta a ponta no supervisor: records (com a negação literal) → escalation → operadora no prazo."""
    monkeypatch.setitem(supervisor.AGENTS, "records", lambda ctx: AgentResult("records", "ok", text=VITRINE))
    ctx = Context(text="Contestar o aluguel da T1988B; a T1988A funciona?", language="pt", user_id="u1",
                  conversation_id="c-vitrine", intent="human_request")
    sim = operator_sim.Operator(FACT, 0.2, operator_sim.reply_direct(), seen=operator_sim.open_handoffs()).start()
    with hitl_sync.override(5, 0.05):
        out = supervisor.run(["records", "escalation"], ctx)
    state = sim.finish(out.results[-1].handoff.ticket_id if out.results[-1].handoff else None)
    assert state["status"] == 200 and state["clock"] == "wait"
    answer = out.answer
    assert answer.count("Consultei um atendente humano") == 1 and "Resposta do atendente: " + FACT in answer
    assert "a decisão é de um atendente humano" in answer and "A T1988A está funcionando." in answer
    assert "não foi encaminhado" not in answer and "Não tenho ferramenta para abrir" not in answer


# --- espera de um caso só ---------------------------------------------------------------------------------------
def test_wait_override_holds_only_in_its_context(monkeypatch):
    monkeypatch.delenv("HITL_SYNC_WAIT_S", raising=False)
    monkeypatch.setenv("HITL_SYNC_POLL_S", "2")
    seen: dict = {}

    def other_case():  # outro caso, outra thread, contexto próprio: segue o env
        seen["other"] = (hitl_sync.wait_s(), hitl_sync.poll_s())

    with hitl_sync.override(7, 0.1):
        assert (hitl_sync.wait_s(), hitl_sync.poll_s()) == (7.0, 0.1)
        inherit = threading.Thread(target=contextvars.copy_context().run, args=(
            lambda: seen.setdefault("copied", hitl_sync.wait_s()),))
        alone = threading.Thread(target=other_case)
        inherit.start(), alone.start(), inherit.join(), alone.join()
        with hitl_sync.override(None):
            assert hitl_sync.wait_s() == 0  # None = vale o env
        assert hitl_sync.wait_s() == 7.0
        with hitl_sync.override(99):
            assert hitl_sync.wait_s() == hitl_sync.MAX_WAIT_S  # o teto vale também para o override
    assert seen == {"copied": 7.0, "other": (0.0, 2.0)}  # o turno do caso herda; o vizinho, não
    assert (hitl_sync.wait_s(), hitl_sync.poll_s()) == (0.0, 2.0)


# --- resposta antes da espera -----------------------------------------------------------------------------------
def test_answer_before_the_wait_starts_reaches_the_customer_once(monkeypatch):
    """O operador responde entre abrir o caso e o turno começar a esperar (ao vivo: durante a redação final do
    supervisor LLM). Antes: a resposta saía no turno E numa mensagem retomada. Agora: só a retomada a leva."""
    monkeypatch.setenv("HITL_SYNC_WAIT_S", "3")
    monkeypatch.setenv("HITL_SYNC_POLL_S", "0.05")
    real, replies = supervisor.AGENTS["escalation"], []

    def escalation_then_fast_operator(ctx):
        result = real(ctx)
        if result.handoff and result.handoff.ticket_id:
            replies.append(client.post(f"/handoffs/{result.handoff.ticket_id}/reply", json={"answer": FACT},
                                       headers=OP).json())
        return result

    monkeypatch.setitem(supervisor.AGENTS, "escalation", escalation_then_fast_operator)
    r = client.post("/chat", json={"message": "Quero falar com um atendente humano"}, headers=auth()).json()
    msgs = client.get(f"/conversations/{r['conversation_id']}", headers=auth()).json()["messages"]
    assert replies[0]["resumed"]["engine"] != "live_turn"  # sem prazo gravado: a retomada assíncrona levou
    assert [m["intent"] for m in msgs].count("resumed") == 1
    assert not any(st.get("answered_live") for st in r["steps"]) and "Consultei um atendente" not in r["answer"]
    assert not hitl_sync.live_owns(get_store().get_ticket(r["handoff"]["ticket_id"]))


# --- split hitl no eval -----------------------------------------------------------------------------------------
def _cases(tmp_path, monkeypatch, *cases):
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases), encoding="utf-8")
    monkeypatch.setattr(run_evals, "CASES", path)


def _hitl(cid, after_s, wait_s=None, in_turn=True):
    case = {"id": cid, "split": "hitl", "user_id": "u1", "message": "Quero falar com um atendente sobre o prazo",
            "operator": {"answer": FACT, "after_s": after_s},
            "expect": {"intent": "human_request", "handoff": True, "human_in_turn": in_turn,
                       "facts": ["3 a 5 dias úteis"], "not_contains": ["não foi encaminhad"]}}
    return {**case, "wait_s": wait_s} if wait_s is not None else case


def test_kit_case_in_time_puts_the_operator_in_the_turn(tmp_path):
    report = run_evals.run(out=tmp_path / "r.json", split="hitl")
    row = report["rows"][0]
    assert row["id"] == "hitl-01" and all(row["checks"].values()), row["checks"]
    assert row["checks"]["human_in_turn"] and row["checks"]["human_once"] and "resolved" not in row["checks"]
    assert "3 a 5 dias úteis" in row["answer"] and "Consultei um atendente humano" in row["answer"]
    assert row["operator"]["posted"] and row["operator"]["clock"] == "wait"
    assert row["operator"]["resume_engine"] == "live_turn" and row["resumed"] == []  # a retomada não repetiu
    hitl = report["metrics"]["hitl"]
    assert hitl["human_in_turn_acc"] == 100.0 and hitl["human_once_acc"] == 100.0 and hitl["facts_acc"] == 100.0
    assert "hitl" not in report["resolved"]["by_split"]  # "resolvido sem humano" não mede o caso do humano
    assert "humano no turno certo **100%**" in run_evals.to_markdown(report, split_view=True)


def test_late_operator_goes_through_the_resume_once_and_the_eval_reads_it(tmp_path, monkeypatch):
    _cases(tmp_path, monkeypatch, _hitl("hitl-late", after_s=0.8, wait_s=0.3, in_turn=False))
    row = run_evals.run(out=tmp_path / "r.json", split="hitl")["rows"][0]
    assert all(row["checks"].values()), row["checks"]
    assert row["checks"]["human_in_turn"] and row["checks"]["human_once"]  # fora do turno, como o caso pede
    assert "A resposta aparece nesta conversa" in row["answer"] and FACT not in row["answer"]
    assert len(row["resumed"]) == 1 and FACT in row["resumed"][0]  # o fato chegou pela retomada, uma vez
    assert row["operator"]["resume_engine"] == "template" and row["turn_ms"] < 0.8 * 1000


def test_one_case_wait_does_not_leak_to_the_case_beside_it(tmp_path, monkeypatch):
    """Dois casos ao mesmo tempo (workers=2): só o que tem `wait_s` espera; o vizinho, sem espera, vai pela retomada.
    Com a espera no env do processo, o vizinho também esperaria e a resposta dele sairia no turno."""
    _cases(tmp_path, monkeypatch, _hitl("hitl-wait", after_s=0.5, wait_s=4),
           _hitl("hitl-nowait", after_s=0.5, in_turn=False))
    rows = {r["id"]: r for r in run_evals.run(out=tmp_path / "r.json", split="hitl", workers=2)["rows"]}
    assert all(rows["hitl-wait"]["checks"].values()) and all(rows["hitl-nowait"]["checks"].values())
    assert rows["hitl-wait"]["operator"]["clock"] == "wait" and rows["hitl-nowait"]["operator"]["clock"] == "seen"
    assert len(rows["hitl-nowait"]["resumed"]) == 1 and rows["hitl-wait"]["resumed"] == []


def test_case_without_a_case_opened_has_no_operator_answer(tmp_path, monkeypatch):
    case = {"id": "hitl-none", "split": "hitl", "user_id": "u1", "message": "Onde está meu pedido 1002?",
            "operator": {"answer": FACT, "after_s": 0.1}, "wait_s": 2,
            "expect": {"intent": "records", "handoff": False, "human_in_turn": False}}
    _cases(tmp_path, monkeypatch, case)
    row = run_evals.run(out=tmp_path / "r.json", split="hitl")["rows"][0]
    assert row["operator"]["ticket"] is None and row["operator"]["status"] is None and "human_once" not in row["checks"]
    assert all(row["checks"].values()) and row["resumed"] == []


def test_badly_written_hitl_case_breaks_at_load(tmp_path, monkeypatch):
    import pytest

    for bad in ({"operator": {"after_s": 1}}, {"operator": "resposta"}, {"operator": {"answer": "x", "after_s": "2"}},
                {"operator": {"answer": "x"}, "wait_s": -1}):
        _cases(tmp_path, monkeypatch, {**_hitl("hitl-bad", after_s=1, wait_s=3), **bad})
        with pytest.raises(ValueError, match="hitl-bad"):
            run_evals.load_cases((run_evals.CASES,))


def test_vitrine_transcript_uses_the_same_operator_and_says_when_she_was_late(tmp_path):
    """scripts/demo_md.py usa a operadora do eval: atrasada (depois da espera), a resposta segue pela retomada."""
    from scripts import demo_md

    path = tmp_path / "t.jsonl"
    path.write_text('{"user": "u1"}\n{"say": "Quero falar com um atendente", "operator": "O prazo é de 3 a 5 dias '
                    'úteis.", "wait_s": 0.3, "operator_after_s": 0.8}\n', encoding="utf-8")
    md = demo_md.transcript(path, "abc1234", "hoje")
    assert "depois da espera do turno (a resposta segue pela retomada do caso)" in md
    assert "operador respondeu durante a espera" not in md
    assert "registrado por `operator:operadora_demo` (canal console)" in md
    assert "HITL_SYNC_WAIT_S" not in os.environ  # a espera foi do turno, não do processo


# --- placar ----------------------------------------------------------------------------------------------------
def test_scorecard_headline_counts_in_turn_only_among_cases_that_expect_it(tmp_path):
    rows = [{"split": "hitl", "id": "a", "expected_human_in_turn": True, "checks": {"human_in_turn": True}},
            {"split": "hitl", "id": "b", "expected_human_in_turn": True, "checks": {"human_in_turn": False}},
            {"split": "hitl", "id": "c", "expected_human_in_turn": False, "checks": {"human_in_turn": True}},
            {"split": "hitl", "id": "d", "expected_human_in_turn": True, "checks": {"human_in_turn": True},
             "crash": "Boom"}]
    (tmp_path / "live_hitl.json").write_text(json.dumps({"status": "complete", "rows": rows}), encoding="utf-8")
    assert scorecard.measure(tmp_path)["hitl_in_turn"] == round(1 / 3, 4)
    head = scorecard.headline_markdown(tmp_path)
    assert "| Humano no laço: resposta do operador no mesmo turno (split hitl) | 0.33 |" in head
    assert "hitl_in_turn" in scorecard.HEADLINE and "hitl_in_turn" in scorecard.HOW
    assert scorecard.measure(tmp_path / "vazio")["hitl_in_turn"] is None  # sem split: "não medido", nunca some
