# 🐻 Otso 20 Vuotta — Ultimate Visualization Redesign

## Context

Otso (Espoo Ultimate Club) celebrates 20 years (2006–2026) of men's ultimate frisbee. The story is rich:
- **2006–2010**: Single Otso team, dominating every season
- **2011–2018**: Growth → split into Otso + Otso 2, sometimes Otso 3 in winters (max 3 teams)
- **2019–2020**: Bear-themed year — instead of Otso/Otso 2, two equally strong teams named **Grizzly** and **Polar**
- **2021–2022**: Return to Otso + Otso 2
- **2023–2025**: Three teams — Otso, Otso 2, **Akatemia** (academy team)

All compete in the avoin (open) division. 95+ seasons, many medals.

The current site has basic Chart.js charts that don't tell the story. We need an **immersive, interactive, scroll-driven** experience.

## Approach

### Part A: Data Pipeline (Python)
- [x] Scrape ultimate.fi/pelikone for match data, team rosters, and player stats
- [x] Parse into meaningful statistics (playometrics)
- [x] Store processed data as JSON/CSV (committed to GitHub)
- [x] Raw full dataset excluded from git (.gitignore)
- [ ] Scrape historical seasons (only 2026 scraped so far)

### Part B: Visualization
- [x] Interactive Gantt chart of team evolution (Canvas 2D with hover tooltips)
- [x] Team count river (stacked area chart, Canvas 2D)
- [x] Performance heatmap (Canvas 2D with hover tooltips)
- [x] Medal timeline (placeholder data, animated counters)
- [x] Player social network (Canvas 2D force-directed with click-to-profile)
- [x] Player timelines and searchable profiles (search + modal)

### Design Decisions

- **Dark theme** — Keep existing
- **Max 3 teams per year** — Confirmed
- **Grizzly/Polar** — One year where two equally strong teams replaced Otso/Otso 2 (not a family tree)
- **Performance/medal data** — Placeholders for now (will be filled from pelikone)
- **Responsive** — Both desktop and mobile must work well
- **Deployment** — GitHub Pages from current repo (`teemusailynoja.github.io/otso-20v-gaala/`)

## Files to Modify

- **`index.html`** — Complete rewrite of the visualization sections
- **`parse_data.py`** — Python script for scraping/parsing pelikone data
- **`data/`** — Processed data (JSON/CSV) committed to GitHub
- **`.gitignore`** — Exclude raw downloaded data

## Reuse

- **Chart.js** (CDN) — Keep for polar area and doughnut charts
- **Color palette** — `--orange`, `--pink`, `--blue`, `--green`, `--purple`, `--gold` CSS variables
- **Fonts** — Space Grotesk + Inter (already loaded)
- **Dark theme** — CSS variables and card styles
- **Git remote** — Already configured: `origin git@github.com:TeemuSailynoja/otso-20v-gaala.git`

## Steps

### Phase 1: Pelikone Data Research ✅ COMPLETE
- [x] Visit ultimate.fi/pelikone and examine the URL structure
- [x] Map out the data available: team rosters, match records, player stats, scores, assists
- [x] Identify API endpoints or HTML patterns for scraping
- [x] Determine which pages exist for: team cards, player lists, standings, games
- [x] Document the data structure in `docs/pelikone-structure.md`

### Phase 2: Python Data Pipeline ✅ COMPLETE
- [x] Create `parse_data.py` with scraping functions
- [x] Parse team rosters per season (18 teams found for KESA2026)
- [x] Parse match records (4 games parsed for Otso in KESA2026)
- [x] Parse player stats from team cards (18 players) and player lists (36 all-time)
- [x] Compute playometrics: per-season scores, player stats, team performance
- [x] Output processed data as JSON to `data/` directory
- [x] Test with sample year KESA2026 (year classification, team timeline, player network)

### Phase 3: Hero Enhancement ✅ COMPLETE
- [x] Add particle canvas with floating bear paw prints (Canvas 2D, 40 particles desktop, 15 mobile)
- [x] Add subtle gradient animation to hero background (CSS keyframes)
- [x] Keep existing stats but add a "scroll to explore" arrow animation (bounce animation)
- [x] Add fade-in animations for hero elements (staggered)

### Phase 4: Team Evolution Gantt Chart ✅ COMPLETE
- [x] Build custom canvas-based Gantt chart showing each team as a horizontal bar across 2006–2026
- [x] Color-code by team type (Otso=orange, Grizzly=pink, Polar=blue, Akatemia=green, Otso 2=purple, Otso 3=gold)
- [x] Add hover tooltips with season details
- [x] Add scroll-driven year highlight (fixed panel, top-right)

### Phase 5: Team Count River ✅ COMPLETE
- [x] Custom canvas stacked area chart showing total active teams per year
- [x] Smooth bezier curves, gradient fills
- [x] Color-coded layers for each team type
- [x] Peak years visible in data (2013, 2014, 2017 with 3 teams)

### Phase 6: Performance Heatmap ✅ COMPLETE
- [x] Grid: rows = years, columns = tours (Tour 1, Tour 2, Tour 3, Finaalit, Kesä, Talvi)
- [x] Each cell colored by placement (1st=gold, 2nd=silver, 3rd=bronze, 4+=muted)
- [x] Placeholder values for missing years (marked with comments for future replacement)
- [x] Hover shows exact placement and tournament name

