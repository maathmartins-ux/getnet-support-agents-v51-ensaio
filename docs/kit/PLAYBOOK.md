# Roteiro da tentativa (kit v5.3) — 100% na nuvem, ≤ 58 min, mirando ≥ 9,5

Escrito a partir da Getnet v4 (34 min do 1º ao último commit, CI verde; lições em [LICOES_V4.md](LICOES_V4.md)),
da V5 (50,8 min, nota estimada 8,2–8,5, não enviada; erros de nota e de tempo em [POSMORTEM_V5.md](POSMORTEM_V5.md))
e da leitura de 28 soluções públicas do mesmo case ([pesquisa/getnet.md](pesquisa/getnet.md),
[pesquisa/formato_swarm.md](pesquisa/formato_swarm.md)). Cada regra abaixo existe porque a falta dela custou nota
ou tempo. O PC só abre o Chrome: nenhum fork, teste ou Docker roda nele.

Prompt da sessão principal pronto para colar: [V5_PROMPT_M.md](V5_PROMPT_M.md). Prompts das frentes:
[PROMPTS.md](PROMPTS.md). Operação pelo Chrome: [CHROME.md](CHROME.md).

**Três fatos que mudam a estratégia** (pesquisa de 01/11/2026):
1. O avaliador da Régua V4 **não roda nada e não assiste ao vídeo** ("Não executei build nem testes", "Vídeo …
   não assistido"). A nota sai do que está ESCRITO e COMMITADO: respostas reais em `docs/DEMO.md`, números em
   `evals/results/`, prova do relógio em `docs/TIMESHEET.md`.
2. Ele pune **atalho em vez de arquitetura** ("resolvem casos por atalho, em vez de pela arquitetura"), resposta
   em pt para pergunta em en, Support que não lê o dado do cliente, HITL que não volta ao fluxo, memória ausente.
3. Nenhuma nota ≥ 9 na Régua V4 foi feita em 60 min. O 9,5 público (nelsondell) perdeu meio ponto em: escala
   presa ao armazenamento, suíte que precisava de rede para começar, factual sem validação humana.

**O que a V5 ensinou sobre o relógio** (pós-morte §3): a frente K foi o caminho crítico (corpus + gold +
escolha do buscador sob 8 subagentes, integrada só no T+18,9); o buscador foi decidido no T+24,9; o primeiro sinal
ao vivo dos oficiais veio no T+31; ~10 min se perderam ANTES do relógio (add_repo negado, ramo padrão errado, tag que
o proxy não envia). A v5.3 tira tudo isso do relógio: kit já no repositório, buscador já escolhido, fumaça ao vivo no
T+12, cortes escritos e 5 min de folga.

---

## 0. Antes do relógio (na véspera ou até T−30 min). Nada disto conta no tempo.

| # | O quê | Como saber que está feito |
|---|---|---|
| A0 | **Repositório da tentativa preparado pela sessão maestra** (pós-morte T1): repositório vazio do desafio, público, com o app do Claude com push; `main` com **1 commit** (`chore: repositório (antes do relógio)`, só um README de uma linha); ramo **`kit-fonte`** com o kit v5.4 inteiro (inclusive `docs/kit/`; origem: ramo `kit-v5.4.0` do repositório do kit); **ramo padrão = `main`** conferido no GitHub (Settings → Branches). A sessão do relógio abre NESTE repositório: nenhum `add_repo` dentro do relógio (V5: add_repo negado). | `git ls-remote --symref origin HEAD` → `refs/heads/main`; `git ls-remote --heads origin kit-fonte` com 1 linha |
| A1 | **Ambiente da nuvem com rede** para o site da empresa e para as APIs de dado ao vivo (`olinda.bcb.gov.br`, `geocoding-api.open-meteo.com`, `api.open-meteo.com`). Menu do ambiente → *Network access*: Full, ou os domínios em *Allowed domains*. | `python scripts/cloud_probe.py --site <url>` sem FALTA |
| A2 | **Chave do LLM do app** nas variáveis do ambiente: `APP_ANTHROPIC_API_KEY` (nunca no chat). Opcional: juiz de outra família (`JUDGE_PROVIDER=openai_compat`, `JUDGE_BASE_URL`, `JUDGE_MODEL`, `JUDGE_API_KEY`). | sonda: "chave do LLM do app" OK |
| A3 | **Buscador decidido pelo kit** (pós-morte N3/T2): o padrão do kit (`data/retriever.json` / padrões de `config.py`, frente K53) vale no relógio; a K **não** roda `--choose-retriever`. A latência foi medida no ensaio com a máquina parada. | `kit-fonte` traz o padrão; a K só mede a qualidade no gold novo |
| A4 | **Sonda verde** numa sessão da nuvem no repositório da tentativa: `python scripts/cloud_probe.py --site <url>` | `AMBIENTE PRONTO` |
| A5 | **PC só com o Chrome** (sem app desktop, sem Docker Desktop). | > 3 GB livres |
| A6 | **Orçamento, em DUAS contas separadas.** (1) Plano/créditos do Claude (claude.ai → Configurações → Uso; a tela do dono é em **reais**, limite R$ 130 na v4). (2) **API da Anthropic** (console.anthropic.com → Limits), que paga o eval ao vivo e o juiz (≈ US$ 11 no roteiro do §2). Confira o limite da API ANTES: no ensaio da v5 ele acabou no meio ("regain access on 2026-12-01") e nenhuma rodada ao vivo rodou depois. | os dois limites conferidos; sonda da API sem `aborted_quota` |
| A7 | **Página de conferência testada antes do relógio** (`scripts/label_page.py`, publicada pela maestra com o Artifact tool): dono e 2ª pessoa abrem o link e marcam 2–3 respostas de teste; a maestra lê a coleção `rotulos` e vê as duas fichas. 2ª pessoa ensaia com uma conversa em INGLÊS (V5: kappa 0,054 porque ela leu "idioma" como "devia ser em português"). | duas fichas em `rotulos` |
| A7b | **Dono e 2ª pessoa com as janelas do §2.3 reservadas**: J1 (T+16→T+26, os dois, cada um sozinho: 2 exemplos de treino + 10 respostas às cegas; T+26→T+29, os dois juntos: consenso só das divergências) e J2 (T+34→T+41, só o dono, revisão da análise de erros). Sem a 2ª pessoa, o placar mostra "1 rotulador" como abaixo da referência. | combinado, com a hora de Brasília de cada janela |
| A8 | **Limite da API com folga de US$ 30** | sonda da API sem `aborted_quota` |

---

## 1. Quem faz o quê (orquestração da v4, que funcionou)

A sessão principal (**M**, o regente) faz SPEC, integração, medição e README. As frentes são **subagentes da
própria M** (ferramenta Agent, em segundo plano), cada uma num `git worktree` com branch `fork/<x>`; a M integra
localmente com `scripts/check_ownership.py <x> --base main` e merge `--no-ff`. Não há sessão-irmã nem prompt
colado pelo dono (na v3, sessão criada por outra sessão recusou tarefa; na v4, subagentes não recusaram). A
**maestra** (sessão fora do relógio, §2.2) prepara o repositório, publica as páginas humanas e escreve docs em
ramos `maestra/<x>`; ela nunca commita em `main`.

| Frente | Dono de (OWNERSHIP.json) | Entrega | Pronto (v4 → alvo v5.3) |
|---|---|---|---|
| **H** autor cego | `evals/heldout_blind.jsonl` (devolve o JSONL; a M commita sem ler) | 2 × 40 casos que só viram enunciado + SPEC | T+3 → T+12 |
| **R** roteamento | `domain/challenge/flow.py`, prompts router/supervisor/geral, `data/intent_examples.d/r.jsonl`, testes do router/supervisor, **`needs` do domínio** | intent ≥ 90% nos splits do gate; `standalone` no router.md; casos `dependent` | T+4 → T+16 |
| **K** conhecimento | `data/sources.json`, `data/knowledge/**`, glossário, `evals/retrieval.d/**` (com o gold essencial), prompt faq, `docs/SOURCES.md` | corpus por entidade oficial, gold essencial às cegas, Recall@3/MRR do buscador do kit, **`official_check` verde** | T+6 → **T+12** (V5: T+18,9) |
| **T** ferramentas | `domain/challenge/tools.py`, `data/crm/**`, prompt records, `tests/test_tools.py` | leituras + escritas com confirmação; tool devolve totais e datas calculadas (o LLM não soma) | T+4 → T+16 |
| **Q** qualidade e segurança | `evals/cases.d/**`, calibração do juiz, testes HTTP e de guardrail, EVAL_STRATEGY, THREAT_MODEL (com OWASP Agentic ASI01–10) | official-var, memory ≥ 15 (com `standalone`), guardrail ≥ 30, hard, `dependent` | T+6 → T+18 |
| **D** documentação | ARCHITECTURE, OBSERVABILITY, RUNBOOK, ADRs (inclui "considerado e não feito"), PILOT, perguntas da entrevista no README | docs só com o que o código faz | T+5 → T+15 |

O motor (`src/app/*.py`), scripts, runner do eval e fixtures são **congelados** durante o relógio
(`.claude/hooks/ownership_guard.py` recusa a edição; `check_ownership.py` recusa o merge). Exceção: bug de motor
achado pelo eval ao vivo vira commit da M com teste de regressão e o número no commit (v4: 3 correções assim).

---

## 2. Linha do tempo (T = commit `chore: scaffold`; **regra dura: nada depois de T+58**)

**Hora sempre pela máquina, nunca de cabeça** (pós-morte T6: a M informava a hora ~3 min adiantada). O relógio vale
pelo commit de scaffold e pelo último commit (T7); tags são opcionais: crie `clock-start`/`clock-end` **localmente**
(`timesheet.py` e `delivery_message.py` leem as tags locais) e tente o push, mas o proxy da nuvem derruba push de tag,
então nunca espere por ele. Em todo relatório ao dono:

```bash
T0=$(git log --format=%ct --grep='^chore: scaffold' | tail -1)
echo "T+$(( ($(date +%s) - T0) / 60 )) min · $(TZ=America/Sao_Paulo date +%H:%M) Brasília"
```

| Quando | Quem | O quê | Saída verificável |
|---|---|---|---|
| T+0 | M | **scaffold a partir de `kit-fonte`** (comandos no V5_PROMPT_M passo 1: `git checkout origin/kit-fonte -- .`, procedência para `docs/`, `docs/kit/` fora do índice), `pip install -e ".[dev]"`, commit `chore: scaffold from entregar-desafio-cronometrado kit v5.4.0`, push de `main` | 1º commit do relógio |
| T+0 | M (2º plano) | (melhor: `python scripts/fetch_models.py --fast` no script de configuração do ambiente da nuvem, antes do relógio; aí este passo só confere o cache) `python scripts/fetch_models.py --fast > var/fetch_models.log 2>&1 &` (modelos do buscador do kit no cache) e `python scripts/preflight.py > var/preflight.log 2>&1 &` (confere ramo padrão `main` e `kit-fonte` consumido ANTES de mexer em arquivo; depois a suíte) | `MODELOS PRONTOS`, `PRÉ-VOO OK` |
| T+0→**T+4** | M | **SPEC dos oficiais primeiro** (o `evals/cases.jsonl` só depois de `esvaziar evals/cases.jsonl` aparecer no `var/preflight.log`, em segundos: o pré-voo esvazia esse arquivo): os 10 casos `official` literais, cada um com `expect.facts` (regex dos fatos de referência, escritas ANTES do código, COM SINÔNIMOS: o mesmo fato dito de outro jeito também passa — ensaio v5.4: "conta digital/Get Conta" reprovava por a regex só aceitar "conta de pagamento"; no T+15 confira cada regex contra as 3 respostas da fumaça) e `expect.entities` (produtos citados); sonda da API (1 caso, `--max-usd 0.2`); commit do pré-voo e commit `spec: oficiais` | `aborted_quota` = PARE e avise o dono |
| **T+4** | M | worktree + subagente **K** (Opus): só precisa do enunciado, da URL do site e dos casos oficiais | K no ar |
| T+4→T+8 | M | resto da SPEC (taxonomia, desempates, resposta parcial, `standalone`) + casos: replan ≥ 20, dependent ≥ 10, parallel, approval, memory ≥ 15 com `expects_fact` e `standalone`, cobrindo os seguimentos que derrubaram a V5 ("e a outra?", "and the other terminal?", "how long has it been down?", "e qual foi o valor dela?": demonstrativo = entidade da última resposta) | commit `spec` |
| **T+8** | M | dispara R, T, Q, D (Opus) e H1, H2, P (Sonnet: escrevem só JSONL) | 7 subagentes |
| T+4→**T+12** | K | ingere (páginas de cada entidade oficial + FAQ), perguntas do gold com `origin` geradas em segundos por `python -m evals.gold_questions` (`page` = FAQ do próprio corpus, `official`/`real` = casos e perguntas reais, 20 `no_source`: a K só revisa, não escreve; no nelsondell a metade das páginas saturou e toda a diferença veio da outra), gold essencial às cegas (2 rotuladores, grupos por fato), placar do caminho do agente (Recall@5, MRR@10, rank do 1º gold, por origem), **≥ 15 perguntas sem fonte** (fora do domínio, `relevant: []`) para a separação com × sem fonte (AUC e gap; nelsondell: 82 × 15) e **`python scripts/official_check.py` verde** e `python -m evals.gold_questions --check` = GOLD OK (≤ 8 min) | `fork k: pronto (… official_check N/N, GOLD OK)` |
| **T+12** | M | merge da K **só com `official_check` verde** (condição de merge); logo depois, em 2º plano, o **eval aquecido**: `python -m evals.run_evals --out var/warm.json > var/warm.log 2>&1 &` e a **imagem aquecida**: `python scripts/check.py --warm-image > var/warm_image.log 2>&1 &` (build frio com o buscador do kit ~4 min: pip + modelos; depois só dados e código, segundos). O eval monta o índice do corpus e grava a medida da busca em `var/retrieval_cache.json`; ensaio v5.4: frio, o eval do T+18 levou 580 s e a medida da busca 91 s em cada chamada) | `main` com corpus, `var/warm.json` |
| T+12→T+15 | M (2º plano) | **fumaça ao vivo** só do official, repeat 1 (~US$ 0,3): `python -m evals.run_evals --live --split official --repeat 1 --max-usd 0.5`; completa → commit `evals/results/live_official.json` (a maestra gera a página dela no T+15) | cada oficial reprovado com a causa (fonte, portão, idioma) |
| T+15→T+18 | M | causa de cada oficial reprovado na fumaça corrigida no domínio (corpus, glossário, regra), com teste; `official_check` de novo | commits `fix:` com o caso |
| T+8→**T+18** | R, T, Q, D | commits pequenos por item, `fork_check.py <x>` antes de cada um; M integra cada frente ao ficar pronta; H1+H2 → `evals/heldout_blind.jsonl` e P → `evals/real_questions.jsonl` sem ler | `main` verde |
| T+18→T+20 | M | `run_evals --calibrate-gate --apply`; `make eval`; gate ≥ 90%; `python scripts/check.py` e `python scripts/official_check.py` (com o eval aquecido do T+12 e o cache da busca: 2–3 min; ensaio v5.4 sem eles: 10–14 min). `make compare` (comparar buscadores, 504 s) só se a K pedir, em 2º plano. Gate verde antes do T+20 → rodada 1 na hora | commit com o gate |
| **T+20→T+33** | M (2º plano) | **rodada 1, bateria integral num processo só**: `scripts/live_eval.sh --max-usd 20` (todos os splits; official e memory repeat 3, o resto 1; o aviso `Estimativa ao vivo` sai antes do 1º gasto e `AVISO: teto` = suba o teto, não corte split). Até 12 conversas ao mesmo tempo (`LIVE_MAX_CONCURRENT`) e o juiz em 8 linhas paralelas (`JUDGE_WORKERS`), julgando cada split ao terminar com um saldo único. Ensaio v5.3 final (8 workers): 12,8 min com o juiz, US$ 11,1 + 6,5 | `live_*.json` todos `complete`, `judge.json` |
| T+33→T+36 | M | `evals.failure_modes` + reprovações do juiz **caso a caso**: corrigir a CAUSA no domínio (corpus, tool, regra, cartão de capacidades), nunca prompt genérico; teste por correção | commits `fix:` com o caso |
| **T+36→T+44** | M (2º plano) | **rodada 2 só dos splits afetados** (official e memory `--repeat 3`; os outros que caíram, repeat 1) com o juiz; antes, `cp judge.json judge_r1.json`; o juiz julga SÓ as linhas novas; depois `python -m evals.judge_diff evals/results/judge_r1.json evals/results/judge.json` → `docs/JUDGE_DIFF.md` | antes × depois |
| **T+35** | M (2º plano) | **vídeo** (`make video`), sem depender da rodada 2 (pós-morte N10) | MP4 |
| T+44→T+47 | M | merge dos ramos `maestra/*`; `scripts/demo_md.py`; `scripts/timesheet.py`; `check.py --docker --scale`; `scripts/delivery_message.py --repo <url>`; textos `{{...}}` do README; commit de tudo que não é README | `CHECK VERDE` |
| T+47→T+50 | M | `git tag clock-end` (local; push opcional); `make final` (README sozinho no último commit + push) | `fill_readme --check` OK |
| T+50→T+53 | M | CI do último commit no GitHub; vermelho → plano B (§4). Com o buscador do kit o job `check` leva ~6–8 min com os caches do Actions quentes (modelos e vetores, semeados pelos pushes do T+0 e do T+12; frio ~12 min): o CI do commit do gate (T+20) é o sinal cedo; o do `make final` (só README) repete o mesmo código | Actions verde |
| **T+53→T+58** | — | **folga planejada de 5 min**: só absorve atraso; nada novo começa aqui | — |
| **T+58** | — | **nada depois** (o dono fixou 60 min redondos como teto absoluto; o kit para em 58). Mensagem ao dono com o placar inteiro | — |

