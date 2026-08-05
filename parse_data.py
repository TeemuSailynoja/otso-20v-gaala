#!/usr/bin/env python3
"""
Otso 20-vuotisgaala - Data Parser
Scrapes and processes data from ultimate.fi/pelikone

Usage:
    python parse_data.py              # Parse all available data
    python parse_data.py --season 2019.T1  # Parse specific season
    python parse_data.py --csv-only     # Only use CSV export (current season)
    python parse_data.py --refresh      # Force re-download all data
"""

import os
import sys
import json
import time
import hashlib
import argparse
import re
from pathlib import Path
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

# Configuration
BASE_URL = "https://ultimate.fi/pelikone"
DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CACHE_FILE = DATA_DIR / "cache_manifest.json"
REQUEST_DELAY = 1.5  # seconds between requests to be respectful

# Otso-specific team name patterns
OTSO_PATTERNS = [
    "otso", "grizzly", "polar", "akatemia",
]

# Season classification
SEASON_TYPES = {
    "Kesä": "summer",
    "Talvi": "winter",
    "Tour 1": "tour",
    "Tour 2": "tour",
    "Tour 3": "tour",
    "Finaalit": "finals",
    "Finaali": "finals",
    "Ranta": "beach",
}


def setup_dirs():
    """Create necessary directories."""
    DATA_DIR.mkdir(exist_ok=True)
    RAW_DIR.mkdir(exist_ok=True)
    PROCESSED_DIR.mkdir(exist_ok=True)


