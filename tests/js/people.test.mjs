// The page's decoder: key → name, and name → key.
//
// The name→key direction is what keeps old QR codes and bookmarks working after
// the whole site was re-keyed to player ids, so it is tested against the real
// corpus: the forms a printed QR code and a typed URL actually arrive in.
import test from 'node:test';
import assert from 'node:assert/strict';

import { canonicalKey, nameIn, nameFor, firstName, initials, resolvePlayerKey } from '../../js/people.js';
import { stubFetch } from './helpers.mjs';
import { DATA, loadData } from '../../js/state.js';

test('canonicalKey folds case, spacing and token order — and treats a non-breaking space as a space', () => {
    // Roster cells in pelikone carry U+00A0 between names; a decoder that split
    // on ' ' alone would miss them.
    assert.equal(canonicalKey('Roni Hotari'), 'hotari roni');
    assert.equal(canonicalKey('roni   HOTARI'), 'hotari roni');
    assert.equal(canonicalKey('Hotari Roni'), 'hotari roni');
    assert.equal(canonicalKey('Roni\u00A0Hotari'), 'hotari roni', 'U+00A0 between the names');
    assert.equal(canonicalKey('  Roni Hotari  '), 'hotari roni');
});

test('canonicalKey does not fold accents: it is a lookup, not an identity rule', () => {
    // Identity is the build's job — canon() in the ultiorg package (names.py) plus the
    // human-asserted merges in config/aliases.json. The page only forgives
    // typing, so "Ojanperä" and "Ojanpera" stay two different strings.
    assert.equal(canonicalKey('Ari Ojanperä'), 'ari ojanperä');
    assert.notEqual(canonicalKey('Ari Ojanperä'), canonicalKey('Ari Ojanpera'));
});

test('nameIn prints the name, and falls back to the key rather than to nothing', () => {
    assert.equal(nameIn({ 7: 'Iso T' }, '7'), 'Iso T');
    assert.equal(nameIn({}, '7'), '7', 'an unnameable key must still print something');
    assert.equal(nameIn(undefined, '7'), '7');
});

stubFetch();
await loadData();

test('every player the page can reach has a name — no key leaks into the prose', () => {
    const unnameable = Object.keys(DATA.players).filter(k => !DATA.names[k]);
    assert.deepEqual(unnameable, [], `${unnameable.length} keys would print as their own id`);
});

test('a name from an old link or QR code resolves to the site key', () => {
    const key = '6890';
    const display = DATA.names[key];
    assert.equal(display, 'Roni Hotari');
    assert.equal(resolvePlayerKey(display), key, 'the exact form the old URLs carry');
    assert.equal(resolvePlayerKey(canonicalKey(display)), key, 'the folded form');
    assert.equal(resolvePlayerKey('Hotari Roni'), key, 'reversed tokens, as pelikone writes roster cells');
    assert.equal(resolvePlayerKey('Roni\u00A0Hotari'), key, 'a non-breaking space, as pelikone writes them');
});

test('a key passes straight through, and an unknown name resolves to nothing', () => {
    assert.equal(resolvePlayerKey('6890'), '6890');
    assert.equal(resolvePlayerKey('NoSuch Person'), null);
    assert.equal(resolvePlayerKey(''), null);
    assert.equal(resolvePlayerKey(null), null);
});

test('the decoder resolves every player in the table, by both of its forms', () => {
    const broken = [];
    for (const key of Object.keys(DATA.players)) {
        const display = DATA.names[key];
        if (resolvePlayerKey(display) !== key) broken.push(`${key} via "${display}" → ${resolvePlayerKey(display)}`);
        if (resolvePlayerKey(canonicalKey(display)) !== key) broken.push(`${key} via folded "${canonicalKey(display)}"`);
    }
    assert.deepEqual(broken, [], `${broken.length} players could not be reached by name: ${broken.slice(0, 5).join(', ')}`);
});

test('firstName and initials take a key and speak a name', () => {
    assert.equal(firstName('6890'), 'Roni');
    assert.equal(initials('6890'), 'R. Hotari');
    // A one-word name has nothing to abbreviate, and must not become ". X".
    assert.equal(initials('solo'), 'solo');
});

test('initials abbreviates the given name and keeps the whole surname', () => {
    // Three-word surnames are real here ("Jim Mc Keen"), and the compact slot
    // must not drop a middle word of the family name.
    const key = Object.keys(DATA.names).find(k => DATA.names[k].split(' ').length === 3);
    assert.ok(key, 'the corpus is expected to contain a three-word name');
    const parts = DATA.names[key].split(' ');
    assert.equal(initials(key), `${parts[0].charAt(0)}. ${parts.slice(1).join(' ')}`);
    assert.equal(firstName(key), parts[0]);
});
