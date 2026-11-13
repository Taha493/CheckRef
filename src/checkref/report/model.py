"""The report as data (plan phase 9): everything the HTML view, the PDF and the corrected-list
DOCX show, built from a CheckResult. Rendering lives in checkref.report.render.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from functools import cache
from pathlib import Path

from checkref import __version__
from checkref.models import (
    Citation,
    CorrectedReference,
    CorrectionStatus,
    Finding,
    Level,
    Piece,
    Reference,
)
from checkref.rules.rulebook import Rule, rulebook

GUIDE_DIR = Path(__file__).resolve().parents[3] / "data" / "guide"
TOKEN = re.compile(r"\w+|\s+|[^\w\s]")  # words, spaces and single punctuation marks
STATUS_LABELS = {
    CorrectionStatus.CORRECT: "Correct",
    CorrectionStatus.CORRECTED: "Corrected",
    CorrectionStatus.PARTIAL: "Partly corrected",
    CorrectionStatus.NOT_CORRECTED: "Not corrected",
}
# Headings for the rulebook's template groups, in the rulebook's order.
GROUP_LABELS = {
    "journal": "Journals, magazines and newspapers",
    "book": "Books and e-books",
    "web": "Web pages and online documents",
    "report": "Reports",
    "thesis": "Theses",
    "conference": "Conference papers",
    "software": "Software and manuals",
    "av": "Film, television and video",
    "social": "Blogs",
    "standard": "Standards and patents",
}
UNREAD = "Could not be read"
CITED_NOT_LISTED, LISTED_NOT_CITED = "MAT-01", "MAT-02"


@dataclass
class Run:
    """A piece of displayed text with its style."""

    text: str
    italic: bool = False
    changed: bool = False  # differs from what the student wrote
    placeholder: bool = False


@dataclass
class Problem:
    level: str  # "error" | "needs_review"
    rule_id: str
    rule_title: str
    message: str
    source: RuleSource
    correction: str | None = None
    page: int | None = None


@dataclass
class ReferenceItem:
    number: int
    id: str
    page: int | None
    type_name: str
    label: str  # "Soule et al. (1988)"
    original: list[Run]
    status: str  # CorrectionStatus value
    status_label: str
    problems: list[Problem]
    corrected: list[Run]
    notes: list[str]

    @property
    def errors(self) -> int:
        return sum(p.level == Level.ERROR for p in self.problems)

    @property
    def reviews(self) -> int:
        return sum(p.level == Level.NEEDS_REVIEW for p in self.problems)

    @property
    def anchor(self) -> str:
        return f"ref-{self.number}"


@dataclass
class CitationItem:
    number: int
    raw: str
    page: int | None
    problems: list[Problem]

    @property
    def anchor(self) -> str:
        return f"cite-{self.number}"


@dataclass
class Occurrence:
    """One problem as listed under its rule or in the citation consistency lists, with a link
    to the entry or citation it belongs to."""

    kind: str  # "reference" | "citation" | "list"
    anchor: str  # "ref-12", "cite-4", "list"
    where: str  # "12. Soule et al. (1988)", the citation as written, "The reference list"
    problem: Problem


@dataclass
class RuleGroup:
    """Every place one rule is broken (section "Rules not followed")."""

    rule_id: str
    title: str
    occurrences: list[Occurrence]
    sources: list[RuleSource]  # different only for template rules (one guide example per type)

    @property
    def level(self) -> str:
        levels = {o.problem.level for o in self.occurrences}
        return Level.ERROR.value if Level.ERROR.value in levels else Level.NEEDS_REVIEW.value

    def count(self, kind: str) -> int:
        return sum(o.kind == kind for o in self.occurrences)


@dataclass
class TypeGroup:
    label: str
    types: list[tuple[str, int]]  # (template name, number of references)

    @property
    def count(self) -> int:
        return sum(n for _, n in self.types)


@dataclass
class Recency:
    year: int
    share_required: float
    share_actual: float
    window: tuple[int, int]
    total: int
    recent: int
    older: list[str]
    non_journal: list[str]
    undated: list[str]


@dataclass
class Report:
    file_name: str
    generated: str
    engine_version: str
    guide_snapshot: str
    references: int
    citations: int
    errors: int
    needs_review: int
    statuses: dict[str, int]
    list_problems: list[Problem]
    items: list[ReferenceItem]
    citation_items: list[CitationItem]
    corrected_list: list[list[Run]]
    type_groups: list[TypeGroup] = field(default_factory=list)
    rule_groups: list[RuleGroup] = field(default_factory=list)
    cited_not_listed: list[Occurrence] = field(default_factory=list)  # MAT-01
    listed_not_cited: list[Occurrence] = field(default_factory=list)  # MAT-02
    mismatches: list[Occurrence] = field(default_factory=list)  # the other MAT rules
    has_pages: bool = True  # PDF input; a Word file has no fixed pages
    recency: Recency | None = None
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- sources


@cache
def _guide_pages() -> dict[str, tuple[str, str | None]]:
    """Snapshot page slug → (title, live address)."""
    manifest = json.loads((GUIDE_DIR / "manifest.json").read_text(encoding="utf-8"))
    pages = {p["slug"]: (p["title"], p["url"]) for p in manifest["pages"]}
    pages["brief-guide-pdf"] = ("Brief guide (PDF, March 2019)", None)
    return pages


@dataclass
class RuleSource:
    """Where a rule comes from, shown under each problem: a place in the guide (with the quoted
    words or a guide example), a project ruling, and/or a note on how it follows from the guide."""

    where: str | None = None  # "APA 6th guide › Articles › DOI and URL"
    url: str | None = None  # the live guide page
    quote: list[Run] = field(default_factory=list)
    example: bool = False  # the quote is a guide example rather than the guide's own words
    ruling: str | None = None  # "6.2"
    ruling_title: str | None = None
    ruling_text: str | None = None
    note: str | None = None
    note_label: str | None = None


def md_runs(text: str) -> list[Run]:
    """Text with *...* italics, as in the rulebook, as runs."""
    return [Run(part, italic=i % 2 == 1) for i, part in enumerate(text.split("*")) if part]


def guide_url() -> str:
    """The guide's home page, linked from the website."""
    return json.loads((GUIDE_DIR / "manifest.json").read_text(encoding="utf-8"))["start_url"]


