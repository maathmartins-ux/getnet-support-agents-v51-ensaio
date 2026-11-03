# Atalhos para Linux/CI. No Windows, rode os comandos python diretamente (ou scripts/live_eval.ps1).
.PHONY: check check-docker eval compare live judge readme up scale video final

check:
	python scripts/check.py

check-docker:
	python scripts/check.py --docker

# eval: o que roda a cada mudança (gate offline + ablação do replanejamento). A comparação de buscadores (8 min
# medidos num corpus real) é decisão à parte, tomada antes: `make compare`.
eval:
	python -m evals.run_evals
	python -m evals.run_evals --ablate-replan

compare:
	python -m evals.run_evals --compare-retrievers

live:
	python -m evals.run_evals --live --max-usd $${MAX_USD:-3} --workers 4

judge:
	LLM_PROVIDER=anthropic python -m evals.judge --max-usd $${MAX_USD:-1}

readme:  # só o README a partir dos resultados commitados (refazer o eval é `make eval`)
	python scripts/fill_readme.py

up:
	docker compose up -d --build

scale:
	python scripts/scale_smoke.py

video:
	scripts/video/make_video.sh

final:
	scripts/final.sh
