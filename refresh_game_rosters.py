#!/usr/bin/env python3
"""Refresh the gameplay rosters in data/processed/match_results.json from the archived HTML.

The point-by-point rows in the archived game pages are complete, but the rosters
stored alongside them are not: in 132 of the 795 archived games the stored roster
is smaller than the one the same HTML yields today. Game 9170 (Helsinki Ultimate
14 - Otso Polar 13) stores no away roster at all, so Simo Soini is absent from a
game in which he scored twice.

That gap costs two things downstream:

    points whose scorer is missing from the stored roster   1,848 / 18,477  (10.0%)
    players with any defense/offense attribution                  99 / 177

This re-parses data/raw/game_<id>.html and merges the roster back in. It is a
merge, not a replacement: names already stored are kept even if the fresh parse
does not list them, because for 3 of the 795 games the archived page now shows
fewer names than the scrape recorded. Measured across all 795 games the fresh
roster is a superset in 792, so the union never loses a name and never drops a
game.

Points are deliberately NOT touched. Re-parsing them would be unsafe: game 3418
stores 28 point rows from an older page while the same URL now yields 2, and
11 games store no points at all while their HTML has a full table. That is a
separate repair, not a roster refresh.

Idempotent: a second run adds 0 names.
"""

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

from ultiorg.parsers import parse_gameplay  # noqa: E402

MATCH_RESULTS = BASE_DIR / "data" / "processed" / "match_results.json"
RAW_DIR = BASE_DIR / "data" / "raw"


def canon(name: str) -> str:
    """Match names across scrapes: nbsp to space, case-insensitive, any part order."""
    parts = [p for p in name.replace("\xa0", " ").replace("(c)", "").replace("(C)", "").split() if p]
    return " ".join(sorted(p.lower() for p in parts))


def refresh() -> tuple[int, int, int]:
    with open(MATCH_RESULTS) as f:
        games = json.load(f)

    by_id = {str(g.get("game_id", "")): g for g in games}
    games_changed = names_added = 0

    for html_file in sorted(RAW_DIR.glob("game_*.html")):
        game_id = re.search(r"game_(\d+)\.html$", html_file.name)
        if not game_id:
            continue
        game = by_id.get(game_id.group(1))
        if not game:
            continue
        gameplay = game.get("gameplay")
        if not gameplay:
            continue

        fresh = parse_gameplay(html_file.read_text(encoding="utf-8", errors="replace"))

        changed = False
        for side, fresh_key in (("home_players", "home_players"), ("away_players", "away_players")):
            stored = gameplay.get(side) or []
            seen = {canon(p.get("name", "")) for p in stored if p.get("name")}
            for player in fresh.get(fresh_key) or []:
                name = player.get("name", "")
                key = canon(name)
                if not key or key in seen:
                    continue
                seen.add(key)
                stored.append(player)
                names_added += 1
                changed = True
            gameplay[side] = stored

        if changed:
            games_changed += 1

    games_without_roster = sum(
        1 for game in games
        if (game.get("gameplay") or {}).get("points")
        and not ((game["gameplay"].get("home_players") or []) or (game["gameplay"].get("away_players") or []))
    )

    with open(MATCH_RESULTS, "w") as f:
        json.dump(games, f, ensure_ascii=False, indent=2)

    return games_changed, names_added, games_without_roster


if __name__ == "__main__":
    games_changed, names_added, games_without_roster = refresh()
    print(f"games changed: {games_changed} | roster names added: {names_added} | games with points but no roster: {games_without_roster}")
