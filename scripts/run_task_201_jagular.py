import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import re
from jagular_agent import call_jagular

system_prompt = """You are Jagular (177B Big Iron on Chunkito), the master 3D/Python engineer for the Pantheon Swarm.
You write complete, verified, robust Python code using Blender 4.2 bpy and bmesh.
Always include all necessary imports, materials, bmesh creation, transformations, and clean up.
Follow headless rules: sys.stdout.flush(), sys.stderr.flush(), and os._exit(0) in finally block.
"""

user_prompt = """Implement TASK-CV-201: Update `blender/build_cluster_assets.py` for cluster-vis.

SPECIFICATION:
We are transitioning cluster-vis to a stylized skyscraper / layered apartment-building architecture.
We need procedural 3D models with clean PBR materials exported to `public/assets/cluster-kit.glb`.

Keep all 8 existing models so existing views don't break:
1. NodeTray
2. ControlPlane_Cube
3. Pod_Cylinder
4. Framework_Ray
5. Framework_Spark
6. Database_Postgres
7. Cache_Redis
8. Conduit_Link

AND add the 9 new Skyscraper models required by SPEC-01:
9. Skyscraper_FloorTray: Sleek beveled rectangular node platform (e.g. size=(3.6, 2.4, 0.35)) with LED perimeter edge rim and metallic floor plating.
10. Skyscraper_Penthouse: Glass/canopy penthouse enclosure for API aggregation (e.g. glass/canopy frame, glowing core terminal).
11. ControlPlane_Vault: Heavy reinforced metallic vault box with cooling ribs/fins for etcd backing store (metallic charcoal/slate, cooling ribs along sides).
12. Module_Kubelet: Compact control terminal box with vertical antenna / transmitter nub.
13. Module_Containerd: Precision container runtime housing with socket ports / heat sink ridges.
14. Module_PodCapsule: Sleek capsule pod unit with workload status glow band.
15. Conduit_VerticalShaft: Vertical cylindrical conduit pipe riser section with connector flanges at ends.
16. Conduit_Elbow: 90-degree curved conduit elbow connector.
17. Client_Slab: Floating minimalist terminal pad / slab representing remote client tooling (kubectl, browser) with glowing interface strip.

Make sure:
- All materials use Blender 4.2 Principled BSDF inputs: "Base Color", "Metallic", "Roughness", "Emission Color", "Emission Strength".
- Use `bmesh.ops.create_cone` for cylinders (`radius1 == radius2`).
- Each asset function (`build_...`) returns a single named Object centered at (0,0,0) with mesh geometry joined via `join_to`.
- `main()` registers all 17 required object names in `required = [...]`, selects them, and exports to `OUT_GLB`.
- Headless script exits cleanly with `sys.stdout.flush()`, `sys.stderr.flush()`, `os._exit(rc)`.

Output ONLY the full, complete Python code for `blender/build_cluster_assets.py` inside a ```python ... ``` code block.
"""

print("[dispatching to Jagular 177B on Chunkito...]")
ans = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=8192)

match = re.search(r"```python\s*(.*?)\s*```", ans, re.DOTALL)
if match:
    code = match.group(1)
else:
    code = ans

with open("blender/build_cluster_assets.py", "w") as f:
    f.write(code)

print("[Jagular generated blender/build_cluster_assets.py successfully!]")
