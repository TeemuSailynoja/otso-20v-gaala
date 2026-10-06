// The category slides' claims, tested against a made-up squad.
//
// These are the page's assertions about the club — who fed whom, who came back,
// what a "rate" is allowed to mean — and until js/categories.js existed none of
// them could be tested at all, because every rule was written between two
// template literals. Each test below states the rule in the test name and then
// shows the rule firing (and, where a floor is the point, *not* firing).
import test from 'node:test';
import assert from 'node:assert/strict';

import { buildCategorySlides } from '../../js/categories.js';
import { player, slide } from './helpers.mjs';

// A data object shaped like the site's: id keys, names separate, pass network
// and co-occurrence as the build publishes them.
function mk({ players = {}, given = {}, received = {}, cooc = {}, names = {}, summary = {}, trophies = {} } = {}) {
    return { players, given, received, cooc, names, summary, trophies,
             passNetwork: { given, received }, cooccurrence: cooc };
}

// ---------------------------------------------------------------- The Pair
test('The Pair: a link counts only when the feeder and the finisher choose each other', () => {
    // 1 feeds 2 most (9) and 2's biggest source is 1 → a link.
    // 2 feeds 5 most (4) but 5's biggest source is 4 (7) → not a link.
    // 4 feeds 5 most (7) and 5's biggest source is 4 → a link.
    const d = mk({
        given: { 1: { 2: 9, 3: 1 }, 2: { 5: 4 }, 4: { 5: 7 } },
        received: { 2: { 1: 9 }, 5: { 4: 7, 2: 4 }, 3: { 1: 1 } },
        players: { 1: player({ games: 40, total: 60 }), 2: player({ games: 44, total: 70 }),
                   4: player({ games: 30 }), 5: player({ games: 33 }) },
        cooc: { 1: { 2: 30 }, 2: { 1: 30 }, 4: { 5: 12 }, 5: { 4: 12 } },
    });
    const { categories } = buildCategorySlides(d);
    const pair = slide(categories, 'The Pair');
    assert.equal(pair.totalLinks, 2, 'the one-sided 2→5 must not count');
    assert.deepEqual([pair.duo.name1, pair.duo.name2], ['1', '2']);
    assert.equal(pair.duo.weight, 9);
    assert.equal(pair.duo.games, 30, 'field time comes from co-occurrence, not assists');
    assert.deepEqual(pair.others.map(o => [o.name1, o.name2]), [['4', '5']]);
});

test('The Pair: ranked by the weight of the pass, not by field time', () => {
    // The heavier link plays fewer shared games; the slide must still lead with it.
    const d = mk({
        given: { 1: { 2: 9 }, 3: { 4: 20 } },
        received: { 2: { 1: 9 }, 4: { 3: 20 } },
        cooc: { 1: { 2: 200 }, 2: { 1: 200 }, 3: { 4: 5 }, 4: { 3: 5 } },
    });
    const { categories } = buildCategorySlides(d);
    assert.equal(slide(categories, 'The Pair').duo.weight, 20);
});

test('The Pair: the hub is whichever half of the pair more players feed', () => {
    const d = mk({
        given: { 1: { 2: 9 }, 7: { 2: 6 }, 8: { 2: 5 }, 2: { 1: 4 } },
        received: { 2: { 1: 9, 7: 6, 8: 5 }, 1: { 2: 4 } },
        cooc: { 1: { 2: 40 }, 2: { 1: 40 } },
    });
    const { categories } = buildCategorySlides(d);
    const pair = slide(categories, 'The Pair');
    assert.equal(pair.hub, '2', 'three players feed 2, none feed 1');
    assert.equal(pair.spoke, '1');
    assert.deepEqual(pair.hubFeeds, ['1', '7', '8']);
});

