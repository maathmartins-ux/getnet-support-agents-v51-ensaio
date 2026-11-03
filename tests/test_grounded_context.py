"""Cartão `policy:capabilities` e `context` da linha do eval: o juiz vê o texto que quem redigiu viu.

Getnet v4 (judge.json, official): 6 das 12 reprovações eram "as fontes só têm título e URL" (clima e câmbio pela
web) e outras 2 eram regra verdadeira do sistema ("a antecipação precisa da sua confirmação e da aprovação de um
atendente") que não estava em fonte nenhuma. Aqui: o cartão sai do registro de ferramentas, entra no prompt de
quem redige e na evidência; a linha do eval leva a evidência como texto, com teto.
"""
import json

from fakes import fake_llm, resp, text

from app import capabilities, grounding, live_data, pipeline, supervisor
from app.agents import Context, faq_agent
from app.schemas import RouterDecision
from evals import context as eval_context
from evals import judge, run_evals

GEO = {"results": [{"name": "Porto Alegre", "admin1": "Rio Grande do Sul", "country": "Brasil", "latitude": -30.03,
                    "longitude": -51.23, "timezone": "America/Sao_Paulo"}]}
FORECAST = {"daily": {"time": ["2026-11-02"], "temperature_2m_max": [31.4], "temperature_2m_min": [19.6],
                      "precipitation_probability_max": [60], "weather_code": [95]}}


# --- cartão --------------------------------------------------------------------------------------------------------
def test_card_is_generated_from_the_registry_and_action_policy(monkeypatch):
    monkeypatch.setenv("ACTION_TTL_MIN", "15")
    card = capabilities.card("pt")
    assert card.startswith(f"[{capabilities.CARD_ID}]")
    assert "lookup_record (Consulta um registro" in card  # leitura
    assert "PROPOR" in card and "cancel_record" in card  # escrita normal: só propõe
    risky = next(line for line in card.splitlines() if "risco alto" in line)
    assert "refund_record" in risky and "aprovação de um atendente" in risky  # quatro olhos
    assert "15 minutos" in card and "atendente humano" in card
    assert capabilities.card("en").count("operator") >= 1


def test_domain_policy_lines_and_card_numbers_count_as_evidence(monkeypatch):
    from app import domain

    monkeypatch.setattr(domain.active(), "POLICY_LINES", {"pt": ["Pix cai no mesmo dia; débito em 1 dia útil."]},
                        raising=False)
    card = capabilities.card("pt")
    assert card.endswith("- Pix cai no mesmo dia; débito em 1 dia útil.")
    assert grounding.unsupported_numbers("A proposta expira em 15 minutos; o débito cai em 1 dia útil.",
                                         [card]) == []


def test_writer_and_supervisor_prompts_carry_the_card(monkeypatch):
    llm, msgs = fake_llm([resp("end_turn", text("Troca em até 7 dias [1]."))])
    monkeypatch.setattr("app.agents.get_llm", lambda role="agent": llm)
    faq_agent(Context(text="Posso trocar um livro?", language="pt", user_id="u1", conversation_id="c1"))
    assert f"[{capabilities.CARD_ID}]" in msgs.sent[0]["messages"][-1]["content"]

    sup, smsgs = fake_llm([resp("end_turn", text("ok"))])
    supervisor.run_llm(["faq"], Context(text="oi", language="pt", user_id="u1", conversation_id="c1"), sup)
    assert f"[{capabilities.CARD_ID}]" in smsgs.sent[0]["messages"][0]["content"]


# --- context da linha do eval ----------------------------------------------------------------------------------------
def test_context_is_bounded_and_keeps_the_card():
    card = capabilities.card("pt")
    ctx = eval_context.build(["x" * 9000, "y" * 9000, "z" * 9000, card], limit=6000)
    assert len(ctx) <= 6000 + 200 and card in ctx and "fora do teto" in ctx


def test_live_data_row_gives_the_judge_the_numbers(monkeypatch, tmp_path):
    """Turno de clima pelo Open-Meteo (HTTP trocado): a linha carrega o texto da API e o juiz recebe os números."""
    monkeypatch.setenv("LIVE_DATA", "on")
    monkeypatch.setattr(live_data, "_get_json",
                        lambda url, params: GEO if url == live_data.GEOCODING else FORECAST)
    monkeypatch.setattr(pipeline, "route", lambda text, history: RouterDecision(
        intent="general", plan=["faq"], language="en", confidence=0.9))
    case = {"id": "official-02", "split": "official", "user_id": "u1",
            "message": "What's the weather forecast in Porto Alegre tomorrow?", "expect": {"intent": "general"}}
    row = run_evals.run_case(run_evals.Client(None), case)
    assert "31.4" in row["answer"]
    assert "31.4" in row["context"] and "19.6" in row["context"] and "Open-Meteo" in row["context"]
    assert f"[{capabilities.CARD_ID}]" in row["context"] and row["checks"]["claims"] is True

    live = tmp_path / "live_official.json"
    live.write_text(json.dumps({"rows": [row]}, ensure_ascii=False), encoding="utf-8")
    cal = tmp_path / "cal.jsonl"
    cal.write_text("", encoding="utf-8")
    seen: list[str] = []

    class Capture:
        model = "capture"

        def complete(self, system, messages, max_tokens=1024, schema=None):
            from app.llm import LLMReply

            seen.append(messages[0]["content"])
            return LLMReply(json.dumps({"grounded": True, "helpful": True, "score": 5, "failure_type": "none",
                                        "reason": "ok"}), "capture")

    judge.run(Capture(), [live], calibration=cal)
    fontes = seen[-1].split("Fontes:\n", 1)[1].split("\n\nDados de ferramenta:", 1)[0]
    assert "31.4" in fontes and "19.6" in fontes  # o número está no que o juiz lê como fonte


def test_old_rows_get_web_snippets_from_evidence():
    sources = [{"id": "https://tempo.example/poa", "title": "Previsão POA", "url": "https://tempo.example/poa"},
               {"id": "https://x.example", "title": "Sem trecho", "url": "https://x.example"}]
    out = judge._sources_text([], sources, ["Previsão POA: máxima de 31 °C amanhã", "Sem trecho (3 days ago)"])
    assert "Previsão POA (https://tempo.example/poa): máxima de 31 °C amanhã" in out
    assert "Sem trecho (https://x.example) (3 days ago) [fonte externa: título e endereço]" in out
