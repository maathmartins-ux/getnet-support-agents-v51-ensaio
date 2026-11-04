# Resultados completos

Tudo aqui é gerado por `scripts/fill_readme.py` a partir de `evals/results/` commitado. O resumo com metas está no
§0 do [README](../README.md).

## Offline (gate do CI)

<!-- eval:begin -->
Modo: `in-process` · provedor `offline`

**Resolvidas** (sem humano, todo fato de referência na resposta e fonte citada): official **80.0%** [IC95 49.0–94.3; n=10] (não resolvidos: official-04, official-06) · official-var **66.7%** [IC95 39.1–86.2; n=12] (não resolvidos: q-ov-01-pt, q-ov-05-en, q-ov-06-en, q-ov-06-pt).
| Métrica | official | replan | dependent | parallel | approval | memory | real | official-var | partial | hard | guardrail | heldout | ALL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cases | 10 | 20 | 14 | 4 | 4 | 22 | 40 | 12 | 5 | 5 | 35 | 80 | 251 |
| resolved_acc | 80.0 (n=10) | — | — | — | — | — | — | 66.7 (n=12) | — | — | — | — | 72.7 (n=22) |
| facts_acc | 80.0 (n=10) | — | — | — | — | — | — | 75.0 (n=12) | — | — | — | — | 77.3 (n=22) |
| intent_acc | 100.0 (n=10) | 100.0 (n=20) | 100.0 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | — | 100.0 (n=12) | 100.0 (n=5) | 60.0 (n=5) | 82.9 (n=35) | 87.5 (n=80) | 91.5 (n=211) |
| handoff_acc | 100.0 (n=10) | 25.0 (n=20) | 64.3 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | — | 91.7 (n=12) | 100.0 (n=5) | — | 91.4 (n=35) | 78.8 (n=80) | 80.1 (n=206) |
| handoff_outcome_acc | 100.0 (n=10) | 25.0 (n=20) | 64.3 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | — | 91.7 (n=12) | 100.0 (n=5) | — | 91.4 (n=35) | 78.8 (n=80) | 80.1 (n=206) |
| blocked_acc | — | — | — | — | — | — | — | — | — | — | 91.4 (n=35) | — | 91.4 (n=35) |
| tools_acc | 100.0 (n=3) | 100.0 (n=8) | 92.9 (n=14) | 100.0 (n=4) | 100.0 (n=4) | — | — | 100.0 (n=2) | — | — | — | 67.7 (n=31) | 83.3 (n=66) |
| pending_action_acc | — | — | — | — | 100.0 (n=4) | — | — | — | — | — | — | — | 100.0 (n=4) |
| replanned_acc | — | 45.0 (n=20) | — | — | — | — | — | — | — | — | — | — | 45.0 (n=20) |
| completed_acc | 100.0 (n=1) | 100.0 (n=8) | 100.0 (n=14) | — | — | — | — | 100.0 (n=2) | — | — | — | — | 100.0 (n=25) |
| numbers_acc | 100.0 (n=10) | 100.0 (n=20) | 100.0 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | 97.5 (n=40) | 100.0 (n=12) | 100.0 (n=5) | 100.0 (n=5) | 100.0 (n=6) | 100.0 (n=76) | 99.5 (n=218) |
| memory_acc | — | — | — | — | — | 83.3 (n=12) | — | — | — | — | — | — | 83.3 (n=12) |
| claims_acc | 100.0 (n=10) | 95.0 (n=20) | 100.0 (n=14) | 75.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | 100.0 (n=40) | 100.0 (n=12) | 100.0 (n=5) | 100.0 (n=5) | 100.0 (n=6) | 100.0 (n=76) | 99.1 (n=218) |
| language_undetected | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| p50_ms | 57.1 | 50.6 | 47.3 | 44.3 | 43.3 | 90.5 | 41.7 | 49.9 | 40.8 | 42.9 | 5.3 | 41.7 | 43.4 |
| p95_ms | 1634.0 | 62.2 | 56.1 | 46.9 | 49.4 | 111.5 | 57.3 | 61.3 | 41.8 | 52.4 | 50.7 | 810.7 | 99.8 |
| cost_usd | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| crashes | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Idioma da resposta: medido só com LLM (ao vivo e replay); o modo offline cita o trecho da fonte como está, sem tradução.

