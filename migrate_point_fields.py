#!/usr/bin/env python3
"""Rename the mislabelled point-by-point name fields in data/processed/match_results.json.

The pelikone gameplay points table has these columns:

    Pisteet | Syöttäjä | Maali | Aika | Kesto | Pelitapahtumat
     score  |  passer  |  goal | time

The scrapers read cells[1] and cells[2] and stored them as "scorer" and
"assist" — but cells[1] (Syöttäjä) is the PASSER and cells[2] (Maali) is the
GOAL SCORER. So in every committed point object the two names sit under the
wrong key. This renames them honestly, in place:

    old "scorer"  ->  "passer"    (cells[1], Syöttäjä)
    old "assist"  ->  "scorer"    (cells[2], Maali)

The "title" field keeps the source order ("passer -> scorer") and is not
touched. The migration is idempotent: a point that already carries "passer"
is left alone, so it is safe to re-run.

Evidence for the mapping, beyond the column headers above: against the season
card totals in players.json (a separate scrape), restricted to Otso games and
Otso players, the field stored as "scorer" correlates 0.974 with career
assists and 0.819 with career goals; the field stored as "assist" correlates
0.940 with goals and 0.839 with assists. Sign(field1 - field2) matches
sign(goals - assists) for 8 of 108 players and is inverted for 100.
"""

import json
from pathlib import Path

MATCH_RESULTS = Path(__file__).resolve().parent / "data" / "processed" / "match_results.json"


def migrate() -> tuple[int, int, int]:
    with open(MATCH_RESULTS) as f:
        games = json.load(f)

    migrated = skipped = no_points = 0
    for game in games:
        points = (game.get("gameplay") or {}).get("points") or []
        if not points:
            no_points += 1
            continue
        for point in points:
            if "passer" in point:
                skipped += 1
                continue
            if "scorer" not in point and "assist" not in point:
                skipped += 1
                continue
            passer = point.pop("scorer", "")
            scorer = point.pop("assist", "")
            point["passer"] = passer
            point["scorer"] = scorer
            migrated += 1

    with open(MATCH_RESULTS, "w") as f:
        json.dump(games, f, ensure_ascii=False, indent=2)

    return migrated, skipped, no_points


if __name__ == "__main__":
    migrated, skipped, no_points = migrate()
    print(f"points renamed: {migrated} | already migrated or empty: {skipped} | games without points: {no_points}")
