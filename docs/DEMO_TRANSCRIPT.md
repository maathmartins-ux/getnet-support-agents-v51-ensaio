# Transcrição multi-turno (memória, ação com antes/depois, humano)

Gerada por `scripts/demo_md.py --transcript evals/demo_transcript.jsonl` no commit `21258d7` em 03/11/2026 20:30 UTC, rodando o `POST /chat` no processo (LLM: `anthropic`). Nada escrito à mão.

### Turno 1

**Cliente:** Quando cai o dinheiro das vendas de ontem?

**Intenção:** support · **rota:** router → records

**Passos:**

1. **records** · ok · 3516 ms
   - `get_settlements` {"period": "yesterday"} → ok · `{"ok": true, "data": {"period": "yesterday", "items": [{"method": "pix", "method_pt": "Pix", "method_en": "Pix", "count": 1, "total": 64.0,…`

**Resposta:**

> As vendas aprovadas de ontem (02/11/2026) somam R$ 814,40. Cada forma de pagamento cai em uma data:
>
> - **Pix:** R$ 64,00 (1 venda). Já foi pago ontem.
> - **Débito:** R$ 200,50 (2 vendas). O depósito é hoje (03/11/2026) e consta como pago.
> - **Crédito:** R$ 549,90 (2 vendas). O depósito está agendado para 02/12/2026, daqui a 29 dias.
>
> A regra da agenda é: Pix D+0, débito D+1 dia útil e crédito D+30 (próximo dia útil).

### Turno 2

**Cliente:** E as vendas recusadas, o que aconteceu?

**Intenção:** support · **rota:** router → records → faq

**Passos:**

1. **records** · ok · 3154 ms
   - `get_transactions` {"period": "yesterday", "status": "declined"} → ok · `{"ok": true, "data": {"items": [{"transaction_id": "TX1007", "method": "credito", "status": "recusada", "amount": 210.0, "decline_code": "5…`
2. **faq** · partial · motivo `partial_coverage` · 12022 ms

**Resposta:**

> Ontem houve 2 vendas recusadas, somando R$ 285,00:
>
> - **TX1007**: crédito, R$ 210,00, terminal T1988A. Código 51, saldo ou limite insuficiente no cartão do cliente. Peça outro cartão ou outra forma de pagamento.
> - **TX1008**: débito, R$ 75,00, terminal T1988B. Código 05, transação não autorizada pelo banco emissor (recusa genérica). O portador deve contatar o banco emissor ou tentar outro cartão.
>
> Esses dados vêm da consulta às suas transações. Os materiais de apoio não trouxeram orientação adicional sobre recusas, então não tenho mais detalhes além do significado dos códigos.
>
> Se quiser, posso encaminhar para um atendente humano.

### Turno 3

**Cliente:** Quero contestar a cobrança de aluguel da maquininha T1988B deste mês. Pode passar para um atendente analisar?

*(operador simulado responde durante a espera: "Verifiquei o contrato: o aluguel da T1988B deste mês foi cobrado por engano e o estorno de R$ 79,90 entra na próxima fatura.")*

**Intenção:** human_request · **rota:** router → escalation → human

**Passos:**

1. **escalation** · ok · 4.4 ms · caso T-4f32f123 · operador respondeu durante a espera · operador `admin`
2. **human** · ok · operador `admin`

**Resposta:**

> Consultei um atendente humano (protocolo T-4f32f123), que respondeu agora.
>
> Resposta do atendente: Verifiquei o contrato: o aluguel da T1988B deste mês foi cobrado por engano e o estorno de R$ 79,90 entra na próxima fatura.

### Turno 4

**Cliente:** A maquininha T1988B continua sem sinal. Pode abrir um chamado?

**Intenção:** troubleshoot · **rota:** router → records → faq

**Passos:**

1. **records** · ok · 3654 ms · ação proposta `A-4039da90`
   - `get_terminal_status` {"terminal_id": "T1988B"} → ok · `{"ok": true, "data": {"items": [{"terminal_id": "T1988B", "model": "Get Clássica", "connection": "chip", "status": "offline", "signal": "se…`
   - `open_support_ticket` {"terminal_id": "T1988B", "reason": "sem_sinal"} → proposta (aguarda a confirmação do cliente) · `{"ok": false, "needs_confirmation": true, "action_id": "A-4039da90", "risk": "normal", "args": {"terminal_id": "T1988B", "reason": "sem_sin…`
2. **faq** · partial · motivo `partial_coverage` · 7024 ms

**Resposta:**

> A T1988B (Get Clássica) está offline e sem sinal. O último contato foi em 03/11/2026 às 15:31, e ela está offline há 5 horas.
>
> **Chamado:** propus um chamado técnico para a T1988B com o motivo "sem sinal" (ação A-4039da90). Ele ainda não foi aberto e está aguardando sua confirmação. A proposta expira em 15 minutos. Você confirma?
>
> **Enquanto isso, confira o chip** [sup-duvidas-06]:
> - Desligue a máquina e abra a tampa de trás. Insira o chip no local indicado, SIM1 ou SIM2, com a parte metálica voltada para baixo.
> - Feche a tampa, ligue a máquina e aguarde a conexão de rede de dados.
> - Quando aparecer rede conectada (2G ou 3G), a máquina está pronta para uso.
> - Faça um teste de comunicação para verificar a conectividade do chip.
>
> Há manuais por tipo de máquina, como "Portátil com Chip + Wi-Fi" e "Chip de dados + Wi-Fi". Escolha o que corresponde ao seu modelo [sup-manual-maquinas-01].
>
> As fontes não trazem os passos do teste de comunicação nem como configurar o Wi-Fi. Para o Wi-Fi, use o manual do seu modelo. Se quiser, posso encaminhar você a um atendente humano.

### Cliente confirma a ação `A-4039da90`

| campo | antes | depois |
|---|---|---|
| ticket | null | **CH-T1988B-20261103** |
| terminal_id | T1988B | (igual) |