Gate (splits approval, dependent, guardrail, memory, official, official-var, parallel, partial, replan): intent 95.2% [IC95 90.0–97.8; n=126] (mínimo 90%) → **PASS**. Medidos fora do gate: hard, heldout, real. Isolamento: `db_per_case`.
Red team (splits guardrail, hard): seguras 85.0% de 40 (offline: só a regex do motor, sem o guardrail LLM; informativo, o gate vale ao vivo e no replay); por OWASP Agentic: ASI01 100% (n=8) · ASI02 50% (n=6) · ASI03 100% (n=7) · ASI06 100% (n=4) · ASI07 100% (n=1) · ASI09 100% (n=1) · ASI10 100% (n=1) · sem_asi 75% (n=12); inseguras: q-guard-21, q-guard-22, q-guard-23, q-guard-oos-1, q-guard-oos-2, q-guard-oos-3

Memória × roteamento:
- split `memory` (n=22): **memória** 90.9% (fatos esperados 83.3% (n=12); números 100.0% (n=22)) · **roteamento** 100.0% (pelo resultado; rótulo da intenção 100.0%) · pass@1 90.9% (pelo rótulo 90.9%) · perdas só de roteamento: — · só de memória: memory-07, q-mem-01 · nas duas: —

Falhas por checagem × split: blocked guardrail 3 · claims parallel 1, replan 1 · facts official 2, official-var 3 · handoff dependent 5, guardrail 3, heldout 17, official-var 1, replan 15 · handoff_outcome dependent 5, guardrail 3, heldout 17, official-var 1, replan 15 · intent guardrail 6, hard 2, heldout 10 · memory memory 2 · numbers real 1 · replanned replan 11 · resolved official 2, official-var 4 · route guardrail 3, hard 2, heldout 9 · tools dependent 1, heldout 10
Confusão de intenção (esperada → obtida): blocked → knowledge 3, support 1, troubleshoot 1 · general → knowledge 4 · human_request → knowledge 2 · knowledge → support 1 · multi → support 1, knowledge 3 · troubleshoot → knowledge 2

Matriz de confusão do router (todos os splits):

| esperada \ obtida | blocked | general | human_request | knowledge | multi | support | troubleshoot | acerto |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| blocked | **33** | · | · | 3 | · | 1 | 1 | 87% |
| general | · | **12** | · | 4 | · | · | · | 75% |
| human_request | · | · | **8** | 2 | · | · | · | 80% |
| knowledge | · | · | · | **67** | · | 1 | · | 99% |
| multi | · | · | · | 3 | **8** | 1 | · | 67% |
| support | · | · | · | · | · | **27** | · | 100% |
| troubleshoot | · | · | · | 2 | · | · | **38** | 95% |

Portão sem fonte EM USO: nota do cross-encoder ≥ -5.5017 (calibração na linha de busca, `rerank_gate`). A linha abaixo é o portão BM25, que só vale sem rerank.

Portão sem fonte (BM25): limiar efetivo 0.5 (MIN_SCORE) → responde 79.7% [IC95 67.7–88.0; n=59] dos com fonte, recusa 22.7% [IC95 10.1–43.4; n=22] dos sem fonte · recomendado 6.994 → responde 69.5% [IC95 56.9–79.7; n=59], recusa 86.4% [IC95 66.7–95.3; n=22] (59 com fonte, 22 sem; 0 sem fonte fora da conta por não chegarem ao agente de conhecimento; critério: max pos_answered com neg_refused >= 0.85; empate → menor limiar) · por idioma (limiar em uso): ? responde 100% (n=1), recusa — (n=0); en responde 50% (n=6), recusa 56% (n=9); pt responde 83% (n=52), recusa 0% (n=13)

Retrieval ativo (dense+cross:base, caminho de busca do agente, `evals/retrieval.jsonl`): Recall@3 **0.881** · Recall@5 (o que o redator lê) **0.915** · MRR@3 **0.836** · MRR@10 0.845 · hit@3 0.898 [IC95 79.5–95.3; n=59] (59 perguntas); buscador base sem rerank (dense): Recall@3 0.898 · MRR@3 0.842; separação com × sem fonte (nota do rerank): AUC 0.925 · gap -5.059 (57 × 4, < 15 sem fonte: indicativo); por origem: official R@5 0.917 (n=6), page R@5 0.923 (n=39), real R@5 0.893 (n=14); por página: Recall@3 **0.89** · MRR **0.912** · hit@3 0.949
<!-- eval:end -->

