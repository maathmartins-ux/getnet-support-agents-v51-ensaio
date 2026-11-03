"""Gera slides.html do vídeo a partir dos resultados COMMITADOS (evals/results) e de respostas reais (demo.json).

Uso: python scripts/video/make_slides.py [saida.html]   (lê README, docs/SPEC.md, evals/results, docs/video/demo.json)
Nenhum número é digitado: tudo vem do JSON commitado. Getnet v4 (01/11/2026): 15 cenas, ~3 min.
"""
import html
import json
import re
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
out = Path(sys.argv[1]) if len(sys.argv) > 1 else repo / "var" / "slides.html"
out.parent.mkdir(parents=True, exist_ok=True)
demo_path = repo / "docs" / "video" / "demo.json"
demo = json.loads(demo_path.read_text(encoding="utf-8")) if demo_path.exists() else []
readme = (repo / "README.md").read_text(encoding="utf-8")
title = (re.search(r"^# (.+)$", readme, re.M) or [None, "Projeto"])[1]
spec = (repo / "docs" / "SPEC.md").read_text(encoding="utf-8") if (repo / "docs" / "SPEC.md").exists() else ""
problem = (re.search(r"## Problema\s+(.+?)(?:\n\n|\n#)", spec, re.S) or [None, readme.split("\n\n")[1]])[1]
limits = re.findall(r"^- (.+)$", readme.split("## 9.")[-1], re.M)[:5] if "## 9." in readme else []
R = repo / "evals" / "results"
def load(n):
    p = R / n
    return json.loads(p.read_text()) if p.exists() else None
off = load("latest.json") or {}
m = off.get("metrics", {})
def pct(split, key):
    v = (m.get(split) or {}).get(key)
    return "—" if v is None else f"{v:.0f}%"
live = {p.stem.replace("live_", ""): json.loads(p.read_text()) for p in sorted(R.glob("live_*.json"))}
judge = load("judge.json") or {}
abl = load("ablation_replan.json") or {}
ret = off.get("retrieval") or {}
def cell(v): return html.escape(str(v))
slides = []
def S(title, body, secs=12):
    slides.append(f'<section data-s="{secs}"><h1>{cell(title)}</h1><div class="b">{body}</div></section>')
S(title, "<p>Vídeo legendado gerado a partir do repositório.</p><p class='s'>Respostas reais do <code>POST /chat</code> com LLM e números lidos de evals/results/ commitado.</p>", 8)
S("O problema", f"<p>{cell(re.sub(r'[`*]', '', problem.strip()))}</p>", 12)
S("Arquitetura", "<pre>guardrails → Router (intenção, plano, idioma)\n          → Supervisor (lê ok / insufficient / error e REPLANEJA)\n               ├─ Knowledge (faq): RAG nas fontes de data/sources.json, web p/ general\n               ├─ Customer Support (records): tools do domínio, escrita só com confirmação\n               └─ Human Escalation: fila persistida, operador responde, conversa retoma\n          → checagem de números e flags de risco (sem LLM) → JSON</pre>", 14)
for d in demo[:5]:
    r = d.get("response") or {}
    meta = {k: r.get(k) for k in ("intent", "route", "tool_calls", "replans", "pending_action", "unsupported_numbers")}
    meta["handoff"] = (r.get("handoff") or {}).get("required")
    ans = (r.get("answer") or "")[:700]
    body = (f"<p class='q'>POST /chat “{cell(d.get('message'))}”</p><pre class='a'>{cell(ans)}</pre>"
            f"<pre class='m'>{cell(json.dumps(meta, ensure_ascii=False))}</pre>")
    S("Demo ao vivo: " + d.get("label", "cenário"), body, 14)
S("Avaliação offline (gate do CI)", "<table><tr><th>split</th><th>intenção</th><th>handoff</th><th>idioma</th><th>tools</th></tr>" + "".join(
    f"<tr><td>{s}</td><td>{pct(s,'intent_acc')}</td><td>{pct(s,'handoff_acc')}</td><td>{pct(s,'language_acc')}</td><td>{pct(s,'tools_acc')}</td></tr>"
    for s in ["official", "replan", "parallel", "approval", "official-var", "memory", "guardrail", "heldout", "ALL"] if s in m) + "</table>", 14)
if live:
    rows = "".join(f"<tr><td>{s}</td><td>{(r.get('metrics',{}).get(s) or r.get('metrics',{}).get('ALL') or {}).get('intent_acc','—')}</td><td>{r.get('stability',{}).get('pass_hat_k','—')}</td><td>US$ {r.get('spent_usd',0):.3f}</td></tr>" for s, r in live.items())
    S("Ao vivo (LLM real, 3 rodadas por caso)", f"<table><tr><th>split</th><th>intenção %</th><th>pass^3</th><th>custo</th></tr>{rows}</table>", 12)
if abl:
    a = (m.get("replan") or {}).get("handoff_outcome_acc"); b = (abl.get("metrics", {}).get("replan") or {}).get("handoff_outcome_acc")
    S("Replanejamento vale quanto?", f"<p>Mesmos casos do split replan, desfecho certo:</p><p class='big'>{a if a is not None else '—'}% com × {b if b is not None else '—'}% sem</p>", 10)
if ret:
    S("RAG medido", f"<p>{ret.get('positives','?')} perguntas com fonte: Recall@3 <b>{ret.get('recall@3','—')}</b> · MRR <b>{ret.get('mrr','—')}</b></p><p class='s'>Portão “sem fonte, sem afirmação” calibrado; negativas vão para o humano.</p>", 10)
if judge:
    S("Juiz LLM calibrado", f"<p>grounded {judge.get('grounded_rate','—')} · helpful {judge.get('helpful_rate','—')}</p><p class='s'>calibração contra rótulos humanos: κ {(judge.get('calibration') or {}).get('cohen_kappa','—')}</p>", 10)
S("Segurança e produção", "<ul><li>JWT com exp/iss/aud/jti e revogação; demo marca identity_verified=false</li><li>guardrails regex + LLM, PII mascarada na entrada, no log e na saída</li><li>escrita só com confirmação; risco alto pede operador (quatro olhos)</li><li>CI: gitleaks, testes, gate do eval, Docker, 2 réplicas atrás de balanceador</li></ul>", 12)
_MD = re.compile(r"[`*\[\]]")
S("Limitações", "<ul>" + "".join(f"<li>{cell(_MD.sub('', x))[:160]}</li>" for x in limits)
  + "</ul><p class='s'>Detalhes: README §9.</p>", 12)
css = """body{margin:0;background:#0f1720;color:#e8eef5;font-family:Inter,Segoe UI,Arial,sans-serif}
section{display:none;flex-direction:column;justify-content:center;width:1280px;height:720px;padding:56px 72px;box-sizing:border-box}
h1{font-size:44px;margin:0 0 24px;color:#ffcf33}.b{font-size:26px;line-height:1.45}.s{color:#9fb3c8;font-size:20px}
pre{background:#16212d;border-radius:10px;padding:16px 20px;font-size:17px;white-space:pre-wrap}.q{font-size:28px;color:#9fe0ff}
table{border-collapse:collapse;font-size:22px}td,th{border-bottom:1px solid #2a3a4a;padding:6px 18px;text-align:left}.big{font-size:56px;color:#7ee787}.a{font-size:18px}.m{font-size:15px;color:#9fe0ff}"""
out.write_text(f"<!doctype html><meta charset=utf-8><style>{css}</style>" + "".join(slides), encoding="utf-8")
print(len(slides), "cenas,", sum(int(s.split('data-s="')[1].split('"')[0]) for s in slides), "s")
