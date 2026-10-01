"""Side-by-side cluster diff classifier for Cluster Visualizer.

Categorizes component matches, semantic version skews, image digest drifts,
and missing/added workloads between two Kubernetes cluster graphs.
"""

from __future__ import annotations
from typing import Dict, List, Tuple
from .models import (
    ClusterGraph,
    DataFlowEdge,
    DiffReport,
    DiffSummary,
    EdgeMatch,
    NodeComponent,
    NodeMatch,
)


def _canonical_key(node: NodeComponent) -> str:
    """Generate a stable canonical key across replica hash differences and node names."""
    name = node.name
    # Normalize control plane pod names like etcd-cluster-alpha-control-plane -> etcd
    if node.layer == "control-plane":
        for cp_prefix in ("kube-apiserver", "etcd", "coredns", "kindnet", "kube-controller-manager", "kube-scheduler", "kube-proxy"):
            if name.startswith(cp_prefix):
                return f"control-plane:{node.namespace}:{cp_prefix}"

    if node.layer == "node":
        return f"node:{node.kind}:primary-node"

    # Strip random replica hashes (e.g. redis-cluster-6587c5bb48-hjkvm -> redis-cluster)
    name_parts = name.split("-")
    if len(name_parts) >= 3 and len(name_parts[-1]) >= 4 and len(name_parts[-2]) >= 5:
        base_name = "-".join(name_parts[:-2])
    elif len(name_parts) >= 2 and len(name_parts[-1]) >= 4 and not name_parts[-1].isdigit():
        base_name = "-".join(name_parts[:-1])
    else:
        base_name = name
    return f"{node.layer}:{node.namespace}:{node.kind}:{base_name}"


def diff_clusters(
    cluster_a: ClusterGraph,
    cluster_b: ClusterGraph
) -> DiffReport:
    """Compare cluster A (source) and cluster B (target) and produce a detailed DiffReport."""
    nodes_a_by_key: Dict[str, List[NodeComponent]] = {}
    for n in cluster_a.nodes:
        key = _canonical_key(n)
        nodes_a_by_key.setdefault(key, []).append(n)

    nodes_b_by_key: Dict[str, List[NodeComponent]] = {}
    for n in cluster_b.nodes:
        key = _canonical_key(n)
        nodes_b_by_key.setdefault(key, []).append(n)

    all_keys = set(nodes_a_by_key.keys()).union(nodes_b_by_key.keys())

    node_matches: List[NodeMatch] = []
    identical_count = 0
    skew_count = 0
    missing_count = 0
    added_count = 0

    for key in sorted(all_keys):
        list_a = nodes_a_by_key.get(key, [])
        list_b = nodes_b_by_key.get(key, [])

        if list_a and not list_b:
            for na in list_a:
                node_matches.append(NodeMatch(
                    node_id=na.id,
                    status="missing",
                    source_version=na.version,
                    source_image=na.image,
                    source_digest=na.digest,
                    diff_details=[f"Present in {cluster_a.metadata.cluster_name}, absent in {cluster_b.metadata.cluster_name}"]
                ))
                missing_count += 1
        elif list_b and not list_a:
            for nb in list_b:
                node_matches.append(NodeMatch(
                    node_id=nb.id,
                    status="added",
                    target_version=nb.version,
                    target_image=nb.image,
                    target_digest=nb.digest,
                    diff_details=[f"Absent in {cluster_a.metadata.cluster_name}, present in {cluster_b.metadata.cluster_name}"]
                ))
                added_count += 1
        else:
            # Both present: match corresponding instances
            max_len = max(len(list_a), len(list_b))
            for i in range(max_len):
                na = list_a[i] if i < len(list_a) else None
                nb = list_b[i] if i < len(list_b) else None

                if na and nb:
                    diffs: List[str] = []
                    is_version_skew = False

                    if na.version != nb.version:
                        diffs.append(f"Version skew: '{na.version}' vs '{nb.version}'")
                        is_version_skew = True

                    if na.image != nb.image:
                        diffs.append(f"Image tag drift: '{na.image}' vs '{nb.image}'")
                        is_version_skew = True

                    if na.digest and nb.digest and na.digest != nb.digest:
                        diffs.append(f"Image digest skew: {na.digest[:16]}... vs {nb.digest[:16]}...")
                        is_version_skew = True

                    status = "version_skew" if is_version_skew else "identical"
                    if is_version_skew:
                        skew_count += 1
                    else:
                        identical_count += 1

                    node_matches.append(NodeMatch(
                        node_id=na.id,
                        status=status,
                        source_version=na.version,
                        target_version=nb.version,
                        source_image=na.image,
                        target_image=nb.image,
                        source_digest=na.digest,
                        target_digest=nb.digest,
                        diff_details=diffs
                    ))
                elif na:
                    node_matches.append(NodeMatch(
                        node_id=na.id,
                        status="missing",
                        source_version=na.version,
                        source_image=na.image,
                        source_digest=na.digest,
                        diff_details=["Excess replica in source cluster"]
                    ))
                    missing_count += 1
                elif nb:
                    node_matches.append(NodeMatch(
                        node_id=nb.id,
                        status="added",
                        target_version=nb.version,
                        target_image=nb.image,
                        target_digest=nb.digest,
                        diff_details=["Excess replica in target cluster"]
                    ))
                    added_count += 1

    summary = DiffSummary(
        identical_nodes=identical_count,
        version_skew_nodes=skew_count,
        missing_in_target=missing_count,
        added_in_target=added_count,
    )

    return DiffReport(
        source_cluster=cluster_a.metadata.cluster_name,
        target_cluster=cluster_b.metadata.cluster_name,
        summary=summary,
        nodes=node_matches,
        edges=[]
    )
