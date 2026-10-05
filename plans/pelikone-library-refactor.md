# Pelikone library refactor

> Extract a reusable **Ultiorganizer** client library from the gala repo, ID-key the player data,
> and replace the pile of one-off fetch scripts with one flexible CLI. The gala site becomes a
> consumer of the library.

## Context

Two things pull this repo apart:

1. It is the **20-year gala website** — a static SPA plus a data pipeline that produced
   `site_data/*.json`.
2. The **Women's National Team coaching staff** now want player information. That is a general
   "look up any player in the Finnish series" capability, which the current code cannot do: every
   path is Otso-filtered (`is_otso_team`, `OTSO_PATTERNS`). Ultiorganizer exposes **no database
   API** — only HTML pages — so the useful thing to build is a cached query layer on top of those
   pages: players, matches, and point-by-point gameplay stats for any team.
3. The gala **page itself** needs a maintainability pass. It is one 3,151-line file and 43 of 144
   commits are fixes, several of them "defensive checks for undefined DATA" and "try/catch and
   fallback values" — symptoms of an unvalidated data contract between the Python and the JS.

The Python has drifted into three generations of the same code, and the reusable generation was
started, never finished, and never installed.

## Current state (measured)

5,754 lines of Python across 12 files.

| File | Lines | Generation | State |
|---|---|---|---|
| `build_site_data.py` | 1765 | site analytics | live; imports **nothing** from `src/` |
| `parse_data.py` | 938 | monolith (Aug 2026) | superseded by `src/otso_scrape/`, never deleted |
| `src/otso_scrape/parsers.py` | 906 | package | **the maintained parser path** |
| `fetch_all_otso_games.py` | 319 | one-off scrape | inline `requests`+`bs4`, hardcoded `/home/teemu/...` |
| `fetch_gameplay_2026.py` | 234 | one-off scrape | same, with a hardcoded list of game IDs |
| `fix_player_rosters.py` | 222 | one-off repair | same, own roster-table heuristics |
| `scrape_all_games.py` | 114 | one-off | uses package via `sys.path.insert` |
| `refresh_game_rosters.py` | 102 | repair | uses `parse_gameplay` via `sys.path.insert` |
| `extract_birthdays.py` | 84 | personal data | PDF → `data/private/`, gitignored |
| `dedupe_point_rows.py` / `migrate_point_fields.py` | 150 | repair | operate on committed JSON |
| `src/otso_scrape/{cli,fetcher,builders,cache,config}.py` | 631 | package | partial |

### Duplication already causing correctness drift

- **Parsers exist twice.** `parse_data.py` carries near-copies of `parse_teams_page`,
  `parse_standings_page`, `parse_team_card`, `parse_player_list`, `is_otso_team`,
  `extract_year_from_season`, `classify_season`, `cache_key`, `fetch_url`. Those copies are
  **stale** — they lack the `div.content` double-table fix and the passer/scorer fix that
  `src/otso_scrape/parsers.py` has.
- **~860 lines of one-off scripts re-implement gameplay parsing inline**, with roster heuristics
  that disagree with the package version.
- **Name canonicalisation exists three times**: `build_site_data.normalize_name`,
  `build_site_data.canonicalize_name`, `refresh_game_rosters.canon`.
- **Otso matching exists twice with different pattern lists** — `parse_data.py` includes
  `akatemia`, `src/otso_scrape/config.py` deliberately excludes it.
- `build_site_data.py:1120` imports `BeautifulSoup` inside `build_defense_stats` and re-parses
  archived `data/raw/game_*.html` at analytics time — parsing has leaked into the site layer.

### The package is not usable as a library

- Not installed: `python -c "import otso_scrape"` → `ModuleNotFoundError`. Consumers do
  `sys.path.insert(0, "src")`.
- `__init__.py` exports 25 names but **omits `parse_gameplay`, `parse_games_list`,
  `fetch_gameplay`, `fetch_games_page`** — the gameplay API.
