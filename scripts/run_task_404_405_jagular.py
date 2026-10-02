#!/usr/bin/env python3
"""
TASK-CV-404 & TASK-CV-405: Jagular runner for 3D Git-Diff Engine & Interactive 3D Diff Hunk Card.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    print("--- Summoning Jagular for TASK-CV-405 (src/scene/diff_card.ts) ---")
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Three.js and WebGL systems architect.
You author production-grade TypeScript for Three.js applications."""

    user_prompt_diff_card = """SPEC-03 / TASK-CV-405:
Create `src/scene/diff_card.ts` for floating 3D billboarding diff hunk cards.

Requirements:
1. Export class `DiffCardManager`:
   - Manages a floating DOM card overlay that anchors to 3D world coordinates of a selected node.
   - When a node is selected (or hovered):
     - If the node has `diffStatus === 'version_skew'` or `diffStatus === 'missing'` or `diffStatus === 'added'`:
       - Show an in-scene floating diff card showing a side-by-side YAML git-style diff.
       - Construct git-diff hunk header:
         `--- {source_cluster}/{namespace}/{name}`
         `+++ {target_cluster}/{namespace}/{name}`
         `@@ diff @@`
         `- {source_diff_lines}`
         `+ {target_diff_lines}`
       - If `diffDetails` exists on node:
         format each detail into clean colored diff lines (red '-' for old, green '+' for new).
     - Provide `updatePosition(camera: THREE.Camera, renderer: THREE.WebGLRenderer)` method:
       Project the 3D world position of the selected node to 2D screen coordinates (using `vector.project(camera)`), and translate the floating DOM card so it hovers neatly adjacent to the 3D cuboid.
     - Provide `hide()` and `show(node: ClusterNodeData, worldPos: THREE.Vector3, clusterName: string, peerClusterName?: string)` methods.
2. Styling:
   - Floating dark glass card (`background: rgba(15, 23, 42, 0.92); backdrop-filter: blur(8px); border: 1px solid #334155; border-radius: 6px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); font-family: monospace; font-size: 11px; color: #e2e8f0; pointer-events: auto; padding: 10px; max-width: 360px; z-index: 1000; position: absolute;`).
   - Clean close button [×] to dismiss.
   - Syntax-highlighted diff lines: red for `-`, green for `+`, cyan for `@@`.

Write the complete `src/scene/diff_card.ts`.
Output ONLY TypeScript code inside ```typescript ```.
"""

    code_card = call_jagular(system_prompt, user_prompt_diff_card, temperature=0.1, max_tokens=3500)
    match_card = re.search(r"```typescript\s*(.*?)\s*```", code_card, re.DOTALL)
    if match_card:
        code_card = match_card.group(1)

    out_card_path = os.path.join(REPO_ROOT, "src/scene/diff_card.ts")
    with open(out_card_path, "w") as f:
        f.write(code_card.strip() + "\n")
    print(f"Successfully authored {out_card_path}")

    # TASK-CV-404: Refactor cluster_viewport.ts
    print("\n--- Summoning Jagular for TASK-CV-404 (src/scene/cluster_viewport.ts 3D Diff Visuals) ---")
    with open(os.path.join(REPO_ROOT, "src/scene/cluster_viewport.ts"), "r") as f:
        existing_viewport = f.read()

    user_prompt_viewport = f"""SPEC-03 / TASK-CV-404 & TASK-CV-405:
Update `src/scene/cluster_viewport.ts`:

1. Import `DiffCardManager` from `./diff_card.js` (or `.ts`).
   Initialize `this.diffCard = new DiffCardManager(this.container);` in constructor.
   In the animation loop `animate()`, call `this.diffCard.updatePosition(this.camera, this.renderer);`.
   In `onNodeSelected`:
     When a node is selected, call `this.diffCard.show(...)` with the node and world position. If null, call `this.diffCard.hide()`.

2. Volumetric Shading & Hologram in `applyDiffVisuals(mesh: THREE.Object3D, status?: string)`:
   - `status === 'identical'`:
     Mesh materials get slate tone `#1e293b`, roughness 0.4, with subtle cyan contour brackets.
   - `status === 'added'`:
     - Vibrant emerald tint / emission (`#10b981`, emissive `#34d399` at 0.6).
     - Holographic corner brackets: 8 corner line brackets (or pulsing box frame) with glowing green material.
     - Store reference to animate pulsing opacity in `animate()`: `0.5 + 0.5 * Math.sin(time * 4)`.
   - `status === 'missing'`:
     - Ghost Cuboid:
       Traverse all child meshes and set material to transparent: `transparent = true`, `opacity = 0.20`, `depthWrite = false`, `color = 0x475569`.
       Add bright red dashed or wireframe contour cage (`#ef4444`, opacity 0.85).
   - `status === 'version_skew'`:
     - Metallic amber housing: `#f59e0b`, emissive `#fbbf24` (intensity 0.5).
     - Hazard stripes on top face: Add an overlay planar mesh with amber/black or amber/yellow caution stripes or pulsing hazard edge brackets.

Here is the existing `src/scene/cluster_viewport.ts`:
```typescript
{existing_viewport}
```

Write the complete updated `src/scene/cluster_viewport.ts`.
Output ONLY TypeScript code inside ```typescript ```.
"""

    code_vp = call_jagular(system_prompt, user_prompt_viewport, temperature=0.1, max_tokens=4500)
    match_vp = re.search(r"```typescript\s*(.*?)\s*```", code_vp, re.DOTALL)
    if match_vp:
        code_vp = match_vp.group(1)

    out_vp_path = os.path.join(REPO_ROOT, "src/scene/cluster_viewport.ts")
    with open(out_vp_path, "w") as f:
        f.write(code_vp.strip() + "\n")
    print(f"Successfully updated {out_vp_path}")

if __name__ == "__main__":
    run()
