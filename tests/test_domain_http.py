"""Frente Q: casos official pelo HTTP, em AUTH_MODE demo e required; token ruim = 401."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.auth import issue_token

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = [c for c in (json.loads(x) for x in (ROOT / "evals/cases.jsonl").read_text(encoding="utf-8").splitlines()
                        if x.strip()) if c["split"] == "official"]
client = TestClient(app)


def test_official_loaded():
    assert len(OFFICIAL) == 10


@pytest.mark.parametrize("case", OFFICIAL[:3], ids=lambda c: c["id"])
def test_official_demo_mode(case, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "demo")
    r = client.post("/chat", json={"message": case["message"], "user_id": case["user_id"]})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] and body["identity_verified"] is False


@pytest.mark.parametrize("case", OFFICIAL[:3], ids=lambda c: c["id"])
def test_official_required_mode(case, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "required")
    headers = {"Authorization": f"Bearer {issue_token(case['user_id'])}"}
    r = client.post("/chat", json={"message": case["message"]}, headers=headers)
    assert r.status_code == 200
    assert r.json()["answer"] and r.json()["user_id"] == case["user_id"]


@pytest.mark.parametrize("mode", ["demo", "required"])
def test_bad_token_is_401(mode, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", mode)
    r = client.post("/chat", json={"message": OFFICIAL[0]["message"]},
                    headers={"Authorization": "Bearer cliente1988.forjado"})
    assert r.status_code == 401


def test_required_without_token_is_401(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "required")
    assert client.post("/chat", json={"message": "oi", "user_id": "cliente1988"}).status_code == 401
