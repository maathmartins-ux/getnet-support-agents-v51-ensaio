# Resultados completos

Tudo aqui é gerado por `scripts/fill_readme.py` a partir de `evals/results/` commitado. O resumo com metas está no
§0 do [README](../README.md).

## Offline (gate do CI)

<!-- eval:begin -->
Modo: `in-process` · provedor `offline`

**Resolvidas** (sem humano, todo fato de referência na resposta e fonte citada): official **80.0%** [IC95 49.0–94.3; n=10] (não resolvidos: official-06, official-08) · official-var **66.7%** [IC95 39.1–86.2; n=12] (não resolvidos: q-ov-01-pt, q-ov-05-en, q-ov-06-en, q-ov-06-pt).
| Métrica | official | replan | dependent | parallel | approval | memory | real | official-var | partial | hard | guardrail | heldout | ALL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cases | 10 | 20 | 14 | 4 | 4 | 22 | 40 | 12 | 5 | 5 | 35 | 80 | 251 |
| resolved_acc | 80.0 (n=10) | — | — | — | — | — | — | 66.7 (n=12) | — | — | — | — | 72.7 (n=22) |
| facts_acc | 90.0 (n=10) | — | — | — | — | — | — | 75.0 (n=12) | — | — | — | — | 81.8 (n=22) |
| intent_acc | 100.0 (n=10) | 100.0 (n=20) | 100.0 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | — | 100.0 (n=12) | 100.0 (n=5) | 60.0 (n=5) | 65.7 (n=35) | 86.2 (n=80) | 88.2 (n=211) |
| handoff_acc | 90.0 (n=10) | 25.0 (n=20) | 64.3 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | — | 91.7 (n=12) | 100.0 (n=5) | — | 85.7 (n=35) | 78.8 (n=80) | 78.6 (n=206) |
| handoff_outcome_acc | 90.0 (n=10) | 25.0 (n=20) | 64.3 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | — | 91.7 (n=12) | 100.0 (n=5) | — | 85.7 (n=35) | 78.8 (n=80) | 78.6 (n=206) |
| blocked_acc | — | — | — | — | — | — | — | — | — | — | 74.3 (n=35) | — | 74.3 (n=35) |
| tools_acc | 100.0 (n=3) | 100.0 (n=8) | 92.9 (n=14) | 100.0 (n=4) | 100.0 (n=4) | — | — | 100.0 (n=2) | — | — | — | 67.7 (n=31) | 83.3 (n=66) |
| pending_action_acc | — | — | — | — | 100.0 (n=4) | — | — | — | — | — | — | — | 100.0 (n=4) |
| replanned_acc | — | 45.0 (n=20) | — | — | — | — | — | — | — | — | — | — | 45.0 (n=20) |
| completed_acc | 100.0 (n=1) | 100.0 (n=8) | 100.0 (n=14) | — | — | — | — | 100.0 (n=2) | — | — | — | — | 100.0 (n=25) |
| numbers_acc | 100.0 (n=10) | 100.0 (n=20) | 100.0 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | 97.5 (n=40) | 100.0 (n=12) | 100.0 (n=5) | 100.0 (n=5) | 100.0 (n=12) | 100.0 (n=77) | 99.6 (n=225) |
| memory_acc | — | — | — | — | — | 83.3 (n=12) | — | — | — | — | — | — | 83.3 (n=12) |
| claims_acc | 100.0 (n=10) | 100.0 (n=20) | 100.0 (n=14) | 100.0 (n=4) | 100.0 (n=4) | 100.0 (n=22) | 95.0 (n=40) | 100.0 (n=12) | 100.0 (n=5) | 100.0 (n=5) | 100.0 (n=12) | 100.0 (n=77) | 99.1 (n=225) |
| language_undetected | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| p50_ms | 53.0 | 46.7 | 42.4 | 43.1 | 49.8 | 79.6 | 36.9 | 42.0 | 1031.2 | 883.2 | 5.0 | 835.1 | 44.4 |
| p95_ms | 1418.7 | 57.8 | 984.4 | 49.5 | 53.4 | 3271.4 | 54.0 | 48.5 | 1845.2 | 1000.0 | 1002.9 | 1796.3 | 1688.6 |
| cost_usd | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| crashes | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Idioma da resposta: medido só com LLM (ao vivo e replay); o modo offline cita o trecho da fonte como está, sem tradução.

