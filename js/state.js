// The page's data, and the one place it is loaded.
// 
// DATA is a live binding: every module that imports it sees the object the
// loader returned, which is what the inline script got for free from shared
// function scope. The default shape stays here so a renderer that runs before
// the fetch still finds the keys it indexes.


// ==================== DATA ====================
export let DATA = {
    players: {}, passNetwork: {}, cooccurrence: {}, summary: {}, frenemies: [],
    years: {}, yearsOtso: {}, yearsOtsoSummer: {}, yearsOtsoWinter: {},
};


// The data contract lives in site_data/: manifest.json says what was
// published and at which version, schema.json says what each file looks
// like. js/data.js fetches through both and validates what it gets, so a
// shape change fails with a message naming the field instead of rendering an
// empty grid. Nothing stamps a version into this file any more.
export async function loadData() {
    const { loadSiteData } = await import('./data.js');
    DATA = await loadSiteData();
}

