#!/usr/bin/env python3
"""
Build site data for Otso 20v gaala website.

Reads raw scraped data and gameplay data, produces JSON files for the static site:
  site_data/players.json     — per-player stats
  site_data/pass_network.json — directed pass connections
  site_data/cooccurrence.json — undirected co-occurrence matrix
  site_data/summary.json     — aggregate stats for landing page
  site_data/years.json       — year-by-year evolution data
  site_data/trophies.json    — season-level gold/silver/bronze record
"""

import json
import os
import re
import sys
import csv
import glob
import hashlib
import unicodedata
from datetime import date
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "data" / "raw"
GAMEPLAY_FILE = BASE_DIR / "data" / "processed" / "match_results.json"
SITE_DATA_DIR = BASE_DIR / "site_data"

# Load season mapping for type filtering
SEASON_MAPPING_FILE = SITE_DATA_DIR / "season_mapping.json"
with open(SEASON_MAPPING_FILE) as _f:
    SEASON_MAPPING = json.load(_f)


def normalize_name(name: str) -> str:
    """Normalize player name: strip whitespace, replace non-breaking spaces,
    and sort name parts so 'Lastname Firstname' and 'Firstname Lastname' match.
    
    Strategy: if the name has 2+ parts, try both orderings and pick the one
    that matches a known player. For unknown names, default to first-last order.
    """
    name = name.replace('\xa0', ' ').strip()
    if not name:
        return name
    parts = [p for p in name.split() if p]
    if len(parts) <= 1:
        return name
    # Check if this is "Lastname Firstname" by checking against known patterns
    # Most Finnish names are "Firstname Lastname" or "Firstname Middlename Lastname"
    # Pelikone points use "Lastname Firstname" format
    # We'll normalize to "Firstname Lastname" by checking if the reverse order
    # is more common (but we don't know yet). Safer approach: just keep as-is
    # and match by checking both orderings.
    return name


def is_otso_team(name: str) -> bool:
    """Check if a team name belongs to Otso main/2/3/Grizzly/Polar/Hukka/Karhuvaarit (excludes Akatemia)."""
    lower = name.lower()
    if "akatemia" in lower:
        return False
    return any(t in lower for t in ["otso", "grizzly", "polar", "hukka", "karhuvaarit"])


def is_otso_akatemia(name: str) -> bool:
    """Check if a team name is Otso Akatemia (not UFO Akatemia)."""
    lower = name.lower()
    return "akatemia" in lower and "otso" in lower


def _is_main_otso_team(name: str) -> bool:
    """Check if a team name is the main Otso team (Otso, Otso1, Otso Grizzly, Otso Polar).
    
    Excludes: Otso 2, Otso 3, Hukka, Karhuvaarit, Akatemia.
    """
    lower = name.lower()
    no_space = lower.replace(" ", "").replace("-", "")
    
    # Main Otso variants
    if no_space in ["otso", "otso1", "otso1", "otsogrizzly", "otsog", "otso polar", "otsop"]:
        return True
    
    # Also check for "Otso Grizzly" and "Otso Polar" with spaces
    if "otso grizzly" in lower or "otso polar" in lower:
        return True
    
    return False


def canonicalize_team_name(name: str) -> str:
    """Canonicalize team names to a consistent format.
    
    Maps variants like 'OTSO 2', 'Otso 2', 'Otso2' → 'Otso 2'
    Also handles scraping artifacts like 'Terror - Otso 2' → 'Otso 2'.
    """
    lower = name.strip().lower()
    # Remove spaces to normalize 'Otso 2' vs 'Otso2'
    no_space = lower.replace(' ', '')
    
    # Handle scraping artifacts: 'X - Otso Y' → 'Otso Y'
    if ' - otso ' in lower or ' - otso' in lower:
        # Extract the Otso part after the dash
        parts = lower.split(' - otso', 1)
        if len(parts) == 2:
            rest = parts[1].strip()
            if rest == '':
                return 'Otso'
            elif rest == '2':
                return 'Otso 2'
            elif rest == '3':
                return 'Otso 3'
            elif rest == '1':
                return 'Otso 1'
            elif rest == 'grizzly':
                return 'Otso Grizzly'
            elif rest == 'polar':
                return 'Otso Polar'
            elif rest == 'akatemia':
                return 'Otso Akatemia'
            else:
                return 'Otso'  # Default fallback
    
    # Map to canonical names
    if no_space == 'otso':
        return 'Otso'
    elif no_space == 'otso2':
        return 'Otso 2'
    elif no_space == 'otso3':
        return 'Otso 3'
    elif no_space == 'otso1':
        return 'Otso 1'
    elif 'grizzly' in lower:
        return 'Otso Grizzly'
    elif 'polar' in lower:
        return 'Otso Polar'
    elif 'hukka' in lower:
        return 'Hukka'
    elif 'karhuvaarit' in lower:
        return 'Karhuvaarit'
    elif 'akatemia' in lower and 'otso' in lower:
        return 'Otso Akatemia'
    elif 'akatemia' in lower:
        return name  # Keep as-is (e.g., UFO Akatemia)
    else:
        return name  # Unknown team, keep as-is


def extract_year_from_season_id(season_id: str) -> int | None:
    """Extract year from season ID like '2025.1', 'KESA2026', 'Talvi2016', 'Hallitour2', etc."""
    # Direct year pattern
    for part in season_id.split("."):
        if part.isdigit() and len(part) == 4:
            return int(part)
    # KESAYYYY
    if season_id.startswith("KESA") and season_id[4:].isdigit():
        return int(season_id[4:])
    # TALVIyyyy
    if season_id.startswith("Talvi") and season_id[5:].isdigit():
        return int(season_id[5:])
    # BEACHyyyy (skip beach - Otso didn't play)
    if season_id.startswith("BEACH") and season_id[5:].isdigit():
        return int(season_id[5:])
    # SMyyyy, XSMyyyy, MSMyyyy, OSMyyyy (also handle suffixes like SM2022K)
    for prefix in ["SM", "XSM", "MSM", "OSM"]:
        if season_id.startswith(prefix) and len(season_id) > len(prefix):
            rest = season_id[len(prefix):]
            # Extract leading digits (ignore trailing letters like K)
            digits = ''.join(c for c in rest if c.isdigit())
            if digits and len(digits) == 4:
                y = int(digits)
                return y if y >= 2006 else None
    # JSMyyyy
    if season_id.startswith("JSM") and season_id[3:].isdigit():
        y = int(season_id[3:])
        return y if y >= 2006 else None
    # *JSMyyyy
    if season_id.startswith("*JSM") and season_id[4:].isdigit():
        y = int(season_id[4:])
        return y if y >= 2006 else None
    # HallitourN -> look up in mapping for year
    if season_id.startswith("Hallitour"):
        mapping_info = SEASON_MAPPING.get(season_id, {})
        name = mapping_info.get("name", "")
        # Extract year from name like "Talvi 2014JoukkueetPelatut"
        import re
        match = re.search(r'(\d{4})', name)
        if match:
            return int(match.group(1))
    # BMSMyyyy (handle truncated like BMSM2)
    if season_id.startswith("BMSM") and len(season_id) > 4:
        suffix = season_id[4:]
        if suffix.isdigit():
            y = int(suffix)
            if y >= 2006:
                return y
            elif y >= 10:
                return 1900 + y  # 10-99 → 1910-1999
            else:
                return 2000 + y  # 0-9 → 2000-2009
    # Hallitouryyyy (handle truncated like Hallitour2)
    if season_id.startswith("Hallitour") and len(season_id) > 9:
        suffix = season_id[9:]
        if suffix.isdigit():
            y = int(suffix)
            if y >= 2006:
                return y
            elif y >= 10:
                return 1900 + y
            else:
                # Hallitour2 is from 2016 (context: Talvi2016 exists)
                return 2016
    return None


