"""Configuração lida do ambiente a cada chamada (testes trocam variáveis sem reimportar)."""
from __future__ import annotations

import json
import os
import secrets
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# USD por 1M de tokens (entrada, saída). Fonte: tabela de preços da Anthropic, consultada em
# 30/10/2026 (cache de 06/10/2026). Confira antes de publicar números de custo; modelo fora da
# tabela é contado com custo 0 e aparece como "unpriced" nas métricas.
PRICES_PER_MTOK = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}

# Papel → (modelo, effort). Cada um troca por env: ROUTER_MODEL, ROUTER_EFFORT, SUPERVISOR_MODEL...
# Effort é declarado sempre (output_config.effort): os padrões mudam entre modelos.
# - router/guardrail: classificação curta com JSON schema → Haiku, low.
# - supervisor: só escolhe o próximo especialista → Sonnet, low (em medium, o p95 ao vivo vinha dele).
# - agent: redige com fonte e usa tools → Sonnet, medium.
# - judge: deve ser pelo menos tão capaz quanto o julgado → Opus, medium.
ROLES = {
    "router": ("claude-haiku-5-5", "low"),
    "guardrail": ("claude-haiku-5-5", "low"),
    "supervisor": ("claude-sonnet-5-5", "low"),
    "agent": ("claude-sonnet-5-5", "medium"),
    "judge": ("claude-opus-5-5", "medium"),
    # reranker: só reordena 20 trechos por relevância → Haiku, low. Medido num corpus real (884 trechos,
    # 45 perguntas): o BM25 acha a fonte no top-20 em 90,4% e no top-3 em 70,8%; o gargalo é a ordem.
    "reranker": ("claude-haiku-5-5", "low"),
    # claims: confere frase a frase contra a evidência (JSON com os índices sem base) → Haiku, low (app/claims.py).
    "claims": ("claude-haiku-5-5", "low"),
}


# Papéis que rodam sem pensamento estendido (ROLE_THINKING=off|adaptive troca por env, ex.: CLAIMS_THINKING=adaptive).
THINKING_OFF: set[str] = set()


def thinking_for(role: str) -> str:
    raw = os.getenv(f"{role.upper()}_THINKING", "").strip().lower()
    if raw in ("off", "adaptive"):
        return raw
    return "off" if role in THINKING_OFF else "adaptive"


def thinking_param(model: str, mode: str, effort: str | None) -> dict | None:
    """Parâmetro `thinking` da API para desligar o pensamento, ou None (padrão do modelo: adaptativo).

    Regras da API (skill claude-api): Haiku 5.5 aceita {"type": "disabled"} com effort até high; Sonnet 5.5 recusa
    "disabled" e desliga com {"type": "between_tools"}, também só até high; Opus 5.5 não desliga (400 em qualquer
    effort). Fora dessas combinações devolve None e o modelo segue no padrão: nunca um pedido que dá 400.
    """
    if mode != "off" or effort in ("xhigh", "max"):
        return None
    if model.startswith("claude-haiku-5-5"):
        return {"type": "disabled"}
    if model.startswith("claude-sonnet-5-5"):
        return {"type": "between_tools"}
    return None


def model_for(role: str) -> str:
    return os.getenv(f"{role.upper()}_MODEL") or ROLES[role][0]


def effort_for(role: str) -> str:
    return os.getenv(f"{role.upper()}_EFFORT") or ROLES[role][1]


def data_dir() -> Path:
    # Caminho explícito: no container o pacote não mora ao lado de data/, e um índice vazio
    # passaria despercebido até o smoke test.
    return Path(os.getenv("DATA_DIR", ROOT / "data"))


def db_path() -> Path:
    return Path(os.getenv("DB_PATH", ROOT / "var" / "app.db"))


def database_url() -> str:
    # postgresql://... = Postgres (réplicas em vários hosts; docs/adr/0003-postgres-opcional.md). Qualquer outro valor,
    # ou ausente, mantém o SQLite em DB_PATH: o padrão não pede serviço externo.
    url = os.getenv("DATABASE_URL", "").strip()
    return url if url.startswith(("postgresql://", "postgres://")) else ""


def llm_provider() -> str:
    # "offline" é determinístico e roda no CI sem chave; o modo com LLM nunca é pré-requisito.
    return os.getenv("LLM_PROVIDER", "offline")


