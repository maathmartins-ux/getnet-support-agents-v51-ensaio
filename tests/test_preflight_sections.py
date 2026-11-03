"""O pré-voo do T+0 tem destino para TODA seção do domínio de exemplo: sem isso, uma seção nova quebra a
largada com "seção sem destino no pré-voo" e nenhum outro teste pega."""
import importlib.util

from app.config import ROOT


def test_every_example_section_has_a_destination():
    spec = importlib.util.spec_from_file_location("preflight", ROOT / "scripts" / "preflight.py")
    pre = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pre)
    files = pre.split_example(pre.EXAMPLE.read_text(encoding="utf-8"))
    assert set(files) == {"flow.py", "tools.py", "__init__.py"}
    assert "def needs_for" in files["tools.py"]
