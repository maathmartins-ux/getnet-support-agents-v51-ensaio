# Resultados completos

Tudo aqui é gerado por `scripts/fill_readme.py` a partir de `evals/results/` commitado. O resumo com metas está no
§0 do [README](../README.md).

## Offline (gate do CI)

<!-- eval:begin -->
Modo: `in-process` · provedor `offline`

**Resolvidas** (sem humano, todo fato de referência na resposta e fonte citada): official **90.0%** [IC95 59.6–98.2; n=10] (não resolvidos: official-06) · official-var **75.0%** [IC95 46.8–91.1; n=12] (não resolvidos: q-ov-01-pt, q-ov-06-en, q-ov-06-pt).
| Métrica | official | replan | dependent | parallel | approval | memory | real | official-var | partial | hard | guardrail | heldout | ALL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cases | 10 | 20 | 14 | 4 | 4 | 22 | 40 | 12 | 5 | 5 | 35 | 80 | 251 |
| resolved_acc | 90.0 (n=10) | — | — | — | — | — | — | 75.0 (n=12) | — | — | — | — | 81.8 (n=22) |
| facts_acc | 90.0 (n=10) | — | — | — | — | — | — | 75.0 (n=12) | — | — | — | — | 81.8 (n=22) |
| intent_acc | 100.0 (n=10) | 100.0 (n=20) | 100.0 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | — | 100.0 (n=12) | 100.0 (n=5) | 60.0 (n=5) | 65.7 (n=35) | 86.2 (n=80) | 88.2 (n=211) |
| handoff_acc | 100.0 (n=10) | 40.0 (n=20) | 100.0 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | — | 100.0 (n=12) | 100.0 (n=5) | — | 100.0 (n=35) | 91.2 (n=80) | 90.8 (n=206) |
| handoff_outcome_acc | 100.0 (n=10) | 40.0 (n=20) | 100.0 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | — | 100.0 (n=12) | 100.0 (n=5) | — | 100.0 (n=35) | 91.2 (n=80) | 90.8 (n=206) |
| blocked_acc | — | — | — | — | — | — | — | — | — | — | 74.3 (n=35) | — | 74.3 (n=35) |
| tools_acc | 100.0 (n=3) | 100.0 (n=8) | 92.9 (n=14) | 100.0 (n=4) | 100.0 (n=4) | — | — | 100.0 (n=2) | — | — | — | 67.7 (n=31) | 83.3 (n=66) |
| pending_action_acc | — | — | — | — | 100.0 (n=4) | — | — | — | — | — | — | — | 100.0 (n=4) |
| replanned_acc | — | 0.0 (n=20) | — | — | — | — | — | — | — | — | — | — | 0.0 (n=20) |
| completed_acc | 100.0 (n=1) | 100.0 (n=8) | 100.0 (n=14) | — | — | — | — | 100.0 (n=2) | — | — | — | — | 100.0 (n=25) |
| numbers_acc | 100.0 (n=10) | 100.0 (n=20) | 100.0 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | 97.5 (n=40) | 100.0 (n=12) | 100.0 (n=5) | 100.0 (n=5) | 100.0 (n=12) | 100.0 (n=77) | 99.6 (n=225) |
| memory_acc | — | — | — | — | — | 83.3 (n=12) | — | — | — | — | — | — | 83.3 (n=12) |
| claims_acc | 90.0 (n=10) | 90.0 (n=20) | 92.9 (n=14) | 100.0 (n=4) | 75.0 (n=4) | 95.5 (n=22) | 95.0 (n=40) | 100.0 (n=12) | 100.0 (n=5) | 100.0 (n=5) | 100.0 (n=12) | 94.8 (n=77) | 94.7 (n=225) |
| language_undetected | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| p50_ms | 37.4 | 36.0 | 41.9 | 43.1 | 54.0 | 70.1 | 40.1 | 34.6 | 33.4 | 33.4 | 5.6 | 35.8 | 36.0 |
| p95_ms | 4437.7 | 48.8 | 50.5 | 46.1 | 74.9 | 99.2 | 49.3 | 49.8 | 36.9 | 42.5 | 42.2 | 940.2 | 77.0 |
| cost_usd | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| crashes | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Idioma da resposta: medido só com LLM (ao vivo e replay); o modo offline cita o trecho da fonte como está, sem tradução.

