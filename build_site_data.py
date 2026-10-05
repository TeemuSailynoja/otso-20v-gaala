#!/usr/bin/env python3
"""Build the gala site's data files.

This is a **consumer** of the `ultiorg` library, not a second implementation of
it. It loads the corpus and the scraped season files, asks the library for the
analytics views — which are parameterised by the focus team in `teams.yaml` and
keyed by person (canonical name plus the merges in `config/aliases.json`) — puts
a display name on each person, adds the aggregate age from the private birthdays
file, and writes `site_data/`.

  site_data/players.json      — per-player career + defense, keyed by display name
  site_data/pass_network.json — directed pass connections
  site_data/cooccurrence.json — undirected teammate matrix
  site_data/summary.json      — aggregate stats for the landing page
  site_data/years*.json       — year-by-year evolution, per scope and season type
  site_data/frenemies.json    — the rivals
  site_data/trophies.json     — season-level medal record

Personal data: birthdays live in a gitignored file (see extract_birthdays.py) and
only ever leave here as an aggregate — the mean age of a year's roster. Never
write a birthday, a birth year, or a per-player age into site_data/.
"""

import csv
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

from ultiorg import (
    PersonKeys,
    build_career_stats,
    build_cooccurrence,
    build_defense_stats,
    build_frenemies,
    build_pass_network,
    build_trophies,
    build_years,
    canon,
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
                for k in map(name_key, row["roster_names"]) if k in birthdays]
        if ages:
            row["avg_age"] = round(sum(ages) / len(ages), 1)
            row["avg_age_known"] = len(ages)


# --- landing page -----------------------------------------------------------
def build_summary(players: dict, pass_network: dict, cooccurrence: dict,
                  years: dict, games: list[dict], focus) -> dict:
    """The aggregate cards on the landing page.

    `players` is display-keyed, `pass_network` is `{"received": …, "given": …}`,
    so the connection counts read `received` — reading the outer dict itself used
    to publish the two words "received" and "given" as the most connected
    players.
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

    top_scorers = [
        {"name": n, "total": p["total"], "goals": p["goals"], "assists": p["assists"], "games": p["games"]}
        for n, p in sorted(players.items(), key=lambda x: x[1]["total"], reverse=True)[:15]
    ]
    top_assists = [
        {"name": n, "assists": p["assists"], "goals": p["goals"], "total": p["total"], "games": p["games"]}
        for n, p in sorted(players.items(), key=lambda x: x[1]["assists"], reverse=True)[:15]
    ]
    longest_careers = [
        {"name": n, "seasons": p["season_count"], "years": f"{p['first_year']}-{p['last_year']}", "games": p["games"]}
        for n, p in sorted(players.items(), key=lambda x: x[1]["season_count"], reverse=True)[:10]
    ]
    most_connected = [
        {"name": n, "connections": len(partners)}
        for n, partners in sorted(pass_network["received"].items(), key=lambda kv: -len(kv[1]))[:10]
        if partners
    ]
    most_teammates = [
        {"name": n, "teammates": len(partners)}
        for n, partners in sorted(cooccurrence.items(), key=lambda kv: -len(kv[1]))[:10]
        if partners
    ]
    scored = [(n, p) for n, p in players.items() if p["games"] >= 10 and p["total"] > 0]
    goals_per_match = [
        {"name": n, "goals_per_match": round(p["total"] / p["games"], 2), "total": p["total"], "games": p["games"]}
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

    print("Building defense stats...")
    defense = build_defense_stats(games, focus, persons)
    print(f"  {len(defense)} players with defense stats")

    print("Resolving display names...")
    spellings = collect_spellings(seasons, games, persons)
    display = display_names(career, spellings)
    players = {display[key]: stats for key, stats in career.items()}
    for key, stats in defense.items():
        shown = display.get(key)
        if shown in players:
            players[shown].update(stats)

    names_for_views = list(players)
    print("Building pass network...")
    pass_network = build_pass_network(games, focus, names_for_views, persons)
    received, given = pass_network["received"], pass_network["given"]
    print(f"  {len(received)} received, {len(given)} gave, "
          f"{sum(len(v) for v in received.values())} directed edges")

    print("Building co-occurrence...")
    cooccurrence = build_cooccurrence(games, focus, names_for_views, persons)
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

    print("Building summary...")
    summary = build_summary(players, pass_network, cooccurrence, years["years_otso.json"], games, focus)

    print("Building trophies...")
    trophies = build_trophies(seasons, focus)
    missing = [r["event"] for r in trophies["seasons"]
               if r["event"] not in {s.get("id") for s in seasons}]
    for event in missing:
        print(f"  WARNING: no season file for championship event {event}")
    totals = trophies["totals"]["all"]
    print(f"  {totals['gold']} gold, {totals['silver']} silver, {totals['bronze']} bronze "
          f"= {totals['podiums']} podiums in {totals['contested']} seasons contested")

    files = {
        "players.json": players,
        "pass_network.json": pass_network,
        "cooccurrence.json": cooccurrence,
        "summary.json": summary,
        "frenemies.json": frenemies,
        "trophies.json": trophies,
        **years,
    }

    SITE_DATA_DIR.mkdir(exist_ok=True)
    for filename, data in files.items():
        path = SITE_DATA_DIR / filename
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Written {filename} ({path.stat().st_size / 1024:.1f} KB)")

    stamp_build_version(files)
    print("\nDone! Site data ready in site_data/")


def stamp_build_version(files: dict) -> None:
    """Stamp a content hash of the site data into index.html as DATA_VERSION.

    index.html appends ?v=<hash> to every JSON fetch. Without it, browsers and
    the GitHub Pages CDN serve stale data after a rebuild — the old frenemies
    team bug stayed visible long after the fix shipped. Phase 10 replaces this
    with site_data/manifest.json.
    """
    digest = hashlib.sha256()
    for filename in sorted(files):
        digest.update(filename.encode("utf-8"))
        digest.update((SITE_DATA_DIR / filename).read_bytes())
    version = digest.hexdigest()[:12]

    index = BASE_DIR / "index.html"
    text = index.read_text(encoding="utf-8")
    new, n = re.subn(
        r"(// BUILD_VERSION_START\s*\n\s*const DATA_VERSION = ')[^']*(';)",
        lambda m: m.group(1) + version + m.group(2),
        text,
        count=1,
    )
    if n == 0:
        print("  WARNING: BUILD_VERSION markers not found in index.html; not stamped")
        return
    index.write_text(new, encoding="utf-8")
    print(f"  Stamped DATA_VERSION={version} into index.html")


if __name__ == "__main__":
    main()
