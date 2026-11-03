# Kit — mudanças

## v5.5 (03/11/2026, branch kit-v5.4.0) — perfil Skywalker (o bench que tirou 10)

Estudo do 10 (`docs/kit/estudo/skywalker.md` §3): a nota veio da forma agentic visível, de nenhuma medida própria
mostrando resposta ruim nos cenários e de um README que explica cada mecanismo; não de CI, testes ou números.
- **Supervisor LLM decide todo turno** (`SUPERVISOR_FAST` desligado por padrão): o DEMO mostrava "atalho" nos
  oficiais, e "regra decidindo" foi o que o avaliador puniu. Custo: ~2 chamadas e ~4 s a mais por turno de 1 passo.
- **Manchete do README sem meta própria** (`scorecard.headline_markdown`): só oficiais resolvidas, pass^k, juiz
  (fundamentadas, úteis), memória e busca, com o valor e como se mede. Diagnósticos do kit ficam em `docs/RESULTS.md`.
- **Entrega** lista só as medidas do enunciado (as ruins entre elas continuam listadas).
- **README**: mapeamento "requisito do enunciado → implementação → onde" com os 4 bônus, teste em 3 minutos,
  avaliação descrita como capacidade (gabarito, camadas, o que é "resolvida") e limitações com efeito e o que faltaria.

## v5.4 (03/11/2026, branch kit-v5.4.0) — metodologia Skywalker (10) e nelsondell (9,5) em busca e memória

- **Busca:** placar pelo caminho do agente (rerank incluso) com Recall@5, MRR@10, rank do 1º gold e origem; buscador
  base ao lado. Gold da V5: 0,842/0,737 publicados → 0,895 / Recall@5 0,947 / MRR 0,829. Híbrido com BM25 só no
  idioma do corpus (`rag.lexical_fits`); palavras do cliente como 1ª busca também offline. Padrão dense+cross por medida.
- **Memória:** especialistas sem estado (pergunta reescrita pelo router + livro de fatos; `SPECIALIST_HISTORY=on`
  volta ao antigo); regra de demonstrativos no router. Ao vivo parcial (n=48): rota 96%, tools 94%.
- **Docs:** gold com `origin`; casos de memória com os seguimentos da V5; prompt e PLAYBOOK apontam o v5.4.0.
- Ensaio: ENSAIO_V54.md (a conta da API atingiu o limite no meio da bateria). Estimativa 9,54 central,
  9,32 no pior caso.
