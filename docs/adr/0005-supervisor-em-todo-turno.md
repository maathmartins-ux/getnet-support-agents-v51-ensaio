# ADR 0005 — O supervisor LLM decide todo turno; o atalho de 1 passo fica como opção de custo

Status: aceito.

**Contexto.** O supervisor LLM coordena os especialistas como tools (`src/app/supervisor.py`). Num plano de UM
especialista com o router confiante, existia um atalho (`fast_path`): o passo rodava direto e a resposta era a do
especialista, sem o supervisor. Ele economizava 2 chamadas sequenciais (escolher a tool e redigir a resposta final),
cerca de 4 s por turno. Mas, nos cenários mais comuns, a decisão de rota deixava de ser observável: quem lia o trace
via a tabela escolher o caminho, não o modelo que lê o resultado e decide.

**Decisão.** O supervisor LLM decide em todo turno (`SUPERVISOR_FAST` desligado por padrão). Ele lê o status de cada
especialista (`ok`, `partial`, `insufficient`, `error`) e escolhe: responder, chamar outro especialista ou o humano,
dentro de `ALLOWED`, `MAX_STEPS` e do orçamento do turno. A escalada quando nada resolve é garantida em código
(`_enforce_escalation`). Sem chave ou com falha do provedor, a mesma tabela de transições (`FALLBACK`, `ALLOWED`)
roda offline. `SUPERVISOR_FAST=on` religa o atalho para quem prefere custo e latência menores.

**Alternativas.** (1) Atalho de 1 passo ligado por padrão: 1 chamada de modelo a menos na maioria dos turnos, mas a
decisão fica na tabela nos casos mais frequentes. (2) Só a tabela: perde o replanejamento que lê o resultado.

**Consequências.** Mais 2 chamadas e alguns segundos por turno de um passo. A resposta final passa pela redação do
supervisor, conferida pelo verificador de claims e de números como qualquer outra; a oferta do humano numa resposta
parcial é texto fixo (`_offer_human_on_gap`), não depende da redação.

**Números.** Cenários oficiais ao vivo com o supervisor em todo turno, 3 rodadas: resolvidas 1,00, juiz úteis 1,00 e
fundamentadas 0,97, decisão do supervisor LLM nas 30 execuções; latência p50 ~15 s. Prova:
`tests/test_supervisor_fast.py::test_single_step_confident_plan_skips_the_supervisor_llm` (atalho, quando ligado) e
`tests/test_v54_rehearsal_guards.py::test_supervisor_llm_decides_every_turn_by_default`.