def get_cache():
    """Load the cache manifest."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {"last_updated": None, "seasons": {}, "teams": {}, "players": {}}


def save_cache(cache):
    """Save the cache manifest."""
    cache["last_updated"] = datetime.now().isoformat()
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def cache_key(url):
    """Generate a cache key from a URL."""
    return hashlib.md5(url.encode()).hexdigest()


def fetch_url(url, use_cache=True, cache=None, refresh=False):
    """Fetch a URL with caching."""
    if cache is None:
        cache = get_cache()

    key = cache_key(url)

    # Check cache
    if use_cache and not refresh and key in cache.get("urls", {}):
        cached = cache["urls"][key]
        if cached.get("expires", "") > datetime.now().isoformat():
            print(f"  [CACHE] {url[:80]}...")
            return cached["content"]

    # Fetch from network
    print(f"  [FETCH] {url[:80]}...")
    try:
        headers = {
            "User-Agent": "Otso20v-Gaala-DataBot/1.0 (educational project, please be gentle)"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        # Store in cache (expire after 7 days)
        cache.setdefault("urls", {})[key] = {
            "url": url,
            "content": response.text,
            "expires": (datetime.now() + timedelta(days=7)).isoformat()
        }
        save_cache(cache)

        time.sleep(REQUEST_DELAY)
        return response.text
    except requests.RequestException as e:
        print(f"  [ERROR] Failed to fetch {url}: {e}")
        return None


def parse_season_list(html):
    """Parse the season list page to get all available seasons."""
    seasons = []
    soup = BeautifulSoup(html, "html.parser")

    # Find all season headings
    for h3 in soup.find_all("h3"):
        season_name = h3.get_text(strip=True)
        # Find the first link in the season block
        season_div = h3.find_next_sibling("div")
        if season_div:
            link = season_div.find("a", href=True)
            if link:
                season_id = parse_season_id(link["href"])
                if season_id:
                    seasons.append({
                        "name": season_name,
                        "id": season_id,
                        "url": f"{BASE_URL}/{link['href']}"
                    })

    return seasons


def parse_season_id(href):
    """Extract season ID from a URL."""
    if "season=" in href:
        for part in href.split("&"):
            if part.startswith("season="):
                return part.split("=")[1]
    return None


def extract_year_from_season(season_id, season_name):
    """Extract year from season ID or name."""
    # Try season ID first
    # Patterns: KESA2026, 2025.1, 2019.T1, SM2022K, XSM2018, Talvi2016, BEACH2021
    year_match = re.search(r'(20\d{2})', season_id)
    if year_match:
        return int(year_match.group(1))
    
    # Try season name
    year_match = re.search(r'(20\d{2})', season_name)
    if year_match:
        return int(year_match.group(1))
    
    return None


def classify_season(season_id, season_name):
    """Classify a season into type and year."""
    year = extract_year_from_season(season_id, season_name)
    
    # Determine season type
    if season_id.startswith("KESA"):
        season_type = "summer"
    elif "T1" in season_id:
        season_type = "tour1"
    elif "T2" in season_id:
        season_type = "tour2"
    elif "T3" in season_id:
        season_type = "tour3"
    elif "Finaa" in season_id or season_id.endswith("F"):
        season_type = "finals"
    elif "Talvi" in season_name or "Talvi" in season_id:
        season_type = "winter"
    elif "BEACH" in season_id or "Ranta" in season_name:
        season_type = "beach"
    elif "SM" in season_id:
        season_type = "championship"
    else:
        season_type = "unknown"
    
    return {
        "year": year,
        "type": season_type,
        "id": season_id,
        "name": season_name,
    }


def parse_teams_page(html, season_id):
    """Parse the teams list page.
    
    Handles two HTML formats:
    1. New format (KESA2026+): tables with class='teams-table'
    2. Old format (pre-2026): single large table with teams embedded as text
    """
    teams = []
    soup = BeautifulSoup(html, "html.parser")

    # Format 1: New format with teams-table class
    for table in soup.find_all("table", class_="teams-table"):
        division = ""
        # Get division from the table header
        th = table.find("th", colspan=True)
        if th:
            division = th.get_text(strip=True)
        # Also check for division in first row
        first_row = table.find("tr")
        if first_row and not division:
            first_td = first_row.find("td")
            if first_td:
                division = first_td.get_text(strip=True)

        for row in table.find_all("tr")[1:]:  # Skip header
            tds = row.find_all("td")
            if len(tds) >= 3:
                team_link = tds[0].find("a")
                club_link = tds[1].find("a")
                player_link = tds[2].find("a", href=True)

                if team_link:
                    team_id = None
                    if "team=" in team_link["href"]:
                        for part in team_link["href"].split("&"):
                            if part.startswith("team="):
                                team_id = part.split("=")[1]

                    teams.append({
                        "name": team_link.get_text(strip=True),
                        "id": team_id,
                        "club": club_link.get_text(strip=True) if club_link else "",
                        "division": division,
                        "season_id": season_id,
                        "player_list_url": f"{BASE_URL}/{player_link['href']}" if player_link else None,
                    })

    # Format 2: Old format - single large table with all data
    if not teams:
        teams = _parse_teams_old_format(html, season_id)

    return teams


def _parse_teams_old_format(html, season_id):
    """Parse teams from old-format HTML (pre-2026 pelikone)."""
    teams = []
    soup = BeautifulSoup(html, "html.parser")
    
    # Get all text content
    text = soup.get_text("\n")
    
    # Find division headers (Avoin, Naiset, Mixed, Juniorit)
    divisions = ["Avoin", "Naiset", "Mixed", "Juniorit", "U17"]
    
    # Split by division headers
    current_division = ""
    current_teams = []
    
    # Find all team-like entries (words followed by club names)
    # Pattern: TeamName followed by ClubName
    team_pattern = re.compile(
        r'(\w+(?:\s+\w+)*(?:\s+\d+)?)(?:\n|\xa0)'
        r'((?:Espoo|Helsinki|Lemp\u00e4\u00e4l\u00e4|Jyv\u00e4skyl\u00e4|Turku|VirHe|Atletico|Ufo|Unlimited|Lemp\u00e4\u00e4l\u00e4n|Espoon Rennot|Jyv\u00e4skyl\u00e4n|Lemp\u00e4\u00e4l\u00e4n Kisa|Espoo Ultimate|Unlimited Frisbee)[^\n]{0,50})',
        re.MULTILINE
    )
    
    # Alternative: look for team entries in the raw HTML
    # Teams appear as links with "Pelaajalista" nearby
    team_links = soup.find_all("a", href=True, string=re.compile(r'^\w'))
    
    # Build a list of potential team names
    seen_teams = set()
    for link in team_links:
        name = link.get_text(strip=True)
        if (len(name) > 2 and len(name) < 40 and 
            name not in ["Pelaajalista", "Pistep\u00f6rssi", "Pelit",
                        "Sijoitukset", "Pelit", "Joukkueet", "Avoin",
                        "Naiset", "Mixed", "Juniorit"] and
            name not in seen_teams and
            not name.startswith("\u00bb") and
            not name.startswith("Talvi") and
            not name.startswith("Kes\u00e4") and
            not name.startswith("Ranta")):
            seen_teams.add(name)
            current_division = ""
            for d in divisions:
                # Check if we're in this division section
                pass  # We'll determine division by position
            
            team_id = None
            if "team=" in link["href"]:
                for part in link["href"].split("&"):
                    if part.startswith("team="):
                        team_id = part.split("=")[1]
            
            teams.append({
                "name": name,
                "id": team_id,
                "club": "",
                "division": current_division,
                "season_id": season_id,
                "player_list_url": None,
            })
    
    # Deduplicate by name
    seen = set()
    unique_teams = []
    for t in teams:
        if t["name"] not in seen:
            seen.add(t["name"])
            unique_teams.append(t)
    
    return unique_teams


def parse_standings_page(html, season_id):
    """Parse the standings page to get placements.
    
    Handles two HTML formats:
    1. New format: tables with proper placement structure
    2. Old format (pre-2026): placements embedded in text
    """
    placements = []
    soup = BeautifulSoup(html, "html.parser")

    # Try new format first
    table = soup.find("table", class_="placements-table")
    if table:
        placements = _parse_standings_new_format(html, season_id)
    else:
        placements = _parse_standings_old_format(html, season_id)

    return placements


def _parse_standings_new_format(html, season_id):
    """Parse placements from new-format HTML."""
    placements = []
    soup = BeautifulSoup(html, "html.parser")

    table = soup.find("table", class_="placements-table")
    if not table:
        return placements

    # Get division headers
    header_row = table.find("tr")
    divisions = []
    if header_row:
        for th in header_row.find_all("th")[1:]:  # Skip "Sijoitus" column
            link = th.find("a")
            if link:
                divisions.append(link.get_text(strip=True))
            else:
                divisions.append(th.get_text(strip=True))

    # Parse placement rows
    for row in table.find_all("tr")[1:]:  # Skip header
        tds = row.find_all("td")
        if len(tds) < 2:
            continue

        placement = tds[0].get_text(strip=True)

        for i, division in enumerate(divisions):
            if i + 1 < len(tds):
                team_cell = tds[i + 1]
                team_link = team_cell.find("a")
                if team_link:
                    team_id = None
                    if "team=" in team_link["href"]:
                        for part in team_link["href"].split("&"):
                            if part.startswith("team="):
                                team_id = part.split("=")[1]

                    placements.append({
                        "placement": placement,
                        "team_name": team_link.get_text(strip=True),
                        "team_id": team_id,
                        "division": division,
                        "season_id": season_id,
                    })

    return placements


def _parse_standings_old_format(html, season_id):
    """Parse placements from old-format HTML (pre-2026 pelikone).
    
    In old format, placements are embedded in the page text:
    Kulta/Hopea/Pronssi followed by team names, or numbered positions (4., 5., etc.)
    """
    placements = []
    soup = BeautifulSoup(html, "html.parser")
    
    # Get all text
    text = soup.get_text()
    
    # Find placement patterns
    # Pattern: Kulta/Hopea/Pronssi/4./5./etc. followed by team names
    placement_pattern = re.compile(
        r'(Kulta|Hopea|Pronssi|(\d+)\.)\s+([^\n]{2,200}?)'
        r'(?:\n|$)',
        re.MULTILINE
    )
    
    divisions = ["Avoin", "Naiset", "Mixed", "Juniorit"]
    
    # Split text by division headers
    for division in divisions:
        # Find this division's section
        div_match = re.search(rf'{division}\s*\n(.*?)(?:\n\s*(?:Avoin|Naiset|Mixed|Juniorit)|\n\s*$)', text, re.DOTALL)
        if not div_match:
            # Try without division header
            continue
        
        div_text = div_match.group(1)
        
        # Find all placements in this division
        for match in placement_pattern.finditer(div_text):
            placement_type = match.group(1)
            team_names_str = match.group(3).strip()
            
            # Parse team names from the string
            # Teams are separated by newlines or special characters
            team_names = re.split(r'[\n\xa0]+', team_names_str)
            
            # Determine placement number
            if placement_type == "Kulta":
                placement_num = "1." if len(team_names) > 1 else "Kulta"
            elif placement_type == "Hopea":
                placement_num = "2." if len(team_names) > 1 else "Hopea"
            elif placement_type == "Pronssi":
                placement_num = "3." if len(team_names) > 1 else "Pronssi"
            else:
                placement_num = placement_type
            
            for team_name in team_names:
                team_name = team_name.strip()
                if team_name and len(team_name) > 1 and team_name not in ["Kulta", "Hopea", "Pronssi"]:
                    placements.append({
                        "placement": placement_num,
                        "team_name": team_name,
                        "team_id": None,
                        "division": division,
                        "season_id": season_id,
                    })
    
    return placements


def parse_team_card(html, team_id):
    """Parse a team card page - FIXED for actual HTML structure."""
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "team_id": team_id,
        "players": [],
        "games": [],
    }

    # Parse player list - look for the table with player stats
    # The player table has: # (jersey), Nimi (name link), Pelit (games), Syötöt (assists), Maalit (goals), Yhteensä (total)
    player_table = soup.find("table", style=lambda s: s and "width:80%" in s)
    if player_table:
        rows = player_table.find_all("tr")
        for row in rows[1:]:  # Skip header
            tds = row.find_all("td")
            if len(tds) >= 6:
                # td[0] = jersey number
                # td[1] = player name link
                # td[2] = games
                # td[3] = assists
                # td[4] = goals
                # td[5] = total
                player_link = tds[1].find("a")
                if player_link:
                    player_id = None
                    if "player=" in player_link["href"]:
                        for part in player_link["href"].split("&"):
                            if part.startswith("player="):
                                player_id = part.split("=")[1]

                    result["players"].append({
                        "name": player_link.get_text(strip=True),
                        "id": player_id,
                        "jersey": tds[0].get_text(strip=True),
                        "games": tds[2].get_text(strip=True),
                        "assists": tds[3].get_text(strip=True),
                        "goals": tds[4].get_text(strip=True),
                        "total": tds[5].get_text(strip=True),
                    })

    # Parse game results - look for game rows with score format
    # Games appear in a table with structure:
    # <tr><td><span class='game-loser'>Home</span></td><td>-</td><td><span class='game-winner'>Away</span></td><td>HomeScore</td><td>-</td><td>AwayScore</td></tr>
    for tr in soup.find_all("tr"):
        game_loser = tr.find("span", class_="game-loser")
        game_winner = tr.find("span", class_="game-winner")
        if game_loser and game_winner:
            tds = tr.find_all("td")
            if len(tds) >= 6:
                try:
                    home_score = int(tds[3].get_text(strip=True))
                    away_score = int(tds[5].get_text(strip=True))
                except (ValueError, IndexError):
                    continue
                
                result["games"].append({
                    "home": game_loser.get_text(strip=True),
                    "away": game_winner.get_text(strip=True),
                    "home_score": home_score,
                    "away_score": away_score,
                })

    return result


def parse_player_list(html, team_id):
    """Parse the all-time player list for a team.
    
    Table structure:
    <tr><td><a href='?view=playercard&...'>Name</a></td><td>Jersey</td><td>Events</td><td>Games</td><td>Assists</td><td>Total</td></tr>
    """
    soup = BeautifulSoup(html, "html.parser")
    players = []

    # Find the table containing player links
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
            
        for row in rows[1:]:  # Skip header
            tds = row.find_all("td")
            if len(tds) >= 6:
                # td[0] = player name link
                # td[1] = jersey
                # td[2] = events
                # td[3] = games
                # td[4] = assists
                # td[5] = total
                player_link = tds[0].find("a")
                if player_link:
                    player_id = None
                    if "player=" in player_link["href"]:
                        for part in player_link["href"].split("&"):
                            if part.startswith("player="):
                                player_id = part.split("=")[1]

                    # Skip total/summary row
                    if tds[0].get_text(strip=True) == "":
                        continue

                    players.append({
                        "name": player_link.get_text(strip=True),
                        "id": player_id,
                        "jersey": tds[1].get_text(strip=True),
                        "events": tds[2].get_text(strip=True),
                        "games": tds[3].get_text(strip=True),
                        "assists": tds[4].get_text(strip=True),
                        "total": tds[5].get_text(strip=True),
                    })

    return players


def parse_csv_teams(html, season_id):
    """Parse the teams CSV export."""
    import csv
    from io import StringIO

    teams = []
    reader = csv.DictReader(StringIO(html))
    for row in reader:
        teams.append({
            "name": row.get("Team", ""),
            "short_name": row.get("ShortName", ""),
            "club": row.get("Club", ""),
            "country": row.get("Country", ""),
            "division": row.get("Division", ""),
            "pool": row.get("Pool", ""),
            "games": int(row.get("Games", 0) or 0),
            "wins": int(row.get("Wins", 0) or 0),
            "goals_for": int(row.get("GoalsFor", 0) or 0),
            "goals_against": int(row.get("GoalsAgainst", 0) or 0),
            "spirit_points": int(row.get("SpiritPoints", 0) or 0),
            "season_id": season_id,
        })
    return teams


def parse_csv_players(html, season_id):
    """Parse the players CSV export."""
    import csv
    from io import StringIO

    players = []
    reader = csv.DictReader(StringIO(html))
    for row in reader:
        players.append({
            "first_name": row.get("FirstName", ""),
            "last_name": row.get("LastName", ""),
            "full_name": f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip(),
            "jersey": row.get("Jersey", ""),
            "team_name": row.get("TeamName", ""),
            "team_abbreviation": row.get("TeamAbbreviation", ""),
            "club": row.get("Club", ""),
            "division": row.get("Division", ""),
            "country": row.get("Country", ""),
            "games": int(row.get("Games", 0) or 0),
            "assists": int(row.get("Assists", 0) or 0),
            "goals": int(row.get("Goals", 0) or 0),
            "callahans": int(row.get("Callahans", 0) or 0),
            "total": int(row.get("Total", 0) or 0),
            "season_id": season_id,
        })
    return players


def parse_csv_games(html, season_id):
    """Parse the games CSV export."""
    import csv
    from io import StringIO

    games = []
    reader = csv.DictReader(StringIO(html))
    for row in reader:
        games.append({
            "time": row.get("Time", ""),
            "home_team": row.get("HomeTeam", ""),
            "away_team": row.get("AwayTeam", ""),
            "home_scores": row.get("HomeScores", ""),
            "visitor_scores": row.get("VisitorScores", ""),
            "pool": row.get("Pool", ""),
            "division": row.get("Division", ""),
            "field": row.get("Field", ""),
            "reservation_group": row.get("ReservationGroup", ""),
            "place": row.get("Place", ""),
            "game_name": row.get("GameName", ""),
            "season_id": season_id,
        })
    return games


def parse_csv_results(html, season_id):
    """Parse the results CSV export."""
    import csv
    from io import StringIO

    results = []
    reader = csv.DictReader(StringIO(html))
    for row in reader:
        results.append({
            "home": row.get("Home", ""),
            "away": row.get("Away", ""),
            "home_scores": row.get("HomeScores", ""),
            "away_scores": row.get("AwayScores", ""),
            "division": row.get("Division", ""),
            "pool": row.get("Pool", ""),
            "season_id": season_id,
        })
    return results


def is_otso_team(team_name):
    """Check if a team name matches Otso patterns."""
    name_lower = team_name.lower()
    for pattern in OTSO_PATTERNS:
        if pattern in name_lower:
            return True
    return False


def parse_season(season_id, season_name, csv_only=False):
    """Parse a complete season's data."""
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
        teams_url = f"{BASE_URL}/?view=teams&season={season_id}&list=allteams"
        teams_html = fetch_url(teams_url)
        if teams_html:
            season_data["teams"] = parse_teams_page(teams_html, season_id)
            print(f"  Found {len(season_data['teams'])} teams")

        # Parse standings page
        standings_url = f"{BASE_URL}/?view=teams&season={season_id}&list=bystandings"
        standings_html = fetch_url(standings_url)
        if standings_html:
            season_data["placements"] = parse_standings_page(standings_html, season_id)
            otso_placements = [p for p in season_data["placements"] if is_otso_team(p["team_name"])]
            print(f"  Found {len(season_data['placements'])} placements ({len(otso_placements)} Otso)")

        # Parse team cards for Otso teams
        for team in season_data["teams"]:
            if is_otso_team(team["name"]) and team["id"]:
                team_card_url = f"{BASE_URL}/?view=teamcard&team={team['id']}"
                team_html = fetch_url(team_card_url)
                if team_html:
                    team_data = parse_team_card(team_html, team["id"])
                    team["players"] = team_data["players"]
                    team["games"] = team_data["games"]
                    print(f"  Parsed team card for {team['name']}: {len(team_data['players'])} players, {len(team_data['games'])} games")

        # Parse player lists for Otso teams
        for team in season_data["teams"]:
            if is_otso_team(team["name"]) and team.get("player_list_url"):
                player_html = fetch_url(team["player_list_url"])
                if player_html:
                    all_time_players = parse_player_list(player_html, team["id"])
                    team["all_time_players"] = all_time_players
                    print(f"  Parsed player list for {team['name']}: {len(all_time_players)} players")

    # Try CSV export
    csv_season_url = f"{BASE_URL}/?view=ext/export"
    csv_html = fetch_url(csv_season_url)
    if csv_html and "CSV-tiedostot" in csv_html:
        print(f"  CSV export available")
        # Note: CSV export only works for current season
        # We'd need to construct the direct URLs
    else:
        print(f"  CSV export not available for this season")

    return season_data


