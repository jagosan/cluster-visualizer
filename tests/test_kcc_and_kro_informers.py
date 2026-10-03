"""Unit tests for the SPEC-08 KCC / kro informers (src/operator/kcc_mapper.py)
and the TopologyController subterranean mutation plumbing
(src/operator/controller.py).

Covers:
1. parse_kcc_resource: SQLInstance / StorageBucket / PubSubTopic / RedisInstance
   category mapping, and kro-managed composites -> managed_by='kro'.
2. parse_node_machine_shape: GPU labels + Ki quantities, karpenter spot
   capacity-type.
3. TopologyController.get_snapshot() subterranean strata with valid
   coordinates, and inject_mutation() for the four subterranean events.
"""

import math
import queue
import unittest
from typing import Any, Dict

from src.ingestion.models import (
    CloudProvider,
    MachineShape,
    ManagedServiceCategory,
    RemoteServiceResource,
)
from src.ingestion.layout import ELEVATION_TIERS
from src.operator.kcc_mapper import parse_kcc_resource, parse_node_machine_shape
from src.operator.controller import TopologyController


# ---------------------------------------------------------------------------
# Raw-manifest builders (shaped like ConfigMap-dumped CRDs / Node objects)
# ---------------------------------------------------------------------------

def _raw_crd(group: str, version: str, kind: str, name: str,
             namespace: str = "default",
             spec: Dict[str, Any] | None = None,
             annotations: Dict[str, str] | None = None) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {"name": name, "namespace": namespace}
    if annotations:
        metadata["annotations"] = dict(annotations)
    return {
        "apiVersion": f"{group}/{version}",
        "kind": kind,
        "metadata": metadata,
        "spec": dict(spec or {}),
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }


def _raw_node(name: str, labels: Dict[str, str],
              capacity: Dict[str, str],
              allocatable: Dict[str, str] | None = None) -> Dict[str, Any]:
    node: Dict[str, Any] = {
        "apiVersion": "v1",
        "kind": "Node",
        "metadata": {"name": name, "labels": dict(labels)},
        "status": {"capacity": dict(capacity)},
    }
    if allocatable is not None:
        node["status"]["allocatable"] = dict(allocatable)
    return node


# ---------------------------------------------------------------------------
# 1. parse_kcc_resource — KCC category map and kro detection
# ---------------------------------------------------------------------------

class TestParseKccResourceCategories(unittest.TestCase):

    def test_sql_instance_maps_to_database_relational(self):
        raw = _raw_crd("sql.cnrm.cloud.google.com", "v1beta1", "SQLInstance",
                       "sql-prod",
                       spec={"tier": "db-custom-4-16384"},
                       )
        raw["status"]["selfLink"] = (
            "https://sqladmin.googleapis.com/sql/projects/demo/instances/sql-prod")
        res = parse_kcc_resource(raw)
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res.category, ManagedServiceCategory.DATABASE_RELATIONAL)
        self.assertEqual(res.managed_by, "kcc")
        self.assertEqual(res.provider, CloudProvider.GCP)
        self.assertEqual(res.cr_group, "sql.cnrm.cloud.google.com")
        self.assertEqual(res.cr_kind, "SQLInstance")
        self.assertEqual(res.id, "sql.cnrm.cloud.google.com/SQLInstance/default/sql-prod")
        self.assertEqual(res.status_phase, "Ready")
        self.assertEqual(res.endpoint, raw["status"]["selfLink"])

    def test_storage_bucket_maps_to_object_storage(self):
        raw = _raw_crd("storage.cnrm.cloud.google.com", "v1beta1",
                       "StorageBucket", "media-vault", spec={"location": "US"})
        res = parse_kcc_resource(raw)
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res.category, ManagedServiceCategory.OBJECT_STORAGE)
        self.assertEqual(res.managed_by, "kcc")
        self.assertEqual(res.name, "media-vault")

    def test_pubsub_topic_maps_to_messaging_eventing(self):
        raw = _raw_crd("pubsub.cnrm.cloud.google.com", "v1beta1",
                       "PubSubTopic", "events-feed")
        res = parse_kcc_resource(raw)
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res.category, ManagedServiceCategory.MESSAGING_EVENTING)
        self.assertEqual(res.managed_by, "kcc")

    def test_redis_instance_maps_to_cache_in_memory(self):
        raw = _raw_crd("redis.cnrm.cloud.google.com", "v1beta1",
                       "RedisInstance", "session-cache",
                       spec={"tier": "STANDARD_HA", "memoryGb": 16})
        raw["status"] = {"phase": "Ready", "host": "10.0.42.72"}
        res = parse_kcc_resource(raw)
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res.category, ManagedServiceCategory.CACHE_IN_MEMORY)
        self.assertEqual(res.managed_by, "kcc")
        self.assertEqual(res.status_phase, "Ready")
        # Endpoint resolves via the canonical status fields (selfLink/endpoint/
        # ipAddress); a bare status.host is not part of that contract.
        self.assertIsNone(res.endpoint)
        raw["status"]["ipAddress"] = "10.0.42.72"
        res2 = parse_kcc_resource(raw)
        assert res2 is not None
        self.assertEqual(res2.endpoint, "10.0.42.72")

    def test_unmapped_kind_without_kro_returns_none(self):
        raw = _raw_crd("example.com", "v1", "Widget", "not-managed")
        self.assertIsNone(parse_kcc_resource(raw))

    def test_manifest_without_name_returns_none(self):
        raw = _raw_crd("sql.cnrm.cloud.google.com", "v1beta1", "SQLInstance", "")
        self.assertIsNone(parse_kcc_resource(raw))


