"""Unit tests for SPEC-09 pod geometry (TASK-CV-1001).

Covers:
1. calculate_pod_dimensions formula, clamp bounds, and blueprint test
   vectors (micro-sidecar, standard service, in-memory cache, ML worker).
2. extract_pod_requests metrics key precedence and fallback defaults.
3. AutoscalingStatus / KueueWorkloadStatus / PodGeometrySpec defaults,
   serialization / deserialization, and NodeComponent / ClusterGraph wiring.
4. Integration: apply_spatial_layout assigns pod_geometry on the worker deck.
"""

import json
import math
import unittest
from typing import Literal  # noqa: F401  (used in _pod helper annotation)

from src.ingestion.models import (
    AutoscalingStatus,
    KueueWorkloadStatus,
    PodGeometrySpec,
    NodeComponent,
    ClusterGraph,
    ClusterMetadata,
)
from src.ingestion.layout import (
    POD_HEIGHT_MIN,
    POD_HEIGHT_MAX,
    POD_RADIUS_MIN,
    POD_RADIUS_MAX,
    POD_DEFAULT_CPU_CORES,
    POD_DEFAULT_MEMORY_GIB,
    calculate_pod_dimensions,
    extract_pod_requests,
    assign_pod_geometry,
    apply_spatial_layout,
)

EPS = 1e-3


def _reference_dims(cpu: float, mem: float) -> tuple:
    """Independent re-derivation of the SPEC-09 §3.1 formulae."""
    h = min(2.60, max(0.40, 0.40 + 0.35 * math.sqrt(cpu)))
    r = min(0.90, max(0.20, 0.20 + 0.12 * math.log2(max(1.0, mem))))
    return (h, r)


def _pod(name: str, metrics=None, layer: "Literal['workload', 'framework']" = "workload",
         kind: str = "Pod") -> NodeComponent:
    return NodeComponent(
        id=f"pod-{name}",
        layer=layer,
        kind=kind,
        name=name,
        status="Healthy",
        metrics=metrics or {},
    )


# ---------------------------------------------------------------------------
# 1. calculate_pod_dimensions
# ---------------------------------------------------------------------------

class TestCalculatePodDimensions(unittest.TestCase):

    def test_clamp_constants_match_spec(self):
        self.assertEqual(POD_HEIGHT_MIN, 0.40)
        self.assertEqual(POD_HEIGHT_MAX, 2.60)
        self.assertEqual(POD_RADIUS_MIN, 0.20)
        self.assertEqual(POD_RADIUS_MAX, 0.90)

    def test_formula_against_reference(self):
        # Property-style sweep across a resource grid.
        for cpu in (0.01, 0.05, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 64.0, 1024.0):
            for mem in (0.0, 0.031, 0.5, 1.0, 2.0, 8.0, 32.0, 128.0, 4096.0):
                h, r = calculate_pod_dimensions(cpu, mem)
                rh, rr = _reference_dims(cpu, mem)
                self.assertAlmostEqual(h, rh, delta=EPS, msg=f"height cpu={cpu} mem={mem}")
                self.assertAlmostEqual(r, rr, delta=EPS, msg=f"radius cpu={cpu} mem={mem}")

    def test_micro_sidecar_vector(self):
        # 10m CPU, 32MiB RAM (~0.03125 GiB) -> slender needle.
        h, r = calculate_pod_dimensions(0.01, 0.031)
        self.assertAlmostEqual(h, 0.435, delta=EPS)
        self.assertAlmostEqual(r, 0.200, delta=EPS)
        self.assertLess(h, 0.60)
        self.assertEqual(r, POD_RADIUS_MIN)  # memory < 1 GiB clamps to floor

    def test_standard_service_vector(self):
        # 500m CPU, 2 GiB -> balanced capsule.
        h, r = calculate_pod_dimensions(0.5, 2.0)
        self.assertAlmostEqual(h, 0.647, delta=EPS)  # blueprint: H = 0.647
        self.assertAlmostEqual(r, 0.320, delta=EPS)

    def test_in_memory_cache_vector(self):
        # 500m CPU, 32 GiB -> wide squat canister.
        h, r = calculate_pod_dimensions(0.5, 32.0)
        self.assertAlmostEqual(h, 0.647, delta=EPS)  # blueprint: H = 0.647
        self.assertAlmostEqual(r, 0.800, delta=EPS)

    def test_ml_worker_vector(self):
        # 8 cores, 32 GiB -> commanding cylinder.
        h, r = calculate_pod_dimensions(8.0, 32.0)
        self.assertAlmostEqual(h, 1.390, delta=EPS)
        self.assertAlmostEqual(r, 0.800, delta=EPS)

    def test_height_clamps(self):
        # sqrt saturation: enormous CPU pins at 2.60.
        self.assertEqual(calculate_pod_dimensions(10_000_000.0, 1.0)[0], POD_HEIGHT_MAX)
        # Negative CPU is floored (no NaN, no below-min height).
        h, _ = calculate_pod_dimensions(-5.0, 1.0)
        self.assertEqual(h, POD_HEIGHT_MIN)
        # Zero CPU sits exactly on the floor constant.
        self.assertEqual(calculate_pod_dimensions(0.0, 1.0)[0], POD_HEIGHT_MIN)

    def test_radius_clamps(self):
        # log2 saturation: enormous memory pins at 0.90.
        self.assertEqual(calculate_pod_dimensions(1.0, 10_000_000.0)[1], POD_RADIUS_MAX)
        # Memory below 1 GiB uses max(1, mem) -> radius floor.
        self.assertEqual(calculate_pod_dimensions(1.0, 0.0)[1], POD_RADIUS_MIN)
        self.assertEqual(calculate_pod_dimensions(1.0, -3.0)[1], POD_RADIUS_MIN)
        # Exactly 1 GiB is the log2 inflection (radius = 0.20).
        self.assertAlmostEqual(calculate_pod_dimensions(1.0, 1.0)[1], 0.20, delta=EPS)

    def test_monotonicity(self):
        prev_h = 0.0
        prev_r = 0.0
        for cpu in (0.1, 0.5, 1, 2, 4, 8, 16, 32):
            h = calculate_pod_dimensions(cpu, 4.0)[0]
            self.assertGreaterEqual(h, prev_h)
            prev_h = h
        for mem in (0.1, 0.5, 1, 2, 2, 8, 16, 64):
            r = calculate_pod_dimensions(1.0, mem)[1]
            self.assertGreaterEqual(r, prev_r)
            prev_r = r

    def test_capsule_length_contract(self):
        # THREE.CapsuleGeometry(radius, length) spans length + 2*radius;
        # for every legal (H, R), length = max(0.02, H - 2R) keeps it valid
        # and never negative even when the radius floor dominates the CPU floor.
        h, r = calculate_pod_dimensions(0.0, 4096.0)  # H=0.40, R=0.90
        length = max(0.02, h - 2 * r)
        self.assertGreaterEqual(length, 0.02)
        self.assertAlmostEqual(length + 2 * r, 2 * r + 0.02, delta=EPS)


