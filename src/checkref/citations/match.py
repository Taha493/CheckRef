"""Match in-text citations to reference-list entries (spec §5 ⑩).

Names are compared after normalisation: accents removed, lower case, apostrophes and
hyphens ignored, leading particles (van, de, El-, Al-) dropped. A citation matches on first
surname + year (+ a/b suffix); further authors decide between candidates. The graded
results (year mismatch, spelling mismatch, not listed, ambiguous, suffix) become MAT-
findings in checkref.citations.checks.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from checkref.models import Citation, Reference
from checkref.parse import parse_authors

PARTICLES = r"(?:van|von|de|der|den|da|del|della|di|du|la|le|el|al|bin|ibn|abu)"


def name_key(name: str) -> str:
    """'El-Ghareeb' -> 'ghareeb', 'D’Cruze' -> 'dcruze', 'van Roy' -> 'roy', 'Ö. Can' -> 'can'."""
    text = re.sub(r"\s*\[[^\]]*\]", "", name)
    text = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    ).lower()
    text = re.sub(rf"^(?:{PARTICLES}[\s-]+)+(?=\w{{3}})", "", text.strip())
    return re.sub(r"[^a-z0-9]", "", text)


def acronym(corporate: str) -> str:
    """'World Health Organization' -> 'who'."""
    words = [w for w in re.findall(r"[A-Za-z][\w-]*", corporate) if w[0].isupper()]
    return "".join(w[0] for w in words).lower()


@dataclass
class RefKey:
    ref: Reference
    first: set[str]  # keys that identify the first author (surname, corporate name, acronym)
    others: list[str]  # keys of the further authors
    year: str | None
    suffix: str | None
    authors: int  # number of authors (8 when the list is truncated with an ellipsis)
    initials: str = ""
    parts: set[str] = field(default_factory=set)  # parts of a double surname
    name: str = ""  # the first author's surname (or corporate name) as written


def reference_keys(refs: list[Reference]) -> list[RefKey]:
    keys = []
    for r in refs:
        year = r.year
        if not year:  # unparsed: the first year in the entry, with or without brackets
            y = re.search(r"\b(?:1[5-9]|20)\d\d\b", r.raw)
            year = y.group(0) if y else None
        people = r.authors or r.editors
        if not people and not r.type:
            head = r.raw[: r.raw.find(year)] if year and year in r.raw else r.raw[:150]
            people = parse_authors(head)[0]
        if people:
            first = {name_key(people[0].family)}
            others = [name_key(a.family) for a in people[1:]]
            count = len(people)
            if r.author_text and re.search(r"…|\.\s?\.\s?\.", r.author_text):
                count = max(count, 8)
            initials, family = people[0].initials, people[0].family
        elif r.corporate_author:
            first = {name_key(r.corporate_author), acronym(r.corporate_author)}
            bracket = re.search(r"\[([A-Z]{2,})\]", r.raw[:200])
            if bracket:
                first.add(bracket.group(1).lower())
            others, count, initials, family = [], 1, "", r.corporate_author
        else:
            # Title-first or unreadable entries: the first words stand for the author.
            word = re.match(r"\W*([^\s,.(]+(?: [A-Z][^\s,.(]+)?)", r.raw)
            family = word.group(1) if word else ""
            first, others, count, initials = {name_key(family)}, [], 1, ""
        keys.append(
            RefKey(
                r,
                {k for k in first if k},
                others,
                year,
                r.year_suffix,
                count,
                initials,
                _parts(family),
                family,
            )
        )
    return keys


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def similar(a: str, b: str) -> bool:
    """Spelling variants of one surname: 'majdinasab' / 'majdinasa' (1–2 letters apart)."""
    if a == b or min(len(a), len(b)) < 4:
        return False
    limit = 1 if min(len(a), len(b)) < 6 else 2
    return edit_distance(a, b) <= limit


@dataclass
class Match:
    citation: Citation
    outcome: str  # "ok" | "year" | "spelling" | "not_listed" | "ambiguous" | "suffix"
    candidates: list[RefKey] = field(default_factory=list)


def match(citations: list[Citation], refs: list[Reference]) -> list[Match]:
    """Match every citation (personal communications excepted) and set `reference_id`."""
    keys = reference_keys(refs)
    out = []
    for c in citations:
        if c.personal:
            continue
        out.append(_match_one(c, keys))
    return out


def _title_key(text: str) -> str:
    return name_key(" ".join(text.split()[:4]))


def _match_one(c: Citation, keys: list[RefKey]) -> Match:
    if c.title is not None and not c.authors:
        t = _title_key(c.title)
        found = [k for k in keys if t and _title_key(k.ref.title or k.ref.raw).startswith(t)]
        return _decide(c, found, keys)
    first = name_key(c.authors[0])
    same_name = [k for k in keys if first in k.first]
    if same_name:
        return _decide(c, same_name, keys)
    close = [k for k in keys if k.year == c.year and any(similar(first, f) for f in k.first)]
    # Part of a double surname: "Salgado" for "Salgado-Caxito", "Waheed" for "Waheed Anwar".
    cited_parts = _parts(c.authors[0])
    partial = [k for k in keys if k.year == c.year and (first in k.parts or k.first & cited_parts)]
    for found in (close, partial):
        if found:
            m = _decide(c, found, keys)
            if m.outcome == "ok":
                m.outcome = "spelling"
            return m
    return Match(c, "not_listed")


def _parts(name: str) -> set[str]:
    """The parts of a double name: 'Salgado-Caxito' -> {'salgado', 'caxito'}; 'Ziyun Li' ->
    {'ziyun', 'li'}."""
    words = [name_key(w) for w in re.split(r"[\s-]+", name)]
    return {w for w in words if len(w) >= 2} if len(words) > 1 else set()


def _decide(c: Citation, cands: list[RefKey], keys: list[RefKey]) -> Match:
    same_year = [k for k in cands if k.year == c.year]
    if not same_year:
        if len(cands) == 1:
            c.reference_id = cands[0].ref.id
        return Match(c, "year", cands)
    if len(same_year) > 1 and len(c.authors) > 1:
        # Further authors tell same-surname, same-year works apart.
        later = [name_key(a) for a in c.authors[1:]]
        narrowed = [k for k in same_year if k.others[: len(later)] == later]
        same_year = narrowed or same_year
    if len(same_year) > 1:
        # "Ajmal, 2025" is the one-author work, "Ajmal et al., 2025" the one with co-authors.
        fits = [
            k for k in same_year if (k.authors >= 3 if c.et_al else k.authors == len(c.authors))
        ]
        same_year = fits or same_year
    if len(same_year) > 1:
        by_suffix = [k for k in same_year if k.suffix and k.suffix == c.year_suffix]
        if len(by_suffix) == 1:
            same_year = by_suffix
    if len(same_year) > 1:
        return Match(c, "ambiguous", same_year)
    k = same_year[0]
    c.reference_id = k.ref.id
    if (k.suffix or None) != (c.year_suffix or None):
        return Match(c, "suffix", [k])
    return Match(c, "ok", [k])
