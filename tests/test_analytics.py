"""The analytics views, on a hand-sized corpus.

These are the builders the gala page is made of. The corpus-wide numbers are
pinned in `test_store.py`; what is pinned here is the *rule* each view encodes —
which side of the field a point belongs to, which squad counts, which season
decides a medal — because those are the rules that were previously spread over
1,765 lines of site script and disagreed with each other.
"""

import pytest

from ultiorg.aliases import PersonKeys
from ultiorg.analytics import (
    build_career_stats,
    build_cooccurrence,
    build_defense_stats,
    build_frenemies,
    build_pass_network,
    build_trophies,
    build_years,
)
from ultiorg.teams import FocusTeam

FOCUS = FocusTeam(
    name="Otso",
    include=("otso",),
    exclude=("akatemia",),
    akatemia=("otso",),
    main=frozenset({"otso"}),
    canonical={"otso": "Otso", "otso2": "Otso 2"},
)

SEASON_NAMES = {"2024.1": "Kesä 2024", "2023.2": "Talvi 2023", "2024.F": "Finaalit"}


def _point(score, scorer, passer="", possession="home", known=1):
    """One row of the point table.

    `possession` is the side that started the point on *defense*, which is what
    `parse_gameplay.apply_possession` records; `known=0` means the half-opening
    possession could not be established and the point stays unattributed.
    """
    return {
        "type": "point",
        "score": score,
        "scorer": scorer,
        "passer": passer,
        "possession": possession if known else None,
        "possession_known": known,
    }


def _game(game_id, season_id, home, away, home_score, away_score, home_players,
          away_players, points):
    return {
        "game_id": game_id,
        "season_id": season_id,
        "home_team": home,
        "away_team": away,
        "home_score": home_score,
        "away_score": away_score,
        "gameplay": {
            "home_team": home, "away_team": away,
            "home_score": home_score, "away_score": away_score,
            "home_players": [{"id": str(i), "name": n} for i, n in enumerate(home_players, 1)],
            "away_players": [{"id": str(i), "name": n} for i, n in enumerate(away_players, 10)],
            "points": points,
        },
    }


# Otso (main) beats UFO. Aki scores off a Roni pass while starting on defense;
# Roni scores on offense; Uno scores for the opponent.
GAME_MAIN = _game(
    "1", "2024.1", "Otso", "UFO", 3, 1,
    ["Aki Vehtari", "Roni Hotari"], ["Ufo Uno"],
    [_point("1-0", "Aki Vehtari", "Roni Hotari", possession="home"),
     _point("2-0", "Roni Hotari", possession="guest"),
     _point("3-1", "Ufo Uno", possession="guest")],
)

# Otso 2 (a squad of the club, not a main one) beats Terror in a winter season.
# One point has no established possession.
GAME_SECOND = _game(
    "2", "2023.2", "Otso 2", "Terror", 6, 2,
    ["Aki Vehtari"], ["Tim Terror"],
    [_point("1-0", "Aki Vehtari", possession="guest"),
     _point("2-0", "Aki Vehtari", known=0)],
)

# An intra-club derby: an opponent for nobody.
GAME_DERBY = _game(
    "3", "2024.1", "Otso", "Otso 2", 5, 3,
    ["Roni Hotari"], ["Aki Vehtari"], [],
)

GAMES = [GAME_MAIN, GAME_SECOND, GAME_DERBY]

SEASONS = [
    {
        "id": "2024.1",
        "name": "Kesä 2024",
        "teams": [
            {"name": "Otso", "players": [
                {"name": "Aki Vehtari", "games": 5, "goals": 9, "assists": 3},
                {"name": "Roni Hotari", "games": 4, "goals": 7, "assists": 11},
            ]},
            {"name": "UFO", "players": [
                {"name": "Ufo Uno", "games": 5, "goals": 12, "assists": 1},
            ]},
        ],
    },
    {
        "id": "2024.F",
        "name": "Finaalit",
        "teams": [],
        "placements": [
            {"division": "avoin", "team_name": "Otso", "placement": "Kulta"},
            {"division": "avoin", "team_name": "Otso 2", "placement": "7."},
            {"division": "avoin", "team_name": "UFO", "placement": "Hopea"},
            {"division": "naiset", "team_name": "Otso N", "placement": "Kulta"},
        ],
    },
]


# --- career -----------------------------------------------------------------
def test_career_games_take_the_larger_source_never_the_sum():
    """Aki has 5 card games and 2 scraped roster appearances in 2024.1: 5, not 7.

    Summing the two counted most careers twice — 16,424 site-wide against 9,061
    card games — and every Pts/Game figure inherited the inflated denominator.
    The winter season adds one more, from the roster alone: 6 in total.
    """
    stats = build_career_stats(SEASONS, GAMES, FOCUS, season_names=SEASON_NAMES)
    aki = stats["aki vehtari"]
    assert aki["summer_games"] == 5 and aki["winter_games"] == 1
    assert aki["games"] == 6
    assert stats["hotari roni"]["games"] == 4  # card 4 beats 2 roster appearances


