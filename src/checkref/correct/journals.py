"""Journal names: full names for abbreviations, and headline-style capitals (plan phase 7).

The abbreviation index comes from the NLM journal catalogue (public domain), built by
tools/build_journal_index.py into data/journals/nlm_abbreviations.tsv. A full name is
suggested only when exactly one journal matches the abbreviation.
"""

from __future__ import annotations

import re
from collections import defaultdict
from functools import cache
from pathlib import Path

from checkref.rules.rulebook import rulebook

INDEX = Path(__file__).resolve().parents[3] / "data" / "journals" / "nlm_abbreviations.tsv"


def abbreviation_key(name: str) -> str:
    """'J. Adv. Biol.  Biotechnol' -> 'j adv biol biotechnol'."""
    return re.sub(r"[.\s]+", " ", name).strip().lower()


@cache
def _index() -> dict[str, frozenset[str]]:
    found: dict[str, set[str]] = defaultdict(set)
    if INDEX.is_file():
        for line in INDEX.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                key, _, title = line.partition("\t")
                found[key].add(title)
    return {k: frozenset(v) for k, v in found.items()}


def full_name(abbreviated: str) -> str | None:
    """The journal's full name in headline style, when exactly one journal matches."""
    titles = _index().get(abbreviation_key(abbreviated), frozenset())
    if len(titles) != 1:
        return None
    return headline_case(next(iter(titles)))


def catalogue_name(title: str) -> str:
    """The journal name without the catalogue's additions: subtitles after ' : ' and
    qualifiers such as "Lancet (London, England)" or "(Online)"."""
    title = title.split(" : ")[0]
    return re.sub(r"\s*\((?:[^()]*,[^()]*|Online|Print)\)$", "", title).strip()


def headline_words(name: str) -> list[tuple[str, str]]:
    """(word, headline form) for every word of a journal name whose capital is wrong.

    Headline style: capitalise all words except articles, prepositions and conjunctions
    (rulebook settings `capitalisation`); longer prepositions may take either case.
    """
    caps = rulebook().settings["capitalisation"]
    lower_ok = {w.lower() for w in caps["headline_lowercase"]}
    either = {w.lower() for w in caps["headline_either_case"]}
    words = re.findall(r"[A-Za-zÀ-ɏ][\w'’]*", name)
    wrong = []
    for i, w in enumerate(words):
        lw = w.lower()
        if lw in either or is_acronym(w) and w[:1].isupper():
            continue
        if i == 0 or lw not in lower_ok:
            if w[0].islower():
                wrong.append((w, w[0].upper() + w[1:]))
        elif w[0].isupper() and i > 0:
            wrong.append((w, lw))
    return wrong


def headline_case(name: str) -> str:
    fixed = name
    for bad, good in headline_words(name):
        fixed = re.sub(rf"\b{re.escape(bad)}\b", good, fixed, count=1)
    return fixed


def is_acronym(word: str) -> bool:
    """DNA, PLoS, COVID-19, 5G, single letters: words whose capitals are not a case style."""
    letters = re.sub(r"[^A-Za-z]", "", word)
    return (
        bool(re.search(r"\d", word))
        or sum(c.isupper() for c in letters[1:]) >= 1
        or len(letters) <= 1
    )
