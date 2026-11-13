"""Corrected references and the corrected reference list (plan phase 7, spec §5 ⑨).

Each parsed reference is rendered with its template from the student's own field values,
after the fixes that the findings call for. Three safeguards:

* Structure (rule FMT-ORDER-01): the reference rendered *without* fixes is compared with
  what the student wrote. Any difference that no finding already explains is reported.
* Fidelity: if the rendering drops words the student wrote, the renderer has not
  understood the reference, and no corrected version is offered.
* No invented data: every word of a correction comes from the student's text, the
  template, a placeholder, or a finding's correction (e.g. a journal's full name).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from checkref.correct.render import PLACEHOLDERS, render, template_nodes, values_of
from checkref.models import (
    CorrectedReference,
    CorrectionStatus,
    Finding,
    Level,
    Piece,
    Reference,
)
from checkref.normalize import body_lines
from checkref.parse import AUTHOR, LITERALS
from checkref.rules.checks import (
    ELLIPSIS,
    MONONYM,
    CheckContext,
    _author_keys,
    _fold,
    _sort_key,
    finding,
    proper_noun_list,
)
from checkref.rules.rulebook import rulebook

# Rules whose problem disappears when the reference is rendered with its template: italics,
# punctuation and spacing come from the template; a missing element becomes a placeholder.
TEMPLATE_FIXED = {
    "FMT-ITAL-01",
    "FMT-ITAL-02",
    "FMT-ITAL-03",
    "FMT-ITAL-04",
    "FMT-ORDER-01",
    "FMT-SPACE-01",
    "REF-JRNL-02",
    "REF-JRNL-03",
    "REF-DOI-02",
    "REF-PUB-01",
    "REF-BOOK-01",
    "REF-BOOK-02",
}
# Problems with the list as a whole, fixed when the corrected list is assembled.
LIST_FIXED = {
    "LST-ORDER-01",
    "LST-ORDER-02",
    "LST-ORDER-03",
    "LST-DUP-01",
    "LST-INTEXTONLY-01",
    "LST-MERGED-01",
    "LST-HEADING-01",
}


@dataclass
class Fix:
    values: dict
    ref: Reference
    ctx: CheckContext
    allowed_words: set[str] = field(default_factory=set)  # words a fix may introduce
    notes: list[str] = field(default_factory=list)


Fixer = Callable[[Fix, Finding], bool]
FIXERS: dict[str, Fixer] = {}


def fixer(*rule_ids: str):
    def register(fn: Fixer) -> Fixer:
        for rule_id in rule_ids:
            FIXERS[rule_id] = fn
        return fn

    return register


def _set(fix: Fix, key: str, value: str | None) -> bool:
    fix.values[key] = value
    if value:
        fix.allowed_words.update(_words(value))
    return True


# --------------------------------------------------------------------------- fixers


# A name in Vancouver order inside an APA list: "Broadaway SC", "Abdullah-Al-Wadud M".
VANCOUVER_NAME = re.compile(
    r"(?P<family>[A-ZÀ-Þ][\w'’-]+(?: [A-ZÀ-Þ][\w'’-]+)?) (?P<initials>[A-Z]{1,3})(?![\w.])"
)
# "Tao, L. t." — initials typed in lower case.
LOWERCASE_INITIALS = re.compile(r"(?P<family>[A-ZÀ-Þ][\w'’-]+),\s*(?P<initials>(?:[A-Za-z]\.\s?)+)")
TRAILING_PARTICLE = re.compile(
    r"\s*(van|von|de|da|do|dos|das|der|den|del|di|du|la|le)\b(?=\s*(?:,|&|$))"
)
SEPARATOR = re.compile(r"\s*,?\s*(?:&|and(?= )|…|(?:\.\s?){3})?\s*,?\s*")


def _apa_initials(initials: str) -> str:
    """'S.A.' / 'l. t.' / 'SA' (Vancouver) -> 'S. A.' / 'L. T.' / 'S. A.'; 'J.-P.' kept."""
    if re.fullmatch(r"[A-Z]{1,3}", initials):
        return " ".join(f"{c}." for c in initials)
    text = re.sub(r"\b([a-z])\.", lambda m: m.group(1).upper() + ".", initials.strip())
    text = re.sub(r"\.\s*(?=[A-ZÀ-Þ])", ". ", text)
    return re.sub(r"\.\s*-\s*", ".-", text)


def _names(author_text: str) -> tuple[list[str], bool] | None:
    """The authors as 'Surname, I. I.' and whether an ellipsis was used; None when part of
    the element is not a recognisable personal name."""
    names, truncated, pos = [], False, 0
    text = author_text.strip().rstrip(",")
    while pos < len(text):
        sep = SEPARATOR.match(text, pos)
        if sep and sep.end() > pos:
            truncated |= bool(ELLIPSIS.search(sep.group(0)))
            pos = sep.end()
            continue
        found = [p.match(text, pos) for p in (AUTHOR, VANCOUVER_NAME, LOWERCASE_INITIALS)]
        m = max((f for f in found if f), key=lambda f: f.end(), default=None)
        if not m:
            mononym = MONONYM.match(text, pos)
            if mononym and SEPARATOR.match(text, mononym.end()).end() > mononym.end():
                names.append(mononym.group(0))  # a person known by one name: as given
                pos = mononym.end()
                continue
            return None
        if re.search(r"\b[A-Z]{2,3}\b", m.group("family")):
            return None  # initials run into the surname ("Wong JY, Z.")
        name = f"{m.group('family').strip()}, {_apa_initials(m.group('initials'))}"
        pos = m.end()
        particle = TRAILING_PARTICLE.match(text, pos)  # "Oliveira, E. S. de"
        if particle:
            name += " " + particle.group(1)
            pos = particle.end()
        names.append(name)
    return names, truncated


def canonical_authors(author_text: str) -> str | None:
    """The author element in APA 6 form, or None when some of it is not a 'Surname, I.'
    name (then only the student can fix it). Spaced initials, ', &' before the last
    author, and first six + '…' + last for eight or more."""
    parsed = _names(author_text)
    if not parsed or not parsed[0]:
        return None
    names, truncated = parsed
    keep = rulebook().settings["authors"]["truncate_keep_first"]
    if truncated and len(names) < keep + 1:
        return None  # REF-AUTH-03: authors are missing, only the student knows them
    if len(names) >= rulebook().settings["authors"]["truncate_from"] or truncated:
        return ", ".join(names[:keep]) + ", … " + names[-1]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}, & {names[1]}"
    return ", ".join(names[:-1]) + ", & " + names[-1]


@fixer("REF-AUTH-01", "REF-AUTH-02", "REF-AUTH-03", "REF-AUTH-04")
def _authors(fix: Fix, f: Finding) -> bool:
    text = fix.values.get("author_text")
    fixed = canonical_authors(text) if text else None
    if not fixed:
        return False
    return _set(fix, "author_text", fixed)


@fixer("REF-AUTH-05", "REF-AUTH-06")
def _editor_role(fix: Fix, f: Finding) -> bool:
    return bool(f.correction) and _set(fix, "editor_role", f.correction.strip("()"))


@fixer("REF-DATE-01")
def _date_full_stop(fix: Fix, f: Finding) -> bool:
    text = fix.values.get("author_text")
    if text and not text.endswith("."):
        fix.values["author_text"] = text + "."
    return True  # the full stop after the date comes from the template


@fixer("REF-DATE-02")
def _nd(fix: Fix, f: Finding) -> bool:
    return bool(f.correction) and _set(fix, "year", f.correction.strip("()"))


def _case_change(fix: Fix, key: str, original: str | None, corrected: str | None) -> bool:
    """Apply a letter-case correction to the current value. Case fixes from several
    findings combine letter by letter: each changes only the letters it is about."""
    current = fix.values.get(key)
    if not (current and original and corrected) or corrected.lower() != original.lower():
        return False
    if current.lower() != original.lower():
        return True  # the element was replaced by another fix (e.g. a journal's full name)
    letters = zip(current, original, corrected, strict=True)
    return _set(fix, key, "".join(new if old != new else cur for cur, old, new in letters))


@fixer("REF-TITLE-01")
def _title_case(fix: Fix, f: Finding) -> bool:
    return _case_change(fix, "title", f.original, f.correction)


@fixer("REF-TITLE-03")
def _all_caps(fix: Fix, f: Finding) -> bool:
    title = fix.ref.title
    fixed = f.correction
    if title and not fixed:
        fixed = sentence_case_from_capitals(title, fix.ctx)
        fix.notes.append(
            "The title was converted from capitals automatically: check that proper nouns "
            "and abbreviations keep their capitals."
        )
    return _case_change(fix, "title", title, fixed)


@fixer("REF-TITLE-02")
def _journal_case(fix: Fix, f: Finding) -> bool:
    return _case_change(fix, "container", f.original, f.correction)


@fixer("REF-JRNL-01")
def _journal_name(fix: Fix, f: Finding) -> bool:
    if not f.correction:
        return False
    if f.correction != PLACEHOLDERS["full_journal"]:
        fix.notes.append(
            f"Likely full journal name, from the NLM journal list: {f.correction} (verify)."
        )
    return _set(fix, "container", f.correction)


@fixer("REF-JRNL-04")
def _locator(fix: Fix, f: Finding) -> bool:
    if not (fix.values.get("pages") or fix.values.get("article_number")):
        return True  # missing: the template renders a placeholder
    if not f.correction:
        return False
    key = "pages" if fix.values.get("pages") else "article_number"
    return _set(fix, key, f.correction)


@fixer("FMT-DASH-01", "FMT-DASH-02")
def _dash(fix: Fix, f: Finding) -> bool:
    pages = fix.values.get("pages")
    if not (pages and f.original and f.correction and f.original in pages):
        return False
    return _set(fix, "pages", pages.replace(f.original, f.correction))


@fixer("REF-DOI-01", "REF-DOI-03")
def _doi(fix: Fix, f: Finding) -> bool:
    if not f.correction:
        return False
    if fix.values.get("doi"):
        return _set(fix, "doi", f.correction)
    return False


@fixer("REF-DOI-05")
def _doi_only(fix: Fix, f: Finding) -> bool:
    fix.values.update(url=None, retrieval_statement=None, retrieval_date=None)
    if fix.values.get("_type") == "journal_article_no_doi_online":
        fix.values["_type"] = "journal_article"
    return True


@fixer("REF-URL-01")
def _homepage(fix: Fix, f: Finding) -> bool:
    return _set(fix, "url", PLACEHOLDERS["homepage_url"])


@fixer("REF-URL-02", "REF-URL-06")
def _url(fix: Fix, f: Finding) -> bool:
    return bool(f.correction) and _set(fix, "url", f.correction)


@fixer("REF-URL-03", "REF-URL-05")
def _retrieved_from(fix: Fix, f: Finding) -> bool:
    fix.values.update(retrieval_statement="Retrieved from", retrieval_date=None)
    return True


@fixer("REF-PUB-03")
def _author_publisher(fix: Fix, f: Finding) -> bool:
    return _set(fix, "publisher", "Author")


@fixer("REF-SOFT-01", "REF-DESC-01")
def _description(fix: Fix, f: Finding) -> bool:
    return bool(f.correction) and _set(fix, "description", f.correction.strip("[]"))


def body_abbreviations(ctx: CheckContext) -> set[str]:
    """Words the thesis writes in capitals inside ordinary sentences (DNA, PCR, WHO), not
    in headings ("MATERIALS AND METHODS")."""
    found: set[str] = set()
    for line in body_lines(ctx.doc):
        words = re.findall(r"[A-Za-zÀ-ɏ][\w'’-]*", line.text)
        if len(words) < 6 or sum(w[0].islower() for w in words) < 0.6 * len(words):
            continue
        found.update(re.findall(r"\b[A-Z][A-Z0-9]{1,7}\b", line.text))
    return found


def sentence_case_from_capitals(title: str, ctx: CheckContext) -> str:
    """Sentence case for a title written in capitals, without the AI: lower-case every word
    except the first, the first after a colon, known proper nouns, and words the thesis
    itself writes in capitals (abbreviations such as DNA or PCR)."""
    proper = proper_noun_list() | ctx.body_proper_nouns
    body_caps = body_abbreviations(ctx)

    def word(m: re.Match) -> str:
        w = m.group(0)
        start = title[: m.start()].rstrip()
        if w in body_caps or any(c.isdigit() for c in w):
            return w
        if not start or start.endswith((":", "?", "!")):
            return w[0].upper() + w[1:].lower()
        month_or_verb = _fold(w) in {"may", "march"} and not re.match(r"\s*\d", title[m.end() :])
        if _fold(w) in proper and not month_or_verb:
            return w[0].upper() + w[1:].lower()
        return w.lower()

    return re.sub(r"[A-Za-zÀ-ɏ][\w'’-]*", word, title)


# --------------------------------------------------------------------------- one reference


def _words(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[^\W_]+", text)]


def _template_words(template_id: str) -> set[str]:
    words: set[str] = set()

    def walk(nodes):
        for n in nodes:
            if n.kind == "text":
                words.update(_words(n.text))
            elif n.children:
                walk(n.children)

    walk(template_nodes(template_id))
    return words


PLACEHOLDER_WORDS = {w for p in PLACEHOLDERS.values() for w in _words(p)}


def _text(pieces: list[Piece]) -> str:
    return "".join(p.text for p in pieces)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _covered(ref: Reference, findings: list[Finding]) -> list[tuple[int, int]]:
    """Positions in the raw text that existing findings already point at."""
    spans = []
    raw = _squash(ref.raw)
    for f in findings:
        original = _squash(f.original or "")
        if not original or original == raw:
            continue
        for m in re.finditer(re.escape(original), raw):
            spans.append((m.start(), m.end()))
    return spans


def _structure(
    ref: Reference, rendered: list[Piece], findings: list[Finding]
) -> tuple[bool, list[str]]:
    """(renderer understood the reference, unexplained differences from the template)."""
    raw, text = _squash(ref.raw), _squash(_text(rendered))
    allowed = _template_words(ref.type or "") | PLACEHOLDER_WORDS | LITERALS
    lost = Counter(_words(raw)) - Counter(_words(text))
    added = Counter(_words(text)) - Counter(_words(raw))
    if lost or any(w not in allowed for w in added):
        return False, []
    placeholder_at = []
    pos = 0
    for p in rendered:
        if p.placeholder:
            placeholder_at.append((pos, pos + len(p.text)))
        pos += len(p.text)
    covered = _covered(ref, findings)
    diffs: list[list[int]] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, raw, text, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        lo, hi = (i1 - 1, i2 + 1) if i1 == i2 else (i1, i2)
        if any(a < hi and lo < b for a, b in covered):
            continue
        if any(a <= j2 and j1 <= b for a, b in placeholder_at):
            continue
        if diffs and i1 - diffs[-1][1] <= 8:  # one snippet for neighbouring differences
            diffs[-1][1], diffs[-1][3] = i2, j2
        else:
            diffs.append([i1, i2, j1, j2])
    snippets = []
    for i1, i2, j1, j2 in diffs:
        a, b = max(0, i1 - 8), min(len(raw), i2 + 8)
        c, d = max(0, j1 - 8), min(len(text), j2 + 8)
        snippets.append(f"'…{raw[a:b]}…' → '…{text[c:d]}…'")
    return True, snippets


def correct_reference(
    ref: Reference, findings: list[Finding], ctx: CheckContext
) -> tuple[CorrectedReference, list[Finding]]:
    """The corrected reference, plus any FMT-ORDER-01 finding the comparison produces."""
    findings = [f for f in findings if f.reference_id == ref.id]
    if not ref.type or ref.type not in {t.id for t in rulebook().templates}:
        return (
            CorrectedReference(
                reference_id=ref.id,
                status=CorrectionStatus.NOT_CORRECTED,
                pieces=[Piece(text=ref.raw)],
                notes=["The reference could not be read as an APA reference; rewrite it."],
            ),
            [],
        )
    if any(f.rule_id == "LST-TYPE-01" for f in findings):
        return (
            CorrectedReference(
                reference_id=ref.id,
                status=CorrectionStatus.NOT_CORRECTED,
                pieces=[Piece(text=ref.raw)],
                notes=["The source type is unclear, so no corrected version is offered."],
            ),
            [],
        )
    new_findings: list[Finding] = []
    understood, differences = _structure(ref, render(ref.type, values_of(ref)), findings)
    if understood and differences:
        rule = rulebook().rule("FMT-ORDER-01")
        new_findings.append(
            finding(
                rule,
                ref,
                "Punctuation or element order differs from the template: "
                + "; ".join(differences[:4])
                + ".",
            )
        )
    errors = [f for f in findings + new_findings if f.level == Level.ERROR]

    fix = Fix(values=values_of(ref), ref=ref, ctx=ctx)
    unfixed = []
    for f in errors:
        if f.rule_id in TEMPLATE_FIXED or f.rule_id in LIST_FIXED:
            continue
        fn = FIXERS.get(f.rule_id)
        if not (fn and fn(fix, f)):
            unfixed.append(f.rule_id)
    if not understood:
        return (
            CorrectedReference(
                reference_id=ref.id,
                status=CorrectionStatus.NOT_CORRECTED,
                pieces=[Piece(text=ref.raw)],
                unfixed=sorted({f.rule_id for f in errors}),
                notes=[
                    "The reference has elements the template does not provide for; "
                    "correct it by hand using the findings."
                ],
            ),
            new_findings,
        )
    pieces = render(fix.values.get("_type") or ref.type, fix.values)
    template_id = fix.values.get("_type") or ref.type
    allowed = (
        set(_words(ref.raw))
        | _template_words(template_id)
        | PLACEHOLDER_WORDS
        | LITERALS
        | fix.allowed_words
    )
    invented = [w for w in _words(_text(pieces)) if w not in allowed]
    if invented:  # a safeguard: should never happen
        return (
            CorrectedReference(
                reference_id=ref.id,
                status=CorrectionStatus.NOT_CORRECTED,
                pieces=[Piece(text=ref.raw)],
                unfixed=sorted({f.rule_id for f in errors}),
                notes=[f"Internal check: the correction added words ({', '.join(invented)})."],
            ),
            new_findings,
        )
    if not errors:
        status = CorrectionStatus.CORRECT
    elif unfixed:
        status = CorrectionStatus.PARTIAL
    else:
        status = CorrectionStatus.CORRECTED
    return (
        CorrectedReference(
            reference_id=ref.id,
            status=status,
            pieces=pieces,
            unfixed=sorted(set(unfixed)),
            notes=fix.notes,
        ),
        new_findings,
    )


# --------------------------------------------------------------------------- the list


def _with_year_suffixes(refs: list[Reference], corrected: dict[str, CorrectedReference]):
    """Same author(s) and year: add a, b … after the year, ordered by title (LST-ORDER-03)."""
    groups: dict[tuple, list[Reference]] = {}
    for ref in refs:
        if ref.year and ref.authors and not ref.year_suffix and ref.year[:1].isdigit():
            groups.setdefault((tuple(_author_keys(ref)), ref.year), []).append(ref)
    for group in groups.values():
        if len(group) < 2:
            continue
        by_title = sorted(group, key=lambda r: _fold(r.title or ""))
        for letter, ref in zip("abcdefghijklmnopqrstuvwxyz", by_title, strict=False):
            c = corrected[ref.id]
            for p in c.pieces:
                if f"({ref.year}" in p.text:
                    p.text = p.text.replace(f"({ref.year}", f"({ref.year}{letter}", 1)
                    break


def corrected_list(
    refs: list[Reference], findings: list[Finding], corrected: dict[str, CorrectedReference]
) -> list[CorrectedReference]:
    """The full corrected reference list: duplicates and personal communications removed,
    year suffixes added, in alphabetical order (then year, for the same authors)."""
    drop = {f.reference_id for f in findings if f.rule_id in {"LST-DUP-01", "LST-INTEXTONLY-01"}}
    kept = [r for r in refs if r.id not in drop]
    _with_year_suffixes(kept, corrected)

    def key(ref: Reference):
        year = ref.year or ""
        return (_sort_key(ref), len(ref.authors) > 1, _author_keys(ref)[1:], year, ref.title or "")

    return [corrected[r.id] for r in sorted(kept, key=key)]


def correct_all(
    refs: list[Reference], findings: list[Finding], ctx: CheckContext
) -> tuple[dict[str, CorrectedReference], list[Finding]]:
    """Corrected references by id, and the findings with FMT-ORDER-01 added and every
    finding's `correction` filled in from the corrected reference where it was empty."""
    by_ref: dict[str, list[Finding]] = {}
    for f in findings:
        if f.reference_id:
            by_ref.setdefault(f.reference_id, []).append(f)
    corrected: dict[str, CorrectedReference] = {}
    added: list[Finding] = []
    for ref in refs:
        c, new = correct_reference(ref, by_ref.get(ref.id, []), ctx)
        corrected[ref.id] = c
        added += new
    for f in findings + added:
        c = corrected.get(f.reference_id or "")
        if (
            f.level == Level.ERROR
            and not f.correction
            and c
            and c.status in {CorrectionStatus.CORRECTED, CorrectionStatus.PARTIAL}
            and f.rule_id not in c.unfixed
        ):
            f.correction = c.text
    return corrected, findings + added
