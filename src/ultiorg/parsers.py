"""HTML and CSV parsing functions for pelikone data."""

import csv
import re
from io import StringIO
from typing import List, Dict, Optional, Tuple

from bs4 import BeautifulSoup

from .config import BASE_URL
from .names import canon
from .seasons import classify, season_stage, season_type, season_year


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
    """Year a season ID belongs to — see `ultiorg.seasons.season_year`.

    Any four-digit year counts, so `1999.2` reads as 1999 and `2017F` as 2017.
    """
    return season_year(season_id, season_name)


def classify_season(season_id: str, season_name: str) -> Dict:
    """Classify a season: year, summer/winter, and where it sits in that season.

    Returns `{year, season_type, stage, id, name}`. Two axes, because they are
    two questions: `season_type` is summer / winter / beach / other, and `stage`
    is whether this id is the season itself, a tour stop or a finale
    (`2019.T3` is tour 3 *of* the 2019 summer season).

    The season type comes from the season **name**, not the numeric suffix:
    `2018.1` is winter while `2020.1` is summer. Passing the name is what makes
    `2018.1` classify at all — with no name the numeric ids are `other`, which
    is reported rather than guessed.
    """
    return classify(season_id, season_name)


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


def parse_teams_page(html: str, season_id: str, focus=None) -> List[Dict]:
    """Parse a season's teams page.

    `focus` is a `FocusTeam` (see `teams.py`): when given, only that club's
    squads come back. Left `None`, every team in the season does - the library
    has no default club, so filtering is always the caller's decision.

    One HTML format. There used to be a second branch for a "pre-2026" layout no
    page in the archive uses: 73/73 cached teams pages, spanning 2006 to 2026,
    carry `teams-table`. Dead code for a format nobody has ever observed.
    """
    teams = []
    soup = BeautifulSoup(html, "html.parser")

    for table in soup.find_all("table", class_="teams-table"):
        division = ""
        th = table.find("th", colspan=True)
        if th:
            division = th.get_text(strip=True)
        first_row = table.find("tr")
        if first_row and not division:
            first_td = first_row.find("td")
            if first_td:
                division = first_td.get_text(strip=True)

        for row in table.find_all("tr")[1:]:  # Skip header
            tds = row.find_all("td")
            if len(tds) < 3:
                continue
            team_link = tds[0].find("a")
            if not team_link:
                continue
            team_name = team_link.get_text(strip=True)
            if focus is not None and not focus.matches(team_name):
                continue

            team_id = None
            for part in team_link["href"].split("&"):
                if part.startswith("team="):
                    team_id = part.split("=")[1]

            club_link = tds[1].find("a")
            player_link = tds[2].find("a", href=True)
            teams.append({
                "name": team_name,
                "id": team_id,
                "club": club_link.get_text(strip=True) if club_link else "",
                "division": division,
                "season_id": season_id,
                "player_list_url": f"{BASE_URL}/{player_link['href']}" if player_link else None,
            })

    return teams


def parse_standings_page(html: str, season_id: str, focus=None) -> List[Dict]:
    """Parse a season's standings/placements page.

    `focus` narrows the result to one club's squads; left `None` the whole
    podium comes back, which is what the trophy view needs in order to see who
    beat whom.

    One HTML format, as for teams: every one of the 717 placements in the
    archive carries a `team_id`, which only the table parser produces, so the
    old text-scraping branch had never run on a single page. It is gone.
    """
    soup = BeautifulSoup(html, "html.parser")
    if soup.find("table", class_="placements-table") is None:
        return []
    return _parse_standings_new_format(html, season_id, focus)


