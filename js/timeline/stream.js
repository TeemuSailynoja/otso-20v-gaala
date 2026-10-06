// The year blocks: what is on screen, and which year the scroll says
// you are reading.

import { SEASON_STORY, computeHighlightBadges } from '../badges.js';
import { MEDAL_EMOJI, SEASON_LABEL } from '../format.js';
import { DATA } from '../state.js';
import { hudActiveYear, hudYearList, setHudYear } from './hud.js';

let yearObserver = null;

let streamRaf = null;


// Kesä / Talvi split for one year, following the active view.
export function seasonSplitLine(y) {
    const summer = DATA.yearsOtsoSummer;
    const winter = DATA.yearsOtsoWinter;
    const parts = [];
    for (const [label, src] of [['Kesä', summer], ['Talvi', winter]]) {
        const s = src && src[y];
        if (s && (s.wins + s.losses) > 0) parts.push(`${label} ${s.wins}–${s.losses}`);
    }
    return parts.join(' · ');
}


// The raw scrape writes the same club four ways — Otso, OTSO, Otso1, Otso 2,
// OTSO 2. Collapse them to one label; Otso1 is the main team, not a reserve.
export function otsoTeamLabel(name) {
    const raw = String(name || '').replace(/\s+/g, ' ').trim();
    if (!raw) return '';
    if (raw.toLowerCase().replace(/[\s-]/g, '') === 'otso1') return 'Otso';
    const family = raw.replace(/^otso\s*/i, '').trim();
    if (!family || family === '1') return 'Otso';
    return `Otso ${family}`;
}


// Every Otso team that finished the season-deciding event, not just the best one:
// in 2013 winter Otso won it, Otso 2 was 7th and Otso 3 was 10th.
function teamPlacementsLine(y) {
    const seasons = ((DATA.trophies && DATA.trophies.seasons) || []).filter(s => String(s.year) === y);
    const groups = [];
    for (const s of seasons) {
        if (!s.played || !(s.entries || []).length) continue;
        const label = SEASON_LABEL[s.season] || s.season;
        const teams = s.entries.map(e =>
            // A middot before a numeric placement: "Otso 2 · 5." must not read
            // as a team called Otso 25, or "Otso 2 🥉, Otso 4." as Otso 4.
            e.medal ? `${otsoTeamLabel(e.team)} ${MEDAL_EMOJI[e.medal]}` : `${otsoTeamLabel(e.team)} · ${e.placement}`
        ).join(', ');
        groups.push(`<span class="team-group"><span class="team-season">${label}</span><span>${teams}</span></span>`);
    }
    return groups.join('');
}


export function renderTimelineStream() {
    const host = document.getElementById('timeline-stream');
    if (!host) return;
    const years = hudYearList();
    const badges = computeHighlightBadges();
    host.innerHTML = years.map(y => {
        const d = DATA.years[y];
        const played = d.wins + d.losses;
        const wr = played > 0 ? Math.round(d.wins / played * 100) : 0;
        const diff = d.goals_for - d.goals_against;
        return `
                <div class="year-block" data-year="${y}">
                    <div class="year-num">${y}</div>
                    <div class="year-stats">
                        <div class="year-stat">
                            <div class="val" style="color: ${wr >= 60 ? 'var(--gold)' : wr >= 45 ? 'var(--blue)' : 'var(--red)'}">${d.wins}–${d.losses}</div>
                            <div class="lbl">${wr}% win rate</div>
                        </div>
                        <div class="year-stat">
                            <div class="val" style="color: ${diff > 0 ? 'var(--gold)' : 'var(--red)'}">${diff > 0 ? '+' : ''}${diff}</div>
                            <div class="lbl">Goal diff</div>
                        </div>
                    </div>
                    <div class="year-split">${seasonSplitLine(y)}</div>
                    <div class="year-teams">${teamPlacementsLine(y)}</div>
                    <div class="year-badges">${(badges[y] || []).map(b => `<span class="year-badge">${b}</span>`).join('')}</div>
                    <div class="year-notes">${(SEASON_STORY[y] || []).map(n => `<p class="year-note">${n}</p>`).join('')}</div>
                </div>`;
    }).join('');
    observeYearBlocks();
    const first = host.querySelector('.year-block');
    if (first) first.classList.add('active');
}


// Reveal on entry (same idea as the home category carousel, index.html:1541).
function observeYearBlocks() {
    if (yearObserver) yearObserver.disconnect();
    yearObserver = new IntersectionObserver(entries => {
        entries.forEach(e => {
            if (e.isIntersecting && e.intersectionRatio > 0.15) e.target.classList.add('active');
        });
    }, { threshold: [0.15, 0.4], rootMargin: '-5% 0px -5% 0px' });
    document.querySelectorAll('.year-block').forEach(b => yearObserver.observe(b));
}


// Which year the reader is standing on: the block whose centre is nearest the
// middle of the viewport. A scroll handler is more direct here than squeezing
// "closest" into the reveal observer.
function activeYearFromScroll() {
    const blocks = document.querySelectorAll('.year-block');
    if (!blocks.length) return;
    const mid = window.innerHeight / 2;
    let best = null;
    let bestDist = Infinity;
    blocks.forEach(b => {
        const r = b.getBoundingClientRect();
        const dist = Math.abs(r.top + r.height / 2 - mid);
        if (dist < bestDist) { bestDist = dist; best = b; }
    });
    if (best && best.dataset.year !== hudActiveYear) setHudYear(best.dataset.year);
}


window.addEventListener('scroll', () => {
    if (!document.getElementById('page-timeline')?.classList.contains('active')) return;
    if (streamRaf) return;
    streamRaf = requestAnimationFrame(() => {
        streamRaf = null;
        activeYearFromScroll();
    });
}, { passive: true });

