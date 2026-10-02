#!/usr/bin/env python3
"""
Jagular Swarm Delegator for SPEC-05 Frontend:
- TASK-CV-603: src/scene/timeline_player.ts
- TASK-CV-604: src/ui/timeline_scrubber.ts
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Three.js and TypeScript frontend architect.
You author clean, modular, production-grade TypeScript modules with full type annotations.
Never truncate code."""

    # -------------------------------------------------------------
    # TASK-CV-603: src/scene/timeline_player.ts
    # -------------------------------------------------------------
    print("\n=======================================================")
    print("🐆 Summoning Jagular for TASK-CV-603 (src/scene/timeline_player.ts)")
    print("=======================================================")

    user_prompt_player = """SPEC-05 / TASK-CV-603:
Author `src/scene/timeline_player.ts`: Time-travel playback engine driving Three.js ClusterViewport.

Requirements:
1. Export interfaces:
```typescript
import { ClusterViewport } from './cluster_viewport.js';
import type { ClusterGraphData, ClusterNodeData } from './cluster_viewport.js';

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

2. Export class `TimelinePlayer`:
   - `private timeline: ClusterTimelineData | null = null;`
   - `private viewports: ClusterViewport[] = [];`
   - `private currentTime: number = 0;`
   - `private currentKeyframeIndex: number = -1;`
   - `private isPlaying: boolean = false;`
   - `private playbackSpeed: number = 1.0;`
   - `private isLooping: boolean = true;`
   - `private callbacks: TimelinePlayerCallbacks = {};`
   - `private keyframeOffsets: number[] = [];` // precalculated second offsets for each keyframe

   Methods:
   - `constructor(callbacks?: TimelinePlayerCallbacks)`
   - `setCallbacks(callbacks: TimelinePlayerCallbacks): void`
   - `attachViewport(viewport: ClusterViewport): void`
   - `detachViewport(viewport: ClusterViewport): void`
   - `loadTimeline(timeline: ClusterTimelineData): void`:
     - Normalizes keyframeOffsets from `time_offset_seconds` or by parsing ISO timestamps relative to `start_time`.
     - Resets `currentTime = 0`, `currentKeyframeIndex = -1`.
     - Applies first keyframe.
   - `play(): void`, `pause(): void`, `togglePlay(): void`
   - `seekToTime(seconds: number): void`:
     - Clamps `seconds` between 0 and `duration_seconds`.
     - Finds the active keyframe index for `seconds`.
     - If index changed, applies keyframe with `loadGraph` on viewports.
     - Dispatches `onTimeUpdate`.
   - `seekToFrame(index: number): void`:
     - Clamps index.
     - Sets `currentTime = this.keyframeOffsets[index]`.
     - Applies keyframe and notifies.
   - `setSpeed(speed: number): void`
   - `setLoop(loop: boolean): void`
   - `update(delta: number): void`:
     - If not playing or no timeline, return.
     - `this.currentTime += delta * this.playbackSpeed;`
     - If `this.currentTime >= this.timeline.duration_seconds`:
       - If `this.isLooping`: `this.currentTime = 0;` else pause.
     - Check if keyframe changed based on `this.currentTime`:
       - If keyframe changed, transitions viewport:
         - Dispatches `events` via `onEventTriggered`.
         - Calls `applyKeyframeDelta(prevKf, nextKf)` for smooth component mutations (`addNode`, `removeNode`, `modifyNode`), or `loadGraph` if gap > 1.
     - Dispatches `onTimeUpdate`.
   - `applyKeyframeDelta(prevKf: ClusterTimelineKeyframeData, nextKf: ClusterTimelineKeyframeData)`:
     - Detects added nodes -> calls `viewport.addNode(n)` on attached viewports.
     - Detects removed nodes -> calls `viewport.removeNode(nodeId)` on attached viewports.
     - Detects modified nodes -> calls `viewport.modifyNode(nodeId, diffDetails, status)` on attached viewports.
   - Getters:
     `getCurrentTime()`, `getDuration()`, `getSpeed()`, `getIsPlaying()`, `getKeyframes()`, `getCurrentKeyframe()`.

Write the complete `src/scene/timeline_player.ts`.
Output ONLY TypeScript code inside ```typescript ```.
"""

    code_player = call_jagular(system_prompt, user_prompt_player, temperature=0.1, max_tokens=4000)
    match_p = re.search(r"```typescript\s*(.*?)\s*```", code_player, re.DOTALL)
    if match_p:
        code_player = match_p.group(1)

    out_player_path = os.path.join(REPO_ROOT, "src", "scene", "timeline_player.ts")
    with open(out_player_path, "w") as f:
        f.write(code_player.strip() + "\n")
    print(f"\n Authored {out_player_path}")

    # -------------------------------------------------------------
    # TASK-CV-604: src/ui/timeline_scrubber.ts
    # -------------------------------------------------------------
    print("\n=======================================================")
    print("🐆 Summoning Jagular for TASK-CV-604 (src/ui/timeline_scrubber.ts)")
    print("=======================================================")

    user_prompt_scrubber = """SPEC-05 / TASK-CV-604:
Author `src/ui/timeline_scrubber.ts`: HUD Timeline Scrubber component with play/pause, slider, speed controls, event pins, and time display.

Requirements:
1. Import `TimelinePlayer`, `ClusterTimelineData`, `ClusterTimelineKeyframeData`, `TimelineEventData` from `../scene/timeline_player.js`.

2. Export class `TimelineScrubber`:
   - `private container: HTMLElement;`
   - `private player: TimelinePlayer | null = null;`
   - `private isVisible: boolean = false;`
   - `private isDragging: boolean = false;`
   - Elements:
     - Play button (`#ts-play-btn`)
     - Prev button (`#ts-prev-btn`)
     - Next button (`#ts-next-btn`)
     - Speed button (`#ts-speed-btn`) (cycles `0.5x` -> `1x` -> `2x` -> `5x` -> `10x`)
     - Time readout (`#ts-time-readout`) e.g. "00:15 / 01:00"
     - Slider track container (`#ts-track`)
     - Progress bar fill (`#ts-progress`)
     - Slider thumb handle (`#ts-thumb`)
     - Pin markers container (`#ts-pins`)
     - Event popover tooltip (`#ts-tooltip`)
     - Event marquee banner (`#ts-event-banner`) e.g. "⚡ [14:00:15] Canary pod scheduled on worker-2"
     - Close / Minimize button (`#ts-close-btn`)

3. Styling:
   Injects a dedicated style block `<style id="timeline-scrubber-styles">` if not present:
   - Bottom-docked HUD: `position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); width: calc(100% - 48px); max-width: 1080px; background: rgba(15, 23, 42, 0.94); backdrop-filter: blur(14px); border: 1px solid #334155; border-radius: 10px; box-shadow: 0 12px 36px rgba(0, 0, 0, 0.6); padding: 12px 20px; z-index: 500; font-family: monospace; display: flex; flex-direction: column; gap: 8px;`
   - Event pin marker (`.ts-event-pin`): Diamond shape `width: 10px; height: 10px; transform: rotate(45deg); background: #38bdf8; position: absolute; top: -3px; cursor: pointer; border: 1px solid #0f172a;`
   - Hover popover tooltip: clean dark glass tooltip showing time, event_type, and summary.
   - Smooth hover & active transitions.

4. Functionality:
   - `attachPlayer(player: TimelinePlayer): void`: wires up callbacks:
     - `onTimeUpdate(curr, dur, index)`: updates thumb position, progress fill, and time readout.
     - `onPlayStateChanged(isPlaying)`: updates play button icon/text ('▶ PLAY' vs '⏸ PAUSE').
     - `onSpeedChanged(speed)`: updates speed button text (`${speed}x`).
     - `onEventTriggered(event)`: flashes and updates the event banner text.
   - `renderKeyframePins(timeline: ClusterTimelineData): void`:
     - Creates diamond pin markers along `#ts-track` positioned at `(offset / duration) * 100%`.
     - Adds hover popover with event summary.
     - Clicking a pin calls `player.seekToFrame(i)`.
   - Scrubbing interaction:
     - Mouse down on track or thumb initiates drag.
     - Mouse move calculates percentage along track and calls `player.seekToTime(percent * duration)`.
     - Mouse up releases drag.
   - `show(): void`, `hide(): void`, `toggle(): void`.
   - Keyboard listener: Space to toggle play/pause, Left/Right arrow keys to seek +/- 2 seconds.

Write the complete `src/ui/timeline_scrubber.ts`.
Output ONLY TypeScript code inside ```typescript ```.
"""

    code_scrubber = call_jagular(system_prompt, user_prompt_scrubber, temperature=0.1, max_tokens=4000)
    match_s = re.search(r"```typescript\s*(.*?)\s*```", code_scrubber, re.DOTALL)
    if match_s:
        code_scrubber = match_s.group(1)

    out_scrubber_path = os.path.join(REPO_ROOT, "src", "ui", "timeline_scrubber.ts")
    with open(out_scrubber_path, "w") as f:
        f.write(code_scrubber.strip() + "\n")
    print(f"\n Authored {out_scrubber_path}")

if __name__ == "__main__":
    run()
