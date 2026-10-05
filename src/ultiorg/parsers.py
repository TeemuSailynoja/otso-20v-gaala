"""HTML and CSV parsing functions for pelikone data."""

import csv
import re
from io import StringIO
from typing import List, Dict, Optional, Tuple

from bs4 import BeautifulSoup

from .config import BASE_URL, OTSO_PATTERNS
from .names import canon


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


def is_otso_akatemia(team_name: str) -> bool:
    """True for Otso Akatemia specifically, not for Akatemia teams in general.

    `is_otso_team` excludes every Akatemia team because Akatemia is a separate
    club; the gala still wants to know when the opponent (or the other side of a
    fixture) is Otso's Akatemia squad. `build_site_data.is_otso_akatemia` is the
    same rule; Phase 8 folds both into the `teams.yaml` predicate.
    """
    lower = team_name.lower()
    return "akatemia" in lower and "otso" in lower


def parse_games_list(html: str, season_id: str) -> List[Dict]:
    """Parse the games list page.
    
    Row structure (verified from KESA2026):
    [0] Time, [1] Field, [2] Home team, [3] "-", [4] Away team,
    [5] Home score, [6] "-", [7] Away score, [8+] division/series, [10] Pelin kulku link
    
    Args:
        html: HTML content of the games list page.
        season_id: Season identifier.
        
    Returns:
        List of game dictionaries with game_id, time, venue, home_team, away_team,
        home_score, away_score, division.
    """
    games = []
    soup = BeautifulSoup(html, "html.parser")
    
    # Find all game rows by looking for "Pelin kulku" links
    for tr in soup.find_all("tr"):
        # Look for Pelin kulku link anywhere in the row
        gameplay_link = tr.find("a", string="Pelin kulku")
        if not gameplay_link:
            continue
        
        # Get the td cells
        tds = tr.find_all("td")
        if len(tds) < 8:
            continue
        
        # Extract game_id from href
        href = gameplay_link["href"]
        game_id = None
        if "game=" in href:
            for part in href.split("&"):
                if part.startswith("game="):
                    game_id = part.split("=")[1]
        
        if not game_id:
            continue
        
        # Extract time and venue
        time_str = tds[0].get_text(strip=True) if len(tds) > 0 else ""
        venue = tds[1].get_text(strip=True) if len(tds) > 1 else ""
        
        # Extract teams and scores
        home_team = tds[2].get_text(strip=True) if len(tds) > 2 else ""
        # tds[3] is "-" separator
        away_team = tds[4].get_text(strip=True) if len(tds) > 4 else ""
        
        # Try to extract scores
        home_score = None
        away_score = None
        try:
            home_score = int(tds[5].get_text(strip=True)) if len(tds) > 5 else None
            away_score = int(tds[7].get_text(strip=True)) if len(tds) > 7 else None
        except (ValueError, IndexError):
            pass
        
        # Extract division from remaining cells
        division = ""
        for td in tds[8:]:
            text = td.get_text(strip=True)
            if text and text not in ["-", ""] and "Pelin kulku" not in text:
                division = text
                break
        
        # Only include games where at least one team is Otso
        if is_otso_team(home_team) or is_otso_team(away_team):
            games.append({
                "game_id": game_id,
                "time": time_str,
                "venue": venue,
                "home_team": home_team,
                "away_team": away_team,
                "home_score": home_score,
                "away_score": away_score,
                "division": division,
                "season_id": season_id,
            })
    
    return games


def _player_cell(td) -> Optional[str]:
    """`#77 Patrick Potrykus` -> `Patrick Potrykus`; empty or `-` -> None."""
    text = td.get_text(" ", strip=True)
    text = re.sub(r"^#\d*\s*", "", text).strip()
    return text if text and text != "-" else None


