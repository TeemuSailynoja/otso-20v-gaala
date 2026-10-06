#!/usr/bin/env python3
"""Build the gala site's data files.

This is a **consumer** of the `ultiorg` library, not a second implementation of
it. It loads the corpus and the scraped season files, asks the library for the
analytics views — which are parameterised by the focus team in `teams.yaml` and
keyed by person (canonical name plus the merges in `config/aliases.json`) — turns
those person keys into **site keys**, puts a display name on each person, adds
the aggregate age from the private birthdays file, and writes `site_data/`.

  site_data/players.json      — per-player career + defense, keyed by site key
  site_data/names.json        — site key -> display name, for every person the
                                other files mention (the page renders from this)
  site_data/data_quality.json — what the data cannot say: names with no pelikone
                                id, points with no scorer, markers that are not
                                people, and the id clusters behind the keys
  site_data/pass_network.json — directed pass connections
  site_data/cooccurrence.json — undirected teammate matrix
  site_data/summary.json      — aggregate stats for the landing page
  site_data/years*.json       — year-by-year evolution, per scope and season type
  site_data/frenemies.json    — the rivals
  site_data/trophies.json     — season-level medal record

A **site key** is one key per person: the lowest pelikone player id in that
person's id cluster, or `name:<canon>` when pelikone never registered them. It is
not a pelikone id as such, because pelikone mints a new id per registration — the
longest career on record holds 69 of them. See `src/ultiorg/persons.py`.

Personal data: birthdays live in a gitignored file (see extract_birthdays.py) and
only ever leave here as an aggregate — the mean age of a year's roster. Never
write a birthday, a birth year, or a per-player age into site_data/.
"""

import csv
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

import site_contract as contract

from ultiorg import (
    PersonIds,
    PersonKeys,
    build_career_stats,
    build_cooccurrence,
    build_defense_stats,
    build_frenemies,
    build_pass_network,
    build_trophies,
    build_years,
    canon,
    career_source_report,
    collect_id_clusters,
    is_person,
    load_focus_team,
    plain,
)

BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "data" / "raw"
CORPUS_FILE = BASE_DIR / "data" / "processed" / "match_results.json"
SITE_DATA_DIR = BASE_DIR / "site_data"
TEAMS_FILE = BASE_DIR / "teams.yaml"
ALIASES_FILE = BASE_DIR / "config" / "aliases.json"
BIRTHDAYS_PATH = BASE_DIR / "data" / "private" / "birthdays.csv"

# Age is measured at the middle of the season, not at build time — otherwise the
# 2006 squad reads as a team of 30-year-olds today.
SEASON_AGE_REF = {None: (6, 30), "summer": (7, 30), "winter": (1, 30)}

# Display-name fixes `title()` cannot reach: it uppercases after a space only,
# so it cannot restore an accented first letter or know that a hyphenated name is
# two given names. Keys are person keys, so they go through `canon`.
DISPLAY_OVERRIDES = {canon(k): v for k, v in {
    "euramo sisu": "Euramo Sisu",
    "iivo laaksonen": "Iivo Laaksonen",
    "lacy theo": "Lacy Theo",
    "abhinav omprakash naik": "Abhinav Omprakash Naik",
    "clemens jonas hellmig": "Clemens Jonas Hellmig",
    "samuel-visal roeung": "Samuel-Visal Roeung",
    "\u0161imon kadlec": "\u0160imon Kadlec",
}.items()}