def normalize_season_id(season_id: str, season_type_map: dict) -> str:
    """Normalize a season ID to its base season for counting unique seasons.
    
    Strips tour/final suffixes (.T1-.T4, .F, .Finaa, .1F) to get the base season.
    Uses the season_type_map to determine if a season is summer or winter.
    
    Every year has ONE summer season and ONE winter season. Tours and Finals
    are part of the main season, not separate.
    
    Examples:
        '2011.1.T1' -> '2011.1' (summer tour -> summer)
        '2012.T4' -> '2012' (summer tour -> summer, year-only)
        '2016.1.F' -> '2016.1' (summer final -> summer)
        '2012' -> '2012' (summer, year-only kept as-is)
        '2007.2' -> '2007.2' (winter, kept distinct from summer .1)
        '2014.3' -> '2014.3' (winter, kept distinct from summer .1)
        'Hallitour2' -> 'Hallitour2' (winter, kept distinct)
        'Talvi2016' -> 'Talvi2016' (winter, kept distinct)
    """
    # Strip tour suffixes: .T1, .T2, .T3, .T4
    season_id = re.sub(r'\.T[1-4]$', '', season_id)
    # Strip final suffixes: .F, .Finaa, .1F, .Finaa
    season_id = re.sub(r'\.Finaa$', '', season_id)
    season_id = re.sub(r'\.1F$', '', season_id)
    season_id = re.sub(r'\.F$', '', season_id)
    
    return season_id


def load_raw_data() -> list[dict]:
    """Load all raw season JSON files."""
    all_data = []
    for f in sorted(glob.glob(str(RAW_DIR / "*.json"))):
        with open(f) as fh:
            data = json.load(fh)
        if isinstance(data, dict) and "teams" in data:
            all_data.append(data)
    return all_data


def load_gameplay() -> list[dict]:
    """Load match_results.json."""
    with open(GAMEPLAY_FILE) as f:
        return json.load(f)


def canonicalize_name(name: str) -> str:
    """Normalize a player name to a canonical form (case-insensitive).
    
    Strategy: prefer the order that appears most often. For now, we'll use
    alphabetical order of parts as a stable canonical form, then resolve
    to a human-readable form at the end.
    
    Strips captain notation '(c)' from names before processing.
    """
    name = normalize_name(name)
    # Strip captain notation
    name = name.replace('(c)', '').replace('(C)', '').strip()
    parts = [p for p in name.split() if p]
    if not parts:
        return name
    # Use sorted lowercase parts as canonical key (case-insensitive dedup)
    return " ".join(sorted(p.lower() for p in parts))


