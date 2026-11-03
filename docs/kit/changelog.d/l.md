# Frente L — latência ao vivo sem perder qualidade (kit v5.1)

Diagnóstico (ensaio v5.1 sobre o domínio da v4, logs `ens51/logs/{official,memory}.log` cruzados com os cassetes
pela ordem global das chamadas: 206 e 532 chamadas, modelo e tokens batem 1:1). Por turno, média do split memória
(12,9 s de parede): guardrail‖router 1,2 s; supervisor escolhendo tool 1,8 s; supervisor redigindo a resposta final
2,3 s; agentes 4,1 s; verificador de frases (claims) 1,7 s; reescritas 0,2 s; fora do LLM ~1,7 s. Nenhuma chamada
isolada passou de 14 s (o hedge de 15 s já cortava a cauda antiga de 19–46 s). O p95 da memória vem de caso com DOIS
turnos (o eval soma `before` + a pergunta) e de clima: Open-Meteo com timeout/429 levou o `live_data` a 5–11 s e ainda
caiu na busca web (Sonnet, 24–41 mil tokens de entrada, 10–14 s). Official: 1,4 / 1,7 / 2,5 / 3,2 / 1,8 s nas mesmas
categorias, 12,2 s de parede.

- **Papel no span `llm`.** O que: o span leva `role` (supervisor, agent, claims...) e `hedged=true` quando a 2ª
  tentativa entrou. Por quê: a decomposição acima só saiu cruzando log e cassete; agora sai do log. Prova:
  `tests/test_llm_hedge.py::test_llm_span_names_the_role_and_marks_the_hedged_call`.
- **Atalho do supervisor em plano de 1 passo.** O que: com LLM, plano de um passo e router com confiança >= 0,8
  (`SUPERVISOR_FAST_MIN_CONFIDENCE`) vão pela tabela; a resposta é a do próprio agente. Fica no LLM: plano de 2+
  passos, router incerto, retomada de caso; `SUPERVISOR_FAST=off` desliga. O faq troca "[n]" (número da passagem no
  prompt) pelo id da fonte, que antes era o supervisor quem trocava. Por quê: no ensaio v5.1 essas 2 chamadas
  sequenciais (escolher a tool + reescrever a resposta) custavam 3,5 s por turno (média; p95 4,3 s) em 24 de 30
  turnos do official e 3,4 s (p95 4,7 s) em 57 de 78 turnos da memória, e a reescrita às vezes acrescentava frase
  sem base que o verificador cortava depois. Prova: `tests/test_supervisor_fast.py` (sem chamada ao supervisor,
  FALLBACK da tabela mantido, os 4 casos que continuam no LLM) e `test_cite_ids_*`.
- **Teto de tempo no dado ao vivo e 429 sem nova tentativa.** O que: a consulta inteira (geocoding + previsão, com as
  tentativas) tem teto de 5 s (`LIVE_DATA_BUDGET_S`); cada tentativa usa o menor entre 3 s e o que sobra; 429 não se
  repete. Por quê: no ensaio v5.1 o clima com falha levou o `live_data` a 5–11 s (6 `ConnectTimeout`) e ainda caiu na
  busca web; sucesso levou 1,3–2,3 s. Sondado agora com curl: geocoding 0,55–0,93 s com 200, previsão 3 x 429
  seguidos (limite de taxa do IP da nuvem, fora do nosso controle). Prova:
  `tests/test_live_data.py::test_rate_limit_is_not_retried_and_the_whole_lookup_has_a_deadline`.
- **Pensamento por papel (`<PAPEL>_THINKING=off`), padrão inalterado.** O que: `config.thinking_param` desliga o
  pensamento só onde a API aceita (Haiku 5.5 `disabled`, Sonnet 5.5 `between_tools`, effort até high); Opus 5.5 e
  xhigh/max seguem no padrão. Medido e REJEITADO como padrão para o verificador de claims: sonda ao vivo com 20
  respostas gravadas do ensaio v5.1 (10 official + 10 memória), cada uma verificada nos dois modos — sem pensamento
  p50 1194 ms / p95 1585 ms / 24 tokens de saída; com pensamento p50 1672 ms / p95 2595 ms / 168 tokens; mas os
  vereditos divergiram em 10 de 20, todas com o modo sem pensamento marcando frase a mais (8 "contradicts_evidence")
  em respostas que o juiz aprovou. Com CLAIMS_POLICY=remove isso corta frase certa: 0,5 s não paga. Custo da sonda:
  US$ 0,0114. Prova: `tests/test_llm_hedge.py::test_thinking_off_is_per_role_and_never_sends_a_combination_the_api_rejects`.
