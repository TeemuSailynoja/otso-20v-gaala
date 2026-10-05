"""The corpus builder: recompose, never clobber.

The old `--season X --gameplay` run wrote the games it had just fetched straight
over `match_results.json`, so fetching one season replaced a 795-game corpus with
24 games. These tests pin the two properties that replace that failure:

* a fetch **adds** — games from other seasons survive;
* `merge` is **safe on a fresh clone**, where `data/raw/` is gitignored and the
  corpus is the only record of the point-by-point data.
"""

import json
import shutil
from pathlib import Path

import pytest
from conftest import FIXTURES

from ultiorg.corpus import build_corpus, write_corpus

CORPUS = pytest.mark.skipif(
    not Path("data/processed/match_results.json").exists(),
    reason="processed corpus not present"
)


def _corpus_entry(game_id, season_id, points=2, **extra):
    return {
        "game_id": game_id, "season_id": season_id,
        "home_team": "Otso", "away_team": "UFO", "home_score": points, "away_score": 0,
        "gameplay": {
            "home_team": "Otso", "away_team": "UFO", "home_score": points, "away_score": 0,
            "points": [{"type": "point", "side": "home", "score": f"{i + 1}-0", "time": f"{i}.00",
                        "passer": "A B", "scorer": "C D"} for i in range(points)],
            "home_players": [{"id": "1", "name": "A B"}], "away_players": [{"id": "2", "name": "C D"}],
        },
        **extra,
    }


def _data_dir(tmp_path, entries) -> Path:
    data = tmp_path / "data"
    (data / "processed").mkdir(parents=True)
    write_corpus(data / "processed" / "match_results.json", entries)
    return data


# --- the fresh-clone case ---------------------------------------------------


def test_merge_on_a_fresh_clone_keeps_every_point(tmp_path):
    """`data/raw/` is gitignored; the corpus is tracked. So a fresh clone has the
    points and no HTML — and `merge` must not answer by deleting them."""
    data = _data_dir(tmp_path, [_corpus_entry("100", "KESA2024"), _corpus_entry("200", "KESA2026", 3)])
    before = (data / "processed" / "match_results.json").read_bytes()
    games, stats = build_corpus(data)
    assert (stats.games, stats.points, stats.gameplay_carried) == (2, 5, 2)
    assert stats.gameplay_attached == 0
    write_corpus(data / "processed" / "match_results.json", games)
    assert (data / "processed" / "match_results.json").read_bytes() == before


@CORPUS
def test_merge_on_a_fresh_clone_reproduces_the_committed_corpus():
    """The same claim at full size: 795 games, 18,681 points, byte for byte."""
    committed = Path("data/processed/match_results.json").read_bytes()
    data = _stage_clone()
    games, stats = build_corpus(data)
    assert stats.games == 795 and stats.points == 18681
    assert stats.gameplay_carried == 795 and stats.gameplay_attached == 0
    write_corpus(data / "processed" / "match_results.json", games)
    assert (data / "processed" / "match_results.json").read_bytes() == committed


def _stage_clone(source: Path = Path("data")) -> Path:
    """A directory shaped like a fresh clone's `data/`: the corpus, nothing else."""
    import tempfile

    staging = Path(tempfile.mkdtemp(prefix="fresh-clone-"))
    (staging / "processed").mkdir(parents=True)
    shutil.copy(source / "processed" / "match_results.json", staging / "processed" / "match_results.json")
    return staging


# --- recomposition ----------------------------------------------------------


def test_archived_html_beats_the_stored_row(tmp_path):
    """The corpus row may hold points written by a broken scraper; the archived
    page re-parsed by `parse_gameplay` is the source of truth."""
    stale = _corpus_entry("11049", "KESA2026", points=1)
    stale["gameplay"]["points"] = [{"type": "point", "side": "home", "score": "1-0", "time": "1.00",
                                    "scorer": "Vanha", "assist": "Neko"}]  # the old swapped shape
    data = _data_dir(tmp_path, [stale])
    raw = data / "raw"
    raw.mkdir()
    shutil.copy(FIXTURES / "gameplay_11049_modern.html", raw / "game_11049.html")

    games, stats = build_corpus(data)
    assert (stats.gameplay_attached, stats.gameplay_carried) == (1, 0)
    points = games[0]["gameplay"]["points"]
    assert all("assist" not in p for p in points)
    assert len([p for p in points if p.get("type") == "point"]) > 1


