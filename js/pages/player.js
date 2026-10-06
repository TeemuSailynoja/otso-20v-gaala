// One player: career, defense, the pass network, the teammates.

import { canonicalKey, getEraInfo, statBars } from '../format.js';
import { DATA } from '../state.js';

// ==================== PLAYER DETAIL ====================
export function renderPlayerDetail(name) {
    const p = DATA.players[name];
    if (!p) {
        document.getElementById('player-detail').innerHTML = '<p>Player not found.</p>';
        return;
    }

    const era = getEraInfo(p.first_year);
    const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2);
    const passReceived = DATA.passNetwork.received?.[name] || {};
    const passGiven = DATA.passNetwork.given?.[name] || {};
    const cooc = DATA.cooccurrence[name] || {};

    // Top 3 only — three bars make a claim ("these are the people"), ten is a dump.
    const topReceived = Object.entries(passReceived).sort((a, b) => b[1] - a[1]).slice(0, 3);
    // Top assists given to
    const topGiven = Object.entries(passGiven).sort((a, b) => b[1] - a[1]).slice(0, 3);
    // Top teammates
    const topTeammates = Object.entries(cooc).sort((a, b) => b[1] - a[1]).slice(0, 3);

    const c = era.statColors;
    const cc = era.chartColors;

    const detail = document.getElementById('player-detail');
    detail.style.background = era.bgGrad;
    detail.style.border = `1px solid ${era.borderColor}`;
    detail.style.borderRadius = '16px';
    detail.style.padding = '2rem';
    detail.innerHTML = `
            <div class="player-header" style="border-color: ${era.borderColor}; background: var(--card);">
                <div class="player-avatar" style="background: ${era.avatarGrad};">${initials}</div>
                <div class="player-info">
                    <h2>${name}</h2>
                    <div class="player-meta">
                        <span>${p.first_year}–${p.last_year} · ${p.year_count} years</span>
                        <span>${p.season_count} seasons</span>
                        ${p.teams.length > 0 ? `<span>${p.teams.join(', ')}</span>` : ''}
                    </div>
                </div>
            </div>

            <div class="player-big-stats">
                <div class="player-big-stat">
                    <div class="value" style="color: ${c.games}">${p.games}</div>
                    <div class="label">Games</div>
                </div>
                <div class="player-big-stat">
                    <div class="value" style="color: ${c.goals}">${p.goals}</div>
                    <div class="label">Goals</div>
                </div>
                <div class="player-big-stat">
                    <div class="value" style="color: ${c.assists}">${p.assists}</div>
                    <div class="label">Assists</div>
                </div>
                <div class="player-big-stat">
                    <div class="value" style="color: ${c.total}">${p.total}</div>
                    <div class="label">Total</div>
                </div>
                <div class="player-big-stat">
                    <div class="value" style="color: ${c.ppg}">${p.games > 0 ? (p.total / p.games).toFixed(2) : '—'}</div>
                    <div class="label">Pts/Game</div>
                </div>
            </div>

            ${(topReceived.length > 0 || topGiven.length > 0) ? `
            <div class="charts-row" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                ${topReceived.length > 0 ? `
                <div class="chart-card">
                    <h3>Assists Received From</h3>
                    ${statBars(topReceived, cc.received, cc.receivedBorder)}
                </div>
                ` : ''}
                ${topGiven.length > 0 ? `
                <div class="chart-card">
                    <h3>Assists Given To</h3>
                    ${statBars(topGiven, cc.given, cc.givenBorder)}
                </div>
                ` : ''}
            </div>
            ` : ''}

            ${topTeammates.length > 0 ? `
            <div class="chart-card">
                <h3>Most Frequent Teammates</h3>
                ${statBars(topTeammates, cc.teammates, cc.teammatesBorder)}
            </div>
            ` : ''}
        `;
}


document.getElementById('player-back').addEventListener('click', () => {
    location.hash = '#/players';
});


let _playerByCanon = null;

export function playerByCanon() {
    if (!_playerByCanon) {
        _playerByCanon = {};
        for (const name in DATA.players) _playerByCanon[canonicalKey(name)] = name;
    }
    return _playerByCanon;
}

