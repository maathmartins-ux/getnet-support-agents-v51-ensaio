"""docs/TIMESHEET.md: prova do relógio, gerada do git log (nunca à mão).

Uso: python scripts/timesheet.py [--out docs/TIMESHEET.md]

Relógio = da tag `clock-start` à tag `clock-end`; sem as tags, do 1º ao último commit. Commits depois de
`clock-end` aparecem marcados "pós-relógio": a autoria se confere pelos commits, então o que veio depois do relógio
fica declarado em vez de misturado. Mostra também a cadência: rajada de commits em poucos minutos sugere trabalho
pré-fabricado, então o relatório destaca a maior rajada.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str, cwd: Path = ROOT) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    return r.stdout.strip()


def commits(cwd: Path = ROOT) -> list[dict]:
    out = _git("log", "--reverse", "--no-merges", "--format=%H|%aI|%an|%s", cwd=cwd)
    rows = []
    for line in out.splitlines():
        sha, when, author, subject = line.split("|", 3)
        files = len(_git("show", "--name-only", "--format=", sha, cwd=cwd).splitlines())
        rows.append(
            {
                "sha": sha[:7],
                "full": sha,
                "t": datetime.fromisoformat(when),
                "author": author,
                "subject": subject,
                "files": files,
            }
        )
    return rows


def tag_time(name: str, cwd: Path = ROOT) -> datetime | None:
    iso = _git("log", "-1", "--format=%aI", name, cwd=cwd) if _git("tag", "--list", name, cwd=cwd) else ""
    return datetime.fromisoformat(iso) if iso else None


def scaffold_time(rows: list[dict]) -> datetime | None:
    """Hora do commit de scaffold do kit: o início do relógio quando a tag clock-start não existe."""
    return next((r["t"] for r in rows if str(r.get("subject", "")).startswith("chore: scaffold")), None)


def biggest_burst(rows: list[dict], minutes: int = 10) -> tuple[int, datetime | None]:
    best, start = 0, None
    for i, a in enumerate(rows):
        n = sum(1 for b in rows[i:] if (b["t"] - a["t"]).total_seconds() <= minutes * 60)
        if n > best:
            best, start = n, a["t"]
    return best, start


def render(rows: list[dict], t0: datetime | None, t1: datetime | None, source: str) -> str:
    if not rows:
        return "# Linha do tempo\n\nSem commits.\n"
    start = t0 or rows[0]["t"]
    end = t1 or rows[-1]["t"]
    inside = [r for r in rows if r["t"] <= end]
    after = [r for r in rows if r["t"] > end]
    burst, burst_at = biggest_burst(rows)
    out = [
        "# Linha do tempo (gerada do `git log`)",
        "",
        f"Relógio: **{(end - start).total_seconds() / 60:.0f} min** de {start:%d/%m/%Y %H:%M:%S} a {end:%H:%M:%S} "
        f"({source}; horário do commit, fuso {start.tzinfo}). "
        f"{len(inside)} commits dentro do relógio, {len(after)} depois (declarados abaixo).",
        f"Maior rajada: {burst} commits em até 10 min a partir de {burst_at:%H:%M:%S}." if burst_at else "",
        "",
        "| min | hora | autor | arquivos | commit | relógio |",
        "|---:|---|---|---:|---|---|",
    ]
    for r in rows:
        out.append(
            f"| {(r['t'] - start).total_seconds() / 60:.1f} | {r['t']:%H:%M:%S} | {r['author']} | {r['files']} | "
            f"`{r['sha']}` {r['subject'][:90]} | {'pós-relógio' if r['t'] > end else 'dentro'} |"
        )
    if after:
        out += ["", "Commits pós-relógio: não contam no tempo declarado e não entram no que foi medido no prazo."]
    return "\n".join(x for x in out if x is not None) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "TIMESHEET.md")
    args = ap.parse_args(argv)
    rows = commits()
    t0, t1 = tag_time("clock-start"), tag_time("clock-end")
    basis = "tags clock-start/clock-end" if t0 and t1 else "1º e último commit (sem tags)"
    if t0 is None:  # o proxy da nuvem derruba push de tag, e o repo pode ter commits anteriores ao relógio
        t0 = scaffold_time(rows)
        if t0 is not None:
            basis = "commit de scaffold ('chore: scaffold') ao " + ("clock-end" if t1 else "último commit")
    text = render(rows, t0, t1, basis)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"{args.out}: {len(rows)} commits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
