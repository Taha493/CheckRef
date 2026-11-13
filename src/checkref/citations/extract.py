"""Find in-text citations in the thesis body (spec §5 ⑩: find generously, judge strictly).

Three forms:
* parenthetical: "(Li & Seale, 2007; Wu et al., 2010, p. 5)"
* narrative: "Li and Seale (2007)", "Wu et al. (2010, p. 5)"
* year-first narrative: "In 2007, Li and Seale found …" (allowed by the guide)

Every work in a citation becomes one `Citation` with the author part, the year and any
page locator exactly as written, so that the format checks can judge them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from checkref.models import Citation, CitationKind, Document, Line
from checkref.normalize import _glue, body_lines
from checkref.segment import Segmentation

YEAR = r"(?:1[5-9]|20)\d\d"
YEAR_TOKEN = re.compile(
    rf"(?P<orig>{YEAR}/)?(?P<year>{YEAR})(?P<suffix>[a-z])?(?![\d–-])"
    r"|(?P<nd>n\.\s?d\.)(?:-(?P<ndsuffix>[a-z]))?"
    r"|(?P<press>in press)(?:-(?P<presssuffix>[a-z]))?",
    re.I,
)
ONE_YEAR = rf"(?:(?:{YEAR}/)?{YEAR}[a-z]?(?![\d–-])|n\.\s?d\.(?:-[a-z])?|in press(?:-[a-z])?)"
YEARS = rf"{ONE_YEAR}(?:\s*,\s*{ONE_YEAR})*"
LOCATOR = r"(?:pp?\.|paras?\.|para|Chapter|chap\.|Table|Figure|Fig\.)\s*[\w–-]+(?:\s*[–-]\s*\w+)?"
# "Li & Seale, 2007, p. 5": the author part, a comma (maybe missing), the years, a locator.
ITEM = re.compile(
    rf"^(?P<authors>.*?\S)(?P<comma>\s*,)?\s*(?P<years>{YEARS})"
    rf"(?:\s*,\s*(?P<locator>{LOCATOR}))?\s*$",
    re.I,
)
PREFIX = re.compile(
    r"^(?:(?:e\.g\.|i\.e\.|see also|see|cf\.|for example|for a review,? see|reviewed in|"
    r"reviewed by|adapted from|modified from|source:|data from)[,:]?\s+)+",
    re.I,
)
SECONDARY = re.compile(r",?\s*\b(?:as )?(?:cited|quoted) (?:in|by)\s+", re.I)
ET_AL = re.compile(r"\s*,?\s*\bet\.?\s?al\b\.?,?", re.I)
PARTICLE = r"(?:van|von|de|der|den|da|del|della|di|du|la|le|el|al|bin|ibn)"
NAME_TOKEN = rf"(?:{PARTICLE}\s)*[A-ZÀ-Þ][\w'’À-ɏ-]*"
INITIALS = r"(?:[A-Z]\.\s?-?\s?)+"
# Connectors between author names.
SPLIT = re.compile(r"\s*,\s*(?:&|and)\s+|\s+(?:&|and)\s+|\s*&\s*|\s*,\s*")
# Capitalised words that start sentences, not surnames: trimmed from narrative citations.
NOT_NAMES = {
    w.lower()
    for w in """However Moreover Furthermore Similarly Additionally Also Thus Therefore Hence
    Recently Previously Likewise Meanwhile Interestingly Notably Consequently Besides Further
    Overall Indeed Finally Firstly Secondly Lastly In The A An This These That Those It Its As
    While Although Whereas When Since Because According Accordingly Earlier Later Then So But
    And Or Both Several Many Some Most Other Another Researchers Studies Study Authors Author
    Scientists Experts Work Research Report Reports Results Findings Data Table Figure Fig
    Chapter Section Example For Of On By With From To At Like Unlike Following Based Using
    After Before During Among Between Recent Early Similar Here Their They We Our His Her One
    Two Three Such Yet Still Even Only Again Lately Initially Subsequently Ultimately Likewise
    Specifically Generally Particularly Especially Importantly Additionally Nevertheless
    Nonetheless Conversely Alternatively Elsewhere Today Currently Traditionally Historically
    Gram""".split()
}


@dataclass
class BodyText:
    text: str
    starts: list[int] = field(default_factory=list)  # offset where each line begins
    lines: list[Line] = field(default_factory=list)

    def page(self, offset: int) -> int | None:
        page = None
        for start, line in zip(self.starts, self.lines, strict=True):
            if start > offset:
                break
            page = line.page
        return page


def body_text(doc: Document, seg: Segmentation) -> BodyText:
    """The thesis text before the reference list, as one string (line-end hyphens joined)."""
    stop = seg.heading.index if seg.heading else (seg.lines[0].index if seg.lines else 10**9)
    body = BodyText(text="")
    for line in body_lines(doc):
        if line.index >= stop:
            break
        text = line.text.strip()
        if not text:
            continue
        if body.text:
            # Each DOCX line is a whole paragraph; PDF lines may end in a hyphen that joins.
            body.text += "\n" if doc.kind == "docx" else _glue(body.text, text)
        body.starts.append(len(body.text))
        body.lines.append(line)
        body.text += text
    return body


# --------------------------------------------------------------------------- authors


@dataclass
class AuthorPart:
    authors: list[str]
    initials: list[str]
    et_al: bool
    et_al_written: str | None
    connector: str | None
    title: str | None = None


def parse_authors(text: str) -> AuthorPart | None:
    """'Li, Wu, & Seale' / 'Li et al.' / 'World Health Organization [WHO]' / '"Nuke test"'.
    None when the text is not an author part (it holds ordinary lower-case words)."""
    text = text.strip().strip(",").strip()
    if not text:
        return None
    if text[0] in "\"“'‘*":  # a no-author work cited by its title
        return AuthorPart([], [], False, None, None, title=text.strip("\"“”'‘’*, "))
    et = ET_AL.search(text)
    et_al_written = None
    if et:
        et_al_written = et.group(0).strip(" ,")
        if text[et.end() :].strip(" ,"):
            return None  # words after "et al." — not an author part
        text = text[: et.start()]
    connector = None
    if re.search(r"(?:^|\s)&(?:\s|$)|\s&|&\s", text):
        connector = "&"
    elif re.search(r"\sand\s", text):
        connector = "and"
    names, initials = [], []
    for raw in SPLIT.split(text):
        raw = raw.strip()
        if not raw:
            continue
        m = re.fullmatch(rf"(?P<init>{INITIALS})?\s*(?P<name>.+)", raw)
        name = m.group("name").strip() if m else raw
        if not _name_like(name):
            return None
        names.append(name)
        initials.append((m.group("init") or "").strip() if m else "")
    if not names:
        return None
    return AuthorPart(names, initials, bool(et), et_al_written, connector)


CORPORATE_WORDS = {"of", "and", "for", "the", "on", "in", "de", "du", "des", "la", "für", "&"}


def _name_like(name: str) -> bool:
    """A surname ("van Roy", "Abd-Elghany", "D'Cruze", "Dee Tan") or a corporate author
    ("World Health Organization [WHO]", "FAO")."""
    name = re.sub(r"\s*\[[^\]]+\]$", "", name)
    words = name.split()
    if not words or len(words) > 10:
        return False
    if not re.match(rf"^{NAME_TOKEN}$", " ".join(words[:2])) and not words[0][:1].isupper():
        return False
    for w in words:
        if w.lower() in CORPORATE_WORDS or re.fullmatch(PARTICLE, w):
            continue
        if not w[:1].isupper() or re.search(r"\d", w):
            return False
    return True


# --------------------------------------------------------------------------- years


def _years(text: str) -> list[re.Match]:
    return list(YEAR_TOKEN.finditer(text))


def _year_fields(m: re.Match) -> dict:
    if m.group("year"):
        return {
            "year": m.group("year"),
            "year_suffix": m.group("suffix"),
            "original_year": (m.group("orig") or "").rstrip("/") or None,
        }
    if m.group("nd"):
        return {"year": "n.d.", "year_suffix": m.group("ndsuffix")}
    return {"year": "in press", "year_suffix": m.group("presssuffix")}


# --------------------------------------------------------------------------- extraction


@dataclass
class Extractor:
    body: BodyText
    citations: list[Citation] = field(default_factory=list)
    group: int = 0

    def add(self, raw: str, item: str, kind: CitationKind, pos: int, part: AuthorPart, **kw):
        years = kw.pop("years")
        for ym in years:
            self.citations.append(
                Citation(
                    id=f"C{len(self.citations) + 1}",
                    raw=raw,
                    item=item,
                    kind=kind,
                    group=self.group,
                    position=pos,
                    page=self.body.page(pos),
                    authors=part.authors,
                    initials=part.initials,
                    et_al=part.et_al,
                    et_al_written=part.et_al_written,
                    connector=part.connector,
                    title=part.title,
                    **_year_fields(ym),
                    **kw,
                )
            )


def extract(body: BodyText, known_surnames: set[str] | None = None) -> list[Citation]:
    """Every citation in the body text, in reading order."""
    ex = Extractor(body)
    known = known_surnames or set()
    text = body.text
    for m in re.finditer(r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)", text):
        inner = m.group(1)
        if not _years(inner):
            continue
        ex.group += 1
        if _year_only(inner):
            _narrative(ex, m, known)
        else:
            _parenthetical(ex, m)
    for m in re.finditer(rf"\bIn ({YEAR}[a-z]?), ", text):
        _year_first(ex, m, known)
    ex.citations.sort(key=lambda c: (c.position, c.id))
    return ex.citations


def _year_only(inner: str) -> bool:
    return bool(re.fullmatch(rf"\s*{YEARS}(?:\s*,\s*{LOCATOR})?\s*", inner, re.I))


def _parenthetical(ex: Extractor, m: re.Match) -> None:
    raw, inner = m.group(0), m.group(1)
    # Works wrongly separated by commas ("Smith, 2009, Jones, 2010") are split as well.
    items = re.split(r";\s*|(?<=\d[a-z]),\s+(?=[A-Z])|(?<=\d),\s+(?=[A-Z][a-z])", inner)
    for item in items:
        item = item.strip()
        if not item:
            continue
        personal = "personal communication" in item.lower()
        if personal:
            names = re.match(rf"\s*(?P<init>{INITIALS})?\s*(?P<name>{NAME_TOKEN})", item)
            if names:
                part = AuthorPart(
                    [names.group("name")], [(names.group("init") or "").strip()], False, None, None
                )
                year = _years(item)[-1:]
                ex.add(
                    raw,
                    item,
                    CitationKind.PARENTHETICAL,
                    m.start(),
                    part,
                    years=year,
                    personal=True,
                )
            continue
        body = PREFIX.sub("", item)
        parts = SECONDARY.split(body, maxsplit=1)
        if len(parts) == 2:
            _item(ex, raw, item, parts[1], m.start(), secondary=True)
            continue
        _item(ex, raw, item, body, m.start())


def _item(ex: Extractor, raw: str, item: str, text: str, pos: int, secondary=False) -> None:
    im = ITEM.match(text.strip())
    if not im:
        return
    part = parse_authors(im.group("authors"))
    if not part:
        return
    locator = im.group("locator")
    ex.add(
        raw,
        item,
        CitationKind.PARENTHETICAL,
        pos,
        part,
        years=_years(im.group("years")),
        locator=locator,
        secondary=secondary,
    )


def _names_before(text: str, end: int, known: set[str]) -> tuple[str, int] | None:
    """The author names that end at `end` ("Li and Seale", "Wu et al."), and their start."""
    window_start = max(0, end - 200, text.rfind("\n", 0, end) + 1)
    window = text[window_start:end]
    tokens = list(re.finditer(rf"et\.?\s?al\.?|{INITIALS}|{NAME_TOKEN}|&|\band\b|,|\S+", window))
    keep: list[re.Match] = []
    for t in reversed(tokens):
        word = t.group(0)
        heading_word = len(word) > 3 and word.isupper() and _fold(word) not in known
        if (
            re.fullmatch(rf"et\.?\s?al\.?|&|and|,|{INITIALS}|{NAME_TOKEN}", word)
            and not heading_word
        ):
            keep.append(t)
        else:
            break
    keep.reverse()
    while keep and re.fullmatch(r"&|and|,", keep[0].group(0)):
        keep.pop(0)
    # Drop leading sentence words ("However, Wu et al."), unless they are known surnames.
    while keep and keep[0].group(0).lower() in NOT_NAMES and _fold(keep[0].group(0)) not in known:
        keep.pop(0)
        while keep and re.fullmatch(r"&|and|,", keep[0].group(0)):
            keep.pop(0)
    if not keep or not re.match(NAME_TOKEN, keep[0].group(0)):
        return None
    start = window_start + keep[0].start()
    return text[start:end].strip(), start


def _narrative(ex: Extractor, m: re.Match, known: set[str]) -> None:
    found = _names_before(ex.body.text, m.start(), known)
    if not found:
        return
    names, start = found
    names = re.sub(r"['’]s$", "", names.strip())  # "Wu's (2010) study"
    part = parse_authors(names)
    if not part or not _plausible(part, known):
        return
    inner = m.group(1)
    loc = re.search(LOCATOR, inner, re.I)
    raw = ex.body.text[start : m.end()]
    ex.add(
        raw,
        raw,
        CitationKind.NARRATIVE,
        start,
        part,
        years=_years(inner),
        locator=loc.group(0) if loc else None,
    )


def _year_first(ex: Extractor, m: re.Match, known: set[str]) -> None:
    text = ex.body.text
    after = text[m.end() : m.end() + 250]
    names = re.match(
        rf"(?P<names>(?:{INITIALS})?{NAME_TOKEN}(?:\s+{NAME_TOKEN})?"
        rf"(?:(?:\s*,\s*(?:&|and)?\s*|\s+(?:&|and)\s+)(?:{INITIALS})?{NAME_TOKEN}(?:\s+{NAME_TOKEN})?)*"
        r"(?:\s+et\.?\s?al\.?)?)",
        after,
    )
    if not names:
        return
    part = parse_authors(names.group("names"))
    # "In 1947, sericulture …" is a date, not a citation: the first name must be a known
    # surname or be followed by "et al.".
    if not part or not (_fold(part.authors[0]) in known or part.et_al):
        return
    ex.group += 1
    raw = text[m.start() : m.end() + names.end()]
    ex.add(
        raw,
        raw,
        CitationKind.YEAR_FIRST,
        m.start(),
        part,
        years=list(YEAR_TOKEN.finditer(m.group(1))),
    )


def _plausible(part: AuthorPart, known: set[str]) -> bool:
    """A narrative candidate is kept when its first name is a known surname, or it reads
    like a citation ("et al.", or several names joined by and/&)."""
    if part.title:
        return False
    first = _fold(part.authors[0])
    if first in known:
        return True
    if first.split()[0] in NOT_NAMES:
        return False
    return part.et_al or len(part.authors) > 1 or len(part.authors[0]) > 2


def _fold(name: str) -> str:
    from checkref.citations.match import name_key

    return name_key(name)
