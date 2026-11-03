"""Mensagem de entrega ao recrutador, gerada dos resultados commitados: o bom e o ruim lado a lado.

Uso: python scripts/delivery_message.py --repo https://github.com/<dono>/<repo> [--video URL] [--out docs/ENTREGA.md]

A mensagem tem três partes fixas, nesta ordem, e nenhuma pode ser apagada:
1. o que o sistema faz e onde rodar;
2. o placar inteiro (scripts/scorecard.py), com as métricas abaixo da referência escritas por extenso;
3. a procedência do kit (docs/PROCEDENCIA.md) e os minutos do relógio.
Destacar só os números bons e omitir os ruins, que estão no próprio README, custa nota de julgamento: a mensagem
sai com os dois ou não sai.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import scorecard  # noqa: E402
from scripts.timesheet import commits, scaffold_time, tag_time  # noqa: E402


def minutes(root: Path = ROOT) -> int | None:
    """Do scaffold (ou clock-start) ao último commit QUE JÁ EXISTE. Ensaio de 03/11: a mensagem gerada no T+41 dizia
    "41 min do primeiro ao último commit" e o relógio fechou no T+47; o texto que vai ao dono sai do `make final`
    (var/ENTREGA_final.md), DEPOIS do último commit."""
    rows = commits(root)
    if not rows:
        return None
    start = tag_time("clock-start", root) or scaffold_time(rows) or rows[0]["t"]
    end = tag_time("clock-end", root) or rows[-1]["t"]
    return round((end - start).total_seconds() / 60)


def head_sha(root: Path = ROOT) -> str:
    import subprocess

    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True)
    return out.stdout.strip()


def render(repo: str, video: str | None, results: Path, mins: int | None) -> str:
    # kit v5.5 (perfil Skywalker): só as medidas que o enunciado pede (scorecard.HEADLINE); as de diagnóstico do kit
    # ficam em docs/RESULTS.md. Os ruins entre ELAS continuam listados (regra do dono: nada de esconder número ruim).
    table = [r for r in scorecard.rows(results) if r["key"] in scorecard.HEADLINE]
    good = [r for r in table if r["status"] == "atinge"]
    weak = [r for r in table if r["status"] not in ("atinge", "diagnóstico")]
    lines = [
        "Olá! Segue a minha entrega do desafio.",
        "",
        f"Repositório: {repo}",
        *([f"Vídeo: {video}"] if video else []),
        "Como avaliar em 5 minutos: a seção 0 do README; as respostas reais dos cenários oficiais estão em "
        "docs/DEMO.md e a linha do tempo em docs/TIMESHEET.md.",
        "",
        "Resultados medidos (todos gerados de evals/results/, no README):",
        *[f"- {r['label']}: {r['shown']} (referência {r['goal']})" for r in good],
        "",
        "Onde ainda está abaixo da referência, ou não foi medido (as limitações, com o efeito e o que faltaria, estão "
        "na seção de limitações do README):",
        *([f"- {r['label']}: {r['shown']} (referência {r['goal']})" for r in weak] or ["- nenhuma métrica"]),
        "",
        "Procedência: o primeiro commit traz um kit próprio, que evoluiu a partir das correções das minhas entregas "
        "anteriores deste desafio. O que veio do kit, o que foi feito no relógio e como comparar pela primeira "
        "entrega estão em docs/PROCEDENCIA.md."
        + (f" Relógio: {mins} min do commit de scaffold ao commit {head_sha() or 'atual'}." if mins else ""),
        "",
        "Obrigado!",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--video")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "ENTREGA.md")
    ap.add_argument("--results", type=Path, default=ROOT / "evals" / "results")
    args = ap.parse_args(argv)
    text = render(args.repo, args.video, args.results, minutes())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
