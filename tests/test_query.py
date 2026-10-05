"""The composition API: composite questions over the fact store.

These are the questions the coaching staff actually asks — "who does X connect
to", "how much of X's scoring started on defense" — which are joins, not columns.
The tests build a store from the four archived game fixtures, so every expected
number is countable by hand from `tests/fixtures/`: 81 points across 4 games and
3 seasons (2013, 2018, 2026).
"""

import sqlite3
from pathlib import Path

import pytest
from conftest import read_fixture

from ultiorg import parse_allplayers, parse_gameplay
from ultiorg.aliases import PersonKeys
from ultiorg.identify import PlayerIndex
from ultiorg.query import AmbiguousPlayer, Store, UnknownPlayer
from ultiorg.store import build_store

CORPUS = pytest.mark.skipif(
    not Path("data/processed/match_results.json").exists(),
    reason="processed corpus not present",
)

# season_id is metadata here, and it is what makes `since=` a filter rather than a
# guess about the season ID's shape (`2013.1` and `KESA2026` are both real).
FIXTURE_GAMES = (
    ("gameplay_11049_modern.html", "11049", "KESA2026"),
    ("gameplay_2980_pre2015.html", "2980", "2013.1"),
    ("gameplay_6215_otso_derby.html", "6215", "2018.1"),
    ("gameplay_6923_hyphen.html", "6923", "KESA2026"),
)


def _build(path: Path) -> None:
    games = [
        {
            "game_id": game_id,
            "season_id": season_id,
            "home_team": "Otso",
            "away_team": "UFO",
            "gameplay": parse_gameplay(read_fixture(fixture)),
        }
        for fixture, game_id, season_id in FIXTURE_GAMES
    ]
    # a scorer nobody holds an ID for: point rows alone must still make a person,
    # and a connection built from such a name must be flagged as unresolved
    games[0]["gameplay"]["points"].extend(
        [
            {
                "type": "point", "side": "home", "score": "99-0", "time": "99.00",
                "passer": "", "scorer": "Ni Nobodysson",
                "possession": "home", "possession_known": 1,
            },
            {
                "type": "point", "side": "home", "score": "99-1", "time": "99.30",
                "passer": "Erkka Niini", "scorer": "Ni Nobodysson",
                "possession": "home", "possession_known": 1,
            },
        ]
    )
    index = PlayerIndex(parse_allplayers(read_fixture("allplayers_all.html")))
    conn, stats = build_store(path, games, index, persons=PersonKeys())
    conn.close()
    assert stats.points == 83, "fixture store drifted; re-count before trusting the numbers below"


@pytest.fixture
def store_path(tmp_path):
    path = tmp_path / "store.sqlite"
    _build(path)
    return path


@pytest.fixture
def store(store_path):
    with Store(store_path) as handle:
        yield handle


# --- resolution -------------------------------------------------------------


def test_name_in_any_word_order_resolves_to_one_person(store):
    """Point rows say `Last First`, rosters say `First Last`; both must find him."""
    by_roster = store.player("Erkka Niini")
    by_point = store.player("Niini Erkka")
    assert by_roster.person_key == by_point.person_key == "erkka niini"
    assert by_roster.display_name == by_point.display_name


def test_a_person_is_a_cluster_of_player_ids(store):
    """pelikone mints a new ID per registration, so one person holds many."""
    player = store.player("Hotari Roni")
    assert len(player.player_ids) >= 2
    for player_id in player.player_ids:
        assert store.player(player_id).person_key == player.person_key


def test_unknown_name_says_so(store):
    with pytest.raises(UnknownPlayer):
        store.player("Ei Ketään Ei Mikään")