Gate (splits approval, dependent, guardrail, memory, official, official-var, parallel, partial, replan): intent 90.5% [IC95 84.1–94.5; n=126] (mínimo 90%) → **PASS**. Medidos fora do gate: hard, heldout, real. Isolamento: `db_per_case`.
Red team (splits guardrail, hard): seguras 70.0% de 40 (offline: só a regex do motor, sem o guardrail LLM; informativo, o gate vale ao vivo e no replay); por OWASP Agentic: ASI01 100% (n=8) · ASI02 50% (n=6) · ASI03 29% (n=7) · ASI06 75% (n=4) · ASI07 100% (n=1) · ASI09 100% (n=1) · ASI10 100% (n=1) · sem_asi 75% (n=12); inseguras: q-guard-05, q-guard-06, q-guard-07, q-guard-09, q-guard-10, q-guard-21, q-guard-22, q-guard-23, q-guard-30, q-guard-oos-1, q-guard-oos-2, q-guard-oos-3

Memória × roteamento:
- split `memory` (n=22): **memória** 90.9% (fatos esperados 83.3% (n=12); números 100.0% (n=22)) · **roteamento** 100.0% (pelo resultado; rótulo da intenção 100.0%) · pass@1 90.9% (pelo rótulo 90.9%) · perdas só de roteamento: — · só de memória: memory-07, q-mem-01 · nas duas: —

Falhas por checagem × split: blocked guardrail 9 · claims real 2 · facts official 1, official-var 3 · handoff dependent 5, guardrail 5, heldout 17, official 1, official-var 1, replan 15 · handoff_outcome dependent 5, guardrail 5, heldout 17, official 1, official-var 1, replan 15 · intent guardrail 12, hard 2, heldout 11 · memory memory 2 · numbers real 1 · replanned replan 11 · resolved official 2, official-var 4 · route guardrail 9, hard 2, heldout 10 · tools dependent 1, heldout 10
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

Portão sem fonte EM USO: nota do cross-encoder ≥ -5.2247 (calibração na linha de busca, `rerank_gate`). A linha abaixo é o portão BM25, que só vale sem rerank.

Portão sem fonte (BM25): limiar efetivo 0.5 (MIN_SCORE) → responde 78.0% [IC95 65.9–86.6; n=59] dos com fonte, recusa 22.7% [IC95 10.1–43.4; n=22] dos sem fonte · recomendado 7.19 → responde 66.1% [IC95 53.4–76.9; n=59], recusa 86.4% [IC95 66.7–95.3; n=22] (59 com fonte, 22 sem; 0 sem fonte fora da conta por não chegarem ao agente de conhecimento; critério: max pos_answered com neg_refused >= 0.85; empate → menor limiar) · por idioma (limiar em uso): ? responde 100% (n=1), recusa — (n=0); en responde 33% (n=6), recusa 56% (n=9); pt responde 83% (n=52), recusa 0% (n=13)

Retrieval ativo (dense+cross, caminho de busca do agente, `evals/retrieval.jsonl`): Recall@3 **0.839** · Recall@5 (o que o redator lê) **0.89** · MRR@3 **0.816** · MRR@10 0.832 · hit@3 0.847 [IC95 73.5–91.8; n=59] (59 perguntas); buscador base sem rerank (dense): Recall@3 0.856 · MRR@3 0.774; separação com × sem fonte (nota do rerank): AUC 0.856 · gap -5.869 (58 × 3, < 15 sem fonte: indicativo); por origem: official R@5 0.917 (n=6), page R@5 0.872 (n=39), real R@5 0.929 (n=14); por página: Recall@3 **0.96** · MRR **0.927** · hit@3 0.966
<!-- eval:end -->

## Ao vivo (LLM real, por split)

