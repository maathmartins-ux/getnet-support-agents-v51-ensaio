# Verificação (`scripts/check.py`, docker + réplicas)

Commit `513bea9`, 04/11/2026 07:59 UTC. Resultado: **VERDE**.

| etapa | resultado | s |
|---|---|---:|
| venv aponta para este repo | PASS | 0.1 |
| ruff | PASS | 0.1 |
| buscador = o configurado (sem fallback) | PASS | 6.5 |
| pytest | PASS | 34.2 |
| provas do README passam | PASS | 0.0 |
| eval gate | PASS | 53.2 |
| README ⇔ evidência commitada | PASS | 0.8 |
| evidência do juiz coerente | PASS | 0.3 |
| resultado commitado = código atual | PASS | 0.1 |
| títulos de commit sem marcador {{ }} | PASS | 0.0 |
| sem dado de exemplo no produto | PASS | 0.1 |
| README e SPEC sem marcador do modelo | PASS | 0.0 |
| docs sem link para arquivo inexistente | PASS | 0.0 |
| cenários oficiais com fato verificável | PASS | 0.0 |
| replay das gravações ao vivo | PASS | 357.7 |
| docker build (hybrid) | PASS | 99.6 |
| imagem sem dev/extras | PASS | 1.8 |
| docker run | PASS | 0.3 |
| container /health com dados | PASS | 8.0 |
| eval via HTTP (oficiais) | PASS | 17.2 |
| mcp no container (401 sem token, initialize com JWT) | PASS | 0.3 |
| container sem rede (--network none) | PASS | 9.9 |
| réplicas (conversa, caso único, queda) | PASS | 30.7 |
