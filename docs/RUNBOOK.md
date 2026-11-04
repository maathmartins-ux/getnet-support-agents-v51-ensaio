# Runbook dos alertas

Um bloco por regra de `ops/alerts.yml` (a anotação `runbook_url` de cada regra aponta para cá; `tests/test_alerts.py`
reprova alerta sem bloco). Cada bloco diz o que o alerta significa, como confirmar antes de agir, o que fazer e quando
escalar. Os comandos assumem a API em `localhost:8000` e o Prometheus do perfil `observability` do compose.

## LatenciaAltaDoTurno

- **O que significa:** a média de cada chamada de agente passou de 8 s por 10 min; o cliente espera mais que o
  aceitável e o orçamento por turno (`NODE_TIMEOUT_S`) começa a cortar passos (`budget_exhausted`).
- **Como confirmar:** em `/metrics`, `span_latency_ms_sum{span="agent"}` / `_count` nos últimos 5 min; o p95 do
  agente sai do histograma no Prometheus:
  `histogram_quantile(0.95, sum by (le) (rate(span_latency_ms_bucket{span="agent"}[5m])))` (troque `agent` por
  `llm`, `router` ou `turn` para outra etapa; o painel "Latência p95 por etapa" mostra todas). No log JSON, os spans
  `llm` com `ms` alto mostram qual papel (`role`) e qual modelo estão lentos.
- **O que fazer:** se o lento é o provedor (todos os papéis), ver `ErrosDoProvedorLLM`; se é um papel só, baixar o
  `effort` dele ou trocar para um modelo menor por env (`AGENT_MODEL`, `AGENT_EFFORT`); se é a busca (span `agent`
  do faq alto e `llm` baixo), checar CPU da réplica e o tamanho do lote do rerank (`RERANK_POOL`).
- **Quando escalar:** p95 do agente acima de 15 s por mais de 30 min
  (`histogram_quantile(0.95, sum by (le) (rate(span_latency_ms_bucket{span="agent"}[30m]))) > 15000`; 15 s é um
  limite do balde, então a comparação é exata), ou `budget_exhausted_total` subindo: chamar quem opera o
  provedor/infra.

## LatenciaP95DoTurno

- **O que significa:** o p95 do turno respondido (span `turn`: o turno inteiro, do guardrail à resposta; o bloqueio
  do guardrail fica fora) passou do SLO por turno do kit por 30 min: 1 cliente em 20 espera mais do que o
  prometido.
- **Como confirmar:** no Prometheus,
  `histogram_quantile(0.95, sum by (le) (rate(span_latency_ms_bucket{span="turn"}[30m])))`; o painel "Turno
  respondido: p50 e p95 × SLO" mostra a curva com a linha do SLO. O quantil soma os baldes `le` de todas as réplicas
  antes de calcular (média de p95 por réplica não é p95).
- **O que fazer:** abrir o painel "Latência p95 por etapa" e achar a etapa que subiu: `llm` alto em todos os papéis
  → provedor (ver `ErrosDoProvedorLLM`); `agent` alto com `llm` normal → busca na CPU (CPU da réplica, `RERANK_POOL`,
  réplicas a mais); `guardrails` ou `router` alto → o classificador LLM da camada 2; tudo junto com mais pedidos por
  minuto → carga: subir réplicas.
- **Quando escalar:** p95 acima do SLO por mais de 1 h, ou junto com `budget_exhausted_total` subindo (o turno já é
  cortado pelo `NODE_TIMEOUT_S` e vai ao humano): chamar quem opera o provedor/infra.

## ErrosDoProvedorLLM

- **O que significa:** mais de 1 erro de LLM a cada 10 s por 5 min; os turnos caem no caminho determinístico (sem
  LLM), que responde menos e escala mais.
- **Como confirmar:** `llm_errors_total` por `kind` em `/metrics` (`auth`, `quota`, `rate_limited`, `connection`,
  `api_status`, `refusal`, `max_tokens`, `other`); o log traz o `kind` de cada falha.
- **O que fazer:** `auth` → chave recusada: trocar a chave no segredo do ambiente; `quota` → limite de gasto da conta:
  subir o limite no console do provedor; `rate_limited`/`api_status` (5xx) → reduzir concorrência (réplicas ou workers) e
  esperar; `connection` → ver a rede de saída; `max_tokens`/`refusal` → abrir caso de eval com o trace.
- **Quando escalar:** `auth` ou `quota` sempre (nada se resolve sozinho); os outros, se passarem de 15 min.

## ClassificadorDeSegurancaIndisponivel

- **O que significa:** a camada 2 do guardrail (o classificador LLM) ficou indisponível em algum turno nos últimos
  5 min (`guardrail_llm_unavailable_total`): queda do provedor no papel `guardrail`, ou resposta fora do enum do
  schema. A camada 1 (regex) já rodou, então a defesa não some, mas fica degradada: a suspeita da regex passa a
  bloquear (falha fechada), a leitura corre sem nenhum agente LLM (caminho offline forçado) e a escrita do turno
  fica retida. Recusa do modelo NÃO cai aqui — ela bloqueia como ataque e conta em `guardrail_classifier_refusal_total`.