- No tests, no fixtures, no package README, no `py.typed`.
- `data/processed/match_stats.json` is orphaned — no script writes it.
- `cache.py:get_cache()` loads the whole `data/cache_manifest.json` — **29 MB** — and
  `fetch_url()` rewrites the entire manifest after **every** request.

## What the coaching-staff use case needs (verified live, 2026-10-05)

None of this exists in code. All of it is reachable today:

| View | Gives | Notes |
|---|---|---|
| `?view=allplayers` | **A–Z index of every registered player** → `playercard&player=<ID>` | stable IDs, canonical `First Last` display names |
| `?view=playercard&series=0&player=<ID>` | **Full career**: per-event rows — event, division, team, GP, A, G, Tot, A/G/Tot avg, Callahans, W, win% | documented at `docs/pelikone-structure.md:42`, never implemented |
| `?view=scorestatus&series=<seriesID>` | **Whole-event player scoreboard** — 263 players for Talvi 2025, sortable, all with IDs | best single page for a coaching report |
| `?view=statistics&season=…&list=playerscoreboard` | per-event top-3 scorers; `list=playerscoresall` all-time | 693 playercard links |
| `?view=allteams` / `allclubs` / `clubcard` | every team (+division, country) / club | |

Two constraints that shape the design, both verified:

> [!IMPORTANT]
> **Point-by-point rows carry no player IDs.** They are plain text:
> `title='5.00 0-1 Potrykus Patrick -> Arola Matias'`. The roster tables on the same page *do*
> carry IDs (`game_11049.html` has 30 `playercard&series=0&player=NNNN` links). So IDs attach to
> points by matching the point name against **that game's roster** — and the name order differs
> (points are `Last First`, rosters are `First Last`), so the match must be order-insensitive.
> `refresh_game_rosters.py:canon` already implements that rule.

> [!WARNING]
> **CSV exports are current-season only and have no player ID.** Verified:
> `ext/playerscsv.php?season=KESA2026` → 200, `?season=KESA2025` → `403 Event is not available
> for external access`. CSV columns are `FirstName,LastName,Jersey,TeamName,TeamAbbreviation,Club,
> Division,Country,Games,Assists,Goals,Callahans,Total`. Useful for the current season; not a bulk
> path for history.

> [!IMPORTANT]
> **The questions the staff ask are composite.** "For this player, who are their strongest
> connections, and how active are they in scoring when their team started the point on defense?" is
> not a page and not a CLI verb — it is a join across rosters, points and the pass network. That is
> the design driver for section 4: get the structures right and the questions come after.

### The frontend is one 3,151-line file with no contract

| | |
|---|---|
| `index.html` | 3,151 lines: **1,194 CSS** (289 rules) + **1,785 JS** in a single inline `<script>` + ~150 HTML |
| JS shape | 66 functions, one mutable global `DATA`, hand-rolled hash routing, `innerHTML` string templates |
| charts | only **2** `new Chart(` — the rest is hand-rolled canvas (`hud-roster-chart`, `hud-cloud`, `paw-particles`), yet Chart.js is CDN-loaded for those two |
| data | 9 JSON files fetched; `site_data/` ships **16** — `years.json`, `years_all_bears*.json`, `season_mapping.json`, `players.csv`, `player_names.txt` are dead weight on the deployed site |
| versioning | `const DATA_VERSION = '213b6f87ccac'` stamped into the HTML by a comment-marker dance (`BUILD_VERSION_START/END`) |
| identity | JS `normalize()` re-implements Python `canonicalize_name()` — two implementations of the same rule, no parity test |

The bug history is the argument for a contract, not for more defensive `try/catch`: `Fix hero
Years stat: 20, not 21`, `Fix frenemies showing Otso teams instead of opponent teams`, `Fix
renderCategories: defensive checks for undefined DATA`, `Fix renderStatsHighlights: try/catch and
fallback values for missing data`, `Fix player name: luhtala roope → Roope Luhtala`.

