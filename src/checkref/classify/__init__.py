"""Source-type decision and the parse pipeline with AI fallback (plan phase 5, spec §5 ⑥ ⑦).

Order: the deterministic parser first; references it cannot place go to the AI backend in
one batched call; every AI answer must pass the fidelity check (no words dropped, none
invented). Whatever is still unparsed, or whose type is ambiguous, gets a finding.
"""

from __future__ import annotations

from checkref.llm import ExtractedFields, LLMBackend, NullBackend
from checkref.models import Finding, Level, Location, Reference
from checkref.parse import (
    ParseResult,
    invented_words,
    missing_words,
    parse_authors,
    parse_reference,
)
from checkref.rules.rulebook import rulebook
from checkref.segment import VANCOUVER_AUTHOR

# Two candidate types from different groups closer than this are "type unclear".
AMBIGUITY_MARGIN = 1.0


def _group(template_id: str) -> str:
    return rulebook().template(template_id).group


def _location(ref: Reference) -> Location:
    first = ref.lines[0] if ref.lines else None
    return Location(page=ref.page, top=first.top if first else None, x0=first.x0 if first else None)


def _apply_ai(ref: Reference, fields: ExtractedFields) -> bool:
    """Copy AI fields into `ref` if they pass the fidelity check. Returns success."""
    known = {t.id for t in rulebook().templates}
    trial = ref.model_copy(deep=True)
    for key, value in fields.model_dump(exclude={"id", "type"}).items():
        if value is not None:
            setattr(trial, key, value)
    if trial.author_text:
        trial.authors, trial.corporate_author = parse_authors(trial.author_text)
    trial.type = fields.type if fields.type in known else None
    if missing_words(trial) or invented_words(trial) or trial.type is None:
        return False
    trial.parsed_by = "ai"
    for key, value in trial.model_dump().items():
        setattr(ref, key, value)
    return True


def _ambiguity(ref: Reference) -> Finding | None:
    if len(ref.type_candidates) < 2:
        return None
    (best, best_score), *others = ref.type_candidates
    rival = next(((t, s) for t, s in others if _group(t) != _group(best)), None)
    if rival and best_score - rival[1] < AMBIGUITY_MARGIN:
        names = [rulebook().template(t).name.lower() for t in (best, rival[0])]
        return Finding(
            level=Level.NEEDS_REVIEW,
            rule_id="LST-TYPE-01",
            message=f"Source type unclear: it could be a {names[0]} or a {names[1]}. "
            f"Checked as a {names[0]}.",
            location=_location(ref),
            reference_id=ref.id,
            original=ref.raw,
        )
    return None


def parse_and_classify(references: list[Reference], llm: LLMBackend | None = None) -> list[Finding]:
    """Parse every reference in place; return the classification findings."""
    llm = llm or NullBackend()
    findings: list[Finding] = []
    results: dict[str, ParseResult] = {r.id: parse_reference(r) for r in references}
    pending = [r for r in references if not results[r.id].ok]
    answers = llm.extract_fields([(r.id, r.raw) for r in pending]) if pending else {}

    for ref in references:
        if results[ref.id].ok:
            finding = _ambiguity(ref)
        elif ref.id in answers and _apply_ai(ref, answers[ref.id]):
            finding = None
        elif VANCOUVER_AUTHOR.match(ref.raw) and "(" not in ref.raw[:60]:
            finding = Finding(
                level=Level.ERROR,
                rule_id="LST-STYLE-01",
                message="This reference is written in another citation style (it looks like "
                "Vancouver: 'Surname Initials' and the year after the journal). "
                "Rewrite it in APA style.",
                location=_location(ref),
                reference_id=ref.id,
                original=ref.raw,
            )
        else:
            finding = Finding(
                level=Level.NEEDS_REVIEW,
                rule_id="LST-TYPE-01",
                message="The source type could not be determined: the reference does not match any "
                "APA 6th template, possibly because elements are missing. Please check it by hand.",
                location=_location(ref),
                reference_id=ref.id,
                original=ref.raw,
            )
        if finding:
            findings.append(finding)
    return findings
