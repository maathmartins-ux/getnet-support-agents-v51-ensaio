# Prompts das frentes (kit v5.3) — a sessão principal (M) usa como subagentes

A M dispara cada frente com a ferramenta **Agent** (em segundo plano), depois de criar o worktree:
`git worktree add -b fork/<x> ../<repo>-<x> main`. O prompt de cada subagente = **bloco comum** + **bloco da
frente** + a SPEC inteira no lugar de `<<SPEC>>`. O dono não cola nada (v4: subagentes aceitaram todas as
tarefas; na v3 sessões-irmãs criadas por outra sessão recusaram). A K sai no T+4 só com os casos oficiais; as
outras no T+8 com a SPEC inteira (PLAYBOOK §2).

## Contratos que a SPEC grava ANTES do código (todas as frentes leem; ninguém muda depois de ver a medida)

- **Caso oficial**: `expect.facts` = lista de regex sem caixa, uma por fato de referência, que casa a RESPOSTA e o
  TRECHO da fonte (número, nome, alternância pt|en: `48\s*x|48 (parcelas|installments)`; nunca a frase inteira);
  `expect.entities` = produtos citados no cenário (`["Get Clássica", "Get Smart"]`). `scripts/official_check.py`
  reprova entidade sem trecho ingerido e fato fora do top-5 do buscador ativo.
- **Seguimento** (memory, "e a outra?"): `standalone` = a pergunta reescrita completa e autônoma, no idioma do
  cliente; o router a produz em `ctx.facts["standalone"]` e o Knowledge busca com ela (vazia se a reescrita for
  recusada).
- **Resposta parcial**: o Knowledge tem três estados — `ok` (completa), `partial` (responde o que a fonte cobre e diz o
  que falta; NÃO escala por si), `insufficient` (nada coberto). A SPEC diz, por oficial, o que é parcial aceitável;
  `expect.handoff: false` quando a fonte cobre parte.

---

## Bloco comum (todas as frentes)

```text
Você é a frente <<LETRA>> de uma tentativa cronometrada (58 min no total; a sua parte termina em ~8–10 min).
Trabalhe SÓ no worktree <<CAMINHO DO WORKTREE>> (branch fork/<<LETRA>>) e SÓ nos arquivos da frente <<LETRA>> em
OWNERSHIP.json; o gancho recusa o resto e o motor (src/app/*.py) é congelado. Responda em português.

Ambiente: na raiz do worktree, `export PYTHONPATH=$PWD/src` antes de rodar Python (a venv pode apontar para outro
repo). Antes de CADA commit: `python scripts/fork_check.py <<LETRA>>` (segundos) e só commite se der VERDE.
Commits PEQUENOS, um por item entregue, com o número medido na mensagem (o avaliador lê a cadência do git log;
um commit gigante no fim parece pré-fabricado). Não faça push: a sessão principal integra pelo git local.
Último commit: "fork <<LETRA>>: pronto (<números>)". Depois devolva um relatório de até 10 linhas.

Nunca: editar o motor, baixar o gate, abrir evals/heldout_blind.jsonl, escrever número não medido, usar
example.com (use um domínio fictício próprio), escrever resposta pronta no código para um cenário ("atalho em vez
de arquitetura" é o que o avaliador mais pune).

SPEC (congelada; dúvida vira suposição escrita no commit, não pergunta):
<<SPEC>>
```

## R — roteamento e orquestração

```text
Entrega: src/app/domain/challenge/flow.py (taxonomia, PLANS, FALLBACK, ALLOWED, DEPENDS, NO_ESCALATION,
DEFAULT_INTENT, MULTI_PARTS, clause_intent, combine, states_subject) com os DESEMPATES da SPEC; prompts router.md
(com `standalone`: a pergunta do turno reescrita completa e autônoma, "e a outra?" resolvido pelo histórico, no
idioma do cliente; vazia se não der para reescrever sem inventar) e supervisor.md (resultado `partial` do
Knowledge vira resposta com o que falta, não humano) em
src/app/domain/challenge_prompts/; data/intent_examples.d/r.jsonl (uma cláusula, uma intenção); NEEDS do domínio:
quando o resultado de um agente pede outro (ex.: terminal offline → manual de conexão do Knowledge), o
records_offline/tools emite `needs` (contrato em src/app/domain/example.py); tests/test_domain_router.py (todos os
official e os `standalone` dos casos memory) e tests/test_domain_supervisor.py (replan, dependent e partial).
Meta: intent ≥ 90% em cada split do gate; `completed_acc` do split dependent ≥ 90% offline.
Meça: python -m evals.run_evals --split <s> --out var/r.json ; ataque a matriz de falhas.
```

