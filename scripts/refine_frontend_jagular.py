#!/usr/bin/env python3
"""
Jagular Frontend Refinement:
1. src/scene/timeline_player.ts
2. src/ui/timeline_scrubber.ts
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Three.js and TypeScript frontend architect.
You author concise, complete, robust production TypeScript code.
Never truncate code."""

    # 1. src/scene/timeline_player.ts
    print("🐆 Jagular: Refining src/scene/timeline_player.ts...")
    user_prompt_player = """SPEC-05 / TASK-CV-603:
Author complete `src/scene/timeline_player.ts`.
It must import:
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

Methods:
- `constructor(callbacks?: TimelinePlayerCallbacks)`
- `setCallbacks(callbacks: TimelinePlayerCallbacks): void`
- `attachViewport(viewport: ClusterViewport): void`
- `detachViewport(viewport: ClusterViewport): void`
- `loadTimeline(timeline: ClusterTimelineData): void`:
  Populates `keyframeOffsets` (using `kf.time_offset_seconds` or computing seconds from `start_time`).
  Resets time to 0 and applies frame 0.
- `play(): void`, `pause(): void`, `togglePlay(): void`
- `seekToTime(seconds: number): void`
- `seekToFrame(index: number): void`
- `seekToPreviousKeyframe(): void`: seeks to previous index or 0.
- `seekToNextKeyframe(): void`: seeks to next index or last.
- `setSpeed(speed: number): void`: updates `playbackSpeed`, triggers `callbacks.onSpeedChanged`.
- `setLoop(loop: boolean): void`
- `update(delta: number): void`:
  If playing: advances `currentTime += delta * playbackSpeed`.
  Handles duration boundary (loops or pauses).
  Finds active keyframe index for `currentTime`.
  If keyframe index changed:
    Trigger events in keyframe via `callbacks.onEventTriggered`.
    Trigger `callbacks.onKeyframeChanged`.
    Call `applyKeyframeDelta(prevKf, nextKf)`.
  Trigger `callbacks.onTimeUpdate`.
- `applyKeyframeDelta(prevKf: ClusterTimelineKeyframeData | null, nextKf: ClusterTimelineKeyframeData): void`:
  If `nextKf.graph`:
    for each attached viewport, call `viewport.loadGraph(nextKf.graph)`.
  Else if `nextKf.nodes`:
    construct minimal `ClusterGraphData` and load on viewports.
- Getters:
  `getCurrentTime(): number`, `getDuration(): number`, `getSpeed(): number`, `getIsPlaying(): boolean`, `getKeyframes(): ClusterTimelineKeyframeData[]`, `getCurrentKeyframe(): ClusterTimelineKeyframeData | null`.

Output ONLY complete TypeScript code inside ```typescript ```.
"""

    code_player = call_jagular(system_prompt, user_prompt_player, temperature=0.1, max_tokens=3500)
    match_p = re.search(r"```typescript\s*(.*?)\s*```", code_player, re.DOTALL)
    if match_p:
        code_player = match_p.group(1)

    out_player_path = os.path.join(REPO_ROOT, "src", "scene", "timeline_player.ts")
    with open(out_player_path, "w") as f:
        f.write(code_player.strip() + "\n")
    print(f"Authored {out_player_path}")

    # 2. src/ui/timeline_scrubber.ts
    print("\n🐆 Jagular: Refining src/ui/timeline_scrubber.ts...")
    user_prompt_scrubber = """SPEC-05 / TASK-CV-604:
Author complete `src/ui/timeline_scrubber.ts`.
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
- Export class `TimelineScrubber`:
  - `private container: HTMLElement;`
  - `private player: TimelinePlayer | null = null;`
  - `private isVisible: boolean = false;`
  - `private isDragging: boolean = false;`
  - `private speedSteps: number[] = [0.5, 1, 2, 5, 10];`
  - `private speedIndex: number = 1;`
  - `private duration: number = 0;`

  Build DOM with:
  - Container id `timeline-scrubber-dock` (fixed at bottom, blur background, z-index 500).
  - Play button (`▶ PLAY` / `⏸ PAUSE`)
  - Prev button (`⏮`)
  - Next button (`⏭`)
  - Speed button (`1x`)
  - Time readout (`00:00 / 01:00`)
  - Scrubber track with progress bar, draggable thumb, and diamond pin markers container.
  - Event marquee banner at bottom showing latest event summary.
  - Close button (`✕`) which hides scrubber.

  Methods:
  - `attachPlayer(player: TimelinePlayer): void`:
    Wires callbacks on player:
    - `onTimeUpdate(curr, dur, index)`: updates progress bar width and time readout.
    - `onPlayStateChanged(isPlaying)`: updates play button text.
    - `onSpeedChanged(speed)`: updates speed button text.
    - `onEventTriggered(event)`: flashes event banner with `event.summary`.
    - `onKeyframeChanged(kf, idx)`: highlights active pin marker.
  - `renderKeyframePins(timeline: ClusterTimelineData): void`:
    Renders diamond pins along track at `(offset / duration) * 100%`.
    Hover shows tooltip with event summary, clicking pin calls `player.seekToFrame(i)`.
  - Scrubbing events: mouse down on track or thumb, drag updates `player.seekToTime(percent * duration)`.
  - `show(): void`, `hide(): void`, `toggle(): void`.
  - Keyboard shortcuts: Space (play/pause), ArrowLeft/ArrowRight (seek +/- 2s).

Output ONLY complete TypeScript code inside ```typescript ```.
"""

    code_scrubber = call_jagular(system_prompt, user_prompt_scrubber, temperature=0.1, max_tokens=3500)
    match_s = re.search(r"```typescript\s*(.*?)\s*```", code_scrubber, re.DOTALL)
    if match_s:
        code_scrubber = match_s.group(1)

    out_scrubber_path = os.path.join(REPO_ROOT, "src", "ui", "timeline_scrubber.ts")
    with open(out_scrubber_path, "w") as f:
        f.write(code_scrubber.strip() + "\n")
    print(f"Authored {out_scrubber_path}")

if __name__ == "__main__":
    run()
