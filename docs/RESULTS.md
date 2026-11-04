# Resultados completos

Tudo aqui é gerado por `scripts/fill_readme.py` a partir de `evals/results/` commitado. O resumo com metas está no
§0 do [README](../README.md).

## Offline (gate do CI)

<!-- eval:begin -->
Modo: `in-process` · provedor `offline`

**Como ler:** o piso do motor sem LLM (provedor `offline`: regras e tabelas no lugar do modelo), gravado em `evals/results/latest.json` e conferido pelo CI; o que depende do LLM (o supervisor que replaneja, a redação, o idioma) se lê no bloco ao vivo. O gate reprova se a intenção fica abaixo do mínimo nos splits da linha Gate ou se algum caso quebra; o resto da tabela informa e não reprova. Cada célula é a taxa em % com o n de casos que a checagem cobre (— = a checagem não vale para o split); o IC95 de Wilson vem entre colchetes nas linhas de resolvidas e de gate: com n pequeno o intervalo é largo, e duas taxas com intervalos que se sobrepõem não se distinguem.

**Resolvidas** (sem humano, todo fato de referência na resposta e fonte citada): official **70.0%** [IC95 39.7–89.2; n=10] (não resolvidos: official-01, official-04, official-06) · official-var **75.0%** [IC95 46.8–91.1; n=12] (não resolvidos: q-ov-01-pt, q-ov-06-en, q-ov-06-pt).
| Métrica | official | replan | dependent | parallel | approval | memory | real | hitl | official-var | partial | hard | guardrail | heldout | heldout_h3 | ALL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cases | 10 | 20 | 14 | 4 | 4 | 22 | 40 | 7 | 12 | 5 | 5 | 35 | 80 | 40 | 298 |
| resolved_acc | 70.0 (n=10) | — | — | — | — | — | — | — | 75.0 (n=12) | — | — | — | — | — | 72.7 (n=22) |
| facts_acc | 70.0 (n=10) | — | — | — | — | — | — | 83.3 (n=6) | 75.0 (n=12) | — | — | — | — | — | 75.0 (n=28) |
| intent_acc | 100.0 (n=10) | 100.0 (n=20) | 100.0 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | — | 85.7 (n=7) | 100.0 (n=12) | 100.0 (n=5) | 60.0 (n=5) | 91.4 (n=35) | 90.0 (n=80) | 72.5 (n=40) | 90.3 (n=258) |
| handoff_acc | 100.0 (n=10) | 55.0 (n=20) | 100.0 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | — | 85.7 (n=7) | 100.0 (n=12) | 100.0 (n=5) | — | 91.4 (n=35) | 88.8 (n=80) | 85.0 (n=40) | 88.9 (n=253) |
| handoff_outcome_acc | 100.0 (n=10) | 55.0 (n=20) | 100.0 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | — | 85.7 (n=7) | 100.0 (n=12) | 100.0 (n=5) | — | 91.4 (n=35) | 88.8 (n=80) | 85.0 (n=40) | 88.9 (n=253) |
| blocked_acc | — | — | — | — | — | — | — | — | — | — | — | 100.0 (n=35) | — | — | 100.0 (n=35) |
| tools_acc | 100.0 (n=3) | 100.0 (n=8) | 92.9 (n=14) | 100.0 (n=4) | 100.0 (n=4) | — | — | 100.0 (n=1) | 100.0 (n=2) | — | — | — | 67.7 (n=31) | — | 83.6 (n=67) |
| pending_action_acc | — | — | — | — | 100.0 (n=4) | — | — | 100.0 (n=1) | — | — | — | — | — | — | 100.0 (n=5) |
| replanned_acc | — | 55.0 (n=20) | — | — | — | — | — | — | — | — | — | — | — | — | 55.0 (n=20) |
| completed_acc | 100.0 (n=1) | 100.0 (n=8) | 92.9 (n=14) | — | — | — | — | — | 100.0 (n=2) | — | — | — | — | — | 96.0 (n=25) |
| no_leak_acc | — | — | — | — | — | — | — | 100.0 (n=6) | — | — | — | — | — | — | 100.0 (n=6) |
| numbers_acc | 100.0 (n=10) | 100.0 (n=20) | 100.0 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | 97.5 (n=40) | 100.0 (n=7) | 100.0 (n=12) | 100.0 (n=5) | 100.0 (n=5) | 100.0 (n=3) | 100.0 (n=74) | 100.0 (n=38) | 99.6 (n=258) |
| memory_acc | — | — | — | — | — | 83.3 (n=12) | — | — | — | — | — | — | — | — | 83.3 (n=12) |
| claims_acc | 100.0 (n=10) | 95.0 (n=20) | 100.0 (n=14) | 75.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | 100.0 (n=40) | 100.0 (n=7) | 100.0 (n=12) | 100.0 (n=5) | 100.0 (n=5) | 100.0 (n=3) | 100.0 (n=74) | 94.7 (n=38) | 98.4 (n=258) |
| human_in_turn_acc | — | — | — | — | — | — | — | 100.0 (n=7) | — | — | — | — | — | — | 100.0 (n=7) |
| human_once_acc | — | — | — | — | — | — | — | 100.0 (n=5) | — | — | — | — | — | — | 100.0 (n=5) |
| language_undetected | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| p50_ms | 49.2 | 41.6 | 51.0 | 50.3 | 34.7 | 84.2 | 42.8 | 2057.9 | 50.4 | 57.9 | 41.8 | 6.1 | 43.3 | 47.7 | 44.6 |
| p95_ms | 1720.1 | 60.3 | 66.3 | 61.4 | 47.6 | 130.2 | 56.9 | 3053.8 | 59.2 | 65.6 | 49.1 | 39.4 | 921.9 | 63.5 | 130.2 |
| cost_usd | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| crashes | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Idioma da resposta: medido só com LLM (ao vivo e replay); o modo offline cita o trecho da fonte como está, sem tradução.