### Phase 7: Medal Timeline ✅ COMPLETE
- [x] Medal cards with animated counters (15+ kultaa, 10+ hopeaa, 5+ pronssia)
- [x] Achievement timeline (horizontal scrolling placeholder)
- [x] Season type polar area chart
- [x] Placeholder data marked for future replacement

### Phase 8: Player Social Network ✅ COMPLETE
- [x] Build graph visualization showing player connections (played together on same team)
- [x] Nodes = players, edges = co-team appearances
- [x] Color nodes by team (Otso=orange, Otso 2=purple)
- [x] Click a player to see their timeline and stats (opens modal)
- [x] Hover tooltips on nodes
- [x] Force-directed layout simulation
- [x] Loads real player data from `data/processed/player_network.json` when available

### Phase 9: Player Profiles & Search ✅ COMPLETE
- [x] Searchable player database (search input with autocomplete)
- [x] Per-player profile modal:
  - Years active, teams played for
  - Fun stats: team count, season count, appearance count
  - Season badges
- [x] Data sourced from parsed match records (player_network.json)
- [x] Click network nodes to open player modal
- [x] Keyboard support (Escape to close)

### Phase 10: Year Explorer ✅ COMPLETE
- [x] Add a fixed pill bar at the bottom: "2006 | 2007 | ... | 2026" (glassmorphism)
- [x] Clicking a year scrolls to that year's timeline item
- [x] Auto-highlights current year on scroll
- [x] Shows summary card for selected year (top-right panel)

### Phase 11: Polish & Responsive ✅ COMPLETE
- [x] Smooth scroll between sections (CSS `scroll-behavior: smooth`)
- [x] Mobile responsive: stack Gantt vertically, simplify particles (disabled on mobile), touch-friendly
- [x] Add bear paw print decorative elements (particle system)
- [x] Performance: requestAnimationFrame for animations, passive scroll listeners
- [x] Scroll progress indicator (gradient bar at top)
- [x] Scroll-driven year highlight panel
- [x] Animated medal counters on scroll

### Phase 12: GitHub Pages Deployment ⏸ BLOCKED
- [x] Commit all changes to `main` ✅
- [x] Push to GitHub ✅
- [ ] **BLOCKED**: Repository is private — GitHub Pages requires:
  - **Option A**: Make repository public (free), then enable Pages
  - **Option B**: Upgrade to GitHub Pro/Team (allows private Pages)
- [ ] Manual steps (once repo is public or Pro):
  - Go to GitHub → Settings → Pages → Source: `main` / `/ (root)`
  - Wait ~2 minutes for deployment
  - Verify: `https://teemusailynoja.github.io/otso-20v-gaala/`

## Verification

1. ✅ **Open index.html in a browser** — All sections render, no JS errors
2. ✅ **Scroll through** — Animations trigger on scroll, Gantt chart is readable
3. ✅ **Hover interactions** — Tooltips on Gantt, Heatmap, and Network charts
4. ✅ **Year filter** — Year explorer scrolls to timeline, auto-highlights current year
5. ✅ **Mobile** — Layout adapts, no horizontal overflow, particles disabled on mobile
6. ✅ **Data accuracy** — Cross-reference with existing `teams` array (2006-2026 data)
7. ✅ **Python pipeline** — `parse_data.py` runs without errors, outputs valid JSON (KESA2026 tested)
8. ⏸ **GitHub Pages** — Not yet deployed
9. ✅ **Player search** — Search input with autocomplete, opens profile modal
10. ✅ **Social network** — Graph renders, interactive with click-to-profile

## Current Status

**All visualization phases complete. Code is committed and pushed to GitHub.**

### What's Done
- ✅ Phases 1-11: All visualization features implemented
- ✅ Code committed and pushed to `main` branch
- ✅ Data pipeline working (KESA2026 scraped)
- ✅ Processed data in `data/processed/`

### What's Blocked
- ⏸ Phase 12: GitHub Pages deployment blocked because repository is **private**
  - GitHub Pages requires **public repository** (free) or **Pro/Team account** (private)
  - **To fix**: Make repo public at GitHub → Settings → General → Danger Zone → Change visibility
  - Then enable Pages: GitHub → Settings → Pages → Source: `main` / `/ (root)`

### Site Features
- Hero section with animated bear paw particles and gradient
- Bear lineage cards (Otso, Grizzly, Polar, Akatemia)
- Gantt chart with hover tooltips
- Team count river chart (stacked area)
- Performance heatmap with hover tooltips
- Performance line chart (Chart.js)
- Medal section with animated counters
- Season type polar area chart (Chart.js)
- Player network with click-to-profile
- Player search with autocomplete
- Player profile modal
- Timeline with scroll animations
- Year explorer with auto-highlight
- Scroll progress indicator
- Scroll-driven year highlight panel
- Fully responsive (mobile-friendly)

## Technical Notes

- **Custom canvas charts**: Native Canvas 2D API (no extra library)
- **Particles**: Simple canvas-based particle system with paw print shapes
- **Animations**: CSS transitions + IntersectionObserver for scroll triggers
- **No build step**: Single HTML file, everything inline
- **Chart.js**: Keep for polar area and doughnut charts
- **Placeholders**: Mark clearly with comments for easy future replacement
- **Mobile**: Use CSS media queries, touch events for tooltips, simplified particle count on mobile
- **Python**: Use `requests` + `BeautifulSoup4` for scraping, `json` for output
- **Data storage**: Processed JSON in `data/`, raw data in `.gitignore`
- **Graph visualization**: Custom canvas or D3.js (CDN) for player network
