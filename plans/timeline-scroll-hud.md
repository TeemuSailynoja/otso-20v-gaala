# Timeline revamp — scroll-snapped year story under a sticky HUD

## Context

The Timeline page today is a static dashboard: four chart cards plus a 21-card grid of seasons
(`index.html:1036-1080`). Nothing walks you through the 20 years, and the season-level highlights
that *do* tell a story sit on the home carousel, detached from the year they belong to.

Target: the timeline becomes a **scroll-driven narrative**. A compact HUD pinned at the top shows
where you are in 20.5 years; the page snaps one year at a time; each year block carries its record,
trophies, moved-over season highlights, and a short hand-written note.

### Decisions taken

| Question | Decision |
|---|---|
| Season notes | **Hard-coded** per year — 21 entries is small enough |
| Team Evolution cloud | **Folded into the HUD** as an overlay on the roster chart, with a **deterministic** transition animation triggered on year change |
| Otso/All-Bears + Full/Summer/Winter toggles | **Removed**; instead surface notable per-group facts (1st team, 2nd team, Kesä/Talvi) inside the year blocks |
| Scroll feel | **Snap** — one year per screen |
| Matches in HUD | **Big number** for the current year |
| Home carousel season cards | Removed **last**, only once the timeline version is verified |

## Approach

### 1. Layout: HUD + snapping stream

`#page-timeline` breaks out of `.section` (which caps at 1200px and pads 5rem) and becomes:

```
#page-timeline
  .timeline-hud        position: sticky; top: var(--nav-h); height: ~25vh; full width
  .timeline-stream     scroll-snap-type: y proximity
    .year-block × 21   scroll-snap-align: start; min-height: calc(100vh - var(--nav-h) - var(--hud-h))
```

- Introduce `--nav-h` / `--hud-h`, set from `nav.offsetHeight` and `hud.offsetHeight` in JS — the
  construction banner wraps to two lines on mobile, so a hard-coded offset would drift (this is the
  same clipping class of bug we just fixed for page titles).
- `scroll-margin-top: calc(var(--nav-h) + var(--hud-h))` on each `.year-block`.
- Use `proximity`, not `mandatory`: on mobile a year block with three notes can exceed the viewport,
  and mandatory snap would trap the reader.

### 2. HUD contents (~25vh, full width)

- **Left/centre:** roster-size line chart across 2006-2026, short (fits 25vh), with a vertical marker
  + enlarged point on the current year.
- **Overlaid on that chart:** the Team Cloud canvas (see §4) — the roster dots *are* the players.
- **Right:** current **year** as the dominant number, **matches** as a big number under it, win % and
  medal chips (🥇 Kesä 2012 · 🥉 Talvi 2009) for the current year.
- Chart.js marker: `pointRadius` array + a small inline plugin drawing the vertical year line; update
  with `chart.update('none')` so it does not re-animate on every snap.

### 3. Year blocks (replacing `timeline-cards`)

One block per year, 2006 → 2026, revealed with the existing IntersectionObserver pattern
(`index.html:1541-1585`, CSS `.category-slide` `index.html:352-372`). Each shows:

- year + record `W–L`, win %, goal diff, roster size, matches
- **Kesä / Talvi split line** from `yearsOtsoSummer` / `yearsOtsoWinter` (e.g. `Kesä 15–0 · Talvi 8–0`)
- **medal chips** from `DATA.trophies.seasons` filtered by year — already fetched, currently used only
  for two hero numbers
- **season-highlight badges** for that year (see §5)
- **hand-written notes** (see §5)

The same observer publishes the *active year* → HUD numbers, chart marker, and cloud `setYear()`.

### 4. Team Cloud → deterministic, year-driven

Refactor `initTeamEvolution` (`index.html:2212-2650`) into a `createTeamCloud(canvas)` helper exposing
`setYear(names)`:

- Drop the autoplay timer (`YEAR_DURATION`, `TRANSITION_FRAMES`, `frameCount` loop) — year changes come
  from the observer, not the clock.
- Diff incoming roster vs live particles → `leaving` / `entering` states. Reuse the existing
  `addPlayerParticles` (`index.html:2279`), collision handling (`index.html:2368`) and era colours from
  `getEraInfo(first_year).statColors.goals` (`index.html:1661`).
- **Deterministic:** replace `Math.random()` with a seeded PRNG (`mulberry32(seed)`) seeded from the
  year, so 2012 always animates identically.
- Roster per year must match the chart: add `roster_names` to `build_years()`
  (`build_site_data.py:912-925` — it already builds the name set, it just emits `len()`). Without this
  the cloud would use `players[].years`, which counts all Otso teams (2013: 49) while the chart shows
  the main team (2013: 43).
- Pause the rAF loop when the page is not active; skip the animation entirely under
  `prefers-reduced-motion`.

### 5. Story content

```js
const SEASON_STORY = {
  2006: { notes: ['…first season, 10th at Kesä SM…'] },
  2012: { notes: ['…domestic double, 23–0 across the year…'] },
  // …
};
```

