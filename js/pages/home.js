// The home page: the summary numbers and every category board.
//
// This page draws; it does not decide. The rankings, thresholds and rules that
// produce the claims on these slides are in js/categories.js, where they can be
// tested against a made-up squad. What is left here is the DOM: the row, table,
// triangle and duo renderers, the carousel, the age chart.
//
// Every player reference is a site key: it indexes players.json, pass_network.json
// and cooccurrence.json, and it goes into data-player so the click can route by
// key. A name appears only where a human reads one, and it comes from people.js.

import { buildCategorySlides } from '../categories.js';
import { firstName, initials, nameFor } from '../people.js';
import { DATA } from '../state.js';

// ==================== HOME PAGE ====================
export function renderHome() {
    const s = DATA.summary;
    document.getElementById('stat-years').textContent = s.years_count;
    document.getElementById('stat-players').textContent = s.total_players.toLocaleString();
    document.getElementById('stat-matches').textContent = s.total_matches.toLocaleString();
    document.getElementById('stat-wins').textContent = s.total_wins.toLocaleString();
    document.getElementById('stat-winpct').textContent = s.win_percentage + '%';

    const tr = DATA.trophies;
    if (tr) {
        const t = tr.totals;
        document.getElementById('stat-trophies').textContent = t.all.gold;
        document.getElementById('stat-podiums').textContent = t.all.podiums;
    }

    renderCategories();
}


