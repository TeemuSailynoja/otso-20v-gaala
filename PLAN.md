# Otso 20v — Full Website Redesign

## Context

The current `index.html` is ~2171 lines with a dark theme and Chart.js, but it only has 2026 data — the processed JSON files were regenerated with only the latest season. The raw data has 103 season files, 483 games with full gameplay (point-by-point scorers, assists, rosters), and 163 players from raw team cards. This project rebuilds the site from the full historical dataset for the 20th anniversary gala.

> [!IMPORTANT]
> Birth year data does **not** exist anywhere in the scraped data (raw team cards, gameplay pages, or pelikone HTML). The "average age" stretch goal is not feasible without external data.

## Approach

### Architecture

Single-page application in one `index.html` with hash-based routing:

```
#           → Landing page (hero + summary stats + charts)
#players    → Searchable player grid
#player/Name → Player detail page (stats, pass network, co-occurrence, career timeline)
#timeline   → 20-year evolution animation
```

All data loaded from pre-processed JSON files. Zero build step — just serve `index.html` (GitHub Pages compatible).

### Data Processing Phase

A new Python script `build_site_data.py` processes raw data + gameplay into four JSON files:

| File | Content |
|------|---------|
| `site_data/players.json` | Per-player: seasons played (year list), first/last game date, goals/assists/total from raw data, games played from gameplay rosters |
| `site_data/pass_network.json` | Directed adjacency: `{player: {other: count, ...}, ...}` — how many assists A gave B, and how many B gave A |
| `site_data/cooccurrence.json` | Undirected matrix: `{player: {other: count, ...}, ...}` — how many games played together (from `home_players`/`away_players` in gameplay) |
| `site_data/summary.json` | Aggregate: total matches, total players, total wins/losses, goals for/against, top scorers/assists, longest careers, most connected players |
| `site_data/years.json` | Year-by-year: matches, wins, losses, goals for/against, unique roster players |

### Website Phase

- **Landing page**: Hero section with 4 stat cards, season timeline bar, win/loss chart, top players highlights
- **Player search**: Input field → filters grid of player cards (name, seasons, goals+assists)
- **Player detail**: Stats cards, pass network (Chart.js chord or Sankey-style visualization), co-occurrence heatmap (canvas), career timeline (bar chart)
- **20-year animation**: Scroll-triggered section showing evolution of matches, wins, roster size over years

### Tech Stack

- **HTML/CSS/JS** — vanilla, no framework
- **Chart.js** — reuse from existing site (v4.4.1 via CDN)
- **Canvas 2D** — for co-occurrence heatmap (smaller than Chart.js)
- **CSS Grid/Flexbox** — responsive layout
- **Existing dark theme** — keep the color palette, adapt for new sections

## Files to Modify

