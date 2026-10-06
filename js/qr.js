// The QR badge and its overlay. The library comes from a CDN on demand, and
// the target URL has to survive the page's <base href>.


// ==================== QR OVERLAY ====================
// `?qr` on any URL turns the screen into a scannable link — the case is a laptop or a
// TV at the gaala and a phone across the room. The code encodes the current URL with the
// qr parameter stripped, so scanning lands on the page rather than on another overlay,
// and the hash route is kept: `?qr#/player/Roni%20Hotari` makes a code for one player.
function qrTargetUrl() {
    const url = new URL(location.href);
    url.searchParams.delete('qr');
    return url.toString();
}


// The encoder is only ever useful here, so it is fetched on demand instead of on every
// page view. If it cannot be fetched the address is still printed in full.
function loadQrLib() {
    if (window.QRCode) return Promise.resolve();
    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/qrcode@1.5.1/build/qrcode.min.js';
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    });
}


function isLocalAddress() {
    return location.protocol === 'file:'
        || /^(localhost|127\.|\[::1\]|0\.0\.0\.0)$/.test(location.hostname);
}


async function drawQr(canvas, text, size) {
    try {
        await loadQrLib();
        // Drawn at the size it will be shown, so the modules are not resampled on the
        // way to the screen — a code on a projector has to survive a phone camera at a
        // distance.
        await window.QRCode.toCanvas(canvas, text, { width: size, margin: 2, errorCorrectionLevel: 'M' });
    } catch (err) {
        const fallback = document.createElement('div');
        fallback.className = 'qr-warn';
        fallback.textContent = 'Could not load the QR code — copy the address above.';
        canvas.replaceWith(fallback);
    }
}


// `?qr` puts a scannable code in the top-left of the hero. The site is meant to run on a
// big screen at the gaala, and a corner code leaves the page — and the carousel — usable,
// unlike a full-screen takeover. Clicking it opens the big version for a room further away.
export function showQrBadge() {
    const hero = document.querySelector('#page-home .hero');
    if (!hero || hero.querySelector('.qr-badge')) return;
    const target = qrTargetUrl();
    const badge = document.createElement('div');
    badge.className = 'qr-badge';
    badge.title = 'Open the full-size code';
    badge.innerHTML = '<canvas class="qr-badge-canvas"></canvas><div class="qr-badge-caption">Scan to open</div>';
    const canvas = badge.querySelector('.qr-badge-canvas');
    canvas.setAttribute('aria-label', 'QR code for ' + target);
    if (isLocalAddress()) badge.querySelector('.qr-badge-caption').textContent = 'Local address';
    hero.appendChild(badge);
    const rect = canvas.getBoundingClientRect();
    const size = Math.max(160, Math.min(1024, Math.round((rect.width || 200) * (window.devicePixelRatio || 1))));
    drawQr(canvas, target, size);
    badge.addEventListener('click', showQrOverlay);
}


export function showQrOverlay() {
    const target = qrTargetUrl();
    const local = isLocalAddress();
    const overlay = document.createElement('div');
    overlay.className = 'qr-overlay';
    overlay.innerHTML = `<div class="qr-card">
            <div class="qr-title"></div>
            <canvas id="qr-canvas"></canvas>
            <div class="qr-url"></div>
            <div class="qr-warn" hidden>This address is local — only this machine can open it.</div>
            <div class="qr-hint">Point a phone camera at the code. Esc or click to close.</div>
        </div>`;
    // The address comes from the URL bar, so it goes in as text, never as markup.
    overlay.querySelector('.qr-title').textContent = document.title;
    overlay.querySelector('.qr-url').textContent = target;
    const warn = overlay.querySelector('.qr-warn');
    if (local) warn.hidden = false; else warn.remove();
    const canvas = overlay.querySelector('#qr-canvas');
    canvas.setAttribute('aria-label', 'QR code for ' + target);
    document.body.appendChild(overlay);
    const fullSize = Math.max(220, Math.floor(Math.min(window.innerWidth, window.innerHeight) * 0.6));

    const close = () => {
        overlay.remove();
        document.removeEventListener('keydown', onKey);
        // Drop the flag so a reload does not reopen the overlay.
        history.replaceState(null, '', target);
    };
    const onKey = (e) => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', onKey);
    overlay.addEventListener('click', close);
    drawQr(canvas, target, fullSize);
}