- Hard-coded in `index.html` — no build step, no extra fetch, trivially editable.
- **Per-group facts are hand-written too.** `build_trophies()` keeps only the *best* Otso team per
  event (`build_site_data.py:1364-1390`), so `trophies.json` has exactly one non-main-team row
  (Otso2, bronze, Kesä 2025). "The 2nd team did well in winter" is therefore not derivable from the
  current payload — it goes in the notes. If you later want real per-team placements, that is a
  separate `build_trophies()` change.
- **The six season highlights stay data-derived**, not hard-coded: keep computing `bestWin`,
  `largestRoster`, `smallestRoster`, `mostGames`, `mostDominant` (`index.html:1462-1470`) and attach
  each badge to the year it wins, so a data refresh keeps them honest. Only their labels are fixed.
- :warning: `perfectStart` at `index.html:1471` is hard-coded `9–0` while the data says 2026 is `10–0`.
  Derive it from `DATA.years['2026']` when it moves.
- 2026 is a partial season (10 games, no entries in `players[].years` yet) — include it as the final
  block, labelled *in progress*.

### 6. Removals

- `chart-winrate` and `chart-points` cards + their `new Chart(...)` blocks (`index.html:1069-1074`, `2037-2103`)
- the standalone Team Evolution card and `.animation-wrapper` / `.year-display` CSS (`index.html:1057-1064`, `244-272`)
- the `timeline-year-cards` grid and its CSS (`index.html:1075`, `819-870`)
- both toggle groups and `switchTimelineView` / `switchTimelineSeason` / `updateTimelineDatasets`
  (`index.html:1041-1050`, `2105-2159`)
- the three `years_all_bears*` fetches (`index.html:1114-1128`) — `updateTimelineDatasets` is their only
  consumer, so the timeline stops pulling ~3 unused JSON files. Keep the Otso summer/winter variants:
  they feed the Kesä/Talvi split line.
- the six season cards in the home `categories` array (`index.html:1473-1479`) — **final step, separate
  commit**, after the timeline version is verified.

## Files to modify

| File | What |
|---|---|
| `index.html:1036-1080` | timeline markup → HUD + year stream |
| `index.html:244-272`, `786-870` | drop old timeline/particle CSS; add HUD, year-block, snap CSS |
| `index.html:1114-1128` | stop loading the three all-bears variants |
| `index.html:1462-1479` | season highlights → badges for year blocks; home removal last |
| `index.html:1957-2103` | `renderTimeline()` → HUD charts + year blocks |
| `index.html:2105-2159` | delete toggle handlers |
| `index.html:2212-2650` | `initTeamEvolution` → deterministic `createTeamCloud` |
| `build_site_data.py:835-925` | `build_years()` emits `roster_names` per year |

## Reuse

- Scroll-reveal + progress-dot observer: `index.html:1541-1585`
- Particle model, collisions, era colours: `index.html:2279`, `index.html:2368`, `index.html:1661`
- Chart.js 4.4.1 already loaded (`index.html:8`); `DATA.trophies.seasons` already fetched (`index.html:1101`)
- Mobile headroom fix from `dcf5a77` — the HUD sticky offset must respect the same nav-height reality

## Steps

- [x] 1. `build_years()` emits `roster_names`; regenerate `site_data/years_*.json`
- [x] 2. HUD skeleton: sticky bar, `--nav-h` / `--hud-h` wiring, short roster chart + matches/year/win% readout
- [x] 3. Year blocks + `scroll-snap-type: y proximity` + observer publishing the active year
- [ ] 4. HUD reacts to active year: chart marker, big numbers, medal chips, Kesä/Talvi split
- [ ] 5. `createTeamCloud` refactor: seeded PRNG, `setYear()`, overlay on the roster chart
- [ ] 6. `SEASON_STORY` notes for 2006-2026 + data-derived highlight badges on their years
- [ ] 7. Delete win-rate/points charts, year-card grid, standalone cloud, toggles, all-bears fetches
- [ ] 8. After verification: remove the six season cards from the home carousel (separate commit)

## Verification

- `python -m http.server 8000` → `#/timeline`. Walk top → bottom: the HUD year, matches number, chart
  marker and cloud must change exactly once per snapped block, and the cloud transition must be
  identical on repeat visits (determinism).
- `node --check` on the extracted inline script after each phase (the pattern used earlier this session).
- Console must stay clean; no duplicate `Chart` instances when re-entering the page (navigate away/back).
- Mobile ≤768px: HUD stays below the fixed nav, ≤25vh, year text fully visible; snap must not trap
  scrolling on tall blocks.
- `prefers-reduced-motion`: cloud animation skipped, blocks still readable, HUD numbers still update.
- Home page carousel must remain fully working until step 8.
- Cross-check a year against source data: 2012 → 23 matches, 23–0, gold Kesä + gold Talvi
  (`site_data/years_otso.json`, `site_data/trophies.json`).

## Risks

- **Snap + sticky + fixed nav** is the fiddliest part; offsets come from measured heights, not constants.
- The cloud refactor touches ~440 lines of working animation code; it lands as its own step so it can be
  reverted without losing the HUD/stream work.
- Notes are prose you have to supply — I can draft all 21 from the data and you edit them.
