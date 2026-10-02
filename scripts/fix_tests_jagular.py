#!/usr/bin/env python3
"""
Jagular runner to author exact tests matching src.ingestion models.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    system_prompt = """You are Jagular (177B Big Iron on Chunkito).
Write ONLY python test methods for `TestClusterIngestionAndDiff` class."""

    user_prompt = """SPEC-03: Implement the 3 test methods for `TestClusterIngestionAndDiff`:
The codebase uses:
`from src.ingestion.models import NodeComponent, Spatial, ClusterGraph, ClusterMetadata, DataFlowEdge`
`from src.ingestion.layout import apply_spatial_layout, generate_skyscraper_edges, ELEVATION_TIERS`
`from src.ingestion.exporter import export_cluster`

1. `def test_spec03_horizontal_worker_deck_layout(self):`
   Create nodes:
   - 2 worker nodes:
     `NodeComponent(id="nd-1", layer="node", kind="Node", name="worker-1")`
     `NodeComponent(id="nd-2", layer="node", kind="Node", name="worker-2")`
   - Kubelets:
     `NodeComponent(id="kb-1", layer="node", kind="Kubelet", name="kubelet-1")`
     `NodeComponent(id="kb-2", layer="node", kind="Kubelet", name="kubelet-2")`
   - Containerds:
     `NodeComponent(id="ct-1", layer="node", kind="Containerd", name="containerd-1")`
     `NodeComponent(id="ct-2", layer="node", kind="Containerd", name="containerd-2")`
   - DaemonSets:
     `NodeComponent(id="ds-1", layer="control-plane", kind="DaemonSet", name="kube-proxy-1")`
     `NodeComponent(id="ds-2", layer="control-plane", kind="DaemonSet", name="cilium-1")`
   - Pods:
     `NodeComponent(id="wl-1", layer="workload", kind="Pod", name="postgres-0")`
     `NodeComponent(id="wl-2", layer="workload", kind="Pod", name="redis-0")`
   Run `laid_out = apply_spatial_layout(nodes)`:
   - by_id = {n.id: n for n in laid_out}
   - Assert both worker nodes have y == ELEVATION_TIERS["worker_deck"] (0.5).
   - Assert worker nodes are separated along X: by_id["nd-1"].spatial.x == -3.0 and by_id["nd-2"].spatial.x == 3.0.
   - Assert daemonsets have asset_type == "Cuboid_DaemonSet".
   - Assert kubelets have asset_type == "Cuboid_Kubelet" and y == 0.7, z == -1.5.
   - Assert containerds have asset_type == "Cuboid_Containerd" and y == 0.7, z == -1.5.
   - Assert pods have y == 0.75 and z in (0.2, 1.2).

2. `def test_spec03_lateral_cni_mesh_edges(self):`
   - Create 2 daemonsets:
     `NodeComponent(id="ds-1", layer="control-plane", kind="DaemonSet", name="kube-proxy-1", spatial=Spatial(asset_type="Cuboid_DaemonSet"))`
     `NodeComponent(id="ds-2", layer="control-plane", kind="DaemonSet", name="cilium-1", spatial=Spatial(asset_type="Cuboid_DaemonSet"))`
   - Run `edges = generate_skyscraper_edges([ds-1, ds-2])`
   - Assert at least one edge has `protocol == "eBPF/Mesh"`, `flow_type == "traffic"`, `direction == "bidirectional"`, and connects ds-1 and ds-2.

3. `def test_spec03_universal_cluster_exporter_mock(self):`
   - Call `graph = export_cluster(mock=True)`
   - Assert isinstance(graph, ClusterGraph)
   - Assert len(graph.nodes) >= 10
   - Assert len(graph.edges) >= 5
   - Assert any(n.spatial.asset_type == "Cuboid_DaemonSet" for n in graph.nodes)
   - Assert any(n.spatial.asset_type == "Client_Slab" for n in graph.nodes)

Output ONLY the test methods indented with 4 spaces inside ```python ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=2500)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    test_path = os.path.join(REPO_ROOT, "tests/test_ingestion_and_diff.py")
    with open(test_path, "r") as f:
        content = f.read()

    # Find the end of test_diff_engine_version_skew_classification
    marker = 'self.assertIn("Version skew: \'18.6\' vs \'17.11\'", report.nodes[0].diff_details[0])'
    idx = content.find(marker)
    if idx != -1:
        end_of_func = idx + len(marker)
        content = content[:end_of_func] + "\n\n" + code.strip() + "\n\n\nif __name__ == '__main__':\n    unittest.main()\n"
    
    with open(test_path, "w") as f:
        f.write(content)
    print("Successfully updated tests/test_ingestion_and_diff.py!")

if __name__ == "__main__":
    run()