class TestParseKroComposite(unittest.TestCase):

    def test_kro_api_group_marks_managed_by_kro(self):
        raw = _raw_crd("kro.run", "v1alpha1", "AppManifold",
                       "kro-app-manifold", namespace="kro-system")
        res = parse_kcc_resource(raw)
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res.managed_by, "kro")
        # Unknown kro kind falls back to the canonical default category.
        self.assertEqual(res.category, ManagedServiceCategory.DATABASE_RELATIONAL)
        self.assertEqual(res.cr_group, "kro.run")
        self.assertEqual(res.id, "kro.run/AppManifold/kro-system/kro-app-manifold")

    def test_kro_annotation_marks_managed_by_kro(self):
        raw = _raw_crd("example.com", "v1", "Widget",
                       "kro-rendered-child",
                       annotations={"kro.run/resource-graph-name": "widget-graph"})
        res = parse_kcc_resource(raw)
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res.managed_by, "kro")

    def test_kro_parent_id_from_annotation(self):
        raw = _raw_crd("kro.run", "v1alpha1", "AppDB", "child-db",
                       annotations={"kro.run/parent-resource": "app-manifold-root"})
        res = parse_kcc_resource(raw)
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res.managed_by, "kro")
        self.assertEqual(res.kro_parent_id, "app-manifold-root")

    def test_kro_parent_id_from_spec_parent_ref(self):
        raw = _raw_crd("kro.run", "v1alpha1", "AppDB", "child-db",
                       spec={"parentRef": {"name": "spec-root"}})
        res = parse_kcc_resource(raw)
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res.managed_by, "kro")
        self.assertEqual(res.kro_parent_id, "spec-root")


# ---------------------------------------------------------------------------
# 2. parse_node_machine_shape — chassis normalization
# ---------------------------------------------------------------------------

