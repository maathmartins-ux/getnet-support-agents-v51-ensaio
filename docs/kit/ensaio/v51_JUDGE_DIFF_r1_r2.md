# Juiz: antes × depois por caso

A = `evals/results/judge_r1.json` · B = `evals/results/judge.json`. Gerado por `python -m evals.judge_diff`; grounded e failure_type são do juiz (evals/judge.py), o motivo é o de B (ou o de A, se B não tem o caso).

| split | grounded A | grounded B | melhorou | piorou |
|---|---|---|---:|---:|
| memory | 36/39 (92%) | 31/39 (79%) | 3 | 8 |
| official | 28/30 (93%) | 29/30 (97%) | 2 | 1 |

| caso | rodada | grounded A → B | failure_type A → B | mudança | motivo |
|---|---:|---|---|---|---|
| q-mem-01 | 0 | sim → sim | none → none | igual | Com hoje = 02/11, anteontem é 31/10, e a resposta acerta a única venda dessa data: TX1004, crédito, R$ 350,00, previsão 30/11, status previsto. A menção extra … |
| q-mem-01 | 1 | sim → sim | none → none | igual | Hoje é 02/11, então anteontem é 31/10. A única venda dessa data é a TX1004 (crédito, R$ 350,00, previsão 30/11, status previsto), e a resposta a reproduz corre… |
| q-mem-01 | 2 | sim → sim | none → none | igual | Com hoje em 2026-11-02, anteontem é 31/10. A ferramenta mostra uma única venda nessa data: TX1004, no crédito, R$ 350,00, status previsto, depósito em 30/11. I… |
| q-mem-02 | 0 | sim → sim | none → none | igual | The answer matches the data exactly. Today is 2026-11-02, so the day before yesterday is 31/10, which has a single sale: TX1004, credit, 350, expected 30/11. T… |
| q-mem-02 | 1 | sim → sim | none → none | igual | Today is 11/02, so "the day before" yesterday is 10/31. The answer gives TX1004 correctly: credit, R$350.00, expected deposit 11/30, status expected. The extra… |
| q-mem-02 | 2 | sim → sim | none → none | igual | The day before yesterday is 2026-10-31. The tool data shows exactly one sale that day: TX1004, credit, R$350.00, expected deposit 2026-11-30, status previsto. … |
| q-mem-03 | 0 | sim → sim | none → none | igual | Os dados da T1988A (Wi-Fi, sinal ok, online, 2 min, bobina ok, sem bloqueio) e da T1988B (offline, sem sinal, 190 min) batem com a ferramenta. A proposta de re… |
| q-mem-03 | 1 | sim → sim | none → none | igual | Todos os dados das duas maquininhas (conexão, sinal, online, último contato, bobina, bloqueio) conferem com get_terminal_status. A oferta de reinício remoto e … |
| q-mem-03 | 2 | **não** → sim | unsupported_claim → none | melhorou | Todos os dados das duas maquininhas (modelo, conexão, sinal, online, último contato, bobina, bloqueio) batem com get_terminal_status. A proposta de reinício e … |
| q-mem-04 | 0 | sim → sim | none → none | igual | Every detail about T1988A (Wi-Fi, good signal, online, last contact 2 min, paper roll OK, not blocked) and T1988B (chip, no signal, 190 min) matches the tool d… |
| q-mem-04 | 1 | sim → sim | none → none | igual | The terminal data supports every claim: T1988A is online with an OK signal, a 2-minute last contact, an OK paper roll and no block. T1988B is offline on chip w… |
| q-mem-04 | 2 | sim → sim | none → none | igual | Every detail for T1988A and T1988B matches the terminal data. The restart proposal and the handoff to a human agent are both listed in the capabilities policy.… |
| q-mem-05 | 0 | sim → sim | none → none | igual | All three claims match the source: free rental above R$ 20 mil/month, R$ 79,90/month below that, and Voucher/Crediário sales not counting toward the exemption.… |
| q-mem-05 | 1 | sim → sim | none → none | igual | A resposta se apoia inteiramente nas fontes: isenção acima de R$ 20 mil/mês, R$ 79,90/mês caso o faturamento não seja atingido, e a exclusão de Voucher (VA/VR)… |
| q-mem-05 | 2 | sim → sim | none → none | igual | The figures (R$ 20 mil for the waiver, R$ 79,90/mês, voucher/crediário not counting) match the first source. The answer openly admits it lacks information on h… |
| q-mem-06 | 0 | sim → sim | none → none | igual | Every claim is supported by the sources: free above R$ 20k/month, the choice of Get Clássica or Get Smart at higher volumes, the R$ 79,90/month usage fee, the … |
| q-mem-06 | 1 | sim → sim | none → none | igual | The R$ 79,90/month fee, the R$ 20 mil and R$ 40 mil thresholds and the VA/VR and Crediário exclusion all match the sources. Offering a human handoff is support… |
| q-mem-06 | 2 | sim → sim | none → none | igual | Every figure and condition matches the sources: the rental waiver above R$ 20 mil, the Clássica or Smart choice at R$ 40 mil and R$ 80 mil, the voucher and cre… |
| q-mem-07 | 0 | sim → **não** | none → unsupported_claim | piorou | The values (sell R$ 5,4212, buy R$ 5,4206), the date 30/10/2026, the missing bulletin on 02/11 and the rounding all match the sources, and the response correct… |
| q-mem-07 | 1 | sim → **não** | none → unsupported_claim | piorou | Os valores (venda R$ 5,4212, compra R$ 5,4206, arredondado R$ 5,42) e as datas batem com as fontes. A resposta também deixa claro que 02/11/2026 não teve bolet… |
| q-mem-07 | 2 | sim → **não** | none → unsupported_claim | piorou | The quotes (5,4212 sell / 5,4206 buy) and the date framing match the sources: no bulletin on 02/11, so the last close is 30/10. The response also gives a speci… |
| q-mem-08 | 0 | sim → **não** | none → unsupported_claim | piorou | The rates (sell 5.4212, buy 5.4206, ~R$ 5.42) and the 10/30 Friday date match the sources, and the answer is in English like the question. However, the cited b… |
| q-mem-08 | 1 | sim → **não** | none → unsupported_claim | piorou | The rates (sell 5.4212, buy 5.4206, ≈R$ 5.42), the 10/30 date and the note that there was no quote today all match the PTAX sources, and the answer is in Engli… |
| q-mem-08 | 2 | sim → sim | none → none | igual | The answer is in English, like the question. The PTAX closing rate of 10/30/2026 (sell 5.4212, buy 5.4206, about R$ 5.42) matches the sources. It correctly say… |
| q-mem-09 | 0 | sim → sim | none → none | igual | Every TX1008 detail (date, debit, R$ 75,00, declined, code 05 by the issuer, not contestable) and every T1988A detail matches the tool data. 'Também' is suppor… |
| q-mem-09 | 1 | sim → **não** | none → stale_source | piorou | The TX1008 details (R$ 75,00 no débito, 02/11/2026, código 05, não autorizada pelo emissor, não contestável) and the T1988A status match the tool data. However… |
| q-mem-09 | 2 | sim → sim | none → none | igual | Todos os dados da TX1008 conferem com get_transactions: R$ 75,00 no débito em 02/11, recusada, código 05 (não autorizada pelo emissor), não contestável. O esta… |
| q-mem-10 | 0 | **não** → sim | unsupported_claim → none | melhorou | Every figure and fact matches the tool data: the R$ 285,00 total calculated in code, both decline codes and reasons, T1988A's status, non-contestability, and T… |
| q-mem-10 | 1 | sim → sim | none → none | igual | The answer gives the codes and reasons for both declines exactly as the get_transactions data shows. The terminal status matches get_terminal_status, and the s… |
| q-mem-10 | 2 | sim → **não** | none → unsupported_claim | piorou | Os códigos e motivos de TX1007 e TX1008 batem com os registros, e a restrição a contestar recusas consta da política. Porém, a resposta afirma que a maquininha… |
| q-mem-11 | 0 | sim → sim | none → none | igual | A resposta repete com fidelidade a previsão do Open-Meteo para Curitiba em 03/11/2026: 77% de chance de chuva, pancadas, mínima de 16,0 °C e máxima de 27,7 °C.… |
| q-mem-11 | 1 | sim → sim | none → none | igual | A resposta segue a previsão Open-Meteo para Curitiba em 03/11/2026: pancadas de chuva com até 77% de chance e temperaturas entre 16 °C e 28 °C, conforme os val… |
| q-mem-11 | 2 | sim → **não** | none → stale_source | piorou | The answer gives a 15°C minimum for Curitiba but cites old sources as current: SIMEPAR is from 17 days ago, and the INMET page is dated 20/10/2026 (41 days ago… |
| q-mem-12 | 0 | **não** → sim | stale_source → none | melhorou | The answer is in English, matching the question. It admits it couldn't confirm the forecast details instead of inventing numbers, and its only substantive clai… |
| q-mem-12 | 1 | sim → sim | none → none | igual | The reply makes no factual weather claims and honestly declines, so it is grounded. It is in English, matching the question. It is not helpful: a source dated … |
| q-mem-12 | 2 | sim → sim | none → none | igual | The reply makes no unsupported claims. It only declines to confirm and points to the INMET forecast page, which matches the INMET Curitiba source. However, sev… |
| q-mem-13 | 0 | sim → sim | none → none | igual | A resposta diz corretamente que as fontes não falam do Crediário pelo Link de Pagamento. Os custos do Link (plano mais taxa conforme parcelas e prazo) e os 48x… |
| q-mem-13 | 1 | sim → sim | none → none | igual | The sources do not say how many installments are allowed on the Link de Pagamento. The response admits this without inventing a number and hands off to a human… |
| q-mem-13 | 2 | sim → sim | none → none | igual | As fontes não dizem quantas parcelas o crediário permite pelo Link de Pagamento, e a resposta admite isso sem inventar número. O encaminhamento para humano com… |
| official-01 | 0 | sim → sim | none → none | igual | Every claim matches the sources: the Get Smart's Android features and NF-e caveat, the R$ 79,90 and R$ 129,90 monthly fees, and the free-machine sales tiers. T… |
| official-01 | 1 | sim → sim | none → none | igual | Every claim matches the sources: the free-machine thresholds, the R$ 79,90 and R$ 129,90 monthly fees, the voucher/crediário exclusion, the Android features an… |
| official-01 | 2 | sim → sim | none → none | igual | The answer matches the sources. Prices are R$ 79,90 and R$ 129,90, free from above R$ 20k for the Clássica and above R$ 40k for the Smart, and Voucher/Crediári… |
| official-02 | 0 | **não** → sim | unsupported_claim → none | melhorou | Every figure matches the sources: the rounded low and high of 18 and 29 °C, the 53% rain chance, drizzle, and the date of Tuesday 2026-11-03. The answer is in … |
| official-02 | 1 | sim → sim | none → none | igual | The answer matches the Open-Meteo forecast for 2026-11-03, which is tomorrow given today is 2026-11-02 (Monday). It correctly gives Tuesday, the rounded low of… |
| official-02 | 2 | sim → sim | none → none | igual | The answer matches the sources. The rounded low (18 °C) and high (29 °C) are given in the sources, as are the 53% rain chance and the drizzle. The date is corr… |
| official-03 | 0 | **não** → sim | invented_number → none | melhorou | Every amount and date matches the get_settlements data: the R$ 745,50 total, the four transactions, R$ 265,50 on 03/11 (R$ 205,50 debit plus R$ 60 Pix), R$ 480… |
| official-03 | 1 | sim → sim | none → none | igual | Every amount, date and total matches the tool data and the code-computed sums (745.50 total; 265.50 on 03/11; 480.00 on 01/12). The answer correctly flags that… |
| official-03 | 2 | sim → sim | none → none | igual | Every amount, date, and total matches the settlement data and the code-calculated sums, including R$ 265,50 on 03/11, R$ 480,00 on 01/12, and R$ 1.730,00 avail… |
| official-04 | 0 | sim → sim | none → none | igual | The answer correctly says a receiving bank account is needed. Per the sources, eligibility requires a Santander bank domicile and an active Pix key, and only o… |
| official-04 | 1 | sim → sim | none → none | igual | Each claim matches the sources: a Santander bank domicile with an active Pix key is required for eligibility, a single Pix key linked to the receiving account … |
| official-04 | 2 | sim → sim | none → none | igual | Every claim is backed by the sources: the Santander bank domicile, the active Pix key, and the single key linked to the receiving account. The offer to hand th… |
| official-05 | 0 | sim → sim | none → none | igual | The terminal details for T1988B (offline, chip, no signal, 190 min, not blocked) and T1988A (online, Wi-Fi) match the tool data. The steps for reseating the ch… |
| official-05 | 1 | sim → sim | none → none | igual | Every terminal detail matches the tool data. T1988B is offline on chip with no signal: last contact 190 min, not blocked, paper roll ok. T1988A is online over … |
| official-05 | 2 | sim → sim | none → none | igual | The terminal details match the tool data: T1988B is chip-connected with no signal, last contact 190 min ago, not blocked, paper roll OK, and T1988A is online o… |
| official-06 | 0 | sim → sim | none → none | igual | Every claim is supported by the sources: what an advance is, the app path, and the Santander channels. The request flow (whole available balance or a specific … |
| official-06 | 1 | sim → sim | none → none | igual | The response is in English and matches the sources: early receipt of credit sales (single and installment), the app path depending on segment and profile, and … |
| official-06 | 2 | sim → sim | none → none | igual | All claims are backed by the sources. These cover what an advance is, the app path and the Santander channels. The response correctly says fees and deadlines a… |
| official-07 | 0 | sim → sim | none → none | igual | The answer correctly says there was no quote on Monday, 2026-11-02, and gives the latest PTAX closing rate from Friday, 2026-10-30. The sell rate (R$ 6.0522), … |
| official-07 | 1 | sim → sim | none → none | igual | The rates (6.0522 sell, 6.0505 buy), the 30/10/2026 PTAX closing date and the note that 02/11 had no bulletin all match the sources. The answer is in English, … |
| official-07 | 2 | sim → **não** | none → unsupported_claim | piorou | The rates (sell 6.0522, buy 6.0505), the Oct 30 date, the note that there was no bulletin on Nov 2, and the rounding all match the sources, and the answer is i… |
| official-08 | 0 | sim → sim | none → none | igual | Every claim matches the tool data. TX1007 was R$210 on credit with code 51 (insufficient balance), and TX1008 was R$75 on debit with code 05 (not authorized by… |
| official-08 | 1 | sim → sim | none → none | igual | The transaction details (amounts, codes, reasons, non-contestable status) and the terminal status for both terminals match the tool data. Attributing the decli… |
| official-08 | 2 | sim → sim | none → none | igual | The terminal and transaction details match the tool data. It is reasonable to attribute the declines to the issuer: code 51 is the cardholder's insufficient ba… |
| official-09 | 0 | sim → sim | none → none | igual | Every claim in the answer is backed by the sources. The 48x figure with an asterisk comes from the product page. The issuer limit, the simulation steps on the … |
| official-09 | 1 | sim → sim | none → none | igual | The question is in English and the answer is in English. Every claim is supported by the sources: up to 48x with an asterisk, issuers setting the installment l… |
| official-09 | 2 | sim → sim | none → none | igual | Every claim is backed by the sources. The answer gives up to 48 installments, notes that the asterisk means unspecified conditions, explains that each issuer s… |
| official-10 | 0 | sim → sim | none → none | igual | Every claim is supported by the sources: sharing via WhatsApp, social networks, email and SMS; selling from anywhere; and the step-by-step instructions for cre… |
| official-10 | 1 | sim → sim | none → none | igual | Every claim is backed by the sources. WhatsApp sharing, the debit/credit choice and the step-by-step creation flow all appear there, and the menu names are kep… |
| official-10 | 2 | sim → sim | none → none | igual | Every claim is supported by the sources. The sources state the link can be sent via WhatsApp, social networks, email and SMS, and that the customer clicks the … |
