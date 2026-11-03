"""Feedback 👎 → candidato a caso de teste, com a evidência e a versão das instruções daquela resposta.

👍/👎 e fila de revisão ligados a cada geração fecham o ciclo produção → dataset. O candidato NÃO entra em split nenhum
sozinho: `python -m evals.candidates --review` lista e
`--accept <id> --split <s>` o leva, revisado por uma pessoa, para `evals/cases.d/<s>.jsonl`. O arquivo de candidatos
fica em `var/` (fora do git): texto de cliente só vira dado do repositório depois da revisão. Tudo já mascarado (as
mensagens e a evidência são gravadas mascaradas).
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .config import candidates_file

_LOCK = threading.Lock()


def read_all(path: Path | None = None) -> list[dict]:
    path = path or candidates_file()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError:  # linha truncada (queda no meio de uma escrita antiga): pula, não derruba o /feedback
            continue
    return out


def write_all(rows: list[dict], path: Path | None = None) -> None:
    """Grava num temporário e troca de uma vez (os.replace é atômico): queda no meio não deixa arquivo pela metade."""
    path = path or candidates_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    os.replace(tmp, path)


def add_from_feedback(trace_id: str, user_id: str, comment: str | None, snapshot: dict) -> dict:
    """Grava (ou atualiza) o candidato do atendimento `trace_id`; devolve a linha."""
    row = {"id": f"cand-{trace_id}", "trace_id": trace_id, "status": "pending", "ts": round(time.time(), 1),
           "user_id": user_id, "intent": snapshot.get("intent"), "question": snapshot.get("question", ""),
           "answer": snapshot.get("answer", ""), "evidence": snapshot.get("evidence", []),
           "prompt_versions": snapshot.get("prompt_versions", {}), "comment": (comment or "")[:500]}
    with _LOCK:
        rows = [r for r in read_all() if r.get("id") != row["id"]]
        write_all([*rows, row])
    return row
