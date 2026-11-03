# Runbook dos alertas

Um bloco por regra de `ops/alerts.yml` (a anotação `runbook_url` de cada regra aponta para cá; `tests/test_alerts.py`
reprova alerta sem bloco). Cada bloco diz o que o alerta significa, como confirmar antes de agir, o que fazer e quando
escalar. Os comandos assumem a API em `localhost:8000` e o Prometheus do perfil `observability` do compose.

## LatenciaAltaDoTurno

- **O que significa:** a média de cada chamada de agente passou de 8 s por 10 min; o cliente espera mais que o
  aceitável e o orçamento por turno (`NODE_TIMEOUT_S`) começa a cortar passos (`budget_exhausted`).
- **Como confirmar:** em `/metrics`, `span_latency_ms_sum{span="agent"}` / `_count` nos últimos 5 min; no log JSON,
  os spans `llm` com `ms` alto mostram qual papel (`role`) e qual modelo estão lentos.
- **O que fazer:** se o lento é o provedor (todos os papéis), ver `ErrosDoProvedorLLM`; se é um papel só, baixar o
  `effort` dele ou trocar para um modelo menor por env (`AGENT_MODEL`, `AGENT_EFFORT`); se é a busca (span `agent`
  do faq alto e `llm` baixo), checar CPU da réplica e o tamanho do lote do rerank (`RERANK_POOL`).
- **Quando escalar:** p95 acima de 15 s por mais de 30 min, ou `budget_exhausted_total` subindo: chamar quem opera
  o provedor/infra.

## ErrosDoProvedorLLM

- **O que significa:** mais de 1 erro de LLM a cada 10 s por 5 min; os turnos caem no caminho determinístico (sem
  LLM), que responde menos e escala mais.
- **Como confirmar:** `llm_errors_total` por `kind` em `/metrics` (`auth`, `quota`, `rate_limited`, `connection`,
  `api_status`, `refusal`, `max_tokens`, `other`); o log traz o `kind` de cada falha.
- **O que fazer:** `auth` → chave recusada: trocar a chave no segredo do ambiente; `quota` → limite de gasto da conta:
  subir o limite no console do provedor; `rate_limited`/`api_status` (5xx) → reduzir concorrência (réplicas ou workers) e
  esperar; `connection` → ver a rede de saída; `max_tokens`/`refusal` → abrir caso de eval com o trace.
- **Quando escalar:** `auth` ou `quota` sempre (nada se resolve sozinho); os outros, se passarem de 15 min.

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