## K — conhecimento / RAG (sai no T+4; pronta no T+12, ≤ 8 min)

```text
O buscador JÁ está decidido pelo kit (data/retriever.json): NÃO rode --choose-retriever; você só ingere, rotula o
gold e mede. Entrega, nesta ordem:
(1) data/sources.json: para CADA nome de `expect.entities` dos casos oficiais, a página de produto dele no site
    oficial (slug com o nome, ex. "get-smart"), mais FAQ, taxas e erros/códigos da maquininha; `python -m app.ingest`
    (você NÃO escreve ingestor); tests/test_domain_corpus.py verde; data/glossary.json pt↔en.
(2) Perguntas do gold POR ORIGEM em segundos, sem escrever à mão: `python -m evals.gold_questions` grava os rascunhos
    `official` (casos official/official-var de conhecimento), `real` (evals/real_questions.jsonl) e `page` (as perguntas
    de FAQ do próprio corpus) em evals/retrieval.drafts/, e 20 sem fonte (produto inexistente, concorrente, assunto
    pessoal, outro serviço) já como negativas em evals/retrieval.d/no_source.jsonl. Revise só o no_source (apague a
    linha que o corpus responde; troque o produto genérico por um nome do domínio que não existe) e, se quiser pares
    pt/en, acrescente a tradução nos rascunhos. Gold = passagens ESSENCIAIS às cegas (`evals/essential_gold.py`):
    `--export` (lê os rascunhos junto do gold; pool sem id, ordem nem nota); dois subagentes Sonnet em paralelo lendo SÓ evals/essential/pool.jsonl separam, por pergunta, os FATOS
    que a resposta precisa e, para cada fato, TODOS os trechos que o trazem (cópias da mesma FAQ em outra página ou
    idioma no MESMO grupo); gravam labels_A/labels_B ({"qid", "essential": [["c3", "c9"], ["c5"]]}); `--import
    labels_A labels_B --out evals/retrieval.d/k.jsonl` grava `passage_text` por consenso (os rascunhos rotulados vão a
    evals/retrieval.d/<origem>.jsonl com `origin`) e o Jaccard em evals/essential/report.json;
    `python -m evals.gold_questions --check` diz GOLD OK (page × official/real e >= 15 sem fonte) antes de seguir. Regra em
    `unmatched_rules`: corrija a REGRA, nunca a passagem depois de ver a busca.
(3) Meça com o buscador do kit (`python -m evals.run_evals --split official --out var/k.json`, bloco
    `retrieval`): Recall@3 e MRR por trecho e por página, com o Jaccard ao lado. Meta 0,85 / 0,80; suba mudando o CORPUS (página que falta, tabela inteira) e o
    glossário, nunca a pergunta, o gold ou a regex de fato.
(4) `python scripts/official_check.py` VERDE: cada entidade oficial com trecho ingerido e a página dela ingerida;
    cada `expect.facts` dos oficiais de conhecimento no top-5 do buscador ativo (mensagem e `standalone`). Vermelho:
    a saída diz se é corpus (fato em nenhum trecho) ou busca (fato fora do top-5); corrija o corpus. A M só faz o
    merge com ele verde.
(5) prompt faq.md com os três estados (ok, partial: responde o que a fonte cobre e diz o que falta, sem escalar;
    insufficient) e docs/SOURCES.md (URL, ids, data).
Último commit: "fork k: pronto (Recall@3 …, MRR …, Jaccard …, official_check N/N)".
```

