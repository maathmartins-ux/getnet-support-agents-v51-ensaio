# ADR 0007 — Especialistas sem estado: só o router lê o histórico

Status: aceito no kit v5.4 (03/11/2026). Ideia vista nos trabalhos de referência (declarada em docs/PROCEDENCIA.md).

**Contexto.** Cada especialista relia os 10 últimos turnos crus e reinterpretava o seguimento do seu jeito ("e a
outra?" virava outra entidade). O router já reescreve a pergunta completa para a busca (`standalone`).

**Decisão.** Só o router lê o histórico. O especialista recebe a pergunta autossuficiente que o router reescreveu,
o livro de fatos (ids e números vindos de resultado de ferramenta) e os resumos (`agents.llm_history`). O router
tem a regra dos demonstrativos: "a outra" é a entidade da última resposta que ainda não foi tratada. Sem
`standalone`, ou com `SPECIALIST_HISTORY=on`, o histórico cru volta (desenho anterior).

**Alternativas.** (1) Histórico cru em todo especialista: pass@1 de memória 0,72. (2) Memória própria por
especialista: estado espalhado, difícil de auditar e de retomar entre réplicas. (3) Só o livro de fatos, sem a
reescrita: perde o assunto do seguimento.

**Consequências.** O estado da conversa mora num lugar (store + router); o especialista é uma função da pergunta e
dos fatos, fácil de testar e de rodar em paralelo. O custo: se o router reescrever mal, o especialista não tem como
corrigir lendo o histórico; o livro de fatos e o resumo são a rede de segurança.

**Números.** Memória pass@1: 0,72 (V5) → 0,84–0,875 só com a reescrita → **92,7%** pelo resultado e **fatos 100%**
(r6). Dependent 95% → 100%. Prova:
`tests/test_v54_stateless_specialists.py::test_specialist_gets_the_standalone_question_not_the_raw_history`,
`tests/test_v54_stateless_specialists.py::test_ledger_still_reaches_the_specialist`,
`tests/test_v54_stateless_specialists.py::test_without_standalone_or_with_flag_the_raw_history_comes_back`.
