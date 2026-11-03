# Estudo: por que o Skywalker é o "benchmark 10,0" e o que falta à V5

Data: 02/11/2026. Leitura só de arquivos locais:
- referência: `/home/user/arquivo/refs/farrulla-darze_skywalker` (cópia do HEAD `9f6a431`, 140 arquivos, **sem licença**,
  `refs/MANIFESTO.json`). Abaixo, caminhos da referência são relativos a essa pasta;
- V5: `/home/user/v5-main0` (HEAD `371d960`);
- correções do avaliador: `/home/user/arquivo/conhecimento/feedback_v4_formal.md` (nossa v4, 8,5) e
  `/home/user/arquivo/refs/DiogoOg16_getnet/feedback_diogoog16_v4(1).md` (4,7);
- `/home/user/arquivo/conhecimento/getnet.md` e `docs/kit/POSMORTEM_V5.md` (não repetidos aqui, salvo ângulo novo).

**Regra de uso**: a referência não tem licença. Nada deste estudo copia código ou texto dela; as abordagens estão
descritas com palavras nossas e apontadas por `arquivo:linha`. As propostas da §4 são desenho próprio.

Convenção: **(fato)** = verificado em arquivo; **(palpite)** = inferência minha, não verificável.

---

## 0. O ponto de partida: o "10,0" é uma âncora, não uma medida

**(fato)** As duas correções citam o mesmo cabeçalho: "Benchmark: João / Skywalker = 10,0"
(`feedback_v4_formal.md:8`; `feedback_diogoog16_v4(1).md:8`). A única descrição do que o benchmark tem está nas
seções "Comparação com João":
- Diogo: "supervisor com especialistas como tools, RAG mais completo, autenticação, memória, HITL via Telegram,
  evals e observabilidade" e o desenho `Supervisor → especialistas como tools → observa → decide → humano → retoma`
  (`feedback_diogoog16_v4(1).md:259-271`).
- Nossa v4: semelhante em supervisor-com-tools, HITL Telegram com retomada, memória persistida, identidade por token;
  **João superior em "qualidade semântica das respostas; RAG; maturidade de produto end-to-end"**; nós superiores em
  escala testada, quatro olhos/SLA e método de avaliação (`feedback_v4_formal.md:247-263`).

**(fato)** O Skywalker **não commita nenhum número de avaliação**: não existe `evals/results`, relatório ou tabela de
métricas no repositório (lista de arquivos; `README.md:437-544` descreve a capacidade de medir, não resultados).
Também não tem CI (`README.md:626-627`), roda como root com dependências sem hash
(`docker/Dockerfile:1-22`, `poetry export --without-hashes`), usa `qdrant/qdrant:latest`
(`docker/docker-compose.yml:73`), tem 58 funções de teste (contra 636 na V5) e retrieval denso puro sem rerank
(`README.md:180`). Diogo perdeu pontos de Production exatamente por root e `:latest` (`getnet.md`, §1.3).

**(fato)** Pontos fracos do Skywalker que o avaliador não viu (porque não executa nada):
- o banco mock não tem `cliente1988`; o usuário de referência é `client789`, com datas absolutas de fev/2026
  (`db/support_db/init_db.py:45-50`; consulta read-only em `support.db`: nenhuma linha com "1988"; transfers de
  2026-02-01 a 2026-07-24). Pelo `/chat` literal, os cenários 3, 5 e 8 com `cliente1988` caem em "No support record
  found" (`app/modules/tools/definitions/support_db.py:61-65`);
- não há tabela de transações de cartão nem códigos de recusa (`db/support_db/schema.sql`: users, merchants,
  products_enabled, account_status, auth_status, devices, transfers, incidents);
- `/chat` é anônimo por padrão e usa o `user_id` do corpo como identidade (`app/modules/chat/api.py:333-355`,
  `ALLOW_ANONYMOUS_CHAT` default true em `README.md:618`) — o mesmo "user_id do body" que custou a Diogo;
- as tools de escrita só são barradas pelo prompt (`README.md:291-294`; `app/modules/agents/seeds.py:141-144`);
- qualquer chat que mande `/support_here` vira o canal de escalonamento (`app/modules/integrations/service.py:340-345`),
  e a resposta do humano é aceita de quem responder no chat, identificado só pelo username (`:449-452`);
- o `consult_human` só funciona em sessão autenticada com integração Telegram (`service.py:239-242`); no `/chat`
  anônimo ele devolve "canal não configurado" (`app/modules/tools/definitions/escalation.py:39-43`);
- o README está desatualizado em relação ao código **para menos**: diz 12 itens `seed:getnet-v1` e "não há judge
  customizado" (`README.md:451-461`, `:518-522`), mas o código tem 42 itens `seed:getnet-v2`
  (`app/modules/evaluation/seeds.py:30`, 42 perguntas) e avaliadores determinísticos de ferramentas, fatos e citação
  além de AnswerCorrectness/SemanticSimilarity (`app/modules/evaluation/langfuse_experiments.py:213-260`, `:315-318`).