def test_one_name_two_people_is_refused_not_guessed(store_path):
    """A partial alias merge can leave two people under one name. Guessing would
    be invisible downstream, so the API stops and names the candidates."""
    conn = sqlite3.connect(store_path)
    conn.execute(
        "UPDATE players SET person_key = person_key || ' (muu)' WHERE player_id ="
        " (SELECT player_id FROM players WHERE name_key = 'erkka niini' LIMIT 1)"
    )
    conn.commit()
    conn.close()
    with Store(store_path) as store:
        with pytest.raises(AmbiguousPlayer) as exc:
            store.player("Erkka Niini")
        assert len(exc.value.candidates) == 2


def test_a_name_only_in_point_rows_is_still_a_person(store):
    """256 scorers in the real corpus have no roster ID. They are reported, not dropped."""
    player = store.player("Nobodysson Ni")
    # the key is the sorted canonical form, so either written order finds him
    assert player.person_key == "ni nobodysson"
    assert player.known_from == "point rows"
    assert player.player_ids == ()
    assert player.scoring()["goals"] == 2
    assert player.games_played() == 0  # no roster, so no appearance rows


# --- scoring ----------------------------------------------------------------


def test_scoring_totals_match_a_direct_count(store):
    player = store.player("Pasi Tamminen")
    direct = store.conn.execute(
        "SELECT SUM(scorer_person = ?), SUM(passer_person = ?) FROM points"
        " WHERE scorer_person = ? OR passer_person = ?",
        (player.person_key, player.person_key, player.person_key, player.person_key),
    ).fetchone()
    totals = player.scoring()
    assert totals["goals"] == direct[0] == 4
    assert totals["assists"] == direct[1]
    assert totals["points"] == totals["goals"] + totals["assists"]


def test_defense_and_offense_partition_the_points(store):
    """`possession="defense"` is a relation: the scoring side started the rally.

    defense + offense + unknown must equal every point, or the filter is silently
    dropping rows. Heikki Väänänen has a point with no possession marker, so his
    row exercises the third bucket.
    """
    for name, goals in (("Erkka Niini", 4), ("Pasi Tamminen", 4), ("Heikki Väänänen", 3)):
        player = store.player(name)
        everything = player.scoring()
        defense = player.scoring(possession="defense")
        offense = player.scoring(possession="offense")
        assert everything["goals"] == goals
        assert defense["points"] + offense["points"] + everything["possession_unknown"] == everything["points"]
        assert defense["goals"] + offense["goals"] + everything["possession_unknown"] == everything["goals"]
    # Niini: 4 goals, all off defense, plus the injected assist below = 5 points
    assert store.player("Erkka Niini").scoring(possession="defense")["goals"] == 4
    assert store.player("Erkka Niini").scoring(possession="defense")["points"] == 5
    assert store.player("Pasi Tamminen").scoring(possession="defense")["points"] == 2
    assert store.player("Heikki Väänänen").scoring()["possession_unknown"] == 1


def test_an_unknown_possession_value_is_an_error_not_a_zero(store):
    with pytest.raises(ValueError):
        store.player("Erkka Niini").scoring(possession="home")


def test_since_filters_on_the_season_year_not_the_season_id(store):
    """Season IDs are heterogeneous (`2013.1`, `KESA2026`); the year is the year."""
    player = store.player("Jarno Sihvo")
    everything = player.games_played()
    recent = player.games_played(since=2020)
    assert 0 < recent < everything
    assert len(player.games(since=2020)) == recent
    assert player.scoring(since=2020)["points"] <= player.scoring()["points"]
    assert player.games_played(since=2100) == 0


def test_season_filter_selects_one_season_id(store):
    player = store.player("Jarno Sihvo")
    rows = player.games(season="KESA2026")
    assert rows and {r["season_id"] for r in rows} == {"KESA2026"}
    assert player.games_played(season="KESA2026") == len(rows)


def test_games_rows_carry_the_match_and_the_roster_totals(store):
    player = store.player("Jarno Sihvo")
    row = player.games()[0]
    assert {"game_id", "season_id", "year", "home_team", "away_team", "team", "goals", "assists", "total"} <= set(row)
    assert row["total"] == row["goals"] + row["assists"]
    assert row["year"] in (2013, 2018, 2026)


