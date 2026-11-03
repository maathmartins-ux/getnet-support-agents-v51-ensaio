# Modelo de ameaças (frente Q)

Escopo: API `/chat` → guardrail → roteador → supervisor → agentes (faq/RAG, records/ferramentas, web) → resposta.
Fronteiras de confiança: cliente ↔ API (token), API ↔ LLM, agentes ↔ ferramentas do CRM, agentes ↔ web/base.

## STRIDE

| ameaça | controle | arquivo | teste |
|---|---|---|---|
| S: identidade forjada no corpo | AUTH_MODE required: identidade só do token assinado | src/app/auth.py, src/app/api.py | tests/test_domain_http.py::test_bad_token_is_401, test_required_without_token_is_401 |
| T: injeção indireta altera instrução | documento com instrução embutida descartado na carga | src/app/guardrails.py (looks_like_injection), src/app/ingest.py | tests/test_domain_guardrails.py::test_indirect_injection_in_document_is_detected |
| R: ação sem rastro | trilha de observabilidade e ações pendentes com aprovação | src/app/observability.py, src/app/actions.py | split approval (evals/cases.jsonl) |
| I: vazamento de dado de outro cliente | regex other_user_data + escopo do user_id nas tools + máscara de PII | src/app/guardrails.py, src/app/tools.py | casos q-guard-07..11; juiz `leak` (calibração q-cal) |
| D: abuso de volume | limite por IP no modo demo | src/app/api.py | tests/test_auth_modes.py (rate limit) |
| E: jailbreak para papel de admin | guardrail regex + LLM; ferramentas não têm operação de admin | src/app/guardrails.py | q-guard-03..06 |

## OWASP LLM Top 10 (2025)

| risco | controle | arquivo | teste |
|---|---|---|---|
| LLM01 prompt injection | regex + deobfuscate + camada LLM | src/app/guardrails.py | q-guard-01..04, 12..18; test_regex_layer_blocks |
| LLM02 divulgação de dado sensível | mask_pii / mask_output | src/app/guardrails.py | calibração `leak` |
| LLM05 saída sem tratamento | grounding de números e alegações | src/app/grounding.py | calibração `invented_number`, `unsupported_claim` |
| LLM06 agência excessiva | ação só com aprovação humana | src/app/actions.py | q-guard-28, 29 |
| LLM07 vazamento do prompt de sistema | bloqueio de pedido de prompt | src/app/guardrails.py | q-guard-01, 02, 12 |
| LLM08 fraqueza de vetor/RAG | descarte de documento injetado | src/app/ingest.py | test_indirect_injection_in_document_is_detected |
| LLM09 desinformação | juiz calibrado; `stale_source` | evals/judge.py | calibração q-cal (stale_source) |
| LLM10 consumo sem limite | teto de US$ no eval; rate limit | evals/run_evals.py, src/app/api.py | tests/test_auth_modes.py |

## OWASP Agentic (ASI01–ASI10)

| id | ameaça | controle | arquivo | teste |
|---|---|---|---|---|
| ASI01 | sequestro de objetivo por injeção | guardrail antes do roteador | src/app/guardrails.py | q-guard com owasp ASI01 |
| ASI02 | uso indevido de ferramenta | tools escopadas ao usuário; ação com confirmação | src/app/tools.py, src/app/actions.py | q-guard-19..23, 28 |
| ASI03 | abuso de identidade/privilégio | identidade do token, não do texto | src/app/auth.py | q-guard-05..11; test_domain_http |
| ASI04 | cadeia de suprimentos (skills/MCP) | servidor MCP local, sem plugin externo | src/app/mcp_server.py | fora do escopo de teste da Q |
| ASI05 | execução de código inesperada | nenhum agente executa código | src/app/agents.py | q-guard-oos-2 (não executa script) |
| ASI06 | envenenamento de memória/contexto | injeção indireta descartada; memória por conversa | src/app/store.py, src/app/ingest.py | q-guard-16..18, 30 |
| ASI07 | comunicação insegura entre agentes | supervisor central; mensagem do usuário não vira ordem a agente | src/app/supervisor.py | q-guard-31 |
| ASI08 | falha em cascata | status ok/partial/insufficient/error por agente; replanejamento | src/app/pipeline.py | splits replan, partial |
| ASI09 | exploração da confiança humana | ação irreversível pede aprovação | src/app/actions.py | q-guard-29; split approval |
| ASI10 | agente desonesto / fuga do supervisor | guardrail não é pulável; ordem do usuário não muda o plano | src/app/supervisor.py | q-guard-32 |

Lacuna medida: a camada regex offline deixa passar 9 de 32 ataques (ver docs/EVAL_STRATEGY.md).
