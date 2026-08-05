"""HTML and CSV parsing functions for pelikone data."""

import csv
import re
from io import StringIO
from typing import List, Dict, Optional, Tuple

from bs4 import BeautifulSoup

from .config import BASE_URL, OTSO_PATTERNS


def extract_season_id(href: str) -> Optional[str]:
    """Extract season ID from a URL.
    
    Args:
        href: URL href string.
        
    Returns:
        Season ID, or None if not found.
    """
    if "season=" in href:
        for part in href.split("&"):
            if part.startswith("season="):
                return part.split("=")[1]
    return None


def extract_year_from_season(season_id: str, season_name: str) -> Optional[int]:
    """Extract year from season ID or name.
    
    Args:
        season_id: Season identifier.
        season_name: Season name.
        
    Returns:
        Year as integer, or None if not found.
    """
    # Try season ID first
    year_match = re.search(r"(20\d{2})", season_id)
    if year_match:
        return int(year_match.group(1))
    
    # Try season name
    year_match = re.search(r"(20\d{2})", season_name)
    if year_match:
        return int(year_match.group(1))
    
    return None


def classify_season(season_id: str, season_name: str) -> Dict:
    """Classify a season into type and year.
    
    Args:
        season_id: Season identifier.
        season_name: Season name.
        
    Returns:
        Dictionary with year, type, id, and name.
    """
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


def parse_season_list(html: str) -> List[Dict]:
    """Parse the season list page to get all available seasons.
    
    Args:
        html: HTML content of the season list page.
        
    Returns:
        List of season dictionaries with name, id, and url.
    """
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
                season_id = extract_season_id(link["href"])
                if season_id:
                    seasons.append({
                        "name": season_name,
                        "id": season_id,
                        "url": f"{BASE_URL}/{link['href']}",
                    })

    return seasons


def parse_teams_page(html: str, season_id: str) -> List[Dict]:
    """Parse the teams list page, filtering to Otso teams only.
    
    Handles two HTML formats:
    1. New format (KESA2026+): tables with class='teams-table'
    2. Old format (pre-2026): single large table with teams embedded as text
    
    Args:
        html: HTML content of the teams page.
        season_id: Season identifier.
        
    Returns:
        List of Otso team dictionaries.
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
                    team_name = team_link.get_text(strip=True)
                    # Filter: only keep Otso teams
                    if not is_otso_team(team_name):
                        continue
                    
                    team_id = None
                    if "team=" in team_link["href"]:
                        for part in team_link["href"].split("&"):
                            if part.startswith("team="):
                                team_id = part.split("=")[1]

                    teams.append({
                        "name": team_name,
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


def _parse_teams_old_format(html: str, season_id: str) -> List[Dict]:
    """Parse teams from old-format HTML (pre-2026 pelikone), filtered to Otso teams.
    
    Args:
        html: HTML content of the teams page.
        season_id: Season identifier.
        
    Returns:
        List of Otso team dictionaries.
    """
    teams = []
    soup = BeautifulSoup(html, "html.parser")
    
    # Teams appear as links with "Pelaajalista" nearby
    team_links = soup.find_all("a", href=True, string=re.compile(r"^\w"))
    
    # Build a list of potential team names
    seen_teams = set()
    for link in team_links:
        name = link.get_text(strip=True)
        # Filter: only keep Otso teams
        if not is_otso_team(name):
            continue
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
            
            team_id = None
            if "team=" in link["href"]:
                for part in link["href"].split("&"):
                    if part.startswith("team="):
                        team_id = part.split("=")[1]
            
            teams.append({
                "name": name,
                "id": team_id,
                "club": "",
                "division": "",
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


def parse_standings_page(html: str, season_id: str) -> List[Dict]:
    """Parse the standings page to get placements.
    
    Handles two HTML formats:
    1. New format: tables with proper placement structure
    2. Old format (pre-2026): placements embedded in text
    
    Args:
        html: HTML content of the standings page.
        season_id: Season identifier.
        
    Returns:
        List of placement dictionaries.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Try new format first
    table = soup.find("table", class_="placements-table")
    if table:
        return _parse_standings_new_format(html, season_id)
    else:
        return _parse_standings_old_format(html, season_id)


def _parse_standings_new_format(html: str, season_id: str) -> List[Dict]:
    """Parse placements from new-format HTML.
    
    Args:
        html: HTML content of the standings page.
        season_id: Season identifier.
        
    Returns:
        List of placement dictionaries.
    """
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
                    team_name = team_link.get_text(strip=True)
                    # Filter: only keep Otso teams
                    if not is_otso_team(team_name):
                        continue
                    
                    team_id = None
                    if "team=" in team_link["href"]:
                        for part in team_link["href"].split("&"):
                            if part.startswith("team="):
                                team_id = part.split("=")[1]

                    placements.append({
                        "placement": placement,
                        "team_name": team_name,
                        "team_id": team_id,
                        "division": division,
                        "season_id": season_id,
                    })

    return placements


