"""Nenhum arquivo de src/ cita um caso do eval pelo id ("official-08", "memory-07").

Comentário assim é lido como regra feita para o cenário, e o número do eval passa a ser de desenvolvimento. A regra
fica escrita como regra genérica, com a medida ("medido em resposta ao vivo: ..."), sem o id do caso. Os ids vêm dos
próprios conjuntos do eval (evals/<nome>.jsonl e evals/<nome>.d/), então a guarda vale para o domínio montado no
relógio sem lista de famílias; o padrão `official-NN` vale mesmo sem o arquivo de casos.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.config import ROOT

OFFICIAL = re.compile(r"(?<![\w-])official-\d+(?![\w-])", re.IGNORECASE)
CASE_ID = re.compile(r"[\w.-]+-\d+[a-z]?")  # forma de id de caso ("memory-07", "q-guard-oos-1"); palavra solta não
TEXT = (".py", ".md", ".html", ".txt", ".json", ".jsonl", ".yml", ".yaml")


def eval_case_ids(root: Path = ROOT) -> set[str]:
    """Ids das linhas com forma de caso (id + message) de todo evals/*.jsonl e evals/*.d/*.jsonl (fora as gravações)."""
    ids = set()
    for path in sorted([*root.glob("evals/*.jsonl"), *root.glob("evals/*.d/*.jsonl")]):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and "message" in row and CASE_ID.fullmatch(str(row.get("id", ""))):
                ids.add(str(row["id"]))
    return ids


def case_citations(text: str, ids: set[str]) -> list[tuple[int, str]]:
    """(linha, id) de cada caso citado: `official-NN` ou um id dos conjuntos do eval, como palavra inteira."""
    known = re.compile(r"(?<![\w-])(?:" + "|".join(sorted(map(re.escape, ids), key=len, reverse=True)) + r")(?![\w-])"
                       ) if ids else None
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        hits = {m.group(0) for m in OFFICIAL.finditer(line)} | ({m.group(0) for m in known.finditer(line)}
                                                                 if known else set())
        found += [(n, hit) for hit in sorted(hits)]
    return found


def test_source_cites_no_eval_case_by_id():
    ids = eval_case_ids()
    assert any(i.startswith("official-") for i in ids), "conjunto de casos do eval não encontrado"
    files = [p for p in sorted((ROOT / "src").rglob("*")) if p.is_file() and p.suffix in TEXT]
    assert len(files) > 20, "nada varrido"
    cited = [f"{p.relative_to(ROOT)}:{n}: {hit}" for p in files
             for n, hit in case_citations(p.read_text(encoding="utf-8", errors="replace"), ids)]
    assert not cited, ("src/ cita caso do eval pelo id; escreva a regra genérica com a medida, sem o id:\n"
                       + "\n".join(cited))


def test_case_citation_is_caught():
    text = ("# Medido (official-08): a dica caía.\n"
            "x = 1  # casos memory-07/08 e OFFICIAL-3\n"
            "# memory-070 é outro id; dense-e5 e utf-8 não são caso; memory-07a é\n")
    assert case_citations(text, {"memory-07", "memory-07a"}) == [(1, "official-08"), (2, "OFFICIAL-3"),
                                                                 (2, "memory-07"), (3, "memory-07a")]
    assert case_citations("sem caso nenhum", set()) == []
