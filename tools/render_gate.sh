#!/usr/bin/env bash
# Rendered-DOM gate for the single-page site.
#
# Phase 11 moves ~1,800 lines of inline script and ~1,200 lines of CSS out of
# index.html into ES modules and a stylesheet. The promise is that the *rendered
# page* does not change, and the only honest way to check that is to render it.
# So: serve a build, drive headless chromium over every route, keep the DOM, and
# diff two runs.
#
#   tools/render_gate.sh <out-dir> [port]
#
# The dumps are byte-stable run to run — verified before this script was written —
# because the particle field is seeded (mulberry32) and nothing else in the page
# reads the clock. If a route ever goes unstable, diff the same route twice before
# blaming the change.
#
# A dump is only accepted if the page actually rendered. The first version of this
# script silently captured the *raw* index.html for three of seven routes: the
# budget expired while chart.js was still in flight from the CDN, so the inline
# script — which sits at the end of <body> — had been parsed but not executed.
# Those dumps looked fine (140 KB each) and were blind: they contained the script's
# own source text and no rendered content. So every dump is now checked for the
# page it should have activated, and for the sentinel below, and retried.
#
# The page is served under /otso-20v-gaala/, not /. index.html carries
# <base href="/otso-20v-gaala/"> because that is the path of the GitHub Pages
# project site, and every relative URL in the page — including the dynamic import
# of js/data.js — resolves against it. Serving the repo root at / therefore 404s
# the whole module graph and the page renders nothing at all. So the build is
# staged behind a directory with that name and the *parent* is served. That is how
# the site has to be previewed locally, and the gate encodes it rather than
# discovering it again next time.
set -euo pipefail

OUT="${1:?usage: tools/render_gate.sh <out-dir> [port]}"
PORT="${2:-18322}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# route -> the page div that must be active in the rendered DOM
ROUTES=('#/' '#/players' '#/player/Roni%20Hotari' '#/player/Simo%20Soini'
        '#/player/NoSuch%20Person' '#/frenemies' '#/timeline')
PAGES=(home players player player player frenemies timeline)
# What each route must contain, and how many times. The active-page check proves the
# router ran; it does not prove the data arrived — a page can go active and render an
# empty container, which after the module split is exactly how a failed import or a
# late first fetch looks. The floors are the element counts of the baseline dumps,
# rounded down hard: they exist to catch a page that rendered nothing, not to pin the
# counts (the diff does that). The `class="` prefix keeps CSS selectors out of the
# count — and note the old inline script's own source text counted too, which is why
# the player route's floor is 10 and not the 25 the pre-split dumps appeared to have.
MARKERS=('class="category-slide|10' 'class="player-card|400' 'class="player-|10'
         'class="player-|10' 'Player not found.|1' 'class="frenemy|100'
         'class="year-block|20')

# Route list note: `#/player/...` covers a long career, a short one, and a name
# that is not in the table, so the not-found branch is in the gate. After the id
# re-key a bare id route joins it, and the name routes keep their place because
# old QR codes and bookmarks use them.
mkdir -p "$OUT"
cd "$HERE"

# Stage: <out>/serve/otso-20v-gaala -> the build, and serve <out>/serve.
STAGE="$OUT/serve"
rm -rf "$STAGE"
mkdir -p "$STAGE"
ln -s "$HERE" "$STAGE/otso-20v-gaala"
BASE="http://127.0.0.1:${PORT}/otso-20v-gaala"

uv run python -m http.server "$PORT" --directory "$STAGE" >/dev/null 2>&1 &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT

# `uv run` takes several seconds to resolve the project before the socket exists;
# dumping before that produced chromium's error page, which is also ~140 KB and so
# passed a size check. Wait for a real 200 instead of sleeping a guess.
for _ in $(seq 1 30); do
  if curl -sf -o /dev/null "$BASE/index.html"; then break; fi
  sleep 1
