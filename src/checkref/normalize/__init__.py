"""Page numbers, headers/footers, lookalike characters, line joining and layout (plan phase 3).

See spec §5 ②. Dash characters are never converted: the character the student typed is
kept so that rules can judge it (only lookalikes of the hyphen are mapped to '-').
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from statistics import median

from checkref.models import Document, Line, LineRole, Span

LOOKALIKES = str.maketrans(
    {
        "‐": "-",  # hyphen
        "‑": "-",  # non-breaking hyphen
        "−": "-",  # minus sign
        " ": " ",  # no-break space
        "­": None,  # soft hyphen
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬀ": "ff",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
    }
)

EDGE_BAND = 0.10  # top/bottom share of the page where page numbers and headers live
ROMAN = re.compile(r"^(?=[ivxlc]+$)c{0,3}(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$", re.IGNORECASE)
MIN_PAGES = 3  # a page-number or header pattern must repeat on at least this many pages


def _roman_value(s: str) -> int:
    values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}
    total = 0
    for a, b in zip(s.lower(), s.lower()[1:] + " ", strict=True):
        v = values[a]
        total += -v if b != " " and values[b] > v else v
    return total


def _number(text: str) -> tuple[str, int] | None:
    t = text.strip()
    if re.fullmatch(r"\d{1,4}", t):
        return "arabic", int(t)
    if ROMAN.match(t):
        return "roman", _roman_value(t)
    return None


def _in_edge_band(line: Line, doc: Document) -> str | None:
    if line.top is None or not doc.page_height:
        return None
    if line.top < doc.page_height * EDGE_BAND:
        return "top"
    if line.top > doc.page_height * (1 - EDGE_BAND):
        return "bottom"
    return None


def mark_page_furniture(doc: Document) -> None:
    """Mark page numbers, running headers and footers (PDF only), in place.

    A page-number candidate is a number alone on a line in the top/bottom band. A group of
    candidates at the same position counts only if it appears on MIN_PAGES pages and its
    values rise with the page number (page - value constant), so a reference line ending in
    a number is never removed.
    """
    if doc.kind != "pdf":
        return
    groups: dict[tuple, list[tuple[Line, int]]] = defaultdict(list)
    texts: dict[tuple, list[Line]] = defaultdict(list)
    for line in doc.lines:
        band = _in_edge_band(line, doc)
        if band is None:
            continue
        number = _number(line.text)
        centre = round(((line.x0 or 0) + (line.x1 or 0)) / 2 / 20)  # 20 pt buckets
        if number:
            kind, value = number
            groups[(band, centre, kind)].append((line, value))
        else:
            key = (band, re.sub(r"\d+", "#", line.text.strip().lower()))
            texts[key].append(line)

    for members in groups.values():
        offsets = Counter(line.page - value for line, value in members)
        offset, count = offsets.most_common(1)[0]
        if count >= MIN_PAGES:
            for line, value in members:
                if line.page - value == offset:
                    line.role = LineRole.PAGE_NUMBER
    for (band, _), members in texts.items():
        if len({ln.page for ln in members}) >= MIN_PAGES:
            for line in members:
                line.role = LineRole.HEADER if band == "top" else LineRole.FOOTER


def normalise_characters(doc: Document) -> None:
    """Map hyphen lookalikes to '-', drop soft hyphens, expand ligatures (in place)."""
    for line in doc.lines:
        for span in line.spans:
            span.text = span.text.translate(LOOKALIKES)


def normalise(doc: Document) -> Document:
    mark_page_furniture(doc)
    normalise_characters(doc)
    return doc


def body_lines(doc: Document) -> list[Line]:
    return [ln for ln in doc.lines if ln.role == LineRole.BODY]


# --------------------------------------------------------------------------- joining

URLISH = re.compile(r"(https?://|www\.)\S*$")


def _glue(prev_text: str, next_text: str) -> str:
    """Separator between two consecutive lines of the same paragraph or reference.

    Line-end hyphens and dashes are real characters (ruling: treat them as normal hyphens);
    the next line continues the same token, so no space is inserted. A URL broken across
    lines also continues without a space.
    """
    tail = prev_text.rstrip()
    if not tail or not next_text.strip():
        return ""
    if tail[-1] in "-–—":
        return ""
    if URLISH.search(tail) and not tail.endswith("."):
        return ""
    return " "


def join_lines(lines: list[Line]) -> list[Span]:
    """Concatenate lines into one span list, keeping styles and inserting correct glue."""
    spans: list[Span] = []
    text_so_far = ""
    for line in lines:
        if not line.spans:
            continue
        glue = _glue(text_so_far, line.text) if spans else ""
        if spans:
            spans[-1] = spans[-1].model_copy(update={"text": spans[-1].text.rstrip() + glue})
        for i, span in enumerate(line.spans):
            text = span.text.lstrip() if i == 0 else span.text
            spans.append(span.model_copy(update={"text": text}))
        text_so_far = "".join(s.text for s in spans)
    if spans:
        spans[-1] = spans[-1].model_copy(update={"text": spans[-1].text.rstrip()})
    return spans


# --------------------------------------------------------------------------- layout


def indent_positions(lines: list[Line], tolerance: float = 2.0) -> tuple[float, float] | None:
    """The two dominant left positions of PDF lines: (first line, continuation).

    Returns None when there is no clear second position (no hanging indent).
    """
    xs = [round(ln.x0) for ln in lines if ln.x0 is not None]
    if not xs:
        return None
    counts = Counter(xs)
    clusters: list[list[int]] = []
    for x, _ in sorted(counts.items()):
        if clusters and x - clusters[-1][-1] <= tolerance:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    weighted = sorted(((sum(counts[x] for x in c), median(c)) for c in clusters), reverse=True)
    if len(weighted) < 2 or weighted[1][0] < max(2, 0.1 * len(xs)):
        return None
    first, cont = sorted([weighted[0][1], weighted[1][1]])
    return float(first), float(cont)
