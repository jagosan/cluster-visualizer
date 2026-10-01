"""Automated regression and verification test suite for Cluster Visualizer."""

import os
import unittest
from pathlib import Path

from src.ingestion.models import (
    ClusterGraph,
    ClusterMetadata,
    DataFlowEdge,
    DiffReport,
    NodeComponent,
    Spatial,
)
from src.ingestion.frameworks import enrich_framework_components
from src.ingestion.differ import diff_clusters
from src.ingestion.layout import apply_spatial_layout, generate_skyscraper_edges, ELEVATION_TIERS

class TestClusterIngestionAndDiff(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent

    def test_glb_asset_exists_and_valid(self):
        """Verify Blender exported GLB asset kit exists and has valid size."""
        glb_path = self.root / "public" / "assets" / "cluster-kit.glb"
        self.assertTrue(glb_path.exists(), "cluster-kit.glb must exist")
        self.assertGreater(os.path.getsize(glb_path), 5000, "GLB must exceed 5KB")

    def test_elevation_tiers_consistency(self):
        """Verify spatial layout applies skyscraper architectural elevation tiers."""
        nodes = [
            NodeComponent(id="cl-1", layer="ingress", kind="Client", name="kubectl-cli"),
            NodeComponent(id="cp-1", layer="control-plane", kind="APIServer", name="kube-apiserver"),
            NodeComponent(id="et-1", layer="control-plane", kind="etcd", name="etcd-0"),
            NodeComponent(id="fw-1", layer="framework", kind="RayHead", name="ray-head"),
            NodeComponent(id="wl-1", layer="workload", kind="Pod", name="postgres-primary-0"),
            NodeComponent(id="nd-1", layer="node", kind="Node", name="node-1"),
            NodeComponent(id="ig-1", layer="ingress", kind="Ingress", name="ingress-lb"),
        ]
        laid_out = apply_spatial_layout(nodes)
        by_id = {n.id: n for n in laid_out}

        self.assertEqual(by_id["cl-1"].spatial.y, ELEVATION_TIERS["client"])
        self.assertEqual(by_id["ig-1"].spatial.y, ELEVATION_TIERS["aggregation"])
        self.assertEqual(by_id["cp-1"].spatial.y, ELEVATION_TIERS["apiserver"])
        self.assertEqual(by_id["et-1"].spatial.y, ELEVATION_TIERS["vault"])
        self.assertEqual(by_id["et-1"].spatial.z, -3.5, "etcd must be placed behind API server at Z=-3.5")
        self.assertEqual(by_id["fw-1"].spatial.y, ELEVATION_TIERS["framework"])
        self.assertEqual(by_id["nd-1"].spatial.y, ELEVATION_TIERS["worker_base"])
        self.assertEqual(by_id["wl-1"].spatial.y, ELEVATION_TIERS["worker_base"] + 0.25)
        self.assertEqual(by_id["nd-1"].spatial.asset_type, "LayerTray_Worker")
        self.assertEqual(by_id["cp-1"].spatial.asset_type, "Cuboid_APIServer")
        self.assertEqual(by_id["et-1"].spatial.asset_type, "Cuboid_etcd")
        self.assertEqual(by_id["cl-1"].spatial.asset_type, "Client_Slab")

    def test_framework_detection_and_edge_generation(self):
        """Verify Ray, Spark, and Postgres frameworks generate valid topologies and data-flow edges."""
        nodes = [
            NodeComponent(
                id="ray-h",
                layer="workload",
                kind="Pod",
                name="ray-head-xyz",
                raw_labels={"ray.io/node-type": "head", "app.kubernetes.io/name": "ray"},
                version="2.58.0",
            ),
            NodeComponent(
                id="ray-w",
                layer="workload",
                kind="Pod",
                name="ray-worker-abc",
                raw_labels={"ray.io/node-type": "worker", "app.kubernetes.io/name": "ray"},
                version="2.58.0",
            ),
            NodeComponent(
                id="pg-p",
                layer="workload",
                kind="Pod",
                name="postgres-primary-0",
                raw_labels={"app.kubernetes.io/component": "primary", "app.kubernetes.io/name": "postgresql"},
                version="18.6",
            ),
            NodeComponent(
                id="pg-r",
                layer="workload",
                kind="Pod",
                name="postgres-replica-0",
                raw_labels={"app.kubernetes.io/component": "replica", "app.kubernetes.io/name": "postgresql"},
                version="18.6",
            ),
        ]
        enriched_nodes, edges = enrich_framework_components(nodes, [])
        by_id = {n.id: n for n in enriched_nodes}

        # Check Asset Types
        self.assertEqual(by_id["ray-h"].spatial.asset_type, "Framework_Ray")
        self.assertEqual(by_id["ray-w"].spatial.asset_type, "Framework_Ray")
        self.assertEqual(by_id["pg-p"].spatial.asset_type, "Database_Postgres")
        self.assertEqual(by_id["pg-r"].spatial.asset_type, "Database_Postgres")

        # Check Edges
        flow_types = [e.flow_type for e in edges]
        self.assertIn("framework_control", flow_types)
        self.assertIn("data_replication", flow_types)

    def test_skyscraper_conduit_routes(self):
        """Verify skyscraper layout generates the correct data-flow conduits."""
        nodes = [
            NodeComponent(id="cl-1", layer="ingress", kind="Client", name="kubectl-cli"),
            NodeComponent(id="ig-1", layer="ingress", kind="Ingress", name="kube-aggregator"),
            NodeComponent(id="cp-1", layer="control-plane", kind="APIServer", name="kube-apiserver-0"),
            NodeComponent(id="et-1", layer="control-plane", kind="etcd", name="etcd-0"),
            NodeComponent(id="nd-1", layer="node", kind="Kubelet", name="kubelet-node1")
        ]
        laid_out = apply_spatial_layout(nodes)
        edges = generate_skyscraper_edges(laid_out)
        
        protocols = [e.protocol for e in edges]
        self.assertIn("HTTPS/443", protocols, "Client to Ingress edge missing")
        self.assertIn("HTTPS/6443", protocols, "Ingress to API server edge missing")
        self.assertIn("gRPC/2379", protocols, "API server to etcd edge missing")
        self.assertIn("HTTPS/6443/Heartbeat", protocols, "Kubelet to API server heartbeat missing")

    def test_diff_engine_version_skew_classification(self):
        """Verify diff classifier correctly flags version skews and image drift."""
        meta_a = ClusterMetadata(cluster_name="alpha", kubernetes_version="v1.36.4", timestamp="2026-09-30T00:00:00Z")
        meta_b = ClusterMetadata(cluster_name="beta", kubernetes_version="v1.35.8", timestamp="2026-09-30T00:00:00Z")

        node_a = NodeComponent(
            id="pg-0",
            layer="workload",
            kind="Pod",
            name="postgres-primary-0",
            version="18.6",
            image="postgres:18.6",
            digest="sha256:aaaa",
        )
        node_b = NodeComponent(
            id="pg-0",
            layer="workload",
            kind="Pod",
            name="postgres-primary-0",
            version="17.11",
            image="postgres:17.11",
            digest="sha256:bbbb",
        )

        graph_a = ClusterGraph(metadata=meta_a, nodes=[node_a], edges=[])
        graph_b = ClusterGraph(metadata=meta_b, nodes=[node_b], edges=[])

        report = diff_clusters(graph_a, graph_b)
        self.assertEqual(report.summary.version_skew_nodes, 1)
        self.assertEqual(report.summary.identical_nodes, 0)
        self.assertEqual(report.nodes[0].status, "version_skew")
        self.assertIn("Version skew: '18.6' vs '17.11'", report.nodes[0].diff_details[0])


if __name__ == "__main__":
    unittest.main()
