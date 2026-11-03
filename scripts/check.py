"""Check único do projeto: lint + testes + gate do eval [+ build e smoke do container].

Uso:
  python scripts/check.py            # rápido, a cada merge de fork (~10 s)
  python scripts/check.py --docker   # completo: imagem, /health com dados, eval via HTTP
  python scripts/check.py --docker --extras hybrid   # imagem com a busca híbrida (modelo embutido)

Funciona sem `make` (Windows). Sai com código 1 se qualquer etapa falhar e imprime o resumo.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
IMAGE = "app-check"
# Módulos que NÃO podem estar na imagem: dev (pytest/ruff) e extras opcionais (híbrido, OTel SDK) não pedidos.
FORBIDDEN_IN_IMAGE = ["pytest", "ruff", "fastembed", "opentelemetry.sdk"]
EXTRA_MODULES = {"hybrid": "fastembed", "otel": "opentelemetry.sdk"}
# Console do Windows é cp1252: sem isto, subprocesso que imprime acento/seta quebra com UnicodeEncodeError.
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def sh(cmd: list[str], env: dict | None = None, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env={**ENV, **(env or {})}, **kw)


def pytest_workers() -> list[str]:
    # 4 processos com pytest-xdist (extra dev); venv antiga sem ele roda em série em vez de quebrar o check.
    has_xdist = sh([PY, "-c", "import xdist"]).returncode == 0
    return ["-n", os.getenv("CHECK_WORKERS", "4")] if has_xdist else []


def step(name: str, cmd: list[str], env: dict | None = None) -> tuple[str, bool, float, str]:
    t0 = time.perf_counter()
    r = sh(cmd, env)
    out = (r.stdout + r.stderr).strip()
    return name, r.returncode == 0, time.perf_counter() - t0, out


def free_port() -> int:
    """Porta livre do sistema: nunca colide com um `docker compose up` na 8000 nem com outro check em paralelo."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_health(url: str, timeout_s: float = 60) -> dict | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                return json.loads(resp.read())
        except Exception:
            time.sleep(1)
    return None


CHECK_SECRET = "check-secret-only-for-the-container-smoke"  # o container do smoke sobe com este AUTH_SECRET


def mcp_smoke(port: int) -> tuple[str, bool, float, str]:
    """/mcp no container: sem token → 401; com JWT → initialize responde com o nome do servidor."""
    t0 = time.perf_counter()
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "check", "version": "1"}}}).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

    def post(extra: dict) -> tuple[int, str]:
        req = urllib.request.Request(f"http://localhost:{port}/mcp/", data=body, headers={**headers, **extra})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")

    anon, _ = post({})
    status, text = post({"Authorization": f"Bearer {_token()}"})
    ok = anon == 401 and status == 200 and "support-agents" in text
    return "mcp no container (401 sem token, initialize com JWT)", ok, time.perf_counter() - t0, \
        f"anônimo {anon}; autenticado {status}: {text[:200]}"


def _token() -> str:
    r = subprocess.run([PY, "-c", "from app.auth import issue_token; print(issue_token('u1'))"], cwd=ROOT / "src",
                       capture_output=True, text=True, env={**ENV, "AUTH_SECRET": CHECK_SECRET})
    return r.stdout.strip()


RETRIEVER_PROBE = """
import sys
sys.path.insert(0, "src")
from app.rag import get_retriever
r = get_retriever()
fb = getattr(r, "fallback", "")
print(r.name, "|", fb or "sem fallback")
if fb:
    print("instale: pip install -r requirements-dev.lock -r requirements-hybrid.lock && pip install --no-deps -e . ;"
          " depois python scripts/fetch_models.py")
    sys.exit(1)
"""
CLOUD_CA = Path("/root/.ccr/ca-bundle.crt")  # proxy de saída das sessões da nuvem (claude.ai/code)


def cloud_build_args() -> list[str]:
    """Na nuvem, o build só alcança o PyPI pelo proxy do host e confiando no certificado dele."""
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    if not (proxy and CLOUD_CA.exists()):
        return []
    return ["--network", "host", "--secret", f"id=proxy_ca,src={CLOUD_CA}",
            "--build-arg", f"HTTPS_PROXY={proxy}", "--build-arg", f"HTTP_PROXY={os.getenv('HTTP_PROXY', proxy)}"]


def image_extras(requested: str) -> str:
    """auto = o extra que o buscador escolhido exige (o mesmo cálculo do Dockerfile): container e eval local iguais."""
    if requested != "auto":
        return requested
    sys.path.insert(0, str(ROOT / "scripts"))
    from fetch_models import needed_extras

    return needed_extras(ROOT / "data")


