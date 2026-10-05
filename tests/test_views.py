"""The event-level views: scorestatus, statistics, allteams/allclubs, and CSV.

Fixtures are live pages archived 2026-10-06 (KESA2026 is the instance's current
season, so the CSV exports are available for it and 403 for every past season).
"""

import pytest

from conftest import read_fixture

from ultiorg import parsers


# --- scorestatus: one event's whole scoreboard, with IDs --------------------


def _scorestatus():
    return parsers.parse_scorestatus(read_fixture("scorestatus_3300.html"), "3300")


def test_scorestatus_is_one_row_per_player_and_every_row_has_an_id():
    rows = _scorestatus()
    assert len(rows) == 123
    assert all(r["player_id"] for r in rows), "a scoreboard row without an ID"
    assert len({r["player_id"] for r in rows}) == len(rows)


def test_scorestatus_is_rendered_once_not_twice():
    """The page renders this table twice (page_middle + content).

    Measured: scanning the document yields 246 rows for 123 players. The parser
    scopes to `div.content`; if that ever regresses, this is the tripwire.
    """
    assert len(_scorestatus()) == 123


def test_scorestatus_totals_and_ranks_are_consistent():
    rows = _scorestatus()
    assert all(r["total"] == r["assists"] + r["goals"] for r in rows)
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
    top = rows[0]
    assert (top["name"], top["team"], top["gp"], top["total"]) == (
        "Okko Winqvist", "Helsinki Ultimate Empire", 8, 41,
    )
    assert all(r["series_id"] == "3300" for r in rows)


# --- statistics: event → series ID, plus the top three of every event -------


def _statistics():
    return parsers.parse_statistics(read_fixture("statistics_playerscoreboard.html"))


def test_statistics_maps_every_event_to_a_series_id():
    events = _statistics()
    assert len(events) == 231
    assert all(e["series_id"] for e in events)
    assert len({e["series_id"] for e in events}) == len(events)


def test_statistics_groups_by_section_and_division():
    events = _statistics()
    sections = {e["section"] for e in events}
    assert sections == {"Sisä", "Ulko", "Ranta"}, "indoor / outdoor / beach"
    assert all(e["division"] for e in events)
    talvi = [e for e in events if e["event"] == "Talvi 2025"]
    assert {e["division"] for e in talvi} >= {"Avoin", "Naiset", "Mixed"}


def test_statistics_top_three_carry_ids_and_additive_totals():
    events = _statistics()
    for event in events:
        assert 1 <= len(event["top"]) <= 3
        for entry in event["top"]:
            assert entry["player_id"], event
            assert entry["name"] and entry["team"]
            assert entry["total"] == entry["assists"] + entry["goals"], event
    avoin = next(e for e in events if e["event"] == "Talvi 2025" and e["division"] == "Avoin")
    assert avoin["series_id"] == "3295"
    assert avoin["top"][0]["name"] == "Santtu Lehto"
    assert avoin["top"][0]["total"] == 87


# --- allteams / allclubs: the instance's roster of organisations ------------


def test_allteams_index_has_id_name_division():
    teams = parsers.parse_allteams(read_fixture("allteams_all.html"))
    assert len(teams) == 317
    assert len({t["id"] for t in teams}) == len(teams)
    assert all(t["id"].isdigit() and t["name"] for t in teams)
    assert all(t["division"] for t in teams), "division comes from the [..] suffix"
    otso = [t for t in teams if t["name"] == "Otso"]
    assert otso and otso[0]["division"] == "Avoin"


def test_allteams_skips_the_grid_padding():
    """The grid pads its last row with a `teamcard&team=` cell that has no ID."""
    page = read_fixture("allteams_all.html")
    assert page.count("teamcard&amp;team='") == 1
    teams = parsers.parse_allteams(page)
    assert all(t["id"] for t in teams)
    assert all(t["name"] != "[]" for t in teams)


def test_allclubs_index():
    clubs = parsers.parse_allclubs(read_fixture("allclubs_all.html"))
    assert len(clubs) == 106
    assert len({c["id"] for c in clubs}) == len(clubs)
    assert all(c["id"].isdigit() and c["name"] for c in clubs)


# --- the series menu: where series IDs live --------------------------------


