# Roteiro do vídeo (até 5 min)

Cada cena mostra algo que roda; nenhum número é dito de cabeça: os números lidos na tela vêm do README §0
(gerado por `scripts/fill_readme.py`).

| Tempo | Cena | O que mostrar | Arquivo |
|---|---|---|---|
| 0:00–0:30 | Problema | o lojista Getnet pergunta sobre a própria venda e sobre taxa/produto; o que o enunciado pede | `docs/SPEC.md` |
| 0:30–1:15 | Arquitetura | diagrama de agentes: router reescreve, supervisor coordena, especialistas sem estado | `docs/ARCHITECTURE.md` §1 |
| 1:15–2:00 | Pergunta com fonte | 1º caso oficial (quickstart do README); resposta cita a página e mostra o custo | `README.md` §1, `src/app/rag.py` |
| 2:00–2:45 | Seguimento e memória | "e a outra?" vira pergunta autônoma; o fato vem do livro de fatos | `src/app/router.py`, `src/app/memory.py` |
| 2:45–3:30 | Estorno com quatro olhos | lojista pede estorno; confirmação; operador aprova em `/operator`; executa uma vez | `src/app/actions.py`, ADR 0009 |
| 3:30–4:10 | Humano quando não resolve | pergunta sem fonte abre caso; operador responde; o plano continua no turno | `src/app/hitl_sync.py`, `src/app/resume.py` |
| 4:10–4:40 | Qualidade e operação | placar do README §0 lido na tela; `/metrics` e um alerta do runbook | `evals/results/`, `docs/OBSERVABILITY.md` |
| 4:40–5:00 | Limites e próximo passo | o que ficou de fora e o gatilho para voltar | ADR 0008, `docs/PILOT.md` |
