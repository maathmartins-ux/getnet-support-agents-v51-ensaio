#!/usr/bin/env bash
# Último commit da tentativa: README (e ESTADO.md) gerados por fill_readme, SOZINHOS no commit, e push.
#
# Getnet v4 (01/11/2026): dois commits misturaram README com evals/results e a CI ficou vermelha ("linha do tempo
# com 36 commits, o git tem 37"): a linha do tempo do README conta os commits, então o README precisa ser o ÚLTIMO
# e o único arquivo do último commit. Qualquer commit depois disto exige rodar este script de novo.
#
# Uso: scripts/final.sh            # recusa se houver outra mudança sem commit
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PY:-python}"
dirty="$(git status --porcelain --untracked-files=no | grep -v -E ' (README\.md|ESTADO\.md)$' || true)"
if [[ -n "$dirty" ]]; then
  echo "Commite antes o que não é README/ESTADO (o README tem de ser o último commit):"; echo "$dirty"; exit 1
fi
"$PY" scripts/fill_readme.py
git add README.md
[[ -f ESTADO.md ]] && git add ESTADO.md
if git diff --cached --quiet; then echo "README já está em dia com o git log."; else
  git commit -q -m "readme: números e linha do tempo (fill_readme, último passo)"
fi
"$PY" scripts/fill_readme.py --check
git push -q origin HEAD
# A mensagem que vai ao dono sai DEPOIS do último commit (o relógio dela conta até ele); fora do git (não cria commit).
mkdir -p var
REPO_URL="$(git remote get-url origin 2>/dev/null | sed -E 's#^git@github.com:#https://github.com/#; s#\.git$##; s#https://[^@/]*@#https://#')"
"$PY" scripts/delivery_message.py --repo "${REPO_URL:-<url do repo>}" --out var/ENTREGA_final.md > /dev/null \
  && echo "Mensagem ao dono (relógio até o último commit): var/ENTREGA_final.md"
echo "OK: último commit $(git log -1 --format='%h %aI') enviado. Confira a CI na aba Actions."
