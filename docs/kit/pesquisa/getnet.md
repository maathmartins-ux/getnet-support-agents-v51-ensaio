# Pesquisa: soluções públicas do desafio Getnet ("AI Hardcore Engineer — Multi-Agent Support System")

Data: 01/11/2026. Fontes: só os 6 repositórios já clonados em `/home/user/refs/` (leitura, nenhum clone novo).
Comparado com `/home/user/kit-preflight` (o branch checado é **`kit-v5.0.0`**, não `kit-v3.7.0`; tem
mudanças staged não commitadas em `evals/run_evals.py`, `scripts/fill_readme.py`, `src/app/{agents,grounding,guardrails,router}.py`)
e com a tentativa `/home/user/getnet-support-agents-v4` (README com números).
Convenção: "**(nv)**" = não verificado / inferência minha. Citações do avaliador são literais.
O que já está em `docs/kit/REFERENCIAS.md` (ablação do replanejamento, matriz de confusão, caminho do avaliador,
coluna "limite conhecido", réplicas atrás de balanceador, gitleaks, flags de risco, pares pt/en) **não** é repetido
abaixo, exceto quando acrescento um ângulo novo.

---

## TOPO — as 15 mudanças de maior impacto na nota (ranqueadas)

Critério de ranking: peso do critério na Régua V4 × tamanho da lacuna que vejo na v4 × evidência de que o avaliador
premia/pune isso. Esforço = trabalho no kit ANTES do relógio (o relógio só preenche domínio).

