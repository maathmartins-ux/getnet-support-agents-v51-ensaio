# Modos de falha (eval ao vivo)

Gerado por `python -m evals.failure_modes` a partir de `evals/results/live_*.json`. Cada falha conta uma vez, pela primeira checagem que falhou. Para cada modo: o que fazer é decisão humana; o que foi feito fica no commit que cita o modo.

Fora da conta: `heldout` (80 execuções), `heldout_h3` (40 execuções), o conjunto cego: ler as falhas dele para corrigir o motor o contamina. A medida dele fica nos blocos ao vivo, do juiz e humano de `docs/RESULTS.md`.

13 falhas em 242 execuções (5.4%).

| modo | falhas | casos distintos | splits |
|---|---:|---:|---|
| `intent` | 9 | 8 | dependent (1), memory (5), partial (1), replan (2) |
| `facts` | 3 | 1 | official (3) |
| `completed` | 1 | 1 | dependent (1) |

## `intent`

Casos que mais falham: `memory-09` (2x), `dependent-07` (1x), `memory-08` (1x), `memory-07` (1x), `memory-16` (1x)

- exemplo `dependent-07`: “Teve venda recusada hoje? Como evito isso?”
- esperado: intent `troubleshoot`; obtido: `multi`; rota ['router', 'records', 'faq']; ferramentas ['get_transactions']
- números sem base: nenhum
- resposta: Não, hoje você não teve nenhuma venda recusada. A consulta de hoje voltou com 0 recusas e R$ 0,00. Sobre como evitar recusas, as fontes não trazem orientação. Os trechos tratam só de contestação e chargeback [sup-duvidas-69][sup-duvidas-67]. Se alguma recusa …

## `facts`

Casos que mais falham: `official-01` (3x)

- exemplo `official-01`: “What's the difference between the Get Clássica and the Get Smart?”
- esperado: intent `knowledge`; obtido: `knowledge`; rota ['router', 'faq']; ferramentas []
- números sem base: nenhum
- resposta: The Get Smart costs more and does more. It's R$ 129,90/month, against R$ 79,90/month for the Get Clássica [prod-ofertas-maquininha-11][prod-todas-as-maquininhas-04]. The Get Smart is a smart card machine that runs Android. It works as both a computer and a fi…

## `completed`

Casos que mais falham: `q-dep-02` (1x)

- exemplo `q-dep-02`: “Every card I swipe gets refused today, what is going on?”
- esperado: intent `troubleshoot`; obtido: `troubleshoot`; rota ['router', 'records']; ferramentas ['get_transactions', 'get_terminal_status']
- números sem base: nenhum
- resposta: Your records show no sales or declines today, approved or declined. So there are no decline codes to explain. - **Terminal T1988B (Get Clássica):** It is offline with no signal and has been offline for 5 hours. Its last contact was 2026-11-03 23:20. If you're…
