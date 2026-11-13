"""Rule check implementations (plan phase 6). One function per `check` key in rules.yaml.

Reference checks receive (ref, rule, ctx) and return findings; list checks receive
(refs, rule, ctx). Checks only judge what the parser copied verbatim. `Finding.correction`
holds the corrected element when it is known; whole corrected references are rendered by
checkref.correct.corrector, which fills in the corrections still missing.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from urllib.parse import urlparse

from checkref.correct.journals import full_name, headline_case, headline_words
from checkref.correct.journals import is_acronym as _is_acronym
from checkref.correct.render import PLACEHOLDERS
from checkref.llm import LLMBackend, NullBackend
from checkref.models import Document, Finding, Level, Line, Location, Reference
from checkref.normalize import body_lines
from checkref.parse import AUTHOR, italic_share
from checkref.rules.rulebook import RULEBOOK_DIR, Rule, rulebook

# --------------------------------------------------------------------------- context


@dataclass
class CheckContext:
    doc: Document
    section_lines: list[Line] = field(default_factory=list)
    indents: tuple[float, float] | None = None
    llm: LLMBackend = field(default_factory=NullBackend)
    recency: dict | None = None  # {"share": 0.8, "year": 2025} when the optional check is on
    body_proper_nouns: set[str] = field(default_factory=set)


RefCheck = Callable[[Reference, Rule, CheckContext], list[Finding]]
ListCheck = Callable[[list[Reference], Rule, CheckContext], list[Finding]]
REF_CHECKS: dict[str, RefCheck] = {}
LIST_CHECKS: dict[str, ListCheck] = {}
# In-text citation and matching checks register here from checkref.citations.checks.
CITE_CHECKS: dict[str, Callable] = {}
# Implemented elsewhere: segmentation (headings, merged), classification (style, type).
ELSEWHERE = {
    "list_heading_present",
    "list_heading_accepted",
    "list_merged_entries",
    "list_foreign_style",
    "list_type_unclear",
}


def ref_check(name: str):
    def register(fn: RefCheck) -> RefCheck:
        REF_CHECKS[name] = fn
        return fn

    return register


def list_check(name: str):
    def register(fn: ListCheck) -> ListCheck:
        LIST_CHECKS[name] = fn
        return fn

    return register


def settings() -> dict:
    return rulebook().settings


def location(ref: Reference) -> Location:
    first = ref.lines[0] if ref.lines else None
    return Location(page=ref.page, top=first.top if first else None, x0=first.x0 if first else None)


def finding(
    rule: Rule,
    ref: Reference | None,
    message: str,
    correction: str | None = None,
    original: str | None = None,
    level: Level | None = None,
) -> Finding:
    return Finding(
        level=level or Level(rule.level),
        rule_id=rule.id,
        message=message,
        location=location(ref) if ref else Location(),
        reference_id=ref.id if ref else None,
        original=original if original is not None else (ref.raw if ref else None),
        correction=correction,
    )


def _mask(ref: Reference) -> list[bool]:
    mask: list[bool] = []
    for span in ref.spans:
        mask.extend([span.italic] * len(span.text))
    joined = "".join(s.text for s in ref.spans)
    lead = len(joined) - len(joined.lstrip())
    return mask[lead : lead + len(ref.raw)]


def _fold(word: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", word) if not unicodedata.combining(c)
    ).lower()


# --------------------------------------------------------------------------- authors

ELLIPSIS = re.compile(r"(?:\.\s?){3}|…")
# A name particle written after the initials, e.g. "Oliveira, E. S. de" — acceptable.
# A name written without initials, e.g. "Sajjad-Ur-Rahman": possibly a person known by one name.
MONONYM = re.compile(r"[A-ZÀ-Þ][a-zà-ÿ]+(?:-[A-Za-zÀ-ÿ][a-zà-ÿ]*){1,3}")
PARTICLE_AFTER_INITIALS = re.compile(r"(?:van|von|de|da|do|dos|das|der|den|del|di|du|la|le)\.?,?")


def _author_parts(text: str) -> tuple[list[re.Match], list[str], str]:
    """Author matches, the separators between them, and any text no match covers."""
    matches = list(AUTHOR.finditer(text))
    seps, uncovered, pos = [], [], 0
    for m in matches:
        gap = text[pos : m.start()]
        if pos:
            seps.append(gap)
        elif gap.strip(" ,&"):
            uncovered.append(gap)
        pos = m.end()
    tail = text[pos:].strip()
    if tail and tail not in {".", ","} and not PARTICLE_AFTER_INITIALS.fullmatch(tail):
        uncovered.append(tail)
    # A separator holding a name (e.g. "Mochizuki M, ") is uncovered text too.
    for s in seps:
        core = ELLIPSIS.sub("", s).replace("&", "").replace("and", "").strip(" ,")
        if core and not PARTICLE_AFTER_INITIALS.fullmatch(core):
            uncovered.append(core)
    return matches, seps, " | ".join(u.strip() for u in uncovered if u.strip())


@ref_check("author_name_format")
def author_name_format(ref, rule, ctx):
    if not ref.author_text or ref.corporate_author:
        return []
    matches, _, uncovered = _author_parts(ref.author_text)
    out = []
    if uncovered and all(MONONYM.fullmatch(u.strip(" .")) for u in uncovered.split(" | ")):
        out.append(
            finding(
                rule,
                ref,
                f"'{uncovered}' has no initials. If this is a person known by one name, it "
                "is written as given; otherwise write 'Surname, I. I.'.",
                original=ref.author_text,
                level=Level.NEEDS_REVIEW,
            )
        )
    elif uncovered:
        out.append(
            finding(
                rule,
                ref,
                f"Author names not in the form 'Surname, I. I.': {uncovered}.",
                original=ref.author_text,
            )
        )
    tight = [
        m.group(0).strip(" ,") for m in matches if re.search(r"[A-Z]\.[A-Z]\.", m.group("initials"))
    ]
    if tight:
        out.append(
            finding(
                rule,
                ref,
                "Put a space between initials: " + ", ".join(tight).rstrip(".") + ".",
                original=ref.author_text,
                correction=", ".join(re.sub(r"\.(?=[A-Z])", ". ", t) for t in tight),
            )
        )
    return out


@ref_check("author_ampersand")
def author_ampersand(ref, rule, ctx):
    if not ref.author_text or ref.corporate_author:
        return []
    matches, seps, _ = _author_parts(ref.author_text)
    if len(matches) < 2:
        return []
    last = seps[-1]
    if ELLIPSIS.search(last):
        if "&" in last:
            return [
                finding(
                    rule,
                    ref,
                    "With eight or more authors, APA 6th puts the ellipsis directly "
                    "before the last author, without '&' (… Brown, L.).",
                    original=ref.author_text,
                )
            ]
        return []
    if re.search(r"\band\b", last):
        return [
            finding(
                rule, ref, "Use '&' (not 'and') before the last author.", original=ref.author_text
            )
        ]
    if "&" not in last:
        return [finding(rule, ref, "Use ', &' before the last author.", original=ref.author_text)]
    if not last.lstrip().startswith(","):
        name = matches[-2].group(0).strip(" ,")
        return [
            finding(rule, ref, f"Put a comma before '&': '{name}, & …'.", original=ref.author_text)
        ]
    return []


@ref_check("author_list_complete")
def author_list_complete(ref, rule, ctx):
    if not ref.author_text or ref.corporate_author:
        return []
    matches, seps, _ = _author_parts(ref.author_text)
    if any(ELLIPSIS.search(s) for s in seps) and len(matches) != 7:
        return [
            finding(
                rule,
                ref,
                f"An ellipsis is used but {len(matches)} names are shown. With one to "
                "seven authors list them all; with eight or more give the first six, '…', "
                "and the last author.",
                original=ref.author_text,
            )
        ]
    return []


@ref_check("author_list_truncation")
def author_list_truncation(ref, rule, ctx):
    if not ref.author_text or ref.corporate_author:
        return []
    matches, seps, _ = _author_parts(ref.author_text)
    if len(matches) >= settings()["authors"]["truncate_from"] and not any(
        ELLIPSIS.search(s) for s in seps
    ):
        first6 = ", ".join(m.group(0).strip(" ,") for m in matches[:6])
        last = matches[-1].group(0).strip(" ,")
        return [
            finding(
                rule,
                ref,
                f"{len(matches)} authors are listed. With eight or more, give the "
                "first six, an ellipsis, then the last author.",
                original=ref.author_text,
                correction=f"{first6}, … {last}",
            )
        ]
    return []


@ref_check("editors_format")
def editors_format(ref, rule, ctx):
    if not ref.editors or not ref.editor_role:
        return []
    out = []
    bad = [e.raw for e in ref.editors if not re.match(r"^(?:[A-Z]\.\s?)+\S", e.raw)]
    if bad:
        out.append(
            finding(
                rule,
                ref,
                "Editors in the 'In …' part take their initials first "
                f"(K. Dew & A. Matheson): {', '.join(bad)}.",
            )
        )
    expected = "Ed." if len(ref.editors) == 1 else "Eds."
    if ref.editor_role != expected:
        out.append(
            finding(
                rule,
                ref,
                f"Use ({expected}) for {len(ref.editors)} editor(s).",
                correction=f"({expected})",
            )
        )
    return out


@ref_check("editors_inverted_format")
def editors_inverted_format(ref, rule, ctx):
    if not ref.editor_role or not ref.editors:
        return []
    expected = "Ed." if len(ref.editors) == 1 else "Eds."
    if ref.editor_role != expected:
        return [
            finding(
                rule,
                ref,
                f"Use ({expected}) for {len(ref.editors)} editor(s).",
                correction=f"({expected})",
            )
        ]
    return []


# --------------------------------------------------------------------------- dates


@ref_check("date_format")
def date_format(ref, rule, ctx):
    span = ref.offsets.get("date")
    if not span:
        return []
    start, end = span
    out = []
    before = ref.raw[:start].rstrip()
    if before and not before.endswith("."):
        out.append(
            finding(
                rule,
                ref,
                f"End the author element with a full stop before the date: '{before[-25:]}.'",
                original=before[-40:],
            )
        )
    if not ref.raw[start:end].endswith("."):
        out.append(
            finding(
                rule, ref, "Put a full stop after the date: '(2008).'", original=ref.raw[start:end]
            )
        )
    return out


@ref_check("date_nd_in_press")
def date_nd_in_press(ref, rule, ctx):
    m = re.search(r"\((?:n\.d|nd|n\. d\.|no date|In press|in-press|In Press)\)", ref.raw[:300])
    if m:
        right = "(in press)" if "press" in m.group(0).lower() else "(n.d.)"
        return [finding(rule, ref, f"Write {right}.", original=m.group(0), correction=right)]
    return []


@ref_check("date_exact")
def date_exact(ref, rule, ctx):
    if ref.year and ref.year[:1].isdigit() and not ref.date_detail:
        return [finding(rule, ref, "Give the exact date of publication: (Year, Month day).")]
    return []


# --------------------------------------------------------------------------- titles

SENTENCE_BREAK = re.compile(r"[:?!]\s*$|\.\s*$")
# Names of taxa above genus are always capitalised: Enterobacteriaceae, Lepidoptera, Bombycidae.
# "Aeromonas hydrophila", "Azadirachta indica": a capitalised genus and a lower-case epithet.
BINOMIAL = re.compile(
    r"^[A-Z][a-z]{3,}\s+(?:\(\w+\)\s+)?"
    r"(?!(?:bacteria|data|media|area|criteria|formula|malaria|larvae?|flora|fauna|idea|era|"
    r"plasma|sera|saliva|extra|via|versus|silica|alumina|stimulus|status|virus|focus|bonus|"
    r"genus|nexus|corpus|basis|analysis|synthesis|crisis|axis|thesis|genesis|series|species)\b)"
    r"[a-z]{3,}(?:a|us|um|is|i|ae|es|ii|ensis|ica|ata|ris|ens|ium|ilis|alis|oides|ella)\b"
)
TAXON = re.compile(r"(?:aceae|ales|idae|inae|oidea|ineae|optera|phyta|mycota|phyceae|ota)$")


@cache
def _proper_entries() -> tuple[frozenset[str], frozenset[str]]:
    path = RULEBOOK_DIR / "proper_nouns.txt"
    entries = [_fold(w.strip()) for w in path.read_text(encoding="utf-8").splitlines()]
    entries = [e for e in entries if e and not e.startswith("#")]
    return frozenset(e for e in entries if " " not in e), frozenset(e for e in entries if " " in e)


def proper_noun_list() -> frozenset[str]:
    return _proper_entries()[0]


def _in_proper_phrase(words: list[str], n: int) -> bool:
    """Is words[n] part of a listed multi-word name such as 'United States'?"""
    phrases = _proper_entries()[1]
    for size in (2, 3, 4):
        for start in range(n - size + 1, n + 1):
            if start >= 0 and start + size <= len(words):
                if _fold(" ".join(words[start : start + size])) in phrases:
                    return True
    return False


def learn_body_proper_nouns(doc: Document) -> set[str]:
    """Words capitalised mid-sentence in prose lines of the thesis body (spec §5 ⑧ step 4),
    and never written in lower case there: "Mulberry" in one sentence and "mulberry" in
    another is a habit of the writer, not a proper noun."""
    capital: set[str] = set()
    lower: set[str] = set()
    for line in body_lines(doc):
        words = re.findall(r"[A-Za-zÀ-ɏ][\w'’-]*", line.text)
        if len(words) < 6 or sum(w[0].islower() for w in words) < 0.6 * len(words):
            continue  # headings and title-case lines say nothing about proper nouns
        tokens = line.text.split()
        for prev, tok in zip(tokens, tokens[1:], strict=False):
            word = tok.strip("()[],;:.\"'“”")
            if word[:1].islower():
                lower.add(_fold(word))
            elif word[:1].isupper() and word[1:].islower() and not re.search(r"[.!?:]$", prev):
                capital.add(_fold(word))
    return capital - lower


def _title_words(title: str, start: int, mask: list[bool]):
    """(word, absolute offset, italic, sentence_start) for each word of a title."""
    out, sentence_start = [], True
    for m in re.finditer(r"\S+", title):
        word = m.group(0)
        core = word.strip("()[]\"'“”‘’,;.:?!")
        offset = start + m.start() + word.find(core) if core else start + m.start()
        italic = (
            italic_share(mask, offset, offset + len(core), " " * offset + core) > 0.5
            if core
            else False
        )
        out.append((core, offset, italic, sentence_start))
        sentence_start = bool(re.search(r"[:?!]$|(?<![A-Z])\.$", word))
    return out


def _suspects(
    ref: Reference, ctx: CheckContext, title: str, start: int
) -> tuple[list[str], int, list[str]]:
    """Capitalised words that sentence case would lower-case, before and after resolution."""
    mask = _mask(ref)
    raw_suspects, unresolved, content = [], [], 0
    proper = proper_noun_list() | ctx.body_proper_nouns
    words = _title_words(title, start, mask)
    cores = [w[0] for w in words]
    for n, (core, _, italic, sentence_start) in enumerate(words):
        following = words[n + 1][0] if n + 1 < len(words) else ""
        if BINOMIAL.match(f"{core} {following}") or _in_proper_phrase(cores, n):
            continue  # a species' genus or part of a multi-word name: always capitalised
        parts = core.split("-")
        for i, part in enumerate(parts):
            if not part or not part[0].isalpha():
                continue
            first_of_sentence = sentence_start and i == 0
            if not first_of_sentence and len(part) > 3:
                content += 1
            if first_of_sentence or not part[0].isupper() or _is_acronym(part) or italic:
                continue
            raw_suspects.append(part)
            if _fold(part) not in proper and not TAXON.search(part):
                unresolved.append(part)
    return raw_suspects, content, unresolved


@ref_check("title_sentence_case")
def title_sentence_case(ref, rule, ctx):
    if not ref.title or "title" not in ref.offsets:
        return []
    if _all_caps(ref.title):
        return []  # reported by REF-TITLE-03
    start = ref.offsets["title"][0]
    title = re.sub(r"\s*\[[^\]]*\]", "", ref.title)  # "[Special issue]" etc. are not the title
    out = []
    lower_after_colon = [m.group(1) for m in re.finditer(r":\s+([a-z]\w*)", title)]
    if lower_after_colon and not re.match(r"^[a-z]", title):
        out.append(
            finding(
                rule,
                ref,
                "Capitalise the first word after the colon (subtitle): "
                + ", ".join(f"'{w}'" for w in lower_after_colon)
                + ".",
                original=ref.title,
                correction=re.sub(
                    r"(:\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), ref.title
                ),
            )
        )
    suspects, content, unresolved = _suspects(ref, ctx, title, start)
    if len(suspects) >= 3 and len(suspects) >= 0.5 * max(content, 1):
        out.append(
            finding(
                rule,
                ref,
                "The title is in title case. Use sentence case: capitalise only the "
                "first word, the first word after a colon, and proper nouns.",
                original=ref.title,
                correction=_sentence_case(ref.title, unresolved),
            )
        )
        return out
    still = [w for w in unresolved if ctx.llm.is_proper_noun(w, ref.title) is not True]
    definitely_not = [w for w in still if ctx.llm.is_proper_noun(w, ref.title) is False]
    if definitely_not:
        out.append(
            finding(
                rule,
                ref,
                "Use sentence case: lower-case "
                + ", ".join(f"'{w}'" for w in definitely_not)
                + ".",
                original=ref.title,
                correction=_sentence_case(ref.title, definitely_not),
            )
        )
    unsure = [w for w in still if w not in definitely_not]
    if unsure:
        out.append(
            finding(
                rule,
                ref,
                "Check the capital letters in the title (sentence case keeps capitals "
                "only for proper nouns): " + ", ".join(f"'{w}'" for w in unsure) + ".",
                original=ref.title,
                level=Level.NEEDS_REVIEW,
            )
        )
    return out


def _sentence_case(title: str, lower: list[str]) -> str:
    targets = set(lower)
    return re.sub(
        r"[A-Za-zÀ-ɏ]+",
        lambda m: m.group(0).lower() if m.group(0) in targets else m.group(0),
        title,
    )


def _all_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 12 and sum(c.isupper() for c in letters) / len(letters) > 0.8


@ref_check("title_not_all_caps")
def title_not_all_caps(ref, rule, ctx):
    if ref.title and _all_caps(ref.title):
        fixed = ctx.llm.to_sentence_case(ref.title)
        if fixed and fixed.lower() != ref.title.lower():
            fixed = None  # the model changed more than letter case: discard (spec §5 ⑧)
        return [
            finding(
                rule,
                ref,
                "The title is written in capitals. Use sentence case.",
                original=ref.title,
                correction=fixed,
            )
        ]
    return []


@ref_check("journal_headline_case")
def journal_headline_case(ref, rule, ctx):
    name = ref.container
    if not name or _all_caps(name) and len(name.split()) > 3:
        return (
            []
            if not name
            else [
                finding(
                    rule,
                    ref,
                    "Write the journal name in headline style, not in capitals.",
                    original=name,
                )
            ]
        )
    wrong = headline_words(name)
    if not wrong:
        return []
    fixed = headline_case(name)
    return [
        finding(
            rule,
            ref,
            "Journal names use headline style (capitalise all major words; articles, "
            "prepositions and conjunctions lower-case): "
            + ", ".join(f"'{b}' → '{g}'" for b, g in wrong)
            + ".",
            original=name,
            correction=fixed,
        )
    ]


# --------------------------------------------------------------------------- journals


@ref_check("journal_not_abbreviated")
def journal_not_abbreviated(ref, rule, ctx):
    if not ref.container:
        return []
    cfg = settings()["journal_abbreviations"]
    abbrev = {w.lower().rstrip(".") for w in cfg["words"]}
    common = {w.lower() for w in cfg["also_words"]}
    words = re.findall(r"[A-Za-z]+\.?", ref.container)
    hits = [w for w in words if w.lower().rstrip(".") in abbrev]
    strong = [w for w in hits if w.lower().rstrip(".") not in common or w.endswith(".")]
    expanded = full_name(ref.container)
    if len(strong) >= 2 or (strong and len(hits) >= 2) or (expanded and hits):
        found = f" Full name in the NLM journal list: {expanded}." if expanded else ""
        return [
            finding(
                rule,
                ref,
                f"The journal name '{ref.container}' is abbreviated. Write it in full.{found}",
                original=ref.container,
                correction=expanded or PLACEHOLDERS["full_journal"],
            )
        ]
    if len(strong) == 1 and len(words) <= 3:
        return [
            finding(
                rule,
                ref,
                f"The journal name '{ref.container}' may be abbreviated "
                f"('{strong[0]}'). Check that it is written in full.",
                original=ref.container,
                level=Level.NEEDS_REVIEW,
            )
        ]
    return []


@ref_check("journal_volume_present")
def journal_volume_present(ref, rule, ctx):
    if ref.type in {"journal_article", "journal_article_no_doi_online", "journal_special_issue"}:
        missing = [n for n, v in (("journal name", ref.container), ("volume", ref.volume)) if not v]
        if missing:
            return [
                finding(
                    rule,
                    ref,
                    "The journal " + " and ".join(missing) + " is missing.",
                    correction="[" + " and ".join(missing) + " missing]",
                )
            ]
    return []


@ref_check("journal_issue_format")
def journal_issue_format(ref, rule, ctx):
    if ref.volume and ref.issue and re.search(rf"{re.escape(ref.volume)}\s+\(", ref.raw):
        return [
            finding(
                rule,
                ref,
                f"No space between the volume and the issue: {ref.volume}({ref.issue}).",
                correction=f"{ref.volume}({ref.issue})",
            )
        ]
    return []


@ref_check("journal_pages_format")
def journal_pages_format(ref, rule, ctx):
    loc = ref.pages or ref.article_number
    newspaper = ref.type in {"newspaper_article", "newspaper_article_no_author"}
    if ref.type in {"journal_article", "journal_article_no_doi_online"} and not loc:
        return [
            finding(
                rule,
                ref,
                "The page range (or article number) is missing.",
                correction="[page range missing]",
            )
        ]
    if loc and not newspaper and re.match(r"pp?\.", loc):
        return [
            finding(
                rule,
                ref,
                "Journal and magazine page numbers are given without 'p.' or 'pp.'.",
                original=loc,
                correction=re.sub(r"^pp?\.\s*", "", loc),
            )
        ]
    if loc and newspaper and not re.match(r"pp?\.", loc):
        prefix = "pp." if re.search(r"[-–]", loc) else "p."
        return [
            finding(
                rule,
                ref,
                f"Newspaper page numbers take '{prefix}'.",
                original=loc,
                correction=f"{prefix} {loc}",
            )
        ]
    return []


# --------------------------------------------------------------------------- books etc.


@ref_check("edition_format")
def edition_format(ref, rule, ctx):
    if ref.edition and ref.italics.get("edition", 0) > 0.5:
        return [finding(rule, ref, "The edition is not italic: (3rd ed.).", original=ref.edition)]
    m = re.search(r"\((\d+)(?:st|nd|rd|th)? [Ee]dition\)|\((\d+)(?:st|nd|rd|th)? Ed\.?\)", ref.raw)
    if m:
        return [finding(rule, ref, "Write the edition as '(3rd ed.)'.", original=m.group(0))]
    return []


@ref_check("chapter_pages")
def chapter_pages(ref, rule, ctx):
    if not ref.pages:
        return [
            finding(
                rule,
                ref,
                "Give the chapter's page range after the book title: (pp. 97–106).",
                correction="(pp. [page range])",
            )
        ]
    return []


@ref_check("original_work_published")
def original_work_published(ref, rule, ctx):
    if "Original work published" not in ref.raw:
        return [finding(rule, ref, "Add '(Original work published year)' at the end.")]
    return []


@ref_check("report_number_format")
def report_number_format(ref, rule, ctx):
    m = re.search(r"[.,]\s*(Report No\.?\s*[\w.-]+)", ref.raw)
    if m and not ref.report_number:
        return [
            finding(
                rule,
                ref,
                "Put the report number in brackets straight after the title.",
                original=m.group(1),
                correction=f"({m.group(1)})",
            )
        ]
    return []


@ref_check("thesis_details")
def thesis_details(ref, rule, ctx):
    out = []
    if not ref.degree:
        out.append(
            finding(
                rule,
                ref,
                "Give the type of thesis in brackets after the title "
                "(e.g. Master's thesis, Doctoral dissertation).",
            )
        )
    if ref.type == "thesis_unpublished" and ref.publisher and "," not in ref.publisher:
        out.append(finding(rule, ref, "Give the university's full name and its location."))
    return out


@ref_check("conference_details")
def conference_details(ref, rule, ctx):
    if ref.type != "symposium_contribution" and not ref.date_detail:
        return [finding(rule, ref, "Give the year and month of the meeting: (2008, January).")]
    return []


@ref_check("software_format")
def software_format(ref, rule, ctx):
    if not ref.description:
        return [
            finding(
                rule,
                ref,
                "Add the type of software in square brackets after the title: [Computer software].",
                correction="[Computer software]",
            )
        ]
    return []


# --------------------------------------------------------------------------- publisher


@ref_check("publisher_location_present")
def publisher_location_present(ref, rule, ctx):
    if ref.publisher and not ref.publisher_location and ref.type not in {"thesis_unpublished"}:
        return [
            finding(
                rule,
                ref,
                f"The publisher '{ref.publisher}' needs its location: City, Country: "
                "Publisher (USA: City, ST: Publisher).",
                correction=f"[City, Country]: {ref.publisher}",
            )
        ]
    return []


@ref_check("publisher_location_format")
def publisher_location_format(ref, rule, ctx):
    loc = ref.publisher_location
    if not loc:
        return []
    parts = [p.strip() for p in loc.split(",")]
    states = set(settings()["publisher_location"]["us_states"])
    if len(parts) < 2:
        return [
            finding(
                rule,
                ref,
                f"Give the city and the country (or US state): '{loc}, Country'.",
                original=loc,
            )
        ]
    region = parts[-1]
    if region in {"UK", "U.K.", "USA", "U.S.A.", "US", "UAE"}:
        return [
            finding(
                rule,
                ref,
                "Outside the USA give the country in full; in the USA give the state "
                f"abbreviation (e.g. New York, NY): '{loc}'.",
                original=loc,
            )
        ]
    if len(region) == 2 and region.isupper() and region not in states:
        return [
            finding(
                rule,
                ref,
                f"'{region}' is not a US state abbreviation. Give the country in full.",
                original=loc,
            )
        ]
    return []


@ref_check("author_as_publisher")
def author_as_publisher(ref, rule, ctx):
    if (
        ref.corporate_author
        and ref.publisher
        and _fold(ref.publisher) == _fold(ref.corporate_author)
    ):
        return [
            finding(
                rule,
                ref,
                "When the author is also the publisher, write 'Author' as the publisher.",
                original=ref.publisher,
                correction="Author",
            )
        ]
    return []


@ref_check("description_brackets")
def description_brackets(ref, rule, ctx):
    expected = {
        "online_video": "[Video file]",
        "online_video_series": "[Video file]",
        "blog_post": "[Blog post]",
        "film": "[Motion picture]",
        "tv_series": "[Television series]",
        "tv_episode": "[Television series episode]",
        "course_material": "[Course notes]",
        "software": "[Computer software]",
        "software_no_author": "[Computer software]",
    }
    if ref.type in expected and not ref.description and "[" not in ref.raw:
        return [
            finding(
                rule,
                ref,
                f"Add the format in square brackets after the title, e.g. {expected[ref.type]}.",
                correction=expected[ref.type],
            )
        ]
    return []


# --------------------------------------------------------------------------- DOI / URL

DOI_CORE = re.compile(r"10\.\d{4,9}/\S+")


def _doi_core(doi: str) -> str | None:
    m = DOI_CORE.search(doi.split("doi.org/")[-1])
    return m.group(0).rstrip(".") if m else None


@ref_check("doi_format")
def doi_format(ref, rule, ctx):
    if (
        not ref.doi
        or re.fullmatch(settings()["doi"]["pattern"], ref.doi)
        or ref.doi.count("doi.org") > 1
    ):
        return []
    core = _doi_core(ref.doi)
    return [
        finding(
            rule,
            ref,
            "Remove the library proxy (ezproxy) and write the DOI as https://doi.org/10.xxxx."
            if "ezproxy" in ref.doi.lower()
            else "Write the DOI as https://doi.org/10.xxxx.",
            original=ref.doi,
            correction=f"https://doi.org/{core}" if core else None,
        )
    ]


@ref_check("doi_no_full_stop")
def doi_no_full_stop(ref, rule, ctx):
    if ref.doi and re.search(re.escape(ref.doi) + r"\.\s*$", ref.raw):
        return [
            finding(
                rule, ref, "No full stop after the DOI.", original=ref.doi + ".", correction=ref.doi
            )
        ]
    return []


@ref_check("doi_single")
def doi_single(ref, rule, ctx):
    if ref.raw.count("doi.org/") > 1 or re.search(r"doi\.org/\s*doi:", ref.raw, re.I):
        core = _doi_core(ref.doi or ref.raw)
        return [
            finding(
                rule,
                ref,
                "The DOI prefix is repeated. Write the DOI once.",
                correction=f"https://doi.org/{core}" if core else None,
            )
        ]
    return []


@ref_check("doi_not_with_url")
def doi_not_with_url(ref, rule, ctx):
    if ref.doi and (ref.retrieval_statement or ref.url):
        return [finding(rule, ref, "Give the DOI only; drop the 'Retrieved from' URL.")]
    return []


def _homepage(url: str) -> bool:
    p = urlparse(url if "://" in url else f"http://{url}")
    depth = len([s for s in p.path.split("/") if s])
    return depth <= 1 and not p.query and not re.search(r"\d{4,}|\.(pdf|html?|aspx?)$", p.path)


@ref_check("url_homepage_only")
def url_homepage_only(ref, rule, ctx):
    if ref.url and not _homepage(ref.url):
        host = urlparse(ref.url).netloc
        return [
            finding(
                rule,
                ref,
                "Without a DOI, give the journal's homepage URL, not the article "
                f"URL or a database link ({host}).",
                original=ref.url,
                correction="Retrieved from [journal homepage URL]",
            )
        ]
    return []


@ref_check("url_database_homepage")
def url_database_homepage(ref, rule, ctx):
    if ref.url and not _homepage(ref.url):
        p = urlparse(ref.url)
        return [
            finding(
                rule,
                ref,
                "Give only the database's homepage URL.",
                original=ref.url,
                correction=f"{p.scheme}://{p.netloc}",
            )
        ]
    return []


RETRIEVAL_DATE_ALLOWED = {
    "webpage",
    "webpage_no_author",
    "dictionary_entry_online",
    "ebook_chapter",
    "report_online",
}


@ref_check("retrieval_date_usage")
def retrieval_date_usage(ref, rule, ctx):
    if ref.retrieval_date and ref.type not in RETRIEVAL_DATE_ALLOWED:
        return [
            finding(
                rule,
                ref,
                "Do not give a retrieval date for this kind of source "
                "(only for web pages that may change).",
                original=ref.retrieval_date,
                correction="Retrieved from",
            )
        ]
    return []


@ref_check("retrieval_date_recommended")
def retrieval_date_recommended(ref, rule, ctx):
    if ref.url and not ref.retrieval_date:
        return [
            finding(
                rule,
                ref,
                "Web pages that may change usually include the retrieval date: "
                "Retrieved Month day, year, from URL.",
            )
        ]
    return []


@ref_check("retrieval_statement_format")
def retrieval_statement_format(ref, rule, ctx):
    m = re.search(
        r"\b(Accessed(?: on)?|Retrieved on|Available at|Available online(?: at)?"
        r"|Online available)\b",
        ref.raw,
    )
    if m:
        return [
            finding(
                rule,
                ref,
                "Write 'Retrieved from URL' (or 'Retrieved Month day, year, from URL').",
                original=m.group(0),
                correction="Retrieved from",
            )
        ]
    return []


@ref_check("url_no_full_stop")
def url_no_full_stop(ref, rule, ctx):
    if (
        ref.url
        and re.search(re.escape(ref.url.rstrip(".")) + r"\.\s*$", ref.raw)
        and ref.url.endswith(".")
    ):
        return [
            finding(
                rule,
                ref,
                "No full stop after the URL.",
                original=ref.url,
                correction=ref.url.rstrip("."),
            )
        ]
    return []


# --------------------------------------------------------------------------- typography

PAGE_RANGE = re.compile(r"(?P<a>[A-Za-z]{0,4}\d+)(?P<dash>\s*[-–—‒―]\s*)(?P<b>[A-Za-z]{0,4}\d+)")


def _ranges(ref: Reference):
    for value in (ref.pages,):
        if value:
            yield from PAGE_RANGE.finditer(value)


@ref_check("page_range_dash")
def page_range_dash(ref, rule, ctx):
    accepted = settings()["dashes"]["page_range_accepted"]
    for m in _ranges(ref):
        if m.group("dash").strip() not in accepted:
            return [
                finding(
                    rule,
                    ref,
                    "Use an en dash (or a hyphen) in page ranges, not "
                    f"'{m.group('dash').strip()}'.",
                    original=m.group(0),
                    correction=f"{m.group('a')}–{m.group('b')}",
                )
            ]
    return []


@ref_check("page_range_spacing")
def page_range_spacing(ref, rule, ctx):
    for m in _ranges(ref):
        if m.group("dash") != m.group("dash").strip():
            return [
                finding(
                    rule,
                    ref,
                    "No spaces around the dash in a page range.",
                    original=m.group(0),
                    correction=f"{m.group('a')}–{m.group('b')}",
                )
            ]
    return []


def _italic_problem(ref, rule, key, want_italic, label):
    if key not in ref.italics or not getattr(ref, key, None):
        return []
    share = ref.italics[key]
    if want_italic and share < 0.8:
        return [finding(rule, ref, f"{label} should be italic.", original=getattr(ref, key))]
    if not want_italic and share > 0.5 and not species_only(italic_runs(ref, key)):
        return [finding(rule, ref, f"{label} should not be italic.", original=getattr(ref, key))]
    return []


def italic_runs(ref: Reference, key: str) -> list[str]:
    """The italic stretches of text inside one element."""
    if key not in ref.offsets:
        return []
    start, end = ref.offsets[key]
    mask, runs, current = _mask(ref), [], ""
    for i in range(start, end):
        if i < len(mask) and mask[i]:
            current += ref.raw[i]
        elif current.strip():
            runs.append(current.strip())
            current = ""
        else:
            current = ""
    if current.strip():
        runs.append(current.strip())
    return runs


SPECIES = re.compile(r"[A-Z][a-z]+\.?(?: \(?[a-z]+\)?)?(?: (?:sp|spp|var|subsp)\.)?")


def species_only(runs: list[str]) -> bool:
    """True when every italic stretch is a genus or species name, which keeps its italics
    inside a roman title: "Pathogenic *Escherichia coli*", "*Bombyx mori* L."."""
    return bool(runs) and all(SPECIES.fullmatch(r.strip(" .,;:()")) for r in runs)


@ref_check("italics_periodical")
def italics_periodical(ref, rule, ctx):
    out = []
    out += _italic_problem(ref, rule, "container", True, "The journal name")
    out += _italic_problem(ref, rule, "volume", True, "The volume number")
    out += _italic_problem(ref, rule, "issue", False, "The issue number")
    out += _italic_problem(ref, rule, "pages", False, "The page range")
    out += _italic_problem(ref, rule, "title", False, "The article title")
    return out


@ref_check("italics_title")
def italics_title(ref, rule, ctx):
    return _italic_problem(ref, rule, "title", True, "The title")


@ref_check("italics_chapter")
def italics_chapter(ref, rule, ctx):
    return _italic_problem(
        ref, rule, "title", False, "The chapter or entry title"
    ) + _italic_problem(ref, rule, "container", True, "The book or work title")


@ref_check("italics_not_expected")
def italics_not_expected(ref, rule, ctx):
    return _italic_problem(ref, rule, "title", False, "This title")


MISSING_SPACE = re.compile(r"(?<![A-Z.])(?:[a-z]{2,}|\d|\))[.,;:](?=[A-Z][a-z]{2,})")


@ref_check("missing_space")
def missing_space(ref, rule, ctx):
    text = re.sub(r"https?://\S+|doi:\S+|10\.\d{4,9}/\S+", " ", ref.raw)
    m = MISSING_SPACE.search(text)
    if m and not ref.merged_part:
        snippet = text[max(0, m.start() - 10) : m.end() + 10]
        return [
            finding(
                rule,
                ref,
                f"A space is missing after '{m.group(0)}': '…{snippet}…'.",
                original=snippet,
            )
        ]
    return []


@ref_check("template_structure")
def template_structure(ref, rule, ctx):
    return []  # compares the reference with its rendered template: checkref.correct.corrector


# --------------------------------------------------------------------------- list checks


def _sort_key(ref: Reference) -> str:
    if ref.authors:
        first = ref.authors[0]
        key = f"{first.family} {first.initials}"
    else:
        key = ref.corporate_author or ref.title or ref.raw
        key = re.sub(r"^(?:the|a|an)\s+", "", key, flags=re.I)
    return re.sub(r"[^a-z ]", "", _fold(key))


@list_check("list_alphabetical")
def list_alphabetical(refs, rule, ctx):
    out = []
    refs = [r for r in refs if r.type]  # skip fragments of merged entries and foreign styles
    for prev, ref in zip(refs, refs[1:], strict=False):
        a, b = _sort_key(prev).split(" ")[0], _sort_key(ref).split(" ")[0]
        if b < a:
            out.append(
                finding(
                    rule,
                    ref,
                    f"Out of alphabetical order: '{ref.raw[:40]}…' comes after '{prev.raw[:40]}…'.",
                )
            )
    return out


def _author_keys(ref: Reference) -> list[str]:
    """Surname plus initials: 'Li, Q.' and 'Li, S.' are different people."""
    people = [_fold(f"{a.family} {re.sub(r'[^A-Za-z]', '', a.initials)}") for a in ref.authors]
    return people or [_fold(ref.corporate_author or "")]


@list_check("list_same_author_order")
def list_same_author_order(refs, rule, ctx):
    out = []
    for prev, ref in zip(refs, refs[1:], strict=False):
        pa, ra = _author_keys(prev), _author_keys(ref)
        if not pa[0] or pa[0] != ra[0]:
            continue
        if pa == ra and (prev.year or "") > (ref.year or "") and (ref.year or "")[:1].isdigit():
            out.append(
                finding(
                    rule,
                    ref,
                    f"Works by the same author(s) go in year order, earliest first: "
                    f"{ref.year} should come before {prev.year}.",
                )
            )
        elif len(pa) > 1 and len(ra) == 1:
            out.append(
                finding(
                    rule,
                    ref,
                    "A one-author work comes before works by the same first author "
                    "with co-authors.",
                )
            )
        elif len(pa) > 1 and len(ra) > 1 and pa != ra and pa[1:] > ra[1:]:
            out.append(
                finding(
                    rule, ref, "With the same first author, order by the second author's surname."
                )
            )
    return out


@list_check("list_year_suffix")
def list_year_suffix(refs, rule, ctx):
    seen: dict[tuple, Reference] = {}
    out = []
    for ref in refs:
        if not ref.year or not ref.authors:
            continue
        key = (tuple(_author_keys(ref)), ref.year)
        if key in seen and not (ref.year_suffix and seen[key].year_suffix):
            out.append(
                finding(
                    rule,
                    ref,
                    f"Same author(s) and year as another reference: add 'a' and 'b' "
                    f"after the year ({ref.year}a, {ref.year}b), in the list and in the text.",
                )
            )
        seen[key] = ref
    return out


@list_check("list_duplicates")
def list_duplicates(refs, rule, ctx):
    seen: dict[str, Reference] = {}
    out = []
    for ref in refs:
        key = re.sub(r"[^a-z0-9]", "", _fold(ref.raw))
        if key in seen:
            out.append(finding(rule, ref, "This reference appears twice in the list."))
        seen[key] = ref
    return out


@list_check("list_in_text_only_types")
def list_in_text_only_types(refs, rule, ctx):
    return [
        finding(
            rule,
            r,
            "Personal communications are cited in the text only, not in the reference list.",
        )
        for r in refs
        if re.search(r"personal communication", r.raw, re.I)
    ]


@list_check("layout_hanging_indent")
def layout_hanging_indent(refs, rule, ctx):
    lo, hi = (settings()["layout"]["hanging_indent_inch"][k] * 72 for k in ("min", "max"))
    if ctx.doc.kind == "pdf":
        if ctx.indents is None:
            return [
                finding(
                    rule,
                    None,
                    "The references have no hanging indent: indent the second and "
                    "following lines of each reference by 0.5 inch.",
                )
            ]
        hang = ctx.indents[1] - ctx.indents[0]
        if not lo <= hang <= hi:
            return [
                finding(
                    rule, None, f"The hanging indent is {hang / 72:.2f} inch; use about 0.5 inch."
                )
            ]
        return []
    wrong = [r for r in refs if r.lines and not (lo <= -(r.lines[0].first_line_indent or 0) <= hi)]
    if wrong and len(wrong) >= 0.5 * len(refs):
        return [finding(rule, None, "The references have no 0.5-inch hanging indent.")]
    return [finding(rule, r, "This reference has no 0.5-inch hanging indent.") for r in wrong]


@list_check("recency_share")
def recency_share(refs, rule, ctx):
    if not ctx.recency:
        return []
    year, share = ctx.recency["year"], ctx.recency["share"]
    window = settings()["recency"]["window_years"]
    dated = [r for r in refs if r.year and r.year[:4].isdigit()]
    recent = [r for r in dated if int(r.year[:4]) > year - window]
    actual = len(recent) / len(dated) if dated else 0.0
    if actual < share:
        return [
            finding(
                rule,
                None,
                f"{actual:.0%} of references are from {year - window + 1}–{year}; "
                f"the required share is {share:.0%}.",
            )
        ]
    return []


# --------------------------------------------------------------------------- runner


def implemented(check: str) -> bool:
    return check in REF_CHECKS or check in LIST_CHECKS or check in CITE_CHECKS or check in ELSEWHERE


def run_checks(refs: list[Reference], ctx: CheckContext) -> list[Finding]:
    """Apply every rule with an implementation to the parsed references and to the list."""
    rb = rulebook()
    if not ctx.body_proper_nouns:
        ctx.body_proper_nouns = learn_body_proper_nouns(ctx.doc)
    findings: list[Finding] = []
    for ref in refs:
        if not ref.type:
            continue
        for rule in rb.rules_for(ref.type):
            fn = REF_CHECKS.get(rule.check)
            if fn:
                findings.extend(fn(ref, rule, ctx))
    for rule in rb.rules:
        fn = LIST_CHECKS.get(rule.check)
        if fn and ("list" in rule.applies_to) and rule.check not in CITE_CHECKS:
            findings.extend(fn(refs, rule, ctx))
    return findings
