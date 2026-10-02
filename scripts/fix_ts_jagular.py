#!/usr/bin/env python3
"""
Jagular generator for strict TypeScript compliance:
- src/scene/timeline_player.ts
- src/ui/timeline_scrubber.ts
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Three.js and TypeScript frontend architect.
You author production TypeScript code strictly compliant with:
- verbatimModuleSyntax (use `import type { ... }` for types)
- strict: true
- noUnusedLocals: true
- noUnusedParameters: true (prefix unused callback args with `_`)
- noUncheckedIndexedAccess: true (array indexing returns `T | undefined`, handle with `??` or guards)"""

    # 1. src/scene/timeline_player.ts
    print("🐆 Jagular: Generating strict src/scene/timeline_player.ts...")
    user_prompt_player = """SPEC-05 / TASK-CV-603:
Author `src/scene/timeline_player.ts` with 100% strict TypeScript types.

Imports:
```typescript
import { ClusterViewport } from './cluster_viewport.js';
import type { ClusterGraphData, ClusterNodeData } from './cluster_viewport.js';
```

Interfaces:
```typescript
export interface TimelineEventData {
  timestamp: string;
  event_type: 'pod_scheduled' | 'pod_evicted' | 'image_updated' | 'node_scaled' | 'config_drift' | 'custom';
  summary: string;
  affected_node_ids?: string[];
  metadata?: Record<string, any>;
}

export interface ClusterTimelineKeyframeData {
  timestamp: string;
  snapshot_index: number;
  time_offset_seconds?: number;
  graph?: ClusterGraphData;
  nodes?: ClusterNodeData[];
  edges?: any[];
  events?: TimelineEventData[];
  delta_summary?: Record<string, any>;
}

export interface ClusterTimelineData {
  $schema?: string;
  cluster_name: string;
  start_time: string;
  end_time: string;
  duration_seconds: number;
  keyframes: ClusterTimelineKeyframeData[];
  metadata?: Record<string, any>;
}

export interface TimelinePlayerCallbacks {
  onTimeUpdate?: (currentTime: number, duration: number, keyframeIndex: number) => void;
  onKeyframeChanged?: (keyframe: ClusterTimelineKeyframeData, index: number) => void;
  onEventTriggered?: (event: TimelineEventData) => void;
  onPlayStateChanged?: (isPlaying: boolean) => void;
  onSpeedChanged?: (speed: number) => void;
}
```

Class `TimelinePlayer`:
- `private timeline: ClusterTimelineData | null = null;`
- `private viewports: ClusterViewport[] = [];`
- `private currentTime: number = 0;`
- `private currentKeyframeIndex: number = -1;`
- `private isPlaying: boolean = false;`
- `private playbackSpeed: number = 1.0;`
- `private isLooping: boolean = true;`
- `public callbacks: TimelinePlayerCallbacks = {};`
- `private keyframeOffsets: number[] = [];`

Implement methods:
- `constructor(callbacks?: TimelinePlayerCallbacks)`
- `setCallbacks(callbacks: TimelinePlayerCallbacks): void`
- `attachViewport(viewport: ClusterViewport): void`
- `detachViewport(viewport: ClusterViewport): void`
- `loadTimeline(timeline: ClusterTimelineData): void`:
  Sets `this.timeline = timeline`.
  Populates `keyframeOffsets`:
    for each kf: `offset = kf.time_offset_seconds ?? ((new Date(kf.timestamp).getTime() - startTime) / 1000)`.
  Resets `this.currentTime = 0`, `this.currentKeyframeIndex = -1`, `this.isPlaying = false`.
  If `timeline.keyframes.length > 0`:
    `const firstKf = timeline.keyframes[0]!;`
    `this.applyKeyframe(firstKf);`
    `this.currentKeyframeIndex = 0;`
    `this.callbacks.onKeyframeChanged?.(firstKf, 0);`
- `play(): void`, `pause(): void`, `togglePlay(): void`
- `seekToTime(seconds: number): void`:
  Clamps seconds between 0 and `this.timeline?.duration_seconds ?? 0`.
  Updates `this.currentTime`.
  Calls `this.updateKeyframeIndex()`.
- `seekToFrame(index: number): void`:
  Clamps index.
  `const offset = this.keyframeOffsets[clampedIndex];`
  `if (offset !== undefined) { this.currentTime = offset; this.updateKeyframeIndex(); }`
- `seekToPreviousKeyframe(): void`: index - 1 or 0
- `seekToNextKeyframe(): void`: index + 1
- `setSpeed(speed: number): void`
- `setLoop(loop: boolean): void`
- `update(delta: number): void`:
  If playing: advances `currentTime += delta * playbackSpeed`.
  Handles duration bounds (loop or pause).
  Calls `this.updateKeyframeIndex()`.
  Dispatches `onTimeUpdate?.(this.currentTime, this.getDuration(), this.currentKeyframeIndex)`.
- `private updateKeyframeIndex(): void`:
  Finds new index from `keyframeOffsets`.
  If `newIndex !== this.currentKeyframeIndex` and `newIndex >= 0`:
    `const nextKf = this.timeline?.keyframes[newIndex];`
    `if (nextKf) {`
      `if (nextKf.events) { for (const ev of nextKf.events) this.callbacks.onEventTriggered?.(ev); }`
      `this.callbacks.onKeyframeChanged?.(nextKf, newIndex);`
      `this.applyKeyframe(nextKf);`
      `this.currentKeyframeIndex = newIndex;`
    `}`
- `applyKeyframe(kf: ClusterTimelineKeyframeData): void`:
  If `kf.graph`:
    for each viewport, `viewport.loadGraph(kf.graph);`
  Else if `kf.nodes`:
    `const g: ClusterGraphData = { metadata: { cluster_name: this.timeline?.cluster_name ?? 'cluster-alpha', kubernetes_version: 'v1.36.4', distribution: 'kind', node_count: 2, pod_count: 2 }, nodes: kf.nodes, edges: kf.edges ?? [] };`
    for each viewport, `viewport.loadGraph(g);`
- Getters:
  `getCurrentTime(): number`
  `getDuration(): number`
  `getSpeed(): number`
  `getIsPlaying(): boolean`
  `getKeyframes(): ClusterTimelineKeyframeData[]`
  `getCurrentKeyframe(): ClusterTimelineKeyframeData | null` -> `return (this.timeline && this.currentKeyframeIndex >= 0) ? (this.timeline.keyframes[this.currentKeyframeIndex] ?? null) : null;`

Output ONLY TypeScript code inside ```typescript ```.
"""
    code_p = call_jagular(system_prompt, user_prompt_player, temperature=0.1, max_tokens=3500)
    m_p = re.search(r"```typescript\s*(.*?)\s*```", code_p, re.DOTALL)
    if m_p:
        out_path_p = os.path.join(REPO_ROOT, "src", "scene", "timeline_player.ts")
        with open(out_path_p, "w") as f:
            f.write(m_p.group(1).strip() + "\n")
        print(f"Authored {out_path_p}")

    # 2. src/ui/timeline_scrubber.ts
    print("\n🐆 Jagular: Generating strict src/ui/timeline_scrubber.ts...")
    user_prompt_scrubber = """SPEC-05 / TASK-CV-604:
Author `src/ui/timeline_scrubber.ts` with 100% strict TypeScript types.

Imports:
```typescript
import { TimelinePlayer } from '../scene/timeline_player.js';
import type {
  ClusterTimelineData,
  ClusterTimelineKeyframeData,
  TimelineEventData,
} from '../scene/timeline_player.js';
```

Requirements:
Class `TimelineScrubber`:
- `private container: HTMLElement;`
- `private player: TimelinePlayer | null = null;`
- `private isVisible: boolean = false;`
- `private isDragging: boolean = false;`
- `private speedSteps: number[] = [0.5, 1, 2, 5, 10];`
- `private speedIndex: number = 1;`
- `private duration: number = 0;`

- Element fields:
  `private playBtn!: HTMLButtonElement;`
  `private prevBtn!: HTMLButtonElement;`
  `private nextBtn!: HTMLButtonElement;`
  `private speedBtn!: HTMLButtonElement;`
  `private timeReadout!: HTMLElement;`
  `private track!: HTMLElement;`
  `private progressBar!: HTMLElement;`
  `private thumb!: HTMLElement;`
  `private pinsContainer!: HTMLElement;`
  `private eventBanner!: HTMLElement;`
  `private closeBtn!: HTMLButtonElement;`

Constructor:
Creates `#timeline-scrubber-dock` with HTML:
```html
<div class="ts-row">
  <button class="btn" id="ts-prev" title="Previous Keyframe">⏮</button>
  <button class="btn" id="ts-play" title="Play/Pause">▶ PLAY</button>
  <button class="btn" id="ts-next" title="Next Keyframe">⏭</button>
  <button class="btn" id="ts-speed" title="Speed">1x</button>
  <span class="ts-time" id="ts-time">00:00 / 00:00</span>
  <div style="flex:1"></div>
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
```
Appends to `document.body`.
Calls `this.initElements()`, `this.bindEvents()`.

Methods:
- `initElements()`
- `bindEvents()`:
  - playBtn click -> `this.player?.togglePlay()`
  - prevBtn click -> `this.player?.seekToPreviousKeyframe()`
  - nextBtn click -> `this.player?.seekToNextKeyframe()`
  - speedBtn click:
    `this.speedIndex = (this.speedIndex + 1) % this.speedSteps.length;`
    `const s = this.speedSteps[this.speedIndex] ?? 1.0;`
    `this.player?.setSpeed(s);`
    `this.speedBtn.textContent = \`${s}x\`;`
  - closeBtn click -> `this.hide()`
  - track / thumb mousedown -> start drag, window mousemove / mouseup
  - window keydown (if isVisible): Space togglePlay, ArrowLeft seek(-2), ArrowRight seek(+2)
- `seekFromEvent(e: MouseEvent)`:
  `const rect = this.track.getBoundingClientRect();`
  `const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));`
  `this.player?.seekToTime(ratio * this.duration);`
- `formatTime(sec: number): string`: `MM:SS`
- `attachPlayer(player: TimelinePlayer): void`:
  `this.player = player;`
  `this.duration = player.getDuration();`
  `player.callbacks.onTimeUpdate = (curr, dur, _idx) => {`
    `this.duration = dur;`
    `const pct = dur > 0 ? (curr / dur) * 100 : 0;`
    `this.progressBar.style.width = \`${pct}%\`;`
    `this.thumb.style.left = \`${pct}%\`;`
    `this.timeReadout.textContent = \`${this.formatTime(curr)} / ${this.formatTime(dur)}\`;`
  `};`
  `player.callbacks.onPlayStateChanged = (isPlaying) => { this.playBtn.textContent = isPlaying ? '⏸ PAUSE' : '▶ PLAY'; };`
  `player.callbacks.onSpeedChanged = (s) => { this.speedBtn.textContent = \`${s}x\`; };`
  `player.callbacks.onEventTriggered = (ev) => { this.flashBanner(ev.summary); };`
  `player.callbacks.onKeyframeChanged = (_kf, idx) => { this.highlightPin(idx); };`
- `renderKeyframePins(timeline: ClusterTimelineData): void`:
  `this.pinsContainer.innerHTML = '';`
  `const dur = timeline.duration_seconds || 1;`
  `timeline.keyframes.forEach((kf, i) => {`
    `const offset = kf.time_offset_seconds ?? 0;`
    `const pct = (offset / dur) * 100;`
    `const pin = document.createElement('div');`
    `pin.className = 'ts-pin';`
    `pin.style.left = \`${pct}%\`;`
    `pin.title = kf.events?.[0]?.summary || \`Frame \${i}\`;`
    `pin.addEventListener('click', (e) => { e.stopPropagation(); this.player?.seekToFrame(i); });`
    `this.pinsContainer.appendChild(pin);`
  `});`
- `flashBanner(msg: string)`:
  `this.eventBanner.textContent = msg;`
  `this.eventBanner.style.display = 'block';`
  `setTimeout(() => { if (this.eventBanner.textContent === msg) this.eventBanner.style.display = 'none'; }, 3000);`
- `highlightPin(activeIdx: number)`:
  highlights pin with active class.
- `show()`, `hide()`, `toggle()`

Output ONLY TypeScript code inside ```typescript ```.
"""
    code_s = call_jagular(system_prompt, user_prompt_scrubber, temperature=0.1, max_tokens=3500)
    m_s = re.search(r"```typescript\s*(.*?)\s*```", code_s, re.DOTALL)
    if m_s:
        out_path_s = os.path.join(REPO_ROOT, "src", "ui", "timeline_scrubber.ts")
        with open(out_path_s, "w") as f:
            f.write(m_s.group(1).strip() + "\n")
        print(f"Authored {out_path_s}")

if __name__ == "__main__":
    run()
