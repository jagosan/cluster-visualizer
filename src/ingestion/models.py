"""Pydantic data models for Cluster Visualizer (ClusterGraph Schema v1)."""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
try:
    from pydantic import BaseModel, Field
except ImportError:
    import copy
    import json

    class _FieldInfo:
        def __init__(self, default=None, default_factory=None, alias=None, **kwargs):
            self.default = default
            self.default_factory = default_factory
            self.alias = alias

    def Field(default=None, *, default_factory=None, alias=None, **kwargs):
        return _FieldInfo(default=default, default_factory=default_factory, alias=alias)

    class BaseModel:
        def __init__(self, **kwargs):
            cls = self.__class__
            annotations = {}
            for base in reversed(cls.__mro__):
                annotations.update(getattr(base, "__annotations__", {}))
            alias_map = {}
            for k in list(annotations.keys()) + [a for a in dir(cls) if not a.startswith("_")]:
                v = getattr(cls, k, None)
                if isinstance(v, _FieldInfo) and v.alias:
                    alias_map[v.alias] = k
            mapped = {}
            for k, v in kwargs.items():
                mapped[alias_map.get(k, k)] = v
            for k in annotations:
                val = getattr(cls, k, None)
                if k in mapped:
                    setattr(self, k, self._coerce_field(k, mapped.pop(k), annotations.get(k)))
                elif isinstance(val, _FieldInfo):
                    if val.default_factory is not None:
                        setattr(self, k, val.default_factory())
                    else:
                        setattr(self, k, copy.deepcopy(val.default))
                elif hasattr(cls, k):
                    setattr(self, k, copy.deepcopy(val))
                else:
                    setattr(self, k, None)
            for k, v in mapped.items():
                setattr(self, k, v)

        def _coerce_field(self, name, value, ann):
            if value is None:
                return None
            ann_str = str(ann)
            for g_cls in globals().values():
                if isinstance(g_cls, type) and issubclass(g_cls, Enum) and g_cls is not Enum:
                    if g_cls.__name__ in ann_str and not isinstance(value, g_cls):
                        return g_cls(value)
                if isinstance(g_cls, type) and issubclass(g_cls, BaseModel) and g_cls is not BaseModel:
                    if g_cls.__name__ in ann_str:
                        if isinstance(value, dict):
                            return g_cls(**value)
                        elif isinstance(value, list):
                            return [g_cls(**x) if isinstance(x, dict) else x for x in value]
            return value

        def __eq__(self, other):
            if not isinstance(other, self.__class__):
                return False
            return self.model_dump() == other.model_dump()

        def model_dump(self, by_alias=False, mode=None, **kwargs):
            cls = self.__class__
            def _conv(v):
                if isinstance(v, BaseModel):
                    return v.model_dump(by_alias=by_alias, mode=mode)
                if isinstance(v, Enum):
                    return v.value
                if isinstance(v, list):
                    return [_conv(x) for x in v]
                if isinstance(v, dict):
                    return {k: _conv(val) for k, val in v.items()}
                return v
            out = {}
            for k, v in self.__dict__.items():
                key = k
                if by_alias:
                    f = getattr(cls, k, None)
                    if isinstance(f, _FieldInfo) and f.alias:
                        key = f.alias
                out[key] = _conv(v)
            return out

        def model_dump_json(self, indent=None, by_alias=False, **kwargs):
            return json.dumps(self.model_dump(by_alias=by_alias), indent=indent)

        @classmethod
        def model_validate(cls, data):
            if isinstance(data, cls):
                return data
            return cls(**data)

        @classmethod
        def model_validate_json(cls, text):
            return cls.model_validate(json.loads(text))



class CloudProvider(str, Enum):
    """Vendor taxonomy for managed infrastructure (SPEC-08 ADR-01)."""

    GCP = "gcp"
    AWS = "aws"
    AZURE = "azure"
    GENERIC = "generic"


class ManagedServiceCategory(str, Enum):
    """Vendor-agnostic managed-service taxonomy (SPEC-08 ADR-01)."""

    DATABASE_RELATIONAL = "database_relational"   # CloudSQL, Spanner <-> RDS, Aurora
    DATABASE_NOSQL = "database_nosql"             # Firestore, Bigtable <-> DynamoDB
    OBJECT_STORAGE = "object_storage"             # GCS <-> S3
    MESSAGING_EVENTING = "messaging_eventing"     # Pub/Sub <-> SQS, SNS, Kinesis
    CACHE_IN_MEMORY = "cache_in_memory"           # Memorystore <-> ElastiCache
    SECURITY_SECRET = "security_secret"           # Secret Manager <-> SecretsManager
    NETWORKING_GATEWAY = "networking_gateway"     # Cloud NAT, Interconnect <-> NAT GW