def test_series_menu_is_the_only_source_of_series_ids():
    """A season page's left menu lists one series per division.

    `series` is a different ID space from `season`: KESA2026 → 3300 Avoin,
    3301 Naiset, 3302 Mixed, 3303 Juniorit U17. `scorestatus` takes the series,
    so without this menu a season's scoreboards cannot be enumerated.
    """
    series = parsers.parse_series_menu(read_fixture("games_KESA2026.html"))
    assert [(s["series_id"], s["name"]) for s in series] == [
        ("3300", "Avoin"),
        ("3301", "Naiset"),
        ("3302", "Mixed"),
        ("3303", "Juniorit U17"),
    ]


# --- the CSV path: real endpoints, and a guard against the export page ------


def _csv(name: str) -> str:
    return read_fixture(name)


def test_csv_players_is_the_current_season_roster_with_totals():
    rows = parsers.parse_csv_players(_csv("playerscsv_KESA2026.csv"), "KESA2026")
    assert len(rows) == 364
    assert all(r["last_name"] for r in rows)
    assert all(r["total"] == r["assists"] + r["goals"] for r in rows)
    assert all(r["season_id"] == "KESA2026" for r in rows)
    # No player ID anywhere in this export — that is why identity comes from
    # allplayers/playercard, not from CSV.
    assert not any("player_id" in r for r in rows)


def test_csv_teams_games_results_pools_spirit_all_parse():
    teams = parsers.parse_csv_teams(_csv("teamscsv_KESA2026.csv"), "KESA2026")
    games = parsers.parse_csv_games(_csv("gamescsv_KESA2026.csv"), "KESA2026")
    results = parsers.parse_csv_results(_csv("resultscsv_KESA2026.csv"), "KESA2026")
    pools = parsers.parse_csv_pools(_csv("poolscsv_KESA2026.csv"), "KESA2026")
    spirit = parsers.parse_csv_spirit(_csv("spiritcsv_KESA2026.csv"), "KESA2026")
    assert len(teams) == 22 and all(t["name"] for t in teams)
    assert len(games) == 80 and all(g["home_team"] for g in games)
    assert len(results) == 80 and len(pools) == 61 and len(spirit) == 82
    assert all(p["team"] and p["standing"] is not None for p in pools)
    assert all(s["team"] and s["by_team"] for s in spirit)
    assert all(s["total"] is not None for s in spirit)


def test_csv_parsers_reject_the_export_page_instead_of_returning_empty_rows():
    """The old failure mode: the export page parsed as CSV gave 250 empty rows.

    `?view=ext/export` is HTML that *links* the CSVs. Feeding it to a CSV parser
    is now an error, not a silently empty dataset.
    """
    page = read_fixture("export_page.html")
    for parse in (parsers.parse_csv_teams, parsers.parse_csv_players,
                  parsers.parse_csv_games, parsers.parse_csv_results,
                  parsers.parse_csv_pools, parsers.parse_csv_spirit):
        with pytest.raises(parsers.NotCsvError):
            parse(page, "KESA2026")


def test_export_page_links_all_six_csv_endpoints():
    """The export page is still how the endpoint names are discovered."""
    page = read_fixture("export_page.html")
    for kind in ("players", "teams", "games", "pools", "results", "spirit"):
        assert f"ext/{kind}csv.php" in page


def test_csv_fetcher_knows_only_the_six_kinds():
    from ultiorg import fetch_csv
    from ultiorg.fetcher import CSV_KINDS

    assert CSV_KINDS == ("players", "teams", "games", "pools", "results", "spirit")
    with pytest.raises(ValueError):
        fetch_csv("playerss", "KESA2026")


# --- live check that the archived shapes still match the site ---------------


@pytest.mark.network
def test_live_event_views_still_parse():
    from ultiorg import (fetch_allclubs, fetch_allteams, fetch_games_page,
                         fetch_scorestatus, fetch_statistics)

    teams = parsers.parse_allteams(fetch_allteams())
    clubs = parsers.parse_allclubs(fetch_allclubs())
    assert len(teams) >= 300 and len(clubs) >= 100

    series = parsers.parse_series_menu(fetch_games_page("KESA2026"))
    assert series, "the current season must expose its series menu"
    scoreboard = parsers.parse_scorestatus(fetch_scorestatus(series[0]["series_id"]),
                                           series[0]["series_id"])
    assert scoreboard and all(row["player_id"] for row in scoreboard)

    events = parsers.parse_statistics(fetch_statistics("KESA2026"))
    assert len(events) >= 200
