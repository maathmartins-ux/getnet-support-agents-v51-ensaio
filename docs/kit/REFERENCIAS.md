# Referências públicas (pesquisa de 01/11/2026)

Busca por soluções públicas do mesmo desafio (Getnet, "AI Hardcore Engineer — Multi-Agent Support System") e do
desafio de formato igual da CloudWalk/InfinitePay ("Agent Swarm"). Cada número abaixo tem link. Conferido por
leitura direta: o feedback do DiogoOg16, o REVIEW.md e o README do nelsondell e o histórico do Skywalker. O resto
veio das pesquisas e está marcado quando não foi conferido.

## 1. O que os números dizem (e o que NÃO dizem)

- Circula um ranking com a **mesma Régua V4** (11 critérios, mesmos pesos). Fonte:
  [feedback do DiogoOg16](https://raw.githubusercontent.com/DiogoOg16/getnet/main/feedback_diogoog16_v4(1).md),
  com "Nota V4: 4,7/10 — 28º lugar" e "Benchmark: João / Skywalker = 10,0". O avaliador não é identificado.
- **O 10,0 não é de 60 minutos.** O [Skywalker](https://github.com/farrulla-darze/skywalker) tem o 1º commit em
  18/02/2026 e o último em 17/09/2026 (~7 meses), com a grande reestruturação em julho. Não dá para saber que
  versão foi avaliada.
- **O 9,5 também não.** O [nelsondell](https://github.com/nelsondell/multi-agent-support-system) diz: "v1 was
  built in the challenge's 60-minute timebox and scored 8.7/10"; o 9,5 é da V4, feita fora do relógio "at the
  evaluator's invitation".
- **Melhor nota pública DENTRO de 60 min: 8,7** (nelsondell v1). A v2 do dono tirou 8,18 (17º). Mirar 10 em 60
  min é mirar acima de tudo o que é público; o caminho é chegar com o máximo pronto ANTES do relógio (o kit).

## 2. As melhores soluções e o que fazem melhor

| Solução | Nota / evidência | O que fazem melhor que o nosso kit |
|---|---|---|
| [nelsondell](https://github.com/nelsondell/multi-agent-support-system) | 8,7 em 60 min (v1); 9,5 na V4; [REVIEW.md](https://raw.githubusercontent.com/nelsondell/multi-agent-support-system/main/REVIEW.md) | **Ablação do replanejamento** (32/60 com × 19/60 sem); RAG com AUC de abstenção 1,000, Recall@5 0,939, MRR 0,851 em 82 perguntas; REVIEW.md critério → evidência → comando → **limite conhecido**; "caminho do avaliador" com comandos; held-out separado do tuning (63/80 × 95/100); 2 réplicas com balanceador e teste de morte de réplica no meio do turno; SBOM, trivy, gitleaks no CI; custo por turno resolvido (US$ 0,00048) |
| [Skywalker](https://github.com/farrulla-darze/skywalker) | "Benchmark = 10,0" no ranking de terceiros (versão avaliada não verificada) | especialistas como tools de um agente que mantém a conversa; HITL síncrono no Telegram ("o agente nunca larga a conversa"); JWT com denylist de `jti`; Langfuse no compose; RAGAS. Sem CI e sem números publicados hoje |
| [ArturFBrandi v2](https://github.com/ArturFBrandi/ai-hardcore-engineer-v2) | sem nota; [SCORECARD](https://raw.githubusercontent.com/ArturFBrandi/ai-hardcore-engineer-v2/main/docs/SCORECARD.md) contra a mesma régua | ablação de retrieval publicada (híbrido+rerank × denso 0,818 × BM25 0,636); eval ao vivo com commit/data/duração; política de tools em 4 níveis (auto, escalação, aprovação, proibido); seção "5-minute evaluator path"; cobertura 90,9% com gate de 85% |
| [EduardoColissi](https://github.com/EduardoColissi/agents-orchestration) | v1: memória 1,0/10 e HITL 4,0/10 | o que derruba nota: memória e HITL fracos (vale para nós: v3 tinha memória 61,5%) |
| [bnavarro12](https://github.com/bnavarro12/getnet-multi-agent) | sem nota | juízes calibrados com humanos (κ 0,61); grounding numérico 0,912; réplicas + nginx; CI em SQLite e Postgres |
| [EikiYamashiro](https://github.com/EikiYamashiro/cloudwalk_agent_swarm) (InfinitePay) | sem nota | **matriz de confusão do router** publicada com os erros caso a caso |
| [luiznogueira1210 "Buzz"](https://raw.githubusercontent.com/luiznogueira1210-doc/agent-swarm-case/HEAD/README.md) (InfinitePay) | sem nota | flags de risco na saída de fintech (promessa financeira, compromisso legal, vazamento entre usuários); expansão de consulta + CRAG |
| [jonathansschaffer](https://github.com/jonathansschaffer/cloudwalk-agent-swarm) (InfinitePay) | sem nota | golden set de retrieval em **pares EN/PT** da mesma pergunta |

## 3. O que o kit já tem e as referências não (ou só a de 9,5 tem)

Supervisor que replaneja com tabela de fallback; portão "sem fonte" calibrado; checagem numérica sem LLM em todo
turno; juiz calibrado com TPR/TNR; pass^k ao vivo; gate de eval no CI; travas de honestidade do README
(números = JSON commitado, provas citadas passam); MCP server; domínio separado do motor.

## 4. Espelhado no kit v3.7.0 (a partir desta pesquisa)

| Ideia | Origem | Onde no kit |
|---|---|---|
| Ablação do replanejamento (com × sem) offline e ao vivo, no README | nelsondell | `SUPERVISOR_REPLAN`, `run_evals --ablate-replan`, bloco Replanejamento |
| Caminho do avaliador + coluna "limite conhecido" no mapa da régua | nelsondell, ArturFBrandi | README do kit §0 e §3 |
| Matriz de confusão do router como tabela no README | EikiYamashiro | bloco eval do README |
| Retrieval em pares EN/PT + ablação de retrievers commitada | jonathansschaffer, ArturFBrandi | prompt da frente K |
| Réplicas com balanceador: conversa continua, caso único e queda de réplica (revelou e corrigiu caso duplicado entre réplicas) | nelsondell, bnavarro12 | `docker-compose.scale.yml`, `scripts/scale_smoke.py`, `make scale`, CI |
| gitleaks no CI | nelsondell | `.github/workflows/ci.yml`, `.gitleaks.toml` |
| Flags de risco na saída de fintech | Buzz | `src/app/grounding.py` (`risk_flags`) |

## 5. O que não foi achado

Nenhuma nota oficial atribuída à Getnet com nome do avaliador; nenhum feedback completo do 10,0; nenhuma solução
pública com nota ≥ 9 feita DENTRO dos 60 minutos.

## 6. Atualização v5 (01/11/2026, depois da Getnet v4)

Leitura completa de 9 repositórios clonados + 13 achados na web (28 soluções no total, contando as da seção 2).
Relatórios com evidência por arquivo e linha: [pesquisa/getnet.md](pesquisa/getnet.md) (feedbacks de avaliador,
régua oficial, 15 mudanças ranqueadas) e [pesquisa/formato_swarm.md](pesquisa/formato_swarm.md) (CloudWalk +
13 repositórios novos, 10 ideias). Nenhum desses repositórios tem LICENSE (exceto Fredyycloss, MIT): só ideias.

Fatos novos que mudaram o kit:
- **Régua V4 oficial: 11 critérios** (8/15/10/10/13/8/7/14/6/5/4), Router dentro de "Agentic Reasoning &
  Orchestration", e **4 gates** (Critical Security, Challenge Fit, Evidence, Semantic Quality).
- O avaliador **não roda nada e não assiste ao vídeo**; lê um commit fixo e a autoria pelos commits.
- As notas do nelsondell por critério na V4 batem com os pesos (9,48); as 3 lacunas citadas: escala presa ao
  armazenamento, suíte que precisava de rede, factual sem validação humana.
- Nova nota pública: gabriel-dezani **9,2** (autodeclarada, régua com outros nomes, muitas versões; Infra 8,5).
- Eduardo Colissi: v2 com tags `v2-clock-start`→`v2-clock-end` (39 min 41 s) e timesheet declarando o que foi
  depois do relógio — o modelo para a nossa prova do relógio.

O que entrou no kit v5 a partir disso: ver `docs/kit/CHANGELOG.md` (v5.0.0).
