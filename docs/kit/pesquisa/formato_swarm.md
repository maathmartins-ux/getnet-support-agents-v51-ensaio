# Pesquisa v5: soluções públicas do formato "Multi-Agent Support System" (Getnet) e "Agent Swarm" (CloudWalk)

Data: 01/11/2026. Base de comparação: `/home/user/kit-preflight/docs/kit/REFERENCIAS.md` (o que já sabíamos) e
`/home/user/getnet-support-agents-v4/README.md` (o que a v4 já tem). Este relatório só traz o que é **novo**.
Ideias foram lidas e descritas com palavras próprias; nenhum código foi copiado.

Pesos da Régua V4 (fonte: [feedback do DiogoOg16](https://raw.githubusercontent.com/DiogoOg16/getnet/main/feedback_diogoog16_v4(1).md)):
Orquestração 15% · Avaliação 14% · Segurança 13% · RAG 10% · Tools 10% · Business Fit 8% · Memória 8% ·
HITL 7% · Observabilidade/Custo 6% · Produção 5% · Julgamento 4%.

Pontos fracos medidos da v4 que orientaram a escolha (todos no README da v4, §5):
Recall@3 **0,486** e rerank sem ganho (0,486 = 0,486); falhas de checagem numérica ao vivo (memory 14, official 6,
parallel 2), quase todas em clima/câmbio, porque a busca web cifra o corpo da página
(`evals/results/live_memory.json`: q-mem-07, q-mem-08, q-mem-11, q-mem-12); memory ao vivo com pass^3 **46,2%**;
`language_acc` offline do official **50%**; p50 ao vivo de 7 a 22 s; compose padrão **sem volume**
(`docker-compose.yml`), então o SQLite some num `down`/`up`; sem `/ready`, sem retenção nem apagamento de dados.

---

## As 10 ideias de maior impacto que o kit ainda não tem

Esforço: **P** ≤ 1 h no kit (antes do relógio) · **M** 2–4 h · **G** > 4 h.

| # | Ideia (mecanismo) | Evidência | Critério da régua | Esforço |
|---|---|---|---|---|
| 1 | **Evidência web de página inteira.** Para clima, câmbio e notícia, baixar o texto das 3 a 5 primeiras páginas do resultado (com data e local), guardar como evidência do turno e só então redigir. A checagem numérica passa a enxergar o valor que hoje vem cifrado. Na nossa pilha: ligar a tool de *web fetch* do provedor ao lado do *web search*, ou buscar no servidor as URLs citadas (com allowlist de host e limite de bytes) | Krystian-Keller, linha "Full-page web evidence" do [README](https://raw.githubusercontent.com/Krystian-Keller/IA_HARDCORE_ENGINEER_GETNET/HEAD/README.md). Nosso problema: v4 §9 ("a checagem numérica só enxerga os trechos citados") e as falhas `numbers` de memory/official/parallel | RAG 10% · Avaliação 14% | P–M |
| 2 | **Ingestão que não perde conteúdo.** (a) Snapshots versionados das páginas montadas por JavaScript (catálogo de maquininhas, tabela de taxas), capturadas num navegador e commitadas; (b) manifesto por página com URL, data, método de captura e hash; (c) não remover modais de FAQ (as respostas da Getnet ficam dentro de `o-modal`); (d) lista curada que inclui as páginas de erro do terminal (ADQ 1-18…) e exclui página velha que contradiz a atual | lauroPereira: snapshots renderizados e Recall@6 = 1,00 em 14 perguntas EN/PT ([README](https://raw.githubusercontent.com/lauroPereira/ai-getnet-case/HEAD/README.md), seção RAG). andremelo97: filtro amplo de `modal` deixou 86 caracteres numa FAQ; 42 URLs curadas; `/duvidas/pix/` de 2020 excluída ([README](https://raw.githubusercontent.com/andremelo97/Getnet-Desafio-Tecnico-AI-Hardcore-Engineer/HEAD/README.md), §5). Nosso problema: v4 §9 (AC-01 sem comparação Clássica × Smart; tabela cortada no ingest) | RAG 10% · Business Fit 8% | M (script de captura no kit; captura no relógio) |
| 3 | **Trecho com contexto e busca diversificada.** Cortar por seção (título → parágrafos), nunca partir tabela; prefixar cada trecho com `[mercado] título da página › seção`; limitar a 2 trechos por URL no top-k; medir Recall@k **por página** ao lado do por trecho (o avaliador lê 0,486 como fraco sem saber que é por trecho) | Prefixo com título: andremelo97 §5 e rrehlert ([README](https://raw.githubusercontent.com/rrehlert/getnet-ai-engineer-challenge/HEAD/README.md)); tabelas inteiras e no máximo 2 por documento: maluake §7 ([README](https://raw.githubusercontent.com/maluake/desafio/HEAD/README.md)); `max_chunks_per_url=2`: CaioPereir4 ([README](https://raw.githubusercontent.com/CaioPereir4/multi-agent-support-system/HEAD/README.md)); resumo da página no cabeçalho do trecho: Buzz (`/home/user/refs/luiznogueira1210-doc_agent-swarm-case/README.md`, "Ingestion") | RAG 10% · Avaliação 14% | P |
| 4 | **Estado do caso com resolução por evidência.** O caso vai de `in_progress` a `awaiting_customer` após cada resposta e só fica `resolved` com prova (`customer_confirmed` ou `tool_verified`); "obrigado" sozinho nunca resolve (rota `acknowledgement`); cada passo de troubleshooting fica registrado e não se repete; depois de 2 ciclos sem sucesso o caso vai ao humano levando as tentativas. Variante: o sistema **oferece** o humano após 3 respostas e insatisfação, e só enfileira com o aceite | lauroPereira, seção "Conversations and case follow-up" ([README](https://raw.githubusercontent.com/lauroPereira/ai-getnet-case/HEAD/README.md)); marcatto77, rota `clarify` com oferta e aceite ([README](https://raw.githubusercontent.com/marcatto77-dev/getnet-agent-workspace/HEAD/README.md)). Nosso problema: memory ao vivo pass^3 46,2% | Memória 8% · HITL 7% · Business Fit 8% | M |
| 5 | **Orçamento em tempo de execução.** Tetos por request (chamadas de modelo, chamadas de tool, segundos, US$) e um livro-caixa persistente da instalação com **reserva atômica antes** de cada chamada paga; preço desconhecido bloqueia a chamada; `/ready` mostra o saldo. Hoje o teto de US$ só existe no eval (`--max-usd`) | lauroPereira: `BUDGET_LIMIT_USD`, `MAX_REQUEST_COST_USD`, `MAX_MODEL_CALLS`, `MAX_TOOL_CALLS`, `MAX_REQUEST_SECONDS` e livro-caixa ([README](https://raw.githubusercontent.com/lauroPereira/ai-getnet-case/HEAD/README.md), "Configuration" e "Guardrails"); o projeto inteiro gastou US$ 0,69 de US$ 5 | Observabilidade/Custo 6% · Segurança 13% (abuso) | P–M |
| 6 | **Guardrail de saída contra ação inventada.** Reprovar frase que afirma ação não executada no turno ("reiniciei sua maquininha", "abri o chamado", "estornei") comparando com a tabela de ações/tickets; canário no prompt de sistema para detectar vazamento; manter em `sources` só URLs que uma tool realmente devolveu e só IDs de citação existentes | marcatto77: "detecção de canário e afirmações de ações não executadas" e "IDs de citação validados" ([README](https://raw.githubusercontent.com/marcatto77-dev/getnet-agent-workspace/HEAD/README.md), tabela de controles); andremelo97: `verify_sources` e evento `sources.unverified_dropped` (§5 e §8) | Segurança 13% · Tools 10% | P |
| 7 | **Modelo falso que grava cada prompt.** O fake usado nos testes guarda tudo o que recebe; aí viram testes de propriedade: o LLM nunca viu o número do cartão; o Customer Support só viu dados do próprio lojista; o agente de escalonamento recebeu o motivo do especialista | andremelo97, §9 "How to integration-test the orchestration comprehensively" ([README](https://raw.githubusercontent.com/andremelo97/Getnet-Desafio-Tecnico-AI-Hardcore-Engineer/HEAD/README.md)). Na v4, `tests/fakes.py` não guarda os prompts | Avaliação 14% · Segurança 13% | P |
| 8 | **Diretiva de idioma por turno.** Colocar no início de cada turno "responda estritamente em <idioma>, mesmo que a ferramenta ou o trecho esteja em outra língua", e checar o idioma da saída (reescrever uma vez se errar). A regra só no prompt de sistema deixava respostas em PT vazarem para EN | jonathansschaffer, "Language reliability" no README e `app/agents/knowledge_agent.py:129` (`/home/user/refs/jonathansschaffer_cloudwalk-agent-swarm`). Nosso problema: `language_acc` offline do official 50%; falhas de idioma ao vivo em approval (2), parallel (3), memory (1) | Business Fit 8% · Avaliação 14% | P |
| 9 | **Respostas reais gravadas no README.** Os 10 cenários com request e response HTTP reais (agentes, tools, fontes, `request_id`) em blocos recolhíveis, gerados pelo `fill_readme` a partir de `live_official.json`. O avaliador revisa sem chave e sem vídeo | Krystian-Keller, "Review the project without an API key" e "Recorded execution" ([README](https://raw.githubusercontent.com/Krystian-Keller/IA_HARDCORE_ENGINEER_GETNET/HEAD/README.md)). O feedback do DiogoOg16 diz "Vídeo informado … **não assistido**": a prova precisa estar no texto | Business Fit 8% · Julgamento 4% | P |
| 10 | **Produção que sobrevive a reinício e a auditoria.** Volume nomeado no compose padrão; overlay endurecido (rootfs `read_only`, `cap_drop: ALL`, `no-new-privileges`, limites de CPU, memória e pids, `tmpfs`, rotação de log, porta em `127.0.0.1`); `/health` (vivo) separado de `/ready` (índice, banco, orçamento); retenção por TTL (`MEMORY_RETENTION_DAYS`) e `DELETE` dos dados do próprio usuário (LGPD) | gabriel-dezani: feedback com Infra/Docker **8,5**, a menor nota dele, e o overlay "hardened" ([EVOLUCAO_FEEDBACK_9_2_PARA_9_8.md](https://raw.githubusercontent.com/gabriel-dezani/multi-agent-support/HEAD/docs/EVOLUCAO_FEEDBACK_9_2_PARA_9_8.md)); jonathansschaffer: `DELETE /auth/me` com `ON DELETE CASCADE` (README, "LGPD compliance"); lauroPereira e marcatto77: `/ready` | Produção 5% · Memória 8% · Segurança 13% | P–M |

### Logo abaixo do corte (valem se sobrar tempo)

- **Faixas rápidas para latência.** Saudação, agradecimento e despedida respondidos sem LLM (vrsolutionsaas, rota
  "Atendimento"); *fast-pass* de mensagem benigna pula o guardrail LLM (Buzz, "Stage 1b"); cache de resposta só
  para intenção de conhecimento, com chave (idioma, pergunta normalizada), nunca para suporte, bloqueio ou
  escalonamento (jonathansschaffer, `app/cache.py`). Ataca o nosso p50 de 7 a 22 s. Observabilidade/Custo 6%. P.
- **Versão do prompt no trace.** Prompts com `id` + `version`; cada trace registra qual versão rodou
  (lauroPereira; `PROMPT_VERSION` em CaioPereir4; maluake mostra a versão no `/health`). Avaliação. P.
- **Tempo por nó na resposta** (`timings_ms` por etapa e `path`): Bepaiva
  ([README](https://raw.githubusercontent.com/Bepaiva/bbspj-multi-agent-support/HEAD/README.md)). Observabilidade. P.
- **Glossário de status do CRM.** Status original preservado e traduzido (por exemplo, "lote processado" não é
  "dinheiro na conta"); só se diz "creditado" quando a tool de pagamento confirma (lauroPereira). Tools. P.
- **Impressão digital do índice.** O nome da coleção é o hash de corpus + modelo + parâmetros de corte; o índice
  muda sozinho quando algo muda (rrehlert; manifesto do lauroPereira; Eiki usa só a lista de URLs). Produção. P.
- **Reserva atômica do turno por conversa.** Duas mensagens simultâneas na mesma conversa não rodam em paralelo;
  a reserva expira em 10 min (Krystian-Keller, "atomic turn claims"). Memória. P.
- **Enquanto o caso está com o humano, as ferramentas não rodam.** As mensagens novas só são guardadas para o
  operador (gabriel-dezani, "Atendimento humano completo", item 2). HITL. P.
- **Juiz on-line por amostragem** em segundo plano, com falha que nunca afeta a resposta (rrehlert; plano do
  andremelo97 §8). Avaliação. M.
- **Categoria de guardrail para lavagem de dinheiro e sonegação** ("lavar dinheiro", "sem declarar",
  "estruturar pagamento"): Buzz, `app/guardrails/guardrails.py`. Para autoagressão, resposta de apoio com
  CVV 188 (maluake §9). Segurança. P.
- **Versionar a base de conhecimento** (rascunho, coleção candidata, teste, ativação e rollback), em
  lauroPereira v0.5.0. É G e fora do relógio, mas cabe no "próximos passos".

---

## Parte A — repositórios já clonados (lidos localmente, sem clonar nem dar push)

### A1. EikiYamashiro/cloudwalk_agent_swarm (CloudWalk/InfinitePay)

Caminho: `/home/user/refs/EikiYamashiro_cloudwalk_agent_swarm`. **Licença: nenhuma** (sem arquivo LICENSE).

- **Tempo (git log):** 8 commits, de 12/02/2026 18:16 a 23/02/2026 12:09, em três dias de trabalho
  (12/02: 1; 22/02: 3; 23/02: 4). Há o primeiro commit e uma "new version with guardrails, agent transfer and
  postgres" dez dias depois. Não é entrega de 60 minutos.
- **Arquitetura:** LangGraph com classificador → `safe_response` | `knowledge` | `customer_support` | `transfer`;
  LangGraph `MemorySaver` (em memória); Postgres para clientes, transferências e eventos de guardrail; front em React.
- **Ideias que valem como ideia:**
  - O Router também é o classificador de segurança. Uma só saída estruturada traz rota, `safety_decision`,
    `safety_category` (`prompt_injection`, `security_bypass`, `malicious_intent`) e `blocked_reason`
    (`utils/agents/router_agent.py`).
  - Defesa em profundidade: cada nó especialista confere de novo `safety_decision` antes de rodar e grava o bloqueio
    numa tabela `guardrail_events` com `blocked_at_node` e índice por usuário (`services/agent_service.py`,
    `services/db_service.py`).
  - A identidade chega às tools por `contextvars` (`services/request_context.py`); a tool de transferência nunca
    recebe `user_id` do modelo.
  - Teto determinístico de valor de transferência (`MAX_TRANSFER_AMOUNT`) e de tamanho de mensagem.
  - Reindexa quando muda o sha256 da lista de URLs (`chroma_infinitepay_db/sources.sha256`). Só detecta URL nova,
    não conteúdo novo.
  - O eval do router salva, para cada caso, a saída crua do classificador e a lista de erros, ao lado da matriz
    (`tests/results/router_agent_metrics_*.json`). Isso já está no kit como matriz; o que falta é **guardar a saída
    crua por caso**.
- **Números publicados:** acurácia **0,9565**, precisão e recall macro **0,964**, F1 **0,9615** em **23 casos**,
  1 erro ("Pode analisar minhas movimentacoes recentes?" foi para `customer_support`). Arquivo:
  `tests/results/router_agent_metrics_20260223_013302.json` e a imagem da matriz.
- **Como avaliam:** teste `@pytest.mark.integration` que chama o LLM real, sem gate (só verifica se os arquivos
  foram gerados). Sem juiz, sem golden set de RAG.
- **Guardrails:** tamanho de entrada (2.000 caracteres), limite de transferência, LLM classificador.
  `sanitize_output` não faz nada (devolve o texto como está).
- **HITL:** tool que manda mensagem num webhook do Slack. Sem fila, sem retorno do operador.
- **RAG:** Chroma, 1.200/200 caracteres, k=4, relevância > 0,52; abaixo disso vai para a web (Serper).
  Sem rerank, sem citação verificada.
- **Observabilidade e CI:** nenhuma; sem `.github`. O repositório commitou um `venv` do Windows e o índice Chroma.

### A2. jonathansschaffer/cloudwalk-agent-swarm (CloudWalk/InfinitePay)

Caminho: `/home/user/refs/jonathansschaffer_cloudwalk-agent-swarm`. **Licença: nenhuma.**

- **Tempo (git log):** 44 commits, de 13/04/2026 14:12 a 15/04/2026 14:55 (cerca de 48 h, com commits de
  madrugada: 6 às 03h). Não é 60 minutos.
- **Arquitetura:** LangGraph (guardrails → router → Knowledge RAG | Knowledge web | Support (3 tools) | Escalation);
  Postgres via SQLAlchemy (SQLite em dev); bot do Telegram; deploy no Railway.
- **Ideias que valem como ideia:**
  - **Diretiva de idioma por turno** (ideia nº 8 do topo; `app/agents/knowledge_agent.py:129`).
  - **Cache de resposta só para conhecimento**, com chave (idioma + pergunta normalizada), sem guardar resposta
    bloqueada ou escalada nem dado de CRM; troca por Redis isolada num arquivo (`app/cache.py`;
    `tests/unit/test_cache.py`).
  - **Reindexação incremental por hash de conteúdo por URL:** só re-embeda a página que mudou e troca os trechos
    dela (`tests/rag/test_incremental_rag.py`).
  - **Documentos semente** para páginas que o scraper não alcança, adicionados só se a URL não veio no scraping
    (`app/rag/pipeline.py`, `_SEED_DOCUMENTS`).
  - **Teste de paridade EN↔PT:** cada par de perguntas precisa ter ao menos uma URL em comum no top-k
    (`tests/rag/test_rag_cross_language.py`, 4 pares). O par EN/PT já está no kit; o que é novo é **afirmar
    sobreposição de fonte entre as duas línguas**, não só acerto de cada uma.
  - Desvio do contrato declarado e testado: `user_id` sai do JWT, não do corpo (README, "Deviation…").
  - Rate limit empilhado: por IP (20/min) e por hash do token (30/min); IP real lido do `X-Forwarded-For` com
    número de saltos confiáveis; bloqueio de conta após 10 falhas; captcha após 3.
  - Tabela `audit_events` só de inserção; `/metrics` atrás de token; `/docs` desligado por padrão; cabeçalhos de
    segurança (CSP, HSTS, X-Frame-Options); `DELETE /auth/me` com cascata (LGPD); deduplicação de ticket aberto
    em 24 h; SSE em `/chat/stream`; script k6.
  - "Melhorias" bem escolhidas para o README: canários de prompt injection no CI (garak/promptfoo), varredura
    OWASP ZAP no CI, auditoria de PII **antes** de embedar quando o corpus incluir transcrições.
- **Números publicados:** `/health` com `documents_indexed: 225`; "144 tests" no README (contei 113 funções
  `def test`, com parametrização pode chegar a 144); limiares Recall@K ≥ 0,80 e MRR ≥ 0,60 em 8 perguntas
  (`tests/rag/test_rag_eval.py`), sem resultado commitado; "self-assessed weighted score 9.0/10" de pentest,
  apontando para `security-assessment-report.md`, **que não está no repositório**.
- **Como avaliam:** testes de unidade com Anthropic simulado; integração com chamadas reais; eval de retrieval como
  gate. O golden set casa por **substring da URL** (por exemplo, "maquininha"), o que é leniente e infla o recall.
  Não usar como referência de número.
- **Guardrails:** regex com variantes em português, classificador Claude, bloqueio de HTML e XSS, mascaramento de
  CPF, cartão, telefone e e-mail na saída. 16 testes de regressão de pentest (`tests/security/test_security.py`).
- **HITL:** agente de escalonamento cria ticket (ID com UUID), deduplicado em 24 h; sem operador respondendo.
- **RAG:** MiniLM multilíngue, Chroma, 800/100 caracteres, top-5; sem rerank.
- **Observabilidade:** Prometheus, LangSmith opcional, `X-Process-Time`, log por turno. **Sem CI.**

### A3. luiznogueira1210-doc/agent-swarm-case, "Buzz" (CloudWalk/InfinitePay)

Caminho: `/home/user/refs/luiznogueira1210-doc_agent-swarm-case`. **Licença: nenhuma.**

- **Tempo (git log):** 42 commits, de 14/04/2026 16:53 a 27/04/2026 08:40 (13 dias, 7 dias com commit). O padrão
  de mensagens `feat(phase-03/plan-02)` indica fluxo guiado por plano em fases.
- **Ideias que valem como ideia:**
  - **Enriquecimento contextual do trecho:** um resumo de 2 a 3 frases da página, gerado por LLM na ingestão, vai no
    cabeçalho de cada trecho junto com a URL (README, "Ingestion").
  - **Expansão de consulta em 3 ângulos** (literal, conceitual e por palavra-chave), recuperação mista 60% vetor e
    40% BM25, deduplicação, limiar 0,45; depois uma **autoavaliação CRAG** (`grounded`, `responsive`) contra o
    contexto recuperado; se as duas falham, vai para a web (`app/core/prompts.py`, `CRAG_EVAL_PROMPT`,
    `QUERY_EXPANSION_PROMPT`).
  - **Router com confiança:** regex primeiro; LLM só no ambíguo; confiança abaixo de 0,7 vai para o humano.
  - **RiskAgent em paralelo ao Support,** com regras de combinação escritas no prompt (por exemplo, "suspenso +
    estorno = HIGH") e saída tipada com `human_briefing`. **Quem decide escalar é o código, não o LLM.**
  - **Agente de redirecionamento sem LLM:** monta o pacote do handoff de forma determinística.
  - **Inteligência de operação em segundo plano:** cada interação é classificada depois da resposta e salva; há
    `/ops/insights`, `/ops/escalations` e `/ops/briefing` (resumo para a operação). Falha nunca bloqueia a resposta.
  - **Memória de usuário entre sessões** como resumo corrido, lido por tool no início da conversa.
  - **Guardrail com resultado "reframe":** a mensagem limítrofe é reescrita de forma neutra em vez de bloqueada.
  - **Categoria de guardrail fintech:** lavagem de dinheiro, sonegação, "estruturar pagamento", país sancionado.
  - Testes com **SQLite real** e fixture que recarrega a semente, em vez de simular funções de banco.
- **Atenção, alegações sem lastro no código:**
  - O README lista `test_prompt_regression.py`, `test_load.py` e `test_rag_quality.py`, que **não existem** em
    `tests/`.
  - O README descreve guardrails de saída (vazamento entre usuários, promessa financeira, compromisso legal), mas
    `grep` em `app/` não encontra implementação; `app/guardrails/guardrails.py` só tem a checagem de entrada. A
    REFERENCIAS.md cita essas flags como ideia do Buzz: a ideia é boa, mas no Buzz ela está só no texto.
  - Os números "~50% do tráfego no regex" e "~90% no fast-pass" não têm medição no repositório.
  - O nosso `tests/test_evidence.py` existe justamente para impedir esse tipo de falha.
- **Números publicados:** 186 documentos no Chroma; 18 URLs. Nenhuma métrica de qualidade commitada.
- **Como avaliam:** LLM simulado com `unittest.mock`; 76 funções de teste; `TEST-STRATEGY.md` com tabela
  cenário → arquivo → função. Sem golden set de RAG commitado e **sem CI**.
- **HITL:** handoff estruturado e tabela `escalations` com contagem de contatos; sem resposta do operador.
- **Observabilidade:** `ops.db` com `interaction_logs`; painel React.

---

## Parte B — outras soluções públicas achadas na web

Busca feita com WebSearch; READMEs lidos de `raw.githubusercontent.com` (download direto do arquivo, sem clonar).
"Nota" só quando o próprio repositório ou um feedback publicado a traz. Licença conferida na raiz do repositório.

| Repositório | Nota pública | Licença | 1 a 3 ideias valiosas | Verificação |
|---|---|---|---|---|
| [lauroPereira/ai-getnet-case](https://github.com/lauroPereira/ai-getnet-case) | sem nota; diz "validated by an independent review" | nenhuma | estado do caso com resolução por evidência; orçamento com reserva atômica; snapshots renderizados por JS e Recall@6 = 1,00 (14 perguntas); prompts versionados com a versão no trace; checagem de valor, data e % contra a evidência, removendo a frase ofensiva | README lido |
| [gabriel-dezani/multi-agent-support](https://github.com/gabriel-dezani/multi-agent-support) | **9,2/10 (V6)**, por critério: Arquitetura 9,5 · Orquestração 9,2 · RAG 9,2 · Segurança 9,2 · Testes 9,4 · Observabilidade/evals 8,8 · Memória 9,0 · HITL 9,5 · **Infra 8,5** · Produto 9,3 · Trade-offs 9,6. Fonte: [AUDITORIA_FEEDBACK_9_2_META_9_6.md](https://raw.githubusercontent.com/gabriel-dezani/multi-agent-support/HEAD/docs/AUDITORIA_FEEDBACK_9_2_META_9_6.md). O próprio autor diz que a V7/V8 **não** foi reavaliada | nenhuma | overlay Docker endurecido e `/ready`; `/ops/slo` com `pass/fail/insufficient_data` (falta de amostra não conta como sucesso); erro de provedor web (401/429/5xx) tratado como incidente de infra, não como pedido de humano; ferramentas congeladas enquanto o caso está com o humano | nota tirada do texto do autor; o feedback original (`feedback_gabriel_dezani_02.md`) **não é público**. Os nomes dos critérios diferem da Régua V4 (talvez uma régua anterior, "V2"); **não verificado** que seja a mesma régua. Muitas versões, logo não é de 60 min |
| [andremelo97/Getnet-Desafio-Tecnico-AI-Hardcore-Engineer](https://github.com/andremelo97/Getnet-Desafio-Tecnico-AI-Hardcore-Engineer) | sem nota | nenhuma | fake que grava os prompts e vira teste de propriedade; aritmética no código (`deposits_by_date`, centavos em `Decimal`, "nunca some valores" no prompt); `verify_sources`; manter modais de FAQ; "falha vira handoff, nunca 500", com teste de LLM totalmente fora; diz ter gravado a sessão de desenvolvimento **dentro dos 60 min** ([vídeo](https://youtu.be/AcEbuzerHjs)) | README lido; os 60 min **não verificados** (não vi o vídeo nem o git log) |
| [maluake/desafio](https://github.com/maluake/desafio) | sem nota | nenhuma | trechos por título com tabelas inteiras e no máximo 2 por documento; corpus semente curado com front-matter citando as fontes públicas (inclusive PDFs da Getnet); tool `explain_decline_code` (códigos ABECS); feriados no motor de liquidação; perfil `observability` com Grafana e alertas; aviso honesto "30/30 offline é linha de base de regressão, não alegação de qualidade" | README lido. Arquitetura muito parecida com a nossa (mesmo modelo, *effort* por papel, `fallbacks` de recusa) |
| [Krystian-Keller/IA_HARDCORE_ENGINEER_GETNET](https://github.com/Krystian-Keller/IA_HARDCORE_ENGINEER_GETNET) | sem nota | nenhuma | evidência web de página inteira; as 10 respostas HTTP reais gravadas no README; reserva atômica de turno por conversa; HITL que persiste a interrupção e retoma com a evidência salva; "239 passed" | README lido |
| [Krystian-Keller/IA_HARDCORE_ENGINEER](https://github.com/Krystian-Keller/IA_HARDCORE_ENGINEER) | sem nota | nenhuma | versão anterior e menor (TF-IDF, 15 casos de eval com PASSED/FAILED) | README lido |
| [marcatto77-dev/getnet-agent-workspace](https://github.com/marcatto77-dev/getnet-agent-workspace) | sem nota | nenhuma | canário e checagem de ação não executada na saída; oferta de humano com aceite; quarentena de conteúdo suspeito na ingestão com revisão do admin; `/api/health/live` × `/ready` com `degraded`; central de atendimento com WebSocket; teste Playwright do painel | README lido |
| [vrsolutionsaas-afk/getnetAgent](https://github.com/vrsolutionsaas-afk/getnetAgent) | sem nota | nenhuma | **demo on-line no Railway** com Swagger; rota "Atendimento" sem LLM para saudação e agradecimento; conta bancária retirada do resultado da tool antes de ir ao modelo | README lido; a demo não foi testada |
| [rrehlert/getnet-ai-engineer-challenge](https://github.com/rrehlert/getnet-ai-engineer-challenge) | sem nota | nenhuma | nome da coleção = hash de corpus + modelo + corte; limiar ajustado por medida (relevante ≥ 0,58, fora do tema ≤ 0,34); dois juízes LLM em segundo plano no tráfego | README lido |
| [CaioPereir4/multi-agent-support-system](https://github.com/CaioPereir4/multi-agent-support-system) | sem nota | nenhuma | `max_chunks_per_url=2`; índice que sobrevive a uma atualização com falha; distribuição de score medida (fora do tema 0,29 a 0,31 × certo 0,40 a 0,57); `PROMPT_VERSION` | README lido (AWS Bedrock) |
| [Bepaiva/bbspj-multi-agent-support](https://github.com/Bepaiva/bbspj-multi-agent-support) | sem nota | nenhuma | `timings_ms` por nó e `path` na resposta; webhook de handoff (Teams/Slack); `evals --fake` para testar o próprio harness | README lido |
| [LeonardoColotino/ai-hardcore-engineer](https://github.com/LeonardoColotino/ai-hardcore-engineer) | sem nota | nenhuma | "segunda tentativa", local primeiro (Ollama, vetores em NumPy); 46 testes e 17 casos offline | README lido; pouco a copiar |
| [Fredyycloss/desafio-getnet-multi-agente](https://github.com/Fredyycloss/desafio-getnet-multi-agente) | sem nota | **MIT** | testes por perfil do compose (`docker compose --profile test run`); pouco além disso (25 testes, vídeo pendente) | README lido |
| [maathmartins-ux/getnet-multi-agent-support](https://github.com/maathmartins-ux/getnet-multi-agent-support) e [getnet-agents-sdd](https://github.com/maathmartins-ux/getnet-agents-sdd) | — | — | são tentativas anteriores do próprio dono (conta do usuário); a REFERENCIAS.md registra 8,18 para a v2 | não reavaliado aqui |

**CloudWalk "Agent Swarm":** a busca não achou repositório novo além dos três já clonados. A página
[CloudWalk Nimbus](https://www.cloudwalk.io/nimbus) lista desafios por nível, com entrega por e-mail, sem ranking
público.

**"Régua V4" e rankings:** fora do feedback do DiogoOg16 (já na REFERENCIAS.md: 4,7, 28º lugar, "abaixo de Paulo
Arthur (5,4) e acima de Arthur Di Lorenzo (3,9)"), não achei outro ranking publicado. Duas observações novas tiradas
desse feedback:
1. O avaliador lê um commit fixo ("branch `main`, commit `1abb2a0`") e atribui autoria pelos commits.
2. "Vídeo … **não assistido**": a prova precisa estar no README e no repositório (ideia nº 9).

As buscas por "Régua V4" e "Nota V4" na web não retornaram nada relevante.

---

## Alertas para não copiar errado

- **Número de golden set leniente** (jonathansschaffer casa por substring de URL; Recall@6 = 1,00 do lauroPereira é
  em 14 perguntas) não se compara com o nosso Recall@3 por trecho. Se publicarmos recall por página, rotular
  "por página" e manter o "por trecho" ao lado.
- **Alegações sem arquivo:** o README do Buzz cita testes e guardrails que não existem; o do jonathansschaffer cita um
  relatório de pentest ausente. O nosso `test_evidence.py` e a regra "número = JSON commitado" seguem sendo
  diferencial: não afrouxar.
- **Nota do gabriel-dezani (9,2)** vem de um feedback privado, com nomes de critério diferentes da V4. Use como pista
  do que pesa (Infra e Observabilidade foram as menores), não como benchmark.
- **Nenhum dos três clonados tem CI** nem é de 60 minutos (11 dias, 2 dias e 13 dias pelo git log).
- **Licenças:** os três clonados e 12 dos 13 achados na web não têm LICENSE (todos os direitos reservados), então
  só a ideia pode ser reaproveitada. A exceção é o Fredyycloss, em MIT.

## Fontes

- Repositórios locais: `/home/user/refs/EikiYamashiro_cloudwalk_agent_swarm`,
  `/home/user/refs/jonathansschaffer_cloudwalk-agent-swarm`, `/home/user/refs/luiznogueira1210-doc_agent-swarm-case`.
- READMEs baixados de raw.githubusercontent.com (cópia em
  `/tmp/claude-0/-home-user/fcaab8c4-9c28-5f46-b6c6-1bfdc9006cfa/scratchpad/v5/raw/`):
  [lauroPereira](https://raw.githubusercontent.com/lauroPereira/ai-getnet-case/HEAD/README.md) ·
  [gabriel-dezani](https://raw.githubusercontent.com/gabriel-dezani/multi-agent-support/HEAD/README.md) ·
  [andremelo97](https://raw.githubusercontent.com/andremelo97/Getnet-Desafio-Tecnico-AI-Hardcore-Engineer/HEAD/README.md) ·
  [maluake](https://raw.githubusercontent.com/maluake/desafio/HEAD/README.md) ·
  [Krystian-Keller](https://raw.githubusercontent.com/Krystian-Keller/IA_HARDCORE_ENGINEER_GETNET/HEAD/README.md) ·
  [marcatto77-dev](https://raw.githubusercontent.com/marcatto77-dev/getnet-agent-workspace/HEAD/README.md) ·
  [vrsolutionsaas-afk](https://raw.githubusercontent.com/vrsolutionsaas-afk/getnetAgent/HEAD/README.md) ·
  [rrehlert](https://raw.githubusercontent.com/rrehlert/getnet-ai-engineer-challenge/HEAD/README.md) ·
  [CaioPereir4](https://raw.githubusercontent.com/CaioPereir4/multi-agent-support-system/HEAD/README.md) ·
  [Bepaiva](https://raw.githubusercontent.com/Bepaiva/bbspj-multi-agent-support/HEAD/README.md) ·
  [LeonardoColotino](https://raw.githubusercontent.com/LeonardoColotino/ai-hardcore-engineer/HEAD/README.md) ·
  [Fredyycloss](https://raw.githubusercontent.com/Fredyycloss/desafio-getnet-multi-agente/HEAD/README.md)
- Feedbacks: [DiogoOg16 V4](https://raw.githubusercontent.com/DiogoOg16/getnet/main/feedback_diogoog16_v4(1).md) ·
  [gabriel-dezani, auditoria do 9,2](https://raw.githubusercontent.com/gabriel-dezani/multi-agent-support/HEAD/docs/AUDITORIA_FEEDBACK_9_2_META_9_6.md) ·
  [gabriel-dezani, evolução 9,2 → 9,8](https://raw.githubusercontent.com/gabriel-dezani/multi-agent-support/HEAD/docs/EVOLUCAO_FEEDBACK_9_2_PARA_9_8.md)