test("The Pair: the chain follows where the finisher's own disc goes next", () => {
    const d = mk({
        given: { 1: { 2: 9 }, 2: { 5: 4, 6: 2 } },
        received: { 2: { 1: 9 }, 5: { 2: 4 } },
    });
    const { categories } = buildCategorySlides(d);
    const { chain } = slide(categories, 'The Pair');
    assert.deepEqual([chain.from, chain.mid, chain.end], ['1', '2', '5']);
    assert.deepEqual([chain.w1, chain.w2], [9, 4]);
});

test('The Pair: a chain that loops back to the feeder is no chain at all', () => {
    const d = mk({ given: { 1: { 2: 9 }, 2: { 1: 8 } }, received: { 2: { 1: 9 }, 1: { 2: 8 } } });
    assert.equal(slide(buildCategorySlides(d).categories, 'The Pair').chain, null);
});

// ------------------------------------------------------------- The Triangle
test('an empty pass network yields no pair rather than an error', () => {
    // The slide spec already carries `duo: null`; the math must not throw before
    // the renderer gets there. Real data always has a network, so this only ever
    // fires on a made-up corpus — which is exactly what these tests are.
    const pair = slide(buildCategorySlides(mk()).categories, 'The Pair');
    assert.equal(pair.duo, null);
    assert.equal(pair.hub, null);
    assert.deepEqual(pair.hubFeeds, []);
    assert.equal(pair.chain, null);
    assert.equal(pair.combined, null);
});

test('The Triangle: three mutual partners, scored by the sum of the three edges', () => {
    const d = mk({
        cooc: {
            1: { 2: 30, 3: 12, 4: 5 }, 2: { 1: 30, 3: 20, 4: 4 },
            3: { 1: 12, 2: 20, 4: 3 }, 4: { 1: 5, 2: 4, 3: 3 },
        },
    });
    const trio = slide(buildCategorySlides(d).categories, 'The Triangle');
    assert.deepEqual(trio.triangle.edges.map(e => e.w), [30, 12, 20]);
    assert.equal(trio.triangle.score, 62);
    assert.deepEqual(trio.runnerUp.score, 39, 'the next trio is the same trio with its weakest edge');
});

test('The Triangle: a missing edge disqualifies the trio', () => {
    // 1-2 and 1-3 exist; 2-3 does not.
    const d = mk({ cooc: { 1: { 2: 30, 3: 12 }, 2: { 1: 30 }, 3: { 1: 12 } } });
    assert.equal(slide(buildCategorySlides(d).categories, 'The Triangle').triangle, undefined);
});

test('The Triangle: the vertex order is alphabetical in NAMES, not in keys', () => {
    // Keys sort 1,2,3; the names sort Zeta, Mikko, Aapo → Aapo, Mikko, Zeta.
    // This is the rule that broke when keys stopped being names.
    const d = mk({
        names: { 1: 'Zeta Zeron', 2: 'Aapo Aatonen', 3: 'Mikko Mäkelä' },
        cooc: { 1: { 2: 30, 3: 12 }, 2: { 1: 30, 3: 20 }, 3: { 1: 12, 2: 20 } },
    });
    assert.deepEqual(slide(buildCategorySlides(d).categories, 'The Triangle').triangle.names, ['2', '3', '1']);
});

test("The Triangle: the search is bounded to each player's twelve strongest partners", () => {
    // 1 plays with 14 partners; only the top 12 can form a trio with it.
    const cooc = { 1: {} };
    for (let i = 2; i <= 15; i++) {
        cooc[1][i] = 100 - i;              // descending strength; 14 and 15 are weakest
        cooc[i] = { 1: 100 - i };
    }
    cooc[2][3] = 5; cooc[3][2] = 5;
    const trio = slide(buildCategorySlides(mk({ cooc })).categories, 'The Triangle');
    assert.ok(trio.triangle.names.includes('1'), 'a top-12 partner still forms the trio');
    assert.ok(!trio.triangle.names.includes('15'), 'the weakest partners are never considered');
});

