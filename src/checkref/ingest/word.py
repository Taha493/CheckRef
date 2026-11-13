"""DOCX ingestion: paragraphs → styled spans with resolved formatting (spec §5 ①).

Run formatting is resolved in this order: direct run properties, then the character style
(and its basedOn chain), combined with the paragraph style chain, then document defaults.
For the toggle properties italic/bold, the character-style and paragraph-style values are
XOR-ed, as Word does; direct formatting always wins.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import docx
from docx.oxml.ns import qn
from lxml import etree

from checkref.models import Document, Line, Span

TWIPS_PER_POINT = 20
SINGLE_LINE = 240  # w:spacing w:line value for single spacing when lineRule is "auto"


def _on(el: etree._Element | None) -> bool | None:
    """Value of a toggle property element such as <w:i/> (None = not set)."""
    if el is None:
        return None
    return el.get(qn("w:val"), "true").lower() not in {"0", "false", "off", "none"}


class _Styles:
    def __init__(self, document: docx.document.Document) -> None:
        root = document.styles.element
        self.by_id = {s.get(qn("w:styleId")): s for s in root.findall(qn("w:style"))}
        defaults = root.find(qn("w:docDefaults"))
        self.default_rpr = self.default_ppr = None
        if defaults is not None:
            self.default_rpr = defaults.find(f"{qn('w:rPrDefault')}/{qn('w:rPr')}")
            self.default_ppr = defaults.find(f"{qn('w:pPrDefault')}/{qn('w:pPr')}")
        self.default_para = next(
            (
                style_id
                for style_id, s in self.by_id.items()
                if s.get(qn("w:type")) == "paragraph" and s.get(qn("w:default")) in {"1", "true"}
            ),
            None,
        )

    def chain(self, style_id: str | None) -> list[etree._Element]:
        out, seen = [], set()
        while style_id and style_id in self.by_id and style_id not in seen:
            seen.add(style_id)
            style = self.by_id[style_id]
            out.append(style)
            based = style.find(qn("w:basedOn"))
            style_id = based.get(qn("w:val")) if based is not None else None
        return out

    def name(self, style_id: str | None) -> str | None:
        style = self.by_id.get(style_id or "")
        el = style.find(qn("w:name")) if style is not None else None
        return el.get(qn("w:val")) if el is not None else None

    def chain_prop(self, style_id: str | None, container: str, prop: str) -> etree._Element | None:
        for style in self.chain(style_id):
            el = style.find(f"{qn(container)}/{qn(prop)}")
            if el is not None:
                return el
        return None


def _toggle(run_rpr, char_style, para_style, styles: _Styles, prop: str) -> bool:
    direct = _on(run_rpr.find(qn(prop))) if run_rpr is not None else None
    if direct is not None:
        return direct
    from_char = _on(styles.chain_prop(char_style, "w:rPr", prop))
    from_para = _on(styles.chain_prop(para_style, "w:rPr", prop))
    if from_char is None and from_para is None:
        default = styles.default_rpr.find(qn(prop)) if styles.default_rpr is not None else None
        return bool(_on(default))
    return bool(from_char) ^ bool(from_para)


def _size(run_rpr, char_style, para_style, styles: _Styles) -> float:
    for el in (
        run_rpr.find(qn("w:sz")) if run_rpr is not None else None,
        styles.chain_prop(char_style, "w:rPr", "w:sz"),
        styles.chain_prop(para_style, "w:rPr", "w:sz"),
        styles.default_rpr.find(qn("w:sz")) if styles.default_rpr is not None else None,
    ):
        if el is not None and el.get(qn("w:val")):
            return int(el.get(qn("w:val"))) / 2  # half-points
    return 10.0  # Word's built-in default


def _ppr_prop(ppr, para_style, styles: _Styles, prop: str) -> etree._Element | None:
    if ppr is not None and ppr.find(qn(prop)) is not None:
        return ppr.find(qn(prop))
    el = styles.chain_prop(para_style, "w:pPr", prop)
    if el is None and styles.default_ppr is not None:
        el = styles.default_ppr.find(qn(prop))
    return el


def _twips(el, *attrs: str) -> float | None:
    if el is None:
        return None
    for attr in attrs:
        v = el.get(qn(attr))
        if v is not None:
            return int(v) / TWIPS_PER_POINT
    return None


def _run_text(run: etree._Element) -> str:
    parts = []
    for child in run:
        tag = etree.QName(child).localname
        if tag == "t":
            parts.append(child.text or "")
        elif tag in {"tab", "br", "cr"}:
            parts.append(" ")
        elif tag == "noBreakHyphen":
            parts.append("‑")
        elif tag == "softHyphen":
            parts.append("­")
        elif tag == "sym":
            parts.append(chr(int(child.get(qn("w:char"), "20"), 16)))
    return "".join(parts)


def _runs(p: etree._Element):
    """Runs in reading order, including those in hyperlinks and fields; skipping deletions."""
    for r in p.iter(qn("w:r")):
        if any(etree.QName(a).localname in {"del", "moveFrom"} for a in r.iterancestors()):
            continue
        yield r


def _paragraph(p: etree._Element, index: int, styles: _Styles) -> Line:
    ppr = p.find(qn("w:pPr"))
    pstyle_el = ppr.find(qn("w:pStyle")) if ppr is not None else None
    para_style = pstyle_el.get(qn("w:val")) if pstyle_el is not None else styles.default_para

    spans: list[Span] = []
    for r in _runs(p):
        text = _run_text(r)
        if not text:
            continue
        rpr = r.find(qn("w:rPr"))
        cstyle_el = rpr.find(qn("w:rStyle")) if rpr is not None else None
        char_style = cstyle_el.get(qn("w:val")) if cstyle_el is not None else None
        italic = _toggle(rpr, char_style, para_style, styles, "w:i")
        bold = _toggle(rpr, char_style, para_style, styles, "w:b")
        size = _size(rpr, char_style, para_style, styles)
        cur = spans[-1] if spans else None
        if cur and (cur.italic, cur.bold, cur.size) == (italic, bold, size):
            cur.text += text
        else:
            spans.append(Span(text=text, size=size, italic=italic, bold=bold))

    ind = _ppr_prop(ppr, para_style, styles, "w:ind")
    left = _twips(ind, "w:left", "w:start")
    hanging = _twips(ind, "w:hanging")
    first = -hanging if hanging is not None else _twips(ind, "w:firstLine")
    spacing = _ppr_prop(ppr, para_style, styles, "w:spacing")
    line_spacing = None
    if spacing is not None and spacing.get(qn("w:line")):
        value = int(spacing.get(qn("w:line")))
        rule = spacing.get(qn("w:lineRule"), "auto")
        size = spans[0].size if spans else 12.0
        # auto: 240ths of a line; exact/atLeast: twips (single line ~ 1.15 x font size)
        if rule == "auto":
            line_spacing = value / SINGLE_LINE
        else:
            line_spacing = value / TWIPS_PER_POINT / (1.15 * size)
    jc = _ppr_prop(ppr, para_style, styles, "w:jc")
    return Line(
        spans=spans,
        index=index,
        left_indent=left,
        first_line_indent=first,
        line_spacing=line_spacing,
        space_before=_twips(spacing, "w:before"),
        space_after=_twips(spacing, "w:after"),
        align=jc.get(qn("w:val")) if jc is not None else None,
        style=styles.name(para_style),
    )


def _page_count(path: Path) -> int | None:
    try:
        with zipfile.ZipFile(path) as z:
            app = z.read("docProps/app.xml").decode("utf-8", "replace")
    except (KeyError, zipfile.BadZipFile):
        return None
    m = re.search(r"<Pages>(\d+)</Pages>", app)
    return int(m.group(1)) if m else None


def ingest_docx(path: Path) -> Document:
    document = docx.Document(str(path))
    styles = _Styles(document)
    lines: list[Line] = []
    # Body paragraphs in reading order, including those inside tables.
    for p in document.element.body.iter(qn("w:p")):
        line = _paragraph(p, len(lines), styles)
        if line.text.strip():
            lines.append(line)
    return Document(name=path.name, kind="docx", page_count=_page_count(path), lines=lines)
