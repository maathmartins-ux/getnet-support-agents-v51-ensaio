"""Ingestão (motor do kit): extração literal, tamanho dos trechos, lista de domínios e gravação, sem rede."""

import hashlib
import json

import pytest
from conftest import KIT_DATA

from app.ingest import MAX_CHARS, MIN_CHARS, build, chunk, extract, fetch, is_allowed, load_sources, records

HOSTS = {"loja.example.com"}


def test_only_listed_hosts():
    assert is_allowed("https://loja.example.com/entrega", HOSTS)
    assert not is_allowed("https://loja.example.com.evil.example/", HOSTS)
    with pytest.raises(ValueError):
        fetch("https://outro-pais.example.com/", HOSTS)


def test_sources_file_needs_allowed_hosts(tmp_path):
    cfg = load_sources(KIT_DATA / "sources.json")
    assert cfg["allowed_hosts"] and cfg["groups"]
    bad = tmp_path / "s.json"
    bad.write_text(json.dumps({"groups": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_sources(bad)


def test_extract_drops_chrome_and_scripts():
    html = "<html><title>T</title><nav>Menu</nav><script>x=1</script><p>Texto <b>visível</b></p><footer>F</footer>"
    assert extract(html) == ("T", ["Texto visível"])


def test_h1_inside_header_is_the_page_title_line_but_the_rest_of_the_header_stays_out():
    """Artigo de central de ajuda (tema de WordPress): o h1 mora no <header> do banner. Sem ele, os 22 artigos de
    erro da maquininha tinham o mesmo texto ("Quando ocorre... Solução: 1. Clique na tecla de Função") e o dedupe
    deixava 1 deles; o menu do cabeçalho do site continua fora."""
    from app.ingest import extract_sections

    html = ("<html><head><title>Erro ADQ 4-91 - Loja</title></head><body><header class='site'><nav>Menu · Entrar"
            "</nav><p>Já é cliente?</p></header><header class='banner'><img alt=''><h1>Erro ADQ 4-91: erro na "
            "aprovação</h1><p>subtítulo do banner</p></header><main><h2>Quando ocorre: na venda.</h2><p>1. Clique na "
            "tecla de Função</p></main><svg><title>ícone</title></svg><title>Título repetido por JS</title></body>")
    title, pairs = extract_sections(html)
    assert title == "Erro ADQ 4-91 - Loja"  # só o 1º <title>; o do SVG e o repetido não grudam no título
    assert [t for _, t in pairs] == ["Erro ADQ 4-91: erro na aprovação", "Quando ocorre: na venda.",
                                     "1. Clique na tecla de Função"]
    assert pairs[0][0] == "Erro ADQ 4-91: erro na aprovação"  # o h1 também é a seção da própria linha
    torto = "<header><h1>Título sem fechar</header><p>Texto do corpo da página.</p>"  # HTML torto não pula o resto
    assert [t for _, t in extract_sections(torto)[1]] == ["Título sem fechar", "Texto do corpo da página."]
    assert extract_sections("<nav><header><h1>Logo</h1></header></nav><p>Corpo.</p>")[1] == [("", "Corpo.")]
    # título curto não cola no botão do fim da moldura de cima (outra seção): "AVANÇAR · O que é DIRF" escapava
    curto = "<div><p>Open</p><p>AVANÇAR</p></div><header><h1>O que é DIRF</h1></header><p>A DIRF é a declaração.</p>"
    assert [t for _, t in extract_sections(curto)[1]] == ["Open · AVANÇAR", "O que é DIRF", "A DIRF é a declaração."]


def test_listed_chrome_lines_leave_and_nothing_else_does(tmp_path):
    """Variante do bloco de botões em poucas páginas ("ACESSAR · Fale já · Vamos começar" em 5 de 78; nas outras,
    "Clique aqui · ...") escapa da regra de repetição: o grupo lista a linha em `chrome` e só a linha igual sai."""
    body = " ".join(f"Passo {n} do artigo de ajuda sobre a maquininha." for n in range(9))
    pages = {f"a{i}": f"https://loja.example.com/a{i}" for i in range(5)}

    def fake_fetch(url, hosts):
        first = "ACESSAR" if url.endswith("a0") else "Clique aqui"
        return (f"<title>{url}</title><p>{body} Página {url}.</p><div><p>{first}</p><p>Fale já</p>"
                f"<p>Vamos começar</p></div><p>Para cancelar o serviço {url[-2:]}, ligue 4002-4000.</p>")

    default = build(pages, tmp_path / "padrao", HOSTS, "aj", fetcher=fake_fetch)
    assert "ACESSAR · Fale já · Vamos começar" in default["a0"][-1]["text"]  # a variante escapava
    out = build(pages, tmp_path / "lista", HOSTS, "aj", fetcher=fake_fetch,
                drop={"ACESSAR · Fale já · Vamos começar", "Fale já"})
    assert all("Fale já" not in r["text"] for recs in out.values() for r in recs)
    assert all("4002-4000" in recs[-1]["text"] for recs in out.values())  # o resto fica


def test_chunk_respects_bounds_and_is_literal():
    lines = [f"Frase número {i} sobre o prazo de entrega da loja." for i in range(60)]
    joined = "\n".join(lines)  # linhas do HTML seguem separadas por quebra de linha dentro do trecho
    chunks = chunk(lines)
    assert chunks and all(MIN_CHARS <= len(c) <= MAX_CHARS and c in joined for c in chunks)


def test_chunk_keeps_block_rows_apart_without_moving_the_cuts():
    """Lista em blocos <p> (faixa de faturamento → maquininha): cada linha fica na sua; o separador tem o tamanho do
    espaço, então os cortes (e os ids dos trechos) são os mesmos do texto colado com espaço."""
    rows = ["Vendendo você ganha máquina grátis", "Acima de R$ 20mil por mês | Get Clássica",
            "Acima de R$ 40mil por mês | Get Clássica ou Get Smart",
            "Acima de R$ 80mil por mês | Get Clássica ou Get Smart",
            "*As modalidades de Voucher (VA/VR), Crediário não compõem faturamento para isenção do aluguel."]
    lines = rows * 6
    chunks = chunk(lines)
    assert chunks and "Get Clássica\nAcima de R$ 40mil por mês" in chunks[0]
    flat = [c.replace("\n", " ") for c in chunks]
    assert all(c in " ".join(lines) for c in flat)  # mesmo texto, mesmos cortes; só o separador mudou
    long_line = " ".join(f"Sentença {i} do texto longo." for i in range(80))
    assert all("\n" not in c for c in chunk([long_line]))  # pedaços da MESMA linha seguem com espaço


def test_chunk_splits_long_line_by_sentence():
    long_line = " ".join(f"Sentença {i} do texto longo." for i in range(80))
    assert all(MIN_CHARS <= len(c) <= MAX_CHARS and c in long_line for c in chunk([long_line]))


def test_records_shape():
    (r,) = records("pix", "https://loja.example.com/pix", "Pix", ["a" * 300], "2026-10-31T17:00:00+00:00", "prod")
    assert r["id"] == "prod-pix-01"
    assert r["sha256"] == hashlib.sha256(("a" * 300).encode()).hexdigest()
    assert set(r) == {"id", "title", "url", "text", "fetched_at", "sha256"}


def test_build_drops_repeated_site_chrome_and_writes_jsonl(tmp_path):
    menu = "Menu principal da loja com todos os links"
    pages = {f"p{i}": f"https://loja.example.com/p{i}" for i in range(4)}

    def fake_fetch(url, hosts):
        body = " ".join(f"Conteúdo próprio da página {url} frase {n}." for n in range(40))
        return f"<title>{url}</title><p>{menu}</p><p>{body}</p>"

    out = build(pages, tmp_path, HOSTS, "ajuda", fetcher=fake_fetch)
    rows = [json.loads(line) for f in sorted(tmp_path.glob("*.jsonl")) for line in f.read_text("utf-8").splitlines()]
    assert sum(len(v) for v in out.values()) == len(rows) > 0
    assert all(menu not in r["text"] and r["id"].startswith("ajuda-") for r in rows)


def test_page_without_chunks_leaves_no_file_and_article_mode_keeps_a_short_article(tmp_path):
    """Página sem trecho não deixa arquivo de 0 byte (nem o velho); no modo artigo (central de ajuda), o
    artigo inteiro entre SHORT_PAGE e MIN_CHARS vira 1 trecho em vez de sumir."""
    from app.ingest import SHORT_PAGE

    pages = {"curta": "https://loja.example.com/curta", "vazia": "https://loja.example.com/vazia"}
    (tmp_path / "vazia.jsonl").write_text('{"id": "velho"}\n', encoding="utf-8")  # de uma ingestão anterior

    def fake_fetch(url, hosts):
        if "vazia" in url:
            return "<title>V</title><p>Só uma frase de aviso.</p>"
        return "<title>C</title><p>" + "Passo curto do artigo de ajuda. " * 8 + "</p>"

    assert build(pages, tmp_path, HOSTS, "aj", fetcher=fake_fetch) == {"curta": [], "vazia": []}
    assert not list(tmp_path.glob("*.jsonl"))
    out = build(pages, tmp_path, HOSTS, "aj", fetcher=fake_fetch, articles=True)
    assert [r["id"] for r in out["curta"]] == ["aj-curta-01"] and out["vazia"] == []
    assert SHORT_PAGE <= len(out["curta"][0]["text"]) < MIN_CHARS
    assert [p.name for p in tmp_path.glob("*.jsonl")] == ["curta.jsonl"]


def test_short_table_cells_are_glued_and_repeated_price_table_is_kept_once(tmp_path):
    """A tabela de preços (células curtas, repetida em 6+ páginas) não pode sumir do corpus, senão o AC-01 fica sem
    fonte: as células viram uma linha e a tabela longa repetida fica na 1ª página; o menu curto continua fora."""
    from app.ingest import glue_short

    assert glue_short(["Get Clássica", "R$ 79,90/mês", "Uma frase longa de conteúdo da página."]) == [
        "Get Clássica · R$ 79,90/mês", "Uma frase longa de conteúdo da página."]
    cells = "".join(f"<div>{c}</div>" for c in ("Venda pelo celular", "R$ 0,00/mês", "Get Mini", "R$ 14,90/mês",
                                                "Get Clássica", "R$ 79,90/mês", "Get Smart", "R$ 129,90/mês"))
    pages = {f"p{i}": f"https://loja.example.com/p{i}" for i in range(6)}

    def fake_fetch(url, hosts):
        body = " ".join(f"Conteúdo próprio da página {url} frase {n}." for n in range(40))
        return f"<title>{url}</title><div>Home</div><div>Ajuda</div><p>{body}</p><p>Caso não atinja o faturamento, " \
               f"segue o valor de utilização:</p>{cells}"

    build(pages, tmp_path, HOSTS, "prod", fetcher=fake_fetch)
    rows = [json.loads(line) for f in sorted(tmp_path.glob("*.jsonl")) for line in f.read_text("utf-8").splitlines()]
    with_price = [r for r in rows if "R$ 79,90/mês" in r["text"]]
    assert len(with_price) == 1 and "Get Clássica · R$ 79,90/mês" in with_price[0]["text"]
    assert not any("Home · Ajuda" in r["text"] for r in rows)


TARIFF = ("<h3>Taxas</h3><p>Para maior transparência disponibilizamos todas as taxas.</p><table><tbody>"
          "<tr><th>Plano de recebimento:</th><th><strong>2 dias úteis*</strong></th><th>Receba conforme</th></tr>"
          "<tr><td>Débito:</td><td>1,89%</td><td>1,95%</td></tr>"
          "<tr><td>Crédito à vista:</td><td>3,99%</td><td>3,09%</td></tr></tbody></table><p>Depois da tabela.</p>")


def test_table_rows_keep_their_column_labels():
    """Tabela de taxas célula a célula: cada valor sai com o rótulo da linha e da coluna, e nada cai por curto."""
    from app.ingest import TableLine

    _, lines = extract(f"<title>T</title>{TARIFF}")
    rows = [ln for ln in lines if isinstance(ln, TableLine)]
    assert rows[0] == "Plano de recebimento | 2 dias úteis* | Receba conforme" and rows[0].header
    assert "Débito — 2 dias úteis*: 1,89%; Receba conforme: 1,95%" in rows
    assert "Crédito à vista — 2 dias úteis*: 3,99%; Receba conforme: 3,09%" in rows
    assert "Depois da tabela." in lines and "1,89%" not in lines  # célula solta não vira linha própria


def test_colspan_header_and_numeric_row_label():
    from app.ingest import render_table

    rows = [[("", True, 1), ("Receber em 2 dias", True, 2)],
            [("Parcelas", False, 1), ("Taxa", False, 1), ("Líquido", False, 1)],
            [("2", False, 1), ("5,99%", False, 1), ("R$ 94,01", False, 1)]]
    out = render_table(rows, 1)
    assert out[0] == "Parcelas | Receber em 2 dias Taxa | Receber em 2 dias Líquido"
    assert out[1] == "Parcelas 2 — Receber em 2 dias Taxa: 5,99%; Receber em 2 dias Líquido: R$ 94,01"


def test_small_table_is_one_chunk_and_long_table_repeats_its_header():
    from app.ingest import chunk_sections, extract_sections

    _, pairs = extract_sections(f"<title>T</title>{TARIFF}")
    tables = [c for _, c in chunk_sections(pairs) if "1,89%" in c]
    assert len(tables) == 1 and "3,09%" in tables[0]  # tabela pequena (< MIN_CHARS) inteira, não descartada
    body = "".join(f"<tr><td>{n}x</td><td>{n},{n:02d}%</td><td>R$ {100 - n},00</td></tr>" for n in range(1, 60))
    _, pairs = extract_sections(f"<table><tr><th>Parcelas</th><th>Taxa</th><th>Líquido</th></tr>{body}</table>")
    pieces = [c for _, c in chunk_sections(pairs)]
    assert len(pieces) > 1 and all(len(c) <= MAX_CHARS for c in pieces)
    assert all(c.startswith("Parcelas | Taxa | Líquido\n") for c in pieces)  # cabeçalho repetido em cada pedaço
    joined = "\n".join(pieces)
    assert all(f"{n}x — Taxa: {n},{n:02d}%; Líquido: R$ {100 - n},00" in joined for n in range(1, 60))


def test_long_glued_div_table_is_cut_between_cells_never_mid_cell():
    """Tabela em <div> (células coladas por glue_short) passava de MAX_CHARS sem ponto final: era truncada."""
    from app.ingest import chunk_sections, extract_sections

    cells = "".join(f"<div><p>Crédito {n}x</p><p>{n},{n:02d}%</p></div>" for n in range(1, 80))
    _, pairs = extract_sections(f"<p>A partir de:</p>{cells}")
    pieces = [c for _, c in chunk_sections(pairs)]
    joined = " · ".join(pieces)
    assert all(f"Crédito {n}x · {n},{n:02d}%" in joined for n in range(1, 80))  # rótulo junto do valor
    assert all(len(c) <= MAX_CHARS for c in pieces)
