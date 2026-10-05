# Otso 20 Years — Ultimate Frisbee Visualization

Interactive visualization for the 20th anniversary of Otso Ultimate Frisbee club (est. 2006, Espoo, Finland).

## Features

- **Landing page**: 20-year summary stats, trophy record (golds and podiums, Kesä/Talvi split), top scorers, assists leaders, yearly trends
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
build_site_data.py  — turns the corpus into the JSON the page reads
teams.yaml          — which club this site is about: squad names, which is the flagship,
                      how each is printed. The library has no club baked in.
src/ultiorg/        — the library: fetch, cache, parse, repair, analyse, query Ultiorganizer data
site_data/          — generated JSON the SPA fetches
  players.json      — per-player stats (170 KB)
  pass_network.json — directed pass connections (129 KB); `given[X][Y]` = X assisted Y,
                      `received[X][Y]` = X was assisted by Y
  cooccurrence.json — co-occurrence matrix (187 KB)
  summary.json      — aggregate stats (7.6 KB)
  trophies.json     — season-level gold/silver/bronze record (15 KB)
  years_otso.json   — year-by-year for the flagship squad; `_summer` / `_winter` variants, and
                      `years_all_bears*` for every squad of the club
  years.json, players.csv, player_names.txt, season_mapping.json — orphans: the page fetches
                      none of them and the build no longer writes `years.json`. Phase 11 deletes
                      the lot (see `plans/pelikone-library-refactor.md`).
data/
  raw/              — season parses (tracked) + archived game HTML (gitignored)
  cache/            — per-URL HTTP cache with a freshness policy (excluded from git)
  processed/        — match_results.json: the point-by-point corpus (tracked in git)
  private/          — birthdays CSV: personal data, never committed (excluded from git)
  store.sqlite      — the fact store, rebuilt from the corpus (excluded from git)
