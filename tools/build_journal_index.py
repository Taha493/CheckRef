"""Build data/journals/nlm_abbreviations.tsv from the NLM journal catalogue (plan phase 7).

Source: https://ftp.ncbi.nlm.nih.gov/pubmed/J_Entrez.txt (NLM, public domain). Each line of
the output is `abbreviation key <TAB> full title`, for the MEDLINE and ISO abbreviations of
every journal. The key is the abbreviation without full stops, lowercase. Run:

    uv run python tools/build_journal_index.py [J_Entrez.txt]
"""

from __future__ import annotations

import sys
import urllib.request
from datetime import date
from pathlib import Path

URL = "https://ftp.ncbi.nlm.nih.gov/pubmed/J_Entrez.txt"
OUT = Path(__file__).resolve().parents[1] / "data" / "journals" / "nlm_abbreviations.tsv"


def records(text: str):
    for block in text.split("-" * 56):
        rec = {}
        for line in block.strip().splitlines():
            key, _, value = line.partition(": ")
            rec[key] = value.strip()
        if rec.get("JournalTitle"):
            yield rec


def main() -> None:
    if len(sys.argv) > 1:
        text = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(URL, timeout=600) as resp:
            text = resp.read().decode("utf-8")
    from checkref.correct.journals import abbreviation_key, catalogue_name

    rows = set()
    for rec in records(text):
        title = catalogue_name(rec["JournalTitle"])
        for field in ("MedAbbr", "IsoAbbr"):
            key = abbreviation_key(rec.get(field, ""))
            if key and key != abbreviation_key(title):
                rows.add((key, title))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    header = f"# NLM journal abbreviations, from {URL} on {date.today().isoformat()}\n"
    OUT.write_text(header + "".join(f"{k}\t{t}\n" for k, t in sorted(rows)), encoding="utf-8")
    print(f"{len(rows)} abbreviations -> {OUT}")


if __name__ == "__main__":
    main()
