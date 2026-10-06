# Otso 20 Years — Ultimate Frisbee Visualization

Interactive visualization for the 20th anniversary of Otso Ultimate Frisbee club (est. 2006, Espoo, Finland).

## Features

- **Landing page**: 20-year summary stats, trophy record (golds and podiums, Kesä/Talvi split), top scorers, assists leaders, yearly trends
- **Player directory**: Searchable grid of all 163 players with quick stats
- **Player detail**: Per-player stats, assist networks, teammate co-occurrence charts
- **Timeline**: Year-by-year evolution with win rates, roster sizes, goal differentials

## Tech Stack

- **Static site**: `index.html` is a shell — markup, the route containers, one module script.
  The rendering lives in `js/` as ES modules the browser loads directly: no bundler, no build
  step, so GitHub Pages serves exactly the files in this repo (client-side hash routing:
  `#/`, `#/players`, `#/player/<player-id>`, `#/timeline`, `#/frenemies`; a `#/player/Name`
  URL from an old bookmark or QR code resolves to the id and the address is rewritten)
- **Charts**: Chart.js 4 (loaded from CDN)
- **Styling**: CSS Grid/Flexbox, CSS custom properties, dark theme
- **Data processing**: Python 3.12+ (`build_site_data.py`)

## Project Structure

```
index.html          — the SPA shell: markup, the page containers, one module script (172 lines)
css/site.css        — every rule the page uses, in one file the browser caches
build_site_data.py  — turns the corpus into the JSON the page reads
site_contract.py    — what site_data/ must contain: the shape of every file, the manifest, the
                      version. Checked at build time, and again by the page on load
teams.yaml          — which club this site is about: squad names, which is the flagship,
                      how each is printed. The library has no club baked in.
js/                 — ES modules the page imports, no build step:
  main.js           — entry point: load the data, wire the pages, start the router
  state.js          — DATA, and the one place it is loaded
  router.js         — which page is active, and what renders for it
  data.js           — fetches through the manifest, validates against the schema, hands the page DATA
  contract.js       — the browser half of the shape check (pure; also runnable under node)
  people.js         — the decoder: key -> name, and a name in a URL -> key
  check_load.mjs    — the same loader under node, with fetch() reading the files on disk
  format.js         — era colours, stat bars, medals, season words, the seeded RNG
  categories.js     — the math behind the home page's category slides (pure: takes DATA, returns rows)
  badges.js         — the year badges the timeline shows (pure: takes the seasons, returns the badges)
                      and the season stories they quote
  qr.js             — the `?qr` badge and overlay
  pages/            — home, players, player detail, frenemies
  timeline/         — the year stream, the sticky year HUD, the team cloud
src/ultiorg/        — the library: fetch, cache, parse, repair, analyse, query Ultiorganizer data
site_data/          — generated JSON the SPA fetches, keyed by player id
  manifest.json     — what the build published, at which version, and which files the page reads
  schema.json       — the shape of every file above; checked at build time and on page load
  names.json        — every key used below -> the name to print. The only decoder.
  players.json      — per-player stats (168 KB)
  pass_network.json — directed pass connections (84 KB); `given[X][Y]` = X assisted Y,
                      `received[X][Y]` = X was assisted by Y
  cooccurrence.json — co-occurrence matrix (117 KB)
  summary.json      — aggregate stats (9.0 KB)
  trophies.json     — season-level gold/silver/bronze record (15 KB)
  data_quality.json — what the numbers do not know: how keys were minted, id clusters,
                      points with no scorer, points of unknown possession, seasons where the
                      season card and the play-by-play disagree, and which rows' zeros are a
                      coverage gap rather than a fact (12 KB)
  years_otso.json   — year-by-year for the flagship squad; `_summer` / `_winter` variants, and
                      `years_all_bears*` for every squad of the club

Nothing else is written by the build, and anything sitting in `site_data/` that the build did
not write is **reported on every run, not deleted** — four such files (`years.json`,
`players.csv`, `player_names.txt`, `season_mapping.json`) are still served and still in git,
because while the site is being restructured an unwritten file may be one the next phase wants
back. `python build_site_data.py --prune` deletes them once that is decided.
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

## Identity and keys

Nothing in this repo is keyed by a name, because a name is not a key. The point table writes
`Last First`, rosters write `First Last`, diacritics drift, and pelikone issues a **new player id
for every registration** — measured on the archived corpus, 907 people carry 6,175 ids, and one
long-career player holds 69 of them. So:

- **person key** — `canon(name)`: lowercase, accents kept, tokens sorted, so `Santtu Lehto` and
  `Lehto Santtu` collide. This is what the library and the fact store use.
- **alias** — `config/aliases.json` is the only place two spellings become one person, and every
  entry is a human assertion. Nothing merges on similarity.
- **site key** — the lowest pelikone id in the person's id cluster, or `name:<canon>` when no
  roster ever carried an id for that name. Deterministic across rebuilds, clickable through to a
  pelikone player card, and the `name:` prefix says out loud that it is not an id.

`site_data/names.json` maps every site key to the name to print; the build refuses to write a file
whose keys it cannot name. `site_data/data_quality.json` is the honesty report: how keys were
minted, how big the id clusters are, which points name no scorer (73), which have unknown opening
possession (287), which names join no roster at all, which seasons' goals come from the season
card rather than the point table, and — in `point_table_coverage` — which rows' defense zeros
are a coverage gap instead of a fact.

**Every player row answers all seven defense questions.** `defense_goals + offense_goals ==
`total_points` by construction, because each credited point increments exactly one bucket and
exactly one goal, so a row that publishes `total_points: 0` has already said the other four are
zero; they used to be absent for 19 of 171 rows, which read as unknown and forced the schema to
call them optional. 16 of those 19 are corroborated by the season card too — 0 goals in every Otso
squad-season they appear in, and the point table never names them as scorer or passer on an Otso
side — so "never scored" is a fact for them. The other 3 have published goals that come from the
card alone, and `point_table_coverage` names them. Note also that `defense_assists` counts the
assists that arrived on *this player's own goals*, not assists they made: the passer side lives
in `pass_network.json`.

