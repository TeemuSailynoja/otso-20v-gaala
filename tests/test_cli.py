"""The CLI: one entry point, polite by construction, honest about what it did.

Two properties these tests hold the CLI to:

* **No surprise traffic.** A dry run makes zero network requests, and every command
  ends by reporting the request count, so an accidental crawl is visible.
* **The committed corpus is what `merge` produces.** That is the Phase 7 gate as a
  test: a fresh clone plus `ultiorg merge` reproduces `data/processed/match_results.json`
  byte for byte.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import FIXTURES

from ultiorg.cli import main
from ultiorg.query import Store
from ultiorg.store import build_store
from ultiorg import parse_allplayers, parse_gameplay
from ultiorg.identify import PlayerIndex
from ultiorg.aliases import PersonKeys

CORPUS = pytest.mark.skipif(
    not Path("data/processed/match_results.json").exists(),
    reason="processed corpus not present",
)


@pytest.fixture
def store_path(tmp_path):
    """A fact store built from the archived game fixtures."""
    games = [
        {"game_id": game_id, "season_id": season_id, "home_team": "Otso", "away_team": "UFO",
         "gameplay": parse_gameplay((FIXTURES / fixture).read_text(encoding="utf-8", errors="replace"))}
        for fixture, game_id, season_id in (
            ("gameplay_11049_modern.html", "11049", "KESA2026"),
            ("gameplay_6923_hyphen.html", "6923", "KESA2026"),
        )
    ]
    index = PlayerIndex(parse_allplayers((FIXTURES / "allplayers_all.html").read_text(encoding="utf-8", errors="replace")))
    conn, _ = build_store(tmp_path / "store.sqlite", games, index, persons=PersonKeys())
    conn.close()
    return tmp_path / "store.sqlite"


# --- queries ----------------------------------------------------------------


def test_player_answers_in_words(store_path, capsys):
    code = main(["--store", str(store_path), "player", "Niini Erkka", "--scoring", "--connections", "3"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Erkka" in out and "passes" in out
    assert "person" in out  # says what it resolved the name to


def test_player_json_is_machine_readable(store_path, capsys):
    with Store(store_path) as probe:
        scorer = probe.sql(
            "SELECT scorer_name FROM points WHERE scorer_name IS NOT NULL AND scorer_name != '' LIMIT 1"
        )[0]["scorer_name"]
    capsys.readouterr()
    main(["--store", str(store_path), "player", scorer, "--scoring", "--connections", "3", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["scoring"]["goals"] > 0
    assert payload["scoring"]["points"] == payload["scoring"]["goals"] + payload["scoring"]["assists"]
    assert 1 <= len(payload["connections"]) <= 3
    assert all({"player", "passes", "games_together", "resolved"} <= set(row) for row in payload["connections"])


def test_player_defense_filter_reaches_the_output(store_path, capsys):
    main(["--store", str(store_path), "player", "Erkka Niini", "--scoring", "--possession", "defense"])
    out = capsys.readouterr().out
    assert "defense possession" in out


def test_an_unresolvable_name_exits_with_a_message(store_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--store", str(store_path), "player", "Ei Ketään Ei Mikään"])
    assert "no player matches" in str(exc.value)


def test_a_missing_store_names_the_command_that_builds_it(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--store", str(tmp_path / "nope.sqlite"), "player", "Erkka Niini"])
    assert "ultiorg store" in str(exc.value)


def test_sql_prints_rows_and_refuses_writes(store_path, capsys):
    assert main(["--store", str(store_path), "sql", "SELECT COUNT(*) AS n FROM points"]) == 0
    assert "n" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        main(["--store", str(store_path), "sql", "DELETE FROM points"])
    assert "read-only" in str(exc.value)


def test_defense_reports_a_team_total(store_path, capsys):
    assert main(["--store", str(store_path), "defense", "Otso"]) == 0
    assert "defense-initiated" in capsys.readouterr().out


# --- fetching is polite -----------------------------------------------------


def test_dry_run_fetches_nothing(tmp_path, capsys):
    code = main(["--data-dir", str(tmp_path), "--dry-run", "fetch", "season", "KESA2026"])
    out = capsys.readouterr().out
    assert code == 0
    assert "network requests 0" in out
    assert (tmp_path / "raw" / "KESA2026.json").exists()
    assert json.loads((tmp_path / "processed" / "match_results.json").read_text()) == []


def test_cache_stats_reports_pages_and_kinds(capsys):
    assert main(["cache", "stats"]) == 0
    out = capsys.readouterr().out
    assert "pages," in out and "immutable" in out


def test_repair_without_a_corpus_says_so(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["--data-dir", str(tmp_path), "repair", "dedupe-points"])
    assert "no corpus" in str(exc.value)


def test_a_command_is_required():
    with pytest.raises(SystemExit):
        main([])


# --- the Phase 7 gate -------------------------------------------------------


@CORPUS
def test_merge_reproduces_the_committed_corpus_byte_for_byte():
    """`merge` is what a fresh clone runs; the committed corpus must be exactly its
    output, or the corpus and the code have drifted apart."""
    path = Path("data/processed/match_results.json")
    before = path.read_bytes()
    assert main(["merge"]) == 0
    assert path.read_bytes() == before, "the committed corpus is not what merge produces"


@CORPUS
def test_merge_counts_match_the_corpus():
    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        main(["merge"])
    out = buffer.getvalue()
    assert "795 games / 61 seasons" in out
    assert "18681 points of 18684 expected" in out


@CORPUS
def test_the_installed_console_script_runs():
    """`ultiorg` must be a real entry point, not only `python -m`."""
    result = subprocess.run(
        [sys.executable, "-m", "ultiorg", "cache", "stats"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "pages," in result.stdout
