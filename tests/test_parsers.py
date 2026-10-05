"""Characterization tests: parsers vs golden outputs on archived pages.

Plus the invariants the refactor depends on — the ones that would silently
break if a parser changed shape.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cases import CASES, to_jsonable  # noqa: E402
from conftest import GOLDEN, read_fixture  # noqa: E402

from ultiorg import parsers  # noqa: E402


def golden_name(name: str) -> Path:
    return GOLDEN / f"{name}.json"


@pytest.mark.parametrize(
    "name,fn,fixture,extra",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_parser_matches_golden(name, fn, fixture, extra):
    """The parser's output on the archived page is exactly what it was at Phase 1.

    Change a golden only on purpose: `git diff tests/golden` is the review
    surface for every parser change in later phases.
    """
    path = golden_name(name)
    assert path.exists(), f"missing golden {path}; run tests/regenerate_golden.py"
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert to_jsonable(fn(read_fixture(fixture), *extra)) == expected


# --- invariants the rest of the plan leans on -------------------------------


def test_season_list_is_the_season_universe():
    """101 seasons, and the ID space is not one format.

    The fixture is the archived snapshot (latest season `2025.3`), so it does
    not contain `KESA2026` — do not "fix" this test by expecting it. The odd
    IDs are real: `Talvi2016`, `Hallitour2`, `XSM2018`, `*JSM2018`.
    """
    seasons = parsers.parse_season_list(read_fixture("seasonlist.html"))
    assert len(seasons) == 101
    assert all(s["id"] and s["name"] and s["url"] for s in seasons)
    ids = {s["id"] for s in seasons}
    assert {"2018.1", "2025.3", "1999.2", "Talvi2016", "Hallitour2", "*JSM2018"} <= ids


def test_teams_pages_are_parsed_and_otso_filtered():
    """Both fixtures use tables.teams-table; 2025.3 has three Otso teams.

    Name case differs between seasons (`Otso` vs `OTSO`), so the Otso predicate
    must stay case-insensitive. Phase 8 replaces it with a focus-team predicate
    from the gala config.
    """
    current = parsers.parse_teams_page(read_fixture("teams_KESA2026.html"), "KESA2026")
    multi = parsers.parse_teams_page(read_fixture("teams_2025.3.html"), "2025.3")
    assert [r["name"] for r in current] == ["Otso"]
    assert [r["name"] for r in multi] == ["OTSO", "OTSO 2", "OTSO 3"]
    for row in current + multi:
        assert row["id"], row
        assert row["season_id"]
        assert parsers.is_otso_team(row["name"])


def test_old_format_teams_fallback_has_no_example_left():
    """`_parse_teams_old_format` is unreachable with the archived corpus.

    Measured: 0 of 73 cached teams pages lack `teams-table` — the site renders
    every season, including 2018.1, in the new format. The fallback was for
    pages scraped before the redesign, and the cache has since been re-fetched.
    Phase 8 decides whether to delete it; do not write a synthetic fixture for
    HTML nobody has seen.
    """
    for fixture in ("teams_KESA2026.html", "teams_2025.3.html"):
        assert "teams-table" in read_fixture(fixture)


def test_standings_carry_placement_and_team_id():
    rows = parsers.parse_standings_page(read_fixture("standings_2018.1.html"), "2018.1")
    assert {"Kulta", "6."} == {r["placement"] for r in rows}
    assert {r["team_id"] for r in rows} == {"2573", "2574"}


def test_teamcard_and_playerlist_carry_player_ids():
    card = parsers.parse_team_card(read_fixture("teamcard_3130.html"), "3130")
    assert len(card["players"]) == 14 and len(card["games"]) == 16
    assert all(p["id"] for p in card["players"])

    roster = parsers.parse_player_list(read_fixture("playerlist_2405.html"), "2405")
    assert len(roster) == 58
    assert all(p["id"] for p in roster)


def test_games_list_yields_numeric_game_ids():
    games = parsers.parse_games_list(read_fixture("games_KESA2026.html"), "KESA2026")
    assert len(games) == 10
    assert all(g["game_id"].isdigit() for g in games)
    assert {"game_id", "time", "venue", "home_team", "away_team"} <= set(games[0])


def test_season_id_helpers_classify_the_real_id_space():
    """Season IDs are not one format: `2018.1`, `KESA2026`, `Talvi 2025`.

    Pinned as-is, including the gap: a numeric summer ID (`2018.1`, "Kesä 2018")
    classifies as **unknown**, while `KESA2026` is `summer`. That gap is why
    `build_site_data.py` carries its own `season_type_map`. Phase 8 closes it in
    the library instead of working around it in the site layer.
    """
    assert parsers.extract_season_id("?view=teams&season=2018.1") == "2018.1"
    assert parsers.classify_season("2018.1", "Kesä 2018")["type"] == "unknown"
    assert parsers.classify_season("KESA2026", "Kesä 2026")["type"] == "summer"
    assert parsers.classify_season("2018.3", "Talvi 2018")["type"] == "winter"
    assert parsers.classify_season("2018.1.T2", "Tour 2")["type"] == "tour2"
    assert parsers.classify_season("2018.1F", "Finaalit")["type"] == "finals"
    assert parsers.classify_season("2018.1", "Kesä 2018")["year"] == 2018
    assert parsers.classify_season("KESA2026", "Kesä 2026")["year"] == 2026


@pytest.mark.parametrize(
    "fixture,home,away,home_score,away_score",
    [
        ("gameplay_11049_modern.html", "Suomi U20", "Otso", 5, 15),
        ("gameplay_2980_pre2015.html", "Otso", "Hukka", 17, 3),
    ],
)
def test_gameplay_fixture_shapes(fixture, home, away, home_score, away_score):
    gp = parsers.parse_gameplay(read_fixture(fixture))
    assert (gp["home_team"], gp["away_team"]) == (home, away)
    assert (gp["home_score"], gp["away_score"]) == (home_score, away_score)
    points = [p for p in gp["points"] if p["type"] == "point"]
    assert points
    # point rows are the whole game: 5+15 and 17+3 are both 20 points
    assert len(points) == home_score + away_score


def test_point_rows_carry_no_player_ids_and_never_will():
    """The constraint that forces identify.py: points are plain text names.

    Rosters on the same page carry IDs; point rows do not. If a future parser
    ever starts emitting IDs here, this test fires and identify.py can shrink.
    """
    for fixture in ("gameplay_11049_modern.html", "gameplay_2980_pre2015.html"):
        gp = parsers.parse_gameplay(read_fixture(fixture))
        for point in gp["points"]:
            if point["type"] != "point":
                continue
            assert set(point) <= {
                "type", "side", "score", "time", "passer", "scorer",
                "offense_marker", "possession", "possession_known",
            }
            for name in (point.get("passer"), point.get("scorer")):
                if name:
                    # point rows are plain text; rosters on the same page are links
                    assert "#" not in name and "http" not in name


def test_possession_is_a_fact_on_every_point():
    """Every point says who started it on defense, or admits it cannot know.

    The rule lives in the parser now (it used to be re-derived inside
    `build_defense_stats`), so the site and the fact store read one answer.
    """
    modern = parsers.parse_gameplay(read_fixture("gameplay_11049_modern.html"))
    points = [p for p in modern["points"] if p["type"] == "point"]
    assert all("possession" in p and "possession_known" in p for p in points)
    # this page carries the Hyökkäys marker, so every point is attributed
    assert all(p["possession_known"] == 1 for p in points)
    assert points[0]["possession"] == "guest"  # the marker says home attacked first

    # the pre-2015 page has no events column: the first point of each half is
    # unknown, every later point follows from the previous scorer
    old = parsers.parse_gameplay(read_fixture("gameplay_2980_pre2015.html"))
    assert not any(p.get("offense_marker") for p in old["points"] if p["type"] == "point")
    halves = sum(1 for p in old["points"] if p["type"] == "halftime")
    scored = [p for p in old["points"] if p["type"] == "point"]
    assert halves == 1
    assert {i for i, p in enumerate(scored) if p["possession_known"] == 0} == {0, 11}


def test_scorer_starts_the_next_point_on_defense():
    """The possession rule, on a hand-built game rather than a scraped one."""
    gameplay = {
        "home_players": [{"id": "1", "name": "A One"}, {"id": "2", "name": "B Two"}],
        "away_players": [{"id": "3", "name": "C Three"}],
        "points": [
            {"type": "point", "side": "guest", "scorer": "C Three"},
            {"type": "point", "side": "home", "scorer": "A One"},
            {"type": "halftime", "text": "Puoliaika"},
            {"type": "point", "side": "guest", "scorer": "C Three"},
        ],
    }
    parsers.apply_possession(gameplay)
    first_half = [p for p in gameplay["points"] if p["type"] == "point"][:2]
    # no marker: point 1 unknown, point 2 defended by the point-1 scorer's side
    assert first_half[0]["possession_known"] == 0
    assert first_half[1]["possession"] == "guest"
    # halftime clears the chain: the first point after it is unknown again
    after_half = gameplay["points"][-1]
    assert after_half["possession_known"] == 0

    gameplay["points"][0]["offense_marker"] = "home"
    parsers.apply_possession(gameplay)
    points = [p for p in gameplay["points"] if p["type"] == "point"]
    assert points[0]["possession"] == "guest"      # home attacked first
    assert points[1]["possession"] == "guest"      # guest scored, so guest defends
    assert points[2]["possession"] == "home"       # halftime flips the starter


def test_roster_names_use_a_non_breaking_space():
    """Every roster name in both archived games separates names with U+00A0.

    Measured: 50 of 50 roster names. Any name matching that does not normalize
    NBSP will miss every player. identify.py must fold it to a plain space.
    """
    for fixture in ("gameplay_11049_modern.html", "gameplay_2980_pre2015.html"):
        gp = parsers.parse_gameplay(read_fixture(fixture))
        names = [p["name"] for side in ("home_players", "away_players") for p in gp[side]]
        assert names
        assert all("\xa0" in n for n in names)


def test_hyokkausys_marker_is_present_in_both_archived_games():
    """The possession rule's anchor for point 1 (see build_defense_stats)."""
    for fixture in ("gameplay_11049_modern.html", "gameplay_2980_pre2015.html"):
        assert "Hyökkäys" in read_fixture(fixture)


# --- a bug, recorded rather than pinned -------------------------------------
#
# `?view=ext/export` is the "Tiedon vienti" HTML page, not CSV. Feeding it to a
# CSV parser used to yield 250 rows of empty strings, silently. Phase 6 fixed
# the path: the real endpoints are `ext/<kind>csv.php` (current season only —
# 403 for past seasons), and `tests/test_views.py` now asserts that the export
# page raises `NotCsvError` instead of parsing to nothing.


# --- live smoke test (opt-in) -----------------------------------------------


@pytest.mark.network
def test_allplayers_and_playercard_resolve_a_known_id():
    """One polite pair of requests: the index resolves a name, the card parses."""
    from ultiorg.fetcher import fetch_url
    from ultiorg.config import BASE_URL

    index = fetch_url(f"{BASE_URL}/?view=allplayers")
    assert index and "playercard" in index

    card = fetch_url(f"{BASE_URL}/?view=playercard&series=0&player=27441")
    assert card and "Antti Elonheimo" in card
