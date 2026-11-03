# Piloto — shadow → assistido → autônomo, por intenção

Nenhum número abaixo é escrito à mão: os portões citam a métrica e o arquivo de onde ela sai
(`evals/results/*.json`, `/metrics`). O que é SUPOSIÇÃO está marcado como tal.

## Fases

| Fase | O que o sistema faz | Quem responde ao lojista | Sai da fase quando |
|---|---|---|---|
| **Shadow** (2 semanas) | roda em paralelo ao atendimento humano; a resposta é gravada, não enviada | humano | portões da intenção verdes por 7 dias seguidos na amostra rotulada |
| **Assistido** | a resposta vira rascunho para o operador, que aprova, edita ou descarta (a edição é medida) | humano, com rascunho | taxa de rascunho aprovado sem edição ≥ portão; zero incidente de vazamento |
| **Autônomo** | responde direto; escalonamento humano (`cases.py`) quando o Knowledge fica `insufficient` ou a tool falha | sistema, com humano no caso aberto | — (rollback abaixo) |

## Ordem por intenção (do menor para o maior risco)

| Intenção | Risco | Portão para avançar (métrica → arquivo) |
|---|---|---|
| `general` (clima, câmbio) | baixo: dado de API oficial com data | número com base = 100% (`numbers`, `evals/results/live_official.json`) |
| `knowledge` | médio: resposta errada sobre taxa/regra | fundamentada pelo juiz ≥ 0,90 (`evals/results/judge.json`); Recall@3 ≥ 0,85 (`evals/results/latest.json`, campo `retrieval`) |
| `support` (leitura) | médio: dado do próprio cliente | isolamento entre clientes 100% (`isolation`); `tools` corretas ≥ 0,95 |
| `troubleshoot` | médio | split `dependent` `completed_acc` ≥ 0,90 |
| escrita (`request_receivables_advance`, `open_support_ticket`) | **alto: dinheiro** | fica em assistido: confirmação do lojista + quatro olhos (ADR 0009); nunca autônomo no piloto |

## Rollback
- Gatilho automático: alerta de `ops/alerts.yml` (taxa de escalonamento, erro de LLM, custo por turno) por 15 min →
  a intenção volta uma fase (flag por intenção; o roteamento continua igual).
- Gatilho manual: qualquer resposta com dado de outro cliente → todas as intenções `support` voltam a shadow.

## Custo × benefício

| Item | MEDIDO ou SUPOSIÇÃO | Fonte |
|---|---|---|
| custo de LLM por turno resolvido, por intenção | MEDIDO | `evals/results/live_*.json` (`spent_usd`), `/metrics` |
| latência por agente | MEDIDO | `/metrics`, `docs/OBSERVABILITY.md` |
| custo de um atendimento humano | SUPOSIÇÃO (a Getnet fornece no piloto) | — |
| volume por intenção | SUPOSIÇÃO até o shadow medir | shadow |
| ganho = volume × (custo humano − custo do turno) × taxa resolvida sem humano | SUPOSIÇÃO até o assistido | — |
