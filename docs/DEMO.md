# Respostas reais — split `official`

Geradas de `evals/results/live_official.json` (provedor `anthropic`, status `complete`, gasto US$ 0.90); respostas medidas no commit `3de0e10` (2026-11-03T21:18:41Z), página gerada no commit `3de0e10` em 03/11/2026 21:20 UTC. Nada aqui foi escrito à mão: é a saída do `POST /chat` com o LLM ligado, 1ª rodada de cada caso.

Estabilidade em 3 rodadas: pass@1 1.0, pass^3 1.0; instáveis: nenhum.

| caso | intenção | rota | ferramentas | handoff | veredito automático |
|---|---|---|---|---|---|
| `official-01` | knowledge | router → faq | — | não | OK |
| `official-02` | general | router → faq | — | não | OK |
| `official-03` | support | router → records | get_settlements | não | OK |
| `official-04` | knowledge | router → faq | — | não | OK |
| `official-05` | troubleshoot | router → records → faq | get_terminal_status | não | OK |
| `official-06` | knowledge | router → faq | — | não | OK |
| `official-07` | general | router → faq | — | não | OK |
| `official-08` | troubleshoot | router → records → faq | get_transactions, get_terminal_status | não | OK |
| `official-09` | knowledge | router → faq | — | não | OK |
| `official-10` | knowledge | router → faq | — | não | OK |

## official-01

**Pergunta:** What's the difference between the Get Clássica and the Get Smart?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0276 · **latência:** 16.1 s

**Resposta:**

> The Get Smart costs more and does more at the counter. Here is what the sources say.
>
> - **Get Smart:** It lets you control stock, take orders, close tabs, load menus and issue invoices on the device. It can also be integrated with your business system [sup-duvidas-get-smart-10]. It replaces the need for a computer and fiscal printer at the counter. It also reconciles payments by credit, debit, store credit, QR Code or cash [sup-duvidas-get-smart-08].
> - **Price:** If you don't reach the revenue tiers for rent exemption, the Get Clássica costs R$ 79,90/month and the Get Smart costs R$ 129,90/month [prod-get-tap-03][prod-todas-as-maquininhas-04].
>
> The sources don't describe the Get Clássica's features, so I can't give a full feature comparison. I can pass your question to a human agent if you'd like.

**Passos:**

1. **faq** · partial · motivo `partial_coverage` · 7409 ms

**Fontes:** <https://site.getnet.com.br/duvidas/get-smart/>; <https://site.getnet.com.br/get-tap/>; <https://site.getnet.com.br/duvidas/get-smart/>; <https://site.getnet.com.br/todas-as-maquininhas/>; <https://site.getnet.com.br/todas-as-maquininhas/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-02

**Pergunta:** What's the weather forecast in Porto Alegre tomorrow?

**Intenção:** general (esperada general) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0169 · **latência:** 10.7 s

**Resposta:**

> Tomorrow (2026-11-04) in Porto Alegre, the forecast is a low of 19 °C and a high of 22 °C. There's up to an 82% chance of rain, so it's a good idea to take an umbrella. Source: wttr.in.

**Passos:**

1. **faq** · ok · 5732 ms

**Fontes:** <https://wttr.in/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-03

**Pergunta:** When will the money from yesterday's sales be deposited?

**Intenção:** support (esperada support) · **rota:** router → records · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0314 · **latência:** 9.0 s

**Resposta:**

> Yesterday's sales (2026-11-02) are deposited on different dates depending on the payment method:
>
> | Method | Sales | Total | Deposit date | Status |
> |---|---|---|---|---|
> | Pix | 1 | R$ 64,00 | 2026-11-02 (yesterday) | Paid |
> | Debit | 2 | R$ 200,50 | 2026-11-03 (today) | Paid |
> | Credit | 2 | R$ 549,90 | 2026-12-02 (in 29 days) | Scheduled |
>
> The 5 sales add up to R$ 814,40. Pix and debit are already marked as paid. Only the credit sales, R$ 549,90, are still waiting for their deposit.

**Passos:**

1. **records** · ok · 3062 ms
   - `get_settlements` {"period": "yesterday"} → ok · `{"ok": true, "data": {"period": "yesterday", "items": [{"method": "pix", "method_pt": "Pix", "method_en": "Pix", "count": 1, "total": 64.0,…`