def parse_gameplay(html: str) -> Dict:
    """Parse a gameplay (point-by-point) page: `?view=gameplay&game=ID`.

    Returns `home_team`, `away_team`, `home_score`, `away_score`, `points`,
    `home_players`, `away_players`. Sides are positional (first scoreboard =
    home). Each point carries `side` (the scoring team), `score`, `time`,
    `passer`, `scorer`, and — after `apply_possession` — `possession` (the side
    that started the point on defense) plus `possession_known`. Roster entries
    carry the pelikone player `id`, the only place a gameplay page gives one.
    """
    result = {
        "home_team": "",
        "away_team": "",
        "home_score": None,
        "away_score": None,
        "points": [],
        "home_players": [],
        "away_players": [],
    }
    
    soup = BeautifulSoup(html, "html.parser")
    
    # Parse h1 title: "Team A - Team B    SCORE - SCORE"
    # Team names and sides come from the two scoreboard CAPTIONS, in document
    # order: first board = home, second = away. Measured over the 795 archived
    # games, caption order matches the <h1> order in 792 of them, and the 3
    # exceptions are <h1> parse failures on hyphenated team names
    # ("SOS-Terror - Otso 2", "TT-Lätty - Otso 3"), where the captions are right
    # and the heading is not. Matching captions against an <h1>-derived name is
    # also unsafe: with home "Otso 2" and away "Otso", the substring test put the
    # away roster on the home side and left `away_players` empty — 12 games.
    boards = soup.find_all("div", class_="gameplay-scoreboard")
    board_teams: List[str] = []
    for scoreboard in boards:
        caption = scoreboard.find("caption")
        board_teams.append(caption.get_text(strip=True) if caption else "")

    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
        # Score is the trailing "N - M"; take it from the END of the heading so a
        # hyphen inside a team name cannot be mistaken for the separator.
        score_match = re.search(r"(\d+)\s*-\s*(\d+)\s*$", title)
        if score_match:
            result["home_score"] = int(score_match.group(1))
            result["away_score"] = int(score_match.group(2))
            names_part = title[: score_match.start()].strip()
        else:
            names_part = title
        # Only used when the page has no usable captions.
        heading_teams = [p.strip() for p in re.split(r"\s+-\s+", names_part)]
        if len(heading_teams) >= 2:
            result["home_team"] = heading_teams[0]
            result["away_team"] = " - ".join(heading_teams[1:])

    if len(board_teams) == 2 and all(board_teams):
        result["home_team"], result["away_team"] = board_teams
    
    # Parse point-by-point table
    # The table has a single <tr> with <td> cells.
    #
    # The point-by-point table is a <table> whose <th> headers include Pisteet
    # and Maali, inside div.content:
    #
    #   Pisteet | Syöttäjä | Maali | Aika | Kesto [| Pelitapahtumat]
    #     0 - 1   #77 Potrykus  #88 Arola  5.00   5.00    Hyökkäys 0.00
    #
    # The first cell carries class `home` or `guest` — the team that SCORED. The
    # Syöttäjä column is the passer, Maali the scorer (the column order is the
    # opposite of what the old `title` string implied). Older pages have no
    # Pelitapahtumat column, so the Hyökkäys marker is missing there.
    #
    # The same table is also rendered in a site-wide results strip in
    # div.page_middle, where each cell carries a `title` like
    # "5.00 0-1 Potrykus Patrick -> Arola Matias". The old parser scanned <tr>s
    # document-wide and read those titles: that appends every goal twice (467 of
    # the 788 stored games were exactly doubled), and because the point table sits
    # inside layout tables the scan flattens unrelated cells into one row — a
    # "point row" with 21 cells whose last cell is a score cell, not the events
    # column, which is why the Hyökkäys marker was never seen. Cells are taken as
    # direct children of the row of the content copy, and deduped as a backstop.
    point_tables = [
        table
        for table in soup.find_all("table")
        if {"Pisteet", "Maali"} <= {th.get_text(strip=True) for th in table.find_all("th")}
    ]
    content = soup.find("div", class_="content")
    if content:
        inside = [t for t in point_tables if t.find_parent("div", class_="content")]
        point_tables = inside or point_tables

    seen: set = set()
    for table in point_tables:
        for tr in table.find_all("tr"):
            tds = tr.find_all("td", recursive=False)
            if not tds:
                continue

            for td in tds:
                if "halftime" in (td.get("class") or []):
                    text = td.get_text(strip=True)
                    if ("halftime", text) in seen:
                        continue
                    seen.add(("halftime", text))
                    result["points"].append({"type": "halftime", "text": text})
                    break

            classes = tds[0].get("class") or []
            if "home" not in classes and "guest" not in classes:
                continue
            side = "home" if "home" in classes else "guest"
            score = tds[0].get_text(strip=True).replace(" ", "")
            passer = _player_cell(tds[1]) if len(tds) >= 3 else None
            scorer = _player_cell(tds[2]) if len(tds) >= 3 else None
            clock = tds[3].get_text(strip=True) if len(tds) >= 4 else ""
            if ("point", side, score, passer, scorer, clock) in seen:
                continue
            seen.add(("point", side, score, passer, scorer, clock))

            point = {"type": "point", "side": side, "score": score}
            if clock:
                point["time"] = clock
            if passer:
                point["passer"] = passer
            if scorer:
                point["scorer"] = scorer

            # The events column carries `<div class='home'>Hyökkäys&nbsp;0.00</div>`:
            # the team whose class it is started that point on OFFENSE. Only the
            # very first point needs it — after that the scorer decides the next
            # possession — but it is captured wherever it appears.
            for div in tds[-1].find_all("div", class_=True):
                if "Hyökkäys" in div.get_text():
                    point["offense_marker"] = "home" if "home" in div["class"] else "guest"
                    break

            result["points"].append(point)

    # Parse player rosters from gameplay-scoreboard tables, POSITIONALLY: the
    # first board is the home team, the second is the away team.
    for index, scoreboard in enumerate(boards):
        if index > 1:
            break  # only two teams per game; ignore any extra strip
        caption = scoreboard.find("caption")
        team_name = caption.get_text(strip=True) if caption else ""
        side = "home_players" if index == 0 else "away_players"
        
        players = []
        for row in scoreboard.find_all("tr")[1:]:  # Skip header
            tds = row.find_all("td")
            if len(tds) >= 5:
                # #, Nimi (with link), Syötöt, Maalit, Yht.
                name_cell = tds[1]
                name_link = name_cell.find("a")
                player_name = name_link.get_text(strip=True) if name_link else name_cell.get_text(strip=True)

                # Remove (C) captain marker
                player_name = re.sub(r'\s*\(C\)', '', player_name).strip()

                # The roster link is the only place a gameplay page carries a
                # player ID — point rows are plain text. This is what makes the
                # archived corpus enough to re-key everything offline.
                player_id = ""
                if name_link and "player=" in name_link.get("href", ""):
                    id_match = re.search(r"player=(\d+)", name_link["href"])
                    if id_match:
                        player_id = id_match.group(1)

                try:
                    assists = int(tds[2].get_text(strip=True)) if tds[2].get_text(strip=True) else 0
                    goals = int(tds[3].get_text(strip=True)) if tds[3].get_text(strip=True) else 0
                    total = int(tds[4].get_text(strip=True)) if tds[4].get_text(strip=True) else 0
                except (ValueError, IndexError):
                    assists = goals = total = 0

                players.append({
                    "id": player_id,
                    "name": player_name,
                    "assists": assists,
                    "goals": goals,
                    "total": total,
                })
        
        if team_name:
            result[side] = players

    apply_possession(result)
    return result


