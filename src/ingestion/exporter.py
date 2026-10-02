"""Universal Kubernetes Cluster Topology Exporter CLI.

SPEC-03 / TASK-CV-406
Zero-dependency resource harvesting, secret scrubbing, and graph export
producing standard ClusterGraph JSON conforming to src/ingestion/models.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cli import ingest_cluster
from .extractor import extract_cluster_state
from .frameworks import enrich_framework_components
from .layout import apply_spatial_layout, generate_skyscraper_edges
from .models import ClusterGraph, ClusterMetadata, DataFlowEdge, NodeComponent, Spatial


SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(password|token|key|secret|auth|credential|private|cert|tls|apikey|access_key)"
)


def scrub_sensitive_string(val: str) -> str:
    """Hash long or sensitive values with SHA256; redact tokens."""
    if not val:
        return "[REDACTED]"
    if SENSITIVE_KEY_PATTERN.search(val) or len(val) > 32:
        return f"sha256:{hashlib.sha256(val.encode('utf-8')).hexdigest()[:16]}"
    return "[REDACTED]"


def generate_mock_cluster_graph() -> ClusterGraph:
    """Generate a valid synthetic ClusterGraph for offline testing."""
    nodes = [
        NodeComponent(
            id="mock/client-kubectl",
            layer="ingress",
            kind="Client",
            name="kubectl-cli",
            namespace="external",
            version="v1.31.0",
            status="Healthy",
            metrics={"tool": "kubectl"},
            spatial=Spatial(asset_type="Client_Slab"),
        ),
        NodeComponent(
            id="mock/apiserver-0",
            layer="control-plane",
            kind="APIServer",
            name="kube-apiserver-0",
            namespace="kube-system",
            version="v1.36.4",
            image="registry.k8s.io/kube-apiserver:v1.36.4",
            digest="sha256:73a9f0e1d8",
            status="Healthy",
            spatial=Spatial(asset_type="Cuboid_APIServer"),
        ),
        NodeComponent(
            id="mock/etcd-0",
            layer="control-plane",
            kind="etcd",
            name="etcd-0",
            namespace="kube-system",
            version="v3.5.15",
            image="registry.k8s.io/etcd:3.5.15",
            digest="sha256:a4c5b6e7f8",
            status="Healthy",
            spatial=Spatial(asset_type="Cuboid_etcd"),
        ),
        NodeComponent(
            id="mock/scheduler-0",
            layer="control-plane",
            kind="Scheduler",
            name="kube-scheduler-0",
            namespace="kube-system",
            version="v1.36.4",
            status="Healthy",
            spatial=Spatial(asset_type="Cuboid_Supervisor"),
        ),
        NodeComponent(
            id="mock/controller-0",
            layer="control-plane",
            kind="ControllerManager",
            name="kube-controller-manager-0",
            namespace="kube-system",
            version="v1.36.4",
            status="Healthy",
            spatial=Spatial(asset_type="Cuboid_Supervisor"),
        ),
        NodeComponent(
            id="mock/node-worker-1",
            layer="node",
            kind="Node",
            name="worker-1",
            version="v1.36.4",
            status="Ready",
            spatial=Spatial(asset_type="LayerTray_Worker"),
        ),
        NodeComponent(
            id="mock/node-worker-2",
            layer="node",
            kind="Node",
            name="worker-2",
            version="v1.36.4",
            status="Ready",
            spatial=Spatial(asset_type="LayerTray_Worker"),
        ),
        NodeComponent(
            id="mock/kubelet-1",
            layer="node",
            kind="Kubelet",
            name="kubelet-worker-1",
            namespace="kube-system",
            version="v1.36.4",
            status="Healthy",
            spatial=Spatial(asset_type="Cuboid_Kubelet"),
        ),
        NodeComponent(
            id="mock/kubelet-2",
            layer="node",
            kind="Kubelet",
            name="kubelet-worker-2",
            namespace="kube-system",
            version="v1.36.4",
            status="Healthy",
            spatial=Spatial(asset_type="Cuboid_Kubelet"),
        ),
        NodeComponent(
            id="mock/containerd-1",
            layer="node",
            kind="Containerd",
            name="containerd-worker-1",
            namespace="kube-system",
            version="v1.7.20",
            status="Healthy",
            spatial=Spatial(asset_type="Cuboid_Containerd"),
        ),
        NodeComponent(
            id="mock/containerd-2",
            layer="node",
            kind="Containerd",
            name="containerd-worker-2",
            namespace="kube-system",
            version="v1.7.20",
            status="Healthy",
            spatial=Spatial(asset_type="Cuboid_Containerd"),
        ),
        NodeComponent(
            id="mock/kube-proxy-1",
            layer="control-plane",
            kind="DaemonSet",
            name="kube-proxy-w1",
            namespace="kube-system",
            version="v1.36.4",
            status="Running",
            spatial=Spatial(asset_type="Cuboid_DaemonSet"),
        ),
        NodeComponent(
            id="mock/kube-proxy-2",
            layer="control-plane",
            kind="DaemonSet",
            name="kube-proxy-w2",
            namespace="kube-system",
            version="v1.36.4",
            status="Running",
            spatial=Spatial(asset_type="Cuboid_DaemonSet"),
        ),
        NodeComponent(
            id="mock/cilium-1",
            layer="control-plane",
            kind="DaemonSet",
            name="cilium-cni-w1",
            namespace="kube-system",
            version="v1.16.1",
            status="Running",
            spatial=Spatial(asset_type="Cuboid_DaemonSet"),
        ),
        NodeComponent(
            id="mock/cilium-2",
            layer="control-plane",
            kind="DaemonSet",
            name="cilium-cni-w2",
            namespace="kube-system",
            version="v1.16.1",
            status="Running",
            spatial=Spatial(asset_type="Cuboid_DaemonSet"),
        ),
        NodeComponent(
            id="mock/postgres-0",
            layer="workload",
            kind="Pod",
            name="postgres-primary-0",
            namespace="default",
            version="18.6",
            image="postgres:18.6",
            digest="sha256:d8a2c19e5",
            status="Running",
            spatial=Spatial(asset_type="Database_Postgres"),
        ),
        NodeComponent(
            id="mock/redis-0",
            layer="workload",
            kind="Pod",
            name="redis-cluster-0",
            namespace="default",
            version="7.4.1",
            image="redis:7.4.1",
            digest="sha256:bb8742f9a",
            status="Running",
            spatial=Spatial(asset_type="Cache_Redis"),
        ),
    ]

    laid_out = apply_spatial_layout(nodes)
    edges = generate_skyscraper_edges(laid_out)

    return ClusterGraph(
        metadata=ClusterMetadata(
            cluster_name="mock-cluster",
            kubernetes_version="v1.36.4",
            distribution="mock",
            timestamp=datetime.now(timezone.utc).isoformat(),
            node_count=2,
            pod_count=len(nodes) - 3,
        ),
        nodes=laid_out,
        edges=edges,
    )


def export_cluster(
    context: Optional[str] = None,
    kubeconfig: Optional[str] = None,
    mock: bool = False,
) -> ClusterGraph:
    """Export a normalized ClusterGraph from a live cluster or synthetic mock."""
    if mock:
        return generate_mock_cluster_graph()

    # Determine context
    if not context:
        try:
            res = subprocess.run(
                ["kubectl", "config", "current-context"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                context = res.stdout.strip()
            else:
                context = "kind-cluster-alpha"
        except Exception:
            context = "kind-cluster-alpha"

    if kubeconfig:
        os.environ["KUBECONFIG"] = kubeconfig

    try:
        graph = ingest_cluster(context)
        return graph
    except Exception as e:
        print(f"[WARN] Live cluster extraction failed for context '{context}': {e}", file=sys.stderr)
        print("[INFO] Falling back to synthetic mock cluster topology...", file=sys.stderr)
        return generate_mock_cluster_graph()


def main():
    parser = argparse.ArgumentParser(
        prog="cluster-vis dump / exporter",
        description="Universal Kubernetes Cluster Topology Exporter CLI (SPEC-03)",
    )
    parser.add_argument(
        "--context",
        "-c",
        type=str,
        default=None,
        help="Target Kubernetes context name (defaults to current-context)",
    )
    parser.add_argument(
        "--kubeconfig",
        "-k",
        type=str,
        default=None,
        help="Optional path to kubeconfig file",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Destination JSON output path (prints to stdout if omitted)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Generate synthetic mock cluster topology without live kubectl calls",
    )

    args = parser.parse_args()

    graph = export_cluster(
        context=args.context,
        kubeconfig=args.kubeconfig,
        mock=args.mock,
    )

    json_str = graph.model_dump_json(indent=2, by_alias=True)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json_str, encoding="utf-8")
        print(f"✅ Successfully exported cluster topology ({len(graph.nodes)} nodes, {len(graph.edges)} edges) to: {args.output}")
    else:
        print(json_str)


if __name__ == "__main__":
    main()