def auth_mode() -> str:
    # required: identidade só do Bearer token assinado (padrão seguro).
    # demo: aceita user_id do corpo (payload literal de enunciado) e marca identity_verified=false.
    # Ver docs/adr/0001-auth-mode-demo.md.
    mode = os.getenv("AUTH_MODE", "required").lower()
    return mode if mode in ("demo", "required") else "required"


def _local_secret(name: str) -> str:
    """Segredo aleatório gerado uma vez e guardado ao lado do banco (var/, fora do git, arquivo 0600).

    Sem `.env`, não existe segredo conhecido para forjar token: o servidor e a CLI do mesmo diretório leem o mesmo
    arquivo. O token de operador gerado sai uma vez no log, para o primeiro acesso ao painel.
    """
    path = db_path().parent / "local_secrets.json"
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        found = {}
    if not found.get(name):
        found[name] = secrets.token_urlsafe(48)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(found), encoding="utf-8")
            path.chmod(0o600)
        except OSError:
            pass  # diretório só de leitura: vale para este processo
        if name == "OPERATOR_TOKEN":
            # o valor nunca vai para o log: quem opera lê o arquivo (0600) no próprio host/volume
            print(f"OPERATOR_TOKEN não definido: gerado e guardado em {path} (leia o arquivo; o valor não é "
                  "impresso)", file=sys.stderr)
    return found[name]


def auth_secret() -> str:
    return os.getenv("AUTH_SECRET") or _local_secret("AUTH_SECRET")


def operator_token() -> str:
    return os.getenv("OPERATOR_TOKEN") or _local_secret("OPERATOR_TOKEN")


def operator_keys() -> dict[str, str]:
    # "ana:<sha256>,bruno:<sha256>" — só o hash fica na configuração (python -m app.auth operator-key ana).
    pairs = (p.split(":", 1) for p in os.getenv("OPERATOR_KEYS", "").split(",") if ":" in p)
    return {name.strip(): digest.strip() for name, digest in pairs if name.strip() and digest.strip()}


def token_ttl_min() -> int:
    # 60 min: sessão de atendimento típica; o cliente renova. Revogação antecipada via POST /auth/revoke.
    return int(os.getenv("TOKEN_TTL_MIN", "60"))


def auth_issuer() -> str:
    return os.getenv("AUTH_ISSUER", "app")


def auth_audience() -> str:
    return os.getenv("AUTH_AUDIENCE", "app-api")


def action_ttl_min() -> int:
    # Ação de escrita pendente expira: confirmar uma proposta velha executaria algo fora de contexto.
    return int(os.getenv("ACTION_TTL_MIN", "15"))


def sla_minutes(priority: str) -> int:
    # Alvo de resposta humana por prioridade; caso vencido é re-escalonado uma vez (store.escalate_overdue).
    return int(os.getenv("SLA_HIGH_MIN", "120") if priority == "high" else os.getenv("SLA_NORMAL_MIN", "480"))


def credentials_file() -> Path:
    # Hashes de senha dos usuários de teste (python -m app.auth seed-passwords). Só hash; a senha nunca é gravada.
    # Ao lado do banco (var/, fora do git; na imagem, o volume gravável /app/var): cada ambiente semeia as suas.
    return Path(os.getenv("CREDENTIALS_FILE") or (db_path().parent / "credentials.json"))


def candidates_file() -> Path:
    # 👎 vira candidato a caso de teste ANTES de revisão humana: fica ao lado do banco (var/, fora do git; na imagem o
    # volume gravável). Só `python -m evals.candidates --accept` leva um candidato revisado para evals/cases.d/.
    return Path(os.getenv("CANDIDATES_FILE") or (db_path().parent / "candidates.jsonl"))


def login_rate_per_min() -> int:
    # 5 tentativas/min por IP+usuário: senha certa entra de primeira; força bruta para em 5.
    return int(os.getenv("LOGIN_RATE_PER_MIN", "5"))


def rate_limit_per_min() -> int:
    # 30/min por chave: folgado para conversa humana, corta script em loop.
    return int(os.getenv("RATE_LIMIT_PER_MIN", "30"))


