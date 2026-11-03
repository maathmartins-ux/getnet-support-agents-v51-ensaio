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
  R -->|"1 passo, confiança alta"| F["Atalho de 1 passo<br/>supervisor.fast_path"]
  R -->|"2+ passos ou incerto"| S{"Supervisor: ALLOWED, MAX_STEPS,<br/>orçamento, replanejamento<br/>src/app/supervisor.py"}
  F -->|"insufficient"| S
  subgraph W["Especialistas sem estado: src/app/agents.py"]
    A1["faq: busca no corpus"]
    A2["records: tools do domínio<br/>src/app/domain/challenge/tools.py"]
    A3["escalation: abre caso"]
  end
  S <--> W
  F <--> W
  S --> V["Conferência de claims e números<br/>src/app/grounding.py · src/app/claims.py"]
  F --> V
  V --> OUT["Resposta + fontes + custo<br/>src/app/schemas.py"]
```

- O router é o único que lê o histórico; os especialistas recebem a pergunta reescrita e o livro de fatos
  (`agents.llm_history`, [ADR 0007](adr/0007-especialistas-sem-estado.md)).
- Cada especialista devolve `AgentResult` com status `ok` / `partial` / `insufficient` / `error`
  (`src/app/schemas.py`); o supervisor lê o status e replaneja.
- Fluxo específico do domínio: `src/app/domain/challenge/flow.py`; tools com schema e dono verificado
  (`_lookup` só devolve registro do próprio `user_id`): `src/app/domain/challenge/tools.py`.

## 2. RAG: ingestão → armazenamento → busca → redação

```mermaid
flowchart LR
  SRC["data/sources.json<br/>hosts permitidos"] --> ING["Ingestão: texto visível,<br/>trechos 300–800 chars, dedupe<br/>src/app/ingest.py"]
  ING --> J[("Trechos JSONL versionados<br/>data/ (id, URL, fetched_at, sha256)")]
  J --> IDX["Vetores densos em cache<br/>src/app/rag.py"]
  Q["Pergunta do lojista +<br/>pergunta reescrita do router"] --> RET["Denso + cross-encoder top-10<br/>KIT_RETRIEVER em src/app/config.py<br/>src/app/rag.py"]
  IDX --> RET
  RET --> GATE{"Portão 'sem fonte'<br/>limiar por idioma<br/>agents.covered_hits"}
  GATE -->|"aceito"| GEN["faq redige só com os trechos<br/>src/app/agents.py · src/app/prompts/faq.md"]
  GATE -->|"sem fonte"| INS["insufficient → supervisor"]
  GEN --> CHK["Cada frase contra a fonte<br/>src/app/grounding.py"]
```

- A busca é ação do especialista; o glossário expande a consulta (`agents.expand_query`).
- BM25 só entra quando a pergunta está no idioma do corpus (`rag.lexical_fits`); escolha do buscador feita antes do
  relógio ([ADR 0004](adr/0004-buscador-denso-com-teto-de-ram.md), [ADR 0008](adr/0008-considerado-e-nao-feito.md)).

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
