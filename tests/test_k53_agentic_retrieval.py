"""K53: busca agentic do faq.

Mandada crua ao denso, "What's the difference between X and Y?" deixa o trecho com o fato fora do top-3 e o faq
responde NOT_IN_SOURCES. Por isso: consultas no idioma do corpus, uma por item comparado, a partir de
ctx.facts["standalone"], até 3 buscas por turno, fundidas por rodada; top-5 ao redator; com LLM, tool `search` com teto.
"""
import json

import pytest
from fakes import fake_llm, resp, text, tool_use

from app import agents, rag
from app.agents import Context

DOCS = [
    {"id": "alfa-preco", "title": "Plano Alfa", "url": "https://example.com/alfa",
     "text": "O Plano Alfa custa R$ 10 por mês e inclui entrega grátis para capitais."},
    {"id": "beta-preco", "title": "Plano Beta", "url": "https://example.com/beta",
     "text": "O Plano Beta custa R$ 20 por mês e inclui atendimento prioritário."},
    {"id": "conta", "title": "Como receber", "url": "https://example.com/receber",
     "text": "Para receber os pagamentos você precisa de uma conta corrente, poupança ou conta de pagamento."},
    {"id": "geral", "title": "Planos", "url": "https://example.com/planos",
     "text": "Conheça os planos da loja e escolha o melhor para o seu negócio."},
    {"id": "troca", "title": "Troca", "url": "https://example.com/troca",
     "text": "A troca do produto pode ser pedida em até 7 dias após o recebimento."},
]
GLOSSARY = {"_doc": "teste", "conta corrente": ["bank account", "checking account"], "receber": ["receive"],
            "pagamentos": ["payments"], "troca": ["exchange"]}


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    (tmp_path / "kb.jsonl").write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in DOCS), encoding="utf-8")
    (tmp_path / "glossary.json").write_text(json.dumps(GLOSSARY, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def ctx(message, language="pt", **facts):
    return Context(text=message, language=language, user_id="u1", conversation_id="c1", intent="faq", facts=facts)


class SpyRetriever:
    """BM25 de verdade, guardando cada consulta que chega à busca."""

    name = "bm25"

    def __init__(self):
        self.base, self.queries = rag.BM25Retriever(rag.get_index()), []

    def search(self, query, k=3):
        self.queries.append((query, k))
        return self.base.search(query, k)


# --- comparação: uma consulta por item -------------------------------------------------------------------------------
@pytest.mark.parametrize("message", [
    "What's the difference between the Plano Alfa and the Plano Beta?",
    "Qual a diferença entre o Plano Alfa e o Plano Beta?",
    "Plano Alfa ou Plano Beta?",
    "Plano Alfa vs Plano Beta",
])
def test_comparison_question_gets_one_query_per_entity(corpus, message):
    plan = agents.plan_queries(message, corpus_lang="pt")
    assert plan.entities == ["Plano Alfa", "Plano Beta"]
    assert len(plan.queries) == 2 and plan.queries[0].startswith("Plano Alfa") and plan.queries[1].startswith(
        "Plano Beta")


def test_list_of_three_is_capped_by_the_search_budget(corpus):
    plan = agents.plan_queries("Quanto custam o Plano Alfa, o Plano Beta, o Plano Gama e o Plano Delta?",
                               corpus_lang="pt", max_searches=3)
    assert plan.entities == ["Plano Alfa", "Plano Beta", "Plano Gama"] and len(plan.queries) == 3
    assert all("custam" in q for q in plan.queries)  # o que se quer saber vai junto de cada item


def test_single_question_or_name_without_link_is_not_split(corpus):
    assert agents.plan_queries("Posso usar o Plano Alfa com entrega grátis?", corpus_lang="pt").entities == []
    assert agents.plan_queries("Qual o prazo de entrega?", corpus_lang="pt").queries == ["Qual o prazo de entrega?"]
    # nome solto fora da ligação fica no assunto, não vira item
    plan = agents.plan_queries("Plano Alfa or Plano Beta: which is cheaper for Pix?", corpus_lang="pt")
    assert plan.entities == ["Plano Alfa", "Plano Beta"] and all(q.endswith("Pix") for q in plan.queries)


def test_comparison_runs_one_search_per_entity_and_merges_round_robin(corpus):
    spy = SpyRetriever()
    found = agents.retrieve("What's the difference between the Plano Alfa and the Plano Beta?", retriever=spy)
    assert [q for q, _ in spy.queries] == [agents.expand_query("Plano Alfa"), agents.expand_query("Plano Beta")]
    assert [h.doc.id for h in found.hits][:2] == ["alfa-preco", "beta-preco"]  # cada item leva o seu melhor trecho
    assert len({h.doc.id for h in found.hits}) == len(found.hits)  # sem repetir trecho


# --- idioma do corpus ------------------------------------------------------------------------------------------------
def test_english_question_is_searched_in_the_corpus_language(corpus):
    plan = agents.plan_queries("Do I need a bank account to receive my payments?")
    assert plan.language == "pt"  # detectado pelos trechos do índice
    assert plan.queries == ["Do I need a conta corrente to receber my pagamentos?"] and plan.translated == [True]
    spy = SpyRetriever()
    found = agents.retrieve("Do I need a bank account to receive my payments?", retriever=spy)
    # as palavras do cliente vão cruas como 1ª busca; a tradução do plano vem logo depois
    assert spy.queries[0][0] == "Do I need a bank account to receive my payments?"
    assert spy.queries[1][0] == plan.queries[0]
    assert "conta" in [h.doc.id for h in found.hits]


def test_corpus_language_comes_from_config_when_set(corpus, monkeypatch):
    monkeypatch.setenv("CORPUS_LANGUAGE", "en")
    plan = agents.plan_queries("Quero receber os pagamentos na conta corrente")
    assert plan.language == "en" and plan.queries == ["Quero receive os payments na bank account"]


def test_same_language_question_keeps_the_glossary_expansion(corpus):
    plan = agents.plan_queries("Como receber os pagamentos?")
    assert plan.translated == [False]
    spy = SpyRetriever()
    agents.retrieve("Como receber os pagamentos?", retriever=spy)
    assert spy.queries[0][0] == agents.expand_query("Como receber os pagamentos?")  # mesma consulta de antes


def test_glossary_with_text_values_is_read(corpus):
    # glossário com texto em vez de lista nos valores não pode ser ignorado inteiro
    (corpus / "glossary.json").write_text(json.dumps({"conta corrente": "bank account"}), encoding="utf-8")
    assert agents.to_language("I have a bank account", "pt") == "I have a conta corrente"


# --- pergunta autônoma do router (contrato R53 → K53) ---------------------------------------------------------------
def test_standalone_from_the_router_is_the_base_of_the_search(corpus):
    spy = SpyRetriever()
    found = agents.retrieve("e a outra?", standalone="Quanto custa o Plano Beta?", retriever=spy)
    assert spy.queries[0][0] == agents.expand_query("Quanto custa o Plano Beta?")
    assert found.hits[0].doc.id == "beta-preco"


def test_faq_agent_uses_standalone_from_ctx_facts(corpus, monkeypatch):
    monkeypatch.setattr(agents, "get_retriever", lambda: SpyRetriever())
    r = agents.faq_agent(ctx("e a outra?", standalone="Quanto custa o Plano Beta?"))
    assert r.status == "ok" and r.sources[0].id == "beta-preco"
    assert r.facts["faq_queries"] == ["Quanto custa o Plano Beta?"]


def test_empty_standalone_falls_back_to_the_message(corpus):
    plan = agents.plan_queries("Quanto custa o Plano Alfa?", standalone="")
    assert plan.queries == ["Quanto custa o Plano Alfa?"]


# --- fusão e top-k ---------------------------------------------------------------------------------------------------
def _hit(i):
    return rag.Hit(rag.Doc(i, i, f"https://x/{i}", i), 1.0)


def test_round_robin_merge_dedupes_and_stops_at_k():
    a, b = [_hit("1"), _hit("2"), _hit("3")], [_hit("1"), _hit("4"), _hit("5")]
    assert [h.doc.id for h in rag.merge_round_robin([a, b], 4)] == ["1", "4", "2", "5"]
    assert [h.doc.id for h in rag.merge_round_robin([a, []], 5)] == ["1", "2", "3"]


def test_writer_gets_top_5_by_default_and_it_is_configurable(corpus, monkeypatch):
    llm, msgs = fake_llm([resp("end_turn", text("R$ 10 [1]."))] * 2, effort="medium")
    monkeypatch.setattr(agents, "get_llm", lambda role="agent": llm)
    monkeypatch.setenv("COVERAGE_MIN_SCORE", "0")  # todo trecho com termo em comum conta como fonte
    r = agents.faq_agent(ctx("planos conta pagamentos troca entrega custa"))
    assert len(r.sources) == 5 and msgs.sent[0]["messages"][-1]["content"].count("https://example.com/") == 5
    monkeypatch.setenv("FAQ_TOP_K", "2")
    assert len(agents.faq_agent(ctx("planos conta pagamentos troca entrega custa")).sources) == 2


def test_no_covered_passage_is_still_no_source_without_calling_the_llm(corpus, monkeypatch):
    llm, msgs = fake_llm([])
    monkeypatch.setattr(agents, "get_llm", lambda role="agent": llm)
    r = agents.faq_agent(ctx("Qual a capital da Mongólia?"))
    assert r.status == "insufficient" and r.reason == "no_source" and msgs.sent == []  # sem fonte, sem afirmação


# --- tool `search` do LLM, com teto ----------------------------------------------------------------------------------
def test_llm_search_tool_is_capped_by_the_turn_budget(corpus, monkeypatch):
    # 1 busca do plano + até 2 do LLM (FAQ_MAX_SEARCHES=3); a 3ª pedida volta como erro de tool
    llm, msgs = fake_llm([
        resp("tool_use", tool_use("search", {"query": "Plano Beta preço"}, "s1")),
        resp("tool_use", tool_use("search", {"query": "troca prazo"}, "s2"),
             tool_use("search", {"query": "conta corrente"}, "s3")),
        resp("end_turn", text("O Plano Alfa custa R$ 10 [1] e o Plano Beta R$ 20 [2].")),
    ], effort="medium")
    monkeypatch.setattr(agents, "get_llm", lambda role="agent": llm)
    spy = SpyRetriever()
    monkeypatch.setattr(agents, "get_retriever", lambda: spy)
    r = agents.faq_agent(ctx("Quanto custa o Plano Alfa?"))
    assert len(spy.queries) == 3  # teto do turno: plano + 2 da tool
    assert r.facts["faq_queries"] == ["Quanto custa o Plano Alfa?", "Plano Beta preço", "troca prazo"]
    assert msgs.sent[0]["tools"][0]["name"] == "search"
    last = msgs.sent[2]["messages"][-1]["content"]
    assert [b["is_error"] for b in last] == [False, True] and "limite de 3 buscas" in last[1]["content"]
    assert r.status == "ok" and {"alfa-preco", "beta-preco"} <= {s.id for s in r.sources}
    assert "[beta-preco]" in r.text  # a passagem nova ganha número e vira fonte citada


def test_tool_results_are_marked_untrusted_and_only_covered_passages_enter(corpus, monkeypatch):
    llm, msgs = fake_llm([
        resp("tool_use", tool_use("search", {"query": "conta corrente"}, "s1"),
             tool_use("search", {"query": "capital da Mongólia"}, "s2")),
        resp("end_turn", text("R$ 20 [2].")),
    ], effort="medium")
    monkeypatch.setattr(agents, "get_llm", lambda role="agent": llm)
    agents.faq_agent(ctx("Quanto custa o Plano Alfa?"))
    found, empty = msgs.sent[1]["messages"][-1]["content"]
    assert found["content"].startswith("<untrusted_content>") and "conta corrente" in found["content"]
    assert empty["content"] == "Nenhuma passagem nova com fonte para esta consulta."


def test_comparison_uses_the_whole_budget_and_the_writer_gets_no_tool(corpus, monkeypatch):
    monkeypatch.setenv("FAQ_MAX_SEARCHES", "2")
    llm, msgs = fake_llm([resp("end_turn", text("Alfa R$ 10 [1]; Beta R$ 20 [2]."))], effort="medium")
    monkeypatch.setattr(agents, "get_llm", lambda role="agent": llm)
    r = agents.faq_agent(ctx("Qual a diferença entre o Plano Alfa e o Plano Beta?"))
    assert "tools" not in msgs.sent[0] and r.status == "ok"
    assert r.text == "Alfa R$ 10 [alfa-preco]; Beta R$ 20 [beta-preco]."


def test_tool_loop_without_final_text_falls_back_to_extractive(corpus, monkeypatch):
    calls = [resp("tool_use", tool_use("search", {"query": f"q{i}"}, f"s{i}")) for i in range(6)]
    llm, _ = fake_llm(calls, effort="medium")
    monkeypatch.setattr(agents, "get_llm", lambda role="agent": llm)
    r = agents.faq_agent(ctx("Quanto custa o Plano Alfa?"))
    assert r.status == "ok" and "R$ 10" in r.text and "Fonte" in r.text


def test_offline_comparison_answers_each_entity_with_its_passage(corpus):
    r = agents.faq_agent(ctx("Qual a diferença entre o Plano Alfa e o Plano Beta?"))
    assert r.status == "ok" and "R$ 10" in r.text and "R$ 20" in r.text
    assert r.text.splitlines()[0].startswith("Plano Alfa:")


def test_faq_agent_reads_but_never_writes_ctx(corpus):
    c = ctx("Qual a diferença entre o Plano Alfa e o Plano Beta?", standalone="")
    before = json.dumps(c.facts)
    agents.faq_agent(c)
    assert json.dumps(c.facts) == before  # o que descobre volta em facts do resultado
