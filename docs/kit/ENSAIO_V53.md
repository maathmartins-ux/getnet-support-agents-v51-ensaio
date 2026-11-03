# Ensaio do kit v5.3 no domínio da V5 (03/11/2026)

Motor do kit v5.3 por cima do repositório entregue da V5 (domínio, corpus, casos e prompts da V5; `data/retriever.json`
da V5 fora, então vale o buscador padrão do kit). Bateria integral ao vivo: 11 splits num processo, official e memory
repeat 3, o resto repeat 1; juiz Opus em todas as 352 respostas, com 4 canários e 48 pares de calibração.
Pasta do ensaio: `/home/user/ens55` (fora do repositório). Resultados: `evals/results/r2/` (rodada 2, 4 workers) e
`evals/results/` (rodada 3, 8 workers).

## Placar (rodada 2 · rodada 3)

| Medida | V5 entregue | r2 | r3 |
|---|---|---|---|
| Oficiais resolvidas (sem humano, fatos de referência, fonte) | 80% | 96,7% | 96,7% |
| Oficiais pass^3 | 0,60 | 0,90 | 0,90 |
| Juiz: fundamentadas (352) | — | 95,5% | 97,2% |
| Juiz: úteis (352) | 0,733 (oficiais) | 96,9% | 96,6% |
| Juiz: oficiais úteis | 0,733 | 97% | 100% |
| Held-out: especialista certo | 67,5% (rótulo) | 99% | 98% |
| Memória pass@1 pelo resultado (pelo rótulo) | 0,72 | 87,5% (84,4%) | 84,4% (82,3%) |
| Memória: fatos esperados | 90,6% | 95,8% | 92,7% |
| Replan: humano quando não resolve | 85% | 90% | 85% |
| Approval | 100% | 4/6 → 6/6 depois da correção | 6/6 |
| Splits completos | vários abortados | 11/11 | 11/11 |
| Conversa / juiz (US$) | — | 10,62 / 6,42 | 11,12 / 6,47 |
| Duração da bateria com o juiz | — | 16 min (4 workers) | 12,8 min (8 workers) |
| `budget_exhausted` (timeout por carga) | 5 (44 conversas simultâneas) | 0 | 0 |

## O que o ensaio achou e o kit corrigiu (na ordem)

1. **official-04 (Pix):** a pergunta original achava o fato em 1º; as consultas do router em português, não → as
   palavras do cliente são sempre a 1ª busca.
2. **Prompts do domínio substituíam os do motor:** as três respostas (ok/partial/insufficient), o standalone e as
   search_queries nem rodavam → contrato do motor no fim do prompt do domínio (`prompts/contract/`).
3. **Teto curto:** official abortou em 24/30 e o juiz não rodou → aviso de teto antes de gastar; padrão US$ 24.
4. **Juiz por split com cota:** 9 de 11 splits com 0 vereditos → saldo único (`JudgeWallet`); recusa do juiz num caso
   malicioso derrubava a rodada → anotada (`judge_refused`); 352 vereditos em fila = 41 min → 8 em paralelo.
5. **44 conversas simultâneas** estouraram o timeout do faq → `LIVE_MAX_CONCURRENT=12`.
6. **"amanhã, [valor não confirmado] de novembro"** → dia do calendário junto do mês não vira tarja.
7. **Split real 82% fundamentado:** 5 de 7 frases sem base eram regra do próprio sistema → veredito humano e formato
   dos ids no cartão de capacidades.
8. **Escalada:** a 1ª versão (falta de fonte/dado vira oferta) derrubou o replan para 30% → regra final: oferta só
   para resposta parcial ou quando outro especialista já respondeu; não resolver nada = humano, garantido em código.
9. **Approval 4/6:** o records parava para perguntar "posso propor?" → pedido explícito cria a proposta no turno.
10. **Memória (frente M):** rota medida pelo resultado; records usa o livro de fatos no seguimento (q-memory-08/09).

## Estimativa por critério (leitura do maestro, não nota do avaliador)

| Critério (peso) | Central | Pior caso | Por quê |
|---|---|---|---|
| Business & Challenge Fit (8) | 9,6 | 9,4 | oficiais 96,7% resolvidas; humano só quando não resolve |
| Agentic Reasoning & Orchestration (15) | 9,5 | 9,3 | supervisor + código que dispõe; replan 85–90% |
| Context, Knowledge & RAG (10) | 9,3 | 9,1 | Recall@3 0,842 e MRR 0,72 abaixo da meta 0,85; juiz 95–97% fundamentado |
| Tool & Action Engineering (10) | 9,6 | 9,4 | approval 6/6, dependent 95–100%; tools da memória 87–90% |
| Security & Identity (13) | 9,5 | 9,3 | guardrail 100%; hard 89–93% |
| Memory, State & Resilience (8) | 9,3 | 9,0 | pass@1 84–87,5% pelo resultado; pass^3 0,75–0,78 |
| Human Oversight & Risk (7) | 9,7 | 9,5 | regra de escalada clara, oferta, retomada do plano |
| Evaluation & Quality Engineering (14) | 9,7 | 9,4 | bateria integral, canários 4/4, calibração 0,79; concordância humana ainda não medida com o questionário novo |
| Observability, Reliability & Cost (6) | 9,4 | 9,2 | custo por split, p50/p95; p50 oficial 11 s com 8 workers |
| Production Engineering (5) | 9,2 | 9,0 | Docker/escala não reconferidos neste ensaio |
| Engineering Judgment (4) | 9,7 | 9,5 | cortes declarados, números ruins publicados |
| **Ponderada** | **9,51** | **9,29** | |

**Veredito pela regra do dono ("só a V5.1 se a estimativa mínima for 9,5"): ainda NÃO.** O central bate 9,5; o pior
caso fica em 9,3. O que puxa o pior caso para baixo: RAG (Recall@3 0,842/MRR 0,72), memória (84–87,5%) e a
concordância humana não medida com o questionário novo.