def _place(page: str | None, section: str | None) -> tuple[str | None, str | None]:
    if not page:
        return None, None
    title, url = _guide_pages().get(page, (page, None))
    if section:  # the guide's headings name its library ("via the AUT Library")
        section = re.sub(r"\b(?:the )?AUT Library\b", "the library", section)
    return " › ".join(x for x in ("APA 6th guide", title, section) if x), url


NOTE_LABELS = {"guide_examples": "Basis", "derived": "Basis", "guide_template": "Basis"}


def rule_source(rule: Rule, type_id: str | None = None) -> RuleSource:
    s = rule.source
    out = RuleSource(note=s.note, note_label=NOTE_LABELS.get(s.type))
    if s.ruling:
        ruling = rulebook().rulings[s.ruling]
        out.ruling, out.ruling_title, out.ruling_text = s.ruling, ruling.title, ruling.text
    out.where, out.url = _place(s.page, s.section)
    if s.quote:
        out.quote = md_runs(s.quote)
    elif s.type == "guide_template" and type_id:
        # The rule is the template itself: show the guide's example for this kind of source.
        template = rulebook().template(type_id)
        out.where, out.url = _place(template.source.get("page"), template.source.get("section"))
        if template.examples:
            out.quote, out.example = md_runs(template.examples[0]), True
    return out


# --------------------------------------------------------------------------- text runs


def runs_of(ref: Reference) -> list[Run]:
    """The reference as written, with its italics."""
    runs: list[Run] = []
    joined = "".join(s.text for s in ref.spans)
    lead = len(joined) - len(joined.lstrip())
    pos = 0
    for s in ref.spans:
        text = s.text
        start, end = pos, pos + len(text)
        pos = end
        lo, hi = max(start, lead), min(end, lead + len(ref.raw))
        if lo >= hi:
            continue
        piece = joined[lo:hi]
        if runs and runs[-1].italic == s.italic:
            runs[-1].text += piece
        else:
            runs.append(Run(piece, s.italic))
    return runs or [Run(ref.raw)]


def _chars(runs) -> list[tuple[str, bool]]:
    return [(c, r.italic) for r in runs for c in r.text]


def highlight(original: list[Run], pieces: list[Piece]) -> tuple[list[Run], list[Run]]:
    """(original with removed or replaced words marked, corrected text with the words that
    differ marked). Compared word by word; a change of italics counts as a change in the
    corrected text."""
    a = _chars(original)
    b = [(c, p.italic, p.placeholder) for p in pieces for c in p.text]
    a_text, b_text = "".join(c for c, _ in a), "".join(c for c, *_ in b)
    a_tok = TOKEN.findall(a_text)
    b_tok = TOKEN.findall(b_text)
    a_starts, b_starts = _starts(a_tok), _starts(b_tok)
    removed = [False] * len(a)
    changed = [True] * len(b)
    for op, i1, i2, j1, j2 in SequenceMatcher(None, a_tok, b_tok, autojunk=False).get_opcodes():
        if op != "equal":
            for i in range(i1, i2):
                for n in range(len(a_tok[i])):
                    removed[a_starts[i] + n] = True
            continue
        for k in range(j2 - j1):
            ai, bj = a_starts[i1 + k], b_starts[j1 + k]
            for n in range(len(b_tok[j1 + k])):
                same_style = a[ai + n][1] == b[bj + n][1] or not b[bj + n][0].isalnum()
                changed[bj + n] = not same_style
    removed, changed = _spaces_join(a_text, removed), _spaces_join(b_text, changed)
    before = _merge(
        (ch, italic, flag, False) for (ch, italic), flag in zip(a, removed, strict=True)
    )
    after = _merge(
        (ch, italic, flag, placeholder)
        for (ch, italic, placeholder), flag in zip(b, changed, strict=True)
    )
    return before, after


