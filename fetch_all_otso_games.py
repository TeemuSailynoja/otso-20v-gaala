#!/usr/bin/env python3
"""Fetch all Otso games from all seasons and update match_results.json."""
import requests
import json
import re
import time
from bs4 import BeautifulSoup
from pathlib import Path

BASE_URL = "https://ultimate.fi/pelikone"
headers = {"User-Agent": "Otso20v-Gaala-DataBot/1.0"}

# Load existing match_results.json
with open("/home/teemu/repos/otso-20v-gaala/data/processed/match_results.json") as f:
    matches = json.load(f)

existing_ids = {m["game_id"] for m in matches}
print(f"Existing games in match_results.json: {len(existing_ids)}")

# Fetch season list to get all season IDs
seasons_url = f"{BASE_URL}/?view=seasonlist"
print(f"Fetching season list...")
resp = requests.get(seasons_url, headers=headers, timeout=30)
resp.raise_for_status()
soup = BeautifulSoup(resp.text, "html.parser")

# Find all unique season IDs with "Pelatut pelit"
season_ids = set()
for a in soup.find_all("a", href=True):
    href = a["href"]
    text = a.get_text(strip=True)
    if "Pelatut pelit" in text and "season=" in href:
        m = re.search(r"season=(.+?)(&|$)", href)
        if m:
            season_ids.add(m.group(1))

print(f"Found {len(season_ids)} unique seasons")

# For each season, find Otso games
all_otso_games = []
for season_id in sorted(season_ids):
    games_url = f"{BASE_URL}/?view=games&season={season_id}"
    print(f"\nChecking season {season_id}...")
    try:
        resp = requests.get(games_url, headers=headers, timeout=30)
        if resp.status_code != 200:
            print(f"  Skipping {season_id}: HTTP {resp.status_code}")
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Find Otso games
        season_games = []
        for span in soup.find_all("span"):
            classes = span.get("class", []) or []
            if ("game-winner" in classes or "game-loser" in classes) and "Otso" in span.get_text():
                row = span.find_parent("tr")
                if row:
                    cells = row.find_all(["td", "th"])
                    if cells:
                        pelin_kulku = row.find("a", string="Pelin kulku")
                        if pelin_kulku:
                            m = re.search(r"game=(\d+)", pelin_kulku["href"])
                            if m:
                                game_id = int(m.group(1))
                                home = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                                away = cells[4].get_text(strip=True) if len(cells) > 4 else ""
                                home_score = cells[5].get_text(strip=True) if len(cells) > 5 else ""
                                away_score = cells[7].get_text(strip=True) if len(cells) > 7 else ""
                                season_games.append({
                                    "game_id": game_id,
                                    "home": home,
                                    "away": away,
                                    "home_score": home_score,
                                    "away_score": away_score,
                                    "season_id": season_id,
                                })
        
        if season_games:
            print(f"  Found {len(season_games)} Otso games")
            all_otso_games.extend(season_games)
        
        time.sleep(0.5)  # Be respectful
    except Exception as e:
        print(f"  Error fetching {season_id}: {e}")

print(f"\nTotal Otso games found: {len(all_otso_games)}")

# Filter out games we already have
new_games = [g for g in all_otso_games if str(g["game_id"]) not in existing_ids]
print(f"New games to fetch: {len(new_games)}")