def _parse_standings_new_format(html: str, season_id: str, focus=None) -> List[Dict]:
    """Scrape the placements table: one row per placement, one column per division.

    Columns are divisions, rows are placement numbers; a team link gives the name
    and the pelikone team id. `focus` narrows to one club when given.
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
                    # `focus` narrows to one club; None keeps every team on the podium.
                    if focus is not None and not focus.matches(team_name):
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


class NotCsvError(ValueError):
    """Raised when a CSV parser is handed something that is not CSV.

    `?view=ext/export` is an HTML page that *links* the CSVs; feeding it to a CSV
    parser used to produce one row of empty strings per line, silently. The
    headers are the cheapest thing that distinguishes the two, so check them.
    """


def _read_csv(text: str, required_column: str):
    """`csv.DictReader` over `text`, refusing input that is not that CSV."""
    if text.lstrip().startswith("<"):
        raise NotCsvError(
            "got HTML, not CSV — the CSVs are at ext/<kind>csv.php, "
            "while ?view=ext/export is the page that links them"
        )
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise NotCsvError("empty CSV input")
    if required_column not in reader.fieldnames:
        raise NotCsvError(
            f"not the expected CSV: no {required_column!r} column, "
            f"headers are {reader.fieldnames}"
        )
    return reader


def parse_csv_teams(text: str, season_id: str) -> List[Dict]:
    """Parse the teams CSV export.
    
    Args:
        text: CSV text from `ext/<kind>csv.php` — not the export page.
        season_id: Season identifier.
        
    Returns:
        List of team dictionaries.
    """
    teams = []
    reader = _read_csv(text, "Team")
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


def parse_csv_players(text: str, season_id: str) -> List[Dict]:
    """Parse the players CSV export.
    
    Args:
        text: CSV text from `ext/<kind>csv.php` — not the export page.
        season_id: Season identifier.
        
    Returns:
        List of player dictionaries.
    """
    players = []
    reader = _read_csv(text, "LastName")
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


def parse_csv_games(text: str, season_id: str) -> List[Dict]:
    """Parse the games CSV export.
    
    Args:
        text: CSV text from `ext/<kind>csv.php` — not the export page.
        season_id: Season identifier.
        
    Returns:
        List of game dictionaries.
    """
    games = []
    reader = _read_csv(text, "HomeTeam")
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


def parse_csv_results(text: str, season_id: str) -> List[Dict]:
    """Parse the results CSV export.
    
    Args:
        text: CSV text from `ext/<kind>csv.php` — not the export page.
        season_id: Season identifier.
        
    Returns:
        List of result dictionaries.
    """
    results = []
    reader = _read_csv(text, "Home")
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


def parse_csv_pools(text: str, season_id: str) -> List[Dict]:
    """Parse the pools CSV export — standings per pool.

    Args:
        text: CSV text from `ext/<kind>csv.php` — not the export page.
        season_id: Season identifier.

    Returns:
        List of pool-standing dictionaries.
    """
    standings = []
    reader = _read_csv(text, "Pool")
    for row in reader:
        standings.append({
            "division": row.get("Division", ""),
            "pool": row.get("Pool", ""),
            "standing": _int(row.get("Standing", "")),
            "team": row.get("Team", ""),
            "games": _int(row.get("Games", "")),
            "wins": _int(row.get("Wins", "")),
            "losses": _int(row.get("Losses", "")),
            "goals_for": _int(row.get("GoalsFor", "")),
            "goals_against": _int(row.get("GoalsAgainst", "")),
            "goals_diff": _int(row.get("GoalsDiff", "")),
            "season_id": season_id,
        })
    return standings


def parse_csv_spirit(text: str, season_id: str) -> List[Dict]:
    """Parse the spirit CSV export — one row per evaluation.

    Spirit is the self-refereeing score: each team rates the other on Rules,
    Fouls, Fair, Positive and Communication. `team` is the team being rated,
    `by_team` the rater.
    """
    evaluations = []
    reader = _read_csv(text, "TeamEvaluated")
    for row in reader:
        evaluations.append({
            "division": row.get("Division", ""),
            "field_group": row.get("FieldGroup", ""),
            "date": row.get("Date", ""),
            "field": row.get("Field", ""),
            "time": row.get("Time", ""),
            "pool": row.get("Pool", ""),
            "team": row.get("TeamEvaluated", ""),
            "by_team": row.get("ByTeam", ""),
            "rules": _int(row.get("Rules", "")),
            "fouls": _int(row.get("Fouls", "")),
            "fair": _int(row.get("Fair", "")),
            "positive": _int(row.get("Positive", "")),
            "communication": _int(row.get("Com", "")),
            "total": _int(row.get("Total", "")),
            "comments": row.get("Comments", ""),
            "season_id": season_id,
        })
    return evaluations


def parse_games_list(html: str, season_id: str, focus=None) -> List[Dict]:
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
        
        # `focus` narrows the list to one club; without it, every game in the season.
        if focus is None or focus.matches(home_team) or focus.matches(away_team):
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


# --- event-level views ------------------------------------------------------

def parse_series_menu(html: str) -> List[Dict]:
    """The series (one per division) of the event a page belongs to.

    The left menu lists `?view=seriesstatus&series=NNNN` links. `series` is the
    ID `scorestatus` takes, and it is a **different ID space from `season`**:
    KESA2026 has series 3300 (Avoin), 3301 (Naiset), 3302 (Mixed), 3303
    (Juniorit U17). Nothing else on the page exposes them, so this menu is how
    you enumerate a season's scoreboards.
    """
    series: List[Dict] = []
    seen: set[str] = set()
    for link in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        href = link["href"]
        if "view=seriesstatus" not in href:
            continue
        match = re.search(r"series=(\d+)", href)
        if not match or match.group(1) in seen:
            continue
        seen.add(match.group(1))
        series.append({
            "series_id": match.group(1),
            "name": " ".join(link.get_text().replace("\xa0", " ").split()),
        })
    return series


_SCORESTATUS_HEADERS = ["#", "Pelaaja", "Joukkue", "GP", "A", "G", "Tot.", "A Avg.", "G Avg.", "Tot. Avg.", "Call."]


def parse_scorestatus(html: str, series_id: str) -> List[Dict]:
    """Parse `?view=scorestatus&series=<seriesID>` — one event's whole scoreboard.

    One row per player who played in that series, **with player IDs**: rank,
    name, team, GP, A, G, Tot., the three averages, Callahans. This is the
    cheapest bulk source of ID-keyed per-event scoring: 123 players for KESA2026
    Avoin in one request, versus one request per player.

    Unlike `playercard` this is scoped to one series, so a player who played two
    divisions of the same event appears on two scoreboards.

    The page renders this table **twice** — once inside `div.page_middle` (with
    the event menu) and once inside `div.content`. Same 123 players both times;
    scanning the document would double every row, so scope to `content`.
    """
    soup = BeautifulSoup(html, "html.parser")
    content = soup.find("div", class_="content") or soup
    players: List[Dict] = []
    for table in content.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [c.get_text(strip=True) for c in rows[0].find_all("th")]
        if headers[:11] != _SCORESTATUS_HEADERS:
            continue
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 11:
                continue
            link = cells[1].find("a", href=True)
            player_id = ""
            if link:
                match = re.search(r"player=(\d+)", link["href"])
                player_id = match.group(1) if match else ""
            players.append({
                "series_id": series_id,
                "rank": _int(cells[0].get_text(strip=True)),
                "player_id": player_id,
                "name": " ".join(cells[1].get_text().replace("\xa0", " ").split()),
                "team": " ".join(cells[2].get_text().replace("\xa0", " ").split()),
                "gp": _int(cells[3].get_text(strip=True)),
                "assists": _int(cells[4].get_text(strip=True)),
                "goals": _int(cells[5].get_text(strip=True)),
                "total": _int(cells[6].get_text(strip=True)),
                "avg_assists": _float(cells[7].get_text(strip=True)),
                "avg_goals": _float(cells[8].get_text(strip=True)),
                "avg_total": _float(cells[9].get_text(strip=True)),
                "callahans": _int(cells[10].get_text(strip=True)),
            })
    return players


_TOP_STAT_RE = re.compile(r"A\s+(\d+)\s*\+\s*G\s+(\d+)\s*=\s*Tot\.\s*(\d+)")


def parse_statistics(html: str) -> List[Dict]:
    """Parse `?view=statistics&list=playerscoreboard` — top three per event.

    The page is grouped by `<h2>` (Sisä / Ulko / Ranta — indoor, outdoor, beach)
    and `<h3>` (division), then one table per division listing every event with
    its three leading scorers. Each event cell links its `scorestatus` series and
    each player cell links their `playercard`, so this one page is a map from
    event name to series ID **and** a shortcut to the top scorers' IDs.

    Returns one dict per event:

        {section, division, event, series_id, top: [{rank, player_id, name,
         team, assists, goals, total}]}

    The `season=` parameter does not scope this list — the page shows every
    event the instance has, which is why it is worth caching as an index.
    """
    content = BeautifulSoup(html, "html.parser").find("div", class_="content")
    if content is None:
        return []

    events: List[Dict] = []
    section = division = ""
    for element in content.find_all(["h2", "h3", "table"], recursive=False):
        if element.name == "h2":
            section = " ".join(element.get_text().replace("\xa0", " ").split())
            division = ""
            continue
        if element.name == "h3":
            division = " ".join(element.get_text().replace("\xa0", " ").split())
            continue

        rows = element.find_all("tr")
        if not rows or "Tapahtuma" not in rows[0].get_text():
            continue
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            event_link = cells[0].find("a", href=True)
            if not event_link:
                continue
            series_match = re.search(r"series=(\d+)", event_link["href"])
            top: List[Dict] = []
            for rank, cell in enumerate(cells[1:4], start=1):
                player_link = cell.find("a", href=True)
                if not player_link:
                    continue
                player_match = re.search(r"player=(\d+)", player_link["href"])
                lines = [" ".join(part.replace("\xa0", " ").split())
                         for part in cell.get_text("\n").split("\n")]
                lines = [line for line in lines if line]
                stats = _TOP_STAT_RE.search(cell.get_text(" ", strip=True))
                top.append({
                    "rank": rank,
                    "player_id": player_match.group(1) if player_match else "",
                    "name": " ".join(player_link.get_text().replace("\xa0", " ").split()),
                    "team": lines[1] if len(lines) > 1 else "",
                    "assists": _int(stats.group(1)) if stats else None,
                    "goals": _int(stats.group(2)) if stats else None,
                    "total": _int(stats.group(3)) if stats else None,
                })
            events.append({
                "section": section,
                "division": division,
                "event": " ".join(event_link.get_text().replace("\xa0", " ").split()),
                "series_id": series_match.group(1) if series_match else "",
                "top": top,
            })
    return events


def parse_allteams(html: str) -> List[Dict]:
    """Parse `?view=allteams&list=all` — every team, with ID, name, division.

    `list=all` is required: the default renders one letter group. The grid pads
    its last row with **empty cells** (`teamcard&team=` with no ID and a bare
    `[]`); those are skipped, not returned as nameless teams.
    """
    teams: List[Dict] = []
    seen: set[str] = set()
    for link in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        href = link["href"]
        if "view=teamcard" not in href:
            continue
        match = re.search(r"team=(\d+)", href)
        if not match:
            continue
        team_id = match.group(1)
        if team_id in seen:
            continue
        seen.add(team_id)
        cell = link.find_parent("td") or link
        text = " ".join(cell.get_text().replace("\xa0", " ").split())
        division_match = re.search(r"\[([^\]]+)\]", text)
        teams.append({
            "id": team_id,
            "name": " ".join(link.get_text().replace("\xa0", " ").split()),
            "division": division_match.group(1) if division_match else "",
        })
    return teams


def parse_allclubs(html: str) -> List[Dict]:
    """Parse `?view=allclubs&list=all` — every club, with ID and name.

    Same letter-group trap as `allteams`: without `list=all` you get one group.
    """
    clubs: List[Dict] = []
    seen: set[str] = set()
    for link in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        href = link["href"]
        if "view=clubcard" not in href:
            continue
        match = re.search(r"club=(\d+)", href)
        if not match:
            continue
        club_id = match.group(1)
        if club_id in seen:
            continue
        seen.add(club_id)
        clubs.append({
            "id": club_id,
            "name": " ".join(link.get_text().replace("\xa0", " ").split()),
        })
    return clubs
