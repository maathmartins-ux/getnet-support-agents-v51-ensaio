# Ensaio do kit v5.4 no domínio da V5 (03/11/2026)

Mesma bancada do [ENSAIO_V53.md](ENSAIO_V53.md) (`/home/user/ens55`). Mudanças da v5.4, pela metodologia dos
trabalhos nota 10 (Skywalker) e 9,5 (nelsondell) — ideias, sem código deles:

- **Busca (nelsondell):** placar = caminho do agente com o rerank, Recall@5 (o que o redator lê), MRR@10, rank do 1º
  gold por pergunta e recorte por origem; híbrido BM25+denso com o BM25 só no idioma do corpus; palavras do cliente
  como 1ª busca também sem o router LLM. Escolha do buscador por medida: dense+cross (empate com o híbrido, e é o
  validado ao vivo).
- **Memória (Skywalker e nelsondell):** especialistas sem estado recebem a pergunta reescrita pelo router + livro de
  fatos; regra de demonstrativos no router ("a outra" = a entidade da última resposta que não foi tratada).

## Busca (gold da V5, 38 perguntas, offline, sem API)

| Buscador | Recall@3 | Recall@5 | MRR |
|---|---|---|---|
| dense, sem rerank (o placar publicado até a v5.3) | 0,842 | 0,868 | 0,737 |
| dense+cross, buscador direto | 0,868 | 0,921 | 0,800 |
| hybrid+cross, buscador direto | 0,895 | 0,921 | 0,831 |
| **caminho do agente, dense+cross (padrão v5.4)** | **0,895** | **0,947** | **0,829** |
| caminho do agente, hybrid+cross com filtro de idioma | 0,895 | 0,921 | 0,821 |

## Bateria integral ao vivo (r4, com hybrid+cross SEM o filtro de idioma e especialistas sem estado)

**Abortou por limite da conta da API** em heldout (72/80) e memory (48/96): `aborted_quota`, juiz sem esses dois.
Os outros 9 splits completaram. Gasto: conversa US$ 8,23 + juiz US$ 3,33.

| Medida | r2/r3 (v5.3) | r4 (v5.4) |
|---|---|---|
| Juiz (9 splits): fundamentadas / úteis | 95,5–97,2% / 96,6–96,9% | 97,7% / 97,7% |
| Oficiais resolvidas | 96,7% | 90% (official-04 nas 3: o BM25 sobre a pergunta em inglês tirou o trecho do top-5 → filtro de idioma; padrão voltou a dense+cross) |
| Memória (n=48, parcial): rota pelo resultado / pass@1 / tools | 87,5–91% / 84,4–87,5% / 87–90% | 96% / 87,5% / 94% |
| Dependent / approval (sem histórico cru nos especialistas) | 95% / 100% | 100% / 100% |
| Replan: humano quando não resolve | 85–90% | 80% (4 casos; 2 já falhavam antes) |

Pré-voo completo num clone limpo do ramo `kit-v5.4.0`: `PRÉ-VOO OK`, 899 testes, ruff limpo.

## Estimativa por critério (leitura do maestro)

| Critério (peso) | v5.3 central / pior | v5.4 central / pior | Por quê |
|---|---|---|---|
| RAG (10) | 9,3 / 9,1 | 9,5 / 9,3 | placar pelo método do nelsondell: Recall@5 0,947, MRR 0,829 |
| Memória (8) | 9,3 / 9,0 | 9,4 / 9,1 | especialistas sem estado e demonstrativos; medida ao vivo só parcial (n=48) |
| Demais critérios | iguais | iguais | — |
| **Ponderada** | **9,51 / 9,29** | **9,54 / 9,32** | |

O pior caso abaixo de 9,5 é sobretudo incerteza que só se mede gastando API (memória inteira, concordância humana
com o questionário novo, Docker/escala).

## Depois do passo 1 (Skywalker e nelsondell no que eram melhores; sem API)

Clone limpo do ramo `kit-v5.4.0` (7093e9d): `check.py --docker --scale` **CHECK VERDE** (16 etapas: imagem, contêiner
sem rede, MCP com JWT, 2 réplicas com queda) e `preflight.py` **PRÉ-VOO OK** (930 testes com o domínio do desafio).

| Critério (peso) | antes do passo 1 central / pior | depois central / pior | O que mudou |
|---|---|---|---|
| Orquestração (15) | 9,5 / 9,3 | 9,6 / 9,4 | árvore de passos no DEMO; humano dentro do turno |
| Ferramentas (10) | 9,6 / 9,4 | 9,7 / 9,5 | escrita com antes/depois |
| Segurança (13) | 9,5 / 9,3 | 9,6 / 9,4 | login com senha no quickstart |
| Supervisão humana (7) | 9,7 / 9,5 | 9,8 / 9,6 | consulta síncrona com espera curta |
| Avaliação (14) | 9,7 / 9,4 | 9,8 / 9,5 | regra do juiz fixada antes; "desde a última avaliação"; 👎 → candidato |
| Observabilidade (6) | 9,4 / 9,2 | 9,5 / 9,3 | versão das instruções por resposta |
| Produção (5) | 9,2 / 9,0 | 9,4 / 9,2 | Docker e réplicas conferidos |
| Julgamento (4) | 9,7 / 9,5 | 9,8 / 9,6 | motor sem comentários de bastidor |
| Negócio (8), RAG (10), Memória (8) | 9,6/9,4 · 9,5/9,3 · 9,4/9,1 | iguais | só sobem com medida ao vivo |
| **Ponderada** | **9,54 / 9,32** | **9,62 / 9,40** | |

O que falta para o pior caso chegar a 9,5: medir a memória completa e o held-out com o juiz (~US$ 9 de API) e o teste
do questionário com as duas pessoas (concordância real). Isso tira a incerteza de Memória (9,1), RAG (9,3) e Negócio
(9,4), que hoje puxam o pior caso.

## Bateria integral no kit final (r5, 03/11/2026, kit-v5.4.0 6bc5886, API recarregada)

11/11 splits completos, 0 `budget_exhausted`; conversa US$ 10,98 + juiz US$ 6,46.

| Medida | V5 | r5 |
|---|---|---|
| Oficiais resolvidas / pass^3 | 80% / 0,60 | 93,3% / 0,90 (official-04 instável, 1 de 3) |
| Juiz 352: fundamentadas / úteis | — / 0,733 (oficiais) | 96,9% / 96,9% (oficiais úteis 100%) |
| Memória pass@1 pelo resultado (rótulo) / fatos | 0,72 / 90,6% | 90,6% (84,4%) / 96,9% |
| Held-out: especialista certo / handoff | 67,5% / — | 100% / 96% |
| Replan: humano quando não resolve | — | 85% |
| Busca no caminho do agente: Recall@3 / Recall@5 / MRR@3 | 0,842 / — / 0,715 | 0,868 / 0,921 / 0,789 |
| Separação com × sem fonte (38 × 17) | — | AUC 0,783, gap −0,147 (não separa: a recusa fica com o LLM) |
| Juiz validado (regra fixada antes) | — | não: TNR 0,75 < 0,8 (roda como regressão) |

Estimativa: **9,63 central, 9,42 pior caso** (Memória 9,6/9,4 com o pass@1 de 90,6%; RAG 9,45/9,3 com MRR 0,789 e a
separação fraca). Falta a concordância humana com o questionário novo (página publicada para o teste).
