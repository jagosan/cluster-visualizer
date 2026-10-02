#!/usr/bin/env python3
"""
Jagular Realignment for TASK-CV-602 and TASK-CV-605:
Aligns recorder.py and generate_synthetic_timeline.py strictly with timeline_models.py.
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

    # 1. Align src/ingestion/recorder.py
    print("🐆 Summoning Jagular to refine src/ingestion/recorder.py...")
    user_prompt_rec = """SPEC-05 / TASK-CV-602:
Refine `src/ingestion/recorder.py` to strictly match `src/ingestion/timeline_models.py`:

The exact schema contracts in `src/ingestion/timeline_models.py` are:
```python
class TimelineEvent(BaseModel):
    timestamp: str
    event_type: Literal["pod_scheduled", "pod_evicted", "image_updated", "node_scaled", "config_drift", "custom"]
    summary: str
    affected_node_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ClusterTimelineKeyframe(BaseModel):
    timestamp: str
    snapshot_index: int
    graph: ClusterGraph
    events: List[TimelineEvent] = Field(default_factory=list)
    delta_summary: Optional[Dict[str, Any]] = None

class ClusterTimeline(BaseModel):
    schema_url: str = Field(default="https://cluster-vis.jagosan.com/schemas/cluster-timeline-v1.json", alias="$schema")
    cluster_name: str
    start_time: str
    end_time: str
    duration_seconds: float = 0.0
    keyframes: List[ClusterTimelineKeyframe] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

Ensure:
1. `detect_frame_events(prev_graph: ClusterGraph, curr_graph: ClusterGraph, timestamp: str) -> List[TimelineEvent]` sets:
   - `affected_node_ids=[key]`
   - `metadata={"namespace": ..., "kind": ..., "name": ..., ...}`
2. In `record_timeline(...)`:
   - Initialize `ClusterTimelineKeyframe(timestamp=timestamp, snapshot_index=frame_count, graph=graph, events=events)`
   - Initialize `ClusterTimeline(cluster_name=context or (graph.metadata.cluster_name if hasattr(graph, 'metadata') else "cluster-alpha"), start_time=..., end_time=..., duration_seconds=..., keyframes=keyframes)`
   - Saves to `output_path` using `timeline.to_json_file(output_path)` or `json.dump`.
   - In `--mock` mode, if successive frames need simulated changes, modify node statuses/images or spawn nodes so that timeline recording actually captures simulated changes across frames.

Write the complete `src/ingestion/recorder.py`.
Output ONLY Python code inside ```python ```.
"""
    code_rec = call_jagular(system_prompt, user_prompt_rec, temperature=0.1, max_tokens=3500)
    match_rec = re.search(r"```python\s*(.*?)\s*```", code_rec, re.DOTALL)
    if match_rec:
        code_rec = match_rec.group(1)

    out_rec_path = os.path.join(REPO_ROOT, "src", "ingestion", "recorder.py")
    with open(out_rec_path, "w") as f:
        f.write(code_rec.strip() + "\n")
    print(f"Refined {out_rec_path}")

    # 2. Complete scripts/generate_synthetic_timeline.py
    print("\n🐆 Summoning Jagular to complete scripts/generate_synthetic_timeline.py...")
    user_prompt_syn = """SPEC-05 / TASK-CV-605:
Author `scripts/generate_synthetic_timeline.py` using `ClusterGraph`, `NodeComponent`, `DataFlowEdge`, `Spatial`, `ClusterMetadata` from `src.ingestion.models`, and `ClusterTimeline`, `ClusterTimelineKeyframe`, `TimelineEvent` from `src.ingestion.timeline_models`.

Scenario:
Build 5 successive keyframes (t=0s, 15s, 30s, 45s, 60s) simulating a PostgreSQL canary rollout and autoscaling:
- Base metadata: cluster_name="cluster-alpha", kubernetes_version="v1.36.4"
- Keyframe 0 (t=0s, snapshot_index=0):
  Nodes:
  - kube-apiserver (control-plane)
  - etcd-0 (control-plane)
  - worker-1 (node)
  - worker-2 (node)
  - postgres-primary (workload, image="postgres:15.2", version="v15.2", status="Healthy", spatial=Spatial(x=2.0, y=0.5, z=0.0, asset_type="Database_Postgres"))
  - redis-cache (workload, image="redis:7.0", version="v7.0", status="Healthy", spatial=Spatial(x=4.0, y=0.5, z=0.0, asset_type="Cache_Redis"))
  Events: [TimelineEvent(timestamp="2026-10-02T14:00:00Z", event_type="custom", summary="Baseline healthy cluster state initialized")]

- Keyframe 1 (t=15s, snapshot_index=1):
  Same as Keyframe 0 + newly scheduled canary pod:
  - postgres-primary-canary (workload, image="postgres:16.1", version="v16.1", status="Pending", spatial=Spatial(x=6.0, y=0.5, z=0.0, asset_type="Database_Postgres"))
  Events: [TimelineEvent(timestamp="2026-10-02T14:00:15Z", event_type="pod_scheduled", summary="Canary pod postgres-primary-canary scheduled on worker-2", affected_node_ids=["workload/default/postgres-primary-canary"])]

- Keyframe 2 (t=30s, snapshot_index=2):
  Canary running, old postgres terminating (status="Terminating"):
  - postgres-primary (status="Terminating", version="v15.2")
  - postgres-primary-canary (status="Healthy", version="v16.1")
  Events: [TimelineEvent(timestamp="2026-10-02T14:00:30Z", event_type="image_updated", summary="Canary validated; shifting traffic to postgres:16.1", affected_node_ids=["workload/default/postgres-primary-canary"])]

- Keyframe 3 (t=45s, snapshot_index=3):
  Old postgres evicted, canary promoted to primary:
  - postgres-primary (image="postgres:16.1", version="v16.1", status="Healthy", spatial=Spatial(x=2.0, y=0.5, z=0.0, asset_type="Database_Postgres"))
  Events: [TimelineEvent(timestamp="2026-10-02T14:00:45Z", event_type="pod_evicted", summary="Old postgres-primary pod evicted from worker-1", affected_node_ids=["workload/default/postgres-primary"])]

- Keyframe 4 (t=60s, snapshot_index=4):
  Autoscaling:
  - frontend-web-scale (workload, image="nginx:1.25", status="Healthy", spatial=Spatial(x=8.0, y=0.5, z=0.0, asset_type="Cuboid_DaemonSet"))
  Events: [TimelineEvent(timestamp="2026-10-02T14:01:00Z", event_type="node_scaled", summary="Horizontal autoscaler deployed replica frontend-web-scale", affected_node_ids=["workload/default/frontend-web-scale"])]

Assemble into `ClusterTimeline(cluster_name="cluster-alpha", start_time="2026-10-02T14:00:00Z", end_time="2026-10-02T14:01:00Z", duration_seconds=60.0, keyframes=keyframes)`.
Save to `public/data/timelines/synthetic_rollout.json` and copy to `dist/data/timelines/synthetic_rollout.json` if dist exists.

Output ONLY complete Python code inside ```python ```.
"""
    code_syn = call_jagular(system_prompt, user_prompt_syn, temperature=0.1, max_tokens=3500)
    match_syn = re.search(r"```python\s*(.*?)\s*```", code_syn, re.DOTALL)
    if match_syn:
        code_syn = match_syn.group(1)

    out_syn_path = os.path.join(REPO_ROOT, "scripts", "generate_synthetic_timeline.py")
    with open(out_syn_path, "w") as f:
        f.write(code_syn.strip() + "\n")
    print(f"Refined {out_syn_path}")

if __name__ == "__main__":
    run()
