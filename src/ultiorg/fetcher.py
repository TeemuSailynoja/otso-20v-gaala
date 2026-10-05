"""URL builders per pelikone view, plus cache-aware fetching.

Every function here is a view name and its parameters — the vocabulary of the
site. Network behaviour and politeness live in `http.py`; parsing lives in
`parsers.py`. Pass a configured `Fetcher` to share one politeness budget and
one request counter across a whole run; omit it to get the process default.
"""

from __future__ import annotations

from typing import Optional

from .config import BASE_URL
from .http import Fetcher, fetch_url, get_fetcher


def _f(fetcher: Optional[Fetcher]) -> Fetcher:
    return fetcher or get_fetcher()


def fetch_view(view: str, fetcher: Optional[Fetcher] = None, kind: Optional[str] = None, **params) -> Optional[str]:
    """Fetch `?view=<view>&<params>` — the shape every pelikone page shares."""
    query = "&".join(f"{key}={value}" for key, value in params.items() if value is not None)
    url = f"{BASE_URL}/?view={view}" + (f"&{query}" if query else "")
    return _f(fetcher).get(url, kind=kind)


def fetch_season_list(fetcher: Optional[Fetcher] = None) -> Optional[str]:
    """The season index: every season ID the instance knows."""
    return fetch_view("seasonlist", fetcher)


def fetch_teams_page(season_id: str, fetcher: Optional[Fetcher] = None) -> Optional[str]:
    return fetch_view("teams", fetcher, season=season_id, list="allteams")


def fetch_standings_page(season_id: str, fetcher: Optional[Fetcher] = None) -> Optional[str]:
    return fetch_view("teams", fetcher, season=season_id, list="bystandings")


def fetch_team_card(team_id: str, fetcher: Optional[Fetcher] = None) -> Optional[str]:
    return fetch_view("teamcard", fetcher, team=team_id)


def fetch_player_list(team_id: str, fetcher: Optional[Fetcher] = None) -> Optional[str]:
    return fetch_view("playerlist", fetcher, team=team_id)


def fetch_games_page(season_id: str, fetcher: Optional[Fetcher] = None) -> Optional[str]:
    return fetch_view("games", fetcher, season=season_id, filter="tournaments", group="all")


def fetch_gameplay(game_id: str, fetcher: Optional[Fetcher] = None) -> Optional[str]:
    """Point-by-point for one game: rosters with player IDs, points with names."""
    return fetch_view("gameplay", fetcher, game=game_id)


def fetch_allplayers(fetcher: Optional[Fetcher] = None) -> Optional[str]:
    """A–Z index of every registered player, with IDs."""
    return fetch_view("allplayers", fetcher)


def fetch_playercard(player_id: str, series: str = "0", fetcher: Optional[Fetcher] = None) -> Optional[str]:
    """One player's career: a row per event they have played in."""
    return fetch_view("playercard", fetcher, series=series, player=player_id)


def fetch_scorestatus(series_id: str, fetcher: Optional[Fetcher] = None) -> Optional[str]:
    """Whole-event player scoreboard (all teams, all divisions of one event)."""
    return fetch_view("scorestatus", fetcher, series=series_id)


def fetch_statistics(season_id: str, list_kind: str = "playerscoreboard", fetcher: Optional[Fetcher] = None) -> Optional[str]:
    return fetch_view("statistics", fetcher, season=season_id, list=list_kind)


def fetch_allteams(fetcher: Optional[Fetcher] = None) -> Optional[str]:
    return fetch_view("allteams", fetcher)


def fetch_allclubs(fetcher: Optional[Fetcher] = None) -> Optional[str]:
    return fetch_view("allclubs", fetcher)


def fetch_csv_export(fetcher: Optional[Fetcher] = None) -> Optional[str]:
    """The "Tiedon vienti" page — HTML links to CSV, not CSV itself.

    Kept because the export page lists which CSVs exist. The CSVs themselves are
    `ext/playerscsv.php?season=<ID>` and friends, current season only (403 for
    past seasons). See `test_ext_export_is_html_not_csv`.
    """
    return fetch_view("ext/export", fetcher)


__all__ = [
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
]
