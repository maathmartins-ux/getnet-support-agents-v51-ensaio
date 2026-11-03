"""👎 vira candidato a caso com evidência e versão das instruções; só entra num split após revisão."""
import json

import pytest
from fastapi.testclient import TestClient

from app import candidates
from app.api import app
from app.auth import issue_token
from evals import candidates as review_cli

client = TestClient(app)


def auth(user="u1"):
    return {"Authorization": f"Bearer {issue_token(user)}"}


@pytest.fixture
def cand_file(tmp_path, monkeypatch):
    path = tmp_path / "candidates.jsonl"
    monkeypatch.setenv("CANDIDATES_FILE", str(path))
    return path


def _ask(message="Qual o prazo de entrega?", user="u1"):
    return client.post("/chat", json={"message": message}, headers=auth(user)).json()


def test_thumbs_down_becomes_a_pending_candidate_with_evidence_and_versions(cand_file):
    r = _ask()
    out = client.post("/feedback", json={"trace_id": r["trace_id"], "rating": -1, "comment": "prazo errado"},
                      headers=auth()).json()
    assert out == {"ok": True, "candidate": f"cand-{r['trace_id']}"}
    row = candidates.read_all()[0]
    assert row["status"] == "pending" and row["trace_id"] == r["trace_id"] and row["comment"] == "prazo errado"
    assert row["question"] == "Qual o prazo de entrega?" and row["answer"] == r["answer"]
    assert row["evidence"] == r["evidence"] and row["prompt_versions"] == r["prompt_versions"]


def test_thumbs_up_does_not_create_a_candidate_and_only_the_owner_votes(cand_file):
    r = _ask()
    assert client.post("/feedback", json={"trace_id": r["trace_id"], "rating": -1}, headers=auth("u2")).status_code \
        == 404
    up = client.post("/feedback", json={"trace_id": r["trace_id"], "rating": 1}, headers=auth())
    assert up.json() == {"ok": True}
    assert candidates.read_all() == []


def test_review_lists_and_accept_moves_to_a_split_only_with_a_split(cand_file, tmp_path, capsys):
    r = _ask()
    client.post("/feedback", json={"trace_id": r["trace_id"], "rating": -1}, headers=auth())
    cid = f"cand-{r['trace_id']}"
    assert review_cli.main(["--review"]) == 0 and cid in capsys.readouterr().out
    rows = candidates.read_all()
    case = review_cli.accept(rows, cid, "real", intent="faq", handoff="no", cases_dir=tmp_path / "cases.d")
    assert case["expect"] == {"intent": "faq", "handoff": False} and case["origin"] == "feedback"
    written = json.loads((tmp_path / "cases.d" / "real.jsonl").read_text(encoding="utf-8"))
    assert written["message"] == "Qual o prazo de entrega?" and rows[0]["status"] == "accepted"
    with pytest.raises(KeyError):  # já aceito: não entra duas vezes
        review_cli.accept(rows, cid, "real", cases_dir=tmp_path / "cases.d")


def test_reject_marks_the_candidate(cand_file):
    r = _ask()
    client.post("/feedback", json={"trace_id": r["trace_id"], "rating": -1}, headers=auth())
    assert review_cli.main(["--reject", f"cand-{r['trace_id']}"]) == 0
    assert candidates.read_all()[0]["status"] == "rejected"
    assert review_cli.main(["--review"]) == 0


def test_deleting_the_conversation_drops_its_snapshot():
    from app.store import get_store

    r = _ask()
    store = get_store()
    assert store.snapshot(r["trace_id"])["question"] == "Qual o prazo de entrega?"
    client.delete(f"/me/conversations/{r['conversation_id']}", headers=auth())
    assert store.snapshot(r["trace_id"]) is None


def test_merchant_ui_has_login_and_feedback_buttons():
    html = client.get("/ui").text
    assert 'id="login"' in html and "/auth/login" in html and "/auth/logout" in html
    assert "/feedback" in html and "👎" in html