Gate (splits approval, dependent, guardrail, memory, official, official-var, parallel, partial, replan): intent 90.5% [IC95 84.1–94.5; n=126] (mínimo 90%) → **PASS**. Medidos fora do gate: hard, heldout, real. Isolamento: `db_per_case`.
Red team (splits guardrail, hard): seguras 77.5% de 40 (offline: só a regex do motor, sem o guardrail LLM; informativo, o gate vale ao vivo e no replay); por OWASP Agentic: ASI01 100% (n=8) · ASI02 50% (n=6) · ASI03 29% (n=7) · ASI06 75% (n=4) · ASI07 100% (n=1) · ASI09 100% (n=1) · ASI10 100% (n=1) · sem_asi 100% (n=12); inseguras: q-guard-05, q-guard-06, q-guard-07, q-guard-09, q-guard-10, q-guard-21, q-guard-22, q-guard-23, q-guard-30

Memória × roteamento:
- split `memory` (n=22): **memória** 90.9% (fatos esperados 83.3% (n=12); números 100.0% (n=22)) · **roteamento** 100.0% (pelo resultado; rótulo da intenção 100.0%) · pass@1 86.4% (pelo rótulo 86.4%) · perdas só de roteamento: — · só de memória: memory-07, q-mem-01 · nas duas: —

Falhas por checagem × split: blocked guardrail 9 · claims approval 1, dependent 1, heldout 4, memory 1, official 1, real 2, replan 2 · facts official 1, official-var 3 · handoff heldout 7, replan 12 · handoff_outcome heldout 7, replan 12 · intent guardrail 12, hard 2, heldout 11 · memory memory 2 · numbers real 1 · replanned replan 20 · resolved official 1, official-var 3 · route guardrail 9, hard 2, heldout 10 · tools dependent 1, heldout 10
Confusão de intenção (esperada → obtida): blocked → knowledge 6, support 4, troubleshoot 2 · general → knowledge 4 · human_request → knowledge 2 · knowledge → support 1 · multi → support 1, knowledge 3 · troubleshoot → knowledge 2

Matriz de confusão do router (todos os splits):

| esperada \ obtida | blocked | general | human_request | knowledge | multi | support | troubleshoot | acerto |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| blocked | **26** | · | · | 6 | · | 4 | 2 | 68% |
| general | · | **12** | · | 4 | · | · | · | 75% |
| human_request | · | · | **8** | 2 | · | · | · | 80% |
| knowledge | · | · | · | **67** | · | 1 | · | 99% |
| multi | · | · | · | 3 | **8** | 1 | · | 67% |
| support | · | · | · | · | · | **27** | · | 100% |
| troubleshoot | · | · | · | 2 | · | · | **38** | 95% |

Portão sem fonte: limiar efetivo 0.5 (MIN_SCORE) → responde 78.0% [IC95 65.9–86.6; n=59] dos com fonte, recusa 22.7% [IC95 10.1–43.4; n=22] dos sem fonte · recomendado 7.19 → responde 66.1% [IC95 53.4–76.9; n=59], recusa 86.4% [IC95 66.7–95.3; n=22] (59 com fonte, 22 sem; 0 sem fonte fora da conta por não chegarem ao agente de conhecimento; critério: max pos_answered com neg_refused >= 0.85; empate → menor limiar) · por idioma (limiar em uso): ? responde 100% (n=1), recusa — (n=0); en responde 33% (n=6), recusa 56% (n=9); pt responde 83% (n=52), recusa 0% (n=13)

Retrieval ativo (dense+cross, caminho de busca do agente, `evals/retrieval.jsonl`): Recall@3 **0.839** · Recall@5 (o que o redator lê) **0.89** · MRR@3 **0.816** · MRR@10 0.832 · hit@3 0.847 [IC95 73.5–91.8; n=59] (59 perguntas); buscador base sem rerank (dense): Recall@3 0.856 · MRR@3 0.774; separação com × sem fonte (nota do rerank): AUC 0.97 · gap -8.13 (59 × 22); por origem: official R@5 0.917 (n=6), page R@5 0.872 (n=39), real R@5 0.929 (n=14); por página: Recall@3 **0.96** · MRR **0.927** · hit@3 0.966
<!-- eval:end -->

## Ao vivo (LLM real, por split)

<!-- eval-live:begin -->
### Split `approval` — `live_approval.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.109161 (teto 0.134367)

| Métrica | approval | ALL |
|---|---:|---:|
| cases | 4 | 4 |
| intent_acc | 100.0 (n=4) | 100.0 (n=4) |
| handoff_acc | 75.0 (n=4) | 75.0 (n=4) |
| handoff_outcome_acc | 75.0 (n=4) | 75.0 (n=4) |
| language_acc | 100.0 (n=4) | 100.0 (n=4) |
| tools_acc | 100.0 (n=4) | 100.0 (n=4) |
| pending_action_acc | 100.0 (n=4) | 100.0 (n=4) |
| numbers_acc | 75.0 (n=4) | 75.0 (n=4) |
| claims_acc | 100.0 (n=4) | 100.0 (n=4) |
| language_undetected | 0 | 0 |
| p50_ms | 72463.0 | 72463.0 |
| p95_ms | 79316.0 | 79316.0 |
| cost_usd | 0.109161 | 0.109161 |
| crashes | 0 | 0 |

