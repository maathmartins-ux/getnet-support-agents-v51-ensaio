#!/usr/bin/env bash
# Eval ao vivo por split + juiz + FAILURE_MODES + README (Linux/macOS/Git Bash). Mesmo comportamento de live_eval.ps1.
#
# Uso:
#   scripts/live_eval.sh --max-usd 24        # medido com 11 splits (official/memory repeat 3): conversa ~11 + juiz ~6,5
#   scripts/live_eval.sh --splits official,replan --workers 4 --repeat 1   # padrão 3 (pass^3); 1 = smoke
#   scripts/live_eval.sh --dry-run            # mostra splits e teto, sem gastar
#
# - Lê o .env do projeto SEM imprimir valores (a chave nunca aparece no console nem no log).
# - O teto vale para a rodada inteira: 65% dividido entre os splits (num processo só), 35% para o juiz.
# - Sem chave: run_evals sai com código 2 e mensagem clara; o script para sem traceback.
set -euo pipefail

SPLITS="" MAX_USD="24" WORKERS="8" REPEAT="3" NO_JUDGE=0 DRY=0  # repeat 3: pass^3 (custo ~3x; --repeat 1 = smoke)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --splits) SPLITS="$2"; shift 2 ;;
    --max-usd) MAX_USD="$2"; shift 2 ;;
    --workers) WORKERS="$2"; shift 2 ;;
    --repeat) REPEAT="$2"; shift 2 ;;
    --no-judge) NO_JUDGE=1; shift ;;
    --dry-run) DRY=1; shift ;;
    *) echo "opção desconhecida: $1" >&2; exit 64 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# LIVE_EVAL_PY: intérprete explícito (a CI Linux não tem .venv; sem ele o passo quebra na CI)
PY="${LIVE_EVAL_PY:-$ROOT/.venv/bin/python}"
[[ -x "$PY" ]] || PY="$ROOT/.venv/Scripts/python.exe"  # Git Bash no Windows
[[ -x "$PY" ]] || { echo "Falta a venv em $ROOT/.venv ou LIVE_EVAL_PY (references/brief-de-fork.md, seção Ambiente)."; exit 1; }

if [[ -f .env ]]; then  # exporta KEY=VALUE sem ecoar nada
  while IFS='=' read -r key value; do
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] && export "$key=${value%$'\r'}"
  done < <(grep -E '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=' .env | sed -E 's/^[[:space:]]+//')
fi
export PYTHONIOENCODING=utf-8
# Carga do eval, não do produto: N conversas ao mesmo tempo numa CPU com o buscador denso + cross deixam cada agente
# mais lento que em produção. Medido: 12 simultâneas com o supervisor LLM em todo turno levaram passos além de 60 s e
# o caso ia ao humano por node_timeout (splits partial e parallel inteiros). O eval roda com 8 simultâneas e teto de
# 90 s por agente; o produto segue com os seus 60 s (NODE_TIMEOUT_S no ambiente vence os dois).
export LIVE_MAX_CONCURRENT="${LIVE_MAX_CONCURRENT:-8}"
export NODE_TIMEOUT_S="${NODE_TIMEOUT_S:-90}"
FREE_GB="$("$PY" -c 'import shutil,sys; print(int(shutil.disk_usage(sys.argv[1]).free/1e9))' "$ROOT")"
MIN_GB="${LIVE_EVAL_MIN_FREE_GB:-5}"  # os testes do script zeram (o disco do CI não é o da tentativa)
if (( DRY == 0 && FREE_GB < MIN_GB )); then  # disco cheio no meio da bateria derruba o sqlite
  echo "Disco com ${FREE_GB} GB livres (mínimo ${MIN_GB}). Libere antes: rm -rf /tmp/eval-* e caches." >&2; exit 1
fi
# Buscador: a evidência ao vivo tem de ser do MESMO produto que o CI e o docker servem (sem fastembed, a bateria
# roda no BM25 do fallback e o CI, no denso + cross, discorda dos resultados).
if (( DRY == 0 )) && [[ "${LIVE_EVAL_ALLOW_FALLBACK:-0}" != "1" ]]; then
  FB="$("$PY" -c "import sys; sys.path.insert(0, 'src'); from app.rag import get_retriever; print(getattr(get_retriever(), 'fallback', '') or '')" 2>/dev/null | tail -1)"
  if [[ -n "$FB" ]]; then
    echo "Buscador em fallback ($FB): instale requirements-hybrid.lock e rode scripts/fetch_models.py antes." >&2; exit 1
  fi
fi
# Memória: cada processo com o buscador do kit carrega o e5-large + cross (~3 GB). Medido: eval aquecido + check +
# ablação + rodada 1 juntos = OOM no meio da bateria (3 de 12 splits salvos, 8 min perdidos). Espere os outros acabarem.
MIN_RAM="${LIVE_EVAL_MIN_RAM_GB:-6}"
AVAIL_GB="$(awk '/^MemAvailable:/ {print int($2/1048576)}' /proc/meminfo 2>/dev/null || echo 99)"
if (( DRY == 0 && ${AVAIL_GB:-99} < MIN_RAM )); then
  echo "Memória livre ${AVAIL_GB} GB (mínimo ${MIN_RAM}): outro processo pesado está rodando (eval aquecido, check," >&2
  echo "ablação, build da imagem). Espere terminar (ps -eo rss,args --sort=-rss | head) e rode de novo." >&2; exit 1