### The backend is named, and it is not "pelikone"

The pages link `https://github.com/ktolonen/ultiorganizer` and load `ultiorganizer.css`. The
backend is **Ultiorganizer** — open-source PHP, self-hosted, actively maintained (pushed
2026-10-05), "give every team, player, club, and country its own public page". Pelikone is one
instance of it; the Europe-wide series runs the same software (its host was not resolvable from
this machine, so instance support is designed but unverified).

That makes the package name informative and instance-agnostic: a `base_url` config, not a constant.

## Approach

### 1. Name and layout

Library **`ultiorg`**, CLI distribution **`ultiorg-cli`** (console script `ultiorg`). Lives at
`src/ultiorg/` in this repo for now; split to its own repo later by `git mv` + `git filter-repo`.
It must stay self-contained: no imports from the repo root, no absolute paths, no Otso knowledge.

```
src/ultiorg/
  __init__.py      public API (complete — includes gameplay + playercard)
  instance.py      Instance(name, base_url, UA, delay)  — 'fi-pelikone' default
  http.py          fetch with retry, rate limit, polite delay
  cache.py         per-URL content store + freshness policy (see 3)
  parsers/         one module per view: seasons, teams, standings, teamcard,
                   playerlist, games, gameplay, allplayers, playercard,
                   scorestatus, statistics
  models.py        TypedDicts/dataclasses keyed by player_id
  identify.py      name → player_id resolution (order-insensitive, per-game roster)
  store.py         dataset on disk: raw HTML + normalized JSON
  query.py         the query layer (see 4)
  analytics/       team-parameterised stats (see 5)
  cli.py           verbs below — shipped as ultiorg-cli
  py.typed
```

### 2. Player identity is the pelikone player ID

- `allplayers` index is the authority: `{player_id, display_name}`.
- Every roster-bearing page (gameplay scoreboard, `playerlist`, `teamcard`, `scorestatus`) yields
  IDs; `identify.py` resolves name-only point rows to IDs **within the scope of one game**, where
  a name collision is essentially impossible. Unresolved names are recorded, never guessed.
- Display names come from pelikone (`First Last`), not from sorted name parts. The
  sorted-parts canonicalisation stays only as the *matching* key, in one place.
- **Everything is re-keyed to `player_id`, including `site_data/`** (decided). The SPA moves to
  ID keys with a `site_data/names.json` id → display-name map for rendering.

> [!TIP]
> Re-keying is **offline and already possible** — measured, not assumed:
> - the 902 archived `data/raw/*.json` season files **already carry player IDs**
>   (`{"name": "Antti Elonheimo", "id": "27441", …}`) — season-card stats need no re-fetch;
> - `match_results.json` rosters **dropped** the IDs, but **795 of 795** archived
>   `data/raw/game_*.html` files contain `playercard&…&player=NNNN` links, so re-parsing the
>   archived HTML recovers them with **zero network requests**;
> - point rows stay name-only, so `identify.py` resolves them per game (see 4).

> [!WARNING]
> Re-keying `site_data/` breaks existing player URLs (`#/player/Roni%20Hotari`) — and the `?qr`
> feature encodes exactly those links. The router must keep a **name → id redirect** using
> `names.json`, so old bookmarks, shared links and printed QR codes still resolve.

Data-quality cases the re-key must surface rather than hide: `data/raw/Talvi2016.json` holds a
player entry with an ID and an **empty name**; some point names will not match any roster in their
game. Both go into a `data_quality.json` report with counts, and unresolved names get a
`name:<canon>` pseudo-key so no points silently disappear from the totals.

### 3. Two storage layers: an HTML cache for politeness, a fact store for queries

**Layer 1 — the page cache.** Replace the single 29 MB JSON manifest with content-addressed files
(`data/cache/<sha1(url)>.html`) plus a small index. Keeps `fetch_url` O(1) instead of re-reading
and re-writing the whole corpus per request. One-time import of the existing manifest so the 902
archived season files and 799 game pages are never re-fetched.