class TestParseNodeMachineShape(unittest.TestCase):

    def test_gpu_node_labels_and_ki_memory(self):
        node = _raw_node(
            "gpu-node-1",
            labels={
                "node.kubernetes.io/instance-type": "g2-standard-16",
                "cloud.google.com/gke-accelerator": "nvidia-l4",
                "cloud.google.com/gke-nodepool": "gpu-pool",
                "topology.kubernetes.io/zone": "us-central1-c",
            },
            capacity={"cpu": "16", "memory": "66724464Ki", "nvidia.com/gpu": "1"},
            allocatable={"cpu": "15930m", "memory": "64536208Ki", "nvidia.com/gpu": "1"},
        )
        shape = parse_node_machine_shape(node)
        self.assertIsInstance(shape, MachineShape)
        self.assertEqual(shape.node_name, "gpu-node-1")
        self.assertEqual(shape.accelerator_type, "nvidia-l4")
        self.assertEqual(shape.accelerator_count, 1)
        self.assertEqual(shape.instance_type, "g2-standard-16")
        self.assertEqual(shape.compute_class, "gpu-pool")
        self.assertEqual(shape.zone, "us-central1-c")
        self.assertEqual(shape.capacity_type, "on-demand")
        # allocatable overrides capacity: 64536208Ki -> GiB, millicores -> cores.
        self.assertAlmostEqual(shape.memory_gib, 64536208 / 1024**2, places=4)
        self.assertEqual(shape.vcpus, 16)

    def test_karpenter_spot_capacity_type(self):
        node = _raw_node(
            "spot-node-1",
            labels={
                "node.kubernetes.io/instance-type": "n2-standard-8",
                "karpenter.sh/capacity-type": "spot",
                "karpenter.sh/nodepool": "spot-pool",
                "topology.kubernetes.io/zone": "us-central1-a",
            },
            capacity={"cpu": "8", "memory": "32768Mi"},
            allocatable={"cpu": "7910m", "memory": "31460Mi"},
        )
        shape = parse_node_machine_shape(node)
        self.assertEqual(shape.capacity_type, "spot")
        self.assertEqual(shape.compute_class, "spot-pool")
        self.assertEqual(shape.accelerator_count, 0)
        self.assertIsNone(shape.accelerator_type)
        self.assertAlmostEqual(shape.memory_gib, 31460 / 1024, places=4)

    def test_gpu_count_without_accelerator_label_gets_generic_type(self):
        node = _raw_node(
            "mystery-gpu",
            labels={"node.kubernetes.io/instance-type": "custom-gpu"},
            capacity={"cpu": "4", "memory": "16Gi", "nvidia.com/gpu": "2"},
        )
        shape = parse_node_machine_shape(node)
        self.assertEqual(shape.accelerator_count, 2)
        self.assertEqual(shape.accelerator_type, "nvidia-gpu")


# ---------------------------------------------------------------------------
# 3. TopologyController — snapshot strata + subterranean mutation injection
# ---------------------------------------------------------------------------

def _is_finite_vector3(spatial: Any) -> bool:
    if not isinstance(spatial, dict):
        return False
    vals = [spatial.get("x"), spatial.get("y"), spatial.get("z")]
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals)


class TestTopologyControllerSnapshot(unittest.TestCase):

    def setUp(self):
        self.ctrl = TopologyController(cluster_name="test-cluster")

    def tearDown(self):
        self.ctrl.stop()

    def test_snapshot_contains_subterranean_strata_with_coordinates(self):
        snap = self.ctrl.get_snapshot()

        # --- subterranean_resources (Sub-Level B2 vaults) -------------------
        self.assertIn("subterranean_resources", snap)
        vaults = snap["subterranean_resources"]
        self.assertGreaterEqual(len(vaults), 4)
        by_kind = {v["cr_kind"]: v for v in vaults}
        self.assertEqual(by_kind["SQLInstance"]["category"], "database_relational")
        self.assertEqual(by_kind["StorageBucket"]["category"], "object_storage")
        self.assertEqual(by_kind["PubSubTopic"]["category"], "messaging_eventing")
        self.assertEqual(by_kind["RedisInstance"]["category"], "cache_in_memory")
        self.assertEqual(by_kind["AppManifold"]["managed_by"], "kro")
        for v in vaults:
            self.assertTrue(_is_finite_vector3(v["spatial"]),
                            f"vault {v['id']} lacks valid spatial coordinates: {v['spatial']}")
            self.assertEqual(v["spatial"]["y"], ELEVATION_TIERS["cloud_vault"])

        # --- machine_shapes (Sub-Level B1 chassis) ---------------------------
        self.assertIn("machine_shapes", snap)
        shapes = snap["machine_shapes"]
        self.assertGreaterEqual(len(shapes), 2)
        by_node = {s["node_name"]: s for s in shapes}
        gpu = by_node["gpu-node-1"]
        self.assertEqual(gpu["accelerator_type"], "nvidia-l4")
        self.assertEqual(gpu["accelerator_count"], 1)
        self.assertEqual(by_node["spot-node-1"]["capacity_type"], "spot")
        # Docked chassis footprints must be positive, finite numbers.
        for s in shapes:
            for dim in ("chassis_width", "chassis_depth"):
                val = s[dim]
                self.assertIsInstance(val, (int, float))
                self.assertTrue(math.isfinite(val) and val > 0,
                                f"{s['node_name']} has invalid {dim}={val}")


