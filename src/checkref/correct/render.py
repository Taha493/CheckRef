"""Render a reference from its fields with a rulebook template (plan phase 7).

The template supplies element order, punctuation and italics (rulebook/README.md, "Template
pattern language"); the field values come from the parsed reference, with any corrections
applied. A required element that is missing becomes a placeholder such as "[page range]".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache

from checkref.models import Piece, Reference
from checkref.rules.rulebook import rulebook

# Placeholders for information only the student can supply. Their words are allowed in a
# correction by the no-invented-data guard.
PLACEHOLDERS = {
    "author": "[author]",
    "date": "[year]",
    "title": "[title]",
    "container": "[journal name]",
    "full_journal": "[full journal name]",
    "volume": "[volume]",
    "pages": "[page range]",
    "publisher_location": "[City, Country]",
    "publisher": "[publisher]",
    "homepage_url": "[journal homepage URL]",
    "url": "[URL]",
    "degree": "[type of thesis]",
    "meeting": "[meeting]",
    "description": "[description]",
    "authors_rest": "[remaining authors]",
}

# The rulebook patterns name some elements more finely than the parser stores them (e.g. a
# thesis's institution and location are one stored element). These rewrites map a pattern
# onto the stored elements; literal words they absorb are kept in the stored values.
REWRITES = [
    (r"\(\{year\}(?:, \{month\}(?:\[? \{day\}\]?)?)?\)", "({date})"),
    (r"\(\{year\|nd\}\)|\(in press\)|\(\{year_range\}\)", "({date})"),
    (r"Retrieved \[\{retrieval_date\}, from\|from\] \{url\}", "{retrieved}"),
    (r"Retrieved from \[\{publisher\} website: \]\{url\}", "{retrieved}"),
    (r"Retrieved from \{database\} database\.\[ \(\{accession_number\}\)\]", "{retrieved}"),
    (r"Available from \{database\}\. \(\{accession_number\}\)", "{retrieved}"),
    (r"Retrieved from \{(?:homepage_)?url\}", "{retrieved}"),
    (r"\{retrieved_from\|(?:abstract_retrieved_from|available_from)\}", "{retrieved}"),
    (r"\{doi\|retrieved_from\}", "{doi|retrieved}"),
    (r"\{retrieved_from\|location_publisher\}", "{retrieved|location_publisher}"),
    (r"\{page_prefix\} \{pages\}", "{pages|article_number}"),  # "p. D1" is stored whole
    (r"\[ \[\{screen_name\}\]\]", ""),  # "Dunning, B. [volleybrian]." is one author element
    (r"\(\{degree\}, \{institution\}, \{location\}\)", "({degree})"),
    (r"\(Unpublished \{degree\}\)\. \{institution\}, \{location\}\.", "({degree}). {publisher}."),
    (r"(?:the meeting of )?\{(?:meeting|organisation)\}, \{location\}\.", "{meeting}."),
    (r"\[ \(\{translator\}, Trans\.\)\]", "[ {translator}]"),
    (r"\(Original work published \{original_year\}\)", "{original}"),
    (r"\{volumes\}", "{volume}"),
    (r"\{standard_number\}", "{report_number}"),
    (r"\{paper_name\}", "{container}"),
]

# Pattern field -> Reference attribute, for fields that are stored under another name.
ALIASES = {
    "chapter_title": "title",
    "term": "title",
    "patent_identifier": "title",
    "journal": "container",
    "magazine": "container",
    "newspaper": "container",
    "book_title": "container",
    "work": "container",
    "symposium_title": "container",
    "series_title": "container",
    "location": "publisher_location",
    "country": "publisher_location",
    "studio": "publisher",
    "source_name": "publisher",
    "software_type": "description",
    "screen_name": "description",
    "editors": "editors_text",
    "chair": "editors_text",
    "series_producer": "editors_text",
    "ed": "editor_role",
}


@dataclass
class Node:
    kind: str  # "text" | "field" | "optional"
    text: str = ""
    names: tuple[str, ...] = ()
    italic: bool = False
    children: list[Node] | None = None


def _rewrite(pattern: str) -> str:
    for old, new in REWRITES:
        pattern = re.sub(old, new, pattern)
    return pattern


def _parse(pattern: str, pos: int = 0, italic: bool = False, close: str = ""):
    """Parse the pattern language into nodes. Returns (nodes, end position, italic state).

    `[...]` is an optional segment, except when it holds a single field or no field at
    all: "[{description}]" and "[Special issue]" are literal square brackets.
    """
    nodes: list[Node] = []
    buf = ""

    def flush():
        nonlocal buf
        if buf:
            nodes.append(Node("text", text=buf, italic=italic))
            buf = ""

    while pos < len(pattern):
        c = pattern[pos]
        if close and c == close:
            flush()
            return nodes, pos + 1, italic
        if c == "*":
            flush()
            italic = not italic
            pos += 1
        elif c == "{":
            flush()
            end = pattern.index("}", pos)
            names = tuple(pattern[pos + 1 : end].split("|"))
            nodes.append(Node("field", names=names, italic=italic))
            pos = end + 1
        elif c == "[":
            end = _matching(pattern, pos)
            inner = pattern[pos + 1 : end]
            if re.fullmatch(r"\{\w+\}", inner) or "{" not in inner:
                # Literal brackets around a description: "[{description}]", "[Video file]".
                buf += "["
                flush()
                children, pos, italic = _parse(pattern, pos + 1, italic, close="]")
                nodes.extend(children)
                buf = "]"
            else:
                flush()
                children, pos, italic = _parse(pattern, pos + 1, italic, close="]")
                nodes.append(Node("optional", children=children))
        else:
            buf += c
            pos += 1
    flush()
    return nodes, pos, italic


def _matching(pattern: str, start: int) -> int:
    depth = 0
    for i in range(start, len(pattern)):
        if pattern[i] == "[":
            depth += 1
        elif pattern[i] == "]":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError(f"unbalanced [ in pattern: {pattern}")


@cache
def template_nodes(template_id: str) -> list[Node]:
    return _parse(_rewrite(rulebook().template(template_id).pattern))[0]


# --------------------------------------------------------------------------- values


def values_of(ref: Reference) -> dict[str, str | None]:
    """The stored elements of a reference, keyed by Reference attribute name."""
    keys = [k for k in Reference.model_fields if k not in {"id", "raw", "lines", "spans"}]
    values = {k: getattr(ref, k) for k in keys if isinstance(getattr(ref, k), str | None)}
    values["_type"] = ref.type
    # Italics inside a roman title (species names: "silkworm (*Bombyx mori* L.)") are
    # kept; a title that is wholly italic where it should not be is not.
    if ref.title and "title" in ref.offsets and ref.italics.get("title", 0.0) < 0.9:
        mask = _italic_mask(ref)
        start, end = ref.offsets["title"]
        if any(mask[start:end]):
            values["_italic:title"] = mask[start:end]
    return values


def _italic_mask(ref: Reference) -> list[bool]:
    mask: list[bool] = []
    for span in ref.spans:
        mask.extend([span.italic] * len(span.text))
    joined = "".join(s.text for s in ref.spans)
    lead = len(joined) - len(joined.lstrip())
    return mask[lead : lead + len(ref.raw)]


def _date(v: dict) -> str | None:
    year = v.get("year")
    if not year:
        return None
    suffix = v.get("year_suffix") or ""
    if suffix and not year[:1].isdigit():
        suffix = "-" + suffix  # (n.d.-a), (in press-b)
    detail = v.get("date_detail")
    return f"{year}{suffix}" + (f", {detail}" if detail else "")


def _retrieved(v: dict) -> str | None:
    statement = v.get("retrieval_statement") or ("Retrieved from" if v.get("url") else None)
    if v.get("database") and not v.get("url"):
        acc = v.get("report_number")
        statement = v.get("retrieval_statement") or "Retrieved from"
        return f"{statement} {v['database']} database." + (f" ({acc})" if acc else "")
    if not v.get("url"):
        return None
    return f"{statement} {v['url']}"


def _extra(v: dict, pattern: str) -> str | None:
    m = re.search(pattern, v.get("extra") or "")
    return m.group(0) if m else None


def resolve(name: str, v: dict) -> str | None:
    """The text of one pattern field, or None when the reference does not have it."""
    if name in ("author", "editors_inverted"):
        return v.get("author_text")
    if name in ("corporate_author", "contributors"):
        text = v.get("author_text")
        return text[:-1] if text and text.endswith(".") and not text.endswith("..") else text
    if name == "date":
        return _date(v)
    if name == "retrieved":
        return _retrieved(v)
    if name == "edition":
        ed = v.get("edition")
        return re.sub(r"\s*ed\.$", "", ed) if ed else None
    if name == "title" and v.get("_type") == "journal_special_issue":
        title = v.get("title")
        return re.sub(r"\s*\[Special issue\]$", "", title, flags=re.I) if title else None
    if name == "translator":
        return _extra(v, r"\([^()]*Trans\.\)")
    if name == "original":
        return _extra(v, r"\(Original work published [^)]+\)")
    if name == "location_publisher":
        loc, pub = v.get("publisher_location"), v.get("publisher")
        return f"{loc}: {pub}." if loc and pub else None
    return v.get(ALIASES.get(name, name))


def _placeholder(names: tuple[str, ...]) -> str:
    for name in names:
        key = ALIASES.get(name, name)
        if name in ("pages", "article_number") or key == "pages":
            return PLACEHOLDERS["pages"]
        if key in PLACEHOLDERS:
            return PLACEHOLDERS[key]
    return f"[{names[0].replace('_', ' ')}]"


def _emit(nodes: list[Node], v: dict, out: list[Piece], placeholders: bool) -> bool:
    """Append the rendering of `nodes`; False when a required field is missing and
    placeholders are off (used for optional segments)."""
    for node in nodes:
        if node.kind == "text":
            out.append(Piece(text=node.text, italic=node.italic))
        elif node.kind == "field":
            value = next((x for n in node.names if (x := resolve(n, v))), None)
            inner = v.get(f"_italic:{_key(node.names)}") or []
            if value is None:
                if not placeholders:
                    return False
                text = _placeholder(node.names)
                out.append(Piece(text=text, italic=node.italic, placeholder=True))
            elif not node.italic and len(inner) == len(value):
                out.extend(_with_inner_italics(value, inner))
            else:
                out.extend(_with_placeholders(value, node.italic))
        else:
            trial: list[Piece] = []
            if _emit(node.children or [], v, trial, placeholders=False):
                out.extend(trial)
    return True


def _key(names: tuple[str, ...]) -> str:
    return ALIASES.get(names[0], names[0])


def _with_inner_italics(value: str, mask: list[bool]) -> list[Piece]:
    pieces: list[Piece] = []
    for ch, italic in zip(value, mask, strict=True):
        if pieces and pieces[-1].italic == italic:
            pieces[-1].text += ch
        else:
            pieces.append(Piece(text=ch, italic=italic))
    return pieces


PLACEHOLDER_TEXT = re.compile("|".join(re.escape(p) for p in PLACEHOLDERS.values()))


def _with_placeholders(value: str, italic: bool) -> list[Piece]:
    """A value, with any placeholder inside it (set by a fix) marked as one."""
    pieces, pos = [], 0
    for m in PLACEHOLDER_TEXT.finditer(value):
        if m.start() > pos:
            pieces.append(Piece(text=value[pos : m.start()], italic=italic))
        pieces.append(Piece(text=m.group(0), italic=italic, placeholder=True))
        pos = m.end()
    if pos < len(value):
        pieces.append(Piece(text=value[pos:], italic=italic))
    return pieces


def render(template_id: str, v: dict) -> list[Piece]:
    pieces: list[Piece] = []
    _emit(template_nodes(template_id), v, pieces, placeholders=True)
    return _tidy(pieces)


def _tidy(pieces: list[Piece]) -> list[Piece]:
    """Drop a template full stop after a value that already ends a sentence ('high?.',
    'Ltd..'), and merge neighbouring pieces of the same style."""
    out: list[Piece] = []
    for p in pieces:
        text = p.text
        if out and not p.placeholder and text.startswith("."):
            prev = out[-1].text.rstrip("*")
            if re.search(r"[.?!]$", prev) and not text.startswith(".."):
                text = text[1:]
        if not text:
            continue
        last = out[-1] if out else None
        if last and last.italic == p.italic and not last.placeholder and not p.placeholder:
            last.text += text
        else:
            out.append(Piece(text=text, italic=p.italic, placeholder=p.placeholder))
    return out
