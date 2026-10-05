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

### All Players (A–Z index)
- **URL**: `?view=allplayers&list=all`
- **Purpose**: every registered player on the instance
- **Data extracted**: player ID, `First Last` display name (2,568 measured)
- **Trap**: without `list=all` the view renders **one letter group**. Three of the
  2,568 entries have an ID and an empty name — kept, and reported as data quality.

### All Teams / All Clubs
- **URL**: `?view=allteams&list=all`, `?view=allclubs&list=all`
- **Data extracted**: team ID, name, division (from the `[Avoin]` suffix) /
  club ID, name. Measured: 317 teams, 106 clubs.
- **Trap**: same letter-group default as `allplayers`; the grid also pads its last
  row with a `teamcard&team=` cell that has no ID and reads `[]`.

### Score Status (one event's whole scoreboard)
- **URL**: `?view=scorestatus&series=SERIES_ID`
- **Data extracted**: rank, **player ID**, name, team, GP, A, G, Tot., the three
  averages, Callahans — one row per player in that series (123 for KESA2026 Avoin)
- **Why it matters**: the cheapest bulk source of ID-keyed per-event scoring — one
  request per event instead of one per player.
- **Trap**: the page renders this table **twice** (`div.page_middle` and
  `div.content`). Scanning the document gives 246 rows for 123 players.

### Statistics (top three per event, every event)
- **URL**: `?view=statistics&season=SEASON_ID&list=playerscoreboard`
- **Data extracted**: grouped by `<h2>` (Sisä / Ulko / Ranta — indoor, outdoor,
  beach) and `<h3>` (division); one table per division listing every event, its
  `series` ID, and the three leading scorers with player IDs and `A + G = Tot.`
- **Note**: `season=` does **not** scope this list — the page covers every event
  the instance has (231 measured). `list=playerscoresall` is the all-time variant.

## The ID spaces are not interchangeable

| Space | Example | Where it comes from |
|---|---|---|
| `season` | `KESA2026`, `2018.1`, `*JSM2018` | `?view=seasonlist` |
| `series` | `3300` | **only** the left menu of a season page (`?view=seriesstatus&series=NNNN`), one per division of one event — `parse_series_menu` |
| `pool` | `1819` | the menu under a series |
| `team` | `3130` | `allteams`, `teamcard`, game scoreboards |
| `club` | `159` | `allclubs`, `clubcard` |
| `player` | `35304` | `allplayers`, game rosters, `scorestatus` |

> [!WARNING]
> **A player ID is a registration, not a person.** Measured across the 795 archived
> games: 904 distinct roster names map to **6,175** distinct player IDs — pelikone
> re-issues an ID per registration/season. One human can hold a dozen. Any query
> about a *person* goes through the person key (`config/aliases.json`), never
> through a single player ID.

> [!WARNING]
> **Point-by-point rows carry no player IDs, ever.** They are plain text in the
> point table (`#NN First Last`), while the rosters on the same page carry IDs.
> IDs attach to points by matching the point name against **that game's roster**,
> order-insensitively (`ultiorg.canon`).

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

A **past** season returns `403 Event is not available for external access` —
measured: `playerscsv.php?season=KESA2026` → 200, `?season=KESA2025` → 403. CSV is
therefore a current-season convenience and never a bulk-history path; history comes
from the HTML views.

`playerscsv.php` has **no player ID column** — it splits `FirstName`/`LastName`. The
six exports join to the rest of the data only by team name and player name.

> [!WARNING]
> `?view=ext/export` is the HTML page that *links* these files; it is not a CSV.
> Feeding it to a CSV parser used to yield 250 rows of empty strings, silently. The
> parsers now raise `NotCsvError`, and `ultiorg.fetch_csv("players", "KESA2026")`
> returns the file.

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
