#!/usr/bin/env python3
"""Turn the players PDF into a private birthdays CSV.

The source PDF is a top-scorers export that happens to carry a Birthday column.
It is personal data: it sits in data/raw/ and its output goes to
data/private/, both gitignored. Nothing per-person ever reaches site_data/ or
index.html — build_site_data.py reads the CSV only to compute the mean age of a
year's roster.

Requires poppler's pdftotext.
"""
import csv
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_PDF = ROOT / "data" / "raw" / "players (1).pdf"
OUT = ROOT / "data" / "private" / "birthdays.csv"

DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
# The "Years" column, e.g. 2007-2026 — the first token that is not part of a name.
YEARS_RE = re.compile(r"^\d{4}(-\d{4})?$")


def assert_ignored(path: Path) -> None:
    """Refuse to write personal data somewhere git can see."""
    rc = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=ROOT).returncode
    if rc != 0:
        sys.exit(f"{path} is not gitignored — refusing to write personal data there.")


def parse(text: str) -> list[tuple[str, date]]:
    rows, seen = [], set()
    for line in text.splitlines():
        toks = line.split()
        # pdftotext keeps a row on one line but does not guarantee two spaces
        # between columns, so the name ends where the Years column begins.
        at = next((k for k, t in enumerate(toks) if YEARS_RE.match(t)), None)
        if not at:
            continue
        name = " ".join(toks[:at])
        found = DATE_RE.findall(" ".join(toks[at:]))  # birthday is a column, never in the name
        if not name or not found:
            continue
        day, month, year = (int(x) for x in found[-1])
        try:
            bday = date(year, month, day)
        except ValueError:
            continue
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        rows.append((name, bday))
    return rows


def main() -> None:
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    if not pdf.exists():
        sys.exit(f"no PDF at {pdf}")
    assert_ignored(OUT)

    text = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"], check=True, capture_output=True, text=True
    ).stdout
    rows = parse(text)
    if not rows:
        sys.exit("parsed no birthdays — is the Birthday column present?")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["name", "birthday"])
        for name, bday in sorted(rows):
            writer.writerow([name, bday.isoformat()])

    print(f"{pdf.name}: {len(rows)} birthdays -> {OUT.relative_to(ROOT)} (gitignored)")


if __name__ == "__main__":
    main()