| # | Mudança | Critério(s) afetado(s) (peso) | Evidência nos repos de referência | O que a v4 mostra hoje | Esforço |
|---|---|---|---|---|---|
| 1 | **Fazer cumprir a checagem numérica em vez de só sinalizar**: número da resposta que não está na evidência → 1 regeneração com a lista dos números proibidos; se persistir, troca por "[valor não confirmado]" e escala (ou responde só a parte confirmada). Somar as "regras financeiras duras" (nada de taxa/prazo/valor fora de trecho ou tool; nenhuma promessa de data futura; nenhum veredito de caso individual → humano) ao prompt E ao código | Evaluation 14%, RAG 10%, Semantic Quality Gate | Eduardo `src/guardrails/output.ts:12` (substitui e manda ao humano); nelsondell `app/graph/numbers.py:48` (`adds_numbers`) e README v1 §7 "Financial hard rules" (`git show cab65ad:README.md`); bnavarro `README.md:412-470` (`numeric_grounding_rate`) | ao vivo `numbers_acc` 64,1% (memory), 80% (official); juiz `grounded` 0,6 no official (README v4 §5). Número inventado chega ao lojista e o README mostra isso | 45 min |
| 2 | **Recuperação: subir Recall@3 de 0,486 para ≥ 0,85** — consulta reescrita em pt pelo Router (`query_pt`), híbrido BM25+denso com RRF como padrão se medir melhor, abstenção pela similaridade densa (não pelo escore RRF/BM25), gold de retrieval por **regra (regex de URL + regex de texto)** em vez de id de chunk, AUC/"gap" da abstenção no README | RAG 10% (+ Business Fit) | nelsondell `evals/retrieval_calibration.md` (AUC 1,000, gap +0,067 por embedder), README v1 §4/§9 ("`query_pt` is load-bearing. A raw English question scores 0.375 … below an off-topic Portuguese one"; "Abstention keys off **dense similarity, not the RRF score**"); Artur `evaluation/golden/README.md` (relevância por `url` regex + `text` regex, "rules survive re-crawls better than chunk ids"); avaliador pune "só lexical: sem embeddings, hybrid, RRF ou reranker" e "sem métrica de retrieval (Recall@K, MRR)" (feedback Diogo, §3) | Recall@3 **0,486**, MRR 0,61, hit@3 0,72; portão recusa só 81% dos sem fonte (README v4 §5). nelsondell: 0,939/0,851; Artur: 0,894/0,846 | 1 h |
| 3 | **Replanejamento guiado por ACHADO (não só por falha) + ablação por conclusão de tarefa**: o resultado do agente traz `needs` estruturado (ex.: Support viu terminal offline → precisa do guia do Knowledge; Knowledge achou regra por modelo → precisa do modelo do terminal no CRM); o supervisor insere um passo, com orçamento; split `dependent` (20 pedidos) medido com × sem (`MAX_PLAN_CHANGES=0`) em 3 rodadas | Orchestration 15% | nelsondell `app/graph/supervisor.py:71-86` (`revise` insere o passo do `need`), `evals/planning_report.md` (32/60 × 19/60, com custo e p95 por modo, e tabela "Why replanning still misses"); Eduardo `src/orchestration/replanner.ts:13` (terminal offline na saída da tool → adiciona Knowledge); Artur `docs/SCORECARD.md` (gatilhos: código de recusa, retry ampliado, contradição). Avaliador: "Supervisor → especialistas como tools → observa → decide → humano → retoma" (feedback Diogo, "Comparação com João") | ablação da v4 é **60% × 0%** e **93% × 0%**: o "sem" é 0 por construção (o split `replan` só mede escalar após `insufficient`/`error`). Um avaliador atento lê isso como tautologia **(nv)** | 1 h |
| 4 | **Gravar e reproduzir o eval ao vivo no CI** (cassete): o eval ao vivo grava cada resposta do LLM por hash de (papel, prompt, entrada); o CI roda o mesmo eval com um provedor "replay", sem chave; limiares = taxas da gravação aceita; requisição não gravada falha com "grave de novo" | Evaluation 14%, Production 5% | nelsondell `evals/README.md` seção "How it gates PRs" ("The floors are the accepted recording's own rates, so any drop in the replay is a regression"), `Makefile` (`eval`/`eval-offline`) | gate do CI só mede o caminho determinístico offline; os números ao vivo ficam commitados mas não protegem o código contra regressão | 1 h |
| 5 | **Validação humana do que é semântico**: (a) análise de erros — exportar ~50 traces ao vivo para CSV, rotular passa/falha com nota de 1 linha (LLM rascunha, dono revisa e diz quantas edições fez), agrupar em modos de falha, **uma checagem binária por modo** replayada no CI; (b) held-out: o dono rotula às cegas ~30 respostas ao vivo e o README mostra "automático X/N × humano Y/N" | Evaluation 14%, Semantic Quality Gate | nelsondell `evals/failure_modes.md` (27/100 falham, 5 modos, "one binary check per failure mode"), `evals/README.md` (held-out 63/80 rotulado "by the owner, blind, no model draft"); lacuna que o avaliador V4 nomeou ao 9,5: "Factual evaluation needs a bigger set and human validation" (`nelsondell/README.md:44`); bnavarro `evals/human_review.py` (rótulo cego no terminal) | juiz calibrado com 46 rótulos do autor (kappa 0,957); held-out cego mede só **intent**, não a resposta. Sem análise de erros de traces | 40 min de ferramenta no kit + 15–20 min do dono |
| 6 | **Juiz de outra família + canários**: recusar juiz da mesma família do gerador (ou declarar e usar OpenAI-compatível quando houver chave); 4 registros sintéticos com defeito conhecido (contradiz fato, afirmação sem evidência, idioma errado, vaza outro lojista) que o juiz TEM de reprovar, senão `judge_unreliable: true` no relatório | Evaluation 14% | Eduardo `eval/report.ts:100-106` (canários), `docs/plan.md:202`, README ("The runner refuses a judge of the generator's family"; o 7B local pegou 1–2/4 canários, Claude 4/4); nelsondell `evals/README.md` ("a binary judge from another model family"; "**The judge is not validated**" quando há < 10 positivos) | juiz `claude-opus-5-5` julgando respostas de Haiku/Sonnet (mesma família); sem canários | 40 min |
| 7 | **Evidência legível sem rodar nada**: `docs/DEMO.md` gerado do JSON ao vivo — tabela dos 10 cenários + seguimento + pedido composto + HITL + escrita confirmada: pergunta, agentes, status (`answered`/`degraded`/`paused`), resposta encurtada, data, SHA; e `reports/verify.md` gravado pelo `check.py` (contagens, duração, SHA) | Evidence Gate, Business Fit 8% | o avaliador **não roda nem assiste**: "Não executei build nem testes nesta correção (ambiente sem acesso ao PyPI)" (`DiogoOg16_getnet/feedback_diogoog16_v4(1).md:201`), "Vídeo … não assistido" (`:10`); Evidence Gate subiu com "logs de execução real commitados" (`:230`); nelsondell `docs/demo.md` (tabela S01–S10 com respostas reais, inclusive "degraded"), `reports/verify.md` | v4 tem `docs/video/demo.json` e `live_*.json` (2,2 MB), mas nenhuma página humana com as respostas dos 10 cenários | 30 min |
| 8 | **Dados ao vivo por API dedicada e chamados no código**: clima por Open-Meteo (geocoding + previsão da data) e câmbio por PTAX do BCB (com retroação a dia útil) ou Frankfurter; a pergunta de dado ao vivo dispara a consulta no código com consulta montada, o modelo recebe o resultado e nenhuma tool; resposta cita fonte e data. Busca web fica para notícia/assunto geral | Business Fit 8% (cenários 2 e 7), Tool & Action 10% | feedback Diogo §1/§4 elogia: "Clima (Open-Meteo) e câmbio (PTAX do Banco Central) usam fontes reais e dizem o que são"; bnavarro `app/tools/knowledge_tools.py:79-85` (Open-Meteo); Eduardo `docs/checklist.md` ("1 EUR = 1.0000 EUR" e "R$ 5,92, a value present nowhere" → busca no código); nelsondell `docs/demo.md` S02 e S07 saíram `degraded` com busca web | v4 usa a busca web do servidor Anthropic (`src/app/agents.py:44`); limite declarado: número de clima/câmbio fora da citação vira `unsupported_numbers` | 45 min |
| 9 | **CI de cadeia de suprimento e reprodutibilidade**: SBOM (syft/anchore) + trivy com falha em CRITICAL (`.trivyignore` com motivo e validade) + passo de testes com a rede cortada (`unshare --net`) + imagem sem chave sobe e responde com `--network none` + actions fixadas por SHA | Production 5%, Security 13% | nelsondell `.github/workflows/ci.yml:41` (unshare), `:88` (SBOM), `:95` (trivy), `:53` (skip conta como falha); Artur `README.md:322-330` (pip-audit, Bandit, gitleaks, Trivy, SBOM; `make security`); lacuna V4 do 9,5: "The suite did not start locally without `tiktoken`'s download" (`nelsondell/README.md:43`) | v4: gitleaks, digest, Dependabot, lockfiles (sem hash), `actions/checkout@v4` por tag | 40 min |
| 10 | **Orçamento por turno e custo por turno resolvido**: teto de chamadas de modelo e de US$ por turno + timeout por nó; estourou → entrega a parte respondida e o resto vai ao humano (`budget_exhausted`); README com "US$ por turno resolvido" e tabela por intenção (casos, p50, p95, chamadas LLM, tokens, US$) | Observability & Cost 6%, Orchestration 15% (stopping condition) | nelsondell `docs/operations.md` (`MAX_MODEL_CALLS`/`MAX_COST_USD`, `NODE_TIMEOUT_S`, alerta `CostPerResolutionHigh`), `REVIEW.md` ("US$ 0.00048 model spend per resolved turn"); Artur `README.md:341-361` (custo e latência por workflow); avaliador cobra "stopping condition" (feedback Diogo §2) | v4 tem `MAX_STEPS=4` (`src/app/supervisor.py:43`), custo por request e `/analytics` com custo por resolvido; sem teto em US$/chamadas nem timeout por nó; README não mostra custo por resolvido medido nem tabela por intenção | 40 min |
| 11 | **"Perguntas da entrevista, respondidas"** no topo do README: as 5 perguntas do feedback V4 do Diogo + as 6 da revisão do Eduardo, cada uma com arquivo, teste e número | Engineering Judgment 4% + todos (o avaliador usa essas perguntas para decidir) | feedback Diogo "Perguntas de entrevista" (5); Eduardo `README.md:14-23` e `docs/checklist.md` "The review questions" (6, respondidas com prova) | não existe | 20 min (modelo no kit; frente D preenche) |
| 12 | **Plano de piloto e caso de negócio**: por intenção, shadow → assistido → autônomo com portões numéricos e rollback por alerta; tabela custo × benefício mensal separando **medido** de **suposição** | Business & Challenge Fit 8% | nelsondell `docs/pilot.md` (ordem das intenções pela "Rule of Two", portões por mudança de estágio, rollback, "Only A and C are measured") | v4 tem KPI "resolução automática sem número inventado"; sem piloto/rollout | 30 min (modelo) |
| 13 | **OWASP Top 10 for Agentic Applications (2026), ASI01–ASI10** mapeado a controle e teste + red team de ~40 casos com página web e trecho do corpus "plantados", replayado no CI | Security & Identity 13% | nelsondell `docs/security.md` (tabela ASI01…ASI10 com "Tested in"), `evals/red_team.jsonl` (40/40), `REVIEW.md` linha Security | v4 `docs/THREAT_MODEL.md:45-49` mapeia STRIDE + OWASP **LLM** 2025; split `guardrail` com 38 casos | 45 min |
| 14 | **Superfície de demo**: `/ui` do lojista (chat que mostra agentes, passos, fontes, status do caso e a resposta do operador chegando) + perfil `observability` no compose (Prometheus + Grafana com dashboard JSON provisionado + Jaeger) | Business Fit 8%, Observability 6% | Skywalker (o "benchmark 10,0") tem frontend com passos aninhados, Telegram e Langfuse no compose (`farrulla-darze_skywalker/README.md`, seção "Visão geral"); Artur `/ui` + `/operator` + `make observability-up` (20 painéis, 9 alertas); nelsondell `make observe`, `deploy/grafana/dashboards/support.json` | v4 só tem `/operator` (`src/app/static/operator.html`); limite declarado "sem dashboard provisionado" | 1 h |
| 15 | **Prova do relógio legível no git**: tags `clock-start`/`clock-end`, `docs/TIMESHEET.md` gerado do log (dentro × depois do relógio, cada `fix:` pós-relógio declarado), commits com cadência real; nunca 30 commits de 6 frentes em 6 minutos | Challenge Fit Gate, Evidence Gate, Judgment | Eduardo `docs/timesheet.md` e tags `v2-clock-start`→`v2-clock-end` (39 min 41 s); nelsondell `docs/history.md` (um commit por tarefa `<type>(T-id)`, tag `v1`); o avaliador checa "Autoria pelos commits" e se "O núcleo foi implementado no próprio código" (feedback Diogo `:10`, `:222-225`) | v4: 41 commits, de 19:57:56 a 20:04:48 há 30 commits (spec com 46 casos 1 min após o scaffold; 4 frentes "pronto" em 4 min). Lê-se como pré-fabricado **(nv: não sei se o avaliador pune)**; 74% das linhas são do kit | 15 min |

