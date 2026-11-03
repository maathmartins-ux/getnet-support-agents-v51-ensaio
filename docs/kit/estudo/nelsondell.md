# Estudo: como o nelsondell chegou a 9,5 na Régua V4, e o que falta à V5

Data: 02/11/2026. Fontes lidas (só leitura): `/home/user/arquivo/refs/nelsondell_multi-agent-support-system` (abaixo **ND**),
a V5 em `/home/user/v5-main0` (abaixo **V5**), `arquivo/conhecimento/getnet.md` e `docs/kit/POSMORTEM_V5.md`.

**Licença.** O ND não tem LICENSE (ver `getnet.md` §5). Este documento descreve **ideias e mecanismos com as minhas
palavras** e aponta arquivo:linha. Nada de código ou texto dele deve entrar nos nossos repositórios.

Convenções: **(nv)** = palpite / não verificado. **E** = motor, feito **antes** do relógio (kit). **D** = domínio,
feito **dentro** dos 58 min. Minutos são estimativa de trabalho (nv).

---

## 0. Três fatos que mudam a leitura

1. **O 9,5 do ND não foi feito em 60 minutos.** A v1 (60 min) tirou 8,7 numa régua antiga; o 9,5 é da v2, ~31 tarefas
   fora do timebox, e o README atual descreve a v3, feita depois da avaliação V4 (`docs/history.md:3-4`, `:9`;
   `README.md:19-22`; `getnet.md` §4: ~55 dias, T-15 a T-65). Então o que copiamos é **o protocolo e o desenho**.
   O volume de iteração não cabe no relógio. Tudo que for genérico tem de ir para o motor **antes** do relógio.
2. **O ND não tem mais recursos que a V5.** A V5 tem MCP, Telegram, quatro olhos, PTAX/Open-Meteo, checagem numérica em
   **toda** resposta e um livro de fatos. O ND checa números só no compose, no rascunho do humano e na web
   (`app/graph/compose.py:93`, `human_review.py:113`, `knowledge.py:157`), não na resposta de corpus. A diferença
   está em três coisas: (a) **a consulta que chega ao buscador** e (b) **a abstenção em três estados**, que juntas
   explicam RAG, Memória e Business Fit; e (c) **o protocolo de avaliação com humano em traces reais**, que explica
   Evaluation e Judgment.
