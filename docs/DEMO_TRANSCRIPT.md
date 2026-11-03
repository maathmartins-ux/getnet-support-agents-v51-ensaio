# Transcrição multi-turno (memória, ação com antes/depois, humano)

Gerada por `scripts/demo_md.py --transcript evals/demo_transcript.jsonl` no commit `4bdbe71` em 03/11/2026 19:34 UTC, rodando o `POST /chat` no processo (LLM: `anthropic`). Nada escrito à mão.

### Turno 1

**Cliente:** Quando cai o dinheiro das vendas de ontem?

**Intenção:** support · **rota:** router → records

**Passos:**

1. **records** · ok · 3001 ms
   - `get_settlements` {"period": "yesterday"} → ok · `{"ok": true, "data": {"period": "yesterday", "items": [{"method": "pix", "method_pt": "Pix", "method_en": "Pix", "count": 1, "total": 64.0,…`

**Resposta:**

> As vendas de ontem (02/11) somam R$ 814,40, em 5 vendas. Os depósitos caem assim:
>
> - **Pix:** 1 venda, R$ 64,00. Já foi depositado ontem (02/11).
> - **Débito:** 2 vendas, R$ 200,50. O depósito é hoje (03/11).
> - **Crédito:** 2 vendas, R$ 549,90. O depósito está agendado para 02/12.

### Turno 2

**Cliente:** E as vendas recusadas, o que aconteceu?

**Intenção:** support · **rota:** router → records → faq

**Passos:**

1. **records** · ok · 3179 ms
   - `get_transactions` {"period": "yesterday", "status": "declined"} → ok · `{"ok": true, "data": {"items": [{"transaction_id": "TX1007", "method": "credito", "status": "recusada", "amount": 210.0, "decline_code": "5…`
2. **faq** · insufficient · motivo `not_in_sources` · 26341 ms

**Resposta:**

> Ontem houve 2 vendas recusadas, num total de R$ 285,00:
>
> - **TX1007** (crédito, terminal T1988A), R$ 210,00. Código 51: saldo ou limite insuficiente no cartão. Peça outro cartão ou outra forma de pagamento.
> - **TX1008** (débito, terminal T1988B), R$ 75,00. Código 05: transação não autorizada pelo banco emissor, motivo genérico. O portador deve contatar o banco emissor ou tentar outro cartão.
>
> Como as vendas foram recusadas, o valor não entra na agenda de depósitos. A base de conhecimento não trouxe orientação adicional sobre recusas. Se quiser contestar algum caso, posso encaminhar para um atendente humano. Esse tipo de decisão é de um atendente, .

### Turno 3

**Cliente:** Quero contestar a cobrança de aluguel da maquininha T1988B deste mês. Pode passar para um atendente analisar?

*(operador simulado responde durante a espera: "Verifiquei o contrato: o aluguel da T1988B deste mês foi cobrado por engano e o estorno de R$ 79,90 entra na próxima fatura.")*

**Intenção:** human_request · **rota:** router → escalation → human

**Passos:**

1. **escalation** · ok · 6.2 ms · caso T-833a23b0 · operador respondeu durante a espera · operador `admin`
2. **human** · ok · operador `admin`

**Resposta:**

> Consultei um atendente humano (protocolo T-833a23b0), que respondeu agora.
>
> Resposta do atendente: Verifiquei o contrato: o aluguel da T1988B deste mês foi cobrado por engano e o estorno de R$ 79,90 entra na próxima fatura.

### Turno 4

**Cliente:** A maquininha T1988B continua sem sinal. Pode abrir um chamado?

**Intenção:** troubleshoot · **rota:** router → records → faq

**Passos:**

1. **records** · ok · 3356 ms · ação proposta `A-bb72ec59`
   - `get_terminal_status` {"terminal_id": "T1988B"} → ok · `{"ok": true, "data": {"items": [{"terminal_id": "T1988B", "model": "Get Clássica", "connection": "chip", "status": "offline", "signal": "se…`
   - `open_support_ticket` {"terminal_id": "T1988B", "reason": "sem_sinal"} → proposta (aguarda a confirmação do cliente) · `{"ok": false, "needs_confirmation": true, "action_id": "A-bb72ec59", "risk": "normal", "args": {"terminal_id": "T1988B", "reason": "sem_sin…`
2. **faq** · partial · motivo `partial_coverage` · 8230 ms

**Resposta:**

> Deixei a abertura do chamado técnico da T1988B proposta (ação A-bb72ec59). Ela está aguardando a sua confirmação e ainda não foi executada. Para abrir, confirme a ação. Pelo, uma proposta não confirmada expira em 15 minutos.
>
> A T1988B (Get Clássica, chip) está offline e sem sinal. O último contato foi em 03/11 às 14:35, há 5 horas.
>
> Enquanto isso, confira o chip [sup-duvidas-06]:
> - Com a máquina desligada, abra a tampa na parte de trás.
> - Insira o chip no local indicado, SIM1 ou SIM2, com a parte metálica voltada para baixo.
> - Feche a tampa, ligue a máquina e aguarde a conexão de rede de dados.
> - Quando aparecer a indicação de rede conectada (2G ou 3G), a máquina está pronta. Depois, faça um teste de comunicação.
>
> As fontes não trazem os passos do teste de comunicação, a configuração de Wi-Fi nem o que fazer se o sinal não voltar. Se quiser, posso encaminhar você a um atendente humano.

### Cliente confirma a ação `A-bb72ec59`

| campo | antes | depois |
|---|---|---|
| ticket | null | **CH-T1988B-20261103** |
| terminal_id | T1988B | (igual) |

