"""PDF and DOCX ingestion into styled spans and lines (plan phase 2)."""

from pathlib import Path

from checkref.ingest.pdf import ScannedPdfError, ingest_pdf
from checkref.ingest.word import ingest_docx
from checkref.models import Document

__all__ = ["ScannedPdfError", "UnsupportedFileError", "ingest"]


class UnsupportedFileError(ValueError):
    """Only PDF and DOCX files are accepted."""


def ingest(path: Path) -> Document:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return ingest_pdf(path)
    if suffix == ".docx":
        return ingest_docx(path)
    raise UnsupportedFileError("Only .pdf and .docx files are supported.")