def _spaces_join(text: str, flags: list[bool]) -> list[bool]:
    """A space is marked only between two marked characters, so a changed phrase shows as
    one stretch ("[full journal name]") and unchanged spaces stay plain."""
    out = list(flags)
    for i, ch in enumerate(text):
        if ch.isspace():
            out[i] = 0 < i < len(text) - 1 and flags[i - 1] and flags[i + 1]
    return out


def _merge(chars) -> list[Run]:
    runs: list[Run] = []
    for ch, italic, flag, placeholder in chars:
        if runs and (runs[-1].italic, runs[-1].changed, runs[-1].placeholder) == (
            italic,
            flag,
            placeholder,
        ):
            runs[-1].text += ch
        else:
            runs.append(Run(ch, italic, flag, placeholder))
    return runs


def _starts(tokens: list[str]) -> list[int]:
    out, pos = [], 0
    for t in tokens:
        out.append(pos)
        pos += len(t)
    return out


def plain_runs(pieces: list[Piece]) -> list[Run]:
    return [Run(p.text, p.italic, False, p.placeholder) for p in pieces]


# --------------------------------------------------------------------------- building


def _problem(f: Finding, type_id: str | None = None) -> Problem:
    rule = rulebook().rule(f.rule_id)
    return Problem(
        level=f.level.value,
        rule_id=f.rule_id,
        rule_title=rule.title,
        message=f.message,
        source=rule_source(rule, type_id),
        correction=f.correction,
        page=f.location.page,
    )


def _type_name(ref: Reference) -> str:
    if not ref.type:
        return UNREAD
    try:
        return rulebook().template(ref.type).name
    except StopIteration:
        return ref.type


def short_label(ref: Reference) -> str:
    """'Soule et al. (1988)', 'Li & Seale (2007)', 'World Health Organization (2020)'."""
    people = ref.authors or ref.editors
    if people:
        names = people[0].family
        if len(people) == 2:
            names += f" & {people[1].family}"
        elif len(people) > 2:
            names += " et al."
    else:
        names = ref.corporate_author or (ref.title or re.split(r"[.(]", ref.raw)[0])[:50]
    year = ref.year or _year_of(ref)
    return f"{names} ({year})" if year else names


def _year_of(ref: Reference) -> int | None:
    """The publication year; for an unreadable entry, the first year in its text."""
    if ref.year and ref.year[:4].isdigit():
        return int(ref.year[:4])
    if ref.type:
        return None  # (n.d.) or (in press)
    m = re.search(r"\b(?:1[5-9]|20)\d\d\b", ref.raw)
    return int(m.group(0)) if m else None


def type_groups(refs: list[Reference]) -> list[TypeGroup]:
    """How many references the checker classified as each rulebook template, by group."""
    counted = Counter(r.type for r in refs)
    groups = []
    for group, label in GROUP_LABELS.items():
        types = [(t.name, counted[t.id]) for t in rulebook().templates if t.group == group]
        if any(n for _, n in types):
            groups.append(TypeGroup(label, [(name, n) for name, n in types if n]))
    known = {t.id for t in rulebook().templates}
    other = [(_type_name(r), 1) for r in refs if r.type not in known]
    if other:
        names = Counter(name for name, _ in other)
        groups.append(TypeGroup("Not classified", sorted(names.items(), key=lambda x: -x[1])))
    return groups


def occurrences(
    items: list[ReferenceItem], citation_items: list[CitationItem], list_problems: list[Problem]
) -> list[Occurrence]:
    out = [
        Occurrence("reference", it.anchor, f"{it.number}. {it.label}", p)
        for it in items
        for p in it.problems
    ]
    out += [Occurrence("citation", c.anchor, c.raw, p) for c in citation_items for p in c.problems]
    out += [Occurrence("list", "list", "The reference list", p) for p in list_problems]
    return out


