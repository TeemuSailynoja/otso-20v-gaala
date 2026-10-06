"""The published contract of site_data/: the manifest, the schema, and both
validators that enforce it.

Phase 10 replaced two ways of guessing what the page was about to read — a hash
stamped into a comment in index.html, and a fetch list duplicated in the page —
with two files the build writes: `manifest.json` (what exists, at which version,
and who reads it) and `schema.json` (what each file looks like).

These tests hold three things together:
  * the files on disk fit the shape the build claims,
  * the manifest accounts for every file in the directory, so a stale file is
    named rather than silently served or silently deleted,
  * the JS validator reaches the same verdict as the Python one, because the page
    checks with the JS half and nothing else keeps the two honest.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import site_contract as contract

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_data"

pytestmark = pytest.mark.skipif(not SITE.is_dir(), reason="site_data/ not built")


def _load(name: str):
    return json.loads((SITE / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> dict:
    return _load("manifest.json")


@pytest.fixture(scope="module")
def schema() -> dict:
    return _load("schema.json")


def _published(manifest: dict) -> list[str]:
    return [entry["name"] for entry in manifest["files"]]


# --- the shape language itself ----------------------------------------------
def test_int_is_an_integer_and_never_a_bool_or_a_float():
    assert contract.validate(3, "int") == []
    assert contract.validate(True, "int")  # bool is an int in Python; not here
    assert contract.validate(3.0, "int")
    assert contract.validate(3.0, "number") == []
    assert contract.validate("3", "int")


def test_a_missing_field_is_named_by_path():
    spec = contract.obj(name=contract.STR, games=contract.INT)
    problems = contract.validate({"name": "x"}, spec, "players.6890")
    assert problems == ["players.6890.games: missing"]


def test_an_optional_field_may_be_absent_but_not_wrong_when_present():
    spec = contract.obj(age=contract.opt(contract.NUMBER))
    assert contract.validate({}, spec) == []
    assert contract.validate({"age": 24.5}, spec) == []
    assert contract.validate({"age": "24"}, spec)


def test_a_field_the_schema_never_mentioned_is_a_problem():
    """Strict in both directions on purpose.

    A field appearing that nobody declared is the usual shape of a half-finished
    change: something upstream started publishing and the page never heard.
    """
    spec = contract.obj(games=contract.INT)
    assert contract.validate({"games": 1, "games_v2": 1}, spec) == [
        "<root>.games_v2: not in the schema"
    ]


def test_map_and_list_paths_point_at_the_offending_record():
    spec = contract.map_(contract.lst(contract.INT))
    assert contract.validate({"a": [1, 2], "b": [3, "x"]}, spec) == [
        "<root>.b[1]: expected int, got str"
    ]


def test_any_accepts_either_branch():
    spec = contract.any_(contract.INT, "null")
    assert contract.validate(None, spec) == []
    assert contract.validate(4, spec) == []
    assert contract.validate("4", spec)


# --- the published files -----------------------------------------------------
def test_every_published_file_fits_its_shape(manifest):
    """The build checks this before writing; the check is re-run here."""
    for name in _published(manifest):
        problems = contract.validate(_load(name), contract.SHAPE[name])
        assert not problems, f"{name}: {problems[:5]}"


def test_the_schema_on_disk_is_the_schema_the_build_holds(schema):
    assert schema == contract.schema_document()


def test_the_manifest_describes_the_directory_exactly(manifest):
    """No file in site_data/ is unaccounted for.

    A file the build stopped writing but nobody deleted keeps being served and
    keeps being cached, and nothing in the page would ever notice. The build
    reports such files on every run and removes them only with ``--prune`` — while
    the site is being restructured, an unwritten file may be one the next phase
    wants back, so it is flagged rather than forgotten or destroyed. This set is
    the current answer; if it grows, the build said so on stdout.
    """
    on_disk = {p.name for p in SITE.iterdir() if p.is_file()}
    published = set(_published(manifest)) | {"manifest.json", "schema.json"}
    assert published <= on_disk
    assert on_disk - published == {
        "years.json", "players.csv", "player_names.txt", "season_mapping.json",
    }


def test_the_build_deletes_nothing_unless_told_to():
    """Pruning site_data/ is opt-in, and the flag that opts in is named here.

    Deleting a file the build stopped writing is a decision, not a cleanup: the
    owner asked for flagging while the site is being restructured. The guard is
    one line in build_site_data.py; this pins that it is a guard.
    """
    source = (ROOT / "build_site_data.py").read_text(encoding="utf-8")
    assert '"--prune" in sys.argv' in source
    assert source.count("unlink()") == 1


# --- what a zero means -------------------------------------------------------
# A player row answers seven defense questions. They used to be answered with
# three zeros and four absences, which read as "we know the total but not the
# split" — and the schema had to call four fields optional to match. The
# invariant below is what makes the zeros honest: every credited point increments
# exactly one bucket and exactly one goal, so total_points 0 *is* the statement
# that the other four are zero. Where a zero is instead a coverage gap, that is
# written down in data_quality.json rather than left for the reader to suspect.

DEFENSE_FIELDS = ("defense_points", "defense_goals", "defense_assists",
                  "offense_points", "offense_goals", "offense_assists", "total_points")


def test_every_player_row_answers_all_seven_defense_questions():
    players = _load("players.json")
    missing = {k for k, v in players.items() if not all(f in v for f in DEFENSE_FIELDS)}
    assert missing == set()


def test_the_defense_fields_add_up_on_every_row():
    players = _load("players.json")
    for key, row in players.items():
        assert row["defense_goals"] + row["offense_goals"] == row["total_points"], key
        assert row["defense_points"] + row["offense_points"] == row["total_points"], key
        # An assist is recorded on the scorer's row, so it cannot exceed the points
        # that row was credited with. The passer side lives in pass_network.json.
        assert row["defense_assists"] + row["offense_assists"] <= row["total_points"], key


def test_the_rows_where_zero_is_coverage_not_fact_are_named():
    """19 rows have `total_points: 0`. For 16 the season card agrees they scored
    nothing in every Otso squad-season they appear in, so "never scored" is
    corroborated by both sources. For the other 3 the goals come from the card and
    the play-by-play never named them — and that difference is published.
    """
    players = _load("players.json")
    coverage = _load("data_quality.json")["point_table_coverage"]
    zero = {k for k, v in players.items() if v["total_points"] == 0}
    assert coverage["total_points_zero"] == len(zero) == 19
    unseen = {row["site_key"] for row in coverage["goals_the_point_table_never_saw"]}
    assert unseen == {k for k in zero if players[k]["goals"]}
    for row in coverage["goals_the_point_table_never_saw"]:
        assert players[row["site_key"]]["goals"] == row["goals"] > 0
    # An assist belongs to the scorer's row, so published assists with no points
    # are not a gap. The schema test above would fail if this note went missing.
    assert "pass_network.json" in coverage["assists_note"]


def test_the_manifest_version_is_the_data_it_ships(manifest):
    payload = {name: (SITE / name).read_bytes() for name in _published(manifest)}
    assert manifest["version"] == contract.content_version(payload)


def test_the_page_fetch_list_is_all_real_files(manifest):
    published = set(_published(manifest))
    missing = [name for name in contract.PAGE_FILES if name not in published]
    assert not missing, f"the page asks for files the build does not publish: {missing}"


def test_the_version_does_not_move_when_only_the_order_changes():
    payload = {"b.json": b"2", "a.json": b"1"}
    assert contract.content_version(payload) == contract.content_version(
        {"a.json": b"1", "b.json": b"2"})


def test_the_version_moves_when_the_data_moves():
    assert (contract.content_version({"a.json": b"1"})
            != contract.content_version({"a.json": b"2"}))


def test_the_build_refuses_a_file_that_breaks_the_shape():
    """A shape violation fails the build, not the page."""
    players = _load("players.json")
    first = next(iter(players))
    players[first]["goals"] = "17"
    with pytest.raises(ValueError) as excinfo:
        contract.check({"players.json": players})
    assert f"<root>.{first}.goals: expected int, got str" in str(excinfo.value)


def test_a_json_file_with_no_declared_shape_is_itself_a_failure():
    with pytest.raises(ValueError, match="no shape declared"):
        contract.check({"surprise.json": {"anything": 1}})


# --- the two validators must agree ------------------------------------------
node = shutil.which("node")


@pytest.mark.skipif(node is None, reason="node not installed")
def test_the_js_validator_reaches_the_same_verdict(manifest):
    """The page checks with the JS half, so the JS half is tested against the
    same files, not against a story about matching the Python half."""
    script = """
