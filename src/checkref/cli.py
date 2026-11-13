"""Command-line entry point: `checkref check <file>` prints the findings and the corrected
reference list as JSON."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from checkref import __version__
from checkref.ingest import ScannedPdfError, UnsupportedFileError, ingest
from checkref.models import LineRole
from checkref.normalize import normalise
from checkref.pipeline import check_file


def _dump(path: Path) -> int:
    """Development aid: print every ingested line with its position and italics."""
    try:
        doc = normalise(ingest(path))
    except (ScannedPdfError, UnsupportedFileError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for ln in doc.lines:
        if doc.kind == "pdf":
            where = f"p{ln.page:>3} x{ln.x0:6.1f} y{ln.top:6.1f}"
        else:
            where = f"¶{ln.index:>4} ind{ln.left_indent or 0:5.1f}/{ln.first_line_indent or 0:6.1f}"
        role = "" if ln.role == LineRole.BODY else f"[{ln.role}] "
        print(f"{where} | {role}{ln.markdown}")
    return 0


def _check(path: Path, out: Path | None = None, recency: str | None = None) -> int:
    if not path.is_file():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 2
    if path.suffix.lower() not in {".pdf", ".docx"}:
        print("error: only .pdf and .docx files are supported", file=sys.stderr)
        return 2
    try:
        rec = None
        if recency:
            share, _, year = recency.partition("@")
            rec = {"share": float(share) / 100, "year": int(year or date.today().year)}
        result = check_file(path, recency=rec)
    except ScannedPdfError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    output = {
        "file": path.name,
        "references": len(result.references),
        "citations": len(result.citations),
        "errors": len(result.errors),
        "needs_review": len(result.needs_review),
        "findings": [f.model_dump(mode="json", exclude_none=True) for f in result.findings],
        "corrected_list": [
            {
                "reference_id": c.reference_id,
                "status": c.status.value,
                "reference": c.markdown,
                **({"placeholders": c.placeholders} if c.placeholders else {}),
                **({"not_fixed": c.unfixed} if c.unfixed else {}),
                **({"notes": c.notes} if c.notes else {}),
            }
            for c in result.corrected_list
        ],
    }
    if out:
        from checkref.report.model import build_report
        from checkref.report.render import write_all

        paths = write_all(build_report(result, rec), out, path.stem)
        print("\n".join(str(p) for p in paths.values()), file=sys.stderr)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="checkref",
        description="Check thesis references against the AUT APA 6th guide.",
    )
    parser.add_argument("--version", action="version", version=f"checkref {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="check one thesis file and print JSON")
    check.add_argument("file", type=Path)
    check.add_argument(
        "--report", type=Path, metavar="DIR", help="also write the HTML/PDF report and DOCX here"
    )
    check.add_argument(
        "--recency",
        metavar="SHARE[@YEAR]",
        help="optional recency check, e.g. 80 or 80@2025 (university rule, not APA)",
    )
    serve = sub.add_parser("serve", help="run the web app (settings: CHECKREF_* variables)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    dump = sub.add_parser("dump", help="print the ingested lines with italics (development aid)")
    dump.add_argument("file", type=Path)

    args = parser.parse_args(argv)
    if args.command == "check":
        return _check(args.file, args.report, args.recency)
    if args.command == "dump":
        return _dump(args.file)
    if args.command == "serve":
        from checkref.web.app import serve as run_server

        run_server(args.host, args.port)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
