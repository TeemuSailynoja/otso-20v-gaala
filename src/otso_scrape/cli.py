"""CLI entry point for the Otso scraper."""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict

from .config import BASE_URL, DATA_DIR, RAW_DIR, PROCESSED_DIR
from .cache import get_cache, save_cache, setup_dirs
from .fetcher import fetch_url, fetch_season_list, fetch_games_page, fetch_gameplay
from .parsers import parse_season_list, classify_season, parse_games_list, parse_gameplay, is_otso_team
from .builders import build_team_timeline, build_player_network, build_summary


def parse_season(
    season_id: str,
    season_name: str,
    csv_only: bool = False,
    otso_only: bool = False,
    fetch_gameplay_data: bool = False,
    data_dir: Path = DATA_DIR,
    refresh: bool = False,
) -> Dict:
    """Parse a complete season's data.

    Args:
        season_id: Season identifier.
        season_name: Season name.
        csv_only: Only use CSV export (current season).
        otso_only: Skip non-Otso teams entirely (saves requests).
        fetch_gameplay_data: Also fetch games list and point-by-point gameplay.
        data_dir: Directory for cache and output files.
        refresh: Force re-download even if cached.

    Returns:
        Season data dictionary.
    """
    from .fetcher import (
        fetch_teams_page,
        fetch_standings_page,
        fetch_team_card,
        fetch_player_list,
        fetch_csv_export,
    )
    from .parsers import (
        parse_teams_page,
        parse_standings_page,
        parse_team_card,
        parse_player_list,
        is_otso_team,
    )

    print(f"\n{'='*60}")
    print(f"Parsing season: {season_name} ({season_id})")
    print(f"{'='*60}")

    season_data = {
        "id": season_id,
        "name": season_name,
        "classified": classify_season(season_id, season_name),
        "teams": [],
        "placements": [],
        "players": [],
        "games": [],
        "results": [],
    }

    # Try CSV export first (current season only)
    if not csv_only:
        # Parse teams page
        teams_html = fetch_teams_page(season_id, data_dir)
        if teams_html:
            season_data["teams"] = parse_teams_page(teams_html, season_id)
            print(f"  Found {len(season_data['teams'])} teams")

        # Parse standings page
        standings_html = fetch_standings_page(season_id, data_dir)
        if standings_html:
            season_data["placements"] = parse_standings_page(standings_html, season_id)
            otso_placements = [
                p for p in season_data["placements"] if is_otso_team(p["team_name"])
            ]
            print(
                f"  Found {len(season_data['placements'])} placements "
                f"({len(otso_placements)} Otso)"
            )

        # Parse team cards for Otso teams
        for team in season_data["teams"]:
            if not is_otso_team(team["name"]):
                if otso_only:
                    continue
            if team["id"]:
                team_html = fetch_team_card(team["id"], data_dir)
                if team_html:
                    team_data = parse_team_card(team_html, team["id"])
                    team["players"] = team_data["players"]
                    team["games"] = team_data["games"]
                    print(
                        f"  Parsed team card for {team['name']}: "
                        f"{len(team_data['players'])} players, "
                        f"{len(team_data['games'])} games"
                    )

        # Parse player lists for Otso teams
        for team in season_data["teams"]:
            if not is_otso_team(team["name"]):
                if otso_only:
                    continue
            if team.get("player_list_url"):
                player_html = fetch_url(
                    team["player_list_url"], data_dir=data_dir, refresh=refresh
                )
                if player_html:
                    all_time_players = parse_player_list(player_html, team["id"])
                    team["all_time_players"] = all_time_players
                    print(
                        f"  Parsed player list for {team['name']}: "
                        f"{len(all_time_players)} players"
                    )

    # Fetch games list and gameplay data (optional)
    if fetch_gameplay_data and not csv_only:
        print(f"  Fetching games list...")
        games_html = fetch_games_page(season_id, data_dir)
        if games_html:
            season_games = parse_games_list(games_html, season_id)
            season_data["games"] = season_games
            print(f"  Found {len(season_games)} Otso games")
            
            # Fetch point-by-point gameplay for each game
            for game in season_games:
                game_id = game["game_id"]
                print(f"    Fetching gameplay for {game['home_team']} vs {game['away_team']}...")
                gameplay_html = fetch_gameplay(game_id, data_dir)
                if gameplay_html:
                    game["gameplay"] = parse_gameplay(gameplay_html)
                    points = game["gameplay"].get("points", [])
                    print(f"      {len(points)} points, "
                          f"home: {len(game['gameplay'].get('home_players', []))} players, "
                          f"away: {len(game['gameplay'].get('away_players', []))} players")
                else:
                    print(f"      Failed to fetch gameplay")

    # Try CSV export
    csv_html = fetch_csv_export(data_dir)
    if csv_html and "CSV-tiedostot" in csv_html:
        print(f"  CSV export available")
    else:
        print(f"  CSV export not available for this season")

    return season_data


