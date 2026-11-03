# Spec — Getnet Multi-Agent Support

Commitada antes de qualquer código. Congelada (OWNERSHIP.json): mudança aqui é decisão da sessão principal.

## Problema
Lojistas da Getnet perguntam, em português ou inglês, sobre produtos (maquininhas, Pix, antecipação, crediário,
Link de Pagamento), sobre os próprios dados (vendas, depósitos, terminais, recusas) e sobre assuntos gerais (clima,
câmbio). Um Router decide quem atende; o Knowledge responde com RAG sobre o site oficial da Getnet (mais busca web
para o geral); o Support lê o dado do cliente por ferramentas; um humano entra só quando nada resolve.

## Requisitos

| ID | Requisito (do enunciado) | Módulo | Teste / eval |
|---|---|---|---|
| FR-01 | Router: entrada única, decide agente ou sequência | `src/app/router.py`, `domain/challenge/flow.py` | `tests/test_domain_router.py` |
| FR-02 | Knowledge: RAG sobre o site da Getnet + busca web para o geral | `src/app/rag.py`, `data/sources.json` | `scripts/official_check.py` |
| FR-03 | Support: lê o dado do cliente, ≥ 2 tools | `domain/challenge/tools.py` | `tests/test_tools.py` |
| FR-04 | `POST /chat` com `{message, user_id}` → JSON | `src/app/api.py` | `tests/test_domain_http.py` |
| FR-05 | 4º agente: escalonamento humano que volta ao fluxo | `src/app/cases.py` | `tests/test_hitl*.py` |
| NFR-01 | Sobe com um comando (Docker) | `Dockerfile` | `scripts/check.py --docker` |
| NFR-02 | Funciona sem chave de LLM (modo offline) | `config.py` | CI |
| NFR-03 | Identidade: `AUTH_MODE` demo (ADR 0001); `user_id` do corpo só vale em demo | `api.py` | `tests/test_auth_modes.py` |

## Taxonomia (intenções → plano)

| intenção | plano | quando |
|---|---|---|
| `knowledge` | faq | produto, taxa, prazo, regra da Getnet (fonte: site oficial) |
| `general` | faq (dado ao vivo: clima Open-Meteo, câmbio PTAX/BCB; senão busca web) | fora da Getnet mas inofensivo; NUNCA escala |
| `support` | records | dado do próprio cliente: vendas, depósitos, agenda, transações, terminais |
| `troubleshoot` | records → faq (`needs`) | sintoma na maquininha: lê o terminal/transação do cliente e depois o manual do Knowledge |
| `multi` | faq ‖ records | duas perguntas independentes no mesmo turno |
| `human_request` | escalation | pede pessoa explicitamente |

**Desempates** (as 3 fronteiras que derrubaram a V5, N4):
1. Sintoma ("não conecta", "erro", "recusa", "won't", "decline", "offline") com maquininha → `troubleshoot`, mesmo com
   "minha"; `support` é só consulta de dado sem sintoma.
2. Duas perguntas com assuntos diferentes (produto + dado meu) → `multi`; duas sobre o mesmo produto → `knowledge`.
3. "Como funciona X" / "preciso de Y" sobre produto → `knowledge`, mesmo com "eu"/"minha loja".
4. Clima, câmbio, cotação, notícia → `general` (nunca humano, nunca "sem fonte" da Getnet).

## Resposta parcial
O Knowledge tem três estados: `ok`, `partial` (responde o que a fonte cobre e diz o que falta; **não escala**),
`insufficient` (nada coberto → humano). Nos oficiais, `expect.handoff: false` em todos: a fonte cobre ao menos o
fato de referência. Exemplos de parcial aceitável: official-01 (preços e recursos; se faltar um recurso, diz qual);
official-06 (modalidades de antecipação; taxa exata depende do contrato → diz que depende).

