"""The published numbers are the library's numbers, not the build's arithmetic.

`build_site_data.py` does not compute defense-initiated scoring: it calls
`ultiorg.build_defense_stats` and writes what comes back. So the figure a player
page shows is a claim about the library, and this file checks it end to end —
recompute from the corpus with the club's own config and alias file, then compare
against the JSON the site actually serves.

This half of the check used to live in the library's `tests/test_store.py`, where
it read `site_data/players.json` across the repo boundary. The library cannot own
a test about a file it does not publish; the store-vs-builder half stayed there,
and this is the builder-vs-published-page half.

It also pins the one asserted name merge. "Aukusti Touko Väänänen" is how the
point rows spell him and "Touko Väänänen" how the rosters do; before
`config/aliases.json` his 115 defense points existed in the data and did not
exist on the site, because `players.json` is keyed by season-card rosters.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ultiorg import PersonKeys, build_defense_stats, canon, load_focus_team

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_data"
CORPUS = ROOT / "data" / "processed" / "match_results.json"

pytestmark = pytest.mark.skipif(
    not SITE.is_dir() or not CORPUS.exists(), reason="site_data/ or the corpus not built"
)


def _load(name: str):
    return json.loads((SITE / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def published_defense() -> dict[str, int]:
    """Defense points per person, as the site publishes them.

    `players.json` is keyed by person id, so the person key comes through
    `names.json` — the same decoder the page uses.
    """
    names = _load("names.json")
    out: dict[str, int] = {}
    for key, player in _load("players.json").items():
        person = canon(names.get(key, key))
        out[person] = out.get(person, 0) + player.get("defense_points", 0)
    return out


@pytest.fixture(scope="module")
def builder_defense() -> dict[str, int]:
    from build_site_data import load_corpus

    focus = load_focus_team(str(ROOT / "teams.yaml"))
    assert focus is not None, "teams.yaml is the club the published numbers are about"
    persons = PersonKeys.from_file(ROOT / "config" / "aliases.json")
    stats = build_defense_stats(load_corpus(), focus, persons)
    return {key: row["defense_points"] for key, row in stats.items()}


def test_the_published_defense_total_is_the_builder_s(published_defense, builder_defense):
    """Every point the library credits is on a page, and no page shows one more."""
    assert sum(published_defense.values()) == 4443
    assert sum(builder_defense.values()) == sum(published_defense.values())
    # the builder also names players with zero defense points (offense-only
    # scorers); a row of zeros is a real row on the site, so it must be present
    missing = {k: v for k, v in builder_defense.items() if v and k not in published_defense}
    assert missing == {}, "the builder credited players the site never heard of"
    extra = {k: v for k, v in published_defense.items() if v and k not in builder_defense}
    assert extra == {}, "the site publishes defense points the builder does not credit"
    nonzero = {k: v for k, v in builder_defense.items() if v}
    assert {k: v for k, v in published_defense.items() if v} == nonzero


def test_the_asserted_name_merge_holds_on_the_published_rows(published_defense):
    """One merge in `config/aliases.json`, and both spellings' points land on one key."""
    assert published_defense["touko väänänen"] == 180
    assert "aukusti touko väänänen" not in published_defense
