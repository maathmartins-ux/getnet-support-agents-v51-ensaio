# Respostas reais — split `official`

Geradas de `evals/results/live_official.json` (provedor `anthropic`, status `complete`, gasto US$ 1.02); respostas medidas no commit `35020c4` (2026-11-04T02:02:50Z), página gerada no commit `e0951e4` em 04/11/2026 02:53 UTC. Nada aqui foi escrito à mão: é a saída do `POST /chat` com o LLM ligado, 1ª rodada de cada caso.

Estabilidade em 3 rodadas: pass@1 0.9667, pass^3 0.9; instáveis: official-04.

Em cada passo, **decidido por** diz quem pôs o agente no turno: o supervisor LLM (tool call); o plano do router (o router LLM, ou a regra que o substitui: seguimento herdado, guarda da própria empresa, queda do LLM), quando o supervisor LLM não foi consultado (rodado pelo atalho de 1 passo ou pelo motor de tabela); o código, com a regra entre parênteses (`supervisor.CODE_WHY`); ou a operadora que respondeu o caso. "não registrado" = passo gravado sem o campo `decided_by`.

| caso | intenção | rota | ferramentas | handoff | veredito automático |
|---|---|---|---|---|---|
| `official-01` | knowledge | router → faq | — | não | OK |
| `official-02` | general | router → faq | — | não | OK |
| `official-03` | support | router → records | get_settlements | não | OK |
| `official-04` | knowledge | router → faq | — | não | falhou: resolved |
| `official-05` | troubleshoot | router → records → faq | get_terminal_status | não | OK |
| `official-06` | knowledge | router → faq | — | não | OK |
| `official-07` | general | router → faq | — | não | OK |
| `official-08` | troubleshoot | router → records → faq | get_terminal_status, get_transactions | não | OK |
| `official-09` | knowledge | router → faq | — | não | OK |
| `official-10` | knowledge | router → faq | — | não | OK |

## official-01

**Pergunta:** What's the difference between the Get Clássica and the Get Smart?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0301 · **latência:** 19.6 s

**Resposta:**

> The Get Smart costs more and does more. The Get Clássica is R$ 79,90/month and the Get Smart is R$ 129,90/month [prod-ofertas-maquininha-11].
>
> - **Get Smart:** It is an intelligent card machine that runs Android. On the device you can control stock, place orders, close tabs, load a menu and issue invoices [sup-duvidas-get-smart-10][sup-duvidas-get-smart-17].
> - **Integration and messaging:** It can integrate with your establishment's system. It also lets the kitchen and dining room swap messages [sup-duvidas-get-smart-10][sup-duvidas-get-smart-17].
> - **Counter use:** It can replace a computer and fiscal printer at the counter. It reconciles payments in credit, debit, store credit, QR Code or cash [sup-duvidas-get-smart-08].
> - **Processing:** Getnet processes all Get Smart sales [sup-duvidas-get-smart-17].
>
> The sources don't describe the Get Clássica's features beyond its price, so I can't give a feature-by-feature comparison. I can hand you to a human agent if you'd like more detail.

**Passos:**

1. **faq** · partial · motivo `partial_coverage` · 10910 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://site.getnet.com.br/duvidas/get-smart/>; <https://site.getnet.com.br/todas-as-maquininhas/>; <https://site.getnet.com.br/duvidas/get-smart/>; <https://site.getnet.com.br/duvidas/get-smart/>; <https://site.getnet.com.br/ofertas-maquininha-de-cartao-getnet-2/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-02

**Pergunta:** What's the weather forecast in Porto Alegre tomorrow?

**Intenção:** general (esperada general) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0182 · **latência:** 7.3 s

**Resposta:**

