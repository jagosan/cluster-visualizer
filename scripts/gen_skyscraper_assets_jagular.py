import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import re
from jagular_agent import call_jagular

system_prompt = """You are Jagular (177B Big Iron on Chunkito), the master 3D/Python engineer for the Pantheon Swarm.
You write complete, verified Python code for Blender 4.2 bpy and bmesh.
Use existing helper functions: pbr, primitive_box, primitive_cyl, new_mesh_obj, link_into, finalize, join_to.
Do not import new modules.
"""

user_prompt = """Generate Python functions for Blender 4.2 to add 9 new Skyscraper models for `blender/build_cluster_assets.py`:

Each function must build a single named object, joined with `join_to`, centered on origin:

1. `build_skyscraper_floor_tray()` -> returns object named "Skyscraper_FloorTray"
   - Beveled rectangular floor slab: size=(3.6, 2.4, 0.28) with dark chassis material
   - Raised rim / LED border around perimeter: emission green/cyan
   - Surface grid tiles / plates on top

2. `build_skyscraper_penthouse()` -> returns object named "Skyscraper_Penthouse"
   - Roof penthouse enclosure for API aggregation: size=(2.8, 1.8, 0.6)
   - Translucent glass canopy frame / glowing central API aggregation crystal / antenna spire

3. `build_control_plane_vault()` -> returns object named "ControlPlane_Vault"
   - Heavy reinforced vault box for etcd: size=(2.0, 1.6, 1.2) in heavy metallic slate
   - Cooling fins / ribs on left and right sides
   - Reinforced vault door frame with amber status LED

4. `build_module_kubelet()` -> returns object named "Module_Kubelet"
   - Compact control terminal box: size=(0.7, 0.7, 0.45) in dark metallic
   - Small vertical transmitter antenna / cylindrical pin on top
   - Status indicator LED screen on front face

5. `build_module_containerd()` -> returns object named "Module_Containerd"
   - Runtime engine block: size=(0.8, 0.8, 0.45)
   - Socket intake ports / cylinder connectors on sides
   - Heat-sink ridges on top

6. `build_module_pod_capsule()` -> returns object named "Module_PodCapsule"
   - Pill/capsule container pod: cylinder with rounded bevels / end caps, height=0.7, radius=0.25
   - Horizontal glowing ring / band around the middle (emission orange/cyan)

7. `build_conduit_vertical_shaft()` -> returns object named "Conduit_VerticalShaft"
   - Vertical cylindrical conduit pipe: radius=0.12, depth=2.0
   - Flanged connector rings at top and bottom ends: radius=0.18, depth=0.1

8. `build_conduit_elbow()` -> returns object named "Conduit_Elbow"
   - 90-degree curved conduit elbow connector (constructed via two orthogonal short cylinder segments and a corner junction box/sphere or segment join)
   - Terminal flanges on both open ends

9. `build_client_slab()` -> returns object named "Client_Slab"
   - Floating holographic terminal pad: thin sleek slab size=(1.2, 0.8, 0.08)
   - Glowing screen / interface strip on top face (cyan/gold emission)
   - Corner antenna / sensor pips

Output ONLY the Python code containing the color constants, material creation (if new), and the 9 functions.
"""

print("[Querying Jagular for 9 Skyscraper Asset Builders...]")
code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=4096)
match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
if match:
    code = match.group(1)

with open("/tmp/jagular_skyscraper_builders.py", "w") as f:
    f.write(code)

print("Saved /tmp/jagular_skyscraper_builders.py (%d bytes)" % len(code))