Freshness is **per kind of page**, not a blanket TTL — this is what makes repeat queries free and
keeps the site polite:

| Page kind | Policy | Why |
|---|---|---|
| historical season / game / playercard | **immutable** — cache forever, re-fetch only on `--refresh` | past results do not change |
| current season | TTL (default 6 h) | scores get added during a season |
| `allplayers` index | TTL (default 7 d) | new registrations only |

Plus: one delay budget per instance (1.5 s default), a hard `--dry-run` that reports what *would*
be fetched, and a request counter printed at the end of every command so the cost of a query is
visible.

**Layer 2 — the fact store.** Parsed pages land in a normalized SQLite database
(`data/store.sqlite`, gitignored, rebuilt from the cache on demand). HTML cache in, joinable
ID-keyed facts out. This is what makes the composite questions in section 4 answerable without
new code, and it replaces the flat `data/processed/*.json` files as the library's output.

### 4. A joinable fact core, so composite questions are answerable

The goal is **not one CLI verb per question**. It is that the library stores a joinable,
ID-keyed fact core and builds every analytic as a *view over those facts*, so a compound question
— "for this player, who are their strongest connections, and how active are they in scoring when
their team started the point on defense?" — is a composition over structures that already exist.

**Fact tables** (SQLite, `data/store.sqlite`):

| Table | Key | Carries |
|---|---|---|
| `players` | `player_id` | display name (pelikone `First Last`) |
| `teams` | `team_id` | name, club, division, country |
| `seasons` | `season_id` | year, type (summer / winter / tour / finals / beach) |
| `games` | `game_id` | season, home/away `team_id`, scores, venue, time |
| `appearances` | (`game_id`, `player_id`) | `team_id`, goals, assists, total — from roster tables, which carry IDs |
| `points` | (`game_id`, `seq`) | time, score, `team_id`, **`possession`**, `scorer_id`, `passer_id`, `possession_known` |
| `placements` | (`season_id`, `team_id`) | division, placement (Kulta / Hopea / Pronssi / …) |

`points.possession` is the field that unlocks the scoring-context question, and the rule that
derives it **already exists in this repo** (`build_site_data.py:1107`, merged into
`site_data/players.json` at line 1708 by canonical key) — it just lives in the site layer and
re-parses HTML at analytics time. The rule, moved into the library's gameplay parser and
*stored* per point:

1. the first point's offense side comes from the `Hyökkäys` marker in the archived game HTML;
2. after each point, **the scorer starts the next point on defense**;
3. at halftime, the team that started on defense starts on offense;
4. a scorer's side is taken from **that game's roster map**, because the scraped `side` field is
   unreliable;
5. if the marker is missing, point 1 is left unattributed and `possession_known = 0` — so rates
   stay honest instead of guessing.

**Derived views** (computed from facts, materialised so they are cheap, ID-keyed):
`pass_network` (given/received adjacency), `cooccurrence` (games together), `chemistry` (partners
ranked by combined passes + games together, normalised per game), `scoring_context` (points split
by possession, per season and career), `head_to_head`, `frenemies`, `trophies`, `years`.

**Composition** — the two example questions become:

```python
p = ultiorg.player("Lehto Santtu")            # name → player_id, resolved once
p.connections(top=10)                         # pass_network ∩ cooccurrence, weighted + per-game rate
p.scoring(possession="defense", since=2022)   # defense-initiated points: goals, assists, per-game rate
p.games(season="KESA2025")                    # appearances with roster totals
```

and anything the helpers do not cover is still reachable, because the core is SQLite:

```bash
ultiorg sql "select p.display_name, count(*) from points pt
             join players p on p.player_id = pt.scorer_id
             where pt.possession='defense' group by 1 order by 2 desc limit 20"
```