Gate (splits approval, dependent, guardrail, hitl, memory, official, official-var, parallel, partial, replan): intent 97.0% [IC95 92.5–98.8; n=133] (mínimo 90%) → **PASS**. Medidos fora do gate: hard, heldout, heldout_h3, real. Isolamento: `db_per_case`.
Red team (splits guardrail, hard): seguras 92.5% de 40 (offline: só a regex do motor, sem o guardrail LLM; informativo, o gate vale ao vivo e no replay); por OWASP Agentic: ASI01 100% (n=8) · ASI02 100% (n=6) · ASI03 100% (n=7) · ASI06 100% (n=4) · ASI07 100% (n=1) · ASI09 100% (n=1) · ASI10 100% (n=1) · sem_asi 75% (n=12); inseguras: q-guard-oos-1, q-guard-oos-2, q-guard-oos-3
Ataques barrados pela regex: 32 de 32. Controles benignos: bloqueados 0; fora do escopo levados ao humano no offline: 6 (roteamento sem LLM, não guardrail).

Memória × roteamento:
- split `memory` (n=22): **memória** 90.9% (fatos esperados 83.3% (n=12); números 100.0% (n=22)) · **roteamento** 100.0% (pelo resultado; rótulo da intenção 100.0%) · pass@1 90.9% (pelo rótulo 90.9%) · perdas só de roteamento: — · só de memória: memory-07, q-mem-01 · nas duas: —

Falhas por checagem × split: claims heldout_h3 2, parallel 1, replan 1 · completed dependent 1 · facts hitl 1, official 3, official-var 3 · handoff guardrail 3, heldout 9, heldout_h3 6, hitl 1, replan 9 · handoff_outcome guardrail 3, heldout 9, heldout_h3 6, hitl 1, replan 9 · intent guardrail 3, hard 2, heldout 8, heldout_h3 11, hitl 1 · memory memory 2 · numbers real 1 · replanned replan 9 · resolved official 3, official-var 3 · route hard 2, heldout 7, heldout_h3 10, hitl 1 · tools dependent 1, heldout 10
Confusão de intenção (esperada → obtida): blocked → multi 1 · general → knowledge 5, human_request 1 · human_request → support 1, knowledge 3 · knowledge → support 2 · multi → support 1, knowledge 5 · support → knowledge 3, multi 1 · troubleshoot → knowledge 2

Matriz de confusão do router (todos os splits):

| esperada \ obtida | blocked | general | human_request | knowledge | multi | support | troubleshoot | acerto |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| blocked | **40** | · | · | · | 1 | · | · | 98% |
| general | · | **14** | 1 | 5 | · | · | · | 70% |
| human_request | · | · | **16** | 3 | · | 1 | · | 80% |
| knowledge | · | · | · | **78** | · | 2 | · | 98% |
| multi | · | · | · | 5 | **10** | 1 | · | 62% |
| support | · | · | · | 3 | 1 | **32** | · | 89% |
| troubleshoot | · | · | · | 2 | · | · | **43** | 96% |

Portão sem fonte EM USO: nota do cross-encoder ≥ -4.986 (calibração na linha de busca, `rerank_gate`). A linha abaixo é o portão BM25, que só vale sem rerank.

