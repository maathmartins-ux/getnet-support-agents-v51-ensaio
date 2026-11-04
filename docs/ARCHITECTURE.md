# Arquitetura (Getnet)

Três desenhos, cada caixa com o arquivo real que a implementa. Só descreve o que o código faz; números vêm de
`evals/results/` via `scripts/fill_readme.py` (README §0), nunca deste texto.

## 1. Agentes: router, supervisor e especialistas sem estado

```mermaid
flowchart LR
  U["Lojista + Bearer token<br/>src/app/auth.py"] --> API["POST /chat · rate limit<br/>src/app/api.py"]
  API --> G["Guardrails: PII, injeção<br/>src/app/guardrails.py"]
  G --> MEM[("Histórico, resumo, fatos<br/>src/app/memory.py · src/app/store.py")]
  MEM --> R["Router: intenção, plano,<br/>pergunta reescrita (standalone)<br/>src/app/router.py"]
  R -->|"todo turno (ADR 0005)"| S{"Supervisor LLM: ALLOWED, MAX_STEPS,<br/>orçamento, replanejamento<br/>src/app/supervisor.py"}
  R -.->|"SUPERVISOR_FAST=on, desligado por padrão:<br/>1 passo, confiança alta"| F["Atalho de 1 passo<br/>supervisor.fast_path"]
  F -.->|"insufficient"| S
  subgraph W["Especialistas sem estado: src/app/agents.py"]
    A1["faq: busca no corpus"]
    A2["records: tools do domínio<br/>src/app/domain/challenge/tools.py"]
    A3["escalation: abre caso"]
  end
  S <--> W
  F -.-> W
  S --> V["Conferência de claims e números<br/>src/app/grounding.py · src/app/claims.py"]
  F -.-> V
  V --> OUT["Resposta + fontes + custo<br/>src/app/schemas.py"]
```

- O supervisor LLM decide em todo turno ([ADR 0005](adr/0005-supervisor-em-todo-turno.md)): lê o status de cada
  especialista e escolhe responder, chamar outro ou o humano. O atalho de 1 passo (linha pontilhada) só existe com
  `SUPERVISOR_FAST=on`, desligado por padrão (`config.supervisor_fast`); sem chave ou com falha do provedor, a mesma
  tabela de transições (`FALLBACK`, `ALLOWED`) roda offline.

- O router é o único que lê o histórico; os especialistas recebem a pergunta reescrita e o livro de fatos
  (`agents.llm_history`, [ADR 0007](adr/0007-especialistas-sem-estado.md)).
- Cada especialista devolve `AgentResult` com status `ok` / `partial` / `insufficient` / `error`
  (`src/app/schemas.py`); o supervisor lê o status e replaneja.
- Fluxo específico do domínio: `src/app/domain/challenge/flow.py`; tools com schema e dono verificado
  (`_merchant` só devolve o registro do próprio `user_id`): `src/app/domain/challenge/tools.py`.

## 2. RAG: ingestão → armazenamento → busca → redação

```mermaid
flowchart LR
  SRC["data/sources.json<br/>hosts permitidos"] --> ING["Ingestão: texto visível,<br/>trechos 300–800 chars, dedupe<br/>src/app/ingest.py"]
  ING --> J[("Trechos JSONL versionados<br/>data/ (id, URL, fetched_at, sha256)")]
  J --> IDX["Vetores densos em cache<br/>src/app/rag.py"]
  Q["Pergunta do lojista +<br/>pergunta reescrita do router"] --> RET["Denso e5, na ordem do denso;<br/>cross-encoder só dá a nota<br/>escolha em data/retriever.json<br/>src/app/rag.py"]
  IDX --> RET
  RET --> GATE{"Portão 'sem fonte'<br/>nota do cross-encoder (MIN_RERANK)<br/>agents.covered_hits"}
  GATE -->|"aceito"| GEN["faq redige só com os trechos<br/>src/app/agents.py<br/>src/app/domain/challenge_prompts/faq.md<br/>+ src/app/prompts/contract/faq.md"]
  GATE -->|"sem fonte"| INS["insufficient → supervisor"]
  GEN --> CHK["Cada frase contra a fonte<br/>src/app/grounding.py"]
```

- A busca é ação do especialista; o glossário expande a consulta (`agents.expand_query`).
- BM25 só entra quando a pergunta está no idioma do corpus (`rag.lexical_fits`); sem nota do cross-encoder, o portão
  volta ao limiar do BM25/cosseno (`agents.covered_hits`; a calibração é medida por idioma, `agents.gate_by_language`).
- Busca em uso: `dense+cross:base` (ordem do denso; a nota do cross-encoder só no portão), gravada em
  `data/retriever.json` por `python -m evals.run_evals --choose-retriever --fast --apply`, rodado fora do relógio do
  ensaio sobre o gold deste domínio; ela vale sobre o pacote do kit (`KIT_RETRIEVER` em `src/app/config.py`, medido
  antes do relógio, que reordena pela nota). Decisão e emenda do critério no
  [ADR 0004](adr/0004-buscador-denso-com-teto-de-ram.md); variantes rejeitadas no
  [ADR 0008](adr/0008-considerado-e-nao-feito.md).

## 3. HITL: humano só quando o sistema não resolve

```mermaid
flowchart TD
  S["Supervisor<br/>supervisor._enforce_escalation"] -->|"sem fonte/dado, pedido do lojista,<br/>orçamento esgotado, valor acima do limite"| E["escalation abre caso<br/>src/app/cases.py"]
  E --> N["Aviso ao operador: /operator ou Telegram<br/>src/app/notify.py"]
  N --> WAIT{"Espera no turno<br/>HITL_SYNC_WAIT_S<br/>src/app/hitl_sync.py"}
  WAIT -->|"respondeu no prazo"| EV["Resposta vira evidência (agente human);<br/>passos pendentes rodam no mesmo turno"]
  WAIT -->|"fora do prazo"| Q[("Caso com plano pendente<br/>src/app/store.py")]
  Q --> RES["Retomada do plano<br/>src/app/resume.py"]
  RISK["Ação de risco alto (estorno, cancelamento)<br/>src/app/risk.py"] --> FOUR["Quatro olhos: lojista confirma +<br/>operador aprova, executa uma vez<br/>src/app/actions.py"]
  Q --> SLA["Fila por especialidade, SLA, re-roteamento<br/>src/app/routing.py"]
```

- Resposta parcial só oferece o humano, sem abrir caso ([ADR 0006](adr/0006-humano-so-quando-nao-resolve.md)).
- Quem entrega a resposta do operador (turno ao vivo ou retomada) é decidido por carimbo gravado
  (`hitl_sync.live_owns`), sem corrida entre réplicas ([ADR 0002](adr/0002-replicas-mesmo-host.md)).