def build_players(raw_data: list[dict], gameplay: list[dict]) -> dict:
    """Build per-player stats from raw data + gameplay.
    
    Deduplicates names like 'Sandberg Tomi' and 'Tomi Sandberg'.
    Returns dict: {canonical_key: {seasons, years, first_year, last_year, 
                                   games_played, goals, assists, total, teams,
                                   display_name}}
    """
    # Use canonical keys (sorted name parts) internally
    players = {}
    # Track display name preference (most common order)
    name_order_count = defaultdict(int)
    # Load season list page mapping as primary source of truth
    # This was created by reading the actual season list page structure
    mapping_file = BASE_DIR / "site_data" / "season_mapping.json"
    page_mapping = {}
    if mapping_file.exists():
        with open(mapping_file) as f:
            page_mapping = json.load(f)
    
    # Build fallback season_type_map from raw data for seasons not in page mapping
    season_type_map = {}
    for season_data in raw_data:
        sid = season_data.get("id", "")
        classified = season_data.get("classified", {})
        if isinstance(classified, dict):
            stype = classified.get("type", "unknown")
            season_type_map[sid] = stype
    
    def add_player(raw_name: str, season_id: str, year: int, team_name: str, 
                   games: int, goals: int, assists: int):
        """Add a player entry, merging with existing if name matches."""
        canonical = canonicalize_name(raw_name)
        if not canonical:
            return
        
        # Track name order for display name
        parts = [p for p in normalize_name(raw_name).split() if p]
        if len(parts) >= 2:
            name_order_count[" ".join(parts)] += 1
        
        if canonical not in players:
            players[canonical] = {
                "seasons": [],
                "years": set(),
                "season_types": {"summer": set(), "winter": set(), "other": set()},
                "season_count": 0,
                "first_year": year,
                "last_year": year,
                "games": 0,
                "goals": 0,
                "assists": 0,
                "total": 0,
                "teams": set(),
                "summer_games": 0,
                "summer_goals": 0,
                "summer_assists": 0,
                "winter_games": 0,
                "winter_goals": 0,
                "winter_assists": 0,
            }
        
        p = players[canonical]
        # Track unique season IDs for display
        if season_id not in p["seasons"]:
            p["seasons"].append(season_id)
        p["years"].add(year)
        # Track season type - use page_mapping as primary source of truth
        normalized_for_lookup = normalize_season_id(season_id, season_type_map)
        # Try normalized ID in page mapping first, then raw ID, then fallback map
        stype = (page_mapping.get(normalized_for_lookup, {}).get("type") or
                 page_mapping.get(season_id, {}).get("type") or
                 season_type_map.get(season_id, "unknown"))
        
        # Track summer/winter stats
        if stype == "summer":
            p["summer_games"] += games
            p["summer_goals"] += goals
            p["summer_assists"] += assists
            p["season_types"]["summer"].add(year)
        elif stype == "winter":
            p["winter_games"] += games
            p["winter_goals"] += goals
            p["winter_assists"] += assists
            p["season_types"]["winter"].add(year)
        else:
            p["season_types"]["other"].add(year)
        p["teams"].add(team_name)
        
        if year < p["first_year"]:
            p["first_year"] = year
        if year > p["last_year"]:
            p["last_year"] = year
        
        p["games"] += games
        p["goals"] += goals
        p["assists"] += assists
    
    # Phase 1: Build from raw team card data
    for season_data in raw_data:
        season_id = season_data.get("id", "")
        year = extract_year_from_season_id(season_id)
        if not year:
            continue
        
        for team in season_data.get("teams", []):
            if not is_otso_team(team.get("name", "")):
                continue
            
            for p in team.get("players", []):
                raw_name = p.get("name", "")
                if not raw_name:
                    continue
                
                try:
                    g = int(p.get("games", 0))
                    gl = int(p.get("goals", 0))
                    a = int(p.get("assists", 0))
                except (ValueError, TypeError):
                    g, gl, a = 0, 0, 0
                
                add_player(raw_name, season_id, year, canonicalize_team_name(team.get("name", "")), g, gl, a)
    
    # Phase 2: Enrich with gameplay roster appearances and count games
    for game in gameplay:
        gp = game.get("gameplay")
        if not gp:
            continue
        
        season_id = game.get("season_id", "")
        year = extract_year_from_season_id(season_id)
        
        home_is_otso = is_otso_team(gp.get("home_team", ""))
        away_is_otso = is_otso_team(gp.get("away_team", ""))
        home_is_otso_akatemia = is_otso_akatemia(gp.get("home_team", ""))
        away_is_otso_akatemia = is_otso_akatemia(gp.get("away_team", ""))
        
        # Collect Otso players from the roster for this game (main + Akatemia)
        otso_canonicals = set()
        for p in gp.get("home_players", []):
            if home_is_otso or home_is_otso_akatemia:
                name = normalize_name(p.get("name", ""))
                if name:
                    canon = canonicalize_name(name)
                    if canon:
                        otso_canonicals.add(canon)
        for p in gp.get("away_players", []):
            if away_is_otso or away_is_otso_akatemia:
                name = normalize_name(p.get("name", ""))
                if name:
                    canon = canonicalize_name(name)
                    if canon:
                        otso_canonicals.add(canon)
        
        # Count games for Otso players who appeared in the roster
        for canon in otso_canonicals:
            if canon in players:
                players[canon]["games"] += 1
                # Increment summer/winter games
                if season_id in season_type_map:
                    stype = season_type_map[season_id]
                else:
                    normalized_for_lookup = normalize_season_id(season_id, season_type_map)
                    stype = (page_mapping.get(normalized_for_lookup, {}).get("type") or
                             page_mapping.get(season_id, {}).get("type") or
                             season_type_map.get(season_id, "unknown"))
                if stype == "summer":
                    players[canon]["summer_games"] += 1
                elif stype == "winter":
                    players[canon]["winter_games"] += 1
                # Add team if this player appeared for a different team (e.g., Hukka)
                player_team = ""
                if home_is_otso:
                    player_team = canonicalize_team_name(gp.get("home_team", ""))
                elif away_is_otso:
                    player_team = canonicalize_team_name(gp.get("away_team", ""))
                if player_team:
                    players[canon]["teams"].add(player_team)
        
        # Add new Otso players from roster who weren't in raw data
        for canon in otso_canonicals:
            if canon not in players:
                # Determine which team this player belongs to
                player_team = ""
                if home_is_otso:
                    player_team = canonicalize_team_name(gp.get("home_team", ""))
                elif away_is_otso:
                    player_team = canonicalize_team_name(gp.get("away_team", ""))
                
                # Determine season type for this game
                normalized_for_lookup = normalize_season_id(season_id, season_type_map)
                stype = (page_mapping.get(normalized_for_lookup, {}).get("type") or
                         page_mapping.get(season_id, {}).get("type") or
                         season_type_map.get(season_id, "unknown"))
                
                p = {
                    "seasons": [],
                    "years": set(),
                    "season_types": {"summer": set(), "winter": set(), "other": set()},
                    "season_count": 0,
                    "first_year": year if year else 2006,
                    "last_year": year if year else 2006,
                    "games": 1,
                    "goals": 0,
                    "assists": 0,
                    "total": 0,
                    "teams": {player_team} if player_team else set(),
                    "summer_games": 1 if stype == "summer" else 0,
                    "summer_goals": 0,
                    "summer_assists": 0,
                    "winter_games": 1 if stype == "winter" else 0,
                    "winter_goals": 0,
                    "winter_assists": 0,
                }
                if stype == "summer":
                    p["season_types"]["summer"].add(year if year else 2006)
                elif stype == "winter":
                    p["season_types"]["winter"].add(year if year else 2006)
                else:
                    p["season_types"]["other"].add(year if year else 2006)
                players[canon] = p
                # Track season and year (same logic as Phase 1's add_player)
                if season_id:
                    p["seasons"].append(season_id)
                if year:
                    p["years"].add(year)
                    normalized_for_lookup = normalize_season_id(season_id, season_type_map)
                    stype = (page_mapping.get(normalized_for_lookup, {}).get("type") or
                             page_mapping.get(season_id, {}).get("type") or
                             season_type_map.get(season_id, "unknown"))
                    if stype == "winter":
                        p["season_types"]["winter"].add(year)
                    elif stype == "summer":
                        p["season_types"]["summer"].add(year)
                    else:
                        p["season_types"]["other"].add(year)
    
    # Merge known name duplicates (case-insensitive dedup already handles most)
    # Touko Väänänen / Touko aukusti Väänänen — same person, different middle name
    touko_canon = canonicalize_name("Touko Väänänen")
    touko_aukusti_canon = canonicalize_name("Touko aukusti Väänänen")
    if touko_aukusti_canon in players and touko_canon in players:
        # Merge aukusti into main Touko
        main = players[touko_canon]
        aukusti = players[touko_aukusti_canon]
        main["seasons"].extend(aukusti["seasons"])
        main["years"].update(aukusti["years"])
        main["games"] += aukusti["games"]
        main["goals"] += aukusti["goals"]
        main["assists"] += aukusti["assists"]
        main["teams"].update(aukusti["teams"])
        main["first_year"] = min(main["first_year"], aukusti["first_year"])
        main["last_year"] = max(main["last_year"], aukusti["last_year"])
        del players[touko_aukusti_canon]
    
    # Manual display name overrides for names that title() can't handle
    display_overrides = {
        canonicalize_name("euramo sisu"): "Euramo Sisu",
        canonicalize_name("iivo laaksonen"): "Iivo Laaksonen",
        canonicalize_name("lacy theo"): "Lacy Theo",
        canonicalize_name("abhinav omprakash naik"): "Abhinav Omprakash Naik",
        canonicalize_name("clemens jonas hellmig"): "Clemens Jonas Hellmig",
        canonicalize_name("samuel-visal roeung"): "Samuel-Visal Roeung",
        canonicalize_name("šimon kadlec"): "Šimon Kadlec",
    }
    
    # Convert sets to sorted lists for JSON, pick best display name.
    # Sorted by display name so the output is byte-stable across runs.
    result = {}
    for canonical, p in sorted(players.items()):
        # Collect all observed names for this canonical key
        candidate_names = [name for name in name_order_count.keys() 
                          if canonicalize_name(name) == canonical]
        # Prefer properly capitalized names (title case)
        display = None
        # Check for manual override first
        if canonical in display_overrides:
            display = display_overrides[canonical]
        elif candidate_names:
            for name in candidate_names:
                if name == name.title():
                    display = name
                    break
            if display is None:
                # Fallback: use the most frequently observed name
                display = max(candidate_names, key=lambda n: name_order_count.get(n, 0))
        if display is None:
            display = canonical
        
        result[display] = {
            "seasons": sorted(p["seasons"]),
            "season_count": len(p["season_types"]["summer"]) + len(p["season_types"]["winter"]),
            "years": sorted(p["years"]),
            "year_count": len(p["years"]),
            "first_year": p["first_year"],
            "last_year": p["last_year"],
            "games": p["games"],
            "goals": p["goals"],
            "assists": p["assists"],
            "total": p["goals"] + p["assists"],
            "teams": sorted(p["teams"]),
            "season_types": {
                "summer": sorted(p["season_types"]["summer"]),
                "winter": sorted(p["season_types"]["winter"]),
                "other": sorted(p["season_types"]["other"]),
            },
            # Summer/winter split
            "summer_games": p["summer_games"],
            "summer_goals": p["summer_goals"],
            "summer_assists": p["summer_assists"],
            "winter_games": p["winter_games"],
            "winter_goals": p["winter_goals"],
            "winter_assists": p["winter_assists"],
            # Defense stats (will be merged later)
            "defense_points": 0,
            "offense_points": 0,
            "total_points": 0,
        }
    
    return result


