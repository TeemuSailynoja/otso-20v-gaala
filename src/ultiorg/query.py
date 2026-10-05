"""Composition over the fact store: the coaching staff's questions are joins.

The store answers "who scored off defense in 2019" with a `WHERE` clause. This
module is the layer above it that makes the *composite* questions one expression,
without a verb per question:

    p = ultiorg.player("Lehto Santtu")     # name or player ID, resolved once
    p.connections(top=10)                  # who he passes to, weighted per game
    p.scoring(possession="defense")        # points that started on defense
    p.games(season="KESA2025")             # appearances with roster totals

Everything composes from the same rows, so a question these helpers do not cover
is still reachable with `ultiorg sql`. Cache-first by construction: a query here
reads `data/store.sqlite` and makes **zero** requests.

Identity note: queries run on the **person key**, not a single player ID. pelikone
mints a new player ID per registration — 904 roster names carry 6,175 IDs — so a
career is a cluster of IDs and `players.person_key` is what joins them.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .config import STORE_PATH
from .names import canon


class UnknownPlayer(Exception):
    """No player row and no point row carries this name or ID."""


class AmbiguousPlayer(Exception):
    """One canonical name, more than one person. Not guessed — see aliases.json."""

    def __init__(self, needle: str, candidates: Sequence[Tuple[str, str]]):
        super().__init__(
            f"'{needle}' matches {len(candidates)} people: "
            + ", ".join(f"{name} ({key})" for name, key in candidates)
            + " — merge them in config/aliases.json or name one"
        )
        self.needle = needle
        self.candidates = list(candidates)


@dataclass
class Player:
    """A person, not a player ID: every ID that name has ever held."""

    person_key: str
    display_name: str
    player_ids: Tuple[str, ...] = ()
    known_from: str = "roster"  # "roster" | "point rows"
    conn: sqlite3.Connection = field(repr=False, default=None)

    def __bool__(self) -> bool:
        return bool(self.person_key)

    # --- filters shared by every query -------------------------------------
    #
    # every query below joins `games g` and `LEFT JOIN seasons s`, so one filter
    # helper serves them all and named parameters keep the binding unambiguous

    def _filters(self, season: Optional[str], since: Optional[int]) -> Tuple[str, Dict]:
        extra, params = "", {}
        if season:
            extra += " AND g.season_id = :season"
            params["season"] = season
        if since:
            extra += " AND s.year >= :since"
            params["since"] = since
        return extra, params

    # --- the composite questions -------------------------------------------

    def scoring(
        self,
        *,
        possession: Optional[str] = None,
        season: Optional[str] = None,
        since: Optional[int] = None,
    ) -> Dict:
        """Goals, assists and points, optionally only off a given possession.

        `possession="defense"` is the coaching-staff question — points that started
        on defense — and it filters *both* roles, so the answer is "points in
        defense-initiated rallies", not "goals off defense plus every assist".
        Points whose possession is unknown are excluded from a possession filter
        rather than guessed into one; `possession_unknown` reports how many there are.

        "defense" is a relation, not a column: the store keeps which *team* started
        the rally (`possession_team`) and which team scored (`scoring_team`), so a
        point is defense-initiated when they are the same side.
        """
        extra, params = self._filters(season, since)
        params["me"] = self.person_key
        sql = (
            "SELECT"
            "  SUM(CASE WHEN pt.scorer_person = :me THEN 1 ELSE 0 END) AS goals,"
            "  SUM(CASE WHEN pt.passer_person  = :me THEN 1 ELSE 0 END) AS assists,"
            "  COUNT(*) AS points,"
            "  SUM(CASE WHEN pt.possession_known = 0 THEN 1 ELSE 0 END) AS possession_unknown"
            " FROM points pt JOIN games g ON g.game_id = pt.game_id"
            " LEFT JOIN seasons s ON s.season_id = g.season_id"
            f" WHERE (pt.scorer_person = :me OR pt.passer_person = :me){extra}"
        )
        if possession == "defense":
            sql += (
                " AND pt.possession_known = 1 AND pt.possession_team IS NOT NULL"
                " AND pt.scoring_team = pt.possession_team"
            )
        elif possession == "offense":
            sql += (
                " AND pt.possession_known = 1 AND pt.possession_team IS NOT NULL"
                " AND pt.scoring_team IS NOT NULL AND pt.scoring_team != pt.possession_team"
            )
        elif possession is not None:
            raise ValueError(f"possession must be 'defense' or 'offense', got {possession!r}")
        row = self.conn.execute(sql, params).fetchone()

        games = self.games_played(season=season, since=since)
        goals, assists, points = row["goals"] or 0, row["assists"] or 0, row["points"] or 0
        return {
            "player": self.display_name,
            "person_key": self.person_key,
            "possession": possession,
            "season": season,
            "since": since,
            "games": games,
            "goals": goals,
            "assists": assists,
            "points": points,
            "points_per_game": round(points / games, 2) if games else None,
            "possession_unknown": row["possession_unknown"] or 0,
        }

    def connections(self, *, top: int = 10, season: Optional[str] = None, since: Optional[int] = None) -> List[Dict]:
        """Who this player's points are connected to, weighted by games together.

        `assists_given` counts points this player set up; `assists_received` counts
        points finished by others for this player. `games_together` comes from the
        rosters, so a big raw count from a long career is comparable to a small one
        from a short one via `per_game`.
        """
        extra, params = self._filters(season, since)
        params["me"] = self.person_key

        def branch(other: str, mine: str, given: int, received: int) -> str:
            return (
                f"SELECT pt.{other} AS other, {given} AS given, {received} AS received"
                " FROM points pt JOIN games g ON g.game_id = pt.game_id"
                " LEFT JOIN seasons s ON s.season_id = g.season_id"
                f" WHERE pt.{mine} = :me AND pt.{other} IS NOT NULL{extra}"
            )

        sql = (
            "SELECT other, SUM(given) AS given, SUM(received) AS received FROM ("
            + branch("passer_person", "scorer_person", 0, 1)
            + " UNION ALL "
            + branch("scorer_person", "passer_person", 1, 0)
            + ") GROUP BY other HAVING other IS NOT NULL AND other != :me"
        )
        rows = self.conn.execute(sql, params).fetchall()

        together_sql = (
            "SELECT pb.person_key AS other, COUNT(DISTINCT a.game_id) AS games_together"
            " FROM appearances a JOIN players pa ON pa.player_id = a.player_id"
            " JOIN appearances b ON b.game_id = a.game_id JOIN players pb ON pb.player_id = b.player_id"
            " JOIN games g ON g.game_id = a.game_id LEFT JOIN seasons s ON s.season_id = g.season_id"
            f" WHERE pa.person_key = :me AND pb.person_key != :me{extra}"
            " GROUP BY pb.person_key"
        )
        together = {r["other"]: r["games_together"] for r in self.conn.execute(together_sql, params)}

        names = {
            r["person_key"]: r["name"]
            for r in self.conn.execute(
                "SELECT person_key, MIN(display_name) AS name FROM players GROUP BY person_key"
            )
        }
        # a person known only from point rows has no players row: their name still
        # comes from the page, so show it and flag that no ID stands behind it
        fallback = {
            r["person"]: r["name"]
            for r in self.conn.execute(
                "SELECT person, MIN(name) AS name FROM ("
                "  SELECT scorer_person AS person, scorer_name AS name FROM points"
                "  UNION ALL SELECT passer_person, passer_name FROM points"
                ") WHERE person IS NOT NULL GROUP BY person"
            )
        }
        out = []
        for row in rows:
            other = row["other"]
            games_together = together.get(other, 0)
            passes = (row["given"] or 0) + (row["received"] or 0)
            out.append(
                {
                    "player": names.get(other) or fallback.get(other) or other,
                    "person_key": other,
                    "assists_given": row["given"] or 0,
                    "assists_received": row["received"] or 0,
                    "passes": passes,
                    "games_together": games_together,
                    "per_game": round(passes / games_together, 2) if games_together else None,
                    # a person key is a canonical name, so "resolved" can only mean
                    # "a roster ID stands behind this name"
                    "resolved": other in names,
                }
            )
        out.sort(key=lambda r: (-r["passes"], -(r["per_game"] or 0), r["player"]))
        return out[:top]

    def games_played(self, *, season: Optional[str] = None, since: Optional[int] = None) -> int:
        extra, params = self._filters(season, since)
        params["me"] = self.person_key
        sql = (
            "SELECT COUNT(DISTINCT a.game_id) AS n FROM appearances a"
            " JOIN players pl ON pl.player_id = a.player_id"
            " JOIN games g ON g.game_id = a.game_id"
            " LEFT JOIN seasons s ON s.season_id = g.season_id"
            f" WHERE pl.person_key = :me{extra}"
        )
        return self.conn.execute(sql, params).fetchone()["n"] or 0

    def games(self, *, season: Optional[str] = None, since: Optional[int] = None, limit: Optional[int] = None) -> List[Dict]:
        """Appearances with the roster totals the game page reported."""
        extra, params = self._filters(season, since)
        params["me"] = self.person_key
        sql = (
            "SELECT g.game_id, g.season_id, s.year, g.home_team, g.away_team, g.home_score, g.away_score,"
            " a.team, a.side, a.goals, a.assists, a.total"
            " FROM appearances a JOIN players pl ON pl.player_id = a.player_id"
            " JOIN games g ON g.game_id = a.game_id"
            " LEFT JOIN seasons s ON s.season_id = g.season_id"
            f" WHERE pl.person_key = :me{extra} ORDER BY s.year, g.season_id, CAST(g.game_id AS INTEGER)"
        )
        if limit:
            sql += " LIMIT :limit"
            params["limit"] = limit
        return [dict(r) for r in self.conn.execute(sql, params)]

    def career(self) -> Dict:
        """The shape of the career: seasons, years, teams, totals."""
        rows = self.conn.execute(
            "SELECT g.season_id, s.year, a.team, COUNT(DISTINCT a.game_id) AS games,"
            " SUM(a.goals) AS goals, SUM(a.assists) AS assists, SUM(a.total) AS total"
            " FROM appearances a JOIN players pl ON pl.player_id = a.player_id"
            " JOIN games g ON g.game_id = a.game_id"
            " LEFT JOIN seasons s ON s.season_id = g.season_id"
            " WHERE pl.person_key = ? GROUP BY g.season_id, a.team ORDER BY s.year, g.season_id",
            (self.person_key,),
        ).fetchall()
        totals = self.scoring()
        return {
            "player": self.display_name,
            "person_key": self.person_key,
            "player_ids": list(self.player_ids),
            "known_from": self.known_from,
            "seasons": [dict(r) for r in rows],
            "years": sorted({r["year"] for r in rows if r["year"]}),
            "teams": sorted({r["team"] for r in rows if r["team"]}),
            "games": totals["games"],
            "goals": totals["goals"],
            "assists": totals["assists"],
            "points": totals["points"],
            "points_per_game": totals["points_per_game"],
        }


class Store:
    """Read-only handle on `data/store.sqlite` for the composition API."""

    def __init__(self, path: Path = STORE_PATH):
        if not Path(path).exists():
            raise FileNotFoundError(
                f"no fact store at {path} — run `ultiorg store` to build it from the cache"
            )
        self.path = Path(path)
        self.conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def player(self, needle: str) -> Player:
        """Resolve a display name (any word order) or a player ID to a person."""
        needle = str(needle).strip()
        if not needle:
            raise UnknownPlayer("empty player name")

        if needle.isdigit():
            source = "roster"
            rows = self.conn.execute(
                "SELECT person_key, MIN(display_name) AS name, GROUP_CONCAT(player_id) AS ids"
                " FROM players WHERE player_id = ? GROUP BY person_key",
                (needle,),
            ).fetchall()
        else:
            key = canon(needle)
            rows = self.conn.execute(
                "SELECT person_key, MIN(display_name) AS name, GROUP_CONCAT(player_id) AS ids"
                " FROM players WHERE name_key = ? GROUP BY person_key",
                (key,),
            ).fetchall()
            source = "roster"
            if not rows:
                rows = self._from_point_rows(key)
                source = "point rows"

        if not rows:
            raise UnknownPlayer(f"no player matches {needle!r}")
        if len(rows) > 1:
            raise AmbiguousPlayer(needle, [(r["name"] or r["person_key"], r["person_key"]) for r in rows])

        row = rows[0]
        return Player(
            person_key=row["person_key"],
            display_name=row["name"] or row["person_key"],
            player_ids=tuple((row["ids"] or "").split(",")) if row["ids"] else (),
            known_from=source,
            conn=self.conn,
        )

    def _from_point_rows(self, key: str) -> List[sqlite3.Row]:
        """Names that appear only in point rows have no roster ID; they are still people."""
        return self.conn.execute(
            "SELECT person_key, MIN(name) AS name, NULL AS ids FROM ("
            "  SELECT scorer_person AS person_key, scorer_name AS name FROM points"
            "  UNION ALL SELECT passer_person, passer_name FROM points"
            ") WHERE person_key = ? GROUP BY person_key",
            (key,),
        ).fetchall()

    def sql(self, query: str, params: Sequence = ()) -> List[Dict]:
        """The escape hatch: anything the helpers do not cover is still a query."""
        if not query.strip().lower().startswith(("select", "with", "pragma", "explain")):
            raise ValueError("this store is opened read-only; only SELECT/WITH/PRAGMA/EXPLAIN run here")
        return [dict(r) for r in self.conn.execute(query, params)]

    def tables(self) -> List[str]:
        return [
            r["name"]
            for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        ]