Orçamento da API (conta separada do plano), medido no ensaio v5.3 (11 splits): fumaça ≈ US$ 0,5; rodada 1 ≈ 11 de
conversa + 6 de juiz; rodada 2 ≈ 5 + 2 → **≈ US$ 25; deixe pelo menos US$ 40 livres**. Teto curto aborta split e
split abortado não vai ao juiz (ensaio v5.3: teto 4 para ~5,5 cortou o official em 24 de 30).

**Relatório ao dono a cada ~5 min**: a linha do comando acima + marco atual + adiantado/atrasado em minutos +
próximo passo. Uma linha. O dono acompanha pelo celular.

### 2.1 Cortes decididos antes (se X não fechar até T+Y, segue sem X e declara)

Corte não é falha escondida: cada um vira uma linha em README §7 (limitações) com o motivo e o número que faltou.

| Se não fechar até | Então | Declara |
|---|---|---|
| SPEC dos oficiais no **T+5** | K sai com os 10 enunciados oficiais e as entidades; os `facts` chegam no `spec` do T+8 e a K roda o `official_check` de novo | — |
| K com `official_check` verde no **T+15** | merge da K assim mesmo, com os fatos que falham no texto do commit; a M acrescenta a página que falta em `sources.json` até o T+18; ainda vermelho no T+20 → segue | "official-NN: fato fora do top-5" |
| frente R/T/Q/D pronta no **T+18** | integra o que houver | o que ficou de fora |
| gate ≥ 90% no **T+21** | rodada 1 começa assim mesmo; nada de retunar o gate depois | o gate medido |
| rodada 1 completa no **T+34** | usa os splits que terminaram limpos; official ou memory incompleto roda SÓ ele de novo; o resto fica fora | splits fora da rodada 1 |
| J1 (rótulos às cegas) no **T+26** | a página fica aberta até o T+35 e a importação vai para o T+36, sem rodada de consenso; ninguém até o T+35 → segue | "1 rotulador", "sem rodada de consenso" ou "factual sem validação humana" |
| consenso de J1 no **T+29** | publica só a concordância independente (antes); `depois_do_consenso` fica vazio | "sem rodada de consenso" |
| J2 (revisão da análise de erros) no **T+41** | publica o rascunho do LLM como "não revisado", com o nº de linhas revisadas | "análise de erros revisada em N de M linhas" |
| rodada 2 completa no **T+45** | publica só a rodada 1; JUDGE_DIFF "não medido" | "rodada 2 não medida" |
| vídeo no **T+44** | entrega sem vídeo (o avaliador não assiste) | "sem vídeo" |
| `check.py --docker --scale` no **T+48** | `check.py` sem `--docker --scale` | "imagem e escala não reconferidas no relógio" |
| `make final` começado no **T+50** | `make final` com o que houver; nada novo | — |
| CI verde no **T+53** | `git revert` do último commit de código e `make final` de novo (cabe na folga) | o commit revertido |

