"""Medida offline das partes determinísticas (evals/claims_proxy.py) sobre linhas já julgadas de outro repositório."""
import json

from evals import claims_proxy

TOOLS = {"get_terminal_status": {"description": "Maquininhas do lojista: modelo, conexão, sinal.", "write": False},
         "restart_terminal": {"description": "Reinicia remotamente uma maquininha do lojista.", "write": True}}
EVIDENCE = ['{"ok": true, "data": {"terminals": [{"terminal_id": "T1988B", "signal": "sem_sinal"}]}}',
            "Dúvidas: com a máquina desligada, abra a tampa e insira o chip no SIM1."]


def test_proxy_counts_caught_kept_and_false_flags(tmp_path):
    results = tmp_path / "evals" / "results"
    results.mkdir(parents=True)
    rows = [{"id": "official-05", "split": "official", "run": 0, "message": "Minha máquina não conecta",
             "language_declared": "pt", "evidence": EVIDENCE,
             "answer": "Abra a tampa e insira o chip no SIM1. Coloque a máquina perto de uma janela, longe de metal. "
                       "Posso propor um reinício remoto da T1988B."},
            {"id": "official-01", "split": "official", "run": 0, "message": "Como insiro o chip?",
             "language_declared": "pt", "evidence": EVIDENCE,
             "answer": "Com a máquina desligada, abra a tampa e insira o chip no SIM1. Posso enviar outra máquina."}]
    (results / "live_official.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    (results / "judge.json").write_text(json.dumps({"verdicts": [
        {"id": "official-05", "source": "live_official.json", "grounded": False},
        {"id": "official-01", "source": "live_official.json", "grounded": True}]}), encoding="utf-8")
    labels = {"tools": TOOLS, "cited": [
        {"id": "official-05", "run": 0, "sentence": "perto de uma janela", "expect": "catch",
         "type": "unsupported_claim"},
        {"id": "official-05", "run": 0, "sentence": "reinício remoto", "expect": "keep",
         "type": "offered_unavailable_action"}]}
    s = claims_proxy.analyse(tmp_path, labels)["summary"]
    assert s["cited_catch"] == 1 and s["caught_by_lexical"] == 1 and s["caught_any_deterministic"] == 1
    assert s["cited_keep"] == 1 and s["keep_flagged_with_card"] == 0
    assert s["judge_accepted"] == 1 and s["accepted_answers_cut_by_offer_check"] == 1  # "enviar outra máquina"
