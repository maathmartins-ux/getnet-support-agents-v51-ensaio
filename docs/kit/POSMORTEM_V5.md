# Pós-morte da V5 (02/11/2026) — erros de nota e de tempo, e o que muda no kit

Tentativa cronometrada sobre o desafio Getnet, kit v5.1/v5.2, sessão na nuvem orquestrada por uma sessão maestra.
Relógio: commit `5f28b22` (18:05:47 UTC) → último commit `371d960` (18:56:33), **50,8 min** (teto 58). Nota estimada
pela maestra e pela própria sessão: **8,2–8,5** (v4 recebeu 8,5). **Não enviada ao avaliador** (decisão do dono:
abaixo de 9,5 não se envia). Repositório: `maathmartins-ux/getnet-support-agents-v5`.

## 1. Placar final (README §0 da V5)

| métrica | V5 | meta | v4 |
|---|---:|---:|---:|
| juiz: oficiais fundamentadas | **1,00** (r1: 98,9% official+replan) | 0,90 | 0,60 |
| oficiais: números com base | 96,7% | 95% | 80% |
| oficiais: pass^3 | 0,60 | 0,90 | 0,70 |
| memória: pass@1 | 0,72 (memória 90,6%, perda de rota) | 0,85 | 0,54 |
| busca: Recall@3 / MRR (gold essencial) | 0,84 / 0,71 | 0,85 / 0,80 | 0,49 / 0,61 |
| held-out cego: casos / intenção | 80 / 67,5% | 80 / 85% | 24 / — |
| rotuladores / kappa entre humanos | 2 / 0,054 | 2 / — | 1 |
| juiz × humano: kappa | 0,58 | 0,80 | 0,95 |
| ataques ao vivo bloqueados | 60/63 | — | — |
| CI do último commit | vermelha (marcador `{{N}}` no título de commit da maestra) | verde | verde |

## 2. Erros de NOTA (causa → mudança no kit)

| # | erro | causa medida | mudança no kit (com teste) |
|---|---|---|---|
| N1 | official-01 (Clássica × Smart) e official-04 (Pix sem conta) vão ao humano: "não está nas fontes" | o fato estava no corpus (`prod-todas-maquininhas-04`: R$ 79,90 × R$ 129,90) mas fora do top-3 do denso; a v4 tinha posto uma tabela à mão no T+13 | **portão de fato oficial**: a SPEC grava 1 regex por fato de referência; `tests/test_official_facts.py` reprova se algum cenário oficial de conhecimento não tem o trecho do fato no top-3 do buscador escolhido (roda no fork K, antes do merge) |
| N2 | 4 oficiais em inglês recusadas pelo portão (r1) | piso de cosseno 0,88 calibrado sem perguntas em inglês; no denso, com e sem fonte ficam em 0,82–0,88 | `--calibrate-gate` exige pares pt/en e reporta a recusa por idioma; o portão padrão passa a ser o do rerank quando ele está ligado |
| N3 | rerank (0,947 / 0,807) medido e NÃO adotado | p95 medido com 8 subagentes na CPU (2,9 s); no ensaio sem carga 1,1–1,25 s | **escolha do buscador fixada antes do relógio** pelo ensaio (`data/retriever.json` do kit = denso + rerank pool 10, com o p95 sem carga); no relógio só se mede a qualidade no gold novo; latência medida só com a máquina parada |
| N4 | held-out: intenção 67,5% (multi→support 7, troubleshoot→support 5) | taxonomia do router confunde "duas perguntas" e "sintoma" com consulta de dados | exemplos k-NN e desempates da SPEC por essas 3 fronteiras; fork R mede no held-out sintético de autor cego ANTES do merge (sem ver o held-out real) |
| N5 | memória pass@1 0,72: 18 perdas só de rota | seguimento ("e a outra?") roteado sem herdar a intenção | regra de herança de intenção no seguimento curto com teste por padrão de seguimento |
| N6 | juiz da rodada 2 não medido | corte de tempo | juiz roda junto com a rodada (no mesmo processo, ao fim de cada split) |
| N7 | dependent/real/official-var/heldout ao vivo abortaram por teto | cota por split pequena demais com 11 splits | cota por split proporcional ao nº de casos × repeat; só official+memory com repeat 3 |
| N8 | kappa entre humanos 0,054 | a 2ª pessoa leu a pergunta 3 (idioma) como "devia ser em português" | página: pergunta 3 mostra o idioma da pergunta e o da resposta lado a lado e diz "inglês com inglês = Sim"; ensaio da página com a 2ª pessoa usando conversa em inglês |
| N9 | CI vermelha | título de commit com `{{N}}` reproduzido na linha do tempo do README | `fill_readme` neutraliza `{{`/`}}` na linha do tempo; hook/checagem recusa título de commit com marcador |
| N10 | vídeo quase cortado no fim | prioridade errada no corte | vídeo gerado no T+35 em 2º plano, sem depender da rodada 2 |

## 3. Erros de TEMPO (onde foram os minutos)

| marco | v4 | V5 | diferença e causa |
|---|---:|---:|---|
| SPEC | T+1,0 | T+6,0 | SPEC da V5 traz os fatos de referência e 66 casos (necessário); custo aceito |
| todas as frentes integradas | T+6,1 | T+18,9 | **frente K = caminho crítico**: corpus + gold essencial + `--choose-retriever` com e5-large sob 8 subagentes |
| buscador decidido | (bm25, sem medida pesada) | T+24,9 | 6 min reavaliando o rerank com a CPU cheia |
| 1ª rodada ao vivo completa | T+24,0 | T+31,9 | 11 splits × repeat 3 com o denso |
| último commit | T+34,1 | T+50,8 | 2ª rodada + correções + página humana |
| antes do relógio | — | ~10 min | sessão sem acesso ao kit (add_repo negado), ramo padrão errado, tags que o proxy não envia |

**Mudanças de tempo no kit:**
- T1. O kit vai DENTRO do repositório da tentativa antes do relógio (ramo `kit-fonte` criado pela maestra, `main`
  com 1 commit), e o ramo padrão conferido; nada de add_repo na sessão do relógio.
- T2. Buscador decidido antes do relógio (N3): a K só ingere, rotula o gold e mede a qualidade (≤ 8 min).
- T3. Fumaça ao vivo no T+12: 1 rodada só do official, repeat 1 (US$ ~0,3), para achar N1/N2 15 min antes.
- T4. Rodada 1 no T+20 só com official, memory, replan (repeat 3 só nos dois primeiros); o resto com repeat 1.
- T5. Cortes decididos no prompt (o que cai se X não fechar até Y) e folga planejada de 5 min.
- T6. Hora sempre pela máquina (a sessão principal informava a hora ~3 min adiantada).
- T7. Tags: o relógio vale pelo commit de scaffold e pelo último commit (o proxy da nuvem derruba push de tag).

## 4. O que funcionou e fica

- Juiz com o texto das fontes + cartão de capacidades + checagem por frase: **oficiais 100% fundamentadas**.
- Avaliação independente montada no relógio: held-out cego 80, 40 perguntas reais com link, 2 rotuladores pela página.
- Orquestração por `needs` com ablação (dependent 100% com × 0% sem); guardrail ao vivo 60/63.
- Maestra assumindo docs (ARCHITECTURE, ADR 0008, rascunho do README) em ramos próprios: zero conflito.
- Placar honesto: 6 de 11 métricas abaixo da meta na primeira tela, cada uma com a causa.