### 2.2 Sessão maestra (fora do relógio; nunca commita em `main`)

A maestra é a sessão que orquestra a tentativa de fora: não conta no relógio, não escreve código do produto e só
entrega por ramos `maestra/<x>`, que a M integra com `merge --no-ff` (V5: zero conflito assim).

| Quando | O quê | Saída |
|---|---|---|
| T−30 | A0 (repositório, `kit-fonte`, `main` com 1 commit, ramo padrão), A4 (sonda) e A7 (página de teste com as duas pessoas) | §0 verde |
| T+0→T+58 | acompanha `git log origin/main` e avisa a M (`send_message`) quando um marco passar do corte do §2.1 | — |
| **T+15** | `git pull`; `python scripts/label_page.py --n 10 --splits official --raters <dono>,<2ª pessoa>`; publica `var/rotulagem.html` com o Artifact tool e as `capabilities` que o script imprime; manda o link ao dono (ele compartilha com a 2ª pessoa como quem usa a página, não edita) | link da página de rotulagem (J1) |
| **T+26** | lê a coleção `rotulos` (ArtifactData) para `var/rotulos.json`; `python -m evals.label --import-page var/rotulos.json`, `--report` e `--divergences`; manda ao dono o conteúdo de `evals/human_divergences.md` (só as situações em que os dois marcaram diferente, com o modelo das linhas de volta) | `evals/human_labels.*.csv`; concordância, kappa e AC1 (antes) |
| **T+29** | recebe do dono as linhas `id=pass\|fail\|diverge` do consenso; `python -m evals.label --consensus <txt>` e `--report`; commit em `maestra/rotulos` | `human_review.json` com antes e depois do consenso |
| **T+34** | página de revisão da análise de erros da rodada 1 (frente E53: ~30 linhas com a evidência inteira e o rascunho passa/falha do LLM; o dono confirma ou edita cada uma); link ao dono | link da página de revisão (J2) |
| T+34→T+42 | rascunho do README §0/§5/§7 com os números da rodada 1 e ADRs que mudaram, em `maestra/readme` e `maestra/adr` | ramos `maestra/*` |
| **T+35** | lê as revisões do dono; grava o resultado (linhas revisadas, edições) para o `FAILURE_MODES.md`; commit em `maestra/analise` | ramo `maestra/analise` |
| T+38 | avisa a M de que os ramos `maestra/*` estão prontos para o merge | — |