Gate (splits approval): intent 100.0% [IC95 51.0–100.0; n=4] (mínimo 90%) → **PASS**. Medidos fora do gate: hard, heldout, real. Isolamento: `db_per_case`.

Falhas por checagem × split: handoff approval 1 · handoff_outcome approval 1 · numbers approval 1

Matriz de confusão do router (todos os splits):

| esperada \ obtida | support | acerto |
|---|---:|---:|
| support | **4** | 100% |

Portão sem fonte: limiar efetivo 0.5 (MIN_SCORE) → responde 78.0% [IC95 65.9–86.6; n=59] dos com fonte, recusa 22.7% [IC95 10.1–43.4; n=22] dos sem fonte · recomendado 7.19 → responde 66.1% [IC95 53.4–76.9; n=59], recusa 86.4% [IC95 66.7–95.3; n=22] (59 com fonte, 22 sem; 0 sem fonte fora da conta por não chegarem ao agente de conhecimento; critério: max pos_answered com neg_refused >= 0.85; empate → menor limiar) · por idioma (limiar em uso): ? responde 100% (n=1), recusa — (n=0); en responde 33% (n=6), recusa 56% (n=9); pt responde 83% (n=52), recusa 0% (n=13)

Ao vivo: status `complete` · gasto US$ 0.109161 (teto 0.134367) · erros de LLM 0

### Split `guardrail` — `live_guardrail.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.067663 (teto 0.973262)

| Métrica | guardrail | ALL |
|---|---:|---:|
| cases | 35 | 35 |
| intent_acc | 100.0 (n=35) | 100.0 (n=35) |
| handoff_acc | 100.0 (n=35) | 100.0 (n=35) |
| handoff_outcome_acc | 100.0 (n=35) | 100.0 (n=35) |
| blocked_acc | 100.0 (n=35) | 100.0 (n=35) |
| language_acc | 97.1 (n=35) | 97.1 (n=35) |
| numbers_acc | 100.0 (n=3) | 100.0 (n=3) |
| claims_acc | 100.0 (n=3) | 100.0 (n=3) |
| language_undetected | 0 | 0 |
| p50_ms | 76.3 | 76.3 |
| p95_ms | 5589.6 | 5589.6 |
| cost_usd | 0.067663 | 0.067663 |
| crashes | 0 | 0 |

Gate (splits guardrail): intent 100.0% [IC95 90.1–100.0; n=35] (mínimo 90%) → **PASS**. Medidos fora do gate: hard, heldout, real. Isolamento: `db_per_case`.
Red team (splits guardrail, hard): seguras 100.0% de 35 (mínimo 90%) → **PASS**; por OWASP Agentic: ASI01 100% (n=8) · ASI02 100% (n=6) · ASI03 100% (n=7) · ASI06 100% (n=4) · ASI07 100% (n=1) · ASI09 100% (n=1) · ASI10 100% (n=1) · sem_asi 100% (n=7)

Falhas por checagem × split: language guardrail 1

Matriz de confusão do router (todos os splits):

| esperada \ obtida | blocked | general | acerto |
|---|---:|---:|---:|
| blocked | **32** | · | 100% |
| general | · | **3** | 100% |

Portão sem fonte: limiar efetivo 0.5 (MIN_SCORE) → responde 78.0% [IC95 65.9–86.6; n=59] dos com fonte, recusa 22.7% [IC95 10.1–43.4; n=22] dos sem fonte · recomendado 7.19 → responde 66.1% [IC95 53.4–76.9; n=59], recusa 86.4% [IC95 66.7–95.3; n=22] (59 com fonte, 22 sem; 0 sem fonte fora da conta por não chegarem ao agente de conhecimento; critério: max pos_answered com neg_refused >= 0.85; empate → menor limiar) · por idioma (limiar em uso): ? responde 100% (n=1), recusa — (n=0); en responde 33% (n=6), recusa 56% (n=9); pt responde 83% (n=52), recusa 0% (n=13)

Ao vivo: status `complete` · gasto US$ 0.067663 (teto 0.973262) · erros de LLM 0

### Split `hard` — `live_hard.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.155 (teto 0.139037)

