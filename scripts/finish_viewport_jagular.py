#!/usr/bin/env python3
"""
Jagular completion for cluster_viewport.ts remaining methods.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    system_prompt = """You are Jagular (177B Big Iron on Chunkito).
Write ONLY the remaining section of `src/scene/cluster_viewport.ts` starting from finishing `hazard_stripes` in `applyDiffVisuals` and including `createFallbackMesh`, `onMouseMove`, `onClick`, `highlightSelected`, `onResize`, and `render`."""

    user_prompt = """Complete `src/scene/cluster_viewport.ts`:
Finish:
- In `applyDiffVisuals`:
  Finish the hazard stripes overlay on top face for `status === 'version_skew'`.
  mesh.add(stripeGroup);
- `private createFallbackMesh(node: ClusterNodeData): THREE.Object3D`
- `private onMouseMove(e: MouseEvent)`
- `private onClick(e: MouseEvent)`:
  - If a node is clicked:
    `const node = topObj.userData.nodeData as ClusterNodeData;`
    `this.selectedNodeId = node.id;`
    `this.highlightSelected(topObj);`
    `const worldPos = new THREE.Vector3();`
    `topObj.getWorldPosition(worldPos);`
    `this.diffCard.show(node, worldPos, this.clusterData?.metadata.cluster_name || 'Cluster');`
    `if (this.onNodeSelected) this.onNodeSelected(node);`
  - If empty space clicked:
    `this.diffCard.hide();`
- `private highlightSelected(target: THREE.Object3D | null)`
- `public onResize()`
- `public render(delta: number, speedMultiplier: number = 1.0)`:
  - Animate `pulsingMaterials` opacity with `0.4 + 0.4 * Math.sin(this.clock.getElapsedTime() * 4.0)`
  - Call `this.diffCard.updatePosition(this.camera, this.renderer);`
  - Call `this.controls.update();`
  - Call `this.flowSystem.update(delta, speedMultiplier);`
  - Call `this.renderer.render(this.scene, this.camera);`

Output ONLY the TypeScript code inside ```typescript ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=2500)
    match = re.search(r"```typescript\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    vp_path = os.path.join(REPO_ROOT, "src/scene/cluster_viewport.ts")
    with open(vp_path, "r") as f:
        content = f.read()

    idx = content.find("const stripeGroup = new THREE.Group();")
    if idx != -1:
        content = content[:idx]

    content = content.rstrip() + "\n      " + code.strip() + "\n"
    with open(vp_path, "w") as f:
        f.write(content)
    print("Successfully finished cluster_viewport.ts!")

if __name__ == "__main__":
    run()
