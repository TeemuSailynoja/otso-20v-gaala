// The season notes in js/badges.js are hand-written. When the career numbers
// were corrected, six of them quietly became false — a "26–2 again" beside a
// card that said 25–2. This test is the reason that cannot happen again: every
// number a story quotes is measured against the same object the timeline
// renders next to it, and every superlative is re-derived from the data.
//
// Unlike the rule tests, this one reads the real corpus on purpose: it is about
// what this club's record actually says.
import test from 'node:test';
import assert from 'node:assert/strict';
import { SEASON_STORY } from '../../js/badges.js';
import { stubFetch } from './helpers.mjs';
import { loadSiteData } from '../../js/data.js';

stubFetch();
const DATA = await loadSiteData();

const years = DATA.years;                 // years_otso.json — what the stream shows
const seasons = DATA.trophies.seasons;
const ys = Object.keys(years).sort((a, b) => a - b);

const gd = (y) => years[y].goals_for - years[y].goals_against;
const played = (y) => years[y].wins + years[y].losses;
const winPct = (y) => Math.round((years[y].wins / played(y)) * 100);
const story = (y) => SEASON_STORY[y].join(' ');

// Roster change from one year to the next, in calendar order.
const deltas = ys.slice(1).map((y, i) => ({
    year: y, from: ys[i], d: years[y].roster_players - years[ys[i]].roster_players,
}));
const seasonRow = (y, which) => seasons.find(s => String(s.year) === y && s.season === which);
const onPodium = (row) => Boolean(row) && (row.medal || ['1.', '2.', '3.'].includes(row.placement));

test('every season has a story and every story has a season', () => {
    assert.deepEqual(Object.keys(SEASON_STORY).sort((a, b) => a - b), ys,
        'a season without a note, or a note for a season that never happened');
});

test('the numbers a story quotes are the numbers the page shows', () => {
    // The checks are patterns in the prose, so a new note is checked by being
    // written in the same shape — "25–2", "27 matches", "35 names", "+179".
    const patternsFor = (y) => [
        [/(\d+)\u2013(\d+)/g, (m, w, l) => (Number(w) === years[y].wins && Number(l) === years[y].losses
            ? null : `record is ${years[y].wins}\u2013${years[y].losses}`), 'win–loss line'],
        [/(\d+) matches/g, (m, n) => (Number(n) === years[y].matches ? null : `matches is ${years[y].matches}`), 'match count'],
        [/(\d+) names/g, (m, n) => (Number(n) === years[y].roster_players ? null : `roster is ${years[y].roster_players}`), 'roster size'],
        [/(\d+) losses/g, (m, n) => (Number(n) === years[y].losses ? null : `losses is ${years[y].losses}`), 'loss count'],
        [/(\d+) wins/g, (m, n) => (Number(n) === years[y].wins ? null : `wins is ${years[y].wins}`), 'win count'],
        [/(?:jumps|drops) (\d+) to/g, (m, n) => {
            const prev = ys[ys.indexOf(y) - 1];
            const d = years[y].roster_players - years[prev].roster_players;
            const want = m[0].startsWith('jumps') ? Number(n) : -Number(n);
            return d === want ? null
                : `the change from ${prev} was ${d > 0 ? '+' : ''}${d}`;
        }, 'roster change'],
        [/\+(\d+)(?![\d%])/g, (m, n) => (Number(n) === gd(y) ? null : `goal difference is ${gd(y)}`), 'goal difference'],
        [/(\d+) fewer goals scored than conceded/g, (m, n) => (gd(y) === -Number(n) ? null : `goal difference is ${gd(y)}`), 'negative goal difference'],
    ];
    const wrong = [];
    for (const y of ys) {
        const text = story(y);
        for (const [re, check, label] of patternsFor(y)) {
            for (const m of text.matchAll(re)) {
                const problem = check(m, ...m.slice(1));
                if (problem) wrong.push(`${y}: "${m[0]}" (${label}) — ${problem}`);
            }
        }
    }
    assert.deepEqual(wrong, [], `season stories contradict the data:\n${wrong.join('\n')}`);
});

