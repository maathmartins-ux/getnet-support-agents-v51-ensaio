"""docs/DEMO.md: as respostas REAIS dos cenários oficiais, legíveis sem rodar nada.

Uso: python scripts/demo_md.py [--split official] [--out docs/DEMO.md]
     python scripts/demo_md.py --transcript evals/demo_transcript.jsonl [--out docs/DEMO_TRANSCRIPT.md]

Quem lê o repositório nem sempre executa o código ou assiste ao vídeo: a prova de que o sistema responde tem de
estar escrita e commitada. Este script lê
evals/results/live_<split>.json (1ª rodada de cada caso) e escreve, por cenário: pergunta, intenção, rota de
agentes, ferramentas, fontes, números sem base, resposta e custo. O cabeçalho carimba o commit e a data.

Árvore de passos (o trace legível por caso): quando a linha traz `steps` (a resposta do /chat), cada cenário mostra
agente → status/motivo → ms → ferramenta com args → prévia do resultado → quem decidiu o passo, lido de
`decided_by`/`why` ("decidido por: supervisor LLM (tool call)", "plano do router, rodado pelo atalho sem o
supervisor" ou "... pelo motor de tabela", "código (regra)", "operadora <nome>"; passo gravado sem o campo sai "não
registrado").
`--transcript`: roda NO PROCESSO (o LLM que o ambiente tiver; sem chave, o modo offline) uma conversa multi-turno
descrita em JSONL — {"user": "u1"} na 1ª linha; depois {"say": "..."}, {"confirm": true} (confirma a última ação
proposta e mostra o antes/depois da escrita) e {"say": "...", "operator": "resposta", "wait_s": 5,
"operator_after_s": 0.3} (a operadora simulada, evals/operator_sim.py — a mesma do split `hitl` do eval —, responde
o caso `operator_after_s` s depois de o turno começar a esperar, app/hitl_sync.py, com chave pessoal: o nome dela vai
para o passo e para a auditoria) — e escreve a transcrição com a árvore. O que a transcrição diz da operadora vem do
status do POST dela e da árvore do turno, não do roteiro.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
from contextlib import contextmanager
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


# Ao vivo, o plano vem do router LLM OU de uma regra que o substitui (seguimento herdado, guarda da própria empresa,
# queda do LLM para as palavras-chave); a linha ao vivo não grava qual dos dois, então o rótulo não diz "LLM".
ROUTER_LLM = ""
ROUTER_RULES = "regras, sem LLM"
# Por onde rodou o agente que o plano do router escolheu (supervisor.ROUTER_WHY), sem consultar o supervisor LLM.
ROUTER_LABEL = {
    "fast_path": "rodado pelo atalho sem o supervisor",
    "plan": "rodado pelo motor de tabela",
}
# A regra do código que pôs o passo no turno (supervisor.CODE_WHY), dita para quem lê o DEMO sem abrir o código.
WHY_LABEL = {
    "needs": "achado `needs` de outro especialista",
    "escalation": "escalada garantida: ninguém resolveu",
    "table": "FALLBACK do domínio ou router incerto",
    "budget": "orçamento do turno esgotado",
    "lead": "1º passo do plano do router, rodado antes do supervisor LLM",
    "hold": "caso aberto: modo espera",
}


DECIDED_LEGEND = ("Em cada passo, **decidido por** diz quem pôs o agente no turno: o supervisor LLM (tool call); o "
                  "plano do router (o router LLM, ou a regra que o substitui: seguimento herdado, guarda da própria "
                  "empresa, queda do LLM), quando o supervisor LLM não foi consultado (rodado pelo atalho de 1 passo "
                  "ou pelo motor de tabela); o código, com a regra entre parênteses "
                  "(`supervisor.CODE_WHY`); ou a operadora que respondeu o caso. \"não registrado\" = passo gravado "
                  "sem o campo `decided_by`.")
RULES_NOTE = ("Nesta execução não havia LLM: o plano do router veio das regras de palavras-chave "
              "(`router.classify_offline`) e o motor de tabela fez o papel do supervisor.")


def decided(st: dict, router: str = ROUTER_LLM) -> str:
    """Quem decidiu o passo: o supervisor LLM (tool call), o plano do router (`router` diz se foi o LLM ou as
    regras), o código (com a regra entre parênteses) ou a operadora que respondeu.

    Passo gravado sem o campo `decided_by` sai "não registrado": a decisão não é deduzida dos replanos nem do
    motor do turno, porque um mesmo turno mistura passos de origens diferentes.
    """
    who, why = st.get("decided_by"), st.get("why")
    if not who:
        return "decidido por: não registrado"
    if who == "llm":
        return "decidido por: supervisor LLM (tool call)"
    if who == "router":
        how = ROUTER_LABEL.get(why) or _short(why or "sem motivo", 40)
        return f"decidido por: plano do router{f' ({router})' if router else ''}, {how}"
    if who == "code":
        return f"decidido por: código ({WHY_LABEL.get(why) or _short(why or 'sem regra', 40)})"
    if who == "operator":
        name = st.get("operator")
        return f"decidido por: operadora `{_short(name, 40)}`" if name else "decidido por: operadora (sem nome)"
    return f"decidido por: {_short(who, 40)}"


def step_tree(steps: list[dict], router: str = ROUTER_LLM) -> list[str]:
    """Linhas markdown da árvore de passos: um item por agente (terminando em quem decidiu o passo), sub-itens por
    ferramenta. `router`: de onde veio o plano do router nestas respostas (ROUTER_LLM ou ROUTER_RULES)."""
    out = []
    for n, st in enumerate(steps, 1):
        extra = [f"motivo `{st['reason']}`"] if st.get("reason") else []
        if st.get("ms") is not None:
            extra.append(f"{st['ms']:.1f} ms" if st["ms"] < 10 else f"{st['ms']:.0f} ms")
        if st.get("ticket_id"):
            extra.append(f"caso {st['ticket_id']}")
        if st.get("answered_live"):
            extra.append("operador respondeu durante a espera")
        if st.get("operator") and st.get("decided_by") != "operator":  # a resposta dela já sai com o nome
            extra.append(f"operador `{st['operator']}`")
        if st.get("from_memory"):
            extra.append("do livro de fatos")
        if st.get("pending_action"):
            extra.append(f"ação proposta `{st['pending_action']}`")
        extra.append(decided(st, router))
        out.append(f"{n}. **{st.get('agent')}** · {st.get('status')} · " + " · ".join(extra))
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
    router = ROUTER_RULES if report.get("provider") == "offline" else ROUTER_LLM  # sem LLM, o router são regras
    unstable = ", ".join(stab.get("unstable", [])) or "nenhum"
    out = [
        f"# Respostas reais — split `{split}`",
        "",
        f"Geradas de `evals/results/live_{split}.json` (provedor `{report.get('provider')}`, "
        f"status `{report.get('status')}`, gasto US$ {report.get('spent_usd', 0):.2f}); respostas medidas no commit "
        f"`{report.get('git_sha', '?')}` ({report.get('recorded_at', '?')}), página gerada no commit `{sha}` "
        f"em {when}. "
        "Nada aqui foi escrito à mão: é a saída do `POST /chat` com o LLM ligado, 1ª rodada de cada caso.",
        "",
    ]
    if stab:
        out += [
            f"Estabilidade em {stab.get('runs')} rodadas: pass@1 {stab.get('pass_at_1')}, "
            f"pass^{stab.get('runs')} {stab.get('pass_hat_k')}; instáveis: {unstable}.",
            "",
        ]
    if any(r.get("steps") for r in rows):
        out += [DECIDED_LEGEND if router == ROUTER_LLM else f"{DECIDED_LEGEND} {RULES_NOTE}", ""]
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
            out += ["**Passos:**", "", *step_tree(r["steps"], router), ""]
        sources = [s.get("url") or s.get("id") for s in (r.get("sources") or [])][:5]
        if sources:
            out.append("**Fontes:** " + "; ".join(f"<{s}>" for s in sources))
        if r.get("unsupported_numbers"):
            out.append(f"**Números sem base na evidência:** {r['unsupported_numbers']}")
        out.append(f"**Checagens:** {r.get('checks')}")
    return "\n".join(out) + "\n"


DEMO_OPERATOR = "operadora_demo"


def demo_operator_key() -> tuple[str, str]:
    """Chave pessoal da operadora de demonstração, nova a cada transcrição: (chave, entrada do OPERATOR_KEYS).

    O servidor guarda só o sha256 da chave (app.auth.operator_name) e grava o NOME de quem respondeu na auditoria e
    no passo "human"; pelo token compartilhado, os dois diriam "admin", sem dono. A chave vive só na memória deste
    processo: nada a imprime nem grava.
    """
    key = secrets.token_urlsafe(24)
    return key, f"{DEMO_OPERATOR}:{hashlib.sha256(key.encode()).hexdigest()}"


@contextmanager
def _env(name: str, value: str):
    """`name`=`value` só durante o bloco; o ambiente do processo volta ao que era, com erro ou sem."""
    prev = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = prev


def operator_note(state: dict, ticket: str | None, steps: list[dict], answer: str) -> str:
    """O que a transcrição diz da operadora simulada no turno, lido do que aconteceu (não do roteiro): "responde"
    só com o POST 2xx no caso que o turno abriu; a resposta só é "durante a espera" se voltou no próprio turno (passo
    da operadora na árvore)."""
    who, status, answered = f"a operadora simulada `{DEMO_OPERATOR}`", state.get("status"), state.get("ticket")
    if status is None:
        if not (answered or ticket):
            return f"*({who} não respondeu: nenhum caso de atendimento novo na fila)*"
        return f"*({who} não respondeu: o caso {answered or ticket} ficou na fila, sem resposta enviada)*"
    if not 200 <= status < 300:
        return f"*({who} não respondeu: status {status})*"
    if not ticket or answered != ticket:
        return f"*({who} não respondeu ao caso deste turno: respondeu o caso {answered}, status {status})*"
    live = any(st.get("decided_by") == "operator" or st.get("answered_live") for st in steps)
    when = "durante a espera" if live else "depois da espera do turno (a resposta segue pela retomada do caso)"
    return f"*({who} responde pelo console, com chave pessoal, {when}: \"{answer}\")*"


def _audit_line(ticket: str) -> list[str]:
    """Quem a auditoria registrou como autor da resposta ao caso (lido do banco, não do roteiro da conversa)."""
    from app.store import get_store

    rows = get_store().audit_for(ticket, "handoff_reply")
    if not rows:
        return []
    who = ", ".join(f"`{r['actor']}` (canal {r['detail'].get('channel', '?')})" for r in rows)
    return [f"*(auditoria do caso {ticket}: `handoff_reply` registrado por {who})*", ""]


def transcript(path: Path, sha: str, when: str) -> str:
    """Roda a conversa descrita em `path` pelo /chat no processo e devolve a transcrição em markdown.

    A operadora simulada responde com a chave pessoal de `demo_operator_key`, somada às chaves que o ambiente já
    tiver só enquanto a transcrição roda (com chave pessoal configurada, o token compartilhado deixa de valer).
    """
    key, entry = demo_operator_key()
    with _env("OPERATOR_KEYS", ",".join(filter(None, [os.environ.get("OPERATOR_KEYS", ""), entry]))):
        return _transcript(path, sha, when, key)


def _transcript(path: Path, sha: str, when: str, operator_key: str) -> str:
    sys.path[:0] = [str(ROOT), str(ROOT / "src")]
    from fastapi.testclient import TestClient

    from app import hitl_sync
    from app.api import app
    from app.auth import issue_token
    from app.llm import get_llm
    from evals import operator_sim

    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    user = (lines[0] if lines and "user" in lines[0] else {}).get("user", "u1")
    turns = [x for x in lines if "user" not in x or len(x) > 1]
    client, headers = TestClient(app), {"Authorization": f"Bearer {issue_token(user)}"}
    router = ROUTER_LLM if get_llm("router").enabled else ROUTER_RULES
    head = (f"Gerada por `scripts/demo_md.py --transcript {path.as_posix()}` no commit `{sha}` em {when}, rodando o "
            f"`POST /chat` no processo (LLM: `{os.getenv('LLM_PROVIDER', 'padrão do ambiente')}`). Nada escrito à "
            "mão.")
    if any(turn.get("operator") for turn in turns):
        head += (f" Quem responde o caso é a operadora simulada `{DEMO_OPERATOR}`, com chave pessoal gerada nesta "
                 "execução (o `OPERATOR_KEYS` do processo guarda só o sha256 dela), pelo mesmo endpoint do console.")
    legend = DECIDED_LEGEND if router == ROUTER_LLM else f"{DECIDED_LEGEND} {RULES_NOTE}"
    out = ["# Transcrição multi-turno (memória, ação com antes/depois, humano)", "", head, "", legend, ""]
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
        operator = None
        if turn.get("operator"):  # a mesma operadora simulada do split hitl do eval, pelo console e com chave pessoal
            operator = operator_sim.Operator(turn["operator"], float(turn.get("operator_after_s", 0.3)),
                                             operator_sim.reply_console(operator_key),
                                             seen=operator_sim.open_handoffs()).start()
        # espera síncrona só neste turno (contexto, não env do processo); o TestClient leva o contexto ao /chat
        with hitl_sync.override(turn.get("wait_s", 5) if operator else None, operator_sim.TURN_POLL_S):
            got = client.post("/chat", json={"message": turn["say"], "conversation_id": conv}, headers=headers).json()
        ticket = (got.get("handoff") or {}).get("ticket_id")
        # o turno acabou: sem caso, ela desiste (o caso de um turno seguinte não é deste); com caso, a resposta dela
        # sai na hora dela, no turno ou depois dele (aí vai pela retomada do caso)
        state = operator.finish(ticket) if operator else {}
        conv = got.get("conversation_id", conv)
        pending = got.get("pending_action") or pending
        steps = got.get("steps") or []
        out += [f"### Turno {n}", "", f"**Cliente:** {turn['say']}", ""]
        if operator:
            out += [operator_note(state, ticket, steps, turn["operator"]), ""]
        out += [f"**Intenção:** {got.get('intent')} · **rota:** {' → '.join(got.get('route') or [])}", "",
                "**Passos:**", "", *step_tree(steps, router), "", "**Resposta:**", "",
                *[f"> {ln}" if ln.strip() else ">" for ln in (got.get("answer") or "").splitlines()], ""]
        if operator and ticket:
            out += _audit_line(ticket)
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
