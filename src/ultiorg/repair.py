"""Repairs for data already on disk, as commands rather than scripts.

Each of these fixed a real defect in the committed corpus and is **idempotent** —
running it twice changes nothing the second time. They exist because the corpus is
committed: a fix to the parser does not retroactively fix the JSON that was written
by the broken parser, and a fresh clone starts from that JSON.

| command | defect it repairs |
|---|---|
| `point-fields` | cells[1] (Syöttäjä, the passer) and cells[2] (Maali, the scorer) were stored under swapped keys |
| `dedupe-points` | the point table is rendered twice per page, so 10,793 of 29,270 stored rows were phantoms |
| `rosters` | 132 of 795 games stored a roster smaller than the same HTML yields today |

`ultiorg merge` re-parses gameplay from the archived HTML, which supersedes all
three for any game whose HTML is archived. The repairs remain for the games whose
HTML is not: their stored rows are the only record, and they were written wrong.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from .names import canon
from .parsers import parse_gameplay


@dataclass
class RepairReport:
    name: str
    changed: int
    unchanged: int
    notes: Dict[str, int]

    def summary(self) -> str:
        extra = " ".join(f"{k}={v}" for k, v in self.notes.items())
        return f"{self.name}: {self.changed} changed, {self.unchanged} unchanged" + (f" | {extra}" if extra else "")


def _load(path: Path) -> List[Dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, games: List[Dict]) -> None:
    path.write_text(json.dumps(games, ensure_ascii=False, indent=2), encoding="utf-8")


def _points(games: List[Dict]):
    for game in games:
        points = (game.get("gameplay") or {}).get("points")
        if points is not None:
            yield game, points


# --- point-fields -----------------------------------------------------------

def migrate_point_fields(path: Path) -> RepairReport:
    """Swap the mislabelled name fields on stored point rows.

    The pelikone points table is `Pisteet | Syöttäjä | Maali | Aika | Kesto |
    Pelitapahtumat` — score, **passer**, **goal**, time, duration, events. The old
    scrapers read cells[1] and cells[2] and stored them as `scorer` and `assist`,
    so in every point object written before the fix the two names sat under the
    wrong key. This renames them in place:

        old "scorer" -> "passer"   (cells[1], Syöttäjä)
        old "assist" -> "scorer"   (cells[2], Maali)

    Evidence beyond the headers: against the season-card totals in `players.json`
    (a separate scrape), restricted to Otso games and Otso players, the field
    stored as `scorer` correlates 0.974 with career assists and 0.819 with career
    goals; the field stored as `assist` correlates 0.940 with goals and 0.839 with
    assists. `sign(field1 - field2)` matches `sign(goals - assists)` for 8 of 108
    players and is inverted for 100.

    Idempotent, and the guard matters: the marker of the old shape is the presence
    of an `assist` key, because the pre-fix scraper wrote **both** `scorer` and
    `assist` on every row. Keying on a *missing* `passer` instead would corrupt
    real data — measured on the current corpus, 81 points legitimately carry a
    scorer with no passer and 33 a passer with no scorer (the page leaves one cell
    blank), and 0 points carry `assist`. A missing key is not the same as an
    un-migrated row.
    """
    games = _load(path)
    migrated = skipped = hybrid = games_without_points = 0
    for game, points in _points(games):
        if not points:
            games_without_points += 1
            continue
        for point in points:
            if "assist" not in point:
                skipped += 1
                continue
            if "passer" in point:  # a shape neither scraper wrote — do not guess
                hybrid += 1
                continue
            point["passer"] = point.pop("scorer", "")
            point["scorer"] = point.pop("assist", "")
            migrated += 1
    _save(path, games)
    return RepairReport(
        "point-fields", migrated, skipped,
        {"games without points": games_without_points, "hybrid rows left alone": hybrid},
    )


# --- dedupe-points ----------------------------------------------------------

def _row_key(point: Dict) -> Tuple:
    """Identity of a point-by-point row: one real goal, or one halftime marker."""
    if point.get("type") == "halftime":
        return ("halftime", point.get("text", ""))
    return (
        point.get("type", ""),
        point.get("side", ""),
        point.get("time", ""),
        point.get("score", ""),
        point.get("scorer", ""),
        point.get("passer", ""),
    )


def dedupe_point_rows(path: Path) -> RepairReport:
    """Drop the duplicated point rows that the doubled page produced.

    The gameplay page renders its point table twice: one copy in `div.page_middle`
    (a site-wide results strip) and one in `div.content` (the game's own table). The
    old scraper walked every `<tr>` in the document and stored both, so each goal
    was kept twice — twice the goals, twice the assists, and a `pass_network.json`
    that read 2x of reality.

    Measured on the committed dataset before the repair:

        point rows stored   29,270
        unique point rows   18,477
        phantom rows        10,793   (36.9%)
        games exactly 2x    467 / 788
        games clean (1x)    321 / 788
        games mixed         0

    The clean 321 are games scraped before the page grew the second table and
    before the score string changed from `"0 - 1"` to `"0-1"`; re-parsing their
    archived HTML today yields the doubled version. So the split is a scrape
    vintage, not a property of the game — which is why the repair is a flat dedupe
    rather than a per-game factor.

    A goal cannot repeat: the score in each row is the cumulative score at that
    moment, so (side, time, score, scorer, passer) identifies a real goal uniquely.
    Halftime markers are keyed by their text. Idempotent: a second run removes 0.
    """
    games = _load(path)
    removed = kept = games_changed = 0
    for game, points in _points(games):
        seen = set()
        unique = []
        for point in points:
            key = _row_key(point)
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            unique.append(point)
        if len(unique) != len(points):
            games_changed += 1
            game["gameplay"]["points"] = unique
        kept += len(unique)
    _save(path, games)
    return RepairReport("dedupe-points", games_changed, len(games) - games_changed,
                        {"rows removed": removed, "rows kept": kept})


# --- rosters ----------------------------------------------------------------

def refresh_rosters(path: Path, raw_dir: Path) -> RepairReport:
    """Merge the rosters the archived HTML knows about back into the corpus.

    The stored point-by-point rows are complete, but the rosters stored next to
    them are not: in 132 of the 795 archived games the stored roster is smaller
    than the one the same HTML yields today. Game 9170 (Helsinki Ultimate 14 -
    Otso Polar 13) stores no away roster at all, so Simo Soini is absent from a
    game in which he scored twice. That costs two things downstream:

        points whose scorer is missing from the stored roster   1,848 / 18,477 (10.0%)
        players with any defense/offense attribution                99 / 177

    This is a **merge, not a replacement**: names already stored are kept even if a
    fresh parse does not list them, because for 3 of the 795 games the archived page
    now shows fewer names than the scrape recorded. Measured across all 795 games the
    fresh roster is a superset in 792, so the union never loses a name and never
    drops a game.

    Points are deliberately not touched: game 3418 stores 28 point rows from an
    older page while the same URL now yields 2, and 11 games store no points while
    their HTML has a full table. That is a different repair. Idempotent.
    """
    games = _load(path)
    by_id = {str(g.get("game_id", "")): g for g in games}
    games_changed = names_added = 0

    for html_file in sorted(raw_dir.glob("game_*.html")):
        match = re.search(r"game_(\d+)\.html$", html_file.name)
        if not match:
            continue
        game = by_id.get(match.group(1))
        if not game or not game.get("gameplay"):
            continue
        fresh = parse_gameplay(html_file.read_text(encoding="utf-8", errors="replace"))
        changed = False
        for side in ("home_players", "away_players"):
            stored = game["gameplay"].get(side) or []
            seen = {canon(p.get("name", "")) for p in stored if p.get("name")}
            for player in fresh.get(side) or []:
                key = canon(player.get("name", ""))
                if not key or key in seen:
                    continue
                seen.add(key)
                stored.append(player)
                names_added += 1
                changed = True
            game["gameplay"][side] = stored
        if changed:
            games_changed += 1

    without_roster = sum(
        1 for game in games
        if (game.get("gameplay") or {}).get("points")
        and not ((game["gameplay"].get("home_players") or []) or (game["gameplay"].get("away_players") or []))
    )
    _save(path, games)
    return RepairReport("rosters", games_changed, len(games) - games_changed,
                        {"names added": names_added, "games with points but no roster": without_roster})