**(fato)** O Skywalker também é uma plataforma reaproveitada: o seed arquiva gerações de um domínio anterior
(InfinitePay) (`app/modules/evaluation/seeds.py:4-8`; `README.md:462-463`) e o runner se descreve como substituto de
uma v1 (`app/modules/agents/runner.py:1-11`). Foi construído em ~7 meses, fora de relógio (`getnet.md:241`).

**Conclusão (palpite, forte):** a régua é relativa a um **desenho de referência** que o avaliador tem na cabeça, e o
Skywalker é a instância dele. O 10 vem de (a) a forma agentic visível no código e na prosa (orquestrador LLM dono do
histórico, especialistas como tools, humano consultado de dentro do laço e o laço continua), (b) aparência de produto
completo (frontend, CRUD de agentes, Telegram sem túnel, Langfuse provisionado), (c) **nenhuma medida própria que
mostre resposta ruim nos 10 oficiais**, e (d) um README que explica cada mecanismo e o porquê, com limitações
honestas. Não vem de rigor de CI, de testes nem de números. A V5 perde contra ele quase só onde **as nossas próprias
evidências mostram resposta pior** (3 de 10 oficiais viram "passei para um humano") e onde o desenho parece regra
(`motor: table`), não onde falta infraestrutura.

---

## 1. Os 11 critérios: Skywalker × V5 × lacuna × mudança no kit

Legenda de esforço: **K** = kit/motor, feito antes do relógio; **D** = domínio, dentro dos 58 min.

### 1.1 Business & Challenge Fit (8%)

- **Skywalker.** Tabela "requisito do enunciado → implementação → status", incluindo os 4 bônus
  (`README.md:147-161`); o `/chat` aceita o payload literal e o alternativo (`app/modules/chat/schemas.py:80-86`); um
  roteiro de 3 minutos para o avaliador testar pelo celular (`README.md:358-385`); golden com os 10 cenários literais
  (`app/modules/evaluation/seeds.py:197`, `:564`, `:582`, `:625`, `:641`, `:690-718`). Seções do README com os
  nomes exatos que o enunciado exige: "Pipeline RAG (ingestão → storage → retrieval → geração)" (`README.md:248`) e
  estratégia de testes de integração descrita (`README.md:570-577`), que é o que o enunciado pede no item 4.
- **V5.** Os 10 oficiais viram split `official` com fatos de referência (`docs/SPEC.md`, tabela AC-01..10); `DEMO.md`
  mostra as respostas reais. Mas: **o exemplo de `curl` do README é de outro domínio** — "Qual o prazo de entrega? E
  onde está meu pedido 1002?" (`README.md:50`), sobra do kit; o README não tem seção de "message workflow", de
  "RAG pipeline ingestion→storage→retrieval→generation" nem de estratégia de testes (estão em `docs/ARCHITECTURE.md`
  e no `check.py`); e o `DEMO.md` mostra 3 oficiais terminando em "I've handed this to a human agent"
  (`docs/DEMO.md:28`, `:70`, `:147`).
- **Lacuna.** O avaliador lê o README antes de tudo; um exemplo de e-commerce no quickstart e títulos que não batem com
  o enunciado são risco gratuito de Challenge Fit. As três escaladas nos oficiais são o que ele vai citar.
- **Mudança.** (K, 20 min) `fill_readme` injeta no quickstart a 1ª mensagem do split `official` e um teste reprova
  README cujo exemplo não esteja no split; esqueleto do README com os títulos literais do enunciado ("How to build,
  configure, run and test", "Message workflow", "RAG pipeline: ingestion → storage → retrieval → generation", "Testing
  strategy (unit, integration, live)") e uma tabela "requisito do enunciado → onde" ao lado da tabela da régua. (D, 0
  min: gerado.)

### 1.2 Agentic Reasoning & Orchestration (15%, Router dentro)

- **Skywalker.** Um agente LLM roteador é dono da conversa; cada especialista é registrado como tool dele
  (`app/modules/agents/runner.py:243-295`), e a chamada do especialista grava passos aninhados com args, prévia do
  resultado e duração (`runner.py:275-283`). Não há taxonomia de intenções nem tabela: o roteador decide a sequência
  pelo prompt (`app/modules/agents/seeds.py:35-48`) e pode chamar vários especialistas e o humano no mesmo turno. O
  contexto de execução (data/hora, cliente autenticado, idioma) entra como segunda instrução
  (`runner.py:196-202`). Sem orçamento explícito de passos ou custo (só timeout por chamada, `runner.py:168`).