- **Como confirmar:** em `/metrics`, `guardrail_llm_unavailable_total` subindo e `llm_errors_total{kind=...}` do papel
  `guardrail` (auth, quota, rate_limited, connection); no log JSON, os turnos com a flag `guardrail_llm_unavailable`
  e `writes_held_total`. Cruze com `ErrosDoProvedorLLM`: se os dois disparam, é o provedor; se só este, é o papel
  `guardrail` (modelo/chave/effort próprios).
- **O que fazer:** tratar a causa pelo `kind` (ver `ErrosDoProvedorLLM`: `auth` troca a chave, `quota` sobe o limite,
  `rate_limited`/`api_status` reduz concorrência, `connection` vê a rede); se for categoria fora do enum recorrente,
  abrir caso de eval com o trace do papel `guardrail` e conferir o schema/modelo. Enquanto durar, o atendimento segue
  seguro mas conservador (mais recusas e nenhuma escrita).
- **Quando escalar:** `auth` ou `quota` no papel `guardrail` sempre (não se resolve sozinho e deixa a 2ª camada fora);
  os outros, se passarem de 15 min ou se o volume de `writes_held_total` incomodar o atendimento.

## NumeroSemBase

- **O que significa:** respostas com número (preço, prazo, valor) que não está em fonte, ferramenta nem pergunta; a
  checagem numérica já tarja ou escala (`NUMBERS_POLICY`), mas o padrão subiu.
- **Como confirmar:** procurar `numeric_ungrounded` no log JSON e abrir os traces (`trace_id`); conferir se o número
  existe na fonte com outra grafia (falso positivo) ou não existe (inventado).
- **O que fazer:** falso positivo → caso de teste em `tests/test_grounding.py` e ajuste da normalização; inventado →
  corrigir a fonte (página nova no corpus) ou a instrução do domínio; em ambos os casos, o trace vira caso de eval.
- **Quando escalar:** número inventado em resposta sobre dinheiro do cliente (valor de venda, taxa, prazo de
  liquidação): avisar o responsável pelo produto no mesmo dia.

## EscalonamentoAnormal

- **O que significa:** mais de 40% dos atendimentos indo para humano por 30 min; ou a base não cobre o que os
  clientes estão perguntando, ou algo quebrou na busca ou no portão de cobertura.
- **Como confirmar:** `GET /analytics` → `worst_intents` e motivos (`handoffs_total` por `reason`): `faq_not_in_sources`
  em massa aponta para a base; `records_tool_error` para a ferramenta; `budget_exhausted` para latência.
- **O que fazer:** base → acrescentar a página que falta e reindexar; ferramenta → ver o sistema de registros;
  latência → ver `LatenciaAltaDoTurno`. Conferir que nenhum deploy recente mudou o limiar do portão.
- **Quando escalar:** acima de 60%, ou se a fila humana passar do SLA (`SLAVencido`).

## SLAVencido

- **O que significa:** um caso com o humano passou do SLA e foi re-escalonado uma vez (`sla_escalations_total`).
- **Como confirmar:** `/operator` lista os casos abertos com a idade; o log traz o `ticket_id` re-escalonado.
- **O que fazer:** responder o caso de prioridade alta em `/operator` (a resposta retoma a conversa na hora); se a
  fila está grande, chamar mais operadores da especialidade do caso.
- **Quando escalar:** sempre que acontecer em horário comercial sem operador disponível: supervisor do atendimento.

## ContadorDeLimiteIndisponivel

- **O que significa:** o rate limit não consegue ler ou gravar o contador e falha FECHADO: clientes recebem 429.
- **Como confirmar:** `rate_limit_store_errors_total` em `/metrics`; no log, o erro do banco (disco cheio, permissão,
  `database is locked`).
- **O que fazer:** liberar disco ou permissão do volume do banco; com Postgres, conferir a conexão; reiniciar a
  réplica afetada depois de corrigir (o contador volta a funcionar sem perder dados).
- **Quando escalar:** imediatamente: é indisponibilidade para clientes.

## GastoPorHoraAlto

- **O que significa:** mais de US$ 5 por hora em LLM por 10 min; ou o volume subiu, ou um laço de ferramentas está
  gastando chamadas sem resolver.
- **Como confirmar:** `llm_cost_usd_total` por `model` em `/metrics`; comparar com `chat_requests_total` (custo por
  turno); no log, turnos com muitas chamadas `llm` no mesmo `trace_id`.
- **O que fazer:** volume → aceitar ou baixar o modelo de um papel; laço → conferir `MAX_STEPS` e `MAX_MODEL_CALLS`
  e abrir caso de eval com o trace.
- **Quando escalar:** acima de US$ 20 por hora, ou custo por turno resolvido acima do dobro do medido no README.
