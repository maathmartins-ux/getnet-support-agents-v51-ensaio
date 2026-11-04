# Transcrição multi-turno (memória, ação com antes/depois, humano)

Gerada por `scripts/demo_md.py --transcript evals/demo_transcript.jsonl` no commit `c5a47f7` em 04/11/2026 07:41 UTC, rodando o `POST /chat` no processo (LLM: `anthropic`). Nada escrito à mão. Quem responde o caso é a operadora simulada `operadora_demo`, com chave pessoal gerada nesta execução (o `OPERATOR_KEYS` do processo guarda só o sha256 dela), pelo mesmo endpoint do console.

Em cada passo, **decidido por** diz quem pôs o agente no turno: o supervisor LLM (tool call); o plano do router (o router LLM, ou a regra que o substitui: seguimento herdado, guarda da própria empresa, queda do LLM), quando o supervisor LLM não foi consultado (rodado pelo atalho de 1 passo ou pelo motor de tabela); o código, com a regra entre parênteses (`supervisor.CODE_WHY`); ou a operadora que respondeu o caso. "não registrado" = passo gravado sem o campo `decided_by`.

### Turno 1

**Cliente:** Quando cai o dinheiro das vendas de ontem?

**Intenção:** support · **rota:** router → records

**Passos:**

1. **records** · ok · 3504 ms · decidido por: supervisor LLM (tool call)
   - `get_settlements` {"period": "yesterday"} → ok · `{"ok": true, "data": {"period": "yesterday", "items": [{"method": "pix", "method_pt": "Pix", "method_en": "Pix", "count": 1, "total": 64.0,…`

**Resposta:**

> As vendas aprovadas de ontem (03/11/2026) somam R$ 814,40, em 5 vendas. Cada forma de pagamento cai em uma data:
>
> - **Pix:** 1 venda, R$ 64,00. Já foi pago ontem (03/11/2026).
> - **Débito:** 2 vendas, R$ 200,50. Foi pago hoje (04/11/2026).
> - **Crédito:** 2 vendas, R$ 549,90. Está agendado para 03/12/2026, daqui a 29 dias.
>
> A regra da agenda é Pix D+0, débito D+1 dia útil e crédito D+30 (próximo dia útil).

### Turno 2

**Cliente:** E as vendas recusadas, o que aconteceu?

**Intenção:** support · **rota:** router → records → faq

**Passos:**

1. **records** · ok · 3214 ms · decidido por: supervisor LLM (tool call)
   - `get_transactions` {"period": "yesterday", "status": "declined"} → ok · `{"ok": true, "data": {"items": [{"transaction_id": "TX1007", "method": "credito", "status": "recusada", "amount": 210.0, "decline_code": "5…`
2. **faq** · insufficient · motivo `not_in_sources` · 9988 ms · decidido por: supervisor LLM (tool call)

**Resposta:**

> Ontem (03/11/2026) houve 2 vendas recusadas, somando R$ 285,00:
>
> - **TX1007**: crédito, R$ 210,00, terminal T1988A. Código 51: saldo ou limite insuficiente no cartão do cliente. O cliente pode pagar com outro cartão ou outra forma de pagamento.
> - **TX1008**: débito, R$ 75,00, terminal T1988B. Código 05: transação não autorizada pelo banco emissor (recusa genérica). O portador deve contatar o banco emissor ou tentar outro cartão.
>
> Não encontrei no material de apoio nenhuma orientação adicional além dessas. Posso propor a abertura de um chamado técnico para o terminal T1988B, que só é aberto depois da sua confirmação. Também posso encaminhar você a um atendente humano, se preferir.

### Turno 3

**Cliente:** Quero contestar a cobrança de aluguel da maquininha T1988B deste mês: pode passar para um atendente analisar? E a outra maquininha, a T1988A, está funcionando?

*(a operadora simulada `operadora_demo` responde pelo console, com chave pessoal, durante a espera: "Verifiquei o contrato: o aluguel da T1988B deste mês foi cobrado por engano e o estorno de R$ 79,90 entra na próxima fatura.")*

