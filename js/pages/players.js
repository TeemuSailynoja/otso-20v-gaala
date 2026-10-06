// The player index and its search filter.
//
// allPlayers is a list of site keys. The card prints a name and links by key:
// the key is what the player route needs, and a name in the URL would be a
// second, weaker identity for the same person.

import { getEraInfo } from '../format.js';
import { nameFor } from '../people.js';
import { DATA } from '../state.js';

// ==================== PLAYERS PAGE ====================
let allPlayers = [];


export function renderPlayers(filter = '') {
    const grid = document.getElementById('players-grid');
    const countEl = document.getElementById('player-count');

    allPlayers = Object.keys(DATA.players).sort((a, b) => {
        const aLast = nameFor(a).split(' ').pop();
        const bLast = nameFor(b).split(' ').pop();
        return aLast.localeCompare(bLast);
    });

    // Search matches the name the reader sees, not the key behind it.
    const filtered = filter
        ? allPlayers.filter(k => nameFor(k).toLowerCase().includes(filter.toLowerCase()))
        : allPlayers;

    countEl.textContent = filtered.length;

    grid.innerHTML = filtered.map(key => {
        const p = DATA.players[key];
        const name = nameFor(key);
        const era = getEraInfo(p.first_year);
        const c = era.statColors;
        return `
                <div class="player-card" onclick="location.hash='#/player/${encodeURIComponent(key)}'" style="border-color: ${era.borderColor};">
                    <div class="player-card-name" style="color: ${c.total}">${name}</div>
                    <div class="player-card-stats">
                        <div><span style="color: ${c.games}">${p.games}</span> games</div>
                        <div><span style="color: ${c.total}">${p.total}</span> pts</div>
                        <div><span style="color: ${c.assists}">${p.first_year}–${p.last_year}</span></div>
                    </div>
                </div>
            `;
    }).join('');
}


document.getElementById('player-search').addEventListener('input', (e) => {
    renderPlayers(e.target.value);
});

