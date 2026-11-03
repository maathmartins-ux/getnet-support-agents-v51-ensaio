# ADR 0003 — SQLite como padrão; Postgres atrás da mesma interface para réplicas em vários hosts

Status: aceito no kit v5.1 (02/11/2026). Complementa o ADR 0002.

**Contexto.** O ADR 0002 deixou as réplicas no MESMO host: o SQLite em WAL é um arquivo e não é banco de rede. Com
réplicas em máquinas diferentes, cada uma veria um arquivo próprio e as garantias de "uma vez só" (um caso aberto
por conversa, resposta do operador, aprovação, claim de ação, retomada do plano, limite de uso) deixariam de valer
entre elas.

**Decisão.** `DATABASE_URL=postgresql://...` troca o backend do store por `app.store_pg.PgStore`, subclasse de
`Store` com a MESMA interface pública. Sem a variável, nada muda: SQLite em `DB_PATH`.

- SQL no subconjunto comum aos dois (placeholders `?`, upsert `ON CONFLICT ... DO UPDATE`); o que é de dialeto vira
  gancho da classe: `_begin` (SQLite: `BEGIN IMMEDIATE`), `_lock_key` (Postgres: `pg_advisory_xact_lock` só da
  chave do limite de uso), `_claim_overdue` (Postgres: `UPDATE ... WHERE id IN (SELECT ... FOR UPDATE SKIP
  LOCKED) RETURNING id`), `NO_LIMIT`, `IntegrityError`.
- Disputas: o UPDATE condicional (`WHERE status = 'pending'`, rowcount == 1) vale igual no Postgres em READ
  COMMITTED (a 2ª transação espera a 1ª e reavalia o WHERE). Varredura de fila usa `SKIP LOCKED`.
- Esquema: migrações versionadas (`schema_version`), aplicadas sob trava consultiva; réplicas que sobem juntas não
  aplicam a mesma versão duas vezes. Auditoria só de inclusão por gatilho (UPDATE, DELETE e TRUNCATE recusados).
- Limite de uso continua falhando fechado: banco fora do ar → exceção → 429.

**Prova.** Os testes de store, HITL, retomada, privacidade e concorrência (`BACKEND_MODULES` em
`tests/conftest.py`) rodam nos dois backends; a variante Postgres tem o marcador `postgres` e roda com
`TEST_DATABASE_URL` (job `postgres` do CI, serviço `postgres:16`). `tests/test_store_backends.py` cobre réplicas
(instâncias separadas sobre o mesmo banco) disputando caso, ação, resposta, SLA, plano pendente e limite de uso.
O perfil `postgres` do compose sobe duas réplicas da API num Postgres compartilhado (prontidão para vários hosts;
o compose em si continua num host).

**Por que SQLite continua o padrão.** O desafio é cronometrado e avaliado por quem clona e roda: zero serviço
externo, banco que nasce sozinho, testes em segundos. O Postgres entra quando há mais de um host, e a troca é uma
variável de ambiente, sem mudar código de domínio.

**Alternativas descartadas.** ORM (SQLAlchemy): mais uma camada para 25 consultas simples, e o comportamento de
disputa precisa ser visível no SQL. Postgres como padrão: serviço obrigatório no `docker compose up` e nos testes.
Redis para o limite de uso: terceiro serviço; a trava consultiva do Postgres resolve sem ele.

**Não provado.** Latência e vazão com Postgres (nenhuma medida feita); failover do Postgres; pool de conexões
compartilhado entre processos (cada processo guarda até 4 conexões ociosas).
