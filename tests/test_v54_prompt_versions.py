"""Kit v5.4: versão das instruções (hash por arquivo de prompt) na resposta, no log e na linha do eval."""
import logging

from fastapi.testclient import TestClient

from app import domain, observability
from app.api import app
from app.auth import issue_token

client = TestClient(app)


def test_prompt_hash_is_recorded_per_request():
    observability.new_trace_id()
    text = domain.prompt("faq.md")
    versions = observability.prompt_versions()
    assert set(versions) == {"faq.md"} and len(versions["faq.md"]) == 10
    assert versions["faq.md"] == observability.record_prompt("x", text)  # mesmo texto, mesmo hash
    observability.new_trace_id()
    assert observability.prompt_versions() == {}  # zera a cada request


def test_response_and_log_carry_the_versions_used(caplog):
    from app import pipeline

    observability.new_trace_id()
    domain.prompt("router.md")
    domain.prompt("faq.md")
    with caplog.at_level(logging.INFO, logger="app"):
        versions = pipeline._log_prompts("t-1")
    assert set(versions) == {"router.md", "faq.md"}
    logged = [rec for rec in caplog.records if rec.getMessage() == "prompt_versions"]
    assert logged and logged[-1].extra_fields == {"trace_id": "t-1", "prompts": versions}


def test_chat_response_has_the_field():
    r = client.post("/chat", json={"message": "Qual o prazo de entrega?"},
                    headers={"Authorization": f"Bearer {issue_token('u1')}"})
    assert r.status_code == 200 and isinstance(r.json()["prompt_versions"], dict)


def test_eval_row_keeps_prompt_versions():
    from evals import run_evals

    class Fake:
        def send(self, message, user_id, conversation_id):
            return {"conversation_id": "c", "answer": "ok", "intent": "faq", "route": ["router", "faq"],
                    "prompt_versions": {"faq.md": "abc1234567"}, "usage": {"cost_usd": 0}}

    case = {"id": "x", "split": "official", "message": "oi", "expect": {}}
    row = run_evals.run_case(Fake(), case)
    assert row["prompt_versions"] == {"faq.md": "abc1234567"}