def load_season_files() -> list[dict]:
    """The scraped season files: standings, placements and season cards."""
    out = []
    for path in sorted(RAW_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "teams" in data:
            out.append(data)
    return out


def load_corpus() -> list[dict]:
    """`match_results.json` — every game, with play-by-play attached."""
    return json.loads(CORPUS_FILE.read_text(encoding="utf-8"))


# --- display names ----------------------------------------------------------
def name_key(name: str) -> tuple:
    """Order- and accent-insensitive key, for matching the birthdays file.

    The scrape writes 'hotari roni' while the birthdays file says 'Roni Hotari';
    both keys come out as ('hotari', 'roni').
    """
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return tuple(sorted(p.strip(".-").lower() for p in re.split(r"[\s\-]+", stripped) if p.strip(".-")))


def collect_spellings(seasons: list[dict], games: list[dict], persons: PersonKeys) -> dict:
    """person key -> observed spellings, in two tiers, most frequent first.

    Season cards and gameplay rosters both write `First Last` (rosters with a
    non-breaking space); point rows write `Last First` and are deliberately not
    candidates, because printing "Potrykus Patrick" on a player page is wrong.

    Card spellings win over roster spellings: the card is the form the series
    itself prints, and it is what the site has always shown. Roster spellings are
    the fallback for the handful of players who appeared in a scraped game but
    never on a scraped season card — without them the page prints the canonical
    key, which reads as "luhtala roope".
    """
    tiers: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: {"card": defaultdict(int), "roster": defaultdict(int)}
    )

    def note(raw: str, tier: str) -> None:
        shown = plain(raw)
        if not shown:
            return
        tiers[persons.resolve(raw)][tier][shown] += 1

    for season in seasons:
        for team in season.get("teams", []):
            for row in team.get("players", []):
                note(row.get("name", ""), "card")
    for game in games:
        gp = game.get("gameplay") or {}
        for cells in ("home_players", "away_players"):
            for row in gp.get(cells, []):
                note(row.get("name", ""), "roster")

    def ranked(inner):
        return sorted(inner.items(), key=lambda kv: (-kv[1], kv[0]))

    return {key: {tier: ranked(counts) for tier, counts in by_tier.items()}
            for key, by_tier in tiers.items()}


def display_names(keys, spellings: dict) -> dict:
    """person key -> the name the site prints.

    Preference: an explicit override, then a properly capitalised card spelling,
    then the most frequent card spelling, then the same two steps over roster
    spellings, then the canonical key itself.
    """
    def pick(candidates):
        capitalised = [name for name, _ in candidates if name == name.title()]
        if capitalised:
            return capitalised[0]
        return candidates[0][0] if candidates else None

    out = {}
    for key in keys:
        if key in DISPLAY_OVERRIDES:
            out[key] = DISPLAY_OVERRIDES[key]
            continue
        by_tier = spellings.get(key, {})
        out[key] = (pick(by_tier.get("card", []))
                    or pick(by_tier.get("roster", []))
                    or key)
    return out


# --- personal data (aggregate only) ----------------------------------------
def load_birthdays(path: Path = BIRTHDAYS_PATH) -> dict:
    """{name_key: date of birth} from the private CSV, or {} if it is absent.

    Absent is normal — the file never ships to a checkout, and the build simply
    omits the age stat in that case.
    """
    if not path.exists():
        return {}
    out = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            iso = (row.get("birthday") or "").strip()
            name = (row.get("name") or "").strip()
            if not name or not iso:
                continue
            try:
                out[name_key(name)] = date.fromisoformat(iso)
            except ValueError:
                continue
    return out


def age_at(bday: date, year: int, month: int, day: int) -> int:
    return (year - bday.year) - ((month, day) < (bday.month, bday.day))


def add_ages(years: dict, season_type: str, birthdays: dict) -> None:
    """Add `avg_age` / `avg_age_known` to each year row, in place.

    Honest about its basis: the birthdays file is a top-scorers export, so some
    roster players have no recorded birthday, and `avg_age_known` says how many
    did.
    """
    if not birthdays:
        return
    ref_month, ref_day = SEASON_AGE_REF.get(season_type, (6, 30))
    for year, row in years.items():
        ages = [age_at(birthdays[k], int(year), ref_month, ref_day)
                for k in map(name_key, row["roster"]) if k in birthdays]
        if ages:
            row["avg_age"] = round(sum(ages) / len(ages), 1)
            row["avg_age_known"] = len(ages)


