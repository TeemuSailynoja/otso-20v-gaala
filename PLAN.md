# Otso 20v — Data Cleanup, Visual Redesign & Gameplay Scraping

## Context

The current site has three problems:
1. **Data is noisy** — the scraper pulls all teams from pelikone (418 teams, 247 players), including women's, mixed, and youth divisions. Otso only plays Avoin/miehet.
2. **Visuals are team-name focused** — the Gantt chart, Bear Lineage, and team river treat "Otso 2", "Grizzly", "Polar", "Akatemia" as separate clubs. They're just roster splits of one club.
3. **No point-by-point data** — we have 562 unique Otso match results (scores, opponents, seasons) but no disc-by-disc scoring.

## Approach

### Phase 1: Filter Data Pipeline to Otso-Only Avoin

**Goal**: Re-scan pelikone but only extract Otso teams and their Avoin matches.

**Steps**:
- [x] Update `config.py` — `OTSO_PATTERNS` to only match `otso`, `grizzly`, `polar` (remove `akatemia` — it's a separate club)
- [x] Update `parsers.py` — `parse_teams_page()` to only return teams matching Otso patterns
- [x] Update `builders.py` — `build_team_timeline()` and `build_player_network()` to only process Otso data
- [x] Update `cli.py` — add `--otso-only` flag to skip non-Otso teams entirely (saves ~80% of requests)
- [x] Re-run scraper with `--otso-only` flag (67 seasons × ~3 pages/season = ~200 requests, down from ~300)
- [x] Expected output: ~116 Otso team instances, ~562 unique Otso matches, ~200 players

**Key insight**: We already have 562 unique Otso matches from the current data. The filtering just removes the ~300 non-Otso teams and their ~1,400 non-Otso team instances.

### Phase 2: Scrape Point-by-Point Gameplay Data

**Goal**: Get disc-by-disc scoring for Otso matches.

**Steps**:
- [x] Add `fetch_games_page()` to `fetcher.py` — scrapes `?view=games&season=SEASON_ID&filter=tournaments` to get game IDs, times, venues, and scores
- [x] Add `fetch_gameplay()` to `fetcher.py` — scrapes `?view=gameplay&game=GAME_ID` for point-by-point data, player rosters, final score
- [x] Add `parse_gameplay()` to `parsers.py` — extracts point-by-point scoring (scorer + assist), team rosters (goals/assists per player), final score from `<h1>`
- [x] Update `cli.py` — after fetching team cards, also fetch games list for each season, filter for Otso matches, then fetch gameplay for each Otso match
- [x] Rate limiting: 562 games × 1.5s delay = ~14 minutes of scraping. Do it in batches per season.
- [x] Cache every gameplay page (they don't change)

**Data structure per game** (verified from 3 actual gameplay pages):

**Gameplay page** (`?view=gameplay&game=GAME_ID`):
- `<h1>` title: `"Team A - Team B    SCORE - SCORE"` (e.g., "Saints - Otso Akatemia    9 - 12")
- Two `<div class="gameplay-scoreboard">` tables with player rosters:
  - `<caption>` = team name
  - Per player: `#` (number), `Nimi` (name + player card link), `Syötöt` (assists), `Maalit` (goals), `Yht.` (total)
  - Captain marked with `(C)`
- Point-by-point table: single `<tr>` with `<td>` cells
  - `class="home"` / `class="guest"` per point
  - `class="halftime"` for halftime marker
  - `title` = `"TIME SCORE SCORER -> ASSISTANT"` (e.g., `"2.35 1-0 Kantonen Miikka -> Wiklund Antti"`)

**Games list page** (`?view=games&season=SEASON&filter=tournaments`):
- Per row: "Pelin kulku" link, time, venue, home team, home score, away score, away team
- Series/division headers (e.g., "Avoin Tour 2: SM Lohko A") between groups

**NOT available**: throw types, throw-by-throw data, dates (only time), field numbers, pool info.

**Scope**: Start with 2023–2026 (most recent, ~130 games). If that goes well, expand to all 562 games.

### Phase 3: Redesign Visuals — "Otso" as One Club

**Goal**: Replace team-name-focused visuals with a club-centric narrative.

**Changes**:

#### 3a. Remove "Bear Lineage" section
- [x] Deleted the entire "Bear Lineage" section (Grizzly/Polar/Akatemia cards)
- [x] Confirmed — Grizzly and Polar were alternate names for the same team in 2019–2020, not separate clubs

#### 3b. Redesign Gantt Chart
- [x] Show "Otso" as one continuous bar from 2006–2026
- [x] Add annotations/labels for when multiple squads existed:
  - "Otso 2 formed" (2011)
  - "Grizzly/Polar split" (2019–2020)
  - "Akatemia formed" (2023)
- [x] Add milestone markers on the bar:
  - First SM medal
  - First national trophy
  - 100th match won
  - 200th match won
  - etc.
- [x] Color the main bar Otso orange, with thin annotation lines for squad splits
- [x] Tooltip shows: "Otso (Avoin)" + squad info + milestones for that year

#### 3c. Redesign Team River
- [x] Instead of separate rivers for "Otso", "Otso 2", "Grizzly", etc., show:
  - **One thick river**: "Otso" (all squads combined)
  - **Y-axis**: number of active players (sum of all Otso squad rosters that season)
  - **Optional thin overlay**: "Active squads" count (1, 2, or 3)
- [x] This shows the club's participation scale over time, not roster fragmentation

#### 3d. Update Hero Stats
- [x] Changed "6 Teams" → "200+ Players"
- [x] Kept "20 Years" and "95+ Seasons"
- [x] Added "480+ Matches" from scraped match data

#### 3e. Update Timeline
- [x] Group entries by year, show "Otso" as the team name
- [x] Add notes for squad splits: "Otso + Otso 2" or "Otso (Grizzly) + Otso (Polar)"
- [x] Removed "UFO Akatemia" from timeline (not an Otso team)

#### 3f. Update Medals & Achievements
- [x] Removed all women's division achievements (SM-kulta naiset, etc.)
- [x] Only show Otso Avoin/miehet achievements
- [x] Medal counts set to "TBD" medal data exists, use placeholder text like "Medal data from pelikone being compiled"

#### 3g. Player Network
- [x] Updated with real player names from scraped data — 247 players from Otso teams only
- [x] Updated with real player names from scraped data — 580+ unique players from Otso teams

#### 3h. Performance Heatmap & Placement Timeline
- [x] Filtered to Otso-only placements (remove non-Otso teams from standings)
- [x] Updated embedded data in `index.html` with filtered placements
- [x] Removed women's/mixed achievements from the timeline

### Phase 4: Integrate Gameplay Data into Visuals

**When gameplay data is available (Phase 2)**:

- [x] Added "Match Results" section showing:
  - Win/loss record by year
  - Average score differential
  - Notable games (big wins, close losses)
- [x] Point-by-point scoring available for all 472 games with gameplay data
- [x] Season Record cards with W-L and win % bars
- [x] Top 15 scorers from scraped gameplay data
- [x] Top 15 assist leaders from scraped gameplay data
- [x] Confirmed: no throw-type data available, so no throw-type analytics

## Files to Modify

### Data Pipeline
- `src/otso_scrape/config.py` — OTSO_PATTERNS, add GAMEPLAY settings
- `src/otso_scrape/fetcher.py` — add `fetch_games_page()` (game list), `fetch_gameplay()` (point-by-point + rosters)
- `src/otso_scrape/parsers.py` — add `parse_games_list()` (teams, scores, venues), `parse_gameplay()` (points, scorers, assists, player stats)
- `src/otso_scrape/builders.py` — filter Otso-only, add match builder
- `src/otso_scrape/cli.py` — add `--otso-only` flag, integrate gameplay scraping

### Visuals
- `index.html` — complete rewrite of sections (remove Bear Lineage, redesign Gantt/River, update hero stats, clean medals, remove non-Otso data from embedded arrays)

### Data
- `data/raw/` — re-scan with otso-only filter (overwrite old raw data)
- `data/processed/team_timeline.json` — regenerated Otso-only
- `data/processed/player_network.json` — already clean
- `data/processed/summary.json` — regenerated
- `data/processed/match_results.json` — new file: games list data (teams, scores, venues, times) + gameplay data (point-by-point, player stats) for Otso matches

## Reuse

- `fetch_url()` — already handles caching, rate limiting, polite delays
- `parse_teams_page()` — already handles both old and new HTML formats
- `parse_team_card()` — already extracts games with scores (just need to filter)
- `build_player_network()` — already deduplicates connections
- Canvas 2D chart code in `index.html` — keep the rendering logic, just change data
- Chart.js embedded in `index.html` — keep for season type pie chart
- CSS dark theme — keep as-is

## Steps Summary

1. **Filter config** — update `OTSO_PATTERNS`, add `--otso-only` flag
2. **Re-scan** — run scraper with `--otso-only`, verify ~116 Otso teams, ~562 matches
3. **Scrape gameplay** — add fetcher/parser for games list + gameplay pages, scraped 483 games across 12 seasons
4. **Rewrite index.html** — remove Bear Lineage, redesign Gantt/River/Timeline, update hero stats, clean medals, add Match Results section
5. **Commit & push** — single commit with all changes
6. **Verify** — local preview on port 3000

## Verification

- [x] `python -m otso_scrape --otso-only` runs and produces clean Otso-only JSON
- [x] `data/processed/team_timeline.json` has only Otso teams (no UFO Akatemia, no women's teams)
- [x] `data/processed/summary.json` shows correct Otso-only counts
- [x] Gameplay scraper fetches 483 games with point-by-point data (472 with full point-by-point)
- [x] `index.html` renders correctly with redesigned sections
- [x] No Finnish text remains in `index.html`
- [x] Local preview on port 3000 verified
- [x] Git commit and push to `main`
