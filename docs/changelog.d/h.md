# Frente H — supervisão humana, identidade e produção (kit v5.1)

- **Comentários só com o porquê técnico.** O que: tirado o parágrafo de histórico do docstring de `resume.py` e a
  citação a outro candidato em `config.supervisor_replan`. Por quê: comentário explica o código, não a história da
  correção. Prova: `grep -rn "Feedback v\|nelsondell" src/` vazio.
- **Store em Postgres atrás da mesma interface.** O que: `DATABASE_URL=postgresql://...` troca o backend por
  `store_pg.PgStore` (psycopg 3, pool pequeno, migrações versionadas com trava consultiva, `FOR UPDATE SKIP LOCKED`
  no SLA, trava por chave no limite de uso, auditoria só de inclusão por gatilho); o SQL do store virou o
  subconjunto comum (upsert `ON CONFLICT`). Por quê: com SQLite as réplicas ficavam num host só (ADR 0002). Prova:
  os módulos de store/HITL/retomada/privacidade rodam nos dois backends (`BACKEND_MODULES`, marcador `postgres`);
  `tests/test_store_backends.py` (réplicas disputando caso, ação, resposta, SLA, plano e limite de uso); ADR 0003.
- **Compose: padrão seguro, demo explícito, perfil postgres.** O que: `docker-compose.yml` segue `AUTH_MODE=required`;
  `docker-compose.demo.yml` é o override que aceita o payload literal `{"message","user_id"}` (identity_verified=false);
  perfil `postgres` sobe `postgres:16` (por digest) + `api-pg` com 2 réplicas sem volume compartilhado + `lb-pg`. Por
  quê: o padrão não pode ser o modo sem identidade, e vários hosts só exigem rede até o banco. Prova:
  `tests/test_production_ops.py` (estrutura) e `docker compose ... config -q` dos três arranjos (rodado localmente).
- **Métricas com várias réplicas.** O que: Prometheus descobre cada réplica por DNS (`dns_sd_configs` em `api` e
  `api-pg`, rótulo `service`); alertas e painéis somam com `sum(...)`; painel novo por réplica. Por quê: raspar o
  nome do serviço pega uma réplica diferente a cada coleta. Prova: `test_production_ops` (todo serviço da API está
  na descoberta; nenhum rate/increase fora de sum).
- **CI com Postgres.** O que: job `postgres` com serviço `postgres:16@sha256:...`, roda `-m postgres` e reprova se
  alguma variante for pulada. Prova: `test_ci_runs_the_postgres_variants_against_a_pinned_postgres_service`; o job em
  si só roda no GitHub (não executado aqui).
- **Livro de fatos (frente M) no Postgres.** O que: migração 2 cria `conversation_facts`; `test_memory_ledger` entrou
  nos módulos que rodam nos dois backends (inclui o apagamento LGPD dos fatos). Prova:
  `test_postgres_upgrades_an_older_schema_in_place` (banco na versão 1 com dados sobe para a 2 sem perder nada).
- **Resposta humana vira evidência e o plano continua, também no escalonamento simples.** O que: a retomada entrega
  ao supervisor um `AgentResult("human")` (texto/evidência = resposta do operador, fatos `operator_answer` e dica de
  busca) como `prior`, que abre a rota (`["human", ...]`); quando um passo falha e vai ao humano, quem DEPENDE dele
  (DEPENDS do domínio) sai da fila e espera a resposta (`_defer_dependents`); a retomada não reescala
  (`no_escalation`); o fallback LLM→tabela preserva os fatos de entrada (antes zerava tudo, inclusive a resposta
  humana). Por quê: antes a resposta só virava a próxima mensagem quando não havia orçamento estourado, e o passo
  dependente rodava sem o fato que faltou. Prova: `tests/test_resume_human_evidence.py` (5 testes, TestClient, nos
  dois backends): defer → resposta → faq roda com a evidência → uma retomada só; passo que ainda falha não reabre caso;
  supervisor LLM vê a resposta e o fallback a mantém.
