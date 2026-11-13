"""Deterministic reference parser, AI fallback and fidelity check (plan phase 5, spec §5 ⑥).

Fields are always copied verbatim from the reference: the parser never corrects anything,
because the rule checks need to see exactly what the student wrote. Every candidate parse
is scored; the best one sets `Reference.type`. The source-type decision itself lives in
checkref.classify.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from checkref.models import Author, Reference
from checkref.segment import INITIAL, NAME, PARTICLES

# --------------------------------------------------------------------------- patterns

DATE = re.compile(
    r"\((?P<date>"
    r"(?P<year>(?:1[5-9]|20)\d\d(?:[-–](?:1[5-9]|20)?\d\d)?)(?P<suffix>[a-z])?"
    r"(?:, (?P<detail>[^)]{2,40}))?"
    r"|(?P<nd>n\.d\.)(?:-(?P<ndsuffix>[a-z]))?"
    r"|(?P<press>in press)(?:-(?P<presssuffix>[a-z]))?"
    r")\)\.?"
)
AUTHOR = re.compile(
    rf"(?P<family>{PARTICLES}{NAME}),\s*(?P<initials>(?:{INITIAL}[a-z]?\.\s?-?\s?)+)"
)
EDITOR_ROLE = re.compile(r"\s*\((?P<role>Eds?\.)\)\.?$")
DOI = re.compile(
    r"(?P<doi>(?:https?://(?:dx\.)?doi[.-]org(?:\.[\w-]+)*/|doi:\s?)(?:https?://(?:dx\.)?doi\.org/)?10\.\d{4,9}/\S+?)(?P<stop>\.?)$",
    re.I,
)
RETRIEVED = re.compile(
    r"(?P<stmt>(?:Abstract )?Retrieved (?:(?P<rdate>[A-Z][a-z]+ \d{1,2}, \d{4}), )?from"
    r"|Available from)"
    r"\s+(?:(?P<site>[^:]{3,120}?) website:\s*)?(?P<target>\S.*?)$"
)
LOCATOR = r"(?:pp?\.\s*)?[A-Za-z]{0,4}\d+[A-Za-z]?(?:\s*[-–—‒]\s*[A-Za-z]{0,4}\d+[A-Za-z]?)?"
TAIL = r"\.?(?:\s+(?P<tail>.*))?$"
JOURNAL_NAME = r"(?P<journal>[^,]+?(?:,(?! *\d)[^,]+?)*)"
NAME_ONLY_SCORE = 1.5
# Journal shapes, best first: (pattern, base score). The incomplete shapes exist so that a
# reference missing its volume or journal name still parses and the rules can report it.
JOURNAL_SHAPES = [
    (
        re.compile(
            rf"{JOURNAL_NAME},\s*(?P<volume>\d+[A-Za-z]?)(?:\s*\((?P<issue>[^)]+)\))?"
            rf"(?:,\s*(?P<locator>{LOCATOR}))?{TAIL}"
        ),
        3.0,
    ),
    (re.compile(rf"{JOURNAL_NAME},\s*(?P<locator>\d+\s*[-–—‒]\s*\d+){TAIL}"), 2.0),  # no volume
    # newspaper page: "*The New Zealand Herald*, p. D1."
    (
        re.compile(
            rf"{JOURNAL_NAME},\s*(?P<locator>pp?\.\s*[A-Z]?\d+(?:\s*[-–—‒]\s*[A-Z]?\d+)?){TAIL}"
        ),
        2.0,
    ),
    (
        re.compile(
            rf"(?P<volume>\d+[A-Za-z]?)\s*\((?P<issue>[^)]+)\)(?:,\s*(?P<locator>{LOCATOR}))?{TAIL}"
        ),
        1.5,
    ),
    (
        re.compile(rf"(?P<journal>[^,.]+(?:,(?! *\d)[^,.]+)*){TAIL}"),
        NAME_ONLY_SCORE,
    ),  # name only; must be italic
]
JOURNAL_TAIL = JOURNAL_SHAPES[0][0]
LOCATION_PUBLISHER = re.compile(
    r"(?P<location>(?!In )[A-Z][^.:]{1,60}?):\s+(?P<publisher>[^:]+?)\.$"
)
EDITION = re.compile(r"\s*\((?P<edition>[^()]*?ed\.)\)")
REPORT_NO = re.compile(r"\s*\((?P<report>[^()]*?(?:Report|Bulletin|No\.)[^()]*)\)")
BRACKET = re.compile(r"\s*\[(?P<desc>[^\]]+)\]")
VOLUMES = re.compile(r"\s*\(Vols?\. (?P<volumes>[^()]+)\)$")
STANDARD_NO = re.compile(r"\s*\((?P<number>(?:[A-Z]{2,}[ /]?)+[\w ]*\d[\w:.-]*)\)$")
THESIS = re.compile(
    r"\((?P<degree>(?:Unpublished )?[^()]*?(?:thesis|dissertation|exegesis)[^()]*)\)", re.I
)
# A full stop after a single capital ends a title only when a capital follows: "gen Y. New
# Zealand Management" splits, the abbreviated genus in "B. mori" does not.
SENTENCE_END = re.compile(r"(?<!\b[A-Z])[.?!]\s+|(?<=\b[A-Z])\.\s+(?=[A-Z0-9(*])")
ORIGINAL_WORK = re.compile(r"\s*\(Original work published [^)]+\)\.?")
TRANSLATOR = re.compile(r"\s*\([^()]*?, Trans\.\)")


@dataclass
class Candidate:
    template: str
    score: float
    fields: dict[str, str | None]
    offsets: dict[str, tuple[int, int]] = field(default_factory=dict)
    leftover: str = ""


# --------------------------------------------------------------------------- helpers


def _italic_mask(ref: Reference) -> list[bool]:
    mask: list[bool] = []
    for span in ref.spans:
        mask.extend([span.italic] * len(span.text))
    # `raw` is the joined text stripped; align by leading whitespace removed.
    joined = "".join(s.text for s in ref.spans)
    lead = len(joined) - len(joined.lstrip())
    return mask[lead : lead + len(ref.raw)]


def italic_share(mask: list[bool], start: int, end: int, text: str) -> float:
    """Share of the non-space, non-punctuation characters in text[start:end] that are italic."""
    idx = [i for i in range(start, end) if i < len(text) and text[i].isalnum()]
    if not idx:
        return 0.0
    return sum(mask[i] for i in idx if i < len(mask)) / len(idx)


def parse_authors(text: str) -> tuple[list[Author], str | None]:
    """(people, corporate author) from the author element as written."""
    people = [
        Author(
            family=m.group("family").strip(),
            initials=m.group("initials").strip(),
            raw=m.group(0).strip(),
        )
        for m in AUTHOR.finditer(text)
    ]
    if people:
        return people, None
    corporate = text.strip().rstrip(".").strip()
    return [], corporate or None


def _locate(text: str, value: str | None, start: int = 0) -> tuple[int, int] | None:
    if not value:
        return None
    i = text.find(value, start)
    return (i, i + len(value)) if i >= 0 else None


# --------------------------------------------------------------------------- tail


def _parse_tail(tail: str) -> tuple[dict[str, str | None], str]:
    """DOI / retrieval statement at the end of a reference. Returns (fields, leftover)."""
    tail = tail.strip()
    if not tail:
        return {}, ""
    m = DOI.search(tail)
    if m and m.start() <= 1:
        return {"doi": m.group("doi"), "doi_full_stop": m.group("stop") or None}, ""
    m = RETRIEVED.search(tail)
    if m:
        fields = {
            "retrieval_statement": m.group("stmt")
            + (f" {m.group('site')} website:" if m.group("site") else ""),
            "retrieval_date": m.group("rdate"),
        }
        target = m.group("target").strip()
        db = re.match(r"(?P<db>.+?) database\.?(?:\s*\((?P<acc>[^)]+)\))?$", target)
        if db and "://" not in target:
            fields["database"] = db.group("db")
            fields["report_number"] = db.group("acc")
        else:
            fields["url"] = target
        before = tail[: m.start()].strip()
        return fields, before
    if re.match(r"https?://", tail):
        return {"url": tail}, ""
    return {}, tail


# --------------------------------------------------------------------------- extractors
# Each receives the text after the date and returns candidates with fields relative to it.

Extractor = Callable[[str, list[bool], int], list[Candidate]]


def _group(m: re.Match, name: str) -> str | None:
    return m.groupdict().get(name)


def _journal(rest: str, mask: list[bool], base: int) -> list[Candidate]:
    out = []
    # Split points between title and journal; an italic start means there is no title here
    # (a no-author article: its title stands before the date).
    splits = [
        (m.start() + 1, m.end())
        for m in SENTENCE_END.finditer(rest)
        # An italic run that continues through the full stop ("*Adv. Biol. Biomed*") is one
        # element: not a boundary between the title and the journal.
        if not all(
            base + i < len(mask) and mask[base + i] for i in (m.start() - 1, m.start(), m.end())
        )
    ]
    if base < len(mask) and mask[base]:
        splits.insert(0, (0, 0))
    for title_end, after_start in splits:
        title, after = rest[:title_end], rest[after_start:]
        for shape, shape_score in JOURNAL_SHAPES:
            jm = shape.fullmatch(after)
            if not jm:
                continue
            journal = _group(jm, "journal")
            italic_journal = 0.0
            if journal:
                j0 = base + after_start + jm.start("journal")
                italic_journal = italic_share(mask, j0, j0 + len(journal), " " * j0 + journal)
            if shape is JOURNAL_SHAPES[-1][0] and italic_journal < 0.8:
                continue  # a bare trailing phrase is a journal only if it is italic
            tail = re.sub(r"^Advance online publication\.\s*", "", _group(jm, "tail") or "")
            tail_fields, leftover = _parse_tail(tail)
            locator = _group(jm, "locator")
            is_range = bool(locator and re.search(r"[-–—‒]", locator))
            fields = {
                "title": (title.rstrip(".") if title.endswith(".") else title).strip() or None,
                "container": journal.strip() if journal else None,
                "volume": _group(jm, "volume"),
                "issue": _group(jm, "issue"),
                "pages": locator if is_range else None,
                "article_number": locator if locator and not is_range else None,
                **tail_fields,
            }
            template = "journal_article_no_doi_online" if fields.get("url") else "journal_article"
            score = shape_score + italic_journal - (2.0 if leftover else 0.0)
            if journal and ". " in journal:
                score -= 0.5  # a journal name rarely contains a full stop: prefer a later split
            if title_end == 0:
                score -= 1.0  # an article without a title is unusual (no-author newspapers)
            out.append(Candidate(template, score, fields, leftover=leftover))
            break  # the first (most complete) shape that fits this title split
    return out


def _chapter(rest: str, mask: list[bool], base: int) -> list[Candidate]:
    m = re.match(
        r"(?P<title>.+?[.?!])\s+In\s+(?P<editors>.+?)\s+\((?P<role>Eds?\.)\),\s+(?P<book>.+?)"
        r"(?:\s+\((?:(?P<edition>[^()]*?ed\.),\s*)?(?:Vol\. \d+, )?pp\.\s*(?P<pages>[^)]+)\))?"
        r"\.\s*(?P<pub>.*)$",
        rest,
    )
    if not m:
        return []
    fields: dict[str, str | None] = {
        "title": m.group("title").rstrip(".").strip(),
        "editors_text": m.group("editors"),
        "editor_role": m.group("role"),
        "container": m.group("book").strip(),
        "edition": m.group("edition"),
        "pages": m.group("pages"),
    }
    pub = m.group("pub").strip()
    lp = LOCATION_PUBLISHER.fullmatch(pub)
    leftover = ""
    if lp:
        fields.update(publisher_location=lp.group("location"), publisher=lp.group("publisher"))
        template = "book_chapter"
    else:
        tail_fields, leftover = _parse_tail(pub)
        fields.update(tail_fields)
        template = "ebook_chapter"
    if re.match(r"(?:Wikipedia|.*dictionary|.*encyclopedia)", fields["container"] or "", re.I):
        template = "dictionary_entry_online"
    return [Candidate(template, 4.0 - (2.0 if leftover else 0.0), fields, leftover=leftover)]


def _title_block(rest: str) -> tuple[str, str]:
    """Split 'Title (3rd ed.) [Desc]. remainder' at the end of the title."""
    m = re.match(
        r"(?P<title>.+?[.?!])(?=\s+(?:[A-Z][^.]*?:\s|Retrieved|Available|https?://|doi:|\(|Paper|Symposium|Doctoral|Master|Unpublished|$))",
        rest,
    )
    if not m:
        return rest, ""
    return m.group("title"), rest[m.end() :].strip()


def _italic_run_end(mask: list[bool], start: int, text_len: int) -> int | None:
    """End offset (exclusive, relative to `start`) of an italic run beginning at `start`."""
    if start >= len(mask) or not mask[start]:
        return None
    end = start
    while end < min(len(mask), start + text_len) and mask[end]:
        end += 1
    return end - start


def _title_parts(title: str) -> dict[str, str | None]:
    """Split the elements that follow a book-like title out of it: '(3rd ed.)',
    '(Report No. 5)', '[Video file]', '(Vols. 1-6)', a standard number '(NZS 3910:2013)'."""
    fields: dict[str, str | None] = {"title": title.strip().rstrip(".").strip()}
    for pattern, key in (
        (EDITION, "edition"),
        (REPORT_NO, "report_number"),
        (BRACKET, "description"),
        (VOLUMES, "volume"),
        (STANDARD_NO, "report_number"),
    ):
        found = pattern.search(fields["title"] or "")
        if found and not fields.get(key):
            fields[key] = found.group(1)
            fields["title"] = (
                fields["title"][: found.start()] + fields["title"][found.end() :]
            ).strip()
    fields["title"] = (fields["title"] or "").rstrip(".").strip()
    return fields


def _book_like(rest: str, mask: list[bool], base: int) -> list[Candidate]:
    run = _italic_run_end(mask, base, len(rest))
    if run and run < len(rest) and not _title_block(rest)[1]:
        # The italic title ends before ": Publisher." or ". Publisher." — split there.
        title, remainder = rest[:run].strip(), rest[run:].lstrip(" .:").strip()
    else:
        title, remainder = _title_block(rest)
    fields = _title_parts(title)
    t0 = base + rest.find(fields["title"]) if fields["title"] else base
    italic_title = italic_share(
        mask, t0, t0 + len(fields["title"] or ""), " " * t0 + (fields["title"] or "")
    )
    out: list[Candidate] = []

    lp = LOCATION_PUBLISHER.fullmatch(remainder)
    if lp:
        fields.update(publisher_location=lp.group("location"), publisher=lp.group("publisher"))
        template = "report_print" if fields.get("report_number") else "book"
        out.append(Candidate(template, 2.5 + italic_title, fields))
        return out

    tail_fields, leftover = _parse_tail(remainder)
    if not tail_fields:
        publisher_only = re.fullmatch(r"(?P<publisher>[A-Z][^.:/]{1,80})\.", remainder)
        if publisher_only and italic_title > 0.5:  # publisher given without its location
            fields["publisher"] = publisher_only.group("publisher")
            out.append(Candidate("book", 1.5 + italic_title, fields))
        return out
    fields.update(tail_fields)
    url = fields.get("url") or ""
    if fields.get("doi"):
        template = "ebook_doi"
    elif fields.get("database"):
        template = "report_database"
    elif fields.get("report_number"):
        template = "report_online"
    elif url.lower().split("?")[0].endswith((".pdf", ".ppt", ".pptx")) or fields.get("description"):
        template = "web_document"
    elif fields.get("retrieval_date"):
        template = "webpage"
    else:
        template = "web_document"
    # A partly italic "title" usually holds an italic container (newspaper, journal) instead.
    mixed = 0.2 < italic_title < 0.8
    score = 2.0 + italic_title - (2.0 if leftover else 0.0) - (1.0 if mixed else 0.0)
    out.append(Candidate(template, score, fields, leftover=leftover))
    return out


def _thesis(rest: str, mask: list[bool], base: int) -> list[Candidate]:
    m = THESIS.search(rest)
    if not m:
        return []
    fields: dict[str, str | None] = {
        "title": rest[: m.start()].strip().rstrip(".").strip(),
        "degree": m.group("degree"),
    }
    after = rest[m.end() :].lstrip(". ").strip()
    tail_fields, leftover = _parse_tail(after)
    if tail_fields:
        fields.update(tail_fields)
        template = "thesis_database" if after.startswith("Available") else "thesis_repository"
    else:
        fields["publisher"] = after.rstrip(".")  # "Institution, Location"
        template, leftover = "thesis_unpublished", ""
    return [Candidate(template, 5.0 - (2.0 if leftover else 0.0), fields, leftover=leftover)]


def _conference(rest: str, mask: list[bool], base: int) -> list[Candidate]:
    sym = re.fullmatch(
        r"(?P<title>.+?[.?!])\s+In (?P<chair>.+?) \(Chair\), (?P<symposium>.+?)\. "
        r"Symposium conducted at (?P<meeting>.+?)\.",
        rest,
    )
    if sym:
        fields = {
            "title": sym.group("title").rstrip(".").strip(),
            "editors_text": sym.group("chair"),
            "container": sym.group("symposium"),
            "meeting": sym.group("meeting"),
        }
        return [Candidate("symposium_contribution", 5.0, fields)]
    m = re.search(
        r"\b(?:Paper|Poster) presented at (?P<meeting>.+?)"
        r"(?:\.\s+(?P<tail>(?:Abstract )?Retrieved.*)|\.?$)",
        rest,
    )
    if not m:
        return []
    fields: dict[str, str | None] = {
        "title": rest[: m.start()].strip().rstrip(".").strip(),
        "meeting": m.group("meeting"),
    }
    tail_fields, leftover = _parse_tail(m.group("tail") or "")
    fields.update(tail_fields)
    template = "conference_paper_online" if tail_fields else "conference_paper_unpublished"
    return [Candidate(template, 5.0, fields, leftover=leftover)]


def _software(rest: str, mask: list[bool], base: int) -> list[Candidate]:
    desc = re.search(r"\[(?P<desc>(?:Computer|Mobile application) software|Source code)\]", rest)
    version = re.search(r"\(?\bVersion\s+(?P<version>[\d.]+)\)?", rest)
    markers = [m for m in (desc, version) if m]
    if not markers:
        return []
    fields: dict[str, str | None] = {
        "description": desc.group("desc") if desc else None,
        "version": version.group("version") if version else None,
    }
    first, last = min(markers, key=lambda m: m.start()), max(markers, key=lambda m: m.end())
    fields["title"] = rest[: first.start()].strip().rstrip(".( ").strip()
    after = rest[last.end() :].strip(" .)]")
    tail_fields, leftover = _parse_tail(after)
    fields.update(tail_fields)
    if not tail_fields:
        leftover = after
    if leftover:
        lp = LOCATION_PUBLISHER.fullmatch(leftover.rstrip(".") + ".")
        if lp:
            fields.update(publisher_location=lp.group("location"), publisher=lp.group("publisher"))
            leftover = ""
        elif not re.search(r"[A-Za-z]{2}", leftover):  # stray numbers, e.g. "Version 0.11, 2"
            fields["extra"], leftover = leftover.strip(" ,."), ""
    score = 4.5 if fields["description"] else 3.5  # a "Version x" marker alone is weaker
    return [Candidate("software", score - (1.0 if leftover else 0.0), fields, leftover=leftover)]


EXTRACTORS: list[Extractor] = [_thesis, _conference, _chapter, _software, _journal, _book_like]


# --------------------------------------------------------------------------- main


@dataclass
class ParseResult:
    ok: bool
    candidates: list[Candidate]
    reason: str = ""


def parse_reference(ref: Reference) -> ParseResult:
    """Fill `ref` in place with the best deterministic parse. ok=False -> AI fallback."""
    text = ref.raw
    mask = _italic_mask(ref)
    date = DATE.search(text[:600])
    if not date:
        return ParseResult(False, [], "no (year) element found — possibly another citation style")

    head = text[: date.start()].strip()
    rest = text[date.end() :].strip()
    base = date.end() + (len(text[date.end() :]) - len(text[date.end() :].lstrip()))
    # Elements the templates add around the core: kept verbatim in `extra`.
    extras = []
    for pattern in (ORIGINAL_WORK, TRANSLATOR):
        found = pattern.search(rest)
        if found:
            extras.append(found.group(0).strip(" ."))
            rest = (rest[: found.start()] + rest[found.end() :]).strip()
            if pattern is ORIGINAL_WORK and not rest.endswith("."):
                rest += "."

    role = EDITOR_ROLE.search(head)
    author_text = head[: role.start()] if role else head
    people, corporate = parse_authors(author_text)
    title_first = not people and italic_share(mask, 0, len(head), text) > 0.6
    software_first = BRACKET.search(head) and "software" in head.lower()

    candidates: list[Candidate] = []
    if software_first:
        # No rightsholder: "Title [Computer software]. (2014). Retrieved from …"
        desc = BRACKET.search(head)
        tail_fields, leftover = _parse_tail(rest)
        fields = {
            "title": head[: desc.start()].strip(),
            "description": desc.group("desc"),
            **tail_fields,
        }
        candidates.append(
            Candidate(
                "software_no_author", 5.0 - (2.0 if leftover else 0.0), fields, leftover=leftover
            )
        )
    elif title_first:
        # No author: the title stands in the author position ("*Title*. (2008). ...").
        tail_fields, leftover = _parse_tail(rest)
        lp = LOCATION_PUBLISHER.fullmatch(rest)
        fields = {**_title_parts(head), **tail_fields}
        if lp:
            fields.update(publisher_location=lp.group("location"), publisher=lp.group("publisher"))
            candidates.append(Candidate("book_no_author", 4.0, fields))
        elif tail_fields:
            candidates.append(
                Candidate(
                    "webpage_no_author", 4.0 - (2.0 if leftover else 0.0), fields, leftover=leftover
                )
            )
    else:
        for extractor in EXTRACTORS:
            candidates.extend(extractor(rest, mask, base))
        if role:  # edited book: editors in the author position
            for c in candidates:
                if c.template in {"book", "ebook_doi", "ebook_url"}:
                    c.template, c.score = "edited_book", c.score + 0.5

    if not people and date.group("detail"):
        # No personal author and an exact date: a no-author newspaper article, whose title
        # stands before the date — lift the title-less penalty from _journal.
        for c in candidates:
            if c.template in JOURNAL_FAMILY and not c.fields.get("title"):
                c.score += 1.0
    candidates.sort(key=lambda c: c.score, reverse=True)
    if not candidates or candidates[0].leftover:
        return ParseResult(False, candidates, "the reference does not fit any template cleanly")

    best = candidates[0]
    ref.type_candidates = [(c.template, round(c.score, 2)) for c in candidates]
    ref.parsed_by = "rules"
    no_author = title_first or software_first
    ref.author_text = author_text.strip() if not no_author else None
    ref.authors, ref.corporate_author = (people, corporate) if not no_author else ([], None)
    if extras:
        ref.extra = "; ".join(extras)
    ref.editor_role = role.group("role") if role else best.fields.get("editor_role")
    if role:
        ref.editors, ref.authors = ref.authors, []
    elif best.fields.get("editors_text"):
        ref.editors = [
            Author(family=n.strip(), raw=n.strip())
            for n in re.split(r",\s*(?:&\s*)?|\s+&\s+", best.fields["editors_text"] or "")
            if n.strip()
        ]
    ref.year = date.group("year") or date.group("nd") or date.group("press")
    ref.year_suffix = date.group("suffix") or date.group("ndsuffix") or date.group("presssuffix")
    ref.date_detail = date.group("detail")
    for key, value in best.fields.items():
        if key in Reference.model_fields and value is not None:
            setattr(ref, key, value)

    # Offsets and italics of the main fields, located in the raw text.
    cursor = 0
    for key in (
        "author_text",
        "title",
        "container",
        "volume",
        "issue",
        "pages",
        "article_number",
        "edition",
        "publisher_location",
        "publisher",
        "doi",
        "url",
    ):
        value = getattr(ref, key, None)
        span = _locate(text, value, cursor if key != "author_text" else 0)
        if span:
            ref.offsets[key] = span
            ref.italics[key] = round(italic_share(mask, span[0], span[1], text), 2)
            cursor = span[1] if key != "author_text" else cursor
    ref.offsets["date"] = (date.start(), date.end())
    ref.type = refine_type(best.template, ref)
    if (
        ref.type in JOURNAL_FAMILY | {"newspaper_article"}
        and not ref.title
        and ref.corporate_author
    ):
        # No author: what stands before the date is the article's title.
        ref.type, ref.title, ref.corporate_author = (
            "newspaper_article_no_author",
            ref.corporate_author,
            None,
        )
        ref.author_text = None
    if ref.type == "dictionary_entry_online" and not ref.container and ref.corporate_author:
        # "Light. (n.d.). In *Merriam-Webster's online dictionary*": the entry stands in the
        # author position and the work follows "In".
        ref.title, ref.container = ref.corporate_author, re.sub(r"^In\s+", "", ref.title or "")
        ref.author_text = ref.corporate_author = None
    episode = re.fullmatch(
        r"(?P<title>.+?)\. In (?P<producer>.+?) \(Executive producer\), (?P<series>.+)",
        ref.title or "",
    )
    if ref.type == "tv_episode" and episode:
        ref.title, ref.editors_text, ref.container = episode.group("title", "producer", "series")
    if ref.type == "course_material" and ref.title and ". " in ref.title:
        # "*Title* [Course notes]. Paper name 123456." — the course paper follows the title.
        ref.title, ref.container = ref.title.rsplit(". ", 1)
    return ParseResult(True, candidates)


AV_TYPES = {
    "motion picture": "film",
    "television series": "tv_series",
    "television series episode": "tv_episode",
    "blog post": "blog_post",
}
VIDEO_DESCRIPTIONS = {"video file", "video podcast", "audio podcast", "streaming video", "dvd"}
JOURNAL_FAMILY = {"journal_article", "journal_article_no_doi_online"}


def refine_type(template: str, ref: Reference) -> str:
    """Sharpen the source type using markers that the base patterns share (spec §5 ⑦)."""
    raw, desc = ref.raw, (ref.description or "").lower()
    if "special issue" in desc or "[special issue]" in raw.lower():
        return "journal_special_issue"
    if desc in AV_TYPES:
        return AV_TYPES[desc]
    if desc in VIDEO_DESCRIPTIONS:
        title_italic = ref.italics.get("title", 0.0) >= 0.5
        return "online_video" if title_italic or desc != "video file" else "online_video_series"
    if "software" in desc or desc == "source code":
        return template if template.startswith("software") else "software"
    if desc in {"course notes", "powerpoint slide", "powerpoint slides"} and re.search(
        r"\]\.\s+[^.]+\.\s+Retrieved", raw
    ):
        return "course_material"
    if "kindle" in desc:
        return "ebook_url"
    if template in JOURNAL_FAMILY | {"ebook_doi", "web_document", "webpage"}:
        if ref.year == "in press" and not ref.volume:
            return "journal_article_in_press"
        if "Advance online publication" in raw:
            return "journal_article_advance_online"
    if template in JOURNAL_FAMILY and ref.date_detail:
        is_newspaper = (ref.pages or ref.article_number or "").startswith("p") or not ref.volume
        return "newspaper_article" if is_newspaper else "magazine_article"
    if template in {"web_document", "webpage"} and ref.date_detail and ref.container:
        return "newspaper_article"
    if re.search(r"\.\s+In \S", raw) and template in {"web_document", "webpage", "ebook_url"}:
        return "dictionary_entry_online"
    if "Patent No." in (ref.title or ""):
        return "patent"
    if re.search(r"\((?:[A-Z]{2,}[ /]?)+[\w ]*\d[\w:.-]*\)", raw) and template in {
        "book",
        "report_print",
        "report_online",
        "web_document",
    }:
        return "standard"
    if template in {"book", "edited_book"}:
        if (ref.publisher or "").strip() == "Author":
            return "book_author_as_publisher"
        if "(Vols." in raw:
            return "book_multivolume"
    if ref.extra and "Original work published" in ref.extra:
        return "book_reprint_translation"
    return template


# --------------------------------------------------------------------------- fidelity

LITERALS = {
    "chair",
    "executive",
    "producer",
    "symposium",
    "conducted",
    "version",
    "in",
    "eds",
    "ed",
    "pp",
    "p",
    "retrieved",
    "from",
    "available",
    "website",
    "database",
    "vol",
    "vols",
    "trans",
    "original",
    "work",
    "published",
    "paper",
    "presented",
    "at",
    "the",
    "meeting",
    "of",
    "doi",
    "https",
    "http",
    "org",
    "advance",
    "online",
    "publication",
    "abstract",
    "unpublished",
    "nd",
    "press",
}


def _words(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[^\W_]+", text)]


def missing_words(ref: Reference) -> list[str]:
    """Words of the raw reference not accounted for by the parsed fields (spec §5 ⑥).

    Empty means the parse is faithful: nothing was dropped. Words that appear in fields but
    not in the raw text (invented content) are checked by `invented_words`.
    """
    covered: set[str] = set(LITERALS)
    for value in _field_values(ref):
        covered.update(_words(value))
    return [w for w in _words(ref.raw) if w not in covered]


def invented_words(ref: Reference) -> list[str]:
    raw = set(_words(ref.raw))
    return [w for value in _field_values(ref) for w in _words(value) if w not in raw]


def _field_values(ref: Reference) -> list[str]:
    values = [a.raw or f"{a.family} {a.initials}" for a in ref.authors + ref.editors]
    for key in (
        "author_text",
        "corporate_author",
        "editor_role",
        "editors_text",
        "year",
        "year_suffix",
        "date_detail",
        "title",
        "container",
        "volume",
        "issue",
        "pages",
        "article_number",
        "edition",
        "publisher",
        "publisher_location",
        "doi",
        "url",
        "retrieval_statement",
        "retrieval_date",
        "database",
        "description",
        "degree",
        "report_number",
        "meeting",
        "version",
        "extra",
    ):
        value = getattr(ref, key)
        if value:
            values.append(value)
    return values
