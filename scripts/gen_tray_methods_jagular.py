import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

system_prompt = """You are Jagular (177B Big Iron on Chunkito).
Write concise, complete TypeScript for Three.js.
"""

user_prompt = """Provide the complete `buildTowerTrays` and `clear` methods for `LayerTrayManager`:
- Spawns:
  - clientsTray: width=8.0, depth=5.0, height=0.25, color=0x88ccff, rimColor=0x44aaff, Y=12.0
  - apiGatewayTray: width=7.0, depth=4.5, height=0.35, color=0x38bdf8, rimColor=0x0284c7, Y=9.5
  - apiServerTray: width=7.0, depth=4.5, height=0.35, color=0x0284c7, rimColor=0x38bdf8, Y=7.0
  - etcdVaultTray: width=4.8, depth=3.0, height=0.30, color=0xd97706, rimColor=0xfbbf24, Y=5.5, Z=-3.5
  - supervisorTray: width=7.0, depth=4.5, height=0.35, color=0x7c3aed, rimColor=0xa78bfa, Y=4.5
  - if hasRay: rayTray: width=7.0, depth=4.5, height=0.35, color=0x9333ea, rimColor=0xc084fc, Y=2.5
  - workerTrays (i from 0 to workerCount-1): width=7.8, depth=4.8, height=0.35, color=0x059669, rimColor=0x34d399, Y = 0.5 + i * -2.8
- TowerCage:
  - width=8.5, depth=5.5, bottomY = 0.5 + (workerCount-1)*(-2.8) - 0.8, topY = 12.5, postColor = 0x334155, bracketColor = 0x1e293b, workerTierCount = workerCount
- `clear()`:
  - disposes all trays and removes from scene
  - disposes cage and removes from scene
  - resets array and cage to null

Output ONLY the TypeScript method definitions.
"""

code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=2000)
import re
match = re.search(r"```typescript\s*(.*?)\s*```", code, re.DOTALL)
if match:
    code = match.group(1)
elif "```" in code:
    code = code.split("```")[1]

with open("tmp/jagular_tray_methods.ts", "w") as f:
    f.write(code)

print("\nSaved tmp/jagular_tray_methods.ts (%d bytes)" % len(code))