def rule_groups(found: list[Occurrence]) -> list[RuleGroup]:
    """One group per rule: errors first, then the most frequent."""
    groups: dict[str, RuleGroup] = {}
    for o in found:
        p = o.problem
        g = groups.setdefault(p.rule_id, RuleGroup(p.rule_id, p.rule_title, [], []))
        g.occurrences.append(o)
        if p.source not in g.sources:
            g.sources.append(p.source)
    return sorted(
        groups.values(),
        key=lambda g: (g.level != Level.ERROR.value, -len(g.occurrences), g.rule_id),
    )


def recency_of(refs: list[Reference], year: int, share: float) -> Recency:
    window = rulebook().settings["recency"]["window_years"]
    first = year - window + 1
    years = {r.id: _year_of(r) for r in refs}
    dated = [r for r in refs if years[r.id]]
    recent = [r for r in dated if first <= years[r.id] <= year]
    journal = {t.id for t in rulebook().templates if t.group == "journal"}
    return Recency(
        year=year,
        share_required=share,
        share_actual=len(recent) / len(dated) if dated else 0.0,
        window=(first, year),
        total=len(dated),
        recent=len(recent),
        older=[short_label(r) for r in dated if years[r.id] < first],
        non_journal=[short_label(r) for r in dated if r.type and r.type not in journal],
        undated=[short_label(r) for r in refs if not years[r.id]],
    )


def build_report(result, recency: dict | None = None) -> Report:
    """`result` is a checkref.pipeline.CheckResult; `recency` = {"year": 2025, "share": 0.8}."""
    by_ref: dict[str, list[Finding]] = {}
    by_cite: dict[str, list[Finding]] = {}
    list_level: list[Finding] = []
    for f in result.findings:
        if f.citation_id:
            by_cite.setdefault(f.citation_id, []).append(f)
        elif f.reference_id:
            by_ref.setdefault(f.reference_id, []).append(f)
        elif f.rule_id != "REC-01":
            list_level.append(f)

    items = []
    for n, ref in enumerate(result.references, 1):
        c: CorrectedReference = result.corrected[ref.id]
        original = runs_of(ref)
        corrected: list[Run] = []
        if c.status in (CorrectionStatus.CORRECTED, CorrectionStatus.PARTIAL):
            original, corrected = highlight(original, c.pieces)
        items.append(
            ReferenceItem(
                number=n,
                id=ref.id,
                page=ref.page,
                type_name=_type_name(ref),
                label=short_label(ref),
                original=original,
                status=c.status.value,
                status_label=STATUS_LABELS[c.status],
                problems=[_problem(f, ref.type) for f in by_ref.get(ref.id, [])],
                corrected=corrected,
                notes=c.notes,
            )
        )

    cites: dict[str, Citation] = {c.id: c for c in result.citations}
    citation_items: list[CitationItem] = []
    seen: dict[tuple[str, int | None], CitationItem] = {}
    for cid, findings in sorted(by_cite.items(), key=lambda kv: cites[kv[0]].position):
        c = cites[cid]
        key = (c.raw, c.position)
        item = seen.get(key)
        if not item:
            item = seen[key] = CitationItem(len(citation_items) + 1, c.raw, c.page, [])
            citation_items.append(item)
        for f in findings:
            p = _problem(f)
            if all((q.rule_id, q.message) != (p.rule_id, p.message) for q in item.problems):
                item.problems.append(p)

    list_problems = [_problem(f) for f in list_level]
    found = occurrences(items, citation_items, list_problems)
    statuses = Counter(STATUS_LABELS[c.status] for c in result.corrected.values())
    manifest = json.loads((GUIDE_DIR / "manifest.json").read_text(encoding="utf-8"))
    snapshot = manifest.get("snapshot_date") or "2026-11-08"
    return Report(
        file_name=result.document.name,
        generated=date.today().isoformat(),
        engine_version=__version__,
        guide_snapshot=snapshot,
        references=len(result.references),
        citations=len(result.citations),
        errors=len(result.errors),
        needs_review=len(result.needs_review),
        statuses={k: statuses.get(k, 0) for k in STATUS_LABELS.values()},
        list_problems=list_problems,
        items=items,
        citation_items=citation_items,
        corrected_list=[plain_runs(c.pieces) for c in result.corrected_list],
        type_groups=type_groups(result.references),
        rule_groups=rule_groups(found),
        cited_not_listed=[o for o in found if o.problem.rule_id == CITED_NOT_LISTED],
        listed_not_cited=[o for o in found if o.problem.rule_id == LISTED_NOT_CITED],
        mismatches=[
            o
            for o in found
            if o.problem.rule_id.startswith("MAT-")
            and o.problem.rule_id not in (CITED_NOT_LISTED, LISTED_NOT_CITED)
        ],
        has_pages=result.document.kind == "pdf",
        recency=recency_of(result.references, recency["year"], recency["share"])
        if recency
        else None,
    )
