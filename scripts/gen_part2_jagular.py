import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

system_prompt = """You are Jagular (177B Big Iron on Chunkito).
Write concise, clean Python bpy builder functions for Blender 4.2.
"""

user_prompt = """Continue generating the remaining 5 builder functions for TASK-CV-301:
1. `build_cuboid_supervisor()`: beveled violet cuboid (size=(0.95, 0.65, 0.5)) with purple telemetry groove. Object name: "Cuboid_Supervisor"
2. `build_cuboid_kubelet()`: beveled emerald cuboid (size=(0.65, 0.45, 0.4)) with green heartbeat LED. Object name: "Cuboid_Kubelet"
3. `build_cuboid_containerd()`: beveled slate teal cuboid (size=(0.65, 0.45, 0.4)) with container runtime slot grooves. Object name: "Cuboid_Containerd"
4. `build_cuboid_pod()`: beveled workload cuboid (size=(0.85, 0.55, 0.45)) with workload status stripe. Object name: "Cuboid_Pod"
5. `build_cuboid_ray()`: beveled electric magenta cuboid (size=(0.95, 0.65, 0.5)) with high-throughput tensor bus channels. Object name: "Cuboid_Ray"

Assume `pbr`, `primitive_box`, `join_to`, `build_cuboid_base` are already defined.
Output ONLY the Python code for these 5 functions.
"""

code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=2500)
import re
match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
if match:
    code = match.group(1)
elif "```" in code:
    code = code.split("```")[1]

with open("tmp/jagular_spec02_part2.py", "w") as f:
    f.write(code)

print("\nSaved tmp/jagular_spec02_part2.py (%d bytes)" % len(code))
