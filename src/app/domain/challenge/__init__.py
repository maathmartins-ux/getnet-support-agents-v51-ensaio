"""Domínio do desafio (sessão principal): junta flow + tools e guarda o limiar calibrado.

MIN_SCORE sai de `python -m evals.run_evals --calibrate-gate` NO CORPUS DO DESAFIO; troque aqui,
nunca no motor nem no domínio de exemplo (v3: trocar o padrão do kit quebrou 14 testes).
"""
from __future__ import annotations

from pathlib import Path

from .flow import *  # noqa: F403
from .tools import *  # noqa: F403

# --- portão "sem fonte, sem afirmação" ----------------------------------------------------------------------
# BM25 bruto abaixo disso = sem fonte. O valor do desafio sai de `run_evals --calibrate-gate` e vai para o
# challenge.py (ou COVERAGE_MIN_SCORE no compose). Trocar o padrão do KIT quebrou 14 testes.
MIN_SCORE = 0.5
# Portão pela nota do cross-encoder (bge-reranker-v2-m3): menor limiar que recusa >= 85% dos sem fonte no gold.
# run_evals --calibrate-rerank-gate (04/11/2026): responde 100% dos com fonte, recusa 91% dos sem fonte (n=48/22)
MIN_RERANK = -4.986

# --- prompts ------------------------------------------------------------------------------------------------
# None = prompts do kit (src/app/prompts). O pré-voo aponta o challenge para src/app/domain/challenge_prompts.
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "challenge_prompts"

