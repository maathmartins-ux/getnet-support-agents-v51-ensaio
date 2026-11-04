"""Ingestão do corpus (motor do kit): baixa as páginas listadas em data/sources.json e grava trechos LITERAIS.

Uso: python -m app.ingest [--sources data/sources.json] [--group produtos]

Cada linha: {id, title, url, context, text, fetched_at, sha256}. `text` é recorte literal do HTML (só texto visível,
sem script/menu/rodapé), em trechos de 300–800 caracteres, cortados de preferência na troca de seção (h1/h2/h3).
`context` = "título da página › seção mais próxima": vai para o índice junto do texto, nunca para dentro de `text`.
Linha repetida em metade das páginas é chrome do site
(menu, banner de cookie) e sai. Só baixa de `allowed_hosts` (o domínio do país do enunciado).

Escrever um ingest no relógio custou ~30 min numa tentativa real; no kit, quem monta o corpus só preenche
data/sources.json. Na nuvem, o domínio precisa estar liberado na rede do ambiente (scripts/cloud_probe.py).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

MIN_CHARS, MAX_CHARS = 300, 800

SKIP_TAGS = {"script", "style", "noscript", "svg", "header", "footer", "nav", "template", "iframe", "form"}
BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "li",
    "ul",
    "ol",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "br",
    "tr",
    "td",
    "th",
    "table",
    "dt",
    "dd",
    "button",
    "a",
    "span_block",
    "summary",
    "details",
    "main",
    "aside",
}


def load_sources(path: Path) -> dict:
    """data/sources.json: {"allowed_hosts": [...], "groups": {"<pasta>": {"prefix": "...", "pages": {slug: url}}}}."""
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if not cfg.get("allowed_hosts"):
        raise ValueError(f"{path}: allowed_hosts vazio (o domínio do país do enunciado, nada mais)")
    return cfg


def is_allowed(url: str, allowed_hosts: set[str] | list[str]) -> bool:
    return urlparse(url).hostname in set(allowed_hosts)


HEADINGS = {"h1", "h2", "h3"}  # seção = o h1/h2/h3 visível mais próximo acima da linha


def cut_on_section() -> bool:
    """INGEST_SECTION_CUT=on corta o trecho na troca de seção (h1/h2/h3) quando ele já tem MIN_CHARS. Padrão: off.

    Medido: corpus real re-ingerido do mesmo HTML, gold de passagens ESSENCIAIS rotulado às cegas
    por 2 rotuladores (concordância 0,81), denso e5 + rerank bge: Recall@3 0,747 com o corte por seção e o contexto
    indexado; 0,787 só sem o corte; 0,79 só sem o contexto; 0,82 sem os dois (o ingest anterior, sem nenhum, deu 0,85).
    Em página de FAQ o h2/h3 não separa assunto: cortar nele partia resposta ao meio.
    """
    return os.getenv("INGEST_SECTION_CUT", "off").lower() == "on"
SECTION_CHARS = 120  # seção mais longa que isso é parágrafo estilizado como título: corta
TABLE_HEADER_ROWS = 3  # no máximo 3 linhas de cabeçalho (cabeçalho agrupado com colspan + nomes das colunas)


class TableLine(str):
    """Linha de uma <table> já rotulada ("Débito — 2 dias úteis: 1,89%"). É `str` (compara e grava igual a texto);
    os atributos dizem ao chunker que ela não se cola, não se descarta por curta e só se corta entre linhas."""

    table: int
    header: bool

    def __new__(cls, text: str, table: int, header: bool = False) -> TableLine:
        obj = super().__new__(cls, text)
        obj.table, obj.header = table, header
        return obj


def _clean(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _has_digit(cell: str) -> bool:
    return bool(re.search(r"\d", cell))


def render_table(rows: list[list[tuple[str, bool, int]]], table: int) -> list[TableLine]:
    """Linhas de células [(texto, é_th, colspan)] → linhas de texto em que cada valor leva o rótulo da coluna.

    Uma tabela de taxas célula a célula ("Débito:", "1,89%", "1,95%") perde o sentido se o "1,95%" não disser a que
    coluna pertence; as células curtas também caíam como menu. Cabeçalho = linhas iniciais só de <th> ou sem nenhum
    dígito (até TABLE_HEADER_ROWS); colspan repete o rótulo nas colunas cobertas. A 1ª linha devolvida é o
    cabeçalho (o chunker a repete em cada pedaço de uma tabela longa).
    """
    grid = [[text for text, _, span in row for _ in range(max(1, span))] for row in rows]
    grid_th = [all(is_th for _, is_th, _ in row) for row in rows]
    cut = 0
    while cut < min(len(grid) - 1, TABLE_HEADER_ROWS) and (grid_th[cut] or not any(map(_has_digit, grid[cut][1:]))):
        cut += 1
    head, body = grid[:cut], grid[cut:]
    width = max((len(r) for r in grid), default=0)
    cols = [" ".join(dict.fromkeys(h[j] for h in head if j < len(h) and h[j])).strip(" :") for j in range(width)]
    out: list[TableLine] = []
    if any(cols):
        out.append(TableLine(" | ".join(c for c in cols if c), table, header=True))
    for row in body:
        cells = [c for c in row if c]
        if not cells:
            continue
        if not head or len(row) < 2:
            out.append(TableLine(" · ".join(cells), table))
            continue
        label = row[0].strip(" :")
        if cols[0] and label and not re.search(r"[^\W\d_]", label):  # rótulo só numérico ("2"): "Parcelas 2"
            label = f"{cols[0]} {label}"
        values = [f"{cols[j]}: {v}" if cols[j] else v for j, v in enumerate(row[1:], 1) if v]
        out.append(TableLine(f"{label} — " + "; ".join(values) if label else "; ".join(values), table))
    return out


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[tuple[str, str]] = []  # (seção, linha)
        self._buf: list[str] = []
        self._skip = 0
        self._header = 0  # <header> abertos (também contam em _skip)
        self._lifted = 0  # _skip guardado enquanto lê o h1 de dentro de um <header>
        self.title = ""
        self._in_title = False
        self._title_done = False  # só o 1º <title> (o do <head>): o 2º, de JS ou de SVG, duplicava o título
        self._extra_titles = 0  # <title> além do 1º: texto que não aparece na página, pulado como script
        self.section = ""
        self._heading: list[str] | None = None
        self._tables = 0
        self._table_depth = 0  # tabela dentro de tabela: o texto da interna vai para a célula da externa
        self._rows: list[list[tuple[str, bool, int]]] = []
        self._cell: list[str] | None = None
        self._cell_meta: tuple[bool, int] = (False, 1)

    def _flush(self) -> None:
        line = _clean(self._buf)
        if line:
            self.lines.append((self.section, line))
        self._buf = []

    def _end_cell(self) -> None:
        if self._cell is not None:
            if not self._rows:
                self._rows.append([])
            self._rows[-1].append((_clean(self._cell), *self._cell_meta))
            self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "h1" and self._skip and self._skip == self._header:
            # h1 dentro de <header> (e de nada mais que se pula): é o título da página no banner do artigo (tema de
            # WordPress, central de ajuda), não o menu. Medido no desafio: 79 de 80 artigos da central tinham o h1
            # assim, e o trecho saía sem o nome do erro ("Erro ADQ 4-91") que o separa dos outros 21 erros.
            self._lifted, self._skip = self._skip, 0
        if tag in SKIP_TAGS:
            self._skip += 1
            self._header += tag == "header"
        elif tag == "title":
            if self._title_done or self._skip:
                self._skip += 1
                self._extra_titles += 1
            else:
                self._in_title = True
        if self._table_depth and not self._skip:
            self._table_tag(tag, attrs)
            return
        if tag == "table" and not self._skip:
            self._flush()
            self._table_depth, self._rows = 1, []
            return
        if tag in BLOCK_TAGS:
            self._flush()
        if tag in HEADINGS and not self._skip:
            self._heading = []

    def _table_tag(self, tag, attrs):
        if tag == "table":
            self._table_depth += 1
        elif self._table_depth > 1:
            return
        elif tag == "tr":
            self._end_cell()
            self._rows.append([])
        elif tag in ("td", "th"):
            self._end_cell()
            span = dict(attrs).get("colspan") or "1"
            self._cell, self._cell_meta = [], (tag == "th", int(span) if span.isdigit() else 1)
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and (self._skip or self._lifted):
            if self._skip:
                self._skip -= 1
            else:  # </header> antes do </h1> (HTML torto): fecha o que estava guardado
                self._lifted -= 1
            if tag == "header" and self._header:
                self._header -= 1
        elif tag == "title":
            if self._extra_titles:
                self._extra_titles -= 1
                self._skip -= bool(self._skip)
            else:
                self._title_done = self._title_done or self._in_title
                self._in_title = False
        if self._table_depth and not self._skip:
            if tag == "table":
                self._table_depth -= 1
                if not self._table_depth:
                    self._end_cell()
                    self._tables += 1
                    self.lines += [(self.section, ln) for ln in render_table(self._rows, self._tables)]
            elif tag in ("td", "th") and self._table_depth == 1:
                self._end_cell()
            return
        if tag in HEADINGS and self._heading is not None:
            heading = _clean(self._heading)
            if heading:
                self.section = heading[:SECTION_CHARS]  # antes do flush: a própria linha do título já é da seção
            self._heading = None
        if tag in BLOCK_TAGS:
            self._flush()
        if tag == "h1" and self._lifted:  # fim do h1 do <header>: o resto do cabeçalho volta a ser pulado
            self._skip, self._lifted = self._lifted, 0

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            if self._table_depth:
                if self._cell is not None:
                    self._cell.append(data)
                return
            self._buf.append(data)
            if self._heading is not None:
                self._heading.append(data)

    def close(self):
        super().close()
        if self._table_depth:  # tabela sem </table> no fim do HTML: renderiza o que veio
            self._end_cell()
            self._tables += 1
            self.lines += [(self.section, ln) for ln in render_table(self._rows, self._tables)]
            self._table_depth = 0
        self._flush()


SHORT = 15  # linha abaixo disso sozinha é botão/menu ("Saiba mais") ou célula de tabela ("R$ 79,90/mês")
KEEP_REPEATED = 80  # linha repetida em várias páginas com isso ou mais é conteúdo (tabela de preço): fica 1 vez


def glue_short(lines: list) -> list:
    """Junta linhas curtas consecutivas numa só ("Plano Básico · R$ 79,90/mês").

    Medido: a tabela de preços e faixas (células "Plano Básico", "R$ 79,90/mês") saía inteira por ter linhas < 15
    caracteres, e a pergunta que compara dois produtos da tabela ficava sem fonte.
    Juntas, as células viram uma linha de tabela; menus juntos viram uma linha repetida em toda página e saem
    pela regra de repetição.
    Aceita linhas soltas ou pares (seção, linha); a linha colada fica com a seção da primeira. Não cola através de
    uma troca de seção: o título curto ("O que é DIRF", h1 do artigo) colava no botão do fim da moldura de cima
    ("AVANÇAR · O que é DIRF") e a linha colada, única, escapava da regra de repetição.
    """
    pairs = [ln if isinstance(ln, tuple) else (None, ln) for ln in lines]
    out: list = []
    run: list[tuple] = []
    for item in [*pairs, None]:
        if item is not None and len(item[1]) < SHORT and not isinstance(item[1], TableLine):
            if run and item[0] != run[0][0]:
                out.append((run[0][0], " · ".join(t for _, t in run)))
                run = []
            run.append(item)
            continue
        if run:
            out.append((run[0][0], " · ".join(t for _, t in run)))
            run = []
        if item is not None:
            out.append(item)
    return [t if s is None else (s, t) for s, t in out]


def extract_sections(html: str) -> tuple[str, list[tuple[str, str]]]:
    """(título da página, [(seção, linha)]): a seção é o h1/h2/h3 mais próximo acima da linha ("" antes do 1º)."""
    p = _TextExtractor()
    p.feed(html)
    p.close()
    title = re.sub(r"\s+", " ", p.title).strip()
    return title, glue_short(p.lines)


def extract(html: str) -> tuple[str, list[str]]:
    title, pairs = extract_sections(html)
    return title, [t for _, t in pairs]


GLUE = " · "  # separador das células coladas por glue_short (e das linhas de tabela sem cabeçalho)


def _is_value(cell: str) -> bool:
    """Célula que é valor ("1,69%", "R$ 79,90/mês", "--"), não rótulo: começa sem letra."""
    return not re.match(r"\W*[^\W\d_]", cell)


def _split_cells(line: str, hi: int, sep: str) -> list[str]:
    """Corta uma linha de células só entre células, nunca no meio de uma, e de preferência antes de um RÓTULO.

    "Débito · 1,69% · Crédito 1x · 3,79% · …" (tabela em <div>) passava de MAX_CHARS sem ponto final e era truncada
    em `[:hi]` ou descartada; cortar antes de um valor separaria "Crédito 1x" do "3,79%" dele.
    """
    cells, pieces, cur = line.split(sep), [], []
    # pedaços de tamanho parecido: cortar sempre no teto deixava um rabo < MIN_CHARS que o chunker descartava
    limit = min(hi, int(len(line) / math.ceil(len(line) / hi) * 1.15))
    for cell in cells:
        if cur and len(sep.join([*cur, cell])) > limit:
            back = next((i for i in range(len(cur) - 1, 0, -1) if not _is_value(cur[i])), len(cur))
            pieces.append(sep.join(cur[:back]))
            cur = cur[back:]
        cur.append(cell)
    if cur:
        pieces.append(sep.join(cur))
    return [p for piece in pieces for p in ([piece] if len(piece) <= hi else _split_long(piece, hi))]


def _split_long(line: str, hi: int) -> list[str]:
    if len(line) <= hi:
        return [line]
    for sep in ("; ", GLUE):  # linha de tabela rotulada ou células coladas: corta entre células
        if sep in line and not re.search(r"[.!?]\s", line):
            return _split_cells(line, hi, sep)
    pieces, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", line):
        if cur and len(cur) + 1 + len(sent) > hi:
            pieces.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        pieces.append(cur[:hi])
    return pieces


# Separador entre linhas do HTML (blocos <p>, <li>, <div>) dentro do mesmo trecho: quebra de linha, não espaço. Uma
# lista em blocos ("Acima de R$ 20mil | Get Clássica" / "Acima de R$ 40mil | Get Clássica ou Get Smart") colada com
# espaço vira "...Get Clássica Acima de R$ 40mil..." e o redator lia a faixa errada. Tem o mesmo tamanho do espaço:
# os cortes dos trechos (e os ids) não mudam. Pedaços de uma MESMA linha longa (_split_long) seguem com espaço.
LINE_SEP = "\n"


def _chunk_prose(pieces: list[tuple[str, str] | tuple[str, str, str]], lo: int,
                 hi: int) -> tuple[list[tuple[str, str]], str, str]:
    """Trechos de texto corrido + a sobra (< lo) do fim, que vira legenda da tabela seguinte ou emenda no anterior.

    Cada peça é (seção, texto) ou (seção, texto, separador do texto anterior); sem separador, LINE_SEP."""
    out: list[tuple[str, str]] = []
    cur, cur_sec = "", ""
    section_cut = cut_on_section()
    for sec, piece, *rest in pieces:
        sep = rest[0] if rest else LINE_SEP
        if section_cut and cur and sec != cur_sec and len(cur) >= lo:
            out.append((cur_sec, cur))
            cur = ""
        if cur and len(cur) + 1 + len(piece) > hi:
            if len(cur) >= lo:
                out.append((cur_sec, cur))
                cur, cur_sec = piece, sec
                continue
            cur = ""  # sobra curta que não cabe com a próxima peça: descarta (abaixo do mínimo)
        if not cur:
            cur_sec = sec
        cur = (f"{cur}{sep}{piece}" if cur else piece).strip()
        if len(cur) >= lo and piece.endswith((".", "!", "?", ":")):
            out.append((cur_sec, cur))
            cur = ""
    if len(cur) >= lo:
        out.append((cur_sec, cur))
        cur = ""
    return out, cur, cur_sec


def _chunk_table(rows: list[TableLine], sec: str, hi: int, caption: str = "") -> list[tuple[str, str]]:
    """Tabela inteira num trecho se couber; senão, cortada ENTRE linhas, com o cabeçalho repetido em cada pedaço.

    Linhas separadas por quebra de linha: cada uma já carrega o rótulo da coluna (render_table), então um pedaço
    sozinho continua legível ("Crédito à vista — 2 dias úteis: 3,99%").
    """
    header = [rows[0]] if rows and rows[0].header else []
    body = [p for r in rows[len(header):] for p in _split_long(r, hi)]
    if not body:
        body, header = [str(h) for h in header], []
    lead = [caption] if caption and len("\n".join([caption, *header, body[0]])) <= hi else []
    out: list[tuple[str, str]] = []
    cur = [*lead, *header]
    fixed = len(cur)
    for row in body:
        if len(cur) > fixed and len("\n".join([*cur, row])) > hi:
            out.append((sec, "\n".join(cur)))
            cur = [*header]
            fixed = len(cur)
        cur.append(row)
    if len(cur) > fixed:
        out.append((sec, "\n".join(cur)))
    return out


def chunk_sections(lines: list[tuple[str, str]], lo: int = MIN_CHARS, hi: int = MAX_CHARS) -> list[tuple[str, str]]:
    """Agrupa linhas consecutivas em trechos de lo..hi caracteres: [(seção do 1º pedaço, trecho)].

    Corta em fim de frase depois de lo; corta também na troca de seção quando o trecho já tem lo (o trecho não
    mistura duas seções sem necessidade). Seção curta demais (< lo) emenda na seguinte. Linha > hi: corte em frase
    (ou entre células, se for linha de células). Tabela (TableLine) vira trecho próprio, inteira ou cortada entre
    linhas com o cabeçalho repetido, mesmo abaixo de lo: tabela pequena de taxas é conteúdo, não sobra.
    """
    segments: list[tuple[int | None, list[tuple[str, str]]]] = []
    for sec, line in lines:
        key = line.table if isinstance(line, TableLine) else None
        if not segments or segments[-1][0] != key:
            segments.append((key, []))
        segments[-1][1].append((sec, line))
    out: list[tuple[str, str, bool]] = []
    carry, carry_sec = "", ""
    for i, (key, seg) in enumerate(segments):
        if key is not None:
            sec = carry_sec if carry else seg[0][0]
            table = _chunk_table([ln for _, ln in seg], sec, hi, carry)
            if carry and not (table and table[0][1].startswith(carry)):
                _attach(out, carry, hi)  # legenda não coube junto da tabela: regra antiga da sobra
            out += [(s, c, True) for s, c in table]
            carry = ""
            continue
        pieces = [(sec, p, " " if j else LINE_SEP) for sec, line in seg for j, p in enumerate(_split_long(line, hi))]
        chunks, carry, carry_sec = _chunk_prose(pieces, lo, hi)
        out += [(s, c, False) for s, c in chunks]
        nxt_is_table = i + 1 < len(segments) and segments[i + 1][0] is not None
        if carry and not nxt_is_table:
            carry = _attach(out, carry, hi)
    return [(s, c) for s, c, table in out if table or lo <= len(c) <= hi]


def _attach(out: list[tuple[str, str, bool]], tail: str, hi: int) -> str:
    """Sobra curta emenda no último trecho de texto se couber (regra antiga); devolve "" quando emendou."""
    if out and not out[-1][2] and len(out[-1][1]) + 1 + len(tail) <= hi:
        out[-1] = (out[-1][0], f"{out[-1][1]}{LINE_SEP}{tail}", False)
        return ""
    return tail


def chunk(lines: list[str], lo: int = MIN_CHARS, hi: int = MAX_CHARS) -> list[str]:
    """Agrupa linhas consecutivas em trechos de lo..hi caracteres; linha maior que hi é cortada em frase."""
    return [c for _, c in chunk_sections([("", ln) for ln in lines], lo, hi)]


def context(title: str, section: str) -> str:
    """"título da página › seção"; sem seção (ou seção igual ao título), só o título."""
    return f"{title} › {section}" if section and section != title else title


def records(slug: str, url: str, title: str, chunks: list[str], fetched_at: str, prefix: str = "doc",
            contexts: list[str] | None = None) -> list[dict]:
    rows = []
    for i, text in enumerate(chunks, 1):
        row = {"id": f"{prefix}-{slug}-{i:02d}", "title": title, "url": url}
        if contexts is not None:
            row["context"] = contexts[i - 1]
        row |= {"text": text, "fetched_at": fetched_at, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        rows.append(row)
    return rows


def fetch(url: str, allowed_hosts: set[str] | list[str]) -> str:
    """HTML estático da página. Página montada por JavaScript (casca vazia) é renderizada por
    scripts/ingest_render.py, que chama `build` com outro `fetcher` (o app não abre processo)."""
    if not is_allowed(url, allowed_hosts):
        raise ValueError(f"domínio fora da lista de sources.json: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (support-agents ingest)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


SHORT_PAGE = 200  # modo artigo: página inteira abaixo de MIN_CHARS e com isso ou mais vira 1 trecho


def build(pages: dict[str, str], out_dir: Path, allowed_hosts, prefix: str = "doc", fetcher=fetch,
          articles: bool = False, drop: frozenset[str] | set[str] = frozenset()) -> dict[str, list[dict]]:
    """Baixa, extrai e grava um grupo.

    Linha curta repetida em metade das páginas (ou 3+) é chrome do site (menu, cookie) e sai. Linha LONGA repetida
    (>= KEEP_REPEATED, ex.: tabela de preços que o site repete em toda página de produto) é conteúdo: fica só na
    primeira página em que aparece, em vez de sumir de todas.

    `articles` (artigos de central de ajuda, scripts/ingest_render.py --discover): a página cujo texto inteiro fica
    entre SHORT_PAGE e MIN_CHARS vira 1 trecho, em vez de nenhum. Medido no desafio: o erro S-2074 (título + 6
    passos, 291 caracteres) é a resposta inteira e saía do corpus. `drop`: linhas de moldura que a regra de repetição
    não pega (variante de bloco de botões em poucas páginas), listadas em `chrome` do grupo no sources.json; só a
    linha inteira igual sai. Página sem trecho não deixa arquivo (o 0 byte de get-ajuda.jsonl foi apontado na
    avaliação); um arquivo velho dela é apagado.
    """
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    parsed = {slug: (url, *extract_sections(fetcher(url, allowed_hosts))) for slug, url in pages.items()}
    freq = Counter(line for _, _, pairs in parsed.values() for line in {t for _, t in pairs})
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, list[dict]] = {}
    seen: set[str] = set()
    kept_once: set[str] = set()

    def keep(line: str) -> bool:
        if len(line) < SHORT or line in drop:
            return False
        if freq[line] < max(3, len(parsed) // 2):
            return True
        if len(line) >= KEEP_REPEATED and line not in kept_once:
            kept_once.add(line)
            return True
        return False

    for slug, (url, title, pairs) in parsed.items():
        lines = [(sec, ln) for sec, ln in pairs if keep(ln)]
        chunks = chunk_sections(lines)
        if not chunks and articles and SHORT_PAGE <= len(whole := LINE_SEP.join(t for _, t in lines)) <= MAX_CHARS:
            chunks = [(lines[0][0], whole)]
        recs = []
        for r in records(slug, url, title, [c for _, c in chunks], fetched_at, prefix,
                         contexts=[context(title, sec) for sec, _ in chunks]):
            if r["sha256"] not in seen:
                seen.add(r["sha256"])
                recs.append(r)
        result[slug] = recs
        path = out_dir / f"{slug}.jsonl"
        if not recs:
            path.unlink(missing_ok=True)
            continue
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="data/sources.json")
    ap.add_argument("--group", help="só um grupo de sources.json (padrão: todos)")
    args = ap.parse_args()
    cfg = load_sources(Path(args.sources))
    total = 0
    for name, group in cfg["groups"].items():
        if args.group and name != args.group:
            continue
        result = build(group["pages"], Path("data/knowledge") / name, cfg["allowed_hosts"], group.get("prefix", name))
        for slug, recs in result.items():
            print(f"{name}/{slug}: {len(recs)} trechos")
        total += sum(len(r) for r in result.values())
    print(f"total: {total}")


if __name__ == "__main__":
    main()
