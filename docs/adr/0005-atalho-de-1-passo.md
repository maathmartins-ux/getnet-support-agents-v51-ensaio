# ADR 0005 — Atalho de 1 passo: o especialista responde direto; o supervisor LLM decide quando ele não resolve

Status: aceito no kit v5.3 (03/11/2026).

**Contexto.** O supervisor LLM coordena os especialistas como tools (`src/app/supervisor.py`). Num plano de UM
especialista com o router confiante, o turno custava 2 chamadas sequenciais do supervisor (escolher a tool e redigir
a resposta final), cerca de 4 s por turno, e a redação final só reescrevia o texto do agente, às vezes com uma frase
a mais que o verificador de claims cortava depois. No ensaio da v5.3, 24 de 30 oficiais ao vivo eram de um passo.

**Decisão.** `fast_path` (`SUPERVISOR_FAST=on`, confiança do router ≥ `SUPERVISOR_FAST_MIN_CONFIDENCE`, padrão 0,8):
o passo roda direto e, se o especialista respondeu (`ok`/`partial`), a resposta é a dele. Quando ele **não resolve**
(`insufficient`), o resultado vai ao supervisor LLM, que o lê e decide (responder com o que houver e oferecer o
humano, outro especialista ou escalation), dentro do mesmo orçamento e de `MAX_STEPS`. Ficam sempre no LLM: plano de
2+ passos, router incerto e a retomada de caso (a resposta do humano muda o que falta fazer). Sem chave ou com falha
do provedor, a mesma tabela de transições (`FALLBACK`, `ALLOWED`) roda offline.

**Alternativas.** (1) Toda mensagem pelo loop do supervisor: +1 chamada e ~4 s por turno sem decisão a tomar.
(2) Atalho sem devolver o `insufficient` ao LLM: o faq "sem fonte" escalava por regra, sem decisão observada (era o
comportamento até a v5.2). (3) Só a tabela: perde o replanejamento que lê o resultado.

**Consequências.** Uma chamada de modelo a menos na maioria dos turnos; a resposta é o texto do especialista (o que o
verificador de claims confere), não uma reescrita. Um replanejamento que só o LLM enxergaria numa resposta `ok`
não acontece no atalho: o achado (`needs`) do especialista é o caminho para isso, e segue `ALLOWED` igual ao LLM.
A oferta do humano que a redação do supervisor acrescentava virou texto fixo (`_offer_human_on_gap`): sem ela,
1 de 30 oficiais foi julgada não útil ("não responde nem oferece humano").

**Números.** Replan (humano quando não resolve) 95% com o atalho ligado (ensaio r6); oficiais resolvidas 96,7%
(r2/r3). Prova: `tests/test_supervisor_fast.py::test_single_step_confident_plan_skips_the_supervisor_llm`,
`tests/test_supervisor_fast.py::test_fast_path_insufficient_goes_to_the_llm_and_keeps_the_table_fallback_if_it_fails`,
`tests/test_supervisor_fast.py::test_uncertain_router_multi_step_plan_resume_and_flag_off_still_use_the_llm`.
`SUPERVISOR_FAST=off` volta ao LLM em todo turno.