# Buscador padrão do kit (decidido com a máquina parada, não com a CPU cheia): denso
# multilingual-e5-large + cross-encoder bge-reranker-v2-m3-int8 sobre o top-10 do denso, lendo 600 caracteres por
# trecho. Medido num corpus de pagamentos (50 perguntas com gold por fato, máquina SEM outra carga): Recall@3 0,93 /
# MRR 0,94 contra 0,93 / 0,927 do denso sozinho, p95 por busca 1,1–1,25 s (`measured["dense+cross"]` p95 1251 ms).
# Com 8 processos disputando a mesma CPU, o mesmo rerank mediu p95 2,9–3,5 s; por isso latência só
# se mede com a máquina parada. Vale quando NADA escolheu o buscador: data/retriever.json (`--choose-retriever
# --apply`) ou RETRIEVER no ambiente trocam o pacote inteiro (escolha sem `rerank` = sem rerank; RERANK=cross liga).
# Escolha POR MEDIDA (medir no caminho do agente, top-5 do redator, e só então escolher). Gold real (38 perguntas),
# caminho do agente (palavras do cliente + plano, rerank): dense+cross Recall@3 0,895 / Recall@5 0,947 / MRR@3 0,820;
# hybrid+cross (com o BM25 só no idioma do corpus, rag.lexical_fits) 0,895 / 0,921 / 0,830. Empate técnico;
# dense+cross fica porque foi o validado ao vivo (2 baterias integrais: oficiais 96,7%), e o híbrido sem o filtro de
# idioma tirou a fonte de uma pergunta em inglês nas 3 rodadas. RETRIEVER=hybrid troca.
KIT_RETRIEVER = {
    "retriever": "dense",
    "embed_model": "intfloat/multilingual-e5-large",
    "rerank": "cross",
    "rerank_model": "BAAI/bge-reranker-v2-m3-int8",
    "rerank_pool": 10,
    "rerank_chars": 600,
}


def retriever_choice() -> dict:
    # data/retriever.json: escolha MEDIDA por `run_evals --choose-retriever --apply` (retriever, modelos, rerank e
    # os números que a justificam). Ausente ou ilegível = padrões do kit (KIT_RETRIEVER). Env sempre vence o arquivo.
    path = data_dir() / "retriever.json"
    try:
        return dict(_choice_for(str(path), path.stat().st_mtime))  # cópia: quem chama não altera o cache
    except OSError:
        return {}


@lru_cache(maxsize=4)
def _choice_for(path: str, mtime: float) -> dict:
    import json

    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw.get("choice", {}) if isinstance(raw, dict) else {}


def _bundle() -> dict:
    """Pacote que vale para o que o ambiente não disse: a escolha do arquivo, senão o padrão do kit.

    RETRIEVER no ambiente sem arquivo = escolha explícita sem rerank (o padrão do kit não se mistura com ela): os
    modelos seguem os padrões do kit, mas o rerank só liga com RERANK=cross|llm.
    """
    choice = retriever_choice()
    if choice.get("retriever"):
        return choice
    if os.getenv("RETRIEVER"):
        return {k: v for k, v in KIT_RETRIEVER.items() if k not in ("retriever", "rerank")}
    return dict(KIT_RETRIEVER)


def retriever_name() -> str:
    # bm25 (sem dependência) | hybrid (BM25 + embeddings, RRF) | dense (só embeddings; BM25 só no portão).
    # Sem fastembed ou sem o modelo, rag.get_retriever cai no bm25 e grava o motivo em `fallback`.
    name = (os.getenv("RETRIEVER") or _bundle().get("retriever") or "bm25").lower()
    return name if name in ("bm25", "hybrid", "dense") else "bm25"


def rerank_mode() -> str:
    # RERANK=cross|llm|off|auto. auto (padrão) = o rerank da escolha (data/retriever.json, senão o do KIT_RETRIEVER).
    # O rerank por LLM só liga pedido (RERANK=llm): num corpus real ele não mudou o Recall@3 e custava latência.
    mode = os.getenv("RERANK", "auto").lower()
    if mode == "auto":
        mode = str(_bundle().get("rerank") or "off").lower()
    return mode if mode in ("cross", "llm") else "off"


def rerank_enabled() -> bool:
    return rerank_mode() != "off"


def rerank_model() -> str:
    # Cross-encoder multilíngue (pt/en) suportado pelo fastembed; troca por env ou pela escolha medida.
    return os.getenv("RERANK_MODEL") or _bundle().get("rerank_model") or KIT_RETRIEVER["rerank_model"]


