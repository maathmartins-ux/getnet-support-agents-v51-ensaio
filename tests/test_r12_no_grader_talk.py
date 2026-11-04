"""O código e os prompts falam do sistema, não de quem o avalia: comentário diz a regra e a medida, nunca "a régua
leu" ou "as réguas viram". Quem lê o código lia isso como regra feita para a nota. Os docs de processo do kit
(docs/kit/) ficam fora: lá a régua é o assunto."""
import re

from app.config import ROOT

WORD = re.compile(r"\bréguas?\b", re.IGNORECASE)
CODE = ("src", "evals", "scripts", "tests", "ops")
SUFFIXES = {".py", ".md", ".sh", ".ps1", ".js", ".html", ".yml", ".yaml", ".json", ".toml"}


def test_no_code_or_prompt_talks_about_the_grader():
    hits = []
    for top in CODE:
        for path in (ROOT / top).rglob("*"):
            if path.suffix not in SUFFIXES or "__pycache__" in path.parts or path.name == __file__.rsplit("/", 1)[-1]:
                continue
            if any(part in ("results", "cassettes", "validation") for part in path.parts):
                continue  # resultados e gravações são dados: o texto que o LLM escreveu
            for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if WORD.search(line):
                    hits.append(f"{path.relative_to(ROOT)}:{n}")
    assert not hits, f"menção ao avaliador no código: {hits[:10]}"
