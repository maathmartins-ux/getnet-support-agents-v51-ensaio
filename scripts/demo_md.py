"""docs/DEMO.md: as respostas REAIS dos cenários oficiais, legíveis sem rodar nada.

Uso: python scripts/demo_md.py [--split official] [--out docs/DEMO.md]
     python scripts/demo_md.py --transcript evals/demo_transcript.jsonl [--out docs/DEMO_TRANSCRIPT.md]

O avaliador da Régua V4 não executa o código nem assiste ao vídeo ("Não executei build nem testes"; "Vídeo … não
assistido"): a prova de que o sistema responde tem de estar escrita e commitada. Este script lê
evals/results/live_<split>.json (1ª rodada de cada caso) e escreve, por cenário: pergunta, intenção, rota de
agentes, ferramentas, fontes, números sem base, resposta e custo. O cabeçalho carimba o commit e a data.

Árvore de passos (kit v5.4, ideia do Skywalker: o trace legível por caso): quando a linha traz `steps` (a resposta do
/chat), cada cenário mostra agente → status/motivo → ms → ferramenta com args → prévia do resultado.
`--transcript`: roda NO PROCESSO (o LLM que o ambiente tiver; sem chave, o modo offline) uma conversa multi-turno
descrita em JSONL — {"user": "u1"} na 1ª linha; depois {"say": "..."}, {"confirm": true} (confirma a última ação
proposta e mostra o antes/depois da escrita) e {"say": "...", "operator": "resposta", "wait_s": 5} (um operador
simulado responde o caso durante a espera síncrona, app/hitl_sync.py) — e escreve a transcrição com a árvore.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str, cwd: Path = ROOT) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    return r.stdout.strip()


ENGINE_LABEL = {"fast_path": "atalho de 1 passo (o supervisor LLM decide se o especialista não resolver)",
                "llm": "supervisor LLM (laço de tool use)", "table": "determinístico (sem LLM)"}


def first_runs(rows: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for r in rows:
        if str(r.get("run", 0)) in ("0", "") and r["id"] not in seen:
            seen[r["id"]] = r
    return list(seen.values())


def tool_names(row: dict) -> list[str]:
    """Nas respostas reais `tool_calls` é lista de {name, args, ok}; aceita também texto simples."""
    return [t.get("name", "?") if isinstance(t, dict) else str(t) for t in row.get("tool_calls") or []]


def handoff(row: dict) -> str:
    return "não" if (row.get("checks") or {}).get("handoff", True) else "sim"


def verdict(row: dict) -> str:
    checks = row.get("checks") or {}
    bad = [k for k, v in checks.items() if v is False]
    return "OK" if not bad else "falhou: " + ", ".join(bad)


def _short(value, limit: int = 140) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def step_tree(steps: list[dict]) -> list[str]:
    """Linhas markdown da árvore de passos: um item por agente, sub-itens por ferramenta."""
    out = []
    for n, st in enumerate(steps, 1):
        extra = [f"motivo `{st['reason']}`"] if st.get("reason") else []
        if st.get("ms") is not None:
            extra.append(f"{st['ms']:.1f} ms" if st["ms"] < 10 else f"{st['ms']:.0f} ms")
        if st.get("ticket_id"):
            extra.append(f"caso {st['ticket_id']}")
        if st.get("answered_live"):
            extra.append("operador respondeu durante a espera")
        if st.get("operator"):
            extra.append(f"operador `{st['operator']}`")
        if st.get("from_memory"):
            extra.append("do livro de fatos")
        if st.get("pending_action"):
            extra.append(f"ação proposta `{st['pending_action']}`")
        out.append(f"{n}. **{st.get('agent')}** · {st.get('status')}" + (" · " + " · ".join(extra) if extra else ""))
        for t in st.get("tools") or []:
            proposed = '"needs_confirmation": true' in (t.get("preview") or "")
            state = "proposta (aguarda a confirmação do cliente)" if proposed else "ok" if t.get("ok") else "falhou"
            line = f"   - `{t.get('name')}` {_short(t.get('args') or {}, 80)} → {state}"
            if t.get("preview"):
                line += f" · `{_short(t['preview'])}`"
            out.append(line)
    return out


def change_table(data: dict) -> list[str]:
    """Antes/depois de uma escrita executada (actions.record_change)."""
    changed, unchanged = data.get("changed") or {}, data.get("unchanged") or []
    rows = ["| campo | antes | depois |", "|---|---|---|"]
    rows += [f"| {k} | {_short(a, 60)} | **{_short(b, 60)}** |" for k, (a, b) in changed.items()]
    rows += [f"| {k} | {_short((data.get('before') or {}).get(k), 60)} | (igual) |" for k in unchanged]
    return rows


def render(report: dict, split: str, sha: str, when: str) -> str:
    rows = first_runs(report.get("rows", []))
    stab = report.get("stability") or {}
    unstable = ", ".join(stab.get("unstable", [])) or "nenhum"
    out = [
        f"# Respostas reais — split `{split}`",
        "",
        f"Geradas de `evals/results/live_{split}.json` (provedor `{report.get('provider')}`, "
        f"status `{report.get('status')}`, gasto US$ {report.get('spent_usd', 0):.2f}) no commit `{sha}` em {when}. "
        "Nada aqui foi escrito à mão: é a saída do `POST /chat` com o LLM ligado, 1ª rodada de cada caso.",
        "",
    ]
    if stab:
        out += [
            f"Estabilidade em {stab.get('runs')} rodadas: pass@1 {stab.get('pass_at_1')}, "
            f"pass^{stab.get('runs')} {stab.get('pass_hat_k')}; instáveis: {unstable}.",
            "",
        ]
    out += ["| caso | intenção | rota | ferramentas | handoff | veredito automático |", "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(
            f"| `{r['id']}` | {r.get('got_intent')} | {' → '.join(r.get('route') or [])} | "
            f"{', '.join(tool_names(r)) or '—'} | {handoff(r)} | "
            f"{verdict(r)} |"
        )
    for r in rows:
        out += [
            "",
            f"## {r['id']}",
            "",
            f"**Pergunta:** {r.get('message')}",
            "",
            f"**Intenção:** {r.get('got_intent')} (esperada {r.get('expected_intent')}) · "
            f"**rota:** {' → '.join(r.get('route') or [])} · **replanos:** {r.get('replans') or 'nenhum'} · "
            f"**caminho:** {ENGINE_LABEL.get(r.get('engine'), r.get('engine'))} · "
            f"**custo:** US$ {r.get('cost_usd', 0):.4f} · "
                f"**latência:** {r.get('ms', 0) / 1000:.1f} s",
            "",
            "**Resposta:**",
            "",
            *[f"> {line}" if line.strip() else ">" for line in (r.get("answer") or "").splitlines()],
            "",
        ]
        if r.get("steps"):
            out += ["**Passos:**", "", *step_tree(r["steps"]), ""]
        sources = [s.get("url") or s.get("id") for s in (r.get("sources") or [])][:5]
        if sources:
            out.append("**Fontes:** " + "; ".join(f"<{s}>" for s in sources))
        if r.get("unsupported_numbers"):
            out.append(f"**Números sem base na evidência:** {r['unsupported_numbers']}")
        out.append(f"**Checagens:** {r.get('checks')}")
    return "\n".join(out) + "\n"


def _operator_thread(answer: str, after_s: float, seen: set[str]):
    """Operador simulado: responde, pelo endpoint do console, o 1º caso de atendimento novo da fila."""
    import threading
    import time

    from fastapi.testclient import TestClient

    from app.api import app
    from app.config import operator_token
    from app.store import get_store

    def run() -> None:
        client, end = TestClient(app), time.time() + 30
        while time.time() < end:
            fresh = [t for t in get_store().list_tickets("open") if t["kind"] == "handoff" and t["id"] not in seen]
            if fresh:
                time.sleep(after_s)
                client.post(f"/handoffs/{fresh[0]['id']}/reply", json={"answer": answer},
                            headers={"X-Operator-Token": operator_token()})
                return
            time.sleep(0.05)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def transcript(path: Path, sha: str, when: str) -> str:
    """Roda a conversa descrita em `path` pelo /chat no processo e devolve a transcrição em markdown."""
    import os

    sys.path[:0] = [str(ROOT), str(ROOT / "src")]
    from fastapi.testclient import TestClient

    from app.api import app
    from app.auth import issue_token
    from app.store import get_store

    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    user = (lines[0] if lines and "user" in lines[0] else {}).get("user", "u1")
    turns = [x for x in lines if "user" not in x or len(x) > 1]
    client, headers = TestClient(app), {"Authorization": f"Bearer {issue_token(user)}"}
    out = ["# Transcrição multi-turno (memória, ação com antes/depois, humano)", "",
           f"Gerada por `scripts/demo_md.py --transcript {path.as_posix()}` no commit `{sha}` em {when}, rodando o "
           f"`POST /chat` no processo (LLM: `{os.getenv('LLM_PROVIDER', 'padrão do ambiente')}`). Nada escrito à mão.",
           ""]
    conv, pending, n = None, None, 0
    for turn in turns:
        if turn.get("confirm"):
            if not pending:
                continue
            done = client.post(f"/actions/{pending}/confirm", headers=headers).json()
            out += [f"### Cliente confirma a ação `{pending}`", ""]
            data = done.get("data") if isinstance(done, dict) else None
            if isinstance(data, dict) and data.get("changed") is not None:
                out += change_table(data) + [""]
            else:
                out += [f"> {_short(done, 300)}", ""]
            pending = None
            continue
        n += 1
        thread, prev = None, os.environ.get("HITL_SYNC_WAIT_S")
        if turn.get("operator"):
            os.environ["HITL_SYNC_WAIT_S"] = str(turn.get("wait_s", 5))
            os.environ.setdefault("HITL_SYNC_POLL_S", "0.2")
            seen = {t["id"] for t in get_store().list_tickets("open")}
            thread = _operator_thread(turn["operator"], float(turn.get("operator_after_s", 0.3)), seen)
        try:
            got = client.post("/chat", json={"message": turn["say"], "conversation_id": conv}, headers=headers).json()
        finally:
            if turn.get("operator"):
                if prev is None:
                    os.environ.pop("HITL_SYNC_WAIT_S", None)
                else:
                    os.environ["HITL_SYNC_WAIT_S"] = prev
        if thread:
            thread.join(5)
        conv = got.get("conversation_id", conv)
        pending = got.get("pending_action") or pending
        out += [f"### Turno {n}", "", f"**Cliente:** {turn['say']}", ""]
        if turn.get("operator"):
            out += [f"*(operador simulado responde durante a espera: \"{turn['operator']}\")*", ""]
        out += [f"**Intenção:** {got.get('intent')} · **rota:** {' → '.join(got.get('route') or [])}", "",
                "**Passos:**", "", *step_tree(got.get("steps") or []), "", "**Resposta:**", "",
                *[f"> {ln}" if ln.strip() else ">" for ln in (got.get("answer") or "").splitlines()], ""]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="official")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--results", type=Path, default=ROOT / "evals" / "results")
    ap.add_argument("--transcript", type=Path, default=None, help="conversa em JSONL (ver o docstring)")
    args = ap.parse_args(argv)
    sha = _git("rev-parse", "--short", "HEAD") or "sem git"
    when = datetime.now(UTC).strftime("%d/%m/%Y %H:%M UTC")
    if args.transcript:
        out = args.out or ROOT / "docs" / "DEMO_TRANSCRIPT.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(transcript(args.transcript, sha, when), encoding="utf-8")
        print(f"{out}: transcrição de {args.transcript}")
        return 0
    args.out = args.out or ROOT / "docs" / "DEMO.md"
    path = args.results / f"live_{args.split}.json"
    if not path.exists():
        print(f"Sem {path}: rode o eval ao vivo antes (scripts/live_eval.sh).", file=sys.stderr)
        return 1
    report = json.loads(path.read_text(encoding="utf-8"))
    text = render(report, args.split, sha, when)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"{args.out}: {len(first_runs(report.get('rows', [])))} cenários")
    return 0


if __name__ == "__main__":
    sys.exit(main())
