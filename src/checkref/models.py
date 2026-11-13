"""Core data types shared by every pipeline stage (see spec.md §5).

Coordinates are PDF points with the origin at the top-left of the page,
matching pdfplumber's `top`/`bottom` convention. DOCX input has no
geometry, so its positions are left as None.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Span(BaseModel):
    """A run of text sharing one font, as drawn on the page."""

    text: str
    page: int | None = None  # None for DOCX, which has no fixed pages
    x0: float | None = None
    top: float | None = None
    x1: float | None = None
    bottom: float | None = None
    font: str = ""
    size: float = 0.0
    italic: bool = False
    bold: bool = False


class LineRole(StrEnum):
    BODY = "body"
    PAGE_NUMBER = "page_number"
    HEADER = "header"
    FOOTER = "footer"


class Line(BaseModel):
    """One visual line of text (PDF) or one paragraph (DOCX)."""

    spans: list[Span]
    index: int  # position in the document, 0-based
    page: int | None = None
    role: LineRole = LineRole.BODY
    # Geometry in points (PDF only).
    x0: float | None = None
    x1: float | None = None
    top: float | None = None
    bottom: float | None = None
    # Paragraph layout in points (DOCX, from w:ind / w:spacing / w:jc).
    left_indent: float | None = None
    first_line_indent: float | None = None  # negative = hanging indent
    line_spacing: float | None = None  # multiple of single spacing (2.0 = double)
    space_before: float | None = None
    space_after: float | None = None
    align: str | None = None  # "left" | "center" | "right" | "both"
    style: str | None = None  # paragraph style name, e.g. "Heading 1"

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    @property
    def size(self) -> float:
        """Font size of most of the line's text."""
        sizes: dict[float, int] = {}
        for s in self.spans:
            sizes[s.size] = sizes.get(s.size, 0) + len(s.text.strip())
        return max(sizes, key=lambda k: sizes[k]) if sizes else 0.0

    @property
    def markdown(self) -> str:
        """Text with italic runs wrapped in *...* — for display and the AI only."""
        out = []
        for s in self.spans:
            core = s.text.strip()
            if s.italic and core:
                lead = s.text[: len(s.text) - len(s.text.lstrip())]
                trail = s.text[len(s.text.rstrip()) :]
                out.append(f"{lead}*{core}*{trail}")
            else:
                out.append(s.text)
        return "".join(out).replace("* *", " ")


class Document(BaseModel):
    """A thesis after ingestion."""

    name: str
    kind: str  # "pdf" | "docx"
    page_count: int | None = None
    page_width: float | None = None  # points, PDF only
    page_height: float | None = None
    lines: list[Line] = Field(default_factory=list)


class Author(BaseModel):
    family: str
    initials: str = ""
    raw: str = ""


class Reference(BaseModel):
    """One reference-list entry, split into fields (spec §5 ⑥)."""

    id: str
    raw: str
    page: int | None = None
    lines: list[Line] = Field(default_factory=list)
    spans: list[Span] = Field(default_factory=list)  # the joined text, with styles
    merged_part: bool = False  # split off from an entry that merged two references

    # Source type (template id) and how it was decided (spec §5 ⑥ ⑦).
    type: str | None = None
    type_candidates: list[tuple[str, float]] = Field(default_factory=list)
    parsed_by: str | None = None  # "rules" | "ai" | None (not parsed)
    # Where each field sits in `raw` (start, end) and the italic share of its characters.
    offsets: dict[str, tuple[int, int]] = Field(default_factory=dict)
    italics: dict[str, float] = Field(default_factory=dict)

    author_text: str | None = None  # the author element exactly as written
    authors: list[Author] = Field(default_factory=list)
    corporate_author: str | None = None
    editors: list[Author] = Field(default_factory=list)
    editors_text: str | None = None  # the "In ..." editors (or symposium chair) as written
    editor_role: str | None = None  # "Ed." | "Eds." as written
    year: str | None = None
    year_suffix: str | None = None
    date_detail: str | None = None

    title: str | None = None
    container: str | None = None  # journal, newspaper, book (for chapters), website
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    article_number: str | None = None

    edition: str | None = None
    publisher: str | None = None
    publisher_location: str | None = None

    doi: str | None = None  # as written, e.g. "https://doi.org/10.1/x" or "doi:10.1/x"
    url: str | None = None
    retrieval_statement: str | None = None  # e.g. "Retrieved June 26, 2022, from"
    retrieval_date: str | None = None
    database: str | None = None
    description: str | None = None  # square-bracket text, e.g. "Video file"
    degree: str | None = None  # thesis
    report_number: str | None = None
    meeting: str | None = None  # conference
    version: str | None = None  # software
    extra: str | None = None  # text the parser could not place