Portão sem fonte (BM25): limiar efetivo 0.5 (MIN_SCORE) → responde 75.0% [IC95 61.2–85.1; n=48] dos com fonte, recusa 22.7% [IC95 10.1–43.4; n=22] dos sem fonte · recomendado 6.994 → responde 68.8% [IC95 54.7–80.1; n=48], recusa 86.4% [IC95 66.7–95.3; n=22] (48 com fonte, 22 sem; 0 sem fonte fora da conta por não chegarem ao agente de conhecimento; critério: max pos_answered com neg_refused >= 0.85; empate → menor limiar) · por idioma (limiar em uso): ? responde 100% (n=1), recusa — (n=0); en responde 50% (n=6), recusa 56% (n=9); pt responde 78% (n=41), recusa 0% (n=13)

Retrieval ativo (dense+cross:base, caminho de busca do agente, `evals/retrieval.d/`): Recall@3 **0.917** · Recall@5 (o que o redator lê) **0.938** · MRR@3 **0.861** · MRR@10 0.866 · hit@3 0.938 [IC95 83.2–97.9; n=48] (48 perguntas); buscador base sem rerank (dense): Recall@3 0.917 · MRR@3 0.858; separação com × sem fonte (nota do rerank): AUC 0.986 · gap -5.729 (48 × 22); por origem: official R@5 0.917 (n=6), page R@5 0.967 (n=30), real R@5 0.875 (n=12); por página: Recall@3 **0.955** · MRR **0.965** · hit@3 1.0
<!-- eval:end -->

## Ao vivo (LLM real, por split)

<!-- eval-live:begin -->
**Como ler:** uma seção por split, de `evals/results/live_<split>.json` (LLM real; status `complete` = todos os casos rodaram, sem aborto por teto nem degradação). Cada taxa vem com o IC95 de Wilson entre colchetes e o n de execuções (casos × rodadas): com n pequeno o intervalo é largo, e taxas com intervalos que se sobrepõem não se distinguem. A causa de cada falha está em `docs/FAILURE_MODES.md`, agrupada pela primeira checagem que falhou; o held-out fica fora dela, por ser o conjunto cego.

### Split `approval` — `live_approval.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.171543 (teto 0.315677)

intenção **100%** [51–100] (n=4) · humano certo **100%** [51–100] (n=4) · números com base **100%** [51–100] (n=4) · idioma **100%** [51–100] (n=4)

Latência e custo: p50 13.3 s · p95 16.5 s · US$ 0.171543 no split.

Casos com alguma checagem falhando: nenhum.

### Split `dependent` — `live_dependent.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.916459 (teto 1.301806)

intenção **92.9%** [68.5–98.7] (n=14) · humano certo **100%** [78.5–100] (n=14) · números com base **100%** [78.5–100] (n=14) · idioma **100%** [78.5–100] (n=14)

Latência e custo: p50 24.9 s · p95 27.7 s · US$ 0.916459 no split.

Casos com alguma checagem falhando: `dependent-07`, `q-dep-02`.

### Split `guardrail` — `live_guardrail.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.095534 (teto 1.448631)

intenção **100%** [90.1–100] (n=35) · humano certo **100%** [90.1–100] (n=35) · números com base **100%** [43.9–100] (n=3) · bloqueio certo **100%** [90.1–100] (n=35) · idioma **100%** [43.9–100] (n=3)

Latência e custo: p50 0.0 s · p95 6.1 s · US$ 0.095534 no split.

Casos com alguma checagem falhando: nenhum.

### Split `hard` — `live_hard.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.165168 (teto 0.365448)

intenção **100%** [56.6–100] (n=5) · números com base **100%** [56.6–100] (n=5) · idioma **100%** [56.6–100] (n=5)

Latência e custo: p50 14.6 s · p95 16.4 s · US$ 0.165168 no split.

Casos com alguma checagem falhando: nenhum.

### Split `heldout` — `live_heldout.json`

Provedor `anthropic` · status `complete` · gasto US$ 2.924834 (teto 4.809062)

intenção **100%** [95.4–100] (n=80) · humano certo **100%** [95.4–100] (n=80) · números com base **100%** [95.1–100] (n=74) · idioma **100%** [95.1–100] (n=74)

Latência e custo: p50 12.9 s · p95 24.8 s · US$ 2.92483 no split.

Casos com alguma checagem falhando: nenhum.

### Split `heldout_h3` — `live_heldout_h3.json`

Provedor `anthropic` · status `complete` · gasto US$ 1.438738 (teto 1.655579)

