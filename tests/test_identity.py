"""Identity: name canonicalisation, ID recovery, and the roster-side rule.

Two of these tests exist because of measured bugs, not hypotheticals:

* the roster side used to be decided by matching a scoreboard caption against a
  team name parsed from the `<h1>`. With home "Otso 2" and away "Otso" the
  substring test matched, the away roster overwrote the home one, and
  `away_players` stayed empty — 12 of the 795 archived games.
* the `<h1>` was split on the first `-`, which mangles hyphenated team names
  ("SOS-Terror - Otso 2").
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))

from conftest import FIXTURES  # noqa: E402

from ultiorg.identify import PlayerIndex, canon, pseudo_key, recover_rosters  # noqa: E402
from ultiorg.parsers import parse_gameplay  # noqa: E402

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def board_player_ids(html: str) -> list[set[str]]:
    """Ground truth: player IDs linked from each scoreboard, in document order."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for board in soup.find_all("div", class_="gameplay-scoreboard"):
        out.append(
            {
                a["href"].split("player=")[-1]
                for a in board.find_all("a", href=True)
                if "player=" in a["href"]
            }
        )
    return out


# --- name canonicalisation ---------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        # canon sorts the name parts, so both orders collapse to the same key;
        # the sorted form is alphabetical, not "Last First".
        ("Potrykus Patrick", "patrick potrykus"),
        ("Patrick Potrykus", "patrick potrykus"),  # point rows vs rosters
        ("Mikael\xa0Vitikainen", "mikael vitikainen"),  # U+00A0 separator
        ("Aalto Kristiina (C)", "aalto kristiina"),  # captain marker
        ("Aalto Kristiina (c)", "aalto kristiina"),
        ("  Isokangas   Mikko ", "isokangas mikko"),
        ("", ""),
    ],
)
def test_canon_is_order_insensitive_and_nbsp_safe(raw, expected):
    # NBSP is the real separator in roster HTML; a rule that ignores it matches
    # nobody, and a rule that is order-sensitive matches only one side.
    assert canon(raw) == expected


def test_pseudo_key_is_stable_for_both_name_orders():
    assert pseudo_key("Potrykus Patrick") == pseudo_key("Patrick Potrykus")
    assert pseudo_key("Potrykus Patrick") == "name:patrick potrykus"


# --- the player index --------------------------------------------------------


INDEX = [
    {"id": "1", "name": "Aalto Kristiina"},
    {"id": "2", "name": "Korhonen Matti"},
    {"id": "3", "name": "Vitikainen Mikael"},
    {"id": "4", "name": "Vitikainen Mikael"},  # duplicate registration
    {"id": "5", "name": ""},  # real ID, no name
]


@pytest.fixture()
def index() -> PlayerIndex:
    return PlayerIndex(INDEX)


def test_resolve_matches_either_name_order(index):
    assert index.resolve("Kristiina Aalto").player_id == "1"
    assert index.resolve("Aalto Kristiina").player_id == "1"
    assert index.resolve("Aalto\xa0Kristiina").player_id == "1"


def test_resolve_reports_ambiguity_instead_of_guessing(index):
    found = index.resolve("Mikael Vitikainen")
    assert found.player_id is None
    assert found.via == "ambiguous"
    assert found.candidates == ["3", "4"]


def test_resolve_reports_misses(index):
    found = index.resolve("Nikolaev Nikolay")
    assert (found.player_id, found.via) == (None, "none")


def test_index_counts_blank_names_and_ambiguous_names(index):
    assert index.blank_ids == ["5"]
    assert index.ambiguous() == {"mikael vitikainen": ["3", "4"]}
    assert index.size == 5


# --- roster sides ------------------------------------------------------------


def test_roster_sides_follow_board_order_not_name_matching():
    # Otso 2 (home) vs Otso (away): the old substring rule put the away roster
    # on the home side and left away_players empty.
    html = (FIXTURES / "gameplay_6215_otso_derby.html").read_text(encoding="utf-8")
    gp = parse_gameplay(html)
    assert (gp["home_team"], gp["away_team"]) == ("Otso 2", "Otso")
    assert gp["home_players"] and gp["away_players"]
    assert {p["id"] for p in gp["home_players"]} == board_player_ids(html)[0]
    assert {p["id"] for p in gp["away_players"]} == board_player_ids(html)[1]
    # Roni Hotari played for the away side in this game.
    assert "16382" in {p["id"] for p in gp["away_players"]}
    assert "16382" not in {p["id"] for p in gp["home_players"]}