| File | Action |
|------|--------|
| `index.html` | **Replace** — complete rewrite as SPA |
| `build_site_data.py` | **Create** — data processing script |
| `site_data/players.json` | **Create** — player stats |
| `site_data/pass_network.json` | **Create** — pass connections |
| `site_data/cooccurrence.json` | **Create** — co-occurrence matrix |
| `site_data/summary.json` | **Replace** — full historical summary |
| `site_data/years.json` | **Create** — year-by-year evolution |
| `.gitignore` | **Update** — add `site_data/` to git tracking (it's new processed data) |

## Reuse

| Existing Code | File | What to Reuse |
|---------------|------|---------------|
| Dark theme CSS variables | `index.html:14-28` | `--bg`, `--card`, `--orange`, `--pink`, `--blue`, `--green`, `--purple`, `--gold`, `--text`, `--muted`, `--border` |
| Font imports | `index.html:8` | Space Grotesk + Inter from Google Fonts |
| Chart.js CDN | `index.html:7` | Chart.js 4.4.1 |
| Hero stat card style | `index.html:79-94` | `.hero-stat` layout |
| Section layout | `index.html:110-116` | `.section`, `.section-header` |
| Chart card style | `index.html:121-133` | `.chart-card`, `.grid-2` |
| Fade-in animation | `index.html:265-270` | `.fade-in` class |
| Player network builder | `src/otso_scrape/builders.py:55` | Logic for co-occurrence (adapt for gameplay data) |
| Is Otso team filter | `src/otso_scrape/parsers.py:is_otso_team()` | Team name matching |
| Season year extraction | `parse_data.py:SEASON_TYPES` + pattern matching | Year from season_id |

## Steps

### Phase 1: Data Processing

- [ ] Create `build_site_data.py` with imports and config
- [ ] Implement `load_raw_data()` — reads all `data/raw/*.json` files
- [ ] Implement `load_gameplay_data()` — reads `data/processed/match_results.json`
- [ ] Implement `build_players()` — aggregate per-player stats from raw + gameplay:
  - Seasons played (deduplicated year list)
  - First and last game year
  - Total goals, assists, points (from raw team cards)
  - Games played (count of gameplay roster appearances)
- [ ] Implement `build_pass_network()` — from gameplay points:
  - For each point with scorer+assist: `pass_network[scorer][assistant] += 1`
  - Also track reverse: `pass_network[assistant][scorer] += 1` (who passed TO you)
  - Filter to only Otso players (names appearing in Otso rosters)
- [ ] Implement `build_cooccurrence()` — from gameplay rosters:
  - For each game, for each pair of players on the same Otso roster: `cooc[p1][p2] += 1`
  - Undirected (symmetric matrix)
  - Only Otso players
- [ ] Implement `build_summary()` — aggregate stats for landing page
- [ ] Implement `build_years()` — year-by-year evolution data
- [ ] Write all JSON files to `site_data/`
- [ ] Run script and verify output sizes

### Phase 2: Website

- [ ] Write HTML skeleton with hash routing structure
- [ ] Implement CSS (reuse existing variables, adapt layout)
- [ ] Implement router: `#`, `#players`, `#player/Name`, `#timeline`
- [ ] Build landing page:
  - Hero with 4 stat cards (matches, players, wins, seasons)
  - Summary section: win/loss bar chart, goals for/against chart
  - Top players highlights (top 5 scorers, top 5 assists, longest careers)
- [ ] Build player search page:
  - Search input with debounce
  - Grid of player cards (name, seasons, goals+assists)
  - Click → navigate to `#player/Name`
- [ ] Build player detail page:
  - Stats cards (matches, seasons, goals, assists, points, goals/match)
  - Pass network chart (bar chart: top 10 receivers, top 10 givers)
  - Co-occurrence chart (bar chart: top 10 teammates)
  - Career timeline (bar chart: matches per year)
- [ ] Build 20-year timeline page:
  - Roster size over years (line chart)
  - Matches/wins over years (stacked bar)
  - Win rate over years (line chart)
- [ ] Add smooth scrolling, fade-in animations
- [ ] Responsive design (mobile-friendly)
- [ ] Local preview and test

### Phase 3: Polish

- [ ] Add Finnish translation toggle (simple object-based i18n)
- [ ] Optimize JSON file sizes (compress if needed)
- [ ] Add favicon / meta tags for GitHub Pages
- [ ] Commit and push

## Verification

1. **Data**: `python build_site_data.py` runs cleanly, outputs 5 JSON files
   - `players.json`: ~400 players with stats
   - `pass_network.json`: player→player adjacency, total edges > 1000
   - `cooccurrence.json`: player→player adjacency, total edges > 1000
   - `summary.json`: correct totals (483 games, ~400 players, wins/losses match match_stats.json)
   - `years.json`: 12 years of data (2015-2026)
2. **Website**: `python -m http.server 3000` serves the site
   - Landing page loads, hero stats are correct
   - Player search filters correctly
   - Player detail page shows stats, charts render
   - Timeline page shows year-by-year evolution
   - All charts use Chart.js and render without errors
   - Mobile layout works (viewport meta, flex-wrap)
3. **GitHub Pages**: Site works as static files (no server-side code needed)

## Known Limitations

- **No birth years** — average age cannot be computed; omit from the 20-year animation
- **Player count discrepancy** — raw data has 163 players, gameplay has ~400 scorers/assistants. The site will include all players who appear in any Otso gameplay roster (more complete).
- **2024 inflated** — the `2024.123` season file adds extra games to 2024 count; document this in the data