# ---------------------------------------------------------------------------
# 2. extract_pod_requests
# ---------------------------------------------------------------------------

class TestExtractPodRequests(unittest.TestCase):

    def test_defaults_when_empty(self):
        cpu, mem = extract_pod_requests({})
        self.assertEqual(cpu, POD_DEFAULT_CPU_CORES)
        self.assertEqual(mem, POD_DEFAULT_MEMORY_GIB)

    def test_request_keys_preferred(self):
        cpu, mem = extract_pod_requests({
            "cpu_request_cores": 2.5,
            "memory_request_gib": 8.0,
            "cpu_cores": 16.0,        # capacity keys must NOT win
            "memory_gib": 64.0,
        })
        self.assertEqual(cpu, 2.5)
        self.assertEqual(mem, 8.0)

    def test_capacity_key_fallback(self):
        cpu, mem = extract_pod_requests({"cpu_cores": 4, "memory_gib": 16})
        self.assertEqual(cpu, 4.0)
        self.assertEqual(mem, 16.0)

    def test_mixed_and_bad_values(self):
        cpu, mem = extract_pod_requests({"cpu_request_cores": "0.25", "memory_gib": "not-a-number"})
        self.assertEqual(cpu, 0.25)          # numeric strings coerce
        self.assertEqual(mem, POD_DEFAULT_MEMORY_GIB)  # bad value -> default

    def test_none_value_falls_through(self):
        cpu, mem = extract_pod_requests({"cpu_request_cores": None, "cpu_cores": 3.0,
                                         "memory_request_gib": None, "memory_gib": 2.0})
        self.assertEqual(cpu, 3.0)
        self.assertEqual(mem, 2.0)


# ---------------------------------------------------------------------------
# 3. Models: defaults, serialization, wiring
# ---------------------------------------------------------------------------

class TestAutoscalingStatus(unittest.TestCase):

    def test_defaults(self):
        s = AutoscalingStatus()
        self.assertFalse(s.has_vpa)
        self.assertFalse(s.is_resizing_in_place)
        self.assertFalse(s.has_hpa)
        self.assertEqual(s.current_replicas, 1)
        self.assertEqual(s.desired_replicas, 1)
        self.assertIsNone(s.vpa_target_cpu)
        self.assertIsNone(s.target_metric)

    def test_roundtrip(self):
        s = AutoscalingStatus(
            has_vpa=True, vpa_target_cpu="2", vpa_target_memory="4Gi",
            is_resizing_in_place=True,
            has_hpa=True, current_replicas=3, desired_replicas=6,
            target_metric="cpu: 70%",
        )
        payload = json.loads(s.model_dump_json())
        self.assertTrue(payload["is_resizing_in_place"])
        self.assertEqual(payload["desired_replicas"], 6)
        restored = AutoscalingStatus.model_validate(payload)
        self.assertEqual(restored, s)