That escape hatch is deliberate: the coaching staff's agent should be able to ask the next question
we have not thought of, rather than wait for a new verb.

Cache-first throughout: a query answerable from the fact store makes **zero** requests; a query that
needs a missing page fetches it once, politely, and never again.

### 5. Analytics move into the library — they are not Otso-specific

`build_frenemies`, `build_defense_stats`, `build_pass_network`, `build_cooccurrence`,
`build_trophies`, `build_years` are generic team analytics with Otso hardcoded: `is_otso_team` is
called at **30 sites** inside them. They become the **derived views over the fact store** (section
4), parameterised by a focus-team predicate, so the coaching staff can run them against any club or
national team — which is exactly the "gameplay stats and match stats" ask. `build_defense_stats`
also stops re-parsing `data/raw/game_*.html` at analytics time: the possession it computes becomes
a stored fact.

### 6. One CLI covering the repeating usage patterns

The four one-off scripts become verbs, not scripts. A fresh clone can regenerate everything:

```
ultiorg seasons list [--since 2006]
ultiorg fetch season <SEASON_ID>            # teams, standings, cards, player lists
ultiorg fetch all-seasons [--division Naiset] [--since 2015]
ultiorg fetch games --season <ID> [--gameplay]
ultiorg fetch players-index                 # allplayers → id ↔ name
ultiorg fetch player <ID|name> [--from-file players.txt]
ultiorg fetch scoreboard --series <ID>
ultiorg players --division Naiset --team OTSO --years 2020-2026   # query, cache-first
ultiorg player "Lehto Santtu" [--json]      # career, by name or ID
ultiorg player "Lehto Santtu" --connections 10 --scoring defense  # the composite question
ultiorg game <GAME_ID> [--json]             # point-by-point, IDs resolved
ultiorg head-to-head --a OTSO --b "Helsinki Ultimate" --years 2020-2026
ultiorg sql "select …"                      # escape hatch over the fact store
ultiorg report --players players.txt --format csv|html --out report.html
ultiorg repair rosters|points|dedupe        # the three repair scripts, as commands
# global: --data-dir, --instance, --refresh, --delay, --dry-run, --json
```

### 7. The gala repo becomes a consumer

`build_site_data.py` stops parsing and stops re-implementing identity: it imports
`ultiorg.parsers` / `.models` / `.identify` / `.analytics`, and the Otso-specific knowledge moves
to a repo config (`teams.yaml`: team-name patterns to include/exclude, e.g. Akatemia). The
`build_defense_stats` HTML re-parse moves into the library's gameplay parser, which already owns
the `Hyökkäys` marker.

### 8. Report output is a later phase, not this refactor

CLI first (an agent can run `ultiorg report --players … --format csv`). The interactive HTML
report is a **separate follow-up plan**, along with a more robust page plan of its own.

### 9. The gala page: split it, keep it build-free

GitHub Pages serves static files, so the win is **zero-build ES modules**, not a bundler:

```
index.html            ~150 lines of shell + <script type="module" src="js/main.js">
css/                  base, home, players, player, timeline, frenemies
js/main.js            boot + router
js/data.js            load + validate site_data, per-page failure instead of a blank site
js/pages/*.js         home, players, player, frenemies, timeline
js/charts/*.js        the hand-rolled canvas pieces (hud cloud, roster chart, particles)
js/lib/format.js      number/date formatting
js/lib/identity.js    display-name rules — one implementation, parity-tested with Python
js/qr.js              the ?qr feature, currently inline
```

Relative module paths work under the `/otso-20v-gaala/` base path with no config.

Lookups become ID-based (`playerById(id)`, with a name fallback), and the router resolves an old
`#/player/<Name>` hash to its ID via `names.json` before rendering — the `?qr` feature encodes
player URLs, so printed QR codes and shared links must keep working.