**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'tools': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-04

**Pergunta:** Do I need a bank account to receive my sales via Pix?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0395 · **latência:** 13.7 s

**Resposta:**

> Getnet offers Get Conta, a free digital account for your business. You can use it to receive money and sell through Pix [sup-duvidas-42].
>
> To open one, choose a rental or purchase machine and select the option to receive your sales in the Account. The account is opened immediately [sup-duvidas-44].
>
> If you'd rather use another account, Pix works with checking accounts, savings accounts and prepaid payment accounts at different banks [sup-duvidas-59].

**Passos:**

1. **faq** · ok · 7736 ms

**Fontes:** <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/pix/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/link-de-pagamento/>; <https://site.getnet.com.br/pix/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-05

**Pergunta:** My card machine won't connect to the internet, what should I do?

**Intenção:** troubleshoot (esperada troubleshoot) · **rota:** router → records → faq · **replanos:** ['records:need->faq (terminal offline/sem sinal: o passo a passo vem do manual de conexão)'] · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0462 · **latência:** 17.5 s

**Resposta:**

> Your offline terminal is T1988B (Get Clássica). It connects by chip, shows no signal, and has been offline for about 5 hours. T1988A is online. Start by checking the SIM chip, using these steps from the Getnet FAQ [sup-duvidas-06]:
>
> 1. With the machine off, open the cover on the back.
> 2. Insert the chip in the slot marked SIM1 or SIM2, with the metal part facing down.
> 3. Close the cover, turn the machine on and wait for it to connect to the data network.
> 4. When it shows a connected network (2G or 3G), the machine is ready to use.
> 5. Run a communication test to check that the chip is connecting.
>
> The steps for turning the machine on and off depend on the model [sup-duvidas-66]. There are also user manuals for each model [sup-manual-maquinas-01].
>
> I can propose a technical support ticket for T1988B with the reason "no signal". Nothing runs until you confirm, and the proposal expires after 15 minutes. Do you want me to propose it?
>
> The sources don't cover Wi-Fi setup, how to improve signal strength, or the steps for the communication test. I can hand your case to a human agent if you want help with those.

**Passos:**

1. **records** · ok · 3288 ms
   - `get_terminal_status` {} → ok · `{"ok": true, "data": {"items": [{"terminal_id": "T1988A", "model": "Get Smart", "connection": "Wi-Fi", "status": "online", "signal": "bom",…`
2. **faq** · partial · motivo `partial_coverage` · 5757 ms

**Fontes:** <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/boas-vindas/manual-maquinas/>; <https://site.getnet.com.br/todas-as-maquininhas/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/duvidas/get-smart/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'tools': True, 'numbers': True, 'claims': True, 'completed': True, 'facts': True, 'resolved': True}

## official-06

**Pergunta:** How does receivables advance (antecipação) work with Getnet?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0268 · **latência:** 12.1 s

**Resposta:**

> You can advance your sales through the Getnet Brasil app, which is always available for this. Using the app has no extra fee [sup-duvidas-17].
>
> - **Automatic Advance (Antecipação Automática):** It is a condition for the exemption if you choose the "Receba Conforme suas Vendas" receiving plan. It goes through credit approval, and Getnet assesses each contract individually [sup-duvidas-102].
> - **Through this assistant:** I can propose an advance of your scheduled receivables. You would need to confirm it, and then a human agent would have to approve it before it runs.
>
> The sources don't give the advance rate, the payout timing, or the step-by-step process. A human agent can help with those if you'd like.

**Passos:**

1. **faq** · partial · motivo `partial_coverage` · 5124 ms

**Fontes:** <https://site.getnet.com.br/get-ajuda-reserva-financeira/antecipacao-reserva-financeira/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/get-ajuda-reserva-financeira/antecipacao-reserva-financeira/>; <https://site.getnet.com.br/conta-digital/>; <https://site.getnet.com.br/duvidas/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-07

**Pergunta:** What's the euro exchange rate today?

**Intenção:** general (esperada general) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0175 · **latência:** 7.7 s

**Resposta:**

