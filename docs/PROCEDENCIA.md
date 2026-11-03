# Procedência: o que veio do kit e o que foi feito no relógio

Este documento existe para que a comparação com quem entregou uma vez só seja justa. Ele diz o que já estava
pronto antes do relógio, de onde veio e o que os 58 minutos medem.

## 1. O kit e a sua história

O primeiro commit (`chore: scaffold from entregar-desafio-cronometrado kit v5.4.0`) traz um kit próprio, mantido
entre as tentativas deste mesmo desafio. **O kit evoluiu a partir das correções das entregas anteriores.** Cada
versão absorveu os gaps apontados na correção da tentativa anterior:

| Tentativa | Kit usado | Nota recebida | O que a versão seguinte do kit absorveu |
|---|---|---:|---|
| v1 | sem kit | 7,1 | — |
| v2 | v2.0.0 | 8,2 | token sem expiração, operador com token compartilhado, HITL sem retomada (→ v3.7.0) |
| v4 | v3.7.0 | 8,5 | groundedness 60%, busca fraca, memória 54%, humano sem continuar o plano, avaliação de um rotulador só (→ v5.4.0) |
| v5 | v5.1.0 | não enviada (ensaio cronometrado, medido pelo próprio autor) | 2 cenários oficiais sem resposta, escaladas a mais, intenção do held-out 67,5%, memória 0,72, juiz cortado (→ v5.4.0) |
| **v5.1 (esta)** | **v5.4.0** | — | — |

O registro completo do que mudou em cada versão, com a causa medida, está em
[KIT_CHANGELOG.md](KIT_CHANGELOG.md), copiado do kit sem edição.

**Ideias de soluções públicas.** Algumas ideias do kit vieram da leitura de soluções públicas deste desafio (lista em
[KIT_CHANGELOG.md](KIT_CHANGELOG.md), seção de referências): replanejamento medido com e sem, retomada do plano após o
humano, juiz com canários. Na versão v5.4.0, do desenho de duas entregas públicas:

- **farrulla-darze/skywalker:** o router como único leitor do histórico, com especialistas sem estado que recebem a
  pergunta reescrita; busca como ação do especialista, com uma busca por item comparado; corpus com a página de cada
  produto citado nos cenários; humano consultado de dentro do turno, com espera curta; resultado de escrita com antes
  e depois; login com senha; versão das instruções e 👍/👎 ligados a cada resposta; README que explica o porquê de
  cada mecanismo e lista os limites com o custo de corrigir.
- **nelsondell/multi-agent-support-system:** resposta em três estados (completa, parcial, sem fonte); regra de
  demonstrativos na reescrita ("essa venda" = a entidade da última resposta); placar de busca no caminho do agente
  (Recall@5, rank do 1º gold, recorte por origem, separação com × sem fonte); regra de validação do juiz fixada antes
  de medir; "desde a última avaliação" no topo do README, sem meta própria.

Nenhum código nem texto foi copiado (os repositórios não têm licença); o kit tem a sua própria implementação e os
seus próprios testes, e o motivo técnico de cada escolha está no código; a origem da ideia fica só aqui.

### O que a correção da v4 pediu e onde o kit já trazia a resposta antes do relógio

Para quem quiser descontar da nota o que veio pronto: cada item do "Caminho para 9,5" da correção da v4, a mudança
correspondente no kit e se ela foi feita **antes** do relógio (kit) ou **no** relógio (este repositório).

| Item da correção da v4 | Mudança | Onde | Quando |
|---|---|---|---|
| 1. respostas oficiais sem fundamento (juiz 60%) | juiz recebe o texto que o redator viu; cartão de capacidades; checagem por frase; dado ao vivo de API oficial | `evals/context.py`, `src/app/capabilities.py`, `src/app/claims.py`, `src/app/live_data.py` | kit |
| 1. idem, a correção caso a caso das respostas DESTE enunciado | reprovações do juiz lidas uma a uma e corrigidas na causa | commits `fix:` e a diferença do juiz entre as rodadas (judge_diff) | relógio |
| 2. busca fraca (Recall@3 0,49) | denso + rerank local, tabelas inteiras, dedupe, escolha por medida | `src/app/rag.py`, `src/app/ingest.py` | kit |
| 2. idem, corpus, glossário e gold DESTE enunciado | páginas, glossário, gold por passagem essencial | `data/`, `evals/retrieval.d/` | relógio |
| 3. memória (pass@1 54%) | livro de fatos, números do histórico, seguimento elíptico | `src/app/memory.py`, `src/app/followup.py` | kit |
| 4. humano não continuava o plano; um operador por caso; segredo único; SQLite num host | retomada do plano com a resposta humana como evidência; especialidade; JWKS com rotação; Postgres | `src/app/resume.py`, `src/app/routing.py`, `src/app/keys.py`, `src/app/store_pg.py` | kit |
| 5. avaliação de um rotulador só; held-out de 24; casos feitos para exigir replanejamento | 2+ rotuladores com kappa entre humanos; held-out de 2 autores cegos; perguntas reais com link | `evals/label.py`, `evals/heldout_blind.jsonl`, `evals/real_questions.jsonl` | ferramentas: kit · casos e rótulos: relógio |
| Julgamento: mensagem sem os números ruins; narrativa dos minutos | placar com metas e status; mensagem gerada com bons e ruins; este documento | `scripts/scorecard.py`, `scripts/delivery_message.py` | kit |

