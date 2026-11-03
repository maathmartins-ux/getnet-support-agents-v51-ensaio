# Observabilidade (Getnet)

O que o sistema emite, onde, e qual pergunta de operação cada sinal responde. Implementação em
`src/app/observability.py`; regras de alerta em `ops/alerts.yml` (cada uma com bloco em [RUNBOOK.md](RUNBOOK.md));
Prometheus e Grafana do perfil `observability` em `ops/prometheus.yml` e `ops/grafana/`.

## 1. Três sinais

| Sinal | Onde | Como |
|---|---|---|
| Log JSON por evento | stdout | `observability.span(...)` grava `span`, `ms` e os campos do chamador; todo evento leva o `trace_id` do turno (`new_trace_id`, `current_trace_id`). PII é mascarada antes (`src/app/guardrails.py`) |
| Métricas | `GET /metrics` | contadores `*_total` e latência por span (`span_latency_ms_sum` / `_count`) |
| Traces | OpenTelemetry, opcional | `configure_otel` liga quando há exportador; cada span leva `app.trace_id` e os campos como atributos |

## 2. Custo por turno

`record_llm_usage` soma `llm_tokens_total{model,kind}` e `llm_cost_usd_total{model}`; modelo sem preço conta em
`llm_unpriced_calls_total` (custo nunca some calado). `request_usage()` devolve o custo e o número de chamadas do
turno, que vai na própria resposta do `/chat`. Alerta: `GastoPorHoraAlto`.

## 3. Versão das instruções

`record_prompt` grava o hash de cada prompt carregado; `prompt_versions()` liga a versão a cada resposta e ao
👍/👎 (`feedback_total`), para comparar qualidade entre versões de prompt.

## 4. Painel mínimo do piloto (contador → pergunta)

| Pergunta de operação | Contadores |
|---|---|
| Quanto vai ao humano? | `handoffs_total`, `case_escalated_total`, `escalation_offered_total`, `hitl_sync_total`, `handoff_resumed_total`, `plan_resumed_total` |
| A resposta tem base? | `claims_unsupported_total`, `numeric_ungrounded_total`, `numeric_enforced_total`, `answer_rewrites_total` |
| A busca degradou? | `retriever_fallback_total`, `rerank_fallback_total`, `embed_cache_hits_total`, `poisoned_docs_dropped_total` |
| O provedor LLM está bem? | `llm_errors_total`, `llm_retry_total`, `llm_hedged_total`, `router_fallback_total`, `supervisor_fallback_total`, `node_timeouts_total`, `budget_exhausted_total` |
| Ações de escrita (estorno, cancelamento) | `tool_calls_total`, `approvals_requested_total`, `approvals_decided_total`, `actions_blocked_by_limit_total`, `actions_expired_total`, `actions_on_hold_total`, `risk_flags_total` |
| Segurança | `guardrail_blocks_total`, `auth_failures_total`, `login_failures_total`, `operator_auth_failures_total`, `mcp_auth_failures_total`, `rate_limited_total` |
| Orquestração | `supervisor_fast_path_total`, `replans_total`, `parallel_batches_total`, `supervisor_handover_total` |
| SLA do operador | `sla_escalations_total` (alerta `SLAVencido`) |

## 5. Alertas

`LatenciaAltaDoTurno`, `ErrosDoProvedorLLM`, `NumeroSemBase`, `EscalonamentoAnormal`, `SLAVencido`,
`ContadorDeLimiteIndisponivel`, `GastoPorHoraAlto` — limiares em `ops/alerts.yml`, ação em [RUNBOOK.md](RUNBOOK.md).
`tests/test_alerts.py` reprova alerta sem bloco no runbook.