def test_career_goals_come_from_the_card_plus_the_point_table():
    stats = build_career_stats(SEASONS, GAMES, FOCUS, season_names=SEASON_NAMES)
    aki, roni = stats["aki vehtari"], stats["hotari roni"]
    assert (aki["goals"], aki["assists"]) == (12, 3)     # card 9+3, +3 scored
    assert (roni["goals"], roni["assists"]) == (8, 12)   # card 7+11, +1 scored +1 passed
    assert aki["total"] == aki["goals"] + aki["assists"]


def test_career_covers_only_the_focus_club():
    stats = build_career_stats(SEASONS, GAMES, FOCUS, season_names=SEASON_NAMES)
    assert "ufo uno" not in stats, "an opponent's card row is not our career table"
    assert "tim terror" not in stats


def test_career_lists_every_season_an_appearance_was_recorded():
    """A roster appearance in a season with no card row still belongs to the career.

    The old builder counted those games but never the season, so a player's
    `games` included a season his `seasons` list did not mention.
    """
    stats = build_career_stats(SEASONS, GAMES, FOCUS, season_names=SEASON_NAMES)
    aki = stats["aki vehtari"]
    assert aki["seasons"] == ["2023.2", "2024.1"]
    assert aki["years"] == [2023, 2024]
    assert aki["season_types"] == {"summer": [2024], "winter": [2023], "other": []}
    assert aki["first_year"] == 2023 and aki["last_year"] == 2024
    assert aki["winter_games"] == 1 and aki["summer_games"] == 5


def test_a_development_appearance_is_an_appearance_but_not_a_squad_label():
    """Akatemia is the club, so its games count; its label does not join `teams`.

    `is_family` decides who is on the field, `matches` decides what the squad is
    called. Using one predicate for both put "Otso Akatemia" in main-squad
    careers.
    """
    game = _game("8", "2024.1", "Otso Akatemia", "Terror", 4, 1,
                 ["Aki Vehtari"], ["Tim Terror"],
                 [_point("1-0", "Aki Vehtari", possession="guest")])
    stats = build_career_stats(SEASONS, [game], FOCUS, season_names=SEASON_NAMES)
    aki = stats["aki vehtari"]
    assert aki["games"] == 5, "the card season still decides the count"
    assert aki["teams"] == ["Otso"]

# --- defense ----------------------------------------------------------------
def test_defense_is_a_fact_about_the_point_not_the_team():
    """Aki's first point was scored after we started the point on defense."""
    stats = build_defense_stats(GAMES, FOCUS)
    aki = stats["aki vehtari"]
    assert aki["defense_points"] == 1
    assert aki["offense_points"] == 2  # one offense point, one unattributed
    assert stats["hotari roni"]["defense_points"] == 0
    assert stats["hotari roni"]["offense_points"] == 1


def test_unattributed_possession_counts_as_offense_and_stays_countable():
    """287 of 18,770 points have no established half-opening possession.

    They are published as offense rather than dropped, and the honest variant
    stays computable because `possession_known` says which is which.
    """
    stats = build_defense_stats([GAME_SECOND], FOCUS)
    aki = stats["aki vehtari"]
    assert aki["offense_points"] == 2
    only_known = [p for p in GAME_SECOND["gameplay"]["points"] if p["possession_known"]]
    assert len(only_known) == 1


def test_defense_never_credits_an_opponent():
    stats = build_defense_stats(GAMES, FOCUS)
    assert "ufo uno" not in stats


# --- passes and teammates ---------------------------------------------------
def test_pass_network_is_directed_and_mirrored():
    net = build_pass_network(GAMES, FOCUS, ["Aki Vehtari", "Roni Hotari"])
    assert net["received"]["Aki Vehtari"] == {"Roni Hotari": 1}
    assert net["given"]["Roni Hotari"] == {"Aki Vehtari": 1}
    assert "Roni Hotari" not in net["received"], "Roni's point had no passer"


def test_cooccurrence_counts_pairs_on_a_squad_together():
    cooc = build_cooccurrence(GAMES, FOCUS, ["Aki Vehtari", "Roni Hotari"])
    # once in the derby, once more where they lined up on opposite Otso squads:
    # both sides are the club, so they were teammates in the game
    assert cooc["Aki Vehtari"]["Roni Hotari"] == 2
    assert cooc["Roni Hotari"]["Aki Vehtari"] == 2
    assert "Ufo Uno" not in cooc


def test_frenemies_skips_intra_club_games_and_counts_the_opponent():
    ranked = build_frenemies(GAMES, FOCUS)
    assert [e["name"] for e in ranked] == ["Ufo Uno"]
    uno = ranked[0]
    assert (uno["goals"], uno["assists"], uno["total"]) == (1, 0, 1)
    assert uno["games"] == 1 and uno["wins"] == 0 and uno["teams"] == ["UFO"]
    assert uno["rank"] == 1