def build_pass_network(gameplay: list[dict], players: dict) -> dict:
    """Build directed pass network from gameplay points.

    A point carries "passer" (pelikone column Syöttäjä) and "scorer" (column
    Maali); see migrate_point_fields.py for why those names were swapped in the
    scraped data before 2026-10. network[scorer][passer] = times passer fed
    scorer.

    Returns: {player: {other: count, ...}, ...}
    """
    # Build reverse map: canonical_key → display_name
    canon_to_display = {}
    for name in players:
        canon = canonicalize_name(name)
        if canon not in canon_to_display:
            canon_to_display[canon] = name
    
    network = defaultdict(lambda: defaultdict(int))
    
    for game in gameplay:
        gp = game.get("gameplay")
        if not gp:
            continue
        
        home_is_otso = is_otso_team(gp.get("home_team", ""))
        away_is_otso = is_otso_team(gp.get("away_team", ""))
        
        # Get canonical Otso player names in this game
        otso_canonicals = set()
        for p in gp.get("home_players", []):
            if home_is_otso:
                name = normalize_name(p.get("name", ""))
                if name:
                    canon = canonicalize_name(name)
                    if canon in canon_to_display:
                        otso_canonicals.add(canon)
        for p in gp.get("away_players", []):
            if away_is_otso:
                name = normalize_name(p.get("name", ""))
                if name:
                    canon = canonicalize_name(name)
                    if canon in canon_to_display:
                        otso_canonicals.add(canon)
        
        # Process points
        for point in gp.get("points", []):
            if point.get("type") != "point":
                continue
            raw_scorer = point.get("scorer", "")
            raw_passer = point.get("passer", "")

            scorer_canon = canonicalize_name(raw_scorer)
            passer_canon = canonicalize_name(raw_passer)

            # Only count if both players are Otso players we know
            if scorer_canon in otso_canonicals and passer_canon in otso_canonicals:
                network[scorer_canon][passer_canon] += 1
    
    # Convert to regular dicts with display names
    received = {}  # player → {other: count} = assists received from other
    given = {}     # player → {other: count} = assists given to other
    
    for canon, display_name in canon_to_display.items():
        if network[canon]:
            received[display_name] = {}
            for other_canon, count in network[canon].items():
                if other_canon in canon_to_display:
                    received[display_name][canon_to_display[other_canon]] = count
                    # Also populate the reverse (given)
                    other_display = canon_to_display[other_canon]
                    if other_display not in given:
                        given[other_display] = {}
                    given[other_display][display_name] = given[other_display].get(display_name, 0) + count
    
    return {"received": received, "given": given}


def build_cooccurrence(gameplay: list[dict], players: dict) -> dict:
    """Build undirected co-occurrence matrix from gameplay rosters.
    
    Returns: {player: {other: count, ...}}
    """
    # Build reverse map: canonical_key → display_name
    canon_to_display = {}
    for name in players:
        canon = canonicalize_name(name)
        if canon not in canon_to_display:
            canon_to_display[canon] = name
    
    cooc = defaultdict(lambda: defaultdict(int))
    
    for game in gameplay:
        gp = game.get("gameplay")
        if not gp:
            continue
        
        home_is_otso = is_otso_team(gp.get("home_team", ""))
        away_is_otso = is_otso_team(gp.get("away_team", ""))
        
        # Get canonical Otso player names
        otso_canonicals = set()
        for p in gp.get("home_players", []):
            if home_is_otso:
                name = normalize_name(p.get("name", ""))
                if name:
                    canon = canonicalize_name(name)
                    if canon in canon_to_display:
                        otso_canonicals.add(canon)
        for p in gp.get("away_players", []):
            if away_is_otso:
                name = normalize_name(p.get("name", ""))
                if name:
                    canon = canonicalize_name(name)
                    if canon in canon_to_display:
                        otso_canonicals.add(canon)
        
        # For each pair, increment count
        otso_list = sorted(otso_canonicals)
        for i in range(len(otso_list)):
            for j in range(i + 1, len(otso_list)):
                p1, p2 = otso_list[i], otso_list[j]
                cooc[p1][p2] += 1
                cooc[p2][p1] += 1
    
    # Convert to regular dicts with display names. Sort outer keys by display
    # name and inner keys by count so the JSON is byte-stable across runs —
    # set iteration order is hash-randomized, which otherwise churns the file
    # (and the cache-busting DATA_VERSION) on every rebuild.
    result = {}
    for canon, display_name in sorted(canon_to_display.items(), key=lambda kv: kv[1]):
        if cooc[canon]:
            inner = {}
            for other_canon, count in cooc[canon].items():
                if other_canon in canon_to_display:
                    inner[canon_to_display[other_canon]] = count
            result[display_name] = dict(
                sorted(inner.items(), key=lambda kv: (-kv[1], kv[0]))
            )
    
    return result


def build_summary(players: dict, pass_network: dict, cooccurrence: dict, 
                  years: dict, gameplay: list[dict]) -> dict:
    """Build aggregate stats for the landing page."""
    # Total matches
    games_with_gameplay = sum(1 for g in gameplay if g.get("gameplay"))
    
    # Total wins/losses
    wins = 0
    losses = 0
    total_goals_for = 0
    total_goals_against = 0
    
    for game in gameplay:
        gp = game.get("gameplay")
        if not gp:
            continue
        home_is_otso = is_otso_team(gp.get("home_team", ""))
        away_is_otso = is_otso_team(gp.get("away_team", ""))
        if not home_is_otso and not away_is_otso:
            continue
        
        otso_score = gp["away_score"] if away_is_otso else gp["home_score"]
        opp_score = gp["home_score"] if away_is_otso else gp["away_score"]
        
        total_goals_for += otso_score
        total_goals_against += opp_score
        if otso_score > opp_score:
            wins += 1
        elif otso_score < opp_score:
            losses += 1
    
    # Top scorers (from raw data totals)
    top_scorers = sorted(players.items(), key=lambda x: x[1]["total"], reverse=True)[:15]
    top_scorers = [{"name": n, "total": p["total"], "goals": p["goals"], 
                    "assists": p["assists"], "games": p["games"]} 
                   for n, p in top_scorers]
    
    # Top assist leaders
    top_assists = sorted(players.items(), key=lambda x: x[1]["assists"], reverse=True)[:15]
    top_assists = [{"name": n, "assists": p["assists"], "goals": p["goals"],
                    "total": p["total"], "games": p["games"]}
                   for n, p in top_assists]
    
    # Longest careers (most seasons)
    longest_careers = sorted(players.items(), key=lambda x: x[1]["season_count"], reverse=True)[:10]
    longest_careers = [{"name": n, "seasons": p["season_count"], 
                        "years": f"{p['first_year']}-{p['last_year']}",
                        "games": p["games"]}
                       for n, p in longest_careers]
    
    # Most connected (most pass connections)
    pass_conn_counts = [(n, len(neighbors)) for n, neighbors in pass_network.items() if neighbors]
    most_connected = sorted(pass_conn_counts, key=lambda x: -x[1])[:10]
    most_connected = [{"name": n, "connections": c} for n, c in most_connected]
    
    # Most teammates (most co-occurrence connections)
    cooc_conn_counts = [(n, len(neighbors)) for n, neighbors in cooccurrence.items() if neighbors]
    most_teammates = sorted(cooc_conn_counts, key=lambda x: -x[1])[:10]
    most_teammates = [{"name": n, "teammates": c} for n, c in most_teammates]
    
    # Goals per match (top 10 by rate, min 10 games)
    scored = [(n, p) for n, p in players.items() if p["games"] >= 10 and p["total"] > 0]
    goals_per_match = sorted(scored, 
                             key=lambda x: x[1]["total"] / x[1]["games"], 
                             reverse=True)[:10]
    goals_per_match = [{"name": n, "goals_per_match": round(p["total"] / p["games"], 2),
                        "total": p["total"], "games": p["games"]}
                       for n, p in goals_per_match]
    
    # Anniversary count, not a count of distinct calendar years in the data.
    # The data spans 2006-2026, but 2026 is still in progress, so counting it
    # gives 21 — wrong for a 20th anniversary gala. Full years elapsed since the
    # first season is what the milestone means.
    first_year = min(int(y) for y in years) if years else 0
    years_count = max(date.today().year - first_year, 0) if first_year else len(years)
    
    return {
        "total_matches": games_with_gameplay,
        "total_players": len(players),
        "total_wins": wins,
        "total_losses": losses,
        "total_goals_for": total_goals_for,
        "total_goals_against": total_goals_against,
        "win_percentage": int(round(wins / (wins + losses) * 100)) if (wins + losses) > 0 else 0,
        "top_scorers": top_scorers,
        "top_assists": top_assists,
        "longest_careers": longest_careers,
        "most_connected": most_connected,
        "most_teammates": most_teammates,
        "goals_per_match": goals_per_match,
        "years_count": years_count,
        "first_year": first_year,
        "current_year": date.today().year,
    }


