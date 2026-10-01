#!/usr/bin/env python3
"""Fetch latest KESA2026 Otso games from pelikone.fi."""
import requests
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

BASE_URL = "https://ultimate.fi/pelikone"
headers = {"User-Agent": "Otso20v-Gaala-DataBot/1.0"}

# Fetch games page for KESA2026
games_url = f"{BASE_URL}/?view=games&season=KESA2026&filter=tournaments&group=all"
print(f"Fetching {games_url}...")
resp = requests.get(games_url, headers=headers, timeout=30)
resp.raise_for_status()
soup = BeautifulSoup(resp.text, "html.parser")

# Find Otso games
games = []
for span in soup.find_all("span", string=lambda text: text and "Otso" in text):
    row = span.find_parent("tr")
    if row:
        cells = row.find_all(["td", "th"])
        if len(cells) >= 12:
            # Find the 'Pelin kulku' link in cell 11
            cell11 = cells[11]
            link = cell11.find("a")
            if link and "game=" in link.get("href", ""):
                game_id = int(re.search(r"game=(\d+)", link["href"]).group(1))
                games.append({
                    "game_id": game_id,
                    "time": cells[0].get_text(strip=True),
                    "venue": cells[1].get_text(strip=True),
                    "home": cells[2].get_text(strip=True),
                    "away": cells[4].get_text(strip=True),
                    "home_score": int(cells[5].get_text(strip=True)),
                    "away_score": int(cells[7].get_text(strip=True)),
                })

print(f"Found {len(games)} Otso games in KESA2026")
for g in games:
    print(f"  {g['time']} {g['home']} {g['home_score']}-{g['away_score']} {g['away']} (game={g['game_id']})")

# Load existing KESA2026.json
raw_dir = Path("/home/teemu/repos/otso-20v-gaala/data/raw")
kesa_file = raw_dir / "KESA2026.json"
if kesa_file.exists():
    with open(kesa_file) as f:
        existing = json.load(f)
    
    # Update Otso team games
    for team in existing.get("teams", []):
        if team.get("name") == "Otso":
            # Get existing game keys
            existing_keys = {(g.get("home"), g.get("away"), g.get("home_score"), g.get("away_score")) 
                           for g in team.get("games", [])}
            
            # Add new games
            new_count = 0
            for g in games:
                key = (g["home"], g["away"], g["home_score"], g["away_score"])
                if key not in existing_keys:
                    team["games"].append(g)
                    existing_keys.add(key)
                    new_count += 1
            
            print(f"Updated Otso team: {len(team['games'])} total games ({new_count} new)")
            break
else:
    existing = {
        "id": "KESA2026",
        "name": "Kesä 2026",
        "classified": "summer",
        "teams": [{
            "name": "Otso",
            "games": games
        }],
        "placements": [],
        "players": [],
        "games": [],
        "results": [],
    }

# Save
with open(kesa_file, "w") as f:
    json.dump(existing, f, indent=2, ensure_ascii=False)

print(f"Saved to {kesa_file}")
