"""O pré-voo copia os prompts do kit para o domínio, mas não o contrato do motor (prompts/contract/): domain.prompt
anexa a versão do kit em todo prompt de domínio, e a cópia ficava no domínio sem ser lida, envelhecendo (no ensaio, a
cópia era a do kit antigo)."""
import shutil

from app.config import ROOT
from scripts import preflight


def test_preflight_copies_the_prompts_but_not_the_engine_contract(tmp_path, monkeypatch):
    prompts = tmp_path / "prompts"
    shutil.copytree(ROOT / "src" / "app" / "prompts", prompts)
    assert (prompts / "contract" / "faq.md").exists()
    domain = tmp_path / "domain"
    domain.mkdir()
    (tmp_path / "data").mkdir()
    # tudo o que o build escreve ou apaga fica no diretório do teste: a raiz (glossário, sources), as ferramentas do
    # kit (KIT_ONLY, que ele remove) e os exemplos esvaziados (EMPTIED) — nunca o repositório de verdade
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.setattr(preflight, "KIT_ONLY", [])
    monkeypatch.setattr(preflight, "PROMPTS", prompts)
    monkeypatch.setattr(preflight, "DOMAIN", domain)
    monkeypatch.setattr(preflight, "TARGET", domain / "challenge")
    monkeypatch.setattr(preflight, "TARGET_PROMPTS", domain / "challenge_prompts")
    monkeypatch.setattr(preflight, "EMPTIED", [])
    preflight.build(dry=False)
    copied = domain / "challenge_prompts"
    assert (copied / "faq.md").read_text(encoding="utf-8") == (prompts / "faq.md").read_text(encoding="utf-8")
    assert not (copied / "contract").exists()
    assert (tmp_path / "data" / "sources.json").exists()  # o build escreveu na raiz do teste, não na do repositório