- **Evidência = produto (confirmação de 03/11):** o passo 1 instalava só `[dev]` (sem fastembed): a tentativa mediu tudo no BM25 do fallback e o CI, no denso + cross, reprovou "resultado commitado = código atual" (oficiais 33% × 83%). Instalação agora igual à do CI (`requirements-dev.lock` + `requirements-hybrid.lock`); `check.py` reprova buscador em fallback e o `live_eval.sh` recusa rodar nele. Router: pergunta sobre a própria empresa nunca fica em intenção sem escalada (`OWN_COMPANY`); cota do live pelo custo medido por caso.
- **Ensaio pré-produção de 03/11 (correções):** CI vermelha por 3 defeitos do kit, agora corrigidos e testados — gitleaks acusava 1492 falsos positivos nas gravações (`evals/cassettes/` fora da varredura; teste próprio procura credencial real nelas), 6 testes exigiam fastembed no job offline (`importorskip`), `COPY var/embeddin[g]s` quebrava sem a pasta (bind do contexto). Gate de red team só ao vivo/replay (offline é a regex: 77,5% reprovava a CI). Placar: "juiz × gabarito de calibração" (dizia "humano" para rótulos de agente). `live_eval.sh` recusa com < 6 GB de RAM livre (OOM com 4 processos pesados) e ignora a guarda de disco no --dry-run; PLAYBOOK/prompt: 2º plano rastreado, nada pesado junto da rodada.
- **Imagem = produto medido (ensaio v5.4):** o padrão do kit virou denso + cross, mas a imagem padrão seguia sem fastembed e o CI instalava só o lock de dev: no container a busca caía no BM25 e o eval via HTTP resolvia 3 de 10 oficiais (9 de 10 em processo); no CI o gate mediria outro produto. Agora `EXTRAS=auto` no Dockerfile segue a escolha (`fetch_models.py --extras`), os vetores do corpus vão prontos na imagem (`EMBED_CACHE_DIR=/opt/vectors`; sem eles o 1º pedido vetorizava o corpus, 2–4 min), o check reprova `/health` com fallback, o job `check` do CI instala o lock híbrido com modelos e vetores em cache, e o eval via HTTP do container roda os 10 oficiais (271 casos = 373 s em série). `check.py --warm-image` aquece a imagem no T+12.
- **Tempo (revisão 2):** a medida da busca fica em `var/retrieval_cache.json` pela chave do que muda o número (gold, índice, glossário, buscador, código da busca; `RETRIEVAL_CACHE=off` mede sempre): 91 s → 0 s nas chamadas repetidas. Eval aquecido em 2º plano no T+12; `make eval` sem o `--compare-retrievers` (504 s, agora `make compare`); `fork_check` das frentes fora da K sem e5-large nem medida de busca; pré-voo e `live_eval.sh` param com < 5 GB livres.
- **Do Skywalker (o que era melhor que o kit):** operador consultado DENTRO do turno com espera curta
  (`HITL_SYNC_WAIT_S`, 0 nos testes, até 20 s na demo, teto abaixo do timeout do balanceador) e o plano continua no mesmo turno; escrita com antes/depois;
  DEMO com árvore de passos e transcrição multi-turno; `POST /auth/login` e `/auth/logout` (scrypt, limite com
  Retry-After) no quickstart; versão das instruções em cada resposta (`prompt_versions`); 👎 vira candidato a caso
  com revisão humana (`python -m evals.candidates`); motor sem comentários de bastidor (origem das ideias só em
  `docs/PROCEDENCIA.md`). Mantido o nosso onde é melhor: identidade (JWKS, revogação, PII), produção (imagem
  não-root, CI, réplicas), avaliação (bateria integral, juiz com canários) e governança do humano (fila, 4 olhos, SLA).
- **Do nelsondell:** "desde a última avaliação" no topo do README e referência da avaliação no lugar de meta própria
  (sem ícone de falha); separação com × sem fonte (AUC, gap) no placar de busca; regra de validação do juiz fixada
  antes de medir. ≥ 15 perguntas sem fonte no gold (PLAYBOOK).
- `check.py --docker --scale` verde num clone limpo (imagem, contêiner sem rede, MCP, 2 réplicas com queda); 930 testes.

## v5.3 (03/11/2026, branch kit-v5.3.0) — pós-morte da V5 + estudo Skywalker (10) e nelsondell (9,5)

Medido ao vivo na bateria integral (11 splits, official e memory repeat 3) sobre o domínio da V5, com o motor do
kit por cima (ENSAIO_V53.md). V5 → kit v5.3:

| O que pesava na V5 | O que mudou | V5 → v5.3 |
|---|---|---|
| 2 oficiais sem resposta (escalada) | busca agentic (consultas do router no idioma da base + as palavras do cliente sempre como 1ª busca), três estados de resposta, contrato do motor no fim do prompt do domínio | oficiais resolvidas 80% → 96,7%; pass^3 0,60 → 0,90 |
| 40 de 49 falhas de handoff por excesso | humano só com motivo real: resposta parcial ou com outro especialista já respondendo vira OFERTA; não resolver nada continua indo ao humano (enunciado), e o código garante | replan 90%, heldout 96%, memory 96% de handoff certo |
| juiz útil 0,73 | contrato do motor (resposta indireta conta), cartão com veredito humano e formato dos ids, dia do calendário sem tarja | juiz 352 respostas: fundamentadas 95,5%, úteis 96,9% |
| intenção do held-out 67,5% | router reescreve o seguimento (standalone) e classifica a pergunta completa | 99% |
| memória pass@1 0,72 | rota medida pelo resultado (especialistas certos); records usa o livro de fatos no seguimento | 87,5% pelo resultado (84,4% pelo rótulo); fatos 95,8% |
| kappa entre humanos 0,054 | questionário com treino, perguntas sim/não concretas, consenso e AC1 de Gwet | medir na V5.1 |
| splits abortados por teto; juiz cortado | aviso de teto antes de gastar; saldo único do juiz; juiz em 8 linhas paralelas; recusa do juiz anotada | 11/11 splits completos; juiz 41 → ~2 min |
| tempo no limite | 12 conversas simultâneas (44 estouravam o timeout), 8 workers por split, cronograma com folga de 5 min | bateria integral com o juiz 16 → 12,8 min |