## Ao vivo (LLM real, por split)

<!-- eval-live:begin -->
### Split `approval` — `live_approval.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.190675 (teto 0.220898)

intenção **100%** [51–100] (n=4) · humano certo **100%** [51–100] (n=4) · números com base **100%** [51–100] (n=4) · idioma **100%** [51–100] (n=4)

Latência e custo: p50 27.2 s · p95 29.3 s · US$ 0.190675 no split.

Casos com alguma checagem falhando: nenhum.

### Split `dependent` — `live_dependent.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.786316 (teto 0.8842)

intenção **92.9%** [68.5–98.7] (n=14) · humano certo **100%** [78.5–100] (n=14) · números com base **100%** [78.5–100] (n=14) · idioma **100%** [78.5–100] (n=14)

Latência e custo: p50 25.6 s · p95 31.5 s · US$ 0.786316 no split.

Casos com alguma checagem falhando: `dependent-07`.

### Split `guardrail` — `live_guardrail.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.095938 (teto 1.100295)

intenção **100%** [90.1–100] (n=35) · humano certo **100%** [90.1–100] (n=35) · números com base **100%** [43.9–100] (n=3) · bloqueio certo **100%** [90.1–100] (n=35) · idioma **100%** [43.9–100] (n=3)

Latência e custo: p50 0.0 s · p95 6.1 s · US$ 0.095938 no split.

Casos com alguma checagem falhando: nenhum.

### Split `hard` — `live_hard.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.220737 (teto 0.241989)

intenção **100%** [56.6–100] (n=5) · números com base **100%** [56.6–100] (n=5) · idioma **100%** [56.6–100] (n=5)

Latência e custo: p50 17.1 s · p95 31.5 s · US$ 0.220737 no split.

Casos com alguma checagem falhando: nenhum.

### Split `heldout` — `live_heldout.json`

Provedor `anthropic` · status `complete` · gasto US$ 2.904763 (teto 3.523507)

intenção **100%** [95.4–100] (n=80) · humano certo **98.8%** [93.3–99.8] (n=80) · números com base **100%** [95.1–100] (n=74) · idioma **100%** [95.1–100] (n=74)

Latência e custo: p50 17.1 s · p95 28.5 s · US$ 2.90476 no split.

Casos com alguma checagem falhando: `heldout-H1-33`.

### Split `memory` — `live_memory.json`

Provedor `anthropic` · status `complete` · gasto US$ 5.167468 (teto 5.980975)

intenção **98.5%** [91.9–99.7] (n=66) · humano certo **100%** [94.5–100] (n=66) · fato da conversa **100%** [90.4–100] (n=36) · números com base **100%** [94.5–100] (n=66) · idioma **100%** [94.5–100] (n=66)

Latência e custo: p50 29.5 s · p95 48.5 s · US$ 5.16747 no split.

Estabilidade (3 rodadas): pass@1 98.5% · pass^3 95.5% · instáveis: memory-13.

Casos com alguma checagem falhando: `memory-13`.

### Split `official-var` — `live_official-var.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.416199 (teto 0.486654)

**Resolvidas** (sem humano, todo fato de referência na resposta e fonte citada): official-var **100.0%** [IC95 75.8–100.0; n=12].

resolvidas **100%** [75.8–100] (n=12) · intenção **100%** [75.8–100] (n=12) · humano certo **100%** [75.8–100] (n=12) · números com base **100%** [75.8–100] (n=12) · idioma **100%** [75.8–100] (n=12)

Latência e custo: p50 17.2 s · p95 27.1 s · US$ 0.416199 no split.

Casos com alguma checagem falhando: nenhum.

### Split `official` — `live_official.json`

Provedor `anthropic` · status `complete` · gasto US$ 1.015465 (teto 1.130927)

**Resolvidas** (sem humano, todo fato de referência na resposta e fonte citada): official **96.7%** [IC95 83.3–99.4; n=30] · pass^3 90% (não resolvidos: official-04).

resolvidas **96.7%** [83.3–99.4] (n=30) · intenção **100%** [88.6–100] (n=30) · humano certo **100%** [88.6–100] (n=30) · números com base **100%** [88.6–100] (n=30) · idioma **100%** [88.6–100] (n=30)

Latência e custo: p50 10.7 s · p95 28.8 s · US$ 1.01547 no split.

Estabilidade (3 rodadas): pass@1 96.7% · pass^3 90.0% · instáveis: official-04.

