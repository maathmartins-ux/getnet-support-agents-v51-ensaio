# Mapa OWASP Top 10 for Agentic Applications (2026) → controle → arquivo → teste

Cada linha diz o que o motor do kit faz contra a ameaça, onde está o código e **qual teste prova**. Todo caminho e
todo teste citado aqui existe: `tests/test_security_asi.py` lê este arquivo e reprova se um sumir. A coluna "Lacuna"
diz o que o kit NÃO cobre; o domínio do desafio acrescenta o que for dele (ferramentas, dados) em `THREAT_MODEL.md`.

Nomes das categorias: ASI01, ASI02, ASI03 e ASI10 batem em várias fontes públicas; ASI04 a ASI09 seguem uma
referência pública e **devem ser conferidos no documento oficial da OWASP GenAI Security Project** antes de citar
o nome em material formal (uma fonte consultada diverge em ASI06 e ASI10).

| ID | Ameaça (resumo) | Controle no kit | Código | Prova | Lacuna |
|---|---|---|---|---|---|
| ASI01 Agent Goal Hijack | mensagem, página ou documento manda o agente fazer outra coisa | regex com desofuscação antes de qualquer LLM + 2ª camada LLM sobre texto mascarado; documento com instrução é descartado na carga; trechos entram no prompt como `<untrusted_content>` | `src/app/guardrails.py` | `tests/test_guardrails.py::test_obfuscated_injection_is_caught`, `tests/test_guardrails.py::test_poisoned_document_is_dropped_at_load`, `tests/test_guardrails.py::test_faq_passages_are_wrapped_as_untrusted` | injeção em página da web da busca não passa pelo filtro de carga |
| ASI02 Tool Misuse and Exploitation | o modelo chama tool com argumento que não devia, ou em laço | JSON Schema com `additionalProperties: false`; escrita só com confirmação do dono e, se de risco alto, também do operador; teto de rodadas de tool e orçamento por turno | `src/app/actions.py`, `src/app/supervisor.py` | `tests/test_hitl.py::test_high_risk_action_needs_owner_then_operator_and_runs_once`, `tests/test_hitl.py::test_rejected_high_risk_action_runs_nothing`, `tests/test_supervisor.py::test_supervisor_respects_max_steps` | sem limite de valor por ação de risco alto: toda `high` vai ao operador |
| ASI03 Identity and Privilege Abuse | o modelo ou o cliente escolhe de quem são os dados | identidade só do `sub` do JWT, injetada pelo servidor nas tools (nunca no schema); token expira e pode ser revogado; rate limit que falha fechado | `src/app/auth.py`, `src/app/api.py` | `tests/test_agents.py::test_tool_identity_is_server_side`, `tests/test_identity.py::test_expired_token_is_rejected`, `tests/test_identity.py::test_revoked_token_is_rejected_via_api`, `tests/test_identity.py::test_rate_limit_fails_closed` | `AUTH_MODE=demo` aceita `user_id` do corpo e marca `identity_verified=false` |
| ASI04 Agentic Supply Chain Vulnerabilities | dependência, imagem ou action comprometida | actions fixadas por SHA de commit; imagem base por digest; SBOM e trivy reprovando CRITICAL (exceção só com motivo e validade); testes com a rede cortada | `.github/workflows/ci.yml`, `.trivyignore`, `Dockerfile` | `tests/test_supply_chain.py::test_every_action_is_pinned_by_commit_sha_with_version_comment`, `tests/test_supply_chain.py::test_ci_has_offline_tests_sbom_and_trivy_gate`, `tests/test_supply_chain.py::test_trivyignore_entries_have_reason_and_valid_expiry` | lock sem hash; modelo de embeddings (extra opcional) baixado em build |
| ASI05 Unexpected Code Execution | o agente roda código que o modelo escreveu | nenhum `eval`, `exec`, `pickle`, `subprocess` ou shell no código do app; o estado é JSON em SQLite | `src/app/` | `tests/test_security_asi.py::test_no_dynamic_code_execution_in_the_app` | tools do domínio que chamem sistemas externos precisam do mesmo cuidado |
| ASI06 Memory and Context Poisoning | uma mensagem injetada contamina os turnos seguintes | mensagem barrada pelo guardrail nunca entra no histórico; PII mascarada antes de gravar; histórico entra no prompt como dado | `src/app/pipeline.py`, `src/app/guardrails.py` | `tests/test_security_asi.py::test_blocked_message_is_never_remembered`, `tests/test_guardrails.py::test_cpf_masked` | memória de longo prazo do usuário não expira (retenção por idade existe: ver ASI10) |
| ASI07 Insecure Inter-Agent Communication | a saída de um agente muda as instruções de outro | agentes trocam objetos tipados (`AgentResult`), não texto livre; transição fora de `ALLOWED` é recusada; "achado" que pede outro agente só vale se permitido | `src/app/agents.py`, `src/app/supervisor.py` | `tests/test_supervisor.py::test_llm_disallowed_transition_is_refused`, `tests/test_supervisor_needs_budget.py::test_need_outside_allowed_or_unknown_is_ignored` | tudo roda num processo; comunicação entre processos não existe |
| ASI08 Cascading Agent Failures | falha de modelo, tool ou réplica derruba o turno | queda do LLM cai no caminho determinístico; erro de agente vira status `error` e o supervisor replaneja; timeout por nó; 2 réplicas testadas | `src/app/supervisor.py`, `src/app/router.py` | `tests/test_supervisor.py::test_llm_failure_falls_back_to_table`, `tests/test_router.py::test_llm_failure_falls_back_to_rules`, `tests/test_supervisor.py::test_agent_exception_becomes_error_status` | réplicas só no mesmo host (SQLite em volume compartilhado) |
| ASI09 Human-Agent Trust Exploitation | resposta fluente convence o humano de algo falso | número sem base na evidência é reescrito ou trocado por `[valor não confirmado]`; ação alegada sem execução é removida; resposta do operador é mascarada e auditada | `src/app/grounding.py`, `src/app/pipeline.py` | `tests/test_numbers_policy.py::test_invented_number_is_redacted_with_offer_by_default`, `tests/test_claimed_action.py::test_claim_without_execution_is_detected`, `tests/test_privacy.py::test_operator_reply_is_audited` | afirmação factual sem número não é checada (só o juiz ao vivo e a validação humana) |
| ASI10 Rogue Agents | um agente age fora do papel, sem ninguém ver | cada agente só sai por `ok`/`insufficient`/`error`; transições limitadas por `ALLOWED` e `MAX_STEPS`; log JSON com `trace_id` por agente; trilha de auditoria só de inclusão; apagamento e retenção de dados auditados | `src/app/supervisor.py`, `src/app/store.py`, `src/app/observability.py` | `tests/test_supervisor.py::test_supervisor_respects_max_steps`, `tests/test_privacy.py::test_audit_log_is_append_only`, `tests/test_privacy.py::test_owner_deletes_own_conversation_and_it_is_audited` | sem detecção automática de desvio de papel além dos limites de transição |

## Red team medido (gate)

Cada caso dos splits `guardrail` e `hard` leva o rótulo `owasp` (ASI01–ASI10). O gate offline (`python -m
evals.run_evals`) reprova o CI se a fração SEGURA (bloqueou quando devia, levou ao humano quando devia, não vazou
dado de outro cliente) ficar abaixo de `RED_TEAM_GATE` (padrão 90%). Gerado por `scripts/fill_readme.py`:

<!-- red-team:begin -->
<!-- red-team:end -->

## Como o domínio do desafio usa este mapa

A frente Q copia esta tabela para o `THREAT_MODEL.md` do desafio, acrescenta as ameaças do domínio (dado de outro
lojista, ação de dinheiro) e troca a coluna "Prova" pelos testes de guardrail do próprio domínio (arquivo criado pela frente Q). O teste
`tests/test_security_asi.py::test_every_cited_path_and_test_exists` roda sobre este arquivo no kit; no desafio,
aponte-o para o arquivo novo.