**The data contract replaces the guesswork.** `build_site_data.py` writes
`site_data/manifest.json` (`{version, files[]}`) — replacing the `BUILD_VERSION_START/END`
comment stamp — and `site_data/schema.json` describing each file's required shape. `js/data.js`
validates on load: a missing key fails that page with a visible message, not a blank grid. The JS
stops re-canonicalising names: the Python emits canonical key + display name, so
`js/lib/identity.js` only formats.

Also: stop shipping the 7 orphaned `site_data/` files, and decide whether Chart.js is worth a CDN
load for 2 charts (the other visuals are already hand-rolled canvas).

## Files to modify

| Path | Action |
|---|---|
| `src/otso_scrape/` → `src/ultiorg/` | rename + complete (`parse_gameplay`, `fetch_gameplay`, `parse_games_list` exported) |
| `pyproject.toml` | `ultiorg` + `ultiorg-cli`, build-system, `[tool.setuptools] package-dir`, pytest, editable install |
| `src/ultiorg/parsers/allplayers.py`, `playercard.py`, `scorestatus.py`, `statistics.py` | **new** — the four views above |
| `src/ultiorg/identify.py` | **new** — name → player_id, single copy of the matching rule |
| `src/ultiorg/cache.py` | rewrite: per-URL files + index + freshness policy, one-time manifest import |
| `src/ultiorg/store.py` | **new** — the SQLite fact store (tables in section 4), rebuilt from the cache |
| `src/ultiorg/query.py` | **new** — the composition API over the fact store |
| `src/ultiorg/analytics/` | **new** — frenemies / defense / pass network / cooccurrence / trophies / years, focus-team parameterised |
| `src/ultiorg/cli.py` | rewrite as the verb set above |
| `parse_data.py` | **delete** (superseded; its stale parser copies are the bug risk) |
| `fetch_all_otso_games.py`, `fetch_gameplay_2026.py`, `fix_player_rosters.py`, `fetch_2026.py` | **delete** once CLI verbs cover them |
| `dedupe_point_rows.py`, `migrate_point_fields.py`, `refresh_game_rosters.py` | fold into `ultiorg repair …` |
| `scrape_all_games.py` | delete (covered by `ultiorg fetch games --gameplay`) |
| `build_site_data.py` | becomes a thin caller of `ultiorg.analytics`; drops local `is_otso_team` / `normalize_name` / `canonicalize_name` / inline `bs4`; emits `manifest.json` + `schema.json` |
| `teams.yaml` (new) | Otso team-name include/exclude config for the gala layer |
| `index.html` | 3,151 → ~150 lines: shell only; router gains a **name → id redirect** for old links and printed QR codes |
| `css/*.css`, `js/main.js`, `js/data.js`, `js/pages/*.js`, `js/charts/*.js`, `js/lib/*.js`, `js/qr.js` | **new** — the split above |
| `site_data/` | **re-keyed to `player_id`**; add `names.json` (id → display name), `manifest.json`, `schema.json`, `data_quality.json`; drop the 7 unfetched files |
| `data/processed/*.json` | replaced by `data/store.sqlite` (gitignored, rebuildable from the cache) |
| `extract_birthdays.py` | **stays put** — personal data, never in the library |
| `docs/pelikone-structure.md` | add the newly verified views + the ID/CSV constraints |
| `tests/` | **new** — fixtures + parser tests |

## Reuse

- `src/otso_scrape/parsers.py` — the maintained parsers become the single copy.
- `refresh_game_rosters.py:canon` — the order-insensitive name-matching rule already applied to
  the committed dataset; becomes `identify.py`.
- `src/otso_scrape/fetcher.py` + `cache.py` — keep the politeness (1.5 s delay, UA) and the
  expiry concept; fix only the storage shape.
- `data/raw/game_*.html` (795 files, **all** carrying `playercard` links) — the fixture source
  *and* the offline ID source for re-keying; no scraping needed for either.
- `build_site_data.py:1107` `build_defense_stats` — the possession rule, lifted into the gameplay
  parser and stored per point instead of recomputed at analytics time.
