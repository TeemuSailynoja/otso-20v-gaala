// A replica of what the browser does, run under node: fetch() reads the files on
// disk, js/data.js does the rest. If the page would fail to load, this fails.
import { readFileSync } from 'node:fs';
import { loadSiteData } from './data.js';

globalThis.fetch = async (url) => {
    const path = url.replace(/^site_data\//, 'site_data/').replace(/\?.*$/, '');
    try {
        const body = readFileSync(path, 'utf8');
        return { ok: true, status: 200, json: async () => JSON.parse(body) };
    } catch (err) {
        return { ok: false, status: 404, json: async () => { throw new Error('nope'); } };
    }
};

const DATA = await loadSiteData();

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
console.log('years            :', count(DATA.years), 'years; roster_names present:',
    Object.values(DATA.yearsOtso).every(r => Array.isArray(r.roster_names)));
console.log('sample player    :', DATA.names['6890'], JSON.stringify(DATA.players['Roni Hotari']?.games));
console.log('sample rival     :', DATA.frenemies[0].name, DATA.frenemies[0].total);
console.log('sample received  :', JSON.stringify(Object.entries(DATA.passNetwork.received['Oskari Vuorio'] || {}).slice(0, 3)));
