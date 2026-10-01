import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Three.js graphics engineer.
Write complete, modern TypeScript for Three.js (no any, strict types, verbatimModuleSyntax compatible).
"""

user_prompt = """Implement TASK-CV-303: Create `src/scene/layer_trays.ts` for cluster-vis.

SPECIFICATION:
We need a `LayerTrayManager` class that manages the 3D layered architectural trays and outer tower cage brackets in Three.js (matching the Transformer reference art):

1. `LayerTray`:
   - Represents a semi-transparent rectangular open tray at elevation Y.
   - Dimensions: width, depth, height (e.g. 7.5 x 4.5 x 0.3 for worker; 6.5 x 4.2 x 0.35 for control; 4.5 x 2.8 x 0.3 for vault).
   - Geometry:
     - Translucent floor and walls: `THREE.MeshStandardMaterial({ color, roughness: 0.2, metalness: 0.1, transparent: true, opacity: 0.35, depthWrite: false })`
     - Glowing top rim: `THREE.LineSegments` created from `THREE.EdgesGeometry` with `THREE.LineBasicMaterial({ color: rimColor, transparent: true, opacity: 0.85 })`
   - Glow ring or neon contour along the top perimeter.

2. `TowerCage`:
   - Structural outer bounding frame enclosing the tower column:
     - 4 slender vertical corner posts / lines framing the building tower from bottom worker base (Y=-5.5) up to penthouse (Y=10.0).
     - Subtle horizontal tier rings / brackets framing the worker floors.
     - Bracket line marking `Nx Worker Tiers`.

3. Methods:
   - `constructor(scene: THREE.Scene)`
   - `buildTowerTrays(workerCount: number, hasRay: boolean)`:
     - Spawns:
       - Clients horizon pad (Y=12.0)
       - API Gateway Tray (Y=9.5, cyan rim)
       - Kube-API Server Tray (Y=7.0, cyan rim)
       - etcd Vault Tray (Y=5.5, Z=-3.5, amber rim)
       - Supervisor Tray (Y=4.5, violet rim)
       - If hasRay: Ray Framework Tray (Y=2.5, electric purple rim)
       - Worker Node Trays (Y=0.5, -2.3, ... emerald rim)
     - Builds the `TowerCage` around the stack.
   - `clear()`: disposes geometries and materials cleanly.

Output ONLY the full TypeScript code for `src/scene/layer_trays.ts`.
"""

code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3000)
import re
match = re.search(r"```typescript\s*(.*?)\s*```", code, re.DOTALL)
if match:
    code = match.group(1)
elif "```" in code:
    code = code.split("```")[1]

with open("src/scene/layer_trays.ts", "w") as f:
    f.write(code)

print("\nSaved src/scene/layer_trays.ts (%d bytes)" % len(code))
