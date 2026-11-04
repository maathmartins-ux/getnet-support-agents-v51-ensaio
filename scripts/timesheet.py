"""docs/TIMESHEET.md: prova do relógio, gerada do git log (nunca à mão).

Uso: python scripts/timesheet.py [--clock-end <sha>] [--out docs/TIMESHEET.md]

Relógio = do início (tag `clock-start`; sem ela, o commit `chore: scaffold`; sem ele, o 1º commit) ao fim (o commit
de `--clock-end`; sem ele, a tag `clock-end`; sem ela, o último commit). `--clock-end` existe porque o proxy da nuvem
derruba o push de tag: sem a tag, o relógio terminava no último commit e "0 depois" saía por construção (rodada 10:
o TIMESHEET parou em 446 min e "0 depois" com 47 commits a mais no git). Cada commit sai com a sua situação:
"antes do relógio" (anterior ao início, ex.: o commit que cria o repositório), "dentro" ou "pós-relógio" (depois do
fim): a autoria se confere pelos commits, então o que veio fora do relógio fica declarado em vez de misturado.
Mostra também a cadência: rajada de commits em poucos minutos sugere trabalho pré-fabricado, então o relatório
destaca a maior rajada dentro do relógio.

Gerado pelo scripts/final.sh (antes do último commit, que só leva arquivos gerados); o `fill_readme.py --check` reprova
o arquivo com menos linhas de commit que o git log (tolera só esse último commit).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEFORE, INSIDE, AFTER = "antes do relógio", "dentro", "pós-relógio"


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


def commit_time(rev: str, cwd: Path = ROOT) -> tuple[str, datetime] | None:
    """(sha curto, hora do autor) do commit que `rev` nomeia (sha, tag ou ramo); None se não for um commit."""
    sha = _git("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", cwd=cwd)
    iso = _git("log", "-1", "--format=%aI", sha, cwd=cwd) if sha else ""
    return (sha[:7], datetime.fromisoformat(iso)) if iso else None


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


def situation(t: datetime, start: datetime, end: datetime) -> str:
    return BEFORE if t < start else AFTER if t > end else INSIDE


def render(rows: list[dict], t0: datetime | None, t1: datetime | None, source: str) -> str:
    if not rows:
        return "# Linha do tempo\n\nSem commits.\n"
    start = t0 or rows[0]["t"]
    end = t1 or rows[-1]["t"]
    where = [situation(r["t"], start, end) for r in rows]
    inside = [r for r, w in zip(rows, where, strict=True) if w == INSIDE]
    n_before, n_after = where.count(BEFORE), where.count(AFTER)
    burst, burst_at = biggest_burst(inside)  # rajada fora do relógio (o repositório, o pós-entrega) não diz nada
    out = [
        "# Linha do tempo (gerada do `git log`)",
        "",
        f"Relógio: **{(end - start).total_seconds() / 60:.0f} min** de {start:%d/%m/%Y %H:%M:%S} a {end:%H:%M:%S} "
        f"({source}; horário do commit, fuso {start.tzinfo}). "
        f"{len(inside)} commits dentro do relógio, {n_after} depois"
        + (f" e {n_before} antes" if n_before else "") + " (declarados abaixo).",
        f"Maior rajada: {burst} commits em até 10 min a partir de {burst_at:%H:%M:%S}." if burst_at else "",
        "",
        "| min | hora | autor | arquivos | commit | relógio |",
        "|---:|---|---|---:|---|---|",
    ]
    for r, w in zip(rows, where, strict=True):
        subject = r["subject"][:90].replace("|", "\\|")  # `|` no título abriria uma coluna
        out.append(
            f"| {(r['t'] - start).total_seconds() / 60:.1f} | {r['t']:%H:%M:%S} | {r['author']} | {r['files']} | "
            f"`{r['sha']}` {subject} | {w} |"
        )
    if n_before:
        out += ["", "Commits antes do relógio: anteriores ao início (o repositório antes do scaffold); não contam no "
                    "tempo declarado."]
    if n_after:
        out += ["", "Commits pós-relógio: não contam no tempo declarado e não entram no que foi medido no prazo."]
    return "\n".join(x for x in out if x is not None) + "\n"


def main(argv: list[str] | None = None) -> int:
    root = ROOT  # lido na chamada: o teste aponta para um repositório temporário
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=root / "docs" / "TIMESHEET.md")
    ap.add_argument("--clock-end", metavar="SHA",
                    help="commit que fecha o relógio (sha, tag ou ramo); o que vem depois sai como pós-relógio. "
                         "Vence a tag clock-end, que o proxy da nuvem não deixa subir")
    args = ap.parse_args(argv)
    rows = commits(root)
    t0 = tag_time("clock-start", root)
    if args.clock_end:
        found = commit_time(args.clock_end, root)
        if found is None:
            print(f"--clock-end {args.clock_end!r} não é um commit deste repositório.", file=sys.stderr)
            return 2
        end_sha, t1 = found
        end_name = f"ao commit {end_sha} (--clock-end)"
    else:
        t1, end_sha = tag_time("clock-end", root), None
        end_name = "à tag clock-end" if t1 else "ao último commit"
    if t0 is not None:
        start_name = "tag clock-start"
    else:  # o repo pode ter commits anteriores ao relógio (o que cria o repositório)
        t0 = scaffold_time(rows)
        start_name = "commit de scaffold ('chore: scaffold')" if t0 is not None else "1º commit"
    text = render(rows, t0, t1, f"{start_name} {end_name}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"{args.out}: {len(rows)} commits" + (f", relógio até {end_sha}" if end_sha else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
