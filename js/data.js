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

    // No name re-expansion here. site_data/ is keyed by person id, and the page
    // looks players up by id: js/people.js is the only thing that turns a key
    // back into a name, and the router resolves a name in the URL into a key.
    // The Phase 9 stopgap that rebuilt name-keyed maps here is gone — it kept
    // the page's lookups on a key that is not stable across seasons, which is
    // the thing the re-keying was for.
    return DATA;
}