# Personal data. Birthdays live in a gitignored file (see extract_birthdays.py)
# and only ever leave here as an aggregate: the mean age of a year's roster.
# Never write a birthday, a birth year, or a per-player age into site_data/.
BIRTHDAYS_PATH = Path(__file__).resolve().parent / "data" / "private" / "birthdays.csv"

# Age is measured at the middle of the season, not at build time — otherwise the
# 2006 squad reads as a team of 30-year-olds today.
SEASON_AGE_REF = {None: (6, 30), "summer": (7, 30), "winter": (1, 30)}


def name_key(name: str) -> tuple:
    """Order- and accent-insensitive person key.

    The scrape writes the same person as 'hotari roni' while the birthdays file
    says 'Roni Hotari'; both keys come out as ('hotari', 'roni').
    """
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return tuple(sorted(p.strip(".-").lower() for p in re.split(r"[\s\-]+", stripped) if p.strip(".-")))


def load_birthdays(path: Path = BIRTHDAYS_PATH) -> dict:
    """{name_key: date of birth} from the private CSV, or {} if it is absent.

    Absent is normal — the file never ships to a checkout, and the build simply
    omits the age stat in that case.
    """
    if not path.exists():
        return {}
    out = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            iso = (row.get("birthday") or "").strip()
            name = (row.get("name") or "").strip()
            if not name or not iso:
                continue
            try:
                out[name_key(name)] = date.fromisoformat(iso)
            except ValueError:
                continue
    return out


def age_at(bday: date, year: int, month: int, day: int) -> int:
    return (year - bday.year) - ((month, day) < (bday.month, bday.day))


def build_years(gameplay: list[dict], include_all_bears: bool = False, season_type: str = None,
                birthdays: dict = None) -> dict:
    """Build year-by-year evolution data.
    
    Args:
        gameplay: List of game data.
        include_all_bears: If True, include Otso 2, Otso 3, Hukka, Karhuvaarit, etc.
                          If False, only include main Otso team.
        season_type: If 'summer', only summer seasons. If 'winter', only winter seasons.
                    If None, include all seasons (full year).
    
    Returns: {year: {matches, wins, losses, goals_for, goals_against, roster_players,
                     roster_names, avg_age, avg_age_known}}
    """
    if birthdays is None:
        birthdays = load_birthdays()
    years = defaultdict(lambda: {
        "matches": 0, "wins": 0, "losses": 0,
        "goals_for": 0, "goals_against": 0,
        "roster_players": set(),
    })
    
    for game in gameplay:
        gp = game.get("gameplay")
        if not gp:
            continue
        
        season_id = game.get("season_id", "")
        year = extract_year_from_season_id(season_id)
        if not year:
            continue
        if year < 2006:
            year = 2006  # Otso founded 2006
        
        # Filter by season type - look up directly in season mapping
        if season_type:
            season_info = SEASON_MAPPING.get(season_id, {})
            stype = season_info.get("type", "unknown")
            if stype != season_type:
                continue
        
        home_team = gp.get("home_team", "")
        away_team = gp.get("away_team", "")
        
        if include_all_bears:
            # Include all Otso-related teams
            home_is_otso = is_otso_team(home_team) or is_otso_akatemia(home_team)
            away_is_otso = is_otso_team(away_team) or is_otso_akatemia(away_team)
        else:
            # Main Otso team: "Otso", "Otso1", "Otso Grizzly", "Otso Polar"
            # Exclude: Otso 2, Otso 3, Hukka, Karhuvaarit, Akatemia
            home_is_otso = _is_main_otso_team(home_team)
            away_is_otso = _is_main_otso_team(away_team)
        
        if not home_is_otso and not away_is_otso:
            continue
        
        years[year]["matches"] += 1
        
        otso_score = gp["away_score"] if away_is_otso else gp["home_score"]
        opp_score = gp["home_score"] if away_is_otso else gp["away_score"]
        
        years[year]["goals_for"] += otso_score
        years[year]["goals_against"] += opp_score
        if otso_score > opp_score:
            years[year]["wins"] += 1
        elif otso_score < opp_score:
            years[year]["losses"] += 1
        
        for p in gp.get("home_players", []):
            if home_is_otso:
                name = canonicalize_name(p.get("name", ""))
                if name:
                    years[year]["roster_players"].add(name)
        for p in gp.get("away_players", []):
            if away_is_otso:
                name = canonicalize_name(p.get("name", ""))
                if name:
                    years[year]["roster_players"].add(name)
    
    # Convert sets to counts
    result = {}
    ref_month, ref_day = SEASON_AGE_REF.get(season_type, (6, 30))
    for year in sorted(years.keys()):
        y = years[year]
        names = sorted(y["roster_players"])
        # Aggregate only, and honest about its basis: the birthdays file is a
        # top-scorers export, so some roster players have no recorded birthday.
        ages = [age_at(birthdays[k], int(year), ref_month, ref_day)
                for k in map(name_key, names) if k in birthdays]
        result[str(year)] = {
            "matches": y["matches"],
            "wins": y["wins"],
            "losses": y["losses"],
            "goals_for": y["goals_for"],
            "goals_against": y["goals_against"],
            "roster_players": len(names),
            # Canonicalized names of the players who appeared for this team in this
            # year — the timeline HUD cloud is seeded from exactly this roster, so it
            # must match roster_players rather than players[].years (all Otso teams).
            "roster_names": names,
            **({
                "avg_age": round(sum(ages) / len(ages), 1),
                "avg_age_known": len(ages),
            } if ages else {}),
        }
    
    return result