def apply_possession(gameplay: Dict) -> None:
    """Store which side started each point on defense, in place.

    The rule was `build_site_data.build_defense_stats` (line 1107), which
    re-derived it from raw HTML at analytics time. It is a property of the game,
    not of Otso, so it belongs in the parser and in the fact store:

    1. the first point's offense side comes from the `Hyökkäys` marker;
    2. after each point **the scorer starts the next point on defense**;
    3. at halftime the team that started the half on defense starts on offense;
    4. a scorer's side comes from **that game's roster map**, because the point
       cell's `side` class is not reliable for identifying the scorer's team;
    5. with no marker, point 1 is left unattributed and `possession_known = 0`
       — rates stay honest instead of guessing.

    Each point gains `possession` ('home' | 'guest' | None) and
    `possession_known` (1 | 0).
    """
    roster_side: Dict[str, str] = {}
    for side, key in (("home", "home_players"), ("guest", "away_players")):
        for player in gameplay.get(key, []):
            key_name = canon(player.get("name", ""))
            if key_name:
                roster_side[key_name] = side

    def opposite(side: str) -> str:
        return "guest" if side == "home" else "home"

    def scorer_side(point: Dict) -> Optional[str]:
        name = canon(point.get("scorer") or "")
        return roster_side.get(name) if name else None

    points = gameplay.get("points", [])
    markers = [p.get("offense_marker") for p in points if p.get("offense_marker")]
    first_offense = markers[0] if markers else None

    if first_offense:
        first_half_defense = opposite(first_offense)
        defense = first_half_defense
        for point in points:
            if point.get("type") == "halftime":
                defense = opposite(first_half_defense)
                continue
            point["possession"] = defense
            point["possession_known"] = 1
            side = scorer_side(point)
            if side:
                defense = side
        return

    # No marker anywhere: the first point of each half cannot be attributed.
    defense: Optional[str] = None
    for point in points:
        if point.get("type") == "halftime":
            defense = None
            continue
        if defense is None:
            point["possession"] = None
            point["possession_known"] = 0
        else:
            point["possession"] = defense
            point["possession_known"] = 1
        side = scorer_side(point)
        if side:
            defense = side


# --- player identity views --------------------------------------------------