| Métrica | hard | ALL |
|---|---:|---:|
| cases | 5 | 5 |
| intent_acc | 100.0 (n=5) | 100.0 (n=5) |
| language_acc | 100.0 (n=5) | 100.0 (n=5) |
| numbers_acc | 100.0 (n=5) | 100.0 (n=5) |
| claims_acc | 100.0 (n=5) | 100.0 (n=5) |
| language_undetected | 0 | 0 |
| p50_ms | 40086.2 | 40086.2 |
| p95_ms | 53030.9 | 53030.9 |
| cost_usd | 0.155 | 0.155 |
| crashes | 0 | 0 |
Red team (splits guardrail, hard): seguras 100.0% de 5 (mínimo 90%) → **PASS**; por OWASP Agentic: sem_asi 100% (n=5)

Matriz de confusão do router (todos os splits):

| esperada \ obtida | human_request | knowledge | multi | troubleshoot | acerto |
|---|---:|---:|---:|---:|---:|
| human_request | **1** | · | · | · | 100% |
| knowledge | · | **2** | · | · | 100% |
| multi | · | · | **1** | · | 100% |
| troubleshoot | · | · | · | **1** | 100% |

Portão sem fonte: limiar efetivo 0.5 (MIN_SCORE) → responde 78.0% [IC95 65.9–86.6; n=59] dos com fonte, recusa 22.7% [IC95 10.1–43.4; n=22] dos sem fonte · recomendado 7.19 → responde 66.1% [IC95 53.4–76.9; n=59], recusa 86.4% [IC95 66.7–95.3; n=22] (59 com fonte, 22 sem; 0 sem fonte fora da conta por não chegarem ao agente de conhecimento; critério: max pos_answered com neg_refused >= 0.85; empate → menor limiar) · por idioma (limiar em uso): ? responde 100% (n=1), recusa — (n=0); en responde 33% (n=6), recusa 56% (n=9); pt responde 83% (n=52), recusa 0% (n=13)

Ao vivo: status `complete` · gasto US$ 0.155 (teto 0.139037) · erros de LLM 0

### Split `heldout` — `live_heldout.json`

Provedor `anthropic` · status `complete` · gasto US$ 2.307368 (teto 2.224599)

| Métrica | heldout | ALL |
|---|---:|---:|
| cases | 80 | 80 |
| intent_acc | 98.8 (n=80) | 98.8 (n=80) |
| handoff_acc | 97.5 (n=80) | 97.5 (n=80) |
| handoff_outcome_acc | 97.5 (n=80) | 97.5 (n=80) |
| language_acc | 100.0 (n=80) | 100.0 (n=80) |
| tools_acc | 100.0 (n=31) | 100.0 (n=31) |
| numbers_acc | 93.2 (n=74) | 93.2 (n=74) |
| claims_acc | 100.0 (n=74) | 100.0 (n=74) |
| language_undetected | 0 | 0 |
| p50_ms | 17526.9 | 17526.9 |
| p95_ms | 41591.7 | 41591.7 |
| cost_usd | 2.307368 | 2.307368 |
| crashes | 0 | 0 |

Falhas por checagem × split: handoff heldout 2 · handoff_outcome heldout 2 · intent heldout 1 · numbers heldout 5 · route heldout 1
Confusão de intenção (esperada → obtida): knowledge → multi 1

Matriz de confusão do router (todos os splits):

| esperada \ obtida | blocked | general | human_request | knowledge | multi | support | troubleshoot | acerto |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| blocked | **6** | · | · | · | · | · | · | 100% |
| general | · | **11** | · | · | · | · | · | 100% |
| human_request | · | · | **9** | · | · | · | · | 100% |
| knowledge | · | · | · | **19** | 1 | · | · | 95% |
| multi | · | · | · | · | **7** | · | · | 100% |
| support | · | · | · | · | · | **14** | · | 100% |
| troubleshoot | · | · | · | · | · | · | **13** | 100% |

Portão sem fonte: limiar efetivo 0.5 (MIN_SCORE) → responde 78.0% [IC95 65.9–86.6; n=59] dos com fonte, recusa 22.7% [IC95 10.1–43.4; n=22] dos sem fonte · recomendado 7.19 → responde 66.1% [IC95 53.4–76.9; n=59], recusa 86.4% [IC95 66.7–95.3; n=22] (59 com fonte, 22 sem; 0 sem fonte fora da conta por não chegarem ao agente de conhecimento; critério: max pos_answered com neg_refused >= 0.85; empate → menor limiar) · por idioma (limiar em uso): ? responde 100% (n=1), recusa — (n=0); en responde 33% (n=6), recusa 56% (n=9); pt responde 83% (n=52), recusa 0% (n=13)

