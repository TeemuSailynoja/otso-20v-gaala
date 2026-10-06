// Entry point: load the data, wire the pages, start the router.
// 
// A module script is deferred, so this runs after the document is parsed — the
// same moment the inline script used to run at the end of <body>.

import { showQrBadge, showQrOverlay } from './qr.js';
import { navigate } from './router.js';
import { loadData } from './state.js';
import { initParticles } from './timeline/cloud.js';

async function init() {
    try {
        await loadData();
    } catch (err) {
        // A contract failure is shown, not swallowed. A blank grid tells the
        // reader nothing and tells us nothing; this names the file and the
        // field.
        showDataError(err);
        return;
    }
    initParticles();
    navigate();
    if (new URLSearchParams(location.search).has('qr')) {
        // `?qr` = corner code on the hero, `?qr=full` = the takeover version.
        (new URLSearchParams(location.search).get('qr') === 'full' ? showQrOverlay : showQrBadge)();
    }
}


function showDataError(err) {
    console.error(err);
    const banner = document.createElement('div');
    banner.className = 'data-error';
    banner.setAttribute('role', 'alert');
    const title = document.createElement('strong');
    title.textContent = 'The data did not load';
    const detail = document.createElement('p');
    detail.textContent = String((err && err.message) || err);
    banner.append(title, detail);
    document.body.prepend(banner);
}


init();
