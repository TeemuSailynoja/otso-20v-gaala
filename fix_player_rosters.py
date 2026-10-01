#!/usr/bin/env python3
"""Re-fetch player rosters for games that are missing them."""
import requests
import json
import re
import time
from bs4 import BeautifulSoup

BASE_URL = "https://ultimate.fi/pelikone"
headers = {"User-Agent": "Otso20v-Gaala-DataBot/1.0"}

# Load match_results.json
with open("/home/teemu/repos/otso-20v-gaala/data/processed/match_results.json") as f:
    matches = json.load(f)

# Find games without player rosters or with unreasonable player counts
games_to_fix = []
for m in matches:
    gp = m.get("gameplay", {})
    home_players = gp.get("home_players", [])
    away_players = gp.get("away_players", [])
    # Re-fetch if no rosters OR if either team has more than 15 players (indicates cumulative stats bug)
    if not home_players and not away_players:
        games_to_fix.append(m)
    elif len(home_players) > 15 or len(away_players) > 15:
        print(f"  Re-fixing game {m['game_id']}: home={len(home_players)}, away={len(away_players)}")
        games_to_fix.append(m)

print(f"Games to fix: {len(games_to_fix)}")

def is_player_table(table, home_team, away_team):
    """Check if a table contains player stats for a single team (not cumulative stats).
    
    Cumulative stats tables contain players from BOTH teams under the same caption,
    while actual player roster tables contain only one team's players.
    """
    rows = table.find_all("tr")
    found_home = False
    found_away = False
    
    for row in rows[1:]:  # Skip header
        tds = row.find_all("td")
        if len(tds) >= 5:
            first_cell = tds[0].get_text(strip=True)
            second_cell = tds[1].get_text(strip=True)
            # Player rows have jersey numbers in first cell and names in second
            if re.match(r"^\d+$", first_cell) and second_cell:
                # Check if this looks like a cumulative stats entry (has score in first cell)
                # Cumulative stats rows have format like "1 - 0" in first cell
                if " - " in first_cell:
                    continue
                # This is a player row - check which team it belongs to
                # We can't determine team from the table alone, but we can check
                # if the table has players from both teams
                found_home = True  # Assume home for now
    
    # A single-team roster table should have a reasonable number of players (5-15)
    # Cumulative stats tables have many more (both teams combined) AND many more rows
    player_count = sum(1 for row in rows[1:] for tds in [row.find_all("td")] if len(tds) >= 5 and re.match(r"^\d+$", tds[0].get_text(strip=True)) and tds[1].get_text(strip=True) and " - " not in tds[0].get_text(strip=True))
    # Cumulative stats tables have many more rows (navigation + both teams)
    # A single-team roster table typically has 5-15 players + 1 header = 6-16 rows
    if len(rows) > 20:
        return False
    return player_count <= 15

def parse_players_from_tables(soup, home_team, away_team):
    """Parse player rosters from table captions (old format)."""
    home_players = []
    away_players = []
    
    tables = soup.find_all("table")
    for table in tables:
        caption = table.find("caption")
        if not caption:
            continue
        
        # Skip tables that don't contain player stats (e.g., navigation tables)
        if not is_player_table(table, home_team, away_team):
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
    
    return home_players, away_players

def parse_players_from_scoreboards(soup, home_team, away_team):
    """Parse player rosters from div.gameplay-scoreboard (modern format)."""
    home_players = []
    away_players = []
    
    scoreboards = soup.find_all("div", class_="gameplay-scoreboard")
    for sb in scoreboards:
        team_name = sb.find("span", class_="gameplay-team-name")
        if team_name:
            team = team_name.get_text(strip=True)
            if team == home_team:
                is_home = True
            elif team == away_team:
                is_home = False
            else:
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
    
    return home_players, away_players

# Re-fetch player rosters
for i, match in enumerate(games_to_fix):
    gid = match["game_id"]
    game_url = f"{BASE_URL}/?view=gameplay&game={gid}"
    print(f"[{i+1}/{len(games_to_fix)}] Fetching game {gid}...")
    
    try:
        resp = requests.get(game_url, headers=headers, timeout=30)
        if resp.status_code != 200:
            print(f"  Skipping {gid}: HTTP {resp.status_code}")
            continue
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Get teams from match
        home_team = match["home_team"]
        away_team = match["away_team"]
        
        # Try modern format first
        home_players, away_players = parse_players_from_scoreboards(soup, home_team, away_team)
        
        # Fall back to old format
        if not home_players and not away_players:
            home_players, away_players = parse_players_from_tables(soup, home_team, away_team)
        
        if home_players or away_players:
            match["gameplay"]["home_players"] = home_players
            match["gameplay"]["away_players"] = away_players
            print(f"  Added {len(home_players)} home, {len(away_players)} away players")
        else:
            print(f"  Warning: No players found for game {gid}")
        
        time.sleep(0.5)
        
    except Exception as e:
        print(f"  Error fetching game {gid}: {e}")

# Save updated match_results.json
with open("/home/teemu/repos/otso-20v-gaala/data/processed/match_results.json", "w") as f:
    json.dump(matches, f, indent=2, ensure_ascii=False)

# Count remaining games without rosters
remaining = sum(1 for m in matches if not m.get("gameplay", {}).get("home_players") and not m.get("gameplay", {}).get("away_players"))
print(f"\nSaved match_results.json")
print(f"Games still without rosters: {remaining}")
