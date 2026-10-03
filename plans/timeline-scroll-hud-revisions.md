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