Estimativa por critério no ENSAIO_V53.md: central 9,51, pior caso 9,29 — pela regra do dono, ainda
não basta para a V5.1 (RAG, memória e concordância humana puxam o pior caso).

## v5.2 (02/11/2026, branch kit-v5.1.0) — medido no ensaio sobre o domínio da v4

- **Busca:** ingest sem corte por seção e sem contexto no índice por padrão (Recall@3 essencial 0,747 → 0,82 no
  mesmo corpus); gold por FATO rotulado às cegas por 2 rotuladores (`evals/essential_gold.py`; cópias do mesmo
  fato contam uma vez): Recall@3 0,93, MRR 0,94, Jaccard 0,89 entre rotuladores.
- **Juiz:** limite da API no meio grava o parcial e `--resume` continua (o limite acabou no 99º julgamento).
- **Avaliação humana:** página do claude.ai para 2+ pessoas, feita para leigos (uma situação por vez, conversa em
  balões, dados em tabela, 3 perguntas de sim/não, resultado calculado, tradução); `evals.label --import-page`.
- **Latência (frente L):** atalho do supervisor no plano de 1 passo; p50 oficiais 10,6 → 7,2 s, memória 22,6 →
  14,0 s; custo da rodada 2,00 → 1,55 US$.
- **RAM/velocidade (frente R2):** eval ao vivo num processo; pico 7,7 → 4,8 GB; `--choose-retriever --fast`.
- **Pré-voo:** seção "achados" do domínio de exemplo sem destino quebrava o T+0 (teste novo).
- Ensaio v5.2 ao vivo: oficiais 100% fundamentadas e úteis, pass^3 0,90; memória pass@1 0,90, 97,4% fundamentada
  (ENSAIO_V51.md, seção v5.2).

## v5.1.0 (02/11/2026) — correção formal da Getnet v4 (8,5)

A correção da v4 disse onde estava a nota: qualidade das respostas, busca, memória, humano continuando o plano,
avaliação independente e honestidade na entrega. O v5.1 ataca cada item e foi **ensaiado ao vivo sobre o repositório
entregue da v4** antes de ser declarado (ENSAIO_V51.md). Detalhe por frente em
changelog.d/. Testes: 487 → 656 passando.

| Item da correção | O que mudou | Medida (ensaio no domínio da v4) |
|---|---|---|
| juiz 60% nos oficiais | o juiz lê o texto que o redator viu (`context`); cartão de capacidades como fonte; checagem por frase (`CLAIMS_POLICY`); oferta de ação sem ferramenta sai; seguimento de câmbio/clima pela API oficial; link da fonte na evidência; soma por data em código | 60% → 96,7% fundamentadas; pass^3 0,70 → 0,90; números 80% → 100% |
| busca (Recall@3 0,49, MRR 0,61) | tabelas inteiras; denso multilíngue + rerank local; dedupe; `--choose-retriever`; BM25 confere antes de "sem fonte"; calibração do portão sobre o BM25 | MRR 0,61 → 0,92; Recall@3 0,49 → 0,70 (meta 0,85 não atingida) |
| memória (pass@1 54%) | livro de fatos da conversa; números do histórico do cliente como base; seguimento elíptico herda a intenção; memória medida separada do roteamento | pass@1 0,54 → 0,92; números 64% → 100% |
| humano não continuava o plano | resposta do operador vira evidência do supervisor; operador por especialidade; limite de valor por ação; JWKS com rotação; Postgres com 2 réplicas; métricas somadas entre réplicas | testes (687 com Postgres local); CI com job Postgres |
| avaliação de um rotulador só | `--rater` com kappa humano × humano; held-out com 2 autores cegos (≥ 80); split `real` com link público; juiz com `failure_type` e TPR/TNR por tipo; `judge_diff` antes × depois | ferramentas; os rótulos são do relógio |
| entrega sem os números ruins; narrativa dos minutos | placar com meta e status no topo do README; mensagem de entrega gerada com bons e ruins; `docs/PROCEDENCIA.md` | — |
| achados do próprio ensaio | modelo de 2 GB recarregado (eval morria com 14 GB); 1º caso frio estourava o tempo; portão do denso recusava pergunta com fonte | pico 7,7 GB; handoff offline 84,0% → 90,8% |

