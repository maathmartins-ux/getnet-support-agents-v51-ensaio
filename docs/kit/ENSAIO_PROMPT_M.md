# Prompt da sessão principal do ENSAIO (pronto para colar)

Copie TUDO dentro do bloco abaixo e cole na sessão principal (Opus) aberta no repositório `ensaio-kit-v37`,
pelo Chrome ([CHROME.md](CHROME.md) §3). Nada a preencher.

```text
ENSAIO GERAL (repositório descartável ensaio-kit-v37; ensaio REDUZIDO: só as frentes R e K, pare no T+30 depois do 1º `check.py --docker` verde; no passo 8 rode só `python -m evals.run_evals --live --split official --repeat 1 --max-usd 0.3`).

Você é a sessão principal (M) de uma tentativa cronometrada: menos de 60 min do primeiro ao último commit,
qualidade mirando 10 na régua abaixo, tratada como a última tentativa. Responda ao dono em português simples.

Enunciado (literal):
**Desafio — Sistema multiagente de atendimento sobre Pix**

Uma fintech fictícia, a **PagaJá**, atende clientes que usam Pix. Construa um sistema com pelo menos três
agentes que cooperam:

1. **Router**: ponto de entrada de toda mensagem; decide qual agente (ou sequência) atende e gerencia o
   fluxo de dados entre eles.
2. **Knowledge Agent**: responde dúvidas sobre o Pix com RAG sobre as páginas públicas do Pix no site do
   Banco Central (`https://www.bcb.gov.br/estabilidadefinanceira/pix` e páginas ligadas), e usa busca na web
   para perguntas gerais (clima, câmbio, notícias).
3. **Customer Support Agent**: responde sobre os dados do PRÓPRIO cliente da PagaJá com pelo menos duas
   ferramentas (ex.: extrato de Pix, limites, chaves cadastradas, contestação via MED com confirmação).

Exponha `POST /chat` com o corpo `{"message": "...", "user_id": "..."}` e resposta JSON útil. Entregue Docker,
estratégia de testes e um README que explique como construir, rodar e testar, a arquitetura, o fluxo de uma
mensagem, o RAG (ingestão → armazenamento → busca → geração) e como o LLM foi usado.

Bônus: 4º agente de escalonamento humano, guardrails, handoff quando não houver confiança, avaliação e
observabilidade. Grave um vídeo curto explicando a solução.

Cenários de exemplo (`user_id` = `cliente7`):
1. Qual o limite do Pix no período noturno?
2. What's the weather forecast in Recife tomorrow?
3. Quanto eu mandei de Pix ontem?
4. Como funciona o MED (Mecanismo Especial de Devolução)?
5. Fiz um Pix para a pessoa errada, o que eu faço?
6. What is the dollar exchange rate today?
7. Quais chaves Pix eu tenho cadastradas?
8. Can I schedule a Pix for next week?
9. Meu Pix não chegou e o dinheiro saiu da conta.
10. Quero aumentar meu limite noturno para R$ 5.000.

Régua de avaliação:
Business & Challenge Fit 8% (cenários oficiais via HTTP no container; multi-turno) · Agentic Reasoning & Orchestration 15% (supervisor que observa e replaneja; plano fixo por intent = faixa 7–8) · Context, Knowledge & RAG 10% (híbrido, Recall@K e MRR medidos, trechos literais) · Tool & Action Engineering 10% (JSON Schema, ação de escrita com confirmação, estado persistido) · Security & Identity 13% (user_id do token, rate limit, guardrails além de regex) · Memory, State & Resilience 8% (memória multi-turno persistida) · Human Oversight & Risk 7% (HITL real: fila persistida, operador responde, conversa retoma) · Evaluation & Quality 14% (golden set, splits, gate no CI, juiz LLM calibrado, casos que falham) · Observability, Reliability & Cost 6% (trace_id, Prometheus, tokens e custo por request, OTel) · Production Engineering 5% (lockfile, multi-stage, réplicas) · Engineering Judgment 4% (ADRs, proporcionalidade, honestidade). O avaliador pode NÃO rodar nada: a evidência tem de estar escrita no repositório.

Kit: maathmartins-ux/kit-preflight, branch kit-v3.7.0 (anexe esse repositório com add_repo e copie o conteúdo para este). Siga docs/kit/PLAYBOOK.md À RISCA (marcos duros da
seção 2, regras da seção 3, planos B da seção 4) e use os prompts de docs/kit/PROMPTS.md para as sessões-irmãs.

Passos:
1. T+0: copie o kit para este repositório (sem o histórico do kit), commit
   "chore: scaffold from entregar-desafio-cronometrado kit v3.7.0", push. Esta é a hora zero.
2. Rode `python scripts/cloud_probe.py --site https://www.bcb.gov.br/`. Se faltar algo, me
   avise numa linha e siga com o que não depende disso.
3. `python scripts/preflight.py` → commit "preflight: domínio do desafio" (ensaio sem ramo `kit-fonte`:
   `--skip-repo-check`).
4. Até T+10: docs/SPEC.md completa + evals/cases.jsonl (official literais, replan ≥ 20, parallel, approval).
   Commit "spec".
5. T+10: monte o prompt de cada frente (H, R, K, T, Q, D): o bloco dela de PROMPTS.md com o texto da SPEC no
   lugar de <<SPEC>> e, no H, o SEU id de sessão (get_session sem argumento) no lugar de <<ID DA SESSÃO M>>.
   Grave em var/prompts/<letra>.md e IMPRIMA cada um no chat, numerado, para o dono colar na sessão daquela
   frente (sessão criada por você recusa tarefa sensível porque a ordem não veio do dono; medido em 31/10/2026).
6. Ondas de integração em T+20, T+26 e T+32 (PLAYBOOK §2). Para cada fork/<x> com push novo:
   `python scripts/check_ownership.py <x> --base main`, merge --no-ff, `python scripts/check.py`.
   Mensagens entre sessões só chegam no fim do turno: coordene pelo git e confira cada sessão com get_session.
7. T+32→T+38: `python -m evals.run_evals --calibrate-gate`, ponha o limiar em src/app/domain/challenge/__init__.py
   (MIN_SCORE), `python scripts/check.py --docker --scale`.
8. T+33: em segundo plano, na nuvem: `scripts/live_eval.sh --splits official,replan,parallel,memory,approval
   --repeat 3 --max-usd 3 --workers 4` (inclui o juiz) e depois `python -m evals.run_evals --live --ablate-replan
   --repeat 1 --max-usd 0.5`. Commite evals/results/ quando terminar. PLANO B, se a sonda do passo 2 acusou a
   chave: mande ao dono, numa linha, o comando do PC
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\kit\scripts\pc_live.ps1" -Repo <URL deste repositório>
   e, quando ele disser "live pronto" (ou no T+46): `git fetch origin fork/live`,
   `python scripts/check_ownership.py live --base main`, merge.
9. T+48: `make readme`, `python scripts/check.py --docker --scale`, commit "readme" com README + evals/results/.
10. T+54: `python scripts/fill_readme.py` por último; commit só de README/ESTADO; push; confira o CI no GitHub.
11. T+59: pare. Nada de commit depois. Mande ao dono um resumo de 10 linhas: nota esperada por critério,
    o que ficou de fora e por quê, link do CI e do vídeo.

Regras que você não quebra: motor congelado; gate nunca desce; held-out cego; número só via fill_readme;
nada da loja de exemplo no produto; comentário só com número medido; ESTADO.md atualizado a cada marco.
```