### 2.3 Tempo do dono dentro do relógio (≈ 20 min, em três janelas)

| Janela | Quem | O quê | Duração |
|---|---|---|---|
| antes (T−30) | dono + 2ª pessoa | página de teste (A7), 2–3 respostas cada | 5 min |
| **J1: T+16→T+26** | dono **e** 2ª pessoa, cada um sozinho | **2 exemplos de treino** (a página mostra o gabarito e o porquê; não contam) e **10 respostas às cegas** na página de rotulagem (sem a nota do juiz; ninguém vê a marcação do outro) | ~9 min cada |
| **J1b: T+26→T+29** | dono **e** 2ª pessoa, juntos (ligação ou mesma sala) | **rodada de consenso**: leem só as situações em que marcaram diferente (`human_divergences.md`, ~20 s cada) e dizem o rótulo combinado, ou `diverge` se continuarem discordando; o dono manda as linhas à maestra. A concordância independente (antes) não muda; o README publica as duas | ~3 min |
| **J2: T+34→T+41** | só o dono | **revisão da análise de erros** da rodada 1: confirma ou corrige o passa/falha que o LLM rascunhou em cada linha (o nº de edições é publicado) | ~8 min |
| fora das janelas | dono | lê o relatório de 5 em 5 min; não precisa responder | — |
| T+58 | dono | recebe o placar inteiro e decide se envia (abaixo de 9,5 não se envia) | — |