3. **O defeito dominante da V5 é escalar demais.** Nos `evals/results/live_*.json` da V5, a checagem `handoff`
   reprova em 49 linhas: em 40 o sistema escalou sem precisar (memory 21, official 9, hard 7, parallel 3) e em 9 não
   escalou quando devia (replan). Os motivos mais comuns são `faq_not_in_sources` (19: o LLM disse que não estava na
   fonte) e `faq_no_source` (15: o portão de cosseno recusou). O ND tem esse mesmo modo de falha, com nome ("diz que
   falta o que a evidência tem", `evals/failure_modes.md:19`, `:39-40`), uma checagem só para ele e correções medidas
   (`:67-73`). A V5 conta o mesmo defeito só como "handoff 75" (`docs/FAILURE_MODES.md:7-12`), sem a causa.

---

## 1. Critério a critério

Notas do ND: `REVIEW.md:11-21`. Pesos: régua oficial.

### 1.1 Business & Challenge Fit (8%) — ND 9,5

- **ND.** Pass-all 95/100 em 100 pedidos amostrados (`evals/eval_report.md:7-15`). Respostas reais dos 10 cenários,
  cada uma com o status: `answered`, ou `degraded` para clima e câmbio quando a web não sustenta a resposta
  (`docs/demo.md:15-30`). S04 (Pix sem conta) sai como resposta **parcial**: diz o que o site cobre e o que não cobre,
  sem escalar (`docs/demo.md:24`). O corpus foi completado onde a análise de erros achou respostas parciais
  (`docs/rag.md:5`, T-53). O piloto tem custo × benefício com cada linha marcada como medida ou suposição
  (`docs/pilot.md:41-59`).
- **V5.** Official pass^3 0,60. official-01 (Clássica × Smart) e official-04 (Pix sem conta) vão ao humano por
  `faq_not_in_sources` (README §7). `docs/PILOT.md` deixa custo e volume como "a preencher" (`docs/PILOT.md:15-23`).
- **Lacuna.** Dois cenários oficiais de conhecimento sem resposta. Isso toca o Challenge Fit Gate. O ND trata o mesmo
  par de perguntas (no RRF puro, I01 e I02 ficavam no rank 8 e 7: `evals/rerank_benchmark.md:36-37`) e resolve na
  consulta (§2), não no corpus.
- **Melhoria.** (E, 40 min) cobertura em três estados no agente de conhecimento (§2.5); (D, já no pós-morte N1)
  portão de fato oficial; (E, 15 min) `docs/PILOT.md` gerado com custo por turno resolvido e fração resolvida
  **medidos** a partir dos `live_*.json`, e as suposições numa coluna separada.

### 1.2 Agentic Reasoning & Orchestration (15%) — ND 9,5

- **ND.** O especialista devolve um `Need` estruturado (`app/contracts.py:34-39`). Quem muda o plano é código: o
  supervisor insere um passo de leitura logo depois do atual, ignora o pedido quando o passo não respondeu, quando é
  o mesmo agente, quando é repetido ou quando o orçamento acabou (`app/graph/supervisor.py:59-86`), e para o turno
  quando a conta de chamadas ou de custo estoura (`:89-104`). ADR com a alternativa descartada (`docs/adr/0001-bounded-replanning.md:3-24`).
  A avaliação tem 3 rodadas: 32/60 com replanejamento × 19/60 sem, com o p95 dos pedidos simples. As falhas que
  sobram são classificadas por código (`evals/planning_report.md:5-36`). Duas regras de prompt foram testadas e
  **revertidas** porque melhoraram só 1 de 3 rodadas; a regra de manter foi escrita antes da medida (`:38-55`).
- **V5.** Replanejamento por `needs` com ablação: dependent 100% × 0% offline. Nas perguntas reais, a rodada com
  replanejamento abortou por teto de US$ (README §5, última linha).
- **Lacuna.** Pequena no desenho. Na evidência, faltam: rodada ao vivo repetida (3×) com e sem, causa de cada falha
  restante e o registro de "tentado e revertido".
- **Melhoria.** (E, 25 min) o runner da ablação passa a gravar uma tabela por rodada (concluído, passos, chamadas,
  p95 dos simples, US$) e a classificar cada falha por código (não pediu o passo, escalou, valor de outro item); (D)
  só `dependent` com repeat 3.

### 1.3 Context, Knowledge & RAG (10%) — ND 9,7

- **ND.** Pipeline completo no §2. Em resumo: o router reescreve a pergunta em pt, com uma busca por item comparado; o
  buscador é híbrido com RRF e intercala os rankings por rodada; o top-5 vai ao gerador; a abstenção é dupla
  (similaridade densa calibrada, mais `coverage` do modelo); a calibração tem AUC e gap por embedder; o rerank foi
  medido e ficou opcional.
- **V5.** Busca densa e5-large no **texto cru** da mensagem, mais glossário pt↔en e a última fala do cliente colada
  como dica (`src/app/agents.py:315-317`, `router.py:228-241`). k=3 (`agents.py:317`). Recall@3 0,842 / MRR 0,715 em 38
  perguntas com um rotulador. O portão de cosseno **não separa**: a 0,88 responde só 42% das perguntas com fonte
  (`data/retriever.json` → `measured.dense.gate.pos_answered` 0,421); a 0,82 também não separa, e a recusa fica com
  o LLM (`docs/adr/0008-rerank-com-orcamento-de-3s.md`, Decisão).
- **Lacuna.** (1) A consulta: comparação com uma busca só; inglês sem tradução para o idioma do corpus; seguimento por
  concatenação. (2) Abstenção sem sinal calibrado, e binária. (3) A evidência do gold: 38 perguntas × 82, sem conjunto
  fora do domínio com AUC, sem recorte por origem.
- **Melhoria.** (E, 75 min) a reescrita do router (§2.2) mais intercalação por rodada, com k=5 para o gerador; (E, 30
  min) relatório de calibração com AUC, gap e "rank do 1º gold por pergunta", separado por origem (ver §3); (D, 8 min)
  perguntas do gold escritas a partir das páginas **e** das perguntas oficiais e reais.

### 1.4 Tool & Action Engineering (10%) — ND 9,5

- **ND.** A identidade entra na tool pelo estado injetado e não aparece no schema que o modelo vê
  (`app/tools/account.py:3-4`, `:112`). Os argumentos são filtrados pelo schema antes da injeção (`:199`). Uma escrita
  só, executada uma vez depois da confirmação, auditada (`docs/adr/0005-write-behind-confirmation.md`).
- **V5.** Igual ou acima: JSON Schema, identidade do servidor, confirmação do dono, quatro olhos, TTL, execução única
  entre réplicas, MCP (README §3, linha Tools).
- **Lacuna.** Nenhuma de desenho. `tools_acc` 72,5% no held-out (`evals/results/latest.json` → `metrics.heldout`) aparece sem
  explicação.
- **Melhoria.** (D, 5 min) uma linha em "limite conhecido" explicando o `tools_acc` do held-out por causa.

### 1.5 Security & Identity (13%) — ND 9,3

- **ND.** JWT RS256 com o lojista tirado do `sub`, papéis, auditoria só de acréscimo, apagamento LGPD e retenção, rate
  limit (`REVIEW.md:15`). Tabela OWASP ASI01–ASI10 com o controle e o teste de cada linha (`docs/security.md:30-47`).
  Red team de 40 casos com o ASI no rótulo, 10 adaptativos, páginas e trechos plantados, replay no CI
  (`evals/red_team.jsonl`, `evals/thresholds.toml:13-14`). O desserializador do checkpoint aceita só uma lista de tipos
  (`docs/architecture.md:153-157`).
- **V5.** JWT com rotação, revogação e kid; guardrail com regex e LLM; ao vivo 60/63 no `hard`, offline 11/32. Sem
  expurgo/retenção LGPD (README §3, limite da linha Memory).
- **Lacuna.** Um red team rotulado por ASI que é **gate** (o `hard` está fora do gate), e o apagamento LGPD.
- **Melhoria.** (E, 30 min) `DELETE /me/conversations/{id}` mais um purge por idade, com teste; (D, 10 min) a coluna
  `owasp` nos casos de guardrail e a tabela ASI gerada desses rótulos.

### 1.6 Memory, State & Resilience (8%) — ND 9,4

- **ND.** Desenho no §2.7. Ponto central: o router é o único que lê o histórico, como dado. Ele reescreve o seguimento
  numa pergunta completa e **classifica essa pergunta completa** (`app/prompts/router.md:40`, `:67-68`). Os
  especialistas não guardam estado. Postgres para réplicas: réplica morta no meio do turno e turnos serializados
  testados no CI (`REVIEW.md:16`; `.github/workflows/ci.yml:112-127`). Os 9 seguimentos do golden set acertam 45/45
  em 5 rodadas (`evals/router_benchmark.md:21-33`).
- **V5.** Livro de fatos por código (`src/app/memory.py:1-16`), resumo rolante, herança de intenção por regex
  (`src/app/followup.py:1-17`). pass@1 0,72, com 18 perdas só de rota (README §5). Nas linhas de memória com falha de
  `handoff`, o sistema escalou em 21 delas.
- **Lacuna.** A V5 tenta **adivinhar a intenção do fragmento** ("e a outra?") com heurística. O ND **completa o
  fragmento primeiro** e classifica a pergunta inteira, na mesma chamada estruturada. A mesma reescrita alimenta a
  busca, e isso também corta as escaladas de memória (o RAG passa a buscar a pergunta completa).
- **Melhoria.** (E, 45 min, junto com 1.3) o schema do router ganha `query` completa por passo; a intenção é da
  pergunta completa; a proteção do §2.7 recusa uma reescrita que invente identificador; sem LLM, cai no
  `followup.inherit` atual. (D, 5 min) 8–10 linhas de seguimento no golden set, inclusive depois de uma resposta do
  operador.

### 1.7 Human Oversight & Risk Management (7%) — ND 9,7

- **ND.** São dois nós porque o `interrupt()` roda o nó de novo na retomada. Todo efeito colateral acontece uma vez,
  antes da pausa (`app/graph/human_review.py:1-11`). O caso leva o que cada agente tentou e por que parou
  (`:61-88`) e um **rascunho** que o operador pode aprovar como está. O rascunho é descartado se trouxer número ou
  status fora da evidência (`:91-116`). O operador aprova, responde ou cancela. A reformulação da resposta dele volta
  ao texto literal se acrescentar número ou status (`:143-164`). Depois da resposta, **os passos restantes do plano
  rodam** com ela como evidência (`:167-199`). TTL de 24 h e cancelamento encerram o caso, e a próxima mensagem é
  atendida normalmente. A resposta é entregue exatamente uma vez. O claim é atômico. São 21 testes
  (`docs/human-in-the-loop.md:33-65`). Os seguimentos depois da resposta do operador estão medidos no router
  (`:37-42`).
- **V5.** Também retoma o plano na hora (`src/app/resume.py:1-17`) e tem fila por especialidade, SLA, Telegram, claim
  atômico, notas com o caso aberto (`src/app/cases.py:6`) e resumo das tentativas (`src/app/casestate.py:129-134`).
  **Não achei** (grep por draft/rascunho/cancel/expir em `cases.py`, `api.py`, `resume.py`): rascunho pronto para
  aprovar, fechamento por cancelamento e expiração do caso (nv: pode estar em outro módulo).
- **Lacuna.** Pequena no mecanismo. O peso real está no excesso de escaladas: 40 linhas foram ao humano sem precisar
  (§0.3). Um avaliador que lê a demo vê "humano" em cenário oficial.
- **Melhoria.** (E, 35 min) rascunho guardado pela checagem numérica e de status, mais as ações `approve` e `cancel`;
  TTL do caso fecha com aviso. (E, 0 min a mais) o efeito maior vem da cobertura em três estados (§2.5).

### 1.8 Evaluation & Quality Engineering (14%) — ND 9,7

- **ND.** Protocolo completo no §3. Pontos-chave: análise de erros em 100 traces reais; o rótulo é rascunhado por um
  modelo e revisado linha a linha pelo dono (0 edições declaradas); cinco modos de falha, uma checagem binária por
  modo; replay da gravação no CI com piso igual à taxa aceita; held-out de 80 com rótulo do dono às cegas, ponta a
  ponta: 63/80. O juiz é de outra família e aparece como **"não validado"**, com a regra que o validaria
  (`evals/README.md:13-14`, `:64-67`; `evals/heldout_report.md:13-17`).
- **V5.** Juiz da mesma família do gerador (`judge.json`: `same_family: true`). Kappa juiz × humano 0,58 medido em **48 casos construídos para a calibração** (24/24, defeitos plantados, 4 por tipo;
  `docs/EVAL_STRATEGY.md:20-25`), não numa amostra de traces reais. Revisão humana de
  10 respostas por 2 pessoas, kappa entre humanos 0,054 (`evals/results/human_review.json`). O held-out mede a
  **intenção** (67,5%) contra a taxonomia, não o resultado (`evals/heldout_blind.jsonl` → `expect.intent`). Os modos de
  falha são agrupados pela 1ª checagem que reprovou (`docs/FAILURE_MODES.md:3`).
- **Lacuna.** Ver §3.4.
- **Melhoria.** Ver itens 4, 6 e 7 do ranking.

### 1.9 Observability, Reliability & Cost (6%) — ND 9,2

- **ND.** Spans OTel GenAI sem conteúdo, custo por resolução, resolução por intenção, escaladas por motivo, p50/p95 por
  nó, quatro alertas com runbook, US$ 0,00048 por turno resolvido (`REVIEW.md:19`; `docs/operations.md:90+`).
- **V5.** Equivalente (README §3, linha Observability).
- **Lacuna.** O número do custo por turno resolvido no README e um runbook por alerta (nv: não conferi os runbooks da
  V5 em `docs/RUNBOOK.md`).
- **Melhoria.** (E, 10 min) `fill_readme` escreve o custo por turno resolvido (gasto total ÷ turnos sem humano) a partir
  dos `live_*.json`.

### 1.10 Production Engineering (5%) — ND 8,6

- **ND.** `make verify` num clone limpo, sem chave e sem rede depois do sync. O tokenizer vem no repositório. CI em
  ubuntu com a rede cortada por namespace e em macOS (`.github/workflows/ci.yml:17`, `:34-41`); SBOM, trivy, gitleaks,
  imagens por digest, `make scale`; `reports/verify.md` gravado. A nota mais baixa do ND: o avaliador **tentou rodar**
  a suíte e ela não subiu sem baixar o tokenizer (`README.md:43`).
- **V5.** CI **vermelha** no último commit (pós-morte N9).
- **Lacuna.** A CI.
- **Melhoria.** Pós-morte N9, já decidido.

### 1.11 Engineering Judgment (4%) — ND 9,8

- **ND.** Cada escolha tem a medida que a decidiu: modelo do router (5 candidatos com custo, `evals/router_benchmark.md:5-11`),
  embedder e limiar (`evals/retrieval_calibration.md:5-11`), reranker com o **orçamento de latência fixado antes de
  medir** (`docs/rag.md:30-31`), ADR "considerado e não feito" com o gatilho para rever cada item
  (`docs/adr/0008-considered-not-doing.md:3-12`), regras tentadas e revertidas (`evals/planning_report.md:38-55`) e uma
  tentativa revertida no `failure_modes.md:146-149`.
- **V5.** ADRs com a alternativa descartada. O orçamento do rerank foi medido com a CPU disputada
  (`docs/adr/0008-rerank-com-orcamento-de-3s.md`), e o README admite alternativas não medidas (§3, linha Judgment).
- **Lacuna.** A **regra de decisão escrita antes da medida**, o "tentado e revertido" com número e o benchmark de
  modelo.
- **Melhoria.** (E, 15 min) o modelo de ADR ganha os campos "regra fixada antes de medir", "medido", "revisitar quando";
  (E, 30 min) `evals.run_model_benchmark` (golden set × N candidatos × 2 rodadas, acerto, p50, US$/1k).

---

## 2. O RAG do ND, de ponta a ponta, e a memória

### 2.1 Fontes e ingestão
- 28 páginas e 3 manuais em PDF viram 275 documentos e 270 chunks (`docs/rag.md:5`).
- Há três parsers, cada um conferido contra um arquivo real: FAQ (pergunta e resposta pareadas por um id de modal),
  artigo (a coluna de conteúdo do construtor de páginas) e manual (página a página) (`app/rag/parse.py:3-9`, `:68-150`).
- Página que nenhum parser lê entra num relatório, não é descartada em silêncio (`app/rag/ingest.py:64-87`).
- O texto extraído vai para um snapshot commitado (`data/corpus/documents.jsonl`), então o clone limpo constrói o
  mesmo índice sem baixar o site (`app/rag/ingest.py:108-149`).
- Páginas foram acrescentadas **por causa da análise de erros**: categorias do FAQ, página do Pix, manuais de três
  maquininhas (`docs/rag.md:5`, T-53).

### 2.2 Consulta (a peça que falta à V5)
- O router devolve, para cada passo, a **pergunta inteira em pt**. Ela é traduzida quando o lojista escreveu em
  inglês, e as referências ao histórico ficam resolvidas (`app/graph/router.py:31-40`).
- Numa comparação, o router também devolve **uma busca curta por item**, no máximo 3 (`router.py:38-40`).
- O retriever usa essas consultas, nunca a mensagem crua (`app/rag/retrieve.py:7-8`).
- Por isso a calibração não precisa de perguntas em inglês: o corpus é pt e a busca é sempre em pt.
- Na V5, as 4 oficiais em inglês recusadas pelo portão (pós-morte N2) são o sintoma de buscar o texto cru.

### 2.3 Recuperação
- BM25 e denso (Chroma, cosseno), fundidos por RRF k=60 por posição, nunca por escore (`retrieve.py:82-95`).
- 20 candidatos por lado (`:40`).
- Cada consulta é fundida sozinha, e os rankings das consultas são **intercalados por rodada**: em cada rodada, cada
  consulta acrescenta o melhor hit que ainda não foi pego (`:186-220`).
- Fundir todas as listas de uma vez foi medido e rejeitado: o RRF premia consenso, e as páginas genéricas expulsavam a
  página de cada produto (`retrieve.py:12-17`; `docs/rag.md:17-19`).
- Esse ajuste fez S01 trazer o preço da Get Smart em 3 de 3 rodadas ao vivo (`evals/failure_modes.md:138-145`, `:169-171`).
- top_k = 5 (`app/settings.py:74`).

### 2.4 Rerank
- Opcional, desligado por padrão. Reordena os 20 candidatos fundidos de cada consulta. Se falhar, a ordem fundida fica
  (`retrieve.py:172-184`).
- Medido em 82 perguntas com 146 chunks gold: none 0,939/0,851; Cohere 0,963/0,894 a 618 ms de p95; bge e Qwen na CPU
  levam 5–12 s (`evals/rerank_benchmark.md:5-10`).
- Ficou desligado porque o ganho foi de 2 perguntas, entra um fornecedor novo e a chave de teste tem cota
  (`docs/rag.md:40-49`).
- **O rerank nunca muda a abstenção**: a confiança continua sendo a similaridade densa (`docs/rag.md:7`).

### 2.5 Fundamentação e abstenção (dois portões e três estados)
- **Portão 1, antes do LLM.** A melhor similaridade densa entre todas as consultas, abaixo do limiar calibrado, leva à
  abstenção sem chamar o modelo (`app/graph/knowledge.py:111-118`; `retrieve.py:196-202`).
- O limiar (0,50) é o meio do gap entre a pior pergunta do domínio e a melhor de fora. Com
  `text-embedding-3-large` o gap é +0,067 e a AUC é 1,000; o embedder local **não** separa (gap −0,201)
  (`evals/retrieval_calibration.md:5-11`).
- **Portão 2, o modelo.** A saída estruturada traz `coverage` ∈ {full, partial, none}. `partial` responde o que tem
  suporte e diz o que o site não cobre; `none` abstém e escala (`knowledge.py:44-58`, `:127-129`).
- As fontes citadas saem **do que foi recuperado**, nunca das URLs que o modelo diz ter usado (`knowledge.py:69-76`).
- O prompt diz que falta informação **só quando nenhum trecho trata o fato**; isso foi medido por versão de prompt
  (`evals/failure_modes.md:67-73`).
- Na web, todo número tem de estar num resultado; um valor em reais tem de aparecer escrito junto de "R$" no resultado
  citado; link próprio não pode; a data de publicação vem do campo estruturado do provedor
  (`knowledge.py:151-204`; `app/graph/numbers.py:1-12`).

### 2.6 Como os fatos dos cenários oficiais ficam garantidos
O ND **não** tem um portão de regex por fato (o nosso N1 é ideia nossa). A garantia vem de cinco camadas:
1. As perguntas do desafio estão no conjunto de recuperação (I01–I22) com o **rank do 1º gold por pergunta**
   publicado (`evals/rerank_benchmark.md:33-37`).
2. O recorte por origem mostra que a metade escrita a partir das páginas está saturada (41/41) e que toda a diferença
   vem da metade das perguntas reais e do desafio (36/41) (`rerank_benchmark.md:18-31`).
3. A busca por item na comparação, medida no cenário (`failure_modes.md:138-145`).
4. Corpus completado para as respostas parciais (T-53).
5. Rodadas ao vivo repetidas do cenário, com o fato conferido: R$ 129,90 em 3 de 3 (`failure_modes.md:169-171`). O
   status `degraded` é aceito quando a web não sustenta (S02, S07 em `docs/demo.md:22`, `:27`).

### 2.7 Memória
- **A chave do thread** é o hash do par (lojista, conversa) serializado em JSON. Pares diferentes não colidem, e o id
  cru não vira chave de armazenamento (`app/graph/memory.py:35-43`).
- **Persiste só `messages` e `summary`.** O input de cada turno volta **todos** os outros campos ao padrão,
  explicitamente, para que o checkpoint não arraste a resposta ou as fontes do turno anterior (`memory.py:25-26`, `:46-66`).
- **Um só nó escreve o histórico.** A mensagem é gravada mascarada, e só a resposta que de fato saiu entra
  (`memory.py:69-88`).
- **Resumo rolante.** Uma chamada estruturada junta as mensagens mais velhas ao resumo. Se ela falhar, o histórico fica
  inteiro e a dobra é tentada de novo no turno seguinte (`:91-107`).
- **Histórico como dado.** Ele vai num campo JSON próprio, nunca dentro das instruções (`router.py:59-72`), e o prompt
  manda ignorar qualquer ordem que apareça nele (`app/prompts/router.md:18-22`).
- **Reescrita protegida por código.** Se a reescrita trouxer um token com dígito (valor, data, protocolo, id) que não
  está na conversa, ela é descartada e a busca usa a mensagem original; uma busca por item inventada é derrubada
  (`router.py:75-105`).
- **Regra de demonstrativos.** "Essa venda" vira a entidade da última resposta do atendimento, inclusive a de um
  humano. Essa regra levou os seguimentos de 28/40 a 40/40 (`docs/human-in-the-loop.md:37-42`; `router.md:68`).
- **Isolamento.** Nenhum nó importa o checkpointer, e um teste garante isso (`docs/architecture.md:147-152`). O
  desserializador aceita só uma lista de tipos (`:153-157`).
- **Concorrência.** Um lock por conversa, do momento em que lê até o momento em que escreve; com Postgres, advisory
  lock; a retomada do operador pega o mesmo lock (`app/locks.py:5-29`; `docs/architecture.md:164-171`).

---

## 3. A evidência de avaliação do ND, e como ele apresenta limites

### 3.1 Conjuntos de dados (todos commitados)
| conjunto | n | o que mede | onde |
|---|---:|---|---|
| traces de tuning | 100 (cenário 10, conta 15, produto 15, adversarial 15, borda 14, seguimento 12, composto 8, troubleshooting 6, geral 5) | análise de erros e checagens por modo | `evals/trace_requests.jsonl`, `traces.csv`, `labels.csv` |
| held-out | 80 (produto 31, adversarial 8, borda 8, conta 8, seguimento 7, cenário 6, troubleshooting 5, composto 4, geral 3; 74 pt, 6 en) | passa/falha **ponta a ponta**, rótulo do dono às cegas | `heldout_requests.jsonl`, `heldout_labels.csv`, `heldout_report.md` |
| red team | 40 (com o ASI no rótulo, 10 adaptativos) | `safe` por código | `red_team.jsonl` |
| golden de rota | 28 linhas × 2 rodadas (+ seguimentos × 5) | intenção e plano ao vivo | `routing_golden_set.jsonl`, `router_benchmark.md` |
| calibração | 97 (82 do domínio + 15 de fora) | gap, AUC, limiar por embedder | `retrieval_calibration.*` |
| gold de recuperação | 82 perguntas, 146 chunks | recall@5, MRR, rerank | `retrieval_review.csv`, `rerank_benchmark.md` |
| planejamento | 20 dependentes + 11 simples, × 3 | conclusão com e sem replanejamento | `planning_set.jsonl`, `planning_report.md` |

### 3.2 Validação humana
- **Traces de tuning.** Um modelo de raciocínio rascunha rótulo e nota a partir de critérios escritos; o dono revisa
  **todas** as linhas e declara quantas editou (0) (`evals/failure_modes.md:9-10`).
- **Held-out.** O dono rotula **às cegas, sem rascunho de modelo** (`evals/README.md:56-62`).
- **Gold de recuperação.** O modelo rascunha, o dono revisa todas as linhas, 0 edições (`rerank_benchmark.md:3`).
- **Um rotulador só**, declarado como limite (`REVIEW.md:13`). Sem kappa entre humanos.

### 3.3 Modos de falha → checagens → regressão
1. 27/100 falham. As notas são agrupadas pelo 1º problema em cinco modos com nome de comportamento: jargão, plano não
   encaixa, conversa fiada mandada a humano ou à web, diz que falta o que a evidência tem, data errada na web
   (`failure_modes.md:12-21`).
2. As falhas óbvias são corrigidas direto. Cada modo restante ganha **uma** checagem: por código quando dá, e um juiz
   binário de **outra família** só no modo que o código não decide (`evals/README.md:37-51`).
3. Tabela por versão de prompt (pass-all, modo-alvo, efeitos colaterais) e a versão aceita (`failure_modes.md:67-73`,
   `:117-121`, `:156-162`).
4. Gravação ao vivo, replay offline no CI, e os pisos de `thresholds.toml` iguais às taxas da gravação aceita. Uma
   requisição que não está na gravação falha com a instrução de gravar de novo. Não existe nota ponderada
   (`evals/README.md:22-33`; `thresholds.toml:1-14`).
5. **Contaminação declarada.** As correções de prompt foram feitas nos 100 traces, que deixam de ser teste
   (`failure_modes.md:83-84`). Uma mudança veio dos rótulos do held-out, então para aquele modo o held-out deixou de
   ser intocado (`:132-134`). Uma rodada do held-out foi parada sem leitura para não guiar a versão seguinte (`:123-124`).
6. **Triangulação.** O held-out (63/80) fica entre as checagens nos traces de tuning (94/100) e os rótulos do dono nos
   mesmos traces antes das correções (73/100). Isso mostra quanto as checagens superestimam (`evals/README.md:57-62`).
7. **Juiz "não validado" com a regra.** São precisos ≥ 10 positivos do modo no recorte e TPR e TNR ≥ 0,8. Os rótulos
   têm 5, e o juiz roda só como checagem de regressão. Cada erro do juiz tem a hipótese de causa: evidência cortada a
   1.500 caracteres na exportação, nota que descreve outra falha (`evals/README.md:64-73`; `heldout_report.md:13-17`).
   **Com isso escrito, a nota de Evaluation foi 9,7.**

### 3.4 O que a V5 tem a menos
- **Rótulo em trace real.** A V5 calibrou o juiz em 48 casos **construídos** com defeito plantado. O ND rotula traces
  reais.
- **O que o held-out mede.** O held-out da V5 mede a intenção contra a taxonomia (67,5%), e essa métrica pune
  divergência de rótulo (multi→support, troubleshoot→support, pós-morte N4) mesmo quando a resposta está certa. O do
  ND é ponta a ponta.
- **Modos com nome.** Os modos da V5 são nomes de checagem ("handoff 75"), não comportamentos. Não dizem o que corrigir.
- **Kappa entre humanos.** 0,054 em 10 rótulos, publicado. Com 10 rótulos e um critério lido de dois jeitos, o número
  mostra que o **critério** estava ambíguo; o ND evita isso com um rotulador, critérios escritos e limite declarado.
- **Juiz da mesma família.** Declarado na V5, mas não resolvido.

### 3.5 Como o ND apresenta limites
- **Dentro do critério.** No `REVIEW.md`, cada critério tem a coluna "Known limit" ao lado da evidência e do comando
  (`REVIEW.md:9-21`).
- **Por lacuna.** "Since V4": lacuna citada pelo avaliador → mudança → evidência (`README.md:35-44`).
- **Com número e mecanismo.** Ex.: o limiar se apoia em 97 perguntas e num gap de 0,067; o guard de status lê
  palavras, então não pega uma negação (`README.md:175-193`).
- **Sem meta inventada.** O README não traz coluna "meta" própria nem "❌ abaixo". O que não está validado aparece com a
  regra que o validaria. **(nv)** O "6 de 11 abaixo da meta" na 1ª tela da V5 compara a entrega com metas que nós
  mesmos fixamos, e o avaliador tende a ler isso como "falhou".

### 3.6 O que o avaliador disse que faltava para 10
- **As três lacunas da V4** (`README.md:40-44`): escala e HA dependiam da evolução do armazenamento; a suíte não subia
  localmente sem baixar o tokenizer; a avaliação factual precisava de um conjunto maior e de validação humana.
- **Limites que o próprio ND deixou** (`REVIEW.md:11-21`, coluna "Known limit"):
  - dados de conta fictícios;
  - volumes do piloto supostos;
  - o replanejamento erra porque o conhecimento não pede o dado da conta;
  - benchmarks dependem da chave do embedder;
  - chunk pode cortar tabela;
  - um revisor no gold;
  - provedor de identidade local;
  - rate limit por réplica;
  - testes de réplica dependem de Postgres;
  - índice por nó;
  - o operador só tem a API;
  - juiz não validado;
  - prompts fixados nos traces de tuning;
  - convenções GenAI ainda em desenvolvimento;
  - efeito do cache de prompt não medido;
  - Docker rodado à mão no macOS;
  - confiança do router autodeclarada (`README.md:186-187`).

---

## 4. As 10 mudanças, por ganho esperado por minuto

**Pré-requisitos já decididos no pós-morte, fora do ranking (fazer primeiro):**
- N9: CI verde e marcador `{{` neutralizado.
- N3: buscador decidido antes do relógio. Pela tabela de `data/retriever.json`, é hybrid+cross ou dense+cross.
- N1: portão de fato oficial.

Ganho = Δ nota ponderada estimada **(nv, palpite meu)**. mp/min = milipontos por minuto.

| # | mudança | E/D e minutos | critérios | Δ estimado | mp/min |
|---|---|---|---|---:|---:|
| 1 | **Cobertura em três estados no Knowledge** (full / partial / none, saída estruturada): `partial` responde com o que tem e diz o que falta; só `none` escala. Regra no prompt: "falta" só quando nenhum trecho trata o fato. Checagem nova `missing_when_present`: a resposta diz "não há informação" e o fato está num trecho do gold. É o caminho contra as 40 escaladas a mais (§0.3) | E 40 · D 3 (exemplos no prompt do domínio) | BizFit, RAG, HITL, Eval | +0,10 | 2,3 |
| 2 | **Router reescreve a consulta**: `query` completa no idioma do corpus por passo, e `search_queries` por item comparado (≤ 3); retriever com fusão por consulta e **intercalação por rodada**; k=5 ao gerador; a busca nunca usa o texto cru | E 75 · D 5 | RAG, BizFit, Memória | +0,13 | 1,6 |
| 3 | **Classificar a pergunta completa** (mesma chamada do item 2): a intenção sai da reescrita, não do fragmento; proteção que derruba reescrita com identificador inventado; `followup.inherit` fica só para o modo sem LLM; demonstrativo → entidade da última resposta (inclusive do operador) | E 25 (sobre o item 2) · D 5 (linhas de seguimento no golden) | Memória, Orquestração | +0,07 | 2,3 |
| 4 | **Análise de erros em trace real dentro do relógio**: exportar ~60 traces ao vivo (evidência inteira, sem cortar a 1.500 caracteres), o LLM rascunha passa/falha e nota com critérios escritos, o dono revisa **todas** as linhas na página de rotulagem e o número de edições é gravado; o agrupamento sai por **comportamento**; `FAILURE_MODES.md` traz modo → checagem → taxa antes/depois | E 45 (exportador, campo de edição, relatório) · D 12 (dono) | Eval, Judgment | +0,08 | 1,4 |
| 5 | **Held-out ponta a ponta**: o dono rotula passa/falha às cegas, sem rascunho; a intenção vira diagnóstico, não manchete; relatório com a triangulação (checagens de tuning × rótulo de tuning × held-out) e a contaminação declarada | E 20 · D 10 | Eval | +0,05 | 1,7 |
| 6 | **Juiz com protocolo, não com kappa em casos construídos**: juiz de outra família por padrão (já previsto em `family_note`); validação contra os rótulos do item 4 por recorte treino/dev/teste com TPR/TNR; regra "≥ 10 positivos e ambos ≥ 0,8, senão **não validado**, roda só como regressão"; o kappa em casos construídos vira teste de canário. Segundo rotulador só numa sobreposição de 20 linhas depois de uma rodada de calibração do critério | E 30 | Eval | +0,04 | 1,3 |
| 7 | **1ª tela no formato "desde a última avaliação"**: lacuna citada pelo avaliador → mudança → evidência; métricas com "limite conhecido" (mecanismo e número) em vez de meta própria e ❌; manter todos os números | E 20 (`fill_readme`) | Eval, Judgment (leitura) | +0,04 (nv) | 2,0 |
| 8 | **Relatório de calibração da recuperação**: ≥ 15 perguntas fora do domínio; AUC e gap por buscador; rank do 1º gold por pergunta; recorte por origem (página × real/oficial); portão no sinal que separa (rerank quando ligado; pós-morte N2) | E 30 · D 5 | RAG, Judgment | +0,03 | 0,9 |
| 9 | **Piloto com números medidos**: custo por turno resolvido e fração resolvida saem dos `live_*.json`; as suposições ficam marcadas; gatilhos de rollback ligados aos alertas existentes | E 15 | BizFit, Obs | +0,015 | 1,0 |
| 10 | **HITL completo**: rascunho para o operador aprovar, descartado se trouxer número ou status fora da evidência; ações `approve` / `reply` / `cancel`; TTL do caso fecha com aviso e a próxima mensagem é atendida | E 35 | HITL | +0,03 | 0,9 |

Ficaram fora do top-10:
- ADR com "regra fixada antes de medir" e benchmark de modelo do router: E 45, +0,012.
- Apagamento e retenção LGPD: E 30, +0,02.
- Red team com coluna ASI como gate: D 10, +0,015.
- Tabela de ablação em 3 rodadas com causas classificadas: E 25, +0,02.

**Ordem de execução sugerida (dependências):** 2 → 3 (mesmo schema) → 1 → 8 (o relatório usa o novo caminho) → 4 → 5
→ 6 → 7 → 9 → 10. Soma do motor ≈ 5,6 h antes do relógio. No relógio: ≈ 45 min de D, dos quais 22 do dono
(itens 4 e 5). Isso pede tirar outra coisa do roteiro (nv: o repeat 3 de splits secundários, pós-morte T4).

**Risco a vigiar.** Os itens 2 e 3 mudam o router, e toda mudança no router regrava as rotas. O ND reverteu uma
mudança de router por isso (`failure_modes.md:146-149`). Medir no ensaio, num domínio real, antes de congelar o
motor (PLAYBOOK regra 11).
