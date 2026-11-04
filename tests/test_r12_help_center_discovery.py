"""Descoberta de artigos de central de ajuda (scripts/ingest_render.py --discover): HTML local, sem rede nem navegador.

Índice e categorias montados por JavaScript (no estático, só a moldura do site); artigo com o texto no HTML estático.
Medido no desafio: os 2 índices da central davam 0 trechos e os artigos nunca entravam no corpus.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = "ajuda.example.com"
BASE = f"https://{HOST}"


def _mod():
    spec = importlib.util.spec_from_file_location("ingest_render_r12", ROOT / "scripts" / "ingest_render.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CHROME = ("<header><nav>Menu · Entrar</nav></header><div class='modal'><p>Já é cliente? Informe o seu CPF ou CNPJ "
          "para continuar o atendimento.</p></div><p>Política de cookies do site e preferências de privacidade.</p>")
FOOT = "<section><p>Veja os nossos vídeos com as principais dicas.</p><p>Fale conosco pelo WhatsApp oficial.</p>" \
       "</section><footer>Rodapé</footer>"


def _page(body: str, title: str = "Página", canonical: str = "", header: str = "") -> str:
    link = f"<link rel='canonical' href='{canonical}'>" if canonical else ""
    return (f"<html><head><title>{title}</title>{link}</head><body>{CHROME}{header}<main>{body}</main>{FOOT}"
            "</body></html>")


def _links(*paths: str) -> str:
    return "<ul>" + "".join(f"<li><a href='{p}'>{p}</a></li>" for p in paths) + "</ul>"


STEPS = "<ol>" + "".join(f"<li>{i}. Passo {i} para antecipar as vendas pelo aplicativo.</li>" for i in range(1, 7)) \
        + "</ol><p>O valor mínimo para antecipação é de R$ 50,00.</p>"
RENDERED = {  # o que o navegador devolve (links montados por JavaScript)
    f"{BASE}/ajuda/": _page("<h1>Central de ajuda</h1>" + _links(
        "/ajuda-vendas/", "/ajuda-erros", "/ajuda-vendas/como-antecipar/#passo", "https://outro.example.com/ajuda-x/",
        "/blog/novidade/", "/ajuda-vendas/como-antecipar/?utm=1", "mailto:a@b.c", "/ajuda-erros/ja-listado/",
        "/ajuda-vendas/redireciona/")),
    f"{BASE}/ajuda-vendas/": _page("<h1>Vendas</h1>" + _links("/ajuda-vendas/como-antecipar/",
                                                             "/ajuda-vendas/so-video/", "/ajuda-vendas/receber-hoje",
                                                             "/ajuda/")),
    f"{BASE}/ajuda-erros/": _page("<h1>Erros</h1>" + _links("/ajuda-erros/erro-12/", "/ajuda-erros/copia-do-12/",
                                                           "/ajuda-vendas/")),
}
STATIC = {  # o que o fetch estático devolve
    f"{BASE}/ajuda/": _page("<h1>Central de ajuda</h1>"),
    f"{BASE}/ajuda-vendas/": _page("<h1>Vendas</h1>"),
    f"{BASE}/ajuda-erros/": _page("<h1>Erros</h1>"),
    f"{BASE}/ajuda-vendas/como-antecipar/": _page("<p>É possível antecipar as vendas no crédito pelo app.</p>" + STEPS),
    f"{BASE}/ajuda-vendas/so-video/": _page("<iframe src='https://video.example.com/x'></iframe><p>Assista.</p>"),
    f"{BASE}/ajuda-vendas/receber-hoje/": _page("<p>Com o plano de recebimento reduzido, o valor das vendas no crédito "
                                                "cai na conta em 1 dia útil, e não em 30 dias.</p><p>Os valores são "
                                                "depositados no domicílio bancário cadastrado no aplicativo.</p><p>O "
                                                "plano vale para todas as bandeiras e pode ser cancelado a qualquer "
                                                "momento pela central.</p>"),
    # o "artigo" que redireciona para uma página de produto já ingerida (rel=canonical em outro grupo)
    f"{BASE}/ajuda-vendas/redireciona/": _page("<p>" + "Conheça as maquininhas e as taxas de cada plano. " * 6 + "</p>",
                                               canonical=f"{BASE}/produtos/"),
    # o mesmo erro listado com 2 endereços: a cópia aponta para o original
    f"{BASE}/ajuda-erros/copia-do-12/": _page("<p>" + "Desligue a maquininha e ligue de novo depois de 10 s. " * 4
                                              + "</p>", canonical="/ajuda-erros/erro-12"),
    # artigo curto (título no <header> + 3 passos, < 300 caracteres): é a resposta inteira
    f"{BASE}/ajuda-erros/erro-12/": _page("<h2>Quando ocorre: na venda.</h2><ol><li>1. Desligue a maquininha e "
                                          "ligue de novo depois de 10 segundos.</li><li>2. Faça uma venda teste com "
                                          "um cartão de débito.</li><li>3. Se o erro continuar, ligue para a "
                                          "central de atendimento.</li></ol>",
                                          header="<header><nav>Menu</nav><h1>Erro 12: falha de leitura do "
                                                 "cartão</h1></header>"),
}


def _fakes():
    calls = {"render": [], "static": [], "sleep": []}

    def renderer(url, hosts):
        calls["render"].append(url)
        return RENDERED[url]

    def fetch(url, hosts):
        calls["static"].append(url)
        if url not in STATIC:
            raise OSError(f"404 {url}")
        return STATIC[url]

    return calls, renderer, fetch, calls["sleep"].append


def test_discover_renders_index_and_categories_and_keeps_static_articles():
    mod = _mod()
    calls, renderer, fetch, sleep = _fakes()
    follow = {"from": [f"{BASE}/ajuda/"], "path_prefix": "/ajuda-", "depth": 2, "pause_s": 0.5}
    urls, html = mod.discover(follow, [HOST], fetch=fetch, renderer=renderer, sleep=sleep,
                              skip=[f"{BASE}/ajuda-erros/ja-listado", f"{BASE}/produtos/"])
    # o vídeo só com título, o redirect para a página de produto e a cópia do erro ficam de fora
    assert urls == [f"{BASE}/ajuda-vendas/como-antecipar/", f"{BASE}/ajuda-vendas/receber-hoje/",
                    f"{BASE}/ajuda-erros/erro-12/"]
    assert set(html) == set(urls) and "R$ 50,00" in html[urls[0]]
    # só o índice e as 2 categorias vão ao navegador; o artigo, o vídeo e a página já listada não
    assert calls["render"] == [f"{BASE}/ajuda/", f"{BASE}/ajuda-vendas/", f"{BASE}/ajuda-erros/"]
    assert f"{BASE}/ajuda-erros/ja-listado/" not in calls["static"]  # skip: já está em outro grupo
    assert not any("outro.example.com" in u or "/blog/" in u for u in calls["static"])  # outro host, outro prefixo
    assert calls["static"].count(f"{BASE}/ajuda-vendas/como-antecipar/") == 1  # âncora e query = a mesma página
    assert calls["sleep"] == [0.5] * (len(calls["render"]) + len(calls["static"]) - 1)  # pausa entre pedidos


def test_discover_stops_at_the_page_cap_and_skips_failing_pages(capsys):
    mod = _mod()
    calls, renderer, fetch, sleep = _fakes()
    follow = {"from": [f"{BASE}/ajuda/"], "path_prefix": "/ajuda-", "depth": 2, "max_pages": 4}
    urls, _ = mod.discover(follow, [HOST], fetch=fetch, renderer=renderer, sleep=sleep)
    # índice (render + estático) e as 2 categorias no estático; o teto barra o resto
    assert len(calls["render"]) + len(calls["static"]) == 4 and urls == []
    assert "teto de 4 pedidos" in capsys.readouterr().err
    calls, renderer, fetch, sleep = _fakes()
    index = _page(_links("/ajuda-nao-existe/a/", "/ajuda-vendas/como-antecipar/"))
    urls, _ = mod.discover({"from": [f"{BASE}/ajuda/"], "path_prefix": "/ajuda-", "depth": 1}, [HOST],
                           fetch=fetch, renderer=lambda url, hosts: index, sleep=sleep)
    assert urls == [f"{BASE}/ajuda-vendas/como-antecipar/"]  # o 404 é avisado e pulado
    assert "404" in capsys.readouterr().err


def test_name_pages_keeps_known_keys_and_disambiguates_same_slug():
    mod = _mod()
    pages = {"como-antecipar": f"{BASE}/ajuda-vendas/como-antecipar/"}
    out = mod.name_pages([f"{BASE}/ajuda-vendas/como-antecipar/", f"{BASE}/ajuda-pix/como-antecipar/",
                          f"{BASE}/ajuda-erros/Erro-12/"], pages)
    assert out == {"como-antecipar": f"{BASE}/ajuda-vendas/como-antecipar/",
                   "ajuda-pix-como-antecipar": f"{BASE}/ajuda-pix/como-antecipar/",
                   "erro-12": f"{BASE}/ajuda-erros/Erro-12/"}


def test_discovered_articles_are_ingested_from_the_html_already_fetched(tmp_path):
    """O artigo não é pedido 2 vezes ao site: o build lê o HTML da descoberta; a moldura sai como linha repetida."""
    from app import ingest

    mod = _mod()
    calls, renderer, fetch, sleep = _fakes()
    follow = {"from": [f"{BASE}/ajuda/"], "path_prefix": "/ajuda-", "depth": 2, "pause_s": 0}
    urls, html = mod.discover(follow, [HOST], fetch=fetch, renderer=renderer, sleep=sleep)
    pages = mod.name_pages(urls, {})
    n_static = len(calls["static"])
    getter = mod.make_fetcher("never", static=mod.cached(html, fetch))
    out = ingest.build(pages, tmp_path, [HOST], "aj", fetcher=getter, articles=True)
    assert len(calls["static"]) == n_static  # nenhum pedido novo
    text = "\n".join(r["text"] for recs in out.values() for r in recs)
    assert "R$ 50,00" in text and "Já é cliente" not in text and "cookies" not in text
    assert [r["id"] for r in out["como-antecipar"]] == ["aj-como-antecipar-01"] and set(out) == set(pages)
    (short,) = out["erro-12"]  # artigo curto: 1 trecho com o título do <header>, em vez de nenhum
    assert short["text"].startswith("Erro 12: falha de leitura do cartão") and len(short["text"]) < ingest.MIN_CHARS
    assert sorted(p.name for p in tmp_path.glob("*.jsonl")) == sorted(f"{s}.jsonl" for s in pages)
    saved = [json.loads(x) for x in (tmp_path / "como-antecipar.jsonl").read_text("utf-8").splitlines()]
    assert saved[0]["url"] == f"{BASE}/ajuda-vendas/como-antecipar/" and saved[0]["sha256"]
