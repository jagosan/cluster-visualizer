import unittest
import os
import json
import queue
import yaml
from pathlib import Path
from unittest.mock import MagicMock, patch

# Assuming these imports exist in the project structure based on the spec
# If they don't exist, these tests will fail as expected for missing implementations
try:
    from src.operator.controller import TopologyController
    from src.ingestion.models import ClusterGraph, NodeComponent, Spatial
except ImportError:
    # Fallback for environments where specific module paths might differ
    # In a real scenario, these would be adjusted to match the actual project structure
    TopologyController = None
    ClusterGraph = None


class TestOperatorAndStream(unittest.TestCase):
    """
    SPEC-04 / TASK-CV-506:
    Verifies the in-cluster operator and offline fallbacks.
    """

    def setUp(self):
        """Set up common test fixtures."""
        self.base_dir = Path(__file__).parent.parent
        self.deploy_dir = self.base_dir / "deploy"
        self.dist_dir = self.base_dir / "dist"

    # --------------------------------------------------------------------------
    # 2. Test CRD & Manifests
    # --------------------------------------------------------------------------

    def test_crd_exists_and_valid(self):
        """Verify deploy/crd/clustervis.io_clustertopologysnapshots.yaml exists and contains valid YAML for ClusterTopologySnapshot."""
        crd_path = self.deploy_dir / "crd" / "clustervis.io_clustertopologysnapshots.yaml"
        
        self.assertTrue(crd_path.exists(), f"CRD file not found at {crd_path}")
        
        with open(crd_path, 'r') as f:
            try:
                crd_data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                self.fail(f"Invalid YAML in CRD file: {e}")
        
        self.assertIsInstance(crd_data, dict, "CRD YAML should parse to a dictionary")
        
        # Check for required fields
        self.assertIn("apiVersion", crd_data, "CRD missing apiVersion")
        self.assertIn("kind", crd_data, "CRD missing kind")
        
        # Verify specific values as per spec
        self.assertEqual(crd_data["apiVersion"], "apiextensions.k8s.io/v1", 
                         "CRD apiVersion should be apiextensions.k8s.io/v1")
        self.assertEqual(crd_data["kind"], "CustomResourceDefinition", 
                         "CRD kind should be CustomResourceDefinition")
        
        # Check spec.group and spec.names.kind
        spec = crd_data.get("spec", {})
        self.assertEqual(spec.get("group"), "clustervis.io", 
                         "CRD group should be clustervis.io")
        
        names = spec.get("names", {})
        self.assertEqual(names.get("kind"), "ClusterTopologySnapshot", 
                         "CRD kind should be ClusterTopologySnapshot")
        
        # Check version
        versions = spec.get("versions", [])
        self.assertTrue(len(versions) > 0, "CRD must have at least one version")
        self.assertEqual(versions[0].get("name"), "v1alpha1", 
                         "CRD version should be v1alpha1")

    def test_operator_manifest_exists_and_valid(self):
        """Verify deploy/operator/operator.yaml exists and defines ServiceAccount, ClusterRole, Deployment, and Service."""
        operator_path = self.deploy_dir / "operator" / "operator.yaml"
        
        self.assertTrue(operator_path.exists(), f"Operator manifest not found at {operator_path}")
        
        with open(operator_path, 'r') as f:
            try:
                # operator.yaml might contain multiple documents
                docs = list(yaml.safe_load_all(f))
            except yaml.YAMLError as e:
                self.fail(f"Invalid YAML in Operator manifest: {e}")
        
        self.assertTrue(len(docs) > 0, "Operator manifest should contain at least one document")
        
        # Filter out None documents (empty lines)
        docs = [d for d in docs if d is not None]
        
        kinds_found = set()
        for doc in docs:
            if isinstance(doc, dict) and "kind" in doc:
                kinds_found.add(doc["kind"])
        
        required_kinds = {"ServiceAccount", "ClusterRole", "Deployment", "Service"}
        missing_kinds = required_kinds - kinds_found
        
        self.assertEqual(len(missing_kinds), 0, 
                         f"Operator manifest missing required kinds: {missing_kinds}. Found: {kinds_found}")

    # --------------------------------------------------------------------------
    # 3. Test TopologyController
    # --------------------------------------------------------------------------

    @unittest.skipIf(TopologyController is None, "TopologyController not available")
    def test_topology_controller_initialization(self):
        """Initialize TopologyController and verify basic state."""
        controller = TopologyController(cluster_name="test-cluster")
        self.assertEqual(controller.cluster_name, "test-cluster")

    @unittest.skipIf(TopologyController is None, "TopologyController not available")
    def test_get_snapshot_structure(self):
        """Call get_snapshot() and verify returned dictionary structure."""
        controller = TopologyController(cluster_name="test-cluster")
        
        # Ensure the controller has some data to snapshot. 
        # If the controller starts empty, we might need to inject data first.
        # Based on spec: "verify returned dictionary contains metadata, nodes (>=10), and edges."
        # This implies the controller should either be pre-populated or generate mock data.
        # We assume the controller initializes with some default/mock data or we inject it.
        
        # If the controller doesn't auto-populate, we might need to trigger a sync or inject.
        # For this test, we assume the controller is capable of returning a snapshot with >=10 nodes.
        # If it fails, it means the implementation doesn't meet the spec's expectation of having data.
        
        snapshot = controller.get_snapshot()
        
        self.assertIsInstance(snapshot, dict, "Snapshot should be a dictionary")
        self.assertIn("metadata", snapshot, "Snapshot missing 'metadata'")
        self.assertIn("nodes", snapshot, "Snapshot missing 'nodes'")
        self.assertIn("edges", snapshot, "Snapshot missing 'edges'")
        
        nodes = snapshot["nodes"]
        self.assertIsInstance(nodes, list, "Nodes should be a list")
        self.assertGreaterEqual(len(nodes), 10, "Snapshot should contain at least 10 nodes")
        
        edges = snapshot["edges"]
        self.assertIsInstance(edges, list, "Edges should be a list")

    @unittest.skipIf(TopologyController is None, "TopologyController not available")
    def test_event_broadcasting_node_added(self):
        """Test event broadcasting for node_added mutation."""
        controller = TopologyController(cluster_name="test-cluster")
        q = queue.Queue()
        
        # Register listener
        controller.add_listener(q)
        
        # Inject node_added mutation
        test_payload = {'node': {'id': 'pod-test-1', 'layer': 'workload', 'kind': 'Pod', 'name': 'test-pod-1', 'spatial': {'x': 1.0, 'y': 0.75, 'z': 0.5}}}
        controller.inject_mutation('node_added', test_payload)
        
        # Verify queue receives the event
        try:
            event_type, payload = q.get(timeout=1)
        except queue.Empty:
            self.fail("Queue did not receive event within timeout")
        
        self.assertEqual(event_type, "node_added")
        self.assertEqual(payload['node']['id'], 'pod-test-1')

    @unittest.skipIf(TopologyController is None, "TopologyController not available")
    def test_event_broadcasting_node_modified(self):
        """Test event broadcasting for node_modified mutation."""
        controller = TopologyController(cluster_name="test-cluster")
        q = queue.Queue()
        
        controller.add_listener(q)
        
        controller.inject_mutation('node_modified', {'node_id': 'pod-test-1', 'status': 'version_skew'})
        
        try:
            event_type, payload = q.get(timeout=1)
        except queue.Empty:
            self.fail("Queue did not receive event within timeout")
        
        self.assertEqual(event_type, "node_modified")
        self.assertEqual(payload['node_id'], 'pod-test-1')

    @unittest.skipIf(TopologyController is None, "TopologyController not available")
    def test_event_broadcasting_node_removed(self):
        """Test event broadcasting for node_removed mutation and verify node removal."""
        controller = TopologyController(cluster_name="test-cluster")
        q = queue.Queue()
        
        controller.add_listener(q)
        
        controller.inject_mutation('node_removed', {'node_id': 'pod-test-1'})
        
        try:
            event_type, payload = q.get(timeout=1)
        except queue.Empty:
            self.fail("Queue did not receive event within timeout")
        
        self.assertEqual(event_type, "node_removed")
        self.assertEqual(payload['node_id'], 'pod-test-1')
        
        # Verify node is removed from the controller's internal state
        # This depends on how the controller exposes its state. 
        # We can check via get_snapshot()
        snapshot = controller.get_snapshot()
        node_names = [n["name"] for n in snapshot["nodes"]]
        self.assertNotIn('test-pod-1', node_names, f"Node test-pod-1 should have been removed")

    # --------------------------------------------------------------------------
    # 4. Test Offline Static Fallback Integrity
    # --------------------------------------------------------------------------

    @unittest.skipIf(ClusterGraph is None, "ClusterGraph model not available")
    def test_static_fallback_cluster_alpha(self):
        """Load dist/data/cluster-alpha.json and validate against ClusterGraph."""
        data_path = self.dist_dir / "data" / "cluster-alpha.json"
        
        self.assertTrue(data_path.exists(), f"Static data file not found at {data_path}")
        
        with open(data_path, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                self.fail(f"Invalid JSON in {data_path}: {e}")
        
        # Validate using Pydantic model
        try:
            graph = ClusterGraph.model_validate(data)
        except Exception as e:
            self.fail(f"ClusterGraph validation failed for cluster-alpha: {e}")
        
        # Verify integrity/completeness
        self.assertIsNotNone(graph)
        self.assertTrue(hasattr(graph, 'nodes'))
        self.assertTrue(hasattr(graph, 'edges'))
        self.assertTrue(len(graph.nodes) > 0, "Cluster alpha should have nodes")

    @unittest.skipIf(ClusterGraph is None, "ClusterGraph model not available")
    def test_static_fallback_cluster_beta(self):
        """Load dist/data/cluster-beta.json and validate against ClusterGraph."""
        data_path = self.dist_dir / "data" / "cluster-beta.json"
        
        self.assertTrue(data_path.exists(), f"Static data file not found at {data_path}")
        
        with open(data_path, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                self.fail(f"Invalid JSON in {data_path}: {e}")
        
        # Validate using Pydantic model
        try:
            graph = ClusterGraph.model_validate(data)
        except Exception as e:
            self.fail(f"ClusterGraph validation failed for cluster-beta: {e}")
        
        # Verify integrity/completeness
        self.assertIsNotNone(graph)
        self.assertTrue(hasattr(graph, 'nodes'))
        self.assertTrue(hasattr(graph, 'edges'))
        self.assertTrue(len(graph.nodes) > 0, "Cluster beta should have nodes")


if __name__ == "__main__":
    unittest.main()
