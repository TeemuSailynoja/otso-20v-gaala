// The page's loader, under node: fetch() reads the committed site_data/ files,
// so a test can ask the same questions the browser asks. Tests of a *rule*
// should not use this — they build a small made-up data object instead, which
// is the whole reason js/categories.js and js/badges.js take their data as a
// parameter. Use the real corpus only for the things that are only true of the
// real corpus (a name exists for every key, a season story names a real year).
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

export function stubFetch() {
    globalThis.fetch = async (url) => {
        const file = url.replace(/^site_data\//, 'site_data/').replace(/\?.*$/, '');
        try {
            const body = readFileSync(path.join(ROOT, file), 'utf8');
            return { ok: true, status: 200, json: async () => JSON.parse(body) };
        } catch (err) {
            return { ok: false, status: 404, json: async () => { throw new Error('nope'); } };
        }
    };
}

// A player row as build_site_data.py publishes it. Every field the category
// math reads is present and typed, so a test that forgets one fails loudly
// rather than comparing against undefined.
export function player(over = {}) {
    return {
        games: 0, goals: 0, assists: 0, total: 0, total_points: 0,
        defense_goals: 0, defense_assists: 0, defense_points: 0,
        offense_goals: 0, offense_assists: 0, offense_points: 0,
        summer_games: 0, summer_goals: 0, summer_assists: 0,
        winter_games: 0, winter_goals: 0, winter_assists: 0,
        teams: [], years: [], seasons: [], season_types: [],
        season_count: 0, year_count: 0, first_year: 2020, last_year: 2021,
        ...over,
    };
}

// The slide specs come back as one array; a test should say which slide it
// means by the name a reader sees, so renaming a slide breaks the test that
// belongs to it and nothing else.
export function slide(categories, name) {
    const found = categories.find(c => c.name === name);
    if (!found) throw new Error(`no slide named ${name}: have ${categories.map(c => c.name).join(', ')}`);
    return found;
}