---

## 3. Regras para todas as frentes e para a M

1. **Motor congelado** durante o relógio (exceção: bug do ao vivo, com teste e número no commit).
2. **Gate nunca desce.** Abaixo de 90%, corrige-se o domínio pela matriz de falhas.
3. **Held-out cego.** O teste de contaminação reprova frase copiada para regra ou exemplo.
4. **Número só de arquivo commitado.** README só por `fill_readme.py`; o check reprova divergência.
5. **README sozinho no último commit** (`make final`). Qualquer commit depois exige rodar de novo (v4: CI
   vermelha 2 vezes por isso).
6. **Nada de exemplo no produto**: nem `example.com` em caso de teste (use domínio fictício próprio).
7. **Comentário e commit só com número medido.**
8. **Atalho não:** nenhuma resposta escrita no código para um cenário; o Support sempre lê o dado do cliente;
   respostas no idioma da pergunta.
9. **Processos:** nunca `pkill -f "<texto do próprio comando>"` (mata o shell); mate por PID:
   `ps -eo pid,args | grep "[r]un_evals"`. Espera longa: Monitor com `until`, nunca `sleep` encadeado.
10. **Rodada ao vivo só vale se terminou limpa.** `status: complete` e `llm_errors` ~0. `degraded` (chamadas perdidas),
    `aborted_quota` (limite da API) e `aborted_*` vão para `.degraded.json`/`.aborted_*.json` e NUNCA substituem um
    resultado completo; não commite nem cite número de rodada assim (a v5 descartou uma por isso).
    **Juiz interrompido** (`judge.json` com `aborted_quota`/`aborted_llm_error`): o parcial fica gravado; com o limite
    da API liberado, `python -m evals.judge <os mesmos live_*.json> --resume` julga só o que faltou (ensaio v5.1: o
    limite acabou no 99º julgamento e, antes desta regra, tudo se perdia).