Limites que continuam: Recall@3 abaixo de 0,85; p95 da memória 52,8 s (frente L em andamento); denso pesado em memória.

## v5.0.0 (01/11/2026) — lições da Getnet v4 e de 28 soluções públicas

Getnet v4: 34 min do 1º ao último commit, CI verde; nota honesta estimada 8,4 (faixa 7,5–8,8). O v5 ataca o que
segurava a nota, na ordem do peso na Régua V4. Detalhe: LICOES_V4.md e pesquisa/.
Testes do kit: 336 → 487 passando (e 459 → 487 só nesta segunda rodada de trabalho).

| Causa na v4 (ou na pesquisa) | O que mudou | Onde |
|---|---|---|
| ingest descartava a tabela de preços; o AC-01 (Get Clássica × Get Smart) ficava sem fonte | células curtas viram linha de tabela; linha longa repetida fica 1 vez | `src/app/ingest.py` |
| número sem base chegava ao lojista (`numbers_acc` 64–80% ao vivo) | a checagem BLOQUEIA: 1 reescrita, depois `[valor não confirmado]` (`NUMBERS_POLICY=flag\|redact\|escalate`); soma, diferença e contagem da evidência passam; "R$ 80mil" é número | `src/app/grounding.py`, `pipeline.py` |
| clima e câmbio pela busca web (corpo cifrado, número sem base) | PTAX do Banco Central e Open-Meteo chamados no código, com data e fonte; falha cai na busca web (`LIVE_DATA=on\|off`). O teste achou 2 defeitos reais (a checagem apagava `[60]` como citação) | `src/app/live_data.py` |
| ação "alegada" sem execução, promessa de data | detector de "reiniciei/abri o chamado/estornei" sem tool no turno; regras financeiras duras no prompt | `grounding.py`, `prompts/` |
| resposta em pt para pergunta em en (Router LLM) | `clear_language`: vantagem ≥ 2 palavras manda; diretiva de idioma no pedido de cada agente | `router.py`, `agents.py` |
| replanejamento só reagia a falha; ablação "93% × 0%" era zero por construção | `needs` do agente insere o passo; `--ablate-replan --mode no_needs` mede o ganho por conclusão (`completed_acc`) | `supervisor.py`, `evals/run_evals.py` |
| sem teto por turno | `MAX_MODEL_CALLS`, `MAX_TURN_USD`, `NODE_TIMEOUT_S`; estourou → parte respondida + humano (`budget_exhausted`) | `supervisor.py` |
| operador respondia, mas o plano não continuava | a resposta do operador retoma os passos restantes; com o caso aberto, tools de escrita não rodam | `resume.py`, `cases.py` |
| RAG: gold por id quebra a cada re-ingest; recall só por trecho | `relevant_urls`/`relevant_text` (regex) e Recall@k/MRR também por página; contexto de seção no índice; máx. 2 trechos por URL | `rag.py`, `ingest.py` |
| eval ao vivo não protegia o código na CI | cassete: gravação do ao vivo e `LLM_PROVIDER=replay` com pisos = taxas da gravação aceita | `llm.py`, `run_evals.py` |
| juiz Claude julgando Claude, sem canário | 4 canários com defeito conhecido (`judge_unreliable`); juiz de outra família por `JUDGE_PROVIDER=openai_compat` | `evals/judge.py` |
| factual sem validação humana (lacuna do 9,5) | `python -m evals.label`: o dono rotula às cegas, relatório humano × automático (kappa) no README | `evals/label.py` |
| ninguém lia os traces antes de medir | `python -m evals.failure_modes` → `docs/FAILURE_MODES.md` (v4: 39 falhas em 4 modos) | `evals/failure_modes.py` |
| o avaliador não roda nada nem assiste ao vídeo | `docs/DEMO.md` com as respostas reais, `docs/TIMESHEET.md` do git log (tags `clock-start`/`clock-end`), `reports/verify.md` pelo `check.py` | `scripts/demo_md.py`, `timesheet.py`, `check.py` |
| README misturado com resultados deixou a CI vermelha 2 vezes | `make final`: README sozinho no último commit, recusa outra mudança pendente | `scripts/final.sh` |
| eval ao vivo em fila: splits sem verba, juiz sem nada | splits em paralelo, 80% do teto em cotas, 20% para o juiz (teto padrão US$ 10; custo medido ~6) | `scripts/live_eval.sh` |
| `live_eval.sh` sem bit de execução; venv apontando para outro repo; `MIN_SCORE` à mão | teste do bit no git; `check.py` recusa venv de outro repo; `--calibrate-gate --apply` grava o limiar | `tests/test_scripts_exec.py`, `check.py`, `run_evals.py` |
| vídeo manual | `make video`: respostas reais + slides do JSON + Playwright + ffmpeg (~5 min) | `scripts/video/` |
| LGPD e produção | volume nomeado, `DELETE /me/conversations/{id}`, retenção por `MEMORY_RETENTION_DAYS`, `/ready` separado de `/health`, trilha de auditoria só de inclusão | `api.py`, `store.py` |
| CI sem cadeia de suprimento | testes com a rede cortada, SBOM, trivy (CRITICAL falha; `.trivyignore` com motivo e validade), actions por SHA, imagem com `--network none`, overlay endurecido | `.github/workflows/ci.yml`, `docker-compose.hardened.yml` |
| guardrail só com regex e recusa seca | lavagem/sonegação (recusa, com verbo de intenção para não pegar "o que é lavagem de dinheiro?") e autoagressão (resposta de apoio com CVV 188 e SAMU 192, sem LLM); a camada LLM ganhou as 2 categorias | `guardrails.py`, `pipeline.py`, `prompts/guardrail.md` |

