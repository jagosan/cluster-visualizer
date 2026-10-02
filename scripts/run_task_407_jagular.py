#!/usr/bin/env python3
"""
Jagular runner to add unit tests for SPEC-03 in tests/test_ingestion_and_diff.py
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    print("--- Summoning Jagular for TASK-CV-407 (tests/test_ingestion_and_diff.py) ---")
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead QA engineer and test architect.
Write clean, robust unittest test methods in Python."""

    user_prompt = """SPEC-03 / TASK-CV-407:
Write new test methods for `tests/test_ingestion_and_diff.py`:
1. `test_horizontal_worker_deck_layout(self)`:
   - Test that when 2 worker nodes (`node-1`, `node-2`) and their components (kubelet, containerd, kube-proxy daemonsets, pods) are laid out:
     - Both worker nodes have `spatial.y == 0.5`.
     - Worker nodes are separated along X (X_0 = -3.0, X_1 = +3.0).
     - DaemonSets get `asset_type == "Cuboid_DaemonSet"`.
     - Kubelets and Containerds sit on their respective node chassis at Y ~ 0.7, Z = -1.5.
     - Workload pods sit on their respective node chassis at Y ~ 0.75, Z >= 0.2.
2. `test_lateral_cni_mesh_edges(self)`:
   - Test that when multiple daemonsets exist across nodes, `generate_skyscraper_edges` produces a lateral CNI mesh edge:
     - `protocol == "eBPF/Mesh"`
     - `flow_type == "traffic"`
     - `direction == "bidirectional"`
3. `test_universal_cluster_exporter_mock(self)`:
   - Call `export_cluster(mock=True)` from `src.ingestion.exporter`.
   - Verify it returns a `ClusterGraph` with valid metadata, nodes >= 10, edges >= 5.
   - Verify presence of `Client_Slab`, `Cuboid_APIServer`, `Cuboid_DaemonSet`.

Output ONLY the Python test methods to be added to `TestClusterIngestionAndDiff` inside ```python ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=2500)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    test_path = os.path.join(REPO_ROOT, "tests/test_ingestion_and_diff.py")
    with open(test_path, "r") as f:
        content = f.read()

    # Add import of export_cluster if not present
    if "from src.ingestion.exporter import export_cluster" not in content:
        content = "from src.ingestion.exporter import export_cluster\n" + content

    idx = content.rfind("if __name__ == '__main__':")
    if idx == -1:
        idx = content.rfind('if __name__ == "__main__":')

    if idx != -1:
        content = content[:idx].rstrip() + "\n\n" + code.strip() + "\n\n\n" + content[idx:]
    else:
        content = content.rstrip() + "\n\n" + code.strip() + "\n"

    with open(test_path, "w") as f:
        f.write(content)
    print("Successfully added new unit tests!")

if __name__ == "__main__":
    run()