- **V5.** Router (Haiku + regras + k-NN) → supervisor com dois motores, `needs`, ALLOWED/FALLBACK/MAX_STEPS,
  paralelismo e ablação (`README.md:102-103`; `src/app/domain/challenge/flow.py:14-34`). Porém a V5 introduziu um
  **atalho**: plano de 1 passo com router confiante vai direto à tabela (`src/app/supervisor.py:528-539`). Resultado
  nos oficiais ao vivo: **24 de 30 execuções com `engine: table`** (`evals/results/live_official.json`, campo
  `engine` por linha; só official-05 e 08 usaram `llm`); o `DEMO.md` imprime "motor: table" em 8 dos 10
  (`docs/DEMO.md:24`, `:37`...). A escalada de official-01/04 é o FALLBACK fixo `faq → escalation`
  (`flow.py:22`), não uma decisão observada.
- **Lacuna.** O avaliador puniu Diogo por "nenhum LLM decide rota ou tool" e elogia o "observa → decide". Na V5 o
  mecanismo existe, mas a evidência que o avaliador lê (DEMO) mostra tabela decidindo nos casos que ele mais olha. A
  taxonomia rígida também cria um número ruim que o Skywalker não tem (held-out intenção 67,5%, `README.md:30`).
- **Mudança.** (K, 30 min) Manter o atalho só para `ok`; qualquer `insufficient` ou `needs` volta ao supervisor LLM
  com o resultado do agente à vista (observa → decide → responde parcial, pede outro agente ou abre caso), e o DEMO
  mostra a decisão e o motivo em uma linha. (K, 30 min) Medir roteamento também por **conjunto de agentes
  necessários ⊆ agentes usados** (o que o enunciado pede: "qual agente ou sequência"), publicado ao lado da acurácia
  de rótulo — não no lugar dela.

### 1.3 Context, Knowledge & RAG (10%)

- **Skywalker.** Corpus pequeno e mirado: 9 páginas de produto e a FAQ, escolhidas a partir dos cenários
  (`README.md:123-139`: `/maquininha/get-classica/`, `/maquininha/get-smart/`, `/todas-as-maquininhas/`, `/pix/`,
  `/conta-digital/`, `/duvidas/`, `/get-ajuda-antecipacao-de-venda/`, `/crediario/`, `/link-de-pagamento/`).
  Extração com tabelas preservadas (`app/modules/knowledge/scraper.py:45-51`); trechos grandes (1024/150) com o
  caminho de títulos prefixado ao texto embutido e sobreposição só dentro da seção
  (`app/modules/knowledge/chunker.py:50-57`); embeddings grandes (`README.md:178`); `top_k=5`, até 20 por chamada
  (`app/modules/tools/definitions/rag_search.py:16-21`). O ponto central: **a busca é uma tool do especialista LLM**,
  que pode reformular e chamar várias vezes (prompt em `seeds.py:84-101`). Não há portão de abstenção numérico: o LLM
  diz "não encontrei". Grafo tipado opcional para taxas, com a justificativa de que taxa em prosa de marketing é
  ruim para similaridade (`README.md:270-274`; `app/modules/tools/definitions/graph_search.py:66-77`).
- **V5.** 341 trechos de 29 URLs (`docs/SOURCES.md`), denso e5-large escolhido por medida, gold de passagem essencial,
  checagem numérica sem LLM. Mas: **uma busca só, k=3, com a pergunta crua**, portão de cosseno, e uma chamada LLM que
  responde ou devolve `NOT_IN_SOURCES` (`src/app/agents.py:317`, `:327`, `:341-342`). O corpus **não tem a página da
  Get Clássica nem a da Get Smart de produto, nem `/conta-digital/`** (`docs/SOURCES.md`; o único trecho que cita as
  duas maquininhas juntas é a linha de preço `prod-todas-maquininhas-04`). No retriever escolhido, o portão de
  cosseno 0,88 respondia só 42% das perguntas com fonte (`data/retriever.json`, `dense.gate.pos_answered 0.421`).
- **Lacuna.** O "RAG mais completo" do avaliador é, na prática, cobertura de corpus nas páginas dos cenários + busca
  agentic multi-consulta. A V5 tem melhor método de medida e pior cobertura dos fatos que o avaliador espera.
- **Mudança.** (K, 15 min + D, 5 min) Regra do kit: toda entidade nomeada num cenário oficial tem a sua página de
  produto ingerida; teste de corpus reprova se não houver trecho da URL de cada entidade. (K, 75 min) Knowledge com
  busca como tool: o LLM decompõe comparação em uma consulta por entidade, traduz consulta en→pt quando o corpus é pt,
  k=5, até 3 buscas por turno, dentro do orçamento do supervisor; o portão de cosseno fica só no modo offline. (K, já
  previsto no POSMORTEM N3) rerank decidido antes do relógio.

### 1.4 Tool & Action Engineering (10%)

