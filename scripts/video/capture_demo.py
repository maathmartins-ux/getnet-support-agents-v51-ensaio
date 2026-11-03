"""Respostas REAIS do sistema para o vídeo: app em processo (TestClient), AUTH_MODE=demo, payload literal, LLM ligado.

Uso: python scripts/video/capture_demo.py [saida.json]   (padrão docs/video/demo.json)
Cenários: um por intenção do split `official` de evals/cases.jsonl (máx. 5) + o 1º caso `approval` (escrita com
confirmação). Getnet v4 (01/11/2026): ~US$ 0,10 e 1 min para 5 respostas. DEMO_PROVIDER=offline para ensaiar.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "video" / "demo.json"
out.parent.mkdir(parents=True, exist_ok=True)
os.environ.update({"AUTH_MODE": "demo", "LLM_PROVIDER": os.getenv("DEMO_PROVIDER", "anthropic"),
                   "DB_PATH": str(ROOT / "var" / "demo.db"), "RATE_LIMIT_PER_MIN": "1000"})
(ROOT / "var").mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)
from fastapi.testclient import TestClient  # noqa: E402

from app.api import app  # noqa: E402

cases = [json.loads(line) for line in (ROOT / "evals" / "cases.jsonl").read_text(encoding="utf-8").splitlines()
         if line.strip()]
picked, seen = [], set()
for c in cases:
    intent = (c.get("expect") or {}).get("intent")
    if c.get("split") == "official" and intent not in seen and c.get("message"):
        seen.add(intent)
        picked.append((f"{intent} ({c['id']})", c["message"], c.get("user_id")))
picked = picked[:5]
picked += [(f"escrita com confirmação ({c['id']})", c["message"], c.get("user_id"))
           for c in cases if c.get("split") == "approval" and c.get("message")][:1]
keep = ("answer", "intent", "route", "replans", "sources", "tool_calls", "handoff", "pending_action", "engine",
        "unsupported_numbers", "risk_flags", "usage", "identity_verified")
res = []
with TestClient(app) as client:
    for label, msg, user in picked:
        r = client.post("/chat", json={"message": msg, "user_id": user}).json()
        slim = {k: r.get(k) for k in keep}
        slim["sources"] = [s.get("url") for s in (r.get("sources") or [])][:3]
        slim["tool_calls"] = [t.get("name") for t in (r.get("tool_calls") or [])]
        res.append({"label": label, "message": msg, "response": slim})
out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(res), "respostas →", out.relative_to(ROOT), [r["response"]["intent"] for r in res])
