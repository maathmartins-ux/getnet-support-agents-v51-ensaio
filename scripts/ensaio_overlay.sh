#!/usr/bin/env bash
# Ensaio de motor: copia um repositório entregue (domínio, dados, casos) para uma pasta à parte e coloca por cima o
# motor deste kit (src/app/*.py, prompts do kit, evals/*.py, scripts/), mantendo domain/challenge*, data/ e os casos.
# Uso: scripts/ensaio_overlay.sh <repo_entregue> <destino> [<kit>]   (o original não é tocado; kit padrão = este)
set -euo pipefail
src="${1:?repo entregue}"; dst="${2:?destino}"; kit="${3:-$(cd "$(dirname "$0")/.." && pwd)}"
rm -rf "$dst" && cp -a "$src" "$dst" && rm -rf "$dst/.git" "$dst"/.pytest_cache "$dst"/.ruff_cache
cp "$kit"/src/app/*.py "$dst"/src/app/
cp "$kit"/src/app/domain/__init__.py "$kit"/src/app/domain/example.py "$dst"/src/app/domain/
cp -r "$kit"/src/app/prompts/. "$dst"/src/app/prompts/
cp "$kit"/evals/*.py "$dst"/evals/
cp -r "$kit"/scripts/. "$dst"/scripts/
find "$dst" -name __pycache__ -prune -exec rm -rf {} +
echo "motor de $kit sobre $src -> $dst"