# --- landing page -----------------------------------------------------------
def build_summary(players: dict, pass_network: dict, cooccurrence: dict,
                  years: dict, games: list[dict], focus, display_of: dict) -> dict:
    """The aggregate cards on the landing page.

    Every entry carries both the site key (`id`) and the name to print (`name`):
    the page links by id and renders from `names.json`, so a rename never breaks a
    link. `pass_network` is `{"received": …, "given": …}`, so the connection counts
    read `received` — reading the outer dict itself used to publish the two words
    "received" and "given" as the most connected players.
    """
    games_with_play = sum(1 for g in games if g.get("gameplay"))

    wins = losses = goals_for = goals_against = 0
    for game in games:
        gp = game.get("gameplay")
        if not gp:
            continue
        home_is = focus.matches(gp.get("home_team", ""))
        away_is = focus.matches(gp.get("away_team", ""))
        if not home_is and not away_is:
            continue
        our_score = gp["away_score"] if away_is else gp["home_score"]
        opp_score = gp["home_score"] if away_is else gp["away_score"]
        goals_for += our_score
        goals_against += opp_score
        if our_score > opp_score:
            wins += 1
        elif our_score < opp_score:
            losses += 1

    def top(items, key, n, fields):
        ranked = sorted(items, key=lambda kv: -key(kv[1]))[:n]
        return [{"name": name, **{f: stats[f] for f in fields}} for name, stats in ranked]

    def named(key: str) -> str:
        return display_of.get(key, key)

    top_scorers = [
        {"id": n, "name": named(n), "total": p["total"], "goals": p["goals"],
         "assists": p["assists"], "games": p["games"]}
        for n, p in sorted(players.items(), key=lambda x: x[1]["total"], reverse=True)[:15]
    ]
    top_assists = [
        {"id": n, "name": named(n), "assists": p["assists"], "goals": p["goals"],
         "total": p["total"], "games": p["games"]}
        for n, p in sorted(players.items(), key=lambda x: x[1]["assists"], reverse=True)[:15]
    ]
    longest_careers = [
        {"id": n, "name": named(n), "seasons": p["season_count"],
         "years": f"{p['first_year']}-{p['last_year']}", "games": p["games"]}
        for n, p in sorted(players.items(), key=lambda x: x[1]["season_count"], reverse=True)[:10]
    ]
    most_connected = [
        {"id": n, "name": named(n), "connections": len(partners)}
        for n, partners in sorted(pass_network["received"].items(), key=lambda kv: -len(kv[1]))[:10]
        if partners
    ]
    most_teammates = [
        {"id": n, "name": named(n), "teammates": len(partners)}
        for n, partners in sorted(cooccurrence.items(), key=lambda kv: -len(kv[1]))[:10]
        if partners
    ]
    scored = [(n, p) for n, p in players.items() if p["games"] >= 10 and p["total"] > 0]
    goals_per_match = [
        {"id": n, "name": named(n), "goals_per_match": round(p["total"] / p["games"], 2),
         "total": p["total"], "games": p["games"]}
        for n, p in sorted(scored, key=lambda x: x[1]["total"] / x[1]["games"], reverse=True)[:10]
    ]

    # Anniversary count, not a count of distinct calendar years in the data. The
    # data spans 2006-2026, but 2026 is still in progress, so counting it gives
    # 21 — wrong for a 20th anniversary gala. Full years elapsed since the first
    # season is what the milestone means.
    first_year = min(int(y) for y in years) if years else 0
    years_count = max(date.today().year - first_year, 0) if first_year else len(years)

    return {
        "total_matches": games_with_play,
        "total_players": len(players),
        "total_wins": wins,
        "total_losses": losses,
        "total_goals_for": goals_for,
        "total_goals_against": goals_against,
        "win_percentage": int(round(wins / (wins + losses) * 100)) if (wins + losses) else 0,
        "top_scorers": top_scorers,
        "top_assists": top_assists,
        "longest_careers": longest_careers,
        "most_connected": most_connected,
        "most_teammates": most_teammates,
        "goals_per_match": goals_per_match,
        "years_count": years_count,
        "first_year": first_year,
        "current_year": date.today().year,
    }