**Intenção:** human_request · **rota:** router → records → escalation → human

**Passos:**

1. **records** · ok · 3534 ms · decidido por: supervisor LLM (tool call)
   - `get_terminal_status` {"terminal_id": "T1988A"} → ok · `{"ok": true, "data": {"items": [{"terminal_id": "T1988A", "model": "Get Smart", "connection": "Wi-Fi", "status": "online", "signal": "bom",…`
2. **escalation** · ok · 5.3 ms · caso T-a84fb0ad · operador respondeu durante a espera · operador `operadora_demo` · decidido por: supervisor LLM (tool call)
3. **human** · ok · decidido por: operadora `operadora_demo`

**Resposta:**

> A T1988A está funcionando. Segundo o registro, ela está online, conectada por Wi-Fi e com sinal bom. O último contato foi em 2026-11-04 às 04:41.
>
> Sobre a contestação do aluguel da T1988B: a decisão sobre um caso individual é de um atendente humano.
>
> Consultei um atendente humano (protocolo T-a84fb0ad), que respondeu agora.
>
> Resposta do atendente: Verifiquei o contrato: o aluguel da T1988B deste mês foi cobrado por engano e o estorno de R$ 79,90 entra na próxima fatura.

*(auditoria do caso T-a84fb0ad: `handoff_reply` registrado por `operator:operadora_demo` (canal console))*

### Turno 4

**Cliente:** A maquininha T1988B continua sem sinal. Pode abrir um chamado?

**Intenção:** troubleshoot · **rota:** router → records → faq

**Passos:**

1. **records** · ok · 4858 ms · ação proposta `A-85c39f8f` · decidido por: supervisor LLM (tool call)
   - `get_terminal_status` {"terminal_id": "T1988B"} → ok · `{"ok": true, "data": {"items": [{"terminal_id": "T1988B", "model": "Get Clássica", "connection": "chip", "status": "offline", "signal": "se…`
   - `open_support_ticket` {"terminal_id": "T1988B", "reason": "sem_sinal"} → proposta (aguarda a confirmação do cliente) · `{"ok": false, "needs_confirmation": true, "action_id": "A-85c39f8f", "risk": "normal", "args": {"terminal_id": "T1988B", "reason": "sem_sin…`
2. **faq** · partial · motivo `partial_coverage` · 8095 ms · decidido por: supervisor LLM (tool call)

**Resposta:**

> Propus um chamado técnico para a T1988B com o motivo "sem sinal" (ação A-85c39f8f). Ele só será aberto depois que você confirmar, e a proposta expira em 15 minutos. Ainda não abri nada.
>
> A T1988B está offline, usa chip, e o último contato foi em 03/11/2026 às 23:42. Faz cerca de 5 horas que ela está offline.
>
> Enquanto isso, você pode tentar o seguinte:
>
> **Chip:**
> 1. Com a máquina desligada, abra a tampa traseira [sup-duvidas-06].
> 2. Coloque o chip em SIM1 ou SIM2, com a parte metálica para baixo [sup-duvidas-06].
> 3. Feche a tampa, ligue a máquina e aguarde a conexão de rede de dados [sup-duvidas-06].
> 4. Quando aparecer rede conectada (2G ou 3G), a máquina está pronta [sup-duvidas-06].
>
> **Teste de comunicação:** aperte o botão função (F, # ou o da sua máquina), escolha 2 (manutenção) e depois 1 (teste de comunicação) [sup-duvidas-07].
>
> A base que consultei não traz o passo a passo de Wi-Fi. O manual dos modelos com Wi-Fi está disponível para baixar [sup-manual-maquinas-01].
>
> Você confirma a abertura do chamado?

### Cliente confirma a ação `A-85c39f8f`

| campo | antes | depois |
|---|---|---|
| ticket | null | **CH-T1988B-20261104** |
| terminal_id | T1988B | (igual) |