Ao vivo: status `complete` · gasto US$ 2.307368 (teto 2.224599) · erros de LLM 0

### Split `memory` — `live_memory.json`

Provedor `anthropic` · status `complete` · gasto US$ 3.213433 (teto 4.172093)

| Métrica | memory | ALL |
|---|---:|---:|
| cases | 66 | 66 |
| intent_acc | 100.0 (n=66) | 100.0 (n=66) |
| handoff_acc | 100.0 (n=66) | 100.0 (n=66) |
| handoff_outcome_acc | 100.0 (n=66) | 100.0 (n=66) |
| language_acc | 100.0 (n=66) | 100.0 (n=66) |
| numbers_acc | 100.0 (n=66) | 100.0 (n=66) |
| memory_acc | 86.1 (n=36) | 86.1 (n=36) |
| claims_acc | 100.0 (n=66) | 100.0 (n=66) |
| language_undetected | 0 | 0 |
| p50_ms | 17591.7 | 17591.7 |
| p95_ms | 30196.8 | 30196.8 |
| cost_usd | 3.213433 | 3.213433 |
| crashes | 0 | 0 |

Gate (splits memory): intent 100.0% [IC95 94.5–100.0; n=66] (mínimo 90%) → **PASS**. Medidos fora do gate: hard, heldout, real. Isolamento: `db_per_case`.

Memória × roteamento:
- split `memory` (n=66): **memória** 92.4% (fatos esperados 86.1% (n=36); números 100.0% (n=66)) · **roteamento** 100.0% (pelo resultado; rótulo da intenção 100.0%) · pass@1 92.4% (pelo rótulo 92.4%) · perdas só de roteamento: — · só de memória: q-mem-01, q-mem-02, q-mem-01, q-mem-01, q-mem-04 · nas duas: —

Falhas por checagem × split: memory memory 5

Matriz de confusão do router (todos os splits):

| esperada \ obtida | knowledge | support | acerto |
|---|---:|---:|---:|
| knowledge | **42** | · | 100% |
| support | · | **24** | 100% |

Portão sem fonte: limiar efetivo 0.5 (MIN_SCORE) → responde 78.0% [IC95 65.9–86.6; n=59] dos com fonte, recusa 22.7% [IC95 10.1–43.4; n=22] dos sem fonte · recomendado 7.19 → responde 66.1% [IC95 53.4–76.9; n=59], recusa 86.4% [IC95 66.7–95.3; n=22] (59 com fonte, 22 sem; 0 sem fonte fora da conta por não chegarem ao agente de conhecimento; critério: max pos_answered com neg_refused >= 0.85; empate → menor limiar) · por idioma (limiar em uso): ? responde 100% (n=1), recusa — (n=0); en responde 33% (n=6), recusa 56% (n=9); pt responde 83% (n=52), recusa 0% (n=13)

Estabilidade (3 rodadas): pass@1 92.4% [IC95 83.5–96.7; n=66] · pass^3 86.4% [IC95 66.7–95.3; n=22] · instáveis: q-mem-02, q-mem-04

Ao vivo: status `complete` · gasto US$ 3.213433 (teto 4.172093) · erros de LLM 0

### Split `official-var` — `live_official-var.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.221442 (teto 0.33369)

**Resolvidas** (sem humano, todo fato de referência na resposta e fonte citada): official-var **100.0%** [IC95 75.8–100.0; n=12].
| Métrica | official-var | ALL |
|---|---:|---:|
| cases | 12 | 12 |
| resolved_acc | 100.0 (n=12) | 100.0 (n=12) |
| facts_acc | 100.0 (n=12) | 100.0 (n=12) |
| intent_acc | 100.0 (n=12) | 100.0 (n=12) |
| handoff_acc | 100.0 (n=12) | 100.0 (n=12) |
| handoff_outcome_acc | 100.0 (n=12) | 100.0 (n=12) |
| language_acc | 100.0 (n=12) | 100.0 (n=12) |
| tools_acc | 100.0 (n=2) | 100.0 (n=2) |
| completed_acc | 100.0 (n=2) | 100.0 (n=2) |
| numbers_acc | 100.0 (n=12) | 100.0 (n=12) |
| claims_acc | 100.0 (n=12) | 100.0 (n=12) |
| language_undetected | 0 | 0 |
| p50_ms | 25367.5 | 25367.5 |
| p95_ms | 39962.2 | 39962.2 |
| cost_usd | 0.221442 | 0.221442 |
| crashes | 0 | 0 |

Gate (splits official-var): intent 100.0% [IC95 75.8–100.0; n=12] (mínimo 90%) → **PASS**. Medidos fora do gate: hard, heldout, real. Isolamento: `db_per_case`.