import { readFileSync } from 'node:fs';
import { validate } from './js/contract.js';
const schema = JSON.parse(readFileSync('site_data/schema.json', 'utf8'));
const manifest = JSON.parse(readFileSync('site_data/manifest.json', 'utf8'));
const failures = [];
for (const entry of manifest.files) {
    const value = JSON.parse(readFileSync('site_data/' + entry.name, 'utf8'));
    const problems = validate(value, schema.files[entry.name]);
    if (problems.length) failures.push(entry.name + ': ' + problems.slice(0, 3).join('; '));
}
console.log(JSON.stringify({ files: manifest.files.length, failures }));
"""
    out = subprocess.run([node, "--input-type=module", "-e", script],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    report = json.loads(out.stdout)
    assert report["files"] == len(_published(manifest))
    assert report["failures"] == []


@pytest.mark.skipif(node is None, reason="node not installed")
def test_the_js_validator_rejects_what_the_python_one_rejects():
    """One bad value, both halves, same answer."""
    script = """
import { validate } from './js/contract.js';
const spec = { obj: { games: 'int', age: { optional: 'number' } } };
console.log(JSON.stringify([
    validate({ games: 3 }, spec),
    validate({ games: 3, age: 24.5 }, spec),
    validate({ games: true }, spec),
    validate({ games: 3, age: 24.5, extra: 1 }, spec),
]));
"""
    out = subprocess.run([node, "--input-type=module", "-e", script],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    js = json.loads(out.stdout)
    spec = contract.obj(games=contract.INT, age=contract.opt(contract.NUMBER))
    py = [
        contract.validate({"games": 3}, spec),
        contract.validate({"games": 3, "age": 24.5}, spec),
        contract.validate({"games": True}, spec),
        contract.validate({"games": 3, "age": 24.5, "extra": 1}, spec),
    ]
    assert js == py
    assert js[2] == ["<root>.games: expected int, got bool"]
    assert js[3] == ["<root>.extra: not in the schema"]


@pytest.mark.skipif(node is None, reason="node not installed")
def test_the_page_actually_loads():
    """js/data.js, end to end, with fetch() reading the files on disk.

    This is the part a schema check cannot prove: that the manifest, the schema
    and the loader agree on names, and that the id-keyed views still come back
    with printable names attached.
    """
    out = subprocess.run([node, "js/check_load.mjs"], cwd=ROOT,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "roster_names present: true" in out.stdout
    assert "Error" not in out.stdout