def build_defense_stats(gameplay: list[dict]) -> dict:
    """Build per-player defense stats from point-by-point gameplay data.
    
    For each point, determines whether Otso was on offense or defense:
    - First point: uses 'Hyökkäys' marker from HTML (team with matching class started on offense)
      Falls back to side field for older JSON data without the marker
    - Subsequent points: the scorer starts on defense for the next point
    - Halftime: resets offense to the team that started on defense in the first point
    
    Attributes defense points to specific players (Otso scored while on defense).
    
    Returns: {display_name: {defense_points, offense_points, total_points}}
    """
    from bs4 import BeautifulSoup
    
    player_stats = defaultdict(lambda: {
        'defense_points': 0,
        'defense_goals': 0,
        'defense_assists': 0,
        'offense_points': 0,
        'offense_goals': 0,
        'offense_assists': 0,
        'total_points': 0,
    })
    
    for game in gameplay:
        gp = game.get('gameplay')
        if not gp:
            continue
        
        points = gp.get('points', [])
        if not points:
            continue
        
        # Deduplicate points by score string in title
        seen_scores = set()
        unique_points = []
        for p in points:
            if p.get('type') == 'point':
                title = p.get('title', '')
                # Extract full score like "0 - 1" from title "1.30 0 - 1 Player -> Player"
                parts = title.split()
                score = None
                for i, part in enumerate(parts):
                    if part == '-' and i > 0 and i < len(parts) - 1:
                        score = f"{parts[i-1]} - {parts[i+1]}"
                        break
                if score and score not in seen_scores:
                    seen_scores.add(score)
                    unique_points.append(p)
            elif p.get('type') == 'halftime':
                unique_points.append(p)
        
        point_entries = [p for p in unique_points if p.get('type') == 'point']
        if not point_entries:
            continue
        
        # Determine Otso's side
        home_team = gp.get('home_team', '')
        away_team = gp.get('away_team', '')
        home_is_otso = is_otso_team(home_team) or is_otso_akatemia(home_team)
        away_is_otso = is_otso_team(away_team) or is_otso_akatemia(away_team)
        
        if home_is_otso:
            otso_side = 'home'
        elif away_is_otso:
            otso_side = 'guest'
        else:
            continue
        
        # Determine which team started on offense for the first point
        # Try to load HTML file using game_id
        game_id = game.get('game_id', '')
        html_file = RAW_DIR / f'game_{game_id}.html'
        
        first_offense_side = None
        
        if html_file.exists():
            with open(html_file) as f:
                raw_html = f.read()
            
            if 'Hyökkäys' in raw_html:
                # Parse HTML to find Hyökkäys marker class
                soup = BeautifulSoup(raw_html, 'html.parser')
                tables = soup.find_all('table')
                
                # Find the point table (headers: Pisteet, Syöttäjä, Maali, Aika, Kesto, Pelitapahtumat)
                point_table = None
                for table in tables:
                    headers = [th.get_text(strip=True) for th in table.find_all('th')]
                    if 'Pelitapahtumat' in headers:
                        point_table = table
                        break
                
                if point_table:
                    rows = point_table.find_all('tr')
                    for row in rows:
                        cells = [td.get_text(strip=True) for td in row.find_all('td')]
                        if cells and len(cells) >= 2 and ' - ' in cells[0]:
                            # Found first data row
                            last_cell = row.find_all('td')[-1]
                            div = last_cell.find('div')
                            if div and div.get('class'):
                                hyökk_class = div.get('class')[0]
                                # The team with matching class started on offense
                                first_offense_side = hyökk_class
                            break
        
        # Build roster map: canonical name → team side (home/guest)
        # This is needed because the `side` field in points data is unreliable
        # and doesn't always match the player's actual team
        roster_map = {}
        for p in gp.get('home_players', []):
            name = p.get('name', '')
            if name:
                canon = canonicalize_name(name)
                if canon:
                    roster_map[canon] = 'home'
        for p in gp.get('away_players', []):
            name = p.get('name', '')
            if name:
                canon = canonicalize_name(name)
                if canon:
                    roster_map[canon] = 'guest'
        
        if first_offense_side is not None:
            # HTML file with Hyökkäys marker: use it for the first point
            first_defense_side = 'home' if first_offense_side == 'guest' else 'guest'
            first_half_defense_side = first_defense_side
            current_offense_side = first_offense_side
            current_defense_side = first_defense_side
            
            for point in point_entries:
                if point.get('type') == 'halftime':
                    # Halftime: team that started on defense starts on offense
                    current_offense_side = first_half_defense_side
                    current_defense_side = 'home' if first_half_defense_side == 'guest' else 'guest'
                    continue
                
                scorer_name = point.get('scorer', '')
                
                # Determine scorer's team from roster
                scorer_canon = canonicalize_name(scorer_name) if scorer_name else None
                scorer_side = roster_map.get(scorer_canon) if scorer_canon else None
                
                if scorer_side is None:
                    continue
                
                otso_is_scorer = (scorer_side == otso_side)
                otso_on_defense = (current_defense_side == otso_side)
                
                if otso_is_scorer and scorer_name:
                    is_defense = otso_on_defense
                    player_stats[scorer_name]['defense_points' if is_defense else 'offense_points'] += 1
                    player_stats[scorer_name]['defense_goals' if is_defense else 'offense_goals'] += 1
                    player_stats[scorer_name]['total_points'] += 1
                    
                    # Track assist on defense/offense
                    assist_name = point.get('passer', '')
                    if assist_name:
                        assist_canon = canonicalize_name(assist_name)
                        if assist_canon:
                            player_stats[assist_name]['defense_assists' if is_defense else 'offense_assists'] += 1
                
                # Next point: scorer starts on defense
                current_defense_side = scorer_side
                current_offense_side = 'home' if scorer_side == 'guest' else 'guest'
        else:
            # No HTML file: can't know who started on offense for point 1
            # Use alternating logic from point 2 onward
            # Skip defensive attribution for point 1 only
            point_index = 0
            
            for point in point_entries:
                if point.get('type') == 'halftime':
                    # Halftime: team that was on defense starts on offense
                    # But we don't know who was on defense at halftime without HTML
                    # Reset: alternate from the point after halftime
                    point_index += 1
                    continue
                
                scorer_name = point.get('scorer', '')
                
                # Determine scorer's team from roster
                scorer_canon = canonicalize_name(scorer_name) if scorer_name else None
                scorer_side = roster_map.get(scorer_canon) if scorer_canon else None
                
                if scorer_side is None:
                    point_index += 1
                    continue
                
                otso_is_scorer = (scorer_side == otso_side)
                
                # For point 1 (index 0), we don't know who was on defense
                # So we can't attribute defensive points
                # For point 2+ (index >= 1), we can use alternating logic
                if point_index == 0:
                    # First point: only count offensive points for Otso
                    # (we don't know who was on defense)
                    if otso_is_scorer and scorer_name:
                        player_stats[scorer_name]['offense_points'] += 1
                        player_stats[scorer_name]['offense_goals'] += 1
                        player_stats[scorer_name]['total_points'] += 1
                        
                        # Track assist
                        assist_name = point.get('passer', '')
                        if assist_name:
                            assist_canon = canonicalize_name(assist_name)
                            if assist_canon:
                                player_stats[assist_name]['offense_assists'] += 1
                    
                    # Initialize alternating state for next point
                    # If Otso scored, they start on defense next
                    # If opponent scored, they start on defense next
                    current_defense_side = scorer_side
                    current_offense_side = 'home' if scorer_side == 'guest' else 'guest'
                else:
                    # Points 2+: use alternating logic
                    otso_on_defense = (current_defense_side == otso_side)
                    
                    if otso_is_scorer and scorer_name:
                        is_defense = otso_on_defense
                        player_stats[scorer_name]['defense_points' if is_defense else 'offense_points'] += 1
                        player_stats[scorer_name]['defense_goals' if is_defense else 'offense_goals'] += 1
                        player_stats[scorer_name]['total_points'] += 1
                        
                        # Track assist on defense/offense
                        assist_name = point.get('passer', '')
                        if assist_name:
                            assist_canon = canonicalize_name(assist_name)
                            if assist_canon:
                                player_stats[assist_name]['defense_assists' if is_defense else 'offense_assists'] += 1
                    
                    # Next point: scorer starts on defense
                    current_defense_side = scorer_side
                    current_offense_side = 'home' if scorer_side == 'guest' else 'guest'
                
                point_index += 1
    
    # Convert defaultdict to regular dict with display names
    result = {}
    for name, stats in player_stats.items():
        result[name] = stats
    
    return result


