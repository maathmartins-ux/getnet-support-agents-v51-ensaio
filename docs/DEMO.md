# Respostas reais — split `official`

Geradas de `evals/results/live_official.json` (provedor `anthropic`, status `complete`, gasto US$ 0.87) no commit `1fa7c26` em 03/11/2026 18:50 UTC. Nada aqui foi escrito à mão: é a saída do `POST /chat` com o LLM ligado, 1ª rodada de cada caso.

Estabilidade em 3 rodadas: pass@1 0.9667, pass^3 0.9; instáveis: official-04.

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

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0262 · **latência:** 15.0 s

**Resposta:**

> The main difference the sources give is price. The Get Clássica costs R$ 79,90/month and the Get Smart costs R$ 129,90/month [prod-todas-as-maquininhas-04][prod-get-tap-03].
>
> The Get Smart is a smart machine that lets you do the following directly on the device [sup-duvidas-get-smart-10][sup-duvidas-get-smart-08]:
> - Control stock, take orders, close tabs, load a menu and issue invoices.
> - Integrate with your business system.
> - Work as both the computer and the fiscal printer.
> - Reconcile payments across credit, debit, store credit, QR Code and cash.
>
> The sources don't describe the Get Clássica's features, so I can't compare it with the Get Smart beyond price. I can hand you to a human agent if you want more detail.

**Passos:**

1. **faq** · partial · motivo `partial_coverage` · 6952 ms

**Fontes:** <https://site.getnet.com.br/duvidas/get-smart/>; <https://site.getnet.com.br/todas-as-maquininhas/>; <https://site.getnet.com.br/duvidas/get-smart/>; <https://site.getnet.com.br/todas-as-maquininhas/>; <https://site.getnet.com.br/get-tap/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-02

**Pergunta:** What's the weather forecast in Porto Alegre tomorrow?

**Intenção:** general (esperada general) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0172 · **latência:** 10.4 s

**Resposta:**

