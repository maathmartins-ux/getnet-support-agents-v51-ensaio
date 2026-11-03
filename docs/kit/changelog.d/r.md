# Frente R — retrieval (v5.1)

Bancada: cópia da entrega v4 (`getnet-support-agents-v4`, corpus `data/knowledge` com 424 trechos, gold
`evals/retrieval.d/k.jsonl`: 50 perguntas com 1–5 trechos relevantes e 16 sem fonte), com os arquivos do motor
deste branch por cima. Nenhuma chamada a LLM: tudo medido offline, em CPU (4 núcleos).

## Ingest: tabelas inteiras e rotuladas

- **O quê:** `<table>` vira linhas rotuladas ("Débito — 2 dias úteis*: 1,89%; Receba conforme suas vendas: 1,95%"):
  cabeçalho com colspan, rótulo de linha numérico ganha o nome da 1ª coluna, tabela pequena vira trecho próprio
  (mesmo abaixo de 300 caracteres), tabela longa é cortada entre linhas com o cabeçalho repetido em cada pedaço.
  Linha de células coladas (tabela em `<div>`) longa demais é cortada entre células, antes de um rótulo, em pedaços
  de tamanho parecido; antes era truncada em 800 caracteres ou descartada.
- **Por quê:** a feedback v4 pediu "corrigir o chunking que corta tabelas de tarifa". No corpus da v4, as tabelas de
  taxas de débito/crédito (`/duvidas/taxas/` e `/duvidas/`) não existiam: as células têm menos de 15 caracteres e o
  ingest da v4 as descartava como menu. O ingest do kit v5.0 (glue_short) já as mantinha, mas sem saber de que
  coluna era cada valor ("Débito: · 1,89% · 1,95%") e com linhas da tabela misturadas.
- **Prova medida** (mesmo HTML baixado em 02/11/2026; o ingest da v4 sobre ele reproduz 423 dos 424 trechos da v4
  com o mesmo sha256 — o 424º é a tabela de maquininhas escrita à mão):
  - linhas de preço/taxa do HTML (`\d,\d%` ou `R$ \d`) ausentes do corpus: v4 156 de 217 · kit v5.0 2 de 217 ·
    agora 0 de 217;
  - linhas de dados das 2 `<table>` de taxas (34 linhas, nas 2 páginas) com rótulo e valores juntos na mesma linha:
    v4 0 · kit v5.0 30 (sem o nome da coluna em nenhum valor) · agora 34 (todo valor com o nome da coluna).

## Retriever escolhido por medida (denso, cross-encoder local, dedupe, portão por retriever)

- **O quê:** `RETRIEVER=bm25|hybrid|dense`; embeddings fastembed com o prefixo de papel que o e5 exige
  ("query:"/"passage:") e vetores dos trechos em disco (`var/embeddings/<modelo>-<hash do corpus>.json`);
  `RERANK=cross` = cross-encoder local (fastembed `TextCrossEncoder`) sobre o top-N (`RERANK_POOL`). O rerank por
  LLM só liga com `RERANK=llm` explícito. Sem fastembed ou sem o modelo: BM25, com o motivo em `.fallback`, no
  `/health` (`retriever_fallback`) e em cada linha do eval.
- **Dedupe na carga do índice:** trecho com >= 90% dos 5-gramas contido em outro sai (fica o maior; empate → o da
  página com menos trechos, a específica, não a que agrega). `Index.aliases` liga o removido ao mantido e o
  Recall@3 conta por passagem do gold original (o denominador não muda). `RAG_DEDUPE=off` desliga.
- **Portão "sem fonte, sem afirmação" por retriever:** o piso de cosseno fixo do kit (0,4, medido com MiniLM) não
  serve ao e5-large, que põe quase todo trecho entre 0,75 e 0,90: na bancada, denso e5 com o piso fixo recusou
  **0 de 16** perguntas sem fonte (BM25 com o MIN_SCORE da v4: 13 de 16). O eval calibra o par (BM25, cosseno) por
  configuração; a escolha só aceita configuração cujo portão recuse >= 85% das sem fonte e grava os limiares junto
  (`choice.gate`), que só valem se o ambiente não trocou retriever, modelo ou rerank e nada caiu para o BM25.