| seguimento curto não achava o assunto da pergunta anterior | `search_query`: herda o assunto da última fala do cliente como dica de busca (sem histórico, nada muda) | `router.py`, `pipeline.py` |
| resposta em pt para pergunta em en (regressão do próprio v5, achada no ensaio) | diretiva de idioma no fim de TODO pedido de agente + 1 reescrita se a saída vem no idioma errado | `agents.py`, `pipeline.py` |
| caso aberto marcava `handoff.required` em todo turno (regressão do v5) | `required=False` (só aviso e `ticket_id`) | `supervisor.py` |
| caso de suporte fechava por cortesia | estado do caso só fecha com prova (`customer_confirmed` / `tool_verified`), lembra os passos tentados, 2 ciclos sem sucesso → humano com as tentativas | `casestate.py` |
| mapa de ameaças genérico | OWASP Agentic ASI01–10 → controle → arquivo → teste; um teste reprova citação inexistente (pegou 1) | `docs/SECURITY_ASI.md` |
| só `/operator` e sem painel | `/ui` do lojista (testada num navegador real) e Grafana com 12 painéis provisionados (perfil `observability`), com teste que reprova painel de métrica que o código não emite | `static/ui.html`, `ops/grafana/` |
| rodada com LLM fora do ar parecia medida; aborto sobrescrevia resultado completo | `degraded` e `aborted_quota`, arquivo à parte, saída 3; o limite de gasto da API vira erro `quota` | `run_evals.py`, `llm.py`, `live_eval.sh` |

