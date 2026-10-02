#!/usr/bin/env python3
"""
Jagular generator for src/ui/timeline_scrubber.ts
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Three.js and TypeScript frontend architect.
You author clean, concise TypeScript classes conforming strictly to ES6 and standard DOM APIs.
Never use complicated cssText strings. Use clean HTML templates via innerHTML and simple styles."""

    user_prompt = """SPEC-05 / TASK-CV-604:
Author `src/ui/timeline_scrubber.ts`: HUD Timeline Scrubber component.

Imports:
```typescript
import {
  TimelinePlayer,
  ClusterTimelineData,
  ClusterTimelineKeyframeData,
  TimelineEventData,
} from '../scene/timeline_player.js';
```

Requirements:
Export class `TimelineScrubber`:
```typescript
export class TimelineScrubber {
  private container: HTMLElement;
  private player: TimelinePlayer | null = null;
  private isVisible: boolean = false;
  private isDragging: boolean = false;
  private speedSteps: number[] = [0.5, 1, 2, 5, 10];
  private speedIndex: number = 1;
  private duration: number = 0;

  // DOM elements:
  private playBtn!: HTMLButtonElement;
  private prevBtn!: HTMLButtonElement;
  private nextBtn!: HTMLButtonElement;
  private speedBtn!: HTMLButtonElement;
  private timeReadout!: HTMLElement;
  private track!: HTMLElement;
  private progressBar!: HTMLElement;
  private thumb!: HTMLElement;
  private pinsContainer!: HTMLElement;
  private eventBanner!: HTMLElement;
  private closeBtn!: HTMLButtonElement;

  constructor() {
    this.container = document.createElement('div');
    this.container.id = 'timeline-scrubber-dock';
    this.container.className = 'timeline-scrubber-dock';
    this.container.style.display = 'none';

    this.container.innerHTML = `
      <div class="ts-row">
        <button class="btn" id="ts-prev" title="Previous Keyframe">⏮</button>
        <button class="btn" id="ts-play" title="Play/Pause">▶ PLAY</button>
        <button class="btn" id="ts-next" title="Next Keyframe">⏭</button>
        <button class="btn" id="ts-speed" title="Speed">1x</button>
        <span class="ts-time" id="ts-time">00:00 / 00:00</span>
        <div class="ts-spacer" style="flex:1"></div>
        <button class="btn" id="ts-close" title="Close">✕</button>
      </div>
      <div class="ts-track-wrap" id="ts-track-wrap">
        <div class="ts-track" id="ts-track">
          <div class="ts-progress" id="ts-progress"></div>
          <div class="ts-thumb" id="ts-thumb"></div>
          <div class="ts-pins" id="ts-pins"></div>
        </div>
      </div>
      <div class="ts-banner" id="ts-banner" style="display:none"></div>
    `;
    document.body.appendChild(this.container);

    this.initElements();
    this.bindEvents();
  }
...
```

Methods to implement:
- `initElements()`: querySelector all elements from this.container.
- `bindEvents()`:
  - playBtn click -> `this.player?.togglePlay()`
  - prevBtn click -> `this.player?.seekToPreviousKeyframe()`
  - nextBtn click -> `this.player?.seekToNextKeyframe()`
  - speedBtn click -> cycle speed:
    `this.speedIndex = (this.speedIndex + 1) % this.speedSteps.length; const s = this.speedSteps[this.speedIndex]; this.player?.setSpeed(s); this.speedBtn.textContent = s + 'x';`
  - closeBtn click -> `this.hide()`
  - track / thumb mousedown -> start drag, listen to window mousemove/mouseup, call `seekFromEvent(e)`
  - window keydown -> Space: togglePlay, ArrowLeft: seek(-2), ArrowRight: seek(+2)
- `seekFromEvent(e: MouseEvent)`:
  calc ratio `const rect = this.track.getBoundingClientRect(); const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)); this.player?.seekToTime(ratio * this.duration);`
- `formatTime(sec: number): string`: `MM:SS` format.
- `attachPlayer(player: TimelinePlayer)`:
  - store `this.player = player`
  - wire callbacks:
    - `player.callbacks.onTimeUpdate = (curr, dur, idx) => { ... update progress width %, thumb left %, timeReadout.textContent ... }`
    - `player.callbacks.onPlayStateChanged = (isPlaying) => { this.playBtn.textContent = isPlaying ? '⏸ PAUSE' : '▶ PLAY'; }`
    - `player.callbacks.onSpeedChanged = (s) => { this.speedBtn.textContent = s + 'x'; }`
    - `player.callbacks.onEventTriggered = (ev) => { this.flashBanner(ev.summary); }`
    - `player.callbacks.onKeyframeChanged = (kf, idx) => { this.highlightPin(idx); }`
- `renderKeyframePins(timeline: ClusterTimelineData)`:
  - empty pinsContainer
  - for each keyframe: calculate position `(offset / duration) * 100%`, create pin element with title=event.summary or `Frame ${i}`, click pin -> `this.player?.seekToFrame(i)`.
- `flashBanner(msg: string)`: show `ts-banner` with `msg`, flash animation or 3s timeout.
- `highlightPin(activeIdx: number)`: add active class to matching pin.
- `show()`, `hide()`, `toggle()`: sets `display = 'flex'` / `'none'` and toggles `this.isVisible`.

Output ONLY complete TypeScript code inside ```typescript ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3500)
    m = re.search(r"```typescript\s*(.*?)\s*```", code, re.DOTALL)
    if m:
        out_path = os.path.join(REPO_ROOT, "src", "ui", "timeline_scrubber.ts")
        with open(out_path, "w") as f:
            f.write(m.group(1).strip() + "\n")
        print(f"Authored {out_path}")

if __name__ == "__main__":
    run()
