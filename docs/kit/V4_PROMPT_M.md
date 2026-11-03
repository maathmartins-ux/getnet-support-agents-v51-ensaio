# Prompt da sessão principal da V4 (desafio Getnet) — pronto para colar

Abra uma sessão da nuvem pelo Chrome ([CHROME.md](CHROME.md) §2), no repositório VAZIO da v4, com o modelo
**Opus**. Copie o bloco abaixo, troque SÓ `<<COLE O ENUNCIADO INTEIRO>>` pelo enunciado da Getnet (literal) e cole.

Modelos das sessões (decisão de 01/11/2026: "sem limite de tokens", PC só com o Chrome):

| Sessão | Modelo | Por quê |
|---|---|---|
| M (principal) | Opus | integra, decide, mede: tudo passa por ela |
| R (roteamento e orquestração) | Opus | Agentic 15% + Business 8%: o critério mais pesado |
| Q (qualidade e segurança) | Opus | Evaluation 14% + Security 13% |
| K, T, D, H | Sonnet | trabalho mais mecânico; metade do custo |

Custo estimado: US$ 60 a 110 de crédito (limite mensal ≥ US$ 130).

```text
Você é a sessão principal (M) de uma tentativa cronometrada: menos de 60 min do primeiro ao último commit,
qualidade mirando 10 na régua abaixo, tratada como a última tentativa. Responda ao dono em português simples.

Enunciado (literal):
<<COLE O ENUNCIADO INTEIRO>>

Régua de avaliação:
Business & Challenge Fit 8% (cenários oficiais via HTTP no container; multi-turno) · Agentic Reasoning & Orchestration 15% (supervisor que observa e replaneja; plano fixo por intent = faixa 7–8) · Context, Knowledge & RAG 10% (híbrido, Recall@K e MRR medidos, trechos literais) · Tool & Action Engineering 10% (JSON Schema, ação de escrita com confirmação, estado persistido) · Security & Identity 13% (user_id do token, rate limit, guardrails além de regex) · Memory, State & Resilience 8% (memória multi-turno persistida) · Human Oversight & Risk 7% (HITL real: fila persistida, operador responde, conversa retoma) · Evaluation & Quality 14% (golden set, splits, gate no CI, juiz LLM calibrado, casos que falham) · Observability, Reliability & Cost 6% (trace_id, Prometheus, tokens e custo por request, OTel) · Production Engineering 5% (lockfile, multi-stage, réplicas) · Engineering Judgment 4% (ADRs, proporcionalidade, honestidade). O avaliador pode NÃO rodar nada: a evidência tem de estar escrita no repositório.

Kit: maathmartins-ux/kit-preflight, branch kit-v3.7.0 (anexe esse repositório com add_repo e copie o conteúdo para este). Siga docs/kit/PLAYBOOK.md À RISCA (marcos duros da
seção 2, regras da seção 3, planos B da seção 4) e use os prompts de docs/kit/PROMPTS.md para as sessões-irmãs.


Armadilhas que a v3 mostrou NESTE desafio (docs/kit/REFERENCIAS.md e o balanço da v3) — copie para a SPEC e para
os prompts das frentes R, K e Q:
- AC-04 "Do I need a bank account to receive my sales via Pix?" é KNOWLEDGE, não support (a v3 errou por uma regra
  com "conta bancária"). Maiores confusões da v3: troubleshoot→knowledge (10) e support→knowledge (8); split
  parallel 50%; memória multi-turno 61,5%. Gate de intenção ≥ 90% em CADA split do gate.
- Resposta no IDIOMA da pergunta, também no caminho sem LLM (v3: 4/10 dos official em inglês respondidos em
  português) e em FRASE que responde (v3 devolvia trecho cru ou lista de campos).
- Nenhuma frase do held-out em regra ou exemplo (v3: `o dinheiro d[ae]s?` copiava o heldout-05).
- Corpus só do site BRASIL (`site.getnet.com.br`; `getnet.net/pt` é Portugal).
- Publicar: replanejamento com × sem (`run_evals --ablate-replan`, offline e ao vivo), comparação de buscadores
  (`--compare-retrievers --rerank`), matriz de confusão do router, `check.py --docker --scale` verde (2 réplicas).
- Referência pública: a melhor nota DENTRO de 60 min é 8,7 (nelsondell v1); 9,5 e 10,0 vieram fora do relógio.

Passos:
1. T+0: copie o kit para este repositório (sem o histórico do kit), commit
   "chore: scaffold from entregar-desafio-cronometrado kit v3.7.0", push. Esta é a hora zero.
2. Rode `python scripts/cloud_probe.py --site https://site.getnet.com.br/`. Se faltar algo, me
   avise numa linha e siga com o que não depende disso.
3. `python scripts/preflight.py` → commit "preflight: domínio do desafio".
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
