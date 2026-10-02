#!/usr/bin/env python3
"""
Jagular runner to author dynamic streaming mutation methods for src/scene/cluster_viewport.ts.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    print("--- Summoning Jagular for cluster_viewport.ts streaming mutation methods ---")
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Three.js graphics engineer."""

    user_prompt = """SPEC-04 / TASK-CV-505:
Author the TypeScript methods to add to `ClusterViewport` for real-time SSE streaming mutations and transitions:

1. Properties:
```typescript
  private animatingEntrances: Map<string, { mesh: THREE.Object3D; startTime: number; duration: number }> = new Map();
  private animatingDecays: Map<string, { mesh: THREE.Object3D; startTime: number; duration: number }> = new Map();
```

2. `public addNode(node: ClusterNodeData): void`:
   - Clones prototype mesh using `this.assetPrototypes.get(assetKey)` or `this.createFallbackMesh(node)`.
   - Sets position to `(node.spatial.x, node.spatial.y, node.spatial.z)`.
   - Sets initial scale to `(0.1, 0.1, 0.1)`.
   - Stores `userData: { nodeData: node }`.
   - Calls `this.applyDiffVisuals(instance, 'added')`.
   - Adds instance to `this.scene` and `this.nodeMeshes.set(node.id, instance)`.
   - Registers in `this.animatingEntrances.set(node.id, { mesh: instance, startTime: this.clock.getElapsedTime(), duration: 0.6 })`.
   - If `this.clusterData?.nodes`: appends node to `this.clusterData.nodes`.

3. `public removeNode(nodeId: string): void`:
   - Finds mesh by `nodeId`. If not found, return.
   - Sets material to wireframe red ghost:
     traverse mesh, for standard material set `color.setHex(0xef4444)`, `transparent = true`, `opacity = 0.45`, `depthWrite = false`, `wireframe = true`.
   - Registers in `this.animatingDecays.set(nodeId, { mesh, startTime: this.clock.getElapsedTime(), duration: 3.0 })`.
   - If `this.clusterData?.nodes`: removes node from `this.clusterData.nodes`.

4. `public modifyNode(nodeId: string, diffDetails?: string[], status?: string): void`:
   - Finds mesh by `nodeId`. If not found, return.
   - Updates `node.diffStatus = (status as any) || 'version_skew'`, `node.diffDetails = diffDetails`.
   - Calls `this.applyDiffVisuals(mesh, node.diffStatus)`.

5. In `render(delta: number, speedMultiplier: number = 1.0)`:
   - For each entrance in `this.animatingEntrances`:
     elapsed = now - entry.startTime, progress = Math.min(1.0, elapsed / entry.duration).
     scale = THREE.MathUtils.lerp(0.1, 1.0, progress).
     entry.mesh.scale.set(scale, scale, scale);
     if progress >= 1.0, delete from `animatingEntrances`.
   - For each decay in `this.animatingDecays`:
     elapsed = now - entry.startTime, progress = Math.min(1.0, elapsed / entry.duration).
     scale = THREE.MathUtils.lerp(1.0, 0.0, progress).
     entry.mesh.scale.set(scale, scale, scale);
     if progress >= 1.0:
       this.scene.remove(entry.mesh);
       this.nodeMeshes.delete(nodeId);
       delete from `animatingDecays`.

Output ONLY the code block containing these methods and updated render method inside ```typescript ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3000)
    match = re.search(r"```typescript\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "tmp/jagular_streaming_methods.ts")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Authored {out_path}")

if __name__ == "__main__":
    run()
