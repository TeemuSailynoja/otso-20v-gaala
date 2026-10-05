"""The repair commands: each one fixes a defect that is already committed.

The corpus is tracked in git, so a parser fix does not retroactively fix the JSON
the broken parser wrote, and a fresh clone starts from that JSON. These tests pin
two things: the repair fixes the old shape, and it is a **no-op on current data** —
a repair that rewrites correct rows is worse than no repair.
"""

import json
import shutil
from pathlib import Path

import pytest
from conftest import FIXTURES, read_fixture

from ultiorg.repair import dedupe_point_rows, migrate_point_fields, refresh_rosters

CORPUS = pytest.mark.skipif(
    not Path("data/processed/match_results.json").exists(),
    reason="processed corpus not present",
)


def _write(path: Path, games) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(games, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _game(points, game_id="11049"):
    return {"game_id": game_id, "season_id": "KESA2026", "gameplay": {"points": points}}


# --- point-fields -----------------------------------------------------------


def test_point_fields_swap_the_mislabelled_names(tmp_path):
    """cells[1] is Syöttäjä (the passer) and cells[2] is Maali (the scorer); the
    old scrapers stored them as `scorer` and `assist`, i.e. swapped."""
    old = _game([
        {"type": "point", "side": "home", "score": "1-0", "time": "3.10",
         "scorer": "Potrykus Patrick", "assist": "Arola Matias"},
    ])
    report = migrate_point_fields(_write(tmp_path / "corpus.json", [old]))
    point = _read(tmp_path / "corpus.json")[0]["gameplay"]["points"][0]
    assert report.changed == 1
    assert point["passer"] == "Potrykus Patrick"   # cells[1], Syöttäjä
    assert point["scorer"] == "Arola Matias"       # cells[2], Maali
    assert "assist" not in point


def test_point_fields_is_idempotent(tmp_path):
    path = _write(tmp_path / "corpus.json", [_game([
        {"type": "point", "side": "home", "score": "1-0", "time": "3.10",
         "passer": "Potrykus Patrick", "scorer": "Arola Matias"},
    ])])
    before = path.read_text(encoding="utf-8")
    report = migrate_point_fields(path)
    assert (report.changed, report.unchanged) == (0, 1)
    assert path.read_text(encoding="utf-8") == before


def test_point_fields_leaves_blank_cells_alone(tmp_path):
    """A missing key is not an un-migrated row.

    Measured on the committed corpus: 81 points carry a scorer and no passer, 33 a
    passer and no scorer — the page leaves one cell blank. A guard keyed on the
    *absence* of `passer` moved those scorers into `passer` and blanked the scorer.
    The marker of the old shape is the presence of `assist`.
    """
    rows = [
        {"type": "point", "side": "home", "score": "1-0", "time": "1.00", "scorer": "Arola Matias"},
        {"type": "point", "side": "home", "score": "2-0", "time": "2.00", "passer": "Potrykus Patrick"},
        {"type": "halftime", "text": "Tauko"},
    ]
    path = _write(tmp_path / "corpus.json", [_game(rows)])
    before = path.read_text(encoding="utf-8")
    report = migrate_point_fields(path)
    assert report.changed == 0
    assert path.read_text(encoding="utf-8") == before


@CORPUS
def test_point_fields_is_a_no_op_on_the_committed_corpus():
    path = Path("data/processed/match_results.json")
    before = _read(path)
    scorer_only = sum(
        1 for g in before for p in (g.get("gameplay") or {}).get("points", [])
        if "scorer" in p and "passer" not in p
    )
    passer_only = sum(
        1 for g in before for p in (g.get("gameplay") or {}).get("points", [])
        if "passer" in p and "scorer" not in p
    )
    assert (scorer_only, passer_only) == (81, 33)
    report = migrate_point_fields(path)
    assert report.changed == 0, "the corpus drifted back to the old shape"
    assert _read(path) == before


# --- dedupe-points ----------------------------------------------------------


def test_dedupe_drops_the_rows_the_doubled_page_produced(tmp_path):
    """The gameplay page renders its point table twice; the old scraper kept both."""
    point = {"type": "point", "side": "home", "score": "1-0", "time": "3.10",
             "passer": "Potrykus Patrick", "scorer": "Arola Matias"}
    same_but_reordered = dict(reversed(list(point.items())))
    other = {"type": "point", "side": "home", "score": "2-0", "time": "4.00",
             "passer": "Potrykus Patrick", "scorer": "Arola Matias"}
    halftime = {"type": "halftime", "text": "Tauko"}
    path = _write(tmp_path / "corpus.json", [_game([point, dict(point), same_but_reordered, other, halftime, halftime])])
    report = dedupe_point_rows(path)
    kept = _read(path)[0]["gameplay"]["points"]
    assert report.changed == 1
    assert len(kept) == 3  # two distinct goals + one halftime marker
    assert report.notes["rows removed"] == 3
    # idempotent
    again = dedupe_point_rows(path)
    assert again.changed == 0 and again.notes["rows removed"] == 0


def test_dedupe_keeps_a_repeated_score_that_is_a_different_point(tmp_path):
    """The score is cumulative, so (side, time, score, names) identifies a goal.

    Two rows with the same score but different clocks are two real points — the
    doubled copy differs in *every* field that matters, so only exact repeats go.
    """
    rows = [
        {"type": "point", "side": "home", "score": "1-0", "time": "3.10", "scorer": "A"},
        {"type": "point", "side": "home", "score": "1-0", "time": "9.40", "scorer": "B"},
    ]
    path = _write(tmp_path / "corpus.json", [_game(rows)])
    report = dedupe_point_rows(path)
    assert report.changed == 0 and len(_read(path)[0]["gameplay"]["points"]) == 2


@CORPUS
def test_dedupe_is_a_no_op_on_the_committed_corpus():
    path = Path("data/processed/match_results.json")
    before = path.read_text(encoding="utf-8")
    report = dedupe_point_rows(path)
    assert report.changed == 0 and report.notes["rows removed"] == 0
    assert path.read_text(encoding="utf-8") == before


# --- rosters ----------------------------------------------------------------


@pytest.fixture
def raw_dir(tmp_path):
    """An archive directory shaped like data/raw: game_<id>.html."""
    directory = tmp_path / "raw"
    directory.mkdir()
    shutil.copy(FIXTURES / "gameplay_11049_modern.html", directory / "game_11049.html")
    return directory


def test_rosters_merge_back_names_the_stored_entry_lost(raw_dir, tmp_path):
    """Game 9170 stores no away roster, so Simo Soini is missing from a game in
    which he scored twice. The fix is a merge, not a replacement."""
    from ultiorg import parse_gameplay

    fresh = parse_gameplay(read_fixture("gameplay_11049_modern.html"))
    stored = _game([{"type": "point", "side": "away", "score": "0-1", "time": "1.00",
                     "scorer": fresh["away_players"][0]["name"]}], game_id="11049")
    stored["gameplay"]["home_players"] = fresh["home_players"]
    stored["gameplay"]["away_players"] = []  # the defect: an empty side
    path = _write(tmp_path / "corpus.json", [stored])

    report = refresh_rosters(path, raw_dir)
    after = _read(path)[0]["gameplay"]
    assert report.changed == 1
    assert report.notes["names added"] == len(fresh["away_players"])
    assert [p["name"] for p in after["away_players"]] == [p["name"] for p in fresh["away_players"]]
    assert report.notes["games with points but no roster"] == 0

    again = refresh_rosters(path, raw_dir)
    assert again.changed == 0 and again.notes["names added"] == 0


def test_rosters_never_drop_a_name_the_archive_no_longer_shows(raw_dir, tmp_path):
    """For 3 of 795 games the archived page now lists fewer names than the scrape
    recorded, so the union keeps stored names a fresh parse does not mention."""
    stored = _game([{"type": "point", "side": "home", "score": "1-0", "time": "1.00", "scorer": "Kadonnut Pelaaja"}], game_id="11049")
    stored["gameplay"]["home_players"] = [{"id": "1", "name": "Kadonnut Pelaaja"}]
    stored["gameplay"]["away_players"] = []
    path = _write(tmp_path / "corpus.json", [stored])
    refresh_rosters(path, raw_dir)
    after = _read(path)[0]["gameplay"]
    assert "Kadonnut Pelaaja" in [p["name"] for p in after["home_players"]]


def test_rosters_ignore_games_without_archived_html(raw_dir, tmp_path):
    stored = _game([{"type": "point", "side": "home", "score": "1-0", "time": "1.00"}], game_id="99999")
    path = _write(tmp_path / "corpus.json", [stored])
    report = refresh_rosters(path, raw_dir)
    assert report.changed == 0
    assert _read(path)[0]["gameplay"].get("home_players", []) == []
