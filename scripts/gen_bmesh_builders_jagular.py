import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

system_prompt = """You are Jagular (177B Big Iron on Chunkito), the master 3D/Python engineer for the Pantheon Swarm.
Write clean Blender 4.2 Python functions that use:
- `pbr(name, base_color, metallic=0.0, roughness=0.5, emission_color=None, emission_strength=0.0)`
- `primitive_box(name, mat, size=(x, y, z), loc=(x, y, z))`
- `primitive_cyl(name, mat, radius, depth, loc=(x, y, z), vertices=32)`
- `join_to(target, others)`
Do NOT use bpy.ops.mesh.*. All mesh primitives must use the existing primitive_box and primitive_cyl helpers.
Each function returns a single joined Object centered at (0, 0, 0).
"""

user_prompt = """Implement these 9 asset builder functions for `blender/build_cluster_assets.py`:

Palette colors to declare:
COL_SKYSCRAPER_TRAY = (0.12, 0.14, 0.17, 1.0)
COL_SKYSCRAPER_RIM = (0.05, 0.85, 0.95, 1.0) # cyan LED
COL_PENTHOUSE = (0.15, 0.25, 0.45, 0.8)     # glass canopy
COL_PENTHOUSE_CORE = (0.95, 0.80, 0.20, 1.0) # golden aggregation core
COL_VAULT = (0.20, 0.22, 0.25, 1.0)         # etcd heavy slate
COL_VAULT_ACCENT = (1.0, 0.60, 0.10, 1.0)   # etcd amber raft LED
COL_KUBELET = (0.15, 0.40, 0.35, 1.0)       # kubelet teal
COL_CONTAINERD = (0.30, 0.32, 0.35, 1.0)    # containerd steel
COL_POD_CAPSULE = (0.95, 0.55, 0.15, 1.0)   # pod orange
COL_CONDUIT_PIPE = (0.10, 0.75, 0.85, 1.0)  # conduit glass cyan
COL_CLIENT_PAD = (0.08, 0.10, 0.14, 1.0)    # dark client console
COL_CLIENT_GLOW = (0.30, 0.70, 1.0, 1.0)    # client holographic glow

Functions to implement:
1. `build_skyscraper_floor_tray()`:
   Base tray = primitive_box("Skyscraper_FloorTray", tray_mat, size=(3.6, 2.4, 0.28), loc=(0,0,0))
   Perimeter LED rims on front/back/left/right using rim_mat (emission cyan).
   Plating ridges on top.
   join_to(tray, rims + ridges)

2. `build_skyscraper_penthouse()`:
   Base enclosure = primitive_box("Skyscraper_Penthouse", glass_mat, size=(2.8, 1.8, 0.55), loc=(0,0,0))
   Central API aggregation crystal/core = primitive_box("penthouse_core", core_mat, size=(0.8, 0.8, 0.7), loc=(0,0,0.1))
   Four glass corner pillar columns = primitive_cyl(...)
   join_to(base, [core] + pillars)

3. `build_control_plane_vault()`:
   Base vault = primitive_box("ControlPlane_Vault", vault_mat, size=(2.2, 1.6, 1.2), loc=(0,0,0))
   Side cooling ribs = 6 fins along left and right sides.
   Front amber status LED strip.
   join_to(vault, ribs + [led])

4. `build_module_kubelet()`:
   Box = primitive_box("Module_Kubelet", kubelet_mat, size=(0.65, 0.65, 0.45), loc=(0,0,0))
   Antenna pin = primitive_cyl("kubelet_antenna", ant_mat, radius=0.03, depth=0.35, loc=(0.2, 0.2, 0.4))
   Front status screen = primitive_box("kubelet_screen", screen_mat, size=(0.4, 0.04, 0.25), loc=(0, -0.33, 0.05))
   join_to(box, [antenna, screen])

5. `build_module_containerd()`:
   Box = primitive_box("Module_Containerd", containerd_mat, size=(0.75, 0.75, 0.45), loc=(0,0,0))
   Side socket ports = 2 cylinders on left and right sides.
   Top heat sink fins.
   join_to(box, ports + fins)

6. `build_module_pod_capsule()`:
   Cylinder body = primitive_cyl("Module_PodCapsule", pod_mat, radius=0.25, depth=0.7, loc=(0,0,0))
   Glowing mid-ring = primitive_cyl("pod_ring", ring_mat, radius=0.27, depth=0.12, loc=(0,0,0))
   Top cap = primitive_cyl("pod_top_cap", cap_mat, radius=0.23, depth=0.08, loc=(0,0,0.38))
   Bottom cap = primitive_cyl("pod_bot_cap", cap_mat, radius=0.23, depth=0.08, loc=(0,0,-0.38))
   join_to(body, [ring, top_cap, bot_cap])

7. `build_conduit_vertical_shaft()`:
   Pipe = primitive_cyl("Conduit_VerticalShaft", pipe_mat, radius=0.12, depth=2.0, loc=(0,0,0))
   Flange top = primitive_cyl("conduit_flange_top", flange_mat, radius=0.18, depth=0.10, loc=(0,0,0.95))
   Flange bot = primitive_cyl("conduit_flange_bot", flange_mat, radius=0.18, depth=0.10, loc=(0,0,-0.95))
   join_to(pipe, [flange_top, flange_bot])

8. `build_conduit_elbow()`:
   Vertical limb = primitive_cyl("Conduit_Elbow", pipe_mat, radius=0.12, depth=0.5, loc=(0,0,0.25))
   Corner block/sphere = primitive_box("conduit_corner", pipe_mat, size=(0.28, 0.28, 0.28), loc=(0,0,0.5))
   Horizontal limb = primitive_box("conduit_h", pipe_mat, size=(0.5, 0.24, 0.24), loc=(0.25, 0, 0.5))
   join_to(vertical, [corner, horizontal])

9. `build_client_slab()`:
   Pad = primitive_box("Client_Slab", pad_mat, size=(1.2, 0.8, 0.08), loc=(0,0,0))
   Screen strip = primitive_box("client_screen", screen_mat, size=(1.0, 0.6, 0.03), loc=(0, 0, 0.05))
   Corner sensor pips = 4 small pins at corners.
   join_to(pad, [screen] + pips)

Return valid Python code defining the colors and the 9 functions.
"""

print("[Querying Jagular for precise bmesh skyscraper builders...]")
code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3000)
import re
match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
if match:
    code = match.group(1)

with open("/tmp/jagular_bmesh_builders.py", "w") as f:
    f.write(code)

print("Saved /tmp/jagular_bmesh_builders.py (%d bytes)" % len(code))
