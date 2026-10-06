// The team cloud canvas and its particle field. Seeded, so the same
// season draws the same cloud every time — the rendered-DOM gate
// depends on that.

import { getEraInfo, mulberry32 } from '../format.js';
import { DATA } from '../state.js';
import { hudChart, renderTimelineHud } from './hud.js';

function createTeamCloud(canvas) {
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let w = 0, h = 0, raf = null, year = null, particles = [];

    function resize() {
        const box = canvas.parentElement;
        w = canvas.width = box.clientWidth;
        h = canvas.height = box.clientHeight;
        replan();
    }

    // The cloud belongs to the plot, not to the canvas: stay under the top of the
    // graph and above the horizontal axis, and keep both ends clear so a dot
    // arriving from the right, or leaving to the left, reads as movement rather
    // than as noise inside the crowd. The insets are generous because shadowBlur
    // spreads each dot roughly 15px past its edge — a slot at the axis line paints
    // into the year labels.
    function activeBand() {
        const area = (hudChart && hudChart.chartArea) || { left: 0, right: w, top: 0, bottom: h };
        const side = Math.max(0, area.right - area.left) * 0.08;
        const left = area.left + side;
        const right = area.right - side;
        const top = area.top + 12;
        const bottom = area.bottom - 16;
        return { left, right, top, bottom, width: right - left, height: bottom - top };
    }

    function hashKey(key) {
        let hv = 0x811c9dc5;
        for (let i = 0; i < key.length; i++) {
            hv ^= key.charCodeAt(i);
            hv = Math.imul(hv, 0x01000193);
        }
        return hv >>> 0;
    }

    // A player's slot is a property of the player, not of the year: someone who
    // stays on the roster keeps their spot instead of drifting to a new one.
    function place(p, band) {
        const rng = mulberry32(hashKey(p.key));
        p.tx = band.left + rng() * band.width;
        p.ty = band.top + rng() * band.height;
    }

    function radiusFor(key) {
        return 2.2 + mulberry32(hashKey(`${key}#r`))() * 1.6;
    }

    // Hashed slots can collide, and a collision hides an arrival. Players who were
    // already on the roster are anchors — their slots are theirs from last year, so
    // they never get nudged. Only arrivals are pushed clear of them.
    function separate(live, band, fresh) {
        const minDist = 11;
        for (const p of live) {
            if (!fresh.has(p)) continue;
            for (let pass = 0; pass < 6; pass++) {
                let moved = false;
                for (const q of live) {
                    if (q === p) continue;
                    const dx = p.tx - q.tx, dy = p.ty - q.ty;
                    const d = Math.hypot(dx, dy);
                    if (d >= minDist) continue;
                    const push = minDist - (d || 0.5);
                    p.tx += (d ? dx / d : 1) * push;
                    p.ty += (d ? dy / d : 0) * push;
                    moved = true;
                }
                p.tx = Math.min(band.right, Math.max(band.left, p.tx));
                p.ty = Math.min(band.bottom, Math.max(band.top, p.ty));
                if (!moved) break;
            }
        }
    }

    // Re-derive every slot when the box changes size (window resize, HUD re-render).
    // Here everyone is new: the band itself moved, so all slots are recomputed.
    function replan() {
        if (!year || !w || !h) return;
        const band = activeBand();
        if (band.width <= 0 || band.height <= 0) return;
        const live = particles.filter(p => !p.leaving);
        for (const p of live) place(p, band);
        separate(live, band, new Set(live));
    }

    function colorFor(key) {
        const p = DATA.players[key];
        // Era colours are jersey-dark (Founders #a04a5a); on the navy background
        // they vanish, so lift them toward white before plotting.
        const base = p && p.first_year ? getEraInfo(p.first_year).statColors.goals : '#8a9bae';
        return lighten(base, 0.45);
    }

    function lighten(hex, amt) {
        const m = hex.replace('#', '');
        const full = m.length === 3 ? m.split('').map(c => c + c).join('') : m;
        const n = parseInt(full, 16);
        const lift = v => Math.round(v + (255 - v) * amt);
        return `rgb(${lift((n >> 16) & 255)}, ${lift((n >> 8) & 255)}, ${lift(n & 255)})`;
    }

    function draw() {
        ctx.clearRect(0, 0, w, h);
        for (const p of particles) {
            ctx.globalAlpha = p.a;
            ctx.fillStyle = p.color;
            ctx.shadowColor = p.color;
            ctx.shadowBlur = 6;
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.globalAlpha = 1;
        ctx.shadowBlur = 0;
    }

    function frame() {
        let moving = false;
        for (const p of particles) {
            if (p.delay > 0) { p.delay -= 1; moving = true; continue; }
            if (p.leaving) { p.a = Math.max(0, p.a - 0.012); p.x -= 2.2; }
            else if (p.a < 0.9) { p.a = Math.min(0.9, p.a + 0.02); moving = true; }
            const dx = p.tx - p.x, dy = p.ty - p.y;
            p.x += dx * 0.025;
            p.y += dy * 0.025;
            if (Math.abs(dx) + Math.abs(dy) > 0.5) moving = true;
        }
        particles = particles.filter(p => !(p.leaving && p.a <= 0));
        draw();
        raf = (moving && particles.length) ? requestAnimationFrame(frame) : null;
    }

    function start() {
        if (reduceMotion) { particles.forEach(p => { p.x = p.tx; p.y = p.ty; p.delay = 0; p.a = p.leaving ? 0 : 0.9; }); particles = particles.filter(p => !p.leaving); draw(); return; }
        if (!raf) raf = requestAnimationFrame(frame);
    }

    function setYear(y) {
        const key = String(y);
        if (key === year) return;
        year = key;
        if (!w || !h) resize();
        if (!w || !h) return; // page hidden: nothing to draw into yet

        const band = activeBand();
        if (band.width <= 0 || band.height <= 0) return;

        // The roster is a list of site keys, which is what players.json is keyed
        // by — no name round trip. Note that a dot's slot and radius are hashed
        // from this key, so re-keying the data reshuffles which dot sits where;
        // the rule (deterministic per year, arrivals stagger, incumbents keep
        // their slot) is unchanged.
        const roster = ((DATA.years[key] && DATA.years[key].roster) || []);
        const inRoster = new Set(roster);

        for (const p of particles) {
            if (!inRoster.has(p.key)) { p.leaving = true; p.a = Math.max(p.a, 0.7); }
        }
        const live = particles.filter(p => !p.leaving);
        for (const p of live) place(p, band);   // same slot as last year

        // Only the arrival stagger is seeded by the year; positions are not.
        const rng = mulberry32(parseInt(key, 10) || 1);
        const present = new Set(live.map(p => p.key));
        const fresh = new Set();
        for (const playerKey of roster) {
            if (present.has(playerKey)) continue;
            const p = {
                key: playerKey,
                color: colorFor(playerKey),
                r: radiusFor(playerKey),
                x: w + 10,
                y: 0,
                tx: 0, ty: 0,
                a: 0,
                delay: Math.floor(rng() * 24),
                leaving: false
            };
            place(p, band);
            p.y = p.ty;   // slide in along the row they will settle on
            particles.push(p);
            live.push(p);
            fresh.add(p);
        }

        separate(live, band, fresh);
        start();
    }

    function pause() { if (raf) { cancelAnimationFrame(raf); raf = null; } }
    function resume() { if (!raf && !reduceMotion) raf = requestAnimationFrame(frame); }

    resize();
    return { setYear, resize, pause, resume };
}


export let hudCloud = null;


// ==================== PARTICLES ====================
export function initParticles() {
    const canvas = document.getElementById('paw-particles');
    const ctx = canvas.getContext('2d');
    let w, h, particles = [];

    function resize() {
        w = canvas.width = window.innerWidth;
        h = canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    class Particle {
        constructor() {
            this.reset();
        }
        reset() {
            this.x = Math.random() * w;
            this.y = Math.random() * h;
            this.vx = (Math.random() - 0.5) * 0.3;
            this.vy = (Math.random() - 0.5) * 0.3;
            this.r = Math.random() * 2 + 0.5;
            this.alpha = Math.random() * 0.3 + 0.1;
        }
        update() {
            this.x += this.vx;
            this.y += this.vy;
            if (this.x < 0 || this.x > w || this.y < 0 || this.y > h) this.reset();
        }
        draw() {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(229, 176, 55, ${this.alpha})`;
            ctx.fill();
        }
    }

    for (let i = 0; i < 60; i++) particles.push(new Particle());

    function animate() {
        ctx.clearRect(0, 0, w, h);
        particles.forEach(p => { p.update(); p.draw(); });
        requestAnimationFrame(animate);
    }
    animate();
}



// renderTimelineHud used to write `if (!hudCloud) hudCloud = createTeamCloud(...)`.
// hudCloud belongs here, so the check lives here too and the HUD asks for a
// cloud — which is what it wanted anyway.
export function ensureHudCloud() {
    if (!hudCloud) hudCloud = createTeamCloud(document.getElementById('hud-cloud'));
    return hudCloud;
}