# --- what the data cannot say ----------------------------------------------
def build_quality_report(games: list[dict], ids: PersonIds, persons: PersonKeys,
                         player_ids: set, names: dict, used_keys: set,
                         sources: dict) -> dict:
    """`data_quality.json` — the gaps, written down instead of quietly averaged away.

    The site's totals are only as good as the name→person matching, and that
    matching fails in three different ways. Each one is counted here so a reader
    of `players.json` can tell a zero from an unknown.
    """
    slots: dict[str, dict[str, int]] = defaultdict(lambda: {"scorer": 0, "passer": 0})
    markers: dict[str, dict[str, int]] = defaultdict(lambda: {"scorer": 0, "passer": 0})
    points = no_scorer = possession_unknown = 0

    for game in games:
        gp = game.get("gameplay") or {}
        for point in gp.get("points", []):
            if point.get("type") != "point":
                continue
            points += 1
            scorer = plain(point.get("scorer", ""))
            passer = plain(point.get("passer", ""))
            if not scorer:
                no_scorer += 1
            if not point.get("possession_known"):
                possession_unknown += 1
            for field, value in (("scorer", scorer), ("passer", passer)):
                if not value:
                    continue
                if not is_person(value):
                    markers[value][field] += 1
                    continue
                slots[persons.resolve(value)][field] += 1

    # A name in the point table that joins no roster: counted, not dropped, and
    # keyed as `name:<canon>` everywhere it appears.
    unresolved = [
        {"person_key": key, "site_key": ids.site_key(key), **counts}
        for key, counts in sorted(slots.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))
        if key and not ids.clusters.get(key)
    ]
    # Keys the site data references that are not in the site's own player table —
    # the rivals in frenemies, mostly, which is expected. The count is the check
    # that the key space is not leaking strangers into players.json.
    outside = sorted(key for key in used_keys if key not in player_ids)

    clusters = sorted(((len(v), k) for k, v in ids.clusters.items()), reverse=True)
    return {
        "career_sources": {
            "rule": sources["rule"],
            "pairs": sources["pairs"],
            "published": sources["published"],
            "card_only": sources["card_only"],
            "play_only": sources["play_only"],
            "seasons": sources["seasons"],
            "note": (
                "The career table takes the larger of the season card and the "
                "play-by-play for each person-season. Adding them counted most "
                "careers twice. `seasons` lists every season where the two sources "
                "disagree, biggest gap first: there the published figure comes from "
                "whichever source saw more, and a season with no play-by-play at all "
                "means the scrape never got that season's games."
            ),
        },
        "keys": {
            "explained": (
                "A site key is the lowest pelikone player id in a person's id cluster, "
                "or name:<canon> when no roster ever carried an id for that name. "
                "pelikone mints a new id per registration, so one person has many ids; "
                "names.json maps every key used in site_data back to a printable name."
            ),
            "keys_used_in_site_data": len(used_keys),
            "named": len(names),
            "in_the_player_table": len(player_ids),
            "pseudo_keyed": sum(1 for key in used_keys if key.startswith("name:")),
        },
        "id_clusters": {
            "persons_seen_in_rosters": len(ids.clusters),
            "persons_with_multiple_ids": len(ids.multi_id),
            "max_ids_for_one_person": clusters[0][0] if clusters else 0,
            "largest": [
                {"site_key": ids.site_key(person), "ids": count, "person_key": person}
                for count, person in clusters[:10] if count > 1
            ],
        },
        "aliases_asserted": dict(sorted(persons.aliases.items())),
        "points": {
            "total": points,
            "no_scorer_named": no_scorer,
            "possession_unknown": possession_unknown,
            "possession_note": (
                "Points whose starting possession cannot be read from the page are "
                "counted as offense-initiated in the published defense totals."
            ),
        },
        "non_person_markers": [
            {"value": value, **counts,
             "note": "a scoring event label in the point table, not a player"}
            for value, counts in sorted(markers.items(),
                                        key=lambda kv: -(kv[1]["scorer"] + kv[1]["passer"]))
        ],
        "unresolved_names": unresolved,
        "unresolved_note": (
            "A name in the point table that joins no roster anywhere in the archive. "
            "It is still counted, under a name:<canon> key, and listed here. The fact "
            "store applies a stricter test — a name must also appear in the pelikone "
            "player index, which covers the current season only — so its count of "
            "`name:` keys is larger than this one by design."
        ),
        "keys_outside_the_player_table": {
            "count": len(outside),
            "note": (
                "Expected: frenemies names rivals, who are not in players.json. "
                "A rise here that is not matched by a rise in rivals is a leak."
            ),
        },
    }