def get_all_seasons():
    """Get all available seasons from the season list page."""
    print("Fetching season list...")
    html = fetch_url(f"{BASE_URL}/?view=seasonlist")
    if not html:
        return []
    return parse_season_list(html)


def build_team_timeline(seasons_data):
    """Build a timeline of Otso teams across all seasons."""
    timeline = []

    for season in seasons_data:
        classified = season["classified"]
        year = classified.get("year")
        if not year:
            continue

        # Find Otso teams in this season
        otso_teams = []
        for team in season["teams"]:
            if is_otso_team(team["name"]):
                otso_teams.append({
                    "name": team["name"],
                    "id": team["id"],
                    "division": team["division"],
                })

        # Also check placements
        for placement in season["placements"]:
            if is_otso_team(placement["team_name"]):
                # Check if already added
                if not any(t["name"] == placement["team_name"] for t in otso_teams):
                    otso_teams.append({
                        "name": placement["team_name"],
                        "placement": placement["placement"],
                        "division": placement["division"],
                    })

        if otso_teams:
            timeline.append({
                "year": year,
                "season_id": season["id"],
                "season_name": season["name"],
                "season_type": classified["type"],
                "teams": otso_teams,
            })

    return timeline


def build_player_network(seasons_data):
    """Build a network of players who played together."""
    player_teams = {}  # player_name -> list of (team_name, season_id)

    for season in seasons_data:
        for team in season["teams"]:
            for player in team.get("players", []):
                name = player["name"]
                if name not in player_teams:
                    player_teams[name] = []
                player_teams[name].append({
                    "team": team["name"],
                    "season_id": season["id"],
                    "season_name": season["name"],
                })

    # Build co-occurrence matrix
    network = {
        "players": {},
        "connections": [],
    }

    for player_name, teams in player_teams.items():
        network["players"][player_name] = {
            "teams": teams,
            "team_count": len(set(t["team"] for t in teams)),
            "season_count": len(set(t["season_id"] for t in teams)),
        }

        # Build connections with other players on same teams
        for i, team1 in enumerate(teams):
            for player2_name, other_teams in player_teams.items():
                if player2_name == player_name:
                    continue
                for team2 in other_teams:
                    if team1["team"] == team2["team"]:
                        # They played together
                        network["connections"].append({
                            "player1": player_name,
                            "player2": player2_name,
                            "team": team1["team"],
                            "season_id": team1["season_id"],
                        })

    # Deduplicate connections
    seen = set()
    unique_connections = []
    for conn in network["connections"]:
        key = tuple(sorted([conn["player1"], conn["player2"]])) + (conn["team"],)
        if key not in seen:
            seen.add(key)
            unique_connections.append(conn)
    network["connections"] = unique_connections

    return network