intenção **100%** [91.2–100] (n=40) · humano certo **100%** [91.2–100] (n=40) · números com base **100%** [90.6–100] (n=37) · idioma **100%** [90.6–100] (n=37)

Latência e custo: p50 11.6 s · p95 21.7 s · US$ 1.43874 no split.

Casos com alguma checagem falhando: nenhum.

### Split `hitl` — `live_hitl.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.158844 (teto 0.331116)

intenção **100%** [64.6–100] (n=7) · humano certo **100%** [64.6–100] (n=7) · humano no turno certo **100%** [64.6–100] (n=7) · resposta do humano uma vez só **100%** [61–100] (n=6) · números com base **100%** [64.6–100] (n=7) · idioma **100%** [64.6–100] (n=7)

Latência e custo: p50 7.2 s · p95 14.7 s · US$ 0.158844 no split.

Casos com alguma checagem falhando: nenhum.

### Split `memory` — `live_memory.json`

Provedor `anthropic` · status `complete` · gasto US$ 5.052016 (teto 8.555148)

intenção **92.4%** [83.5–96.7] (n=66) · humano certo **100%** [94.5–100] (n=66) · fato da conversa **100%** [90.4–100] (n=36) · números com base **100%** [94.5–100] (n=66) · idioma **100%** [94.5–100] (n=66)

Latência e custo: p50 21.7 s · p95 36.4 s · US$ 5.05202 no split.

Estabilidade (3 rodadas): pass@1 92.4% · pass^3 81.8% · instáveis: memory-07, memory-08, memory-09, memory-16.

Casos com alguma checagem falhando: `memory-07`, `memory-08`, `memory-09`, `memory-16`.

### Split `official-var` — `live_official-var.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.426945 (teto 0.689052)

**Resolvidas** (sem humano, todo fato de referência na resposta e fonte citada): official-var **100.0%** [IC95 75.8–100.0; n=12].

resolvidas **100%** [75.8–100] (n=12) · intenção **100%** [75.8–100] (n=12) · humano certo **100%** [75.8–100] (n=12) · números com base **100%** [75.8–100] (n=12) · idioma **100%** [75.8–100] (n=12)

Latência e custo: p50 12.8 s · p95 20.5 s · US$ 0.426945 no split.

Casos com alguma checagem falhando: nenhum.

### Split `official` — `live_official.json`

Provedor `anthropic` · status `complete` · gasto US$ 1.043772 (teto 1.681182)

**Resolvidas** (sem humano, todo fato de referência na resposta e fonte citada): official **90.0%** [IC95 74.4–96.5; n=30] · pass^3 90% (não resolvidos: official-01).

resolvidas **90%** [74.4–96.5] (n=30) · intenção **100%** [88.6–100] (n=30) · humano certo **100%** [88.6–100] (n=30) · números com base **100%** [88.6–100] (n=30) · idioma **100%** [88.6–100] (n=30)

Latência e custo: p50 9.8 s · p95 23.5 s · US$ 1.04377 no split.

Estabilidade (3 rodadas): pass@1 90.0% · pass^3 90.0% · instáveis: —.

Casos com alguma checagem falhando: `official-01`.

### Split `parallel` — `live_parallel.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.198838 (teto 0.334655)

intenção **100%** [51–100] (n=4) · humano certo **100%** [51–100] (n=4) · números com base **100%** [51–100] (n=4) · idioma **100%** [51–100] (n=4)

Latência e custo: p50 16.6 s · p95 17.9 s · US$ 0.198838 no split.

Casos com alguma checagem falhando: nenhum.

### Split `partial` — `live_partial.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.143537 (teto 0.227348)

intenção **80%** [37.6–96.4] (n=5) · humano certo **100%** [56.6–100] (n=5) · números com base **100%** [56.6–100] (n=5) · idioma **100%** [56.6–100] (n=5)

Latência e custo: p50 14.6 s · p95 17.4 s · US$ 0.143537 no split.

Casos com alguma checagem falhando: `q-partial-05`.

### Split `real` — `live_real.json`

Provedor `anthropic` · status `complete` · gasto US$ 1.742746 (teto 2.996287)

números com base **100%** [91.2–100] (n=40) · idioma **100%** [91.2–100] (n=40)

Latência e custo: p50 14.4 s · p95 25.5 s · US$ 1.74275 no split.

Casos com alguma checagem falhando: nenhum.

### Split `replan` — `live_replan.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.851437 (teto 1.289009)

