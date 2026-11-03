"""E53 — página de rotulagem, pergunta 3 (idioma): idioma da pergunta e da resposta lado a lado e a regra escrita.

Pós-morte V5 (N8): kappa entre humanos 0,054 porque a 2ª pessoa leu a pergunta 3 como "devia ser em português" e
marcou 5 de 10 respostas certas em inglês como idioma errado.
"""
import json
import re
import shutil
import subprocess

import pytest

from scripts import label_page

RULE = "pergunta em inglês e resposta em inglês = Sim"


def _results(tmp_path):
    d = tmp_path / "results"
    d.mkdir()
    rows = [{"id": "en-1", "split": "official", "run": 0, "message": "What is the fee of the card reader?",
             "answer": "The fee is shown on the plan page and you can change it in the app.",
             "expected_language": "en", "language_detected": "en", "sources": []},
            {"id": "pt-1", "split": "official", "run": 0, "message": "Qual o prazo?",
             "answer": "The deadline is five days and you can check it in the app.", "language_detected": "en",
             "sources": []}]
    (d / "live_official.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    return d


def test_items_carry_question_and_answer_language_from_the_text(tmp_path):
    got = {r["id"]: r for r in label_page.items(10, results=_results(tmp_path))}
    assert (got["en-1"]["lang"], got["en-1"]["answer_lang"]) == ("en", "en")
    assert (got["pt-1"]["lang"], got["pt-1"]["answer_lang"]) == ("pt", "en")  # pergunta sem idioma no caso: pelo texto


def test_template_states_the_rule_plainly():
    html = label_page.TEMPLATE.read_text(encoding="utf-8")
    assert RULE in html and "NÃO precisa estar em português" in html
    assert "Idioma da pergunta" in html and "Idioma da resposta" in html
    assert "A pergunta foi em ${lang}" not in html  # título antigo, que deixava a leitura "devia ser português"


DOM = r"""
const els = {};
function el(id) {
  return els[id] ||= { id, innerHTML: "", textContent: id === "data" ? DATA_JSON : "", hidden: false, value: "",
    disabled: false, style: {}, dataset: {}, classList: { toggle() {} }, addEventListener() {}, focus() {} };
}
const docListeners = [];
globalThis.document = { getElementById: el, addEventListener: (t, f) => docListeners.push([t, f]) };
globalThis.window = { scrollTo() {} };
globalThis.localStorage = { getItem() { return null; }, setItem() {} };
globalThis.navigator = {};
"""


@pytest.mark.skipif(not shutil.which("node"), reason="sem node")
def test_rendered_item_shows_both_languages_side_by_side(tmp_path):
    # sem treino: o "Começar" leva direto à 1ª situação (o treino tem teste próprio em test_v53_human_agreement)
    page = label_page.render(label_page.items(10, results=_results(tmp_path)), ["Ana", "Bia"], practice=[])
    data = re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1)
    script = re.findall(r"<script>(.*?)</script>", page, re.S)[-1]
    click_go = """
for (const [t, f] of docListeners) if (t === "click") f({ target: { closest: (sel) =>
  sel.includes("#start") ? { id: "go", dataset: {}, disabled: false } : null } });
console.log(JSON.stringify(els.item.innerHTML));
"""
    js = f"const DATA_JSON = {json.dumps(data)};\n{DOM}\n{script}\n{click_go}"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30, check=True).stdout
    html = json.loads(out.strip().splitlines()[-1])
    first = json.loads(data.replace("<\\/", "</"))["items"][0]
    pair = re.search(r'<div class="langpair".*?</div></div>', html, re.S).group(0)
    names = {"en": "inglês", "pt": "português"}
    assert f"Idioma da pergunta</small><b>{names[first['lang']]}" in pair
    assert f"Idioma da resposta</small><b>{names[first['answer_lang']]}" in pair
    assert RULE in html and "MESMO idioma da pergunta" in html
