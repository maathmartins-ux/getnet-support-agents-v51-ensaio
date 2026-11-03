"""Oficial resolvido sem humano precisa de fato verificável; senão uma recusa educada conta como resolvida."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check  # noqa: E402


def _write(root, cases):
    (root / "evals").mkdir()
    (root / "evals" / "cases.jsonl").write_text("\n".join(json.dumps(c) for c in cases), encoding="utf-8")


def test_official_without_facts_fails_unless_it_expects_a_human(tmp_path):
    _write(tmp_path, [{"id": "o1", "split": "official", "expect": {"facts": ["48"]}},
                      {"id": "o2", "split": "official", "expect": {"handoff": True}},
                      {"id": "o3", "split": "official", "expect": {"intent": "general"}},
                      {"id": "m1", "split": "memory", "expect": {}}])
    _name, ok, _, detail = check.officials_have_facts(tmp_path)
    assert not ok and detail == "sem expect.facts: o3"


def test_offline_quote_engine_does_not_count_language():
    """Modo offline (motor `table`) cita a fonte em português sem tradução: o idioma do redator se mede com LLM."""
    from evals.run_evals import score

    case = {"expect": {"language": "en"}}
    quoted = {"engine": "table", "answer": "O Pix é um meio de pagamento criado pelo Banco Central do Brasil."}
    assert "language" not in score(case, quoted)
    assert score(case, {**quoted, "engine": "llm"})["language"] is False


def test_tomorrow_written_with_year_is_not_redacted():
    """"Wednesday, Nov 4, 2026" (amanhã) saía "Nov [unconfirmed value], 2026": dia e ano da data de amanhã contam."""
    import datetime as dt

    from app.grounding import is_calendar_day

    today = dt.date(2026, 11, 3)
    answer = "Tomorrow (Wednesday, Nov 4, 2026) in Porto Alegre"
    assert is_calendar_day("4", answer, today) and is_calendar_day("2026", answer, today)
    assert is_calendar_day("2026", "amanhã, 4 de novembro de 2026", today)
    assert not is_calendar_day("2026", "In 2026 we sold 4 units", today)
    assert not is_calendar_day("9", "Nov 9, 2026", today)


def test_number_inside_tool_identifier_supports_the_answer():
    from app.grounding import unsupported_numbers

    assert unsupported_numbers("Só aceita ontem, hoje ou os últimos 7 dias.", ['{"period": "last_7_days"}']) == []
    assert unsupported_numbers("Nos últimos 8 dias.", ['{"period": "last_7_days"}']) == ["8"]


def test_answer_opening_with_abstention_is_not_resolved():
    from evals.run_evals import opens_with_abstention, resolved

    hedge = "I couldn't confirm whether you need a bank account. Getnet offers Get Conta [sup-42]."
    direct = "Yes: you receive into Get Conta, a free digital account [sup-42]. I couldn't confirm other banks."
    got = {"answer": hedge, "sources": [{"id": "sup-42"}], "route": ["router", "faq"]}
    assert opens_with_abstention(hedge) and not resolved(got, [])
    assert not opens_with_abstention(direct) and resolved({**got, "answer": direct}, [])
    assert opens_with_abstention("Não consegui confirmar a previsão.")


def test_policy_citation_scrub_leaves_no_broken_sentence():
    from app.pipeline import _scrub_internal

    assert _scrub_internal("Esse tipo de decisão é de um atendente, conforme [policy:capabilities].", "pt") == \
        "Esse tipo de decisão é de um atendente."
    assert _scrub_internal("Pelo [policy:capabilities], uma proposta não confirmada expira em 15 minutos.", "pt") == \
        "Uma proposta não confirmada expira em 15 minutos."
    assert _scrub_internal("Total: R$ 10,00 [policy:capabilities].", "pt") == "Total: R$ 10,00."


def test_rerank_gate_decides_when_the_retriever_reranks(monkeypatch):
    """Com rerank e limiar calibrado, a nota do cross-encoder decide "tem fonte"; sem rerank, vale o portão antigo."""
    from types import SimpleNamespace

    from app import agents

    monkeypatch.setenv("COVERAGE_MIN_RERANK", "-5.0")
    hit = lambda r: SimpleNamespace(rerank=r, bm25=9.0, cosine=None)  # noqa: E731
    assert agents.covered_hits([hit(-7.0), hit(-6.0)]) == []  # BM25 alto não salva: o rerank recusa
    assert len(agents.covered_hits([hit(-4.0), hit(-9.0)])) == 2
    assert len(agents.covered_hits([hit(None)])) == 1  # sem nota de rerank: o BM25 decide


def test_enriched_label_sample_brings_suspected_failures_and_skips_labeled():
    from evals import label

    rows = [{"id": f"c{i}", "split": "s", "checks": {"facts": i % 5 != 0}} for i in range(40)]
    got = label.enriched_sample(rows, 10, suspects=6, exclude={"c0"}, suspect_ids={"c5", "c10", "c15", "c20", "c0"})
    ids = {r["id"] for r in got}
    assert len(got) == 10 and "c0" not in ids and {"c5", "c10", "c15", "c20"} <= ids


def test_replay_gate_fails_only_on_fresh_recordings_below_floor(tmp_path, monkeypatch):
    import json as _json
    import sys as _sys
    from pathlib import Path as _P

    _sys.path.insert(0, str(_P(__file__).resolve().parents[1] / "scripts"))
    import check as _check

    (tmp_path / "evals" / "cassettes").mkdir(parents=True)
    (tmp_path / "evals" / "cassettes" / "official.jsonl").write_text("{}", encoding="utf-8")
    (tmp_path / "var" / "replay").mkdir(parents=True)

    def fake_run(*a, **k):
        (tmp_path / "var" / "replay" / "replay.json").write_text(_json.dumps({"splits": {
            "official": {"misses": 0, "problems": ["intent_acc: replay 80 abaixo do piso 100"]},
            "memory": {"misses": 4, "problems": ["4 pedido(s) não gravado(s)"]}}}), encoding="utf-8")

    monkeypatch.setattr(_check.subprocess, "run", fake_run)
    _n, ok, _t, detail = _check.replay_gate(tmp_path)
    assert not ok and "official" in detail and "AVISO regravar: memory" in detail


def test_apply_min_rerank_writes_the_domain_threshold(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app import domain
    from evals import run_evals

    target = tmp_path / "challenge" / "__init__.py"
    target.parent.mkdir()
    target.write_text("MIN_SCORE = 0.5\nMIN_RERANK: float | None = None\n", encoding="utf-8")
    monkeypatch.setattr(domain, "active", lambda: SimpleNamespace(__file__=str(target)))
    monkeypatch.setattr(run_evals, "HERE", tmp_path / "evals")
    gate = {"min_rerank": -5.2, "pos_answered": 0.98, "neg_refused": 0.91, "positives": 59, "negatives": 22}
    assert run_evals.apply_min_rerank(gate) == 0
    text = target.read_text(encoding="utf-8")
    assert "MIN_RERANK = -5.2" in text and "recusa 91%" in text and text.count("MIN_RERANK =") == 1


def test_second_label_page_appends_new_answers(tmp_path):
    import json as _json

    from evals import label

    res = tmp_path / "results"
    res.mkdir()
    rows = [{"id": f"c{i}", "split": "official", "message": "q", "answer": "a", "run": 0} for i in range(4)]
    (res / "live_official.json").write_text(_json.dumps({"rows": rows}), encoding="utf-8")
    for marks in ({"c0": {"v": "pass"}, "c1": {"v": "pass"}}, {"c2": {"v": "fail"}, "c3": {"v": "pass"}}):
        dump = tmp_path / "dump.json"
        dump.write_text(_json.dumps([{"rater": "ana", "marks": marks}]), encoding="utf-8")
        label.import_page(dump, results=res, base=tmp_path)
    got = {r["id"]: r["humano"] for r in label.read_labels(tmp_path / "human_labels.ana.csv")}
    assert got == {"c0": "pass", "c1": "pass", "c2": "fail", "c3": "pass"}


def test_ingest_renders_only_the_javascript_shell_pages():
    """Página com texto no HTML estático não chama o navegador; casca vazia é renderizada e o texto entra."""
    import importlib.util as _u
    from pathlib import Path as _P

    script = _P(__file__).resolve().parents[1] / "scripts" / "ingest_render.py"
    spec = _u.spec_from_file_location("ingest_render", script)
    mod = _u.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rich = "<html><body><main><h1>Pix</h1><p>" + "Pix cai na hora para o lojista. " * 30 + "</p></main></body></html>"
    shell = "<html><body><div id='app'></div></body></html>"
    rendered = "<html><body><main><h1>Zap</h1><p>" + "Venda pelo WhatsApp com o link. " * 30 + "</p></main></body>"
    calls = []
    static = lambda url, hosts: rich if "pix" in url else shell  # noqa: E731
    fetch = mod.make_fetcher("auto", static=static, renderer=lambda url, hosts: calls.append(url) or rendered)
    assert fetch("https://site.x/pix/", ["site.x"]) == rich and calls == []
    assert "WhatsApp" in fetch("https://site.x/zap/", ["site.x"]) and calls == ["https://site.x/zap/"]
    assert mod.make_fetcher("never", static=static)("https://site.x/zap/", ["site.x"]) == shell


def test_render_thin_keeps_existing_ids_and_drops_lines_already_in_the_corpus(tmp_path):
    import importlib.util as _u
    import json as _json
    from pathlib import Path as _P

    script = _P(__file__).resolve().parents[1] / "scripts" / "ingest_render.py"
    spec = _u.spec_from_file_location("ingest_render2", script)
    mod = _u.module_from_spec(spec)
    spec.loader.exec_module(mod)
    old = {"ofertas": [{"id": "prod-ofertas-01", "text": "Get Clássica custa R$ 79,90 por mês no plano."}]}
    page = ("<html><body><main><h1>Ofertas</h1><p>Get Clássica custa R$ 79,90 por mês no plano.</p>"
            "<p>" + "A oferta vale por 12 meses a partir da contratação da maquininha. " * 8 + "</p></main></body>")
    out = mod.render_thin({"ofertas": "https://site.x/ofertas"}, tmp_path, ["site.x"], "prod",
                          corpus=old["ofertas"][0]["text"], existing=old, renderer=lambda url, hosts: page)
    ids = [r["id"] for r in out["ofertas"]]
    assert ids[0] == "prod-ofertas-01" and ids[1] == "prod-ofertas-02"
    assert all("79,90" not in r["text"] for r in out["ofertas"][1:])  # linha que já existia não se repete
    saved = [_json.loads(x) for x in (tmp_path / "ofertas.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in saved] == ids