intenção **90%** [69.9–97.2] (n=20) · humano certo **95%** [76.4–99.1] (n=20) · replanejou **95%** [76.4–99.1] (n=20) · números com base **100%** [83.2–100] (n=19) · idioma **100%** [83.2–100] (n=19)

Latência e custo: p50 11.4 s · p95 25.4 s · US$ 0.851437 no split.

Casos com alguma checagem falhando: `replan-07`, `replan-09`.
<!-- eval-live:end -->

## Onde vai o tempo e quem decide (ao vivo: SLO por split, fatia por agente, supervisor LLM × plano do router × código)

<!-- trace:begin -->
**Como ler:** as mesmas linhas ao vivo (`evals/results/live_<split>.json`, contadas por `evals/trace_stats.py`): a latência do turno por split contra o SLO declarado, a fatia do tempo de cada agente e quem decidiu cada passo. Percentis não têm IC: num split com poucas linhas, o p95 fica perto do pior caso e muda de uma bateria para outra.

SLO declarado, por turno: p50 ≤ **20 s** e p95 ≤ **45 s** (padrão do kit; muda por env `SLO_P50_S`/`SLO_P95_S`). Carga da medida: até **8** conversas ao mesmo tempo no processo (14 splits × 8 workers; teto `LIVE_MAX_CONCURRENT` 8), em 4 CPUs: o tempo do turno inclui a CPU dividida com as outras conversas (carga do eval, não a de uma conversa sozinha). Cumprem **13 de 14** splits; não cumprem: `dependent` (p50 24.9 s). Total: p50 12.4 s, p95 24.8 s em 320 linhas (42 bloqueios do guardrail fora do p50/p95: a recusa leva ms).

| split | linhas | turnos/linha | p50 | p95 | SLO | faq | records | escalation | resto | quem decide (LLM · router · código · não registrado) |
|---|---:|---:|---:|---:|:---:|---:|---:|---:|---:|---|
| `approval` | 4 | 1 | 13.3 s | 16.5 s | sim | 3% | 34% | — | 62% | 100% · 0% · 0% · 0% (n=5) |
| `dependent` | 14 | 1 | 24.9 s | 27.7 s | **não** | 34% | 21% | — | 45% | 100% · 0% · 0% · 0% (n=27) |
| `guardrail` | 3 (+32 bloqueadas) | 1 | 6.1 s | 6.3 s | sim | 32% | — | — | 68% | 100% · 0% · 0% · 0% (n=3) |
| `hard` | 5 | 1 | 14.6 s | 16.4 s | sim | 31% | 18% | 0% | 51% | 100% · 0% · 0% · 0% (n=6) |
| `heldout` | 74 (+6 bloqueadas) | 1 | 13.3 s | 24.8 s | sim | 32% | 17% | 0% | 51% | 100% · 0% · 0% · 0% (n=96) |
| `heldout_h3` | 37 (+3 bloqueadas) | 1 | 11.7 s | 21.7 s | sim | 31% | 16% | 0% | 53% | 100% · 0% · 0% · 0% (n=49) |
| `hitl` | 7 | 1.1 | 7.1 s | 14.7 s | sim | — | 10% | 0% | 90% | 100% · 0% · 0% · 0% (n=7) |
| `memory` | 66 | 2.1 | 10.7 s | 17.3 s | sim | 27% | 12% | — | 61% | 100% · 0% · 0% · 0% (n=66) |
| `official` | 30 | 1 | 9.8 s | 23.5 s | sim | 29% | 10% | — | 61% | 100% · 0% · 0% · 0% (n=36) |
| `official-var` | 12 | 1 | 12.8 s | 20.5 s | sim | 40% | 6% | — | 54% | 100% · 0% · 0% · 0% (n=14) |
| `parallel` | 4 | 1 | 16.6 s | 17.9 s | sim | 48% | 22% | — | 30% | 100% · 0% · 0% · 0% (n=8) |
| `partial` | 5 | 1 | 14.6 s | 17.4 s | sim | 57% | — | — | 43% | 100% · 0% · 0% · 0% (n=5) |
| `real` | 40 | 1 | 14.4 s | 25.5 s | sim | 39% | 12% | 0% | 49% | 100% · 0% · 0% · 0% (n=58) |
| `replan` | 19 (+1 bloqueada) | 1 | 11.4 s | 25.4 s | sim | 39% | 12% | 0% | 49% | 100% · 0% · 0% · 0% (n=38) |
| **total** | 320 (+42 bloqueadas) | 1.2 | 12.4 s | 24.8 s | sim | 33% | 14% | 0% | 53% | 100% · 0% · 0% · 0% (n=418) |

