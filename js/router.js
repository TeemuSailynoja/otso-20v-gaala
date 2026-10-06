// Hash routing: which page is active, and what gets rendered for it.

import { renderFrenemies } from './pages/frenemies.js';
import { renderHome } from './pages/home.js';
import { renderPlayerDetail } from './pages/player.js';
import { renderPlayers } from './pages/players.js';
import { renderTimeline } from './timeline.js';
import { hudCloud } from './timeline/cloud.js';
import { resetHudYear } from './timeline/hud.js';

// ==================== ROUTING ====================
export function navigate() {
    const hash = location.hash || '#/';
    const parts = hash.split('/');
    const page = parts[1] || 'home';

    // Hide all pages
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));

    // Snap is timeline-only: leave it off the other pages.
    document.documentElement.classList.toggle('snap-timeline', page === 'timeline');
    if (page !== 'timeline' && hudCloud) hudCloud.pause();

    // Update nav
    document.querySelectorAll('.nav-links a').forEach(a => {
        a.classList.toggle('active', a.dataset.page === page);
    });

    if (page === 'home') {
        document.getElementById('page-home').classList.add('active');
        renderHome();
    } else if (page === 'players') {
        document.getElementById('page-players').classList.add('active');
        renderPlayers();
    } else if (page === 'player') {
        const playerName = decodeURIComponent(parts.slice(2).join('/'));
        document.getElementById('page-player').classList.add('active');
        renderPlayerDetail(playerName);
    } else if (page === 'frenemies') {
        document.getElementById('page-frenemies').classList.add('active');
        renderFrenemies();
    } else if (page === 'timeline') {
        document.getElementById('page-timeline').classList.add('active');
        resetHudYear(); // re-entry starts at the top of the stream
        renderTimeline();
        if (hudCloud) hudCloud.resume();
    }
}


window.addEventListener('hashchange', navigate);