def test_hyphenated_team_name_survives():
    # "SOS-Terror - Otso 2    15 - 10": splitting the heading on the first dash
    # used to yield home team "SOS" and away "Terror - Otso 2".
    html = (FIXTURES / "gameplay_6923_hyphen.html").read_text(encoding="utf-8")
    gp = parse_gameplay(html)
    assert (gp["home_team"], gp["away_team"]) == ("SOS-Terror", "Otso 2")
    assert (gp["home_score"], gp["away_score"]) == (15, 10)


@pytest.mark.skipif(not RAW_DIR.exists(), reason="needs the archived corpus")
def test_archived_corpus_identity_gates(allplayers_index):
    """One pass over the 795 archived games: sides, ID recovery, name coverage.

    These are the numbers the re-key (Phase 9) and the fact store (Phase 5) are
    built on, so they are pinned rather than assumed:

    * roster sides match the scoreboard order in every game;
    * roster player IDs are recoverable offline from the archived HTML;
    * at least 98% of the `Last First` names in point rows resolve to exactly
      one player ID in the `allplayers` index. The rest are reported, not dropped.
    """
    sides_checked = 0
    slots = 0
    resolved = 0
    recovered_ids: set[str] = set()
    for path in sorted(RAW_DIR.glob("game_*.html")):
        html = path.read_text(encoding="utf-8", errors="replace")
        gp = parse_gameplay(html)
        boards = board_player_ids(html)
        if len(boards) == 2 and all(boards):
            assert {p["id"] for p in gp["home_players"] if p["id"]} == boards[0], path.name
            assert {p["id"] for p in gp["away_players"] if p["id"]} == boards[1], path.name
            sides_checked += 1
        for player in gp["home_players"] + gp["away_players"]:
            if player["id"]:
                recovered_ids.add(player["id"])
        for point in gp["points"]:
            if point["type"] != "point":
                continue
            for name in (point.get("passer"), point.get("scorer")):
                if not name:
                    continue
                slots += 1
                if allplayers_index.resolve(name).resolved:
                    resolved += 1

    assert sides_checked > 700, sides_checked
    assert len(recovered_ids) > 6000, len(recovered_ids)
    assert slots > 30000, slots
    coverage = resolved / slots
    assert coverage >= 0.98, f"only {coverage:.3%} of point names resolved"


# --- offline ID recovery -----------------------------------------------------


@pytest.fixture(scope="module")
def allplayers_index() -> PlayerIndex:
    """The real player index, from the cached `?view=allplayers&list=all`."""
    from ultiorg.cache import Cache
    from ultiorg.config import BASE_URL
    from ultiorg.parsers import parse_allplayers

    html = Cache().read(f"{BASE_URL}/?view=allplayers&list=all")
    if not html:
        pytest.skip("needs the cached allplayers index; run ultiorg --import-cache")
    return PlayerIndex(parse_allplayers(html))


def test_recover_rosters_reads_ids_from_archived_html(tmp_path):
    for name in ("gameplay_6215_otso_derby.html", "gameplay_11049_modern.html"):
        game_id = name.split("_")[1]
        (tmp_path / f"game_{game_id}.html").write_bytes((FIXTURES / name).read_bytes())

    result = recover_rosters(tmp_path)
    assert result["games"] == 2
    assert result["roster_entries_with_ids"] > 0
    assert result["roster_entries_without_ids"] == 0
    game = result["rosters"]["6215"]
    assert game["home_team"] == "Otso 2"
    assert all(p["id"] for p in game["home"] + game["away"])


def test_recover_rosters_flags_index_gaps(tmp_path):
    (tmp_path / "game_6215.html").write_bytes(
        (FIXTURES / "gameplay_6215_otso_derby.html").read_bytes()
    )
    index = PlayerIndex([{"id": "16368", "name": "Vehtari Aki"}])
    result = recover_rosters(tmp_path, index=index)
    # Every other roster ID is unknown to that index: the quality report says so
    # rather than dropping the entries.
    assert result["quality"].roster_ids_not_in_index
