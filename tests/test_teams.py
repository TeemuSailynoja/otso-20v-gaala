"""The focus-team predicate: `teams.yaml` in, three scopes out.

The library must not know that Otso exists, and the gala must not lose a squad
name: a predicate that quietly drops "Karhuvaarit" drops that squad's games and
every player who only ever played in them.
"""

import pytest

from ultiorg.teams import FocusTeam, load_focus_team

TEAMS_YAML = "teams.yaml"


@pytest.fixture(scope="module")
def focus():
    team = load_focus_team(TEAMS_YAML)
    assert team is not None, "teams.yaml must be committed: the build needs it"
    return team


def test_the_gala_config_names_every_squad_it_always_counted(focus):
    """The set `build_site_data` used before Phase 8, pinned.

    Measured then: a three-pattern list (`otso`, `grizzly`, `polar`) disagreed
    with the site for 13 players, because the site also counted Hukka and
    Karhuvaarit.
    """
    for name in ("Otso", "Otso 2", "Otso 3", "OTSO", "Otso Grizzly", "Otso Polar",
                 "Otso Hukka", "Karhuvaarit"):
        assert focus.matches(name), name


def test_the_development_squad_counts_as_the_club(focus):
    """Otso Akatemia is an Otso squad. UFO Akatemia is not ours.

    The club substring decides membership, so no exclusion rule is needed to
    keep another club's development squad out. `exclude: [akatemia]` used to
    remove *our* development squad instead, and it did so unevenly: the career
    table, the pass network, the co-occurrence matrix and the win/loss record
    dropped 38 games and 866 points, while the defense view — a different
    predicate — counted them. It also dropped 37 season-card rows carrying 443
    goals, 442 assists and 369 player-games, and left three players who only
    ever turned out for Akatemia out of the site entirely.
    """
    assert focus.matches("Otso Akatemia")
    assert focus.is_akatemia("Otso Akatemia")
    assert focus.is_family("Otso Akatemia")
    # somebody else's development squad is not ours at all
    assert not focus.matches("UFO Akatemia")
    assert not focus.is_akatemia("UFO Akatemia")
    assert not focus.is_family("UFO Akatemia")
    # counting it does not make it the flagship: `years_otso.json` stays flagship
    assert not focus.is_main("Otso Akatemia")


@pytest.mark.parametrize("name", ["Otso", "OTSO", "Otso 1", "Otso-1", "Otso1",
                                  "Otso Grizzly", "Otso Polar"])
def test_main_is_the_flagship_squad(name, focus):
    assert focus.is_main(name)


@pytest.mark.parametrize("name", ["Otso 2", "Otso 3", "Otso Hukka", "Karhuvaarit",
                                  "Otso Akatemia", "UFO", "Tallinn Thunder"])
def test_main_excludes_the_rest(name, focus):
    assert not focus.is_main(name)


def test_opponents_are_not_the_club(focus):
    for name in ("UFO", "Tallinn Thunder", "Terror", "LeKi", "Saints", "UFBG"):
        assert not focus.is_family(name), name


def test_canonical_name_folds_scraped_variants(focus):
    assert focus.canonical_name("OTSO 2") == "Otso 2"
    assert focus.canonical_name("Otso2") == "Otso 2"
    assert focus.canonical_name("otsogrizzly") == "Otso Grizzly"
    # substring fallback catches a squad with no exact key
    assert focus.canonical_name("Otso Polar B") == "Otso Polar"
    # the development squad keeps its own label rather than folding onto Otso
    assert focus.canonical_name("Otso Akatemia") == "Otso Akatemia"
    # an opponent is returned unchanged: this is not a name normaliser
    assert focus.canonical_name("Tallinn Thunder") == "Tallinn Thunder"


def test_canonical_name_unwraps_the_away_team_artifact(focus):
    """Some season cards write the fixture as "Terror - Otso 2".

    The part after " - Otso" is the squad, so the label is ours, not the
    opponent's: printing "Terror - Otso 2" as a team in our own table would
    invent a club.
    """
    assert focus.canonical_name("Terror - Otso 2") == "Otso 2"
    assert focus.canonical_name("UFO - Otso") == "Otso"


def test_another_club_works_with_the_same_class():
    """No Otso knowledge is baked in: a different config gives different answers."""
    ufo = FocusTeam(name="UFO", include=("ufo",), exclude=("akatemia",), akatemia=("ufo",),
                    main=frozenset({"ufo"}))
    assert ufo.matches("UFO") and ufo.is_main("UFO")
    assert not ufo.matches("Otso")
    assert ufo.is_akatemia("UFO Akatemia") and not ufo.is_akatemia("Otso Akatemia")


def test_missing_config_means_no_focus_not_a_guess(tmp_path):
    assert load_focus_team(None) is None
    assert load_focus_team(tmp_path / "absent.yaml") is None
