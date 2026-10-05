#!/usr/bin/env python3
"""Drop the duplicated point-by-point rows in data/processed/match_results.json.

The pelikone gameplay page renders its point-by-point table twice: one copy in
div.page_middle (a site-wide results strip) and one in div.content (the game's
own table). The scraper walked every <tr> in the document and appended both
copies, so each goal was stored twice — twice the goals, twice the assists, and
a pass_network.json that read 2x of reality.

Measured on the committed dataset before this migration:

    point rows stored   29,270
    unique point rows   18,477
    phantom rows        10,793   (36.9%)
    games exactly 2x    467 / 788
    games clean (1x)    321 / 788
    games mixed         0

The clean 321 are the games scraped before the page grew the second table and
before the score string changed from "0 - 1" to "0-1"; re-parsing the archived
HTML for any of them today yields the doubled version. So the split is a scrape
vintage, not a property of the game — which is why the fix is a flat dedupe
rather than a per-game factor.

A goal cannot repeat: the score in each row is the cumulative score at that
moment, so (side, time, score, title) identifies a real goal uniquely. Halftime
markers are keyed by their text. The migration is idempotent — a second run
removes 0 rows.

The parser no longer produces the duplicates (see parse_gameplay in
src/ultiorg/parsers.py); this repairs the data already on disk.
"""

import json
from pathlib import Path

MATCH_RESULTS = Path(__file__).resolve().parent / "data" / "processed" / "match_results.json"


def row_key(point: dict) -> tuple:
    """Identity of a point-by-point row: one real goal, or one halftime marker."""
    if point.get("type") == "halftime":
        return ("halftime", point.get("text", ""))
    return (
        point.get("type", ""),
        point.get("side", ""),
        point.get("time", ""),
        point.get("score", ""),
        point.get("title", ""),
    )


def dedupe() -> tuple[int, int, int]:
    with open(MATCH_RESULTS) as f:
        games = json.load(f)

    removed = kept = games_affected = 0
    for game in games:
        points = (game.get("gameplay") or {}).get("points")
        if not points:
            continue
        seen = set()
        unique = []
        for point in points:
            key = row_key(point)
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            unique.append(point)
        if len(unique) != len(points):
            games_affected += 1
            game["gameplay"]["points"] = unique
        kept += len(unique)

    with open(MATCH_RESULTS, "w") as f:
        json.dump(games, f, ensure_ascii=False, indent=2)

    return removed, kept, games_affected


if __name__ == "__main__":
    removed, kept, games_affected = dedupe()
    print(f"rows removed: {removed} | rows kept: {kept} | games changed: {games_affected}")