def docker_steps(extras: str = "", forced: bool = False) -> list[tuple[str, bool, float, str]]:
    build = ["docker", "build", "-q", *cloud_build_args(), "-t", IMAGE, "."]
    if forced:  # auto fica com o padrão do Dockerfile: mesma chave de cache do scale_smoke e do compose (1 build só)
        build[2:2] = ["--build-arg", f"EXTRAS={extras or 'none'}"]
    results = [step("docker build" + (f" ({extras})" if extras else ""), build)]
    if not results[-1][1]:
        return results
    probe = ("import importlib.util as u, sys; bad = [m for m in sys.argv[1:] if u.find_spec(m)]; "
             "print('presentes:', bad or 'nenhum'); sys.exit(1 if bad else 0)")
    forbidden = [m for m in FORBIDDEN_IN_IMAGE if m != EXTRA_MODULES.get(extras)]
    results.append(step("imagem sem dev/extras", ["docker", "run", "--rm", IMAGE, "python", "-c", probe,
                                                   *forbidden]))
    sh(["docker", "rm", "-f", IMAGE])
    port = free_port()
    # O eval manda dezenas de requests/min como um só usuário; com o limite de produção (30/min) o próprio
    # rate limiter (correto) devolveria 429. O smoke sobe o container com limite alto.
    env = ["-e", "RATE_LIMIT_PER_MIN=1000", "-e", f"AUTH_SECRET={CHECK_SECRET}"]
    run = step("docker run", ["docker", "run", "-d", "--name", IMAGE, *env, "-p", f"{port}:8000", IMAGE])
    results.append(run)
    if not run[1]:
        return results
    try:
        t0 = time.perf_counter()
        health = wait_health(f"http://localhost:{port}/health")
        # o buscador do container é o pedido (sem fallback para BM25): o que o avaliador sobe é o que foi medido
        ok = bool(health) and health.get("data_files", 0) > 0 and not health.get("retriever_fallback")
        logs = "" if health else sh(["docker", "logs", IMAGE]).stdout[-2000:]
        detail = json.dumps(health) if health else f"sem resposta em 60 s: {logs}"
        results.append(("container /health com dados", ok, time.perf_counter() - t0, detail))
        if ok:
            # o token do eval é assinado com o mesmo segredo do container (senão 401)
            # os 10 oficiais pelo container (o eval inteiro já rodou em processo no "eval gate"): prova que a imagem
            # serve o MESMO produto (buscador, modelos, dados). Ensaio v5.4: 271 casos via HTTP = 373 s em série.
            results.append(step("eval via HTTP (oficiais)", [PY, "-m", "evals.run_evals", "--url",
                                                            f"http://localhost:{port}", "--split", "official",
                                                            "--out", str(ROOT / "var" / "check-eval-http.json")],
                                env={"AUTH_SECRET": CHECK_SECRET}))
            results.append(mcp_smoke(port))
    finally:
        sh(["docker", "rm", "-f", IMAGE])
    # mesma imagem, sem rede nenhuma: nada é baixado na subida e o modo offline fica pronto (/ready 200)
    results.append(step("container sem rede (--network none)", [PY, "scripts/smoke_network_none.py", "--image", IMAGE]))
    return results


# Marcas do domínio de EXEMPLO do kit: não podem sobrar no produto depois do pré-voo (Getnet v3: 3 textos da loja
# no índice de busca, 9 perguntas da loja no Recall@3, 6 rótulos da loja na calibração do juiz, tools da loja
# expostas ao LLM).
EXAMPLE_MARKS = ("example.com", '"faq-entrega"', '"faq-troca"', '"faq-horario"', '"cal-0')
EXAMPLE_TOOLS = {"lookup_record", "cancel_record", "refund_record"}


def domain_started() -> bool:
    d = ROOT / "src" / "app" / "domain"
    return (d / "challenge").is_dir() or (d / "challenge.py").exists()


def no_example_data() -> tuple[str, bool, float, str]:
    t0 = time.perf_counter()
    found = []
    for folder in ("data", "evals"):
        for path in sorted((ROOT / folder).rglob("*.json*")):
            if "results" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            found += [f"{path.relative_to(ROOT)}: {m}" for m in EXAMPLE_MARKS if m in text]
    r = sh([PY, "-c", "import sys; sys.path.insert(0, 'src'); from app.domain import challenge as c; "
                     "print(' '.join(sorted(c.TOOLS)))"])
    leftover = EXAMPLE_TOOLS & set(r.stdout.split())
    found += [f"tool da loja no domínio: {t}" for t in sorted(leftover)]
    return "sem dado de exemplo no produto", not found, time.perf_counter() - t0, "\n".join(found[:20])