def rerank_pool() -> int:
    # Quantos trechos do base o cross-encoder reordena: o custo cresce linear com isso (um par por trecho).
    return int(os.getenv("RERANK_POOL") or _bundle().get("rerank_pool") or KIT_RETRIEVER["rerank_pool"])


def rerank_chars() -> int:
    # Caracteres de cada trecho que o cross-encoder lê. Medido (bge-m3-int8, CPU): 600 caracteres custaram
    # ~1/5 do tempo por par de 1500 e, com pool 20, deram Recall@3 maior (0,777 × 0,764): o fato costuma estar no começo
    # do trecho (o ingest abre cada um com a pergunta da FAQ ou o título da seção).
    return int(os.getenv("RERANK_CHARS") or _bundle().get("rerank_chars") or KIT_RETRIEVER["rerank_chars"])


def embed_model() -> str:
    # Multilíngue (pt/en), suportado pelo fastembed. Troque por env ou pela escolha medida.
    return os.getenv("EMBED_MODEL") or _bundle().get("embed_model") or KIT_RETRIEVER["embed_model"]


def embed_cache_dir() -> Path:
    # Vetores dos trechos por modelo + hash do corpus (rag.doc_vectors): a 2ª subida não recalcula o corpus.
    # Num `git worktree`, o padrão é o var/embeddings do repositório PRINCIPAL: a chave é modelo +
    # texto, então quem monta o corpus o vetoriza uma vez e o check da sessão principal, depois do merge, já o encontra
    # (sem isso, cada worktree vetorizava de novo: 2–4 min de CPU com o e5-large).
    value = os.getenv("EMBED_CACHE_DIR")
    return Path(value) if value else _main_root(ROOT) / "var" / "embeddings"


def _main_root(root: Path) -> Path:
    """Raiz do repositório principal quando `root` é um worktree (`.git` é um arquivo com
    "gitdir: <main>/.git/worktrees/x"); senão o próprio `root` (repositório normal, container sem .git)."""
    marker = root / ".git"
    try:
        if marker.is_file():
            line = marker.read_text(encoding="utf-8").strip()
            if line.startswith("gitdir:"):
                gitdir = Path(line.split(":", 1)[1].strip())
                gitdir = gitdir if gitdir.is_absolute() else (root / gitdir).resolve()
                if gitdir.parent.name == "worktrees":
                    return gitdir.parent.parent.parent
    except OSError:
        pass
    return root


def supervisor_replan() -> bool:
    # Ablação (eval --ablate-replan): "off" = só o plano inicial do router, sem desvio. Mede quanto o replanejamento
    # vale no eval (mesmos casos com e sem). Produção: sempre "on".
    return os.getenv("SUPERVISOR_REPLAN", "on").lower() != "off"


def supervisor_fast() -> bool:
    # Atalho de 1 passo (sem o supervisor LLM): DESLIGADO por padrão. Com o atalho, uma regra escolhe o próximo passo
    # e o trace só mostra "atalho"; com o supervisor LLM em todo turno a decisão e o motivo ficam visíveis.
    # Custo: ~2 chamadas e ~4 s a mais por turno de 1 passo (medido). SUPERVISOR_FAST=on liga.
    return os.getenv("SUPERVISOR_FAST", "off").lower() == "on"


def supervisor_fast_min_confidence() -> float:
    # Confiança mínima do router para pular o supervisor LLM; abaixo dela o modelo ainda lê o status e replaneja.
    try:
        return float(os.getenv("SUPERVISOR_FAST_MIN_CONFIDENCE", "0.8"))
    except ValueError:
        return 0.8


def supervisor_parallel() -> bool:
    # Agentes independentes do mesmo passo rodam em threads; "false" serializa (depuração).
    return os.getenv("SUPERVISOR_PARALLEL", "true").lower() != "false"


def coverage_min_score(default: float) -> float:
    # Limiar do portão "sem fonte, sem afirmação". Escolha por medida: run_evals --calibrate-gate.
    value = os.getenv("COVERAGE_MIN_SCORE")
    return float(value) if value else default


def coverage_min_rerank(default: float | None) -> float | None:
    # Portão pela nota do cross-encoder (quando o buscador tem rerank): a pergunta tem fonte se a melhor nota do top-5
    # passa do limiar. Calibrado por `retrieval_eval` (rerank_gate); None = desligado (vale o portão BM25/cosseno).
    value = os.getenv("COVERAGE_MIN_RERANK")
    return float(value) if value else default