def test_frenemies_ranks_ties_by_name():
    """A stable sort over insertion order made rank 15/16 swap between runs."""
    a = build_frenemies(GAMES, FOCUS)
    b = build_frenemies(list(reversed(GAMES)), FOCUS)
    assert [e["name"] for e in a] == [e["name"] for e in b]


# --- years ------------------------------------------------------------------
def test_years_scope_main_is_the_flagship_squad_only():
    years = build_years(GAMES, FOCUS, scope="main", season_names=SEASON_NAMES)
    assert set(years) == {"2024"}
    assert years["2024"]["matches"] == 2          # the derby counts: Otso is main
    assert years["2024"]["wins"] == 2
    assert (years["2024"]["goals_for"], years["2024"]["goals_against"]) == (8, 4)
    assert years["2024"]["roster_players"] == 2


def test_years_scope_all_adds_the_other_squads():
    years = build_years(GAMES, FOCUS, scope="all", season_names=SEASON_NAMES)
    assert set(years) == {"2023", "2024"}
    assert years["2023"]["matches"] == 1
    assert years["2023"]["goals_for"] == 6


def test_years_season_type_filter_uses_the_season_name():
    years = build_years(GAMES, FOCUS, scope="all", season_type_filter="winter",
                        season_names=SEASON_NAMES)
    assert set(years) == {"2023"}


def test_years_roster_is_person_keys_not_display_names():
    """The page resolves keys to names; the library does not print names."""
    years = build_years(GAMES, FOCUS, season_names=SEASON_NAMES)
    assert years["2024"]["roster_names"] == ["aki vehtari", "hotari roni"]


# --- trophies ---------------------------------------------------------------
def test_trophies_count_only_season_deciding_events():
    record = build_trophies(SEASONS, FOCUS, events={"2024.F": (2024, "summer")})
    assert record["totals"]["all"]["gold"] == 1
    assert record["totals"]["all"]["podiums"] == 1
    season = [r for r in record["seasons"] if r["event"] == "2024.F"][0]
    assert (season["medal"], season["team"]) == ("gold", "Otso")
    # every focus squad in the division is listed, best first, opponents never
    assert [(e["team"], e["placement"]) for e in season["entries"]] == [("Otso", "Kulta"), ("Otso 2", "7.")]


def test_trophies_ignore_other_divisions_and_other_clubs():
    record = build_trophies(SEASONS, FOCUS, events={"2024.F": (2024, "summer")})
    season = [r for r in record["seasons"] if r["event"] == "2024.F"][0]
    assert season["medal"] == "gold" and season["team"] == "Otso"
    assert all(e["team"] != "UFO" for e in season["entries"])


def test_trophies_record_a_season_that_was_not_played():
    record = build_trophies([], FOCUS, events={"2020.2": (2020, "winter")},
                            not_played=["2020.2"])
    season = record["seasons"][0]
    assert season["played"] is False and season["medal"] is None


def test_trophies_keep_a_row_for_an_event_with_no_scoped_data():
    """A missing file must show as a gap, not silently shorten the cabinet."""
    record = build_trophies([], FOCUS, events={"2015.F": (2015, "summer")})
    assert record["seasons"] == [{
        "year": 2015, "season": "summer", "event": "2015.F", "medal": None,
        "team": None, "placement": None, "played": True, "entries": [],
    }]


# --- person keys ------------------------------------------------------------
def test_two_spellings_of_one_person_are_one_row():
    """Point rows write `Last First`, rosters `First Last`, and spellings drift.

    `config/aliases.json` is the only place two spellings become one person, and
    it is asserted by a human, never inferred.
    """
    persons = PersonKeys({"aukusti väänänen": "touko väänänen"})
    game = _game("9", "2024.1", "Otso", "UFO", 2, 0, ["Touko Väänänen"], ["Ufo Uno"],
                 [_point("1-0", "Aukusti Väänänen", possession="home"),
                  _point("2-0", "Touko Väänänen", possession="home")])
    defense = build_defense_stats([game], FOCUS, persons)
    assert defense["touko väänänen"]["defense_points"] == 2
    assert "aukusti väänänen" not in defense

    career = build_career_stats([], [game], FOCUS, persons, SEASON_NAMES)
    assert career["touko väänänen"]["goals"] == 2
    assert career["touko väänänen"]["games"] == 1


def test_a_point_row_that_joins_no_roster_is_not_credited():
    """Without a person key, a spelling that only appears in the point table is a
    different person as far as the builders can tell — which is why the alias
    file exists and why the gap used to be invisible."""
    game = _game("9", "2024.1", "Otso", "UFO", 1, 0, ["Touko Väänänen"], ["Ufo Uno"],
                 [_point("1-0", "Aukusti Väänänen", possession="home")])
    defense = build_defense_stats([game], FOCUS)
    assert defense == {}
