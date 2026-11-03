"""Ingestão do corpus com render de JavaScript quando o HTML estático é casca vazia.

Uso: python scripts/ingest_render.py [--sources data/sources.json] [--group suporte] [--render auto|always|never]

Mesmo `app.ingest.build`, em duas passadas: 1ª com o HTML estático; as páginas que renderam até MIN_CHUNKS
trechos (o texto estático delas é só menu e aviso de cookie, que o build tira como linha repetida) entram numa 2ª
passada renderizadas no Chromium (scripts/render_page.js, Playwright do ambiente). No site do desafio, 3 de 15
páginas davam 0 trechos no estático e ~7,7 mil caracteres de texto renderizadas. O processo do navegador fica aqui,
fora do pacote do app (o app não abre processo: tests/test_security_asi.py).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="data/sources.json")
    ap.add_argument("--group", help="só um grupo de sources.json (padrão: todos)")
    ap.add_argument("--render", default="auto", choices=["auto", "always", "never"])
    args = ap.parse_args()
    cfg = ingest.load_sources(Path(args.sources))
    total = 0
    for name, group in cfg["groups"].items():
        if args.group and name != args.group:
            continue
        out_dir, hosts, prefix = Path("data/knowledge") / name, cfg["allowed_hosts"], group.get("prefix", name)
        result = ingest.build(group["pages"], out_dir, hosts, prefix, fetcher=make_fetcher(args.render))
        thin = {slug: group["pages"][slug] for slug, recs in result.items() if len(recs) <= MIN_CHUNKS}
        if thin and args.render != "never":  # 2ª passada: SÓ as páginas finas, renderizadas, sem repetir o corpus
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