def build_frenemies(gameplay: list[dict], top_n: int = 21) -> list[dict]:
    """Build top opponents by career points against Otso.
    
    Processes all non-Otso players in gameplay data, counting goals/assists
    from the points data (not roster totals which are unreliable).
    Uses canonical name matching to handle "Lastname Firstname" vs
    "Firstname Lastname" format differences.
    
    Returns list of dicts sorted by total points, limited to top_n.
    Each entry has: rank, name, games, wins, losses, goals, assists, total, ppg, teams
    """
    players = defaultdict(lambda: {
        'games': 0, 'wins': 0, 'goals': 0, 'assists': 0, 'teams': Counter()
    })
    
    for game in gameplay:
        gp = game.get('gameplay')
        if not gp:
            continue
        
        home = gp.get('home_team', '')
        away = gp.get('away_team', '')
        home_score = gp.get('home_score', 0)
        away_score = gp.get('away_score', 0)
        
        home_is_otso = is_otso_team(home) or is_otso_akatemia(home)
        away_is_otso = is_otso_team(away) or is_otso_akatemia(away)
        
        if not home_is_otso and not away_is_otso:
            continue
        
        # Skip intra-squad games: both sides are Otso-family teams, so there is
        # no external opponent to count as a frenemy.
        if home_is_otso and away_is_otso:
            continue
        
        canon_to_display = {}
        for p in gp.get('home_players', []) + gp.get('away_players', []):
            name = p.get('name', '')
            if name:
                canon = canonicalize_name(name)
                if canon and canon not in canon_to_display:
                    canon_to_display[canon] = name
        
        # Build set of Otso canonical names
        otso_canonicals = set()
        for p in gp.get('home_players', []):
            if home_is_otso:
                canon = canonicalize_name(p.get('name', ''))
                if canon:
                    otso_canonicals.add(canon)
        for p in gp.get('away_players', []):
            if away_is_otso:
                canon = canonicalize_name(p.get('name', ''))
                if canon:
                    otso_canonicals.add(canon)
        
        # Determine which side is Otso and which is opponent
        if home_is_otso:
            otso_score = home_score
            opp_score = away_score
            opp_team = away
        else:
            otso_score = away_score
            opp_score = home_score
            opp_team = home
        opp_canonicals = set(canon_to_display.keys()) - otso_canonicals
        
        # Count games and wins for opponent players
        for canon in opp_canonicals:
            display_name = canon_to_display[canon]
            players[display_name]['games'] += 1
            if opp_score > otso_score:
                players[display_name]['wins'] += 1
            # Track the OPPONENT's team (not the Otso team), with game counts so
            # the team they faced Otso most often for sorts first.
            players[display_name]['teams'][opp_team] += 1
        
        # Count goals/assists from points data using canonical matching
        for point in gp.get('points', []):
            if point.get('type') != 'point':
                continue
            scorer_canon = canonicalize_name(point.get('scorer', ''))
            assist_canon = canonicalize_name(point.get('passer', ''))
            
            if scorer_canon in canon_to_display and scorer_canon not in otso_canonicals:
                players[canon_to_display[scorer_canon]]['goals'] += 1
            if assist_canon in canon_to_display and assist_canon not in otso_canonicals:
                players[canon_to_display[assist_canon]]['assists'] += 1
    
    # Sort by total points and take top_n
    scored = []
    for name, p in players.items():
        total = p['goals'] + p['assists']
        if total > 0:
            ppg = total / p['games'] if p['games'] > 0 else 0
            scored.append({
                'name': name,
                'games': p['games'],
                'wins': p['wins'],
                'losses': p['games'] - p['wins'],
                'goals': p['goals'],
                'assists': p['assists'],
                'total': total,
                'ppg': round(ppg, 2),
                'teams': [t for t, _ in sorted(p['teams'].items(), key=lambda kv: (-kv[1], kv[0]))],
            })
    
    scored.sort(key=lambda x: -x['total'])
    
    # Add rank
    for i, entry in enumerate(scored[:top_n], 1):
        entry['rank'] = i
    
    return scored[:top_n]


# --- Trophy record -----------------------------------------------------------
#
# The pelikone format changed three times, so which file decides a season's medals
# is stated explicitly here rather than inferred from filenames: filename inference
# is what would silently count a Tour stop as a finale.
#   2006-2010  the season file itself (no separate finale existed)
#   2011-2019  summer = the Finaalit file; winter = the winter season file
#   2020+      one championship event per season, in the season file itself
#              (Kesä 2026 keeps Tour 1 / Tour 2 / Finaalit as sub-tournaments inside
#              the single KESA2026 season id; its placements are the final standings)
# Winter never had a separate finale file.
TROPHY_EVENTS: dict[str, tuple[int, str]] = {
    # summer (Kesä)
    "2006.1": (2006, "summer"), "2007.1": (2007, "summer"), "2008.1": (2008, "summer"),
    "2009.1": (2009, "summer"), "2010.1": (2010, "summer"), "2011.4": (2011, "summer"),
    "2012.T4": (2012, "summer"), "2013.1": (2013, "summer"), "2014.1F": (2014, "summer"),
    "2015.1F": (2015, "summer"), "2016.1.F": (2016, "summer"), "2017F": (2017, "summer"),
    "2018.F": (2018, "summer"), "2019.Finaa": (2019, "summer"), "2020.1": (2020, "summer"),
    "2021.1": (2021, "summer"), "SM2022K": (2022, "summer"), "2023.1": (2023, "summer"),
    "2024.1": (2024, "summer"), "2025.1": (2025, "summer"), "KESA2026": (2026, "summer"),
    # winter (Talvi)
    "2006.2": (2006, "winter"), "2007.2": (2007, "winter"), "2008.2": (2008, "winter"),
    "2009.2": (2009, "winter"), "2010.2": (2010, "winter"), "2011.2": (2011, "winter"),
    "2012.2": (2012, "winter"), "2013.2": (2013, "winter"), "Hallitour2": (2014, "winter"),
    "2015.4": (2015, "winter"), "Talvi2016": (2016, "winter"), "2017.1": (2017, "winter"),
    "2018.1": (2018, "winter"), "2019.1": (2019, "winter"), "2020.2": (2020, "winter"),
    "2021.2": (2021, "winter"), "2022.3": (2022, "winter"), "2023.2": (2023, "winter"),
    "2024.2": (2024, "winter"), "2025.3": (2025, "winter"),
}

MEDAL_PLACEMENTS = {"Kulta": "gold", "Hopea": "silver", "Pronssi": "bronze"}
MEDAL_RANK = {"gold": 0, "silver": 1, "bronze": 2}
MEDAL_PLACEMENTS_INV = {v: k for k, v in MEDAL_PLACEMENTS.items()}

# Talvi 2020 was never played — cancelled because of the covid pandemic. It is not
# a missing scrape and must not count as a season contested.
SEASONS_NOT_PLAYED = {"2020.2"}

# Only the open/flagship division counts towards the trophy cabinet. Juniorit,
# Naiset, Mixed, Master Mixed and SM Ranta results live in other divisions.
# The label is written two ways in the raw data — "Avoin" and "Avoin SM" (Kesä 2010).
TROPHY_DIVISION = "avoin"


def _placement_rank(placement: str, medal: str | None) -> int:
    """Sort key for a placement string: medals first, then numeric rank, unknown last."""
    if medal:
        return MEDAL_RANK[medal]
    match = re.match(r"^(\d+)\.$", placement or "")
    return 3 + int(match.group(1)) if match else 999


