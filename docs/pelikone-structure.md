# Pelikone Data Structure

## Overview

Pelikone is the Finnish Ultimate Federation's tournament management system (powered by Ultiorganizer).
URL: `https://ultimate.fi/pelikone/`

## Base URL Pattern

```
https://ultimate.fi/pelikone/?view=VIEW&season=SEASON_ID[&additional_params]
```

## Key Views

### Season List
- **URL**: `?view=seasonlist`
- **Purpose**: Lists all available seasons with their IDs
- **Data extracted**: Season name, season ID, available series/divisions

### Teams List
- **URL**: `?view=teams&season=SEASON_ID&list=allteams`
- **Purpose**: Lists all teams in a season
- **Data extracted**: Team name, team ID, club, division

### Team Standings
- **URL**: `?view=teams&season=SEASON_ID&list=bystandings`
- **Purpose**: Shows placement results for each division
- **Data extracted**: Placement (Kulta/Hopea/Pronssi/4./5./etc.), team name, team ID, division

### Team Card
- **URL**: `?view=teamcard&team=TEAM_ID`
- **Purpose**: Detailed view of a team
- **Data extracted**: Team name, club, country, division, player list with stats, game results, spirit scores

### Player List (by team)
- **URL**: `?view=playerlist&team=TEAM_ID`
- **Purpose**: All-time stats for players on a team
- **Data extracted**: Player name, player ID, events, games, assists, goals, total

### Player Card
- **URL**: `?view=playercard&series=0&player=PLAYER_ID`
- **Purpose**: Detailed stats for a player
- **Data extracted**: Player name, all teams played for, all-time stats

### Games/Matches
- **URL**: `?view=games&season=SEASON_ID&filter=tournaments&group=all`
- **Purpose**: All games in a season
- **Data extracted**: Game time, home team, away team, scores, pool, division, field

### Game Play (detailed)
- **URL**: `?view=gameplay&game=GAME_ID`
- **Purpose**: Detailed game log with disc-by-disc scoring
- **Data extracted**: Point-by-point scoring, throws, scores, team rosters for that game

## CSV Export (Current Season Only)

Available for the **current season only** via:

```
https://ultimate.fi/pelikone/ext/VIEWcsv.php?season=SEASON_ID&enc=UTF-8&sep=,
```

### Available CSV Endpoints

| Endpoint | Description |
|----------|-------------|
| `gamescsv.php` | All scheduled games with times, teams, scores, pools |
| `resultscsv.php` | All game results (home, away, scores, division, pool) |
| `playerscsv.php` | Player stats (first name, last name, jersey, team, division, games, assists, goals, total) |
| `teamscsv.php` | Team stats (team name, short name, club, country, division, games, wins, goals for/against, spirit) |
| `poolscsv.php` | Pool standings |
| `spiritcsv.php` | Spirit scores |

## Season ID Patterns

Season IDs follow various patterns:

| Pattern | Example | Description |
|---------|---------|-------------|
| `KESAYYYY` | `KESA2026` | Summer season |
| `YYYY.1` | `2025.1` | Summer season (newer format) |
| `YYYY.2` | `2025.2` | Winter season (newer format) |
| `YYYY.3` | `2025.3` | Winter season (newer format) |
| `YYYY.T1` | `2019.T1` | Summer Tour 1 |
| `YYYY.T2` | `2019.T2` | Summer Tour 2 |
| `YYYY.T3` | `2019.T3` | Summer Tour 3 |
| `YYYY.F` or `YYYY.Finaa` | `2018.F` | Summer Finals |
| `YYYY.1F` | `2015.1F` | Summer Finals (alternate format) |
| `YYYY.1.T1` | `2016.1.T1` | Summer Tour 1 (alternate format) |
| `SMYYYYK` | `SM2022K` | SM (Championship) Summer |
| `XSMYYYY` | `XSM2018` | Mixed SM |
| `MSMYYYY` | `MSM2015` | Mixed SM (alternate) |
| `OSMYYYY` | `OSM2015` | Open SM |
| `JSMYYYY` | `JSM2019` | Junior SM |
| `*JSMYYYY` | `*JSM2018` | Junior SM (wildcard) |
| `BEACHYYYY` | `BEACH2021` | Beach SM |
| `BMSMYYYY` | `BMSM2` | Beach SM (alternate) |
| `TalviYYYY` | `Talvi2016` | Winter (old format) |
| `HallitourYYYY` | `Hallitour2` | Indoor/Winter tour |
| `2024.123` | `2024.123` | Beach event |

## Division Names

| Finnish | English |
|---------|---------|
| Avoin | Open |
| Naiset | Women |
| Mixed | Mixed |
| Juniorit U17 | Junior U17 |
| Juniorit U20 | Junior U20 |
| Masters | Masters |

## Key Metrics for Otso

### Otso Team IDs (historical)

| Season | Team ID | Team Name |
|--------|---------|-----------|
| 2026 | 3258 | Otso (Avoin) |
| 2025 | 3177 | Otso (Avoin) |
| 2025 | 3178 | Otso2 (Avoin) |
| 2019 T1 | 2630 | Otso Polar |
| 2019 T1 | 2631 | Otso Grizzly |

### Player IDs (current Otso 2026)

| Player ID | Name |
|-----------|------|
| 35408 | Aleksi Mustonen |
| 35409 | Eelis Junnila |
| 35411 | Emil Videman |
| 35412 | Erkka Niini |
| 35413 | Kivi Knuuti |
| 35414 | Matias Arola |
| 35415 | Mikko Alitalo |
| 35416 | Patrick Potrykus |
| 35417 | Pekka Kinnunen |
| 35418 | Phong Tran |
| 35419 | Roope Kettunen |
| 35420 | Samuel-visal Roeung |
| 35421 | Santeri Harmaala |
| 35422 | Roni Hotari |
| 35423 | Tomi Sandberg |
| 35424 | Jarno Sihvo |
| 35425 | Ilkka Vaahtoranta |
| 35462 | Oskari Vuorio |

## Scraping Strategy

### Priority Order

1. **CSV export** (current season only) - Most structured, easiest to parse
2. **HTML standings** (`bystandings`) - For placements across all seasons
3. **HTML team cards** (`teamcard`) - For team rosters and game results
4. **HTML player lists** (`playerlist`) - For all-time player stats
5. **HTML games** (`games`) - For match schedules and results

### Rate Limiting

- Add 1-2 second delays between requests
- Cache all responses to avoid repeated requests
- Respect robots.txt if available

### Data Caching

- Store raw HTML in `data/raw/` with season/team identifiers
- Store parsed JSON in `data/processed/`
- Use a cache manifest to track what's been downloaded
