// Formatting helpers: era bands, bar charts, and the seeded layout RNG.
import test from 'node:test';
import assert from 'node:assert/strict';

import { getEraInfo, statBars, mulberry32, MEDAL_EMOJI, SEASON_LABEL } from '../../js/format.js';
import { stubFetch } from './helpers.mjs';
import { DATA, loadData } from '../../js/state.js';

test('the era bands are decided by the year a career started, at the boundaries', () => {
    const band = (y) => [getEraInfo(y).name, getEraInfo(y).range];
    assert.deepEqual(band(2006), ['Founders', '2006–2009']);
    assert.deepEqual(band(2009), ['Founders', '2006–2009']);
    assert.deepEqual(band(2010), ['Red Era', '2010–2014'], 'the band changes at 2010, not 2009');
    assert.deepEqual(band(2014), ['Red Era', '2010–2014']);
    assert.deepEqual(band(2015), ['Classic', '2015–2018']);
    assert.deepEqual(band(2018), ['Classic', '2015–2018']);
    assert.deepEqual(band(2019), ['Blue Era', '2019–2022']);
    assert.deepEqual(band(2022), ['Blue Era', '2019–2022']);
    assert.deepEqual(band(2023), ['Modern', '2023+']);
    assert.deepEqual(band(2026), ['Modern', '2023+']);
});

test('every era supplies the colours the player page reads', () => {
    // A missing entry here does not throw: it paints `undefined` into a style
    // attribute, which is the kind of bug a screenshot catches and a diff does not.
    const stats = ['games', 'goals', 'assists', 'total', 'ppg'];
    const charts = ['received', 'receivedBorder', 'given', 'givenBorder', 'teammates', 'teammatesBorder'];
    const wrong = [];
    for (const y of [2006, 2010, 2015, 2019, 2023]) {
        const e = getEraInfo(y);
        for (const k of ['name', 'range', 'avatarGrad', 'bgGrad', 'borderColor']) {
            if (!e[k]) wrong.push(`${e.name || y}: no ${k}`);
        }
        for (const k of stats) if (!e.statColors[k]) wrong.push(`${e.name}: statColors.${k}`);
        for (const k of charts) if (!e.chartColors[k]) wrong.push(`${e.name}: chartColors.${k}`);
    }
    assert.deepEqual(wrong, [], wrong.join('\n'));
});

test('a year that arrives as a string still gets a band', () => {
    // The player table reads first_year out of JSON, where it is a number; the
    // timeline hands over a key, which is a string. Both must work.
    assert.equal(getEraInfo('2010').name, 'Red Era');
    assert.equal(getEraInfo('2010').range, '2010–2014');
});

test('the medal and season-type labels are the page vocabulary', () => {
    assert.deepEqual(MEDAL_EMOJI, { gold: '🥇', silver: '🥈', bronze: '🥉' });
    assert.deepEqual(SEASON_LABEL, { summer: 'Kesä', winter: 'Talvi' });
});

test('mulberry32 is deterministic, so the same year always animates the same way', () => {
    const draw = (seed) => { const r = mulberry32(seed); return [r(), r(), r()]; };
    assert.deepEqual(draw(2019), draw(2019));
    assert.notDeepEqual(draw(2019), draw(2020));
    for (const v of draw(7)) {
        assert.ok(v >= 0 && v < 1, `a layout coordinate must stay inside the canvas: ${v}`);
    }
});

stubFetch();
await loadData();

test('statBars takes keys, and links the ones that are players', () => {
    const key = '6890';
    const other = Object.keys(DATA.players).find(k => k !== key);
    const html = statBars([[key, 60], [other, 30]], '#f00', '#900');
    assert.ok(html.includes(`href="#/player/${encodeURIComponent(key)}"`),
        'the link needs the key, so a caller that pre-named its rows would lose it');
    assert.ok(html.includes(`>${DATA.names[key]}</a>`), 'the label needs the name');
    assert.ok(html.includes('<div class="stat-bar-val">60</div>'));
});

test('statBars prints a name for a key it does not know, without inventing a link', () => {
    const html = statBars([['not-a-player', 5]], '#f00', '#900');
    assert.ok(!html.includes('<a '), 'an unknown key is not a player page');
    assert.ok(html.includes('<span class="stat-bar-name">not-a-player</span>'),
        'and it still prints something');
});

test('bar width is relative to the first row, and never smaller than 6%', () => {
    const widths = (rows) => [...statBars(rows, '#f00', '#900').matchAll(/width: (\d+)%/g)].map(m => Number(m[1]));
    assert.deepEqual(widths([['a', 100], ['b', 50], ['c', 1]]), [100, 50, 6],
        'the leader is full width; a 1% sliver is still visible');
    assert.deepEqual(widths([]), [], 'an empty set draws no bars');
    assert.deepEqual(widths([['a', 0]]), [0], 'a set whose leader is zero draws no fill');
});