> Tomorrow (2026-11-04) in Porto Alegre, the forecast is a low of 19 °C and a high of 22 °C, with up to an 82% chance of rain. Take an umbrella.
>
> Source: wttr.in (https://wttr.in/). It isn't the Open-Meteo source normally used for this kind of answer.

**Passos:**

1. **faq** · ok · 6157 ms

**Fontes:** <https://wttr.in/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-03

**Pergunta:** When will the money from yesterday's sales be deposited?

**Intenção:** support (esperada support) · **rota:** router → records · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0314 · **latência:** 9.3 s

**Resposta:**

> Yesterday's sales (2026-11-02) were 5 sales totaling R$ 814,40. Deposits by payment method:
>
> | Method | Sales | Total | Deposit date | Status |
> |---|---|---|---|---|
> | Pix | 1 | R$ 64,00 | 2026-11-02 (yesterday) | Paid |
> | Debit | 2 | R$ 200,50 | 2026-11-03 (today) | Paid |
> | Credit | 2 | R$ 549,90 | 2026-12-02 (in 29 days) | Scheduled |
>
> Pix and debit have already been paid. Only the credit amount is still scheduled.

**Passos:**

1. **records** · ok · 3806 ms
   - `get_settlements` {"period": "yesterday"} → ok · `{"ok": true, "data": {"period": "yesterday", "items": [{"method": "pix", "method_pt": "Pix", "method_en": "Pix", "count": 1, "total": 64.0,…`

**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'tools': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-04

**Pergunta:** Do I need a bank account to receive my sales via Pix?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0271 · **latência:** 12.9 s

**Resposta:**

> Pix works with a checking account, a savings account or a prepaid payment account, across different banks [sup-duvidas-59]. Getnet generates the Pix QR Code on its terminals, TEF Auttar and Ecommerce [sup-duvidas-84]. When you receive the money can vary by up to one calendar day, depending on your Pix model and when the sale is approved [prod-pix-01].
>
> The sources don't say which account type Getnet requires to receive your sales, or whether you must have a bank account. I can pass your question to a human agent if you'd like.

**Passos:**

1. **faq** · partial · motivo `partial_coverage` · 7236 ms

**Fontes:** <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/pix/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/link-de-pagamento/>; <https://site.getnet.com.br/pix/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-05

**Pergunta:** My card machine won't connect to the internet, what should I do?

**Intenção:** troubleshoot (esperada troubleshoot) · **rota:** router → records → faq · **replanos:** ['records:need->faq (terminal offline/sem sinal: o passo a passo vem do manual de conexão)'] · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0463 · **latência:** 16.9 s

**Resposta:**

> Your terminal T1988B (Get Clássica) is the one that can't connect. It uses a chip, has no signal, and has been offline for 5 hours. It last made contact at 2026-11-03 13:44. Your other terminal, T1988A, is online on Wi-Fi with a good signal.
>
> For T1988B, check the chip setup [sup-duvidas-06]:
> - Turn the machine off and open the cover on the back.
> - Put the chip in the slot marked SIM1 or SIM2, with the metal part facing down.
> - Close the cover, turn the machine on and wait for it to connect to the data network.
> - When it shows a connected network (2G or 3G), the machine is ready.
> - Run a communication test to check the chip's connectivity.
>
> Getnet also has a downloadable manual for each model [sup-manual-maquinas-01].
>
> I can propose a technical support ticket for T1988B with the reason "sem_sinal" (no signal). Nothing is opened until you confirm. Do you want me to propose it?
>
> The sources I found don't cover Wi-Fi setup or fixing a weak signal. If you want, I can also hand this to a human agent.

**Passos:**

1. **records** · ok · 2937 ms
   - `get_terminal_status` {} → ok · `{"ok": true, "data": {"items": [{"terminal_id": "T1988A", "model": "Get Smart", "connection": "Wi-Fi", "status": "online", "signal": "bom",…`
2. **faq** · partial · motivo `partial_coverage` · 5711 ms

**Fontes:** <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/boas-vindas/manual-maquinas/>; <https://site.getnet.com.br/todas-as-maquininhas/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/duvidas/get-smart/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'tools': True, 'numbers': True, 'claims': True, 'completed': True, 'facts': True, 'resolved': True}

## official-06

**Pergunta:** How does receivables advance (antecipação) work with Getnet?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0284 · **latência:** 12.5 s

**Resposta:**

> You can advance your sales through the Getnet Brasil app, which is always available. The app has no extra fees [sup-duvidas-17].
>
> - **Automatic Advance:** This is a condition for the exemption for customers on the "Receba Conforme suas Vendas" plan. It goes through credit approval, and Getnet assesses each contract individually [sup-duvidas-102].
> - **Financial Reserve:** Funds are released on the originally scheduled date. The exceptions are funds used to cover sale cancellations, chargebacks, or terminal rental and other expenses [sup-antecipacao-02].
> - **Through this assistant:** I can propose an advance of your scheduled receivables. It only runs after you confirm it and a human agent approves it. A proposal you don't confirm expires after 15 minutes.
>
> The sources I found don't give the fee rate, the processing time, or the eligibility rules. A human agent can help with those if you want.

**Passos:**

1. **faq** · partial · motivo `partial_coverage` · 5122 ms

**Fontes:** <https://site.getnet.com.br/get-ajuda-reserva-financeira/antecipacao-reserva-financeira/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/get-ajuda-reserva-financeira/antecipacao-reserva-financeira/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/duvidas/get-smart/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-07

**Pergunta:** What's the euro exchange rate today?

**Intenção:** general (esperada general) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0170 · **latência:** 6.9 s

**Resposta:**

> Today (2026-11-03), the Banco Central do Brasil PTAX closing bulletin shows 1 EUR = R$ 6.1500 for sell and R$ 6.1482 for buy. That's about R$ 6.15 either way.
>
> Source: https://www.bcb.gov.br/estabilidadefinanceira/historicocotacoes

**Passos:**

1. **faq** · ok · 2760 ms

**Fontes:** <https://www.bcb.gov.br/estabilidadefinanceira/historicocotacoes>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-08

**Pergunta:** My card machine is showing a transaction decline error.

**Intenção:** troubleshoot (esperada troubleshoot) · **rota:** router → records → faq · **replanos:** ['records:need->faq (transação recusada: a orientação vem do Knowledge)'] · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0457 · **latência:** 18.7 s

**Resposta:**

> Your two recent declines came from the cards or the issuing banks, not from your terminals.
>
> - **TX1007** (T1988A, credit, R$ 210,00): code 51, insufficient funds or credit limit on the customer's card. Ask for another card or payment method.
> - **TX1008** (T1988B, debit, R$ 75,00): code 05, not authorized by the issuing bank. The cardholder should contact the issuing bank or try another card.
>
> T1988B is also offline. It has no signal on chip and has been offline for 5 hours. Its last contact was 2026-11-03 13:45. T1988A is online with good signal.
>
> I can propose a support ticket for T1988B. Nothing runs until you confirm. Do you want me to propose it?
>
> I found no additional written guidance on decline errors in the knowledge base. If you want more help, I can hand your case to a human agent.

**Passos:**

1. **records** · ok · 4231 ms
   - `get_transactions` {"status": "declined", "period": "last_7_days"} → ok · `{"ok": true, "data": {"items": [{"transaction_id": "TX1007", "method": "credito", "status": "recusada", "amount": 210.0, "decline_code": "5…`
   - `get_terminal_status` {} → ok · `{"ok": true, "data": {"items": [{"terminal_id": "T1988A", "model": "Get Smart", "connection": "Wi-Fi", "status": "online", "signal": "bom",…`
2. **faq** · insufficient · motivo `not_in_sources` · 5238 ms

**Fontes:** <https://site.getnet.com.br/crediario/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/todas-as-maquininhas/>; <https://site.getnet.com.br/get-tap/>; <https://site.getnet.com.br/todas-as-maquininhas/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'tools': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-09

**Pergunta:** How many installments can I split a sale into with the crediário?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0252 · **latência:** 10.7 s

**Resposta:**

> With the Crediário, you can split a sale into up to 48 installments. The maximum term and the interest rate depend on the card issuer [prod-crediario-01][prod-crediario-02].
>
> - You receive the full sale amount at once, within 2 business days after the transaction is captured. This is the same no matter how many installments the cardholder chooses [sup-duvidas-39].
> - The discount fee (MDR) is subtracted from the original amount [sup-duvidas-39]. You can check it in the Getnet Brasil app or the Customer Portal [prod-crediario-03].
> - Parcelado Lojista is interest-free for the customer and limited to 12 installments [sup-duvidas-78].

**Passos:**

1. **faq** · ok · 5413 ms

**Fontes:** <https://site.getnet.com.br/crediario/>; <https://site.getnet.com.br/crediario/>; <https://site.getnet.com.br/crediario/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/duvidas/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-10

**Pergunta:** Can I sell through WhatsApp using the Payment Link?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0257 · **latência:** 11.0 s

**Resposta:**

> Yes, you can sell through WhatsApp with the Payment Link. You can also use it on social media [prod-link-de-pagamento-01].
>
> **How to do it:**
> 1. Open the Minha Conta portal or the Getnet Brasil app.
> 2. Go to Products and Services, choose Link de Pagamento, then Criar Link de Pagamento.
> 3. Fill in the product, shipping and payment options.
> 4. Click share or copy, then send the link on WhatsApp or anywhere else [prod-link-de-pagamento-04].
>
> Buyers can pay by debit, credit, Pix, Wallet or boleto [prod-link-de-pagamento-01].

**Passos:**

1. **faq** · ok · 4854 ms

**Fontes:** <https://site.getnet.com.br/link-de-pagamento/>; <https://site.getnet.com.br/get-tap/>; <https://site.getnet.com.br/link-de-pagamento/>; <https://site.getnet.com.br/link-de-pagamento/>; <https://site.getnet.com.br/duvidas/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}