def readme_has_no_placeholders() -> tuple[str, bool, float, str]:
    """Depois do pré-voo, nenhum `{{...}}` do modelo sobra no README nem na SPEC (o avaliador lê como desleixo)."""
    import re

    t0 = time.perf_counter()
    left = []
    for rel in ("README.md", "docs/SPEC.md"):
        path = ROOT / rel
        if path.exists():
            left += [f"{rel}: {m}" for m in re.findall(r"\{\{[^}]{0,60}\}\}", path.read_text(encoding="utf-8"))]
    return "README e SPEC sem marcador do modelo", not left, time.perf_counter() - t0, "; ".join(left[:8])


def commit_titles_clean(root: Path = ROOT) -> tuple[str, bool, float, str]:
    """Nenhum título de commit com `{{` ou `}}` (pós-morte V5, N9: o título `{{N}}` de um commit da maestra foi para a
    linha do tempo do README como marcador de modelo e a CI do último commit ficou vermelha)."""
    t0 = time.perf_counter()
    r = subprocess.run(["git", "log", "--format=%h %s"], cwd=root, check=False, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    bad = [line for line in r.stdout.splitlines() if "{{" in line or "}}" in line]
    return "títulos de commit sem marcador {{ }}", not bad, time.perf_counter() - t0, \
        ("reescreva o título (git commit --amend / rebase) antes do push: " + "; ".join(bad[:5])) if bad else ""


def cited_tests_pass(junit: Path) -> tuple[str, bool, float, str]:
    """Todo `tests/x.py::teste` citado no README existe e passou nesta rodada (Getnet v3: 12 de 42 falhavam)."""
    import re
    import xml.etree.ElementTree as ET

    t0 = time.perf_counter()
    if not junit.exists():
        return "provas do README passam", False, 0.0, "pytest não gerou o relatório junit"
    status: dict[str, bool] = {}
    for tc in ET.parse(junit).iter("testcase"):
        key = f"{tc.get('classname', '').split('.')[-1]}::{tc.get('name', '').split('[')[0]}"
        bad = tc.find("failure") is not None or tc.find("error") is not None
        status[key] = status.get(key, True) and not bad
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    cited = sorted(set(re.findall(r"tests/(test_\w+)\.py::(\w+)", readme)))
    bad = [f"{f}::{t} ({'falha' if f'{f}::{t}' in status else 'não existe'})" for f, t in cited
           if not status.get(f"{f}::{t}", False)]
    return "provas do README passam", not bad, time.perf_counter() - t0, \
        f"{len(cited)} citados; com problema: " + ("; ".join(bad) or "nenhum")


LATENCY_KEYS = {"p50_ms", "p95_ms"}  # só a latência varia entre rodadas offline


def committed_eval_is_current(fresh: Path) -> tuple[str, bool, float, str]:
    """O evals/results/latest.json commitado é o que o código ATUAL mede (offline é determinístico)."""
    t0 = time.perf_counter()
    committed = ROOT / "evals" / "results" / "latest.json"
    if not committed.exists():
        return "resultado commitado = código atual", True, 0.0, "sem resultado commitado ainda"
    if not fresh.exists():
        return "resultado commitado = código atual", False, 0.0, "o eval gate não gravou a medida fresca"
    a, b = (json.loads(p.read_text(encoding="utf-8")) for p in (committed, fresh))

    def strip(report: dict) -> dict:
        return {split: {k: v for k, v in m.items() if k not in LATENCY_KEYS}
                for split, m in report.get("metrics", {}).items()}

    diff = [f"{split}.{k}: commitado {strip(a)[split].get(k)} × agora {v}"
            for split, m in strip(b).items() for k, v in m.items() if strip(a).get(split, {}).get(k) != v]
    if a.get("coverage_min_score") != b.get("coverage_min_score"):
        diff.insert(0, f"limiar: commitado {a.get('coverage_min_score')} × agora {b.get('coverage_min_score')}")
    return "resultado commitado = código atual", not diff, time.perf_counter() - t0, \
        ("rode `make readme` e commite evals/results com o README. " + "; ".join(diff[:8])) if diff else ""


# Getnet v4 (01/11/2026): a venv tinha o pacote `app` instalado em modo editável apontando para o repo da v3; o ingest
# gravou o corpus no repo errado e os testes passaram contra o código antigo. O check recusa antes de tudo.
VENV_PROBE = (
    "import sys, pathlib, app; root = pathlib.Path(sys.argv[1]).resolve(); src = pathlib.Path(app.__file__).resolve(); "
    "ok = root in src.parents; print('app importado de', src); "
    "ok or print('a venv aponta para OUTRO repo: rode `pip install -e .` neste diretório'); sys.exit(0 if ok else 1)"
)


def write_verify_report(results: list, args) -> None:
    """reports/verify.md: o que o check provou, com data e commit. O avaliador da V4 não roda nada; lê isto."""
    import datetime

    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                         check=False).stdout.strip() or "sem git"
    modo = "docker" + (" + réplicas" if getattr(args, "scale", False) else "") if args.docker else "sem docker"
    ok = all(r[1] for r in results)
    lines = [f"# Verificação (`scripts/check.py`, {modo})", "",
             f"Commit `{sha}`, {datetime.datetime.now(datetime.UTC):%d/%m/%Y %H:%M UTC}. Resultado: "
             f"**{'VERDE' if ok else 'VERMELHO'}**.", "", "| etapa | resultado | s |", "|---|---|---:|"]
    lines += [f"| {n} | {'PASS' if o else 'FAIL'} | {sec:.1f} |" for n, o, sec, _ in results]
    out = ROOT / "reports" / "verify.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # console cp1252 do Windows quebra acentos
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--docker", action="store_true", help="inclui build e smoke do container")
    ap.add_argument("--extras", default="auto", choices=["auto", "", "hybrid"],
                    help="extra embutido na imagem (auto = o que o buscador escolhido exige)")
    ap.add_argument("--scale", action="store_true",
                    help="+ teste de réplicas: 2 cópias da api atrás de um balanceador (scripts/scale_smoke.py)")
    ap.add_argument("--warm-image", action="store_true",
                    help="só o build da imagem (2º plano no T+12): dependências e modelos ficam no cache do docker")
    args = ap.parse_args()
    if args.warm_image:  # build frio com o buscador do kit ~4 min (pip + modelos); depois, só dados/código: segundos
        extras = image_extras(args.extras)
        build = ["docker", "build", "-q", *cloud_build_args(), "-t", IMAGE, "."]
        if args.extras != "auto":
            build[2:2] = ["--build-arg", f"EXTRAS={extras or 'none'}"]
        name, ok, secs, detail = step(f"docker build ({extras or 'enxuta'})", build)
        print(f"{name}: {'OK' if ok else 'FALHOU'} em {secs:.0f} s" + ("" if ok else f"\n{detail}"))
        return 0 if ok else 1

    junit = ROOT / "var" / "check-junit.xml"
    junit.parent.mkdir(exist_ok=True)
    results = [
        step("venv aponta para este repo", [PY, "-c", VENV_PROBE, str(ROOT)]),
        step("ruff", [PY, "-m", "ruff", "check", "."]),
        # ensaio de 03/11: a tentativa instalou só [dev] (sem fastembed) e mediu tudo com o BM25 do fallback, enquanto
        # CI e docker serviam denso + cross: evidência commitada de outro produto (oficiais 33% × 83% no CI)
        step("buscador = o configurado (sem fallback)", [PY, "-c", RETRIEVER_PROBE]),
        step("pytest", [PY, "-m", "pytest", "-q", f"--junitxml={junit}", *pytest_workers()]),
        cited_tests_pass(junit),
        # o gate grava num arquivo à parte: evals/results/ só muda quando alguém decide commitar a medida
        step("eval gate", [PY, "-m", "evals.run_evals", "--out", str(ROOT / "var" / "check-eval.json")]),
        step("README ⇔ evidência commitada", [PY, "scripts/fill_readme.py", "--check"]),
    ]
    results.append(committed_eval_is_current(ROOT / "var" / "check-eval.json"))
    results.append(commit_titles_clean())
    if domain_started():
        results.append(no_example_data())
        results.append(readme_has_no_placeholders())
    if args.docker:
        results += docker_steps(image_extras(args.extras), forced=args.extras != "auto")
    if args.scale:
        results.append(step("réplicas (conversa, caso único, queda)", [PY, "scripts/scale_smoke.py"]))

    failed = [r for r in results if not r[1]]
    for name, _ok, _, out in failed:
        print(f"\n=== {name} FALHOU ===\n{out[-3000:]}")
    print("\n| etapa | resultado | s |\n|---|---|---:|")
    for name, ok, secs, _ in results:
        print(f"| {name} | {'PASS' if ok else 'FAIL'} | {secs:.1f} |")
    print(f"\nCHECK {'VERDE' if not failed else 'VERMELHO'}")
    write_verify_report(results, args)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
