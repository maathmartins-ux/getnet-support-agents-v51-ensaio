"""Consultas do RAG escritas pelo router no idioma da base, sem perder a pergunta original."""
from app import agents, router


def test_schema_asks_for_search_queries_in_the_corpus_language():
    sch = router.schema()
    assert "search_queries" in sch["required"] and sch["properties"]["search_queries"]["type"] == "array"
    assert "idioma da base" in sch["properties"]["search_queries"]["description"]


def test_invented_ids_are_dropped_and_list_is_capped():
    hist = [{"role": "user", "content": "minha venda TX1007 foi recusada"}]
    out = router.check_search_queries(["motivo da recusa", "TX9999 status", "motivo da recusa", "a", "b", "c"],
                                      "por que?", hist)
    assert "TX9999 status" not in out and len(out) <= router.SEARCH_QUERIES_MAX
    assert out.count("motivo da recusa") == 1 and out[0] == "motivo da recusa"
    assert router.check_search_queries("não é lista", "x", []) == []


def test_retrieve_searches_customer_words_first_then_router_queries():
    seen = []

    class Fake:
        name, gate = "fake", None

        def search(self, query, k=3):
            seen.append(query)
            return []

    agents.retrieve("Do I need a bank account to receive via Pix?", retriever=Fake(), k=5,
                    queries=["Pix conta corrente poupança conta de pagamento", "  "])
    # a pergunta original vai primeiro: há caso oficial em que ela acha o fato em 1º e as consultas do LLM, não
    assert seen == ["Do I need a bank account to receive via Pix?", "Pix conta corrente poupança conta de pagamento"]
    seen.clear()
    agents.retrieve("e a taxa?", standalone="taxa do Pix", retriever=Fake(), k=5, queries=["taxa do Pix"])
    assert seen == ["taxa do Pix"]  # sem busca repetida quando o LLM já usou as mesmas palavras


def test_budget_warns_when_ceiling_below_estimate(capsys, monkeypatch):
    from evals import run_evals

    monkeypatch.setenv("LIVE_USD_PER_TURN", "0.025")
    assert run_evals.budget_estimate({"official": 30, "memory": 190}) == 5.5
    assert "AVISO" in run_evals.warn_budget({"official": 30, "memory": 190}, 4.0)
    assert run_evals.warn_budget({"official": 30}, 4.0) is None
    assert "Estimativa" in capsys.readouterr().err


def test_judge_wallet_is_one_balance_for_all_splits():
    from evals import run_evals

    w = run_evals.JudgeWallet(1.0)
    w.charge(0.7)
    assert abs(w.left() - 0.3) < 1e-9
    w.charge(0.5)
    assert w.left() == 0.0


def test_tomorrow_day_number_is_not_flagged():
    import datetime

    from app import clock, grounding

    t = clock.today() + datetime.timedelta(days=1)
    assert grounding.unsupported_numbers(f"No forecast found for tomorrow, {t.day} {t:%B}.", []) == []
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
             "novembro", "dezembro"]
    assert grounding.unsupported_numbers(f"Amanhã, {t.day} de {meses[t.month - 1]}.", []) == []
    assert grounding.unsupported_numbers(f"Chega em {t.day} dias.", []) == [str(t.day)]  # número solto segue tarja
    assert grounding.unsupported_numbers("The fee is 47% for you.", []) == ["47"]