def build_trophies(raw_data: list[dict]) -> dict:
    """Derive the season-level trophy record from the raw placement tables.

    A trophy is a Kulta/Hopea/Pronssi placement in the Avoin division by an Otso
    team (main, 2, 3, Grizzly, Polar — never Akatemia) in a season-deciding event.
    Tour stops are regular-season events and are deliberately not counted.

    Each season record keeps the single best result (medal/team/placement, which is
    what the trophy cabinet counts) and also lists every Otso team that finished in
    the division under "entries" — in 2013 winter Otso won it, Otso 2 was 7th and
    Otso 3 was 10th, and the timeline shows all three.
    """
    by_id = {d["id"]: d for d in raw_data if isinstance(d, dict) and "id" in d}

    seasons = []
    for season_id, (year, season_type) in sorted(
        TROPHY_EVENTS.items(), key=lambda kv: (kv[1][0], kv[1][1], kv[0])
    ):
        record = {
            "year": year,
            "season": season_type,
            "event": season_id,
            "medal": None,
            "team": None,
            "placement": None,
            "played": season_id not in SEASONS_NOT_PLAYED,
            "entries": [],
        }
        season = by_id.get(season_id)
        if season is None:
            print(f"  WARNING: no raw file for trophy event {season_id}")
            seasons.append(record)
            continue

        best_medal = None
        best_team = None
        best_numeric = None  # (rank, placement string, team)
        by_team: dict[str, dict] = {}  # every Otso team in the division, best result each
        for p in season.get("placements") or []:
            if not (p.get("division") or "").strip().lower().startswith(TROPHY_DIVISION):
                continue
            team = p.get("team_name", "")
            if not is_otso_team(team):
                continue
            placement = p.get("placement", "")
            medal = MEDAL_PLACEMENTS.get(placement)
            if medal is not None:
                if best_medal is None or MEDAL_RANK[medal] < MEDAL_RANK[best_medal]:
                    best_medal, best_team = medal, team
            else:
                match = re.match(r"^(\d+)\.$", placement)
                if match:
                    rank = int(match.group(1))
                    if best_numeric is None or rank < best_numeric[0]:
                        best_numeric = (rank, placement, team)

            if placement:
                prev = by_team.get(team)
                if prev is None or _placement_rank(placement, medal) < _placement_rank(
                    prev["placement"], prev["medal"]
                ):
                    by_team[team] = {"team": team, "placement": placement, "medal": medal}

        record["entries"] = sorted(
            by_team.values(), key=lambda e: _placement_rank(e["placement"], e["medal"])
        )

        if best_medal is not None:
            record["medal"] = best_medal
            record["team"] = best_team
            record["placement"] = MEDAL_PLACEMENTS_INV[best_medal]
        elif best_numeric is not None:
            record["placement"] = best_numeric[1]
            record["team"] = best_numeric[2]
        seasons.append(record)

    def totals(rows: list[dict]) -> dict:
        out = {"gold": 0, "silver": 0, "bronze": 0, "podiums": 0, "contested": 0}
        for r in rows:
            if r["played"]:
                out["contested"] += 1
            if r["medal"]:
                out[r["medal"]] += 1
                out["podiums"] += 1
        return out

    summer = [r for r in seasons if r["season"] == "summer"]
    winter = [r for r in seasons if r["season"] == "winter"]

    return {
        "seasons": seasons,
        "totals": {
            "summer": totals(summer),
            "winter": totals(winter),
            "all": totals(summer + winter),
        },
    }


def main():
    print("Loading raw data...")
    raw_data = load_raw_data()
    print(f"  Loaded {len(raw_data)} season files")
    
    print("Loading gameplay data...")
    gameplay = load_gameplay()
    print(f"  Loaded {len(gameplay)} games")
    
    print("Building players...")
    players = build_players(raw_data, gameplay)
    print(f"  {len(players)} players")
    
    print("Building defense stats...")
    defense_stats = build_defense_stats(gameplay)
    print(f"  {len(defense_stats)} players with defense stats")
    
    print("Building pass network...")
    pass_network = build_pass_network(gameplay, players)
    received_count = len(pass_network.get("received", {}))
    given_count = len(pass_network.get("given", {}))
    total_pass_edges = sum(len(v) for v in pass_network.get("received", {}).values())
    print(f"  {received_count} players received assists, {given_count} gave assists, {total_pass_edges} directed edges")
    
    print("Building co-occurrence...")
    cooccurrence = build_cooccurrence(gameplay, players)
    total_cooc_edges = sum(len(v) for v in cooccurrence.values())
    print(f"  {len(cooccurrence)} players with co-occurrences, {total_cooc_edges // 2} undirected edges")
    
    print("Building years...")
    # Generate datasets for each team scope and season type
    years_otso = build_years(gameplay, include_all_bears=False)
    years_all_bears = build_years(gameplay, include_all_bears=True)
    years_otso_summer = build_years(gameplay, include_all_bears=False, season_type="summer")
    years_all_bears_summer = build_years(gameplay, include_all_bears=True, season_type="summer")
    years_otso_winter = build_years(gameplay, include_all_bears=False, season_type="winter")
    years_all_bears_winter = build_years(gameplay, include_all_bears=True, season_type="winter")
    print(f"  Full: {len(years_otso)} years (Otso), {len(years_all_bears)} years (All Bears)")
    print(f"  Summer: {len(years_otso_summer)} years (Otso), {len(years_all_bears_summer)} years (All Bears)")
    print(f"  Winter: {len(years_otso_winter)} years (Otso), {len(years_all_bears_winter)} years (All Bears)")
    
    print("Building frenemies...")
    frenemies = build_frenemies(gameplay)
    print(f"  {len(frenemies)} frenemies")
    
    print("Building summary...")
    summary = build_summary(players, pass_network, cooccurrence, years_otso, gameplay)

    print("Building trophies...")
    trophies = build_trophies(raw_data)
    t = trophies["totals"]["all"]
    print(f"  {t['gold']} gold, {t['silver']} silver, {t['bronze']} bronze "
          f"= {t['podiums']} podiums in {t['contested']} seasons contested")
    
    # Create output directory
    SITE_DATA_DIR.mkdir(exist_ok=True)
    
    # Write files
    files = {
        "players.json": players,
        "pass_network.json": pass_network,
        "cooccurrence.json": cooccurrence,
        "years_otso.json": years_otso,
        "years_all_bears.json": years_all_bears,
        "years_otso_summer.json": years_otso_summer,
        "years_all_bears_summer.json": years_all_bears_summer,
        "years_otso_winter.json": years_otso_winter,
        "years_all_bears_winter.json": years_all_bears_winter,
        "summary.json": summary,
        "frenemies.json": frenemies,
        "trophies.json": trophies,
    }
    
    # Merge defense stats into players
    for display_name, stats in defense_stats.items():
        if display_name in players:
            players[display_name]["defense_points"] = stats["defense_points"]
            players[display_name]["defense_goals"] = stats["defense_goals"]
            players[display_name]["defense_assists"] = stats["defense_assists"]
            players[display_name]["offense_points"] = stats["offense_points"]
            players[display_name]["offense_goals"] = stats["offense_goals"]
            players[display_name]["offense_assists"] = stats["offense_assists"]
            players[display_name]["total_points"] = stats["total_points"]
    
    for filename, data in files.items():
        filepath = SITE_DATA_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        size_kb = filepath.stat().st_size / 1024
        print(f"  Written {filename} ({size_kb:.1f} KB)")
    
    stamp_build_version(files)
    
    print("\nDone! Site data ready in site_data/")


def stamp_build_version(files: dict) -> None:
    """Stamp a content hash of the site data into index.html as DATA_VERSION.

    index.html appends ?v=<hash> to every JSON fetch. Without it, browsers and
    the GitHub Pages CDN serve stale data after a rebuild — the old frenemies
    team bug stayed visible long after the fix shipped.
    """
    h = hashlib.sha256()
    for filename in sorted(files):
        h.update(filename.encode("utf-8"))
        h.update((SITE_DATA_DIR / filename).read_bytes())
    version = h.hexdigest()[:12]
    
    index = BASE_DIR / "index.html"
    text = index.read_text(encoding="utf-8")
    new, n = re.subn(
        r"(// BUILD_VERSION_START\s*\n\s*const DATA_VERSION = ')[^']*(';)",
        lambda m: m.group(1) + version + m.group(2),
        text,
        count=1,
    )
    if n == 0:
        print("  WARNING: BUILD_VERSION markers not found in index.html; not stamped")
        return
    index.write_text(new, encoding="utf-8")
    print(f"  Stamped DATA_VERSION={version} into index.html")


if __name__ == "__main__":
    main()
