# ADR 0004 — Buscador escolhido por medida com teto de latência E de RAM; eval ao vivo num processo só

Status: aceito no kit v5.1 (02/11/2026), frente R2. Complementa a escolha medida da frente R
(`run_evals --choose-retriever --apply`, que grava a escolha em data/retriever.json).

**Contexto.** Na bancada da v4 (corpus de 395 trechos depois do dedupe, gold de 50 perguntas com fonte e 16 sem),
o denso e5-large com rerank local foi o melhor buscador medido, e também o mais pesado: um processo com e5-large +
bge-reranker-v2-m3-int8 teve pico de 2672 MB no eval offline com os vetores do corpus em cache e 7051 MB vetorizando
o corpus. A máquina do relógio tem 15 GB e roda ao mesmo tempo a API, o eval ao vivo e outra sessão (6–8 GB). O
`live_eval.sh` abria um processo por split (5 ou mais), e a escolha só olhava a latência: nada impedia escolher uma
configuração que não cabe na memória.

**Decisão.**
- `choose()` aceita só configuração com p95 por consulta ≤ `--latency-budget-ms` (padrão 1500) **e** RAM ≤
  `--ram-budget-mb` (padrão 4096; 0 desliga) **e** portão que recusa ≥ 85% das perguntas sem fonte; entre elas, maior
  MRR. A RAM de cada configuração é medida no próprio comparativo: o processo antes do 1º modelo + o RSS que cada
  modelo dela somou ao carregar. A escolha gravada (data/retriever.json) traz os dois tetos e a RAM de cada linha.
- 4096 MB por processo: API + eval ao vivo cabem em 8 GB, metade da máquina, com a outra sessão ao lado.
- O eval ao vivo roda todos os splits num processo só (`run_evals --live --splits a,b,c`), cada um com a sua cota,
  arquivo e cassete; os modelos carregam uma vez. `live_eval.sh` e `live_eval.ps1` usam esse modo sempre.
- Vetorização do corpus em lotes de 16 trechos ordenados por tamanho e sem a arena de memória do ONNX; vetor por
  trecho em disco (re-ingest só vetoriza o texto novo); cache compartilhado entre os worktrees do relógio.
- `--choose-retriever --fast` mede só 3 configurações (bm25, dense[e5-large], dense[e5-large] + bge-m3-int8 com
  pool 10 e 600 caracteres por trecho), e `scripts/fetch_models.py --fast` baixa os dois modelos no T+0.

**Prova** (medida antes do relógio, CPU de 4 vCPU compartilhada).

| configuração | Recall@3 | MRR | p95 ms | RAM estimada MB |
|---|---:|---:|---:|---:|
| bm25 | 0,543 | 0,617 | 1,3 | — |
| dense[e5-large] | 0,703 | 0,920 | 98 | 1516 |
| dense[e5-large] + bge-m3-int8 @5 (1500 caracteres) | 0,734 | 0,937 | 896 | 2359 |
| dense[e5-large] + bge-m3-int8 @10 (600 caracteres) | 0,754 | 0,947 | 1130 | 2359 |
| dense[e5-large] + bge-m3-int8 @20 (600 caracteres) | 0,777 | 0,957 | 4666 | 2359 |
| hybrid[e5-large] + bge-m3-int8 @20 (600 caracteres) | 0,774 | 0,927 | 6092 | 2359 |

- Pico medido do processo do comparativo: 2909 MB (a estimativa, 2359 MB, não conta os vetores do corpus nem o eval).
- Vetorizar o corpus: lote 256 com pico de 4927 MB; lote 16, 2075 MB. Eval offline com o corpus por vetorizar:
  445 s / 7051 MB → 276 s / 2928 MB; com vetores e consultas em cache: 165 s / 2672 MB → 60 s / 2491 MB, relatório
  idêntico. Re-ingest com 10 trechos mudados: 143 s → 12,1 s.
- `--choose-retriever --fast` com o corpus por vetorizar: 269 s, pico 2941 MB. `make eval`: 177,6 s, pico 2742 MB.
- Rodada ao vivo, 5 splits num processo (`--repeat 1`, 4 workers por split, pool 10/600): 59 casos em 161 s, todos
  `complete`, pico de 4821 MB no processo (cinco processos seriam 5 x 2,7 GB ou mais). O teto de 4096 MB estima um
  processo servindo a API; o eval ao vivo com 20 casos ao mesmo tempo passa dele.

**Alternativas consideradas.**
- *Modelo menor.* MiniLM multilíngue (medido pela frente R na mesma bancada): denso 0,569 / 0,700, híbrido
  0,675 / 0,803. Cabe em muito menos RAM, mas perde 0,13 de Recall@3 e 0,22 de MRR para o e5-large: não é o padrão;
  o teto de RAM o escolhe sozinho quando o e5-large não cabe.
- *Sem reranker.* O denso sozinho fica em 1516 MB e 98 ms de p95; o rerank soma ~843 MB e ~1 s de p95 por +0,051 de
  Recall@3 e +0,027 de MRR (pool 10/600). A escolha decide por medida e pelos dois tetos; sob carga maior (p95 do
  pool 10 medido em 3345 ms numa 2ª rodada) ela cai para o denso sem rerank.
- *e5-large quantizado (int8).* Não medido nesta frente; sem medida de qualidade, não entra.
- *Threads do ONNX.* Não medidas; ficou o padrão do fastembed.
- *Processos em paralelo com limite por RAM.* Mais um parâmetro para errar no relógio; o processo único dá a mesma
  concorrência de casos (`--workers` por split) com uma cópia só dos modelos.

**Não provado.** Latência em máquina dedicada (todas as medidas acima foram em máquina compartilhada, load 2–7,6; o
mesmo pool 10 mediu p95 de 1130 ms e de 3345 ms em duas rodadas); RAM fora do Linux (sem `/proc`, a RAM sai `None`
e não reprova); o teto de 4096 MB não foi testado contra uma falta real de memória; e5-large quantizado.