- **Escolha:** `python -m evals.run_evals --choose-retriever [--apply] [--latency-budget-ms 1500]
  [--embed-models a,b] [--rerank-models x,y] [--rerank-pools 5,10,20] [--reuse] [--verify]`: maior MRR com p95 por
  consulta dentro do teto e portão válido; grava `data/retriever.json`, que o app lê como padrão e o README cita
  (bloco `retrieval` do `fill_readme.py`). Job `retrieval` no CI: instala o fastembed, baixa os modelos da escolha
  (`scripts/fetch_models.py`, cache entre execuções) e roda `--verify` (mede de novo só a escolhida e o bm25;
  reprova se MRR ou Recall@3 derivarem mais que 0,01). A imagem `EXTRAS=hybrid` embute os modelos da escolha.
- **Métricas:** Recall@3, MRR@3, hit@3 (IC 95%), nDCG@3, as mesmas por URL (independem do corte em trechos),
  latência p50/p95 por consulta e o portão; por pergunta, e quem melhorou/piorou contra o bm25, em
  `evals/results/retrieval_compare.json`.

### Números da bancada (corpus e gold da v4, CPU 4 vCPU, sem LLM)

Linha de base da v4 reproduzida com o motor novo e `RAG_DEDUPE=off`: **bm25 Recall@3 0,486 · MRR 0,61 · hit@3 0,72**
· nDCG@3 0,498 · URL hit@3 0,90 (os mesmos 0,486/0,61/0,72 do feedback).

Grade completa (dedupe ligado, 29 trechos removidos de 424; gold original; MRR = MRR@3). Gerada pelo
`--choose-retriever` (duas rodadas: modelos × pool 20, depois bge-m3-int8 com pool 5 e 10; as bases repetidas ficam
com a 2ª rodada). Latência por consulta (embedding da pergunta + rerank), máquina compartilhada com outras sessões:
load average 3,5–6 na 1ª rodada e 1–4 na 2ª, então os p95 são teto, não piso.

| configuração | Recall@3 | MRR | hit@3 | nDCG@3 | URL hit@3 | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| bm25 | 0.543 | 0.617 | 0.74 | 0.53 | 0.86 | 1.7 | 2.2 |
| hybrid[multilingual-e5-large] | 0.669 | 0.777 | 0.88 | 0.662 | 0.94 | 81.3 | 101.1 |
| dense[multilingual-e5-large] | 0.703 | 0.92 | 0.94 | 0.751 | 0.94 | 86.4 | 163.3 |
| hybrid[paraphrase-multilingual-MiniLM-L12-v2] | 0.675 | 0.803 | 0.88 | 0.678 | 0.9 | 21.7 | 25.1 |
| dense[paraphrase-multilingual-MiniLM-L12-v2] | 0.569 | 0.7 | 0.8 | 0.575 | 0.92 | 22.8 | 30.9 |
| bm25+cross[jina-reranker-v2-base-multilingual@20] | 0.633 | 0.837 | 0.88 | 0.661 | 0.96 | 3239.3 | 5136.4 |
| bm25+cross[bge-reranker-v2-m3-int8@20] | 0.629 | 0.82 | 0.88 | 0.655 | 0.96 | 2360.4 | 3391.1 |
| hybrid[multilingual-e5-large]+cross[jina-reranker-v2-base-multilingual@20] | 0.747 | 0.927 | 0.96 | 0.774 | 0.98 | 3639.2 | 5076.4 |
| hybrid[multilingual-e5-large]+cross[bge-reranker-v2-m3-int8@20] | 0.781 | 0.917 | 0.96 | 0.807 | 0.98 | 2685.0 | 3294.5 |
| dense[multilingual-e5-large]+cross[jina-reranker-v2-base-multilingual@20] | 0.743 | 0.947 | 1.0 | 0.772 | 1.0 | 3805.1 | 4574.3 |
| dense[multilingual-e5-large]+cross[bge-reranker-v2-m3-int8@20] | 0.764 | 0.947 | 0.98 | 0.801 | 1.0 | 2911.6 | 3308.8 |
| hybrid[paraphrase-multilingual-MiniLM-L12-v2]+cross[jina-reranker-v2-base-multilingual@20] | 0.723 | 0.897 | 0.94 | 0.751 | 0.96 | 3087.3 | 3883.1 |
| hybrid[paraphrase-multilingual-MiniLM-L12-v2]+cross[bge-reranker-v2-m3-int8@20] | 0.757 | 0.897 | 0.92 | 0.783 | 0.98 | 2346.0 | 2920.1 |
| dense[paraphrase-multilingual-MiniLM-L12-v2]+cross[jina-reranker-v2-base-multilingual@20] | 0.639 | 0.857 | 0.92 | 0.671 | 0.98 | 2913.8 | 3696.5 |
| dense[paraphrase-multilingual-MiniLM-L12-v2]+cross[bge-reranker-v2-m3-int8@20] | 0.675 | 0.867 | 0.88 | 0.709 | 1.0 | 2256.9 | 2771.2 |
| bm25+cross[bge-reranker-v2-m3-int8@5] | 0.559 | 0.747 | 0.78 | 0.589 | 0.9 | 457.2 | 748.8 |
| bm25+cross[bge-reranker-v2-m3-int8@10] | 0.589 | 0.77 | 0.8 | 0.62 | 0.94 | 918.9 | 1490.3 |
| hybrid[multilingual-e5-large]+cross[bge-reranker-v2-m3-int8@5] | 0.699 | 0.87 | 0.88 | 0.739 | 0.94 | 564.6 | 844.0 |
| hybrid[multilingual-e5-large]+cross[bge-reranker-v2-m3-int8@10] | 0.756 | 0.94 | 0.96 | 0.793 | 0.98 | 1152.2 | 1741.7 |
| dense[multilingual-e5-large]+cross[bge-reranker-v2-m3-int8@5] **← escolhida** | 0.734 | 0.937 | 0.96 | 0.78 | 0.96 | 609.3 | 827.6 |
| dense[multilingual-e5-large]+cross[bge-reranker-v2-m3-int8@10] | 0.741 | 0.957 | 0.98 | 0.787 | 0.98 | 1211.4 | 1618.6 |

