// Key ↔ name. This is the page's decoder: names.json is the only thing that
// turns a site key back into a printable name, and this is the only module
// that reads it. Everything else works in keys and asks here at the two
// boundaries — when it has to print a name, and when a URL or a QR code hands
// it a name and needs a key.
//
// Why keys and not names: pelikone mints a new player id for every
// registration, so one person arrives under many ids and sometimes under two
// spellings. The build collapses that into one person and one site key
// (src/ultiorg/persons.py). A name cannot be the key of a fact table; it can
// only be the label on one.

import { DATA } from './state.js';

// Folded name form: lower case, single spaces, tokens sorted, so "Roni Hotari",
// "roni  hotari" and "Hotari Roni" all fold to "hotari roni". This is the page's
// forgiving lookup for a name typed into a URL or carried in a QR code — it does
// not decide identity. The build's canon() (src/ultiorg/persons.py) and the
// human-asserted merges in config/aliases.json do that.
export const canonicalKey = name =>
    name.split(/\s+/).filter(Boolean).map(p => p.toLowerCase()).sort().join(' ');

// Two names, not one function with an optional argument. `nameFor(key)` is what
// the page calls, and it is safe to hand to .map() — a second parameter here
// would be filled by the array index, which is a silent way to make every name
// fall back to its key. A caller holding its own data object (js/categories.js)
// says so explicitly with nameIn().
export function nameIn(names, key) {
    return (names && names[key]) || key;
}

export function nameFor(key) {
    return nameIn(DATA.names, key);
}

// Display helpers for the prose slots on the category slides: both take a site
// key and speak in names, so a caller never has to remember which of the two it
// is holding.
export function firstName(key) { return nameFor(key).split(' ')[0]; }
export function initials(key) {
    const name = nameFor(key);
    const parts = name.split(' ');
    return parts.length > 1 ? parts[0].charAt(0) + '. ' + parts.slice(1).join(' ') : name;
}


// Built lazily and rebuilt if the player count changes, because the router can
// be entered before the data has loaded (that is the "data did not load" path)
// and a name index frozen at that moment would resolve nothing, forever.
let index = null;
let indexSize = -1;

function buildIndex() {
    const map = new Map();
    for (const key of Object.keys(DATA.players || {})) {
        const display = nameFor(key);
        // Exact display name first: it is what the old links and QR codes carry.
        if (!map.has(display)) map.set(display, key);
        // Then the folded form, so "roni hotari" and "Hotari Roni" find him too.
        const canon = canonicalKey(display);
        if (!map.has(canon)) map.set(canon, key);
    }
    return map;
}

function getIndex() {
    const size = Object.keys(DATA.players || {}).length;
    if (index === null || size !== indexSize) {
        index = buildIndex();
        indexSize = size;
    }
    return index;
}

// A route param is a site key in every link this page writes. A param that is
// not a key is an old bookmark, a printed QR code, or a typed name: resolve it,
// and let the router canonicalise the address so the URL, the QR code and the
// back button all end up saying the same thing.
export function resolvePlayerKey(param) {
    if (!param) return null;
    if (DATA.players && param in DATA.players) return param;
    const map = getIndex();
    return map.get(param) || map.get(canonicalKey(param)) || null;
}
