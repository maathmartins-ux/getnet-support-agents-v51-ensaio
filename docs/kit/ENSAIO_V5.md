# Ensaio do v5 sobre o domínio da Getnet v4 (01/11/2026)

**O que foi feito:** o repositório entregue da v4 (`getnet-support-agents-v4`, commit `fd85cf6`) foi copiado para uma
pasta à parte (o original não foi tocado) e o **motor do v5** foi colocado por cima (`src/app/*.py`, `evals/*.py`,
`scripts/`), mantendo o domínio, os dados, o corpus e os casos da v4. Mesmo domínio, mesmos casos, motor diferente.
Eval ao vivo com o LLM real, 3 rodadas por caso (`--repeat 3`). Custo total do ensaio: cerca de US$ 5.
Resultados brutos em [ensaio/](ensaio/): `v4_*` (entregues na v4), `v5_*` (motor v5 corrigido) e
`v5_antes_das_correcoes_*` (a 1ª rodada, com as regressões abaixo).

## Resultado

**Offline** (gate do CI, 129 casos): portão de intenção 96,1% nos dois. O v5 ficou **igual ou melhor em todos os
splits**: idioma 87,1% → 87,9% no total e 78,1% → 81,2% em `official-var`; handoff do `memory` 92,3% → 100%
(com `search_query`). Recall@3 por trecho idêntico (0,486; MRR 0,61): as melhorias de RAG do v5 não mexem nessa medida.

**Ao vivo, `official`** (10 cenários literais do enunciado × 3 rodadas):

| métrica | v4 | v5 sem as correções | v5 corrigido |
|---|---:|---:|---:|
| intenção | 100% | 100% | 100% |
| handoff certo | 96,7% | 100% | 100% |
| números com base na evidência | 80% | 100% | 100% |
| **idioma da resposta** | 100% | **76,7%** | 100% |
| ferramentas | 100% | 100% | 100% |
| pass@1 | 0,77 | 0,77 | 1,00 |
| **pass^3** | 0,70 | 0,70 | **1,00** |
| p95 | 15,6 s | 22,3 s | 21,6 s |

**Ao vivo, `memory`** (multi-turno, 13 casos × 3):

| métrica | v4 | v5 sem as correções | v5 corrigido |
|---|---:|---:|---:|
| intenção | 92,3% | 89,7% | 92,3% |
| handoff certo | 100% | 92,3% | 94,9% |
| números com base | 64,1% | 97,4% | 92,3% |
| idioma | 97,4% | 100% | 100% |
| pass@1 | 0,54 | 0,79 | 0,79 |
| pass^3 | 0,46 | 0,69 | 0,62 |

Leitura honesta: no `official` o ganho é grande e limpo (30 de 30 execuções passam), mas é **uma rodada de 10
cenários**; o intervalo é largo e não deve ser lido como garantia. No `memory` o ganho em números é real
(64% → 92%); o pass^3 oscila entre rodadas (0,69 e 0,62), o que é o ruído esperado com 13 casos.

**Uma rodada descartada (e por quê).** A 3ª rodada do `memory`, já com o estado do caso, saiu com 135 erros de LLM e
foi **descartada**. A causa, descoberta depois: a API respondeu `You have reached your specified API usage limits.
You will regain access on 2026-12-01` (o limite mensal de gasto da conta; o ensaio inteiro custou cerca de US$ 8 e
consumiu o que restava). Por isso **o estado do caso NÃO foi medido ao vivo**: só por 8 testes de ponta a ponta e pelo
eval offline (sem regressão). Os números do `memory` acima são os da 2ª rodada (motor com idioma e `search_query`,
sem estado do caso). Repetir essa medida é o item 1 do [CONTINUAR_LOCAL.md](CONTINUAR_LOCAL.md).

## O que o ensaio achou (e que os 459 testes do kit não pegaram)

| Achado | Causa | Correção | Prova |
|---|---|---|---|
| handoff do `memory` caiu 92,3% → 76,9% offline | o aviso "caso aberto" vinha com `handoff.required=True`, e toda pergunta depois de uma escalação virava "handoff" | `required=False` (só `reason` e `ticket_id`) | offline volta a 92,3% e sobe a 100% com `search_query` |
| idioma ao vivo 100% → 76,7% | pergunta em inglês com um termo em português, ou trechos do site em português, saía em português ~50% das vezes (com e sem dado ao vivo, medido em 4 chamadas reais); o prompt de sistema em português vencia | diretiva de idioma no FIM de todo pedido de agente + 1 reescrita se a saída vem no idioma errado | `official` ao vivo: idioma 100% |
| rodada com a API fora do ar parecia uma medida válida (`status: complete` com 135 erros) | o runner não olhava as chamadas perdidas | `degraded`/`aborted_quota`, arquivo à parte, nunca por cima de resultado completo | 2 testes; a proteção barrou a 4ª rodada na 1ª onda e preservou a 2ª |
| seguimento ("E pelo Link de Pagamento?") não achava o assunto anterior | o Knowledge buscava só a frase curta | `search_query`: o seguimento herda o assunto da última fala do cliente | `q-mem-13` passou a achar as páginas de Link de Pagamento |

## Limites que continuam

- `q-mem-09` ("E a TX1008?") falha igual na v4 e no v5: o Router classifica como `support` e o caso espera
  `troubleshoot`. Não é regressão e não foi mexido (o caso e o gate não se alteram para passar).
- `q-mem-13` oscila: as fontes **não dizem** o máximo de parcelas do Link de Pagamento; às vezes o sistema responde
  parcial, às vezes escala. As duas saídas são honestas; o caso prefere a parcial.
- `numbers` do `memory` ainda perde 1 execução por caso em `q-mem-07/08/11` (soma e contagem sobre a tool).
- Recall@3 por trecho continua 0,486: o gargalo é o corpus e o glossário do domínio, não o motor.
- Nada disto foi medido no relógio de 60 min: é o motor sobre um domínio já pronto.
