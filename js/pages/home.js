// The home page: the summary numbers and every category board.

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

    // Helper: normalize name
    function normalize(name) {
        if (!name || !(name in players)) return name;
        return name;
    }

    // Helper: get rank class
    function rankClass(i) {
        return i === 0 ? 'gold' : i === 1 ? 'silver' : 'bronze';
    }

    // Helper: render a player row
    function playerRow(rank, name, stat, highlight) {
        const n = normalize(name);
        const click = n in players ? `data-player="${n}"` : '';
        return `<div class="category-player" ${click}>
                <span class="category-rank ${rankClass(rank)}">${rank + 1}</span>
                <span class="category-player-name">${n}</span>
                <span class="category-player-stat ${highlight ? 'highlight' : ''}">${stat}</span>
            </div>`;
    }

    // Helper: render a pair row
    function pairRow(rank, name1, name2, stat1, stat2) {
        const n1 = normalize(name1), n2 = normalize(name2);
        const click = (n1 in players && n2 in players) ? `data-player1="${n1}" data-player2="${n2}"` : '';
        return `<div class="category-player" ${click}>
                <span class="category-rank ${rankClass(rank)}">${rank + 1}</span>
                <span class="category-pair">
                    <span class="category-player-name">${n1}</span>
                    <span class="category-pair-arrow">↔</span>
                    <span class="category-player-name">${n2}</span>
                </span>
                <span class="category-player-stat highlight">${stat1} + ${stat2}%</span>
            </div>`;
    }

    // Helper: render one ranked table. Several metrics about the same players
    // belong on one screen: columns, not another three-row podium.
    function categoryTableHtml(cat) {
        const head = cat.columns.map(c => `<th>${c}</th>`).join('');
        const body = cat.rows.map((r, i) => {
            const n = normalize(r.name);
            const click = n in players ? `data-player="${n}"` : '';
            const mark = r.mark ? `<span class="cat-mark">${r.mark}</span>` : '';
            return `<tr class="category-tr" ${click}>
                    <td class="cat-td-name"><span class="category-rank ${rankClass(i)}">${i + 1}</span>${r.label || n}${mark}</td>
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
                const n = normalize(p.name);
                const click = n in players ? `data-player="${n}"` : '';
                return `<div class="gap-row" ${click}>
                    <div class="gap-name">${n}</div>
                    <div class="gap-track">
                        <span class="gap-span" style="left:${pct(p.before).toFixed(2)}%;width:${(pct(p.after) - pct(p.before)).toFixed(2)}%"></span>
                        <span class="gap-dot before" style="left:${pct(p.before).toFixed(2)}%"></span>
                        <span class="gap-dot after" style="left:${pct(p.after).toFixed(2)}%"></span>
                    </div>
                    <div class="gap-label"><span>${p.before}</span><span>${p.gap} years out · ${p.seasons} seasons back</span><span>${p.after}</span></div>
                </div>`;
            }).join('')}</div>`;
    }

    // ===== Pair helpers, shared by the duo slide and the triangle caption =====
    // Shared calendar seasons for a pair. 74 of the 3,299 co-occurrence pairs have an empty
    // year intersection, so span comes back null-ended and renders '—', never 0–0, and a
    // null span must not break the sort below.
    function pairSpan(a, b) {
        const ya = (players[a] && players[a].years) || [];
        const yb = (players[b] && players[b].years) || [];
        const shared = ya.filter(y => yb.indexOf(y) !== -1).sort((x, y) => x - y);
        return shared.length
            ? { seasons: shared.length, first: shared[0], last: shared[shared.length - 1], years: shared }
            : { seasons: 0, first: null, last: null, years: [] };
    }
    function linkWeight(a, b) { return (given[a] && given[a][b]) || 0; }
    function topTarget(p) {
        const d = given[p];
        if (!d || Object.keys(d).length === 0) return null;
        return Object.entries(d).sort((x, y) => y[1] - x[1])[0][0];
    }
    // Players whose single biggest assist target is `target` — how much traffic a name gets.
    function runsThrough(target) {
        return Object.keys(given).filter(p => topTarget(p) === target);
    }
    function firstName(n) { return String(n).split(' ')[0]; }
    function initials(n) {
        const parts = String(n).split(' ');
        return parts.length > 1 ? parts[0].charAt(0) + '. ' + parts.slice(1).join(' ') : n;
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
                `<text class="trio-name" x="${p[0]}" y="${ly}" text-anchor="middle">${n}</text></g>`;
        }).join('');
        const spans = t.edges.map(e => {
            const s = pairSpan(e.a, e.b);
            const range = s.first ? `${s.seasons} seasons, ${s.first}–${s.last}` : 'no shared season';
            return `${initials(e.a)}–${initials(e.b)} ${e.w} (${range})`;
        });
        const runner = cat.runnerUp;
        return `<svg class="trio-svg" viewBox="0 0 300 210" role="img" aria-label="${t.names.join(', ')}">${edges}${nodes}</svg>
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
                    <div class="duo-lane-name">${name}</div>
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
            ? `${ch.from} → ${ch.mid} → ${ch.end} (${ch.w1} + ${ch.w2}) is the heaviest chain of #1 targets in the data. `
            : '';
        const spokeTxt = cat.spokeFeeds.length === 0
            ? `nobody's #1 target is ${cat.spoke} — he is the source of this link, not its hub`
            : cat.spokeFeeds.length === 1
                ? `the only player whose #1 target is ${cat.spoke} is ${cat.spokeFeeds[0]}`
                : `${cat.spokeFeeds.length} players — ${cat.spokeFeeds.map(firstName).join(', ')} — have ${cat.spoke} as theirs`;
        const traffic = `${cat.hubFeeds.length} players run their offense through ${cat.hub}; ${spokeTxt}.`;
        const others = (cat.others || []).map(p =>
            `${p.name1} → ${p.name2} · ${p.weight} assists, ${p.games} games`);
        const othersLine = (cat.others || []).length
            ? `<div class="duo-foot">True of ${cat.totalLinks} links in all; the next ${cat.others.length}: ${others.join(' · ')}.</div>`
            : '';
        return `<div class="duo-names"><span class="duo-name" ${c1}>${d.name1}</span><span class="duo-vs">→</span><span class="duo-name" ${c2}>${d.name2}</span></div>
                <div class="duo-stats">${stats}</div>
                <div class="duo-lanes">${lane(d.name1)}${lane(d.name2)}
                    <div class="duo-axis"><span>${lo}</span><span>${hi}</span></div>
                </div>
                <div class="duo-foot">${chainLine}${traffic}</div>
                ${othersLine}`;
    }

    // ===== THE PAIR LINKS — a link X → Y counts when X's #1 assist target is Y, and Y's
    // #1 assist source is X: the feeder and the finisher chose each other. Directional on
    // purpose. Before the pass-network field fix (ultiorg repair point-fields) this rule was
    // measured on transposed maps and returned four unrelated pairs; with the direction
    // corrected it returns 13, and the heaviest is the pair the club is known for.
    const mutualLinks = [];
    for (const feeder in given) {
        const fGiven = given[feeder];
        if (!fGiven || Object.keys(fGiven).length === 0) continue;
        const topReceiver = Object.entries(fGiven).sort((a, b) => b[1] - a[1])[0];
        if (!topReceiver || topReceiver[1] === 0) continue;
        const finisher = topReceiver[0];
        if (finisher === feeder) continue;
        // The other half of the rule: Y's biggest source must be X, not merely someone.
        const fRecv = received[finisher];
        if (!fRecv || Object.keys(fRecv).length === 0) continue;
        const topSource = Object.entries(fRecv).sort((a, b) => b[1] - a[1])[0];
        if (!topSource || topSource[1] === 0 || topSource[0] !== feeder) continue;
        const span = pairSpan(feeder, finisher);
        mutualLinks.push({
            name1: feeder, name2: finisher,
            weight: topReceiver[1],
            assists1: topReceiver[1],
            assists2: (given[finisher] || {})[feeder] || 0,
            games: (cooc[feeder] || {})[finisher] || 0,
            seasons: span.seasons,
            first: span.first,
            last: span.last,
        });
    }
    // Ranked by the link itself, not by field time: the claim is about the pass, and the
    // weight is what makes "heaviest" checkable against the numbers on the slide.
    mutualLinks.sort((a, b) => b.weight - a.weight || b.games - a.games);

    // ===== THE TRIANGLE — the three players who shared the most field time, scored by the
    // sum of the three co-occurrence edges. The search is bounded to each player's 12
    // strongest partners. Edges are games on the same roster, never assists.
    const topPartners = {};
    for (const a in cooc) {
        topPartners[a] = Object.entries(cooc[a]).sort((x, y) => y[1] - x[1]).slice(0, 12).map(x => x[0]);
    }
    const triangles = [];
    const triSeen = new Set();
    for (const a in topPartners) {
        const ps = topPartners[a];
        for (let i = 0; i < ps.length; i++) {
            for (let j = i + 1; j < ps.length; j++) {
                const b = ps[i], c = ps[j];
                if ((topPartners[b] || []).indexOf(c) === -1) continue;
                const key = [a, b, c].sort().join('||');
                if (triSeen.has(key)) continue;
                triSeen.add(key);
                const edges = [
                    { a: a, b: b, w: (cooc[a] || {})[b] || 0 },
                    { a: a, b: c, w: (cooc[a] || {})[c] || 0 },
                    { a: b, b: c, w: (cooc[b] || {})[c] || 0 },
                ];
                if (edges.some(e => !e.w)) continue;
                triangles.push({
                    names: [a, b, c].sort(),
                    edges,
                    score: edges.reduce((s, e) => s + e.w, 0),
                });
            }
        }
    }
    triangles.sort((x, y) => y.score - x.score);

    // ===== THE PAIR — the heaviest link the rule finds. Derived, never named: the rule is
    // "the passer's #1 target is the finisher, and the finisher's #1 source is that passer".
    // The weight is also the single heaviest assist link in the pass matrix, so the headline
    // superlative is one the data supports without leaning on field time (where this pair is
    // #9, not #1).
    const duo = mutualLinks[0] || null;
    const duoFeeds1 = duo ? runsThrough(duo.name1) : [];
    const duoFeeds2 = duo ? runsThrough(duo.name2) : [];
    const duoHub = duoFeeds2.length >= duoFeeds1.length ? duo.name2 : duo.name1;
    const duoSpoke = duoHub === duo.name1 ? duo.name2 : duo.name1;
    const duoHubFeeds = duoHub === duo.name1 ? duoFeeds1 : duoFeeds2;
    const duoSpokeFeeds = duoHub === duo.name1 ? duoFeeds2 : duoFeeds1;
    // feeder → finisher → the finisher's own #1 target, i.e. where the link goes next.
    const duoChainEnd = duo ? topTarget(duo.name2) : null;
    const duoChain = duo && duoChainEnd && duoChainEnd !== duo.name1 ? {
        from: duo.name1, mid: duo.name2, end: duoChainEnd,
        w1: linkWeight(duo.name1, duo.name2), w2: linkWeight(duo.name2, duoChainEnd),
    } : null;
    const duoCombined = duo ? {
        games: ((players[duo.name1] || {}).games || 0) + ((players[duo.name2] || {}).games || 0),
        points: ((players[duo.name1] || {}).total || 0) + ((players[duo.name2] || {}).total || 0),
    } : null;

    // ===== TARGET ACQUIRED =====
    const targetAcq = [];
    for (const passer in given) {
        const total = Object.values(given[passer]).reduce((s, v) => s + v, 0);
        if (total < 20) continue;
        const top = Object.entries(given[passer]).sort((a, b) => b[1] - a[1])[0];
        targetAcq.push({ name: passer, target: top[0], pct: Math.round(top[1] / total * 100) });
    }
    targetAcq.sort((a, b) => b.pct - a.pct);

    // ===== LIFELINE =====
    const lifeline = [];
    for (const receiver in received) {
        const total = Object.values(received[receiver]).reduce((s, v) => s + v, 0);
        if (total < 20) continue;
        const top = Object.entries(received[receiver]).sort((a, b) => b[1] - a[1])[0];
        lifeline.push({ name: receiver, source: top[0], pct: Math.round(top[1] / total * 100) });
    }
    lifeline.sort((a, b) => b.pct - a.pct);

    // ===== THE CONNECTOR — one table: who they receive from, who they give to,
    // and the union of the two. Pass to Me and Good Samaritan were this table's
    // first two columns each wearing a slide of its own. =====
    const connectorRows = [];
    for (const name in players) {
        const games = players[name].games;
        if (games < 100) continue;
        const gp = new Set(Object.keys(given[name] || {}));
        const rp = new Set(Object.keys(received[name] || {}));
        const unique = new Set([...gp, ...rp]).size;
        connectorRows.push({
            name, games, unique,
            inCount: rp.size,
            outCount: gp.size,
        });
    }
    // Ranked by how many different names a player traded the disc with, not per game: the
    // per-game rate falls as careers lengthen, so it was always won by whoever sat just
    // above the floor. Volume is the claim here, and games are shown beside it.
    connectorRows.sort((a, b) => b.unique - a.unique || b.games - a.games);

    // ===== LONGEVITY — one table, not four leaderboards of the same four names.
    // season_count counts season-instances (summer and winter separately); span
    // counts calendar years. Streak Master used to rank consecutive calendar
    // years while labelling them "seasons", and is dropped rather than relabelled:
    // the span column already says who never left. The Archivist was a single row
    // (Ilkka, the only 2006 founder still active), so it became the ★ marker.
    const longevity = Object.entries(players).map(([name, d]) => ({
        name,
        seasons: d.season_count,
        first: d.first_year,
        last: d.last_year,
        span: d.last_year - d.first_year + 1,
        founder: d.first_year === 2006 && d.last_year >= 2023,
    })).sort((a, b) => b.seasons - a.seasons || b.span - a.span).slice(0, 6);

    // ===== THE PHOENIX =====
    const phoenix = [];
    for (const [name, d] of Object.entries(players)) {
        const yrs = [...new Set(d.seasons.map(s => { const m = s.match(/^\d{4}/); return m ? parseInt(m[0]) : null; }).filter(Boolean))].sort((a, b) => a - b);
        let maxGap = 0, gapBefore = 0, gapAfter = 0;
        for (let i = 1; i < yrs.length; i++) {
            const gap = yrs[i] - yrs[i-1];
            if (gap >= 3 && gap > maxGap) {
                maxGap = gap; gapBefore = yrs[i-1]; gapAfter = yrs[i];
            }
        }
        if (maxGap >= 3) phoenix.push({ name, gap: maxGap, before: gapBefore, after: gapAfter, seasons: d.season_count });
    }
    phoenix.sort((a, b) => b.gap - a.gap);

    // ===== SCORING — volume and rate side by side. Points Machine, The Legend,
    // Goal Machine and Assist King were one table torn into four slides.
    // Speed Runner is dropped rather than merged: it filtered players with 100+
    // career points and ranked them by total career games, which is "fewest
    // games played", not "fastest to 100" — the per-game point history the label
    // claims would need is not in the data. =====
    // The all-time leader in each counting column. When one name owns points, assists and
    // games at the same time the table says so on the cell — that sweep is the story of the
    // list, and a plain sort order hides it.
    const allTimeLeader = {
        total: Math.max.apply(null, Object.values(players).map(d => d.total)),
        goals: Math.max.apply(null, Object.values(players).map(d => d.goals)),
        assists: Math.max.apply(null, Object.values(players).map(d => d.assists)),
        games: Math.max.apply(null, Object.values(players).map(d => d.games)),
    };
    const LEAD_MARK = '<span class="cat-mark">▲</span>';
    const scoringVolume = Object.entries(players)
        .sort((a, b) => b[1].total - a[1].total)
        .slice(0, 6)
        .map(([name, d]) => ({
            name,
            cells: [
                d.total + (d.total === allTimeLeader.total ? LEAD_MARK : ''),
                d.goals + (d.goals === allTimeLeader.goals ? LEAD_MARK : ''),
                d.assists + (d.assists === allTimeLeader.assists ? LEAD_MARK : ''),
                d.games + (d.games === allTimeLeader.games ? LEAD_MARK : ''),
            ],
        }));

    // Rate needs a floor. At 5 games the winner is a 10-game sample (Jaakko Junttu, 2.80),
    // not a career; 100 games is about four seasons on a roster. The floor is stated in the
    // panel title so the ranking can be checked.
    const scoringRate = Object.entries(players)
        .filter(([, d]) => d.games >= 100)
        .map(([name, d]) => ({ name, perGame: (d.total / d.games).toFixed(2), points: d.total, games: d.games }))
        .sort((a, b) => b.perGame - a.perGame)
        .slice(0, 4);

    // ===== PURE PLAYMAKER (assists > goals, min 5 games) =====
    const playmaker = Object.entries(players).filter(([, d]) => d.assists > d.goals && d.games >= 50).map(([n, d]) => ({
        name: n, assists: d.assists, goals: d.goals, ratio: (d.assists / Math.max(d.goals, 1)).toFixed(2)
    })).sort((a, b) => b.ratio - a.ratio).slice(0, 4);

    // ===== FINISHER (goals > assists, min 50 games) =====
    const finisher = Object.entries(players).filter(([, d]) => d.goals > d.assists && d.games >= 50).map(([n, d]) => ({
        name: n, goals: d.goals, assists: d.assists, ratio: (d.goals / Math.max(d.assists, 1)).toFixed(2)
    })).sort((a, b) => b.ratio - a.ratio).slice(0, 4);

    // ===== WORLD TRAVELER =====
    const travel = Object.entries(players).sort((a, b) => b[1].teams.length - a[1].teams.length).slice(0, 3);

    // ===== DEFENSE — volume and rate. Four slides (goals/assists × total/rate)
    // become one: the goals/assists split survives as columns, and defense points
    // (D-goals + D-assists) is the quantity the two rankings can both be measured
    // against. =====
    const defVolume = Object.entries(players)
        .map(([name, d]) => ({ name, dg: d.defense_goals, da: d.defense_assists, dp: d.defense_goals + d.defense_assists, games: d.games }))
        .filter(r => r.dp > 0)
        .sort((a, b) => b.dp - a.dp)
        .slice(0, 4);

    const defRate = Object.entries(players)
        .map(([name, d]) => ({ name, dp: d.defense_goals + d.defense_assists, games: d.games, perGame: ((d.defense_goals + d.defense_assists) / d.games).toFixed(2) }))
        .filter(r => r.dp > 0 && r.games >= 10)
        .sort((a, b) => b.perGame - a.perGame)
        .slice(0, 4);

    // ===== SEASON SPLIT — the Bear, the Cub and both Specialists on one screen.
    // "Only played winter" is a fact about a player, not a leaderboard, so the
    // specialists ride in as the ◆ rows instead of two slides of their own. =====
    function seasonRate(season) {
        const other = season === 'winter' ? 'summer_games' : 'winter_games';
        const pts = (d) => d[`${season}_goals`] + d[`${season}_assists`];
        const rows = Object.entries(players)
            .filter(([, d]) => d[`${season}_games`] >= 8 && pts(d) >= 50)
            .map(([name, d]) => ({
                name, perGame: (pts(d) / d[`${season}_games`]).toFixed(2),
                points: pts(d), games: d[`${season}_games`],
                mark: d[other] === 0 ? '◆' : '',
            }))
            .sort((a, b) => b.perGame - a.perGame)
            .slice(0, 3);
        const specialist = Object.entries(players)
            .filter(([, d]) => d[`${season}_games`] > 0 && d[other] === 0)
            .sort((a, b) => b[1][`${season}_games`] - a[1][`${season}_games`])[0];
        if (specialist && !rows.some(r => r.name === specialist[0])) {
            const [name, d] = specialist;
            rows.push({ name, perGame: (pts(d) / d[`${season}_games`]).toFixed(2), points: pts(d), games: d[`${season}_games`], mark: '◆' });
        }
        return rows;
    }
    const seasonWinter = seasonRate('winter');
    const seasonSummer = seasonRate('summer');

    const categories = [
        { name: 'Longevity', desc: 'Seasons played, and how many years they stayed on the roster', type: 'table', columns: ['Player', 'Seasons', 'Career'], foot: '<span class="cat-mark">★</span> founding member (2006), still active', rows: longevity.map(r => ({ name: r.name, mark: r.founder ? '★' : '', cells: [String(r.seasons), `${r.first}–${r.last}<span class="cat-yrs"> · ${r.span} yrs</span>`] })) },
        { name: 'The Phoenix', desc: 'Away three or more years, then back on the roster', type: 'gaps', data: phoenix.slice(0, 3) },
        { name: 'Aging Squad', desc: 'Roster size and mean squad age, 2006–2026', type: 'chart' },
        { name: 'The Triangle', desc: 'The three players who shared the most field time in 20 years', type: 'trio', triangle: triangles[0], runnerUp: triangles[1] },
        { name: 'The Pair', desc: 'The passer\'s #1 target is the finisher, and the finisher\'s #1 source is that passer — the heaviest of the 13 links where that is true', type: 'duo', duo: duo, others: mutualLinks.slice(1, 5), totalLinks: mutualLinks.length, chain: duoChain, hub: duoHub, spoke: duoSpoke, hubFeeds: duoHubFeeds, spokeFeeds: duoSpokeFeeds, combined: duoCombined },
        { name: 'The Connector', desc: 'Different players passed to or received from (100+ games)', foot: 'Total counts each name once — In and Out overlap', type: 'table', columns: ['Player', 'In', 'Out', 'Total', 'Games'], rows: connectorRows.slice(0, 6).map(r => ({ name: r.name, cells: [String(r.inCount), String(r.outCount), String(r.unique), String(r.games)] })) },
        { name: 'Scoring', desc: 'The all-time counting list, and the best rate per game', type: 'split', foot: '▲ the all-time leader in that column', panels: [
            { title: 'Most points', columns: ['Player', 'Pts', 'G', 'A', 'Games'], rows: scoringVolume },
            { title: 'Best points per game (100+ games)', columns: ['Player', 'Pts/g', 'Pts', 'Games'], rows: scoringRate.map(r => ({ name: r.name, cells: [r.perGame, String(r.points), String(r.games)] })) },
        ] },
        { name: 'Ratio', desc: 'Assists per goal, and goals per assist (min 50 games)', type: 'split', panels: [
            { title: 'Pure playmakers', columns: ['Player', 'A:G', 'A', 'G'], rows: playmaker.map(r => ({ name: r.name, cells: [`${r.ratio}x`, String(r.assists), String(r.goals)] })) },
            { title: 'Finishers', columns: ['Player', 'G:A', 'G', 'A'], rows: finisher.map(r => ({ name: r.name, cells: [`${r.ratio}x`, String(r.goals), String(r.assists)] })) },
        ] },
        { name: 'Defense', desc: 'Points scored on defense; rate needs 10+ games', type: 'split', panels: [
            { title: 'Most defense points', columns: ['Player', 'DP', 'DG', 'DA'], rows: defVolume.map(r => ({ name: r.name, cells: [String(r.dp), String(r.dg), String(r.da)] })) },
            { title: 'Best defense rate', columns: ['Player', 'DP/g', 'DP', 'Games'], rows: defRate.map(r => ({ name: r.name, cells: [r.perGame, String(r.dp), String(r.games)] })) },
        ] },
        { name: 'Season Split', desc: 'Points per game in winter and in summer', type: 'split', foot: '<span class="cat-mark">◆</span> played only that season type', panels: [
            { title: 'Winter', columns: ['Player', 'Pts/g', 'Pts', 'Games'], rows: seasonWinter.map(r => ({ name: r.name, mark: r.mark, cells: [r.perGame, String(r.points), String(r.games)] })) },
            { title: 'Summer', columns: ['Player', 'Pts/g', 'Pts', 'Games'], rows: seasonSummer.map(r => ({ name: r.name, mark: r.mark, cells: [r.perGame, String(r.points), String(r.games)] })) },
        ] },
        { name: 'World Traveler', desc: 'Most different teams played on', type: 'single', data: travel.map(([n, d]) => ({ name: n, stat: `${d.teams.length} teams` })) },
    ];

    const scrollContainer = document.getElementById('categories-scroll');
    const scrollProgress = document.getElementById('scroll-progress');

    // Build category slides
    scrollContainer.innerHTML = categories.map((cat, idx) => {
        const rows = (cat.type === 'chart' || cat.type === 'table' || cat.type === 'gaps' || cat.type === 'split' || cat.type === 'trio' || cat.type === 'duo') ? '' : cat.data.map((p, rowIdx) => {
            if (cat.type === 'pair') {
                const n1 = normalize(p.name1), n2 = normalize(p.name2);
                const click = (n1 in players && n2 in players) ? `data-player1="${n1}" data-player2="${n2}"` : '';
                return `<div class="category-row" ${click}>
                        <span class="category-rank ${rowIdx === 0 ? 'gold' : rowIdx === 1 ? 'silver' : 'bronze'}">${rowIdx + 1}</span>
                        <span class="category-pair">
                            <span class="category-player-name">${n1}</span>
                            <span class="category-pair-arrow">↔</span>
                            <span class="category-player-name">${n2}</span>
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