Fora do top 15, mas baratos (≤ 20 min cada): `/ready` que diz o que não está pronto (nelsondell `docs/operations.md`,
Eduardo); checagem de jargão no texto ao lojista ("trecho", "segundo o site", "[n]") (nelsondell `failure_modes.md`
modo 1); armadilhas de alucinação no golden ("Get Ultra Pro", plano "Diamante") (Artur `evaluation/golden/README.md`);
nível `forbidden` explícito na política de tools (Artur `README.md:151-163`); "tráfego de ataque nunca abre caso
humano" (Artur `docs/initial-prompt.md:529`); alerta de taxa de escalonamento ≈ 0 = handoff quebrado (bnavarro
`README.md` §7); ADR "considerado e não feito" (nelsondell `docs/adr/0008-considered-not-doing.md`); benchmark de
modelo do Router (5 candidatos × golden, com custo) (nelsondell `evals/router_benchmark.md`) — a v4 declara "modelo
por papel não foi comparado em custo × qualidade"; offline em inglês responder em inglês (v4 `language_acc` offline
official 50%; o avaliador puniu Diogo por "respostas em português mesmo para perguntas em inglês"); usar no mapa do
README os **nomes oficiais** dos 11 critérios (a v4 usa "Orchestration", "Router", "Human Oversight", "Evaluation &
Quality"; o oficial é "Agentic Reasoning & Orchestration", sem linha própria para Router).

---

## 1. Feedbacks de avaliador, régua, faixas e padrões de erro

### 1.1 Arquivos de feedback/nota encontrados

| Repo | Arquivo | Natureza |
|---|---|---|
| DiogoOg16 | `feedback_diogoog16_v4(1).md` (293 linhas, lido inteiro) | **Feedback do avaliador, Régua V4**, nota 4,7, quadro por critério, gates, perguntas de entrevista. Fonte mais valiosa |
| nelsondell | `REVIEW.md`, `README.md` ("Since V4"), `docs/history.md` | Guia do candidato com as **notas V4 por critério** (batem com os pesos oficiais: Σ = 9,48 ≈ 9,5) e as notas da v1 numa régua antiga |
| EduardoColissi | `README.md:7-31`, `docs/checklist.md`, `docs/spec.md`, `docs/plan.md:10-20` | Resumo da revisão da v1 feito pelo candidato: memória 1,0/10, HITL 4,0/10, as 6 perguntas literais do revisor e a lista do que foi "rated strong" |
| ArturFBrandi | `docs/SCORECARD.md`, `docs/initial-prompt.md:83-112` | Régua escrita pelo **candidato** (pesos somam 108%, não são os oficiais) com "What a 10 requires" e "Common reasons strong submissions lose points" (**nv**: origem não dita; parece destilada de feedbacks) |
| bnavarro12, Skywalker | — | Nenhum feedback no repo |

### 1.2 Régua V4 oficial (nomes e pesos confirmados no feedback do Diogo)

"Cálculo com os pesos oficiais da Régua V4 (soma = 100%): 4,725." (`DiogoOg16_getnet/feedback_diogoog16_v4(1).md`)

| Critério V4 (nome oficial) | Peso | Diogo (4,7) | nelsondell V4 (9,5) |
|---|---:|---:|---:|
| Business & Challenge Fit | 8% | 6,5 | 9,5 |
| Agentic Reasoning & Orchestration | 15% | 4,5 | 9,5 |
| Context, Knowledge & RAG | 10% | 6,5 | 9,7 |
| Tool & Action Engineering | 10% | 5,5 | 9,5 |
| Security & Identity | 13% | 4,5 | 9,3 |
| Memory, State & Resilience | 8% | 1,0 | 9,4 |
| Human Oversight & Risk Management | 7% | 1,5 | 9,7 |
| Evaluation & Quality Engineering | 14% | 5,5 | 9,7 |
| Observability, Reliability & Cost | 6% | 3,5 | 9,2 |
| Production Engineering | 5% | 6,0 | 8,6 |
| Engineering Judgment | 4% | 7,0 | 9,8 |

São **11** critérios: "Router" não é critério separado, está dentro de "Agentic Reasoning & Orchestration" (a lista
do pedido tinha 12). Notas do nelsondell por critério: `nelsondell_multi-agent-support-system/REVIEW.md:11-21`
(entre parênteses na 1ª coluna). Os pesos do Artur (`docs/SCORECARD.md`: 10/15/10/10/13/8/7/14/7/6/8 = 108%) **não**
são os oficiais. O kit (`docs/kit/PLAYBOOK.md` §5) já usa os oficiais.

**Gates V4** (feedback Diogo `:215-240`), com as frases do avaliador:
- *Critical Security Gate* — "Não acionado, com ressalva. Sem autenticação, mas a consulta de transação valida o dono. O log de PII em texto puro é um problema de privacidade a corrigir…"
- *Challenge Fit Gate* — "Não acionado. O núcleo foi implementado no próprio código, com fontes oficiais da Getnet."
- *Evidence Gate* — "**Médio.** Código + 82 testes + logs de execução real commitados. Não executei a suíte nesta correção."
- *Semantic Quality Gate* — "**Não comprovado.** Não há medição de qualidade das respostas."

**Faixas da régua citadas** (únicas visíveis): Orchestration "Faixa da régua: **routing (4–6)**, no limite inferior por
ser exclusivamente lexical." (`:76`); HITL "Faixa da régua: **apenas flag/escalation (0–2)**." (`:156`). Inferência
**(nv)**: as faixas altas são "supervisor que observa e replaneja" (Orchestration 8–10) e "humano no fluxo que devolve
ao agente" (HITL 8–10), pelo contraste com o benchmark: "Supervisor → especialistas como tools → observa → decide →
humano → retoma".

**Benchmark**: "Benchmark: **João / Skywalker = 10,0**" e "João é superior em todos os critérios técnicos: supervisor
com especialistas como tools, RAG mais completo, autenticação, memória, HITL via Telegram, evals e observabilidade."
Observação: o Skywalker atual não tem CI, tem retrieval denso puro e 12 arquivos de teste unitário
(`farrulla-darze_skywalker/README.md`, "Limitações conhecidas"). Inferência **(nv)**: a régua é relativa ao
benchmark, e o que pesa nele é o desenho agentic visível (agente-como-tool, HITL síncrono demonstrável no celular,
UI com passos, Langfuse), não o rigor de CI.

**Como o avaliador trabalha** (importa para a forma da entrega):
- "Avaliação da branch `main`, commit `1abb2a0` (23/10/2026). Autoria pelos commits … Vídeo informado em `video.txt` (Google Drive), **não assistido**." (`:10`)
- "Não executei build nem testes nesta correção (ambiente sem acesso ao PyPI)." (`:201`)
- O avaliador do nelsondell **tentou** rodar a suíte localmente: lacuna "The suite did not start locally without `tiktoken`'s download" (`nelsondell/README.md:43`).
- Conclusão: a nota sai da leitura do código, do README e dos artefatos commitados; o que não está escrito/commitado não existe.

### 1.3 Frases-chave do avaliador, por critério (literais, curtas)

Arquivo: `/home/user/refs/DiogoOg16_getnet/feedback_diogoog16_v4(1).md`.

- Teto: "O teto vem da arquitetura: nenhum LLM decide rota ou tool, não há sequência entre agentes, o Customer Support não usa dados do cliente nos cenários oficiais, e não há memória, autenticação nem HITL além de uma flag."
- Business Fit: cenário 3 "vai para o Support, mas responde um texto genérico … **sem consultar nenhum dado** do `cliente1988`"; cenários 5 e 8 "são roteados para o Knowledge, não para o Support, então não há diagnóstico do terminal nem consulta à transação"; "respostas em português mesmo para perguntas em inglês".
- Orchestration: "Router 100% por regras, sem LLM"; "Escalonamento não é um agente: é um dicionário fixo dentro do orquestrador."; "Não há sequência entre agentes, estado compartilhado, loop de tools, replanejamento ou stopping condition."; "O enunciado pede que o Router decida 'qual agente (ou sequência de agentes)'; só a primeira parte foi implementada."
- RAG (elogio): "corpus real e rastreável, com URL e timestamp por chunk"; "relevance gate com abstenção"; "correção registrada de colisão de stem". (puniu): "só lexical: sem embeddings, hybrid, RRF ou reranker"; "`_direct_answer` tem dezenas de respostas escritas no código … não passam pelo retrieval e não citam a fonte"; "limiares … 'calibrados com as perguntas de teste', sem métrica de retrieval (Recall@K, MRR)"; "corpus estático, sem rotina de atualização."
- Tools (elogio): "`lookup_transaction` só devolve a transação se ela pertencer ao `user_id`"; "o LLM nunca escolhe identidade"; "Web Search com **allowlist de domínios**"; "timeouts nas chamadas externas". (puniu): "tools escolhidas por palavras-chave, sem function calling e sem schema"; "`tool_used: \"settlement_timeline\"` no cenário 3 rotula como tool um texto fixo"; "não há liquidação, terminal ou recusas".
- Security: "sem autenticação: o `user_id` vem do body"; "**`main.py` loga a mensagem completa antes do roteamento**"; "sem mascaramento de PII, sem rate limiting"; "guardrails apenas por regex".
- Memory: "Não há memória. Cada request é independente, sem sessão e sem histórico."
- HITL: "devolve `handoff_required: true` e uma mensagem fixa. Não há ticket, fila, protocolo ou humano no fluxo."
- Evaluation: "não há dataset de eval versionado, métrica de routing/retrieval nem juiz"; "a qualidade semântica das respostas não é medida"; "sem CI". (elogio) "LLM substituído por fake em todos os testes"; "matriz de roteamento com os 10 cenários oficiais, equivalentes em português e falsos positivos"; "**logs de execução real** commitados".
- Observability: "Faltam `trace_id`, latência por etapa, tokens, logs estruturados em JSON, métricas e alertas"; "Os logs registram PII."
- Production: "container roda como root"; "testes copiados para a imagem de produção"; "`ollama/ollama:latest` sem versão"; "sem lockfile com hash e sem CI."
- Judgment (elogio): "router por regras escolhido conscientemente por previsibilidade, com o custo declarado"; "RAG lexical declarado como lexical"; "abstenção preferida a resposta inventada". (puniu): "as respostas diretas no código e o texto genérico do cenário 3 resolvem casos por atalho, em vez de pela arquitetura." E: "A honestidade da documentação é um ponto positivo de postura, não de capacidade."
- Perguntas de entrevista (5): dado do cliente no cenário 3; por que "transação recusada" vai ao Knowledge; como Support e Knowledge colaboram na mesma resposta; CPF colado e o log; "Como você mediria se o BM25 está recuperando bem? Que dataset e que métrica usaria antes de trocar por embeddings?"

Outros avaliadores/revisões (via candidato):
- nelsondell V4, 3 lacunas (`README.md:42-44`): "Horizontal scale and HA depend on how storage evolves"; "The suite did not start locally without `tiktoken`'s download"; "Factual evaluation needs a bigger set and human validation".
- nelsondell v1 (régua antiga, `docs/history.md`): Memory 1,5; HITL 5,8; Infra/Docker 6,8; Product 7,5; Multi-agent 8,8; Obs/evals 9,1; Tests 9,2; Architecture 9,5; Security 9,5; RAG 9,8; Trade-offs 10,0 → **8,7** com Docker nunca construído e `[preencher]` no README (`git show cab65ad:README.md`: "Not verified. Docker was unavailable…").
- Eduardo v1 (`README.md:7`, `docs/spec.md`): "weak memory (1.0/10), authentication, human-in-the-loop (4.0/10) and evaluation"; "'handoff' opened a ticket and stopped"; "quality was measured with lexical checks only, and the one real run was not versioned". As 6 perguntas do revisor (`docs/checklist.md`, "The review questions"): onde acontece a autenticação e como `user_id` deixa de vir do payload; como a conversa sobrevive entre requests e a restart; como o operador recebe, responde e devolve o controle; como a resposta final é provada correta e fundamentada; o que faz o sistema replanejar após observar um especialista; que artefatos provam que Docker, eval ao vivo e fluxos críticos foram executados.

### 1.4 Padrões de erro que derrubaram nota (consolidado)

1. Router só por regex; um agente por mensagem; nenhuma sequência/estado compartilhado/replanejamento (Diogo 4,5).
2. Support que não lê dado do cliente nos cenários oficiais 3, 5 e 8 (Diogo); "texto fixo rotulado como tool".
3. Sem memória (Diogo 1,0; Eduardo 1,0; nelsondell v1 1,5).
4. HITL como flag ou ticket que não volta ao fluxo (Diogo 1,5; Eduardo 4,0; nelsondell v1 5,8).
5. `user_id` do corpo como identidade; PII crua em log.
6. Eval só estrutural/lexical, run real não versionado, sem juiz, sem CI.
7. Respostas escritas no código ("atalho, em vez de pela arquitetura").
8. Imagem root, `:latest`, testes na imagem, sem lock com hash.
9. Suíte que precisa de rede para começar (nelsondell V4).
10. Escala/HA presas a armazenamento local (nelsondell V4) — a v4 declara "réplicas só no mesmo host (SQLite)".
11. Factual sem validação humana (nelsondell V4).
12. Resposta em pt para pergunta em en.

---

## 2. Por critério: (a) melhor prática vista, (b) o kit/v4 já tem?, (c) o que falta e proposta ≤ 1 h

### Business & Challenge Fit (8%)
- (a) nelsondell `docs/demo.md` (S01–S10 com resposta real e status, inclusive `degraded`) e `docs/pilot.md` (rollout por intenção, custo × benefício medido × suposto); Artur `README.md:12-24` ("5-minute evaluator path", `make demo-scenarios` em PT+EN e `make demo-conversation` com restart da API no meio).
- (b) v4: 10 cenários como split `official` (100% intent ao vivo), caminho de 5 min, CRM com datas relativas. Falta página legível com as respostas e o piloto.
- (c) Mudanças #7 e #12. Também: `make demo-conversation` (roteiro de 1 conversa: memória com restart → dependência → escalonamento → resposta do operador → próximo turno usa) gravando a transcrição em `docs/DEMO.md` — 30 min.

### Agentic Reasoning & Orchestration (15%) — inclui o Router
- (a) nelsondell `app/graph/supervisor.py:71-96` (passo adicionado por `need`, orçamentos de mudança de plano/chamadas/custo, `halt`) e `evals/planning_report.md`; Skywalker especialistas como tools do roteador (`app/modules/agents/runner.py:239`, `tool_plain`), roteador dono do histórico; Artur `README.md:71-85` (tabela "The LLM proposes, deterministic code disposes" por preocupação), ADR 010 (supervisor × fan-out estático medido ao vivo: 3/3 × 0/4, 2,2× latência → teto de 1 passo proposto pelo LLM por turno). Router: nelsondell `evals/router_benchmark.md` (5 modelos × golden, `gpt-6-luna` 54/56 a 1/19 do custo de `gpt-6-sol`).
- (b) v4: supervisor LLM com agentes como tools e tabela de fallback, paralelo, ablação com × sem, matriz de confusão, k-NN offline, teste de contaminação do held-out. Replanejamento só reage a `insufficient`/`error`.
- (c) Mudança #3 (replan por achado + ablação por conclusão) e #10 (stopping condition por orçamento). Router: benchmark Haiku × Sonnet no golden de roteamento com US$ (20 min ao vivo, < US$ 0,50). Tabela "LLM propõe / código decide" no README (10 min, texto).

### Context, Knowledge & RAG (10%)
- (a) nelsondell README v1 §4 (parser por rota confirmado em arquivo real, dedup por SHA com contagem, abstenção pela similaridade densa), `evals/retrieval_calibration.md` (3 embedders × 97 perguntas, AUC, gap), `evals/rerank_benchmark.md` (Cohere +0,024 recall@5 a 618 ms p95, fica opt-in, ADR 0002); Artur gold por regras de URL/texto + 68 itens com fatos atômicos e armadilhas; Skywalker chunk com cabeçalho hierárquico prefixado ao texto embutido, overlap só dentro da seção.
- (b) v4: BM25 + glossário pt↔en, híbrido atrás de flag, rerank Haiku, portão calibrado, pares pt/en, SHA/URL/data por trecho, documento envenenado descartado. Recall@3 0,486.
- (c) Mudança #2. Extra (15 min): chunk de tabela inteira (o próprio README v4 registra a tabela Get Clássica × Get Smart cortada) e cabeçalho da seção prefixado ao trecho.

### Tool & Action Engineering (10%)
- (a) nelsondell `app/tools/account.py:112` (`InjectedState`: `user_id` fora do schema do modelo) e `:199` (argumentos filtrados ao schema antes de injetar a identidade), ADR 0005 (uma escrita, executada uma vez na confirmação, auditada); Artur política em 4 níveis com `forbidden` explícito (`README.md:151-163`), "Foreign and missing rows are indistinguishable (`not_found`)"; Eduardo saída da tool já com o que o modelo pequeno erra (dia da semana, "hoje/amanhã/ontem", significado do código de recusa calculados no código).
- (b) v4: JSON Schema estrito, identidade do servidor, 3 leituras + 3 escritas com confirmação, quatro olhos em `high`, TTL, execução única entre réplicas, MCP.
- (c) Mudança #8 (clima/câmbio como tools reais). Mais (15 min): `forbidden` explícito e "estrangeiro = inexistente" no retorno da tool; datas relativas e significado de código de recusa calculados na tool.

### Security & Identity (13%)
- (a) nelsondell `docs/security.md` (RS256/JWKS, papéis merchant/operator/supervisor, auditoria append-only por trigger, apagamento LGPD `DELETE /me/conversations/{id}`, retenção `make purge`, OWASP Agentic ASI01–ASI10 com teste por linha), `evals/red_team.jsonl` (40, 10 adaptativos, página e trecho plantados); Artur `make security` (pip-audit, Bandit, gitleaks, Trivy; falha de verdade, sem `|| true`) e canário no guardrail de saída; Eduardo "body `user_id` ≠ `sub` → 403 antes de qualquer chamada de modelo".
- (b) v4: JWT HS256 com exp/iss/aud/jti e revogação, operador com chave pessoal, rate limit que falha fechado, `AUTH_MODE`, guardrails regex + Haiku com desofuscação, PII mascarada em entrada/log/saída, STRIDE + OWASP LLM 2025.
- (c) Mudança #13 e #9. Extra (20 min): apagamento e retenção LGPD (endpoint `DELETE /me/conversations/{id}` + purga por idade, auditados, com teste). Na v4 a LGPD só aparece como categoria de ativo em `docs/THREAT_MODEL.md:14`; não achei endpoint de apagamento.

### Memory, State & Resilience (8%)
- (a) nelsondell checkpoints em SQLite ou Postgres, réplica morta no meio do turno e turnos serializados por `pg_advisory_xact_lock` no CI (`ci.yml:110-127`, `docs/operations.md` "Scaling out"); Eduardo compactação **sem LLM** que copia ids/valores/datas literalmente ("lossy but cannot invent a value"), reescrita do seguimento em `standalone_query` só quando há histórico (e checagem de que não reescreve mensagem única); Artur idempotency key cujo replay de outro sujeito não conta como replay.
- (b) v4: SQLite WAL, resumo rolante, memória de longo prazo, 2 réplicas no mesmo host, queda de réplica no smoke, caso único entre réplicas. Reescrita do seguimento em pergunta autônoma: **não encontrei** no `router.py`/`pipeline.py` (grep por standalone/rewrite) **(nv)**.
- (c) 30 min: `standalone_query` do Router usada pelo RAG + caso de eval "sem reescrita espúria em mensagem única". Postgres atrás de `Store` é > 1 h (fica como limite declarado; é a lacuna que o V4 nomeou ao 9,5).

### Human Oversight & Risk Management (7%)
- (a) nelsondell `app/graph/human_review.py:170` (`interrupt()` com aprovar/responder/cancelar; o plano **continua os passos restantes** depois da resposta; TTL; notas enquanto espera); Eduardo máquina de estados `pending → resuming → completed`, CAS em `version` (409), entrega exatamente uma vez (`UNIQUE(handoff_id)`), recuperação no boot; Skywalker `consult_human` síncrono ("o agente nunca larga a conversa"), demonstrável em 3 min pelo Telegram com polling sem túnel.
- (b) v4: fila persistida, `/operator`, retomada imediata, quatro olhos, SLA com re-escalonamento único, Telegram ida e volta, "duas respostas simultâneas, só uma vence".
- (c) 30 min: depois da resposta do operador, **executar os passos que faltavam do plano** (nelsondell: "the plan resumes after the reply"). Na v4, `src/app/resume.py:1-9` redige na hora uma mensagem a partir da resposta humana (corrige o feedback interno da v2 citado ali: "a resposta humana não retoma o plano, aparece só no próximo turno"), mas não roda os passos restantes do plano (ex.: a parte de Knowledge de um pedido composto). Mais: recuperação de resolução interrompida no boot (Eduardo) e teste que prova as duas.

### Evaluation & Quality Engineering (14%)
- (a) nelsondell (análise de erros → modos → checagem binária por modo → replay no CI; held-out rotulado pelo dono às cegas; "judge not validated" dito com números); Eduardo (juiz de outra família, canários, N rodadas com dispersão, baseline com gate por juiz, relatório carimbado com build da API e commit do runner, "Reference facts were written before the build"); Artur (126 casos, 17 multi-turno, 7 HITL, 6 supervisor, cobertura 90,9% com gate, `--strict`, `live.yml` agendado); bnavarro (painel de juízes de 2 provedores com concordância e kappa ponderado; "forbidden terms"; o handoff entra como evidência para o juiz não punir o protocolo).
- (b) v4: gate offline, splits, held-out cego (intent), pass^3, juiz com kappa/TPR/TNR, IC95, matriz de falhas. É a parte mais forte do kit.
- (c) Mudanças #4, #5, #6. Extra (10 min): fatos de referência dos 10 cenários escritos e commitados no commit da SPEC (antes do código).

### Observability, Reliability & Cost (6%)
- (a) nelsondell spans OTel GenAI sem conteúdo, custo por resolução, resolução por intenção, escalonamentos por motivo, p50/p95 por nó, 4 alertas com runbook; Artur 30+ métricas, `docs/SLO.md` (SLO → SLI em PromQL → alerta, inclusive custo/hora e "RAG sem evidência"), disjuntores, timeouts por dependência listados; Skywalker Langfuse com versão de prompt ligada à geração.
- (b) v4: log JSON com `trace_id`, US$/tokens por request, `/metrics`, alertas Prometheus, `/analytics`, OTel opcional.
- (c) Mudanças #10 e #14. Extra (15 min): `docs/SLO.md` no formato SLO/SLI/alerta.

### Production Engineering (5%)
- (a) nelsondell CI ubuntu (rede cortada) + macOS, Postgres de serviço, SBOM, trivy, réplica morta, `reports/verify.md`; Artur migrações Alembic com `alembic check`, imagem 833 MB com modelos em volume com checksum, bootstrap para Ubuntu limpo; bnavarro CI em SQLite e Postgres.
- (b) v4: multi-stage não-root por digest, Dependabot, lockfiles, smoke do container, 2 réplicas no CI.
- (c) Mudança #9. Extra: lock com hash (`pip-compile --generate-hashes`/`uv`) — o avaliador citou "sem lockfile com hash" (10 min).

### Engineering Judgment (4%)
- (a) nelsondell ADR "considerado, não feito" (MCP, K8s, cascata de modelo, cache semântico, com o gatilho para revisitar) e "cada escolha medida"; Diogo elogiado por declarar o lexical como lexical; Eduardo "No framework … ~300 lines that are easier to test and explain".
- (b) v4: 7 ADRs, limitações honestas, kit declarado.
- (c) Mudança #11; ADR 0008-like (10 min); benchmark de modelo do Router (ver Orchestration).

---

## 3. Ideias de engenharia para copiar como IDEIA (mecanismo, sem código)

1. **Eval gravado e replayado** (nelsondell): a rodada ao vivo grava cada resposta por chave da requisição; o CI responde da gravação, sem chave e sem rede; os pisos do gate são as taxas da gravação aceita; mudança de prompt exige regravar. Faz a qualidade semântica virar gate de CI.
2. **Análise de erros antes das métricas** (nelsondell `failure_modes.md`): 100 pedidos amostrados → rótulo passa/falha + nota → agrupar pela 1ª falha → corrigir as óbvias → uma checagem por modo restante (código quando dá, juiz binário quando não). Inclui tabela "antes/depois" por versão de prompt e a regra "manter a mudança só se melhora nas 3 rodadas" (T-58 revertida porque melhorou em 1 de 3).
3. **Held-out rotulado por humano, às cegas, sem rascunho de modelo** e comparado com as checagens automáticas (63/80 humano × 95/100 automático) — mostra o viés do tuning.
4. **Ablação por conclusão de tarefa, com custo e latência por modo e 3 rodadas** (nelsondell `planning_report.md`), mais a tabela "por que ainda falha" com causas classificadas por código.
5. **Calibração da abstenção por AUC e "gap"** (menor escore dentro do domínio − maior fora) para vários embedders; abstenção pela similaridade densa absoluta, não pelo RRF.
6. **Gold de retrieval por regra** (regex de URL + regex de texto), que sobrevive a recrawl; fatos atômicos por pergunta + armadilhas de alucinação (produto inexistente) (Artur).
7. **Juiz com canários** (Eduardo): registros sintéticos com defeito conhecido que o juiz tem de reprovar; senão o relatório se marca `judge_unreliable`. Juiz de outra família; gate de rubrica só contra baseline do mesmo juiz.
8. **Painel de 2 juízes de provedores diferentes** com concordância (exata, ±1, kappa ponderado) e calibração humana cega; a discordância grande achou defeito do juiz (o protocolo de handoff não era evidência) (bnavarro).
9. **Checagem numérica que bloqueia** (Eduardo): valor ausente da evidência → "[valor não confirmado]" + humano; e o cuidado de bnavarro: soma correta também é sinalizada (a tool não devolve total) — o kit deve deixar a tool devolver o total para não punir aritmética correta.
10. **Dados ao vivo resolvidos no código** (Eduardo): pergunta de câmbio/clima detectada (flag do Router ou detector estreito) → busca/API chamada com consulta montada ("cotação do euro hoje em reais") → o modelo recebe resultados e nenhuma tool. Evita o modelo pequeno copiar exemplo do prompt.
11. **CI com a rede cortada** (`unshare --net`) e imagem que sobe e responde com `--network none`; tokenizer/modelos commitados com hash; "skip conta como falha" no teste de réplicas.
12. **Teste de morte de réplica no meio do turno** com checkpoint por passo e lock por conversa no banco (o retry na outra réplica retoma do último passo). A v4 já derruba réplica no smoke; o mecanismo novo é "no meio do turno" + lock de conversa no banco.
13. **SBOM + trivy CRITICAL com `.trivyignore` que exige motivo e validade**; actions fixadas por SHA.
14. **Custo por turno resolvido** = gasto total ÷ turnos resolvidos sem humano (o gasto dos escalados é carregado pelos resolvidos), como painel e alerta; tabela por workflow (Artur) e caso de negócio por mês (nelsondell `pilot.md`).
15. **Orçamento por turno** (chamadas de modelo, US$, mudanças de plano, hops) com saída `budget_exhausted` que entrega a parte respondida.
16. **Tráfego de ataque não abre caso humano** só por baixa confiança (Artur), para não queimar operador.
17. **Confiança do Router por sinais do sistema, não autoavaliação do LLM** (Artur `initial-prompt.md:529`: penalidades por falta de evidência, entidade ausente, contradição, falha de tool…). nelsondell declara "Router confidence is self-reported" como limite.
18. **README e caminho do avaliador**: nelsondell abre com tabela Agents/Stack/Run/Verify/Evals e "Go deeper" com links; REVIEW.md "Criterion → Evidence → Reproduce offline → Known limit"; Eduardo responde as perguntas do revisor ANTES de tudo e faz `checklist.md` "brief + review, point by point" (requisito → onde → prova); Artur "5-minute evaluator path" com 4 comandos e `make verify` que imprime tabela-resumo.
19. **Como gravam o vídeo**: Artur `docs/ROTEIRO_VIDEO.md` — ~5 min, ~750 palavras faladas em PT palavra por palavra, cenas com tempo (0:00–0:25…), abas abertas na ordem (README, ARCHITECTURE, /ui, /operator, Jaeger, Grafana, relatório ao vivo), "[CORTE]" na espera de 25–40 s do LLM, narração só cita o que se repete entre execuções. Skywalker e bnavarro: link no topo do README (Drive/YouTube com miniatura). Eduardo: limite de 15 min, gravado depois do branch. Lembrete: o avaliador V4 do Diogo **não assistiu** o vídeo; o vídeo não substitui evidência escrita. A v4 tem vídeo legendado **sem narração**; o enunciado pede "your reasoning, architecture decisions" — narração (mesmo TTS) **(nv)** tende a pesar mais.
20. **Revisão adversarial pós-relógio declarada** (Eduardo `docs/timesheet.md`): 3 rodadas de revisão do diff por agente independente + reavaliação contra a mesma régua + caminhada manual pelo plano de testes começando pelo exemplo do próprio feedback; cada achado vira `fix:` com teste, marcado como pós-relógio. Artur fez o mesmo no prompt ("act as an adversarial senior engineer scoring a competing candidate with the rubric").
21. **SDD com tarefas = commits** (nelsondell `CLAUDE.md`: "Conventional Commits, one per task … `<type>(<T-id>)`", "do not write application code until specs/tasks.md exists"): o `git log` vira a lista de tarefas com critério de pronto.

---

## 4. Tempo e padrão de commits (git log)

| Repo | 1º → último commit | Duração | Commits | Padrão |
|---|---|---|---|---|
| nelsondell | 01/09/2026 14:26 → 26/10/2026 10:56 | ~55 dias | 93 (67 Juniordell, 23 Nelson Dell, 3 dependabot) | **v1 em 60 min**: scaffold 14:26:27 → `build(T-14)` 15:26:56 (tag `v1`), 17 commits no dia, 1 por tarefa `<type>(T-xx)`, intervalos de 1–6 min; 3.826 linhas em 61 arquivos, 78 testes. v2/v3 de 13/10 a 26/10 (T-15…T-65) a convite do avaliador |
| farrulla-darze/Skywalker | 18/02/2026 17:31 → 17/09/2026 15:47 | ~7 meses | 14 | "kick starter" (1 commit) + "video link" em 18–19/02; reestruturação grande em 28–29/07 (10 commits); 2 de Langfuse em 17/09. Commits grandes, sem T-ids. Versão avaliada pelo V4: não identificada **(nv; provavelmente o HEAD de 17/09, anterior ao feedback de 23/10)** |
| ArturFBrandi v2 | 19/10/2026 14:34 → 20/10/2026 13:48 | ~23 h 14 min | 19 | Fases grandes ("Phase 0-1", "Phases 2-3", "Phase 4-7"), madrugada de correções após eval ao vivo, último dia com roteiro do vídeo e link. 40 mil linhas |
| bnavarro12 | 20/10/2026 01:10 (−03) → 25/10/2026 16:41 UTC | ~5,6 dias | 6 | Commits gigantes, um deles "Add files via upload" (upload pela web); tags `v1.0` (20/10), `v2.0` e `v2.1` (21/10) |
| DiogoOg16 | 17/10/2026 20:12 → 01/11/2026 14:10 | ~15 dias | 38 | 14 commits em 18/10; mensagens "Final", "Final1", "Modificacao EMERGENCIA", "Etapa 1 feita"; o commit avaliado `1abb2a0` (23/10) **não existe** no histórico clonado (histórico reescrito **nv**); commits pós-feedback de 24/10 a 01/11 |
| EduardoColissi | 25/10/2026 20:10 → 30/10/2026 02:17 | ~4 dias e 6 h | 88 | v1: 21 commits com o **mesmo segundo** (20:10:16–17), sinal de replay/rebase; tag `v1-submission` 27/10 00:13. v2: SDD antes do relógio, tags `v2-clock-start` 29/10 12:52:29 → `v2-clock-end` 13:32:10 (**39 min 41 s**, 19 commits), depois ~30 `fix:`/`docs:` declarados como pós-relógio em `docs/timesheet.md` |
| (nossa v4) | 01/11/2026 19:57:56 → 20:32:01 UTC | 34 min | 41 | 30 commits em 6 min 52 s (19:57:56–20:04:48), inclusive "fork x: pronto" de 4 frentes em 4 min; 74% das linhas vêm do kit |

Leitura: a única nota alta pública **dentro** de 60 min continua sendo a v1 do nelsondell (8,7, régua antiga) — e
ela tinha Docker nunca construído e Router nunca rodado com modelo real, mas um README de decisões muito claro
(fronteira entre agentes por uma pergunta, identidade injetada fora do schema, regras financeiras duras,
limitações com números). Na Régua V4, nenhuma nota ≥ 9 foi feita em 60 min.

---

## 5. Licenças

| Repo | LICENSE | Observação |
|---|---|---|
| nelsondell_multi-agent-support-system | ausente | `pyproject.toml` sem campo de licença |
| farrulla-darze_skywalker | ausente | — |
| ArturFBrandi_ai-hardcore-engineer-v2 | ausente | — |
| bnavarro12_getnet-multi-agent | ausente | — |
| DiogoOg16_getnet | ausente | — |
| EduardoColissi_agents-orchestration | ausente | só `"license": "ISC"` em `package.json` (metadado npm, sem arquivo de licença) |

Sem arquivo LICENSE, o padrão é "todos os direitos reservados": aproveitar **ideias e mecanismos**, nunca trechos de
código ou de texto. O caso do Eduardo (ISC só no `package.json`) é ambíguo **(nv juridicamente)**; trate igual.

Outros repositórios presentes em `/home/user/refs/` e fora do pedido (EikiYamashiro, jonathansschaffer,
luiznogueira1210 — desafio CloudWalk/InfinitePay): sem arquivos de feedback (busca por feedback/review/scorecard
não achou nada neles); já resumidos em `docs/kit/REFERENCIAS.md`.