11. **Mudou o motor, meça num domínio real antes de declarar melhoria.** 487 testes verdes não pegaram 3 regressões
    que o ensaio sobre a v4 achou em 1 hora (`ENSAIO_V5.md`). Use `docs/kit/ENSAIO_V5.md` como roteiro.
12. **venv certa:** o `check.py` recusa se o pacote `app` vier de outro repo (`pip install -e .` no repo atual).
13. **Fato oficial garantido antes do ao vivo** (pós-morte N1). Cada caso oficial traz `expect.facts` (regex sem
    caixa que casa a resposta E o trecho da fonte: número, nome, alternância pt|en, nunca a frase inteira) e
    `expect.entities`. `python scripts/official_check.py` reprova entidade sem trecho ingerido e fato fora do top-5
    do buscador ativo; roda na K antes do merge, na M no T+18 e no `check.py` (gancho da frente E53). Vermelho se corrige no CORPUS (página que falta,
    tabela inteira, glossário), nunca afrouxando a regex depois de ver a busca.
14. **Hora pela máquina e relógio pelo commit** (T6/T7): toda hora citada sai do comando do §2; tags só locais.

---

## 4. Planos B (o que não é corte de tempo; os cortes estão no §2.1)

| Se… | Então |
|---|---|
| `preflight.py` reprova o repositório (ramo padrão ≠ `main` ou `kit-fonte` ausente/não consumido) | PARE antes da SPEC e avise a maestra numa linha: ela corrige no GitHub; o relógio só conta a partir do scaffold certo |
| API com limite atingido no T+0 | parar: sem LLM o sistema roda no determinístico e o gate semântico não passa; remarcar |
| fumaça do T+12 com oficial em "sem fonte" | `official_check` verde e o ao vivo recusa → é o portão (calibre com pares pt/en, N2), não o corpus; `official_check` vermelho → corpus |
| split ao vivo `aborted_max_usd` | rodar SÓ ele de novo: `run_evals --live --split <s> --max-usd 2 --repeat 3` |
| APIs de clima/câmbio bloqueadas | `LIVE_DATA=off` (cai na busca web) e declarar `unsupported_numbers` como limite |
| modelo do buscador do kit não baixou (`fetch_models` falhou) | `official_check` reprova "buscador caiu"; rode `fetch_models` de novo; no T+15 ainda sem modelo → `RETRIEVER=bm25` declarado e `official_check` nele |
| CI vermelho no T+53 | `git revert` do último commit de código, `make final` de novo (cabe na folga) |
| proxy recusa o push de tag | ignore: tags são locais (T7); o relógio é o commit de scaffold |

