"""R12-G: o bloco ao vivo do docs/RESULTS.md abre com UMA tabela (uma linha por split, a taxa que define o split com
IC95 e n, as execuções sem falha e os casos que falharam), e as outras taxas de cada split ficam num bloco recolhido.
Antes eram 14+ seções com uma linha de taxas com IC95 cada, que escondiam o que importa."""
import json

from scripts import fill_readme


def _report(split: str, rows: list[dict], metrics: dict, status: str = "complete") -> dict:
    return {"split": split, "provider": "anthropic", "status": status, "spent_usd": 0.123456, "max_usd": 1.0,
            "live": True, "rows": rows, "metrics": {"ALL": {"cases": len(rows), "p50_ms": 9800.0, "p95_ms": 23500.0,
                                                            "cost_usd": 0.12, **metrics}}}


def test_live_block_is_one_table_with_the_defining_check_and_the_failures_counted(tmp_path):
    official = _report("official", [
        {"id": "official-01", "checks": {"facts": False, "intent": True}},
        {"id": "official-01", "checks": {"facts": False, "intent": True}},
        {"id": "official-02", "checks": {"facts": True, "intent": True}}],
        {"resolved_acc": 33.3, "intent_acc": 100.0, "ci": {"resolved_acc": {"lo": 6.1, "hi": 79.2, "n": 3}}})
    hitl = _report("hitl", [{"id": "hitl-01", "checks": {"human_in_turn": True, "intent": True}}],
                   {"human_in_turn_acc": 100.0, "intent_acc": 100.0}, status="aborted")
    real = _report("real", [{"id": "r-1", "checks": {"numbers": True}}], {"numbers_acc": 100.0})
    for r in (official, hitl, real):
        (tmp_path / f"live_{r['split']}.json").write_text(json.dumps(r), encoding="utf-8")
    block = fill_readme.live_block(tmp_path)
    assert block.startswith("**Como ler:**")
    table = block[block.index("| Split |"):block.index("<details>")].strip().splitlines()
    assert len(table) == 2 + 3  # cabeçalho, separador e uma linha por split
    assert table[2].startswith("| `official` |")  # os cenários do enunciado abrem a tabela
    assert "resolvidas **33.3%** [6.1–79.2] (n=3)" in table[2] and "| 1/3 |" in table[2]
    assert "`official-01` ×2" in table[2] and "9.8 s · 23.5 s" in table[2] and table[2].endswith("| 0.12 |")
    assert "| `hitl` (aborted) | humano no turno certo **100%** (n=1) | 1/1 | nenhum |" in block
    assert "| `real` | números com base **100%** (n=1) |" in block  # sem intenção nem humano: a 1ª que vale
    # o detalhe por split continua, recolhido, uma vez por split
    details = block[block.index("<details>"):]
    assert details.rstrip().endswith("</details>") and details.count("#### Split") == 3
    assert block.count("**Como ler:**") == 1 and block.count("| Split |") == 1


def test_many_failing_cases_are_cut_with_the_rest_counted():
    rows = [{"id": f"c-{i:02d}", "checks": {"intent": False}} for i in range(8)]
    line = fill_readme.live_row(_report("x", rows, {"intent_acc": 0.0}), "live_x.json")
    assert line.count("`c-") == fill_readme.FAILED_IDS_SHOWN and "+3" in line and "| 0/8 |" in line


def test_offline_metric_table_is_folded_and_what_gates_the_ci_stays_in_view():
    md = "**Como ler:** x\n\n**Resolvidas** y\n| Métrica | a | ALL |\n|---|---:|---:|\n| cases | 1 | 1 |\n\nGate z"
    out = fill_readme._fold_metric_table(md)
    assert "**Resolvidas** y\n\n<details>" in out  # linha vazia antes do HTML: o GitHub só abre o bloco assim
    assert out.index("<details>") < out.index("| Métrica |") < out.index("</details>") < out.index("Gate z")
    assert fill_readme._fold_metric_table("sem tabela") == "sem tabela"