**The data contract.** `site_data/manifest.json` and `site_data/schema.json` are written by
`site_contract.py`, and they replace guessing. The manifest lists every published file with its
size and whether the page reads it, plus a `version` — a hash of the data and the schema together,
which is what the page puts in `?v=` for cache busting. There is no longer a `DATA_VERSION`
stamped into a comment in `index.html`. `schema.json` describes the shape of every file, and both
halves check it: the build refuses to write a file that does not fit (and a JSON file with no
declared shape is itself a failure), and `js/data.js` validates on load, so a field that moved
fails with a banner naming the file and the field instead of rendering an empty grid. The shape
language is deliberately tiny and implemented twice — `site_contract.py` and `js/contract.js` —
and `tests/test_contract.py` runs both over the built files so they cannot drift.

Everything the page knows about a person is keyed by that person's site key, not by their name —
pelikone mints a new id per registration, so a name is not a stable key and one person arrives
under many of them. `js/people.js` is the only module that reads `names.json`: `nameFor(key)` for
the two places a name gets printed, `resolvePlayerKey(param)` for the one place a name arrives
from a URL. A route param that is not a key is rewritten to its key once, so an old bookmark or a
printed QR code lands on the same page and leaves a canonical address behind.

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

The page sets `<base href="/otso-20v-gaala/">`, because that is the path GitHub Pages serves it
under. So every relative URL — `js/main.js`, `site_data/manifest.json` — resolves against
`/otso-20v-gaala/`, and serving the repo at `/` 404s the whole module graph: you get the shell
with no data and no error in the page itself. Serve the **parent** directory and visit the repo
name:

```bash
cd .. && python -m http.server 8000
# Visit http://localhost:8000/otso-20v-gaala/
```

`tools/render_gate.sh <outdir>` does that for you and dumps the rendered DOM of eight routes with
headless Chromium; `tools/dump_diff.py A B` compares two dumps with the `<style>`/`<script>`
elements reduced to their attributes. That pair is the Phase 11 gate: a refactor of the frontend
is only proven not to have changed the page if the rendered DOM is byte-identical, because the
page is built at runtime and no Python test can see it.

