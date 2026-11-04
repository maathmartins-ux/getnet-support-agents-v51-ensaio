# ADR 0008 — Considerado e não feito (com o número que decidiu)

Status: registrado no kit v5.4 (03/11/2026).

**Contexto.** Cada item abaixo foi medido ou pesado e ficou de fora. Registrar o que NÃO entrou evita refazer a
medida no relógio e responde "por que não X?" com número.

| Considerado | Medido | Por que não |
|---|---|---|
| Busca híbrida BM25 + denso como padrão | caminho do agente, Recall@3 / Recall@5 / MRR: híbrido 10/600 0,895 / 0,895 / 0,794 contra dense+cross 0,868 / 0,921 / 0,789; sem filtro de idioma, o BM25 sobre a pergunta em inglês tirou o trecho do official-04 do top-5 nas 3 rodadas (oficiais 96,7% → 90%) | perde no Recall@5, o que o redator lê; o dense+cross é o validado ao vivo. Fica disponível (`RETRIEVER=hybrid`, BM25 só no idioma do corpus, `rag.lexical_fits`) |
| Rerank sobre 20 candidatos (pool 20) | 0,842 / 0,921 / 0,776, p95 6,1 s (× 2,8 s) | o dobro da latência sem ganho no top-5 |
| Trecho de 1000 caracteres no rerank | 0,842 / 0,868 / 0,759 | piora as três medidas |
| Híbrido com pool 20 e 1000 caracteres | 0,842 / 0,868 / 0,816, p95 7,0 s | MRR um pouco maior, Recall@5 menor e latência 2,5× |
| Juiz de outra família de modelo | — (não medido) | o juiz foi calibrado só contra o gabarito escrito a partir da SPEC; contra pessoas, está "não validado" pela regra fixada antes de medir (bloco humano de `docs/RESULTS.md`, gerado) e conta só como regressão; a troca existe (`JUDGE_PROVIDER=openai_compat`), mas exige outra chave e outra calibração |
| Grade completa do buscador no relógio (`--choose-retriever` sem `--fast`) | V5: com 8 subagentes na mesma CPU, p95 do rerank 2,9–3,5 s × 1,1–1,25 s com a máquina parada; foi o caminho crítico | latência só se mede com a máquina parada: o pacote vem do kit, medido antes do relógio (ADR 0004). Neste ensaio rodou só o `--choose-retriever --fast --apply` (as configurações finalistas), fora do relógio, que gravou a ordem do denso e o portão pela nota do cross em `data/retriever.json` (emenda do ADR 0004) |

**Decisão.** Padrão do kit mantido: denso (e5-large) + cross-encoder (bge-reranker-v2-m3), top-10, 600 caracteres;
neste domínio vale a escolha de `data/retriever.json` (ordem do denso, nota do cross só no portão sem fonte). Juiz
do kit com a regra de validação.

**Consequências.** Nenhuma variante ganha no top-5 sem custar latência. O juiz da mesma família fica declarado como
limite (README §3). Calibrado só contra o gabarito da SPEC e "não validado" contra pessoas pela regra fixada antes
(bloco humano de `docs/RESULTS.md`), ele conta só como regressão, não como garantia da medida.

**Números.** Variantes medidas no caminho do agente, gold da entrega anterior (38 perguntas), commit `29222e0`:
pool 20 0,842/0,921/0,776 (6,1 s); 1000 caracteres 0,842/0,868/0,759; híbrido 10/600 0,895/0,895/0,794;
híbrido 20/1000 0,842/0,868/0,816 (7,0 s). Prova do método:
`tests/test_v54_retrieval_method.py::test_published_retrieval_is_the_agent_path_with_the_base_beside_it`,
`tests/test_v54_retrieval_method.py::test_bm25_only_fuses_when_the_query_is_in_the_corpus_language`.
