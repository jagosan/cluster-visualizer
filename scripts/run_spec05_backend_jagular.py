#!/usr/bin/env python3
"""
Jagular Swarm Delegator for SPEC-05 Backend:
- TASK-CV-601: src/ingestion/timeline_models.py
- TASK-CV-602: src/ingestion/recorder.py
- TASK-CV-605: scripts/generate_synthetic_timeline.py
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Python systems architect.
You author clean, robust, type-annotated production code conforming strictly to Pydantic v2 and Python stdlib."""

    # -------------------------------------------------------------
    # TASK-CV-601: src/ingestion/timeline_models.py
    # -------------------------------------------------------------
    print("\n=======================================================")
    print("🐆 Summoning Jagular for TASK-CV-601 (src/ingestion/timeline_models.py)")
    print("=======================================================")

    user_prompt_models = """SPEC-05 / TASK-CV-601:
Author `src/ingestion/timeline_models.py`: Pydantic models for cluster time-travel timeline and delta tracking.

Requirements:
1. Imports:
   from __future__ import annotations
   from typing import Any, Dict, List, Literal, Optional
   from pydantic import BaseModel, Field
   from .models import ClusterGraph

2. Define `TimelineEventType`:
   Literal["pod_scheduled", "pod_evicted", "image_updated", "node_scaled", "config_drift", "custom"]

3. Define `TimelineEvent(BaseModel)`:
   - `timestamp: str`: ISO 8601 UTC timestamp.
   - `event_type: TimelineEventType`
   - `summary: str`
   - `affected_node_ids: List[str] = Field(default_factory=list)`
   - `metadata: Dict[str, Any] = Field(default_factory=dict)`

4. Define `ClusterTimelineKeyframe(BaseModel)`:
   - `timestamp: str`
   - `snapshot_index: int`
   - `graph: ClusterGraph`
   - `events: List[TimelineEvent] = Field(default_factory=list)`
   - `delta_summary: Optional[Dict[str, Any]] = None`

5. Define `ClusterTimeline(BaseModel)`:
   - `schema_url: str = Field(default="https://cluster-vis.jagosan.com/schemas/cluster-timeline-v1.json", alias="$schema")`
   - `cluster_name: str`
   - `start_time: str`
   - `end_time: str`
   - `duration_seconds: float = 0.0`
   - `keyframes: List[ClusterTimelineKeyframe] = Field(default_factory=list)`
   - `metadata: Dict[str, Any] = Field(default_factory=dict)`

   Class Config:
       populate_by_name = True

   Provide helper methods on `ClusterTimeline`:
   - `add_keyframe(self, keyframe: ClusterTimelineKeyframe) -> None`: Appends keyframe and updates `end_time` and `duration_seconds` (computing delta between start_time and end_time).
   - `to_json_file(self, path: str | os.PathLike) -> None`: Saves indented JSON.
   - `from_json_file(cls, path: str | os.PathLike) -> ClusterTimeline`: Loads from JSON file.

Output ONLY Python code inside ```python ```.
"""

    code_models = call_jagular(system_prompt, user_prompt_models, temperature=0.1, max_tokens=3500)
    match_m = re.search(r"```python\s*(.*?)\s*```", code_models, re.DOTALL)
    if match_m:
        code_models = match_m.group(1)

    out_models_path = os.path.join(REPO_ROOT, "src", "ingestion", "timeline_models.py")
    with open(out_models_path, "w") as f:
        f.write(code_models.strip() + "\n")
    print(f"\n Authored {out_models_path}")

    # -------------------------------------------------------------
    # TASK-CV-602: src/ingestion/recorder.py
    # -------------------------------------------------------------
    print("\n=======================================================")
    print("🐆 Summoning Jagular for TASK-CV-602 (src/ingestion/recorder.py)")
    print("=======================================================")

    user_prompt_recorder = """SPEC-05 / TASK-CV-602:
Author `src/ingestion/recorder.py`: Time-travel cluster topology recorder CLI.

Requirements:
1. Functions:
   - `compute_topology_hash(graph: ClusterGraph) -> str`:
     Hashes sorted list of node IDs, versions, images, and statuses using hashlib.sha256 to detect structural state changes.
   - `detect_frame_events(prev_graph: ClusterGraph, curr_graph: ClusterGraph, timestamp: str) -> List[TimelineEvent]`:
     Compares node components by ID / composite key (namespace/kind/name):
     - Added nodes -> `event_type="pod_scheduled"`, summary="Component {kind} {name} scheduled"
     - Removed nodes -> `event_type="pod_evicted"`, summary="Component {kind} {name} evicted/removed"
     - Changed image or version -> `event_type="image_updated"`, summary="Updated {name} image from {prev_image} to {curr_image}"
     - Changed status -> `event_type="config_drift"`, summary="Component {name} status changed to {status}"
     Returns list of `TimelineEvent`.
   - `record_timeline(...)`:
     Supports capturing live cluster or mock samples.
     Parameters:
       - `context: Optional[str] = None`
       - `interval_seconds: float = 5.0`
       - `duration_seconds: float = 30.0`
       - `output_path: str = "public/data/timelines/cluster-timeline.json"`
       - `mock: bool = False`
       - `max_frames: Optional[int] = None`
     Captures frames at intervals until duration is reached, deduplicating identical frames if hash unchanged (or logging no-op), recording events, and packaging into `ClusterTimeline`.
   - `main()` CLI:
     argparse:
       --context: Kubernetes context (e.g. kind-cluster-alpha)
       --interval: sampling interval (default '5s' or float)
       --duration: recording duration (default '30s')
       --output: output json file path
       --mock: flag to record simulated changes without live k8s cluster
     Can be invoked via `python3 -m src.ingestion.recorder`.

Imports to use:
from src.ingestion.models import ClusterGraph, NodeComponent
from src.ingestion.timeline_models import ClusterTimeline, ClusterTimelineKeyframe, TimelineEvent
from src.ingestion.exporter import export_live_cluster, generate_mock_cluster_graph

Output ONLY Python code inside ```python ```.
"""

    code_recorder = call_jagular(system_prompt, user_prompt_recorder, temperature=0.1, max_tokens=4000)
    match_r = re.search(r"```python\s*(.*?)\s*```", code_recorder, re.DOTALL)
    if match_r:
        code_recorder = match_r.group(1)

    out_recorder_path = os.path.join(REPO_ROOT, "src", "ingestion", "recorder.py")
    with open(out_recorder_path, "w") as f:
        f.write(code_recorder.strip() + "\n")
    print(f"\n Authored {out_recorder_path}")

    # -------------------------------------------------------------
    # TASK-CV-605: scripts/generate_synthetic_timeline.py
    # -------------------------------------------------------------
    print("\n=======================================================")
    print("🐆 Summoning Jagular for TASK-CV-605 (scripts/generate_synthetic_timeline.py)")
    print("=======================================================")

    user_prompt_synthetic = """SPEC-05 / TASK-CV-605:
Author `scripts/generate_synthetic_timeline.py`: Script to generate a realistic multi-keyframe testbed timeline.

Scenario to simulate across 5 keyframes (e.g. t = 0s, 15s, 30s, 45s, 60s):
1. Keyframe 0 (t=0s):
   Baseline healthy cluster state:
   - Worker deck: 2 worker nodes (node-1, node-2).
   - Control plane: kube-apiserver, etcd.
   - Workloads: `postgres-primary` running `postgres:15.2` on node-1, `redis-cache` running `redis:7.0` on node-1, `frontend-web` running `nginx:1.24` on node-2.
   - Events: `[TimelineEvent(timestamp=..., event_type="custom", summary="Baseline healthy cluster initialized")]`.

2. Keyframe 1 (t=15s):
   Deployment rollout begins:
   - New canary pod `postgres-primary-canary` scheduled on node-2 with image `postgres:16.1` and version `v16.1.0`.
   - Spatial coordinates calculated cleanly (e.g. node-2 bay).
   - Events: `[TimelineEvent(timestamp=..., event_type="pod_scheduled", summary="Canary pod postgres-primary-canary scheduled on node-2", affected_node_ids=["workload/default/postgres-primary-canary"])]`.

3. Keyframe 2 (t=30s):
   Canary testing & Config Drift:
   - `postgres-primary` marked with status="Terminating", version="v15.2.0".
   - `postgres-primary-canary` promoted to status="Ready", traffic flow edges updated.
   - Events: `[TimelineEvent(timestamp=..., event_type="image_updated", summary="Database canary validation passed; cutover initiated", affected_node_ids=["workload/default/postgres-primary-canary"])]`.

4. Keyframe 3 (t=45s):
   Old pod evicted & node scaling:
   - Old `postgres-primary` is completely removed (evicted).
   - `postgres-primary-canary` renamed / confirmed as `postgres-primary` (image `postgres:16.1`).
   - Events: `[TimelineEvent(timestamp=..., event_type="pod_evicted", summary="Old postgres-primary pod terminated and evicted", affected_node_ids=["workload/default/postgres-primary"])]`.

5. Keyframe 4 (t=60s):
   Autoscaling scale-up:
   - New worker node `worker-node-3` added, or new replica `frontend-web-2` scheduled on node-2.
   - Events: `[TimelineEvent(timestamp=..., event_type="node_scaled", summary="Horizontal pod autoscaler scaled frontend-web to 2 replicas", affected_node_ids=["workload/default/frontend-web-2"])]`.

Script behavior:
- Builds `ClusterTimeline` with these 5 keyframes.
- Writes to `public/data/timelines/synthetic_rollout.json` and copies to `dist/data/timelines/synthetic_rollout.json` if dist exists.
- Pretty-prints summary statistics (duration, keyframe count, events count).

Output ONLY Python code inside ```python ```.
"""

    code_synthetic = call_jagular(system_prompt, user_prompt_synthetic, temperature=0.1, max_tokens=4000)
    match_s = re.search(r"```python\s*(.*?)\s*```", code_synthetic, re.DOTALL)
    if match_s:
        code_synthetic = match_s.group(1)

    out_synthetic_path = os.path.join(REPO_ROOT, "scripts", "generate_synthetic_timeline.py")
    with open(out_synthetic_path, "w") as f:
        f.write(code_synthetic.strip() + "\n")
    print(f"\n Authored {out_synthetic_path}")

if __name__ == "__main__":
    run()