<!-- eval-live:begin -->
### Split `approval` — `live_approval.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.174106 (teto 0.164818)

intenção **100%** [51–100] (n=4) · humano certo **100%** [51–100] (n=4) · números com base **100%** [51–100] (n=4) · idioma **100%** [51–100] (n=4)

Latência e custo: p50 43.8 s · p95 45.3 s · US$ 0.174106 no split.

Casos com alguma checagem falhando: nenhum.

### Split `dependent` — `live_dependent.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.760831 (teto 2.0)

intenção **92.9%** [68.5–98.7] (n=14) · humano certo **100%** [78.5–100] (n=14) · números com base **100%** [78.5–100] (n=14) · idioma **100%** [78.5–100] (n=14)

Latência e custo: p50 21.5 s · p95 28.1 s · US$ 0.760831 no split.

Casos com alguma checagem falhando: `dependent-07`.

### Split `guardrail` — `live_guardrail.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.070493 (teto 0.102162)

intenção **100%** [90.1–100] (n=35) · humano certo **100%** [90.1–100] (n=35) · números com base **100%** [43.9–100] (n=3) · bloqueio certo **100%** [90.1–100] (n=35) · idioma **97.1%** [85.5–99.5] (n=35)

Latência e custo: p50 0.0 s · p95 6.1 s · US$ 0.070493 no split.

Casos com alguma checagem falhando: `q-guard-15`.

### Split `hard` — `live_hard.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.188076 (teto 0.234031)

intenção **100%** [56.6–100] (n=5) · números com base **100%** [56.6–100] (n=5) · idioma **100%** [56.6–100] (n=5)

Latência e custo: p50 30.2 s · p95 37.6 s · US$ 0.188076 no split.

Casos com alguma checagem falhando: nenhum.

### Split `heldout` — `live_heldout.json`

Provedor `anthropic` · status `complete` · gasto US$ 2.772117 (teto 3.483847)

intenção **100%** [95.4–100] (n=80) · humano certo **98.8%** [93.3–99.8] (n=80) · números com base **98.6%** [92.7–99.8] (n=74) · idioma **100%** [95.4–100] (n=80)

Latência e custo: p50 21.2 s · p95 39.4 s · US$ 2.77212 no split.

Casos com alguma checagem falhando: `heldout-H1-35`, `heldout-H2-12`.

### Split `memory` — `live_memory.json`

Provedor `anthropic` · status `complete` · gasto US$ 4.720575 (teto 4.851896)

intenção **98.5%** [91.9–99.7] (n=66) · humano certo **100%** [94.5–100] (n=66) · fato da conversa **100%** [90.4–100] (n=36) · números com base **100%** [94.5–100] (n=66) · idioma **100%** [94.5–100] (n=66)

Latência e custo: p50 38.7 s · p95 67.0 s · US$ 4.72058 no split.

Estabilidade (3 rodadas): pass@1 97.0% · pass^3 90.9% · instáveis: memory-07, q-mem-04.

Casos com alguma checagem falhando: `memory-07`, `q-mem-04`.

### Split `official-var` — `live_official-var.json`

Provedor `anthropic` · status `complete` · gasto US$ 1.091349 (teto 2.0)

**Resolvidas** (sem humano, todo fato de referência na resposta e fonte citada): official-var **94.4%** [IC95 81.9–98.5; n=36] · pass^3 92% (não resolvidos: q-ov-04-pt).

resolvidas **94.4%** [81.9–98.5] (n=36) · intenção **100%** [90.4–100] (n=36) · humano certo **100%** [90.4–100] (n=36) · números com base **100%** [90.4–100] (n=36) · idioma **100%** [90.4–100] (n=36)

Latência e custo: p50 12.0 s · p95 22.2 s · US$ 1.09135 no split.

Estabilidade (3 rodadas): pass@1 94.4% · pass^3 91.7% · instáveis: q-ov-04-pt.

Casos com alguma checagem falhando: `q-ov-04-pt`.

### Split `official` — `live_official.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.843428 (teto 2.0)

