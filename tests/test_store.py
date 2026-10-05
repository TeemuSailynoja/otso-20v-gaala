"""The fact store: keys, possession facts, and the numbers the site publishes.

These tests are the gate for Phase 5. The corpus-wide numbers are asserted here
because "the store agrees with the site" is the property that makes the store
trustworthy; if a number moves, either the parser changed or the store did, and
one of the two is wrong.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest
from conftest import read_fixture

from ultiorg import parse_allplayers, parse_gameplay
from ultiorg.aliases import PersonKeys
from ultiorg.identify import PlayerIndex
from ultiorg.names import canon
from ultiorg.parsers import is_otso_akatemia, is_otso_team
from ultiorg.store import build_store, defense_totals, open_store

CORPUS = pytest.mark.skipif(
    not Path("data/processed/match_results.json").exists(),
    reason="processed corpus not present",
)


def _fixture_games():
    games = []
    for fixture, game_id in (
        ("gameplay_11049_modern.html", "11049"),
        ("gameplay_2980_pre2015.html", "2980"),
        ("gameplay_6215_otso_derby.html", "6215"),
        ("gameplay_6923_hyphen.html", "6923"),
    ):
        gameplay = parse_gameplay(read_fixture(fixture))
        games.append({"game_id": game_id, "season_id": "KESA2026", "gameplay": gameplay})
    return games


@pytest.fixture
def small_store(tmp_path):
    index = PlayerIndex(parse_allplayers(read_fixture("allplayers_all.html")))
    conn, stats = build_store(tmp_path / "store.sqlite", _fixture_games(), index)
    yield conn, stats
    conn.close()


def test_store_counts_match_its_own_rows(small_store):
    conn, stats = small_store
    assert stats.games == 4
    assert conn.execute("SELECT COUNT(*) FROM points").fetchone()[0] == stats.points
    assert conn.execute("SELECT COUNT(*) FROM appearances").fetchone()[0] == stats.appearances
    assert stats.points == sum(
        len([p for p in g["gameplay"]["points"] if p["type"] == "point"]) for g in _fixture_games()
    )


def test_possession_survives_into_rows(small_store):
    conn, _ = small_store
    row = conn.execute(
        "SELECT possession, possession_team, possession_known FROM points WHERE game_id = '11049' ORDER BY seq LIMIT 1"
    ).fetchone()
    assert row["possession_known"] == 1
    assert row["possession"] == "guest"
    assert row["possession_team"] == "Otso"  # Otso is away in this game and defended


def test_unresolved_names_keep_a_pseudo_key(small_store):
    """A point whose scorer is not in the player index is still a point."""
    conn, _ = small_store
    rows = conn.execute(
        "SELECT scorer_key, scorer_name FROM points WHERE scorer_key LIKE 'name:%'"
    ).fetchall()
    for row in rows:
        assert row["scorer_key"] == "name:" + canon(row["scorer_name"])
    # the pre-2015 game's players are not in the 236-row index fixture
    assert rows


def test_aliases_merge_persons(tmp_path):
    """`aliases.json` is the only place two spellings become one person."""
    games = [
        {
            "game_id": "1",
            "season_id": "S",
            "gameplay": {
                "home_team": "Otso",
                "away_team": "TS2",
                "home_players": [{"id": "10", "name": "Touko Väänänen"}],
                "away_players": [{"id": "20", "name": "Cee Three"}],
                "points": [
                    {"type": "point", "side": "home", "score": "1-0", "scorer": "Aukusti Touko Väänänen"},
                ],
            },
        }
    ]
    index = PlayerIndex([{"id": "10", "name": "Touko Väänänen"}])

    conn, _ = build_store(tmp_path / "a.sqlite", games, index)
    split = conn.execute("SELECT scorer_person FROM points").fetchone()[0]
    conn.close()
    assert split == "aukusti touko väänänen"

    persons = PersonKeys({"aukusti touko väänänen": "touko väänänen"})
    conn, _ = build_store(tmp_path / "b.sqlite", games, index, persons=persons)
    merged = conn.execute("SELECT scorer_person FROM points").fetchone()[0]
    conn.close()
    assert merged == "touko väänänen"


def test_alias_cycles_terminate():
    keys = PersonKeys({"a b": "c d", "c d": "a b"})
    assert keys.resolve("a b") in {"a b", "c d"}


def test_schema_change_rebuilds_instead_of_failing(tmp_path):
    """The store is derived: a schema change drops and rebuilds, never migrates."""
    path = tmp_path / "store.sqlite"
    conn = open_store(path)
    conn.execute("PRAGMA user_version = 1")
    conn.execute("CREATE TABLE IF NOT EXISTS points (game_id TEXT, seq INTEGER, scorer_key TEXT)")
    conn.commit()
    conn.close()

    conn = open_store(path)
    columns = {r[1] for r in conn.execute("PRAGMA table_info(points)")}
    conn.close()
    assert "scorer_person" in columns


# --- corpus gate -----------------------------------------------------------


def _otso_side(home, away):
    """Which side is an Otso-family team, by the library's predicate.

    `build_site_data` keeps its own copy of this predicate today. Both lists must
    match — measured: with the library's older three-pattern list (`otso`,
    `grizzly`, `polar`) the two disagree for 13 players, because the site has
    always also counted "Hukka" and "Karhuvaarit". Phase 8 replaces both with one
    `teams.yaml` predicate; `test_otso_predicate_covers_every_squad_name` pins the
    list until then.
    """
    if is_otso_team(home) or is_otso_akatemia(home):
        return home
    if is_otso_team(away) or is_otso_akatemia(away):
        return away
    return None


def test_otso_predicate_covers_every_squad_name():
    """The library predicate must match the set the gala has always counted.

    A pattern list that quietly loses a squad name loses that squad's games, and
    the players who only ever played in them disappear from every aggregate.
    """
    for name in ("Otso", "Otso 2", "Otso Grizzly", "Otso Polar", "Otso Hukka", "Karhuvaarit"):
        assert is_otso_team(name), name
    assert not is_otso_team("Otso Akatemia")
    assert not is_otso_team("UFO Akatemia")
    assert is_otso_akatemia("Otso Akatemia")
    assert not is_otso_akatemia("UFO Akatemia")


@CORPUS
def test_store_matches_the_published_site_numbers():
    """The store and the site's defense builder must agree, point for point.

    Both read the same corpus and the same name rule; the store keeps the facts,
    `build_defense_stats` publishes them. If they disagree, one of them is wrong,
    and the disagreement is a player's published stat on the gala page.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from build_site_data import build_defense_stats, load_gameplay

    corpus = load_gameplay()
    index = PlayerIndex(parse_allplayers(read_fixture("allplayers_all.html")))
    conn, stats = build_store(_tmp_path(), corpus, index)

    assert stats.games == 795
    assert stats.points == 18681
    assert stats.points_with_possession == 18394

    games = {r["game_id"]: dict(r) for r in conn.execute("SELECT * FROM games")}
    by_person: dict[str, int] = {}
    for row in conn.execute("SELECT * FROM points WHERE possession_known = 1"):
        game = games[row["game_id"]]
        otso_team = _otso_side(game["home_team"] or "", game["away_team"] or "")
        if not otso_team or row["possession_team"] != otso_team:
            continue
        if row["scorer_team"] != otso_team:
            continue
        key = canon(row["scorer_name"] or "")
        if key:
            by_person[key] = by_person.get(key, 0) + 1
    conn.close()

    builder = {k: v["defense_points"] for k, v in build_defense_stats(corpus).items()}
    assert sum(builder.values()) == 4443
    assert sum(by_person.values()) == sum(builder.values())
    # the builder also carries players with zero defense points (offense-only
    # scorers); the store only ever produces rows for points that exist
    assert {k: v for k, v in builder.items() if v} == by_person
    # What the *page* shows is a third number, and it is smaller. players.json is
    # keyed by season-card rosters, so a scorer whose point-row spelling never
    # joins a roster entry loses his stats: "Aukusti Touko Väänänen" (point rows)
    # vs "Touko Väänänen" (rosters) — 115 defense points that exist in the data
    # and do not exist on the site. Phase 9 (person keys) closes this; until then
    # the gap is asserted here rather than discovered in production.
    site = json.loads(Path("site_data/players.json").read_text(encoding="utf-8"))
    site_defense: dict[str, int] = {}
    for name, player in site.items():
        site_defense[canon(name)] = site_defense.get(canon(name), 0) + player.get("defense_points", 0)
    missing = {k: builder[k] for k in builder if k not in site_defense}
    assert missing == {"aukusti touko väänänen": 115}
    assert sum(site_defense.values()) == 4328


def _tmp_path():
    import tempfile
    from pathlib import Path

    return Path(tempfile.mkdtemp()) / "store.sqlite"
