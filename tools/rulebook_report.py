"""Write rulebook/RULEBOOK.md, a readable export of the rulebook for owner review.

Usage:  uv run python tools/rulebook_report.py
"""

from __future__ import annotations

from collections import Counter

from checkref.rules.rulebook import RULEBOOK_DIR, Rule, rulebook

CATEGORIES = [
    ("LST-", "Whole reference list"),
    ("LAY-", "Layout"),
    ("REF-AUTH", "Authors and editors"),
    ("REF-DATE", "Dates"),
    ("REF-TITLE", "Titles and capitalisation"),
    ("REF-JRNL", "Journals"),
    ("REF-BOOK", "Books, reports, theses, conferences, software"),
    ("REF-REPORT", None),
    ("REF-THESIS", None),
    ("REF-CONF", None),
    ("REF-SOFT", None),
    ("REF-PUB", "Publisher and location"),
    ("REF-DESC", "Square-bracket descriptions"),
    ("REF-DOI", "DOI"),
    ("REF-URL", "URLs and retrieval statements"),
    ("FMT-", "Typography: dashes, italics, order, spacing"),
    ("CIT-", "In-text citations"),
    ("MAT-", "Matching citations and references"),
    ("REC-", "Recency (optional, off by default)"),
]

SOURCE_LABEL = {
    "ruling": "Project ruling",
    "guide_text": "Guide text",
    "guide_template": "Guide template",
    "guide_examples": "Guide examples",
    "derived": "Derived — please confirm",
}


def _source(rule: Rule) -> str:
    s = rule.source
    parts = [SOURCE_LABEL[s.type]]
    if s.ruling:
        parts.append(f"spec §{s.ruling}")
    if s.page:
        parts.append(f"`{s.page}`" + (f" › {s.section}" if s.section else ""))
    text = ", ".join(parts)
    if s.quote:
        text += f"<br>“{s.quote}”"
    if s.note:
        text += f"<br>{s.note}"
    return text


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _rule_table(rules: list[Rule]) -> list[str]:
    out = ["| ID | Rule | Level | Applies to | Source |", "|---|---|---|---|---|"]
    for r in rules:
        level = "Error" if r.level == "error" else "Needs review"
        cells = [r.id, _cell(r.title), level, _cell(", ".join(r.applies_to)), _cell(_source(r))]
        out.append("| " + " | ".join(cells) + " |")
    return out


def _deferred_line(d: dict[str, str]) -> str:
    where = f"`{d['page']}`" + (f" › {d['section']}" if d.get("section") else "")
    return f"- {where}: {d['reason']}"


def build() -> str:
    rb = rulebook()
    levels = Counter(r.level for r in rb.rules)
    sources = Counter(r.source.type for r in rb.rules)
    lines = [
        "# CiteSure rulebook v1 — for review",
        "",
        "Generated from `rulebook/*.yaml` by `tools/rulebook_report.py`. Do not edit by hand.",
        "",
        f"- **{len(rb.templates)} source types** (templates), "
        f"{len(rb.in_text_only)} cited in the text only, {len(rb.deferred)} deferred",
        f"- **{len(rb.rules)} rules**: {levels['error']} errors, "
        f"{levels['needs_review']} needs review",
        "- Rules by source: "
        + ", ".join(f"{SOURCE_LABEL[k]} {v}" for k, v in sources.most_common()),
        f"- **{len(rb.excluded_examples) + len(rb.excluded_in_text)} guide examples** "
        "excluded or corrected because they contain mistakes",
        "",
        "## 1. What to check first",
        "",
        "### 1.1 Rules that come from project rulings",
        "",
        "The rulings as reports quote them (`rulings` in `rules.yaml`; full text: spec §6):",
        "",
        "| Ruling | Text |",
        "|---|---|",
        *[f"| {n} {r.title} | {_cell(r.text)} |" for n, r in rb.rulings.items()],
        "",
        *_rule_table([r for r in rb.rules if r.source.type == "ruling" or r.source.ruling]),
        "",
        "### 1.2 Rules not stated in the guide (derived) — please confirm",
        "",
        *_rule_table([r for r in rb.rules if r.source.type == "derived"]),
        "",
        "### 1.3 Guide pages not covered by rulebook v1",
        "",
        "References of these types are reported as *Needs review: source type not covered*.",
        "",
        *[_deferred_line(d) for d in rb.deferred],
        "",
        "## 2. All rules",
        "",
    ]
    done: set[str] = set()
    for prefix, title in CATEGORIES:
        group = [r for r in rb.rules if r.id.startswith(prefix) and r.id not in done]
        if not group:
            continue
        if title is None:  # merged into the previous heading
            lines.pop()  # blank line
            lines += _rule_table(group)[2:] + [""]
        else:
            lines += [f"### {title}", "", *_rule_table(group), ""]
        done |= {r.id for r in group}
    lines += ["## 3. Source types (templates)", ""]
    lines += [
        "Pattern syntax: `{field}` required · `[ … ]` optional · `{a|b}` one of · `*…*` italic.",
        "",
    ]
    for t in rb.templates:
        lines += [
            f"### {t.name} — `{t.id}`",
            "",
            f"Pattern: `{t.pattern}`",
            *[f"Alternative: `{a}`" for a in t.alternatives],
            "",
            f"Source: `{t.source['page']}` › {t.source['section']}",
            "",
        ]
        lines += [f"- Note: {n}" for n in t.notes]
        lines += [f"- Example: {e}" for e in t.examples] or ["- Example: (none in the guide)"]
        lines.append("")
    lines += ["### Cited in the text only (never in the reference list)", ""]
    lines += [
        f"- {t.name}" + (f": {t.in_text_example}" if t.in_text_example else "")
        for t in rb.in_text_only
    ]
    lines += ["", "## 4. Guide examples with mistakes (spec §6.9)", ""]
    lines += ["| Page | Example | Problem | Action |", "|---|---|---|---|"]
    for e in rb.excluded_examples:
        action = e["action"].replace("_", " ") + (f": {e['fix']}" if e.get("fix") else "")
        lines.append(
            f"| `{e['page']}` | {_cell(e['example'])} | {_cell(e['problem'])} | {_cell(action)} |"
        )
    for e in rb.excluded_in_text:
        cells = [f"`{e['page']}`", _cell(e["example"]), _cell(e["problem"]), "excluded"]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    path = RULEBOOK_DIR / "RULEBOOK.md"
    path.write_text(build(), encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