def get_all_seasons(data_dir: Path = DATA_DIR) -> List[Dict]:
    """Get all available seasons from the season list page.

    Args:
        data_dir: Directory for cache file.

    Returns:
        List of season dictionaries.
    """
    print("Fetching season list...")
    html = fetch_season_list(data_dir)
    if not html:
        return []
    return parse_season_list(html)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Parse Otso data from Pelikone",
        prog="otso-scrape",
    )
    parser.add_argument("--season", type=str, help="Parse specific season ID")
    parser.add_argument(
        "--csv-only", action="store_true", help="Only use CSV export (current season)"
    )
    parser.add_argument(
        "--otso-only", action="store_true", help="Only fetch Otso teams (skip non-Otso teams entirely)"
    )
    parser.add_argument(
        "--gameplay", action="store_true", help="Also fetch games list and point-by-point gameplay data"
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Force re-download all data"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="processed",
        help="Output directory (default: processed)",
    )
    args = parser.parse_args()

    # Setup directories
    setup_dirs(DATA_DIR)

    if args.refresh:
        print("Cache refresh enabled - all data will be re-downloaded")

    cache = get_cache(DATA_DIR)
    if args.refresh:
        cache = {"last_updated": None, "seasons": {}, "teams": {}, "players": {}}
        save_cache(cache, DATA_DIR)

    # Get all seasons
    if args.season:
        seasons = [
            {
                "id": args.season,
                "name": args.season,
                "url": f"{BASE_URL}/?view=teams&season={args.season}",
            }
        ]
    else:
        seasons = get_all_seasons(DATA_DIR)

    print(f"\nFound {len(seasons)} seasons")

    # Parse each season
    all_seasons_data = []
    for season in seasons:
        season_data = parse_season(
            season["id"],
            season["name"],
            csv_only=args.csv_only,
            otso_only=args.otso_only,
            fetch_gameplay_data=args.gameplay,
            data_dir=DATA_DIR,
            refresh=args.refresh,
        )
        all_seasons_data.append(season_data)

        # Save raw data
        raw_file = RAW_DIR / f"{season['id'].replace('/', '_')}.json"
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(season_data, f, indent=2, ensure_ascii=False)

    # Build derived data
    print(f"\n{'='*60}")
    print("Building derived data...")
    print(f"{'='*60}")

    # Team timeline
    timeline = build_team_timeline(all_seasons_data)
    timeline_file = PROCESSED_DIR / "team_timeline.json"
    with open(timeline_file, "w", encoding="utf-8") as f:
        json.dump(timeline, f, indent=2, ensure_ascii=False)
    print(f"Team timeline: {len(timeline)} years with Otso teams -> {timeline_file}")

    # Player network
    player_network = build_player_network(all_seasons_data)
    network_file = PROCESSED_DIR / "player_network.json"
    with open(network_file, "w", encoding="utf-8") as f:
        json.dump(player_network, f, indent=2, ensure_ascii=False)
    print(
        f"Player network: {len(player_network['players'])} players, "
        f"{len(player_network['connections'])} connections -> {network_file}"
    )

    # Summary statistics
    summary = build_summary(all_seasons_data, player_network)
    summary_file = PROCESSED_DIR / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(
        f"Summary: {summary['total_seasons']} seasons, "
        f"{summary['years_covered']} -> {summary_file}"
    )

    # Save match results (games + gameplay data)
    if args.gameplay:
        all_games = []
        for season in all_seasons_data:
            for game in season.get("games", []):
                all_games.append(game)
        
        match_file = PROCESSED_DIR / "match_results.json"
        with open(match_file, "w", encoding="utf-8") as f:
            json.dump(all_games, f, indent=2, ensure_ascii=False)
        
        games_with_gameplay = sum(1 for g in all_games if g.get("gameplay"))
        print(
            f"Match results: {len(all_games)} games, "
            f"{games_with_gameplay} with point-by-point data -> {match_file}"
        )

    print(f"\n{'='*60}")
    print("Done! Data saved to data/processed/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
