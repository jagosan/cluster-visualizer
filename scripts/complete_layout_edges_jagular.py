#!/usr/bin/env python3
"""
Jagular completion for generate_skyscraper_edges conforming to models.py Pydantic schema
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    system_prompt = """You are Jagular (177B Big Iron on Chunkito).
Write ONLY the complete Python function `generate_skyscraper_edges(nodes: List[NodeComponent]) -> List[DataFlowEdge]:`."""

    user_prompt = """SPEC-03: Implement `generate_skyscraper_edges(nodes: List[NodeComponent]) -> List[DataFlowEdge]:`

CRITICAL SCHEMA RULES (Pydantic models.py):
- `flow_type` MUST BE ONE OF: "traffic", "framework_control", "data_replication", "control_plane".
  Do NOT use "sync", "consensus", "heartbeat", "tensor", "control" as flow_type.
- Asset types in nodes:
  clients = [n for n in nodes if n.spatial.asset_type == "Client_Slab"]
  penthouse = [n for n in nodes if n.spatial.asset_type in ("LayerTray_Control", "Skyscraper_Penthouse")]
  apiservers = [n for n in nodes if "apiserver" in n.name.lower() or n.kind.lower() == "apiserver"]
  etcds = [n for n in nodes if "etcd" in n.name.lower() or n.kind.lower() == "etcd"]
  supervisors = [n for n in nodes if "scheduler" in n.name.lower() or "controller" in n.name.lower()]
  kubelets = [n for n in nodes if n.spatial.asset_type in ("Cuboid_Kubelet", "Module_Kubelet")]
  daemonsets = [n for n in nodes if n.spatial.asset_type == "Cuboid_DaemonSet"]
  ray_heads = [n for n in nodes if "head" in n.name.lower() and "ray" in n.name.lower()]
  ray_workers = [n for n in nodes if "head" not in n.name.lower() and "ray" in n.name.lower()]

Edge Definitions:
1. Client -> Ingress / API Server:
   flow_type="traffic", protocol="HTTPS/443", direction="unidirectional", volume_label="list pods"
2. Penthouse / Aggregator -> API Server Core:
   flow_type="traffic", protocol="HTTPS/6443", direction="unidirectional"
3. Inter-API Server Sync Conduits:
   flow_type="control_plane", protocol="HTTPS/6443", direction="bidirectional", volume_label="peer sync"
4. API Server <-> etcd Vault:
   flow_type="control_plane", protocol="gRPC/2379", direction="bidirectional", volume_label="raft KV"
5. Supervisors <-> API Server:
   flow_type="control_plane", protocol="HTTPS/6443", direction="bidirectional", volume_label="reconcile loop"
6. Kubelet -> API Server:
   flow_type="control_plane", protocol="HTTPS/6443/Heartbeat", direction="unidirectional", volume_label="lease heartbeat"
7. Ray Head <-> Ray Workers:
   flow_type="framework_control", protocol="gRPC/10001", direction="bidirectional", volume_label="tensor bypass"
8. Lateral CNI Mesh between adjacent daemonsets:
   flow_type="traffic", protocol="eBPF/Mesh", direction="bidirectional", volume_label="lateral CNI mesh"

Output ONLY the function inside ```python ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=2000)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    layout_path = os.path.join(REPO_ROOT, "src/ingestion/layout.py")
    with open(layout_path, "r") as f:
        content = f.read()

    idx = content.find("def generate_skyscraper_edges")
    if idx != -1:
        content = content[:idx]

    content = content.rstrip() + "\n\n\n" + code.strip() + "\n"
    with open(layout_path, "w") as f:
        f.write(content)
    print("Updated layout.py with schema-valid generate_skyscraper_edges!")

if __name__ == "__main__":
    run()