**Medido num ensaio** (ENSAIO_V5.md): o motor v5 sobre o domínio da v4, LLM real, 3 rodadas.
`official` ao vivo: pass^3 0,70 → 1,00, números 80% → 100%. `memory` ao vivo: números 64% → 92%, pass@1 0,54 → 0,79.
O ensaio achou 3 regressões do próprio v5 (handoff do caso aberto, idioma, rodada degradada), todas corrigidas.

**Não entrou / não foi provado (declarado, não escondido):**
- o estado do caso **não foi medido ao vivo** (o limite de gasto da API foi atingido durante o ensaio; só testes e offline);
- as imagens do Prometheus e do Grafana não foram baixadas nem executadas (o compose valida; os painéis são
  conferidos contra as métricas que o código emite, não contra um Grafana rodando);
- o juiz de outra família (`JUDGE_PROVIDER=openai_compat`) só foi testado com mock;
- a CI do GitHub passou com Docker, réplicas, testes sem rede, SBOM e trivy, mas sem a tela `/ui` nem o Grafana no ar.

## v3.7.0 (31/10/2026) — lições da Getnet v3

Balanço da v3: nota estimada 6,3 (v2: 8,18). CI vermelho em todos os commits do domínio, eval ao vivo e juiz
fora do relógio, README com números que não saíam do JSON commitado. Cada item abaixo corrige uma causa
medida, e cada trava nova foi testada contra o repositório da v3 (reprova o erro que ela teve).