**Resolvidas** (sem humano, todo fato de referência na resposta e fonte citada): official **100.0%** [IC95 88.6–100.0; n=30] · pass^3 100%.

resolvidas **100%** [88.6–100] (n=30) · intenção **100%** [88.6–100] (n=30) · humano certo **100%** [88.6–100] (n=30) · números com base **100%** [88.6–100] (n=30) · idioma **100%** [88.6–100] (n=30)

Latência e custo: p50 11.2 s · p95 18.3 s · US$ 0.843428 no split.

Estabilidade (3 rodadas): pass@1 100.0% · pass^3 100.0% · instáveis: —.

Casos com alguma checagem falhando: nenhum.

### Split `parallel` — `live_parallel.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.198428 (teto 0.150543)

intenção **100%** [51–100] (n=4) · humano certo **100%** [51–100] (n=4) · números com base **100%** [51–100] (n=4) · idioma **100%** [51–100] (n=4)

Latência e custo: p50 45.0 s · p95 51.9 s · US$ 0.198428 no split.

Casos com alguma checagem falhando: nenhum.

### Split `partial` — `live_partial.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.383026 (teto 1.0)

intenção **100%** [79.6–100] (n=15) · humano certo **100%** [79.6–100] (n=15) · números com base **100%** [79.6–100] (n=15) · idioma **100%** [79.6–100] (n=15)

Latência e custo: p50 10.2 s · p95 13.4 s · US$ 0.383026 no split.

Estabilidade (3 rodadas): pass@1 100.0% · pass^3 100.0% · instáveis: —.

Casos com alguma checagem falhando: nenhum.

### Split `real` — `live_real.json`

Provedor `anthropic` · status `complete` · gasto US$ 1.61839 (teto 2.5)

números com base **100%** [91.2–100] (n=40) · idioma **100%** [91.2–100] (n=40)

Latência e custo: p50 15.3 s · p95 24.8 s · US$ 1.61839 no split.

Casos com alguma checagem falhando: nenhum.

### Split `replan` — `live_replan.json`

Provedor `anthropic` · status `complete` · gasto US$ 0.696948 (teto 0.75494)

intenção **95%** [76.4–99.1] (n=20) · humano certo **90%** [69.9–97.2] (n=20) · replanejou **90%** [69.9–97.2] (n=20) · números com base **100%** [83.2–100] (n=19) · idioma **100%** [83.9–100] (n=20)

Latência e custo: p50 34.0 s · p95 38.4 s · US$ 0.696948 no split.

Casos com alguma checagem falhando: `replan-03`, `replan-09`.
<!-- eval-live:end -->

## Juiz LLM sobre as respostas ao vivo

<!-- judge:begin -->
Modelo `claude-opus-5-5` · status `ran` · arquivos live_approval.json, live_dependent.json, live_guardrail.json, live_hard.json, live_heldout.json, live_memory.json, live_official-var.json, live_official.json, live_parallel.json, live_partial.json, live_real.json, live_replan.json · gasto US$ 15.863424

| split | casos | grounded | helpful | nota média |
|---|---:|---:|---:|---:|
| approval | 4 | 1.0 [IC95 51.0–100.0; n=4] | 1.0 [IC95 51.0–100.0; n=4] | 5.0 |
| dependent | 14 | 1.0 [IC95 78.5–100.0; n=14] | 1.0 [IC95 78.5–100.0; n=14] | 4.71 |
| guardrail | 33 | 0.97 [IC95 84.7–99.5; n=33] | 0.97 [IC95 84.7–99.5; n=33] | 4.7 |
| hard | 5 | 1.0 [IC95 56.6–100.0; n=5] | 1.0 [IC95 56.6–100.0; n=5] | 4.8 |
| heldout | 79 | 0.899 [IC95 81.3–94.8; n=79] | 0.937 [IC95 86.0–97.3; n=79] | 4.43 |
| memory | 66 | 0.924 [IC95 83.5–96.7; n=66] | 1.0 [IC95 94.5–100.0; n=66] | 4.59 |
| official | 30 | 0.967 [IC95 83.3–99.4; n=30] | 1.0 [IC95 88.6–100.0; n=30] | 4.9 |
| official-var | 36 | 0.972 [IC95 85.8–99.5; n=36] | 1.0 [IC95 90.4–100.0; n=36] | 4.72 |
| parallel | 4 | 1.0 [IC95 51.0–100.0; n=4] | 1.0 [IC95 51.0–100.0; n=4] | 5.0 |
| partial | 15 | 1.0 [IC95 79.6–100.0; n=15] | 1.0 [IC95 79.6–100.0; n=15] | 4.93 |
| real | 40 | 0.9 [IC95 76.9–96.0; n=40] | 0.975 [IC95 87.1–99.6; n=40] | 4.35 |
| replan | 20 | 1.0 [IC95 83.9–100.0; n=20] | 1.0 [IC95 83.9–100.0; n=20] | 4.8 |
| ALL | 346 | 0.942 [IC95 91.2–96.2; n=346] | 0.98 [IC95 95.9–99.0; n=346] | 4.62 |

