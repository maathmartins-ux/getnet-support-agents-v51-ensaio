# Transcrição multi-turno (memória, ação com antes/depois, humano)

Gerada por `scripts/demo_md.py --transcript evals/demo_transcript.jsonl` no commit `b10d60f` em 04/11/2026 02:24 UTC, rodando o `POST /chat` no processo (LLM: `anthropic`). Nada escrito à mão. Quem responde o caso é a operadora simulada `operadora_demo`, com chave pessoal gerada nesta execução (o `OPERATOR_KEYS` do processo guarda só o sha256 dela), pelo mesmo endpoint do console.

Em cada passo, **decidido por** diz quem pôs o agente no turno: o supervisor LLM (tool call); o plano do router (o router LLM, ou a regra que o substitui: seguimento herdado, guarda da própria empresa, queda do LLM), quando o supervisor LLM não foi consultado (rodado pelo atalho de 1 passo ou pelo motor de tabela); o código, com a regra entre parênteses (`supervisor.CODE_WHY`); ou a operadora que respondeu o caso. "não registrado" = passo gravado sem o campo `decided_by`.

### Turno 1

**Cliente:** Quando cai o dinheiro das vendas de ontem?

**Intenção:** support · **rota:** router → records

**Passos:**

1. **records** · ok · 3228 ms · decidido por: supervisor LLM (tool call)
   - `get_settlements` {"period": "yesterday"} → ok · `{"ok": true, "data": {"period": "yesterday", "items": [{"method": "pix", "method_pt": "Pix", "method_en": "Pix", "count": 1, "total": 64.0,…`

**Resposta:**

> O dinheiro das vendas de ontem (02/11/2026) cai em datas diferentes, conforme a forma de pagamento. Foram 5 vendas, num total de R$ 814,40:
>
> - **Pix:** R$ 64,00 (1 venda). Já foi depositado ontem (02/11).
> - **Débito:** R$ 200,50 (2 vendas). O depósito é hoje (03/11).
> - **Crédito:** R$ 549,90 (2 vendas). O depósito está agendado para 02/12/2026, em 29 dias.
>
> Já foram pagos R$ 264,50, e R$ 549,90 estão agendados.

### Turno 2

**Cliente:** E as vendas recusadas, o que aconteceu?

**Intenção:** support · **rota:** router → records → faq

**Passos:**

1. **records** · ok · 3141 ms · decidido por: supervisor LLM (tool call)
   - `get_transactions` {"status": "declined", "period": "last_7_days"} → ok · `{"ok": true, "data": {"items": [{"transaction_id": "TX1007", "method": "credito", "status": "recusada", "amount": 210.0, "decline_code": "5…`
2. **faq** · insufficient · motivo `not_in_sources` · 10164 ms · decidido por: código (achado `needs` de outro especialista)

**Resposta:**

> Nos últimos 7 dias, houve 2 vendas recusadas, somando R$ 285,00. As duas foram ontem (02/11/2026):
>
> - **TX1007**: crédito, R$ 210,00, terminal T1988A. Código 51: saldo ou limite insuficiente no cartão. O cliente pode usar outro cartão ou outra forma de pagamento.
> - **TX1008**: débito, R$ 75,00, terminal T1988B. Código 05: o banco emissor não autorizou a transação (recusa genérica). O portador deve falar com o banco emissor ou tentar outro cartão.
>
> Nenhuma das duas recusas indica problema na maquininha.
>
> A base de conhecimento não trouxe orientação adicional sobre recusas. Se quiser, posso encaminhar você a um atendente humano.

### Turno 3

**Cliente:** Quero contestar a cobrança de aluguel da maquininha T1988B deste mês: pode passar para um atendente analisar? E a outra maquininha, a T1988A, está funcionando?

*(a operadora simulada `operadora_demo` responde pelo console, com chave pessoal, durante a espera: "Verifiquei o contrato: o aluguel da T1988B deste mês foi cobrado por engano e o estorno de R$ 79,90 entra na próxima fatura.")*

