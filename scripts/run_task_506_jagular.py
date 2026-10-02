#!/usr/bin/env python3
"""
TASK-CV-506: Jagular runner to author unit tests in tests/test_operator_and_stream.py.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    print("--- Summoning Jagular for TASK-CV-506 (tests/test_operator_and_stream.py) ---")
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead QA and systems test engineer.
You author comprehensive, fast, deterministic Python unittest test suites."""

    user_prompt = """SPEC-04 / TASK-CV-506:
Author `tests/test_operator_and_stream.py` verifying the in-cluster operator and offline fallbacks:

Requirements:
1. Use standard `unittest`.
2. Test CRD & Manifests:
   - Verify `deploy/crd/clustervis.io_clustertopologysnapshots.yaml` exists and contains valid YAML for `ClusterTopologySnapshot` (`clustervis.io/v1alpha1`).
   - Verify `deploy/operator/operator.yaml` exists and defines ServiceAccount, ClusterRole, Deployment, and Service.
3. Test `TopologyController`:
   - Initialize `TopologyController(cluster_name="test-cluster")`.
   - Call `get_snapshot()`: verify returned dictionary contains metadata, nodes (>=10), and edges.
   - Test event broadcasting and listener queue:
     - Register a `queue.Queue()`.
     - Inject `node_added` mutation for a test pod: verify queue receives `("node_added", payload)` with placed coordinates.
     - Inject `node_modified` mutation: verify queue receives `("node_modified", payload)`.
     - Inject `node_removed` mutation: verify queue receives `("node_removed", payload)` and node is removed.
4. Test Offline Static Fallback Integrity:
   - Load `dist/data/cluster-alpha.json` and `dist/data/cluster-beta.json`.
   - Validate them against `ClusterGraph.model_validate(json.loads(...))`.
   - Verify static mode data is 100% intact and complete.

Write the complete `tests/test_operator_and_stream.py`.
Output ONLY Python code inside ```python ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3500)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "tests/test_operator_and_stream.py")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Authored {out_path}")

if __name__ == "__main__":
    run()