def coverage_min_cosine(default: float) -> float:
    # Piso de cosseno do portão no denso/híbrido. Muda de escala com o modelo (e5 põe quase tudo em 0,75–0,90):
    # sai calibrado pelo --choose-retriever junto com o retriever escolhido.
    value = os.getenv("COVERAGE_MIN_COSINE")
    return float(value) if value else default


def choice_gate() -> dict:
    # Limiares do portão calibrados para a escolha medida; só valem se o ambiente não trocou retriever, modelo ou
    # rerank (limiar de um retriever aplicado a outro deixaria passar pergunta sem fonte).
    c = retriever_choice()
    same = (retriever_name() == c.get("retriever") and rerank_mode() == (c.get("rerank") or "off")
            and (not c.get("embed_model") or embed_model() == c.get("embed_model"))
            and (not c.get("rerank_model") or rerank_model() == c.get("rerank_model")))
    gate = c.get("gate") if same else None
    return gate if isinstance(gate, dict) else {}


def otel_exporter() -> str | None:
    # console | otlp (extra [otel]). Ausente = só log JSON + /metrics.
    value = os.getenv("OTEL_EXPORTER", "").lower()
    return value if value in ("console", "otlp") else None


# --- credencial e endereço do LLM do APP (não do Claude Code) ---------------------------------------------------
# Sessão da nuvem: o Claude Code reserva ANTHROPIC_API_KEY para si (a variável criada no
# ambiente não chegava aos programas) e exporta ANTHROPIC_BASE_URL apontando para a conexão interna dele, que o SDK
# leria sozinho. O app usa APP_ANTHROPIC_API_KEY (ou ANTHROPIC_API_KEY fora da nuvem) e, na nuvem, a API pública.
PUBLIC_API = "https://api.anthropic.com"


def llm_api_key() -> str | None:
    # espaço, aspas ou quebra de linha coladas junto com a chave na tela de variáveis viram 401 na API
    raw = os.getenv("APP_ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or ""
    return raw.strip().strip("\"'").strip() or None


def llm_base_url() -> str:
    explicit = os.getenv("APP_ANTHROPIC_BASE_URL")
    if explicit:
        return explicit
    if os.getenv("CLAUDE_CODE_REMOTE") == "true":  # o ANTHROPIC_BASE_URL da sessão é do Claude Code, não do app
        return PUBLIC_API
    return os.getenv("ANTHROPIC_BASE_URL") or PUBLIC_API



def llm_first_timeout_s(web: bool = False) -> float:
    """Prazo da 1ª tentativa de cada chamada ao LLM (app/llm.py, `_hedged`); 0 desliga. Com busca web, o dobro."""
    base = float(os.getenv("LLM_FIRST_TIMEOUT_S", "15"))
    return base * 2 if web else base


def coverage_gate() -> str:
    """Quem decide se há fonte: "bm25" (padrão: limiar do domínio sobre o BM25, qualquer que seja o buscador que
    ordena) ou "retriever" (limiares calibrados para o buscador escolhido em data/retriever.json)."""
    return os.getenv("COVERAGE_GATE", "bm25").lower()


def faq_top_k() -> int:
    # Passagens que o redator do faq recebe depois da fusão das buscas (FAQ_TOP_K). 5 em vez de 3: medido, o trecho com
    # o fato (preço das duas maquininhas) estava no corpus e fora do top-3.
    try:
        return max(1, int(os.getenv("FAQ_TOP_K", "5")))
    except ValueError:
        return 5


def faq_max_searches() -> int:
    # Teto de buscas por turno no faq (FAQ_MAX_SEARCHES): as do plano determinístico + as que o LLM pede pela tool.
    try:
        return max(1, int(os.getenv("FAQ_MAX_SEARCHES", "3")))
    except ValueError:
        return 3


def corpus_language_setting() -> str:
    # Idioma em que o faq escreve as consultas (CORPUS_LANGUAGE=pt|en); "auto" (padrão) = o da maioria dos trechos.
    value = os.getenv("CORPUS_LANGUAGE", "auto").strip().lower()
    return value if value in ("pt", "en") else "auto"
