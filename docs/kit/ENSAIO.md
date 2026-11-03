# Ensaio geral (PLAYBOOK §7)

Uma tentativa completa, com relógio, num desafio INVENTADO, num repositório descartável. Serve para medir os
tempos reais de cada marco, o limite de uso da conta com 7 sessões e a gravação do vídeo na nuvem. Nada do que
for escrito aqui pode ser reaproveitado na tentativa real: o domínio é outro de propósito.

## Como rodar

Pelo **Chrome**, numa aba só em claude.ai/code, seguindo [CHROME.md](CHROME.md) §3 (ensaio reduzido: sessão
principal em Opus + frentes R e K em Sonnet, 30 minutos, eval ao vivo de 1 split no PowerShell). No prompt da
sessão principal (PROMPTS.md, bloco M) troque `<<ENUNCIADO>>` pelo enunciado abaixo, `<<RÉGUA>>` pela régua V4
e `<<URL DO SITE DA EMPRESA>>` por `https://www.bcb.gov.br/`, e acrescente: "o kit está em
maathmartins-ux/kit-preflight, branch kit-v3.7.0: anexe esse repositório (add_repo) e copie o conteúdo".

## Enunciado do ensaio (inventado)

> **Desafio — Sistema multiagente de atendimento sobre Pix**
>
> Uma fintech fictícia, a **PagaJá**, atende clientes que usam Pix. Construa um sistema com pelo menos três
> agentes que cooperam:
>
> 1. **Router**: ponto de entrada de toda mensagem; decide qual agente (ou sequência) atende e gerencia o
>    fluxo de dados entre eles.
> 2. **Knowledge Agent**: responde dúvidas sobre o Pix com RAG sobre as páginas públicas do Pix no site do
>    Banco Central (`https://www.bcb.gov.br/estabilidadefinanceira/pix` e páginas ligadas), e usa busca na web
>    para perguntas gerais (clima, câmbio, notícias).
> 3. **Customer Support Agent**: responde sobre os dados do PRÓPRIO cliente da PagaJá com pelo menos duas
>    ferramentas (ex.: extrato de Pix, limites, chaves cadastradas, contestação via MED com confirmação).
>
> Exponha `POST /chat` com o corpo `{"message": "...", "user_id": "..."}` e resposta JSON útil. Entregue Docker,
> estratégia de testes e um README que explique como construir, rodar e testar, a arquitetura, o fluxo de uma
> mensagem, o RAG (ingestão → armazenamento → busca → geração) e como o LLM foi usado.
>
> Bônus: 4º agente de escalonamento humano, guardrails, handoff quando não houver confiança, avaliação e
> observabilidade. Grave um vídeo curto explicando a solução.
>
> Cenários de exemplo (`user_id` = `cliente7`):
> 1. Qual o limite do Pix no período noturno?
> 2. What's the weather forecast in Recife tomorrow?
> 3. Quanto eu mandei de Pix ontem?
> 4. Como funciona o MED (Mecanismo Especial de Devolução)?
> 5. Fiz um Pix para a pessoa errada, o que eu faço?
> 6. What is the dollar exchange rate today?
> 7. Quais chaves Pix eu tenho cadastradas?
> 8. Can I schedule a Pix for next week?
> 9. Meu Pix não chegou e o dinheiro saiu da conta.
> 10. Quero aumentar meu limite noturno para R$ 5.000.

## Depois do ensaio

- Anote os tempos reais no PLAYBOOK §7 e o gasto de US$ (console da Anthropic, "Gasto este mês").
- Rode o balanço no repositório do ensaio e corrija o kit ANTES da tentativa real.
- Apague ou arquive o repositório `ensaio-kit-v37`.
