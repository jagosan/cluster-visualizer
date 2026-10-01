import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

system_prompt = """You are Jagular (177B Big Iron on Chunkito).
Write clean Blender 4.2 Python function using:
- `pbr(...)`
- `primitive_box(...)`
- `primitive_cyl(...)`
- `join_to(...)`
"""

user_prompt = """Implement:
def build_client_slab():
    # builds object named "Client_Slab"
    # size=(1.2, 0.8, 0.08)
    # screen on top, corner pips
    # returns joined object

Output only the Python function.
"""

code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=600)
import re
match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
if match:
    code = match.group(1)

with open("/tmp/jagular_client_slab.py", "w") as f:
    f.write(code)

print("Saved client_slab (%d bytes)" % len(code))