fi

if [[ -z "$SPLITS" ]]; then  # todos os splits presentes nos casos, na ordem em que aparecem
  SPLITS="$("$PY" -c "import json,pathlib; s=[]; [s.append(c['split']) for p in ['evals/cases.jsonl', *sorted(map(str, pathlib.Path('evals').glob('cases.d/*.jsonl'))), 'evals/heldout_blind.jsonl', *sorted(map(str, pathlib.Path('evals').glob('heldout_blind.d/*.jsonl')))] if pathlib.Path(p).exists() for c in map(json.loads, filter(str.strip, open(p, encoding='utf-8'))) if c['split'] not in s]; print(','.join(s))")"
fi
IFS=',' read -r -a LIST <<< "$SPLITS"
CLEAN=()
for s in "${LIST[@]}"; do s="${s// /}"; [[ -n "$s" ]] && CLEAN+=("$s"); done

if [[ $DRY -eq 1 ]]; then
  JUDGE=$([[ $NO_JUDGE -eq 1 ]] && echo False || echo True)
  echo "DRYRUN splits=$(IFS='|'; echo "${CLEAN[*]}") teto=$MAX_USD workers=$WORKERS repeat=$REPEAT juiz=$JUDGE processos=1"
  exit 0
fi

# Com um teto único em fila, cada split herda o que sobrou do anterior: os últimos abortam por teto (e o aborto
# sobrescrevia um resultado completo) e o juiz fica sem nada. Por isso cada split tem a sua cota e o juiz a dele.
# Custo medido por split (repeat 3, Sonnet): official 0,85 · replan 0,88 · parallel 0,72 · approval 0,59 · memory
# 1,46 · juiz (90 respostas, Opus) 1,16 → ~6,1.
# Os splits rodam ao mesmo tempo num processo SÓ (run_evals --splits). Com o buscador denso cada processo carrega
# e5-large + cross-encoder (GBs de RAM); um processo por split (5 ou mais) estourava a memória da máquina. Num
# processo, os modelos carregam uma vez e as threads dos splits os compartilham.
# Divisão do teto pela medida da rodada completa: conversa US$ 10,45 e juiz ~US$ 6 (352 vereditos, Opus) → 65% / 35%
splits_usd="$("$PY" -c "print(round(float('$MAX_USD') * 0.65, 4))")"
share="$("$PY" -c "print(round(float('$MAX_USD') * 0.65 / ${#CLEAN[@]}, 4))")"
judge_usd="$("$PY" -c "print(round(float('$MAX_USD') * 0.35, 4))")"
mkdir -p var
JOINED="$(IFS=','; echo "${CLEAN[*]}")"
echo "== splits $JOINED num processo (cota US\$ $share cada) → var/live_splits.log"
set +e
# Cota proporcional a casos × repeat (no run_evals), repeat 3 só em official e memory (pass^3), o resto 1, e o juiz
# julga cada split ao terminar no MESMO processo (corte no fim não perde o juiz).
JUDGE_FLAGS=(); [[ $NO_JUDGE -eq 0 ]] && JUDGE_FLAGS=(--judge --judge-max-usd "$judge_usd")
REPEAT_BY=(); [[ "$REPEAT" -gt 1 ]] && REPEAT_BY=(--repeat-by "official=$REPEAT,memory=$REPEAT") && REPEAT=1
"$PY" -m evals.run_evals --live --splits "$JOINED" --max-usd "$splits_usd" --workers "$WORKERS" --repeat "$REPEAT" \
  "${REPEAT_BY[@]}" "${JUDGE_FLAGS[@]}" > var/live_splits.log 2>&1
code=$?
set -e
if [[ $code -eq 2 ]]; then echo "Sem credencial: na nuvem, APP_ANTHROPIC_API_KEY nas variáveis do ambiente; no PC, ANTHROPIC_API_KEY no .env."; exit 2; fi
failed=0
for split in "${CLEAN[@]}"; do
  status="$("$PY" -c "import json; print(json.load(open('evals/results/live_$split.json', encoding='utf-8')).get('status'))" 2>/dev/null || echo ausente)"
  echo "   $split: $status"
  [[ "$status" == "complete" ]] || failed=1
done
if [[ $code -ne 0 ]]; then  # 3 = algum split abortado (teto) ou DEGRADADO: o arquivo bom antigo dele, se houver, ficou intacto
  echo "   saída $code (split abortado, degradado ou quebrado) — veja var/live_splits.log; a rodada ruim NÃO substituiu o resultado anterior"
  failed=1
fi
[[ $failed -eq 0 ]] || echo "ATENÇÃO: split sem status complete (teto curto?). Rode de novo só ele: python -m evals.run_evals --live --split <s> --max-usd 2 --repeat $REPEAT"

# o juiz já rodou por split no mesmo processo (--judge); judge.json traz um bloco por split
LLM_PROVIDER=offline "$PY" -m evals.run_evals > /dev/null  # relatório offline (bloco principal do README e gate)
# análise de erros da bateria que acabou de rodar (gerada, nunca à mão: o fill_readme --check compara); commite
# docs/FAILURE_MODES.md junto com evals/results/
"$PY" -m evals.failure_modes || echo "   docs/FAILURE_MODES.md não gerado (motivo acima)"
"$PY" scripts/fill_readme.py
