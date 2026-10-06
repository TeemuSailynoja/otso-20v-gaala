// The timeline's year badges: superlatives computed from the seasons, never
// typed by hand. (The hand-written *prose* beside them is checked separately,
// in tests/js/season_stories.test.mjs.)
import test from 'node:test';
import assert from 'node:assert/strict';

import { computeHighlightBadges } from '../../js/badges.js';

const year = (o) => ({ matches: 0, wins: 0, losses: 0, goals_for: 0, goals_against: 0, roster_players: 0, ...o });
const has = (badges, y, what) => assert.ok((badges[y] || []).includes(what), `${y} should carry "${what}", got ${JSON.stringify(badges[y])}`);
const lacks = (badges, y, what) => assert.ok(!(badges[y] || []).includes(what), `${y} must not carry "${what}"`);

test('a badge is earned by the season, and lands in the order the rules run', () => {
    const years = {
        // 20 games, all won: undefeated, best win rate, most matches, best goal
        // difference, and the smallest roster among seasons long enough to count.
        2020: year({ matches: 20, wins: 20, losses: 0, goals_for: 100, goals_against: 50, roster_players: 10 }),
        // .500 over 16: the toughest qualifying season, the biggest roster, and
        // the biggest single-year intake of the three.
        2021: year({ matches: 16, wins: 8, losses: 8, goals_for: 60, goals_against: 40, roster_players: 30 }),
        // 5–0, but five games is not a season: no badge of any kind.
        2019: year({ matches: 5, wins: 5, losses: 0, goals_for: 30, goals_against: 5, roster_players: 3 }),
    };
    const badges = computeHighlightBadges(years, { seasons: [] });
    // The badge order is the order the rules run: superlatives first, the roster
    // intake last; the timeline renders the array as it comes.
    assert.deepEqual(badges['2021'], ['Toughest season', 'Largest roster', '+20 players']);
    assert.deepEqual(badges['2020'], ['Best win rate', 'Most matches', 'Best goal difference',
                                      'Skeleton crew', 'Undefeated']);
    assert.equal(badges['2019'], undefined, 'a five-game season earns nothing, even undefeated');
});

test('the intake badge is one season only — the biggest jump, not every jump', () => {
    const years = {
        2020: year({ matches: 20, roster_players: 10 }),
        2021: year({ matches: 20, roster_players: 18 }),   // +8
        2022: year({ matches: 20, roster_players: 30 }),   // +12, the winner
    };
    const badges = computeHighlightBadges(years, { seasons: [] });
    assert.deepEqual(badges['2022'].filter(b => b.endsWith('players')), ['+12 players']);
    assert.deepEqual((badges['2021'] || []).filter(b => b.endsWith('players')), []);
});

test('the win-rate badges only look at seasons with 15+ games', () => {
    const years = {
        2020: year({ matches: 14, wins: 14, losses: 0, goals_for: 40, goals_against: 40, roster_players: 4 }),
        2021: year({ matches: 15, wins: 9, losses: 6, goals_for: 60, goals_against: 40, roster_players: 40 }),
        2022: year({ matches: 20, wins: 18, losses: 2, goals_for: 60, goals_against: 40, roster_players: 30 }),
    };
    const badges = computeHighlightBadges(years, { seasons: [] });
    assert.equal(badges['2020'], undefined, 'a perfect 14-game season is a sample, not a record');
    has(badges, '2022', 'Best win rate');   // 90% beats 60%; the 100% is not in the room
    has(badges, '2021', 'Toughest season');
    has(badges, '2022', 'Skeleton crew');   // the 4-name crew is too short to be a skeleton crew
    lacks(badges, '2020', 'Skeleton crew');
});

test('Undefeated needs no losses and 15 wins, not a short perfect season', () => {
    const years = {
        2020: year({ matches: 15, wins: 15, losses: 0 }),
        2021: year({ matches: 14, wins: 14, losses: 0 }),
        2022: year({ matches: 20, wins: 19, losses: 1 }),
    };
    const badges = computeHighlightBadges(years, { seasons: [] });
    has(badges, '2020', 'Undefeated');
    lacks(badges, '2021', 'Undefeated');
    lacks(badges, '2022', 'Undefeated');
});

test('Kulta molemmissa needs two gold season rows in the same year', () => {
    const years = { 2022: year({ matches: 20, wins: 20, losses: 0 }) };
    const trophies = { seasons: [
        { year: 2022, season_type: 'summer', medal: 'gold' },
        { year: 2022, season_type: 'winter', medal: 'gold' },
        { year: 2021, season_type: 'summer', medal: 'gold' },
        { year: 2021, season_type: 'winter', medal: 'silver' },
    ] };
    const badges = computeHighlightBadges(years, trophies);
    has(badges, '2022', 'Kulta molemmissa');
    lacks(badges, '2021', 'Kulta molemmissa');
    has(badges, '2021', 'First medal');
});

test('First medal goes to the earliest season that medalled at all', () => {
    const years = { 2009: year({ matches: 16, wins: 9, losses: 7 }), 2011: year({ matches: 20, wins: 20, losses: 0 }) };
    const trophies = { seasons: [
        { year: 2011, season_type: 'winter', medal: 'gold' },
        { year: 2009, season_type: 'winter', medal: 'bronze' },
    ] };
    const badges = computeHighlightBadges(years, trophies);
    has(badges, '2009', 'First medal');
    lacks(badges, '2011', 'First medal');
});

test('a season with no trophy rows still gets its computed badges', () => {
    const badges = computeHighlightBadges({ 2020: year({ matches: 20, wins: 20, losses: 0 }) }, null);
    has(badges, '2020', 'Undefeated');
});