function renderCategories() {
    console.log('renderCategories called, DATA.players:', Object.keys(DATA.players || {}).length);
    const players = DATA.players || {};
    const passNet = DATA.passNetwork || {};
    const cooc = DATA.cooccurrence || {};
    const given = passNet.given || {};
    const received = passNet.received || {};
    console.log('given:', Object.keys(given).length, 'received:', Object.keys(received).length);
    if (!document.getElementById('categories-scroll')) return;

    // Helper: get rank class
    function rankClass(i) {
        return i === 0 ? 'gold' : i === 1 ? 'silver' : 'bronze';
    }

    // Helper: render a player row
    function playerRow(rank, name, stat, highlight) {
        const click = name in players ? `data-player="${name}"` : '';
        return `<div class="category-player" ${click}>
                <span class="category-rank ${rankClass(rank)}">${rank + 1}</span>
                <span class="category-player-name">${nameFor(name)}</span>
                <span class="category-player-stat ${highlight ? 'highlight' : ''}">${stat}</span>
            </div>`;
    }

    // Helper: render a pair row
    function pairRow(rank, name1, name2, stat1, stat2) {
        const click = (name1 in players && name2 in players) ? `data-player1="${name1}" data-player2="${name2}"` : '';
        return `<div class="category-player" ${click}>
                <span class="category-rank ${rankClass(rank)}">${rank + 1}</span>
                <span class="category-pair">
                    <span class="category-player-name">${nameFor(name1)}</span>
                    <span class="category-pair-arrow">↔</span>
                    <span class="category-player-name">${nameFor(name2)}</span>
                </span>
                <span class="category-player-stat highlight">${stat1} + ${stat2}%</span>
            </div>`;
    }

    // Helper: render one ranked table. Several metrics about the same players
    // belong on one screen: columns, not another three-row podium.
    function categoryTableHtml(cat) {
        const head = cat.columns.map(c => `<th>${c}</th>`).join('');
        const body = cat.rows.map((r, i) => {
            const click = r.name in players ? `data-player="${r.name}"` : '';
            const mark = r.mark ? `<span class="cat-mark">${r.mark}</span>` : '';
            return `<tr class="category-tr" ${click}>
                    <td class="cat-td-name"><span class="category-rank ${rankClass(i)}">${i + 1}</span>${r.label || nameFor(r.name)}${mark}</td>
                    ${r.cells.map(c => `<td class="cat-td-num">${c}</td>`).join('')}
                </tr>`;
        }).join('');
        return `<table class="category-table">
                    <thead><tr>${head}</tr></thead>
                    <tbody>${body}</tbody>
                </table>`;
    }

    function categoryTable(cat) {
        return categoryTableHtml(cat)
            + (cat.foot ? `<div class="category-foot">${cat.foot}</div>` : '');
    }

    // Helper: two rankings side by side, for the families where the absolute
    // leader and the rate leader are different people and one sort order would
    // hide one of them. Stacks into one column on phones.
    function categorySplit(cat) {
        return `<div class="category-split">${cat.panels.map(p => `
                    <div class="category-panel">
                        <div class="panel-title">${p.title}</div>
                        ${categoryTableHtml(p)}
                    </div>`).join('')}
                </div>${cat.foot ? `<div class="category-foot">${cat.foot}</div>` : ''}`;
    }

    // Helper: render a gap-and-comeback slide. The story is the distance, so
    // draw it on one shared 2006–2026 axis instead of printing numbers nobody
    // can compare. Gold dot = last season before leaving, dashed run = years
    // away, blue dot = the season they came back for.
    function categoryGaps(cat) {
        const lo = 2006, hi = 2026;
        const pct = (y) => (y - lo) / (hi - lo) * 100;
        return `<div class="gap-list">${cat.data.map(p => {
                const click = p.name in players ? `data-player="${p.name}"` : '';
                return `<div class="gap-row" ${click}>
                    <div class="gap-name">${nameFor(p.name)}</div>
                    <div class="gap-track">
                        <span class="gap-span" style="left:${pct(p.before).toFixed(2)}%;width:${(pct(p.after) - pct(p.before)).toFixed(2)}%"></span>
                        <span class="gap-dot before" style="left:${pct(p.before).toFixed(2)}%"></span>
                        <span class="gap-dot after" style="left:${pct(p.after).toFixed(2)}%"></span>
                    </div>
                    <div class="gap-label"><span>${p.before}</span><span>${p.gap} years out · ${p.seasons} seasons back</span><span>${p.after}</span></div>
                </div>`;
            }).join('')}</div>`;
    }


    // ===== THE TRIANGLE renderer. Three nodes, edge stroke width proportional to the
    // co-occurrence weight. Edges are games on the same roster — never assists.
    function categoryTrio(cat) {
        const t = cat.triangle;
        if (!t) return '';
        const pos = [[150, 40], [46, 168], [254, 168]];
        const at = {};
        t.names.forEach((n, i) => { at[n] = i; });
        const maxW = Math.max.apply(null, t.edges.map(e => e.w));
        const edges = t.edges.map(e => {
            const p = pos[at[e.a]], q = pos[at[e.b]];
            const sw = (e.w / maxW * 5.5 + 1.5).toFixed(2);
            return `<line x1="${p[0]}" y1="${p[1]}" x2="${q[0]}" y2="${q[1]}" stroke-width="${sw}"></line>` +
                `<text class="trio-edge-label" x="${(p[0] + q[0]) / 2}" y="${(p[1] + q[1]) / 2 - 8}" text-anchor="middle">${e.w}</text>`;
        }).join('');
        const nodes = t.names.map((n, i) => {
            const p = pos[i];
            const click = n in players ? `data-player="${n}"` : '';
            const ly = i === 0 ? p[1] - 18 : p[1] + 26;
            return `<g class="trio-node" ${click}><circle cx="${p[0]}" cy="${p[1]}" r="7"></circle>` +
                `<text class="trio-name" x="${p[0]}" y="${ly}" text-anchor="middle">${nameFor(n)}</text></g>`;
        }).join('');
        const spans = t.edges.map(e => {
            const s = pairSpan(e.a, e.b);
            const range = s.first ? `${s.seasons} seasons, ${s.first}–${s.last}` : 'no shared season';
            return `${initials(e.a)}–${initials(e.b)} ${e.w} (${range})`;
        });
        const runner = cat.runnerUp;
        return `<svg class="trio-svg" viewBox="0 0 300 210" role="img" aria-label="${t.names.map(nameFor).join(', ')}">${edges}${nodes}</svg>
                <div class="trio-caption">Edge weight = games on the same roster.<br>${spans.join(' · ')}<br>` +
            `Next trio: ${runner ? runner.names.map(initials).join(', ') + ' — ' + runner.score : '—'}.</div>`;
    }

    // ===== THE PAIR renderer. One duo: the stat strip carries the claim, the two season
    // lanes carry the length (a tick per season on a roster, shaded where both were on one),
    // and the footnote carries the rest of the qualifying set so 'top' is legible.
    function categoryDuo(cat) {
        const d = cat.duo;
        if (!d) return '';
        const lo = 2010, hi = 2026;
        const pct = (y) => (y - lo) / (hi - lo) * 100;
        const shared = pairSpan(d.name1, d.name2);
        const shade = shared.first
            ? `<span class="duo-shared" style="left:${pct(shared.first).toFixed(2)}%;width:${(pct(shared.last) - pct(shared.first)).toFixed(2)}%"></span>`
            : '';
        const lane = (name) => {
            const years = (((players[name] || {}).years) || []).slice().sort((x, y) => x - y);
            const ticks = years.map(y => `<span class="duo-tick" style="left:${pct(y).toFixed(2)}%"></span>`).join('');
            const click = name in players ? `data-player="${name}"` : '';
            return `<div class="duo-lane" ${click}>
                    <div class="duo-lane-name">${nameFor(name)}</div>
                    <div class="duo-track">${shade}${ticks}</div>
                </div>`;
        };
        const c1 = d.name1 in players ? `data-player="${d.name1}"` : '';
        const c2 = d.name2 in players ? `data-player="${d.name2}"` : '';
        const stats = [
            { v: String(d.weight), l: `assists ${firstName(d.name1)}→${firstName(d.name2)} — the heaviest single link in the data` },
            { v: String(d.games), l: 'games on the same roster' },
            { v: shared.first ? `${shared.first}–${shared.last}` : '—', l: `${shared.seasons} seasons together` },
            { v: `${cat.combined.games} / ${cat.combined.points}`, l: `combined games / points · ${d.assists2} ${firstName(d.name2)}→${firstName(d.name1)} back` },
        ].map(s => `<div class="duo-stat"><div class="duo-stat-value">${s.v}</div><div class="duo-stat-label">${s.l}</div></div>`).join('');
        const ch = cat.chain;
        const chainLine = ch
            ? `${nameFor(ch.from)} → ${nameFor(ch.mid)} → ${nameFor(ch.end)} (${ch.w1} + ${ch.w2}) is the heaviest chain of #1 targets in the data. `
            : '';
        const spokeTxt = cat.spokeFeeds.length === 0
            ? `nobody's #1 target is ${nameFor(cat.spoke)} — he is the source of this link, not its hub`
            : cat.spokeFeeds.length === 1
                ? `the only player whose #1 target is ${nameFor(cat.spoke)} is ${nameFor(cat.spokeFeeds[0])}`
                : `${cat.spokeFeeds.length} players — ${cat.spokeFeeds.map(firstName).join(', ')} — have ${nameFor(cat.spoke)} as theirs`;
        const traffic = `${cat.hubFeeds.length} players run their offense through ${nameFor(cat.hub)}; ${spokeTxt}.`;
        const others = (cat.others || []).map(p =>
            `${nameFor(p.name1)} → ${nameFor(p.name2)} · ${p.weight} assists, ${p.games} games`);
        const othersLine = (cat.others || []).length
            ? `<div class="duo-foot">True of ${cat.totalLinks} links in all; the next ${cat.others.length}: ${others.join(' · ')}.</div>`
            : '';
        return `<div class="duo-names"><span class="duo-name" ${c1}>${nameFor(d.name1)}</span><span class="duo-vs">→</span><span class="duo-name" ${c2}>${nameFor(d.name2)}</span></div>
                <div class="duo-stats">${stats}</div>
                <div class="duo-lanes">${lane(d.name1)}${lane(d.name2)}
                    <div class="duo-axis"><span>${lo}</span><span>${hi}</span></div>
                </div>
                <div class="duo-foot">${chainLine}${traffic}</div>
                ${othersLine}`;
    }

    // The claims are computed in js/categories.js, apart from the DOM; this page
    // only draws them. pairSpan comes back because the triangle caption and the
    // duo's season lanes quote the same shared-year span.
    const { categories, pairSpan } = buildCategorySlides(DATA);

    const scrollContainer = document.getElementById('categories-scroll');
    const scrollProgress = document.getElementById('scroll-progress');

    // Build category slides
    scrollContainer.innerHTML = categories.map((cat, idx) => {
        const rows = (cat.type === 'chart' || cat.type === 'table' || cat.type === 'gaps' || cat.type === 'split' || cat.type === 'trio' || cat.type === 'duo') ? '' : cat.data.map((p, rowIdx) => {
            if (cat.type === 'pair') {
                const click = (p.name1 in players && p.name2 in players) ? `data-player1="${p.name1}" data-player2="${p.name2}"` : '';
                return `<div class="category-row" ${click}>
                        <span class="category-rank ${rowIdx === 0 ? 'gold' : rowIdx === 1 ? 'silver' : 'bronze'}">${rowIdx + 1}</span>
                        <span class="category-pair">
                            <span class="category-player-name">${nameFor(p.name1)}</span>
                            <span class="category-pair-arrow">↔</span>
                            <span class="category-player-name">${nameFor(p.name2)}</span>
                        </span>
                        <span class="category-player-stat highlight">${p.pct1}% + ${p.pct2}%</span>
                    </div>`;
            }
            return playerRow(rowIdx, p.name, p.stat, rowIdx === 0);
        }).join('');
        const body = cat.type === 'chart'
            ? '<div class="category-chart"><canvas id="slide-age-chart"></canvas></div>'
            : cat.type === 'table' ? categoryTable(cat)
            : cat.type === 'gaps' ? categoryGaps(cat)
            : cat.type === 'split' ? categorySplit(cat)
            : cat.type === 'trio' ? categoryTrio(cat)
            : cat.type === 'duo' ? categoryDuo(cat)
            : `<div class="category-list">${rows}</div>`;
        return `<div class="category-slide" data-category="${idx}">
                <div class="category-name">${cat.name}</div>
                <div class="category-desc">${cat.desc}</div>
                ${body}
            </div>`;
    }).join('');

    // Build progress dots
    scrollProgress.innerHTML = categories.map((_, idx) => `<div class="scroll-dot ${idx === 0 ? 'active' : ''}" data-category="${idx}"></div>`).join('');

    // Two lines on two axes: squad size is a headcount, mean age is years old,
    // and neither belongs on the other's scale. Lines rather than bars because
    // a roster that never leaves 18–31 would need a truncated bar axis to read.
    const ageCanvas = document.getElementById('slide-age-chart');
    if (ageCanvas && DATA.years) {
        const yrs = Object.keys(DATA.years).sort();
        new Chart(ageCanvas, {
            type: 'line',
            data: {
                labels: yrs,
                datasets: [
                    {
                        label: 'Roster (players)',
                        data: yrs.map(y => DATA.years[y].roster_players),
                        borderColor: 'rgba(123, 167, 204, 0.95)',
                        backgroundColor: 'rgba(123, 167, 204, 0.14)',
                        borderWidth: 2, pointRadius: 0, fill: true, tension: 0.3,
                        yAxisID: 'y',
                    },
                    {
                        label: 'Avg age (years)',
                        data: yrs.map(y => DATA.years[y].avg_age ?? null),
                        borderColor: '#e5b037',
                        backgroundColor: '#e5b037',
                        borderWidth: 2, pointRadius: 2, fill: false, tension: 0.3,
                        spanGaps: true, yAxisID: 'y1',
                    },
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { labels: { color: '#8a9bae', boxWidth: 12, font: { size: 11 } } },
                    tooltip: {
                        callbacks: {
                            label: (c) => {
                                if (c.dataset.yAxisID !== 'y1') return `Roster: ${c.parsed.y} players`;
                                const d = DATA.years[c.label] || {};
                                if (c.parsed.y == null) return 'Avg age: no birthdays recorded';
                                return `Avg age: ${c.parsed.y} (${d.avg_age_known}/${d.roster_players} with a recorded birthday)`;
                            }
                        }
                    }
                },
                scales: {
                    x: { ticks: { color: '#8a9bae', maxTicksLimit: 6, font: { size: 10 } }, grid: { display: false } },
                    // No axis titles: the right one lands on top of its own ticks at
                    // slide width. The legend carries the units instead.
                    y: {
                        position: 'left',
                        ticks: { color: 'rgba(123, 167, 204, 0.85)', font: { size: 10 } },
                        grid: { color: 'rgba(255,255,255,0.05)' },
                    },
                    y1: {
                        position: 'right',
                        ticks: { color: 'rgba(229, 176, 55, 0.85)', font: { size: 10 } },
                        grid: { display: false },
                    },
                }
            }
        });
    }

    // Intersection observer for scroll-triggered animations
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const idx = parseInt(entry.target.dataset.category);
            const dots = scrollProgress.querySelectorAll('.scroll-dot');
            const midPoint = entry.boundingClientRect.top + entry.boundingClientRect.height / 2;
            const viewportCenter = window.innerHeight / 2;

            if (entry.isIntersecting && entry.intersectionRatio > 0.2) {
                entry.target.classList.add('active');
                entry.target.classList.remove('exit-up');
                // Activate the closest slide to viewport center
                dots.forEach((d, i) => {
                    const slide = scrollContainer.querySelector(`[data-category="${i}"]`);
                    if (slide) {
                        const slideMid = slide.getBoundingClientRect().top + slide.getBoundingClientRect().height / 2;
                        if (Math.abs(slideMid - viewportCenter) < Math.abs(entry.boundingClientRect.top + entry.boundingClientRect.height / 2 - viewportCenter)) {
                            d.classList.toggle('active', false);
                        } else {
                            d.classList.toggle('active', i === idx);
                        }
                    }
                });
            } else if (entry.boundingClientRect.top + entry.boundingClientRect.height < viewportCenter) {
                entry.target.classList.add('exit-up');
                entry.target.classList.remove('active');
            }
        });
    }, {
        threshold: [0.2, 0.4, 0.6],
        rootMargin: '-5% 0px -5% 0px'
    });

    document.querySelectorAll('.category-slide').forEach(slide => observer.observe(slide));

    // Activate first slide immediately
    const firstSlide = scrollContainer.querySelector('[data-category="0"]');
    if (firstSlide) firstSlide.classList.add('active');

    // Click on category players to go to player page
    scrollContainer.querySelectorAll('.category-player[data-player], .category-tr[data-player], .gap-row[data-player], .trio-node[data-player], .duo-name[data-player], .duo-lane[data-player]').forEach(row => {
        row.addEventListener('click', () => {
            location.hash = `#/player/${encodeURIComponent(row.dataset.player)}`;
        });
    });
    scrollContainer.querySelectorAll('.category-player[data-player1]').forEach(row => {
        row.addEventListener('click', () => {
            location.hash = `#/player/${encodeURIComponent(row.dataset.player1)}`;
        });
    });
    console.log('renderCategories done, slides:', document.querySelectorAll('.category-slide').length);
}

