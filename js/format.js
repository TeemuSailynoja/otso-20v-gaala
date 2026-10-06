// Formatting with no DOM and no data: era colours, stat bars, medals,
// season words, the canonical name key, the seeded RNG.

import { DATA } from './state.js';

// ==================== ERA THEMING ====================
// Player pages styled by the era they started in
export function getEraInfo(firstYear) {
    const fy = parseInt(firstYear);
    if (fy <= 2009) return {
        name: 'Founders',
        range: '2006–2009',
        avatarGrad: 'linear-gradient(135deg, #8b3a4a, #1a237e)',
        bgGrad: 'linear-gradient(135deg, rgba(139,58,74,0.08) 0%, rgba(26,35,126,0.06) 100%)',
        borderColor: 'rgba(139, 58, 74, 0.4)',
        statColors: {
            games: '#8b3a4a',
            goals: '#a04a5a',
            assists: '#3949ab',
            total: '#c0c0c0',
            ppg: '#d4a574'
        },
        chartColors: {
            received: 'rgba(139, 58, 74, 0.6)',
            receivedBorder: 'rgba(139, 58, 74, 1)',
            given: 'rgba(26, 35, 126, 0.6)',
            givenBorder: 'rgba(26, 35, 126, 1)',
            teammates: 'rgba(160, 74, 90, 0.6)',
            teammatesBorder: 'rgba(160, 74, 90, 1)'
        }
    };
    if (fy <= 2014) return {
        name: 'Red Era',
        range: '2010–2014',
        avatarGrad: 'linear-gradient(135deg, #d32f2f, #ff9800)',
        bgGrad: 'linear-gradient(135deg, rgba(211,47,47,0.08) 0%, rgba(255,152,0,0.06) 100%)',
        borderColor: 'rgba(211, 47, 47, 0.4)',
        statColors: {
            games: '#d32f2f',
            goals: '#ff5722',
            assists: '#ff9800',
            total: '#cddc39',
            ppg: '#ffb74d'
        },
        chartColors: {
            received: 'rgba(211, 47, 47, 0.6)',
            receivedBorder: 'rgba(211, 47, 47, 1)',
            given: 'rgba(255, 152, 0, 0.6)',
            givenBorder: 'rgba(255, 152, 0, 1)',
            teammates: 'rgba(205, 220, 57, 0.6)',
            teammatesBorder: 'rgba(205, 220, 57, 1)'
        }
    };
    if (fy <= 2018) return {
        name: 'Classic',
        range: '2015–2018',
        avatarGrad: 'linear-gradient(135deg, #212121, #f5f5f5)',
        bgGrad: 'linear-gradient(135deg, rgba(33,33,33,0.12) 0%, rgba(245,245,245,0.04) 100%)',
        borderColor: 'rgba(245, 245, 245, 0.3)',
        statColors: {
            games: '#f5f5f5',
            goals: '#e0e0e0',
            assists: '#212121',
            total: '#9e9e9e',
            ppg: '#bdbdbd'
        },
        chartColors: {
            received: 'rgba(245, 245, 245, 0.5)',
            receivedBorder: 'rgba(245, 245, 245, 0.8)',
            given: 'rgba(33, 33, 33, 0.6)',
            givenBorder: 'rgba(33, 33, 33, 1)',
            teammates: 'rgba(158, 158, 158, 0.6)',
            teammatesBorder: 'rgba(158, 158, 158, 1)'
        }
    };
    if (fy <= 2022) return {
        name: 'Blue Era',
        range: '2019–2022',
        avatarGrad: 'linear-gradient(135deg, #7ba7cc, #ff8c00)',
        bgGrad: 'linear-gradient(135deg, rgba(123,167,204,0.10) 0%, rgba(255,140,0,0.06) 100%)',
        borderColor: 'rgba(123, 167, 204, 0.4)',
        statColors: {
            games: '#7ba7cc',
            goals: '#5a8ab5',
            assists: '#ff8c00',
            total: '#b0c4de',
            ppg: '#dda857'
        },
        chartColors: {
            received: 'rgba(123, 167, 204, 0.6)',
            receivedBorder: 'rgba(123, 167, 204, 1)',
            given: 'rgba(255, 140, 0, 0.6)',
            givenBorder: 'rgba(255, 140, 0, 1)',
            teammates: 'rgba(176, 196, 222, 0.6)',
            teammatesBorder: 'rgba(176, 196, 222, 1)'
        }
    };
    // 2023+
    return {
        name: 'Modern',
        range: '2023+',
        avatarGrad: 'linear-gradient(135deg, #e5b037, #6a1e32)',
        bgGrad: 'linear-gradient(135deg, rgba(229,176,55,0.08) 0%, rgba(106,30,50,0.06) 100%)',
        borderColor: 'rgba(229, 176, 55, 0.3)',
        statColors: {
            games: '#e5b037',
            goals: '#6a1e32',
            assists: '#085c95',
            total: '#d0d0d0',
            ppg: '#e5b037'
        },
        chartColors: {
            received: 'rgba(106, 30, 50, 0.6)',
            receivedBorder: 'rgba(106, 30, 50, 1)',
            given: 'rgba(8, 92, 149, 0.6)',
            givenBorder: 'rgba(8, 92, 149, 1)',
            teammates: 'rgba(229, 176, 55, 0.6)',
            teammatesBorder: 'rgba(229, 176, 55, 1)'
        }
    };
}


// Bars are plain DOM: the full name sits under its own bar, which an axis
// label can never promise. Width is relative to the leader of the set.
export function statBars(rows, fill, border) {
    const max = rows.length ? rows[0][1] : 0;
    return `<div class="stat-bars">${rows.map(([who, count]) => {
            const pct = max > 0 ? Math.max(6, Math.round(count / max * 100)) : 0;
            const name = DATA.players[who]
                ? `<a class="stat-bar-name" href="#/player/${encodeURIComponent(who)}">${who}</a>`
                : `<span class="stat-bar-name">${who}</span>`;
            return `<div class="stat-bar-row">
                    <div class="stat-bar-track">
                        <div class="stat-bar-fill" style="width: ${pct}%; background: ${fill}; border-color: ${border};"></div>
                        <div class="stat-bar-val">${count}</div>
                    </div>
                    <div class="stat-bar-label">${name}</div>
                </div>`;
        }).join('')}</div>`;
}


export const MEDAL_EMOJI = { gold: '🥇', silver: '🥈', bronze: '🥉' };

export const SEASON_LABEL = { summer: 'Kesä', winter: 'Talvi' };


// ==================== HUD TEAM CLOUD ====================
// The roster dots over the HUD chart *are* the players of the year being read.
// Deterministic on purpose: the same year always animates the same way, so the
// transition is a legible reshaping rather than a fresh dice roll each visit.
export function mulberry32(seed) {
    let s = seed >>> 0;
    return function () {
        s = (s + 0x6D2B79F5) >>> 0;
        let t = Math.imul(s ^ (s >>> 15), 1 | s);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}


// roster_names are canonicalized in the build (sorted lowercase parts, e.g.
// "hotari roni"), so resolve them back to the display keys of players.json.
export const canonicalKey = name =>
    name.split(/\s+/).filter(Boolean).map(p => p.toLowerCase()).sort().join(' ');

