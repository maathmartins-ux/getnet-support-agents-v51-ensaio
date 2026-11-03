# Ensaio do kit v5.1 sobre o domínio da Getnet v4 (02/11/2026)

Motor do kit v5.1 por cima do repositório entregue da v4 (`scripts/ensaio_overlay.sh`; o original não muda). Mesmos
casos, corpus e gold da v4. Ao vivo com o LLM real, 3 rodadas por caso, juiz Opus com canários (4/4 pegos).
Custo total do ensaio: cerca de US$ 13. Resultados brutos em [ensaio/](ensaio/) (`v51_r1_*`, `v51_r2_*`,
`v51_r3_*`, `v51_final_*`).

## Resultado final (motor completo: G + R + H + M + E e as correções do ensaio)

| métrica | v4 entregue | kit v5.1 | meta da correção |
|---|---:|---:|---:|
| juiz: oficiais fundamentadas | 60% | **96,7%** | ≥ 90% |
| juiz: oficiais úteis | 80% | **100%** | — |
| oficiais: números com base | 80% | **100%** | ≥ 95% |
| oficiais: pass^3 | 0,70 | **0,90** | ≥ 0,90 |
| memória: pass@1 | 0,54 | **0,92** | ≥ 0,85 |
| memória: números com base | 64% | **100%** | ≥ 95% |
| juiz: memória fundamentada | — | **97,4%** | — |
| busca: MRR | 0,61 | **0,92** (base denso) / 0,94 (com rerank) | ≥ 0,80 |
| busca: Recall@3 por trecho | 0,486 | **0,70** / 0,73 | ≥ 0,85 ❌ |
| busca: Recall@3 por página | 0,76 | 0,85 | — |
| offline: handoff (174 casos) | 90,2% | 90,8% | — |
| p95 oficiais / memória | 15,6 s / 31,8 s | 20,8 s / 52,8 s ❌ | — |

## O que o ensaio achou e corrigiu (nenhum teste pegava)

| rodada | achado | correção |
|---|---|---|
| 1 | seguimento de câmbio/clima ("E em Curitiba?") ia para a busca web | `live_data.followup_query` |
| 1 | soma por data feita pelo redator (R$ 265,50) | agregados por data em código |
| 1 | fato de turno anterior parecia "sem fonte" ao juiz | fatos da conversa como evidência |
| 1 | oferta de reinício com o caso no humano; nome interno de agente na resposta | oferta de escrita bloqueada; nome removido |
| 2 | link do BCB citado e ausente da evidência (6 reprovações) | link da fonte na evidência |
| 2 | Open-Meteo com timeout em ~1 de 6 chamadas | 3 tentativas com timeout/5xx |
| final | modelo de 2 GB recarregado a cada índice; eval morto com 14 GB | 1 modelo por processo + trava de montagem (pico 7,7 GB) |
| final | 1º caso frio estourava o NODE_TIMEOUT | buscador aquecido antes do 1º caso |
| final | portão do denso recusava pergunta com fonte (handoff 84%) | BM25 confere antes de "sem fonte" |
| final | calibração do portão sobre o denso dava MIN_SCORE = 0 | calibração sobre o BM25 |

## Limites que continuam

- Recall@3 por trecho 0,70–0,73 (meta 0,85): o gold da v4 lista 3–5 trechos por pergunta; o melhor medido foi 0,78
  com p95 > 2,7 s. O gold revisado por humano não foi feito.
- p95 alto: memória 52,8 s. A repetição de chamada lenta não resolveu; a cauda vem de turnos com várias chamadas.
- Memória do processo com o denso: pico de 7,7 GB no eval; a imagem com `EXTRAS=hybrid` precisa de ≥ 8 GB.
  Frente R2 ([changelog.d/r2.md](changelog.d/r2.md)): 2,9 GB vetorizando o corpus (lotes de 16), 2,5 GB com cache, e
  4,8 GB no eval ao vivo com 5 splits num processo só (antes, um processo por split).
- Clima: o Open-Meteo ainda falha às vezes nesta nuvem e a pergunta cai na busca web (q-mem-11/12).
- Tudo isto é o motor sobre um domínio JÁ PRONTO, sem relógio. A V5 refaz domínio, casos e medidas em 58 min.

---

# Ensaio v5.2 (02/11/2026): motor com L + R2, ingest corrigido, gold essencial cego

Mesmo domínio da v4, motor do kit depois das frentes L (latência) e R2 (busca/RAM), máquina sem outro processo
pesado. Ao vivo, 3 rodadas, oficiais e memória num processo só (`run_evals --live --splits official,memory`).
Brutos: [ensaio/v52_*](ensaio/) e [ensaio/v52_essencial/](ensaio/v52_essencial/).