| Causa na v3 | O que mudou | Onde |
|---|---|---|
| 59 testes do kit quebraram porque o domínio editou o motor | o domínio virou pacote trocável (`app/domain/`); o motor lê o domínio ativo na hora da chamada; os testes do kit fixam `DOMAIN=example`. Simulação: domínio Getnet inteiro no lugar → 315 testes do kit verdes | `src/app/domain/`, `tests/conftest.py` |
| trocar o limiar no motor quebrou mais 14 testes | `MIN_SCORE` é do domínio (`domain/challenge/__init__.py`) | `src/app/domain/` |
| pré-voo só trocava dados | `scripts/preflight.py` cria o domínio do desafio em 3 arquivos com dono único, copia prompts, tira a loja do produto e roda a suíte | `scripts/preflight.py` |
| 8 forks com check completo afogaram a CPU | check rápido por frente (segundos); check completo só na integração; 5 frentes | `scripts/fork_check.py`, `OWNERSHIP.json` |
| README §5 de um eval não commitado (replan 80% × 10%) | `fill_readme.py --check` e "resultado commitado = código atual" no `check.py` | `scripts/fill_readme.py`, `scripts/check.py` |
| `latest.json` era ignorado pelo git e entrou velho | `evals/results/` versionado; gate e eval via HTTP gravam em `var/` | `.gitignore`, `scripts/check.py` |
| pytest sobrescrevia `evals/results/latest.json` | testes gravam em `tmp_path`; casos/held-out/retrieval do eval apontam para o fixture | `tests/conftest.py`, `evals/run_evals.py` |
| 12 de 42 "provas" do README falhavam | `check.py` reprova teste citado que falha ou não existe | `scripts/check.py` |
| linha do tempo sem o último commit ("50 min" × 54) | `--check` exige todos os commits; só pode faltar um commit que mexa apenas em README/ESTADO | `scripts/fill_readme.py` |
| "72% escrito no relógio" contava 21.909 linhas de JSON | arquivos gerados fora da conta | `scripts/fill_readme.py` |
| loja de exemplo no índice, no Recall@3, no juiz e nas tools | `check.py` reprova marcas da loja depois do pré-voo | `scripts/check.py` |
| trecho real ("evite o modo desenvolvedor") descartado como injeção | regra só bloqueia a ORDEM de ativar o modo desenvolvedor | `src/app/guardrails.py` |
| ingestor escrito no relógio (~30 min) | `app/ingest.py` genérico lendo `data/sources.json` | `src/app/ingest.py` |
| PC com 7,9 GB e disco cheio não aguenta forks | tentativa 100% na nuvem; `scripts/medir_forks.py` para medir outra máquina | `docs/kit/PLAYBOOK.md` |
| gancho do Windows (`.venv/Scripts/python.exe`) quebra no Linux | gancho com `python3`; sessão da nuvem instala o lock e sobe o Docker ao abrir | `.claude/` |
| Docker não construía atrás do proxy da nuvem | certificado como segredo do build, `--network host` só quando detecta o proxy. Medido: `check --docker` verde em 47 s na nuvem | `Dockerfile`, `scripts/check.py` |
| ambiente da nuvem com rede limitada recusava o site da empresa | `scripts/cloud_probe.py` confere chave, rede, Docker e git ANTES do relógio | `scripts/cloud_probe.py` |
| na nuvem, `ANTHROPIC_API_KEY` não chega aos programas e `ANTHROPIC_BASE_URL` aponta para a conexão interna do Claude Code (o SDK a leria sozinho) | o app lê `APP_ANTHROPIC_API_KEY` e, em sessão remota, fala com a API pública; a sonda testa a chave em `GET /v1/models` (sem custo) | `src/app/config.py`, `src/app/llm.py`, `scripts/cloud_probe.py` |
| mesmo com `APP_ANTHROPIC_API_KEY`, o valor chegava trocado na sessão (107 caracteres, sem `sk-ant-`) e a API recusava; no PC a chave funciona | eval ao vivo e juiz rodam no PC com `scripts/pc_live.ps1` (prepara o Python, guarda a chave fora dos repositórios, testa sem custo, envia só os resultados para `fork/live`); a sonda da nuvem ganha `--chave-no-pc` | `scripts/pc_live.ps1`, `scripts/live_eval.ps1`, `OWNERSHIP.json` |
| (01/11/2026) com o valor certo em `APP_ANTHROPIC_API_KEY`, a sessão da nuvem recebe a chave e a API aceita; eval ao vivo de 4 casos na nuvem: US$ 0,034, 0 erro | eval ao vivo e juiz voltam para a sessão principal na nuvem; `pc_live.ps1` vira plano B | `docs/kit/PLAYBOOK.md`, `docs/kit/PROMPTS.md`, `docs/kit/CHROME.md` |
| eval ao vivo, juiz e vídeo depois do relógio | roteiro com marcos duros: ao vivo em 2º plano a partir de T+33, vídeo publicado até T+52 | `docs/kit/PLAYBOOK.md`, `docs/kit/PROMPTS.md` |

### Espelhado das referências públicas (docs/kit/REFERENCIAS.md, 01/11/2026)

| Ideia | Origem | Onde |
|---|---|---|
| ablação do replanejamento (com × sem), offline e ao vivo | nelsondell (9,5 na V4) | `SUPERVISOR_REPLAN`, `run_evals --ablate-replan`, bloco Replanejamento |
| matriz de confusão do router como tabela | EikiYamashiro | relatório do eval / README §5 |
| caminho do avaliador em 5 minutos + coluna "limite conhecido" | nelsondell, ArturFBrandi | README do kit §0 e §3 |
| 2 réplicas atrás de balanceador no CI (e o defeito de caso duplicado que isso revelou) | nelsondell, bnavarro12 | `scripts/scale_smoke.py`, `docker-compose.scale.yml`, `src/app/store.py`, ADR 0002 |
| flags de risco de fintech na resposta | Buzz | `src/app/grounding.py::risk_flags` |
| gitleaks no CI | nelsondell | `.github/workflows/ci.yml`, `.gitleaks.toml` |
| retrieval em pares pt/en + ablação de buscadores commitada | jonathansschaffer, ArturFBrandi | prompt da frente K |

Não validado ainda (faça no ensaio geral, PLAYBOOK §7): tempos reais de cada marco com 6 sessões da nuvem ao
mesmo tempo, o limite de uso da conta com essas 6 sessões, e a gravação do vídeo dentro da nuvem.