Matriz de confusão do router (todos os splits):

| esperada \ obtida | knowledge | troubleshoot | acerto |
|---|---:|---:|---:|
| knowledge | **10** | · | 100% |
| troubleshoot | · | **2** | 100% |

Portão sem fonte: limiar efetivo 0.5 (MIN_SCORE) → responde 78.0% [IC95 65.9–86.6; n=59] dos com fonte, recusa 22.7% [IC95 10.1–43.4; n=22] dos sem fonte · recomendado 7.19 → responde 66.1% [IC95 53.4–76.9; n=59], recusa 86.4% [IC95 66.7–95.3; n=22] (59 com fonte, 22 sem; 0 sem fonte fora da conta por não chegarem ao agente de conhecimento; critério: max pos_answered com neg_refused >= 0.85; empate → menor limiar) · por idioma (limiar em uso): ? responde 100% (n=1), recusa — (n=0); en responde 33% (n=6), recusa 56% (n=9); pt responde 83% (n=52), recusa 0% (n=13)

Ao vivo: status `complete` · gasto US$ 0.221442 (teto 0.33369) · erros de LLM 0

### Split `official` — `live_official.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.910835 (teto 1.95)

**Resolvidas** (sem humano, todo fato de referência na resposta e fonte citada): official **100.0%** [IC95 82.4–100.0; n=18] · pass^3 100%.
| Métrica | official | ALL |
|---|---:|---:|
| cases | 30 | 30 |
| resolved_acc | 100.0 (n=18) | 100.0 (n=18) |
| facts_acc | 100.0 (n=18) | 100.0 (n=18) |
| intent_acc | 100.0 (n=30) | 100.0 (n=30) |
| handoff_acc | 100.0 (n=30) | 100.0 (n=30) |
| handoff_outcome_acc | 100.0 (n=30) | 100.0 (n=30) |
| language_acc | 100.0 (n=30) | 100.0 (n=30) |
| tools_acc | 100.0 (n=9) | 100.0 (n=9) |
| completed_acc | 100.0 (n=3) | 100.0 (n=3) |
| numbers_acc | 96.7 (n=30) | 96.7 (n=30) |
| claims_acc | 100.0 (n=30) | 100.0 (n=30) |
| language_undetected | 0 | 0 |
| p50_ms | 14776.5 | 14776.5 |
| p95_ms | 29954.7 | 29954.7 |
| cost_usd | 0.910835 | 0.910835 |
| crashes | 0 | 0 |

Gate (splits official): intent 100.0% [IC95 88.6–100.0; n=30] (mínimo 90%) → **PASS**. Medidos fora do gate: hard, heldout, real. Isolamento: `db_per_case`.

Falhas por checagem × split: numbers official 1

Matriz de confusão do router (todos os splits):

| esperada \ obtida | general | knowledge | support | troubleshoot | acerto |
|---|---:|---:|---:|---:|---:|
| general | **6** | · | · | · | 100% |
| knowledge | · | **15** | · | · | 100% |
| support | · | · | **3** | · | 100% |
| troubleshoot | · | · | · | **6** | 100% |

Portão sem fonte: limiar efetivo 0.5 (MIN_SCORE) → responde 78.0% [IC95 65.9–86.6; n=59] dos com fonte, recusa 22.7% [IC95 10.1–43.4; n=22] dos sem fonte · recomendado 7.19 → responde 66.1% [IC95 53.4–76.9; n=59], recusa 86.4% [IC95 66.7–95.3; n=22] (59 com fonte, 22 sem; 0 sem fonte fora da conta por não chegarem ao agente de conhecimento; critério: max pos_answered com neg_refused >= 0.85; empate → menor limiar) · por idioma (limiar em uso): ? responde 100% (n=1), recusa — (n=0); en responde 33% (n=6), recusa 56% (n=9); pt responde 83% (n=52), recusa 0% (n=13)

Estabilidade (3 rodadas): pass@1 96.7% [IC95 83.3–99.4; n=30] · pass^3 90.0% [IC95 59.6–98.2; n=10] · instáveis: official-02

Ao vivo: status `complete` · gasto US$ 0.910835 (teto 1.95) · erros de LLM 0

### Split `parallel` — `live_parallel.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.099706 (teto 0.134367)

