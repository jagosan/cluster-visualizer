#!/usr/bin/env python3
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Python systems architect.
You author clean, robust, type-annotated production code conforming strictly to Pydantic v2 and Python stdlib."""

    user_prompt = """Author complete `src/ingestion/timeline_models.py`:

Imports:
from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator
from .models import ClusterGraph, ClusterMetadata, NodeComponent, DataFlowEdge

TimelineEventType = Literal[
    "pod_scheduled",
    "pod_evicted",
    "image_updated",
    "node_scaled",
    "config_drift",
    "custom",
]

class TimelineEvent(BaseModel):
    timestamp: str
    event_type: TimelineEventType
    summary: str
    affected_node_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ClusterTimelineKeyframe(BaseModel):
    timestamp: str = ""
    snapshot_index: int = 0
    time_offset_seconds: Optional[float] = None
    graph: Optional[ClusterGraph] = None
    nodes: Optional[List[NodeComponent]] = None
    edges: Optional[List[DataFlowEdge]] = None
    events: List[TimelineEvent] = Field(default_factory=list)
    delta_summary: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def sync_graph_and_nodes(self) -> ClusterTimelineKeyframe:
        if not self.timestamp:
            sec = self.time_offset_seconds or 0.0
            self.timestamp = f"2026-10-02T14:00:{int(sec):02d}Z"
        if self.graph is None and self.nodes is not None:
            self.graph = ClusterGraph(
                metadata=ClusterMetadata(
                    cluster_name="cluster-alpha",
                    kubernetes_version="v1.36.4",
                    timestamp=self.timestamp,
                    node_count=len([n for n in self.nodes if n.kind == "WorkerNode"]),
                    pod_count=len([n for n in self.nodes if n.layer == "workload"]),
                ),
                nodes=self.nodes,
                edges=self.edges or []
            )
        elif self.graph is not None and self.nodes is None:
            self.nodes = self.graph.nodes
            self.edges = self.graph.edges
        return self

class ClusterTimeline(BaseModel):
    schema_url: str = Field(
        default="https://cluster-vis.jagosan.com/schemas/cluster-timeline-v1.json",
        alias="$schema",
    )
    cluster_name: str
    start_time: str
    end_time: str
    duration_seconds: float = 0.0
    keyframes: List[ClusterTimelineKeyframe] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    def add_keyframe(self, keyframe: ClusterTimelineKeyframe) -> None:
        self.keyframes.append(keyframe)
        self.end_time = keyframe.timestamp
        try:
            start_dt = datetime.fromisoformat(self.start_time.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(self.end_time.replace("Z", "+00:00"))
            self.duration_seconds = (end_dt - start_dt).total_seconds()
        except Exception:
            self.duration_seconds = 0.0

    def to_json_file(self, path: str | os.PathLike) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2, by_alias=True))

    @classmethod
    def from_json_file(cls, path: str | os.PathLike) -> ClusterTimeline:
        with open(path, "r", encoding="utf-8") as f:
            data = f.read()
        return cls.model_validate_json(data)

Output ONLY Python code inside ```python ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3000)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        out_path = os.path.join(REPO_ROOT, "src", "ingestion", "timeline_models.py")
        with open(out_path, "w") as f:
            f.write(match.group(1).strip() + "\n")
        print(f"Updated {out_path}")

if __name__ == "__main__":
    run()
