"""A imagem sobe SEM rede nenhuma (`docker run --network none`) e responde /health e /ready.

Prova que o container não baixa nada na subida (modelo, tokenizer, índice) e que, sem chave, o modo offline
declarado deixa o serviço pronto. Sem rede não há porta publicada: as chamadas rodam dentro do container
(`docker exec`, Python da própria imagem).

Uso: python scripts/smoke_network_none.py [--image app-check]   (sai 1 se falhar; chamado pelo check --docker)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

PROBE = ("import json, sys, urllib.request, urllib.error\n"
         "out = {}\n"
         "for path in ('/health', '/ready'):\n"
         "    try:\n"
         "        with urllib.request.urlopen('http://127.0.0.1:8000' + path, timeout=3) as r:\n"
         "            out[path] = [r.status, json.loads(r.read())]\n"
         "    except urllib.error.HTTPError as e:\n"
         "        out[path] = [e.code, json.loads(e.read() or b'{}')]\n"
         "print(json.dumps(out))\n")


def docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          check=False)


def smoke(image: str, timeout_s: float | None = None) -> tuple[bool, str]:
    # mesma espera do check (CHECK_HEALTH_TIMEOUT_S): a 1ª subida depois do build lê o disco frio
    timeout_s = float(os.getenv("CHECK_HEALTH_TIMEOUT_S", "180")) if timeout_s is None else timeout_s
    t0 = time.time()
    name = f"{image.replace(':', '-').replace('/', '-')}-netnone"
    docker("rm", "-f", name)
    run = docker("run", "-d", "--network", "none", "--name", name, "-e", "LLM_PROVIDER=offline", image)
    if run.returncode != 0:
        return False, f"docker run falhou: {run.stderr.strip()[-500:]}"
    try:
        deadline, last = time.time() + timeout_s, ""
        while time.time() < deadline:
            r = docker("exec", name, "python", "-c", PROBE)
            if r.returncode == 0:
                out = json.loads(r.stdout)
                health, ready = out["/health"], out["/ready"]
                ok = health[0] == 200 and health[1].get("data_files", 0) > 0 and ready[0] == 200
                net = docker("inspect", "-f", "{{.HostConfig.NetworkMode}}", name).stdout.strip()
                return ok and net == "none", json.dumps({"network": net, "health": health[0],
                                                         "ready": ready, "data_files": health[1].get("data_files"),
                                                         "subiu_em_s": round(time.time() - t0, 1)})
            last = (r.stderr or r.stdout).strip()[-300:]
            time.sleep(1)
        return False, f"sem resposta em {timeout_s:.0f} s: {last}\n{docker('logs', name).stderr[-1500:]}"
    finally:
        docker("rm", "-f", name)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default="app-check")
    args = ap.parse_args()
    ok, detail = smoke(args.image)
    print(("OK " if ok else "FALHOU ") + detail)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
