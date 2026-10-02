#!/usr/bin/env python3
"""
Build site data for Otso 20v gaala website.

Reads raw scraped data and gameplay data, produces JSON files for the static site:
  site_data/players.json     — per-player stats
  site_data/pass_network.json — directed pass connections
  site_data/cooccurrence.json — undirected co-occurrence matrix
  site_data/summary.json     — aggregate stats for landing page
  site_data/years.json       — year-by-year evolution data
"""

import json
import os
import re
import sys
import glob
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "data" / "raw"
GAMEPLAY_FILE = BASE_DIR / "data" / "processed" / "match_results.json"
SITE_DATA_DIR = BASE_DIR / "site_data"


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
    """Check if a team name belongs to Otso main/2/3/Grizzly/Polar/Hukka (excludes Akatemia)."""
    lower = name.lower()
    if "akatemia" in lower:
        return False
    return any(t in lower for t in ["otso", "grizzly", "polar", "hukka"])


def is_otso_akatemia(name: str) -> bool:
    """Check if a team name is Otso Akatemia (not UFO Akatemia)."""
    lower = name.lower()
    return "akatemia" in lower and "otso" in lower


def canonicalize_team_name(name: str) -> str:
    """Canonicalize team names to a consistent format.
    
    Maps variants like 'OTSO 2', 'Otso 2', 'Otso2' → 'Otso 2'
    """
    lower = name.strip().lower()
    # Remove spaces to normalize 'Otso 2' vs 'Otso2'
    no_space = lower.replace(' ', '')
    
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
    elif 'akatemia' in lower and 'otso' in lower:
        return 'Otso Akatemia'
    elif 'akatemia' in lower:
        return name  # Keep as-is (e.g., UFO Akatemia)
    else:
        return name  # Unknown team, keep as-is


def extract_year_from_season_id(season_id: str) -> int | None:
    """Extract year from season ID like '2025.1', 'KESA2026', 'Talvi2016', etc."""
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
    # BEACHyyyy
    if season_id.startswith("BEACH") and season_id[5:].isdigit():
        return int(season_id[5:])
    # SMyyyy, XSMyyyy, MSMyyyy, OSMyyyy
    for prefix in ["SM", "XSM", "MSM", "OSM"]:
        if season_id.startswith(prefix) and len(season_id) > len(prefix) and season_id[len(prefix):].isdigit():
            y = int(season_id[len(prefix):])
            return y if y >= 2006 else None
    # JSMyyyy
    if season_id.startswith("JSM") and season_id[3:].isdigit():
        y = int(season_id[3:])
        return y if y >= 2006 else None
    # *JSMyyyy
    if season_id.startswith("*JSM") and season_id[4:].isdigit():
        y = int(season_id[4:])
        return y if y >= 2006 else None
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
        if stype == "winter":
            p["season_types"]["winter"].add(year)
        elif stype == "summer":
            p["season_types"]["summer"].add(year)
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
                
                players[canon] = {
                    "seasons": [],
                    "years": set(),
                    "season_types": {"summer": set(), "winter": set(), "other": set()},
                    "first_year": year if year else 2006,
                    "last_year": year if year else 2006,
                    "games": 1,
                    "goals": 0,
                    "assists": 0,
                    "total": 0,
                    "teams": {player_team} if player_team else set(),
                }
    
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
    
    # Convert sets to sorted lists for JSON, pick best display name
    result = {}
    for canonical, p in players.items():
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
        }
    
    return result


def build_pass_network(gameplay: list[dict], players: dict) -> dict:
    """Build directed pass network from gameplay points.
    
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
            raw_assist = point.get("assist", "")
            
            scorer_canon = canonicalize_name(raw_scorer)
            assist_canon = canonicalize_name(raw_assist)
            
            # Only count if both players are Otso players we know
            if scorer_canon in otso_canonicals and assist_canon in otso_canonicals:
                network[scorer_canon][assist_canon] += 1
    
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
    
    # Convert to regular dicts with display names
    result = {}
    for canon, display_name in canon_to_display.items():
        if cooc[canon]:
            result[display_name] = {}
            for other_canon, count in cooc[canon].items():
                if other_canon in canon_to_display:
                    result[display_name][canon_to_display[other_canon]] = count
    
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
    
    return {
        "total_matches": games_with_gameplay,
        "total_players": len(players),
        "total_wins": wins,
        "total_losses": losses,
        "total_goals_for": total_goals_for,
        "total_goals_against": total_goals_against,
        "win_percentage": round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0,
        "top_scorers": top_scorers,
        "top_assists": top_assists,
        "longest_careers": longest_careers,
        "most_connected": most_connected,
        "most_teammates": most_teammates,
        "goals_per_match": goals_per_match,
        "years_count": len(years),
    }


def build_years(gameplay: list[dict]) -> dict:
    """Build year-by-year evolution data.
    
    Returns: {year: {matches, wins, losses, goals_for, goals_against, roster_players}}
    """
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
        
        home_is_otso = is_otso_team(gp.get("home_team", ""))
        away_is_otso = is_otso_team(gp.get("away_team", ""))
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
    for year in sorted(years.keys()):
        y = years[year]
        result[str(year)] = {
            "matches": y["matches"],
            "wins": y["wins"],
            "losses": y["losses"],
            "goals_for": y["goals_for"],
            "goals_against": y["goals_against"],
            "roster_players": len(y["roster_players"]),
        }
    
    return result


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
    years = build_years(gameplay)
    print(f"  {len(years)} years")
    
    print("Building summary...")
    summary = build_summary(players, pass_network, cooccurrence, years, gameplay)
    
    # Create output directory
    SITE_DATA_DIR.mkdir(exist_ok=True)
    
    # Write files
    files = {
        "players.json": players,
        "pass_network.json": pass_network,
        "cooccurrence.json": cooccurrence,
        "years.json": years,
        "summary.json": summary,
    }
    
    for filename, data in files.items():
        filepath = SITE_DATA_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        size_kb = filepath.stat().st_size / 1024
        print(f"  Written {filename} ({size_kb:.1f} KB)")
    
    print("\nDone! Site data ready in site_data/")


if __name__ == "__main__":
    main()