// Each claim below must appear in the note it belongs to — so the table cannot
// drift away from the prose — and must still be true of the record.
const CLAIMS = [
    { year: '2006', phrase: "Otso's first competitive year", check: () => ys[0] === '2006' },
    {
        year: '2007',
        phrase: 'the thinnest roster in the record',
        check: () => years['2007'].roster_players === Math.min(...ys.map(y => years[y].roster_players)),
    },
    {
        year: '2009',
        phrase: 'The first medal arrives',
        check: () => String(seasons.filter(s => s.medal).sort((a, b) => a.year - b.year)[0].year) === '2009',
    },
    {
        year: '2011',
        phrase: 'First year with a podium in both seasons',
        check: () => onPodium(seasonRow('2011', 'summer')) && onPodium(seasonRow('2011', 'winter'))
            && ys.filter(y => Number(y) < 2011)
                .every(y => !(onPodium(seasonRow(y, 'summer')) && onPodium(seasonRow(y, 'winter')))),
    },
    {
        year: '2012',
        phrase: 'Undefeated',
        check: () => years['2012'].losses === 0 && years['2012'].wins === years['2012'].matches,
    },
    {
        year: '2013',
        phrase: 'the biggest single-year intake in the record',
        check: () => {
            const best = deltas.reduce((a, b) => (b.d > a.d ? b : a));
            return best.year === '2013' && best.d === years['2013'].roster_players - years['2012'].roster_players;
        },
    },
    {
        year: '2014',
        phrase: 'the first 170+ goal difference',
        check: () => gd('2014') >= 170 && ys.filter(y => Number(y) < 2014).every(y => gd(y) < 170),
    },
    {
        year: '2014',
        phrase: 'winter silver ends the run of double gold',
        check: () => seasonRow('2014', 'winter').medal === 'silver'
            && seasonRow('2013', 'winter').medal === 'gold' && seasonRow('2013', 'summer').medal === 'gold',
    },
    {
        year: '2015',
        phrase: 'the first of three straight titles in both seasons',
        check: () => ['2015', '2016', '2017'].every(y => seasonRow(y, 'summer').medal === 'gold'
                && seasonRow(y, 'winter').medal === 'gold')
            && !(seasonRow('2014', 'summer').medal === 'gold' && seasonRow('2014', 'winter').medal === 'gold')
            && !(seasonRow('2018', 'summer').medal === 'gold' && seasonRow('2018', 'winter').medal === 'gold'),
    },
    {
        year: '2016',
        phrase: 'the fifth straight season above 90%',
        check: () => ['2012', '2013', '2014', '2015', '2016'].every(y => winPct(y) > 90) && winPct('2011') <= 90,
    },
    {
        year: '2017',
        phrase: 'The busiest season so far',
        check: () => years['2017'].matches === Math.max(...ys.filter(y => Number(y) <= 2017).map(y => years[y].matches)),
    },
    {
        year: '2018',
        phrase: 'a then-record +211 goal difference',
        check: () => gd('2018') === Math.max(...ys.filter(y => Number(y) <= 2018).map(gd)),
    },
    {
        year: '2019',
        phrase: 'Still the busiest year',
        check: () => years['2019'].matches === Math.max(...ys.map(y => years[y].matches)),
    },
    {
        year: '2019',
        phrase: 'the most in a season since 2009',
        check: () => years['2019'].losses > Math.max(...ys.filter(y => Number(y) >= 2010 && Number(y) <= 2018).map(y => years[y].losses))
            && years['2009'].losses > years['2019'].losses,
    },
    {
        year: '2020',
        phrase: 'the winter season has no recorded placement',
        check: () => {
            const row = seasonRow('2020', 'winter');
            return Boolean(row) && !row.placement && !row.medal;
        },
    },
    {
        year: '2021',
        phrase: 'the steepest fall in the record',
        check: () => deltas.reduce((a, b) => (b.d < a.d ? b : a)).year === '2021',
    },
    {
        year: '2022',
        phrase: 'the largest goal difference in the record',
        check: () => gd('2022') === Math.max(...ys.map(gd)),
    },
    {
        year: '2023',
        phrase: 'the first summer outside the podium since 2010',
        check: () => !onPodium(seasonRow('2023', 'summer')) && !onPodium(seasonRow('2010', 'summer'))
            && ys.filter(y => Number(y) > 2010 && Number(y) < 2023).every(y => onPodium(seasonRow(y, 'summer'))),
    },
    {
        year: '2025',
        phrase: 'more than in any season between 2019 and 2024',
        check: () => years['2025'].losses > Math.max(...ys.filter(y => Number(y) >= 2019 && Number(y) <= 2024).map(y => years[y].losses)),
    },
    {
        year: '2026',
        phrase: 'the winter season is still to come',
        check: () => seasonRow('2026', 'winter') === undefined,
    },
];

test('the superlatives a story claims are still superlatives', () => {
    const broken = [];
    for (const { year, phrase, check } of CLAIMS) {
        if (!story(year).includes(phrase)) {
            broken.push(`${year}: the note no longer says "${phrase}" — update the claim table with it`);
            continue;
        }
        if (!check()) broken.push(`${year}: "${phrase}" is no longer true of the data`);
    }
    assert.deepEqual(broken, [], `season stories overstate the record:\n${broken.join('\n')}`);
});

test('the computed badges and the notes agree on the superlatives', () => {
    // The timeline shows a computed badge and the hand-written note side by
    // side. If they disagree about who holds a record, the reader sees it.
    assert.equal(years['2019'].matches, Math.max(...ys.map(y => years[y].matches)), 'Most matches');
    assert.equal(gd('2022'), Math.max(...ys.map(gd)), 'Best goal difference');
    const biggest = Math.max(...ys.map(y => years[y].roster_players));
    assert.ok(['2013', '2017'].includes(ys.find(y => years[y].roster_players === biggest)),
        'Largest roster');
    const intake = deltas.reduce((a, b) => (b.d > a.d ? b : a));
    assert.equal(intake.year, '2013', '+N players');
});
