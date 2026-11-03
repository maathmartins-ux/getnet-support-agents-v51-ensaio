# Frente G — respostas oficiais fundamentadas (kit v5.1)

Alvo: item 1 da correção da v4 (juiz: grounded 60% nos 10 cenários oficiais, `numbers_acc` 80%). Nada aqui foi
medido ao vivo: a API está bloqueada (limite de gasto). Os números abaixo são da réplica offline sobre as 30 respostas
oficiais da v4 já julgadas (`evals/results/{live_official,judge}.json` da v4, commit `fd85cf6`).

## O que mudou

- **Cartão `policy:capabilities`** (`src/app/capabilities.py`): gerado do registro de ferramentas (descrição,
  `write`, `risk`), da mecânica de ações (escrita só propõe; risco alto = confirmação + aprovação de operador; TTL) e
  do fluxo humano. Vai no prompt de quem redige (agentes e supervisor), na evidência do turno (números dele contam) e
  na resposta da API. O domínio acrescenta `POLICY_LINES` e `ACTION_KEYWORDS`. Por quê: 2 das 12 reprovações
  (official-03) eram regra verdadeira do sistema sem fonte nenhuma; o "remote restart" do official-05 existia
  (`restart_terminal`), o juiz só não via.
- **Checagem de frases** (`src/app/claims.py`, gancho de 2 linhas no `pipeline.py` depois dos números): verificador LLM
  (papel `claims`, Haiku, JSON estrito com índices + motivo) quando há LLM e evidência; fallback léxico offline que só
  sinaliza; oferta de ação casada com o registro. `CLAIMS_POLICY=remove|flag|off` (padrão remove com LLM, flag sem).
  Corte que esvazia a resposta mantém a original sinalizada. Frase que copia a evidência (≥ 80% das palavras) e oferta
  que casa com ferramenta nem vão ao verificador. `ChatResponse` ganha `unsupported_claims` e `claims_action`.
- **Linha do eval com `context`** (`evals/context.py`): a evidência como texto (trechos, tool, dado ao vivo, trecho web,
  cartão), teto de 16 000 caracteres, cartão sempre incluído; checagem `claims` na linha. Linha antiga: fonte web
  entra com o trecho citado que veio na evidência. Por quê: 6 das 12 reprovações diziam "as fontes só têm título e
  URL".
- **Juiz com `failure_type`** e TPR/TNR por tipo contra `human_failure_type` (campo opcional da calibração).
- **`python -m evals.judge_diff A.json B.json --out docs/JUDGE_DIFF.md`**: antes/depois por caso e rodada.
- **`python -m evals.claims_proxy --repo <v4>`**: a réplica offline abaixo; rótulos em `evals/proxy/v4_judge_cited.json`
  (36 frases tiradas dos motivos do juiz), saída em `docs/kit/ensaio/g_claims_proxy_v4.json`.

## Medido (offline, sem API) — partes determinísticas sobre as 30 respostas oficiais da v4

Rótulos: 27 frases citadas pelo juiz como sem base (`catch`: clima/câmbio inventados, conselho genérico, PTAX) e 9
frases que são regra ou capacidade verdadeira (`keep`: confirmação + aprovação de operador, Pix no mesmo dia, reinício
remoto).

| medida | 1ª passada | final |
|---|---|---|
| frases `catch` apontadas por algum mecanismo determinístico | 27/27 | 27/27 |
| … pela checagem numérica (v5) | 11/27 | 11/27 |
| … pelo fallback léxico | 19/27 (15/15 das sem número) | 19/27 (15/15) |
| respostas reprovadas por conteúdo inventado com ≥ 1 frase apontada | — | 9/9 |
| frases `keep` apontadas **com** o cartão na evidência | 1/9 | 0/9 |
| frases `keep` apontadas **sem** o cartão | 6/9 | 5/9 |
| respostas aprovadas pelo juiz que a checagem de oferta cortaria (`remove`) | 2/18 | 0/18 |
| frases sinalizadas pelo léxico nas aprovadas (só flag, não corta) | 27/121 (10/18 respostas) | 24/114 (10/18) |
| frases não citadas sinalizadas pelo léxico nas reprovadas | 21 | 21 |

- Entre a 1ª passada e a final mudaram três regras, olhando estas mesmas 30 respostas: "I can't" deixou de contar
  como oferta (os 2 cortes errados), verbo genérico ("start a request") procura o objeto antes na frase, e frases de
  ausência ("they don't describe…", "aren't in the sources") deixaram de ser checadas. É ajuste **dentro da amostra**:
  o número final é otimista.
- O fallback léxico é fraco: das 64 frases que ele sinaliza, 19 (30%) são as que o juiz citou. Por isso ele nunca
  corta. Acerto alto nas citadas vem de quase toda frase em inglês sobre fonte em português ter pouca sobreposição.

## O que NÃO está provado

- O verificador LLM (caminho principal com chave) não rodou nenhuma vez contra a API: precisão, falso corte e custo
  real por turno são desconhecidos. Os testes usam dublê (`tests/fakes.py`).
- Nenhuma nova nota do juiz: grounded ≥ 90% e numbers ≥ 95% nos oficiais continuam por medir ao vivo (rodar o eval
  ao vivo, `python -m evals.judge` e `python -m evals.judge_diff` contra o `judge.json` da v4).
- O efeito do cartão no texto que o modelo escreve (citar `[policy:capabilities]`, não oferecer ação inexistente) não
  foi medido; só que, com o cartão como evidência, as 9 frases verdadeiras deixam de ser apontadas pelas checagens
  determinísticas.
