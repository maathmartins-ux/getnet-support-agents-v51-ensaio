"""A §3 do README e a tabela completa dela (docs/COBERTURA.md) só citam o que existe: arquivo citado existe,
teste citado está definido.

Quem lê o README nem sempre roda o código: um caminho quebrado no mapa de evidências custa exatamente a
confiança que o mapa deveria dar.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CITED = re.compile(r"`([\w./-]+\.(?:py|md|jsonl|json|yml|lock|ps1)|Dockerfile)(?:::(\w+))?`")


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
