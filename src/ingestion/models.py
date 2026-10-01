"""Pydantic data models for Cluster Visualizer (ClusterGraph Schema v1)."""

from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class Spatial(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    asset_type: str = "cube_control_plane"


class NodeComponent(BaseModel):
    id: str
    layer: Literal["control-plane", "framework", "workload", "node", "ingress"]
    kind: str
    name: str
    namespace: str = "default"
    version: str = "unknown"
    image: Optional[str] = None
    digest: Optional[str] = None
    status: str = "Healthy"
    metrics: Dict[str, Any] = Field(default_factory=dict)
    spatial: Spatial = Field(default_factory=Spatial)
    raw_labels: Dict[str, str] = Field(default_factory=dict)


class DataFlowEdge(BaseModel):
    source: str
    target: str
    flow_type: Literal["traffic", "framework_control", "data_replication", "control_plane"]
    protocol: str = "TCP"
    direction: Literal["unidirectional", "bidirectional"] = "unidirectional"
    animated: bool = True
    volume_label: Optional[str] = None


class ClusterMetadata(BaseModel):
    cluster_name: str
    kubernetes_version: str
    distribution: str = "kind"
    timestamp: str
    node_count: int = 1
    pod_count: int = 0


class DiffSummary(BaseModel):
    identical_nodes: int = 0
    version_skew_nodes: int = 0
    missing_in_target: int = 0
    added_in_target: int = 0


class NodeMatch(BaseModel):
    node_id: str
    status: Literal["identical", "version_skew", "added", "missing"]
    source_version: Optional[str] = None
    target_version: Optional[str] = None
    source_image: Optional[str] = None
    target_image: Optional[str] = None
    source_digest: Optional[str] = None
    target_digest: Optional[str] = None
    diff_details: List[str] = Field(default_factory=list)


class EdgeMatch(BaseModel):
    source: str
    target: str
    flow_type: str
    status: Literal["identical", "added", "missing"]


class DiffReport(BaseModel):
    source_cluster: str
    target_cluster: str
    summary: DiffSummary
    nodes: List[NodeMatch] = Field(default_factory=list)
    edges: List[EdgeMatch] = Field(default_factory=list)


class ClusterGraph(BaseModel):
    schema_url: str = Field(
        default="https://cluster-vis.jagosan.com/schemas/cluster-graph-v1.json",
        alias="$schema"
    )
    metadata: ClusterMetadata
    nodes: List[NodeComponent] = Field(default_factory=list)
    edges: List[DataFlowEdge] = Field(default_factory=list)
    diff_summary: Optional[DiffSummary] = None

    class Config:
        populate_by_name = True