def main():
    parser = argparse.ArgumentParser(description="Parse Otso data from Pelikone")
    parser.add_argument("--season", type=str, help="Parse specific season ID")
    parser.add_argument("--csv-only", action="store_true", help="Only use CSV export")
    parser.add_argument("--refresh", action="store_true", help="Force re-download all data")
    parser.add_argument("--output", type=str, default="processed", help="Output directory")
    args = parser.parse_args()

    setup_dirs()

    if args.refresh:
        print("Cache refresh enabled - all data will be re-downloaded")

    cache = get_cache()
    if args.refresh:
        cache = {"last_updated": None, "seasons": {}, "teams": {}, "players": {}}
        save_cache(cache)

    # Get all seasons
    if args.season:
        seasons = [{"id": args.season, "name": args.season, "url": f"{BASE_URL}/?view=teams&season={args.season}"}]
    else:
        seasons = get_all_seasons()

    print(f"\nFound {len(seasons)} seasons")

    # Parse each season
    all_seasons_data = []
    for season in seasons:
        season_data = parse_season(
            season["id"],
            season["name"],
            csv_only=args.csv_only
        )
        all_seasons_data.append(season_data)

        # Save raw data
        raw_file = RAW_DIR / f"{season['id'].replace('/', '_')}.json"
        with open(raw_file, "w") as f:
            json.dump(season_data, f, indent=2, ensure_ascii=False)

    # Build derived data
    print(f"\n{'='*60}")
    print("Building derived data...")
    print(f"{'='*60}")

    # Team timeline
    timeline = build_team_timeline(all_seasons_data)
    timeline_file = PROCESSED_DIR / "team_timeline.json"
    with open(timeline_file, "w") as f:
        json.dump(timeline, f, indent=2, ensure_ascii=False)
    print(f"Team timeline: {len(timeline)} years with Otso teams -> {timeline_file}")

    # Player network (only for recent seasons with player data)
    player_network = build_player_network(all_seasons_data)
    network_file = PROCESSED_DIR / "player_network.json"
    with open(network_file, "w") as f:
        json.dump(player_network, f, indent=2, ensure_ascii=False)
    print(f"Player network: {len(player_network['players'])} players, {len(player_network['connections'])} connections -> {network_file}")

    # Summary statistics
    summary = {
        "total_seasons": len(all_seasons_data),
        "years_covered": sorted(set(s["classified"]["year"] for s in all_seasons_data if s["classified"]["year"])),
        "total_teams": sum(len(s["teams"]) for s in all_seasons_data),
        "otso_teams": sum(len([t for t in s["teams"] if is_otso_team(t["name"])]) for s in all_seasons_data),
        "total_players": len(player_network["players"]),
        "total_connections": len(player_network["connections"]),
    }
    summary_file = PROCESSED_DIR / "summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Summary: {summary['total_seasons']} seasons, {summary['years_covered']} -> {summary_file}")

    print(f"\n{'='*60}")
    print("Done! Data saved to data/processed/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
