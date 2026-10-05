"""ultiorg — a cached client for Ultiorganizer league data.

Ultiorganizer (the backend behind ultimate.fi/pelikone) exposes no database API,
only HTML views. This package fetches those views politely, caches them, and
parses them into ID-keyed data:

    from ultiorg import fetch_gameplay, parse_gameplay, parse_allplayers
    from ultiorg.parsers import is_otso_team, classify_season
    from ultiorg.builders import build_team_timeline

The public API below is complete: every parser and fetcher in the package is
re-exported, including the gameplay and player-identity paths.
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
    parse_games_list,
    parse_gameplay,
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
    fetch_games_page,
    fetch_gameplay,
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
    "parse_games_list",
    "parse_gameplay",
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
    "fetch_games_page",
    "fetch_gameplay",
    "fetch_csv_export",
    # Cache
    "get_cache",
    "save_cache",
    "setup_dirs",
]
