// The home page's claims, computed. Every ranking, threshold and rule that
// decides what the category slides say lives here, apart from the DOM that
// draws them: this module takes a data object and returns slide specs, so a
// rule can be tested against a small made-up squad instead of only against the
// real 20-year corpus.
//
// The rules are the page's argument -- "the passer's #1 target is the finisher
// and the finisher's #1 source is that passer", "away three years then back",
// "rate needs 100 games" -- and each one is stated once, here, with the reason
// for its floor next to it. Rendering cannot change a claim; if a claim is
// wrong, it is wrong in this file.
//
// Keys throughout: every player reference is a site key (see js/people.js).
// `named()` is the one lookup, bound to the DATA passed in rather than to the
// page's live DATA, which is what keeps this callable from a test.

import { nameIn } from './people.js';

export function buildCategorySlides(DATA) {
    const players = DATA.players || {};
    const passNet = DATA.passNetwork || {};
    const cooc = DATA.cooccurrence || {};
    const given = passNet.given || {};
    const received = passNet.received || {};
    const named = (key) => nameIn(DATA.names, key);

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
                // Two different sorts, on purpose. The dedup key above sorts
                // keys and does not care what they are. This one decides
                // which name sits at the top vertex of the triangle, so it
                // sorts the names a reader sees — sorting the keys here was
                // alphabetical only while the keys happened to be names.
                names: [a, b, c].sort((x, y) => {
                    const nx = named(x), ny = named(y);
                    return nx < ny ? -1 : nx > ny ? 1 : 0;
                }),
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
// Everything below is derived from the pair, so an empty pass network leaves them
// null and empty instead of throwing: the slide spec already carries `duo: null`,
// and a pure function that cannot be called on an empty corpus cannot be tested.
const duoHub = duo === null ? null : (duoFeeds2.length >= duoFeeds1.length ? duo.name2 : duo.name1);
const duoSpoke = duo === null ? null : (duoHub === duo.name1 ? duo.name2 : duo.name1);
const duoHubFeeds = duo === null ? [] : (duoHub === duo.name1 ? duoFeeds1 : duoFeeds2);
const duoSpokeFeeds = duo === null ? [] : (duoHub === duo.name1 ? duoFeeds2 : duoFeeds1);
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

    // pairSpan is the one helper the page's renderers also need: the triangle
    // caption and the duo's season lanes quote the same shared-year span, and a
    // second implementation would be a second answer.
    //
    // targetAcq and lifeline are returned but read by no slide: separating the
    // math from the DOM showed two rankings that were computed on every page
    // load and never drawn. They are kept, tested and named here rather than
    // deleted — the same flag-don't-delete ruling that keeps the three
    // years_all_bears* views published. If they stay unread, the honest move is
    // to stop computing them, not to leave them silent.
    return { categories, pairSpan, linkWeight, topTarget, runsThrough, targetAcq, lifeline };
}
