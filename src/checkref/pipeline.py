"""The checking pipeline end to end (spec §5): ingest → normalise → segment → parse and
classify → rule checks → corrections → in-text citations and matching. The report (plan
phase 9) attaches here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from checkref.citations.checks import check_citations
from checkref.classify import parse_and_classify
from checkref.correct.corrector import correct_all, corrected_list
from checkref.ingest import ingest
from checkref.llm import LLMBackend, get_backend
from checkref.models import Citation, CorrectedReference, Document, Finding, Level, Reference
from checkref.normalize import normalise
from checkref.rules.checks import CheckContext, run_checks
from checkref.segment import Segmentation, segment

# The stages reported to `progress`, in order, with the wording shown to the user.
STAGES = {
    "reading": "Reading the file",
    "references": "Finding the reference list",
    "parsing": "Reading each reference",
    "rules": "Checking the references against the guide",
    "corrections": "Writing the corrected references",
    "citations": "Checking the in-text citations",
}


@dataclass
class CheckResult:
    document: Document
    segmentation: Segmentation
    references: list[Reference]
    findings: list[Finding]
    corrected: dict[str, CorrectedReference]  # by reference id
    corrected_list: list[CorrectedReference]  # the full list, in the corrected order
    citations: list[Citation]  # in-text citations, in reading order

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == Level.ERROR]

    @property
    def needs_review(self) -> list[Finding]:
        return [f for f in self.findings if f.level == Level.NEEDS_REVIEW]


Progress = Callable[[str], None]


def check_document(
    doc: Document,
    llm: LLMBackend | None = None,
    recency: dict | None = None,
    progress: Progress | None = None,
) -> CheckResult:
    """`progress`, if given, is called with each stage name as it starts (see STAGES)."""
    step = progress or (lambda stage: None)
    llm = llm or get_backend()
    step("references")
    doc = normalise(doc)
    seg = segment(doc)
    findings = list(seg.findings)
    step("parsing")
    findings += parse_and_classify(seg.references, llm)
    ctx = CheckContext(
        doc=doc, section_lines=seg.lines, indents=seg.indents, llm=llm, recency=recency
    )
    step("rules")
    findings += run_checks(seg.references, ctx)
    step("corrections")
    corrected, findings = correct_all(seg.references, findings, ctx)
    step("citations")
    cites = check_citations(doc, seg, seg.references)
    # Reference-list findings in list order, then citation findings in reading order.
    order = {r.id: i for i, r in enumerate(seg.references)}
    position = {c.id: c.position for c in cites.citations}
    findings.sort(key=lambda f: (order.get(f.reference_id or "", -1), f.rule_id))
    findings += sorted(cites.findings, key=lambda f: position.get(f.citation_id or "", -1))
    full_list = corrected_list(seg.references, findings, corrected)
    return CheckResult(doc, seg, seg.references, findings, corrected, full_list, cites.citations)


def check_file(
    path: Path,
    llm: LLMBackend | None = None,
    recency: dict | None = None,
    progress: Progress | None = None,
) -> CheckResult:
    if progress:
        progress("reading")
    return check_document(ingest(path), llm, recency, progress)
