#!/usr/bin/env python3
"""
TASK-CV-502: Jagular modular runner for Topology Informer Controller.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    print("--- Summoning Jagular for TASK-CV-502 (Modular src/operator/controller.py) ---")
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead systems and Kubernetes architect.
You author concise, modular, production-grade Python adhering strictly to existing project modules."""

    user_prompt = """SPEC-04 / TASK-CV-502:
Author `src/operator/controller.py`: The in-cluster Kubernetes topology informer controller.

CRITICAL INSTRUCTION:
DO NOT redefine Pydantic models or layout algorithms inline!
Use the existing implementations by importing them:
```python
import json
import queue
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.ingestion.models import ClusterGraph, ClusterMetadata, DataFlowEdge, NodeComponent, Spatial
from src.ingestion.layout import apply_spatial_layout, generate_skyscraper_edges
from src.ingestion.frameworks import enrich_framework_components
from src.ingestion.exporter import generate_mock_cluster_graph, scrub_sensitive_string
```

Requirements for `TopologyController`:
1. `__init__(self, cluster_name: str = "in-cluster")`:
   - `self.cluster_name = cluster_name`
   - `self.nodes: Dict[str, NodeComponent] = {}`
   - `self.edges: List[DataFlowEdge] = []`
   - `self.listeners: List[queue.Queue] = []`
   - `self.lock = threading.Lock()`
   - `self.running = False`
   - `self.worker_thread: Optional[threading.Thread] = None`

2. Listener management:
   - `add_listener(self, q: queue.Queue)`: with lock, appends q.
   - `remove_listener(self, q: queue.Queue)`: with lock, safely removes q.
   - `broadcast_event(self, event_name: str, payload: dict)`:
     with lock, iterates listeners and puts `(event_name, payload)` into each queue. Catches queue.Full or BrokenPipe.

3. Snapshot generation:
   - `get_snapshot(self) -> dict`:
     with lock:
       if not self.nodes:
         self._seed_mock_data()
       meta = ClusterMetadata(
         cluster_name=self.cluster_name,
         kubernetes_version="v1.36.4",
         distribution="in-cluster",
         timestamp=datetime.now(timezone.utc).isoformat(),
         node_count=len([n for n in self.nodes.values() if n.kind == "Node"]),
         pod_count=len([n for n in self.nodes.values() if n.kind == "Pod"]),
       )
       graph = ClusterGraph(metadata=meta, nodes=list(self.nodes.values()), edges=list(self.edges))
       graph = enrich_framework_components(graph)
       graph = apply_spatial_layout(graph)
       graph = generate_skyscraper_edges(graph)
       # Update self.edges with generated edges so graph stays synchronized
       self.edges = graph.edges
       return graph.model_dump()

4. Real-time Mutation Injection:
   - `inject_mutation(self, event_name: str, payload: dict)`:
     with lock:
       ts = datetime.now(timezone.utc).isoformat()
       if event_name == "node_added":
         node_data = payload.get("node")
         node = NodeComponent(**node_data) if isinstance(node_data, dict) else node_data
         self.nodes[node.id] = node
         # Re-layout
         g = ClusterGraph(
           metadata=ClusterMetadata(cluster_name=self.cluster_name, timestamp=ts, node_count=len(self.nodes)),
           nodes=list(self.nodes.values())
         )
         g = apply_spatial_layout(g)
         g = generate_skyscraper_edges(g)
         self.edges = g.edges
         placed_node = next(n for n in g.nodes if n.id == node.id)
         self.broadcast_event("node_added", {"node": placed_node.model_dump(), "timestamp": ts})
       elif event_name == "node_removed":
         nid = payload.get("node_id")
         if nid in self.nodes:
           del self.nodes[nid]
           self.edges = [e for e in self.edges if e.source != nid and e.target != nid]
         self.broadcast_event("node_removed", {"node_id": nid, "timestamp": ts})
       elif event_name == "node_modified":
         nid = payload.get("node_id")
         if nid in self.nodes:
           node = self.nodes[nid]
           if "status" in payload:
             node.status = payload["status"]
         self.broadcast_event("node_modified", payload)
       elif event_name == "edge_updated":
         self.broadcast_event("edge_updated", payload)

5. Seeding & Loop (`start(mock: bool = False, poll_interval: float = 10.0)` and `stop()`):
   - `_seed_mock_data(self)`:
     Calls `generate_mock_cluster_graph()`, populates `self.nodes = {n.id: n for n in g.nodes}`, `self.edges = g.edges`.
   - `_run_mock_loop(self, interval: float)`:
     Loop while self.running:
       time.sleep(interval)
       if not self.running: break
       # Alternate between adding demo worker pod, modifying status to version_skew, and removing
       # using inject_mutation
   - `_run_real_loop(self, interval: float)`:
     Loop while self.running:
       time.sleep(interval)
   - `start(...)`: starts background worker thread for mock or real loop.
   - `stop()`: sets running=False, joins thread.

Keep the module concise, elegant, clean, and under 180 lines.
Write the complete `src/operator/controller.py`.
Output ONLY Python code inside ```python ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3000)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    os.makedirs(os.path.join(REPO_ROOT, "src/operator"), exist_ok=True)
    out_path = os.path.join(REPO_ROOT, "src/operator/controller.py")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Authored {out_path}")

if __name__ == "__main__":
    run()
