"""Otso 20-vuotisgaala data scraper and parser.

Re-exports the main public API for programmatic use:

    from otso_scrape import run_pipeline, get_all_seasons, parse_season
    from otso_scrape.parsers import is_otso_team, classify_season
    from otso_scrape.builders import build_team_timeline, build_player_network
"""


from .parsers import (
    classify_season,
    extract_year_from_season,
    extract_season_id,
    is_otso_team,
    parse_season_list,
    parse_teams_page,
    parse_standings_page,
    parse_team_card,
    parse_player_list,
    parse_csv_teams,
    parse_csv_players,
    parse_csv_games,
    parse_csv_results,
)
from .builders import (
    build_team_timeline,
    build_player_network,
    build_summary,
)
from .fetcher import (
    fetch_url,
    fetch_season_list,
    fetch_teams_page,
    fetch_standings_page,
    fetch_team_card,
    fetch_player_list,
    fetch_csv_export,
)
from .cache import (
    get_cache,
    save_cache,
    setup_dirs,
)

__all__ = [

    # Parsers
    "classify_season",
    "extract_year_from_season",
    "extract_season_id",
    "is_otso_team",
    "parse_season_list",
    "parse_teams_page",
    "parse_standings_page",
    "parse_team_card",
    "parse_player_list",
    "parse_csv_teams",
    "parse_csv_players",
    "parse_csv_games",
    "parse_csv_results",
    # Builders
    "build_team_timeline",
    "build_player_network",
    "build_summary",
    # Fetchers
    "fetch_url",
    "fetch_season_list",
    "fetch_teams_page",
    "fetch_standings_page",
    "fetch_team_card",
    "fetch_player_list",
    "fetch_csv_export",
    # Cache
    "get_cache",
    "save_cache",
    "setup_dirs",
]