def main() -> None:
    focus = load_focus_team(TEAMS_FILE)
    if focus is None:
        raise SystemExit(f"no focus team: write {TEAMS_FILE} (see teams.yaml in git)")
    persons = PersonKeys.from_file(ALIASES_FILE)
    print(f"Focus team: {focus.name} ({len(persons.aliases)} identity merge(s) asserted)")

    seasons = load_season_files()
    games = load_corpus()
    print(f"Loaded {len(seasons)} season files, {len(games)} games")

    season_names = {s["id"]: s.get("name", "") for s in seasons if s.get("id")}

    print("Building career stats...")
    career = build_career_stats(seasons, games, focus, persons, season_names)
    print(f"  {len(career)} players")
    career_sources = career_source_report(seasons, games, focus, persons, season_names)

    print("Building defense stats...")
    defense = build_defense_stats(games, focus, persons)
    print(f"  {len(defense)} players with defense stats")

    print("Building pass network...")
    pass_network = build_pass_network(games, focus, career.keys(), persons)
    received, given = pass_network["received"], pass_network["given"]
    print(f"  {len(received)} received, {len(given)} gave, "
          f"{sum(len(v) for v in received.values())} directed edges")

    print("Building co-occurrence...")
    cooccurrence = build_cooccurrence(games, focus, career.keys(), persons)
    print(f"  {len(cooccurrence)} players, {sum(len(v) for v in cooccurrence.values()) // 2} edges")

    print("Building years...")
    birthdays = load_birthdays()
    if not birthdays:
        print("  no birthdays file: the age stat is omitted (expected on a fresh clone)")
    years = {}
    for filename, scope, kind in [
        ("years_otso.json", "main", None),
        ("years_all_bears.json", "all", None),
        ("years_otso_summer.json", "main", "summer"),
        ("years_all_bears_summer.json", "all", "summer"),
        ("years_otso_winter.json", "main", "winter"),
        ("years_all_bears_winter.json", "all", "winter"),
    ]:
        rows = build_years(games, focus, scope=scope, season_type_filter=kind,
                           season_names=season_names, persons=persons)
        add_ages(rows, kind, birthdays)
        years[filename] = rows
    print(f"  {len(years['years_otso.json'])} years (main), "
          f"{len(years['years_all_bears.json'])} years (all squads)")

    print("Building frenemies...")
    frenemies = build_frenemies(games, focus, persons=persons)
    print(f"  {len(frenemies)} rivals")

    # --- identity: person key -> site key, and the name each key prints -------
    #
    # Every person mentioned by any view gets a key, not only the ones in the
    # career table: a rival in frenemies and a name in a year's roster are people
    # the page has to be able to print and, where it can, link.
    clusters = collect_id_clusters(games, seasons, persons)
    mentioned = set(career) | set(defense)
    for partners in list(received.values()) + list(given.values()) + list(cooccurrence.values()):
        mentioned |= set(partners)
    for row in years["years_all_bears.json"].values():
        mentioned |= set(row["roster"])
    mentioned |= {entry["id"] for entry in frenemies}
    mentioned.discard("")
    for person in mentioned:
        clusters.setdefault(person, set())
    ids = PersonIds.build(clusters, {})
    print(f"Identity: {len(ids.key_of)} people seen in rosters, {len(ids.multi_id)} with "
          f"more than one pelikone id")

    spellings = collect_spellings(seasons, games, persons)
    display = display_names(mentioned, spellings)
    names = {ids.site_key(person): display[person] for person in sorted(mentioned)}

    # Re-key every view. After this point nothing in site_data is keyed by a name.
    players = {ids.site_key(key): stats for key, stats in career.items()}
    for key, stats in defense.items():
        site_key = ids.site_key(key)
        if site_key in players:
            players[site_key].update(stats)
    pass_network = {axis: {ids.site_key(me): ids.rekey(them) for me, them in partners.items()}
                    for axis, partners in pass_network.items()}
    cooccurrence = {ids.site_key(me): ids.rekey(them) for me, them in cooccurrence.items()}
    for rows in years.values():
        for row in rows.values():
            row["roster"] = [ids.site_key(person) for person in row["roster"]]
    for entry in frenemies:
        entry["id"] = ids.site_key(entry["id"])
        # Print the resolved display name, not whichever spelling the first game
        # happened to use; the id is what links, so this cannot break a URL.
        entry["name"] = names.get(entry["id"], entry["name"])

    # Every key any file references, so the quality report can prove that nothing
    # in site_data is keyed by something names.json cannot name.
    used: set = set(players)
    for partners in list(pass_network["received"].values()) + list(pass_network["given"].values()) \
            + list(cooccurrence.values()):
        used |= set(partners)
    for axis in ("received", "given"):
        used |= set(pass_network[axis])
    used |= set(cooccurrence)
    used |= {entry["id"] for entry in frenemies}
    for rows in years.values():
        for row in rows.values():
            used |= set(row["roster"])

    print("Building summary...")
    summary = build_summary(players, pass_network, cooccurrence,
                            years["years_otso.json"], games, focus, names)

    print("Building trophies...")
    trophies = build_trophies(seasons, focus)
    missing = [r["event"] for r in trophies["seasons"]
               if r["event"] not in {s.get("id") for s in seasons}]
    for event in missing:
        print(f"  WARNING: no season file for championship event {event}")
    totals = trophies["totals"]["all"]
    print(f"  {totals['gold']} gold, {totals['silver']} silver, {totals['bronze']} bronze "
          f"= {totals['podiums']} podiums in {totals['contested']} seasons contested")

    # The invariant that makes ID keys usable: every key any file references is a
    # key names.json can name. This is what catches a half-rekeyed view — a person
    # key left in a site-keyed map is invisible to the page and silently renders
    # as a raw canonical name.
    unnamed = sorted(key for key in used if key not in names)
    if unnamed:
        raise SystemExit(
            f"{len(unnamed)} site keys have no entry in names.json, "
            f"e.g. {unnamed[:5]} — a view was not re-keyed"
        )

    quality = build_quality_report(games, ids, persons, set(players), names, used,
                                   career_sources)
    print(f"Quality: {len(used)} keys in site_data, "
          f"{quality['points']['no_scorer_named']} points with no scorer, "
          f"{len(quality['unresolved_names'])} unresolved names, "
          f"{quality['points']['possession_unknown']} points of unknown possession")
    print(f"  career sources: {career_sources['published']['goals']} goals, "
          f"{career_sources['card_only']['goals']} of them beyond the point table, "
          f"{len(career_sources['seasons'])} seasons where the sources disagree")

    files = {
        "players.json": players,
        "names.json": names,
        "data_quality.json": quality,
        "pass_network.json": pass_network,
        "cooccurrence.json": cooccurrence,
        "summary.json": summary,
        "frenemies.json": frenemies,
        "trophies.json": trophies,
        **years,
    }

    SITE_DATA_DIR.mkdir(exist_ok=True)
    payload = {name: json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
               for name, data in files.items()}

    # The contract is checked before anything lands on disk: a file the page
    # would reject never gets published, and a file with no declared shape is
    # itself a failure. site_contract.SHAPE is the same document js/contract.js
    # validates against in the browser.
    contract.check(files)
    for name, blob in payload.items():
        (SITE_DATA_DIR / name).write_bytes(blob)
        print(f"  Written {name} ({len(blob) / 1024:.1f} KB)")

    version = contract.write(SITE_DATA_DIR, payload)
    manifest = contract.read_manifest(SITE_DATA_DIR)
    unread = [entry["name"] for entry in manifest["files"] if not entry["fetched_by_page"]]
    print(f"  manifest version {version}: {len(manifest['files'])} files, "
          f"{len(contract.PAGE_FILES)} fetched by the page")
    if unread:
        print(f"  published but not read by the page: {', '.join(sorted(unread))}")

    # Anything in site_data/ that this build did not write is stale: it is still
    # served, still cached by the CDN, and invisible to the manifest. Four such
    # files had accumulated (players.csv, player_names.txt, season_mapping.json,
    # years.json) — nothing fetched them, and the code that wrote them is gone.
    published = {entry["name"] for entry in manifest["files"]} | {"manifest.json", "schema.json"}
    for stale in sorted(SITE_DATA_DIR.iterdir()):
        if stale.is_file() and stale.name not in published:
            stale.unlink()
            print(f"  Removed stale {stale.name} (not written by this build)")

    print("\nDone! Site data ready in site_data/")


if __name__ == "__main__":
    main()
