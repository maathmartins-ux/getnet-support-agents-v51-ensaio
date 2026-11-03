"""Padrões do ingest/índice medidos no ensaio v5.2: sem corte por seção e sem o contexto no índice (RAG_CONTEXT)."""
from app import ingest
from app.rag import Doc

# sem ponto final: só a troca de seção (h2) cortaria aqui
LONG_A = ("Resposta da primeira pergunta frequente com bastante texto para passar do mínimo de caracteres " * 4).strip()
LONG_B = "Outra resposta, de outro assunto, que vem logo depois na mesma página de dúvidas frequentes. " * 4


def _chunks():
    return ingest.chunk_sections([("Seção A", LONG_A.strip()), ("Seção B", LONG_B.strip())], lo=300, hi=800)


def test_default_does_not_cut_on_section(monkeypatch):
    monkeypatch.delenv("INGEST_SECTION_CUT", raising=False)
    assert len(_chunks()) == 1  # as duas seções cabem num trecho: não corta só porque o h2 mudou


def test_section_cut_is_opt_in(monkeypatch):
    monkeypatch.setenv("INGEST_SECTION_CUT", "on")
    assert len(_chunks()) == 2


def test_index_header_is_title_unless_context_on(monkeypatch):
    doc = Doc("d1", "Dúvidas | Getnet", "https://x/duvidas", "texto", context="Dúvidas | Getnet › Pix")
    monkeypatch.delenv("RAG_CONTEXT", raising=False)
    assert doc.head == "Dúvidas | Getnet"
    monkeypatch.setenv("RAG_CONTEXT", "on")
    assert doc.head == "Dúvidas | Getnet › Pix"