- **Skywalker.** Registro tipado de tools (nome, descrição, modelo Pydantic dos parâmetros, handler) exposto num
  catálogo (`app/modules/tools/service.py:55-96`); contexto de execução com a identidade autenticada, nunca vinda do
  LLM (`service.py:32-52`; `support_db.py:54`); coluna de produto só de uma lista fechada (`account_ops.py:26-30`);
  escrita confere o estado, executa o mínimo e devolve antes/depois (`account_ops.py:61-90`; protocolo em
  `seeds.py:141-155`); erro de tool volta ao LLM como texto (`runner.py:219-223`). Fraqueza: autorização da escrita é
  só prompt (`README.md:291-294`).
- **V5.** Mais forte: JSON Schema estrito, ação pendente com confirmação do dono, quatro olhos, TTL, execução única,
  MCP com JWT (`README.md:105`). Avaliador deu 9,3 à v4.
- **Lacuna.** Pequena. O Skywalker mostra o antes/depois da escrita no próprio resultado da tool, o que fica legível
  no trace.
- **Mudança.** (K, 15 min) Resultado de escrita sempre com `before`/`after` do registro e o que não mudou; o DEMO de
  `approval` imprime esse par.

### 1.5 Security & Identity (13%)

- **Skywalker.** Cadastro/login com senha em bcrypt, JWT com `jti` e logout que grava o `jti` numa denylist checada em
  toda rota, rate limit de login por IP+e-mail com `Retry-After`, mensagem de erro genérica, CORS por lista
  (`README.md:415-433`; testes `tests/unit/test_auth_api.py:11-74`, `tests/unit/test_security.py`). Guardrail LLM com
  saída estruturada, falha aberta na entrada e fechada na saída quando o texto parece sensível
  (`app/modules/guardrails/service.py:79-120`). Fraquezas listadas no §0 (`/chat` anônimo com `user_id` do corpo,
  `/support_here`).
- **V5.** Mais forte em quase tudo: JWT com `kid`, JWKS, chaves rotacionáveis, revogação, operador com chave pessoal,
  rate limit que falha fechado, PII mascarada, guardrail em duas camadas, threat model (`README.md:53-57`, `:106`).
  Mas o caminho de uso no README é um token de desenvolvimento emitido por CLI (`README.md:48`).
- **Lacuna.** De percepção: o avaliador escreve "autenticação" como vantagem do benchmark; um fluxo "usuário entra com
  senha e recebe token" é o que ele reconhece. (palpite)
- **Mudança.** (K, 40 min) `POST /auth/login` para os lojistas do fixture (senha com hash, mesmo emissor JWT, rate
  limit já existente) e o README usa esse fluxo no quickstart; o token por CLI fica como atalho de teste.

### 1.6 Memory, State & Resilience (8%)

- **Skywalker.** Histórico persistido e reconstruído como mensagens reais do modelo, até 30, passado ao roteador
  (`runner.py:301-309`; `app/modules/chat/service.py:315-319`); especialistas sem estado recebem uma consulta
  autossuficiente que o roteador redige (`runner.py:48-51`, `:262-265`; `seeds.py:36-38`). Turno em stream não é
  cancelado se o cliente cai e emite keepalive (`chat/service.py:164-231`); job de ingestão persistido
  (`README.md:183`). Não há resumo rolante nem teste de restart.
- **V5.** SQLite WAL/Postgres, resumo rolante, memória de longo prazo, réplicas; memória ao vivo 90,6% de fatos, mas
  pass@1 0,72 porque o **seguimento curto é roteado errado** (`README.md:136`).
- **Lacuna.** No Skywalker não existe "rota do seguimento" separada: quem vê o histórico é quem decide e reescreve a
  consulta. Na V5 o classificador decide antes, com pouco contexto.
- **Mudança.** (K, 45 min) O router LLM recebe as últimas 3 falas e devolve, junto da intenção, uma
  `standalone_query` (consulta autossuficiente); é ela que vai à busca e às tools; teste por padrão de seguimento
  ("e a outra?", "and the Smart?"). Complementa o N5 do pós-morte (herança de intenção).

### 1.7 Human Oversight & Risk (7%)

- **Skywalker.** O humano é uma tool síncrona: o agente posta uma pergunta precisa com o contexto já levantado,
  **o turno espera** a resposta (poll a cada 2 s, timeout) e o valor volta ao laço do LLM, que continua — por exemplo,
  chamando a execução da mudança autorizada no mesmo turno (`app/modules/tools/definitions/escalation.py:21-50`;
  `app/modules/integrations/service.py:275-300`, `:434-455`; política de quando consultar em `seeds.py:50-75`).
  Enquanto espera, a UI recebe eventos de progresso (`README.md:327-337`). Teto do turno ajustado ao timeout da
  consulta (`service.py:377-385`). Ticket completo existe no modelo, mas não é o caminho ativo (`README.md:163-167`).
