# Verificação (`scripts/check.py`, sem docker)

Commit `504f0ac`, 03/11/2026 14:28 UTC. Resultado: **VERMELHO**.

| etapa | resultado | s |
|---|---|---:|
| venv aponta para este repo | PASS | 0.0 |
| ruff | PASS | 0.1 |
| pytest | PASS | 22.1 |
| provas do README passam | PASS | 0.0 |
| eval gate | FAIL | 36.2 |
| README ⇔ evidência commitada | PASS | 0.6 |
| resultado commitado = código atual | PASS | 0.1 |
| títulos de commit sem marcador {{ }} | PASS | 0.0 |
| sem dado de exemplo no produto | PASS | 0.1 |
| README e SPEC sem marcador do modelo | FAIL | 0.0 |