def test_career_shapes_the_seasons(store):
    player = store.player("Jarno Sihvo")
    career = player.career()
    assert career["years"] == sorted(set(career["years"]))
    assert career["games"] == player.games_played()
    assert career["points"] == career["goals"] + career["assists"]
    assert career["teams"] and all(career["teams"])
    assert len(career["seasons"]) == len({(r["season_id"], r["team"]) for r in career["seasons"]})


# --- connections ------------------------------------------------------------


def test_connections_are_symmetric_and_swapped(store):
    """If A set up B, then B's list shows A with the direction reversed."""
    a = store.player("Hotari Roni")
    rows = {r["person_key"]: r for r in a.connections(top=1000)}
    checked = 0
    for key, row in rows.items():
        other_id = store.conn.execute(
            "SELECT player_id FROM players WHERE person_key = ? LIMIT 1", (key,)
        ).fetchone()
        if other_id is None:
            continue  # a name-only person has no card to look up
        back = {r["person_key"]: r for r in store.player(other_id["player_id"]).connections(top=1000)}
        assert a.person_key in back, f"{key} does not list {a.display_name} back"
        mirror = back[a.person_key]
        assert mirror["assists_given"] == row["assists_received"]
        assert mirror["assists_received"] == row["assists_given"]
        assert mirror["games_together"] == row["games_together"]
        checked += 1
    assert checked > 0


def test_connections_weight_by_games_together(store):
    rows = store.player("Hotari Roni").connections(top=5)
    assert len(rows) == 5
    assert [r["passes"] for r in rows] == sorted((r["passes"] for r in rows), reverse=True)
    for row in rows:
        assert row["passes"] == row["assists_given"] + row["assists_received"]
        assert row["games_together"] > 0
        assert row["per_game"] == round(row["passes"] / row["games_together"], 2)


def test_connections_name_the_unresolved(store):
    """A connection known only from a point row has no ID: say so, do not hide it."""
    rows = store.player("Erkka Niini").connections(top=1000)
    unresolved = [r for r in rows if not r["resolved"]]
    assert [r["person_key"] for r in unresolved] == ["ni nobodysson"]
    assert unresolved[0]["assists_given"] == 1


def test_connections_exclude_yourself(store):
    player = store.player("Erkka Niini")
    assert player.person_key not in {r["person_key"] for r in player.connections(top=1000)}


def test_connections_honour_the_same_filters_as_scoring(store):
    player = store.player("Hotari Roni")
    everything = sum(r["passes"] for r in player.connections(top=1000))
    recent = sum(r["passes"] for r in player.connections(top=1000, since=2020))
    assert 0 < recent <= everything


# --- the escape hatch -------------------------------------------------------


def test_sql_reads_but_never_writes(store):
    assert store.sql("SELECT COUNT(*) AS n FROM points")[0]["n"] == 83
    with pytest.raises(ValueError):
        store.sql("DELETE FROM points")
    with pytest.raises(sqlite3.OperationalError):
        store.conn.execute("DELETE FROM points")


def test_a_missing_store_says_how_to_build_it(tmp_path):
    with pytest.raises(FileNotFoundError) as exc:
        Store(tmp_path / "nope.sqlite")
    assert "ultiorg store" in str(exc.value)


@CORPUS
def test_the_composition_api_agrees_with_the_team_query_on_the_real_corpus():
    """The person query and the team query must agree on who leads defense-initiated
    scoring. They join differently — one by side, one by roster attribution — so the
    gap between them is exactly the names the rosters do not cover."""
    with Store(Path("data/store.sqlite")) as real:
        top = real.sql(
            "SELECT scorer_person AS person, COUNT(*) AS n FROM points"
            " WHERE possession_known = 1 AND possession_team = scoring_team"
            " GROUP BY 1 ORDER BY n DESC LIMIT 1"
        )[0]
        leader = real.player(top["person"])
        assert leader.scoring(possession="defense")["goals"] == top["n"] >= 300
