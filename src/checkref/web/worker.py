"""Runs one check in a child process: `python -m checkref.web.worker JOB_DIR`.

A separate process keeps a slow or broken file from blocking the web server, and lets the
dispatcher stop it on timeout and cap its memory. The job folder holds:

- in: `input.pdf` or `input.docx`, and `job.json` (original file name and options);
- out: `progress.json` (the current stage), `result.json` (counts, or a message for the user),
  `report.html`, `report.pdf` and `corrected.docx`.

The uploaded file is deleted as soon as the check ends, whatever the outcome. Nothing from the
thesis is written to stderr (spec §5 ⑫): only exception types and code locations.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
import zipfile
from pathlib import Path

MAX_DOCX_UNPACKED = 300 * 1024 * 1024  # a larger unpacked size means a zip bomb, not a thesis
MAX_DOCX_PARTS = 5000


class Rejected(Exception):
    """The file cannot be checked; the message is shown to the user."""


def write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def count_pages(path: Path) -> int | None:
    """Page count, read before the full check so that oversized files stop early. A Word file
    has no fixed pages; the count Word saved in docProps/app.xml is used when present."""
    if path.suffix == ".pdf":
        import pdfplumber

        try:
            with pdfplumber.open(path) as pdf:
                return len(pdf.pages)
        except Exception as exc:
            raise Rejected("This file could not be opened as a PDF.") from exc
    try:
        with zipfile.ZipFile(path) as z:
            parts = z.infolist()
            if len(parts) > MAX_DOCX_PARTS or sum(p.file_size for p in parts) > MAX_DOCX_UNPACKED:
                raise Rejected("This Word file is too large to check.")
            if "word/document.xml" not in z.namelist():
                raise Rejected("This file could not be opened as a Word (.docx) document.")
            try:
                app = z.read("docProps/app.xml").decode("utf-8", "replace")
            except KeyError:
                return None
    except zipfile.BadZipFile as exc:
        raise Rejected("This file could not be opened as a Word (.docx) document.") from exc
    start = app.find("<Pages>")
    end = app.find("</Pages>", start)
    if start < 0 or end < 0:
        return None
    try:
        return int(app[start + len("<Pages>") : end])
    except ValueError:
        return None


def run(job_dir: Path) -> dict:
    from checkref.ingest import ScannedPdfError
    from checkref.pipeline import check_file
    from checkref.report.model import build_report
    from checkref.report.render import to_docx, to_html, to_pdf
    from checkref.web.config import CREDITS

    options = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    (source,) = [p for p in job_dir.iterdir() if p.name.startswith("input.")]
    progress = job_dir / "progress.json"

    def step(stage: str) -> None:
        write_json(progress, {"stage": stage})

    started = time.monotonic()
    try:
        step("opening")
        pages = count_pages(source)
        if pages and pages > options["max_pages"]:
            raise Rejected(
                f"This file has {pages} pages; the limit is {options['max_pages']}. "
                "Please upload a shorter file, for example the chapters with citations and "
                "the reference list."
            )
        try:
            result = check_file(source, recency=options.get("recency"), progress=step)
        except ScannedPdfError as exc:
            raise Rejected(str(exc)) from exc
    finally:
        source.unlink(missing_ok=True)
    checked = time.monotonic()

    step("report")
    report = build_report(result, options.get("recency"))
    report.file_name = options["file_name"]
    note = (
        f"Your file has already been deleted. This report is deleted {options['expiry_min']} "
        "minutes after the check, or as soon as the PDF report has been downloaded."
    )
    links = {"pdf": "pdf", "delete": "delete", "note": note, "credits": CREDITS}
    (job_dir / "report.html").write_text(to_html(report, links), encoding="utf-8")
    (job_dir / "report.pdf").write_bytes(to_pdf(report))
    (job_dir / "corrected.docx").write_bytes(to_docx(report))
    return {
        "ok": True,
        "pages": pages,
        "references": len(result.references),
        "citations": len(result.citations),
        "errors": len(result.errors),
        "needs_review": len(result.needs_review),
        "check_seconds": round(checked - started, 1),
        "report_seconds": round(time.monotonic() - checked, 1),
    }


def _where(exc: BaseException) -> str:
    """The exception type and the innermost code location: no values, so no thesis text."""
    frames = traceback.extract_tb(exc.__traceback__)
    last = frames[-1] if frames else None
    place = f" at {Path(last.filename).name}:{last.lineno}" if last else ""
    return f"{type(exc).__name__}{place}"


def main(argv: list[str]) -> int:
    job_dir = Path(argv[0])
    memory_mb = int(argv[1]) if len(argv) > 1 else 0
    if memory_mb:
        import resource

        limit = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    try:
        outcome = run(job_dir)
    except Rejected as exc:
        outcome = {"ok": False, "message": str(exc)}
    except MemoryError:
        outcome = {"ok": False, "message": "This file needs more memory than the server allows."}
    except Exception as exc:
        print(f"worker failed: {_where(exc)}", file=sys.stderr)
        outcome = {
            "ok": False,
            "message": "Something went wrong while checking this file. If it keeps happening, "
            "please try the other format (PDF or Word).",
        }
    finally:
        for p in job_dir.glob("input.*"):
            p.unlink(missing_ok=True)
    write_json(job_dir / "result.json", outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