- **V5.** Fila persistida, console, Telegram, quatro olhos, SLA, especialidade; a resposta do operador entra como
  evidência e os passos pendentes rodam (`README.md:61-65`, `:108`). Mais governança que o Skywalker.
- **Lacuna.** O que o avaliador vê na V5 é assíncrono: o cliente recebe "passei para um humano, a resposta aparece
  aqui" (`docs/DEMO.md:28`). No Skywalker, o mesmo turno termina com a resposta já informada pelo humano. O desenho
  "humano → retoma" fica óbvio num só turno.
- **Mudança.** (K, 75 min) Modo de consulta síncrona com espera limitada (ex.: 45 s) antes de virar ticket: o
  supervisor pergunta ao operador, espera, e se a resposta chega continua o plano no mesmo turno; se não, cai no
  ticket atual. Um caso de `approval` no DEMO com a transcrição da ida e volta (operador simulado no teste).

### 1.8 Evaluation & Quality Engineering (14%)

- **Skywalker.** Golden tipado com pergunta, idioma, categoria, dificuldade, resposta esperada, **fatos esperados**,
  URLs de ouro, rota e tools esperadas, procedência e versão de seed (`app/modules/evaluation/models.py:33-36`;
  `seeds.py:52-218`). Duas camadas: retrieval determinístico por URL de página (recall@k, hit@k, MRR,
  `app/modules/evaluation/metrics.py:18-42`; `service.py:164-202`) e ponta a ponta como experimento Langfuse com RAGAS
  e avaliadores próprios de tools, cobertura de fatos e citação (`langfuse_experiments.py:213-260`, `:268-380`).
  Promoção de 👎 a item golden (`service.py:64-94`). Nenhum resultado commitado.
- **V5.** Método mais rigoroso do conjunto (avaliador, v4): gate offline, ao vivo por split com pass^k, juiz calibrado,
  held-out cego 80, 2 rotuladores. Números ruins publicados (6 de 11 abaixo da meta, `README.md:34`). Porém a métrica
  de topo "oficiais fundamentadas 1,00" (`README.md:22`) conta como fundamentada a resposta "passei para um humano";
  o mesmo juiz dá **helpful 0,733** no official (`evals/results/judge.json`, `by_split.official.helpful_rate`) e esse
  número não está no placar.
- **Lacuna.** O avaliador mede "qualidade semântica" por resposta certa nos oficiais. Groundedness alta com 3 escaladas
  é lida como métrica escolhida a favor (o mesmo motivo do −0,7 em Judgment da v4, `feedback_v4_formal.md:211-215`).
- **Mudança.** (K, 30 min + D, 5 min) Métrica de topo **"oficiais resolvidas"**: resposta sem handoff E todos os fatos
  de referência presentes (regex por caso escrita na SPEC, no relógio) E fonte citada; pass^3 dessa métrica; o
  placar mostra grounded **e** helpful lado a lado. O gate do kit (antes do merge da frente K) roda os oficiais de
  conhecimento ao vivo uma vez e reprova escalada de caso respondível. Isso estende o N1 do pós-morte (que olha só o
  top-3 da busca) para a resposta final.

### 1.9 Observability, Reliability & Cost (6%)

- **Skywalker.** Langfuse completo no compose, provisionado sem passo manual (`README.md:439-442`); um trace raiz por
  turno com sessão, usuário e canal propagados; spans automáticos de modelo e tool para roteador, especialistas e
  guardrails (`app/core/tracing.py:1-18`; `README.md:535-544`); tokens reais (`runner.py:98-102`); **versão do prompt
  ligada a cada geração** e troca de prompt sem deploy (`README.md:524-533`; `runner.py:184-194`); 👍/👎, nota da
  sessão e fila de revisão como scores no trace (`README.md:470-478`). Uma anedota medida justifica uma escolha
  (modelo de guardrail sem reasoning após uma chamada travar >10 min, `README.md:238-244`). Sem métricas/alertas.
- **V5.** Log JSON com `trace_id`, custo e tokens por request, `/metrics`, alertas Prometheus testados, `/analytics`,
  OTel opcional (`README.md:110`). Mais operação, menos ligação com qualidade.
- **Lacuna.** Ligar prompt/versão e feedback a cada resposta, e fechar o ciclo produção → dataset.
- **Mudança.** (K, 30 min) Hash/versão de cada arquivo de prompt usado gravado no log e no JSON da resposta; endpoint
  que transforma um 👎 em candidato a caso (`evals/candidates.jsonl`, revisão humana antes de entrar no split).

### 1.10 Production Engineering (5%)

- **Skywalker.** Imagem autocontida (código + banco mock, sem bind mount) com healthcheck (`docker/Dockerfile`); compose
  de 9 serviços; nginx para SSE (`README.md:335-336`). Root, sem hash, `:latest`, sem CI.
