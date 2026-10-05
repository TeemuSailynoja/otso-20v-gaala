"""SQLite fact store: the layer that makes questions composable.

The per-URL HTML cache exists to avoid re-fetching. This exists to make the
coaching staff's questions answerable without writing a new scraper each time:
"who are X's strongest connections", "who scores most off defense-initiated
points", "which pair was on the field for every Otso goal in 2019". Those are
joins, not endpoints.

Rebuildable by design — `data/store.sqlite` is gitignored and derived. If it is
wrong, delete it and rebuild from the cache.

Keys: `points.scorer_key` / `passer_key` hold a pelikone player ID when the
point-row name resolved to one, otherwise a `name:<canon>` pseudo-key, so no
point silently disappears. `possession_team` names the team that started the
point on defense, which is what makes defense-initiated scoring a `WHERE`
clause instead of a bespoke script.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .identify import PlayerIndex, canon
from .aliases import PersonKeys
from .seasons import season_type, season_year

SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    player_id     TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL DEFAULT '',
    name_key      TEXT NOT NULL DEFAULT '',
    person_key    TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL DEFAULT ''
);

-- pelikone game pages carry team NAMES, not IDs; pelikone_id is filled in when
-- an allteams/teamcard page supplies it (Phase 6).
CREATE TABLE IF NOT EXISTS teams (
    team_key    TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    pelikone_id TEXT,
    club        TEXT,
    division    TEXT,
    country     TEXT
);

CREATE TABLE IF NOT EXISTS seasons (
    season_id TEXT PRIMARY KEY,
    year      INTEGER,
    type      TEXT,
    name      TEXT,
    division  TEXT
);

CREATE TABLE IF NOT EXISTS games (
    game_id         TEXT PRIMARY KEY,
    season_id       TEXT,
    home_team       TEXT,
    away_team       TEXT,
    home_score      INTEGER,
    away_score      INTEGER,
    venue           TEXT,
    start_time      TEXT,
    points_expected INTEGER,
    points_parsed   INTEGER,
    points_complete INTEGER
);

CREATE TABLE IF NOT EXISTS appearances (
    game_id   TEXT NOT NULL,
    player_id TEXT NOT NULL,
    team      TEXT,
    side      TEXT,
    goals     INTEGER,
    assists   INTEGER,
    total     INTEGER,
    PRIMARY KEY (game_id, player_id)
);

CREATE TABLE IF NOT EXISTS points (
    game_id          TEXT NOT NULL,
    seq              INTEGER NOT NULL,
    clock            TEXT,
    score            TEXT,
    scoring_side     TEXT,
    scoring_team     TEXT,
    possession       TEXT,
    possession_team  TEXT,
    possession_known INTEGER NOT NULL DEFAULT 0,
    scorer_key       TEXT,
    scorer_name      TEXT,
    scorer_person    TEXT,
    scorer_team      TEXT,
    passer_key       TEXT,
    passer_name      TEXT,
    passer_person    TEXT,
    PRIMARY KEY (game_id, seq)
);

CREATE TABLE IF NOT EXISTS placements (
    season_id TEXT NOT NULL,
    team      TEXT NOT NULL,
    division  TEXT,
    placement INTEGER,
    PRIMARY KEY (season_id, team)
);

CREATE INDEX IF NOT EXISTS points_scorer_idx ON points(scorer_key);
CREATE INDEX IF NOT EXISTS points_scorer_person_idx ON points(scorer_person);
CREATE INDEX IF NOT EXISTS points_passer_idx ON points(passer_key);
CREATE INDEX IF NOT EXISTS points_game_idx   ON points(game_id);
CREATE INDEX IF NOT EXISTS appearances_player_idx ON appearances(player_id);
"""


@dataclass
class StoreStats:
    players: int = 0
    persons: int = 0
    teams: int = 0
    seasons: int = 0
    games: int = 0
    appearances: int = 0
    points: int = 0
    points_with_possession: int = 0
    points_pseudo_keyed: int = 0
    placements: int = 0


def open_store(path: Path) -> sqlite3.Connection:
    """Open the store, rebuilding the schema when its version changes.

    The store is derived data: on a schema change it is dropped and rebuilt from
    the cache rather than migrated. `data/store.sqlite` is gitignored precisely
    so that this is always safe.
    """
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version and version != SCHEMA_VERSION:
        conn.executescript(
            """
            DROP TABLE IF EXISTS points;
            DROP TABLE IF EXISTS appearances;
            DROP TABLE IF EXISTS games;
            DROP TABLE IF EXISTS players;
            DROP TABLE IF EXISTS teams;
            DROP TABLE IF EXISTS seasons;
            DROP TABLE IF EXISTS placements;
            """
        )
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
    return conn


