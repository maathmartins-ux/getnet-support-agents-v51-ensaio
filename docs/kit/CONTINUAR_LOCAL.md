# Continuar o kit v5 (estado em 01/11/2026, ~19h30 de Brasília)

As 5 frentes (`v5/a`..`v5/e`) já foram **juntadas** em `kit-v5.0.0`, sem conflito: **487 testes passam e o ruff
está limpo**. O PR rascunho é o `maathmartins-ux/kit-preflight#5`. A quota da nuvem acabou, então o que falta
está listado abaixo para uma sessão local.

## O que falta (em ordem de valor para a nota)

Feito depois da 1ª versão deste guia: ensaio sobre o domínio da v4 ([ENSAIO_V5.md](ENSAIO_V5.md)), `search_query`,
estado do caso, mapa OWASP Agentic, `/ui`, Grafana, correção de idioma, proteção contra rodada degradada. CI do
GitHub verde (Docker, réplicas, testes sem rede, SBOM, trivy). 487 testes passam.

**BLOQUEIO: o limite mensal de gasto da API da Anthropic foi atingido** ("regain access on 2026-12-01"). Nenhum
eval ao vivo roda até lá, ou até você aumentar o limite em console.anthropic.com → Limits. Os itens 1 e 2
dependem disso. Rodar o kit offline e os testes não gasta nada.

| # | Item | Por que importa | Tamanho |
|---|---|---|---|
| 1 | **Medir o estado do caso ao vivo**: `memory` com `--repeat 3` (motor atual) e comparar com a 2ª rodada do ensaio (pass^3 0,62; números 92%). Hoje só há teste e offline | é o único item do v5 sem medida ao vivo | 10 min + ~US$ 1,6 |
| 2 | **Repetir o `official` e o `memory` ao vivo para ter 2 rodadas por split** (o 1,00 de pass^3 é uma rodada de 10 cenários) | tirar o ruído do número | 20 min + ~US$ 2,5 |
| 3 | Subir o perfil `observability` numa máquina com acesso ao Docker Hub e conferir os 12 painéis com tráfego real | só foi validado contra os nomes de métrica | 20 min |
| 4 | Juiz de outra família ao vivo (`JUDGE_PROVIDER=openai_compat`) com uma chave real | hoje só com mock | 20 min |
| 5 | `docs/PILOT.md` e a seção "Perguntas da entrevista, respondidas" no README do desafio (a frente D preenche; o modelo está em `pesquisa/getnet.md` §1.3) | Engineering Judgment e Business Fit | 30 min |
| 6 | Revisar e tirar o PR #5 de rascunho; depois o 1º uso real: uma tentativa cronometrada (`V5_PROMPT_M.md`) | o kit só vale depois de usado | — |

## Preparar o PC

Uma sessão do Claude Code no terminal, sem app desktop, sem Docker Desktop, **um subagente de cada vez**
(cinco ao mesmo tempo estouraram o limite de requisições e derrubaram duas frentes):

```powershell
git clone https://github.com/maathmartins-ux/kit-preflight.git
```
```powershell
cd kit-preflight
```
```powershell
git checkout kit-v5.0.0
```
```powershell
py -m venv .venv          # Python 3.11 ou mais novo
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m pytest -q -n 2
```

Chave do LLM (só para o item 2 e o 7): arquivo `.env` na raiz com `ANTHROPIC_API_KEY=...`, digitada por você no
arquivo, **nunca no chat nem nas variáveis do sistema** (com a variável definida no sistema, o Claude Code pode
cobrar da API em vez do plano).

## Prompt para a sessão local

```text
Você continua o kit v5 (repositório kit-preflight, branch kit-v5.0.0). Leia docs/kit/CONTINUAR_LOCAL.md,
docs/kit/LICOES_V4.md e o CHANGELOG (v5.0.0). Responda em português simples. PC fraco: um subagente por vez,
nada de Docker local, pytest com -n 2. Faça os itens da tabela "O que falta" na ordem, cada um com teste, commit
pequeno e o número medido na mensagem. Nunca escreva número que não mediu e nunca copie código dos repositórios
de referência (sem licença). Comece pelo item 3 (os 1 e 2 esperam o limite da API). Confira a CI da branch na aba Actions depois de cada push.
```

## Onde está o que

| Onde | O quê |
|---|---|
| `kit-v5.0.0` (PR #5) | o v5 integrado: motor, scripts, docs, as 5 frentes |
| `v5/a`..`v5/e` | as branches das frentes (já dentro de `kit-v5.0.0`; ficam como histórico) |
| `arquivo-privado` | **só neste repositório privado**: pesquisa, lições, cópias de 22 repositórios de referência com manifesto, material da v4 e scripts de medida. Uso pessoal; não torne o repositório público e não copie `refs/` para os repositórios dos desafios |
| `getnet-support-agents-v4` (público) | a tentativa entregue, último commit `fd85cf6`; não muda |

O ambiente temporário da nuvem (worktrees, cópias em `/home/user/refs/`) se perde quando a sessão acaba; o que
importa está nas branches acima.
