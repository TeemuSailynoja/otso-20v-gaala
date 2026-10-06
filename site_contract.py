"""The contract between this build and the page that reads it.

`site_data/manifest.json` says what the build published and which version it is.
`site_data/schema.json` says what shape each file has. Both are written here and
read by the page (`js/data.js` fetches the manifest, `js/contract.js` validates
what it then loads), and both are checked here before anything is written: a
shape violation fails the build rather than arriving as a blank grid.

**Why a hand-written shape language and not JSON Schema.** The page validates on
load with no build step and no dependency, so the checking code has to be small
enough to sit in a browser module — and the same rules have to be checkable in
Python at build time. Two small validators over one tiny grammar are easier to
keep honest than a draft-07 subset implemented twice. `tests/test_contract.py`
runs *both* validators over the built files, so they cannot drift apart silently.

The grammar (identical in `js/contract.js`):

    "int" "number" "str" "bool" "null"     a scalar, by JSON type
    {"obj": {field: spec, ...}}            object; every listed field required,
                                           no unlisted field allowed
    {"optional": spec}                     field may be absent (obj only)
    {"map": spec}                          object with any keys, values match
    {"list": spec}                         array, every item matches
    {"any": [spec, ...]}                   at least one matches

`int` accepts a JSON integer only — `3.0` is a `number`, not an `int` — because a
count that arrives as a float means something upstream divided when it should not
have.

One asymmetry is worth naming: JSON has a single number type, so `3.0` parses to
a float in Python and to the number `3` in JavaScript. The strict rule is the
Python one, and it runs first — the build refuses such a file, so the page never
sees one. The JS half is a backstop against a file that got to the CDN without
passing the build, not a second opinion on typing.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

SCHEMA_VERSION = 1

# --- the shape language, as data --------------------------------------------
INT, NUMBER, STR, BOOL, NULL = "int", "number", "str", "bool", "null"


def obj(**fields: Any) -> Dict[str, Any]:
    return {"obj": fields}


def opt(spec: Any) -> Dict[str, Any]:
    return {"optional": spec}


def map_(spec: Any) -> Dict[str, Any]:
    return {"map": spec}


def lst(spec: Any) -> Dict[str, Any]:
    return {"list": spec}


def any_(*specs: Any) -> Dict[str, Any]:
    return {"any": list(specs)}


# Repeated record shapes. Named because the contract is shorter and clearer when
# "a player brief in summary.json" is one thing said once.
_PLAYER_BRIEF = obj(id=STR, name=STR, games=INT, goals=INT, assists=INT, total=INT)
_TALLY = obj(gold=INT, silver=INT, bronze=INT, podiums=INT, contested=INT)
_YEARS = map_(obj(
    matches=INT, wins=INT, losses=INT, goals_for=INT, goals_against=INT,
    roster_players=INT, roster=lst(STR),
    # Age needs the gitignored birthdays file; a fresh clone has no such file and
    # the build omits the two keys rather than publishing a zero.
    avg_age=opt(NUMBER), avg_age_known=opt(INT),
))

#: Every JSON file the build may write, and what it must look like. A file with
#: no entry here is a build error: the contract is complete or it is decoration.
SHAPE: Dict[str, Any] = {
    "players.json": map_(obj(
        seasons=lst(STR), season_count=INT, years=lst(INT), year_count=INT,
        first_year=any_(INT, NULL), last_year=any_(INT, NULL),
        games=INT, goals=INT, assists=INT, total=INT, teams=lst(STR),
        season_types=obj(summer=lst(INT), winter=lst(INT), other=lst(INT)),
        summer_games=INT, summer_goals=INT, summer_assists=INT,
        winter_games=INT, winter_goals=INT, winter_assists=INT,
        defense_points=INT, offense_points=INT, total_points=INT,
        # Absent — not zero, not null — for a player with no Otso point row in
        # the scrape: 19 of 171. The distinction matters: absent means "we never
        # saw this person score in an Otso game", zero would mean they scored
        # nothing in games we did see.
        defense_goals=opt(INT), defense_assists=opt(INT),
        offense_goals=opt(INT), offense_assists=opt(INT),
    )),
    "pass_network.json": obj(received=map_(map_(INT)), given=map_(map_(INT))),
    "cooccurrence.json": map_(map_(INT)),
    "names.json": map_(STR),
    "frenemies.json": lst(obj(
        id=STR, name=STR, games=INT, wins=INT, losses=INT, goals=INT,
        assists=INT, total=INT, ppg=NUMBER, teams=lst(STR), rank=INT,
    )),
    "summary.json": obj(
        total_matches=INT, total_players=INT, total_wins=INT, total_losses=INT,
        total_goals_for=INT, total_goals_against=INT, win_percentage=INT,
        top_scorers=lst(_PLAYER_BRIEF), top_assists=lst(_PLAYER_BRIEF),
        longest_careers=lst(obj(id=STR, name=STR, games=INT, seasons=INT,
                                # A display range — "2007-2026" — not a year list.
                                # `players.json.years` is a list of ints and this
                                # is a string: the same word meaning two things in
                                # one directory. Left as-is because the page reads
                                # it; Phase 11 renames it to `year_range`.
                                years=STR)),
        most_connected=lst(obj(id=STR, name=STR, connections=INT)),
        most_teammates=lst(obj(id=STR, name=STR, teammates=INT)),
        goals_per_match=lst(obj(id=STR, name=STR, games=INT,
                               goals_per_match=NUMBER, total=INT)),
        years_count=INT, first_year=INT, current_year=INT,
    ),
    "trophies.json": obj(
        seasons=lst(obj(
            year=INT, season=STR, event=STR, played=BOOL,
            medal=any_(STR, NULL), team=any_(STR, NULL), placement=any_(STR, NULL),
            entries=lst(obj(team=STR, placement=STR, medal=any_(STR, NULL))),
        )),
        totals=obj(summer=_TALLY, winter=_TALLY, all=_TALLY),
    ),
    "years_otso.json": _YEARS,
    "years_otso_summer.json": _YEARS,
    "years_otso_winter.json": _YEARS,
    "years_all_bears.json": _YEARS,
    "years_all_bears_summer.json": _YEARS,
    "years_all_bears_winter.json": _YEARS,
    "years.json": _YEARS,
    "season_mapping.json": map_(obj(type=STR, name=STR)),
    "data_quality.json": obj(
        career_sources=obj(
            rule=STR, note=STR,
            pairs=obj(both=INT, agree=INT, card_higher=INT, play_higher=INT,
                      card_only=INT, play_only=INT),
            published=obj(goals=INT, assists=INT),
            card_only=obj(goals=INT, assists=INT, note=STR),
            play_only=obj(goals=INT, assists=INT, note=STR),
            seasons=lst(obj(season=STR, name=STR, people=INT,
                            card_goals=INT, card_assists=INT,
                            play_goals=INT, play_assists=INT,
                            published_goals=INT, published_assists=INT, gap=INT)),
        ),
        keys=obj(explained=STR, keys_used_in_site_data=INT, named=INT,
                 in_the_player_table=INT, pseudo_keyed=INT),
        id_clusters=obj(persons_seen_in_rosters=INT, persons_with_multiple_ids=INT,
                        max_ids_for_one_person=INT,
                        largest=lst(obj(site_key=STR, ids=INT, person_key=STR))),
        aliases_asserted=map_(STR),
        points=obj(total=INT, no_scorer_named=INT, possession_unknown=INT,
                   possession_note=STR),
        non_person_markers=lst(obj(value=STR, scorer=INT, passer=INT, note=STR)),
        unresolved_names=lst(obj(person_key=STR, site_key=STR, scorer=INT, passer=INT)),
        unresolved_note=STR,
        keys_outside_the_player_table=obj(count=INT, note=STR),
    ),
}

#: The files the page fetches. The manifest carries this to the page, so the
#: fetch list cannot drift from what the build publishes: `js/data.js` asks for
#: exactly what it is told to ask for. Everything published but not listed here
#: is dead weight on the CDN, and the build says how much there is.
PAGE_FILES = [
    "players.json", "pass_network.json", "cooccurrence.json", "summary.json",
    "frenemies.json", "trophies.json", "names.json",
    "years_otso.json", "years_otso_summer.json", "years_otso_winter.json",
]

MAX_PROBLEMS = 20


# --- the Python validator ----------------------------------------------------
def _is_int(value: Any) -> bool:
    """A JSON integer. `True` is an int in Python, and is not one here."""
    return isinstance(value, int) and not isinstance(value, bool)


def validate(value: Any, spec: Any, path: str = "") -> List[str]:
    """Return a list of `"path: problem"` strings. Empty means the value fits.

    The path is dotted (`players.6890.goals`) so a failure names the record, not
    just the file — which is the difference between a contract and a shrug.
    """
    problems: List[str] = []
    if isinstance(spec, str):
        ok = {
            INT: _is_int, NUMBER: lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            STR: lambda v: isinstance(v, str), BOOL: lambda v: isinstance(v, bool),
            NULL: lambda v: v is None,
        }[spec](value)
        if not ok:
            problems.append(f"{_where(path)}: expected {spec}, got {_kind(value)}")
        return problems

    if not isinstance(spec, dict):
        return [f"{_where(path)}: bad spec {spec!r}"]

    if "any" in spec:
        for alternative in spec["any"]:
            if not validate(value, alternative, path):
                return []
        wanted = " or ".join(_describe(a) for a in spec["any"])
        problems.append(f"{_where(path)}: expected {wanted}, got {_kind(value)}")
        return problems

    if "obj" in spec:
        if not isinstance(value, dict):
            return [f"{_where(path)}: expected an object, got {_kind(value)}"]
        fields = spec["obj"]
        for field, field_spec in fields.items():
            optional = isinstance(field_spec, dict) and "optional" in field_spec
            if optional:
                field_spec = field_spec["optional"]
            if field not in value:
                if not optional:
                    problems.append(f"{_where(path)}.{field}: missing")
                continue
            problems += validate(value[field], field_spec, f"{_where(path)}.{field}")
        for field in value:
            if field not in fields:
                problems.append(f"{_where(path)}.{field}: not in the schema")
        return problems

    if "map" in spec:
        if not isinstance(value, dict):
            return [f"{_where(path)}: expected an object, got {_kind(value)}"]
        for key, item in value.items():
            problems += validate(item, spec["map"], f"{_where(path)}.{key}")
        return problems

    if "list" in spec:
        if not isinstance(value, list):
            return [f"{_where(path)}: expected an array, got {_kind(value)}"]
        for index, item in enumerate(value):
            problems += validate(item, spec["list"], f"{_where(path)}[{index}]")
        return problems

    return [f"{_where(path)}: bad spec {spec!r}"]


def _where(path: str) -> str:
    """The path, or a name for the file itself. Both validators use this exact
    rule, so a failure reads the same in the build log and in the browser."""
    return path or "<root>"


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _describe(spec: Any) -> str:
    if isinstance(spec, str):
        return spec
    if isinstance(spec, dict):
        if "obj" in spec:
            return "object"
        if "map" in spec:
            return "object"
        if "list" in spec:
            return "array"
        if "any" in spec:
            return " or ".join(_describe(s) for s in spec["any"])
        if "optional" in spec:
            return _describe(spec["optional"])
    return repr(spec)


# --- the manifest ------------------------------------------------------------
def content_version(payload: Mapping[str, bytes]) -> str:
    """A hash of everything the version has to cover: the data and the schema.

    The schema is included because a shape change is a contract change: the page
    must refetch the data when the description of it changes, not only when the
    data does.
    """
    digest = hashlib.sha256()
    for name in sorted(payload):
        digest.update(name.encode("utf-8"))
        digest.update(payload[name])
    return digest.hexdigest()[:12]


def manifest_for(version: str, payload: Mapping[str, bytes],
                 page_files: List[str] = PAGE_FILES) -> Dict[str, Any]:
    """`manifest.json` — what was published, at which version, and who reads it.

    No timestamp: the version *is* the identity, and a timestamp would make two
    builds of identical data differ, which would break the rebuild gate.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "version": version,
        "files": [
            {
                "name": name,
                "bytes": len(payload[name]),
                "fetched_by_page": name in page_files,
            }
            for name in sorted(payload)
        ],
    }