def _team_key(name: str) -> str:
    return " ".join((name or "").split()).lower()


def build_store(
    path: Path,
    games: Iterable[Dict],
    index: PlayerIndex,
    *,
    persons: PersonKeys | None = None,
    seasons: Iterable[Dict] = (),
    placements: Iterable[Dict] = (),
    players: Iterable[Dict] = (),
    teams: Iterable[Dict] = (),
    season_names: Dict[str, str] | None = None,
) -> Tuple[sqlite3.Connection, StoreStats]:
    """(Re)build the fact store at `path` from parsed game records.

    Each game record is what the fetch layer produces: `game_id`, `season_id`,
    `home_team`, `away_team`, scores, and a `gameplay` dict from
    `parse_gameplay` (already possession-annotated).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = open_store(path)
    stats = StoreStats()
    person_keys = persons or PersonKeys()
    # iterated more than once below, so a generator would silently yield nothing twice
    players, teams, seasons, placements = list(players), list(teams), list(seasons), list(placements)

    conn.execute("BEGIN")
    for table in ("players", "teams", "seasons", "games", "appearances", "points", "placements"):
        conn.execute(f"DELETE FROM {table}")

    for player in players:
        conn.execute(
            "INSERT OR REPLACE INTO players(player_id, display_name, name_key, person_key, source)"
            " VALUES (?,?,?,?,?)",
            (
                player["player_id"],
                player.get("display_name", ""),
                canon(player.get("display_name", "")),
                person_keys.resolve(player.get("display_name", "")),
                player.get("source", ""),
            ),
        )

    for team in teams:
        conn.execute(
            "INSERT OR REPLACE INTO teams(team_key, name, pelikone_id, club, division, country)"
            " VALUES (?,?,?,?,?,?)",
            (
                _team_key(team.get("name", "")),
                team.get("name", ""),
                team.get("pelikone_id"),
                team.get("club"),
                team.get("division"),
                team.get("country"),
            ),
        )

    for season in seasons:
        conn.execute(
            "INSERT OR REPLACE INTO seasons(season_id, year, type, name, division) VALUES (?,?,?,?,?)",
            (season["season_id"], season.get("year"), season.get("type"), season.get("name"), season.get("division")),
        )

    # A game's season_id is enough to register the season: the year is the four
    # digits inside the ID (`KESA2026`, `2018.1`, `Talvi2016`, `2017F`). Whether it
    # was a summer or a winter season is **not** in the ID — `2018.1` is winter and
    # `2020.1` is summer — so it comes from the season name when the caller has
    # one (`season_names`, read from the scraped season files) and is `other`
    # when it does not. Guessing from the numeric suffix is what used to make
    # every numeric season `unknown`.
    season_seen = {s["season_id"] for s in seasons}
    names_by_season = season_names or {}

    def register_season(season_id: Optional[str]) -> None:
        if not season_id or season_id in season_seen:
            return
        season_seen.add(season_id)
        name = names_by_season.get(season_id, "")
        conn.execute(
            "INSERT OR REPLACE INTO seasons(season_id, year, type, name, division) VALUES (?,?,?,?,?)",
            (
                season_id,
                season_year(season_id, name),
                season_type(season_id, name),
                name or season_id,
                None,
            ),
        )

    for placement in placements:
        conn.execute(
            "INSERT OR REPLACE INTO placements(season_id, team, division, placement) VALUES (?,?,?,?)",
            (placement["season_id"], placement["team"], placement.get("division"), placement.get("placement")),
        )
        stats.placements += 1

    seen_players: Dict[str, str] = {}

    def register_player(player_id: str, name: str, source: str) -> None:
        if not player_id or player_id in seen_players:
            return
        seen_players[player_id] = name
        conn.execute(
            "INSERT OR REPLACE INTO players(player_id, display_name, name_key, person_key, source)"
            " VALUES (?,?,?,?,?)",
            (player_id, name, canon(name), person_keys.resolve(name), source),
        )

    for game in games:
        gameplay = game.get("gameplay") or {}
        register_season(game.get("season_id"))
        home = gameplay.get("home_team") or game.get("home_team", "")
        away = gameplay.get("away_team") or game.get("away_team", "")
        points = [p for p in gameplay.get("points", []) if p.get("type") == "point"]
        home_score = gameplay.get("home_score", game.get("home_score"))
        away_score = gameplay.get("away_score", game.get("away_score"))
        expected = (home_score or 0) + (away_score or 0)

        conn.execute(
            "INSERT OR REPLACE INTO games(game_id, season_id, home_team, away_team, home_score,"
            " away_score, venue, start_time, points_expected, points_parsed, points_complete)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(game["game_id"]),
                game.get("season_id"),
                home,
                away,
                home_score,
                away_score,
                game.get("venue"),
                game.get("start_time"),
                expected,
                len(points),
                1 if expected == len(points) else 0,
            ),
        )
        stats.games += 1

        for side, key, team in (("home", "home_players", home), ("guest", "away_players", away)):
            for player in gameplay.get(key, []):
                player_id = player.get("id") or ""
                name = player.get("name", "")
                if not player_id:
                    resolved = index.resolve(name)
                    if len(resolved.ids) == 1:
                        player_id = resolved.ids[0]
                if not player_id:
                    continue
                register_player(player_id, name, "roster")
                conn.execute(
                    "INSERT OR REPLACE INTO appearances(game_id, player_id, team, side, goals, assists, total)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (str(game["game_id"]), player_id, team, side, player.get("goals", 0), player.get("assists", 0), player.get("total", 0)),
                )
                stats.appearances += 1

        roster_team: Dict[str, str] = {}
        for side, key, team in (("home", "home_players", home), ("guest", "away_players", away)):
            for player in gameplay.get(key, []):
                name_key = canon(player.get("name", ""))
                if name_key:
                    roster_team[name_key] = team

        seq = 0
        for point in points:
            seq += 1
            scorer_name = point.get("scorer") or ""
            passer_name = point.get("passer") or ""
            scorer_key = index.key_for(scorer_name) if scorer_name else None
            passer_key = index.key_for(passer_name) if passer_name else None
            if scorer_key and scorer_key.startswith("name:"):
                stats.points_pseudo_keyed += 1
            possession = point.get("possession")
            possession_team = home if possession == "home" else away if possession == "guest" else None

            conn.execute(
                "INSERT OR REPLACE INTO points(game_id, seq, clock, score, scoring_side, scoring_team,"
                " possession, possession_team, possession_known, scorer_key, scorer_name, scorer_person,"
                " scorer_team, passer_key, passer_name, passer_person) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(game["game_id"]),
                    seq,
                    point.get("time"),
                    point.get("score"),
                    point.get("side"),
                    home if point.get("side") == "home" else away if point.get("side") == "guest" else None,
                    possession,
                    possession_team,
                    int(point.get("possession_known", 0)),
                    scorer_key,
                    scorer_name,
                    person_keys.resolve(scorer_name) or None,
                    roster_team.get(canon(scorer_name)) if scorer_name else None,
                    passer_key,
                    passer_name,
                    person_keys.resolve(passer_name) or None,
                ),
            )
            stats.points += 1
            if point.get("possession_known"):
                stats.points_with_possession += 1

    conn.commit()
    stats.players = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    stats.persons = conn.execute("SELECT COUNT(DISTINCT person_key) FROM players").fetchone()[0]
    stats.teams = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    stats.seasons = conn.execute("SELECT COUNT(*) FROM seasons").fetchone()[0]
    return conn, stats


def defense_totals(conn: sqlite3.Connection, team: str) -> Dict[str, object]:
    """Defense-initiated scoring for `team`: points it scored while it started
    the point on defense. A SQL query, not a script — that is the point of the
    store."""
    rows = conn.execute(
        """
        SELECT p.scorer_person AS person,
               COALESCE(NULLIF(p.scorer_name, ''), pl.display_name) AS name,
               COUNT(*) AS defense_points
        FROM points p
        JOIN games g ON g.game_id = p.game_id
        LEFT JOIN players pl ON pl.player_id = p.scorer_key
        WHERE p.possession_known = 1
          AND p.possession_team = ?
          AND p.scorer_team = ?
        GROUP BY p.scorer_person, name
        ORDER BY defense_points DESC, name
        """,
        (team, team),
    ).fetchall()
    players = [dict(r) for r in rows]
    return {
        "team": team,
        "players": len(players),
        "defense_points": sum(p["defense_points"] for p in players),
        "top": players[:3],
    }
