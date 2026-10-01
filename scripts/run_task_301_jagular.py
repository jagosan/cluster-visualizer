import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead 3D systems engineer and Blender bpy expert.
You write production-grade Python bpy asset generation code for Blender 4.2 using bmesh and Principled BSDF.
Always include error handling, proper naming, vertex counts, and clean geometry.
"""

user_prompt = """Implement TASK-CV-301 for cluster-vis:
We need procedural 3D model builder functions for Blender 4.2 adhering to SPEC-02 (Transformer architecture visual aesthetic):
1. Clean rectangular open trays with thin walls and floor:
   - `build_layer_tray_control()`: open rectangular glass tray (width=6.5, depth=4.2, height=0.4, wall=0.08) with cyan glowing top rim. Object name: "LayerTray_Control"
   - `build_layer_tray_worker()`: open rectangular glass tray (width=7.5, depth=4.5, height=0.4, wall=0.08) with emerald glowing top rim. Object name: "LayerTray_Worker"
   - `build_layer_tray_vault()`: open rectangular glass tray (width=4.5, depth=2.8, height=0.35, wall=0.08) with amber glowing top rim. Object name: "LayerTray_Vault"
2. Clean chamfered / beveled rectangular cuboids (NO spheres, NO cylinders):
   - `build_cuboid_apiserver()`: beveled metallic cuboid (size=(1.1, 0.7, 0.6)) with cyan emissive status bar and dual socket ports. Object name: "Cuboid_APIServer"
   - `build_cuboid_etcd()`: beveled dark slate cuboid (size=(0.9, 0.7, 0.55)) with glowing amber Raft status lens. Object name: "Cuboid_etcd"
   - `build_cuboid_supervisor()`: beveled violet cuboid (size=(0.95, 0.65, 0.5)) with purple telemetry groove. Object name: "Cuboid_Supervisor"
   - `build_cuboid_kubelet()`: beveled emerald cuboid (size=(0.65, 0.45, 0.4)) with green heartbeat LED. Object name: "Cuboid_Kubelet"
   - `build_cuboid_containerd()`: beveled slate teal cuboid (size=(0.65, 0.45, 0.4)) with container runtime slot grooves. Object name: "Cuboid_Containerd"
   - `build_cuboid_pod()`: beveled workload cuboid (size=(0.85, 0.55, 0.45)) with workload status stripe. Object name: "Cuboid_Pod"
   - `build_cuboid_ray()`: beveled electric magenta cuboid (size=(0.95, 0.65, 0.5)) with high-throughput tensor bus channels. Object name: "Cuboid_Ray"

Helper functions available in `build_cluster_assets.py`:
- `pbr(name, base_color, metallic=0.0, roughness=0.5, emission_color=None, emission_strength=0.0)`
- `primitive_box(name, mat, size=(1,1,1), loc=(0,0,0))`
- `primitive_cyl(name, mat, radius=0.5, depth=1.0, loc=(0,0,0), rot=(0,0,0))`
- `join_to(target, others)`

Write Python functions with these exact names and signatures.
Output ONLY the Python code containing these builder functions.
"""

code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3500)
import re
match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
if match:
    code = match.group(1)
elif "```" in code:
    code = code.split("```")[1]

with open("tmp/jagular_spec02_builders.py", "w") as f:
    f.write(code)

print("\nSaved tmp/jagular_spec02_builders.py (%d bytes)" % len(code))
