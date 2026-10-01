import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

system_prompt = """You are Jagular (177B Big Iron on Chunkito).
Write clean Blender 4.2 Python functions using:
- `pbr(name, base_color, metallic=0.0, roughness=0.5, emission_color=None, emission_strength=0.0)`
- `primitive_box(name, mat, size=(x, y, z), loc=(x, y, z))`
- `primitive_cyl(name, mat, radius, depth, loc=(x, y, z), vertices=32)`
- `join_to(target, others)`
"""

user_prompt = """Implement these 4 functions:
6. `build_module_pod_capsule()` -> "Module_PodCapsule"
7. `build_conduit_vertical_shaft()` -> "Conduit_VerticalShaft"
8. `build_conduit_elbow()` -> "Conduit_Elbow"
9. `build_client_slab()` -> "Client_Slab"

Output only the Python code.
"""

code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=2000)
import re
match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
if match:
    code = match.group(1)

with open("/tmp/jagular_bmesh_builders_part2.py", "w") as f:
    f.write(code)

print("Saved part 2 (%d bytes)" % len(code))
