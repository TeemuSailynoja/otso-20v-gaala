"""Season identity over the real ID space.

pelikone season IDs are seven different formats in one column, and the two
questions asked of them (which year, which half of the year) have different
sources. The old site builder answered both from the ID and got three of them
wrong; these are the cases it got wrong, pinned.
"""

import pytest

from ultiorg.seasons import classify, season_stage, season_type, season_year

# (id, name, year) — the year is in the ID for most, in the name for the rest.
@pytest.mark.parametrize(
    "season_id,name,year",
    [
        ("2018.1", "Talvi 2018", 2018),
        ("2020.1", "Kesä 2020", 2020),
        ("2019.T3", "Tour 3", 2019),
        ("2018.F", "Finaalit", 2018),
        ("KESA2026", "Kesä 2026", 2026),
        ("Talvi2016", "Talvi 2016", 2016),
        ("SM2022K", "SM 2022", 2022),
        ("XSM2018", "XSM 2018", 2018),
        ("*JSM2018", "JSM 2018", 2018),
        ("1999.2", "Kausi 1999", 1999),
        # year only in the name — the old extractor returned None or a wrong year
        ("2017F", "Kesä 2017 Finaalit", 2017),
        ("Hallitour2", "Talvi 2014", 2014),
        ("BMSM2", "Ranta SM 2019", 2019),
        ("JSM17", "Juniori SM 2017", 2017),
    ],
)
def test_season_year(season_id, name, year):
    assert season_year(season_id, name) == year


def test_year_without_a_year_anywhere_is_none_not_a_guess():
    assert season_year("Hallitour", "") is None
    assert season_year("", "") is None


def test_bmsm2_is_not_2002():
    """The old extractor read the trailing "2" of `BMSM2` as a year: 2000 + 2.

    It then filed that season's games in a year the club did not exist in. The
    name ("Ranta SM 2019") is the only honest source.
    """
    assert season_year("BMSM2", "Ranta SM 2019") == 2019
    assert season_year("BMSM2", "") is None


# (id, name, type) — the numeric suffix lies, the name does not.
@pytest.mark.parametrize(
    "season_id,name,kind",
    [
        ("2018.1", "Kesä 2018", "summer"),
        ("2018.3", "Talvi 2018", "winter"),
        ("2020.1", "Kesä 2020", "summer"),
        ("BMSM2", "Ranta SM 2019", "beach"),
        ("KESA2026", "Kesä 2026", "summer"),
        ("Talvi2016", "Talvi 2016", "winter"),
        ("2019.T3", "Tour 3", "other"),
    ],
)
def test_season_type_reads_the_name_first(season_id, name, kind):
    assert season_type(season_id, name) == kind


def test_numeric_ids_without_a_name_are_other_not_guessed():
    """`2018.1` alone carries no season word; guessing from ".1" is what broke.

    The old builder classified it "unknown" and then kept an override table in
    the site layer. `other` is the same admission, in the library, with the name
    as the way out.
    """
    assert season_type("2018.1", "") == "other"
    assert season_type("2018.1", "Kesä 2018") == "summer"


def test_season_words_are_accent_insensitive():
    assert season_type("x", "Kesä 2018") == season_type("x", "Kesa 2018") == "summer"


@pytest.mark.parametrize(
    "season_id,stage",
    [
        ("2019.T3", "tour3"),
        ("2018.1F", "finals"),
        ("2017F", "finals"),
        ("KESA2026", "season"),
        ("SM2022K", "championship"),
        ("BEACH2021", "beach"),
        ("2019.2", "unknown"),
    ],
)
def test_stage_is_a_separate_axis(season_id, stage):
    """`2019.T3` is a tour stop *of* the 2019 season, not another kind of season."""
    assert season_stage(season_id) == stage


def test_classify_returns_one_record():
    assert classify("2017F", "Kesä 2017 Finaalit") == {
        "year": 2017,
        "season_type": "summer",
        "stage": "finals",
        "id": "2017F",
        "name": "Kesä 2017 Finaalit",
    }
