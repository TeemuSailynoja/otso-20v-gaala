"""HTTP fetching with caching for pelikone data."""

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

from .config import USER_AGENT, REQUEST_DELAY, BASE_URL
from .cache import get_cache, save_cache, cache_key, is_cache_valid


def fetch_url(
    url: str,
    use_cache: bool = True,
    data_dir: Path = Path("data"),
    refresh: bool = False,
) -> Optional[str]:
    """Fetch a URL with caching.
    
    Args:
        url: URL to fetch.
        use_cache: Whether to use cached data.
        data_dir: Directory for cache file.
        refresh: Force re-download even if cached.
        
    Returns:
        Response text, or None if fetch failed.
    """
    cache = get_cache(data_dir) if use_cache else None
    key = cache_key(url)

    # Check cache
    if use_cache and cache and not refresh:
        if key in cache.get("urls", {}):
            cached = cache["urls"][key]
            if is_cache_valid(cached):
                print(f"  [CACHE] {url[:80]}...")
                return cached["content"]

    # Fetch from network
    print(f"  [FETCH] {url[:80]}...")
    try:
        headers = {"User-Agent": USER_AGENT}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        # Store in cache (expire after 7 days)
        if cache is None:
            cache = get_cache(data_dir)
        cache.setdefault("urls", {})[key] = {
            "url": url,
            "content": response.text,
            "expires": (datetime.now() + timedelta(days=7)).isoformat(),
        }
        save_cache(cache, data_dir)

        time.sleep(REQUEST_DELAY)
        return response.text
    except requests.RequestException as e:
        print(f"  [ERROR] Failed to fetch {url}: {e}")
        return None


def fetch_season_list(data_dir: Path = Path("data")) -> Optional[str]:
    """Fetch the season list page.
    
    Args:
        data_dir: Directory for cache file.
        
    Returns:
        HTML content of the season list page.
    """
    return fetch_url(f"{BASE_URL}/?view=seasonlist", data_dir=data_dir)


def fetch_teams_page(season_id: str, data_dir: Path = Path("data")) -> Optional[str]:
    """Fetch the teams list page for a season.
    
    Args:
        season_id: Season identifier.
        data_dir: Directory for cache file.
        
    Returns:
        HTML content of the teams page.
    """
    return fetch_url(
        f"{BASE_URL}/?view=teams&season={season_id}&list=allteams",
        data_dir=data_dir,
    )


def fetch_standings_page(season_id: str, data_dir: Path = Path("data")) -> Optional[str]:
    """Fetch the standings page for a season.
    
    Args:
        season_id: Season identifier.
        data_dir: Directory for cache file.
        
    Returns:
        HTML content of the standings page.
    """
    return fetch_url(
        f"{BASE_URL}/?view=teams&season={season_id}&list=bystandings",
        data_dir=data_dir,
    )


def fetch_team_card(team_id: str, data_dir: Path = Path("data")) -> Optional[str]:
    """Fetch a team card page.
    
    Args:
        team_id: Team identifier.
        data_dir: Directory for cache file.
        
    Returns:
        HTML content of the team card page.
    """
    return fetch_url(
        f"{BASE_URL}/?view=teamcard&team={team_id}",
        data_dir=data_dir,
    )


def fetch_player_list(team_id: str, data_dir: Path = Path("data")) -> Optional[str]:
    """Fetch the player list page for a team.
    
    Args:
        team_id: Team identifier.
        data_dir: Directory for cache file.
        
    Returns:
        HTML content of the player list page.
    """
    return fetch_url(
        f"{BASE_URL}/?view=playerlist&team={team_id}",
        data_dir=data_dir,
    )


def fetch_csv_export(data_dir: Path = Path("data")) -> Optional[str]:
    """Fetch the CSV export page.
    
    Args:
        data_dir: Directory for cache file.
        
    Returns:
        HTML content of the CSV export page.
    """
    return fetch_url(f"{BASE_URL}/?view=ext/export", data_dir=data_dir)


def fetch_games_page(season_id: str, data_dir: Path = Path("data")) -> Optional[str]:
    """Fetch the games list page for a season.
    
    Args:
        season_id: Season identifier.
        data_dir: Directory for cache file.
        
    Returns:
        HTML content of the games list page.
    """
    return fetch_url(
        f"{BASE_URL}/?view=games&season={season_id}&filter=tournaments",
        data_dir=data_dir,
    )


def fetch_gameplay(game_id: str, data_dir: Path = Path("data")) -> Optional[str]:
    """Fetch the gameplay (point-by-point) page for a game.
    
    Args:
        game_id: Game identifier.
        data_dir: Directory for cache file.
        
    Returns:
        HTML content of the gameplay page.
    """
    return fetch_url(
        f"{BASE_URL}/?view=gameplay&game={game_id}",
        data_dir=data_dir,
    )