class TestKueueWorkloadStatus(unittest.TestCase):

    def test_defaults(self):
        w = KueueWorkloadStatus(
            workload_uid="uid-1", workload_name="ray-finetune-job",
            local_queue="ml-bq", cluster_queue="batch-ai",
        )
        self.assertFalse(w.is_admitted)
        self.assertEqual(w.admission_checks, [])
        self.assertEqual(w.pod_uids, [])
        self.assertEqual(w.total_cpu_requested, 0.0)
        self.assertEqual(w.total_memory_gib_requested, 0.0)
        self.assertEqual(w.total_gpu_requested, 0)
        self.assertEqual(w.phase, "Admissible")
        self.assertEqual(w.namespace, "default")

    def test_roundtrip_with_admission_checks(self):
        w = KueueWorkloadStatus(
            workload_uid="uid-2", workload_name="mpi-job", namespace="ml",
            local_queue="lq", cluster_queue="cq", is_admitted=True,
            admission_checks=[{"reason": "AdmittedByTest", "message": "quota reserved"}],
            pod_uids=["p1", "p2", "p3", "p4"],
            total_cpu_requested=64.0, total_memory_gib_requested=256.0,
            total_gpu_requested=8, phase="Admitted",
        )
        payload = json.loads(w.model_dump_json())
        self.assertEqual(len(payload["pod_uids"]), 4)
        self.assertEqual(payload["total_gpu_requested"], 8)
        restored = KueueWorkloadStatus.model_validate(payload)
        self.assertEqual(restored, w)

    def test_phase_literal_validation(self):
        with self.assertRaises(ValueError):
            KueueWorkloadStatus(
                workload_uid="u", workload_name="n", local_queue="l",
                cluster_queue="c", phase="Teleporting",
            )


class TestPodGeometrySpec(unittest.TestCase):

    def test_defaults(self):
        g = PodGeometrySpec()
        self.assertEqual(g.height, 0.6)
        self.assertEqual(g.radius, 0.3)
        self.assertEqual(g.color_tint, "#4FC3F7")
        self.assertFalse(g.is_pending)
        self.assertIsNone(g.staging_track_x)
        self.assertIsNone(g.karpenter_target_node_claim)

    def test_roundtrip(self):
        g = PodGeometrySpec(
            height=1.39, radius=0.8, color_tint="#FFA726",
            is_pending=True, staging_track_x=-18.5,
            karpenter_target_node_claim="nodeclaim-abc",
        )
        payload = json.loads(g.model_dump_json())
        self.assertEqual(payload["staging_track_x"], -18.5)
        restored = PodGeometrySpec.model_validate(payload)
        self.assertEqual(restored, g)


class TestNodeComponentAndGraphWiring(unittest.TestCase):

    def test_new_fields_default_absent(self):
        n = _pod("plain")
        self.assertIsNone(n.pod_geometry)
        self.assertIsNone(n.autoscaling)

    def test_node_roundtrip_with_nested_models(self):
        n = _pod("vpa-app", metrics={"cpu_request_cores": 1.0, "memory_request_gib": 2.0})
        n.pod_geometry = PodGeometrySpec(height=0.75, radius=0.32)
        n.autoscaling = AutoscalingStatus(has_vpa=True, vpa_target_cpu="4")
        restored = NodeComponent.model_validate(json.loads(n.model_dump_json()))
        self.assertIsNotNone(restored.pod_geometry)
        self.assertEqual(restored.pod_geometry.height, 0.75)
        self.assertTrue(restored.autoscaling.has_vpa)
        self.assertEqual(restored.autoscaling.vpa_target_cpu, "4")

    def test_graph_kueue_workloads_default_and_roundtrip(self):
        meta = ClusterMetadata(
            cluster_name="c", kubernetes_version="v1.31.0", timestamp="2026-10-03T00:00:00Z",
        )
        g = ClusterGraph(metadata=meta)
        self.assertEqual(g.kueue_workloads, [])

        g.kueue_workloads.append(KueueWorkloadStatus(
            workload_uid="w1", workload_name="gang", local_queue="lq",
            cluster_queue="cq", is_admitted=True, pod_uids=["a", "p-1"],
        ))
        node = _pod("a", metrics={"cpu_request_cores": 2.0, "memory_request_gib": 4.0})
        g.nodes.append(node)

        blob = json.loads(g.model_dump_json())
        self.assertIn("kueue_workloads", blob)
        self.assertEqual(len(blob["kueue_workloads"]), 1)
        self.assertTrue(blob["kueue_workloads"][0]["is_admitted"])
        restored = ClusterGraph.model_validate(blob)
        self.assertEqual(restored.kueue_workloads[0].workload_uid, "w1")
        self.assertEqual(len(restored.nodes), 1)

    def test_graph_from_legacy_snapshot_without_new_keys(self):
        # A SPEC-08 era snapshot must still validate with empty SPEC-09 fields.
        meta = ClusterMetadata(
            cluster_name="legacy", kubernetes_version="v1.30.0", timestamp="2026-01-01T00:00:00Z",
        )
        legacy = {
            "metadata": meta.model_dump(),
            "nodes": [],
            "edges": [],
        }
        g = ClusterGraph.model_validate(legacy)
        self.assertEqual(g.kueue_workloads, [])
        self.assertEqual(len(g.nodes), 0)


