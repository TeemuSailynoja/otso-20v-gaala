# Otso 20 Years — Ultimate Frisbee Visualization

Interactive visualization for the 20th anniversary of Otso Ultimate Frisbee club (est. 2006, Espoo, Finland).

## Features

- **Landing page**: 20-year summary stats, top scorers, assists leaders, yearly trends
- **Player directory**: Searchable grid of all 163 players with quick stats
- **Player detail**: Per-player stats, assist networks, teammate co-occurrence charts
- **Timeline**: Year-by-year evolution with win rates, roster sizes, goal differentials

## Tech Stack

- **Static site**: Single `index.html` with client-side hash routing (`#/`, `#/players`, `#/player/Name`, `#/timeline`)
- **Charts**: Chart.js 4 (loaded from CDN)
- **Styling**: CSS Grid/Flexbox, CSS custom properties, dark theme
- **Data processing**: Python 3.12+ (`build_site_data.py`)

## Project Structure

```
index.html          — SPA frontend (47 KB)
build_site_data.py  — Data processing pipeline
site_data/          — Generated JSON data files
  players.json      — Per-player stats (81 KB)
  pass_network.json — Directed pass connections (40 KB)
  cooccurrence.json — Co-occurrence matrix (123 KB)
  summary.json      — Aggregate stats (7.5 KB)
  years.json        — Year-by-year evolution (1.7 KB)
data/
  raw/              — Scraped season data (103 files, excluded from git)
  processed/        — Processed match data (excluded from git)
```

## Generating Data

```bash
python build_site_data.py
```

Reads `data/raw/*.json` and `data/processed/match_results.json`, outputs to `site_data/`.

## Local Development

```bash
python -m http.server 8000
# Visit http://localhost:8000
```

## GitHub Pages Deployment

1. Push to `main` branch
2. Go to Settings → Pages → Source: "Deploy from a branch"
3. Select `main` branch, `/ (root)` folder
4. Site will be live at `https://<username>.github.io/otso-20v-gaala/`

## Data Sources

- **pelikone.fi**: Season team cards, match results, point-by-point gameplay
- **103 season files**: 2006–2026 (including SM, XSM, Beach, Hallitour, Kesa, Talvi)
- **483 games**: With full point-by-point gameplay data
- **163 unique players**: Across 20 years (main Otso teams only, excludes Akatemia)

## Known Limitations

- Birth year data not available in scraped sources
- Finnish translation deferred (stretch goal)
- Some player names may appear in multiple formats if not deduplicated