The eight routes are not seven pages: `#/player/Roni%20Hotari` and `#/player/6890` are the same
person reached two ways — a name from an old QR code, which the router rewrites to the key, and
the key every link now writes. Their dumps are byte-identical, which is the redirect proved from
outside the code.

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
https://<username>.github.io/otso-20v-gaala/?qr#/player/6890
```

The id form is what the page links to now; `#/player/Roni%20Hotari` still works and redirects to
the id, which is how the codes printed for the 2024 gaala keep working.

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
- **171 unique players**: Across 20 years — every squad of the club, **including Otso Akatemia**,
  its development squad. Another club's development squad (`UFO Akatemia`) is not an Otso team and
  never counts; the club substring in `teams.yaml` is what decides it.
- **Which squad scope decides what**: `matches()` (every squad, Akatemia included) drives the career
  table, the pass network, the co-occurrence matrix, the win/loss record and the trophy entries.
  `is_main()` (the flagship squad only) is what keeps Akatemia out of `years_otso.json`; the
  `years_all_bears*` files show every squad.
- **Trophy record**: derived from the `placements` tables (Kulta/Hopea/Pronssi) of the season-deciding
  event of each year, Avoin division only — 23 gold, 3 silver, 4 bronze across the 40 seasons Otso
  contested (21 summer 2006–2026, 19 winter). Tour stops are regular-season events and are not counted.
  **Talvi 2020 was not played** — cancelled because of the covid pandemic.

## Tests

```bash
uv run pytest            # 267 tests, offline; network-marked tests are deselected by default
uv run pytest -m network # the two live smoke tests against ultimate.fi
node --test tests/js/*.test.mjs   # the page's own 49 tests, on their own
```

The parser tests are characterization tests against archived pages (`tests/fixtures/`,
`tests/golden/`): they pin what the scrapers produce today, including the places where the site is
inconsistent, so a parser change has to be a decision rather than an accident. The corpus tests pin
the numbers the site publishes.

`tests/js/` is the page's own suite, run by `node --test` and wrapped by `tests/test_js.py` so one
command covers both halves. It tests the rules the page asserts about the club — that a "rate" needs
100 games to mean anything, that a trio needs all three edges, that a founder's ★ needs 2006 *and*
2023, that a name in an old QR code still finds its player — against made-up squads, so a rule can
be tested in cases the real record never produces. The math had to be pulled out of the renderers
first: `js/categories.js` and `js/badges.js` are pure functions that take their data as an argument,
which is what makes them testable at all. `tests/test_js.py` asserts the pass count, because a JS
suite that silently collected nothing would otherwise report success.

`tests/js/season_stories.test.mjs` is the odd one out: it reads the real corpus,
because it exists to keep the hand-written season notes in `js/badges.js` honest.
Six of them contradicted the corrected numbers rendered beside them — a "biggest
single-year intake" under a year whose roster had dropped — so every number and
every superlative in a note is now measured against `site_data/`.

## Known Limitations

- Birth years are not in the Ultiorganizer data at all. They come from a separate PDF export via
  `extract_birthdays.py`, which stays in this repo (not the library) and writes only to the
  gitignored `data/private/`; the site uses it for one aggregate — the mean roster age per year.
- **Player names are not identity.** pelikone assigns a new player ID per registration, and some
  people are written two ways (a middle name appears and disappears). The library never merges two
  spellings on its own: merges are asserted by a human in `config/aliases.json`, and everything it
  cannot attribute is reported, not dropped. One proposed merge (Touko Väänänen, 115 defense points)
  is still open.
- **Season-card totals and play-by-play totals are separate scrapes and do not fully agree.**
  The career table takes the **larger** of the two for each person-season, never the sum: of the
  1,302 person-seasons that carry both, 1,123 agree exactly, the card is higher on 173 (games the
  scrape never got) and the play-by-play on 6. Summing them — what the site did until this refactor
  — doubled most careers: 21,799 published goals against the 10,414 scored in the games
  `summary.json` counts. `data_quality.json → career_sources` lists every season where the two
  disagree, biggest gap first, so a season whose numbers rest on the card alone is visible rather
  than mistaken for a complete season. The pass network is play-by-play only, which is why
  `sum(received[player])` equals a player's published goals for 113 of 171 players and falls short
  (never overshoots) for the rest.
- Finnish translation deferred (stretch goal).