done
if ! curl -sf -o /dev/null "$BASE/index.html"; then
  echo "FAIL local server never answered on port $PORT" >&2
  exit 1
fi

# Warm the server before the first dump. One page load pulls the module graph and
# eight JSON files through a single-threaded server, and a request served late leaves
# the page active with nothing rendered — which reads like a regression in the diff
# and is really a race with the server starting.
for path in index.html js/main.js js/state.js js/pages/home.js \
            site_data/manifest.json site_data/players.json site_data/summary.json; do
  curl -sf -o /dev/null "${BASE}/${path}" || true
done

dump() {
  # --enable-logging=stderr is what makes the console check below real: without it
  # chromium emits no CONSOLE lines at all, and the gate's "a module that fails to
  # load" check was reading an empty file and passing. With it, a broken import shows
  # up as the uncaught error it is instead of as a page that renders nothing.
  timeout 90 chromium --headless=new --no-sandbox --disable-gpu --enable-logging=stderr \
    --virtual-time-budget=25000 --timeout=60000 --dump-dom \
    "${BASE}/index.html$1" 2>"$OUT/$2.err"
}

fail=0
for i in "${!ROUTES[@]}"; do
  route="${ROUTES[$i]}"; page="${PAGES[$i]}"; name=$(printf 'route%02d' $((i + 1)))
  want="id=\"page-${page}\" class=\"page active\""
  marker="${MARKERS[$i]%%|*}"; mincount="${MARKERS[$i]##*|}"; count=0
  for attempt in 1 2 3; do
    # `if !` rather than a bare call: under `set -e` a chromium that exits non-zero
    # (its own timeout, a crash) ended the whole gate silently after the first route,
    # leaving a directory with one dump in it and no explanation. A bad dump is a
    # retry reason, not a reason to stop.
    if ! dump "$route" "$name" > "$OUT/$name.html"; then
      reason="chromium exited non-zero — see ${name}.err"
    elif grep -q 'main-frame-error' "$OUT/$name.html"; then
      reason="chromium error page: nothing was served"
    elif cmp -s "$OUT/$name.html" "$HERE/index.html"; then
      # A dump byte-identical to index.html is the unexecuted page: the parser got the
      # whole document and the script never ran. Checking for the script's own source
      # text would not do — dump-dom keeps that element whether or not it executed,
      # and after Phase 11 there is no inline script at all to look for.
      reason="dump is the raw file: the script never ran"
    elif ! grep -q "$want" "$OUT/$name.html"; then
      reason="expected ${page} to be the active page"
    else
      # Count the data-derived elements. The `|| true` is load-bearing: with
      # `set -euo pipefail` a grep that finds nothing made the assignment fail, which
      # ended the gate instead of reporting an empty page and retrying.
      count=$({ grep -o "$marker" "$OUT/$name.html" || true; } | wc -l)
      if [ "$count" -lt "$mincount" ]; then
        reason="only ${count} '${marker}' in the rendered DOM, want >= ${mincount}"
      else
        reason=""
        break
      fi
    fi
    echo "  retry $name ($route): $reason"
  done
  if [ -n "$reason" ]; then
    echo "FAIL $name $route: $reason after 3 attempts"
    fail=1
    continue
  fi
  printf '%-9s %-26s %-10s %8d bytes  %4d markers\n' \
    "$name" "$route" "$page" "$(wc -c < "$OUT/$name.html")" "$count"
done

# Console messages from the page are part of the gate: a module that fails to load
# renders a page that looks fine until it does not. Chromium's own logging is not
# part of it — the browser emits GCM/sqlite ERROR lines on every run here, and a
# grep for "error" turned those into a failure. Only CONSOLE: lines are the page
# talking.
if grep -h 'CONSOLE' "$OUT"/*.err 2>/dev/null | grep -qiE 'error|failed|refused|uncaught'; then
  echo "--- page console output ---"
  grep -h 'CONSOLE' "$OUT"/*.err | sort -u | head -20
  fail=1
fi

exit "$fail"