- **Rotação de chaves do JWT (kid + JWKS).** O que: `app/keys.py` — conjunto `AUTH_KEYS` (HS256, EdDSA/Ed25519,
  RS256 ≥ 2048 bits via cryptography), `AUTH_ACTIVE_KID` assina, as outras só validam; `kid` no cabeçalho; o `alg`
  aceito é o da chave do `kid` (bloqueia `none` e HS256 assinado com a pública); `GET /.well-known/jwks.json` publica
  só as públicas; `/health` mostra o kid ativo; config inválida não sobe a API e, em request, falha fechado;
  `python -m app.auth keygen`. Sem `AUTH_KEYS`, vale a chave `default` HS256 do AUTH_SECRET. Chave de operador não
  mudou. Por quê: segredo único sem rotação e sem forma de validar sem poder emitir. Prova:
  `tests/test_key_rotation.py` (token do kid antigo válido até a chave sair, depois 401, em EdDSA/RS256/HS256; PyJWT
  valida só com o JWKS; confusão de algoritmo recusada).
- **Limite de valor por ação.** O que: `app/risk.py` + `RISK_POLICY` do domínio (`amount` = argumento ou função,
  `four_eyes_above`, `block_above` opcional; `RISK_LIMITS` no ambiente): até o limite só o dono confirma, acima vai a
  quatro olhos, acima do teto nada é proposto, valor desconhecido vai a quatro olhos; a regra entra na descrição da
  ferramenta (`tool_specs`, lida pelo modelo e pelo MCP) e no cartão de capacidades (`capabilities.card`). Por quê: `risk: high` fixo mandava toda ação ao operador,
  qualquer valor. Prova: `tests/test_risk_policy.py` (8 testes, nos dois backends, com confirm/approve pela API).
- **Roteamento de casos por especialidade.** O que: `app/routing.py` — caso nasce com a especialidade do agente que
  falhou (ou da intenção; `SPECIALTY_BY_AGENT`/`SPECIALTY_BY_INTENT` do domínio), aprovação vai para `approval`;
  operador tem especialidades (`OPERATOR_SKILLS` + tabela `operator_skills`, `PUT /operators/{nome}/skills`
  auditado); `GET /handoffs` ordena a fila do operador (dele e re-roteados primeiro, campo `lane`); SLA vencido grava
  `routed_to = any` e "ticket_rerouted"; criação grava "ticket_routed" na mesma transação. Por quê: fila única sem
  especialidade. Prova: `tests/test_operator_routing.py` (5 testes, nos dois backends).
- **Teste intermitente do supervisor (isolamento).** O que: o conftest zera os contextvars de orçamento do turno a
  cada teste. Por quê: `new_trace_id()` chamado na thread principal por um teste deixava o contador vivo e um teste
  de supervisor posterior estourava `MAX_MODEL_CALLS` conforme a ordem do xdist. Prova: mesma sequência serial
  (otel, parallel, agents, supervisor, needs_budget) 3 falhas antes → 48 passed depois.
- **Réplicas sobre o mesmo Postgres, de verdade (sem Docker).** O que: `scripts/pg_replicas_smoke.py` sobe 2
  processos uvicorn (portas diferentes, nenhum arquivo comum) num esquema próprio do Postgres e prova pelo HTTP:
  continuidade alternando réplicas, 8 escalonamentos simultâneos → 1 caso, resposta na outra réplica com retomada (2ª
  resposta 404), SLA simultâneo nas duas → cada caso sobe uma vez, limite de uso somado (10/min → 10x200 e 4x429 em 14),
  latência offline. Roda no job `postgres` do CI. Medido aqui (Postgres 16 local, máquina com load average ~9 de
  outras sessões): 6/6 provas ok; /chat offline sem LLM, 1 cliente sequencial, n=100: p50 38,3 ms, p95 67,1 ms. Não é
  latência com LLM nem com rede entre hosts.
