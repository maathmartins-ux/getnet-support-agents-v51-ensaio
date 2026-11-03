Olá! Segue a minha entrega do desafio.

Repositório: https://github.com/maathmartins-ux/getnet-support-agents-v51-ensaio
Como avaliar em 5 minutos: a seção 0 do README; as respostas reais dos cenários oficiais estão em docs/DEMO.md e a linha do tempo em docs/TIMESHEET.md.

Resultados medidos (todos gerados de evals/results/, no README):
- Oficiais resolvidas (sem humano + todo fato + fonte): 1.00 (referência 0.90)
- Oficiais resolvidas: pass^k (todas as rodadas): 1.00 (referência 0.90)
- Juiz: respostas oficiais úteis (helpful): 0.97 (referência 0.90)
- Juiz: respostas oficiais fundamentadas: 1.00 (referência 0.90)
- Oficiais: números com base na evidência: 100.0% (referência 95.0%)
- Oficiais: pass^k (todas as rodadas passam): 1.00 (referência 0.90)
- Busca: MRR: 0.82 (referência 0.80)
- Held-out cego: casos: 80 (referência 80)
- Juiz × humano: kappa: 1.00 (referência 0.80)
- Juiz validado contra humanos (1 = sim, regra fixada antes): 1 (referência 1)
- Busca: Recall@5 (o que o redator lê): 0.89 (sem meta: explica outro número)
- Held-out cego: intenção (diagnóstico): 86.2% (sem meta: explica outro número)
- Custo por turno resolvido sem humano (ao vivo): US$ 0.0334 (sem meta: explica outro número)
- Turnos resolvidos sem humano (ao vivo, todos os splits): 0.88 (sem meta: explica outro número)

Onde ainda está abaixo da referência, ou não foi medido:
- Memória ao vivo: pass@1: 0.67 (referência 0.85)
- Memória ao vivo: números com base: 93.9% (referência 95.0%)
- Busca: Recall@3: 0.84 (referência 0.85)
- Held-out cego: ponta a ponta (humano passa): não medido (referência 0.80)
- Rotuladores humanos independentes: não medido (referência 2)

Procedência: o primeiro commit traz um kit próprio, que evoluiu a partir das correções das minhas entregas anteriores deste desafio. O que veio do kit, o que foi feito no relógio e como comparar pela primeira entrega estão em docs/PROCEDENCIA.md. Relógio: 41 min do primeiro ao último commit (tags clock-start/clock-end).

Obrigado!