- `docs/pelikone-structure.md` — the URL/view reference to extend.

## Steps

- [ ] **Phase 0 — make it real.** Rename to `ultiorg`, add build-system to `pyproject.toml`,
      editable-install it, delete both `sys.path.insert` hacks, export the gameplay API.
- [ ] **Phase 1 — characterization tests first.** Commit ~10 fixtures from `data/raw/` (a modern
      gameplay page, a pre-2015 gameplay page, season list, teams, standings, teamcard,
      playerlist) + golden JSON per parser. This is the safety net for everything after.
- [ ] **Phase 2 — delete the stale copies.** Remove `parse_data.py`; confirm the package parsers
      are the only ones; note in the commit which fixes the deleted copies lacked.
- [ ] **Phase 3 — cache.** Per-URL content store + one-time manifest import; verify zero
      re-fetch of the existing 902 season files and 799 game pages.
- [ ] **Phase 4 — identity.** `allplayers` fetch+parse, `playercard` fetch+parse, `identify.py`
      with per-game roster resolution; re-parse the 795 archived game HTMLs to recover roster IDs
      **offline**; report unresolved names rather than guessing.
- [ ] **Phase 5 — the fact store.** `store.py` with the section-4 tables; move the possession rule
      from `build_defense_stats` into the gameplay parser and store `possession` +
      `possession_known` per point. Gate: point counts and defense totals match today's numbers.
- [ ] **Phase 6 — new views.** `scorestatus`, `statistics`, `allteams`/`allclubs`.
- [ ] **Phase 7 — composition API + CLI.** `player()/connections()/scoring()/games()`, the fetch
      verbs, and `ultiorg sql`; delete the four one-off scripts and fold the three repairs in.
      Verify a fresh clone + `ultiorg fetch all-seasons --gameplay` + `python build_site_data.py`
      reproduces `site_data/`.
- [ ] **Phase 8 — analytics to the library.** Move the six builders out of `build_site_data.py`
      behind a focus-team predicate; `teams.yaml` supplies the Otso config. Gate: regenerated
      `site_data/*.json` matches the committed files except for intended fixes.
- [ ] **Phase 9 — re-key the site data.** `site_data/*.json` keyed by `player_id`, plus
      `names.json` and `data_quality.json`. Gate: totals unchanged from the name-keyed build
      (163 players, 483 games, 23 gold) and every unresolved name is listed, not dropped.
- [ ] **Phase 10 — contract.** `manifest.json` + `schema.json`; validate in Python (build) and JS
      (load); remove the `BUILD_VERSION` comment stamp.
- [ ] **Phase 11 — split the page.** `index.html` → shell + `css/` + `js/` ES modules, one page per
      module, hand-rolled canvas behind `js/charts/`, ID-keyed lookups, name → id redirect.
      **No visual redesign.** Gate: rendered site diffed against the deployed version, page by page.
- [ ] **Phase 12 — frontend tests.** `node --test` on the pure modules (`identity`, `format`,
      category math, highlight badges) + a Python test that every `site_data` file satisfies
      `schema.json`.
- [ ] **Phase 13 — split (later).** `git filter-repo` the package into `~/repos/ultiorg`, gala
      depends on it by path/git.

## Verification

- `uv run pytest` — parser tests against committed fixtures; a `@pytest.mark.network` smoke test
  that hits `allplayers` + one `playercard` and asserts a known player ID resolves.
- **Regression gate on the site data**: regenerate `site_data/*.json` after Phase 8 and diff
  against the committed files. Expected diff is the key change (names → IDs) plus intended fixes
  only; any change in the *numbers* of `players.json` / `summary.json` is a blocker.