class TestTopologyControllerMutations(unittest.TestCase):

    def setUp(self):
        self.ctrl = TopologyController(cluster_name="mutate-cluster")
        self.q: queue.Queue = queue.Queue()
        self.ctrl.add_listener(self.q)
        # Seed the store so removal/modification targets exist.
        self.ctrl.get_snapshot()
        while not self.q.empty():
            self.q.get_nowait()

    def tearDown(self):
        self.ctrl.remove_listener(self.q)
        self.ctrl.stop()

    def _drain(self):
        events = []
        while not self.q.empty():
            events.append(self.q.get_nowait())
        return events

    def test_subterranean_resource_added_from_raw_crd(self):
        raw = _raw_crd("spanner.cnrm.cloud.google.com", "v1",
                       "SpannerInstance", "ledger-instance")
        self.ctrl.inject_mutation("subterranean_resource_added", {"resource": raw})

        rid = "spanner.cnrm.cloud.google.com/SpannerInstance/default/ledger-instance"
        self.assertIn(rid, self.ctrl.subterranean_resources)
        stored = self.ctrl.subterranean_resources[rid]
        self.assertEqual(stored.category, ManagedServiceCategory.DATABASE_RELATIONAL)
        # Layout reapplied on mutation: spatial coords assigned.
        self.assertTrue(_is_finite_vector3(stored.spatial))

        events = self._drain()
        names = [name for name, _ in events]
        self.assertIn("subterranean_resource_added", names)
        payload = dict(events[names.index("subterranean_resource_added")][1])
        self.assertEqual(payload["resource"]["id"], rid)
        self.assertIn("timestamp", payload)

    def test_subterranean_resource_removed(self):
        rid = "storage.cnrm.cloud.google.com/StorageBucket/default/media-vault"
        self.assertIn(rid, self.ctrl.subterranean_resources)

        self.ctrl.inject_mutation("subterranean_resource_removed", {"resource_id": rid})
        self.assertNotIn(rid, self.ctrl.subterranean_resources)

        events = self._drain()
        names = [name for name, _ in events]
        self.assertIn("subterranean_resource_removed", names)

    def test_subterranean_resource_modified(self):
        rid = "pubsub.cnrm.cloud.google.com/PubSubTopic/default/events-feed"
        self.assertIn(rid, self.ctrl.subterranean_resources)

        self.ctrl.inject_mutation("subterranean_resource_modified", {
            "resource_id": rid, "status_phase": "Degraded",
        })
        self.assertEqual(
            self.ctrl.subterranean_resources[rid].status_phase, "Degraded")

        # fields= dict path also applies arbitrary attribute updates.
        self.ctrl.inject_mutation("subterranean_resource_modified", {
            "resource_id": rid, "fields": {"display_name": "events-feed-2"},
        })
        self.assertEqual(
            self.ctrl.subterranean_resources[rid].display_name, "events-feed-2")

        events = self._drain()
        mod_events = [p for name, p in events if name == "subterranean_resource_modified"]
        self.assertEqual(len(mod_events), 2)
        self.assertEqual(mod_events[-1]["resource"]["display_name"], "events-feed-2")

    def test_machine_shape_updated_from_raw_node_object(self):
        node = _raw_node(
            "chassis-new",
            labels={
                "node.kubernetes.io/instance-type": "c2-standard-4",
                "karpenter.sh/capacity-type": "spot",
                "topology.kubernetes.io/zone": "us-central1-b",
            },
            capacity={"cpu": "4", "memory": "8192Mi"},
        )
        self.ctrl.inject_mutation("machine_shape_updated", {"shape": node})

        self.assertIn("chassis-new", self.ctrl.machine_shapes)
        shape = self.ctrl.machine_shapes["chassis-new"]
        self.assertEqual(shape.capacity_type, "spot")
        self.assertAlmostEqual(shape.memory_gib, 8.0, places=4)
        self.assertEqual(shape.zone, "us-central1-b")

        events = self._drain()
        names = [name for name, _ in events]
        self.assertIn("machine_shape_updated", names)

        # Snapshot must carry the new chassis through to the client payload.
        snap = self.ctrl.get_snapshot()
        self.assertIn("chassis-new", {s["node_name"] for s in snap["machine_shapes"]})

    def test_machine_shape_updated_from_model_dict(self):
        shape_dict = MachineShape(node_name="chassis-dict",
                                  instance_type="n2-standard-4",
                                  vcpus=4, memory_gib=8.0).model_dump()
        self.ctrl.inject_mutation("machine_shape_updated",
                                  {"machine_shape": shape_dict})
        self.assertIn("chassis-dict", self.ctrl.machine_shapes)


if __name__ == "__main__":
    unittest.main()
