"""ultiorg — a cached client for Ultiorganizer league data.

Ultiorganizer (the backend behind ultimate.fi/pelikone) exposes no database API,
only HTML views. This package fetches those views politely, caches them, and
parses them into ID-keyed data:

    from ultiorg import fetch_gameplay, parse_gameplay, parse_allplayers
    from ultiorg import load_focus_team, build_defense_stats, build_store
"""


from .parsers import (
    classify_season,
    extract_year_from_season,
    extract_season_id,
    parse_season_list,
    parse_teams_page,
    parse_standings_page,
    parse_team_card,
    parse_player_list,
    parse_games_list,
    parse_gameplay,
    parse_allplayers,
    parse_playercard,
    parse_series_menu,
    parse_scorestatus,
    parse_statistics,
    parse_allteams,
    parse_allclubs,
    parse_csv_teams,
    parse_csv_players,
    parse_csv_games,
    parse_csv_results,
    parse_csv_pools,
    parse_csv_spirit,
    NotCsvError,
)
from .analytics import (
    CHAMPIONSHIP_EVENTS,
    build_career_stats,
    build_cooccurrence,
    build_defense_stats,
    build_frenemies,
    build_pass_network,
    build_trophies,
    build_years,
    career_source_report,
)
from .corpus import CorpusStats, build_corpus, gameplay_source, write_corpus
from .query import AmbiguousPlayer, Player, Store, UnknownPlayer
from .repair import RepairReport, dedupe_point_rows, migrate_point_fields, refresh_rosters
from .fetcher import (
    fetch_url,
    fetch_view,
    fetch_season_list,
    fetch_teams_page,
    fetch_standings_page,
    fetch_team_card,
    fetch_player_list,
    fetch_games_page,
    fetch_gameplay,
    fetch_allplayers,
    fetch_playercard,
    fetch_scorestatus,
    fetch_statistics,
    fetch_allteams,
    fetch_allclubs,
    fetch_csv_export,
    fetch_csv,
    CSV_KINDS,
)
from .http import Fetcher, FetchStats, configure, get_fetcher
from .identify import (
    DataQuality,
    PlayerIndex,
    Resolution,
    canon,
    pseudo_key,
    recover_rosters,
)
from .cache import (
    Cache,
    CachedPage,
    POLICY_SECONDS,
    cache_key,
    kind_for_url,
    is_current_season_id,
    setup_dirs,
)
from .names import canon as _canon, plain, pseudo_key as _pseudo_key
from .aliases import PersonKeys, load_aliases
from .persons import PersonIds, collect_id_clusters, is_person
from .seasons import season_stage, season_type, season_year
from .teams import FocusTeam, load_focus_team
from .store import StoreStats, build_store, defense_totals, open_store

__all__ = [
    # Parsers
    "classify_season",
    "extract_year_from_season",
    "extract_season_id",
    "parse_season_list",
    "parse_teams_page",
    "parse_standings_page",
    "parse_team_card",
    "parse_player_list",
    "parse_games_list",
    "parse_gameplay",
    "parse_allplayers",
    "parse_playercard",
    "parse_series_menu",
    "parse_scorestatus",
    "parse_statistics",
    "parse_allteams",
    "parse_allclubs",
    "parse_csv_teams",
    "parse_csv_players",
    "parse_csv_games",
    "parse_csv_results",
    "parse_csv_pools",
    "parse_csv_spirit",
    "NotCsvError",
    # Focus team (which club the analytics are about)
    "FocusTeam",
    "load_focus_team",
    # Season classification
    "season_year",
    "season_type",
    "season_stage",
    # Analytics views
    "CHAMPIONSHIP_EVENTS",
    "build_career_stats",
    "career_source_report",
    "build_cooccurrence",
    "build_defense_stats",
    "build_frenemies",
    "build_pass_network",
    "build_trophies",
    "build_years",
    # Fetchers
    "fetch_url",
    "fetch_view",
    "fetch_season_list",
    "fetch_teams_page",
    "fetch_standings_page",
    "fetch_team_card",
    "fetch_player_list",
    "fetch_games_page",
    "fetch_gameplay",
    "fetch_allplayers",
    "fetch_playercard",
    "fetch_scorestatus",
    "fetch_statistics",
    "fetch_allteams",
    "fetch_allclubs",
    "fetch_csv_export",
    "fetch_csv",
    "CSV_KINDS",
    # HTTP / politeness
    "Fetcher",
    "FetchStats",
    "configure",
    "get_fetcher",
    # Identity
    "DataQuality",
    "PlayerIndex",
    "Resolution",
    "canon",
    "plain",
    "pseudo_key",
    "recover_rosters",
    # Cache
    "Cache",
    "CachedPage",
    "POLICY_SECONDS",
    "cache_key",
    "kind_for_url",
    "is_current_season_id",
    "setup_dirs",
    # Person identity
    "PersonKeys",
    "load_aliases",
    "PersonIds",
    "collect_id_clusters",
    "is_person",
    # Fact store
    "StoreStats",
    "build_store",
    "defense_totals",
    "open_store",
    # Corpus
    "CorpusStats",
    "build_corpus",
    "gameplay_source",
    "write_corpus",
    # Composition API
    "AmbiguousPlayer",
    "Player",
    "Store",
    "UnknownPlayer",
    # Repairs
    "RepairReport",
    "dedupe_point_rows",
    "migrate_point_fields",
    "refresh_rosters",
]
