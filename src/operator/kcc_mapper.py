"""KCC / kro CRD mapper: normalizes external-infra CRDs into ClusterGraph vaults (SPEC-08 §3).

Turns raw ConfigMap-dumped KCC resources (SQLInstance, SpannerInstance,
StorageBucket, PubSubTopic, RedisInstance) and kro composite instances into
``RemoteServiceResource``, and Node objects into ``MachineShape`` chassis.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from src.ingestion.models import (
    CloudProvider,
    MachineShape,
    ManagedServiceCategory,
    RemoteServiceResource,
)

# ---------------------------------------------------------------------------
# CRD taxonomy: (apiVersion-group, kind) -> ManagedServiceCategory
# ---------------------------------------------------------------------------

KCC_CRD_MAP: Dict[Tuple[str, str], ManagedServiceCategory] = {
    ("sql.cnrm.cloud.google.com", "SQLInstance"): ManagedServiceCategory.DATABASE_RELATIONAL,
    ("spanner.cnrm.cloud.google.com", "SpannerInstance"): ManagedServiceCategory.DATABASE_RELATIONAL,
    ("storage.cnrm.cloud.google.com", "StorageBucket"): ManagedServiceCategory.OBJECT_STORAGE,
    ("pubsub.cnrm.cloud.google.com", "PubSubTopic"): ManagedServiceCategory.MESSAGING_EVENTING,
    ("redis.cnrm.cloud.google.com", "RedisInstance"): ManagedServiceCategory.CACHE_IN_MEMORY,
}

KRO_APIGROUP_PATTERN = re.compile(r"(^|/)kro\.run($|[/-])")
KRO_DEFAULT_CATEGORY = ManagedServiceCategory.DATABASE_RELATIONAL
_KRO_PARENT_ANNOTATIONS: Tuple[str, ...] = (
    "kro.run/parent-resource",
    "kro.run/resource-graph-name",
    "kro.run/composite-namespace",
)

_READY_CONDITION_TYPES = frozenset({"Ready", "Reconciling", "Degraded", "Failed"})


def _split_api_version(api_version: str) -> str:
    """Return the CRD group from ``group/v1`` (or '' for core ``v1``)."""
    return api_version.split("/", 1)[0] if "/" in api_version else ""


def is_kro_managed(raw: Dict[str, Any]) -> bool:
    """True when apiVersion is under kro.run, spec.parentRef exists, or a
    kro.run annotation marks the object as a kro-rendered child."""
    if KRO_APIGROUP_PATTERN.search(str(raw.get("apiVersion", ""))):
        return True
    spec = raw.get("spec") or {}
    if isinstance(spec, dict) and spec.get("parentRef"):
        return True
    annotations = (raw.get("metadata") or {}).get("annotations") or {}
    return any(key in annotations for key in _KRO_PARENT_ANNOTATIONS)


def _resolve_status(raw: Dict[str, Any]) -> str:
    """Collapse status.conditions / status.phase to Ready|Reconciling|Degraded|Failed."""
    status = raw.get("status") or {}
    if not isinstance(status, dict):
        return "Ready"
    phase = str(status.get("phase", ""))
    if phase in _READY_CONDITION_TYPES:
        return phase
    # Priority: terminal-bad > in-flight > good; last-wins within a tier.
    resolved = "Ready"
    rank = {"Ready": 0, "Reconciling": 1, "Degraded": 2, "Failed": 3}
    for cond in status.get("conditions") or []:
        if not isinstance(cond, dict):
            continue
        ctype = str(cond.get("type", ""))
        if ctype in rank and str(cond.get("status", "True")) == "True":
            if rank[ctype] >= rank[resolved]:
                resolved = ctype
    return resolved


def _resolve_endpoint(raw: Dict[str, Any]) -> Optional[str]:
    status = raw.get("status") or {}
    spec = raw.get("spec") or {}
    for candidate in (
        status.get("selfLink") if isinstance(status, dict) else None,
        status.get("endpoint") if isinstance(status, dict) else None,
        spec.get("ipAddress") if isinstance(spec, dict) else None,
    ):
        if candidate:
            return str(candidate)
    if isinstance(status, dict):
        ip = status.get("address") or status.get("ipAddress")
        if ip:
            return str(ip)
    return None


def parse_kcc_resource(raw: Dict[str, Any]) -> Optional[RemoteServiceResource]:
    """Map one raw KCC/kro CRD dict to a RemoteServiceResource, or None if unmapped."""
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind", ""))
    api_version = str(raw.get("apiVersion", ""))
    group = _split_api_version(api_version)

    managed_by = "kro" if is_kro_managed(raw) else "kcc"
    category = KCC_CRD_MAP.get((group, kind))
    if category is None:
        if managed_by != "kro":
            return None
        category = KRO_DEFAULT_CATEGORY

    metadata = raw.get("metadata") or {}
    name = str(metadata.get("name", ""))
    namespace = str(metadata.get("namespace", "default"))
    if not name:
        return None

    kro_parent_id: Optional[str] = None
    annotations = metadata.get("annotations") or {}
    spec = raw.get("spec") or {}
    parent_ref = spec.get("parentRef") if isinstance(spec, dict) else None
    if managed_by == "kro":
        if isinstance(parent_ref, dict):
            kro_parent_id = str(parent_ref.get("name", "")) or None
        kro_parent_id = kro_parent_id or str(annotations.get(_KRO_PARENT_ANNOTATIONS[0], "")) or None

    return RemoteServiceResource(
        id=f"{group or 'kro'}/{kind}/{namespace}/{name}",
        provider=CloudProvider.GCP,
        category=category,
        cr_group=group or "kro.run",
        cr_kind=kind,
        name=name,
        namespace=namespace,
        display_name=name,
        status_phase=_resolve_status(raw),
        endpoint=_resolve_endpoint(raw),
        managed_by=managed_by,
        kro_parent_id=kro_parent_id,
    )


# ---------------------------------------------------------------------------
# Node -> MachineShape (SPEC-08 Sub-Level B1 chassis)
# ---------------------------------------------------------------------------

_MEM_UNITS = {  # unit suffix -> GiB per unit
    "Ki": 1.0 / 1024**2, "Mi": 1.0 / 1024, "Gi": 1.0, "Ti": 1024.0,
    "K": 1e3 / 1024**3, "M": 1e6 / 1024**3, "G": 1e9 / 1024**3, "T": 1e12 / 1024**3,
}


def _to_memory_gib(value: Any) -> Optional[float]:
    """Convert Kubernetes quantity (e.g. '32768Mi', '2Gi', plain bytes) to GiB."""
    s = str(value).strip()
    if not s:
        return None
    for unit, factor in _MEM_UNITS.items():
        if s.endswith(unit):
            try:
                return float(s[: -len(unit)]) * factor
            except ValueError:
                return None
    try:
        return float(s) / 1024**3  # bare number = bytes
    except ValueError:
        return None


def _to_vcpus(value: Any) -> Optional[int]:
    s = str(value).strip()
    try:
        if s.endswith("m"):
            return max(1, round(int(s[:-1]) / 1000))
        cores = float(s)
        return max(1, round(cores)) if cores > 0 else None
    except ValueError:
        return None


def parse_node_machine_shape(node_raw: Dict[str, Any]) -> MachineShape:
    """Normalize a raw Kubernetes Node object into a MachineShape chassis."""
    node = node_raw if isinstance(node_raw, dict) else {}
    metadata = node.get("metadata") or {}
    labels: Dict[str, str] = {str(k): str(v) for k, v in (metadata.get("labels") or {}).items()}
    status = node.get("status") or {}

    instance_type = (
        labels.get("node.kubernetes.io/instance-type")
        or labels.get("beta.kubernetes.io/instance-type")
        or "unknown"
    )
    compute_class = labels.get("karpenter.sh/nodepool") or labels.get("cloud.google.com/gke-nodepool")

    capacity_type: str = "spot" if (
        labels.get("karpenter.sh/capacity-type") == "spot"
        or labels.get("cloud.google.com/gke-spot") == "true"
    ) else "on-demand"

    zone = (
        labels.get("topology.kubernetes.io/zone")
        or labels.get("failure-domain.beta.kubernetes.io/zone")
        or "us-central1-a"
    )

    # allocatable overrides capacity where both exist.
    capacity: Dict[str, Any] = {
        **(status.get("capacity") or {}),
        **(status.get("allocatable") or {}),
    }

    vcpus = _to_vcpus(capacity.get("cpu")) or 4
    memory_gib = _to_memory_gib(capacity.get("memory")) or 16.0

    accelerator_type = labels.get("cloud.google.com/gke-accelerator") or labels.get("accelerator")
    accelerator_count = 0
    gpu_raw = capacity.get("nvidia.com/gpu") or capacity.get("google.com/gke-nvidia-gpu")
    try:
        accelerator_count = int(float(gpu_raw)) if gpu_raw is not None else 0
    except (TypeError, ValueError):
        accelerator_count = 0
    if accelerator_count > 0 and not accelerator_type:
        accelerator_type = "nvidia-gpu"

    return MachineShape(
        node_name=str(metadata.get("name", "unknown")),
        provider=CloudProvider.GCP,
        instance_type=instance_type,
        compute_class=compute_class,
        vcpus=vcpus,
        memory_gib=memory_gib,
        capacity_type=capacity_type,  # type: ignore[arg-type]
        zone=zone,
        accelerator_type=accelerator_type,
        accelerator_count=accelerator_count,
    )
