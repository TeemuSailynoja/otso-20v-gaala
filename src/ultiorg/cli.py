"""`ultiorg` — fetch, parse, repair and query Ultiorganizer data.

One entry point for everything the data pipeline does, so a fresh clone can be
built by a stranger (or an agent) without reading the source:

    ultiorg fetch all-seasons --gameplay     # crawl -> data/raw/
    ultiorg merge                            # data/raw/ -> data/processed/match_results.json
    ultiorg store                            # corpus -> data/store.sqlite
    ultiorg player "Lehto Santtu" --connections 10

Two rules the whole CLI obeys:

* **Politeness.** Every request goes through one Fetcher: 1.5 s between requests,
  a per-URL cache with a freshness policy per page kind, and `--dry-run` that
  reports what would be fetched and sends nothing. The final line of every command
  is the request count, so an accidental crawl is visible immediately.
* **Nothing is silently lost.** Repairs and merges print what they changed and
  what they skipped; `player` refuses to guess between two people and says so.

`--json` on the query commands makes the output an agent's input.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .aliases import PersonKeys
from .cache import Cache, setup_dirs
from .config import (
    ALIASES_PATH,
    BASE_URL,
    DATA_DIR,
    PROCESSED_DIR,
    RAW_DIR,
    REQUEST_DELAY,
    STORE_PATH,
)
from .corpus import build_corpus, write_corpus
from .fetcher import (
    CSV_KINDS,
    fetch_allclubs,
    fetch_allplayers,
    fetch_allteams,
    fetch_csv,
    fetch_gameplay,
    fetch_games_page,
    fetch_playercard,
    fetch_scorestatus,
    fetch_season_list,
    fetch_statistics,
)
from .http import Fetcher, configure, fetch_url
from .identify import PlayerIndex
from .parsers import (
    classify_season,
    parse_allclubs,
    parse_allplayers,
    parse_allteams,
    parse_csv_pools,
    parse_csv_spirit,
    parse_gameplay,
    parse_games_list,
    parse_playercard,
    parse_scorestatus,
    parse_season_list,
    parse_statistics,
)
from .query import AmbiguousPlayer, Store, UnknownPlayer
from .repair import dedupe_point_rows, migrate_point_fields, refresh_rosters
from .store import build_store, defense_totals

CORPUS = PROCESSED_DIR / "match_results.json"


# --- shared plumbing ---------------------------------------------------------


def _fetcher(args) -> Fetcher:
    data_dir = Path(args.data_dir)
    setup_dirs(data_dir)
    fetcher = configure(
        data_dir=data_dir,
        base_url=args.base_url,
        refresh=args.refresh,
        dry_run=args.dry_run,
        delay=args.delay,
    )
    if args.dry_run:
        print("dry run: no requests will be made")
    return fetcher


def _report(fetcher: Fetcher, data_dir: Path) -> None:
    print(f"traffic: {fetcher.stats.summary()}")
    print(f"cache:   {Cache(data_dir).counts()}")


def _load_corpus(path: Path) -> List[Dict]:
    if not path.exists():
        raise SystemExit(f"no corpus at {path} — run `ultiorg merge` first")
    return json.loads(path.read_text(encoding="utf-8"))


def _store(args):
    path = Path(args.store) if args.store else Path(args.data_dir) / "store.sqlite"
    try:
        return Store(path)
    except FileNotFoundError as exc:
        raise SystemExit(f"{exc}")


def _emit(payload, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


# --- fetch -------------------------------------------------------------------


def _fetch_season_data(
    season_id: str,
    season_name: str,
    fetcher: Fetcher,
    *,
    gameplay: bool = False,
    otso_only: bool = False,
    csv_only: bool = False,
) -> Dict:
    """One season -> the raw season file shape `corpus.build_corpus` reads."""
    from .fetcher import fetch_player_list, fetch_standings_page, fetch_team_card, fetch_teams_page
    from .parsers import is_otso_team, parse_player_list, parse_standings_page, parse_team_card, parse_teams_page

    print(f"\nseason {season_name} ({season_id})")
    data: Dict = {
        "id": season_id,
        "name": season_name,
        "classified": classify_season(season_id, season_name),
        "teams": [],
        "placements": [],
        "players": [],
        "games": [],
        "results": [],
    }

    if not csv_only:
        teams_html = fetch_teams_page(season_id, fetcher)
        if teams_html:
            data["teams"] = parse_teams_page(teams_html, season_id)
            print(f"  teams: {len(data['teams'])}")

        standings_html = fetch_standings_page(season_id, fetcher)
        if standings_html:
            data["placements"] = parse_standings_page(standings_html, season_id)
            otso = [p for p in data["placements"] if is_otso_team(p["team_name"])]
            print(f"  placements: {len(data['placements'])} ({len(otso)} Otso)")

        for team in data["teams"]:
            if otso_only and not is_otso_team(team["name"]):
                continue
            if team["id"]:
                team_html = fetch_team_card(team["id"], fetcher)
                if team_html:
                    card = parse_team_card(team_html, team["id"])
                    team["players"] = card["players"]
                    team["games"] = card["games"]
                    print(f"  team card {team['name']}: {len(card['players'])} players, {len(card['games'])} games")
            if team.get("player_list_url"):
                list_html = fetch_url(team["player_list_url"], fetcher=fetcher)
                if list_html:
                    team["all_time_players"] = parse_player_list(list_html, team["id"])
                    print(f"  player list {team['name']}: {len(team['all_time_players'])} players")

    if gameplay and not csv_only:
        games_html = fetch_games_page(season_id, fetcher)
        if games_html:
            data["games"] = parse_games_list(games_html, season_id)
            print(f"  games: {len(data['games'])}")
            for game in data["games"]:
                gameplay_html = fetch_gameplay(game["game_id"], fetcher)
                if gameplay_html:
                    game["gameplay"] = parse_gameplay(gameplay_html)
                    print(
                        f"    game {game['game_id']}: {len(game['gameplay'].get('points', []))} points, "
                        f"{len(game['gameplay'].get('home_players', []))}+{len(game['gameplay'].get('away_players', []))} players"
                    )
                else:
                    print(f"    game {game['game_id']}: no gameplay archived")

    return data


def _write_season_file(data_dir: Path, data: Dict) -> Path:
    path = data_dir / "raw" / f"{data['id'].replace('/', '_')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def cmd_fetch(args, fetcher: Fetcher) -> int:
    data_dir = Path(args.data_dir)
    what = args.what

    if what == "seasons":
        seasons = parse_season_list(fetch_season_list(fetcher) or "")
        for season in seasons:
            print(f"{season['id']}\t{season['name']}")
        print(f"{len(seasons)} seasons")
        return 0

    if what == "all-seasons":
        seasons = parse_season_list(fetch_season_list(fetcher) or "")
        if not seasons:
            raise SystemExit("season list page produced no seasons")
        print(f"{len(seasons)} seasons")
        for season in seasons:
            _write_season_file(data_dir, _fetch_season_data(
                season["id"], season["name"], fetcher,
                gameplay=args.gameplay, otso_only=args.otso_only, csv_only=args.csv_only,
            ))
        if not args.no_merge:
            _merge(data_dir, require_gameplay=args.gameplay)
        return 0

    if what == "season":
        _write_season_file(data_dir, _fetch_season_data(
            args.season_id, args.name or args.season_id, fetcher,
            gameplay=args.gameplay, otso_only=args.otso_only, csv_only=args.csv_only,
        ))
        if not args.no_merge:
            _merge(data_dir, require_gameplay=args.gameplay)
        return 0

    if what == "games":
        html = fetch_games_page(args.season_id, fetcher)
        games = parse_games_list(html or "", args.season_id)
        for game in games:
            print(f"{game['game_id']}\t{game['home_team']} {game['home_score']}-{game['away_score']} {game['away_team']}")
        print(f"{len(games)} games")
        return 0

    if what == "players-index":
        players = parse_allplayers(fetch_allplayers(fetcher) or "")
        for player in (players[: args.limit] if args.limit else players):
            print(f"{player['id']}\t{player['name']}")
        print(f"{len(players)} players in the all-players index")
        return 0

    if what == "player":
        card = parse_playercard(fetch_playercard(args.player_id, fetcher=fetcher) or "", args.player_id)
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return 0

    if what == "scoreboard":
        rows = parse_statistics(fetch_statistics(args.season_id, args.list, fetcher) or "")
        for row in rows:
            print(f"{row['section']} / {row['division']} / {row['event']} (series {row['series_id']})")
            for entry in row["top"]:
                print(f"    {entry['rank']}. {entry['name']} — {entry['team']} "
                      f"{entry['goals']}g {entry['assists']}a {entry['total']} (id {entry['player_id']})")
        print(f"{len(rows)} events")
        return 0

    if what == "scorestatus":
        rows = parse_scorestatus(fetch_scorestatus(args.season_id, fetcher) or "", args.season_id)
        for row in rows:
            print(f"{row['rank']}\t{row['player_id']}\t{row['name']}\t{row['team']}\t"
                  f"{row['gp']} gp\t{row['goals']}g\t{row['assists']}a\t{row['total']}")
        print(f"{len(rows)} players")
        return 0

    if what == "allteams":
        teams = parse_allteams(fetch_allteams(fetcher) or "")
        for team in teams:
            print(f"{team['id']}\t{team['name']}\t{team['division']}")
        print(f"{len(teams)} teams")
        return 0

    if what == "allclubs":
        clubs = parse_allclubs(fetch_allclubs(fetcher) or "")
        for club in clubs:
            print(f"{club['id']}\t{club['name']}")
        print(f"{len(clubs)} clubs")
        return 0

    if what == "csv":
        text = fetch_csv(args.kind, args.season_id, fetcher)
        if args.kind == "pools":
            rows = parse_csv_pools(text)
        elif args.kind == "spirit":
            rows = parse_csv_spirit(text)
        else:
            print(text)
            return 0
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        print(f"{len(rows)} rows")
        return 0

    raise SystemExit(f"unknown fetch target: {what}")


# --- merge / store -----------------------------------------------------------


def _merge(data_dir: Path, *, require_gameplay: bool = True) -> None:
    path = data_dir / "processed" / "match_results.json"
    games, stats = build_corpus(data_dir, require_gameplay=require_gameplay)
    write_corpus(path, games)
    print(f"corpus: {stats.summary()} -> {path}")
    print("  sources: " + ", ".join(f"{k}={v}" for k, v in stats.sources.items()))


def cmd_merge(args) -> int:
    _merge(Path(args.data_dir), require_gameplay=not args.no_gameplay)
    return 0


def cmd_store(args) -> int:
    fetcher = _fetcher(args)
    data_dir = Path(args.data_dir)
    html = fetch_allplayers(fetcher)
    players = parse_allplayers(html or "")
    if not players:
        raise SystemExit("player index empty: no cached allplayers page — run `ultiorg fetch players-index` first")
    games = _load_corpus(data_dir / "processed" / "match_results.json")
    conn, stats = build_store(
        Path(args.store) if args.store else data_dir / "store.sqlite",
        games,
        PlayerIndex(players),
        persons=PersonKeys.from_file(Path(args.aliases)),
    )
    conn.close()
    print(
        f"store: {stats.players} player IDs / {stats.persons} persons, {stats.games} games, "
        f"{stats.seasons} seasons, {stats.appearances} appearances, {stats.points} points "
        f"({stats.points_with_possession} with possession, {stats.points_pseudo_keyed} "
        f"pseudo-keyed scorers) -> {args.store or data_dir / 'store.sqlite'}"
    )
    _report(fetcher, data_dir)
    return 0


# --- query -------------------------------------------------------------------


def cmd_player(args) -> int:
    store = _store(args)
    try:
        player = store.player(args.name)
    except (UnknownPlayer, AmbiguousPlayer) as exc:
        raise SystemExit(str(exc))

    common = dict(season=args.season, since=args.since)
    out: Dict = {}
    if args.career or not any((args.connections, args.scoring, args.games)):
        out["career"] = player.career()
    if args.scoring:
        out["scoring"] = player.scoring(possession=args.possession, **common)
    if args.connections:
        out["connections"] = player.connections(top=args.connections, **common)
    if args.games:
        out["games"] = player.games(limit=args.limit, **common)

    if args.json:
        _emit(out, True)
        return 0

    print(f"{player.display_name}  (person {player.person_key}, {len(player.player_ids)} player IDs, known from {player.known_from})")
    if "career" in out:
        career = out["career"]
        print(f"  {career['games']} games, {career['goals']} goals, {career['assists']} assists, "
              f"{career['points']} points ({career['points_per_game']}/game)")
        print(f"  years {career['years'][0]}–{career['years'][-1]}" if career["years"] else "  no seasons")
        print(f"  teams: {', '.join(career['teams'])}")
    if "scoring" in out:
        s = out["scoring"]
        label = s["possession"] or "any"
        print(f"  {label} possession: {s['goals']} goals, {s['assists']} assists, {s['points']} points "
              f"in {s['games']} games ({s['points_per_game']}/game)"
              + (f", {s['possession_unknown']} points with unknown possession excluded" if s["possession"] and s["possession_unknown"] else ""))
    if "connections" in out:
        print(f"  top connections:")
        for row in out["connections"]:
            print(f"    {row['player']:<28} {row['passes']:>4} passes "
                  f"({row['assists_given']} given / {row['assists_received']} received), "
                  f"{row['games_together']} games together"
                  + (f", {row['per_game']}/game" if row["per_game"] else "")
                  + ("" if row["resolved"] else "  [name only, no ID]"))
    if "games" in out:
        for game in out["games"]:
            print(f"    {game['game_id']:<7} {game['season_id']:<12} {game['home_team']} {game['home_score']}-{game['away_score']} {game['away_team']}"
                  f"   {game['team']} {game['goals']}g {game['assists']}a")
    return 0


def cmd_defense(args) -> int:
    store = _store(args)
    conn = store.conn
    totals = defense_totals(conn, args.team)
    if args.json:
        _emit(totals, True)
        return 0
    print(f"{args.team}: {totals['defense_points']} defense-initiated points by {totals['players']} players")
    for row in totals["top"]:
        print(f"  {row['name']:<28} {row['defense_points']}")
    return 0


def cmd_sql(args) -> int:
    store = _store(args)
    try:
        rows = store.sql(args.query)
    except ValueError as exc:
        raise SystemExit(str(exc))
    except sqlite3.Error as exc:
        raise SystemExit(f"query failed: {exc}")
    if not rows:
        print("(no rows)")
        return 0
    headers = list(rows[0])
    print("\t".join(headers))
    for row in rows:
        print("\t".join("" if row[h] is None else str(row[h]) for h in headers))
    print(f"{len(rows)} rows")
    return 0


# --- repair / cache ----------------------------------------------------------


def cmd_repair(args) -> int:
    path = Path(args.data_dir) / "processed" / "match_results.json"
    if not path.exists():
        raise SystemExit(f"no corpus at {path}")
    if args.what == "dedupe-points":
        print(dedupe_point_rows(path).summary())
    elif args.what == "point-fields":
        print(migrate_point_fields(path).summary())
    elif args.what == "rosters":
        print(refresh_rosters(path, Path(args.data_dir) / "raw").summary())
    else:
        raise SystemExit(f"unknown repair: {args.what}")
    return 0


def cmd_cache(args) -> int:
    data_dir = Path(args.data_dir)
    cache = Cache(data_dir)
    if args.what == "stats":
        stats = cache.counts()
        print(f"{stats['pages']} pages, {stats['bytes'] / 1e6:.1f} MB in {cache.cache_dir}")
        for kind, n in sorted(stats["by_kind"].items(), key=lambda kv: -kv[1]):
            print(f"{n:>5}  {kind}")
        return 0
    if args.what == "import":
        print(f"manifest import: {cache.import_manifest(dry_run=args.dry_run)}")
        print(f"raw HTML import: {cache.import_raw_html(dry_run=args.dry_run)}")
        print(f"cache: {Cache(data_dir).counts()}")
        return 0
    raise SystemExit(f"unknown cache command: {args.what}")


# --- parser ------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ultiorg", description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default=str(DATA_DIR), help=f"data directory (default {DATA_DIR})")
    parser.add_argument("--base-url", default=BASE_URL, help=f"Ultiorganizer instance (default {BASE_URL})")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help=f"seconds between requests (default {REQUEST_DELAY})")
    parser.add_argument("--refresh", action="store_true", help="ignore cache freshness and re-download")
    parser.add_argument("--dry-run", action="store_true", help="report what would be fetched; make no requests")
    parser.add_argument("--store", help="fact store path (default <data-dir>/store.sqlite)")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fetch", help="download and parse pages into data/raw/")
    fetch_sub = p.add_subparsers(dest="what", required=True)
    for name, help_text in (
        ("seasons", "list season IDs"),
        ("all-seasons", "every season, one raw file each"),
        ("season", "one season"),
        ("games", "the games list for a season"),
        ("players-index", "the all-players index (name -> player ID)"),
        ("player", "one player card"),
        ("scoreboard", "the statistics scoreboard"),
        ("scorestatus", "per-player scoring for a series"),
        ("allteams", "every team in the instance"),
        ("allclubs", "every club in the instance"),
        ("csv", "a CSV export (current season only)"),
    ):
        target = fetch_sub.add_parser(name, help=help_text)
        if name in ("season", "games", "scorestatus", "scoreboard"):
            target.add_argument("season_id", help="season ID (scorestatus takes the series ID)")
        if name == "scoreboard":
            target.add_argument("--list", default="playerscoreboard", help="scoreboard kind (default %(default)s)")
        if name == "players-index":
            target.add_argument("--limit", type=int, help="print at most this many rows")
        if name == "player":
            target.add_argument("player_id")
        if name == "csv":
            target.add_argument("kind", choices=list(CSV_KINDS))
            target.add_argument("season_id")
        if name in ("season", "all-seasons"):
            target.add_argument("--gameplay", action="store_true", help="also fetch point-by-point for every game")
            target.add_argument("--otso-only", action="store_true", help="skip other clubs' team cards (fewer requests)")
            target.add_argument("--csv-only", action="store_true", help="CSV exports only (current season)")
            target.add_argument("--no-merge", action="store_true", help="do not recompose the corpus afterwards")
        if name == "season":
            target.add_argument("--name", help="display name for the season file")

    p = sub.add_parser("merge", help="recompose data/processed/match_results.json from everything on disk")
    p.add_argument("--no-gameplay", action="store_true", help="keep entries whose HTML is not archived")

    p = sub.add_parser("store", help="build the SQLite fact store from the corpus")
    p.add_argument("--aliases", default=str(ALIASES_PATH), help="human-asserted identity merges (default %(default)s)")

    p = sub.add_parser("player", help="answer questions about one person")
    p.add_argument("name", help="display name in any word order, or a player ID")
    p.add_argument("--connections", type=int, metavar="N", help="top N connections")
    p.add_argument("--scoring", action="store_true", help="goals/assists/points, with --possession")
    p.add_argument("--games", action="store_true", help="list appearances")
    p.add_argument("--career", action="store_true", help="seasons, years, teams, totals")
    p.add_argument("--possession", choices=["defense", "offense"], help="only points off that possession")
    p.add_argument("--season", help="filter to one season ID")
    p.add_argument("--since", type=int, help="filter to seasons from this year")
    p.add_argument("--limit", type=int, help="cap --games rows")
    p.add_argument("--json", action="store_true", help="machine-readable output")

    p = sub.add_parser("defense", help="defense-initiated scoring for a team")
    p.add_argument("team")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("sql", help="run a SELECT against the fact store")
    p.add_argument("query")

    p = sub.add_parser("repair", help="fix data already on disk (idempotent)")
    repair_sub = p.add_subparsers(dest="what", required=True)
    repair_sub.add_parser("dedupe-points", help="drop point rows the doubled page produced")
    repair_sub.add_parser("point-fields", help="swap the mislabelled scorer/assist keys")
    repair_sub.add_parser("rosters", help="merge rosters the archived HTML knows about")

    p = sub.add_parser("cache", help="inspect or seed the HTTP cache")
    cache_sub = p.add_subparsers(dest="what", required=True)
    cache_sub.add_parser("stats", help="page counts by kind")
    cache_sub.add_parser("import", help="import the legacy manifest and data/raw HTML")

    return parser


def _cmd_fetch(args) -> int:
    fetcher = _fetcher(args)
    code = cmd_fetch(args, fetcher)
    # every command ends by saying what it cost the server
    _report(fetcher, Path(args.data_dir))
    return code


HANDLERS = {
    "fetch": _cmd_fetch,
    "merge": cmd_merge,
    "store": cmd_store,
    "player": cmd_player,
    "defense": cmd_defense,
    "sql": cmd_sql,
    "repair": cmd_repair,
    "cache": cmd_cache,
}


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    handler = HANDLERS[args.command]
    try:
        return handler(args) or 0
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
