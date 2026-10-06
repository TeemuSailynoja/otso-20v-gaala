// The player index and its search filter.

import { getEraInfo } from '../format.js';
import { DATA } from '../state.js';

// ==================== PLAYERS PAGE ====================
let allPlayers = [];


export function renderPlayers(filter = '') {
    const grid = document.getElementById('players-grid');
    const countEl = document.getElementById('player-count');
        
    allPlayers = Object.keys(DATA.players).sort((a, b) => {
        const aLast = a.split(' ').pop();
        const bLast = b.split(' ').pop();
        return aLast.localeCompare(bLast);
    });

    const filtered = filter
        ? allPlayers.filter(p => p.toLowerCase().includes(filter.toLowerCase()))
        : allPlayers;

    countEl.textContent = filtered.length;

    grid.innerHTML = filtered.map(name => {
        const p = DATA.players[name];
        const era = getEraInfo(p.first_year);
        const c = era.statColors;
        return `
                <div class="player-card" onclick="location.hash='#/player/${encodeURIComponent(name)}'" style="border-color: ${era.borderColor};">
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

