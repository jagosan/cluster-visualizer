#!/usr/bin/env python3
"""
TASK-CV-401 & TASK-CV-402: Jagular runner for Horizontal Worker Deck Layout & Layer Trays.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    print("--- Summoning Jagular for TASK-CV-401 (src/ingestion/layout.py) ---")
    
    with open(os.path.join(REPO_ROOT, "src/ingestion/layout.py"), "r") as f:
        existing_layout = f.read()

    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead 3D systems engineer and Kubernetes visualization architect.
You write production-grade Python and TypeScript code.
Output complete, cleanly structured, fully working code."""

    user_prompt_layout = f"""TASK-CV-401: Refactor `src/ingestion/layout.py` to implement the Horizontal Node Peer Worker Deck per SPEC-03:

Key Architecture Requirements:
1. In `ELEVATION_TIERS`:
   - "client": 12.0
   - "aggregation": 9.5
   - "apiserver": 7.0
   - "vault": 5.5 (Z = -3.5)
   - "supervisor": 4.5
   - "framework": 2.5
   - "worker_deck": 0.5 (Single horizontal worker deck floor at Y = 0.5)
   - Maintain "worker_base": 0.5 for backward compatibility.
2. In `apply_spatial_layout`:
   - Categorize nodes: clients, aggregations, apiservers, etcds, schedulers, controllers, frameworks, worker_nodes, kubelets, containerds, daemonsets, and workload_pods.
   - Detect daemonsets: pods/components with "proxy", "cilium", "calico", "node-exporter", or kind "DaemonSet" or daemonset in labels/name.
   - Worker Deck Placement (Y = 0.5):
     All worker nodes sit on Tier 0 as lateral peers along X!
     N = max(len(worker_nodes), 1)
     For node chassis i in range(N):
       X_i = -((N - 1) * 6.0) / 2.0 + i * 6.0
       worker_nodes[i].spatial.x = X_i
       worker_nodes[i].spatial.y = 0.5
       worker_nodes[i].spatial.z = 0.0
       worker_nodes[i].spatial.asset_type = "LayerTray_Worker"
     
     Within each chassis i:
     - Runtime bay (Left):
       - Kubelet: X = X_i - 1.8, Y = 0.7, Z = -1.5, asset_type = "Cuboid_Kubelet"
       - Containerd: X = X_i - 0.8, Y = 0.7, Z = -1.5, asset_type = "Cuboid_Containerd"
     - DaemonSet bay (Right):
       - DaemonSets on chassis i: asset_type = "Cuboid_DaemonSet"
       - Position at X = X_i + 1.2 (or +2.0 for 2nd daemonset), Y = 0.65, Z = -1.5 (or Z = -0.5 for 3rd daemonset)
     - Workload Pod bay (Center/Front):
       - Distribute workload pods among the N worker chassis (e.g. round robin by node).
       - In chassis i, position pods in front slots at Z = 0.2 and Z = 1.2, with X staggered at X_i - 0.6 and X_i + 0.6, Y = 0.75.
       - Assign appropriate asset_type (Database_Postgres, Cache_Redis, Cuboid_Ray, Framework_Spark, Cuboid_Pod).
3. In `generate_skyscraper_edges`:
   - Route Kubelet heartbeat conduit risers from each Kubelet (X = X_i - 1.8, Y = 0.7, Z = -1.5) up to the primary API server floor (Y = 7.0).
   - Add lateral inter-node CNI conduit between CNI/daemonset pods across Node 1 and Node 2:
     flow_type = "traffic", protocol = "eBPF/Mesh", direction = "bidirectional", volume_label = "lateral CNI mesh".

Here is the existing `src/ingestion/layout.py` for reference:
```python
{existing_layout}
```

Write the complete updated `src/ingestion/layout.py`.
Output ONLY the full Python code inside ```python ```.
"""

    code = call_jagular(system_prompt, user_prompt_layout, temperature=0.1, max_tokens=4000)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)
    
    out_path = os.path.join(REPO_ROOT, "src/ingestion/layout.py")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Successfully updated {out_path}")

    # TASK-CV-402
    print("\n--- Summoning Jagular for TASK-CV-402 (src/scene/layer_trays.ts) ---")
    with open(os.path.join(REPO_ROOT, "src/scene/layer_trays.ts"), "r") as f:
        existing_trays = f.read()

    user_prompt_trays = f"""TASK-CV-402: Update `src/scene/layer_trays.ts` to implement the Wide Worker Deck Tray per SPEC-03:

Requirements:
1. In `buildTowerTrays(workerCount: number, hasRay: boolean)`:
   - Worker Deck (Tier 0 at Y = 0.5):
     Replace the loop of vertical worker trays with a SINGLE wide Worker Deck tray:
     const actualWorkers = Math.max(workerCount, 1);
     const deckWidth = 10.0 + (actualWorkers - 1) * 6.0;
     const deckDepth = 6.5;
     const deckHeight = 0.35;
     createTray(deckWidth, deckDepth, deckHeight, 0x047857, 0x34d399, 0.5, 0.0);
   - In addition, create individual sub-tray beveled chassis plates/outlines on top of the wide deck for each worker node chassis i at:
     X_i = -((actualWorkers - 1) * 6.0) / 2.0 + i * 6.0
     Chassis dimensions: width 5.2, depth 4.8, height 0.08, at position (X_i, 0.5 + 0.35/2 + 0.04, 0.0) with subtle dark emerald base (0x064e3b) and cyan/emerald rim (0x10b981).
2. Update `buildTowerCage` to adjust the outer structural tower cage around the skyscraper so that the base accommodates the wide worker deck cleanly.

Here is the existing `src/scene/layer_trays.ts`:
```typescript
{existing_trays}
```

Write the complete updated `src/scene/layer_trays.ts`.
Output ONLY the full TypeScript code inside ```typescript ```.
"""

    code_ts = call_jagular(system_prompt, user_prompt_trays, temperature=0.1, max_tokens=4000)
    match_ts = re.search(r"```typescript\s*(.*?)\s*```", code_ts, re.DOTALL)
    if match_ts:
        code_ts = match_ts.group(1)

    out_ts_path = os.path.join(REPO_ROOT, "src/scene/layer_trays.ts")
    with open(out_ts_path, "w") as f:
        f.write(code_ts.strip() + "\n")
    print(f"Successfully updated {out_ts_path}")

if __name__ == "__main__":
    run()