- **V5.** Muito mais forte (multi-stage não-root, digest, lockfiles, CI com 2 réplicas).
- **Lacuna.** Nenhuma a favor do Skywalker. Retorno decrescente: o benchmark é fraco aqui e mesmo assim é 10 no total.
- **Mudança.** Nenhuma nova. Congelar; não gastar minutos do relógio aqui.

### 1.11 Engineering Judgment (4%)

- **Skywalker.** Cada mecanismo vem com o porquê e com o que ficou de fora; limitações listadas no fim, uma por item,
  com o custo de corrigir (`README.md:622-649`); escolhas explicadas por falha observada (`README.md:238-244`,
  `:270-274`, `:346-356`). Nenhuma métrica escolhida a favor.
- **V5.** ADRs com alternativa descartada, limites medidos. Mas o README dedica ~80 de 257 linhas à linha do tempo do
  git (`README.md:140-220`), o placar é denso, e o código do motor cita correções do avaliador e candidatos (ressalva
  de processo da v4, `feedback_v4_formal.md:13-24`).
- **Mudança.** (K, 20 min) Linha do tempo só em `docs/TIMESHEET.md`; o README fica com 1 frase + link. Remover do
  motor comentários que citam correções ou outros candidatos (o porquê técnico fica; a procedência fica em
  `PROCEDENCIA.md`).

---

## 2. Como o Skywalker responde aos 10 cenários oficiais

Fontes de dados do Skywalker: corpus de 9 URLs ingerido por chamada manual (`README.md:118-143`); banco mock SQLite
(`db/support_db/`); web search DuckDuckGo (`app/modules/tools/definitions/web_search.py:23-53`); grafo opcional,
desligado por padrão (`README.md:181`). Estratégia de corpus: **as URLs ingeridas são as mesmas que o golden usa como
ouro** (`README.md:129-137` × `app/modules/evaluation/seeds.py:33-38`, `:209`, `:576`, `:597`) — o corpus foi
escolhido a partir das perguntas, página de produto por produto.

**Como garante que o fato chega à resposta:** não garante por código. O README admite que a citação é exigida pelo
prompt e não validada (`README.md:266-267`). A probabilidade vem de: página certa no corpus; trechos grandes com o
título da seção embutido; k=5 com possibilidade de repetir a busca; especialista instruído a citar URL e a não
inventar (`seeds.py:96-100`); e um avaliador de fatos esperados para medir depois
(`langfuse_experiments.py:242-253`), sem resultado commitado. Nenhum número próprio diz se acerta.

| # | Cenário | Skywalker (desenho) | V5 (resposta real, `docs/DEMO.md`) |
|---|---|---|---|
| 1 | Clássica × Smart | Knowledge → `rag_search` sobre `/maquininha/get-classica/` e `/maquininha/get-smart/`; golden espera "CNPJ" e "60" (Smart só CNPJ; isenção a partir de R$ 60 mil/mês × R$ 10 mil da Clássica) (`seeds.py:197-213`; prompt cita a comparação, `seeds.py:91-92`) | **Escala ao humano** 3/3 (`DEMO.md:28`; `live_official.json` stability 0/3). Corpus sem página de produto da Clássica; só a linha de preço R$ 79,90 × R$ 129,90 |
| 2 | Clima POA amanhã | `web_search` genérico, sem data garantida (`seeds.py:641-655`, resposta "comportamental") | Open-Meteo não respondeu da nuvem; "não confirmei", sem número (`DEMO.md:41`) |
| 3 | Dinheiro de ontem | Support: overview + operations; banco sem `cliente1988` e datas absolutas → "sem registro" no `/chat` literal (§0) | **Melhor**: total R$ 745,50 e data por modalidade, por tool (`DEMO.md:54-58`) |
| 4 | Conta bancária para Pix | Knowledge sobre `/pix/`, `/duvidas/`, `/conta-digital/`; golden espera "Get Conta" e "key" (conta corrente, poupança ou de pagamento servem) (`seeds.py:564-580`) | **Escala ao humano** 3/3 (`DEMO.md:70`); corpus sem `/conta-digital/` e sem trecho que diga que conta de pagamento basta |
| 5 | Não conecta | Golden espera Support (devices, incidentes) **e** `rag_search` (`seeds.py:699-707`): o roteador LLM precisa chamar dois especialistas em sequência (o Support não tem `rag_search`, `seeds.py:187-192`) | **Bom**: T1988B offline por chip + passos do manual, oferta de chamado (`DEMO.md:83-95`) |
| 6 | Antecipação | Knowledge (grafo + RAG) sobre `/get-ajuda-antecipacao-de-venda/`; golden com resposta composta de 2 páginas (`seeds.py:582-600`) | Fraco: "as fontes não explicam o mecanismo geral" + 3 fatos laterais (`DEMO.md:108-112`); a página de ajuda de antecipação não foi ingerida (`SOURCES.md`, nota final) |
| 7 | Euro hoje | `web_search` | **Melhor**: PTAX do BCB com data do boletim e aviso de dia sem cotação (`DEMO.md:125`) |
| 8 | Erro de recusa | Support: incidentes + operações (`seeds.py:709-718`); não há transações de cartão nem códigos de recusa no banco | Diagnóstico **melhor** (TX1007 código 51, TX1008 código 05), mas termina abrindo caso porque o Knowledge não achou "o que fazer após recusa" (`DEMO.md:138-147`); 0/3 |
| 9 | Crediário parcelas | Knowledge; golden "48" (`seeds.py:57-71`) | Bom: até 48x com 3 citações (`DEMO.md:162`) |
| 10 | Link no WhatsApp | Knowledge sobre `/link-de-pagamento/` | Bom (`DEMO.md:175`) |

