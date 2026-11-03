# Busca com embeddings (padrão do kit: denso + cross-encoder) = modelos embutidos no build: o container não baixa
# nada na subida e o primeiro request não paga download. Decida o buscador pelo eval (`make compare`).
#
# Camadas na ordem de mudança: lockfile e modelo (raros) → dados → código (a cada commit). O app NÃO entra
# na venv: vai como pasta no PYTHONPATH, então mudar código não recria a venv. Medido em 31/10/2026, mudança
# só no src/: híbrido 451 s → 101 s (venv recopiada) → segundos (esta versão; ver check.py).
# auto (padrão) = o extra que o buscador escolhido exige (scripts/fetch_models.py --extras): denso/híbrido/cross →
# hybrid (fastembed + modelos embutidos); bm25 → imagem enxuta. Forçar: --build-arg EXTRAS=hybrid ou EXTRAS=none.
ARG EXTRAS="auto"
# Base fixada por digest (lido em 31/10/2026): build reprodutível; o Dependabot (.github/dependabot.yml) propõe a troca.
# Vazio = o modelo da escolha medida (data/retriever.json), senão o padrão do app; preencher força outro modelo.
ARG EMBED_MODEL=""

# Estágio 1: só dependências exatas do lockfile (e o modelo, no híbrido), num venv isolado.
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS build
ARG EXTRAS
ARG EMBED_MODEL
COPY requirements.lock requirements-hybrid.lock /tmp/
# escolha medida (`run_evals --choose-retriever --apply`): o build baixa exatamente os modelos que ela usa;
# o curinga deixa o build passar quando o arquivo ainda não existe (kit antes do desafio): COPY com várias origens
# só exige que UMA exista
COPY scripts/fetch_models.py data/retriever.jso[n] /tmp/
# Sessão da NUVEM (proxy com certificado próprio): check.py passa o certificado como SEGREDO do build (não fica em
# nenhuma camada) e o proxy por build-arg. Fora da nuvem o segredo não existe e nada muda.
RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca REQUESTS_CA_BUNDLE=/run/secrets/proxy_ca; fi \
 && if [ "$EXTRAS" = "auto" ]; then EXTRAS="$(python /tmp/fetch_models.py --data /tmp --extras)"; fi \
 && if [ "$EXTRAS" = "none" ]; then EXTRAS=""; fi \
 && echo "imagem: extras=${EXTRAS:-nenhum}" \
 && python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements${EXTRAS:+-$EXTRAS}.lock \
 && mkdir -p /opt/models \
 && if [ "$EXTRAS" = "hybrid" ]; then \
      FASTEMBED_CACHE_PATH=/opt/models EMBED_MODEL="$EMBED_MODEL" \
        /opt/venv/bin/python /tmp/fetch_models.py --data /tmp --embed; \
    fi

# Estágio 2: runtime sem pytest/ruff, sem compilador, usuário não-root.
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
ARG EMBED_MODEL
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data \
    DB_PATH=/app/var/app.db \
    FASTEMBED_CACHE_PATH=/opt/models \
    HF_HUB_OFFLINE=1 \
    EMBED_MODEL=$EMBED_MODEL
WORKDIR /app
RUN useradd --uid 10001 --create-home appuser && mkdir -p /app/var && chown appuser /app/var
# modelo é do appuser (a lib grava índice do cache) e offline: o container não busca nada na internet
COPY --from=build --chown=10001:10001 /opt/models /opt/models
COPY --from=build /opt/venv /opt/venv
COPY data ./data
COPY src ./src
# Vetores do corpus prontos na imagem (ensaio v5.4: sem eles o 1º pedido no container vetorizava o corpus inteiro,
# 2–4 min de CPU com o e5-large). Reaproveita var/embeddings do build (o eval local já vetorizou; chave = modelo +
# texto) e calcula só o que falta; o curinga deixa o build passar sem a pasta. Imagem sem fastembed: nada a fazer.
COPY scripts/fetch_models.py var/embeddin[g]s /opt/vectors/
ENV EMBED_CACHE_DIR=/opt/vectors
RUN rm -f /opt/vectors/fetch_models.py \
 && if python -c "import fastembed" 2>/dev/null; then \
      python -c "from app.rag import get_retriever; r = get_retriever(); r.search('teste', 1); \
print('índice:', r.name, getattr(r, 'fallback', '') or 'sem fallback')"; \
    fi \
 && chown -R 10001:10001 /opt/vectors
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