# Fetch gameplay data for new games
print("\nFetching gameplay data for new games...")
for i, game in enumerate(new_games):
    gid = game["game_id"]
    game_url = f"{BASE_URL}/?view=gameplay&game={gid}"
    print(f"  [{i+1}/{len(new_games)}] Fetching game {gid}...")
    
    try:
        resp = requests.get(game_url, headers=headers, timeout=30)
        if resp.status_code != 200:
            print(f"    Skipping {gid}: HTTP {resp.status_code}")
            continue
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Get game info from title
        title = soup.find("h1")
        title_text = title.get_text(strip=True) if title else ""
        
        # Extract score from title
        score_match = re.search(r"(\d+)\s*[-–—]\s*(\d+)", title_text)
        home_score = int(score_match.group(1)) if score_match else 0
        away_score = int(score_match.group(2)) if score_match else 0
        
        # Get teams from title
        teams_match = re.match(r"^(.+?)\s+[-–—]\s+(.+?)\s+\d+\s+[-–—]\s+\d+$", title_text)
        home_team = teams_match.group(1).strip() if teams_match else game["home"]
        away_team = teams_match.group(2).strip() if teams_match else game["away"]
        
        # Get points table
        tables = soup.find_all("table")
        points_table = None
        for table in tables:
            first_row = table.find_all(["td", "th"])
            if first_row and "Pisteet" in first_row[0].get_text():
                points_table = table
                break
        
        if not points_table:
            print(f"    Warning: No points table found for game {gid}")
            continue
        
        # Parse points
        rows = points_table.find_all("tr")[1:]  # Skip header
        points = []
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 4:
                score = cells[0].get_text(strip=True)
                scorer_raw = cells[1].get_text(strip=True)
                assist_raw = cells[2].get_text(strip=True)
                time_str = cells[3].get_text(strip=True)
                
                # Extract player names
                scorer = re.sub(r"^#\d+\s*", "", scorer_raw).strip()
                assist = re.sub(r"^#\d+\s*", "", assist_raw).strip()
                
                # Determine side
                score_parts = score.split("-")
                if len(score_parts) == 2:
                    first_score = int(score_parts[0])
                    side = "home" if first_score <= home_score else "guest"
                else:
                    side = "home"
                
                points.append({
                    "type": "point",
                    "side": side,
                    "title": f"{time_str} {score} {scorer} -> {assist}",
                    "time": time_str,
                    "score": score,
                    "scorer": scorer,
                    "assist": assist,
                })
        
        # Get player rosters - handle both modern (div.scoreboard) and old (table with caption) formats
        home_players = []
        away_players = []
        
        # Modern format: div.gameplay-scoreboard
        scoreboards = soup.find_all("div", class_="gameplay-scoreboard")
        for sb in scoreboards:
            team_name = sb.find("span", class_="gameplay-team-name")
            if team_name:
                team = team_name.get_text(strip=True)
                is_home = team == home_team
                is_away = team == away_team
                
                if not is_home and not is_away:
                    continue
                
                rows = sb.find_all("tr")
                for row in rows[1:]:
                    tds = row.find_all("td")
                    if len(tds) >= 5:
                        name_raw = tds[1].get_text(strip=True)
                        name = re.sub(r"^#\d+\s*", "", name_raw).strip()
                        assists = tds[2].get_text(strip=True)
                        goals = tds[3].get_text(strip=True)
                        total = tds[4].get_text(strip=True)
                        
                        player = {
                            "name": name,
                            "assists": int(assists) if assists.isdigit() else 0,
                            "goals": int(goals) if goals.isdigit() else 0,
                            "total": int(total) if total.isdigit() else 0,
                        }
                        
                        if is_home:
                            home_players.append(player)
                        else:
                            away_players.append(player)
        
        # Old format: table with caption (for pre-2015 games)
        if not home_players and not away_players:
            tables = soup.find_all("table")
            for table in tables:
                caption = table.find("caption")
                if not caption:
                    continue
                
                # Skip tables that don't contain player stats (e.g., navigation tables)
                # Also skip cumulative stats tables that contain players from both teams
                rows_check = table.find_all("tr")
                player_count = 0
                for row_check in rows_check[1:]:
                    tds_check = row_check.find_all("td")
                    if len(tds_check) >= 5:
                        first_cell = tds_check[0].get_text(strip=True)
                        second_cell = tds_check[1].get_text(strip=True)
                        if re.match(r"^\d+$", first_cell) and second_cell and " - " not in first_cell:
                            player_count += 1
                # Cumulative stats tables have many more rows (navigation + both teams)
                # A single-team roster table typically has 5-15 players + 1 header = 6-16 rows
                if player_count == 0 or player_count > 15 or len(rows_check) > 20:
                    continue
                
                team = caption.get_text(strip=True)
                if team == home_team:
                    is_home = True
                elif team == away_team:
                    is_home = False
                else:
                    continue
                
                rows = table.find_all("tr")
                for row in rows[1:]:
                    tds = row.find_all("td")
                    if len(tds) >= 5:
                        name_raw = tds[1].get_text(strip=True)
                        name = re.sub(r"^\d+\s*", "", name_raw).strip()
                        if not name:
                            continue
                        # Old format: columns are [jersey, name, goals, assists, total]
                        goals_raw = tds[2].get_text(strip=True)
                        assists_raw = tds[3].get_text(strip=True)
                        
                        goals = 0
                        if goals_raw:
                            gm = re.search(r"([\d.]+)\s*goals", goals_raw)
                            if gm:
                                goals = int(float(gm.group(1)))
                            else:
                                try:
                                    goals = int(float(goals_raw))
                                except ValueError:
                                    pass
                        
                        assists = 0
                        if assists_raw:
                            am = re.search(r"([\d.]+)\s*assists", assists_raw)
                            if am:
                                assists = int(float(am.group(1)))
                            else:
                                try:
                                    assists = int(float(assists_raw))
                                except ValueError:
                                    pass
                        
                        player = {
                            "name": name,
                            "assists": assists,
                            "goals": goals,
                            "total": 0,
                        }
                        
                        if is_home:
                            home_players.append(player)
                        else:
                            away_players.append(player)
        
        # Build gameplay object
        gameplay = {
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "points": points,
            "home_players": home_players,
            "away_players": away_players,
        }
        
        # Build match result
        match = {
            "game_id": str(gid),
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "season_id": game["season_id"],
            "gameplay": gameplay,
        }
        
        matches.append(match)
        print(f"    Added game {gid} ({len(points)} points)")
        
        time.sleep(0.5)  # Be respectful
        
    except Exception as e:
        print(f"    Error fetching game {gid}: {e}")

# Save updated match_results.json
with open("/home/teemu/repos/otso-20v-gaala/data/processed/match_results.json", "w") as f:
    json.dump(matches, f, indent=2, ensure_ascii=False)

print(f"\nSaved match_results.json with {len(matches)} total games")