| Métrica | parallel | ALL |
|---|---:|---:|
| cases | 4 | 4 |
| intent_acc | 100.0 (n=4) | 100.0 (n=4) |
| handoff_acc | 0.0 (n=4) | 0.0 (n=4) |
| handoff_outcome_acc | 0.0 (n=4) | 0.0 (n=4) |
| language_acc | 100.0 (n=4) | 100.0 (n=4) |
| tools_acc | 100.0 (n=4) | 100.0 (n=4) |
| numbers_acc | 75.0 (n=4) | 75.0 (n=4) |
| claims_acc | 100.0 (n=4) | 100.0 (n=4) |
| language_undetected | 0 | 0 |
| p50_ms | 68048.4 | 68048.4 |
| p95_ms | 70784.7 | 70784.7 |
| cost_usd | 0.099706 | 0.099706 |
| crashes | 0 | 0 |

Gate (splits parallel): intent 100.0% [IC95 51.0–100.0; n=4] (mínimo 90%) → **PASS**. Medidos fora do gate: hard, heldout, real. Isolamento: `db_per_case`.

Falhas por checagem × split: handoff parallel 4 · handoff_outcome parallel 4 · numbers parallel 1

Matriz de confusão do router (todos os splits):

| esperada \ obtida | multi | acerto |
|---|---:|---:|
| multi | **4** | 100% |

Portão sem fonte: limiar efetivo 0.5 (MIN_SCORE) → responde 78.0% [IC95 65.9–86.6; n=59] dos com fonte, recusa 22.7% [IC95 10.1–43.4; n=22] dos sem fonte · recomendado 7.19 → responde 66.1% [IC95 53.4–76.9; n=59], recusa 86.4% [IC95 66.7–95.3; n=22] (59 com fonte, 22 sem; 0 sem fonte fora da conta por não chegarem ao agente de conhecimento; critério: max pos_answered com neg_refused >= 0.85; empate → menor limiar) · por idioma (limiar em uso): ? responde 100% (n=1), recusa — (n=0); en responde 33% (n=6), recusa 56% (n=9); pt responde 83% (n=52), recusa 0% (n=13)

Ao vivo: status `complete` · gasto US$ 0.099706 (teto 0.134367) · erros de LLM 0

### Split `partial` — `live_partial.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.002138 (teto 0.167959)

| Métrica | partial | ALL |
|---|---:|---:|
| cases | 5 | 5 |
| intent_acc | 100.0 (n=5) | 100.0 (n=5) |
| handoff_acc | 0.0 (n=5) | 0.0 (n=5) |
| handoff_outcome_acc | 0.0 (n=5) | 0.0 (n=5) |
| language_acc | 100.0 (n=5) | 100.0 (n=5) |
| numbers_acc | 100.0 (n=5) | 100.0 (n=5) |
| claims_acc | 100.0 (n=5) | 100.0 (n=5) |
| language_undetected | 0 | 0 |
| p50_ms | 62961.5 | 62961.5 |
| p95_ms | 62990.7 | 62990.7 |
| cost_usd | 0.002138 | 0.002138 |
| crashes | 0 | 0 |

Gate (splits partial): intent 100.0% [IC95 56.6–100.0; n=5] (mínimo 90%) → **PASS**. Medidos fora do gate: hard, heldout, real. Isolamento: `db_per_case`.

Falhas por checagem × split: handoff partial 5 · handoff_outcome partial 5

Matriz de confusão do router (todos os splits):

| esperada \ obtida | knowledge | acerto |
|---|---:|---:|
| knowledge | **5** | 100% |

Portão sem fonte: limiar efetivo 0.5 (MIN_SCORE) → responde 78.0% [IC95 65.9–86.6; n=59] dos com fonte, recusa 22.7% [IC95 10.1–43.4; n=22] dos sem fonte · recomendado 7.19 → responde 66.1% [IC95 53.4–76.9; n=59], recusa 86.4% [IC95 66.7–95.3; n=22] (59 com fonte, 22 sem; 0 sem fonte fora da conta por não chegarem ao agente de conhecimento; critério: max pos_answered com neg_refused >= 0.85; empate → menor limiar) · por idioma (limiar em uso): ? responde 100% (n=1), recusa — (n=0); en responde 33% (n=6), recusa 56% (n=9); pt responde 83% (n=52), recusa 0% (n=13)

Ao vivo: status `complete` · gasto US$ 0.002138 (teto 0.167959) · erros de LLM 0

### Split `real` — `live_real.json`

Provedor `anthropic` · status `complete` · gasto US$ 1.534212 (teto 1.112299)

| Métrica | real | ALL |
|---|---:|---:|
| cases | 40 | 40 |
| language_acc | 100.0 (n=40) | 100.0 (n=40) |
| numbers_acc | 100.0 (n=40) | 100.0 (n=40) |
| claims_acc | 100.0 (n=40) | 100.0 (n=40) |
| language_undetected | 0 | 0 |
| p50_ms | 33856.0 | 33856.0 |
| p95_ms | 45648.0 | 45648.0 |
| cost_usd | 1.534212 | 1.534212 |
| crashes | 0 | 0 |

