"""Réplicas sem arquivo compartilhado: 2 processos da API (portas diferentes) sobre o MESMO Postgres, sem Docker.

Prova pelo HTTP o que muda quando cada réplica mora numa máquina (só a rede até o banco é comum):
1. a conversa continua alternando réplicas (histórico completo);
2. 8 escalonamentos simultâneos da mesma conversa, divididos entre as réplicas, abrem UM caso;
3. o caso aberto numa réplica é respondido na outra e o plano retoma (mensagem "resumed" no histórico);
4. a verificação de SLA rodando nas duas ao mesmo tempo sobe cada caso vencido uma vez só;
5. o limite de uso é um só para as duas réplicas;
6. latência do /chat em modo offline (sem LLM; mede o caminho do app + Postgres, não o modelo): p50 e p95.

Uso: TEST_DATABASE_URL=postgresql://... python scripts/pg_replicas_smoke.py [--requests 100]
Cria um esquema próprio no banco e o apaga no fim. Saída: uma linha por prova e um JSON com o resumo.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET = "pg-replicas-smoke-secret-0123456789abcdef"
OPERATOR = "pg-replicas-smoke-operator-0123456789"


def call(port: int, method: str, path: str, headers: dict, body: dict | None = None) -> tuple[int, dict, str]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}"), resp.headers.get("X-Instance", "?")
    except urllib.error.HTTPError as exc:
        return exc.code, {}, exc.headers.get("X-Instance", "?")


def start(port: int, name: str, env: dict) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-m", "uvicorn", "app.api:app", "--host", "127.0.0.1", "--port",
                             str(port), "--log-level", "warning"], cwd=ROOT,
                            env={**env, "INSTANCE_NAME": name}, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def wait_ready(port: int, timeout: float = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if call(port, "GET", "/health", {})[0] == 200:
                return True
        except OSError:
            pass
        time.sleep(0.3)
    return False


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=int, default=100, help="pedidos para medir a latência")
    ap.add_argument("--ports", default="18101,18102")
    args = ap.parse_args()
    base = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not base:
        print("defina TEST_DATABASE_URL=postgresql://...", file=sys.stderr)
        return 2
    import psycopg

    schema = "smoke_" + uuid.uuid4().hex[:10]
    with psycopg.connect(base, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
    url = f"{base}{'&' if '?' in base else '?'}options=-csearch_path%3D{schema}"
    env = {**os.environ, "DATABASE_URL": url, "AUTH_MODE": "required", "AUTH_SECRET": SECRET,
           "OPERATOR_TOKEN": OPERATOR, "LLM_PROVIDER": "offline", "RATE_LIMIT_PER_MIN": "1000",
           "SLA_CHECK_SECONDS": "0", "PYTHONPATH": f"{ROOT / 'src'}{os.pathsep}{os.environ.get('PYTHONPATH', '')}",
           "DOMAIN": os.getenv("DOMAIN", "example"),
           "DATA_DIR": os.getenv("DATA_DIR", str(ROOT / "tests" / "fixtures" / "kit_data" / "data"))}
    env.pop("AUTH_KEYS", None)
    os.environ.update({"AUTH_SECRET": SECRET, "DATABASE_URL": url})
    sys.path.insert(0, str(ROOT / "src"))
    from app.auth import issue_token

    ports = [int(p) for p in args.ports.split(",")]
    procs = [start(p, f"r{i + 1}", env) for i, p in enumerate(ports)]
    results: list[tuple[str, bool, str]] = []
    summary: dict = {}
    try:
        if not all(wait_ready(p) for p in ports):
            print("réplicas não subiram:", [p.stderr.read().decode()[-500:] for p in procs if p.poll() is not None])
            return 1
        user = {"Authorization": f"Bearer {issue_token('u1')}"}
        op = {"X-Operator-Token": OPERATOR}

        # 1. continuidade alternando réplicas
        conv, served, said = None, [], []
        for i in range(6):
            msg = f"Mensagem número {i + 1} da conversa entre réplicas."
            code, body, inst = call(ports[i % 2], "POST", "/chat", user,
                                    {"message": msg, **({"conversation_id": conv} if conv else {})})
            conv, _ = body.get("conversation_id", conv), served.append(inst)
            said.append(msg)
        code, hist, _ = call(ports[1], "GET", f"/conversations/{conv}", user)
        users = [m["content"] for m in hist.get("messages", []) if m["role"] == "user"]
        results.append(("continuidade", users == said and set(served) == {"r1", "r2"},
                        f"6 turnos em {sorted(set(served))}; histórico {len(users)}/6 na ordem"))

        # 2. um caso só com 8 escalonamentos simultâneos nas duas réplicas
        conv2 = call(ports[0], "POST", "/chat", user, {"message": "Oi"})[1]["conversation_id"]
        tickets, lock = [], threading.Lock()

        def escalate(i: int) -> None:
            c, b, _ = call(ports[i % 2], "POST", "/chat", user,
                           {"message": "Quero falar com um atendente humano", "conversation_id": conv2})
            with lock:
                tickets.append((b.get("handoff") or {}).get("ticket_id") if c == 200 else f"HTTP {c}")

        threads = [threading.Thread(target=escalate, args=(i,)) for i in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        distinct = {t for t in tickets if t}
        results.append(("um caso", len(distinct) == 1 and all(str(t).startswith("T-") for t in tickets),
                        f"8 pedidos em 2 réplicas → {sorted(distinct)}"))

        # 3. aberto em r1/r2, respondido na outra, com retomada
        ticket = next(iter(distinct))
        code, out, inst = call(ports[1], "POST", f"/handoffs/{ticket}/reply", op, {"answer": "Resolvido por aqui."})
        again = call(ports[0], "POST", f"/handoffs/{ticket}/reply", op, {"answer": "de novo"})[0]
        last = call(ports[0], "GET", f"/conversations/{conv2}", user)[1]["messages"][-1]
        results.append(("resposta noutra réplica", code == 200 and again == 404 and last["intent"] == "resumed",
                        f"resposta em {inst}: HTTP {code}; 2ª resposta HTTP {again}; última mensagem {last['intent']}"))

        # 4. SLA nas duas réplicas ao mesmo tempo
        for i in range(6):
            call(ports[i % 2], "POST", "/chat", {"Authorization": f"Bearer {issue_token(f'sla{i}')}"},
                 {"message": "Quero falar com um atendente"})
        later, got = time.time() + 10 ** 6, []
        open_now = len(call(ports[0], "GET", "/handoffs", op)[1])  # todos os casos abertos vencem com `later`

        def sla(port: int) -> None:
            body = call(port, "POST", f"/handoffs/sla-check?now={later}", op)[1]
            with lock:
                got.extend(t["id"] for t in body.get("escalated", []))

        threads = [threading.Thread(target=sla, args=(p,)) for p in ports * 2]
        [t.start() for t in threads]
        [t.join() for t in threads]
        results.append(("SLA uma vez", len(got) == open_now >= 6 and len(set(got)) == open_now,
                        f"{open_now} casos abertos; 4 verificações simultâneas (2 por réplica) → {len(got)} subidas, "
                        f"{len(set(got))} casos distintos"))

        # 5. limite de uso compartilhado: 10 por minuto somados nas duas réplicas
        for p in procs:
            p.terminate()
            p.wait(timeout=10)
        procs = [start(p, f"r{i + 1}", {**env, "RATE_LIMIT_PER_MIN": "10"}) for i, p in enumerate(ports)]
        if not all(wait_ready(p) for p in ports):
            print("réplicas não voltaram")
            return 1
        rl = {"Authorization": f"Bearer {issue_token('rl-user')}"}
        codes = [call(ports[i % 2], "POST", "/chat", rl, {"message": "Qual o prazo de entrega?"})[0]
                 for i in range(14)]
        results.append(("limite compartilhado", codes.count(200) == 10 and codes.count(429) == 4,
                        f"14 pedidos alternados: {codes.count(200)}x200, {codes.count(429)}x429 (limite 10/min)"))

        # 6. latência offline (sem LLM) com Postgres
        for p in procs:
            p.terminate()
            p.wait(timeout=10)
        procs = [start(p, f"r{i + 1}", env) for i, p in enumerate(ports)]
        if not all(wait_ready(p) for p in ports):
            return 1
        ms = []
        for i in range(args.requests):
            t0 = time.perf_counter()
            code = call(ports[i % 2], "POST", "/chat", user, {"message": "Qual o prazo de entrega?"})[0]
            ms.append((time.perf_counter() - t0) * 1000)
            if code != 200:
                results.append(("latência", False, f"HTTP {code} no pedido {i}"))
                break
        else:
            q = statistics.quantiles(ms, n=20)
            summary["latency_ms"] = {"n": len(ms), "p50": round(statistics.median(ms), 1), "p95": round(q[18], 1),
                                     "mode": "offline (sem LLM), 1 cliente sequencial, 2 réplicas, Postgres local"}
            results.append(("latência", True, f"n={len(ms)} p50={summary['latency_ms']['p50']} ms "
                                              f"p95={summary['latency_ms']['p95']} ms (offline, sem LLM)"))
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=10)
        with psycopg.connect(base, autocommit=True) as conn:
            conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    for name, ok, detail in results:
        print(f"[{'ok' if ok else 'FALHOU'}] {name}: {detail}")
    summary["passed"] = all(ok for _, ok, _ in results) and len(results) == 6
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