---

## 5. O que cada critério da Régua V4 exige (nomes e pesos oficiais) e onde fica a prova

| Critério (peso) | Evidência escrita no repositório | Frente |
|---|---|---|
| Business & Challenge Fit (8%) | `docs/DEMO.md` com as respostas REAIS dos 10 cenários; Support lendo o dado do cliente; `docs/PILOT.md` (shadow → assistido → autônomo); clima/câmbio de API oficial com data | M, D |
| Agentic Reasoning & Orchestration (15%) — inclui o Router | supervisor que observa e replaneja por falha E por achado (`needs`); split `dependent`; ablação por conclusão (`--mode no_needs`); orçamento por turno (`budget_exhausted`); matriz de confusão do router | R, M |
| Context, Knowledge & RAG (10%) | trechos literais com URL/data/SHA e contexto de seção; Recall@k por trecho e por página; gold por regra; `--compare-retrievers`; portão calibrado (`--apply`) | K |
| Tool & Action Engineering (10%) | JSON Schema estrito, identidade fora do schema, escrita com confirmação e quatro olhos; detector de ação alegada sem execução | T |
| Security & Identity (13%) | JWT, rate limit, guardrails além de regex, PII mascarada; OWASP Agentic ASI01–10 com teste por linha; LGPD (`DELETE /me/conversations/{id}`, retenção) | Q, M |
| Memory, State & Resilience (8%) | split `memory` ao vivo; pergunta autônoma (`search_query`); volume persistente; réplica cai e a conversa segue | R, Q |
| Human Oversight & Risk Management (7%) | fila persistida, operador responde e o PLANO retoma; caso só fecha com prova; ataque não abre caso | T, Q |
| Evaluation & Quality Engineering (14%) | gate no CI + **replay da gravação ao vivo** no CI; pass^3; juiz com canários (e de outra família se houver chave); **validação humana** (`human_review.json`); `FAILURE_MODES.md` | Q, M |
| Observability, Reliability & Cost (6%) | trace_id, `/metrics`, `/ready`, custo por turno resolvido e por intenção, dashboard Grafana provisionado | M |
| Production Engineering (5%) | CI verde com rede cortada, SBOM e trivy, actions por SHA, overlay endurecido, 2 réplicas | M |
| Engineering Judgment (4%) | ADRs com o número que decidiu (inclui "considerado e não feito"); "Perguntas da entrevista, respondidas"; limitações com números; `docs/TIMESHEET.md` | D, M |

Gates da V4 (feedback público): **Critical Security**, **Challenge Fit** ("o núcleo foi implementado no próprio
código"), **Evidence** ("logs de execução real commitados"), **Semantic Quality** ("não comprovado" quando não há
medição de qualidade das respostas). O kit v5 tem um artefato para cada um.

---

## 6. Depois do último commit

Nada no repositório do desafio. Balanço e lições no repositório do kit.

### Senhas de teste do login (kit v5.4)

`POST /auth/login` (usuário + senha → o mesmo JWT do `/chat`) usa só hashes em `var/credentials.json`, fora do git.
Os usuários de teste saem do domínio (`users()` do domínio, se existir; senão os `customers`/`owner` dos registros do
CRM fictício da frente T). Cada ambiente semeia as suas: `python -m app.auth seed-passwords` (na imagem:
`docker compose exec app python -m app.auth seed-passwords`) imprime usuário e senha uma vez e anota em
`var/demo_passwords.txt`. No relógio: depois do merge da T, a M roda o seed uma vez para a demo e o vídeo; o README já
traz o passo "Entrar" para o avaliador semear no clone dele. O token por CLI (`python -m app.auth <usuário>`) fica só
como atalho de teste.
