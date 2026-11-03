#!/usr/bin/env bash
# Vídeo legendado do walkthrough (sem narração), tudo na nuvem: respostas reais + números commitados → MP4.
# Getnet v4 (01/11/2026): 1 min de captura (US$ ~0,10), 3 min de gravação em tempo real, 10 s de ffmpeg; 1,4 MB.
# Requer: chave do LLM (captura), Playwright + Chromium (pré-instalados na nuvem), ffmpeg.
# Uso: scripts/video/make_video.sh            # docs/video/demo.json + docs/video/walkthrough.mp4
#      SKIP_CAPTURE=1 scripts/video/make_video.sh   # regrava com o demo.json já commitado
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
PY="${PY:-python}"
mkdir -p var/video_raw docs/video
[[ "${SKIP_CAPTURE:-0}" == "1" ]] || "$PY" scripts/video/capture_demo.py docs/video/demo.json
"$PY" scripts/video/make_slides.py var/slides.html
rm -f var/video_raw/*.webm
NODE_PATH="$(npm root -g)" node scripts/video/record.js "$ROOT/var/slides.html" "$ROOT/var/video_raw"
ffmpeg -y -loglevel error -i var/video_raw/*.webm -c:v libx264 -preset veryfast -crf 28 -pix_fmt yuv420p \
  -movflags +faststart docs/video/walkthrough.mp4
ffprobe -v error -show_entries format=duration -of csv=p=0 docs/video/walkthrough.mp4 | xargs printf "OK: docs/video/walkthrough.mp4 (%.0f s)\n"
