// The timeline page entry point. The stream, the HUD and the team cloud
// are separate modules; this is the order they come up in.

import { renderTimelineHud } from './timeline/hud.js';
import { renderTimelineStream } from './timeline/stream.js';

export function renderTimeline() {
    renderTimelineHud();
    renderTimelineStream();
}