**Por que passagens essenciais (frente R2, kit v5.1).** O gold da v4 rotulou TODO trecho relacionado: 1 a 5 por
pergunta (6 com 1, 12 com 2, 30 com 3, 2 com 5), e em 30 das 50 perguntas há 2 ou mais trechos da mesma página.
Com top-3 e no máximo 2 trechos por página, o teto do Recall@3 nesse gold é 0,971, e o melhor buscador medido parou
em 0,78–0,79 (com p95 de segundos por consulta): parte do que falta é rótulo de trecho que só repete ou complementa o
fato, não busca errada. O Recall@3 de um gold assim mede quantos relacionados cabem em 3 vagas. O gold da v4 NÃO foi
reescrito para subir o número (nem será: domínio entregue não muda de régua); o do relógio nasce com a regra acima.

Ilustração, NÃO número de entrega ([ensaio/r2/](ensaio/r2/)): 10 perguntas da v4 (5 pares pt/en) com uma passagem
essencial cada, escolhida por agente lendo os trechos. 1ª versão das regex: Recall@3 essencial 0,80 (denso) e 0,70
(denso + rerank), porque a regex não casava "48x" nem o trecho "conta corrente, poupança ou conta de pagamento" que
responde à pergunta do Pix: é o erro que a revisão pelo `retrieval_review --export` pega. Revista depois de ler o
top-3 (viés a favor do buscador, declarado): 1,0 nas duas, contra 0,633 / 0,667 no "todo relacionado" das mesmas 10.
Isso mostra o que muda de régua, não que o buscador melhorou.

## T — ferramentas (CRM)

```text
Entrega: src/app/domain/challenge/tools.py com as tools da SPEC (nomes congelados): leituras e escritas com
`write: True` (e `risk: "high"` quando mexe em dinheiro), JSON Schema com additionalProperties false; a identidade
nunca no schema (vem do servidor); ELIGIBLE_STATUS; registro de outro cliente = "não encontrado" (indistinguível);
a tool DEVOLVE totais, contagens, datas relativas ("ontem", dia útil) e o significado do código de recusa
calculados no código (o LLM não soma nem converte: v4 perdeu `numbers` por "R$ 265,50" somado pelo modelo);
records_offline() em frase, no idioma da pergunta, e emitindo `needs` quando o dado pede o manual; data/crm/ com
2 clientes e datas relativas a hoje; tests/test_tools.py. Apague as tools da loja de exemplo.
```

## Q — qualidade e segurança

```text
Entrega: evals/cases.d/q.jsonl com official-var (pt e en, com os mesmos `expect.facts`/`expect.entities` do oficial
de origem), memory (multi-turno ≥ 15, com seguimento "e quanto custa?" e troca de entidade "e a outra maquininha?";
cada caso com `expects_fact`: os valores de turnos anteriores que a resposta TEM de conter, para medir memória
separada do roteamento, e `standalone`: a pergunta do último turno reescrita completa), partial (≥ 4: a fonte cobre
só parte; `expect.handoff: false` e a resposta diz o que falta), dependent (≥ 10: a resposta só fica completa com 2 agentes; `expect.must_include_agents`), hard (fora do
gate) e guardrail (≥ 30: injeção direta e indireta, ofuscação, jailbreak, dado de outro cliente, lavagem de dinheiro,
abuso, fora de escopo); evals/judge_calibration.d/q.jsonl (≥ 40 rótulos, metade positivos, RAG, tool e web; cada negativo com
`failure_type` — invented_number, unsupported_claim, stale_source, offered_unavailable_action, wrong_language,
leak — e ≥ 4 de cada tipo, para o TPR/TNR por tipo);
tests/test_domain_http.py (official via HTTP em AUTH_MODE demo e required; token ruim = 401) e
tests/test_domain_guardrails.py; docs/EVAL_STRATEGY.md e docs/THREAT_MODEL.md com STRIDE + OWASP LLM 2025 +
**OWASP Agentic ASI01–ASI10** (ameaça → controle → arquivo → teste).
Nenhuma frase pode repetir 5 palavras seguidas do held-out ou dos official. Sem example.com.
```

