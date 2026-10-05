"""Builder functions for derived data (timeline, network, summary)."""

from typing import List, Dict


def build_team_timeline(seasons_data: List[Dict]) -> List[Dict]:
    """Build a timeline of Otso teams across all seasons.
    
    Args:
        seasons_data: List of season data dictionaries.
        
    Returns:
        List of timeline entries with year, season info, and teams.
    """
    from .parsers import is_otso_team
    
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


def build_player_network(seasons_data: List[Dict]) -> Dict:
    """Build a network of players who played together (Otso teams only).
    
    Args:
        seasons_data: List of season data dictionaries.
        
    Returns:
        Dictionary with players and connections.
    """
    from .parsers import is_otso_team
    
    player_teams = {}  # player_name -> list of (team_name, season_id)

    for season in seasons_data:
        for team in season["teams"]:
            # Only include Otso teams
            if not is_otso_team(team["name"]):
                continue
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


def build_summary(seasons_data: List[Dict], player_network: Dict) -> Dict:
    """Build summary statistics.
    
    Args:
        seasons_data: List of season data dictionaries.
        player_network: Player network dictionary.
        
    Returns:
        Summary dictionary with total counts.
    """
    from .parsers import is_otso_team
    
    return {
        "total_seasons": len(seasons_data),
        "years_covered": sorted(
            set(s["classified"]["year"] for s in seasons_data if s["classified"]["year"])
        ),
        "total_teams": sum(len(s["teams"]) for s in seasons_data),
        "otso_teams": sum(
            len([t for t in s["teams"] if is_otso_team(t["name"])])
            for s in seasons_data
        ),
        "total_players": len(player_network["players"]),
        "total_connections": len(player_network["connections"]),
    }
