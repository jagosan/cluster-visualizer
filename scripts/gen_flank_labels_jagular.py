import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Three.js graphics engineer.
Write complete, modern TypeScript for Three.js (no any, strict types, verbatimModuleSyntax compatible).
"""

user_prompt = """Implement TASK-CV-304: Create `src/scene/flank_labels.ts` for cluster-vis.

SPECIFICATION:
We need a `FlankLabelManager` class that creates crisp typographic billboard sprites floating on the left and right flanks of the skyscraper tower (matching the Transformer reference art):

1. Label Sprite generation:
   - Use high-resolution HTML Canvas (e.g. 512x128 or 256x64) with `CanvasTexture`.
   - Render crisp typographic badge:
     - Semi-transparent dark pill background (e.g. `rgba(15, 23, 42, 0.75)` with rounded corners and subtle border).
     - Crisp glowing text in `Inter, system-ui, sans-serif` or monospace:
       - Category accent color dot / prefix (cyan, amber, violet, emerald, purple).
       - Main text (white / high contrast, bold).
       - Optional subtitle or port (e.g. `HTTPS/6443`, `gRPC/2379`).
   - Create `THREE.Sprite` with `THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false })`.
   - Scale sprite appropriately (e.g. width ~3.2, height ~0.8).

2. Flank Positions:
   - Left flank: `x = -5.8`, right-aligned text.
   - Right flank: `x = +5.8`, left-aligned text.
   - Aligned to the Y elevations:
     - Y=12.0: "Clients (kubectl / watchers)"
     - Y=9.5:  "API Gateway / Aggregator"
     - Y=7.0:  "Kube-API Servers"
     - Y=5.5, Z=-3.5: "etcd Consensus Vault"
     - Y=4.5:  "Control Plane Supervisors"
     - Y=2.5 (if hasRay): "Ray Cluster Head"
     - Y=0.5, -2.3, ...: "Worker Floor N"
   - On right flank for extended cluster:
     - Y=4.5:  "KubeRay Operator"
     - Y=2.5:  "Plasma Shared Object Store"
     - Y=0.5:  "Raylet & GPU Workers"

3. Methods:
   - `constructor(scene: THREE.Scene)`
   - `buildLabels(workerCount: number, isExtended: boolean)`
   - `clear()`: disposes textures, materials, and removes sprites.

Output ONLY the full TypeScript code for `src/scene/flank_labels.ts`.
"""

code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3000)
import re
match = re.search(r"```typescript\s*(.*?)\s*```", code, re.DOTALL)
if match:
    code = match.group(1)
elif "```" in code:
    code = code.split("```")[1]

with open("src/scene/flank_labels.ts", "w") as f:
    f.write(code)

print("\nSaved src/scene/flank_labels.ts (%d bytes)" % len(code))