| métrica | v4 entregue | v5.1 (ensaio anterior) | **v5.2** | meta |
|---|---:|---:|---:|---:|
| oficiais: pass@1 / pass^3 | — / 0,70 | 96,7% / 0,90 | **96,7% / 0,90** | pass^3 ≥ 0,90 |
| oficiais: números com base | 80% | 100% | **100%** | ≥ 95% |
| memória: pass@1 | 0,54 | 0,92 | **0,90** | ≥ 0,85 |
| memória: números com base | 64% | 100% | **100%** | ≥ 95% |
| juiz: oficiais fundamentadas / úteis | 60% / 80% | 96,7% / 100% | **100% / 100%** | ≥ 90% |
| juiz: memória fundamentada / útil | — | 97,4% / 92,3% | **97,4% / 94,9%** | — |
| juiz: canários pegos; concordância com a calibração humana | — | 4/4 | **4/4; 95,7% (kappa 0,91)** | 4/4 |
| p50 / p95 oficiais | — / 15,6 s | 10,6 / 20,8 s | **7,2 / 24,3 s** | — |
| p50 / p95 memória | — / 31,8 s | 22,6 / 52,8 s | **14,0 / 41,2 s** | — |
| custo da rodada (oficiais + memória) | — | US$ 2,00 | **US$ 1,55** | — |

Falhas ao vivo (todas de 2 casos): q-mem-13 ("E pelo Link de Pagamento?") vai ao humano nas 3 rodadas porque o
corpus da v4 não traz o limite de parcelas do Link (a v4 respondia em parte; já falhava na v5.1); official-05 abriu
caso em 1 de 3 rodadas (supervisor LLM, variação). Nenhuma é regressão nova; são do tipo que o relógio corrige caso
a caso.

## Busca: o gold "todo relacionado" escondia o que importa, e o ingest do kit piorava a busca

Gold novo: 2 rotuladores (subagentes Sonnet) às CEGAS marcaram as passagens essenciais das 50 perguntas com fonte,
num conjunto de candidatos sem id, ordem nem nota (top-3 de 3 buscadores + o gold da v4, embaralhados).
Concordância: Jaccard 0,81, 31 de 50 idênticas. Consenso (interseção, senão união) virou regra de texto
(`passage_text`), que sobrevive a re-ingest. Ferramenta no kit: `evals/essential_gold.py`.

| corpus (denso e5 + rerank bge pool 10) | Recall@3 essencial | MRR | p95 por busca |
|---|---:|---:|---:|
| corpus entregue da v4 (ingest da v4 + tabela feita no relógio) | 0,85 | 0,87 | 1,1 s |
| ingest do kit v5.1 (corte por seção + contexto indexado) | 0,747 | 0,82 | 1,2 s |
| sem corte por seção | 0,787 | 0,86 | 1,2 s |
| sem contexto no índice | 0,79 | 0,87 | 1,1 s |
| **sem os dois (padrão do kit v5.2)** | **0,82** | **0,86** | 1,3 s |
| pergunta de FAQ abre trecho novo (descartada) | 0,787 | 0,78 | 1,4 s |

O ingest do kit v5.1 custava 7 pontos de Recall@3 neste domínio, e a V5 o usaria: os dois viraram opt-in
(`INGEST_SECTION_CUT=on`, `RAG_CONTEXT=on`). A diferença restante para o corpus da v4 (0,82 × 0,85) são 3 perguntas,
duas delas com regra de rodapé; está dentro do ruído de 50 perguntas. A grade inteira com os modelos padrão
(MiniLM, jina) ficou abaixo (0,51–0,75) e os rerankers de pool 20 levam 4–6 s por busca.

## Achado de operação

O limite de gasto da API acabou no 99º julgamento e o juiz perdia tudo: agora grava o parcial (`aborted_quota`) e
`--resume` julga só o que faltou (`evals/judge.py`, teste).

## Busca, 2ª rodada: gold por FATO (cópias do mesmo fato contam uma vez)

A régua anterior contava cada cópia da mesma informação como passagem a achar (a FAQ de taxas da Loja Virtual
está em duas páginas; a busca trazia uma e era punida pela outra), contra a própria regra do `Gold` ("a mesma FAQ
copiada em 3 páginas é 1 passagem"). `evals/essential_gold.py` passou a aceitar um grupo por fato (qualquer cópia
vale) e o consenso casa fatos por sobreposição. Dois rotuladores novos, às cegas, sobre o corpus re-ingerido pelo
kit v5.2: candidatos = top-10 do BM25 + top-10 do denso (média 17,6 por pergunta), sem id nem ordem.

| (corpus do kit v5.2, mesmas 50 perguntas) | Recall@3 | MRR | hit@3 | p95 |
|---|---:|---:|---:|---:|
| bm25 | 0,693 | 0,657 | 0,76 | 2 ms |
| denso e5 | 0,93 | 0,927 | 0,96 | 92 ms |
| **denso e5 + rerank bge (escolhido)** | **0,93** | **0,94** | 0,96 | 1,2 s |

Concordância entre os rotuladores: Jaccard 0,89, 34 de 50 idênticas (antes 0,81 e 31/50). Fatos por pergunta: 34
com 1, 14 com 2, 2 com 3.

Limites declarados: (1) os rotuladores são subagentes, não pessoas; (2) viés de pooling: um trecho essencial que
nem o BM25 nem o denso põem no top-10 não chega a ser candidato (é o método do TREC, e o rerank só reordena esse
top-10); (3) 50 perguntas. Rerank por LLM (Haiku) sobre o top-10 foi medido: 0,82 → 0,83 no gold anterior, com
+1 s por busca; não compensa (`ensaio/v52_fatos/rerank_llm_experimento.json`).