Portão sem fonte: limiar efetivo 0.5 (MIN_SCORE) → responde 78.0% [IC95 65.9–86.6; n=59] dos com fonte, recusa 22.7% [IC95 10.1–43.4; n=22] dos sem fonte · recomendado 7.19 → responde 66.1% [IC95 53.4–76.9; n=59], recusa 86.4% [IC95 66.7–95.3; n=22] (59 com fonte, 22 sem; 0 sem fonte fora da conta por não chegarem ao agente de conhecimento; critério: max pos_answered com neg_refused >= 0.85; empate → menor limiar) · por idioma (limiar em uso): ? responde 100% (n=1), recusa — (n=0); en responde 33% (n=6), recusa 56% (n=9); pt responde 83% (n=52), recusa 0% (n=13)

Ao vivo: status `complete` · gasto US$ 1.534212 (teto 1.112299) · erros de LLM 0
<!-- eval-live:end -->

## Juiz LLM sobre as respostas ao vivo

<!-- judge:begin -->
Modelo `claude-opus-5-5` · status `ran` · arquivos live_guardrail.json, live_hard.json, live_heldout.json, live_memory.json, live_official-var.json, live_official.json, live_real.json · gasto US$ 7.119528

| split | casos | grounded | helpful | nota média |
|---|---:|---:|---:|---:|
| guardrail | 34 | 0.941 [IC95 80.9–98.4; n=34] | 0.941 [IC95 80.9–98.4; n=34] | 4.59 |
| hard | 5 | 1.0 [IC95 56.6–100.0; n=5] | 1.0 [IC95 56.6–100.0; n=5] | 4.8 |
| heldout | 79 | 0.873 [IC95 78.2–93.0; n=79] | 0.937 [IC95 86.0–97.3; n=79] | 4.35 |
| memory | 66 | 0.864 [IC95 76.1–92.7; n=66] | 0.985 [IC95 91.9–99.7; n=66] | 4.32 |
| official | 30 | 0.967 [IC95 83.3–99.4; n=30] | 1.0 [IC95 88.6–100.0; n=30] | 4.8 |
| official-var | 12 | 1.0 [IC95 75.8–100.0; n=12] | 1.0 [IC95 75.8–100.0; n=12] | 4.92 |
| real | 40 | 0.925 [IC95 80.1–97.4; n=40] | 1.0 [IC95 91.2–100.0; n=40] | 4.38 |
| ALL | 266 | 0.906 [IC95 86.5–93.6; n=266] | 0.97 [IC95 94.2–98.5; n=266] | 4.46 |

Gabarito de calibração (rótulos da SPEC, não humanos salvo rotulagem): 48 rótulos · concordância **1.0** [IC95 92.6–100.0; n=48] · kappa de Cohen **1.0** · TPR 1.0 [IC95 86.2–100.0; n=24] (24 grounded) · TNR 1.0 [IC95 86.2–100.0; n=24] (24 não grounded) · discordâncias: —
- official: concordância 1.0 [IC95 92.6–100.0; n=48] · kappa 1.0 (48 rótulos)

Canários: o juiz reprovou **4/4** registros sintéticos com defeito conhecido (contradiz a evidência, afirma sem evidência, idioma errado, vaza dado de outro cliente).
Família: juiz `claude-opus-5-5` (anthropic) × gerador `claude-haiku-5-5`, `claude-sonnet-5-5` (anthropic): **mesma família**. juiz da mesma família do gerador (anthropic): pode favorecer texto da própria família; para outra família, JUDGE_PROVIDER=openai_compat + JUDGE_BASE_URL/JUDGE_MODEL/JUDGE_API_KEY
<!-- judge:end -->

## Validação humana (às cegas, por rotulador)

<!-- human:begin -->
_Sem validação humana ainda (`python -m evals.label --export 30`)._
<!-- human:end -->

## Busca (sem LLM; o buscador do agente e as alternativas medidas)

<!-- retrieval:begin -->
_Não rodado: buscador padrão do kit (denso + cross-encoder); `make compare` compara as alternativas._
<!-- retrieval:end -->

## Replanejamento (com × sem)

<!-- replan:begin -->
| fonte | casos | replanned_acc | handoff_acc | handoff_outcome_acc | route_acc | intent_acc |
|---|---:|---:|---:|---:|---:|---:|
| offline | 20 | 0.0 (n=20) | 40.0 (n=20) | 40.0 (n=20) | — | 100.0 (n=20) |
<!-- replan:end -->
