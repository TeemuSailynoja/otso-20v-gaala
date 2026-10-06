// Rivalries: who Otso has played most, and how those games went.

import { DATA } from '../state.js';

// ==================== FRENEMIES PAGE ====================
export function renderFrenemies() {
    const grid = document.getElementById('frenemies-grid');
    const frenemies = DATA.frenemies || [];
        
    grid.innerHTML = frenemies.map(f => {
        // Teams are ordered by how many games that player faced Otso in,
        // so the first is their primary team. Show at most 3, rest in tooltip.
        const shown = f.teams.slice(0, 3).join(' · ');
        const extra = f.teams.length > 3 ? ` +${f.teams.length - 3}` : '';
        return `
                <div class="frenemy-card">
                    <div class="frenemy-rank">#${f.rank}</div>
                    <div class="frenemy-name">${f.name}</div>
                    <div class="frenemy-team" title="${f.teams.join(', ')}">${shown}${extra}</div>
                    <div class="frenemy-stats">
                        <div><span>${f.games}</span>G</div>
                        <div><span>${f.wins}-${f.losses}</span></div>
                        <div><span>${f.total}</span>pts</div>
                        <div><span>${f.ppg}</span>PPG</div>
                    </div>
                </div>
            `;
    }).join('');
}