> Today (03/11/2026), the euro closed at R$ 6.1482 for buying and R$ 6.1500 for selling. These are the Banco Central do Brasil PTAX closing rates. Rounded, both are about R$ 6.15.
>
> Source: https://www.bcb.gov.br/estabilidadefinanceira/historicocotacoes

**Passos:**

1. **faq** · ok · 2368 ms

**Fontes:** <https://www.bcb.gov.br/estabilidadefinanceira/historicocotacoes>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-08

**Pergunta:** My card machine is showing a transaction decline error.

**Intenção:** troubleshoot (esperada troubleshoot) · **rota:** router → records → faq · **replanos:** ['records:need->faq (transação recusada: a orientação vem do Knowledge)'] · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0458 · **latência:** 18.8 s

**Resposta:**

> - **TX1007** (credit, R$ 210,00, terminal T1988A): code 51 means insufficient funds or credit limit on the customer's card. Ask the customer for another card or payment method.
> - **TX1008** (debit, R$ 75,00, terminal T1988B): code 05 means the issuing bank did not authorize the transaction, with no specific reason given. The cardholder should contact their bank or try another card.
>
> Terminal T1988B is offline on chip with no signal. It last made contact at 2026-11-03 16:14, about 5 hours ago. T1988A is online with a good signal.
>
> I can propose a support ticket for T1988B. Nothing runs until you confirm it, and the proposal expires after 15 minutes. Do you want me to propose it?
>
> If you want a person to look at this, I can hand it to a human agent.

**Passos:**

1. **records** · ok · 4738 ms
   - `get_transactions` {"status": "declined", "period": "last_7_days"} → ok · `{"ok": true, "data": {"items": [{"transaction_id": "TX1007", "method": "credito", "status": "recusada", "amount": 210.0, "decline_code": "5…`
   - `get_terminal_status` {} → ok · `{"ok": true, "data": {"items": [{"terminal_id": "T1988A", "model": "Get Smart", "connection": "Wi-Fi", "status": "online", "signal": "bom",…`
2. **faq** · insufficient · motivo `not_in_sources` · 3653 ms

**Fontes:** <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/todas-as-maquininhas/>; <https://site.getnet.com.br/get-tap/>; <https://site.getnet.com.br/conta-digital/>; <https://site.getnet.com.br/get-tap/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'tools': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-09

**Pergunta:** How many installments can I split a sale into with the crediário?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0247 · **latência:** 10.9 s

**Resposta:**

> You can split a sale into up to 48 installments with the Crediário [prod-crediario-01][prod-crediario-02].
>
> The maximum term and the interest rate depend on the card issuer, so what your customer gets may vary [prod-crediario-02][prod-crediario-03].
>
> You receive the full sale amount in a single payment within 2 business days after the transaction is captured, whatever number of installments the cardholder picks. The discount fee is subtracted from the original amount [sup-duvidas-39].

**Passos:**

1. **faq** · ok · 5510 ms

**Fontes:** <https://site.getnet.com.br/crediario/>; <https://site.getnet.com.br/crediario/>; <https://site.getnet.com.br/crediario/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/duvidas/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-10

**Pergunta:** Can I sell through WhatsApp using the Payment Link?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0274 · **latência:** 12.0 s

**Resposta:**

> Yes, you can sell through WhatsApp with the Payment Link. It's meant for selling through WhatsApp or social media [prod-link-de-pagamento-01].
>
> How to do it [prod-link-de-pagamento-04]:
> 1. Log in to the Minha Conta portal or the Getnet Brasil app.
> 2. Go to Produtos e Serviços, choose Link de Pagamento, then Criar Link de Pagamento.
> 3. Fill in the product, shipping and payment options.
> 4. Click share or copy, then send the link wherever you like, including WhatsApp.
>
> Your buyer can pay by debit, credit, Pix, Wallet or boleto [prod-link-de-pagamento-01].

**Passos:**

1. **faq** · ok · 5304 ms

**Fontes:** <https://site.getnet.com.br/link-de-pagamento/>; <https://site.getnet.com.br/get-tap/>; <https://site.getnet.com.br/link-de-pagamento/>; <https://site.getnet.com.br/link-de-pagamento/>; <https://site.getnet.com.br/duvidas/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}