```

## Generating data

The library is installed with [uv](https://docs.astral.sh/uv/): `uv sync`, then `uv run ultiorg …`.

```bash
ultiorg fetch all-seasons --gameplay   # crawl every season, archive every game page
ultiorg merge                          # everything on disk -> data/processed/match_results.json
ultiorg store                          # corpus -> data/store.sqlite
python build_site_data.py              # corpus -> site_data/
```

`merge` is idempotent and deterministic: it recomposes the corpus from the union of the corpus
itself, the season files and the cached games pages, re-parsing every game's point-by-point from
its archived HTML when that HTML is present, and carrying the stored rows when it is not. Running
it on a fresh clone reproduces the committed corpus byte for byte — that is a test
(`tests/test_corpus.py`).

**A fresh clone can rebuild the site.** `git clone` → `uv sync` → `ultiorg merge` →
`python build_site_data.py` reproduces every file in `site_data/` byte for byte, with one
exception: `avg_age` / `avg_age_known` in `years*.json`, which come from the gitignored
`data/private/birthdays.csv`. That is deliberate — the site publishes an aggregate of personal
data, never the data itself, so a clone without that file simply omits the two fields. To refresh
from the source instead of rebuilding from what is tracked, run `ultiorg fetch all-seasons
--gameplay` first; it is polite (1.5 s between requests, per-kind freshness) and reports what it
cost.

Every command ends by reporting what it cost the server (`cache hits … | network requests …`).
Requests are spaced 1.5 s apart, cached per URL with a freshness policy per page kind (archived
games never expire, current-season pages go stale after 6 h, index pages after 7 days), and
`--dry-run` reports what it would fetch without sending anything. `ultiorg cache stats` shows what
is held.

## Asking questions

The fact store is joinable, so composite questions are queries rather than scripts:

```bash
ultiorg player "Lehto Santtu" --connections 10
ultiorg player "Lehto Santtu" --scoring --possession defense --since 2022
ultiorg defense Otso
ultiorg sql "SELECT season_id, COUNT(*) FROM games GROUP BY 1 ORDER BY 2 DESC LIMIT 5"
```

Names work in either word order (point rows write `Last First`, rosters write `First Last`). A
person is a cluster of pelikone player IDs — the site mints a new ID per registration, so 904
roster names carry 6,175 IDs — and the store joins them by person key. `--json` makes any of these
an agent's input. `ultiorg sql` is the escape hatch for questions the helpers do not cover.

## Repairs

Three defects are recorded in the committed corpus, so the fixes are commands rather than
one-off scripts. All three are idempotent — a no-op on current data — and all three are tested.

- `ultiorg repair point-fields` — the pelikone points table is `Pisteet | Syöttäjä | Maali | Aika`
  (score, **passer**, **goal**, time). The old scrapers stored cells[1] and cells[2] as `scorer`
  and `assist`, i.e. swapped, so every point object written before 2026-10 had the two names under
  the wrong key. This renames them in place.
- `ultiorg repair dedupe-points` — the gameplay page renders its point table twice (one copy in
  `div.page_middle`, one in `div.content`) and the old scraper walked every `<tr>` and stored both:
  10,793 of 29,270 stored rows were phantom, which made the assist bars on a player page read 2×
  reality. `parse_gameplay` now reads only the content copy; this repairs the rows on disk.
- `ultiorg repair rosters` — 132 of 795 games stored a roster smaller than their own archived HTML
  shows, which dropped 10% of all points from the defense slides and hid players from games they
  played. It merges rather than replaces, so no stored name is lost, and it does not touch points:
  for a few games the archived page no longer matches what was scraped.

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

## QR Code On Screen (`?qr`)

Append `?qr` to any URL to put a scannable QR code for that page in the top-left corner of the
hero — the use case is the site running on a big screen at the gaala while people scan from a
few metres away:

```
https://<username>.github.io/otso-20v-gaala/?qr
https://<username>.github.io/otso-20v-gaala/?qr#/player/Roni%20Hotari
```

The code is a corner card, so the page and its carousel stay usable; clicking it opens the
full-size version (`?qr=full` opens that directly). It is hidden below 760px viewport width — a
corner code is for a projector, not a phone.

The code encodes the same URL with `?qr` removed, so scanning opens the page rather than
another overlay, and the hash route is kept — a code for one player page is the point. In the
full-size version Esc or a click closes it and drops the flag from the address bar. Opened from
`localhost` the code says so, because a local address is not scannable by anyone else's phone.
The encoder (~24 KB) is fetched from jsDelivr only when `?qr` is present; if it cannot be
fetched, the address is printed in text instead.

## Data Sources

- **ultimate.fi/pelikone**: Season team cards, match results, point-by-point gameplay. The backend
  is [Ultiorganizer](https://github.com/ktolonen/ultiorganizer), open-source PHP; `ultiorg` is
  written against that backend, not against Otso, so another instance is a `--base-url` and another
  club is a `teams.yaml`. Every parser and analytics builder takes a `FocusTeam` and filters only
  when given one; `build_site_data.py` passes this repo's `teams.yaml`, and `ultiorg --teams PATH`
  picks it up.
- **104 season files**: 2006–2026 (including SM, XSM, Beach, Hallitour, Kesa, Talvi)
- **795 games**: With full point-by-point gameplay data (18,681 points)
- **171 unique players**: Across 20 years (main Otso teams only, excludes Akatemia)
- **Trophy record**: derived from the `placements` tables (Kulta/Hopea/Pronssi) of the season-deciding
  event of each year, Avoin division only — 23 gold, 3 silver, 4 bronze across the 40 seasons Otso
  contested (21 summer 2006–2026, 19 winter). Tour stops are regular-season events and are not counted.
  **Talvi 2020 was not played** — cancelled because of the covid pandemic.

## Tests

```bash
uv run pytest            # 219 tests, offline; network-marked tests are deselected by default
uv run pytest -m network # the two live smoke tests against ultimate.fi
```

The parser tests are characterization tests against archived pages (`tests/fixtures/`,
`tests/golden/`): they pin what the scrapers produce today, including the places where the site is
inconsistent, so a parser change has to be a decision rather than an accident. The corpus tests pin
the numbers the site publishes.

## Known Limitations

- Birth years are not in the Ultiorganizer data at all. They come from a separate PDF export via
  `extract_birthdays.py`, which stays in this repo (not the library) and writes only to the
  gitignored `data/private/`; the site uses it for one aggregate — the mean roster age per year.
- **Player names are not identity.** pelikone assigns a new player ID per registration, and some
  people are written two ways (a middle name appears and disappears). The library never merges two
  spellings on its own: merges are asserted by a human in `config/aliases.json`, and everything it
  cannot attribute is reported, not dropped. One proposed merge (Touko Väänänen, 115 defense points)
  is still open.
- Season-card totals and point-by-play totals are separate scrapes and do not fully agree. For
  82 players the play-by-play holds more goals or assists than their season card (651 points
  site-wide, 3% of all points), concentrated in tour sub-seasons the card scrape missed. The
  header stat block follows the card; the assist bars follow the play-by-play.
- Finnish translation deferred (stretch goal).
