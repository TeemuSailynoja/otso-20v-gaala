"""Season identity: which year, which half of the year, which stage.

pelikone season IDs are not one format. The corpus holds `2018.1`, `2018.T2`,
`2018.F`, `2017F`, `KESA2026`, `Talvi2016`, `Hallitour2`, `SM2022K`, `XSM2018`,
`BMSM2` and `*JSM2018` (the leading asterisk is real). Two questions get asked
of them, and they need different answers:

- **year** — four digits, in the ID if it has them, otherwise in the season name.
  `2017F` has the year in the ID; `BMSM2` only in its name ("Ranta SM 2019").
- **season_type** — summer or winter (or beach). The numeric suffix does *not*
  encode it: `2018.1` is the *winter* season while `2020.1` is the *summer* one.
  The season name does, every time — "Kesä" summer, "Talvi" winter, "Ranta" beach.

The old site builder classified from the ID and gave up on the numeric forms
(`classify_season("2018.1", "Kesä 2018")` → "unknown"), then carried its own
override table. Name-first classification reproduces that table exactly: 102 of
102 entries in `site_data/season_mapping.json`, measured.

`stage` is a separate axis and stays separate: `2019.T3` is a tour stop *of* the
2019 summer season, not a different kind of season.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Optional

# Four digits, no word boundary: `KESA2026` has the year glued to the letters.
_YEAR_RE = re.compile(r"(\d{4})")

# Folded so "Kesä" and "Kesa" both read as summer.
_SEASON_WORDS = (
    ("kesa", "summer"),
    ("talvi", "winter"),
    ("ranta", "beach"),
)

SUMMER, WINTER, BEACH, OTHER = "summer", "winter", "beach", "other"


def fold(text: str) -> str:
    """Lowercase with accents stripped, for matching Finnish season words."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def season_year(season_id: str, season_name: str = "") -> Optional[int]:
    """The year a season ID belongs to, from the ID first and the name second.

    Any four-digit year counts, not only 20xx: `1999.2` is a real (pre-Otso)
    season id. Returns None when neither carries one — `Hallitour2`, `BMSM2`.
    """
    for text in (season_id or "", season_name or ""):
        match = _YEAR_RE.search(text)
        if match:
            return int(match.group(1))
    return None


def season_type(season_id: str, season_name: str = "") -> str:
    """`summer` | `winter` | `beach` | `other`.

    Name-first, because the ID's numeric suffix lies: `2018.1` is winter and
    `2020.1` is summer. When no name is available the ID's own words
    (`KESA2026`, `Talvi2016`, `BEACH2021`) decide; anything else is `other`
    rather than a guess.
    """
    folded = fold(season_name)
    for word, kind in _SEASON_WORDS:
        if word in folded:
            return kind
    folded_id = fold(season_id)
    if folded_id.startswith("kesa"):
        return SUMMER
    if "talvi" in folded_id:
        return WINTER
    if folded_id.startswith("beach") or "ranta" in folded_id:
        return BEACH
    return OTHER


def season_stage(season_id: str) -> str:
    """Where a season ID sits inside its season: tour stop, finale, or the season itself."""
    sid = season_id or ""
    if sid.startswith("KESA"):
        return "season"
    if "T1" in sid:
        return "tour1"
    if "T2" in sid:
        return "tour2"
    if "T3" in sid:
        return "tour3"
    if "T4" in sid:
        return "tour4"
    if "Finaa" in sid or sid.endswith("F"):
        return "finals"
    if "Talvi" in sid:
        return "season"
    if "BEACH" in sid:
        return "beach"
    if "SM" in sid:
        return "championship"
    return "unknown"


def classify(season_id: str, season_name: str = "") -> Dict:
    """Year, season type and stage for one season ID, in one record."""
    return {
        "year": season_year(season_id, season_name),
        "season_type": season_type(season_id, season_name),
        "stage": season_stage(season_id),
        "id": season_id,
        "name": season_name,
    }
