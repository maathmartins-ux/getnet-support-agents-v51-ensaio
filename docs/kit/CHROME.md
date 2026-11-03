# Operar a tentativa (e o ensaio) pelo Chrome

Tudo roda em sessões da NUVEM, abertas e acompanhadas pelo **Chrome**, numa **aba só**, em
**https://claude.ai/code**. O PC só mostra o Chrome. O eval ao vivo e o juiz rodam na nuvem (a chave
`APP_ANTHROPIC_API_KEY` do ambiente funciona desde 01/11/2026); o PowerShell (`scripts/pc_live.ps1`) é só o
plano B, se a chave falhar na nuvem no dia.

Por que Chrome e não o app de desktop: o Chrome já fica aberto (~430 MB); o app de desktop é outro navegador
inteiro rodando à parte, e havia 17 processos `claude` (1,5 GB) num PC com 7,9 GB e 0,8 GB livres.

---

## 1. Uma vez, antes de tudo (já feito em 31/10/2026, conferir)

| Item | Onde | Pronto quando |
|---|---|---|
| Rede do ambiente da nuvem em **Full** (ou o site da empresa em *Allowed domains*) | claude.ai/code → nome do ambiente → **Edit** → *Network access* | sonda: site com HTTP 200 |
| Limite mensal do crédito em **US$ 130** | tela de crédito (a do "Gasto este mês") | limite ≥ US$ 130 |
| Chave do app na nuvem | Variáveis de ambiente: `APP_ANTHROPIC_API_KEY=<chave>` | sonda: "chave do LLM do app" OK |
| Plano B: PC preparado para o eval ao vivo | PowerShell: `powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\kit\scripts\pc_live.ps1" -Preparar` | `PC PRONTO para o eval ao vivo.` (feito em 01/11/2026) |

## 2. No dia (vale para o ensaio e para a tentativa)

### T−10 min: limpar o PC
1. Feche o **app de desktop do Claude** inteiro (inclusive no ícone perto do relógio). No Gerenciador de
   Tarefas (Ctrl+Shift+Esc) não pode sobrar processo `claude`.
2. Feche abas e programas pesados. Deixe **uma aba do Chrome** em https://claude.ai/code.
3. Anote o valor da **tela de crédito** (para medir o custo depois).

### T−5 min: criar o repositório e as sessões
1. Em **github.com/new**: repositório **público e vazio** (sem README) com o nome do desafio
   (no ensaio: `ensaio-kit-v37`).
2. Em claude.ai/code, crie a **sessão principal (M)**:
   - repositório: o que você acabou de criar; branch `main`;
   - ambiente: o seu (rede Full);
   - modelo: **Opus**.
3. Crie as **sessões das frentes** no mesmo repositório, cada uma com o modelo **Sonnet**, e dê a cada uma um
   título com a letra (ex.: "Frente R"). Elas ficam paradas até o T+10.
   - Tentativa real (v4): H, R, K, T, Q, D (6 sessões); R e Q em **Opus**, o resto em Sonnet
     ([V4_PROMPT_M.md](V4_PROMPT_M.md)).
   - Ensaio reduzido: só **R** e **K** (2 sessões).

### T+0: começar
1. Na sessão **M**, cole o prompt da M já preenchido: v4 → [V4_PROMPT_M.md](V4_PROMPT_M.md) (só falta colar o
   enunciado); ensaio → [ENSAIO_PROMPT_M.md](ENSAIO_PROMPT_M.md). A hora do primeiro commit dela é o T+0.
2. Acompanhe pela **lista de sessões** na lateral da mesma aba: clique numa sessão para ver o que ela faz.
   Não abra uma aba por sessão (cada aba pesa de 100 a 300 MB).

### T+10: soltar as frentes
1. A M imprime, numerados, os prompts de cada frente.
2. Para cada frente: copie o bloco dela, abra a sessão daquela letra na lateral e cole. Você é quem dá a
   ordem (sessão criada por outra sessão recusou tarefa sensível no teste de 31/10/2026).
3. Se uma frente responder que "a ordem não veio do usuário", cole de novo, você mesmo.

### T+33: eval ao vivo (na nuvem; você não faz nada)
A sessão M roda o eval ao vivo e o juiz sozinha. Só se ela disser que a chave falhou (plano B):
1. A M manda, numa linha, o comando para o PowerShell:
   `powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\kit\scripts\pc_live.ps1" -Repo <url do repositório>`
2. Cole no PowerShell e deixe rodar (~10 min; teto de US$ 3). Fim esperado: `PRONTO: resultados em fork/live.`
3. Volte à sessão M e escreva: **live pronto**.

### T+59: parar
Nenhum commit depois. Anote o valor da tela de crédito de novo: a diferença é o custo da tentativa.

---

## 3. Ensaio reduzido pelo Chrome (antes da tentativa real)

Igual à seção 2, com estas diferenças:
- repositório `ensaio-kit-v37`;
- o prompt da sessão principal já vem PREENCHIDO em [ENSAIO_PROMPT_M.md](ENSAIO_PROMPT_M.md) (enunciado, régua V4 e
  site `https://www.bcb.gov.br/`): é só copiar o bloco e colar;
- só 2 frentes (R e K), em Sonnet;
- pare em **T+30**, depois do primeiro `check.py --docker` verde da M; a M roda um eval ao vivo barato
  (`--split official --repeat 1 --max-usd 0.3`) na nuvem, para testar o caminho inteiro.

Anote na tabela do PLAYBOOK §7: hora do pré-voo, da SPEC, do 1º push de R e de K, do 1º check verde, do
`PRONTO` do PC, e o custo (tela de crédito antes e depois).
