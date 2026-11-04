"""Ingestão do corpus com render de JavaScript quando o HTML estático é casca vazia.

Uso: python scripts/ingest_render.py [--sources data/sources.json] [--group suporte] [--render auto|always|never]
     python scripts/ingest_render.py --discover --group ajuda   # central de ajuda: acha os artigos, depois ingere

Mesmo `app.ingest.build`, em duas passadas: 1ª com o HTML estático; as páginas que renderam até MIN_CHUNKS
trechos (o texto estático delas é só menu e aviso de cookie, que o build tira como linha repetida) entram numa 2ª
passada renderizadas no Chromium (scripts/render_page.js, Playwright do ambiente). No site do desafio, 3 de 15
páginas davam 0 trechos no estático e ~7,7 mil caracteres de texto renderizadas. O processo do navegador fica aqui,
fora do pacote do app (o app não abre processo: tests/test_security_asi.py).

Central de ajuda (`--discover`): o grupo com `follow` em sources.json lista as páginas-índice, não os artigos:
{"from": [url do índice], "path_prefix": "/ajuda-", "depth": 2, "max_pages": 300, "pause_s": 1.0}. O índice e as
categorias costumam ser montados por JavaScript (no estático, só a moldura do site) e o artigo tem o texto no HTML
estático. Por isso: o índice é renderizado; cada link dele no mesmo host e com o caminho no prefixo é baixado no
estático; com texto próprio é artigo, sem texto próprio é lista (categoria, "ver mais") e é renderizada no salto
seguinte, até `depth` saltos. Lista no último salto (vídeo só com título, página vazia) fica de fora. Os artigos
vão para `pages` do grupo (chave = último segmento do caminho) e o grupo é ingerido na mesma passada, com o HTML que
a descoberta já baixou. Medido no desafio: os 2 índices da central davam 0 trechos (só títulos montados por JS) e os
artigos, com o passo a passo e os valores, nunca entravam no corpus.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app import ingest  # noqa: E402

RENDER_SCRIPT = ROOT / "scripts" / "render_page.js"
RENDER_MIN_CHARS = 400
MIN_CHUNKS = 1  # página com até isso de trechos na 1ª passada é renderizada na 2ª


def render(url: str, allowed_hosts) -> str:
    """HTML depois do JavaScript. Só host permitido (mesma lista do fetch estático)."""
    if not ingest.is_allowed(url, allowed_hosts):
        raise ValueError(f"domínio fora da lista de sources.json: {url}")
    done = subprocess.run(["node", str(RENDER_SCRIPT), url], capture_output=True, text=True, timeout=90)
    if done.returncode != 0:
        raise RuntimeError(f"render falhou: {done.stderr.strip()[:200]}")
    return done.stdout


def text_chars(html: str) -> int:
    _, pairs = ingest.extract_sections(html)
    return sum(len(t) for _, t in pairs)


def make_fetcher(mode: str = "auto", static=ingest.fetch, renderer=render):
    """auto: renderiza só a casca vazia (< RENDER_MIN_CHARS); always: sempre; never: só estático.
    Render que falha cai no estático, com aviso."""
    def fetch(url: str, allowed_hosts) -> str:
        html = "" if mode == "always" else static(url, allowed_hosts)
        if mode == "never" or (mode == "auto" and text_chars(html) >= RENDER_MIN_CHARS):
            return html
        try:
            rendered = renderer(url, allowed_hosts)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            print(f"AVISO render {url}: {exc}", file=sys.stderr)
            return html or static(url, allowed_hosts)
        if text_chars(rendered) > text_chars(html):
            print(f"renderizada: {url} ({text_chars(html)} → {text_chars(rendered)} caracteres)", file=sys.stderr)
            return rendered
        return html
    return fetch


CHROME_LINES = {"política cookie", "permitir · dispensar", "preferências de cookie"}


def render_thin(pages: dict[str, str], out_dir: Path, hosts, prefix: str, corpus: str,
                existing: dict[str, list[dict]] | None = None, renderer=None) -> dict[str, list[dict]]:
    """Renderiza só as páginas finas e grava só os arquivos delas: as outras páginas do grupo ficam intactas, e os
    trechos que a página fina já tinha ficam com o mesmo id (o gold e as respostas citam esses ids); os novos entram
    depois, numerados em seguida. Linha que já está no corpus (o site repete blocos entre páginas) e linha de
    moldura que sobrou do navegador saem antes de cortar os trechos."""
    import json
    from datetime import UTC, datetime

    renderer = renderer or render
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    taken: set[str] = set()
    out: dict[str, list[dict]] = {}
    for slug, url in pages.items():
        try:
            title, pairs = ingest.extract_sections(renderer(url, hosts))
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
            print(f"AVISO render {url}: {exc}", file=sys.stderr)
            continue
        fresh = []
        for sec, ln in pairs:
            key = " ".join(ln.split())
            if len(key) < ingest.SHORT or key.lower() in CHROME_LINES or key in corpus or key in taken:
                continue
            taken.add(key)
            fresh.append((sec, ln))
        chunks = ingest.chunk_sections(fresh)
        before = list((existing or {}).get(slug) or [])
        new = ingest.records(slug, url, title, [c for _, c in chunks], fetched_at, prefix,
                             contexts=[ingest.context(title, sec) for sec, _ in chunks])
        for i, r in enumerate(new, len(before) + 1):
            r["id"] = f"{prefix}-{slug}-{i:02d}"
        recs = before + new
        out_dir.mkdir(parents=True, exist_ok=True)
        with (out_dir / f"{slug}.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"renderizada: {url} ({len(new)} trechos novos, {len(before)} mantidos)", file=sys.stderr)
        out[slug] = recs
    return out


# --- descoberta de artigos (central de ajuda) -------------------------------------------------------------------
FOLLOW_DEPTH = 2  # índice → categoria → artigo
FOLLOW_MAX_PAGES = 300  # teto de pedidos (render + estático) da descoberta
FOLLOW_PAUSE_S = 1.0  # pausa educada entre pedidos ao mesmo site
# texto próprio (sem a moldura do site) para a página contar como artigo; o mesmo piso do artigo curto no build.
# Medido no desafio: categoria (casca de JS) 0–52 caracteres; o menor artigo, 252.
ARTICLE_MIN_CHARS = ingest.SHORT_PAGE


class _Hrefs(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.canonical = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.hrefs.append(a["href"].strip())
        elif tag == "link" and "canonical" in (a.get("rel") or "").lower().split() and a.get("href"):
            self.canonical = self.canonical or a["href"].strip()


def canonical(url: str) -> str:
    """Sem âncora nem query, host em minúsculas, caminho com barra no fim: /x, /x/ e /x/#passo são a mesma página."""
    p = urlparse(url)
    path = p.path or "/"
    if not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]:
        path += "/"
    host = (p.hostname or "") + (f":{p.port}" if p.port else "")
    return urlunparse((p.scheme.lower(), host, path, "", "", ""))


