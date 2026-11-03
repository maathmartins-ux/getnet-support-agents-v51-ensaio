# Lições da Getnet v4 (01/11/2026) — o que funcionou, o que falhou, o que mudou no kit v5

Repositório: `maathmartins-ux/getnet-support-agents-v4`. Primeiro commit 19:57:56 UTC, último 20:32:01 UTC:
**34 min**. CI verde no último commit. Números abaixo são do `evals/results/` commitado lá.

## 1. O que funcionou (manter)

| Prática | Evidência na v4 |
|---|---|
| Sessão principal (M) como regente e as frentes como **subagentes da própria sessão** (Agent tool, em segundo plano), cada uma num `git worktree` com branch `fork/<x>`; merge local com `check_ownership.py` | 5 frentes (R, K, T, Q, D) com "pronto" entre 20:01 e 20:03; merges até 20:04 (T+7) |
| Autor cego do held-out como subagente separado, que lê só enunciado + SPEC | 24 casos às 20:00; teste de contaminação pegou 1 regra e 6 exemplos coincidentes, trocados antes do merge |
| SPEC com **desempates escritos** (sintoma → troubleshoot; dado → support; "preciso de" sobre produto → knowledge) | intent 100% em official, replan, parallel e approval offline e ao vivo |
| Ablação do replanejamento com × sem | replan ao vivo 93,3% com × 0% sem (mesmos casos) |
| Juiz calibrado só em official + replan | 90 respostas, kappa 0,957, TPR 0,957, TNR 1,0 |
| Eval ao vivo pass^3 por split, depois de congelar o código | official pass^3 0,3 → 0,6 → 0,7 em três rodadas de correção |
| Relatório ao dono a cada ~5 min em horário local (UTC−3), com adiantado/atrasado | o dono acompanhou sem abrir o repositório |
| Vídeo gerado na nuvem: respostas reais + slides do JSON + Playwright + ffmpeg | 3min12s, 1,4 MB, commitado em `docs/video/` |

## 2. O que falhou (e a correção no kit v5)

| Falha | Custo na v4 | Correção no v5 |
|---|---|---|
| Ingest descartava tabela de preços (células < 15 caracteres e linha repetida em 6+ páginas) | AC-01 respondia "não achei comparação"; 10 min para achar e remendar com trecho manual | `app/ingest.py`: células curtas viram linha de tabela; linha longa repetida fica 1 vez (teste em `tests/test_ingest.py`) |
| `live_eval.sh` sem bit de execução | eval ao vivo morreu com 126 ("Permission denied") | bit no git + `tests/test_scripts_exec.py` |
| Eval ao vivo em fila, teto herdado | memory e approval abortaram por teto (o aborto sobrescreveu um approval completo); juiz ficou sem verba | splits em paralelo, 80% do teto em cotas iguais, 20% para o juiz; teto padrão US$ 10 (custo medido ~6,1) |
| Checagem numérica acusava "R$ 80mil" (escala colada) e a data de hoje da busca web | official numbers 66,7% ao vivo | `grounding._NUM` aceita escala colada; data de hoje entra na evidência quando a busca trouxe evidência |
| Router LLM respondeu "pt" para pergunta em inglês com termo pt entre parênteses | official-06 em pt em 2 de 3 rodadas | `router.clear_language`: sem ambiguidade (vantagem ≥ 2 palavras) a contagem manda |
| README commitado junto com resultados | CI vermelha 2 vezes ("linha do tempo com 36 commits, o git tem 37") | `scripts/final.sh` (`make final`): README sozinho no último commit, recusa se houver outra mudança |
| `MIN_SCORE` escrito à mão com comentário de 126 colunas | lint vermelho no check | `run_evals --calibrate-gate --apply` grava o limiar com a medida, em linha curta |
| venv com `app` editável apontando para o repo da v3 | ingest gravou no repo errado; testes passaram contra código antigo | `check.py` recusa antes de tudo ("venv aponta para este repo") |
| `pkill -f "<padrão>"` matou o próprio shell (o padrão aparecia na linha de comando) | 2 comandos perdidos | PLAYBOOK: matar por PID (`ps -eo pid,args \| grep "[p]adrão"`), nunca `pkill -f` com o texto do próprio comando |
| Offline, o Knowledge devolve o trecho em pt para pergunta en | `language_acc` official 50% offline | prefere o trecho no idioma da pergunta (+0,8 p.p. no total da v4); o ao vivo resolve (100%) |
| E-mail `@example.com` num caso de guardrail | check "sem dado de exemplo" vermelho | prompt da frente Q: domínio fictício próprio (`@lojadojoao.com.br`), nunca `example.com` |
| Rótulos de retrieval por id de trecho | re-ingest renomeou ids e o teste de corpus quebrou | PLAYBOOK: re-ingest só com a frente K atualizando `evals/retrieval.d/k.jsonl` no mesmo commit |

## 3. O que ficou abaixo de 9,5 (atacar na v5)

| Ponto | Número v4 | Por que pesa | Plano v5 |
|---|---|---|---|
| Recall@3 | 0,486 (MRR 0,61, n=50) | RAG 10% | frente K mede no T+15 com `--compare-retrievers --rerank` e corrige (glossário, páginas faltando, rótulos de várias passagens); meta ≥ 0,7 |
| Números da web (clima, câmbio) | official numbers 80% ao vivo | o juiz marca 2 de 10 como não fundamentados | a busca web cifra o corpo; declarar no README e, na v5, mostrar `unsupported_numbers` como sinal e não erro na resposta geral |
| memory ao vivo | pass^3 0,46; numbers 64% | Memory 8% | casos de memória com números derivados (soma, "há 3 horas"): prompt pede número copiado da tool, não calculado |
| Portão sem fonte | recusa 81% dos sem fonte | RAG + HITL | `--calibrate-gate --apply` depois do corpus final (recomendou 8,643 → 88%) |

## 4. Linha do tempo real (UTC, `git log`)

19:57 scaffold · 19:58 preflight e SPEC · 20:00 held-out cego · 20:01–20:03 frentes prontas · 20:04 merges e
integração · 20:06 limiar calibrado · 20:10 correção do corpus (AC-01) · 20:14–20:17 correções do ao vivo ·
20:21 resultados ao vivo completos · 20:31 vídeo + juiz · 20:32 README (último commit).