> Tomorrow (2026-11-04) in Porto Alegre, the forecast is a low of 18 °C and a high of 24 °C, with up to a 78% chance of rain and thunderstorms. Source: Open-Meteo (https://open-meteo.com/).

**Passos:**

1. **faq** · ok · 3050 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://open-meteo.com/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-03

**Pergunta:** When will the money from yesterday's sales be deposited?

**Intenção:** support (esperada support) · **rota:** router → records · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0340 · **latência:** 10.7 s

**Resposta:**

> Yesterday's approved sales (2026-11-02) total R$ 814,40 across 5 sales. Deposits depend on the payment method:
>
> - **Pix:** R$ 64,00 (1 sale). It was deposited on 2026-11-02 and is marked paid.
> - **Debit:** R$ 200,50 (2 sales). The deposit date is today, 2026-11-03, and it is marked paid.
> - **Credit:** R$ 549,90 (2 sales). It is scheduled for 2026-12-02, 29 days from now.
>
> The schedule's rule is Pix D+0, debit D+1 business day, and credit D+30 (next business day).

**Passos:**

1. **records** · ok · 4123 ms · decidido por: supervisor LLM (tool call)
   - `get_settlements` {"period": "yesterday"} → ok · `{"ok": true, "data": {"period": "yesterday", "items": [{"method": "pix", "method_pt": "Pix", "method_en": "Pix", "count": 1, "total": 64.0,…`

**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'tools': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-04

**Pergunta:** Do I need a bank account to receive my sales via Pix?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0281 · **latência:** 11.3 s

**Resposta:**

> The sources don't say a bank account is mandatory. They do say Pix works with a checking, savings or prepaid payment account, at different banks [sup-duvidas-59]. Getnet also offers Get Conta, a free digital account for your business. With it you can send and receive money and sell through Pix [sup-duvidas-42].
>
> You receive Pix payments by generating a QR Code on the capture devices: physical terminals, TEF Auttar and Ecommerce [sup-duvidas-84].
>
> The sources don't state whether a specific account is required to receive Pix sales on Getnet. I can pass your question to a human agent if you'd like.

**Passos:**

1. **faq** · partial · motivo `partial_coverage` · 4843 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/pix/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/pix/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': False}

## official-05

**Pergunta:** My card machine won't connect to the internet, what should I do?

**Intenção:** troubleshoot (esperada troubleshoot) · **rota:** router → records → faq · **replanos:** ['records:need->faq (terminal offline/sem sinal: o passo a passo vem do manual de conexão)'] · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0507 · **latência:** 28.6 s

**Resposta:**

> Your Get Clássica terminal (T1988B) is offline with no signal. It last made contact on 2026-11-03 17:56 and has been offline for 5 hours. Your other terminal, T1988A (Get Smart), is online on Wi-Fi with good signal.
>
> For T1988B, check the SIM chip first. These are the steps from the Getnet FAQ [sup-duvidas-06]:
> - With the machine off, open the cover on the back.
> - Insert the chip in the slot marked SIM1 or SIM2, with the metal side facing down.
> - Close the cover, turn the machine on, and wait for it to connect to the data network.
> - When it shows a connected network (2G or 3G), the machine is ready to use.
> - Run a communication test to check that the chip is connecting.
>
> If your model also uses Wi-Fi, Getnet has user manuals by model [sup-manual-maquinas-01].
>
> I can propose a technical support ticket for T1988B with the reason "sem_sinal". It is only a proposal. Nothing happens until you confirm, and the proposal expires after 15 minutes. Do you want me to propose it?
>
> The sources don't cover Wi-Fi setup, weak-signal troubleshooting or the steps for the communication test. I can pass you to a human agent for those.

**Passos:**

1. **records** · ok · 4008 ms · decidido por: supervisor LLM (tool call)
   - `get_terminal_status` {} → ok · `{"ok": true, "data": {"items": [{"terminal_id": "T1988A", "model": "Get Smart", "connection": "Wi-Fi", "status": "online", "signal": "bom",…`
2. **faq** · partial · motivo `partial_coverage` · 16426 ms · decidido por: código (achado `needs` de outro especialista)

**Fontes:** <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/todas-as-maquininhas/>; <https://site.getnet.com.br/boas-vindas/manual-maquinas/>; <https://site.getnet.com.br/duvidas/get-smart/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'tools': True, 'numbers': True, 'claims': True, 'completed': True, 'facts': True, 'resolved': True}

## official-06

**Pergunta:** How does receivables advance (antecipação) work with Getnet?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0295 · **latência:** 10.1 s

**Resposta:**

> You can advance your sales in the Getnet Brasil app, which is always available, and using the app has no extra fees [sup-duvidas-17].
>
> - **Automatic Advance:** If you choose the "Receba Conforme suas Vendas" receiving plan, Automatic Advance is a condition for getting the exemption [sup-duvidas-102]. Getnet treats it as a credit approval process. It assesses each contract individually and decides whether to grant the product [sup-duvidas-102].
> - **Through this assistant:** I can propose a request to advance your scheduled receivables. It only runs after you confirm it and a human agent approves it.
>
> The sources don't give the advance fee or rate, or the payout timing for a manual advance. I can pass your case to a human agent if you'd like those details.

**Passos:**

1. **faq** · partial · motivo `partial_coverage` · 2962 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://site.getnet.com.br/get-ajuda-reserva-financeira/antecipacao-reserva-financeira/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/get-ajuda-reserva-financeira/antecipacao-reserva-financeira/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/crediario/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-07

**Pergunta:** What's the euro exchange rate today?

**Intenção:** general (esperada general) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0189 · **latência:** 9.2 s

**Resposta:**

> Today (2026-11-03), the euro is at R$ 6.1482 for buy and R$ 6.1500 for sell. That is about R$ 6,15 for both when rounded. The figures come from the Banco Central do Brasil PTAX closing bulletin: https://www.bcb.gov.br/estabilidadefinanceira/historicocotacoes

**Passos:**

1. **faq** · ok · 3530 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://www.bcb.gov.br/estabilidadefinanceira/historicocotacoes>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-08

**Pergunta:** My card machine is showing a transaction decline error.

**Intenção:** troubleshoot (esperada troubleshoot) · **rota:** router → records → faq · **replanos:** ['records:need->faq (terminal offline/sem sinal: o passo a passo vem do manual de conexão)'] · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0680 · **latência:** 36.2 s

**Resposta:**

> Your two recent declines came from the cardholders' banks or cards, not from your terminals.
>
> - **TX1007** (yesterday, T1988A): credit, R$ 210,00, code 51. This means insufficient funds or credit limit on the card. Ask for another card or payment method.
> - **TX1008** (yesterday, T1988B): debit, R$ 75,00, code 05. The issuing bank did not authorize it (generic refusal). The cardholder should contact their bank, or you can try another card.
>
> **Terminal status:** T1988A is online with good signal. T1988B has been offline for 5 hours, with no signal on the chip, so it may not be able to process sales right now.
>
> **Chip setup for T1988B** [sup-duvidas-06]:
> 1. With the machine off, open the back cover.
> 2. Insert the chip in the SIM1 or SIM2 slot, metal side facing down.
> 3. Close the cover, turn the machine on and wait for the data network to connect.
> 4. When it shows a connected network (2G or 3G), the machine is ready. Then run a communication test.
>
> Getnet has downloadable manuals for each model [sup-manual-maquinas-01]. The sources I found don't cover Wi-Fi connection or fixing a weak or missing signal.
>
> I can propose a support ticket for T1988B, but nothing is opened until you confirm. I can also hand your case to a human agent. Would you like either?

**Passos:**

1. **records** · ok · 4594 ms · decidido por: supervisor LLM (tool call)
   - `get_terminal_status` {} → ok · `{"ok": true, "data": {"items": [{"terminal_id": "T1988A", "model": "Get Smart", "connection": "Wi-Fi", "status": "online", "signal": "bom",…`
   - `get_transactions` {"status": "declined", "period": "last_7_days"} → ok · `{"ok": true, "data": {"items": [{"transaction_id": "TX1007", "method": "credito", "status": "recusada", "amount": 210.0, "decline_code": "5…`
2. **faq** · partial · motivo `partial_coverage` · 22958 ms · decidido por: código (achado `needs` de outro especialista)

**Fontes:** <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/get-tap/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/todas-as-maquininhas/>; <https://site.getnet.com.br/todas-as-maquininhas/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'tools': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-09

**Pergunta:** How many installments can I split a sale into with the crediário?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0258 · **latência:** 17.8 s

**Resposta:**

> You can split a sale into up to 48 installments with the Crediário [prod-crediario-03][prod-crediario-01]. The maximum term and the interest rate depend on the card issuer [prod-crediario-02].
>
> You receive the full amount of the sale in a single payment within 2 business days after the transaction is captured, however many installments the cardholder chooses. The discount fee (MDR) is subtracted from the original transaction amount [sup-duvidas-39].

**Passos:**

1. **faq** · ok · 12412 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://site.getnet.com.br/crediario/>; <https://site.getnet.com.br/crediario/>; <https://site.getnet.com.br/crediario/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/duvidas/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-10

**Pergunta:** Can I sell through WhatsApp using the Payment Link?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0280 · **latência:** 18.9 s

**Resposta:**

> Yes, you can sell through WhatsApp with the Payment Link. It generates a link that your customer uses to pay online by card, Pix or debit. It is meant for sales over WhatsApp, social media and remote charges [prod-pagamentos-pelo-whatsapp-02, prod-link-de-pagamento-01].
>
> Pricing depends on your plan [prod-link-de-pagamento-02]:
> - **Inicial:** R$1,00 per paid link, charged only when the payment is approved.
> - **Básico:** R$28 per month, which covers 60 card transactions. Each extra transaction costs R$0,50.

**Passos:**

1. **faq** · ok · 12197 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://site.getnet.com.br/pagamentos-pelo-whatsapp/>; <https://site.getnet.com.br/link-de-pagamento/>; <https://site.getnet.com.br/pagamentos-pelo-whatsapp/>; <https://site.getnet.com.br/link-de-pagamento/>; <https://site.getnet.com.br/ofertas-maquininha-de-cartao-getnet-2/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}
