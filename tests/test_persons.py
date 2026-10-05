"""Person keys: the rule that turns a cluster of pelikone ids into one site key.

The measured fact behind this module is that pelikone re-issues a player id for
every registration, so an id is a *season of registration*, not a person. Keying
anything on a single id splits one player across the site; keying it on a name
splits him again by spelling. The key is the lowest id in the cluster, and
`name:<canon>` is what a name that pelikone never registered gets.
"""

from ultiorg.aliases import PersonKeys
from ultiorg.persons import (
    PSEUDO_PREFIX,
    PersonIds,
    collect_id_clusters,
    is_person,
)


def _game(home_players, away_players, game_id="7", season_id="2024.1"):
    return {
        "game_id": game_id,
        "season_id": season_id,
        "home_team": "Otso",
        "away_team": "UFO",
        "gameplay": {"home_players": home_players, "away_players": away_players, "points": []},
    }


def _season(*teams):
    return {"id": "2024.1", "teams": [{"name": n, "players": ps} for n, ps in teams]}


# --- what counts as a person ------------------------------------------------
def test_a_callahan_is_an_event_not_a_player():
    """The passer cell of a Callahan names the interception, and 67 real points
    read that way. Counting it as a person invents a player with 67 assists."""
    assert not is_person("Callahan-maali")
    assert not is_person("callahan-maali")
    assert is_person("Roni Hotari")
    assert not is_person("")
    assert not is_person("   ")


# --- id clusters ------------------------------------------------------------
def test_one_person_is_the_union_of_the_ids_his_rosters_used():
    games = [
        _game([{"id": "10", "name": "Roni Hotari"}], []),
        _game([{"id": "421", "name": "Roni Hotari"}], [], game_id="8"),
    ]
    clusters = collect_id_clusters(games)
    assert clusters["hotari roni"] == {"10", "421"}


def test_season_cards_contribute_ids_too():
    seasons = [_season(("Otso", [{"id": "3", "name": "Aki Vehtari"}]))]
    clusters = collect_id_clusters([], seasons)
    assert clusters["aki vehtari"] == {"3"}


def test_an_asserted_alias_merges_the_clusters():
    """Two spellings become one person only through config/aliases.json — and
    then their ids join one cluster, which is what makes the site key one key."""
    persons = PersonKeys({"aukusti touko väänänen": "touko väänänen"})
    games = [
        _game([{"id": "55", "name": "Touko Väänänen"}], []),
        _game([{"id": "61", "name": "Aukusti Touko Väänänen"}], [], game_id="9"),
    ]
    clusters = collect_id_clusters(games, persons=persons)
    assert clusters["touko väänänen"] == {"55", "61"}
    assert "aukusti touko väänänen" not in clusters


def test_a_name_with_no_roster_id_gets_no_cluster():
    """Point rows carry no ids. Identity is built from rosters, so a name that
    never appears in one has no cluster — and gets a pseudo-key, not an id."""
    games = [_game([], [])]
    games[0]["gameplay"]["points"] = [{"type": "point", "scorer": "Mikael Vitikainen"}]
    assert collect_id_clusters(games) == {}


# --- the site key -----------------------------------------------------------
def test_the_site_key_is_the_lowest_id_and_ids_compare_numerically():
    ids = PersonIds.build({"hotari roni": ["1000", "999", "9"]}, {"hotari roni": "Roni Hotari"})
    assert ids.site_key("hotari roni") == "9"
    assert ids.clusters["hotari roni"] == ("9", "999", "1000")


def test_a_person_with_no_id_gets_a_pseudo_key():
    ids = PersonIds.build({"mikael vitikainen": []}, {})
    assert ids.site_key("mikael vitikainen") == PSEUDO_PREFIX + "mikael vitikainen"
    assert ids.pseudo == {"name:mikael vitikainen": "mikael vitikainen"}


def test_an_unknown_person_still_gets_a_key():
    """Minting, not dropping: a name in the point table has to be countable
    somewhere, and the `name:` prefix says it is not a pelikone id."""
    ids = PersonIds.build({"aki vehtari": ["3"]}, {})
    assert ids.site_key("jarno sihvo") == "name:jarno sihvo"
    assert ids.site_key("") == ""


def test_rekey_turns_builder_output_into_site_keys():
    ids = PersonIds.build({"aki vehtari": ["3"], "mikael vitikainen": []}, {})
    assert ids.rekey({"aki vehtari": 12, "mikael vitikainen": 1}) == {"3": 12, "name:mikael vitikainen": 1}


def test_multi_id_is_the_reason_names_json_exists():
    ids = PersonIds.build({"hotari roni": ["9", "999"], "aki vehtari": ["3"]}, {})
    assert ids.multi_id == {"9": ["9", "999"]}


def test_display_names_hang_off_the_site_key():
    ids = PersonIds.build({"hotari roni": ["9"]}, {"hotari roni": "Roni Hotari"})
    assert ids.display_of == {"9": "Roni Hotari"}
    # a person with no resolved spelling contributes no entry: the key is still
    # valid, it simply has nothing to render, and data_quality.json says so
    assert PersonIds.build({"ufo uno": []}, {}).display_of == {}
