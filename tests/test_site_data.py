"""The published contract of site_data/: every key is a person id that names.json
can name.

Phase 9 re-keyed the site data. A name is not a usable key here: pelikone mints a
new player id per registration, and the same person is spelled two ways in the
source. So every map in site_data/ is keyed by a person id — the lowest pelikone
id in that person's id cluster — and names.json is the only decoder. A bare
canonical name left in one of these files is invisible to the page: it renders as
a lowercase name nobody can click, and no test of the page would notice.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_data"

pytestmark = pytest.mark.skipif(not SITE.is_dir(), reason="site_data/ not built")


def _load(name: str):
    return json.loads((SITE / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def names() -> dict[str, str]:
    return _load("names.json")


def _id_keyed_maps(names):
    """Every map in site_data/ whose keys are person ids, with a label."""
    yield "players.json", {k: {} for k in _load("players.json")}
    net = _load("pass_network.json")
    for axis in ("received", "given"):
        yield f"pass_network.{axis}", net[axis]
        for partners in net[axis].values():
            yield "pass_network.partners", partners
    co = _load("cooccurrence.json")
    yield "cooccurrence.json", co
    for partners in co.values():
        yield "cooccurrence.partners", partners


def test_every_key_is_named(names):
    """The invariant the build asserts too: no key without a decoder."""
    for label, mapping in _id_keyed_maps(names):
        for key in mapping:
            assert key in names, f"{label}: key {key!r} is not in names.json"


def test_keys_are_ids_or_pseudo_keys_not_canonical_names(names):
    """A bare canon name ('aki vehtari') means a view was not re-keyed."""
    for label, mapping in _id_keyed_maps(names):
        for key in mapping:
            assert key.isdigit() or key.startswith("name:"), (
                f"{label}: {key!r} is neither a pelikone id nor a name: pseudo key"
            )


def test_names_map_ids_to_printable_names(names):
    for key, display in names.items():
        assert display and display.strip() == display
        assert "\u00a0" not in display, f"{key}: display name carries a non-breaking space"
        assert not display.isdigit(), f"{key}: name is a number"


def test_year_rosters_are_named_keys():
    names = _load("names.json")
    for name in ("years_otso.json", "years_otso_summer.json", "years_otso_winter.json"):
        for year, row in _load(name).items():
            assert "roster" in row, f"{name} {year}: no roster field"
            assert "roster_names" not in row, f"{name} {year}: still name-keyed"
            for key in row["roster"]:
                assert key in names, f"{name} {year}: roster key {key!r} unnamed"
            assert len(set(row["roster"])) == len(row["roster"])


def test_rivals_carry_a_named_id():
    names = _load("names.json")
    for rival in _load("frenemies.json"):
        assert rival["id"] in names, f"rival {rival['name']!r} has no decoder"
        assert names[rival["id"]] == rival["name"]
        assert "\u00a0" not in rival["name"], (
            f"rival {rival['name']!r}: the roster's non-breaking space leaked into the page"
        )


def test_summary_top_lists_carry_named_ids():
    names = _load("names.json")
    summary = _load("summary.json")
    for key, value in summary.items():
        if not isinstance(value, list):
            continue
        for entry in value:
            if "id" in entry:
                assert entry["id"] in names, f"summary.{key}: {entry!r} unnamed"
                assert entry["name"] == names[entry["id"]]


def test_quality_report_agrees_with_the_files_it_reports():
    """data_quality.json counts the keys; if it disagrees, a view is unkeyed."""
    quality = _load("data_quality.json")
    names = _load("names.json")
    used: set[str] = set()
    for _label, mapping in _id_keyed_maps(names):
        used |= set(mapping)
    for row in _load("years_all_bears.json").values():
        used |= set(row["roster"])
    used |= {r["id"] for r in _load("frenemies.json")}
    assert quality["keys"]["keys_used_in_site_data"] == len(used)
    assert quality["keys"]["named"] == len(names)
    assert quality["keys"]["keys_used_in_site_data"] == quality["keys"]["named"], (
        "site_data references keys names.json cannot name"
    )