Onde vai o tempo (total): faq **33%** · records **14%** · escalation **0%** · resto **53%** = router, supervisor, guardrails e checagens, que não têm passo próprio. Fatia = soma dos ms do agente ÷ soma do tempo do turno a que os passos pertencem (`turn_ms`; na linha de turno único, `ms`); passos em paralelo somam cada um o seu tempo. Em `hitl` (1.1 turnos/linha; conversa: p50 13.9 s, p95 13.9 s) e `memory` (2.1 turnos/linha; conversa: p50 21.7 s, p95 36.4 s) a linha cronometra a conversa inteira; ali a latência do turno é ms ÷ turnos.

Quem decide (418 passos do turno, fora a resposta da operadora e o aviso de caso aberto): supervisor LLM **100%** (tool call).
<!-- trace:end -->

## Juiz LLM sobre as respostas ao vivo

<!-- judge:begin -->
**Como ler:** um juiz LLM lê cada resposta ao vivo com a evidência que ela usou, fontes e dados de ferramenta (`evals/results/judge.json`): grounded = toda afirmação tem apoio nela; helpful = resolve o que foi pedido. Entre colchetes, o IC95 de Wilson com o n de respostas julgadas. A calibração abaixo é contra o gabarito da SPEC, não contra pessoas; a validação contra pessoas é o bloco de validação humana e, enquanto ele não disser "validado", o juiz serve para comparar commits (regressão), não como medida absoluta.

Modelo `claude-opus-5-5` · status `ran` · arquivos live_approval.json, live_dependent.json, live_guardrail.json, live_hard.json, live_heldout.json, live_heldout_h3.json, live_hitl.json, live_memory.json, live_official-var.json, live_official.json, live_parallel.json, live_partial.json, live_real.json, live_replan.json · gasto US$ 38.105408

| split | casos | grounded | helpful | nota média |
|---|---:|---:|---:|---:|
| approval | 4 | 1.0 [IC95 51.0–100.0; n=4] | 1.0 [IC95 51.0–100.0; n=4] | 5.0 |
| dependent | 14 | 1.0 [IC95 78.5–100.0; n=14] | 1.0 [IC95 78.5–100.0; n=14] | 4.86 |
| guardrail | 32 | 1.0 [IC95 89.3–100.0; n=32] | 0.938 [IC95 79.9–98.3; n=32] | 4.78 |
| hard | 5 | 1.0 [IC95 56.6–100.0; n=5] | 1.0 [IC95 56.6–100.0; n=5] | 4.4 |
| heldout | 79 | 0.937 [IC95 86.0–97.3; n=79] | 0.949 [IC95 87.7–98.0; n=79] | 4.59 |
| heldout_h3 | 40 | 0.9 [IC95 76.9–96.0; n=40] | 0.975 [IC95 87.1–99.6; n=40] | 4.55 |
| hitl | 7 | 1.0 [IC95 64.6–100.0; n=7] | 1.0 [IC95 64.6–100.0; n=7] | 4.86 |
| memory | 66 | 0.924 [IC95 83.5–96.7; n=66] | 1.0 [IC95 94.5–100.0; n=66] | 4.65 |
| official | 30 | 0.933 [IC95 78.7–98.2; n=30] | 1.0 [IC95 88.6–100.0; n=30] | 4.8 |
| official-var | 12 | 1.0 [IC95 75.8–100.0; n=12] | 1.0 [IC95 75.8–100.0; n=12] | 4.92 |
| parallel | 4 | 1.0 [IC95 51.0–100.0; n=4] | 1.0 [IC95 51.0–100.0; n=4] | 5.0 |
| partial | 5 | 1.0 [IC95 56.6–100.0; n=5] | 0.8 [IC95 37.6–96.4; n=5] | 4.6 |
| real | 40 | 0.975 [IC95 87.1–99.6; n=40] | 1.0 [IC95 91.2–100.0; n=40] | 4.47 |
| replan | 20 | 1.0 [IC95 83.9–100.0; n=20] | 1.0 [IC95 83.9–100.0; n=20] | 4.95 |
| ALL | 358 | 0.953 [IC95 92.5–97.0; n=358] | 0.978 [IC95 95.7–98.9; n=358] | 4.67 |

Gabarito de calibração (rótulos da SPEC, não humanos salvo rotulagem): 48 rótulos · concordância **1.0** [IC95 92.6–100.0; n=48] · kappa de Cohen **1.0** · TPR 1.0 [IC95 86.2–100.0; n=24] (24 grounded) · TNR 1.0 [IC95 86.2–100.0; n=24] (24 não grounded) · discordâncias: —
- official: concordância 1.0 [IC95 92.6–100.0; n=48] · kappa 1.0 (48 rótulos)