// ----------------------------------------------------------- pairSpan
test('pairSpan: shared seasons only, and an empty intersection is null-ended, never 0–0', () => {
    const d = mk({
        players: { 1: player({ years: [2010, 2011, 2012] }), 2: player({ years: [2011, 2012, 2013] }),
                   3: player({ years: [2020] }) },
    });
    const { pairSpan } = buildCategorySlides(d);
    assert.deepEqual(pairSpan('1', '2'), { seasons: 2, first: 2011, last: 2012, years: [2011, 2012] });
    assert.deepEqual(pairSpan('1', '3'), { seasons: 0, first: null, last: null, years: [] });
});

// ------------------------------------------------------------ thresholds
test('Scoring: a rate needs 100 games; the counting list needs nothing', () => {
    const d = mk({ players: {
        1: player({ games: 99, total: 300 }),   // 3.03 — best in the room, still out
        2: player({ games: 100, total: 250 }),  // 2.50 — in
        3: player({ games: 400, total: 260 }),  // 0.65 — in, last
    } });
    const panels = slide(buildCategorySlides(d).categories, 'Scoring').panels;
    assert.deepEqual(panels[0].rows.map(r => r.name), ['1', '3', '2'], 'volume ignores the floor');
    assert.deepEqual(panels[1].rows.map(r => r.name), ['2', '3'], 'the 99-game career is excluded');
});

test('Scoring: the all-time leader in each column carries the ▲ mark', () => {
    const d = mk({ players: {
        1: player({ total: 500, goals: 100, assists: 400, games: 200 }),
        2: player({ total: 300, goals: 250, assists: 50, games: 400 }),
    } });
    const rows = slide(buildCategorySlides(d).categories, 'Scoring').panels[0].rows;
    assert.deepEqual(rows[0].cells, ['500<span class="cat-mark">▲</span>', '100',
                                     '400<span class="cat-mark">▲</span>', '200']);
    assert.deepEqual(rows[1].cells, ['300', '250<span class="cat-mark">▲</span>',
                                     '50', '400<span class="cat-mark">▲</span>']);
});

test('Ratio: playmakers need more assists than goals and 50 games', () => {
    const d = mk({ players: {
        1: player({ assists: 60, goals: 10, games: 50 }),   // in, 6.00x
        2: player({ assists: 60, goals: 10, games: 49 }),   // out: floor
        3: player({ assists: 10, goals: 60, games: 90 }),   // out: wrong direction
    } });
    const panels = slide(buildCategorySlides(d).categories, 'Ratio').panels;
    assert.deepEqual(panels[0].rows.map(r => [r.name, r.cells[0]]), [['1', '6.00x']]);
    assert.deepEqual(panels[1].rows.map(r => [r.name, r.cells[0]]), [['3', '6.00x']], 'the finisher panel is the mirror');
});

test('Defense: volume counts anyone with a defense point; the rate needs 10 games', () => {
    const d = mk({ players: {
        1: player({ defense_goals: 4, defense_assists: 2, games: 3 }),   // volume only
        2: player({ defense_goals: 1, defense_assists: 1, games: 10 }),  // both
    } });
    const panels = slide(buildCategorySlides(d).categories, 'Defense').panels;
    assert.deepEqual(panels[0].rows.map(r => r.name), ['1', '2']);
    assert.deepEqual(panels[1].rows.map(r => r.name), ['2'], 'a 3-game sample cannot win a rate');
    assert.deepEqual(panels[1].rows[0].cells, ['0.20', '2', '10']);
});

test('The Connector: reach is the union of names passed to and received from, at 100+ games', () => {
    const d = mk({
        players: { 1: player({ games: 120 }), 2: player({ games: 99 }) },
        given: { 1: { 9: 1, 8: 1 }, 2: { 9: 5 } },
        received: { 1: { 8: 1, 7: 1 } },
    });
    const rows = slide(buildCategorySlides(d).categories, 'The Connector').rows;
    assert.deepEqual(rows.map(r => r.cells), [['2', '2', '3', '120']],
        '8 is counted once: In and Out overlap');
    assert.equal(rows.length, 1, 'the 99-game player is below the floor');
});