**Ensaio antes do relógio.** O motor do kit foi ensaiado ao vivo sobre o repositório entregue da v4 (mesmo desafio),
para medir as correções antes de usá-las; o resultado está no histórico do kit (`KIT_CHANGELOG.md`). Os números
deste repositório vêm só das medidas feitas aqui, no relógio, sobre o corpus e os casos deste enunciado.

## 2. O que os 58 minutos medem, e o que não medem

- **Medem:** a especialização do kit para este enunciado, no relógio: spec, base de conhecimento, ferramentas do
  domínio, casos de avaliação (incluindo o held-out cego e as perguntas reais), prompts, regras do router e do
  supervisor, as medições ao vivo, as correções feitas a partir delas e esta documentação.
- **Não medem:** o esforço de engenharia do motor genérico (orquestração, avaliação, identidade, HITL, operação), que
  foi feito antes e ao longo das tentativas anteriores, com conhecimento das correções.
- **Para comparar pela primeira entrega**, a referência é a v1 (7,1).

## 3. A medida, tirada do git

Linhas do kit no commit de scaffold × linhas escritas no relógio, por pasta (gerado por `scripts/fill_readme.py`;
arquivos gerados, como `evals/results/`, ficam fora da conta):

<!-- kit:begin -->
| pasta | linhas do kit | + no relógio | − no relógio | arquivos do kit alterados |
|---|---:|---:|---:|---:|
| `.claude` | 121 | 0 | 0 | 0 |
| `.dockerignore` | 15 | 0 | 0 | 0 |
| `.env.example` | 42 | 16 | 7 | 1 |
| `.github` | 155 | 17 | 3 | 1 |
| `.gitignore` | 7 | 0 | 0 | 0 |
| `.gitleaks.toml` | 14 | 4 | 1 | 1 |
| `.trivyignore` | 8 | 0 | 0 | 0 |
| `Dockerfile` | 72 | 7 | 5 | 1 |
| `Makefile` | 38 | 2 | 2 | 1 |
| `OWNERSHIP.json` | 89 | 0 | 0 | 0 |
| `README.md` | 319 | 191 | 69 | 1 |
| `data` | 34 | 46 | 32 | 4 |
| `data/crm` | 0 | 30 | 0 | 0 |
| `data/intent_examples.d` | 0 | 28 | 0 | 0 |
| `data/knowledge` | 0 | 178 | 0 | 0 |
| `docker-compose.demo.yml` | 10 | 0 | 0 | 0 |
| `docker-compose.hardened.yml` | 37 | 0 | 0 | 0 |
| `docker-compose.scale.yml` | 28 | 0 | 0 | 0 |
| `docker-compose.yml` | 91 | 3 | 0 | 1 |
| `docs` | 429 | 1170 | 28 | 5 |
| `docs/adr` | 255 | 50 | 34 | 2 |
| `docs/changelog.d` | 806 | 0 | 0 | 0 |
| `docs/video` | 0 | 174 | 0 | 0 |
| `evals` | 4993 | 909 | 154 | 16 |
| `evals/cases.d` | 0 | 66 | 0 | 0 |
| `evals/cassettes` | 0 | 1465 | 0 | 0 |
| `evals/essential` | 0 | 2357 | 0 | 0 |
| `evals/judge_calibration.d` | 0 | 48 | 0 | 0 |
| `evals/proxy` | 286 | 0 | 0 | 0 |
| `evals/retrieval.d` | 0 | 81 | 0 | 0 |
| `ops` | 669 | 2 | 1 | 1 |
| `pyproject.toml` | 51 | 0 | 0 | 0 |
| `reports` | 0 | 16 | 0 | 0 |
| `requirements-dev.lock` | 252 | 0 | 0 | 0 |
| `requirements-hybrid.lock` | 282 | 0 | 0 | 0 |
| `requirements.lock` | 149 | 0 | 0 | 0 |
| `scripts` | 4505 | 361 | 336 | 25 |
| `src/app` | 10844 | 1109 | 46 | 23 |
| `tests` | 12008 | 1063 | 217 | 91 |
| `tests/fixtures` | 70 | 0 | 0 | 0 |

Total: **36679** linhas do kit (commit `16ecd02`) e **9393** escritas no relógio (20% do total). Arquivos do kit alterados no relógio: 174. Fora da conta, por serem gerados: 222241 linhas em `evals/results/`.
<!-- kit:end -->

Linha do tempo commit a commit, com as tags `clock-start` e `clock-end`: [TIMESHEET.md](TIMESHEET.md).