def links(html: str, base: str, hosts, path_prefix: str) -> list[str]:
    """Links <a href> da página para o MESMO host (e permitido) com o caminho começando em `path_prefix`: canônicos,
    na ordem da página, sem repetir e sem a própria página."""
    parser = _Hrefs()
    parser.feed(html)
    here = canonical(base)
    out: list[str] = []
    for href in parser.hrefs:
        url = canonical(urljoin(base, href))
        p = urlparse(url)
        if (p.scheme in ("http", "https") and p.hostname == urlparse(here).hostname and ingest.is_allowed(url, hosts)
                and p.path.startswith(path_prefix) and url != here and url not in out):
            out.append(url)
    return out


def canonical_link(html: str, base: str) -> str:
    """URL de <link rel="canonical"> (canônica), "" sem ela. O site que redireciona ou copia a página avisa aqui."""
    parser = _Hrefs()
    parser.feed(html)
    return canonical(urljoin(base, parser.canonical)) if parser.canonical else ""


def own_chars(pages: dict[str, str]) -> dict[str, int]:
    """Caracteres de texto PRÓPRIO de cada página no HTML estático: sem a moldura do site (linha que aparece em metade
    das páginas, ou em 3+, a mesma regra do ingest.build) nem linha curta de botão. Casca montada por JavaScript dá
    só o título da categoria (~20 caracteres); artigo dá o passo a passo."""
    lines = {u: {t for _, t in ingest.extract_sections(h)[1]} for u, h in pages.items()}
    freq = Counter(t for ls in lines.values() for t in ls)
    cut = max(3, len(pages) // 2)
    return {u: sum(len(t) for t in ls if len(t) >= ingest.SHORT and freq[t] < cut) for u, ls in lines.items()}


def discover(follow: dict, hosts, fetch=ingest.fetch, renderer=None, sleep=time.sleep,
             skip=()) -> tuple[list[str], dict[str, str]]:
    """(URLs dos artigos na ordem em que apareceram, {URL: HTML estático}) a partir das páginas-índice de `follow`.

    Cada salto renderiza as listas (no 1º, o índice) e baixa no estático os links novos delas (mesmo host, caminho em
    `path_prefix`, fora de `skip`), separados por texto próprio (own_chars sobre todas as páginas já baixadas, o
    estático do índice inclusive, para achar a moldura mesmo num salto pequeno): >= ARTICLE_MIN_CHARS é artigo; abaixo,
    lista, renderizada no salto seguinte. Página cuja rel=canonical já foi vista (ou está em `skip`) é cópia e sai: no
    desafio, um "artigo" redirecionava para a página de maquininhas já ingerida e outro era o mesmo texto em 2
    categorias. `pause_s` entre pedidos e no máximo `max_pages` pedidos (render + estático); página que falha é
    avisada e pulada.
    """
    renderer = renderer or render
    prefix = follow["path_prefix"]
    depth = int(follow.get("depth", FOLLOW_DEPTH))
    cap = int(follow.get("max_pages", FOLLOW_MAX_PAGES))
    pause = float(follow.get("pause_s", FOLLOW_PAUSE_S))
    done = 0

    def polite(get, url: str) -> str | None:
        nonlocal done
        if done >= cap:
            return None
        if done:
            sleep(pause)
        done += 1
        try:
            return get(url, hosts)
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
            print(f"AVISO descoberta {url}: {exc}", file=sys.stderr)
            return None

    listings = [canonical(u) for u in follow["from"]]
    seen = set(listings) | {canonical(u) for u in skip}
    static: dict[str, str] = {}
    for url in listings:  # o estático do índice é só a moldura do site: ensina o own_chars o que tirar
        if (html := polite(fetch, url)) is not None:
            static[url] = html
    articles: list[str] = []
    for hop in range(1, depth + 1):
        found: list[str] = []
        for url in listings:
            html = polite(renderer, url)
            for link in links(html or "", url, hosts, prefix):
                if link not in seen:
                    seen.add(link)
                    found.append(link)
        for url in found:
            if (html := polite(fetch, url)) is None:
                continue
            canon = canonical_link(html, url)
            if canon and canon != url:  # a página diz que é cópia de outra (redirect, mesmo artigo em 2 categorias)
                if canon in seen:
                    print(f"descoberta: {url} é a mesma página de {canon} (rel=canonical): fora", file=sys.stderr)
                    continue
                seen.add(canon)  # a original não é baixada de novo se aparecer depois
            static[url] = html
        own = own_chars(static)
        articles += [u for u in found if u in own and own[u] >= ARTICLE_MIN_CHARS]
        listings = [u for u in found if u in own and own[u] < ARTICLE_MIN_CHARS]
        print(f"descoberta salto {hop}: {len(found)} links, {len(articles)} artigos até aqui, "
              f"{len(listings)} listas{' (fora: último salto)' if hop == depth else ''}", file=sys.stderr)
    if done >= cap:
        print(f"AVISO descoberta: teto de {cap} pedidos atingido (max_pages); a lista pode estar incompleta",
              file=sys.stderr)
    return articles, {u: static[u] for u in articles}


def name_pages(urls: list[str], pages: dict[str, str]) -> dict[str, str]:
    """`pages` + os artigos novos, chave = último segmento do caminho (o mesmo nome em duas categorias leva o da
    categoria na frente). URL já listada fica com a chave que tinha."""
    out = dict(pages)
    known = {canonical(u) for u in out.values()}
    for url in urls:
        if canonical(url) in known:
            continue
        parts = [p for p in urlparse(url).path.split("/") if p] or [urlparse(url).hostname or "index"]
        slug, n = parts[-1].lower(), 2
        while slug in out:
            slug = "-".join(parts[-2:]).lower() if n == 2 else f"{'-'.join(parts[-2:]).lower()}-{n}"
            n += 1
        out[slug] = url
        known.add(canonical(url))
    return out


def cached(pages: dict[str, str], fetch):
    """Fetcher que devolve o HTML que a descoberta já baixou (o artigo não é pedido 2 vezes ao site)."""
    def get(url: str, allowed_hosts) -> str:
        return pages.get(canonical(url)) or fetch(url, allowed_hosts)
    return get


def polite_fetch(fetch, pause: float, sleep=time.sleep):
    """O mesmo fetcher com pausa entre pedidos (só o que vai ao site; o que veio do cache não espera)."""
    state = {"n": 0}

    def get(url: str, allowed_hosts) -> str:
        if state["n"]:
            sleep(pause)
        state["n"] += 1
        return fetch(url, allowed_hosts)
    return get


def run_discovery(cfg: dict, name: str, sources: Path) -> dict[str, str]:
    """Descobre os artigos do grupo `name`, grava `pages` em sources.json e devolve o HTML estático já baixado."""
    group = cfg["groups"][name]
    others = [u for g, grp in cfg["groups"].items() if g != name for u in (grp.get("pages") or {}).values()]
    urls, html = discover(group["follow"], cfg["allowed_hosts"], skip=others)
    before = dict(group.get("pages") or {})
    group["pages"] = name_pages(urls, before)
    sources.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"descoberta {name}: {len(urls)} artigos ({len(group['pages']) - len(before)} novos) → {sources}",
          file=sys.stderr)
    return html


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="data/sources.json")
    ap.add_argument("--group", help="só um grupo de sources.json (padrão: todos)")
    ap.add_argument("--render", default="auto", choices=["auto", "always", "never"])
    ap.add_argument("--discover", action="store_true",
                    help="só os grupos com `follow`: acha os artigos a partir dos índices, grava `pages` e ingere")
    args = ap.parse_args()
    cfg = ingest.load_sources(Path(args.sources))
    total = 0
    for name, group in cfg["groups"].items():
        if (args.group and name != args.group) or (args.discover and not group.get("follow")):
            continue  # --discover nunca re-ingere um grupo sem `follow` (os ids dele estão no gold e nas respostas)
        out_dir, hosts, prefix = Path("data/knowledge") / name, cfg["allowed_hosts"], group.get("prefix", name)
        follow = group.get("follow")
        static = ingest.fetch
        if follow:  # artigo de central de ajuda: pausa entre pedidos e o HTML que a descoberta já trouxe
            static = polite_fetch(ingest.fetch, float(follow.get("pause_s", FOLLOW_PAUSE_S)))
            if args.discover:
                static = cached(run_discovery(cfg, name, Path(args.sources)), static)
        result = ingest.build(group["pages"], out_dir, hosts, prefix, fetcher=make_fetcher(args.render, static=static),
                              articles=bool(follow), drop=frozenset(group.get("chrome") or ()))
        thin = {slug: group["pages"][slug] for slug, recs in result.items() if len(recs) <= MIN_CHUNKS}
        # artigo descoberto tem texto no estático por construção (é o critério da descoberta): renderizar não traz nada
        if thin and args.render != "never" and not follow:  # 2ª passada: SÓ as páginas finas, sem repetir o corpus
            corpus = "\n".join(" ".join(r["text"].split()) for recs in result.values() for r in recs)
            for slug, recs in render_thin(thin, out_dir, hosts, prefix, corpus, existing=result).items():
                result[slug] = recs
        for slug, recs in result.items():
            print(f"{name}/{slug}: {len(recs)} trechos")
        total += sum(len(r) for r in result.values())
    print(f"total: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
