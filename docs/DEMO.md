# Respostas reais — split `official`

Geradas de `evals/results/live_official.json` (provedor `anthropic`, status `complete`, gasto US$ 1.04); respostas medidas no commit `ff8afed` (2026-11-04T07:23:22Z), página gerada no commit `0b5ffec` em 04/11/2026 07:47 UTC. Nada aqui foi escrito à mão: é a saída do `POST /chat` com o LLM ligado, 1ª rodada de cada caso.

Estabilidade em 3 rodadas: pass@1 0.9, pass^3 0.9; instáveis: nenhum.

Em cada passo, **decidido por** diz quem pôs o agente no turno: o supervisor LLM (tool call); o plano do router (o router LLM, ou a regra que o substitui: seguimento herdado, guarda da própria empresa, queda do LLM), quando o supervisor LLM não foi consultado (rodado pelo atalho de 1 passo ou pelo motor de tabela); o código, com a regra entre parênteses (`supervisor.CODE_WHY`); ou a operadora que respondeu o caso. "não registrado" = passo gravado sem o campo `decided_by`.

| caso | intenção | rota | ferramentas | handoff | veredito automático |
|---|---|---|---|---|---|
| `official-01` | knowledge | router → faq | — | não | falhou: facts, resolved |
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

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0299 · **latência:** 10.7 s

**Resposta:**

> The Get Smart costs more and does more. It's R$ 129,90/month, against R$ 79,90/month for the Get Clássica [prod-ofertas-maquininha-11][prod-todas-as-maquininhas-04].
>
> The Get Smart is a smart card machine that runs Android. It works as both a computer and a fiscal printer. On the device you can:
> - manage stock
> - take orders
> - close the bill
> - load a menu
> - issue fiscal receipts
> - exchange messages between kitchen and floor
> - reconcile payments in all methods
>
> Sources: [sup-duvidas-get-smart-10][sup-duvidas-get-smart-17][sup-duvidas-get-smart-08].
>
> The sources don't describe the Get Clássica's features, so I can't compare the two feature by feature. I can pass you to a human agent if you want more detail.

**Passos:**

1. **faq** · partial · motivo `partial_coverage` · 3693 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://site.getnet.com.br/duvidas/get-smart/>; <https://site.getnet.com.br/todas-as-maquininhas/>; <https://site.getnet.com.br/duvidas/get-smart/>; <https://site.getnet.com.br/duvidas/get-smart/>; <https://site.getnet.com.br/ofertas-maquininha-de-cartao-getnet-2/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': False, 'resolved': False}

## official-02

**Pergunta:** What's the weather forecast in Porto Alegre tomorrow?

**Intenção:** general (esperada general) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0183 · **latência:** 6.7 s

**Resposta:**

