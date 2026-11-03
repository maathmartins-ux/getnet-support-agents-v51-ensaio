"""Scripts .ps1 com acento precisam de BOM UTF-8: o PowerShell 5.1 lê .ps1 sem BOM como ANSI.

Sem BOM, live_eval.ps1 imprime "nÃ£o rodado" no console do Windows.
"""
import codecs
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ps1_with_non_ascii_has_utf8_bom():
    bad = [p.name for p in ROOT.rglob("*.ps1")
           if ".venv" not in p.parts and not p.read_bytes().isascii()
           and not p.read_bytes().startswith(codecs.BOM_UTF8)]
    assert not bad, f"salve com UTF-8 com BOM: {bad}"