**Escolhida (teto p95 1500 ms): dense[e5-large] + cross[bge-reranker-v2-m3-int8, pool 5]** — Recall@3 0,486 →
**0,734**, MRR 0,61 → **0,937**, hit@3 0,72 → **0,96** (IC 95% 86,5–98,9), nDCG@3 0,498 → 0,780; por URL: Recall@3
0,867, MRR 0,950, hit@3 0,96. p50 609 ms / p95 828 ms por consulta. Contra o bm25: 23 perguntas melhoraram,
5 pioraram, 22 iguais (lista em `retrieval_compare.json`). Portão calibrado para ela (no próprio conjunto, 50
com fonte e 16 sem): responde com a fonte certa 94% dos com fonte e recusa 87,5% (14/16) dos sem fonte; o bm25
com o limiar calibrado responde 74% e recusa 93,8%.

- O que é de cada mudança (mesma configuração, dedupe desligado): dense+cross 0,721 / 0,930; dense sozinho
  0,677 / 0,917; bm25 0,486 / 0,610. O dedupe soma +0,013 Recall@3 / +0,007 MRR na escolhida e +0,057 / +0,007
  no bm25 (parte disso é mecânica: duas cópias do mesmo texto no gold passam a ser achadas por um trecho só).
- Rerank só paga com pool pequeno: com pool 20 todos os cross-encoders passaram de 2,7 s de p95 (jina-v2 até 5,1 s);
  `dense[e5]+bge@10` tem o maior MRR medido (0,957) mas p95 1619 ms, fora do teto. O híbrido RRF com o e5 é pior que
  o denso sozinho (MRR 0,777 × 0,920): o BM25 puxa para o top-3 trechos com termo em comum e assunto errado.
