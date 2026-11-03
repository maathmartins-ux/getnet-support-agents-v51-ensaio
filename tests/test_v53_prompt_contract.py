"""Contrato do motor no fim do prompt do domínio (ensaio v5.3: o domínio da V5 trocou faq/router/supervisor)."""
from pathlib import Path

from app import domain


def test_domain_prompt_gets_engine_contract(tmp_path, monkeypatch):
    (tmp_path / "faq.md").write_text("Você responde dúvidas de lojistas. Idioma: {language}.\n", encoding="utf-8")
    monkeypatch.setattr(domain.active(), "PROMPTS_DIR", tmp_path, raising=False)
    text = domain.prompt("faq.md")
    assert text.startswith("Você responde dúvidas de lojistas.")
    assert "MISSING:" in text and "NOT_IN_SOURCES" in text and "Resposta indireta" in text
    assert text.format(language="English")  # o contrato não traz chaves soltas


def test_kit_prompt_is_not_duplicated(monkeypatch):
    monkeypatch.setattr(domain.active(), "PROMPTS_DIR", domain.KIT_PROMPTS, raising=False)
    for name in ("faq.md", "router.md", "supervisor.md"):
        text = domain.prompt(name)
        assert "Regras do motor" not in text
        assert text == (domain.KIT_PROMPTS / name).read_text(encoding="utf-8")


def test_domain_that_already_has_contract_is_left_alone(tmp_path, monkeypatch):
    (tmp_path / "router.md").write_text("x\nRegras do motor (minhas)\n", encoding="utf-8")
    monkeypatch.setattr(domain.active(), "PROMPTS_DIR", tmp_path, raising=False)
    assert domain.prompt("router.md") == "x\nRegras do motor (minhas)\n"


def test_every_contract_file_matches_a_kit_prompt():
    for f in Path(domain.CONTRACT).glob("*.md"):
        assert (domain.KIT_PROMPTS / f.name).exists()


def test_contract_asks_yes_no_questions_to_lead_with_the_direct_answer(tmp_path, monkeypatch):
    (tmp_path / "faq.md").write_text("Domínio.\n", encoding="utf-8")
    monkeypatch.setattr(domain.active(), "PROMPTS_DIR", tmp_path, raising=False)
    assert "a 1ª frase é a resposta direta" in domain.prompt("faq.md")
    monkeypatch.setattr(domain.active(), "PROMPTS_DIR", domain.KIT_PROMPTS, raising=False)
    assert "a 1ª frase é a resposta direta" in domain.prompt("faq.md")


def test_guardrail_contract_keeps_pronoun_follow_ups_safe(tmp_path, monkeypatch):
    # medido: "E qual foi o valor dela?" (a venda da própria conversa) bloqueado como dado de outra pessoa
    (tmp_path / "guardrail.md").write_text("Classifique.\n", encoding="utf-8")
    monkeypatch.setattr(domain.active(), "PROMPTS_DIR", tmp_path, raising=False)
    assert "e o valor dela?" in domain.prompt("guardrail.md")
