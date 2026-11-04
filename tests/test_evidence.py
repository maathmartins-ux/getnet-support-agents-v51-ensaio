"""A §3 do README e a tabela completa dela (docs/COBERTURA.md) só citam o que existe: arquivo citado existe,
teste citado está definido. E nenhum teste citado no README, em docs/*.md, docs/adr/*.md ou nos docker-compose*.yml
(comentário de compose também é prova vendida) falta.

Quem lê o README nem sempre roda o código: um caminho quebrado no mapa de evidências custa exatamente a
confiança que o mapa deveria dar.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CITED = re.compile(r"`([\w./-]+\.(?:py|md|jsonl|json|yml|lock|ps1)|Dockerfile)(?:::(\w+))?`")
# tests/x.py, com ou sem crase, `::teste` opcional; `../tests/x.py` (link relativo) é do check.py (docs_links_exist)
TEST_CITED = re.compile(r"(?<![\w/.-])(tests/[\w/.-]*?\w\.py)(?:::(\w+))?")


def coverage_section(readme: str) -> str:
    start = readme.index("## 3. Cobertura")
    return readme[start:readme.index("\n## ", start + 1)]


def missing_citations(section: str, root: Path = ROOT) -> list[str]:
    missing = []
    for path, func in CITED.findall(section):
        file = root / path
        if not file.exists():
            missing.append(path)
        elif func and not re.search(rf"^def {func}\(", file.read_text(encoding="utf-8"), re.MULTILINE):
            missing.append(f"{path}::{func}")
    return missing


def test_every_cited_path_and_test_exists():
    section = coverage_section((ROOT / "README.md").read_text(encoding="utf-8"))
    full = (ROOT / "docs" / "COBERTURA.md").read_text(encoding="utf-8")  # a tabela completa da §3
    assert len(CITED.findall(section)) >= 12 and len(CITED.findall(full)) >= 20, "mapa de evidências quase vazio"
    assert not missing_citations(section), f"README §3 cita o que não existe: {missing_citations(section)}"
    assert not missing_citations(full), f"docs/COBERTURA.md cita o que não existe: {missing_citations(full)}"


def test_broken_citation_is_caught():
    section = "`src/app/router.py` `tests/test_router.py::nao_existe` `src/app/sumiu.py`"
    assert missing_citations(section) == ["tests/test_router.py::nao_existe", "src/app/sumiu.py"]


def missing_tests(text: str, root: Path = ROOT) -> list[str]:
    """`tests/x.py` (e `tests/x.py::teste`) citados no texto que não existem no repositório."""
    missing = []
    for path, func in TEST_CITED.findall(text):
        file = root / path
        if not file.is_file():
            missing.append(path)
        elif func and not re.search(rf"^\s*(?:async\s+)?def {func}\(|^class {func}\b",
                                    file.read_text(encoding="utf-8"), re.MULTILINE):
            missing.append(f"{path}::{func}")
    return missing


def test_every_test_cited_in_compose_docs_and_readme_exists():
    """O overlay endurecido citava `tests/test_hardening.py`, que não existe: a guarda das citações só varria a §3 e
    a COBERTURA. docs/KIT_CHANGELOG.md fica de fora (histórico do kit, copiado sem edição; check.py faz o mesmo)."""
    files = [ROOT / "README.md", *sorted(ROOT.glob("docs/*.md")), *sorted(ROOT.glob("docs/adr/*.md")),
             *sorted(ROOT.glob("docker-compose*.yml"))]
    files = [f for f in files if f.name != "KIT_CHANGELOG.md"]
    assert len([f for f in files if f.suffix == ".yml"]) >= 2 and any(TEST_CITED.search(f.read_text(encoding="utf-8"))
                                                                     for f in files), "nada varrido"
    broken = {str(f.relative_to(ROOT)): bad for f in files if (bad := missing_tests(f.read_text(encoding="utf-8")))}
    assert not broken, f"cita teste que não existe: {broken}"


def test_missing_test_citation_is_caught():
    text = ("# Prova: tests/test_hardening.py (estrutura), `tests/test_evidence.py::nao_existe`, "
            "tests/test_evidence.py::test_missing_test_citation_is_caught e tests/test_*.py")
    assert missing_tests(text) == ["tests/test_hardening.py", "tests/test_evidence.py::nao_existe"]
