"""Render a Report: HTML (screen), PDF (WeasyPrint, from the same HTML) and the corrected
reference list as DOCX (spec §5 ⑪)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from docx import Document as WordDocument
from docx.enum.text import WD_COLOR_INDEX, WD_LINE_SPACING
from docx.shared import Inches, Pt
from jinja2 import Environment, FileSystemLoader, select_autoescape

from checkref.report.model import Report

TEMPLATES = Path(__file__).parent / "templates"
FONTS = Path(__file__).parent / "fonts"  # bundled, so neither view loads anything from elsewhere
FONTS_URL = "/fonts/"  # where the web app serves FONTS
_env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def to_html(report: Report, links: dict[str, str] | None = None, printing: bool = False) -> str:
    """`links` (web view only): URLs for "pdf" and "delete", a "note" shown beside them and the
    site "credits" for the footer. The PDF is always rendered without them. `printing` opens
    every collapsible section. The web view loads the fonts from the app; the PDF and a saved
    file load them from disk."""
    fonts = FONTS_URL if links else FONTS.as_uri() + "/"
    return _env.get_template("report.html.j2").render(
        r=report, links=links, printing=printing, fonts=fonts
    )


def to_pdf(report: Report) -> bytes:
    from weasyprint import HTML  # imported here: it loads system libraries (Pango)

    return HTML(string=to_html(report, printing=True)).write_pdf()


def to_docx(report: Report) -> bytes:
    """The corrected reference list: "References" heading, Times New Roman 12 pt, 0.5-inch
    hanging indent, double spacing, italics; placeholders highlighted for the student."""
    doc = WordDocument()
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    heading = doc.add_paragraph()
    heading.alignment = 1  # centred, as in APA 6
    heading.paragraph_format.line_spacing_rule = WD_LINE_SPACING.DOUBLE
    heading.add_run("References")
    for entry in report.corrected_list:
        p = doc.add_paragraph()
        fmt = p.paragraph_format
        fmt.left_indent = Inches(0.5)
        fmt.first_line_indent = Inches(-0.5)
        fmt.line_spacing_rule = WD_LINE_SPACING.DOUBLE
        fmt.space_after = Pt(0)
        for run in entry:
            r = p.add_run(run.text)
            r.italic = run.italic or None
            if run.placeholder:
                r.font.highlight_color = WD_COLOR_INDEX.YELLOW
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def write_all(report: Report, directory: Path, stem: str = "checkref") -> dict[str, Path]:
    """Write report.html, report.pdf and the corrected list .docx; returns their paths."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "html": directory / f"{stem}-report.html",
        "pdf": directory / f"{stem}-report.pdf",
        "docx": directory / f"{stem}-corrected-references.docx",
    }
    paths["html"].write_text(to_html(report), encoding="utf-8")
    paths["pdf"].write_bytes(to_pdf(report))
    paths["docx"].write_bytes(to_docx(report))
    return paths