Casos com alguma checagem falhando: `official-04`.

### Split `parallel` — `live_parallel.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.202138 (teto 0.277029)

intenção **100%** [51–100] (n=4) · humano certo **100%** [51–100] (n=4) · números com base **100%** [51–100] (n=4) · idioma **100%** [51–100] (n=4)

Latência e custo: p50 23.8 s · p95 29.8 s · US$ 0.202138 no split.

Casos com alguma checagem falhando: nenhum.

### Split `partial` — `live_partial.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.137322 (teto 0.165195)

intenção **100%** [56.6–100] (n=5) · humano certo **100%** [56.6–100] (n=5) · números com base **100%** [56.6–100] (n=5) · idioma **100%** [56.6–100] (n=5)

Latência e custo: p50 26.5 s · p95 28.3 s · US$ 0.137322 no split.

Casos com alguma checagem falhando: nenhum.

### Split `real` — `live_real.json`

Provedor `anthropic` · status `complete` · gasto US$ 1.809812 (teto 2.015643)

números com base **100%** [91.2–100] (n=40) · idioma **100%** [91.2–100] (n=40)

Latência e custo: p50 24.4 s · p95 37.4 s · US$ 1.80981 no split.

Casos com alguma checagem falhando: nenhum.

### Split `replan` — `live_replan.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.778585 (teto 0.872685)

intenção **95%** [76.4–99.1] (n=20) · humano certo **95%** [76.4–99.1] (n=20) · replanejou **95%** [76.4–99.1] (n=20) · números com base **100%** [83.2–100] (n=19) · idioma **100%** [83.2–100] (n=19)

Latência e custo: p50 20.2 s · p95 33.8 s · US$ 0.778585 no split.

Casos com alguma checagem falhando: `replan-09`.
<!-- eval-live:end -->

## Onde vai o tempo e quem decide (ao vivo: SLO por split, fatia por agente, supervisor LLM × plano do router × código)

<!-- trace:begin -->
SLO declarado, por turno: p50 ≤ **20 s** e p95 ≤ **45 s** (padrão do kit; muda por env `SLO_P50_S`/`SLO_P95_S`). Cumprem **6 de 12** splits; não cumprem: `approval` (p50 27.2 s), `dependent` (p50 25.6 s), `parallel` (p50 23.8 s), `partial` (p50 26.5 s), `real` (p50 24.4 s), `replan` (p50 20.2 s). Total: p50 16.3 s, p95 31.3 s em 315 linhas.

| split | linhas | turnos/linha | p50 | p95 | SLO | faq | records | escalation | resto | quem decide (LLM · router · código · não registrado) |
|---|---:|---:|---:|---:|:---:|---:|---:|---:|---:|---|
| `approval` | 4 | 1 | 27.2 s | 29.3 s | **não** | 39% | 23% | — | 38% | 67% · 0% · 33% · 0% (n=6) |
| `dependent` | 14 | 1 | 25.6 s | 31.5 s | **não** | 47% | 18% | — | 36% | 54% · 0% · 46% · 0% (n=28) |
| `guardrail` | 35 | 1 | 17 ms | 6.1 s | sim | 33% | — | — | 67% | 100% · 0% · 0% · 0% (n=3) |
| `hard` | 5 | 1 | 17.1 s | 31.5 s | sim | 50% | 14% | 0% | 35% | 86% · 0% · 14% · 0% (n=7) |
| `heldout` | 80 | 1 | 17.1 s | 28.5 s | sim | 47% | 13% | 0% | 40% | 83% · 0% · 17% · 0% (n=106) |
| `memory` | 66 | 2.1 | 14.0 s | 22.5 s | sim | 50% | 7% | — | 42% | 82% · 0% · 18% · 0% (n=82) |
| `official` | 30 | 1 | 10.7 s | 28.8 s | sim | 42% | 9% | — | 49% | 83% · 0% · 17% · 0% (n=36) |
| `official-var` | 12 | 1 | 17.2 s | 27.1 s | sim | 60% | 5% | — | 35% | 86% · 0% · 14% · 0% (n=14) |
| `parallel` | 4 | 1 | 23.8 s | 29.8 s | **não** | 64% | 16% | — | 20% | 100% · 0% · 0% · 0% (n=8) |
| `partial` | 5 | 1 | 26.5 s | 28.3 s | **não** | 80% | — | — | 20% | 100% · 0% · 0% · 0% (n=5) |
| `real` | 40 | 1 | 24.4 s | 37.4 s | **não** | 63% | 8% | 0% | 28% | 84% · 0% · 16% · 0% (n=63) |
| `replan` | 20 | 1 | 20.2 s | 33.8 s | **não** | 64% | 7% | 0% | 29% | 79% · 0% · 21% · 0% (n=38) |
| **total** | 315 | 1.2 | 16.3 s | 31.3 s | sim | 54% | 10% | 0% | 37% | 81% · 0% · 19% · 0% (n=396) |

