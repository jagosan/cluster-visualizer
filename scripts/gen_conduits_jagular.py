import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Three.js graphics engineer.
Write complete, modern TypeScript for Three.js (no any, strict types).
"""

user_prompt = """Implement TASK-CV-203: Create `src/scene/conduits.ts` for cluster-vis.

SPECIFICATION:
We need a `ConduitManager` class that generates 3D tubular pipe meshes between components in the skyscraper:
- Takes `THREE.Scene` and list of edges with their source and target positions/types.
- Generates 3D rigid/curved conduit paths using `THREE.CurvePath<THREE.Vector3>` or `THREE.CatmullRomCurve3` / `THREE.CubicBezierCurve3`.
- Creates `THREE.TubeGeometry(path, 40, radius, 12, false)`.
  - Radii: 0.06 for standard pipes, 0.09 for main riser / storage conduits.
- Materials:
  - Transparent emissive glass/metallic tubing:
    `new THREE.MeshStandardMaterial({ color, roughness: 0.2, metalness: 0.8, transparent: true, opacity: 0.45, emissive: color, emissiveIntensity: 0.2 })`
- Route types:
  1. Heartbeat Riser (`kubelet` -> `apiserver`):
     - (src.x, src.y, src.z) -> (src.x - 0.6, src.y, src.z) -> (src.x - 0.6, tgt.y, tgt.z) -> (tgt.x, tgt.y, tgt.z)
  2. etcd Backing Conduits (`apiserver` -> `etcd`):
     - Drops backward from API server down to etcd vault behind it.
  3. Client Stream (`client` -> `penthouse` / `apiserver`):
     - Sweeping arch from distant high slab down into the penthouse canopy.
  4. Inter-API server horizontal bridge:
     - Straight horizontal connector pipe.
  5. Framework bypass:
     - Lateral connector between framework nodes.
- Exposes `getConduitCurves()` returning the curves so that `FlowParticleSystem` can animate pulses along the exact pipes.
- Exposes `dispose()` / `clear()`.

Output ONLY the full TypeScript code for `src/scene/conduits.ts`.
"""

code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3000)
import re
match = re.search(r"```typescript\s*(.*?)\s*```", code, re.DOTALL)
if match:
    code = match.group(1)
elif "```" in code:
    code = code.split("```")[1]

with open("src/scene/conduits.ts", "w") as f:
    f.write(code)

print("Saved src/scene/conduits.ts (%d bytes)" % len(code))