## Memória: pergunta autônoma (`standalone`)
O router reescreve o turno de seguimento como pergunta completa e autônoma, no idioma do cliente, em
`ctx.facts["standalone"]`; o Knowledge busca com ela. Demonstrativo/elipse = entidade da ÚLTIMA resposta:
"e a outra?" depois de Get Smart × Get Clássica = a outra maquininha citada; "and the other terminal?" = o outro
terminal do cliente; "how long has it been down?" = o terminal offline citado; "e qual foi o valor dela?" = a
transação citada. Seguimento curto herda a intenção do turno anterior (N5). Vazia se reescrever exigiria inventar.

## Ferramentas (nomes congelados, frente T)
Leitura: `get_settlements` (agenda de depósitos com datas e total calculados), `get_transactions` (vendas e
recusas, com o significado do código de recusa), `get_terminal_status` (terminais do cliente: conexão, sinal,
último contato; emite `needs` do manual quando offline). Escrita com confirmação: `request_receivables_advance`
(`risk: high`), `open_support_ticket`. Identidade vem do servidor, nunca do schema.

## Cenários de aceite (copiados do enunciado, um por linha)

| ID | Mensagem | Esperado (intent / rota / ferramenta / handoff) | Fato de referência (`expect.facts`) |
|---|---|---|---|
| official-01 | What's the difference between the Get Clássica and the Get Smart? | knowledge / faq / — / não | preços `79,90` e `129,90` |
| official-02 | What's the weather forecast in Porto Alegre tomorrow? | general / faq (Open-Meteo) / — / não | número da API com data |
| official-03 | When will the money from yesterday's sales be deposited? | support / records / get_settlements / não | datas e total da tool |
| official-04 | Do I need a bank account to receive my sales via Pix? | knowledge / faq / — / não | conta corrente/poupança/pagamento ou Get Conta |
| official-05 | My card machine won't connect to the internet, what should I do? | troubleshoot / records→faq / get_terminal_status / não | passo de chip / Wi-Fi do manual |
| official-06 | How does receivables advance (antecipação) work with Getnet? | knowledge / faq / — / não | antecipação automática / pontual |
| official-07 | What's the euro exchange rate today? | general / faq (PTAX) / — / não | cotação do BCB com data |
| official-08 | My card machine is showing a transaction decline error. | troubleshoot / records→faq / get_transactions / não | código de recusa e significado da tool |
| official-09 | How many installments can I split a sale into with the crediário? | knowledge / faq / — / não | `48x` |
| official-10 | Can I sell through WhatsApp using the Payment Link? | knowledge / faq / — / não | WhatsApp |

Cada AC vira um caso `official-NN` em `evals/cases.jsonl`. Respostas no idioma da pergunta (todas en).

## Fora de escopo
- Pagamento real, alteração de cadastro bancário, dado de cartão do portador.
- Cotação/clima sem API oficial: diz que não confirmou, nunca inventa número.

## Divisão em forks

Ver OWNERSHIP.json. Contrato: `src/app/schemas.py` (inclui `RouterDecision` e `AgentName`), assinatura de
`pipeline.handle(req, user_id, identity_verified)` e status `ok|partial|insufficient|error` dos agentes.

## Dados do cliente de teste (contrato da frente T; os casos citam estes ids)
`cliente1988`: terminais `T1988A` (Get Smart, online, Wi-Fi) e `T1988B` (Get Clássica, offline, chip, sem sinal);
vendas de ontem em débito, crédito e Pix com agenda de depósito; recusas `TX1007` (crédito, R$ 210,00, código 51)
e `TX1008` (débito, R$ 75,00, código 05). Segundo cliente `cliente2024` (isolamento: o dado de um nunca aparece ao
outro; registro alheio = "não encontrado"). Datas relativas a hoje.

## Casos além dos oficiais (evals/cases.jsonl)
replan 20 (12 sem fonte → humano; 8 terminal/recusa → manual), dependent 11 (records + faq), parallel 4,
approval 4 (escrita fica pendente de confirmação), memory 16 (com `standalone` e `expects_fact`).