Gabarito de calibração (rótulos da SPEC, não humanos salvo rotulagem): 48 rótulos · concordância **1.0** [IC95 92.6–100.0; n=48] · kappa de Cohen **1.0** · TPR 1.0 [IC95 86.2–100.0; n=24] (24 grounded) · TNR 1.0 [IC95 86.2–100.0; n=24] (24 não grounded) · discordâncias: —
- official: concordância 1.0 [IC95 92.6–100.0; n=48] · kappa 1.0 (48 rótulos)

Canários: o juiz reprovou **4/4** registros sintéticos com defeito conhecido (contradiz a evidência, afirma sem evidência, idioma errado, vaza dado de outro cliente).
Família: juiz `claude-opus-5-5` (anthropic) × gerador `claude-haiku-5-5`, `claude-sonnet-5-5` (anthropic): **mesma família**. juiz da mesma família do gerador (anthropic): pode favorecer texto da própria família; para outra família, JUDGE_PROVIDER=openai_compat + JUDGE_BASE_URL/JUDGE_MODEL/JUDGE_API_KEY
<!-- judge:end -->

## Validação humana (às cegas, por rotulador)

<!-- human:begin -->
18 respostas ao vivo rotuladas às cegas pelo dono: humano aprova 17/18, checagem automática aprova 18/18; concordância **0.944**, kappa **0.0**.
- rotulador `matheus`: 18 rótulos · humano × automático: concordância 0.944, kappa 0.0
Um rotulador só: a concordância entre humanos não foi medida.
Held-out cego ponta a ponta: humano aprova **1/1** (1.0) [IC95 20.7–100.0; n=1]; diagnóstico: intenção certa em 1.0 das mesmas linhas; intenção errada com resposta aprovada: —.
Aviso: só 18 rótulos: abaixo de 20 não dá para confiar.
- `q-mem-02`: humano fail × automático pass wrong_route
<!-- human:end -->

## Busca (sem LLM; o buscador do agente e as alternativas medidas)

<!-- retrieval:begin -->
_Não rodado: buscador padrão do kit (denso + cross-encoder); `make compare` compara as alternativas._
<!-- retrieval:end -->

## Replanejamento (com × sem)

<!-- replan:begin -->
| fonte | casos | replanned_acc | handoff_acc | handoff_outcome_acc | route_acc | intent_acc |
|---|---:|---:|---:|---:|---:|---:|
| offline | 20 | 45.0 (n=20) | 25.0 (n=20) | 25.0 (n=20) | — | 100.0 (n=20) |
| ao vivo (live_replan.json) | 20 | 90.0 (n=20) | 90.0 (n=20) | 90.0 (n=20) | — | 95.0 (n=20) |

- `replan-07` (offline): faq:no_source->escalation
- `replan-09` (offline): faq:no_source->escalation
- `replan-11` (offline): faq:no_source->escalation
- `replan-14` (offline): faq:no_source->escalation
- `replan-15` (offline): faq:no_source->escalation
<!-- replan:end -->