class CitationKind(StrEnum):
    PARENTHETICAL = "parenthetical"
    NARRATIVE = "narrative"
    YEAR_FIRST = "year_first"


class Citation(BaseModel):
    """One in-text citation; a bracket holding several works becomes several Citations."""

    id: str
    raw: str  # the whole citation as written: "(Li & Seale, 2007; Wu, 2010)", "Li et al. (2007)"
    item: str = ""  # this work's part of it: "Li & Seale, 2007"
    kind: CitationKind
    group: int = 0  # citations from the same bracket share a group
    position: int = 0  # character offset in the body text (order of first use)
    page: int | None = None
    authors: list[str] = Field(default_factory=list)  # surnames (or a corporate name) as written
    initials: list[str] = Field(default_factory=list)  # "J." from "J. Smith", if given
    et_al: bool = False
    et_al_written: str | None = None  # "et al." / "et al" / "et. al.", as written
    connector: str | None = None  # "&" or "and" before the last author
    year: str | None = None
    year_suffix: str | None = None
    original_year: str | None = None  # "1900" from "1900/1953" (reprints)
    locator: str | None = None  # e.g. "p. 5"
    title: str | None = None  # a no-author citation by title
    secondary: bool = False  # the "as cited in" source
    personal: bool = False  # personal communication: not in the reference list
    reference_id: str | None = None  # set by matching


class Level(StrEnum):
    ERROR = "error"
    NEEDS_REVIEW = "needs_review"


class Location(BaseModel):
    page: int | None = None
    top: float | None = None
    x0: float | None = None


class Finding(BaseModel):
    """One problem reported to the user. Every finding cites a rulebook rule."""

    level: Level
    rule_id: str
    message: str
    location: Location = Field(default_factory=Location)
    reference_id: str | None = None
    citation_id: str | None = None
    original: str | None = None
    correction: str | None = None


class Piece(BaseModel):
    """A run of a corrected reference: text, its style, and whether it is a placeholder."""

    text: str
    italic: bool = False
    placeholder: bool = False  # e.g. "[page range]": information the student must supply


class CorrectionStatus(StrEnum):
    CORRECT = "correct"  # nothing to change
    CORRECTED = "corrected"  # every error is fixed (placeholders may remain)
    PARTIAL = "partial"  # some errors could not be fixed automatically
    NOT_CORRECTED = "not_corrected"  # the reference could not be read or rendered reliably


class CorrectedReference(BaseModel):
    """The corrected form of one reference-list entry (spec §5 ⑨, plan phase 7)."""

    reference_id: str
    status: CorrectionStatus
    pieces: list[Piece] = Field(default_factory=list)
    unfixed: list[str] = Field(default_factory=list)  # rule ids not fixed automatically
    notes: list[str] = Field(default_factory=list)  # e.g. "check the capitals of proper nouns"

    @property
    def text(self) -> str:
        return "".join(p.text for p in self.pieces)

    @property
    def markdown(self) -> str:
        runs: list[list] = []  # [italic, text], adjacent pieces of one style merged
        for p in self.pieces:
            if runs and runs[-1][0] == p.italic:
                runs[-1][1] += p.text
            else:
                runs.append([p.italic, p.text])
        out = []
        for italic, text in runs:
            core = text.strip()
            if italic and core:
                lead, trail = text[: len(text) - len(text.lstrip())], text[len(text.rstrip()) :]
                out.append(f"{lead}*{core}*{trail}")
            else:
                out.append(text)
        return "".join(out)

    @property
    def placeholders(self) -> list[str]:
        return [p.text for p in self.pieces if p.placeholder]