class Spatial(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    asset_type: str = "cube_control_plane"


class AutoscalingStatus(BaseModel):
    """Autoscaling metadata for VPA and HPA tracking (SPEC-09 §6)."""

    has_vpa: bool = False
    vpa_target_cpu: Optional[str] = None
    vpa_target_memory: Optional[str] = None
    is_resizing_in_place: bool = False

    has_hpa: bool = False
    current_replicas: int = 1
    desired_replicas: int = 1
    target_metric: Optional[str] = None


class KueueWorkloadStatus(BaseModel):
    """Atomic gang workload tracking under Kueue (SPEC-09 §6)."""

    workload_uid: str
    workload_name: str
    namespace: str = "default"
    local_queue: str
    cluster_queue: str
    is_admitted: bool = False
    admission_checks: List[Dict[str, str]] = Field(default_factory=list)
    pod_uids: List[str] = Field(default_factory=list)
    total_cpu_requested: float = 0.0
    total_memory_gib_requested: float = 0.0
    total_gpu_requested: int = 0
    phase: Literal["Inadmissible", "Admissible", "Admitted", "Finished"] = "Admissible"


class KarpenterNodeClaim(BaseModel):
    """Karpenter NodeClaim provisioning a ghost chassis (SPEC-09 §4.2).

    A claim links a batch of pending pods (PodScheduled=False) to a
    holographic wireframe ghost-node chassis on Sub-Level B1 (Y = -2.5)
    while cloud compute is being provisioned; the staging yard renders the
    amber tractor beam from the pending pods down onto the ghost footprint.
    """

    claim_name: str
    namespace: str = "default"
    nodepool: str = "default"
    instance_type: Optional[str] = None
    capacity_type: Literal["spot", "on-demand"] = "on-demand"
    requested_cpu_cores: float = 0.0
    requested_memory_gib: float = 0.0
    requested_gpu_count: int = 0
    pending_pod_uids: List[str] = Field(default_factory=list)
    is_provisioned: bool = False   # NodeReady=True -> chassis solidifies
    created_at: Optional[str] = None


class PodGeometrySpec(BaseModel):
    """Proportional capsule dimensions and staging assignments (SPEC-09 §6)."""

    height: float = 0.6
    radius: float = 0.3
    color_tint: str = "#4FC3F7"
    is_pending: bool = False
    staging_track_x: Optional[float] = None
    karpenter_target_node_claim: Optional[str] = None
    # SPEC-09 §5.2 (ADR-03): workload_uid of the Kueue Workload whose cargo
    # pallet encloses this pod, when gang-packed on the staging-track rail.
    kueue_workload: Optional[str] = None


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
    # SPEC-09: proportional pod capsule dimensions + autoscaling metadata
    pod_geometry: Optional[PodGeometrySpec] = None
    autoscaling: Optional[AutoscalingStatus] = None


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


class RemoteServiceResource(BaseModel):
    """Vendor-agnostic managed cloud service vault (SPEC-08 §3).

    Concrete CRD watchers (KCC / kro / ACK / Crossplane) normalize native
    external-infra CRDs into this unified representation; the scene layer
    depends exclusively on ``ManagedServiceCategory``.
    """

    id: str
    provider: CloudProvider = CloudProvider.GCP
    category: ManagedServiceCategory
    cr_group: str
    cr_kind: str
    name: str
    namespace: str = "default"
    display_name: str
    status_phase: str = "Ready"                 # Ready, Reconciling, Degraded, Failed
    endpoint: Optional[str] = None
    vpc_network: Optional[str] = None
    managed_by: str = "kcc"                     # kcc, kro, ack, crossplane
    kro_parent_id: Optional[str] = None
    spatial: Optional[Dict[str, float]] = None


class MachineShape(BaseModel):
    """Physical machine / Karpenter compute-class chassis (SPEC-08 §3).

    Placed on Sub-Level B1 (``compute_chassis``); chassis footprint is
    proportional to vCPU cores x RAM GiB via
    ``layout.calculate_chassis_dimensions``.
    """

    node_name: str
    provider: CloudProvider = CloudProvider.GCP
    instance_type: str
    compute_class: Optional[str] = None         # GKE Compute Class / Karpenter NodePool
    vcpus: int = 4
    memory_gib: float = 16.0
    capacity_type: Literal["spot", "on-demand"] = "on-demand"
    zone: str = "us-central1-a"
    accelerator_type: Optional[str] = None      # nvidia-l4, tpu-v5e, etc.
    accelerator_count: int = 0
    chassis_width: float = 3.9
    chassis_depth: float = 3.6


class ClusterGraph(BaseModel):
    schema_url: str = Field(
        default="https://example.com/schemas/cluster-graph-v1.json",
        alias="$schema"
    )
    metadata: ClusterMetadata
    nodes: List[NodeComponent] = Field(default_factory=list)
    edges: List[DataFlowEdge] = Field(default_factory=list)
    diff_summary: Optional[DiffSummary] = None
    # SPEC-08: Subterranean strata (machine shapes + managed cloud vaults)
    subterranean_resources: List[RemoteServiceResource] = Field(default_factory=list)
    machine_shapes: List[MachineShape] = Field(default_factory=list)
    # SPEC-09: Kueue gang scheduling workloads (pre-admission staging yard)
    kueue_workloads: List[KueueWorkloadStatus] = Field(default_factory=list)
    # SPEC-09 §4.2: Karpenter NodeClaims provisioning Sub-Level B1 ghost nodes
    karpenter_node_claims: List[KarpenterNodeClaim] = Field(default_factory=list)

    class Config:
        populate_by_name = True