def parse_allplayers(html: str) -> List[Dict]:
    """Parse `?view=allplayers&list=all` — every registered player, with IDs.

    The default view shows only one letter group; `list=all` is the whole index
    (2,568 players measured). Names are `First Last` and separated by a plain
    space here, unlike gameplay rosters (U+00A0).

    Some entries have an **empty name** with a real ID (measured: 3 of 2,568).
    They are kept, not dropped — an ID with no name is a data-quality fact, and
    dropping it would silently lose that player's points.
    """
    soup = BeautifulSoup(html, "html.parser")
    players: List[Dict] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "view=playercard" not in href:
            continue
        match = re.search(r"player=(\d+)", href)
        if not match:
            continue
        player_id = match.group(1)
        if player_id in seen:
            continue
        seen.add(player_id)
        name = " ".join(link.get_text().replace("\xa0", " ").split())
        players.append({"id": player_id, "name": name})
    return players


_PROFILE_LABELS = {
    "Lempinimi": "nickname",
    "Syntymäpaikka": "birthplace",
    "Kansallisuus": "nationality",
    "Kätisyys": "handedness",
    "Pituus": "height",
    "Paino": "weight",
}


def _int(text: str) -> Optional[int]:
    text = text.strip()
    try:
        return int(text)
    except ValueError:
        return None


def _float(text: str) -> Optional[float]:
    text = text.strip().rstrip("%").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_playercard(html: str, player_id: str) -> Dict:
    """Parse `?view=playercard&series=0&player=<id>` — one player's career.

    Returns:

        player_id, name, jersey, current_team {id, name}, profile {...},
        totals {gp, assists, goals, total, callahans, wins, win_pct},
        career_by_type [{type, division, ...}]   (indoor / outdoor / beach)
        career_by_event [{event, division, team, gp, assists, goals, ...}]

    The card is the cheapest way to get a player's whole career: one request per
    player instead of one per season. Note it exposes birthplace and nationality
    but **no birth date** — the birthdays in `data/private/` are not from here.
    """
    soup = BeautifulSoup(html, "html.parser")
    result: Dict = {
        "player_id": player_id,
        "name": "",
        "jersey": "",
        "current_team": None,
        "profile": {},
        "totals": {},
        "career_by_type": [],
        "career_by_event": [],
    }

    h1 = soup.find("h1")
    if h1:
        title = " ".join(h1.get_text().replace("\xa0", " ").split())
        jersey_match = re.match(r"#(\d+)\s+(.*)$", title)
        if jersey_match:
            result["jersey"] = jersey_match.group(1)
            result["name"] = jersey_match.group(2).strip()
        else:
            result["name"] = title

    header = soup.find("p")
    if header:
        team_link = header.find("a", href=True)
        if team_link:
            team_id = re.search(r"team=(\d+)", team_link["href"])
            result["current_team"] = {
                "id": team_id.group(1) if team_id else "",
                "name": team_link.get_text(strip=True),
            }

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) == 2:
            label = cells[0].get_text(strip=True).rstrip(":")
            if label in _PROFILE_LABELS:
                value = " ".join(cells[1].get_text().replace("\xa0", " ").split())
                if value:
                    result["profile"][_PROFILE_LABELS[label]] = value

    for table in soup.find_all("table", class_="statistics-table"):
        rows = table.find_all("tr")
        header_cells = rows[0].find_all("th") if rows else []
        headers = [c.get_text(strip=True) for c in header_cells]
        by_event = "Joukkue" in headers

        for row in rows[1:]:
            cells = row.find_all("td")
            if not cells:
                continue
            texts = [c.get_text(strip=True) for c in cells]
            # The ten numeric columns are always last: GP A G Tot. A Avg. G Avg.
            # Tot. Avg. Call. W Voitto-%. Label columns before them vary — the
            # totals row collapses its two label cells with colspan=2 — so count
            # from the end instead of assuming an offset.
            if len(texts) < 11:
                continue
            numbers = texts[-10:]
            labels = texts[:-10]
            stats = {
                "gp": _int(numbers[0]),
                "assists": _int(numbers[1]),
                "goals": _int(numbers[2]),
                "total": _int(numbers[3]),
                "avg_assists": _float(numbers[4]),
                "avg_goals": _float(numbers[5]),
                "avg_total": _float(numbers[6]),
                "callahans": _int(numbers[7]),
                "wins": _int(numbers[8]),
                "win_pct": _float(numbers[9]),
            }
            if labels and labels[0].startswith("Yhteensä"):
                result["totals"] = stats
                continue
            if by_event and len(labels) >= 3:
                result["career_by_event"].append(
                    {"event": labels[0], "division": labels[1], "team": labels[2], **stats}
                )
            elif len(labels) >= 2:
                result["career_by_type"].append({"type": labels[0], "division": labels[1], **stats})

    return result
