#!/usr/bin/env python3
"""
TASK-CV-504 & TASK-CV-505: Jagular runner for Frontend LiveStreamManager and Dynamic Delta Animations.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    print("--- Summoning Jagular for TASK-CV-504 (src/scene/live_stream.ts) ---")
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Three.js and TypeScript frontend architect.
You author production-grade, highly reliable TypeScript modules for WebGL and browser event streaming."""

    # 1. TASK-CV-504: src/scene/live_stream.ts
    user_prompt_stream = """SPEC-04 / TASK-CV-504:
Author `src/scene/live_stream.ts`: Real-time Server-Sent Events (SSE) streaming client.

Requirements:
1. Export type `StreamStatus = 'connected' | 'reconnecting' | 'disconnected';`
2. Export interface `LiveStreamCallbacks`:
   - `onStatusChange?: (status: StreamStatus, url?: string) => void;`
   - `onInitialSnapshot?: (snapshot: any) => void;`
   - `onNodeAdded?: (node: any) => void;`
   - `onNodeRemoved?: (nodeId: string) => void;`
   - `onNodeModified?: (nodeId: string, diffDetails?: string[], status?: string) => void;`
   - `onEdgeUpdated?: (edges: any[]) => void;`
   - `onHeartbeat?: (data: { timestamp: number; active_clients: number }) => void;`
   - `onError?: (error: any) => void;`

3. Export class `LiveStreamManager`:
   - `private eventSource: EventSource | null = null;`
   - `private currentUrl: string | null = null;`
   - `private status: StreamStatus = 'disconnected';`
   - `private reconnectAttempts = 0;`
   - `private reconnectTimeout: number | null = null;`
   - `private callbacks: LiveStreamCallbacks = {};`
   - `constructor(callbacks?: LiveStreamCallbacks)`
   - `connect(url: string): void`:
     - Clean up any existing connection.
     - Sets status to 'reconnecting' then creates `new EventSource(url)`.
     - Listens to standard events:
       - `eventSource.onopen`: status = 'connected', reconnectAttempts = 0, notify status.
       - `eventSource.onerror`: if disconnected, trigger reconnect backoff (1s, 2s, 4s up to 15s).
       - `eventSource.addEventListener('initial_snapshot', (e) => { ... })`
       - `eventSource.addEventListener('node_added', (e) => { ... })`
       - `eventSource.addEventListener('node_removed', (e) => { ... })`
       - `eventSource.addEventListener('node_modified', (e) => { ... })`
       - `eventSource.addEventListener('edge_updated', (e) => { ... })`
       - `eventSource.addEventListener('heartbeat', (e) => { ... })`
   - `disconnect(): void`: closes EventSource, clears reconnect timer, sets status to 'disconnected'.
   - `getStatus(): StreamStatus`
   - `getUrl(): string | null`
   - `setCallbacks(callbacks: LiveStreamCallbacks)`

Write the complete `src/scene/live_stream.ts`.
Output ONLY TypeScript code inside ```typescript ```.
"""

    code_stream = call_jagular(system_prompt, user_prompt_stream, temperature=0.1, max_tokens=3500)
    match_stream = re.search(r"```typescript\s*(.*?)\s*```", code_stream, re.DOTALL)
    if match_stream:
        code_stream = match_stream.group(1)

    out_stream_path = os.path.join(REPO_ROOT, "src/scene/live_stream.ts")
    with open(out_stream_path, "w") as f:
        f.write(code_stream.strip() + "\n")
    print(f"Authored {out_stream_path}")

    # 2. TASK-CV-505: Read current src/scene/cluster_viewport.ts and update with dynamic mutation methods
    print("\n--- Summoning Jagular for TASK-CV-505 (Dynamic Delta Animations in cluster_viewport.ts) ---")
    with open(os.path.join(REPO_ROOT, "src/scene/cluster_viewport.ts"), "r") as f:
        vp_source = f.read()

    user_prompt_vp = f"""SPEC-04 / TASK-CV-505:
Update `src/scene/cluster_viewport.ts` to add dynamic mutation handling:
1. Method `addNode(node: ClusterNodeData)`:
   - Clones prototype mesh (or fallback), sets position at `(node.spatial.x, node.spatial.y, node.spatial.z)`.
   - Starts with initial scale `(0.1, 0.1, 0.1)`.
   - Stores in `this.animatingEntrances: Map<string, {{ mesh: THREE.Object3D; startTime: number; duration: number }}>`
     so in `animate()`, it smoothly scales up to `(1, 1, 1)` over 600ms.
   - Applies emerald pulsing visual bracket.
   - Adds to `this.scene` and `this.nodeMeshes.set(node.id, mesh)`.
2. Method `removeNode(nodeId: string)`:
   - Finds mesh by `nodeId`.
   - Switches all materials to red transparent wireframe ghost (`color: 0xef4444`, `transparent: true`, `opacity: 0.45`, `depthWrite: false`).
   - Stores in `this.animatingDecays: Map<string, {{ mesh: THREE.Object3D; startTime: number; duration: number }}>`
     so in `animate()`, it fades and scales to 0 over 3000ms, then removes from `this.scene` and deletes from `this.nodeMeshes`.
3. Method `modifyNode(nodeId: string, diffDetails?: string[], status?: string)`:
   - Finds mesh by `nodeId`.
   - Updates `nodeData.diffStatus = status || 'version_skew'` and `nodeData.diffDetails = diffDetails`.
   - Re-applies `this.applyDiffVisuals(mesh, nodeData.diffStatus)`.
4. In `animate(delta)`:
   - Advance entrance animations: `scale = THREE.MathUtils.lerp(0.1, 1.0, progress)`.
   - Advance decay animations: `scale = THREE.MathUtils.lerp(1.0, 0.0, progress)`, `opacity = THREE.MathUtils.lerp(0.45, 0.0, progress)`. Clean up upon completion.

Here is the existing `src/scene/cluster_viewport.ts`:
```typescript
{vp_source}
```

Write the complete updated `src/scene/cluster_viewport.ts`.
Output ONLY TypeScript code inside ```typescript ```.
"""

    code_vp = call_jagular(system_prompt, user_prompt_vp, temperature=0.1, max_tokens=4500)
    match_vp = re.search(r"```typescript\s*(.*?)\s*```", code_vp, re.DOTALL)
    if match_vp:
        code_vp = match_vp.group(1)

    out_vp_path = os.path.join(REPO_ROOT, "src/scene/cluster_viewport.ts")
    with open(out_vp_path, "w") as f:
        f.write(code_vp.strip() + "\n")
    print(f"Authored {out_vp_path}")

if __name__ == "__main__":
    run()
