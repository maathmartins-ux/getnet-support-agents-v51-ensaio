Olá! Segue a minha entrega do desafio.

Repositório: https://github.com/maathmartins-ux/getnet-support-agents-v51-ensaio
Como avaliar em 5 minutos: a seção 0 do README; as respostas reais dos cenários oficiais estão em docs/DEMO.md e a linha do tempo em docs/TIMESHEET.md.

Resultados medidos (todos gerados de evals/results/, no README):
- Oficiais resolvidas (sem humano + todo fato + fonte): 0.97 (referência 0.90)
- Oficiais resolvidas: pass^k (todas as rodadas): 0.90 (referência 0.90)
- Juiz: respostas oficiais úteis (helpful): 1.00 (referência 0.90)
- Juiz: respostas oficiais fundamentadas: 1.00 (referência 0.90)
- Memória ao vivo: pass@1: 0.98 (referência 0.85)
- Busca: Recall@3: 0.88 (referência 0.85)
- Busca: MRR: 0.84 (referência 0.80)

Onde ainda está abaixo da referência, ou não foi medido (as limitações, com o efeito e o que faltaria, estão na seção de limitações do README):
- nenhuma métrica

Procedência: o primeiro commit traz um kit próprio, que evoluiu a partir das correções das minhas entregas anteriores deste desafio. O que veio do kit, o que foi feito no relógio e como comparar pela primeira entrega estão em docs/PROCEDENCIA.md. Relógio: 819 min do commit de scaffold ao commit 70cdeba.

Obrigado!