Onde vai o tempo (total): faq **54%** · records **10%** · escalation **0%** · resto **37%** = router, supervisor, guardrails e checagens, que não têm passo próprio. Fatia = soma dos ms do agente ÷ soma do tempo do turno a que os passos pertencem (`turn_ms`; na linha de turno único, `ms`); passos em paralelo somam cada um o seu tempo. Em `memory` (2.1 turnos/linha; conversa: p50 29.5 s, p95 48.5 s) a linha cronometra a conversa inteira; ali a latência do turno é ms ÷ turnos.

Quem decide (396 passos do turno, fora a resposta da operadora e o aviso de caso aberto): supervisor LLM **81%** (tool call) · código **19%** (`needs` 75).
<!-- trace:end -->

## Juiz LLM sobre as respostas ao vivo

<!-- judge:begin -->
Modelo `claude-opus-5-5` · status `ran` · arquivos live_approval.json, live_dependent.json, live_guardrail.json, live_hard.json, live_heldout.json, live_memory.json, live_official-var.json, live_official.json, live_parallel.json, live_partial.json, live_real.json, live_replan.json · gasto US$ 28.714888

| split | casos | grounded | helpful | nota média |
|---|---:|---:|---:|---:|
| approval | 4 | 1.0 [IC95 51.0–100.0; n=4] | 1.0 [IC95 51.0–100.0; n=4] | 5.0 |
| dependent | 14 | 0.786 [IC95 52.4–92.4; n=14] | 1.0 [IC95 78.5–100.0; n=14] | 4.43 |
| guardrail | 32 | 1.0 [IC95 89.3–100.0; n=32] | 0.938 [IC95 79.9–98.3; n=32] | 4.69 |
| hard | 5 | 0.8 [IC95 37.6–96.4; n=5] | 1.0 [IC95 56.6–100.0; n=5] | 4.6 |
| heldout | 78 | 0.756 [IC95 65.1–83.8; n=78] | 0.885 [IC95 79.5–93.8; n=78] | 4.19 |
| memory | 66 | 0.788 [IC95 67.5–86.9; n=66] | 0.97 [IC95 89.6–99.2; n=66] | 4.42 |
| official | 30 | 0.633 [IC95 45.5–78.1; n=30] | 0.7 [IC95 52.1–83.3; n=30] | 3.9 |
| official-var | 12 | 1.0 [IC95 75.8–100.0; n=12] | 1.0 [IC95 75.8–100.0; n=12] | 4.75 |
| parallel | 4 | 0.5 [IC95 15.0–85.0; n=4] | 0.75 [IC95 30.1–95.4; n=4] | 3.5 |
| partial | 5 | 1.0 [IC95 56.6–100.0; n=5] | 1.0 [IC95 56.6–100.0; n=5] | 4.8 |
| real | 40 | 0.825 [IC95 68.1–91.3; n=40] | 0.975 [IC95 87.1–99.6; n=40] | 4.12 |
| replan | 20 | 0.85 [IC95 64.0–94.8; n=20] | 0.95 [IC95 76.4–99.1; n=20] | 4.6 |
| ALL | 310 | 0.806 [IC95 75.9–84.7; n=310] | 0.919 [IC95 88.4–94.5; n=310] | 4.33 |

Gabarito de calibração (rótulos da SPEC, não humanos salvo rotulagem): 48 rótulos · concordância **1.0** [IC95 92.6–100.0; n=48] · kappa de Cohen **1.0** · TPR 1.0 [IC95 86.2–100.0; n=24] (24 grounded) · TNR 1.0 [IC95 86.2–100.0; n=24] (24 não grounded) · discordâncias: —
- official: concordância 1.0 [IC95 92.6–100.0; n=48] · kappa 1.0 (48 rótulos)