Leitura: **nos cenários de dados do cliente a V5 é objetivamente melhor; nos de conhecimento comparativo ela perde por
corpus e por busca de uma tacada só.** O avaliador, que não executa, vê o desenho do Skywalker como "vai responder" e
o DEMO da V5 como "não respondeu". Os 3 casos 0/3 (01, 04, 08) são determinísticos: consertá-los leva o pass^3 do
official de 0,6 para ~0,9 (palpite, se 02 seguir instável).

---

## 3. Estilo de evidência, estrutura do README e o que provavelmente deu o 10

**Estilo de evidência (fato).** Zero números. A avaliação é apresentada como **capacidade**: esquema do item golden
campo a campo, duas camadas e o custo de cada uma, definição de cada métrica RAGAS com link para a documentação
(`README.md:492-514`), e o que **não** está ligado ainda (context precision/recall, `README.md:504-509`, `:634-636`).
Honestidade: lista "Limitações conhecidas" com 8 itens, cada um com o efeito e o que faltaria (`README.md:622-649`),
inclusive bug de concorrência no Telegram (`:644-649`). Nenhuma métrica é escolhida a favor, porque nenhuma é
mostrada.

**Estrutura do README (fato).** Sumário; visão geral com diagrama ASCII de módulos e serviços e o fluxo de uma
mensagem numa linha (`README.md:34-61`); quickstart com Docker, local e "o que já vem pronto no primeiro boot"
(`:65-143`); mapeamento do desafio (`:147-171`); hiperparâmetros de RAG numa tabela (`:173-183`); arquitetura de
agentes com diagrama e 4 parágrafos de mecanismo (`:187-244`); pipeline RAG (`:248-274`); tools (`:278-294`); HITL
(`:298-337`); Telegram passo a passo (`:340-389`); API (`:393-411`); segurança (`:415-433`); avaliação e
observabilidade (`:437-544`); testes + estratégia de integração (`:548-577`); estrutura; `.env`; limitações. São 649
linhas, mais longo que o nosso (257), mas é **prosa explicativa**, sem tabelas de IC95. O avaliador reclamou da
densidade do nosso ("tabelas com IC95 repetidas por split", `feedback_v4_formal.md:214`), não do tamanho.

**O que provavelmente deu o 10 (palpite, em ordem de peso):**
1. O desenho do avaliador está literalmente no código: orquestrador LLM, especialistas como tools com passos
   aninhados, humano consultado de dentro do laço e o laço continua (`runner.py:243-295`; `escalation.py:21-50`).
2. Aparência de produto pronto: frontend com passos ao vivo e feedback, CRUD de agentes, Telegram sem túnel com QR,
   Langfuse provisionado, "tudo seedado no primeiro boot" (`README.md:104-116`). É a "maturidade de produto
   end-to-end" citada.
3. Corpus mirado nas páginas dos cenários + golden com resposta esperada extraída dessas páginas: o leitor vê que o
   fato certo está lá.
4. Nenhuma medida própria negativa sobre os oficiais; o gate semântico não tem contra o que disparar.
5. README que responde, com os títulos do enunciado, a tudo que o enunciado manda o README cobrir, e explica o porquê
   de cada escolha com uma falha observada.

O que **não** deu o 10: CI, testes, escala, hardening, número. A V5 já é superior nisso; mais esforço ali tem retorno
baixo.

---

## 4. Top 10 mudanças no kit, por ganho esperado de nota por minuto

Ganho = palpite em pontos da nota final ponderada (0–10), ancorado no "Caminho para 9,5" do avaliador
(`feedback_v4_formal.md:282-339`: oficiais +0,20; busca +0,27; memória +0,10; humano retoma o plano +0,25).

