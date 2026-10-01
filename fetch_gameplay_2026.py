#!/usr/bin/env python3
"""Fetch gameplay data for new KESA2026 games and update match_results.json."""
import requests
import json
import re
from bs4 import BeautifulSoup
from pathlib import Path

BASE_URL = "https://ultimate.fi/pelikone"
headers = {"User-Agent": "Otso20v-Gaala-DataBot/1.0"}

# New game IDs to fetch
new_game_ids = [11084, 11083, 11085, 11086, 11087, 11111]

# Load existing match_results.json
with open("/home/teemu/repos/otso-20v-gaala/data/processed/match_results.json") as f:
    matches = json.load(f)

existing_ids = {m["game_id"] for m in matches}
new_to_add = [gid for gid in new_game_ids if str(gid) not in existing_ids]
print(f"Games to add: {len(new_to_add)}")

for gid in new_to_add:
    game_url = f"{BASE_URL}/?view=gameplay&game={gid}"
    print(f"\nFetching game {gid}...")
    resp = requests.get(game_url, headers=headers, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Get game info from title
    title = soup.find("h1")
    title_text = title.get_text(strip=True) if title else ""
    print(f"  Title: {title_text}")
    
    # Extract score from title
    score_match = re.search(r'(\d+)\s*[-–—]\s*(\d+)', title_text)
    home_score = away_score = 0
    if score_match:
        home_score, away_score = int(score_match.group(1)), int(score_match.group(2))
    
    # Get teams from title (format: "Home - Away score")
    teams_match = re.match(r'^(.+?)\s+[-–—]\s+(.+?)\s+\d+\s+[-–—]\s+\d+$', title_text)
    home_team = away_team = ""
    if teams_match:
        home_team = teams_match.group(1).strip()
        away_team = teams_match.group(2).strip()
    
    # Get points table
    tables = soup.find_all("table")
    points_table = None
    for table in tables:
        first_row = table.find_all(["td", "th"])
        if first_row and "Pisteet" in first_row[0].get_text():
            points_table = table
            break
    
    if not points_table:
        print(f"  Warning: No points table found for game {gid}")
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
            
            # Extract player names (remove jersey numbers)
            scorer = re.sub(r'^#\d+\s*', '', scorer_raw).strip()
            assist = re.sub(r'^#\d+\s*', '', assist_raw).strip()
            
            # Determine side (home/away) from score
            side = "home" if score.startswith(score.split("-")[0]) else "guest"
            # Actually, we need to determine this from the game context
            # For now, just mark based on whether the first score matches home_score
            score_parts = score.split("-")
            if len(score_parts) == 2:
                first_score = int(score_parts[0])
                second_score = int(score_parts[1])
                if first_score <= second_score:
                    side = "home" if first_score <= home_score else "guest"
                else:
                    side = "guest"
            
            points.append({
                "type": "point",
                "side": side,
                "title": f"{time_str} {score} {scorer} -> {assist}",
                "time": time_str,
                "score": score,
                "scorer": scorer,
                "assist": assist,
            })
    
    print(f"  Found {len(points)} points")
    
    # Get player rosters from scoreboards
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
            
            # Parse player rows
            rows = sb.find_all("tr")
            for row in rows[1:]:  # Skip header
                tds = row.find_all("td")
                if len(tds) >= 5:
                    name_raw = tds[1].get_text(strip=True)
                    name = re.sub(r'^#\d+\s*', '', name_raw).strip()
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
        "season_id": "KESA2026",
        "gameplay": gameplay,
    }
    
    matches.append(match)
    print(f"  Added game {gid} to match_results.json")

# Save updated match_results.json
with open("/home/teemu/repos/otso-20v-gaala/data/processed/match_results.json", "w") as f:
    json.dump(matches, f, indent=2, ensure_ascii=False)

print(f"\nSaved match_results.json with {len(matches)} total games")