def schema_document() -> Dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "files": SHAPE}


def check(payload: Mapping[str, Any]) -> Dict[str, List[str]]:
    """Validate every payload file against SHAPE.

    Raises `ValueError` listing the offending files when anything fails, so a
    build cannot publish a file the page will reject. A JSON file with no entry
    in SHAPE is itself a failure: an unvalidated file in the contract is a hole.
    """
    report: Dict[str, List[str]] = {}
    for name, value in sorted(payload.items()):
        spec = SHAPE.get(name)
        if spec is None:
            report[name] = ["no shape declared in site_contract.SHAPE"]
            continue
        problems = validate(value, spec)
        if problems:
            report[name] = problems[:MAX_PROBLEMS]
    if report:
        lines = [f"  {name}: {problems[0]}" if len(problems) == 1 else
                 f"  {name}: {len(problems)} problems, first: {problems[0]}"
                 for name, problems in report.items()]
        raise ValueError("site data does not match the contract:\n" + "\n".join(lines))
    return report


def write(site_data_dir: Path, payload: Mapping[str, Any],
          page_files: List[str] = PAGE_FILES) -> str:
    """Write manifest.json + schema.json for `payload` and return the version.

    `payload` is the raw bytes of every data file, as written to disk.
    """
    version = content_version(payload)
    manifest = manifest_for(version, payload, page_files)
    (site_data_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (site_data_dir / "schema.json").write_text(
        json.dumps(schema_document(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return version


def read_manifest(site_data_dir: Path) -> Dict[str, Any]:
    return json.loads((site_data_dir / "manifest.json").read_text(encoding="utf-8"))