> Tomorrow (2026-11-05) in Porto Alegre, the forecast is a low of 17 °C (17.1), a high of 25 °C (24.6), and up to a 41% chance of rain and drizzle. Source: Open-Meteo (https://open-meteo.com/).

**Passos:**

1. **faq** · ok · 3156 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://open-meteo.com/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-03

**Pergunta:** When will the money from yesterday's sales be deposited?

**Intenção:** support (esperada support) · **rota:** router → records · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0338 · **latência:** 10.0 s

**Resposta:**

> Yesterday's approved sales were 5 sales, R$ 814,40 in total. They are deposited on different dates depending on the payment method:
>
> - **Pix:** 1 sale, R$ 64,00. It was deposited yesterday (2026-11-03) and is marked paid.
> - **Debit:** 2 sales, R$ 200,50. The deposit date is today (2026-11-04) and it is marked paid.
> - **Credit:** 2 sales, R$ 549,90. It is scheduled for 2026-12-03, 29 days from now.
>
> The system rule is Pix D+0, debit D+1 business day, and credit D+30 (next business day).

**Passos:**

1. **records** · ok · 3135 ms · decidido por: supervisor LLM (tool call)
   - `get_settlements` {"period": "yesterday"} → ok · `{"ok": true, "data": {"period": "yesterday", "items": [{"method": "pix", "method_pt": "Pix", "method_en": "Pix", "count": 1, "total": 64.0,…`

**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'tools': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-04

**Pergunta:** Do I need a bank account to receive my sales via Pix?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0455 · **latência:** 13.7 s

**Resposta:**

> Your options are:
>
> - **Get Conta:** This is a free digital account that lets you sell via Pix [sup-duvidas-42]. You can use it as the account that receives your sales, within 2 business days of the transaction and after your registration is complete [prod-ofertas-maquininha-13].
> - **Another bank account:** If you aren't eligible for Get Conta, you can name another bank account in Getnet's digital channels. You stay eligible for the offer's discounts [prod-ofertas-maquininha-13].
>
> Pix receipt time can vary by up to one calendar day. It depends on the Pix model you're eligible for and on the time the sale is approved [prod-pix-01].
>
> The sources don't say whether you can receive Pix sales with no account at all. I can hand your case to a human agent if you'd like that confirmed.

**Passos:**

1. **faq** · partial · motivo `partial_coverage` · 7884 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/pix/>; <https://site.getnet.com.br/pix/>; <https://site.getnet.com.br/todas-as-maquininhas/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-05

**Pergunta:** My card machine won't connect to the internet, what should I do?

**Intenção:** troubleshoot (esperada troubleshoot) · **rota:** router → records → faq · **replanos:** ['records:need->faq (terminal offline/sem sinal: o passo a passo vem do manual de conexão)'] · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0583 · **latência:** 17.9 s

**Resposta:**

> Your terminal T1988B (Get Clássica) is the one that's offline. It connects by chip, shows no signal, and has been offline for 5 hours. Your other terminal, T1988A, is online.
>
> For T1988B, the sources give these chip steps:
> - Turn the machine off by pressing the "." key and the yellow key together for 2 seconds [sup-duvidas-66]. Then open the cover on the back [sup-duvidas-06].
> - Put the chip in the slot marked SIM1 or SIM2, with the metal side facing down [sup-duvidas-06].
> - Close the cover and turn the machine on. Wait for the data network to connect [sup-duvidas-06].
> - When it shows a connected network (2G or 3G), it's ready to use. Then run a communication test [sup-duvidas-06].
> - You can download the user manual for your model [sup-manual-maquinas-01].
>
> I can propose a technical support ticket for T1988B with the reason "sem_sinal" or "sem_conexao". Nothing is opened until you confirm, and the proposal expires after 15 minutes. Do you want me to propose it?
>
> The sources don't cover Wi-Fi setup, tips for improving signal, or the steps of the communication test. I can also hand your case to a human agent if you'd like.

**Passos:**

1. **records** · ok · 3141 ms · decidido por: supervisor LLM (tool call)
   - `get_terminal_status` {} → ok · `{"ok": true, "data": {"items": [{"terminal_id": "T1988A", "model": "Get Smart", "connection": "Wi-Fi", "status": "online", "signal": "bom",…`
2. **faq** · partial · motivo `partial_coverage` · 4464 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/todas-as-maquininhas/>; <https://site.getnet.com.br/boas-vindas/manual-maquinas/>; <https://site.getnet.com.br/duvidas/get-smart/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'tools': True, 'numbers': True, 'claims': True, 'completed': True, 'facts': True, 'resolved': True}

## official-06

**Pergunta:** How does receivables advance (antecipação) work with Getnet?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0291 · **latência:** 10.8 s

**Resposta:**

> You can advance your sales in the Getnet Brasil app, which is always available for that, and the app has no extra fees [sup-duvidas-17].
>
> - **Automatic Advance (Antecipação Automática):** If you choose the "Receba Conforme suas Vendas" receiving plan, this is a condition for getting the exemption. It involves a credit approval process, and Getnet evaluates each contract individually to decide whether to grant it [sup-duvidas-102].
> - **Through me:** I can propose a request to advance your scheduled receivables. You would have to confirm it, and then a human agent would have to approve it before it runs. Nothing has been requested yet.
>
> The sources I found don't give the advance fee or rate, the payout timing, or the step-by-step process. A human agent can help with those if you'd like.

**Passos:**

1. **faq** · partial · motivo `partial_coverage` · 4085 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://site.getnet.com.br/get-ajuda-reserva-financeira/antecipacao-reserva-financeira/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/get-ajuda-reserva-financeira/antecipacao-reserva-financeira/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/crediario/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-07

**Pergunta:** What's the euro exchange rate today?

**Intenção:** general (esperada general) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0195 · **latência:** 8.1 s

**Resposta:**

> There's no euro quote for today (Wednesday, 11/04/2026). The latest one is from the last business day, 11/03/2026. On that date, the Banco Central do Brasil (PTAX) closing rate was 1 EUR = R$ 6.1482 (buy) and R$ 6.1500 (sell).
>
> Source: https://www.bcb.gov.br/estabilidadefinanceira/historicocotacoes

**Passos:**

1. **faq** · ok · 3217 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://www.bcb.gov.br/estabilidadefinanceira/historicocotacoes>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-08

**Pergunta:** My card machine is showing a transaction decline error.

**Intenção:** troubleshoot (esperada troubleshoot) · **rota:** router → records → faq · **replanos:** ['records:need->faq (transação recusada: a orientação vem do Knowledge; terminal offline/sem sinal: o)'] · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0797 · **latência:** 23.5 s

**Resposta:**

> You have 2 declined transactions in the last 7 days (R$ 285,00 in total). Only one of them points to a terminal problem.
>
> - **TX1007** (credit, R$ 210,00, terminal T1988A): code 51 means insufficient funds or credit limit on the customer's card. Ask for another card or payment method. T1988A is online with good signal, so this isn't a terminal problem.
> - **TX1008** (debit, R$ 75,00, terminal T1988B): code 05 means the issuing bank did not authorize the transaction. The cardholder should contact their bank or try another card. T1988B is offline with no signal. It has been offline for 5 hours, and its last contact was 2026-11-03 23:18.
>
> **Chip connection steps for T1988B** [sup-duvidas-06]:
> 1. Turn the machine off and open the back cover.
> 2. Insert the chip in the slot marked SIM1 or SIM2, with the metal side facing down.
> 3. Close the cover, turn the machine on and wait for it to connect to the data network.
> 4. When it shows a connected network (2G or 3G), it is ready to use.
> 5. Run a communication test to check the chip's connectivity.
>
> The sources don't give Wi-Fi or other signal steps for an offline terminal.
>
> I can propose a support ticket for T1988B (reason: sem_sinal). Nothing runs until you confirm, and the proposal expires after 15 minutes. Do you want me to propose it? I can also hand your case to a human agent.

**Passos:**

1. **records** · ok · 4160 ms · decidido por: supervisor LLM (tool call)
   - `get_transactions` {"status": "declined", "period": "last_7_days"} → ok · `{"ok": true, "data": {"items": [{"transaction_id": "TX1007", "method": "credito", "status": "recusada", "amount": 210.0, "decline_code": "5…`
   - `get_terminal_status` {} → ok · `{"ok": true, "data": {"items": [{"terminal_id": "T1988A", "model": "Get Smart", "connection": "Wi-Fi", "status": "online", "signal": "bom",…`
2. **faq** · partial · motivo `partial_coverage` · 8257 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://site.getnet.com.br/todas-as-maquininhas/>; <https://site.getnet.com.br/get-tap/>; <https://site.getnet.com.br/todas-as-maquininhas/>; <https://site.getnet.com.br/ofertas-maquininha-de-cartao-getnet-2/>; <https://site.getnet.com.br/get-tap/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'tools': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-09

**Pergunta:** How many installments can I split a sale into with the crediário?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0267 · **latência:** 9.1 s

**Resposta:**

> With the Crediário, you can split a sale into up to 48 installments on a credit card [prod-crediario-03][prod-crediario-01]. Interest rates may vary depending on the card issuer [prod-crediario-03].
>
> However many installments you choose, you receive the sale in a single payment within 2 business days after the transaction is captured. The discount fee (MDR) is deducted from that payment [sup-duvidas-39]. You can check your MDR in the Getnet Brasil app or the Customer Portal [prod-crediario-03].

**Passos:**

1. **faq** · ok · 4104 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://site.getnet.com.br/crediario/>; <https://site.getnet.com.br/crediario/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/duvidas/>; <https://site.getnet.com.br/link-de-pagamento/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}

## official-10

**Pergunta:** Can I sell through WhatsApp using the Payment Link?

**Intenção:** knowledge (esperada knowledge) · **rota:** router → faq · **replanos:** nenhum · **caminho:** supervisor LLM (laço de tool use) · **custo:** US$ 0.0293 · **latência:** 10.2 s

**Resposta:**

> Yes, you can sell through WhatsApp with the Payment Link. It's meant for WhatsApp, social media and remote charges, including if you don't have your own website. You create the link, send it to your customer, and receive the payment [prod-pagamentos-pelo-whatsapp-02].
>
> - **Payment methods:** Customers can pay by card, Pix or debit [prod-pagamentos-pelo-whatsapp-02]. Another page also lists credit, Wallet and boleto [prod-link-de-pagamento-01].
> - **Initial link:** R$1,00 per paid link. You pay only when the payment is approved [prod-link-de-pagamento-02].
> - **Basic plan:** R$28 per month. It includes 60 card transactions per month, plus R$0,50 for each extra transaction [prod-link-de-pagamento-02].

**Passos:**

1. **faq** · ok · 4802 ms · decidido por: supervisor LLM (tool call)

**Fontes:** <https://site.getnet.com.br/pagamentos-pelo-whatsapp/>; <https://site.getnet.com.br/link-de-pagamento/>; <https://site.getnet.com.br/pagamentos-pelo-whatsapp/>; <https://site.getnet.com.br/link-de-pagamento/>; <https://site.getnet.com.br/ofertas-maquininha-de-cartao-getnet-2/>
**Checagens:** {'intent': True, 'route': True, 'handoff': True, 'handoff_outcome': True, 'language': True, 'numbers': True, 'claims': True, 'facts': True, 'resolved': True}