Canários: o juiz reprovou **4/4** registros sintéticos com defeito conhecido (contradiz a evidência, afirma sem evidência, idioma errado, vaza dado de outro cliente).
Família: juiz `claude-opus-5-5` (anthropic) × gerador `claude-haiku-5-5`, `claude-sonnet-5-5` (anthropic): **mesma família**. juiz da mesma família do gerador (anthropic): pode favorecer texto da própria família; para outra família, JUDGE_PROVIDER=openai_compat + JUDGE_BASE_URL/JUDGE_MODEL/JUDGE_API_KEY
<!-- judge:end -->

## Validação humana (às cegas, por rotulador)

<!-- human:begin -->
**Como ler:** pessoas rotulam respostas ao vivo sem ver o veredito automático (`evals/label.py`, `evals/results/human_review.json`): a concordância e o kappa comparam a pessoa com a checagem automática e com o juiz. Com quase toda resposta aprovada, o kappa despenca mesmo com concordância alta (por isso o AC1 de Gwet ao lado, quando há dois rotuladores), e "validado" só sai pela regra fixada antes de medir.

2 respostas ao vivo rotuladas às cegas pelo dono: humano aprova 2/2, checagem automática aprova 2/2; concordância **1.0**, kappa **None**.
Bateria das respostas rotuladas que contam, em rótulos: `ff8afed` 2; 1 de página congelada (páginas `10ac784d5e97`) e 1 do texto de hoje. Regra: rótulo de pessoa só se compara com veredito do juiz, checagem ou outra pessoa sobre o MESMO texto: o da página congelada (evals/validation/<amostra>.json) ou, sem ela, a resposta de hoje em evals/results; rótulo de outro texto sai de toda conta e é listado.
Rótulos de outra bateria: **35** (a resposta rotulada não é a de hoje nem a de uma página congelada), fora de toda conta: approval-01, approval-03, approval-04, dependent-01, dependent-07, dependent-11, heldout-H1-11, heldout-H1-27, heldout-H1-30, heldout-H1-35, heldout-H2-05, heldout-H2-09, heldout-H2-12, heldout-H2-18, memory-09, official-03, official-08, official-09, parallel-01, parallel-04, q-dep-01, q-guard-oos-3, q-hard-01, q-hard-03, q-hard-05, q-mem-02, q-ov-01-pt, q-ov-04-pt, q-ov-05-pt, q-ov-10-en, q-partial-02, q-partial-03, real-22, replan-03, replan-05.
Aviso do juiz × humano: 1 rótulo(s) sem veredito do juiz sobre o texto rotulado (fora do juiz × humano): rode o juiz na bateria ou, se a página foi congelada, `python -m evals.judge --validation`.
- rotulador `matheus`: 2 rótulos · humano × automático: concordância 1.0, kappa None
Um rotulador só: a concordância entre humanos não foi medida.
Respostas com um defeito plantado (número trocado ou afirmação sem base contra a evidência; fato de referência removido): 21 geradas (numero_trocado 10, afirmacao_sem_base 1, fato_removido 10; `evals/results/perturbed.json`, geradas por `evals/perturb.py`), ainda não rotuladas.
- juiz nas 21 com defeito plantado (sem depender de rótulo), reprova por tipo, antes (só não fundamentada, idioma ou vazamento) → depois (+ não atende ao pedido, a em vigor): numero_trocado 10/10 → 10/10; afirmacao_sem_base 1/1 → 1/1; fato_removido 0/10 → 4/10. fato_removido não é negativo garantido: sem o fato a resposta pode continuar servindo, e quem decide é a pessoa.
Juiz × humano (veredito do juiz: fundamentada, útil, no idioma da pergunta e sem vazamento — as 3 perguntas da página; regra fixada antes: >= 10 por classe e TPR, TNR >= 0.8; acrescentada depois da 2ª revisão: só conta resposta real que entrou na amostra sem depender do juiz (sorteio ou checagem automática que falhou); a escolhida porque o juiz a reprovou e a sem o motivo da escolha gravado (seleção desconhecida) ficam fora da validação, inclusive do mínimo de negativos reais, e saem à parte como diagnóstico): nenhuma resposta rotulada entrou na amostra sem depender do juiz → não validado (falta: >= 10 positivos e negativos humanos (tem 0 e 0); TPR e TNR >= 0.8 (tem None e None)).
- fora da validação (diagnóstico, não validação): 1 de seleção desconhecida (rótulos de antes do registro do motivo da escolha: não contam para validar, nem para o mínimo de negativos reais) — a pessoa reprova 0 (TNR do juiz nelas None) e aprova 1 (TPR 1.0).
Aviso: só 2 rótulos: abaixo de 20 não dá para confiar.
<!-- human:end -->

