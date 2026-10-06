// The sticky year HUD: the chart, the year list, and the scroll chrome
// that keeps the right year marked.

import { MEDAL_EMOJI, SEASON_LABEL } from '../format.js';
import { DATA } from '../state.js';
import { ensureHudCloud, hudCloud } from './cloud.js';
import { otsoTeamLabel, seasonSplitLine } from './stream.js';

// ==================== TIMELINE PAGE ====================
// ==================== TIMELINE HUD ====================
export let hudChart = null;

export let hudActiveYear = null;


// The nav height is not a constant: it depends on the viewport and on the
// brand wrapping on narrow screens. Sticky offsets and snap margins must be
// measured, not guessed.
function measureTimelineChrome() {
    const root = document.documentElement;
    const nav = document.querySelector('nav');
    const hud = document.getElementById('timeline-hud');
    if (nav) root.style.setProperty('--nav-h', nav.offsetHeight + 'px');
    if (hud) root.style.setProperty('--hud-h', hud.offsetHeight + 'px');
    if (hudCloud) hudCloud.resize();
}


window.addEventListener('resize', () => {
    if (document.getElementById('page-timeline')?.classList.contains('active')) {
        measureTimelineChrome();
    }
});


// Vertical dashed line on the year the reader is currently standing on.
const hudYearMarkerPlugin = {
    id: 'hudYearMarker',
    afterDatasetsDraw(chart) {
        const idx = chart.$activeIndex;
        if (idx === null || idx === undefined || idx < 0) return;
        const x = chart.scales.x.getPixelForValue(idx);
        const area = chart.chartArea;
        const ctx = chart.ctx;
        ctx.save();
        ctx.strokeStyle = 'rgba(229, 176, 55, 0.5)';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(x, area.top);
        ctx.lineTo(x, area.bottom);
        ctx.stroke();
        ctx.restore();
    }
};


export function hudYearList() {
    return Object.keys(DATA.years).sort((a, b) => a - b);
}


export function renderTimelineHud() {
    const years = hudYearList();
    const rows = years.map(y => ({ year: y, ...DATA.years[y] }));
    const canvas = document.getElementById('hud-roster-chart');
    if (!canvas || years.length === 0) return;

    // offsetHeight is 0 while the page is hidden, so measure only once it is active
    measureTimelineChrome();

    if (hudChart) { hudChart.destroy(); hudChart = null; }
    ensureHudCloud();
    if (hudCloud) hudCloud.resize();
    hudChart = new Chart(canvas, {
        type: 'line',
        data: {
            labels: years,
            datasets: [{
                label: 'Roster',
                data: rows.map(r => r.roster_players),
                borderColor: 'rgba(8, 92, 149, 1)',
                backgroundColor: 'rgba(8, 92, 149, 0.12)',
                fill: true,
                tension: 0.3,
                borderWidth: 2,
                pointRadius: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            layout: { padding: { top: 8 } },
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: {
                x: {
                    ticks: { color: '#8a9bae', maxRotation: 0, autoSkip: true, maxTicksLimit: 7, font: { size: 10 } },
                    grid: { color: 'rgba(255,255,255,0.04)' }
                },
                y: {
                    ticks: { color: '#8a9bae', maxTicksLimit: 4, font: { size: 10 } },
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    beginAtZero: true
                }
            }
        },
        plugins: [hudYearMarkerPlugin]
    });

    setHudYear(years.includes(hudActiveYear) ? hudActiveYear : years[0]);
}


export function setHudYear(year) {
    const y = String(year);
    const d = DATA.years[y];
    if (!d) return;
    hudActiveYear = y;

    const years = hudYearList();
    if (hudChart) {
        const idx = years.indexOf(y);
        hudChart.$activeIndex = idx;
        hudChart.data.datasets[0].pointRadius = years.map((_, i) => (i === idx ? 5 : 0));
        hudChart.data.datasets[0].pointBackgroundColor = years.map((_, i) => (i === idx ? '#e5b037' : 'rgba(0,0,0,0)'));
        hudChart.update('none');
    }

    document.getElementById('hud-matches').textContent = d.matches;
    const played = d.wins + d.losses;
    document.getElementById('hud-winrate').textContent =
        played > 0 ? Math.round(d.wins / played * 100) + '%' : '—';
    document.getElementById('hud-roster').textContent = d.roster_players;

    // Aggregate only — the birthdays themselves stay in a gitignored file.
    const ageEl = document.getElementById('hud-age');
    const ageMetric = document.getElementById('hud-age-metric');
    if (d.avg_age != null) {
        ageEl.textContent = d.avg_age.toFixed(1);
        ageMetric.title = d.avg_age_known === d.roster_players
            ? `Mean age of all ${d.roster_players} players`
            : `Mean age of the ${d.avg_age_known} players with a recorded birthday, of ${d.roster_players}`;
    } else {
        ageEl.textContent = '—';
        ageMetric.title = '';
    }

    const seasons = ((DATA.trophies && DATA.trophies.seasons) || []).filter(s => String(s.year) === y);
    document.getElementById('hud-chips').innerHTML = seasons.map(s => {
        if (!s.played) return '';
        const label = SEASON_LABEL[s.season] || s.season;
        const team = otsoTeamLabel(s.team);
        const who = team && team !== 'Otso' ? ` · ${team}` : '';
        if (s.medal) return `<span class="hud-chip ${s.medal}">${MEDAL_EMOJI[s.medal]} ${label}${who}</span>`;
        return `<span class="hud-chip">${label} ${s.placement || '—'}${who}</span>`;
    }).join('');
    document.getElementById('hud-split').textContent = seasonSplitLine(y);
    if (hudCloud) hudCloud.setYear(y);
}


// The router cannot clear this: hudActiveYear belongs to this module, and a
// module may assign only its own bindings. So it asks rather than writes.
export function resetHudYear() {
    hudActiveYear = null;
}