def _parse_standings_old_format(html: str, season_id: str) -> List[Dict]:
    """Parse placements from old-format HTML (pre-2026 pelikone).
    
    In old format, placements are embedded in the page text:
    Kulta/Hopea/Pronssi followed by team names, or numbered positions (4., 5., etc.)
    
    Args:
        html: HTML content of the standings page.
        season_id: Season identifier.
        
    Returns:
        List of placement dictionaries.
    """
    placements = []
    soup = BeautifulSoup(html, "html.parser")
    
    # Get all text
    text = soup.get_text()
    
    # Find placement patterns
    placement_pattern = re.compile(
        r"(Kulta|Hopea|Pronssi|(\d+)\.)\s+([^\n]{2,200}?)",
        re.MULTILINE,
    )
    
    divisions = ["Avoin", "Naiset", "Mixed", "Juniorit"]
    
    # Split text by division headers
    for division in divisions:
        # Find this division's section
        div_match = re.search(
            rf"{division}\s*\n(.*?)(?:\n\s*(?:Avoin|Naiset|Mixed|Juniorit)|\n\s*$)",
            text,
            re.DOTALL,
        )
        if not div_match:
            continue
        
        div_text = div_match.group(1)
        
        # Find all placements in this division
        for match in placement_pattern.finditer(div_text):
            placement_type = match.group(1)
            team_names_str = match.group(3).strip()
            
            # Parse team names from the string
            team_names = re.split(r"[\n\xa0]+", team_names_str)
            
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
                # Filter: only keep Otso teams
                if not is_otso_team(team_name):
                    continue
                if team_name and len(team_name) > 1 and team_name not in ["Kulta", "Hopea", "Pronssi"]:
                    placements.append({
                        "placement": placement_num,
                        "team_name": team_name,
                        "team_id": None,
                        "division": division,
                        "season_id": season_id,
                    })
    
    return placements


def parse_team_card(html: str, team_id: str) -> Dict:
    """Parse a team card page.
    
    Args:
        html: HTML content of the team card page.
        team_id: Team identifier.
        
    Returns:
        Dictionary with team_id, players list, and games list.
    """
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "team_id": team_id,
        "players": [],
        "games": [],
    }

    # Parse player list - look for the table with player stats
    player_table = soup.find("table", style=lambda s: s and "width:80%" in s)
    if player_table:
        rows = player_table.find_all("tr")
        for row in rows[1:]:  # Skip header
            tds = row.find_all("td")
            if len(tds) >= 6:
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


def parse_player_list(html: str, team_id: str) -> List[Dict]:
    """Parse the all-time player list for a team.
    
    Args:
        html: HTML content of the player list page.
        team_id: Team identifier.
        
    Returns:
        List of player dictionaries.
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


def parse_csv_teams(html: str, season_id: str) -> List[Dict]:
    """Parse the teams CSV export.
    
    Args:
        html: CSV content as string.
        season_id: Season identifier.
        
    Returns:
        List of team dictionaries.
    """
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


def parse_csv_players(html: str, season_id: str) -> List[Dict]:
    """Parse the players CSV export.
    
    Args:
        html: CSV content as string.
        season_id: Season identifier.
        
    Returns:
        List of player dictionaries.
    """
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


def parse_csv_games(html: str, season_id: str) -> List[Dict]:
    """Parse the games CSV export.
    
    Args:
        html: CSV content as string.
        season_id: Season identifier.
        
    Returns:
        List of game dictionaries.
    """
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


def parse_csv_results(html: str, season_id: str) -> List[Dict]:
    """Parse the results CSV export.
    
    Args:
        html: CSV content as string.
        season_id: Season identifier.
        
    Returns:
        List of result dictionaries.
    """
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


def is_otso_team(team_name: str) -> bool:
    """Check if a team name matches Otso patterns.
    
    Excludes Akatemia teams (separate club) and "Otso 3" (often youth/mixed).
    
    Args:
        team_name: Team name to check.
        
    Returns:
        True if the team is an Otso team.
    """
    name_lower = team_name.lower()
    # Exclude Akatemia teams (separate club)
    if "akatemia" in name_lower:
        return False
    for pattern in OTSO_PATTERNS:
        if pattern in name_lower:
            return True
    return False
