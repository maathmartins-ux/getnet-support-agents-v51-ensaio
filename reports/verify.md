# Verificação (`scripts/check.py`, docker + réplicas)

Commit `ccde68e`, 04/11/2026 03:24 UTC. Resultado: **VERDE**.

| etapa | resultado | s |
|---|---|---:|
| venv aponta para este repo | PASS | 0.0 |
| ruff | PASS | 0.0 |
| buscador = o configurado (sem fallback) | PASS | 5.8 |
| pytest | PASS | 25.2 |
| provas do README passam | PASS | 0.0 |
| eval gate | PASS | 28.1 |
| README ⇔ evidência commitada | PASS | 0.5 |
| resultado commitado = código atual | PASS | 0.1 |
| títulos de commit sem marcador {{ }} | PASS | 0.0 |
| sem dado de exemplo no produto | PASS | 0.1 |
| README e SPEC sem marcador do modelo | PASS | 0.0 |
| docs sem link para arquivo inexistente | PASS | 0.0 |
| cenários oficiais com fato verificável | PASS | 0.0 |
| replay das gravações ao vivo | PASS | 516.5 |
| docker build (hybrid) | PASS | 15.4 |
| imagem sem dev/extras | PASS | 0.7 |
| docker run | PASS | 0.2 |
| container /health com dados | PASS | 7.0 |
| eval via HTTP (oficiais) | PASS | 26.6 |
| mcp no container (401 sem token, initialize com JWT) | PASS | 0.1 |
| container sem rede (--network none) | PASS | 8.0 |
| réplicas (conversa, caso único, queda) | PASS | 32.5 |
