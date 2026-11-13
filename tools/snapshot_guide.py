"""Freeze a snapshot of the AUT APA 6th guide (spec §4.2, plan phase 1).

Writes, under data/guide/:
  html/<slug>.html         raw page as downloaded
  md/<slug>.md             each content box as Markdown, italics kept as *...*
  md/brief-guide-pdf.md    the PDF guide's table, italics kept
  manifest.json            url, title, sha256 of the extracted Markdown per page

Usage:  uv run python tools/snapshot_guide.py [--skip-web] [--skip-pdf]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import pdfplumber
from bs4 import BeautifulSoup
from markdownify import markdownify

ROOT = Path(__file__).resolve().parents[1]
GUIDE_DIR = ROOT / "data" / "guide"
PDF_PATH = GUIDE_DIR / "APA_6th_brief_guide_March_2019v2.pdf"
START_URL = "https://aut.ac.nz.libguides.com/APA6th"
GUIDE_ID = "613888"  # LibGuides id of the APA6th guide; some pages use c.php?g=<id>&p=<page>
USER_AGENT = "Mozilla/5.0 (CiteSure guide snapshot)"


# --------------------------------------------------------------------------- web


def _in_guide(url: str) -> bool:
    u = urlparse(url)
    if u.netloc != "aut.ac.nz.libguides.com":
        return False
    if u.path.rstrip("/").lower().startswith("/apa6th"):
        return True
    return u.path == "/c.php" and f"g={GUIDE_ID}" in u.query


def _canonical(url: str) -> str:
    u = urlparse(url)
    path = u.path.rstrip("/") or "/"
    return f"https://{u.netloc}{path}" + (f"?{u.query}" if u.query else "")


def _slug(url: str) -> str:
    u = urlparse(url)
    if u.path == "/c.php":
        m = re.search(r"p=(\d+)", u.query)
        return f"page-{m.group(1)}" if m else "page"
    parts = [p for p in u.path.split("/") if p]
    return "index" if len(parts) <= 1 else "-".join(parts[1:]).lower()


def _page_title(soup: BeautifulSoup) -> str:
    t = soup.title.get_text(" ", strip=True) if soup.title else ""
    return t.split(" - ")[0].strip()


def _boxes_markdown(soup: BeautifulSoup) -> str:
    """Convert every content box in the main column to Markdown."""
    out: list[str] = []
    for box in soup.select("#s-lg-guide-main div.s-lib-box"):
        title_el = box.select_one(".s-lib-box-title")
        content_el = box.select_one(".s-lib-box-content")
        if content_el is None:
            continue
        for bad in content_el.select("script, style, img, iframe"):
            bad.decompose()
        title = title_el.get_text(" ", strip=True) if title_el else ""
        body = markdownify(str(content_el), heading_style="ATX", bullets="-").strip()
        body = re.sub(r"\n{3,}", "\n\n", body)
        if not body:
            continue
        out.append(f"## {title}\n\n{body}" if title else body)
    return "\n\n".join(out) + "\n"


def snapshot_web(client: httpx.Client) -> list[dict]:
    html_dir, md_dir = GUIDE_DIR / "html", GUIDE_DIR / "md"
    html_dir.mkdir(parents=True, exist_ok=True)
    md_dir.mkdir(parents=True, exist_ok=True)

    queue, seen, pages = [START_URL], set(), []
    seen_bodies: dict[str, str] = {}  # content hash -> slug, to skip the same page under two URLs
    while queue:
        url = _canonical(queue.pop(0))
        if url in seen:
            continue
        seen.add(url)
        resp = client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        slug = _slug(url)
        for a in soup.select("a[href]"):
            link = urljoin(url, a["href"]).split("#")[0]
            if _in_guide(link) and _canonical(link) not in seen:
                queue.append(link)

        title = _page_title(soup)
        body = _boxes_markdown(soup)
        body_hash = hashlib.sha256(body.encode()).hexdigest()
        if body_hash in seen_bodies:
            print(f"  {slug:28} (same content as {seen_bodies[body_hash]}, skipped)")
            continue
        seen_bodies[body_hash] = slug

        (html_dir / f"{slug}.html").write_text(resp.text, encoding="utf-8")
        md = f"# {title}\n\nSource: {url}\n\n" + body
        (md_dir / f"{slug}.md").write_text(md, encoding="utf-8")
        pages.append(
            {
                "url": url,
                "slug": slug,
                "title": title,
                "sha256": hashlib.sha256(md.encode()).hexdigest(),
            }
        )
        print(f"  {slug:28} {title}")
        time.sleep(0.5)
    return pages


# --------------------------------------------------------------------------- pdf

COLUMNS = [
    ("Item", 0, 158),
    ("Reference list entry", 158, 392),
    ("In-text citation", 392, 556),
    ("Note", 556, 10_000),
]
FOOTER_TOP = 545  # the running footer "Referencing with APA – Brief Guide … Updated March 2019"


def _style(word: dict) -> tuple[bool, bool]:
    font = word["fontname"].split("+")[-1].lower()
    return ("italic" in font or "oblique" in font), ("bold" in font)


def _render_line(words: list[dict]) -> str:
    """Join words on one line, wrapping italic/bold runs in Markdown markers."""
    parts: list[str] = []
    state = (False, False)
    prev_x1 = None
    for w in words:
        italic, bold = _style(w)
        # Real word gaps in this PDF are >= 1.2 pt; splits caused by a font change are ~0 pt.
        space = " " if prev_x1 is not None and w["x0"] - prev_x1 > 0.6 else ""
        if (italic, bold) != state:
            close = ("*" if state[0] else "") + ("**" if state[1] else "")
            parts.append(close[::-1])
            parts.append(space)
            parts.append(("**" if bold else "") + ("*" if italic else ""))
            state = (italic, bold)
        else:
            parts.append(space)
        parts.append(w["text"])
        prev_x1 = w["x1"]
    parts.append((("*" if state[0] else "") + ("**" if state[1] else ""))[::-1])
    return "".join(parts)


def _join_lines(lines: list[str]) -> str:
    text = ""
    for line in lines:
        if not text:
            text = line
            continue
        last = text.split(" ")[-1]
        url_break = "://" in last or last.startswith("www.")
        # A line ending in a hyphen or en dash (ignoring closing style markers) continues
        # the same token on the next line, e.g. "21–" + "27", "2007-" + "2008".
        dash_break = re.search(r"\S[-–]\**$", text) is not None
        glue = "" if dash_break or url_break else " "
        if not glue and re.search(r"(?<!\*)\*$", text) and re.match(r"\*(?!\*)", line):
            text, line = text[:-1], line[1:]  # italic run continues across the line break
        text += glue + line
    return text.replace("** **", " ").replace("* *", " ")


def _cell_text(words: list[dict]) -> str:
    words = sorted(words, key=lambda w: (round(w["top"]), w["x0"]))
    lines: list[list[dict]] = []
    for w in words:
        if lines and abs(lines[-1][0]["top"] - w["top"]) < 2:
            lines[-1].append(w)
        else:
            lines.append([w])
    return _join_lines([_render_line(sorted(ln, key=lambda w: w["x0"])) for ln in lines])


def snapshot_pdf() -> str:
    rows: list[list[str]] = []
    with pdfplumber.open(PDF_PATH) as pdf:
        for page in pdf.pages:
            words = [
                w
                for w in page.extract_words(extra_attrs=["fontname"], keep_blank_chars=False)
                if w["top"] < FOOTER_TOP
            ]
            if page.page_number == 1:
                # Skip the title block above the table's header row ("Item | Reference ...").
                header_top = min(w["top"] for w in words if w["text"] == "Item")
                words = [w for w in words if w["top"] >= header_top - 2]
            item_tops = sorted({round(w["top"]) for w in words if w["x0"] < COLUMNS[0][2]})
            starts = [t for i, t in enumerate(item_tops) if i == 0 or t - item_tops[i - 1] > 18]
            bounds = starts + [FOOTER_TOP]
            for top, bottom in zip(bounds, bounds[1:], strict=False):
                band = [w for w in words if top - 2 <= w["top"] < bottom - 2]
                cells = [
                    _cell_text([w for w in band if lo <= w["x0"] < hi]) for _, lo, hi in COLUMNS
                ]
                if cells[0].strip("* ") == "Item":
                    continue  # header row
                rows.append(cells)

    def esc(s: str) -> str:
        return s.replace("|", "\\|")

    out = [
        "# Referencing with APA 6th – Brief Guide (PDF, March 2019)",
        "",
        f"Source: data/guide/{PDF_PATH.name}",
        "",
        "Italics from the PDF are kept as `*...*`; bold as `**...**`.",
        "",
        "| " + " | ".join(c for c, _, _ in COLUMNS) + " |",
        "|" + "---|" * len(COLUMNS),
    ]
    out += ["| " + " | ".join(esc(c) for c in row) + " |" for row in rows]
    md = "\n".join(out) + "\n"
    (GUIDE_DIR / "md").mkdir(parents=True, exist_ok=True)
    (GUIDE_DIR / "md" / "brief-guide-pdf.md").write_text(md, encoding="utf-8")
    print(f"  brief-guide-pdf: {len(rows)} rows")
    return md


# --------------------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-web", action="store_true")
    ap.add_argument("--skip-pdf", action="store_true")
    args = ap.parse_args()

    manifest_path = GUIDE_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    if not args.skip_pdf:
        print("PDF guide:")
        md = snapshot_pdf()
        manifest["pdf"] = {
            "file": PDF_PATH.name,
            "sha256_file": hashlib.sha256(PDF_PATH.read_bytes()).hexdigest(),
            "sha256_md": hashlib.sha256(md.encode()).hexdigest(),
        }
    if not args.skip_web:
        print("Website:")
        headers = {"User-Agent": USER_AGENT}
        with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as client:
            manifest["pages"] = snapshot_web(client)
        manifest["snapshot_date"] = datetime.now(UTC).strftime("%Y-%m-%d")
        manifest["start_url"] = START_URL

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"Manifest: {manifest_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
