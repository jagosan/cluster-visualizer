#!/usr/bin/env python3
"""
TASK-CV-403: Jagular runner to add Cuboid_DaemonSet to blender/build_cluster_assets.py and rebuild GLB.
"""

import os
import sys
import subprocess
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BPY_PYTHON = "/home/jagosan/.hermes/toolchains/bpy_env/bin/python"

def run():
    print("--- Summoning Jagular for TASK-CV-403 (Cuboid_DaemonSet in Blender) ---")
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead 3D systems engineer and Blender bpy expert.
Write clean Blender 4.2 Python code with bmesh and PBR materials."""

    user_prompt = """SPEC-03 / TASK-CV-403:
Implement `build_cuboid_daemonset()` for `blender/build_cluster_assets.py`.
Requirements:
- Object Name: "Cuboid_DaemonSet"
- Visual representation:
  - Low-profile sleek chamfered chassis (size=(0.70, 0.45, 0.30) or similar compact rectangular footprint).
  - PBR material for body: dark charcoal/slate metallic chassis (e.g. base_color=(0.14, 0.16, 0.18, 1.0), metallic=0.7, roughness=0.3).
  - Accent / Status indicator: Emissive cyan/teal LED bar or dual ring ports representing network routing / eBPF activity (base_color=(0.10, 0.85, 0.80, 1.0), emission_color=(0.10, 0.85, 0.80, 1.0), emission_strength=4.0).
- Uses helpers available in build_cluster_assets.py:
  - `pbr(name, base_color, metallic=0.0, roughness=0.5, emission_color=None, emission_strength=0.0)`
  - `primitive_box(name, mat, size=(1,1,1), loc=(0,0,0))`
  - `join_to(target, others)`
- Returns the root `Cuboid_DaemonSet` mesh object.

Output ONLY the Python function `build_cuboid_daemonset():` inside ```python ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=1500)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    assets_script = os.path.join(REPO_ROOT, "blender/build_cluster_assets.py")
    with open(assets_script, "r") as f:
        content = f.read()

    # Insert build_cuboid_daemonset before reset_scene
    if "def build_cuboid_daemonset" not in content:
        insert_marker = "def reset_scene():"
        idx = content.find(insert_marker)
        if idx != -1:
            content = content[:idx] + code.strip() + "\n\n\n" + content[idx:]

    # Add build_cuboid_daemonset to builders list in main()
    if "build_cuboid_daemonset," not in content and "build_cuboid_daemonset" not in content[content.find("builders = ["):]:
        content = content.replace(
            "build_cuboid_pod, build_cuboid_ray\n    ]",
            "build_cuboid_pod, build_cuboid_ray, build_cuboid_daemonset\n    ]"
        )

    # Add Cuboid_DaemonSet to required list in main()
    if '"Cuboid_DaemonSet"' not in content:
        content = content.replace(
            '"Cuboid_Kubelet", "Cuboid_Containerd", "Cuboid_Pod", "Cuboid_Ray"',
            '"Cuboid_Kubelet", "Cuboid_Containerd", "Cuboid_Pod", "Cuboid_Ray", "Cuboid_DaemonSet"'
        )

    with open(assets_script, "w") as f:
        f.write(content)
    print("Updated blender/build_cluster_assets.py successfully!")

    # Run blender build
    print("Running headless Blender build script...")
    res = subprocess.run([BPY_PYTHON, assets_script], capture_output=True, text=True)
    print("Blender stdout:\n", res.stdout)
    if res.returncode != 0:
        print("Blender stderr:\n", res.stderr)
        raise RuntimeError(f"Blender export failed with return code {res.returncode}")
    print("Successfully built cluster-kit.glb with Cuboid_DaemonSet!")

if __name__ == "__main__":
    run()