- `--verify` sobre a escolha gravada (51 s): MRR 0,937 / Recall@3 0,734 e bm25 0,617 / 0,543 reproduzidos exatos.
- **Meta Recall@3 >= 0,85 NÃO atingida; meta MRR >= 0,80 atingida (0,937).** Teto do Recall@3 neste gold com
  3 trechos e no máximo 2 por URL: 0,971 (2 perguntas têm 5 trechos relevantes, teto 0,6 nelas). Na revisão por
  agente abaixo, 20 trechos do top-5 que respondem à pergunta não estavam no gold e 2 do gold não respondiam
  (ex.: em "Para receber por Pix preciso ter conta em banco?", o trecho "[o Pix] pode ser feito por conta corrente,
  poupança ou conta de pagamento" não estava no gold). Por URL, que não depende do corte em trechos, o Recall@3 da
  escolhida é 0,867.

### Corpus re-cortado pelo ingest novo (gold mapeado por texto)

Mesmo HTML, ingest deste branch (466 trechos; 31 quase-duplicatas fora): o gold por id foi levado ao corpus novo
por `retrieval_review --map-gold` (130 passagens, 0 perdidas; 8 das 58 passagens distintas têm < 90% do texto no
trecho novo, a menor 54%). Arquivos em `docs/kit/ensaio/r/`.

| configuração | Recall@3 | MRR | hit@3 | nDCG@3 | URL Recall@3 | URL hit@3 | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| bm25 | 0.553 | 0.66 | 0.76 | 0.556 | 0.747 | 0.86 | 2.2 |
| dense[e5] | 0.673 | 0.88 | 0.92 | 0.714 | 0.86 | 0.94 | 144.0 |
| dense[e5]+cross[bge-int8@5] | 0.727 | 0.907 | 0.96 | 0.76 | 0.89 | 0.96 | 1003.0 |

O corte novo não move o número do gold antigo (que não tem pergunta sobre as tabelas que ele recuperou): −0,007 de
Recall@3 e −0,030 de MRR por trecho na escolhida, +0,023 de Recall@3 por URL. O ganho do ingest é o conteúdo que
passou a existir (tabelas), e nenhuma pergunta do gold mede isso — falta gold para tarifa.

### Gold revisado (POR AGENTE, não humano) — nunca misturado com o original

`retrieval_review --export` (top-5 da escolhida, com texto) rotulado por mim, Claude, com o critério "o trecho
responde a pergunta, no todo ou em parte; tangencial = não" e `--apply` → `gold_revisado_por_agente.jsonl`
(revisor e data em cada linha): +20 trechos, −2. É um viés a favor da escolhida (só o top-5 dela foi julgado) e
**não substitui a revisão humana**, que segue pendente (`python -m evals.retrieval_review --export`, depois
`--apply <arquivo> --reviewer "Nome"`).

| configuração (gold revisado por agente) | Recall@3 | MRR | hit@3 | nDCG@3 | URL hit@3 |
|---|---:|---:|---:|---:|---:|
| bm25 | 0.497 | 0.62 | 0.72 | 0.523 | 0.88 |
| dense[e5] | 0.717 | 0.97 | 0.98 | 0.81 | 0.98 |
| dense[e5]+cross[bge-int8@5] | 0.751 | 0.98 | 0.98 | 0.838 | 0.98 |

Com mais trechos relevantes por pergunta (11 perguntas com 4, 5 com 5), o teto do Recall@3 cai para 0,918: o
Recall@3 é limitado pelo k=3, não pela ordem (MRR 0,98).

### O que NÃO está provado

- Latência medida em máquina compartilhada (load 1–6); não há medida em máquina dedicada nem com o container.
- O portão foi calibrado e medido no MESMO conjunto (50 com fonte, 16 sem): é dentro da amostra; com 16 negativos
  o IC 95% da recusa da escolhida vai de 64% a 96,5%.
- A imagem `EXTRAS=hybrid` com os modelos da escolha e o job `retrieval` do CI não rodaram aqui (sem daemon
  Docker e sem Actions nesta sessão); o `--verify` rodou localmente (51 s, números exatos).
- Na bancada o app carrega e5-large (2,2 GB) + bge-m3-int8 (0,6 GB): a 1ª subida sem cache calcula os vetores do
  corpus (minutos em CPU); o cache em `var/embeddings/` evita isso nas seguintes, não o download do modelo.
- Nenhuma resposta ao vivo foi medida com o retriever novo (API bloqueada): o efeito em groundedness é inferido,
  não medido.
