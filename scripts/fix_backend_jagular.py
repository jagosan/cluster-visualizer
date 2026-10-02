#!/usr/bin/env python3
"""
Targeted Jagular generator for:
1. src/ingestion/recorder.py
2. scripts/generate_synthetic_timeline.py
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Python systems architect.
You author concise, complete, robust production code conforming strictly to Pydantic v2 and Python stdlib.
Never truncate code."""

    # 1. src/ingestion/recorder.py
    print("🐆 Jagular: Generating complete src/ingestion/recorder.py...")
    user_prompt_rec = """SPEC-05 / TASK-CV-602:
Author complete `src/ingestion/recorder.py`.
It must import:
```python
import argparse
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.ingestion.models import ClusterGraph, ClusterMetadata, NodeComponent, Spatial
from src.ingestion.timeline_models import (
    ClusterTimeline,
    ClusterTimelineKeyframe,
    TimelineEvent,
    TimelineEventType,
)
from src.ingestion.exporter import export_live_cluster, generate_mock_cluster_graph
```

Functions:
1. `compute_topology_hash(graph: ClusterGraph) -> str`:
   Creates sha256 hex digest of sorted tuple representation: `[(n.namespace, n.kind, n.name, n.version, n.image, n.status) for n in graph.nodes]`.

2. `detect_frame_events(prev_graph: ClusterGraph, curr_graph: ClusterGraph, timestamp: str) -> List[TimelineEvent]`:
   Compares nodes between prev_graph and curr_graph by key `f"{n.namespace}/{n.kind}/{n.name}"`:
   - Added: `TimelineEvent(timestamp=timestamp, event_type="pod_scheduled", summary=f"Scheduled {node.name}", affected_node_ids=[node.id], metadata={"kind": node.kind, "namespace": node.namespace, "image": node.image})`
   - Removed: `TimelineEvent(timestamp=timestamp, event_type="pod_evicted", summary=f"Evicted {node.name}", affected_node_ids=[node.id], metadata={"kind": node.kind, "namespace": node.namespace})`
   - Image/Version changed: `TimelineEvent(timestamp=timestamp, event_type="image_updated", summary=f"Updated {curr.name} image to {curr.image}", affected_node_ids=[curr.id], metadata={"old_image": prev.image, "new_image": curr.image})`
   - Status changed: `TimelineEvent(timestamp=timestamp, event_type="config_drift", summary=f"Status of {curr.name} changed to {curr.status}", affected_node_ids=[curr.id], metadata={"status": curr.status})`
   Returns events list.

3. `record_timeline(context: Optional[str] = None, interval_seconds: float = 5.0, duration_seconds: float = 30.0, output_path: str = "public/data/timelines/cluster-timeline.json", mock: bool = False, max_frames: Optional[int] = None) -> ClusterTimeline`:
   - Runs sampling loop for duration_seconds.
   - In mock mode: uses `generate_mock_cluster_graph()`. For successive frames in mock mode, randomly mutate or add a simulated node so events are produced.
   - In live mode: uses `export_live_cluster(context=context)`.
   - Computes hash. On first frame or hash change, creates `ClusterTimelineKeyframe(timestamp=timestamp, snapshot_index=len(keyframes), graph=graph, events=events)`.
   - Assembles `ClusterTimeline(cluster_name=context or "cluster-alpha", start_time=..., end_time=..., duration_seconds=..., keyframes=keyframes)`.
   - Calls `timeline.to_json_file(output_path)`.
   - Returns timeline.

4. `parse_duration(val: str) -> float`: Parses '10s', '5m', '1h' or float.
5. `main()` with argparse for `--context`, `--interval`, `--duration`, `--output`, `--mock`.

Output ONLY Python code inside ```python ```.
"""
    code_rec = call_jagular(system_prompt, user_prompt_rec, temperature=0.1, max_tokens=4000)
    match_rec = re.search(r"```python\s*(.*?)\s*```", code_rec, re.DOTALL)
    if match_rec:
        code_rec = match_rec.group(1)

    out_rec_path = os.path.join(REPO_ROOT, "src", "ingestion", "recorder.py")
    with open(out_rec_path, "w") as f:
        f.write(code_rec.strip() + "\n")
    print(f"Authored {out_rec_path}")

    # 2. scripts/generate_synthetic_timeline.py
    print("\n🐆 Jagular: Generating complete scripts/generate_synthetic_timeline.py...")
    user_prompt_syn = """SPEC-05 / TASK-CV-605:
Author complete, self-contained `scripts/generate_synthetic_timeline.py`.
Imports:
```python
import os
import shutil
from pathlib import Path
from src.ingestion.models import ClusterGraph, ClusterMetadata, NodeComponent, Spatial, DataFlowEdge
from src.ingestion.timeline_models import ClusterTimeline, ClusterTimelineKeyframe, TimelineEvent
```

Requirements:
Create 5 sequential keyframes:
Helper to create NodeComponent:
`def make_node(nid, layer, kind, name, version, image, status, x, y, z, asset_type): return NodeComponent(id=nid, layer=layer, kind=kind, name=name, version=version, image=image, status=status, spatial=Spatial(x=x, y=y, z=z, asset_type=asset_type))`

Base common nodes:
- `kube-apiserver` (control-plane, APIServer, x=0, y=2.5, z=-2, asset_type="Cuboid_APIServer")
- `etcd-0` (control-plane, etcd, x=0, y=1.5, z=-3, asset_type="Cuboid_etcd")
- `worker-1` (node, WorkerNode, x=-3, y=0.5, z=0, asset_type="LayerTray_WorkerDeck")
- `worker-2` (node, WorkerNode, x=3, y=0.5, z=0, asset_type="LayerTray_WorkerDeck")
- `redis-cache` (workload, Cache, version="v7.0", image="redis:7.0", x=4, y=0.5, z=0, asset_type="Cache_Redis")

Keyframe 0 (t=0s, snapshot_index=0):
- Postgres: `postgres-primary` (workload, version="v15.2", image="postgres:15.2", status="Healthy", x=-2, y=0.5, z=0, asset_type="Database_Postgres")
- Events: `[TimelineEvent(timestamp="2026-10-02T14:00:00Z", event_type="custom", summary="Baseline healthy cluster state initialized")]`

Keyframe 1 (t=15s, snapshot_index=1):
- Same as KF0 + canary pod `postgres-primary-canary` (workload, version="v16.1", image="postgres:16.1", status="Pending", x=2, y=0.5, z=0, asset_type="Database_Postgres")
- Events: `[TimelineEvent(timestamp="2026-10-02T14:00:15Z", event_type="pod_scheduled", summary="Canary pod postgres-primary-canary scheduled on worker-2", affected_node_ids=["workload/default/postgres-primary-canary"])]`

Keyframe 2 (t=30s, snapshot_index=2):
- `postgres-primary` status="Terminating", version="v15.2", image="postgres:15.2", x=-2, y=0.5, z=0
- `postgres-primary-canary` status="Healthy", version="v16.1", image="postgres:16.1", x=2, y=0.5, z=0
- Events: `[TimelineEvent(timestamp="2026-10-02T14:00:30Z", event_type="image_updated", summary="Canary validated; shifting traffic to postgres:16.1", affected_node_ids=["workload/default/postgres-primary-canary"])]`

Keyframe 3 (t=45s, snapshot_index=3):
- Old postgres evicted!
- `postgres-primary` is promoted canary: version="v16.1", image="postgres:16.1", status="Healthy", x=-2, y=0.5, z=0, asset_type="Database_Postgres"
- Events: `[TimelineEvent(timestamp="2026-10-02T14:00:45Z", event_type="pod_evicted", summary="Old postgres-primary pod evicted from worker-1", affected_node_ids=["workload/default/postgres-primary"])]`

Keyframe 4 (t=60s, snapshot_index=4):
- Same as KF3 + new replica `frontend-web-scale` (workload, version="v1.25", image="nginx:1.25", status="Healthy", x=6, y=0.5, z=0, asset_type="Cuboid_DaemonSet")
- Events: `[TimelineEvent(timestamp="2026-10-02T14:01:00Z", event_type="node_scaled", summary="Horizontal autoscaler deployed replica frontend-web-scale", affected_node_ids=["workload/default/frontend-web-scale"])]`

Build `ClusterTimeline(cluster_name="cluster-alpha", start_time="2026-10-02T14:00:00Z", end_time="2026-10-02T14:01:00Z", duration_seconds=60.0, keyframes=keyframes)`.
Save to `public/data/timelines/synthetic_rollout.json` using `timeline.to_json_file(out_path)`.
If `dist/data/timelines/` exists, copy there too.
Print confirmation message with keyframe count and file path.

Output ONLY Python code inside ```python ```.
"""
    code_syn = call_jagular(system_prompt, user_prompt_syn, temperature=0.1, max_tokens=4000)
    match_syn = re.search(r"```python\s*(.*?)\s*```", code_syn, re.DOTALL)
    if match_syn:
        code_syn = match_syn.group(1)

    out_syn_path = os.path.join(REPO_ROOT, "scripts", "generate_synthetic_timeline.py")
    with open(out_syn_path, "w") as f:
        f.write(code_syn.strip() + "\n")
    print(f"Authored {out_syn_path}")

if __name__ == "__main__":
    run()