| # | Mudança (desenho próprio) | K antes do relógio | D no relógio | Ganho (palpite) | Critérios |
|---:|---|---:|---:|---:|---|
| 1 | **Corpus por entidade oficial**: regra + teste "toda maquininha/produto nomeado num cenário oficial tem a página de produto ingerida e ao menos 1 trecho dela no índice"; frente K lista as URLs a partir da SPEC | 15 min | 5 min | +0,15 | RAG, Business, gate semântico |
| 2 | **README sem sobra do kit e com os títulos do enunciado**: quickstart gerado do 1º caso oficial (teste reprova exemplo fora do split); seções "Message workflow", "RAG pipeline: ingestion → storage → retrieval → generation", "Testing strategy (unit/integration/live)"; tabela "requisito do enunciado → onde"; linha do tempo fora do README | 20 min | 0 | +0,08 | Challenge Fit gate, Business, Judgment |
| 3 | **`insufficient` volta ao supervisor LLM** (atalho de tabela só para `ok`): ele vê o resultado e decide responder parcial com oferta, pedir outro agente ou abrir caso; DEMO mostra decisão + motivo; knowledge respondível nunca vira handoff por FALLBACK fixo | 30 min | 0 | +0,10 | Orchestration, Business, HITL |
| 4 | **Métrica e gate "oficiais resolvidas"**: sem handoff + fatos de referência (regex por caso na SPEC) + fonte; pass^3 dela no placar; grounded e helpful lado a lado; gate ao vivo 1× dos oficiais de conhecimento antes do merge da K | 30 min | 5 min | +0,10 | Evaluation, gate semântico, Judgment |
| 5 | **Busca agentic no Knowledge**: busca como tool do LLM, decomposição por entidade em comparações, consulta en→pt, k=5, até 3 buscas dentro do orçamento; portão de cosseno só offline; rerank já fixado antes do relógio (N3) | 75 min | 0 | +0,20 | RAG, Business, Memory |
| 6 | **Troubleshoot sem escalada quando o Support resolveu**: se `records` trouxe o diagnóstico e o `faq` não tem manual, responde com o diagnóstico + oferta de chamado/humano (official-08) | 20 min | 0 | +0,05 | Business, Orchestration |
| 7 | **Limpeza de procedência no motor**: remover comentários que citam correções/candidatos; procedência só em `PROCEDENCIA.md`; placar do README com ≤ 8 linhas e o resto em `RESULTS.md` | 20 min | 0 | +0,05 | Judgment, Challenge Fit (ressalva de processo) |
| 8 | **Router como reescritor**: recebe as 3 últimas falas e devolve `standalone_query` usada por busca e tools; testes por padrão de seguimento | 45 min | 0 | +0,08 | Memory, RAG, Orchestration |
| 9 | **DEMO com árvore de passos**: por caso, agente → tool → args → prévia do resultado → ms, e antes/depois das escritas; 1 transcrição multi-turno com memória e humano | 40 min | 0 (gerado) | +0,05 | Orchestration, Tools, Evidence gate |
| 10 | **Consulta síncrona ao operador com espera limitada** antes do ticket; se a resposta chega, o plano continua no mesmo turno; teste com operador simulado e transcrição no DEMO | 75 min | 0 | +0,07 | HITL, Orchestration |

Fora do top 10 (ganho/minuto menor): login com senha para os lojistas do fixture (40 min, +0,03); versão de prompt
no log e 👎 → candidato a caso (30 min, +0,03); antes/depois no resultado de escrita (15 min, +0,02). Nada novo em
Production Engineering.

Ordem de execução sugerida no kit: 1, 2, 3, 4 (≈ 95 min de kit, 10 min de domínio) já atacam os três 0/3 do
official e o que o avaliador lê primeiro; depois 5 e 6 (≈ 95 min); 7–10 se sobrar.


## 5. O que o kit v5.4 copiou daqui (ideias, sem código nem texto do Skywalker)

| Ideia do Skywalker | No kit | Onde |
|---|---|---|
| humano como consulta síncrona: o turno espera a resposta e o laço continua (`escalation.py`, `integrations/service.py`) | espera limitada `HITL_SYNC_WAIT_S` antes de virar caso assíncrono; resposta dentro do prazo vira evidência e os passos pendentes rodam no mesmo turno; fila, SLA, especialidade e quatro olhos ficam como estavam | `src/app/hitl_sync.py`, `supervisor._continue_with_operator`, `resume.resume_after_human` (não repete a resposta), `tests/test_v54_hitl_sync.py` |
| resultado de escrita com o antes e o depois | `actions.record_change`: antes, depois, o que mudou e o que ficou igual em toda escrita executada; domínio example implementa | `src/app/actions.py`, `src/app/domain/example.py`, `tests/test_v54_write_before_after.py` |
| trace legível por caso | árvore de passos na resposta do `/chat` (`steps`: agente, status, ms, ferramenta, args, prévia mascarada) e no DEMO; transcrição multi-turno gerada (memória, ação com antes/depois, humano durante a espera) | `supervisor.step_view`, `scripts/demo_md.py --transcript`, `evals/demo_transcript.jsonl`, `tests/test_v54_demo_steps.py` |