# ---------------------------------------------------------------------------
# 4. Layout integration
# ---------------------------------------------------------------------------

class TestLayoutIntegration(unittest.TestCase):

    def test_worker_deck_pods_get_geometry(self):
        nodes = [
            NodeComponent(id="n1", layer="node", kind="Node", name="worker-1"),
            _pod("api-7d9-f2x", metrics={"cpu_request_cores": 0.5, "memory_request_gib": 2.0}),
            _pod("redis-0", metrics={"cpu_request_cores": 0.25, "memory_request_gib": 32.0}),
            _pod("ml-trainer", metrics={"cpu_request_cores": 8.0, "memory_request_gib": 32.0}),
            _pod("no-requests"),
        ]
        laid = apply_spatial_layout(nodes)

        api = next(n for n in laid if n.name == "api-7d9-f2x")
        h, r = calculate_pod_dimensions(0.5, 2.0)
        self.assertIsNotNone(api.pod_geometry)
        self.assertAlmostEqual(api.pod_geometry.height, h, delta=EPS)
        self.assertAlmostEqual(api.pod_geometry.radius, r, delta=EPS)

        redis = next(n for n in laid if n.name == "redis-0")
        self.assertAlmostEqual(redis.pod_geometry.radius, 0.800, delta=EPS)
        # redis-0 lands on the Cache_Redis asset but keeps proportional dims
        self.assertEqual(redis.spatial.asset_type, "Cache_Redis")

        trainer = next(n for n in laid if n.name == "ml-trainer")
        self.assertAlmostEqual(trainer.pod_geometry.height, 1.390, delta=EPS)

        plain = next(n for n in laid if n.name == "no-requests")
        dh, pr = calculate_pod_dimensions(POD_DEFAULT_CPU_CORES, POD_DEFAULT_MEMORY_GIB)
        self.assertAlmostEqual(plain.pod_geometry.height, dh, delta=EPS)
        self.assertAlmostEqual(plain.pod_geometry.radius, pr, delta=EPS)
        self.assertFalse(plain.pod_geometry.is_pending)

    def test_geometry_survives_json_export_cycle(self):
        pod = _pod("round-tripper", metrics={"cpu_cores": 2, "memory_gib": 8})
        assign_pod_geometry(pod)
        restored = NodeComponent.model_validate(json.loads(pod.model_dump_json()))
        self.assertIsNotNone(restored.pod_geometry)
        self.assertAlmostEqual(restored.pod_geometry.height,
                               calculate_pod_dimensions(2.0, 8.0)[0], delta=EPS)

    def test_pending_detection(self):
        pending = _pod("unschedulable", metrics={"scheduled": False})
        g1 = assign_pod_geometry(pending)
        self.assertTrue(g1.is_pending)

        flagged = _pod("flagged", metrics={"pending": True})
        self.assertTrue(assign_pod_geometry(flagged).is_pending)

        scheduled = _pod("fine", metrics={"scheduled": True})
        self.assertFalse(assign_pod_geometry(scheduled).is_pending)

    def test_assign_pod_geometry_matches_dimensions_function(self):
        pod = _pod("formula-check", metrics={"cpu_request_cores": 4.0, "memory_request_gib": 16.0})
        g = assign_pod_geometry(pod)
        h, r = calculate_pod_dimensions(4.0, 16.0)
        self.assertEqual(g.height, h)
        self.assertEqual(g.radius, r)
        self.assertIs(pod.pod_geometry, g)

    def test_non_pod_components_untouched(self):
        # Control-plane components routed to other tiers must not receive
        # pod geometry from the sweep.
        nodes = [
            NodeComponent(id="api", layer="control-plane", kind="APIServer",
                          name="kube-apiserver"),
        ]
        laid = apply_spatial_layout(nodes)
        self.assertIsNone(laid[0].pod_geometry)


if __name__ == "__main__":
    unittest.main()
