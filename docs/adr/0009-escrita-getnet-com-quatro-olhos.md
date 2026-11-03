# ADR 0009 — Estorno e cancelamento da Getnet: tool com dono verificado e quatro olhos acima do limite

Status: aceito no commit da spec do desafio Getnet (03/11/2026).

**Contexto.** No suporte ao lojista Getnet as escritas (cancelar uma venda, pedir estorno) mexem em dinheiro do
lojista e do portador. Um agente que executa a escrita só porque o LLM decidiu é o risco mais caro do sistema.

**Decisão.** As escritas são tools do domínio (`src/app/domain/challenge/tools.py`: `_cancel`, `_refund`), com
schema estrito (`record_id` de 4 dígitos) e dono verificado (`_lookup` só devolve registro do `user_id` do token).
O LLM propõe; o código dispõe: confirmação explícita do lojista sempre, e acima do limite de valor ou com sinal de
risco (`src/app/risk.py`) a aprovação de um operador (`src/app/actions.py`), com claim atômico que executa uma vez
só, mesmo entre réplicas, e TTL na pendência.

**Alternativa descartada.** Deixar o especialista `records` executar direto após o "sim" do lojista, sem segundo
olho. Mais rápido e sem fila, mas um "sim" ambíguo ou injetado vira estorno real sem ninguém ver; o custo do erro
(dinheiro movido) é muito maior que o custo da espera.

**Consequências.** Escritas de risco alto passam pela fila do operador (contadores `approvals_requested_total`,
`approvals_decided_total`, `actions_expired_total` em [OBSERVABILITY.md](../OBSERVABILITY.md)); nenhuma escrita é
proposta enquanto a conversa tem caso aberto.