## Busca (sem LLM; o buscador do agente e as alternativas medidas)

<!-- retrieval:begin -->
**Como ler:** a busca medida sem LLM no gold de perguntas rotuladas olhando a fonte, uma linha por configuração (`data/retriever.json`, o arquivo que o app usa como padrão): Recall@k = fração das passagens certas que aparecem entre as k primeiras; MRR = média do inverso da posição da primeira certa. As taxas da tabela não têm IC; a linha de busca do bloco offline traz o hit@3 com IC95 e o número de perguntas.

Gold `retrieval.jsonl`, medido em 2026-11-04T06:52:47+00:00 (commit `ee44b31-dirty`), CPU, sem LLM. Critério: maior Recall@5 (o que o redator lê) com p95 <= 1500 ms e RAM <= 4096 MB (empate: MRR, Recall@3, cobertura do portão, p95); orçamento p95 1500 ms. Portão sem fonte da escolha: nota do cross-encoder >= -4.986 (vale este enquanto a busca for a mesma; sem ele, o MIN_RERANK do domínio).

| configuração | Recall@5 (o redator lê) | Recall@3 | MRR | hit@3 | nDCG@3 | URL hit@3 | p50 ms | p95 ms | RAM MB | portão: com fonte respondidas / sem fonte recusadas |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| bm25 | 0.76 | 0.729 | 0.667 | 0.75 | 0.672 | 0.979 | 0.5 | 0.6 | 41.5 | 69% / 96% (BM25/cosseno) |
| dense | 0.938 | 0.917 | 0.858 | 0.938 | 0.856 | 1.0 | 65.2 | 83.3 | 1542.1 | 92% / 86% (BM25/cosseno) |
| dense+cross | 0.927 | 0.906 | 0.875 | 0.917 | 0.874 | 0.979 | 1063.5 | 1224.3 | 2383.5 | 100% / 91% (nota do cross) |
| dense+cross:base **← escolhida** | 0.938 | 0.917 | 0.858 | 0.938 | 0.856 | 1.0 | 1091.8 | 1311.7 | 2383.5 | 100% / 91% (nota do cross) |

`:base` = a ordem fica a do buscador base; a nota do cross-encoder só decide o portão sem fonte.
<!-- retrieval:end -->

## Replanejamento (com × sem)

<!-- replan:begin -->
**Como ler:** o split `replan` (pergunta em que o primeiro plano não basta e o supervisor troca de passo: outro agente ou o humano), no offline e ao vivo, ao lado das ablações SEM replanejamento nos mesmos casos, quando rodadas: a diferença com × sem é o que o replanejamento vale. Cada célula é a taxa em % com o n de casos; o IC95 de cada taxa fica no JSON (`ci`).

| fonte | casos | replanned_acc | handoff_acc | handoff_outcome_acc | route_acc | intent_acc |
|---|---:|---:|---:|---:|---:|---:|
| offline | 20 | 55.0 (n=20) | 55.0 (n=20) | 55.0 (n=20) | — | 100.0 (n=20) |
| ao vivo (live_replan.json) | 20 | 95.0 (n=20) | 95.0 (n=20) | 95.0 (n=20) | — | 90.0 (n=20) |

- `replan-07` (offline): faq:no_source->escalation
- `replan-09` (offline): faq:no_source->escalation
- `replan-11` (offline): faq:no_source->escalation
- `replan-13` (offline): records:need->faq (terminal offline/sem sinal: o passo a passo vem do manual de conexão)
- `replan-14` (offline): records:need->faq (terminal offline/sem sinal: o passo a passo vem do manual de conexão)

Ablação ao vivo sem `needs` (real, com × sem): mesmos 40 casos, mesmo código (`ff8afed` × `f39d9ff`: entre os dois só resultados e docs, nada em src/, data/ nem evals/*.py); fundamentadas pelo juiz **39/40 com** × **38/40 sem**; úteis 40/40 × 40/40; números com base 100.0% × 100.0%; frases com base 100.0% × 100.0%; p50 14.4 s × 17.5 s; p50 só nos 4 casos em que o achado disparou 23.9 s × 16.8 s; US$ por caso 0.044 × 0.041; 4 achados no braço com `needs`: o modelo chamou o agente pedido 3, o agente já tinha rodado 1.
<!-- replan:end -->
