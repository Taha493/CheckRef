# Rulebook

**Status: v1, approved by the project owner on 2026-11-08** (with ruling 6.1 changed to
accept hyphens in page ranges, as the guide does).

The rules CiteSure applies, built from the frozen guide snapshot in `data/guide/` plus the
project rulings in `spec.md` §6. **Only the project owner changes these files.**

| File | Contents |
|---|---|
| `templates.yaml` | One entry per source type: the reference pattern, where it comes from in the guide, and verified examples |
| `rules.yaml` | Every check, with an ID, a level, the source types it applies to, and its source; plus `rulings`, the project rulings (spec §6) in the words reports quote |
| `excluded_examples.yaml` | Guide examples that contain mistakes. These are never used as examples or to derive rules |
| `settings.yaml` | Word lists and limits the checks use (accepted headings, small words, indent range, …) |
| `RULEBOOK.md` | Generated, readable export for review: `uv run python tools/rulebook_report.py` |

## Precedence (spec §4.3)
1. Project rulings (`source.type: ruling`)
2. Rules written in the guide's text (`source.type: guide_text`)
3. The guide's reference templates (`source.type: guide_template`)
4. The guide's examples (`source.type: guide_examples`). These are used only for rules the guide shows but never states (e.g. what is italic). Rules derived from them are marked with this source type.

Rules with `source.type: derived` follow from the template or from a project decision, rather than from a sentence in the guide. They are listed separately in the review export so the owner can confirm them.

## Template pattern language
| Syntax | Meaning |
|---|---|
| `{field}` | a required element |
| `[ ... ]` | an optional segment, rendered only when every field inside it is present |
| `{a\|b}` | exactly one of the fields `a` or `b` |
| `*...*` | italic text |
| anything else | literal text and punctuation, exactly as it must appear |

`{author}` renders the full author element with its closing full stop:
- `Ali, M., & Seale, C.` for people
- `Radio New Zealand.` for a corporate author
- the APA 6 rules for 8 or more authors are applied automatically

`{editors}` renders editors with their initials first (`K. Dew & A. Matheson`), and `{ed}` renders `Ed.` or `Eds.` to match the number of editors.

## Levels
- `error`: breaks the rule.
- `needs_review`: the engine can't decide reliably, or the guide only recommends the practice.
