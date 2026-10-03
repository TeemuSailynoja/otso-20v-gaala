# Revisions — Timeline revamp (`plans/timeline-scroll-hud.md`)

- **Step 3 — active year is published by a scroll handler, not the IntersectionObserver.** The plan said
  the reused IO pattern would publish the active year. IO reports *intersections*, not *which block owns
  the viewport centre*, and the home-carousel implementation of that (`index.html:1541-1585`) is convoluted
  and easy to get wrong. Split instead: IO does reveal only (`.year-block.active`), and a rAF-throttled
  scroll handler picks the block whose centre is nearest the viewport mid-line and calls `setHudYear()`.
  Verified headless: scrolling to 2012 yields HUD `2012 / 23 / 100% / 🥇 Kesä 🥇 Talvi`.

- **Step 2 — legacy cards are hidden, not deleted yet.** The old dashboard markup is wrapped in
  `.timeline-legacy { display: none }` so each step stays reviewable and the page usable; step 7 deletes
  the block outright.

- **Step 5 — HUD cloud: implemented and now confirmed rendering.** `createTeamCloud()` (seeded
  `mulberry32(year)`, `setYear()`, overlay canvas over the roster chart, pause/resume with the page,
  static draw under `prefers-reduced-motion`) is wired and a duplicate `id="hud-cloud"` left by an
  editing slip is fixed. Verification took three attempts: a pixel probe over CDP measured painted pixels
  scaling with roster size, but headless `--screenshot --virtual-time-budget` never advances
  `requestAnimationFrame`, so no such shot shows the dots. A **live** CDP session (`Page.captureScreenshot`
  after a real 4 s wait, no virtual time) does: at 2013 the cloud draws over the plot area in the era's
  red-pink palette with the glow intact. The era-colour lift, `lighten(base, 0.45)` + `shadowBlur 6`,
  reads fine on the navy background. Closed.

- **Post-plan — every Otso team's placement (user request, not in the approved plan).** `build_trophies`
  collapsed each season to the single best Otso result; the raw placement tables always had the rest. Each
  season record now also carries `entries` (every Otso team in the Avoin season-deciding event, best first,
  deduped per team) — 18 of 41 seasons have more than one. Best-result fields are untouched, so the trophy
  totals stay 23/3/4 over 40 contested seasons. Rendered as a season line under the Kesä/Talvi split, and
  the HUD chips name the team when it is not the main Otso (2025 summer bronze = Otso 2, 2019 summer
  bronze = Otso Grizzly).

- **Post-plan — two superlatives the badge pass had dropped.** The old home carousel's *Skeleton Crew*
  card (fewest names in a season with 15+ matches → 2007, 18 players) was never carried into
  `computeHighlightBadges`, and *Largest roster* was computed for 2019 (31 names) but the 2019 note did not
  mention it. Both fixed: `smallestR` badge on 2007, and the 2007/2019 notes now state the roster facts.