def test_a_fetch_for_one_season_adds_games_it_does_not_have(tmp_path):
    """The clobbering failure: fetching one season must not drop the other seasons."""
    data = _data_dir(tmp_path, [_corpus_entry("100", "KESA2024")])
    raw = data / "raw"
    raw.mkdir()
    (raw / "KESA2026.json").write_text(json.dumps({
        "id": "KESA2026",
        "games": [{"game_id": "200", "season_id": "KESA2026", "home_team": "Otso", "away_team": "Terror",
                   "home_score": 2, "away_score": 1}],
    }), encoding="utf-8")
    shutil.copy(FIXTURES / "gameplay_11049_modern.html", raw / "game_200.html")

    games, stats = build_corpus(data)
    assert sorted(g["game_id"] for g in games) == ["100", "200"]
    assert sorted(g["season_id"] for g in games) == ["KESA2024", "KESA2026"]
    assert stats.gameplay_attached == 1 and stats.gameplay_carried == 1


def test_a_listed_game_nobody_archived_does_not_enter(tmp_path):
    """`require_gameplay` keeps the corpus the point-by-point corpus."""
    data = _data_dir(tmp_path, [])
    raw = data / "raw"
    raw.mkdir()
    (raw / "KESA2026.json").write_text(json.dumps({
        "id": "KESA2026",
        "games": [{"game_id": "777", "season_id": "KESA2026", "home_team": "Otso", "away_team": "UFO",
                   "home_score": 3, "away_score": 0}],
    }), encoding="utf-8")
    games, stats = build_corpus(data)
    assert games == [] and stats.skipped_unarchived == 1


def test_a_game_in_the_corpus_survives_without_archived_html(tmp_path):
    data = _data_dir(tmp_path, [_corpus_entry("100", "KESA2024")])
    games, stats = build_corpus(data)
    assert len(games) == 1 and stats.gameplay_carried == 1


def test_rebuild_is_byte_stable(tmp_path):
    data = _data_dir(tmp_path, [_corpus_entry("2", "KESA2026"), _corpus_entry("1", "KESA2025")])
    first, _ = build_corpus(data)
    write_corpus(data / "processed" / "match_results.json", first)
    bytes_once = (data / "processed" / "match_results.json").read_bytes()
    second, _ = build_corpus(data)
    write_corpus(data / "processed" / "match_results.json", second)
    assert (data / "processed" / "match_results.json").read_bytes() == bytes_once
    # sorted by season then game id, so the order never depends on scrape order
    assert [g["game_id"] for g in second] == ["1", "2"]


def test_metadata_from_a_season_file_fills_what_the_corpus_lacks(tmp_path):
    """Newer scrape wins on conflicts; the corpus keeps what nothing else knows."""
    data = _data_dir(tmp_path, [_corpus_entry("100", "KESA2024", date="2024-07-01")])
    raw = data / "raw"
    raw.mkdir()
    (raw / "KESA2024.json").write_text(json.dumps({
        "id": "KESA2024",
        "games": [{"game_id": "100", "season_id": "KESA2024", "home_team": "Otso", "away_team": "UFO",
                   "home_score": 4, "away_score": 1, "venue": "Matinkylä", "division": "Avoin"}],
    }), encoding="utf-8")
    games, _ = build_corpus(data)
    assert games[0]["date"] == "2024-07-01"      # only the corpus knew it
    assert games[0]["venue"] == "Matinkylä"      # the newer scrape filled it
    assert games[0]["home_score"] == 4


@CORPUS
def test_the_committed_corpus_is_what_the_archive_produces():
    """Full-size gate against the real archive: 795 games, 61 seasons, and every
    point the archived pages hold."""
    games, stats = build_corpus(Path("data"))
    assert stats.games == 795
    assert stats.seasons == 61
    assert stats.gameplay_attached == 795
    assert stats.points == 18681
    assert stats.skipped_unarchived == 5  # listed on a games page, never archived