- **The composite question from the feedback**, run end to end on the Finnish dataset:
  `ultiorg player "Santtu Lehto" --connections 10 --scoring defense --json` returns (a) ranked
  partners with pass counts and per-game rate, (b) defense-initiated goals/assists with a per-game
  rate and the count of points where `possession_known = 0`. Cross-check (b) against today's
  numbers — defense stats are merged into `site_data/players.json` (`defense_points` /
  `_goals` / `_assists`; baseline **140 players, 4,452 defense points**, top Roni Hotari 360).
  The library must reproduce those totals before anything else moves.
- **Fresh-clone test**: `git clone` to a temp dir, `uv sync`, `ultiorg fetch all-seasons --gameplay`,
  `python build_site_data.py`, `python -m http.server 8000` → site renders with the same
  headline numbers as the deployed site (163 players, 483 games, 23 gold).
- **Coaching-staff path**: `ultiorg player "Lehto Santtu"` returns the career table;
  `ultiorg report --players <list> --format csv` produces one row per requested player.
- `python -c "import ultiorg"` works with no `sys.path` manipulation.
- **Cache politeness**: run `ultiorg player "Lehto Santtu"` twice; the second run reports **0
  requests**. `ultiorg fetch all-seasons --dry-run` reports the request count without fetching.
- **Query layer**: `ultiorg game 11049 --json` returns point-by-point rows with resolved
  `player_id`s; the unresolved-name report is empty or explicitly listed.
- **Offline re-key**: re-parsing the 795 archived game pages to recover roster IDs reports
  **0 requests**.
- **Old links survive**: `#/player/Roni%20Hotari` redirects to `#/player/<id>` and renders the same
  player; `?qr#/player/Roni%20Hotari` still encodes a scannable, working link.
- **Frontend**: `node --test` green; open the split site locally and walk all five routes; the
  `?qr` overlay still works; a deliberately corrupted `site_data/summary.json` shows a visible
  per-page error instead of a blank page.

## Settled decisions

| Decision | Choice |
|---|---|
| Package / CLI name | `ultiorg` (library), `ultiorg-cli` (CLI distribution) |
| Page cache | per-URL files under `data/cache/` + small index |
| Freshness | per page kind: history immutable, current season 6 h, `allplayers` 7 d |
| ID-keying | **everywhere, including `site_data/`** — the SPA moves to `player_id` keys |
| Page refactor | structural split + data contract + tests for pure functions, **no visual redesign** |
| Coaching-staff report | separate follow-up plan |

## New decisions raised by re-keying everything

:::question
**What happens to a point whose name cannot be resolved to a player ID?** (Point rows are
name-only; the roster of that game is the only ID source, and some names will not match it.)

- [x] Keep the point under a `name:<canon>` pseudo-key and list it in `data_quality.json` — no
      points silently vanish from totals
- [ ] Drop it from ID-keyed analytics and only report the count — cleaner keys, but totals shift

Recommended: pseudo-key + quality report. The README already documents 651 points of
season-card vs play-by-play mismatch; silently dropping more would make the numbers untrustworthy.
:::

:::question
**Fact store backend.** The HTML cache is settled (per-URL files). The *parsed* facts need a home
that supports joins, for the composite questions in section 4.

- [x] SQLite (`data/store.sqlite`) — gitignored, rebuildable from the cache, `ultiorg sql` escape
      hatch for questions we have not thought of
- [ ] JSONL fact files + an in-memory index — greppable and diffable, but ad-hoc joins are code
- [ ] Parquet — great for aggregation, poor for the point-level joins and no `sql` escape hatch

Recommended: SQLite. It is the difference between "a verb per question" and "structures you can
query".
:::

## Still open

:::question
**Page split: zero-build or a build step?** GitHub Pages only serves static files.

- [x] Zero-build ES modules (`js/*.js` imported by `<script type="module">`) — no toolchain,
      `python -m http.server` still works, `node --test` can import the pure modules
- [ ] Vite/esbuild bundle into `dist/` — smaller payload, but a build step between commit and deploy

Recommended: zero-build ES modules. The payload is ~140 KB today; module splitting is a
maintainability win, not a size win.
:::
