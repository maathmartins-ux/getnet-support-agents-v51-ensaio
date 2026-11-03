# Frente M — memória (v5.1)

Origem: feedback v4, item "Memory, State & Resilience": memória ao vivo com pass@1 53,8% e `numbers_acc` 64,1%; o
avaliador pediu (1) teste de que o resumo preserva valores, IDs e assunto, (2) memória medida separada do roteamento,
(3) números do histórico conferidos pela mesma checagem determinística das respostas.

## O que mudou

- **Livro de fatos da conversa** (`src/app/memory.py`). Extrai por código, de cada turno: IDs (terminal, transação, caso,
  `T-` + hex; extensível por domínio com `ID_PATTERNS`), valores em dinheiro, datas e o assunto vigente (última fala do
  cliente que declarou assunto), e dos resultados de ferramenta os registros por id (`TX1008 {amount, status, ...}`).
  Persistido por conversa (tabela aditiva `conversation_facts`, apagada junto com a conversa na rotina LGPD) e
  injetado como "Fatos da conversa" no contexto de todo agente. Por quê: o resumo rolante (`pipeline._digest`) corta cada
  fala em 120 caracteres e guarda só as 8 últimas; o id do turno 2 some na conversa de 15 turnos. Qualquer resumo, de regra
  ou de LLM, perde valor; o livro não depende dele.
  Prova: `tests/test_memory_ledger.py` (conversa de 26 turnos em que o resumo perde o id e o livro não; resumo "de LLM"
  sem os valores e o agente ainda recebe os fatos; livro apagado com a conversa; conversa antiga sem livro é reconstruída;
  store sem os métodos novos não quebra).
- **O resumo rolante devolve os fatos.** `_digest` termina com a linha `[fatos do cliente] ids ...; valores ...; datas ...;
  assunto ...` quando há conversa além da janela. Quem lê o resumo (LLM ou o código determinístico do domínio, que
  varre `conversation_digest` atrás de ids) vê o que o cliente disse. Prova: no ensaio abaixo, `bench-mem-chargeback-far`
  (id dito 23 turnos antes) passa de "sem ferramenta" para `get_transactions(TX1006)`.
- **Números do histórico e do livro contam como base da checagem numérica** (`pipeline`: `said` recebe
  `ledger.known_text()`). Só entram valores que o cliente ou uma ferramenta/fonte produziram; não existe fato "do
  assistente" no livro, então um número que o modelo inventou antes não vira base depois. Também entram as URLs que o
  próprio sistema citou como fonte: o `4106902` de `simepar.br/.../4106902` foi o único número acusado no q-mem-11 do ensaio
  ao vivo da v5. Prova: `test_value_the_customer_said_long_ago_is_a_valid_basis`,
  `test_tool_value_from_an_earlier_turn_is_a_valid_basis_in_that_conversation_only`,
  `test_number_only_the_assistant_said_is_not_laundered`, `test_number_in_a_cited_source_url_is_not_flagged` (a
  primeira e a segunda falham se `ledger.known_text()` sai do `said`).
- **Soma e contagem em código** (`memory.with_aggregates`, chamada em `agents._records_llm` depois de cada tool). Para listas de
  objetos no resultado: nº de itens, soma por coluna com cara de valor (`amount`, `valor`, `total`, `fee`, ...; extensível
  com `AMOUNT_KEYS`) em `Decimal` e quebra por `status`/`method`. O redator recebe `calculado_em_codigo`; a checagem
  numérica o reconhece como evidência. Prova: `test_aggregates_*`, `test_writer_receives_the_totals_computed_in_code`
  (10 x 0,1 = 1 exato; coluna `installments` não é somada).
- **Seguimento elíptico herda a intenção** (`src/app/followup.py`, chamado por `router.route`). "E a TX1008?", "E a de
  anteontem?", "E a outra maquininha?" não têm intenção própria: herdam intenção e plano do último assunto declarado quando
  a fala é curta, sem pergunta/verbo próprio, e (confiança do router < 0,6 OU troca entidade do mesmo tipo: id com o mesmo
  formato, tempo relativo, "outra <substantivo do assunto>"). Pedido de humano nunca é herdado nem sobrescrito; sem uma das
  provas, a decisão do router fica ("E a Get Clássica?" depois de saldo é produto novo). Nenhum id de caso no código.
  Prova: `tests/test_followup_inherit.py` (10 testes, positivos e negativos).
