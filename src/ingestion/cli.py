"""CLI Orchestrator for Cluster Visualizer Ingestion.

Extracts live cluster graphs from Kind clusters, enriches framework components,
applies 3D spatial layout tiers, runs semantic version diffing, and writes
JSON artifacts into public/data/ for the WebGL frontend.
"""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path

from .extractor import extract_cluster_state
from .frameworks import enrich_framework_components
from .layout import apply_spatial_layout
from .differ import diff_clusters
from .models import ClusterGraph, ClusterMetadata


def ingest_cluster(context_name: str) -> ClusterGraph:
    """Extract, enrich, and spatially position a cluster graph."""
    print(f"📦 Extracting cluster state from context: '{context_name}'...")
    raw = extract_cluster_state(context_name)
    nodes = raw["nodes"]
    edges = raw["edges"]

    print(f"🔍 Detecting frameworks & stateful topologies for '{context_name}'...")
    enriched_nodes, enriched_edges = enrich_framework_components(nodes, edges)

    print(f"📐 Applying 3D spatial elevation tiers and planar layout...")
    spatially_laid_nodes = apply_spatial_layout(enriched_nodes)

    meta = ClusterMetadata(**raw["metadata"])
    graph = ClusterGraph(
        metadata=meta,
        nodes=spatially_laid_nodes,
        edges=enriched_edges,
    )
    return graph


def main():
    root = Path(__file__).resolve().parent.parent.parent
    data_dir = root / "public" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    ctx_alpha = os.environ.get("CLUSTER_A_CONTEXT", "kind-cluster-alpha")
    ctx_beta = os.environ.get("CLUSTER_B_CONTEXT", "kind-cluster-beta")

    try:
        graph_a = ingest_cluster(ctx_alpha)
        graph_b = ingest_cluster(ctx_beta)
    except Exception as e:
        print(f"❌ Failed to extract cluster state: {e}", file=sys.stderr)
        return 1

    print(f"⚡ Computing semantic version, image digest, and topology diff...")
    diff_report = diff_clusters(graph_a, graph_b)

    # Attach diff summary to cluster graphs
    graph_a.diff_summary = diff_report.summary
    graph_b.diff_summary = diff_report.summary

    # Write JSON artifacts
    file_a = data_dir / "cluster-alpha.json"
    file_b = data_dir / "cluster-beta.json"
    file_diff = data_dir / "cluster-diff.json"

    file_a.write_text(graph_a.model_dump_json(indent=2, by_alias=True))
    file_b.write_text(graph_b.model_dump_json(indent=2, by_alias=True))
    file_diff.write_text(diff_report.model_dump_json(indent=2))

    print(f"✅ Successfully exported:")
    print(f"   - {file_a} ({len(graph_a.nodes)} nodes, {len(graph_a.edges)} edges)")
    print(f"   - {file_b} ({len(graph_b.nodes)} nodes, {len(graph_b.edges)} edges)")
    print(f"   - {file_diff} (Diff Summary: {diff_report.summary})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
