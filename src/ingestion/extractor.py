"""Kubernetes live-state extractor for Cluster Visualizer.

Shells out to `kubectl` against a named context and distils the raw
`nodes` / `pods -A` JSON into graph-ready `NodeComponent` entries with
exact images and sha256 digests taken from `status.containerStatuses`.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, Dict as _Dict, List, Optional, Tuple

from .models import ClusterMetadata, DataFlowEdge, NodeComponent, Spatial

# Namespaces treated as cluster plumbing (never "workload" layer).
SYSTEM_NAMESPACES = frozenset({"kube-system", "kube-node-lease", "kube-public"})

# Control-plane pod signatures: (matcher substring, canonical kind name).
# Matched against pod name AND container image so both static pods
# (kube-apiserver-<node>, etcd-<node>) and Deployments (coredns, kindnet)
# are caught regardless of replica hash suffixes.
CONTROL_PLANE_SIGNATURES: Tuple[Tuple[str, str], ...] = (
    ("kube-apiserver", "kube-apiserver"),
    ("apiserver", "kube-apiserver"),
    ("etcd", "etcd"),
    ("coredns", "coredns"),
    ("kindnet", "kindnet"),
)


class ExtractionError(RuntimeError):
    """Raised when kubectl fails or returns unparseable JSON."""


def _run_kubectl(context_name: str, args: List[str]) -> Dict[str, Any]:
    """Execute `kubectl --context <ctx> <args>` and parse the JSON envelope."""
    cmd = ["kubectl", "--context", context_name] + args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as exc:  # kubectl not on PATH
        raise ExtractionError("kubectl not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ExtractionError(f"kubectl timed out: {' '.join(cmd)}") from exc
    if proc.returncode != 0:
        raise ExtractionError(
            f"kubectl failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr.strip()}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"invalid JSON from {' '.join(cmd)}") from exc


def _split_image(image: str) -> Tuple[str, str]:
    """Return (image_without_digest, digest) where digest keeps 'sha256:' prefix."""
    if "@" in image:
        base, digest = image.rsplit("@", 1)
        return base, digest
    return image, ""


def _image_tag(image_ref: str) -> str:
    """Best-effort tag from an image ref (digest-only refs -> 'unknown')."""
    ref, _ = _split_image(image_ref)
    # Strip registry host if present (host contains '.' or ':' before first '/').
    head = ref.split("/", 1)[0]
    if "." in head or ":" in head:
        ref = ref.split("/", 1)[1] if "/" in ref else ref
    if ":" in ref:
        return ref.rsplit(":", 1)[1]
    return "unknown"


def _digest_from_container_status(cs: Dict[str, Any]) -> Optional[str]:
    """Exact runtime digest: prefer imageID, fall back to spec image digest."""
    image_id = cs.get("imageID") or ""
    if "@" in image_id:
        return image_id.rsplit("@", 1)[1]
    spec_digest = _split_image(cs.get("image") or "")[1]
    return spec_digest or None


def _pod_ready(pod: Dict[str, Any]) -> bool:
    for cond in pod.get("status", {}).get("conditions", []):
        if cond.get("type") == "Ready":
            return cond.get("status") == "True"
    return False


def _match_control_plane(pod: Dict[str, Any]) -> Optional[str]:
    """Return canonical control-plane kind if this pod is apiserver/etcd/coredns/kindnet."""
    name = pod.get("metadata", {}).get("name", "")
    images = [
        cs.get("image", "")
        for cs in pod.get("status", {}).get("containerStatuses", [])
    ]
    haystacks = [name.lower()] + [img.lower() for img in images]
    for needle, canonical in CONTROL_PLANE_SIGNATURES:
        if any(needle in hay for hay in haystacks):
            return canonical
    return None


def _extract_nodes(raw_nodes: List[Dict[str, Any]]) -> List[NodeComponent]:
    """Node (machine) entries: layer='node', asset_type='NodeTray'."""
    components: List[NodeComponent] = []
    for node in raw_nodes:
        meta = node.get("metadata", {})
        status = node.get("status", {})
        capacity = status.get("capacity", {})
        allocatable = status.get("allocatable", {})

        kubelet_version = status.get("nodeInfo", {}).get("kubeletVersion", "unknown")
        unschedulable = bool(node.get("spec", {}).get("unschedulable"))
        ready = any(
            c.get("type") == "Ready" and c.get("status") == "True"
            for c in status.get("conditions", [])
        )

        components.append(
            NodeComponent(
                id=f"node/{meta.get('name', 'unknown')}",
                layer="node",
                kind="Node",
                name=meta.get("name", "unknown"),
                namespace="cluster",
                version=kubelet_version,
                status="Healthy" if ready else "Degraded",
                metrics={
                    "cpu_capacity": capacity.get("cpu", "0"),
                    "memory_capacity": capacity.get("memory", "0"),
                    "cpu_allocatable": allocatable.get("cpu", "0"),
                    "memory_allocatable": allocatable.get("memory", "0"),
                    "os_image": status.get("nodeInfo", {}).get("osImage", "unknown"),
                    "unschedulable": unschedulable,
                },
                spatial=Spatial(asset_type="NodeTray"),
                raw_labels=dict(meta.get("labels", {})),
            )
        )
    return components


def _extract_control_plane_pods(raw_pods: List[Dict[str, Any]]) -> List[NodeComponent]:
    """Control-plane pods in kube-system (apiserver/etcd/coredns/kindnet)."""
    components: List[NodeComponent] = []
    for pod in raw_pods:
        meta = pod.get("metadata", {})
        if meta.get("namespace") not in ("kube-system",):
            continue
        canonical = _match_control_plane(pod)
        if canonical is None:
            continue

        image: Optional[str] = None
        digest: Optional[str] = None
        for cs in pod.get("status", {}).get("containerStatuses", []):
            image = cs.get("image") or image
            digest = _digest_from_container_status(cs) or digest

        version = _image_tag(image or "")
        components.append(
            NodeComponent(
                id=f"control-plane/{meta.get('namespace')}/{meta.get('name')}",
                layer="control-plane",
                kind="Pod",
                name=meta.get("name", "unknown"),
                namespace=meta.get("namespace", "kube-system"),
                version=version,
                image=image,
                digest=digest,
                status="Healthy" if _pod_ready(pod) else "Degraded",
                metrics={"component": canonical},
                spatial=Spatial(asset_type="ControlPlane_Cube"),
                raw_labels=dict(meta.get("labels", {})),
            )
        )
    return components


def _extract_workload_pods(raw_pods: List[Dict[str, Any]]) -> List[NodeComponent]:
    """Non-system pods: layer='workload', asset_type='Pod_Cylinder'."""
    components: List[NodeComponent] = []
    for pod in raw_pods:
        meta = pod.get("metadata", {})
        ns = meta.get("namespace", "default")
        if ns in SYSTEM_NAMESPACES:
            continue

        image: Optional[str] = None
        digest: Optional[str] = None
        containers = []
        for cs in pod.get("status", {}).get("containerStatuses", []):
            image = cs.get("image") or image
            digest = _digest_from_container_status(cs) or digest
            containers.append(cs.get("name", ""))

        labels = dict(meta.get("labels", {}))
        components.append(
            NodeComponent(
                id=f"pod/{ns}/{meta.get('name', 'unknown')}",
                layer="workload",
                kind="Pod",
                name=meta.get("name", "unknown"),
                namespace=ns,
                version=_image_tag(image or ""),
                image=image,
                digest=digest,
                status="Healthy" if _pod_ready(pod) else "Degraded",
                metrics={"containers": containers},
                spatial=Spatial(asset_type="Pod_Cylinder"),
                raw_labels=labels,
            )
        )
    return components


def _control_plane_edges(cp_nodes: List[NodeComponent]) -> List[DataFlowEdge]:
    """Canonical control-plane wiring: apiserver -> etcd, apiserver -> coredns."""
    edges: List[DataFlowEdge] = []
    apiservers = [n for n in cp_nodes if n.metrics.get("component") == "kube-apiserver"]
    etcds = [n for n in cp_nodes if n.metrics.get("component") == "etcd"]
    dnses = [n for n in cp_nodes if n.metrics.get("component") == "coredns"]

    for api in apiservers:
        for etcd in etcds:
            edges.append(DataFlowEdge(
                source=api.id, target=etcd.id,
                flow_type="control_plane", protocol="gRPC", direction="unidirectional",
                volume_label="etcd writes",
            ))
        for dns in dnses:
            edges.append(DataFlowEdge(
                source=api.id, target=dns.id,
                flow_type="control_plane", protocol="TCP", direction="unidirectional",
                animated=False,
            ))
    return edges


def extract_cluster_state(context_name: str) -> dict:
    """Extract a full graph-ready snapshot of a live cluster context.

    Returns a dict with:
      metadata   -> dict of ClusterMetadata field values
      nodes      -> List[NodeComponent] (machines + control-plane + workloads)
      edges      -> List[DataFlowEdge] (control-plane wiring)
      raw_nodes  -> raw kubectl node JSON items (for frameworks.py / diffing)
      raw_pods   -> raw kubectl pod JSON items (for frameworks.py / diffing)
    """
    nodes_env = _run_kubectl(context_name, ["get", "nodes", "-o", "json"])
    pods_env = _run_kubectl(context_name, ["get", "pods", "-A", "-o", "json"])

    raw_nodes: List[Dict[str, Any]] = nodes_env.get("items", [])
    raw_pods: List[Dict[str, Any]] = pods_env.get("items", [])

    machine_nodes = _extract_nodes(raw_nodes)
    cp_pods = _extract_control_plane_pods(raw_pods)
    workloads = _extract_workload_pods(raw_pods)

    kube_version = machine_nodes[0].version if machine_nodes else "unknown"
    metadata = ClusterMetadata(
        cluster_name=context_name,
        kubernetes_version=kube_version,
        distribution="kind",
        timestamp=datetime.now(timezone.utc).isoformat(),
        node_count=len(machine_nodes),
        pod_count=len(raw_pods),
    )

    return {
        "metadata": metadata.model_dump(),
        "nodes": machine_nodes + cp_pods + workloads,
        "edges": _control_plane_edges(cp_pods),
        "raw_nodes": raw_nodes,
        "raw_pods": raw_pods,
    }