**Intenção:** human_request · **rota:** router → records → escalation → human

**Passos:**

1. **records** · ok · 4746 ms · decidido por: supervisor LLM (tool call)
   - `get_terminal_status` {"terminal_id": "T1988A"} → ok · `{"ok": true, "data": {"items": [{"terminal_id": "T1988A", "model": "Get Smart", "connection": "Wi-Fi", "status": "online", "signal": "bom",…`
2. **escalation** · ok · 6.1 ms · caso T-dbea38c6 · operador respondeu durante a espera · operador `operadora_demo` · decidido por: supervisor LLM (tool call)
3. **human** · ok · decidido por: operadora `operadora_demo`

**Resposta:**

> A T1988A está funcionando. Ela está online, conectada por Wi-Fi, com sinal bom. O último contato foi em 2026-11-03 às 23:25, e ela está offline há 0 hora.
>
> Sobre a contestação do aluguel da T1988B, a decisão é de um atendente humano. Não tenho ferramenta para abrir esse caso nesta resposta, então ele não foi encaminhado por mim.
>
> Consultei um atendente humano (protocolo T-dbea38c6), que respondeu agora.
>
> Resposta do atendente: Verifiquei o contrato: o aluguel da T1988B deste mês foi cobrado por engano e o estorno de R$ 79,90 entra na próxima fatura.

*(auditoria do caso T-dbea38c6: `handoff_reply` registrado por `operator:operadora_demo` (canal console))*

### Turno 4

**Cliente:** A maquininha T1988B continua sem sinal. Pode abrir um chamado?

**Intenção:** troubleshoot · **rota:** router → records → faq

**Passos:**

1. **records** · ok · 4508 ms · ação proposta `A-692b532b` · decidido por: supervisor LLM (tool call)
   - `get_terminal_status` {"terminal_id": "T1988B"} → ok · `{"ok": true, "data": {"items": [{"terminal_id": "T1988B", "model": "Get Clássica", "connection": "chip", "status": "offline", "signal": "se…`
   - `open_support_ticket` {"terminal_id": "T1988B", "reason": "sem_sinal"} → proposta (aguarda a confirmação do cliente) · `{"ok": false, "needs_confirmation": true, "action_id": "A-692b532b", "risk": "normal", "args": {"terminal_id": "T1988B", "reason": "sem_sin…`
2. **faq** · partial · motivo `partial_coverage` · 8344 ms · decidido por: código (achado `needs` de outro especialista)

**Resposta:**

> Proposta o chamado técnico da T1988B (motivo "sem sinal", ação A-692b532b), mas **ele ainda não foi aberto**. Só será aberto se você confirmar, e a proposta expira em 15 minutos. Você confirma a abertura?
>
> A T1988B está offline e sem sinal. Ela usa chip e o último contato foi em 2026-11-03 às 18:25, há 5 horas.
>
> Enquanto isso, você pode tentar este passo a passo para máquinas com chip de dados [sup-duvidas-06]:
> - Com a máquina desligada, abra a tampa traseira.
> - Coloque o chip no local indicado (SIM1 ou SIM2), com a parte metálica voltada para baixo.
> - Feche a tampa, ligue a máquina e aguarde a conexão de rede de dados.
> - Quando aparecer rede conectada (2G ou 3G), a máquina está pronta.
> - Depois, faça um teste de comunicação para verificar o chip.
>
> Os manuais por modelo estão na página de manuais da Getnet [sup-manual-maquinas-01]. As fontes não trazem os passos do teste de comunicação nem o manual específico da T1988B. Se quiser, posso encaminhar você a um atendente humano.

### Cliente confirma a ação `A-692b532b`

| campo | antes | depois |
|---|---|---|
| ticket | null | **CH-T1988B-20261103** |
| terminal_id | T1988B | (igual) |