- **Ensaio ao vivo, split memória (motor em 589b37e: atalho + teto do live_data), 3 rodadas, 4 workers.** Caso
  (soma dos turnos): p50 19,3 s / p95 45,0 s (antes 22,6 / 52,8); pass@1 97,4% (antes 92,3%), pass^3 92,3%; custo
  US$ 1,08 (antes 1,24). Por turno: p50 8,1 s / p95 22,7 s (antes 10,9 / 24,6); chamadas do supervisor 62 (antes
  172). Juiz: fundamentada 97,1% (34/35) e útil 94,3% (33/35), contra 97,4% (38/39) e 92,3%; o juiz parou no teto de
  US$ 1 com 35 de 39 linhas (a calibração de 46 casos e os canários entram em toda rodada). A reprovação de
  fundamentação (q-mem-04, "You've already tried this") é do caminho troubleshoot, que continua no supervisor LLM;
  as 2 de utilidade (q-mem-11/12) são clima que caiu na busca web com o Open-Meteo em 429/timeout (7 falhas, 4,6–5,6 s
  cada, agora no teto). Meta de p95 <= 30 s NÃO atingida: a cauda é troubleshoot (2 turnos de records → faq pelo
  supervisor LLM, 3 voltas de Sonnet, 34–49 s por caso).
- **Achado para a frente R2 (não mexido aqui):** a busca do retriever escolhido
  (`dense[multilingual-e5-large]+cross[bge-reranker-v2-m3-int8@5]`) custa 2,3–2,8 s por consulta, aquecida e sozinha,
  nesta máquina de 4 núcleos, e 4 em paralelo levam 6,0 s; no ensaio, o faq gastou 2,3–7,5 s fora do LLM. O critério
  da escolha supunha p95 <= 1500 ms. É o maior custo fora do LLM nos turnos de conhecimento.
- **Passo de que os outros dependem roda antes da 1ª volta do supervisor LLM.** O que: em plano de 2+ passos em que um
  passo seguinte DEPENDE do 1º (DEPENDS do domínio; Getnet: troubleshoot = records → faq), o código roda o 1º e o
  supervisor já começa lendo o resultado dele (texto na 1ª mensagem; chamar de novo é transição recusada). Retomada
  de caso fica com o modelo. Por quê: em 48 de 48 turnos troubleshoot gravados (6 official + 21 memória do ensaio
  v5.1, 21 do ensaio acima) a 1ª volta chamou exatamente records_agent; é uma volta de Sonnet sequencial (p50 1,8 s
  no ensaio acima) para confirmar uma ordem já decidida. Prova:
  `tests/test_supervisor_fast.py::test_step_others_depend_on_runs_before_the_first_llm_round`.
- **Ensaio ao vivo, split official (motor em 7c1da5b: atalho + teto do live_data + passo dependente antes do
  supervisor), 3 rodadas, 4 workers.** p50 9,2 s / p95 21,5 s (antes 10,6 / 20,8); pass@1 96,7% (igual), pass^3
  0,90 (igual); custo US$ 0,47 (antes 0,76); chamadas do supervisor 13 (antes 67). Juiz (US$ 0,88): fundamentada
  100% (30/30; antes 96,7%), útil 96,7% (29/30; antes 100%). Meta de p95 <= 15 s NÃO atingida: os 6 turnos
  troubleshoot (official-05/08) levam 19–22 s — router 1 s, records 4 s (2 chamadas), supervisor 1,5 s, faq 4–9 s
  dos quais 3,4–5,2 s são a busca do retriever (achado R2 acima), redação final 3 s, claims 2–4 s.
- **Atalho: oferta de humano quando a fonte não cobre e "fontes" em vez de "passagens".** O que: no atalho, resposta
  do faq que diz que a fonte não cobre parte da pergunta (`claims.states_absence`) e não fala de humano ganha uma
  frase fixa oferecendo o encaminhamento (fora das intenções que nunca escalam); o faq troca "passagens"/"passages"
  (nome do prompt) por "fontes"/"sources". Por quê: era a redação final do supervisor que fazia as duas coisas; no
  ensaio acima a única resposta não útil (official-04, rodada 2) foi "não responde nem oferece humano", e 15
  respostas do atalho (official + memória) diziam "The passages don't say". Prova:
  `test_fast_path_offers_a_human_when_the_answer_says_the_sources_do_not_cover_it`,
  `test_prompt_jargon_becomes_sources_for_the_customer`. NÃO medido com o juiz (orçamento): efeito na nota é hipótese.
- **Conferência ao vivo da oferta (official, 1 rodada, sem juiz, US$ 0,24).** A oferta entrou e o verificador de
  claims não a cortou (official-01 e official-04 terminam em "If you'd like, I can hand this question to a human
  agent."). Mas os 2 troubleshoot (official-05/08) escalaram: faq "sem fonte" → supervisor chamou o humano (handoff
  80% nessa rodada). Somando, com o passo antecipado o faq "sem fonte" virou escalonamento em 3 de 6 vezes; sem ele,
  1 de 4 no official v5.1 (0 de 9 na memória). Amostra pequena demais para decidir e sem orçamento para medir mais:
  **o passo antecipado virou opt-in (`SUPERVISOR_LEAD=on`), padrão desligado.** O ensaio official de 3 rodadas acima
  rodou COM ele ligado.
- **Disputa de CPU nos ensaios (confunde a parede).** Durante os ensaios desta frente, outro processo
  (`run_evals --choose-retriever`, da frente R2) usava ~340% de CPU (load average de 15 min 5,6 em 4 núcleos); o faq
  gastou 2,3–7,5 s fora do LLM contra 0,7–2,7 s no ensaio v5.1, com o mesmo retriever. As comparações limpas são as
  por papel: supervisor por turno 4,0 → 1,6 s (memória) e 4,2 → 1,0 s (official).