- **Eval: memória separada do roteamento** (`evals/memory_metrics.py`, ganchos pequenos em `run_evals.py`). Campo opcional
  `expect.expects_fact` (valores de turnos anteriores que a resposta deve conter; "R$ 75,00" = 75.0) vira a checagem
  `memory`; o relatório ganha "Memória × roteamento" (por caso: perda só de roteamento, só de memória ou nas duas).
  Caso sem o campo segue igual. Prova: `tests/test_eval_memory_metrics.py`.
- `scripts/ensaio_overlay.sh`: copia um repositório entregue e coloca o motor do kit por cima (como o ensaio da v5).

## Medido (offline, sem API; domínio e casos da Getnet v4 + motor do kit)

Split `memory` da v4 (13 casos), motor antes = kit `433980f`, depois = esta branch:

| | antes | depois |
|---|---:|---:|
| intent | 84,6% | 100% |
| tools (n=6) | 66,7% | 83,3% |
| roteamento (intent+handoff+tools) | 76,9% | 92,3% |
| memória (fatos + números) | 100% | 100% |
| pass@1 (todos os checks) | 69,2% (9/13) | 84,6% (11/13) |
| gate de intent do conjunto de gate (129 casos) | 96,1% | 97,7% |

Os demais 8 splits ficaram idênticos (nenhum caso mudou de resultado fora do `memory`). Corrigidos: q-mem-01 e q-mem-09 (o
"E a TX1008?" que a v4 e o ensaio da v5 erravam). Restam q-mem-04 (a regra `_TERMINAL` do domínio da v4 não conhece
"machine"; é do domínio) e q-mem-06 (resposta offline extrativa em português para pergunta em inglês).

Bancada (só aqui, declarada; `docs/kit/ensaio/m_memory_bench_cases.jsonl`, 3 casos NOVOS, não entram no gate nem nos
casos do kit): 16 casos, pass@1 68,8% -> 87,5%; o caso `bench-mem-chargeback-far` (TX1006 dito 23 turnos antes) falha antes
(sem ferramenta, o domínio pergunta "qual transação?") e passa depois. Resultados: `docs/kit/ensaio/m_memory_antes.json` e
`m_memory_depois.json`. Para repetir: `scripts/ensaio_overlay.sh <repo_v4> <destino> [<kit>]`, copiar o JSONL da bancada
para `<destino>/evals/cases.d/` e `python -m evals.run_evals --split memory`.

## Reanálise das 3 falhas de números do ensaio ao vivo (v5_live_memory.json)

- q-mem-07 e q-mem-08: o modelo repetiu, retratando-se, cotações que ELE mesmo tinha dito no turno anterior sem nenhuma
  busca por trás (5,4380; 5,4325; 5,0377; 10/31/2026). A checagem estava certa. De propósito o livro não aceita fala do
  assistente como base, então isso continua sendo acusado; não é "soma/contagem sobre a tool" como o ensaio anotou.
- q-mem-11: era o número dentro de uma URL citada (`.../4106902`). Corrigido acima.
- Soma/contagem sobre tool (a classe que o ensaio atribuiu a elas) já passava na checagem (`_Derived`); o ganho do agregado
  em código é o redator não errar a conta em primeiro lugar.

## O que NÃO está provado

- Nada disto foi medido ao vivo (API bloqueada): pass@1 >= 85% e `numbers_acc` >= 95% ao vivo seguem como meta, não
  como resultado. Offline o `numbers_acc` do `memory` já era 100% (a falha de números só existe com LLM).
- O ganho do livro nas respostas do LLM (ele usar "Fatos da conversa" em vez de perguntar de novo) só é provado até a
  entrada: o teste mostra que o prompt do agente recebe os fatos, não que o modelo os usa.
- O resumo rolante do kit é por regra, não LLM; se um fork trocar por LLM, o livro e a linha de fatos independem dele
  (teste com resumo sem valores), mas esse resumo de LLM não existe aqui para ser medido.
- `facts_acc` offline tem n=1 na bancada: o código determinístico quase nunca repete na resposta um valor de turno anterior.
- A herança de intenção usa o histórico como o router o recebe (assunto = última fala com assunto declarado por regra/vocabulário).