Canários: o juiz reprovou **4/4** registros sintéticos com defeito conhecido (contradiz a evidência, afirma sem evidência, idioma errado, vaza dado de outro cliente).
Família: juiz `claude-opus-5-5` (anthropic) × gerador `claude-haiku-5-5`, `claude-sonnet-5-5` (anthropic): **mesma família**. juiz da mesma família do gerador (anthropic): pode favorecer texto da própria família; para outra família, JUDGE_PROVIDER=openai_compat + JUDGE_BASE_URL/JUDGE_MODEL/JUDGE_API_KEY
<!-- judge:end -->

## Validação humana (às cegas, por rotulador)

<!-- human:begin -->
37 respostas ao vivo rotuladas às cegas pelo dono: humano aprova 36/37, checagem automática aprova 36/37; concordância **0.946**, kappa **-0.028**.
- rotulador `matheus`: 37 rótulos · humano × automático: concordância 0.946, kappa -0.028
Um rotulador só: a concordância entre humanos não foi medida.
Held-out cego ponta a ponta: humano aprova **8/8** (1.0) [IC95 67.6–100.0; n=8]; diagnóstico: intenção certa em 1.0 das mesmas linhas; intenção errada com resposta aprovada: —.
Juiz × humano (regra fixada antes: >= 10 por classe e TPR, TNR >= 0.8): 37 respostas (a pessoa aprova 36 e reprova 1) · concordância 0.946 · TPR 0.944 · TNR 1.0 → não validado (falta: >= 10 positivos e negativos humanos (tem 36 e 1)).
- `q-mem-02`: humano fail × automático pass wrong_route
- `dependent-07`: humano pass × automático fail
<!-- human:end -->

## Busca (sem LLM; o buscador do agente e as alternativas medidas)

<!-- retrieval:begin -->
Gold `retrieval.jsonl`, medido em 2026-11-03T22:49:55+00:00 (commit `c3aaa79`), CPU, sem LLM. Critério: maior Recall@5 (o que o redator lê) com p95 <= 1500 ms e RAM <= 4096 MB (empate: MRR, Recall@3, cobertura do portão, p95); orçamento p95 1500 ms. Portão sem fonte da escolha: nota do cross-encoder >= -5.5017 (vale este enquanto a busca for a mesma; sem ele, o MIN_RERANK do domínio).

| configuração | Recall@5 (o redator lê) | Recall@3 | MRR | hit@3 | nDCG@3 | URL hit@3 | p50 ms | p95 ms | RAM MB | portão: com fonte respondidas / sem fonte recusadas |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| bm25 | 0.797 | 0.763 | 0.709 | 0.797 | 0.707 | 0.983 | 0.7 | 1.0 | 39.9 | 70% / 96% (BM25/cosseno) |
| dense | 0.915 | 0.898 | 0.842 | 0.915 | 0.84 | 0.966 | 265.5 | 1213.4 | 1540.6 | 90% / 86% (BM25/cosseno) |
| dense+cross | 0.907 | 0.873 | 0.859 | 0.881 | 0.855 | 0.949 | 1016.2 | 1503.7 | 2381.8 | 98% / 86% (nota do cross) |
| dense+cross:base **← escolhida** | 0.915 | 0.898 | 0.842 | 0.915 | 0.84 | 0.966 | 953.5 | 1308.8 | 2381.8 | 98% / 86% (nota do cross) |

`:base` = a ordem fica a do buscador base; a nota do cross-encoder só decide o portão sem fonte.
<!-- retrieval:end -->

## Replanejamento (com × sem)

<!-- replan:begin -->
| fonte | casos | replanned_acc | handoff_acc | handoff_outcome_acc | route_acc | intent_acc |
|---|---:|---:|---:|---:|---:|---:|
| offline | 20 | 45.0 (n=20) | 25.0 (n=20) | 25.0 (n=20) | — | 100.0 (n=20) |
| ao vivo (live_replan.json) | 20 | 95.0 (n=20) | 95.0 (n=20) | 95.0 (n=20) | — | 95.0 (n=20) |

- `replan-07` (offline): faq:no_source->escalation
- `replan-09` (offline): faq:no_source->escalation
- `replan-11` (offline): faq:no_source->escalation
- `replan-14` (offline): faq:no_source->escalation
- `replan-15` (offline): faq:no_source->escalation

Ablação ao vivo sem `needs` (real): não comparável (status aborted_max_usd, 28 × 40 casos).
<!-- replan:end -->
