"""In-text citation format checks (CIT-) and matching results (MAT-) — plan phase 8.

Each check receives (rule, CiteContext) and returns findings. Several works in one bracket
are separate citations; a work cited with two years ("Gogel, 1990, 2006") is two. Findings
are reported once per citation as written.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from checkref.citations.extract import (
    SECONDARY,
    BodyText,
    body_text,
    extract,
    parse_authors,
)
from checkref.citations.match import Match, RefKey, match, name_key, reference_keys
from checkref.models import Citation, CitationKind, Document, Finding, Level, Location, Reference
from checkref.rules.checks import CITE_CHECKS, _fold, proper_noun_list
from checkref.rules.rulebook import Rule, rulebook
from checkref.segment import Segmentation

PARENTHETICAL = CitationKind.PARENTHETICAL
MONTH_DATE = re.compile(
    r"(?:January|February|March|April|May|June|July|August|September|October|November|"
    r"December) \d{1,2}, \d{4}"
)


@dataclass
class CiteContext:
    body: BodyText
    citations: list[Citation]
    refs: list[Reference]
    keys: list[RefKey]
    matches: list[Match]
    by_id: dict[str, RefKey] = field(default_factory=dict)

    def key(self, c: Citation) -> RefKey | None:
        return self.by_id.get(c.reference_id or "")

    def first_use(self) -> dict[str, Citation]:
        """The first citation of each reference, in reading order."""
        first: dict[str, Citation] = {}
        for c in self.citations:
            if c.reference_id and c.reference_id not in first:
                first[c.reference_id] = c
        return first


CiteCheck = Callable[[Rule, CiteContext], list[Finding]]


def cite_check(name: str):
    def register(fn: CiteCheck) -> CiteCheck:
        CITE_CHECKS[name] = fn
        return fn

    return register


def finding(
    rule: Rule,
    c: Citation,
    message: str,
    correction: str | None = None,
    level: Level | None = None,
    original: str | None = None,
) -> Finding:
    return Finding(
        level=level or Level(rule.level),
        rule_id=rule.id,
        message=message,
        location=Location(page=c.page),
        reference_id=c.reference_id,
        citation_id=c.id,
        original=original or c.raw,
        correction=correction,
    )


def _once(findings: list[Finding]) -> list[Finding]:
    """One finding per citation as written (multi-year items produce several Citations)."""
    seen, out = set(), []
    for f in findings:
        key = (f.rule_id, f.original, f.message, f.location.page)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def _cited(c: Citation) -> list[Citation]:
    return [c] if not c.personal else []


def _names(c: Citation, joiner: str) -> str:
    names = c.authors
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} {joiner} {names[1]}"
    return ", ".join(names[:-1]) + f", {joiner} " + names[-1]


def _year(c: Citation) -> str:
    return f"{c.year}{c.year_suffix or ''}"


def _family(k: RefKey) -> str:
    return k.name


def _rendered(c: Citation, authors: str, year: str | None = None) -> str:
    year = year or _year(c)
    if c.initials and c.initials[0] and not authors.startswith(c.initials[0]):
        authors = f"{c.initials[0]} {authors}"  # "L. Chen et al." keeps its initials
    loc = f", {c.locator}" if c.locator else ""
    if c.kind == PARENTHETICAL:
        return f"({authors}, {year}{loc})"
    if c.kind == CitationKind.YEAR_FIRST:
        return f"In {year}, {authors}"
    return f"{authors} ({year}{loc})"


# --------------------------------------------------------------------------- format


@cite_check("cite_ampersand")
def cite_ampersand(rule, cx):
    out = []
    for c in cx.citations:
        if c.personal or not c.connector or len(c.authors) < 2:
            continue
        if c.kind == PARENTHETICAL and c.connector == "and":
            out.append(
                finding(
                    rule,
                    c,
                    "Inside brackets, use '&' between the last two authors.",
                    _rendered(c, _names(c, "&")),
                )
            )
        elif c.kind != PARENTHETICAL and c.connector == "&":
            out.append(
                finding(
                    rule,
                    c,
                    "In running text, use 'and' between the last two authors, not '&'.",
                    _rendered(c, _names(c, "and")),
                )
            )
    return _once(out)


@cite_check("cite_punctuation")
def cite_punctuation(rule, cx):
    out = []
    for c in cx.citations:
        if c.personal or c.title is not None:
            continue
        problems = []
        if c.kind == PARENTHETICAL:
            body = SECONDARY.split(c.item)[-1]
            if re.search(r"[A-Za-z.\]’'”\"]\s+(?:1[5-9]|20)\d\d", body):
                problems.append("a comma before the year")
            if re.search(r",(?=[^\s\d])|,(?=\d)", body):
                problems.append("a space after each comma")
            if re.search(r"\s\)$", c.raw):
                problems.append("no space before the closing bracket")
        elif c.kind == CitationKind.NARRATIVE and re.search(r",\s*\($", c.raw.split("(")[0] + "("):
            problems.append("no comma before the bracketed year")
        if len(c.authors) >= 3 and c.connector and not re.search(r",\s*(?:&|and)\s", c.item):
            problems.append(f"a comma before '{c.connector}' (three or more authors)")
        if problems:
            joiner = "&" if c.kind == PARENTHETICAL else "and"
            authors = _names(c, joiner) + (" et al." if c.et_al else "")
            out.append(
                finding(
                    rule,
                    c,
                    "Punctuation: " + "; ".join(problems) + ".",
                    _rendered(c, authors) if not c.secondary else None,
                )
            )
    return _once(out)


def _author_rule(cx: CiteContext):
    """(citation, reference key, is first use) for citations of parsed references."""
    first = cx.first_use()
    for c in cx.citations:
        k = cx.key(c)
        if c.personal or not k or not k.ref.type or not (k.ref.authors or k.ref.editors):
            continue
        yield c, k, first.get(k.ref.id) is c


def _all_names(k: RefKey, joiner: str) -> str:
    people = [a.family for a in (k.ref.authors or k.ref.editors)]
    if len(people) == 1:
        return people[0]
    if len(people) == 2:
        return f"{people[0]} {joiner} {people[1]}"
    return ", ".join(people[:-1]) + f", {joiner} " + people[-1]


def _joiner(c: Citation) -> str:
    return "&" if c.kind == PARENTHETICAL else "and"


@cite_check("cite_et_al_1_2")
def cite_et_al_1_2(rule, cx):
    out = []
    for c, k, _ in _author_rule(cx):
        if k.authors <= 2 and (c.et_al or len(c.authors) < k.authors):
            out.append(
                finding(
                    rule,
                    c,
                    f"The work has {k.authors} author(s): name "
                    f"{'both' if k.authors == 2 else 'the author'} in every citation, "
                    "without 'et al.'.",
                    _rendered(c, _all_names(k, _joiner(c))),
                )
            )
    return _once(out)


@cite_check("cite_et_al_3_5")
def cite_et_al_3_5(rule, cx):
    out = []
    for c, k, first in _author_rule(cx):
        if not 3 <= k.authors <= 5:
            continue
        if first and (c.et_al or len(c.authors) < k.authors):
            out.append(
                finding(
                    rule,
                    c,
                    f"First citation of a work with {k.authors} authors: name all of them.",
                    _rendered(c, _all_names(k, _joiner(c))),
                )
            )
        elif not first and not c.et_al:
            out.append(
                finding(
                    rule,
                    c,
                    f"After the first citation, a work with {k.authors} authors is cited as "
                    "'first author et al.'.",
                    _rendered(c, f"{_family(k)} et al."),
                )
            )
    return _once(out)


@cite_check("cite_et_al_6_plus")
def cite_et_al_6_plus(rule, cx):
    out = []
    for c, k, _ in _author_rule(cx):
        if k.authors >= 6 and (not c.et_al or len(c.authors) > 1):
            out.append(
                finding(
                    rule,
                    c,
                    f"A work with {'eight or more' if k.authors >= 8 else k.authors} authors "
                    "is cited as 'first author et al.' from the first citation.",
                    _rendered(c, f"{_family(k)} et al."),
                )
            )
    return _once(out)


@cite_check("cite_et_al_spelling")
def cite_et_al_spelling(rule, cx):
    out = [
        finding(
            rule,
            c,
            f"Write 'et al.' (written here as '{c.et_al_written}').",
            c.raw.replace(c.et_al_written, "et al.", 1),
        )
        for c in cx.citations
        if c.et_al and c.et_al_written and c.et_al_written != "et al."
    ]
    return _once(out)


@cite_check("cite_corporate_abbreviation")
def cite_corporate_abbreviation(rule, cx):
    out = []
    for k in cx.keys:
        if not k.ref.corporate_author:
            continue
        cites = [c for c in cx.citations if c.reference_id == k.ref.id]
        if not cites:
            continue
        abbreviated = [c for c in cites if c.authors and re.fullmatch(r"[A-Z]{2,8}", c.authors[0])]
        first = cites[0]
        full = k.ref.corporate_author
        if re.fullmatch(r"[A-Z]{2,8}", full):
            continue  # the name is itself an abbreviation ("CITES")
        if abbreviated and (first in abbreviated or "[" not in first.item):
            abbr = abbreviated[0].authors[0]
            out.append(
                finding(
                    rule,
                    first,
                    "Introduce the abbreviation the first time the organisation is cited: "
                    f"{full} [{abbr}], then use {abbr}.",
                    _rendered(first, f"{full} [{abbr}]"),
                )
            )
    return _once(out)


def _groups(cx: CiteContext) -> dict[int, list[Citation]]:
    groups: dict[int, list[Citation]] = {}
    for c in cx.citations:
        if c.kind == PARENTHETICAL and not c.personal:
            groups.setdefault(c.group, []).append(c)
    return groups


def _item_key(c: Citation) -> str:
    return name_key(c.authors[0]) if c.authors else name_key(c.title or "")


@cite_check("cite_multiple_order")
def cite_multiple_order(rule, cx):
    out = []
    for cites in _groups(cx).values():
        items: list[Citation] = []
        for c in cites:
            if not items or items[-1].item != c.item:
                items.append(c)
        if len(items) < 2:
            continue
        problems = []
        inner = items[0].raw[1:-1]
        if re.search(r"\d[a-z]?,\s+(?:[A-Z][a-z]|[A-Z]\.)", inner) and ";" not in inner:
            problems.append("separate the works with semicolons")
        keys = [_item_key(c) for c in items]
        if keys != sorted(keys):
            problems.append("list the works in alphabetical order, as in the reference list")
        if problems:
            ordered = sorted(items, key=_item_key)
            out.append(
                finding(
                    rule,
                    items[0],
                    "Several works in one bracket: " + "; ".join(problems) + ".",
                    "(" + "; ".join(c.item for c in ordered) + ")",
                )
            )
    return _once(out)


@cite_check("cite_same_author_once")
def cite_same_author_once(rule, cx):
    out = []
    for cites in _groups(cx).values():
        items: list[Citation] = []
        for c in cites:
            if not items or items[-1].item != c.item:
                items.append(c)
        for a, b in zip(items, items[1:], strict=False):
            if a.authors and a.authors == b.authors and a.et_al == b.et_al:
                names = _names(a, "&") + (" et al." if a.et_al else "")
                out.append(
                    finding(
                        rule,
                        a,
                        "Works by the same author(s) in one bracket: give the name once, "
                        "then the years in order.",
                        f"({names}, {_year(a)}, {_year(b)})",
                    )
                )
        for c in items:
            years = [x.year for x in cites if x.item == c.item]
            if len(years) > 1 and years != sorted(years):
                out.append(finding(rule, c, "Give the years in chronological order."))
    return _once(out)


@cite_check("cite_same_surname_initials")
def cite_same_surname_initials(rule, cx):
    # Different people: the same surname with a different first initial ("Li, Q." and
    # "Li, G."). "Ajmal, S." and "Ajmal, S. A." are taken to be one person.
    shared: dict[str, set[str]] = {}
    for k in cx.keys:
        people = k.ref.authors or k.ref.editors
        if people and people[0].initials:
            shared.setdefault(name_key(people[0].family), set()).add(people[0].initials[0])
    out = []
    for c in cx.citations:
        k = cx.key(c)
        people = (k.ref.authors or k.ref.editors) if k else []
        if not people or len(shared.get(name_key(people[0].family), set())) < 2:
            continue
        if not (c.initials and c.initials[0]):
            # The reference's spelling of the first author: "Ziyun Li" (a given name written
            # out) becomes "Z. Li", not "Z. Ziyun Li".
            written = c.model_copy(update={"authors": [people[0].family, *c.authors[1:]]})
            out.append(
                finding(
                    rule,
                    c,
                    f"Two first authors are called {people[0].family}: add the initials "
                    f"({people[0].initials} {people[0].family}).",
                    _rendered(
                        c.model_copy(update={"initials": [people[0].initials]}),
                        _names(written, _joiner(c)) + (" et al." if c.et_al else ""),
                    ),
                )
            )
    return _once(out)


QUOTE = re.compile(r"[“\"]([^”\"]{20,800})[”\"]\s*(\([^()]*\))")


@cite_check("cite_quote_page")
def cite_quote_page(rule, cx):
    out = []
    by_position = {c.position: c for c in cx.citations if c.kind == PARENTHETICAL}
    for m in QUOTE.finditer(cx.body.text):
        if len(m.group(1).split()) < 5:
            continue  # a quoted term, not a direct quote
        c = by_position.get(m.start(2))
        if c and not c.locator:
            out.append(
                finding(
                    rule,
                    c,
                    "A direct quote needs the page number: (Author, year, p. 00).",
                    _rendered(
                        c.model_copy(update={"locator": "p. [page]"}),
                        _names(c, "&") + (" et al." if c.et_al else ""),
                    ),
                )
            )
    return _once(out)


@cite_check("cite_no_author")
def cite_no_author(rule, cx):
    out = []
    for c in cx.citations:
        k = cx.key(c)
        if c.title is None or not k:
            continue
        quoted = c.item.lstrip()[:1] in '"“'
        group = rulebook().template(k.ref.type).group if k.ref.type else ""
        if group in {"journal", "web"} and not quoted:
            out.append(
                finding(
                    rule,
                    c,
                    "A work without an author is cited by the first words of its title in "
                    "double quotation marks, with capitals.",
                )
            )
    return _once(out)


@cite_check("cite_secondary")
def cite_secondary(rule, cx):
    out = []
    for c in cx.citations:
        if not c.secondary:
            continue
        phrase = SECONDARY.search(c.item)
        if phrase and phrase.group(0).strip(", ").lower() != "as cited in":
            out.append(
                finding(
                    rule,
                    c,
                    f"Write 'as cited in' (written here as '{phrase.group(0).strip(', ')}').",
                    c.raw.replace(phrase.group(0), ", as cited in ", 1),
                )
            )
        original = parse_authors(
            re.sub(r",?\s*(?:1[5-9]|20)\d\d[a-z]?$", "", SECONDARY.split(c.item)[0].strip(" ,"))
        )
        if original and original.authors:
            key = name_key(original.authors[0])
            listed = [k for k in cx.keys if key in k.first and k.ref.id != c.reference_id]
            if listed:
                out.append(
                    finding(
                        rule,
                        c,
                        f"{original.authors[0]} was read through a secondary source: only "
                        "the secondary source goes in the reference list.",
                    )
                )
    return _once(out)


@cite_check("cite_personal_communication")
def cite_personal_communication(rule, cx):
    out = []
    for c in cx.citations:
        if not c.personal:
            continue
        missing = []
        if not (c.initials and c.initials[0]):
            missing.append("the person's initials")
        if not MONTH_DATE.search(c.item):
            missing.append("the exact date (Month day, year)")
        if missing:
            out.append(
                finding(
                    rule,
                    c,
                    "Personal communication: add "
                    + " and ".join(missing)
                    + ": (I. Tokugawa, personal communication, January 25, 2019).",
                )
            )
    return _once(out)


@cite_check("cite_reprint_years")
def cite_reprint_years(rule, cx):
    out = []
    for c in cx.citations:
        k = cx.key(c)
        if not k or k.ref.type != "book_reprint_translation" or c.original_year:
            continue
        orig = re.search(r"(?:1[5-9]|20)\d\d", k.ref.extra or "")
        out.append(
            finding(
                rule,
                c,
                "A reprint or translation is cited with both years: (Freud, 1900/1953).",
                _rendered(c, _names(c, _joiner(c)), f"{orig.group(0)}/{c.year}") if orig else None,
            )
        )
    return _once(out)


# --------------------------------------------------------------------------- matching


def _outcomes(cx: CiteContext, outcome: str) -> list[Match]:
    return [m for m in cx.matches if m.outcome == outcome]


@cite_check("match_cited_not_listed")
def match_cited_not_listed(rule, cx):
    proper = proper_noun_list()
    out = []
    for m in _outcomes(cx, "not_listed"):
        c = m.citation
        name = c.authors[0] if c.authors else (c.title or "")
        if c.kind != PARENTHETICAL and _fold(name) in proper:
            continue  # "In March (2020)", "Pakistan (2019)": not a citation
        if c.authors:
            name = _names(c, _joiner(c)) + (" et al." if c.et_al else "")
        out.append(
            finding(rule, c, f"'{name} ({_year(c)})' is cited but not in the reference list.")
        )
    return _once(out)


@cite_check("match_year_mismatch")
def match_year_mismatch(rule, cx):
    out = []
    for m in _outcomes(cx, "year"):
        c = m.citation
        years = sorted({f"{k.year}{k.suffix or ''}" for k in m.candidates if k.year})
        listed = " or ".join(years) or "no year"
        fix = None
        if len(m.candidates) == 1 and m.candidates[0].year:
            k = m.candidates[0]
            fix = c.raw.replace(_year(c), f"{k.year}{k.suffix or ''}", 1)
        out.append(
            finding(
                rule,
                c,
                f"Year {_year(c)} in the text, but the reference list has "
                f"{_family(m.candidates[0]) or c.authors[0]} ({listed}).",
                fix,
            )
        )
    return _once(out)


@cite_check("match_spelling_mismatch")
def match_spelling_mismatch(rule, cx):
    out = []
    for m in _outcomes(cx, "spelling"):
        c = m.citation
        k = m.candidates[0]
        family = _family(k)
        out.append(
            finding(
                rule,
                c,
                f"'{c.authors[0]}' in the text, but the reference list has '{family}'.",
                c.raw.replace(c.authors[0], family, 1) if family else None,
            )
        )
    return _once(out)


@cite_check("match_ambiguous")
def match_ambiguous(rule, cx):
    out = []
    for m in _outcomes(cx, "ambiguous"):
        c = m.citation
        out.append(
            finding(
                rule,
                c,
                f"This citation fits {len(m.candidates)} references "
                f"({'; '.join(k.ref.raw[:50] + '…' for k in m.candidates[:3])}). Add year "
                "suffixes (a, b) or further authors to tell them apart.",
            )
        )
    return _once(out)


@cite_check("match_year_suffix")
def match_year_suffix(rule, cx):
    out = []
    for m in _outcomes(cx, "suffix"):
        c, k = m.citation, m.candidates[0]
        listed = f"{k.year}{k.suffix or ''}"
        out.append(
            finding(
                rule,
                c,
                f"The year suffix differs: {_year(c)} in the text, {listed} in the reference list.",
                c.raw.replace(_year(c), listed, 1),
            )
        )
    return _once(out)


@cite_check("match_listed_not_cited")
def match_listed_not_cited(rule, cx):
    cited = {c.reference_id for c in cx.citations if c.reference_id}
    possibly = {k.ref.id for m in cx.matches if m.outcome == "ambiguous" for k in m.candidates}
    out = []
    for k in cx.keys:
        r = k.ref
        if r.id in cited | possibly or not k.first or _mentioned(cx.body.text, k):
            continue
        twin = next(
            (
                o
                for o in cx.keys
                if o.ref.id in cited and o.ref.id != r.id and o.first & k.first and o.year == k.year
            ),
            None,
        )
        message = "This reference is never cited in the text."
        if twin:
            message = (
                "Not cited — it looks like a second copy of the cited entry "
                f"'{twin.ref.raw[:60]}…'."
            )
        out.append(
            Finding(
                level=Level(rule.level),
                rule_id=rule.id,
                message=message,
                location=Location(page=r.page),
                reference_id=r.id,
                original=r.raw,
            )
        )
    return out


def _mentioned(text: str, k: RefKey) -> bool:
    """The surname and year appear together without brackets, e.g. in a table cell
    ("Armougom, 2009"): the reference is used, even if not cited in the usual form."""
    people = k.ref.authors or k.ref.editors
    family = people[0].family if people else None
    if not family or not k.year:
        return False
    pattern = rf"\b{re.escape(family)}\b[^.()]{{0,60}}?\b{re.escape(k.year)}"
    return bool(re.search(pattern, text))


# --------------------------------------------------------------------------- runner


@dataclass
class CitationResult:
    citations: list[Citation]
    findings: list[Finding]


def check_citations(doc: Document, seg: Segmentation, refs: list[Reference]) -> CitationResult:
    """Find the citations, match them to the references, and apply every CIT-/MAT- rule."""
    return check_body(body_text(doc, seg), refs)


def check_body(body: BodyText, refs: list[Reference]) -> CitationResult:
    keys = reference_keys(refs)
    known = set().union(*(k.first for k in keys)) if keys else set()
    citations = extract(body, known)
    matches = match(citations, refs)
    cx = CiteContext(body, citations, refs, keys, matches, {k.ref.id: k for k in keys})
    findings: list[Finding] = []
    for rule in rulebook().rules:
        fn = CITE_CHECKS.get(rule.check)
        if fn:
            findings.extend(fn(rule, cx))
    return CitationResult(citations, findings)
