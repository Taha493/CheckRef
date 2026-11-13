"""Find the reference section, split it into references, detect merged entries (phase 4).

See spec §5 ③ and ④. Layout comes first: in a PDF, the two dominant left positions of the
section's lines are learned (first line, continuation); in a DOCX, each paragraph is one
entry. Text patterns are only a backup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from checkref.models import Document, Finding, Level, Line, Location, Reference, Span
from checkref.normalize import body_lines, indent_positions, join_lines
from checkref.rules.rulebook import rulebook

INDENT_TOLERANCE = 3.0  # points

NAME = r"[A-ZÀ-ɏ][\w'’\-À-ɏ]*(?: [A-Za-zÀ-ɏ][\w'’\-À-ɏ]*){0,3}"
# Lowercase surname particles that may start an entry: "van Roy, Y.", "de Luca, R."
PARTICLES = r"(?:(?:van|von|de|der|den|da|del|della|di|du|la|le|el|al|bin|ibn) )*"
INITIAL = r"[A-ZÀ-Þ]"  # includes accented capitals such as Ö
APA_AUTHOR_START = re.compile(rf"^{PARTICLES}(?:{NAME}), (?:{INITIAL}[a-z]?\.(?: ?-?{INITIAL}\.)*)")
VANCOUVER_AUTHOR = re.compile(rf"^{NAME} {INITIAL}{{1,3}}[,.]")
YEAR_PAREN = re.compile(r"\((?:1[5-9]\d\d|20\d\d)[a-z]?(?:, [^)]*)?\)\.|\((?:n\.d\.|in press)\)\.")
CORPORATE_START = re.compile(r"^[A-Z][^().]{1,150}\. \((?:1[5-9]\d\d|20\d\d|n\.d\.)")
# The end of one reference glued to the start of the next, e.g. "635-640.Dee Tan IY, Bautista"
MERGE_POINT = re.compile(
    rf"(?:\d|\)|[a-z])\.\s?(?=(?:{NAME}), {INITIAL}\.|{NAME} {INITIAL}{{1,3}}[,.] "
    rf"|(?:{NAME}), {INITIAL}{{1,3}}\b)"
)


@dataclass
class Segmentation:
    heading: Line | None
    lines: list[Line]  # body lines of the section, after the heading
    references: list[Reference]
    findings: list[Finding] = field(default_factory=list)
    indents: tuple[float, float] | None = None  # PDF: (first line x, continuation x)


def looks_like_reference_start(text: str) -> bool:
    text = text.strip().lstrip("*")
    head = text[:200]
    return bool(
        APA_AUTHOR_START.match(text)
        or CORPORATE_START.match(text)
        or (VANCOUVER_AUTHOR.match(text) and re.search(r"\b(19|20)\d\d\b", head))
        or (YEAR_PAREN.search(head) and text[:1].isupper())
    )


def _heading_text(line: Line) -> str:
    return re.sub(r"[\s:.]+$", "", line.text.strip()).lower()


def find_section(doc: Document) -> tuple[Line | None, list[Line], bool]:
    """(heading, section lines, heading_missing)."""
    lines = body_lines(doc)
    detect = {h.lower() for h in rulebook().settings["reference_list"]["detect_headings"]}
    candidates = [i for i, ln in enumerate(lines) if _heading_text(ln) in detect]
    for i in reversed(candidates):  # the table of contents comes first, so prefer the last
        following = lines[i + 1 : i + 11]
        if sum(looks_like_reference_start(ln.text) for ln in following) >= 2:
            return lines[i], lines[i + 1 :], False
    # No heading: take the longest run of reference-like lines that reaches the end.
    starts = [i for i, ln in enumerate(lines) if looks_like_reference_start(ln.text)]
    if len(starts) < 3:
        return None, [], True
    begin = starts[-1]
    for a, b in zip(reversed(starts[:-1]), reversed(starts[1:]), strict=True):
        if b - a > 8:
            break
        begin = a
    return None, lines[begin:], True


def _ends_like_reference(text: str) -> bool:
    t = text.rstrip()
    return bool(re.search(r"(\d|\)|[a-z])\.$|https?://\S+$|\d$", t))


def _group_pdf(lines: list[Line], indents) -> tuple[list[list[Line]], list[Line]]:
    """Group lines into entries. Returns (entries, lines at an unexpected indent)."""
    entries: list[list[Line]] = []
    odd: list[Line] = []
    for ln in lines:
        if indents:
            first_x, cont_x = indents
            if abs(ln.x0 - first_x) <= INDENT_TOLERANCE:
                new = True
            elif abs(ln.x0 - cont_x) <= INDENT_TOLERANCE:
                new = False
            else:
                odd.append(ln)
                new = looks_like_reference_start(ln.text)
        else:
            prev = entries[-1][-1].text if entries else ""
            new = looks_like_reference_start(ln.text) and (
                not entries or _ends_like_reference(prev)
            )
        if new or not entries:
            entries.append([ln])
        else:
            entries[-1].append(ln)
    return entries, odd


def _group_docx(lines: list[Line]) -> list[list[Line]]:
    entries: list[list[Line]] = []
    for ln in lines:
        if entries and not looks_like_reference_start(ln.text):
            if not _ends_like_reference(entries[-1][-1].text):
                entries[-1].append(ln)  # Enter pressed in the middle of a reference
                continue
        entries.append([ln])
    return entries


def _split_spans(spans: list[Span], at: int) -> tuple[list[Span], list[Span]]:
    left, right, pos = [], [], 0
    for s in spans:
        end = pos + len(s.text)
        if end <= at:
            left.append(s)
        elif pos >= at:
            right.append(s)
        else:
            left.append(s.model_copy(update={"text": s.text[: at - pos]}))
            right.append(s.model_copy(update={"text": s.text[at - pos :]}))
        pos = end
    return left, right


def _merge_points(text: str) -> list[int]:
    """Character offsets where a second reference starts inside one entry."""
    points = []
    for m in MERGE_POINT.finditer(text):
        rest = text[m.end() :]
        if YEAR_PAREN.search(rest[:250]) or re.search(r"\b(19|20)\d\d\b", rest[:250]):
            points.append(m.end())
    return points


def _location(lines: list[Line]) -> Location:
    first = lines[0]
    return Location(page=first.page, top=first.top, x0=first.x0)


def segment(doc: Document) -> Segmentation:
    heading, lines, heading_missing = find_section(doc)
    findings: list[Finding] = []
    if heading_missing:
        findings.append(
            Finding(
                level=Level.ERROR,
                rule_id="LST-HEADING-01",
                message="The reference list has no heading (e.g. References).",
                location=_location(lines) if lines else Location(),
            )
        )
    elif heading is not None:
        accepted = {h.lower() for h in rulebook().settings["reference_list"]["accepted_headings"]}
        if _heading_text(heading) not in accepted:
            findings.append(
                Finding(
                    level=Level.NEEDS_REVIEW,
                    rule_id="LST-HEADING-02",
                    message=f'The reference list heading is "{heading.text.strip()}"; '
                    'the guide uses "References".',
                    location=_location([heading]),
                    original=heading.text.strip(),
                )
            )
    if not lines:
        return Segmentation(heading, lines, [], findings)

    indents = None
    if doc.kind == "pdf":
        indents = indent_positions(lines)
        entries, _odd = _group_pdf(lines, indents)
    else:
        entries = _group_docx(lines)

    references: list[Reference] = []
    for entry in entries:
        spans = join_lines(entry)
        text = "".join(s.text for s in spans)
        cuts = _merge_points(text)
        parts: list[list[Span]] = []
        rest, offset = spans, 0
        for cut in cuts:
            left, rest = _split_spans(rest, cut - offset)
            offset = cut
            parts.append(left)
        parts.append(rest)
        for part in parts:
            ref_id = f"R{len(references) + 1}"
            references.append(
                Reference(
                    id=ref_id,
                    raw="".join(s.text for s in part).strip(),
                    page=entry[0].page,
                    lines=entry,
                    spans=part,
                    merged_part=len(parts) > 1,
                )
            )
        if cuts:
            findings.append(
                Finding(
                    level=Level.ERROR,
                    rule_id="LST-MERGED-01",
                    message=f"{len(parts)} references are merged into one entry; "
                    "start each reference on a new line.",
                    location=_location(entry),
                    reference_id=references[-len(parts)].id,
                    original=text.strip(),
                )
            )
    return Segmentation(heading, lines, references, findings, indents)
