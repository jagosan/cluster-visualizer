from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


DriverType = Literal["k3d", "kind", "mock"]


class OperatorConfig(BaseModel):
    enabled: bool = True
    export_interval_seconds: int = 5
    host_port: Optional[int] = None
    snapshot_port: Optional[int] = None


class ClusterSpec(BaseModel):
    name: str
    driver: DriverType = "k3d"
    kubernetes_version: str = "v1.36.4-k3s1"
    servers: int = 1
    agents: int = 2
    api_port: int = 64431
    operator: OperatorConfig = Field(default_factory=OperatorConfig)
    workloads: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    labels: Dict[str, str] = Field(default_factory=dict)


class FleetSpec(BaseModel):
    version: str = Field(default="clustervis.io/v1alpha1")
    fleet_name: str = "homelab-canary-matrix"
    host: str = "chunkito"
    network_name: Optional[str] = None
    clusters: List[ClusterSpec] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def get_cluster(self, name: str) -> Optional[ClusterSpec]:
        """Retrieve a cluster specification by name."""
        for cluster in self.clusters:
            if cluster.name == name:
                return cluster
        return None

    @classmethod
    def from_yaml_file(cls, path: str | os.PathLike) -> FleetSpec:
        """Load a FleetSpec from a YAML or JSON file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        content = path.read_text(encoding="utf-8")
        data: Dict[str, Any]

        if yaml is not None:
            try:
                data = yaml.safe_load(content)
            except yaml.YAMLError:
                # Fallback to JSON if YAML parsing fails
                data = json.loads(content)
        else:
            # If PyYAML is not available, assume JSON
            data = json.loads(content)

        if not isinstance(data, dict):
            raise ValueError(f"Expected a dictionary at the root of {path}, got {type(data).__name__}")

        return cls.model_validate(data)

    def to_yaml_file(self, path: str | os.PathLike) -> None:
        """Write the FleetSpec to a YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = self.model_dump(mode="json")

        if yaml is not None:
            with open(path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        else:
            # Fallback to JSON if PyYAML is not available
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)


class ClusterStatus(BaseModel):
    name: str
    driver: str
    status: Literal["running", "stopped", "not_found", "error", "degraded"]
    api_endpoint: str
    server_count: int = 0
    agent_count: int = 0
    operator_stream_url: Optional[str] = None
    operator_snapshot_url: Optional[str] = None
    raw_info: Dict[str, Any] = Field(default_factory=dict)


class FleetStatusReport(BaseModel):
    fleet_name: str
    host: str
    timestamp: str
    total_clusters: int
    running_clusters: int
    clusters: List[ClusterStatus] = Field(default_factory=list)


class ChaosScenario(BaseModel):
    scenario_type: Literal["rollout-restart", "node-drain", "pod-kill", "canary-weight-shift"]
    cluster: str
    target_resource: str
    namespace: str = "default"
    parameters: Dict[str, Any] = Field(default_factory=dict)