test('Longevity: season-instances first, ties broken by the longer calendar span, ★ needs 2006 and 2023+', () => {
    const d = mk({ players: {
        1: player({ season_count: 30, first_year: 2006, last_year: 2023 }),  // ★ 18 yrs
        2: player({ season_count: 30, first_year: 2008, last_year: 2026 }),  // tie, 19 yrs → first
        3: player({ season_count: 28, first_year: 2006, last_year: 2020 }),  // founder, gone
    } });
    const rows = slide(buildCategorySlides(d).categories, 'Longevity').rows;
    assert.deepEqual(rows.map(r => [r.name, r.mark]), [['2', ''], ['1', '★'], ['3', '']],
        '30 seasons each: the 19-year career sits above the 18-year one');
    assert.equal(rows[1].cells[1], '2006–2023<span class="cat-yrs"> · 18 yrs</span>');
    assert.equal(rows[2].mark, '', 'a 2006 founder who left in 2020 is not still active');
});

test('The Phoenix: three absent years, then back — and two is not enough', () => {
    const d = mk({ players: {
        1: player({ seasons: ['2010.1', '2011.1', '2016.1'], season_count: 3 }),   // gap 5
        2: player({ seasons: ['2010.1', '2011.1', '2013.1'] }),   // gap 2
        3: player({ seasons: ['2010.1', '2011.1', '2012.1'] }),   // no gap
    } });
    const phoenix = slide(buildCategorySlides(d).categories, 'The Phoenix').data;
    assert.deepEqual(phoenix, [{ name: '1', gap: 5, before: 2011, after: 2016, seasons: 3 }]);
});

test('Season Split: the ◆ row is the player who only ever played that season type', () => {
    const d = mk({ players: {
        // A winter specialist below the 50-point floor: not a leaderboard row, but a fact.
        1: player({ winter_games: 3, winter_goals: 10, winter_assists: 5, summer_games: 0 }),
        2: player({ winter_games: 20, winter_goals: 40, winter_assists: 20, summer_games: 10 }),
        3: player({ winter_games: 7, winter_goals: 90, winter_assists: 0, summer_games: 4 }),
    } });
    const winter = slide(buildCategorySlides(d).categories, 'Season Split').panels[0].rows;
    assert.deepEqual(winter.map(r => [r.name, r.mark]), [['2', ''], ['1', '◆']]);
    assert.deepEqual(winter[0].cells, ['3.00', '60', '20']);
    assert.deepEqual(winter[1].cells, ['5.00', '15', '3'], 'the specialist keeps its own rate');
});

test('World Traveler: ranked by how many different teams, not by points', () => {
    const d = mk({ players: {
        1: player({ teams: ['a', 'b'], total: 900 }),
        2: player({ teams: ['a', 'b', 'c', 'd'], total: 10 }),
        3: player({ teams: ['a'], total: 500 }),
    } });
    assert.deepEqual(slide(buildCategorySlides(d).categories, 'World Traveler').data,
                     [{ name: '2', stat: '4 teams' }, { name: '1', stat: '2 teams' }, { name: '3', stat: '1 teams' }]);
});

// ------------------------------------------- computed but never drawn
// targetAcq and lifeline feed no slide. They are pinned here so that if one is
// ever revived it starts from the same rule, and so that "computed and unread"
// is at least "computed correctly".
test('Target Acquired and Lifeline need 20 assists before a percentage means anything', () => {
    const d = mk({
        given: { 1: { 2: 18, 3: 2 }, 4: { 5: 4 } },
        received: { 2: { 1: 18, 3: 2 }, 5: { 4: 4 } },
    });
    const { targetAcq, lifeline } = buildCategorySlides(d);
    assert.deepEqual(targetAcq, [{ name: '1', target: '2', pct: 90 }]);
    assert.deepEqual(lifeline, [{ name: '2', source: '1', pct: 90 }]);
});
