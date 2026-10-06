// Loads site_data/ for the page — through the contract, not by guessing.
//
// The manifest says what exists and which version it is; the schema says what
// each file looks like. So the fetch list comes from the build instead of being
// duplicated here, the cache-busting query string comes from the manifest
// instead of a hash stamped into the HTML, and a file whose shape moved fails
// with a message naming the field instead of rendering an empty grid.

import { validate, ContractError } from './contract.js';

const SITE = 'site_data/';

// The files this page needs, by name. The manifest must publish every one; a
// name missing from the manifest is an error, not an undefined that shows up
// three functions later.
const NEEDED = [
    'players.json', 'pass_network.json', 'cooccurrence.json', 'summary.json',
    'frenemies.json', 'trophies.json', 'names.json',
    'years_otso.json', 'years_otso_summer.json', 'years_otso_winter.json',
];

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
    return response.json();
}

export async function loadManifest() {
    // Never cached: the manifest is what makes the versioned fetches correct.
    // A cached manifest would put the previous version back in the query string
    // and serve the previous data forever.
    return fetchJson(`${SITE}manifest.json`, { cache: 'no-store' });
}

export async function loadSiteData() {
    const manifest = await loadManifest();
    if (!manifest || typeof manifest.version !== 'string') {
        throw new Error('manifest.json has no version');
    }
    const bust = `v=${encodeURIComponent(manifest.version)}`;
    const published = new Set((manifest.files || []).map(f => f.name));
    const missing = NEEDED.filter(name => !published.has(name));
    if (missing.length) {
        throw new Error(`manifest.json does not publish: ${missing.join(', ')}`);
    }

    const schema = await fetchJson(`${SITE}schema.json?${bust}`);
    const shapes = (schema && schema.files) || {};
    const loaded = await Promise.all(NEEDED.map(name => fetchJson(`${SITE}${name}?${bust}`)));

    for (let i = 0; i < NEEDED.length; i++) {
        const name = NEEDED[i];
        const spec = shapes[name];
        // A published file with no declared shape is a build bug, and an
        // unvalidated file is exactly the blank grid this exists to prevent.
        if (!spec) throw new Error(`${name}: no shape declared in schema.json`);
        const problems = validate(loaded[i], spec);
        if (problems.length) throw new ContractError(name, problems);
    }

    const byName = Object.fromEntries(NEEDED.map((name, i) => [name, loaded[i]]));
    const DATA = {
        players: byName['players.json'],
        passNetwork: byName['pass_network.json'],
        cooccurrence: byName['cooccurrence.json'],
        summary: byName['summary.json'],
        frenemies: byName['frenemies.json'],
        trophies: byName['trophies.json'],
        names: byName['names.json'],
        yearsOtso: byName['years_otso.json'],
        yearsOtsoSummer: byName['years_otso_summer.json'],
        yearsOtsoWinter: byName['years_otso_winter.json'],
    };
    DATA.years = DATA.yearsOtso; // Default to Otso full year

    // TEMPORARY (Phase 9): site_data is keyed by player id, because a name is
    // not a stable key — pelikone mints a new id per registration, and one
    // person can be spelled two ways. names.json maps every key back to a
    // printable name. The page still looks players up by display name, so the
    // id-keyed maps are re-expanded here and nothing else changes. Phase 11
    // moves the lookups to ids and deletes this block.
    const names = DATA.names;
    const named = (key) => names[key] || key;
    const renameOuter = (map) => Object.fromEntries(
        Object.entries(map).map(([k, v]) => [named(k), v]));
    const renameBoth = (map) => Object.fromEntries(
        Object.entries(map).map(([k, v]) => [named(k), renameOuter(v)]));
    DATA.players = renameOuter(DATA.players);
    DATA.passNetwork = {
        received: renameBoth(DATA.passNetwork.received),
        given: renameBoth(DATA.passNetwork.given),
    };
    DATA.cooccurrence = renameBoth(DATA.cooccurrence);
    // Same stopgap: the year rosters are id lists; the page wants names.
    for (const years of [DATA.yearsOtso, DATA.yearsOtsoSummer, DATA.yearsOtsoWinter]) {
        for (const row of Object.values(years)) {
            if (row.roster) row.roster_names = row.roster.map(named);
        }
    }

    return DATA;
}
