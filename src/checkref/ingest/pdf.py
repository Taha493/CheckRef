"""PDF ingestion with pdfplumber: characters → styled spans → lines (spec §5 ①)."""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber
from pdfminer.pdftypes import resolve1
from pdfminer.psparser import PSLiteral

from checkref.models import Document, Line, Span

ITALIC_NAME = re.compile(r"italic|oblique|[-,]it$|[-,]ital", re.IGNORECASE)
BOLD_NAME = re.compile(r"bold|black|heavy|semibold|demi|[-,]bd$", re.IGNORECASE)
FLAG_ITALIC = 1 << 6
FLAG_FORCE_BOLD = 1 << 18

# Word-exported PDFs draw spaces as gaps, without space characters. Measured on the sample
# theses: gaps inside words are <= 0.04 x font size, gaps between words >= 0.16 x font size.
SPACE_GAP_RATIO = 0.1
# A slant above this (horizontal shear / vertical scale) is a synthetic italic.
SKEW_RATIO = 0.1
# Fewer non-space characters per page than this, on average, means a scanned PDF.
MIN_CHARS_PER_PAGE = 50


class ScannedPdfError(ValueError):
    """The PDF has no usable text layer (spec §3: scanned PDFs are out of scope)."""


def _name(value: object) -> str:
    value = resolve1(value)
    if isinstance(value, PSLiteral):
        value = value.name
    if isinstance(value, bytes):
        value = value.decode("latin-1")
    return str(value or "")


def _strip_subset(fontname: str) -> str:
    """'BHPMEG+TimesNewRomanPSMT' -> 'TimesNewRomanPSMT'."""
    return fontname.split("+", 1)[1] if re.match(r"^[A-Z]{6}\+", fontname) else fontname


def _descriptor_styles(pdf: pdfplumber.PDF) -> dict[str, tuple[bool, bool]]:
    """Italic/bold per font name from the font descriptors (Flags, ItalicAngle, FontWeight)."""
    styles: dict[str, tuple[bool, bool]] = {}
    for page in pdf.pages:
        fonts = resolve1((page.page_obj.resources or {}).get("Font")) or {}
        for ref in fonts.values():
            font = resolve1(ref) or {}
            base = _name(font.get("BaseFont"))
            if not base or base in styles:
                continue
            desc = resolve1(font.get("FontDescriptor"))
            if desc is None and font.get("DescendantFonts"):
                descendant = resolve1(resolve1(font["DescendantFonts"])[0]) or {}
                desc = resolve1(descendant.get("FontDescriptor"))
            desc = desc or {}
            flags = int(resolve1(desc.get("Flags")) or 0)
            angle = float(resolve1(desc.get("ItalicAngle")) or 0)
            weight = float(resolve1(desc.get("FontWeight")) or 0)
            italic = bool(flags & FLAG_ITALIC) or angle != 0
            bold = bool(flags & FLAG_FORCE_BOLD) or weight >= 600
            styles[base] = (italic, bold)
    return styles


def _style(char: dict, descriptors: dict[str, tuple[bool, bool]]) -> tuple[bool, bool]:
    name = _strip_subset(char["fontname"])
    fallback = descriptors.get(name, (False, False))
    desc_italic, desc_bold = descriptors.get(char["fontname"], fallback)
    a, b, c, d, *_ = char.get("matrix") or (1, 0, 0, 1, 0, 0)
    skewed = d != 0 and abs(b) < 1e-6 and abs(c / d) > SKEW_RATIO
    italic = bool(ITALIC_NAME.search(name)) or desc_italic or skewed
    bold = bool(BOLD_NAME.search(name)) or desc_bold
    return italic, bold


def _line(chars: list[dict], page_no: int, index: int, descriptors: dict) -> Line | None:
    chars = sorted((c for c in chars if not c["text"].isspace()), key=lambda c: c["x0"])
    if not chars:
        return None
    spans: list[Span] = []
    prev = None
    for ch in chars:
        italic, bold = _style(ch, descriptors)
        font = _strip_subset(ch["fontname"])
        size = round(ch["size"], 1)
        gap = prev is not None and ch["x0"] - prev["x1"] > SPACE_GAP_RATIO * ch["size"]
        cur = spans[-1] if spans else None
        if cur and (cur.font, cur.size, cur.italic, cur.bold) == (font, size, italic, bold):
            cur.text += (" " if gap else "") + ch["text"]
            cur.x1 = ch["x1"]
        else:
            if cur and gap:
                cur.text += " "  # the space belongs to the run before it
            spans.append(
                Span(
                    text=ch["text"],
                    page=page_no,
                    x0=ch["x0"],
                    top=ch["top"],
                    x1=ch["x1"],
                    bottom=ch["bottom"],
                    font=font,
                    size=size,
                    italic=italic,
                    bold=bold,
                )
            )
        prev = ch
    return Line(
        spans=spans,
        index=index,
        page=page_no,
        x0=chars[0]["x0"],
        x1=max(c["x1"] for c in chars),
        top=min(c["top"] for c in chars),
        bottom=max(c["bottom"] for c in chars),
    )


def ingest_pdf(path: Path) -> Document:
    with pdfplumber.open(path) as pdf:
        descriptors = _descriptor_styles(pdf)
        lines: list[Line] = []
        visible = 0
        for page in pdf.pages:
            page = page.dedupe_chars()
            visible += sum(1 for c in page.chars if not c["text"].isspace())
            for tl in page.extract_text_lines(return_chars=True, strip=False):
                line = _line(tl["chars"], page.page_number, len(lines), descriptors)
                if line:
                    lines.append(line)
        if visible < MIN_CHARS_PER_PAGE * len(pdf.pages):
            raise ScannedPdfError(
                "This PDF has little or no selectable text. Scanned PDFs are not supported."
            )
        first = pdf.pages[0]
        return Document(
            name=path.name,
            kind="pdf",
            page_count=len(pdf.pages),
            page_width=float(first.width),
            page_height=float(first.height),
            lines=lines,
        )
