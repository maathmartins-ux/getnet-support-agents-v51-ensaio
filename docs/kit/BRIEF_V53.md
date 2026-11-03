# Brief comum das frentes do kit v5.3 (02/11/2026)

Leia antes: docs/kit/POSMORTEM_V5.md (erros N1–N10, T1–T7), docs/kit/estudo/skywalker.md e
docs/kit/estudo/nelsondell.md (top-10 de cada). As referências NÃO têm licença: use só as ideias, nunca código ou
texto delas. Domínio de ensaio mais recente (só leitura): /home/user/v5-main0 (repositório da V5, Getnet).

Regras: só mexa nos arquivos da sua frente (tabela abaixo); motor genérico (nada de Getnet no motor fora de
src/app/domain/ e de fixtures); cada mudança com teste; `python -m pytest -q` e `ruff check .` verdes na sua
worktree (venv: /home/user/venv51/bin/python, PYTHONPATH=src:.); commit por mudança com o porquê medido;
registre o que fez e o que NÃO provou em docs/kit/changelog.d/<frente>.md. Sem chamada ao vivo da API, salvo a
frente que tiver teto explícito abaixo. Commits terminam com:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011qmqFpm1AijAdQEQ7HP3Te

Contratos entre frentes (não mude sem avisar a maestra):
- Caso oficial: `expect.facts` = lista de regex (sem caixa) que a resposta TEM de conter; `expect.entities` = nomes
  de produto citados no cenário (ex.: ["Get Clássica", "Get Smart"]). E53 mede, P53 testa o corpus com eles.
- Router → contexto: `ctx.facts["standalone"]` = a pergunta do turno reescrita completa e autônoma (resolve "e a
  outra?" com o histórico), no idioma do cliente; vazio quando a reescrita for recusada. R53 produz; K53 usa como
  base da busca quando existir.
- Resposta do Knowledge com três estados: `AgentResult.status` "ok" (completa), "partial" (responde o que a fonte
  cobre e diz o que falta; NÃO escala por si), "insufficient" (nada coberto). K53 produz; R53 trata no supervisor.

| frente | dono de |
|---|---|
| K53 conhecimento | src/app/agents.py (faq_agent e helpers de busca), src/app/rag.py, src/app/prompts/faq.md, src/app/schemas.py (só o status "partial"), src/app/config.py (padrões do buscador), tests/test_k53_*.py |
| R53 roteador/memória/supervisor | src/app/router.py, src/app/supervisor.py, src/app/memory.py, src/app/followup.py, src/app/prompts/router.md e supervisor.md, tests/test_r53_*.py |
| E53 avaliação e README | evals/*, scripts/fill_readme.py, scripts/scorecard.py, scripts/check.py, scripts/delivery_message.py, scripts/label_page.py, scripts/templates/*, README.md (modelo), tests/test_e53_*.py |
| P53 roteiro e garantias | docs/kit/* (PLAYBOOK, PROMPTS, V5_PROMPT_M, LICOES), scripts/preflight.py, scripts/cloud_probe.py, scripts/official_check.py (novo), tests/test_p53_*.py, tests/fixtures |
