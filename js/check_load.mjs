// A replica of what the browser does, run under node: fetch() reads the files on
// disk, js/data.js and js/state.js do the rest. If the page would fail to load,
// this fails. It also exercises js/people.js, the decoder, because a key that
// names.json cannot name is a blank cell somewhere in the page and should fail
// here rather than in the browser.
import { readFileSync } from 'node:fs';

globalThis.fetch = async (url) => {
    const path = url.replace(/^site_data\//, 'site_data/').replace(/\?.*$/, '');
    try {
        const body = readFileSync(path, 'utf8');
        return { ok: true, status: 200, json: async () => JSON.parse(body) };
    } catch (err) {
        return { ok: false, status: 404, json: async () => { throw new Error('nope'); } };
    }
};

// DATA is a live binding: importing it before loadData() and reading it after
// gives the loaded object, which is exactly what the page's modules see.
import { DATA, loadData } from './state.js';
import { nameFor, resolvePlayerKey } from './people.js';

await loadData();

const count = (o) => Object.keys(o).length;
console.log('DATA keys        :', Object.keys(DATA).join(', '));
console.log('players          :', count(DATA.players));
console.log('names            :', count(DATA.names));
console.log('passNetwork      :', count(DATA.passNetwork.received), 'received,',
    count(DATA.passNetwork.given), 'given');
console.log('cooccurrence     :', count(DATA.cooccurrence));
console.log('frenemies        :', DATA.frenemies.length);
console.log('trophies         :', DATA.trophies.seasons.length, 'seasons,',
    JSON.stringify(DATA.trophies.totals.all));
console.log('summary          :', DATA.summary.total_matches, 'matches,',
    DATA.summary.total_players, 'players');
console.log('years            :', count(DATA.years), 'years; rosters are key lists:',
    Object.values(DATA.yearsOtso).every(r => Array.isArray(r.roster)));

// Every key the page can reach must be nameable. The build refuses to publish an
// unnamed key; this checks the page's side of the same promise, including the
// inner keys of the pass and co-occurrence maps, which the page prints as names.
const unnamed = [];
for (const key of Object.keys(DATA.players)) if (!DATA.names[key]) unnamed.push(key);
for (const map of [DATA.passNetwork.received, DATA.passNetwork.given, DATA.cooccurrence]) {
    for (const [outer, inner] of Object.entries(map)) {
        if (!DATA.names[outer]) unnamed.push(outer);
        for (const inner2 of Object.keys(inner)) if (!DATA.names[inner2]) unnamed.push(inner2);
    }
}
if (unnamed.length) {
    console.error(`FAIL: names.json cannot name ${unnamed.length} keys, e.g. ${unnamed.slice(0, 5).join(', ')}`);
    process.exitCode = 1;
}

// The decoder: a route param is a key, and an old link carries a name.
const hotari = resolvePlayerKey('Roni Hotari');
const folded = resolvePlayerKey('hotari roni');
if (!hotari || !folded || folded !== hotari || resolvePlayerKey(hotari) !== hotari) {
    console.error('FAIL: the decoder could not resolve "Roni Hotari" / "hotari roni" '
        + 'to one key, or a key did not pass through unchanged');
    process.exitCode = 1;
}
console.log('decoder          :', JSON.stringify(hotari), '->', nameFor(hotari),
    '| folded:', JSON.stringify(folded),
    '| key passes through:', JSON.stringify(resolvePlayerKey(hotari)));
console.log('sample player    :', nameFor(hotari), JSON.stringify(DATA.players[hotari]?.games));
console.log('sample rival     :', DATA.frenemies[0].name, DATA.frenemies[0].total);
console.log('sample received  :', JSON.stringify(Object.entries(DATA.passNetwork.received[hotari] || {}).slice(0, 3)));
