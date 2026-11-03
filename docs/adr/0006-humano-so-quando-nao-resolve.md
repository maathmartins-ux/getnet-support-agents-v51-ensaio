# ADR 0006 — Humano só quando o sistema não resolve, garantido em código

Status: aceito no kit v5.3 (03/11/2026).

**Contexto.** O enunciado pede o humano quando o sistema não resolve, e não a cada lacuna. Duas falhas medidas:
(a) a 1ª versão da regra ("falta de fonte ou de dado vira oferta de humano, sem caso") derrubou o split `replan`
para 30%: perguntas que ninguém respondeu terminavam em "posso encaminhar" sem caso aberto; (b) no motor LLM,
9 de 12 perguntas sem fonte terminaram só com a oferta, porque o supervisor preferiu oferecer a escalar.

**Decisão.** Duas regras, as duas em código ("o LLM propõe, o código dispõe"):

1. **Oferta** (`agents.escalation_offer_only`, `OFFER_SUFFIXES = ("_partial_coverage",)`): resposta parcial, ou
   lacuna depois de outro especialista já ter respondido, termina oferecendo o humano, sem abrir caso.
2. **Escalada** (`supervisor._enforce_escalation`): turno em que um especialista não achou fonte, dado ou registro
   (`NOT_RESOLVED = ("not_in_sources", "no_data", "not_found")`) e **ninguém respondeu nada** termina no
   escalation, mesmo que o supervisor LLM tenha só oferecido. O `not_found` é lido do resultado da ferramenta
   (`agents.cited_not_found`), não do texto. Cliente pedindo humano e gancho do domínio vencem a regra.

**Alternativas.** (1) Deixar o LLM decidir sozinho: 9 de 12 sem caso. (2) Toda lacuna abre caso: o operador recebe
perguntas já respondidas em parte, e "útil" cai. (3) Toda lacuna só oferece: replan 30%.

**Consequências.** O operador só recebe o que o sistema não resolveu; a resposta parcial continua sendo resposta. A
regra depende do `reason` que cada especialista devolve: um especialista novo do domínio que não preencher `reason`
não escala por ela (cai no `FALLBACK` do domínio).

**Números.** Replan (humano quando não resolve): 30% com a 1ª regra → 85–90% (v5.3) → **95%** (r6). Prova:
`tests/test_v53_escalation_gate.py::test_code_escalates_when_llm_only_offered_and_nobody_answered`,
`tests/test_v53_escalation_gate.py::test_code_does_not_escalate_when_someone_answered`,
`tests/test_v53_escalation_gate.py::test_missing_piece_offers_human_and_opens_no_case`,
`tests/test_v54_not_found_escalates.py::test_forced_escalation_drops_the_llm_offer_text`.