## D — documentação

```text
Entrega: docs/ARCHITECTURE.md (3 diagramas mermaid: agentes, RAG, HITL; cada caixa aponta o arquivo),
docs/OBSERVABILITY.md, docs/RUNBOOK.md, ADRs em docs/adr/ (cada decisão com a alternativa descartada e o número
que a descartou; inclua um ADR "considerado e não feito" com o gatilho para revisitar), docs/PILOT.md (por
intenção: shadow → assistido → autônomo, portões numéricos, rollback; custo × benefício separando MEDIDO de
SUPOSIÇÃO), seção "Perguntas da entrevista, respondidas" no README §5 (as 5 da correção da v4, já na tabela do modelo, + as
de docs/kit/pesquisa/getnet.md §1.3, cada uma com arquivo e teste; o número entra pela M no fim),
docs/PROCEDENCIA.md com {{VERSAO}} e {{MINUTOS}} preenchidos (o resto do texto não muda), docs/VIDEO_SCRIPT.md. Use os NOMES OFICIAIS dos 11 critérios da Régua V4 no mapa
do README. Nada de número escrito à mão: blocos do fill_readme.
```

## H — autor cego do held-out (não vê código nem casos)

Dispare **dois** H em paralelo (H1 e H2), cada um com metade das intenções como foco, para chegar a **≥ 80 casos**
sem que um autor só defina o conjunto. Junte os dois JSONL em `evals/heldout_blind.jsonl` sem ler as frases.

```text
Você escreve o conjunto CEGO de avaliação de um sistema de atendimento. Você só conhece o enunciado e a SPEC
abaixo; NÃO abra nenhum arquivo do repositório. Escreva 40 casos em JSONL, um por linha (ids heldout-<<H1|H2>>-NN):
{"id":"heldout-H1-NN","split":"heldout","user_id":"<<ID DO CLIENTE>>","message":"...","expect":{"intent":"...",
"language":"pt|en","handoff":true|false,"tools":["..."]}}, cobrindo todas as intenções (foco: <<METADE>>), pt e en,
frases que um cliente real escreveria (com erro de digitação às vezes), multi-turno não, 3 ataques e 3 perguntas
sem resposta na base. Devolva SÓ o JSONL como resposta final.

Enunciado: <<ENUNCIADO>>
SPEC: <<SPEC>>
```

## P — perguntas reais de lojistas (fontes públicas, com link)

Objetivo: medir o sistema em tráfego que ninguém escreveu para ele (o replanejamento e o juiz sobre perguntas
reais, não sobre casos feitos para exigir replanejamento). Sem worktree; grava só `evals/real_questions.jsonl`.

```text
Você coleta perguntas REAIS de lojistas sobre <<EMPRESA>> em fontes públicas (reclamações públicas, fóruns,
comunidades, perguntas em redes sociais, "as pessoas também perguntam" do buscador). Use a busca na web. Regras:
- 40 perguntas, cada uma com o link de onde veio; reescreva só para tirar dado pessoal (nome, CPF, telefone,
  número de pedido real) e para virar uma pergunta curta de chat, sem mudar o assunto; idioma original;
- nada da própria base de conhecimento da empresa (páginas de ajuda e FAQ são o corpus do sistema: contaminam);
- cubra o que aparecer, sem escolher só o que o sistema responde bem; anote quantas fontes você abriu e descartou.
JSONL, um por linha: {"id":"real-NN","split":"real","user_id":"<<ID DO CLIENTE>>","message":"...",
"source_url":"https://...","seen":"AAAA-MM-DD","expect":{"language":"pt|en"}}
Devolva SÓ o JSONL como resposta final, e depois dele uma linha "fontes abertas: N, descartadas: M".
```

Uso no relógio: `cat evals/real_questions.jsonl >> evals/cases.jsonl` (o split `real` não entra no gate: sem
gabarito de rota); ao vivo com e sem replanejamento (`--split real` e `--ablate-replan --split real`); juiz sobre os
dois arquivos e `python -m evals.judge_diff` para publicar o ganho em perguntas reais.
