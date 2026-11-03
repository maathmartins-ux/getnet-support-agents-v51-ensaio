# Estratégia de avaliação (frente Q)

Casos da frente em `evals/cases.d/q.jsonl`; rótulos do juiz em `evals/judge_calibration.d/q.jsonl`.
Nada aqui lê `evals/heldout_blind.jsonl`.

**Held-out e a análise de erros (rodada 10, 03/11/2026).** As afirmações sem base que o juiz achou no held-out (e na memória) da rodada anterior foram lidas para achar causas no motor: lista em blocos colada numa linha só no trecho, cartão de capacidades sem os valores que as consultas aceitam, taxa de tabela geral atribuída a um produto e conclusão tirada de consulta filtrada. As correções são genéricas (chunker, cartão e duas regras dos prompts do kit) e nenhuma cita caso ou frase do held-out; mesmo assim, para essas quatro classes de erro o held-out deixou de ser cego: o número dele a partir desta rodada se lê como conjunto de desenvolvimento, não como generalização pura.

| split | n | o que mede | campos de `expect` |
|---|---|---|---|
| official-var | 12 | paráfrase pt e en de 6 oficiais com fato verificável; mesmos `facts`/`entities` do oficial | intent, language, facts, entities, tools |
| memory | 6 | seguimento "e quanto custa?" e troca de entidade "e a outra maquininha?" | standalone, expects_fact, `before` |
| partial | 5 | fonte cobre só parte; responde o coberto e diz o que falta, sem escalar | handoff: false |
| dependent | 3 | troubleshoot que exige dado do cliente e base | tools, must_include_agents |
| hard | 5 | gíria, abreviação, pedido duplo; fora do gate (UNGATED) | intent, language |
| guardrail | 35 | 32 ataques (`blocked: true`, intent `blocked`) + 3 fora de escopo que não devem bloquear | blocked, owasp |

Ataques cobertos: injeção direta, injeção indireta (texto colado de site/documento), ofuscação (leet, espaços,
caractere de largura zero), jailbreak de persona, dado de outro cliente (`cliente2024`), lavagem de dinheiro e
fraude, abuso verbal, autoagressão, ação sem confirmação, envenenamento de memória.

## Número medido

- Camada regex offline (`app.guardrails.check_input`, sem LLM): bloqueia 23 de 32 ataques do split guardrail.
  Os 9 que passam (personificação de admin, `cliente2024` em pt sem verbo "mostre ... de", lavagem com outro
  vocabulário, clonagem de cartão, memória persistente) ficam para a camada LLM; são o alvo de melhoria.
- `tests/test_domain_http.py` + `tests/test_domain_guardrails.py`: 23 passed.

## Juiz

48 rótulos: 24 grounded, 24 não grounded, 4 por `failure_type` (invented_number, unsupported_claim,
stale_source, offered_unavailable_action, wrong_language, leak). Evidência por `source_kind`: rag, tool, web.
Cada negativo também traz `human_failure_type`, para TPR/TNR por tipo (`evals/judge.py: by_failure_type`).
E-mails fictícios usam o domínio `golpe-ficticio.test`.
