"""Unit tests for SPEC-09 VPA morphing & HPA lateral dynamics (TASK-CV-1002).

Covers:
1. parse_resource_quantity: Kubernetes cpu/memory quantity parsing.
2. vpa_morph_target / vpa_morph_dimensions: recommendation-differs detection
   and tween endpoint math (SPEC-09 §3.2).
3. hpa_scale_out_delta / hpa_lateral_path: scale-out spawn count and
   conveyor intake→slot geometry (SPEC-09 §3.3).
4. TopologyController event wiring: autoscaling_updated fan-out into
   vpa_recommendation / vpa_resize_committed / hpa_scale_out SSE events.
5. AutoscalingStatus model round-trip with controller serialization.
"""

import queue
import unittest

from src.ingestion.layout import (
    CENTRAL_RISER_X,
    CENTRAL_RISER_Z,
    DECK_INTAKE_OFFSET_X,
    HPA_DISPATCH_PULSE_MS,
    HPA_LATERAL_SLIDE_MS,
    POD_X_STAGGER,
    SUPERVISOR_FLOOR_Y,
    VPA_MORPH_DURATION_MS,
    apply_spatial_layout,
    hpa_lateral_path,
    hpa_scale_out_delta,
    parse_resource_quantity,
    vpa_morph_dimensions,
    vpa_morph_target,
)
from src.ingestion.models import AutoscalingStatus, NodeComponent
from src.operator.controller import TopologyController

EPS = 1e-6


def _pod(name: str, metrics=None, autoscaling=None) -> NodeComponent:
    return NodeComponent(
        id=f"ns/{name}",
        layer="workload",
        kind="Pod",
        name=name,
        status="Healthy",
        metrics=dict(metrics or {}),
        autoscaling=autoscaling,
    )


# ---------------------------------------------------------------------------
# 1. parse_resource_quantity
# ---------------------------------------------------------------------------

class TestParseResourceQuantity(unittest.TestCase):

    def test_cpu_millicores_and_cores(self):
        self.assertAlmostEqual(parse_resource_quantity("500m", "cpu"), 0.5, delta=EPS)
        self.assertAlmostEqual(parse_resource_quantity("10m", "cpu"), 0.01, delta=EPS)
        self.assertAlmostEqual(parse_resource_quantity("2", "cpu"), 2.0, delta=EPS)
        self.assertAlmostEqual(parse_resource_quantity(2, "cpu"), 2.0, delta=EPS)
        self.assertAlmostEqual(parse_resource_quantity("1.5", "cpu"), 1.5, delta=EPS)

    def test_memory_suffixes(self):
        self.assertAlmostEqual(parse_resource_quantity("512Mi", "memory"), 0.5, delta=EPS)
        self.assertAlmostEqual(parse_resource_quantity("4Gi", "memory"), 4.0, delta=EPS)
        self.assertAlmostEqual(parse_resource_quantity("1Ti", "memory"), 1024.0, delta=EPS)
        self.assertAlmostEqual(parse_resource_quantity("1024Ki", "memory"), 0.0009765625, delta=1e-9)
        # Bare number interpreted as GiB.
        self.assertAlmostEqual(parse_resource_quantity("8", "memory"), 8.0, delta=EPS)

    def test_absent_and_garbage(self):
        self.assertIsNone(parse_resource_quantity(None, "cpu"))
        self.assertIsNone(parse_resource_quantity("", "cpu"))
        self.assertIsNone(parse_resource_quantity("   ", "memory"))
        self.assertIsNone(parse_resource_quantity("banana", "cpu"))
        self.assertIsNone(parse_resource_quantity("abcGi", "memory"))
        self.assertIsNone(parse_resource_quantity("m", "cpu"))


# ---------------------------------------------------------------------------
# 2. VPA morph target resolution (SPEC-09 §3.2)
# ---------------------------------------------------------------------------

class TestVpaMorphTarget(unittest.TestCase):

    def test_no_vpa_no_target(self):
        pod = _pod("plain", metrics={"cpu_request_cores": 1.0, "memory_request_gib": 2.0})
        self.assertIsNone(vpa_morph_target(pod))
        self.assertIsNone(vpa_morph_dimensions(pod))

    def test_vpa_without_recommendation_no_target(self):
        pod = _pod(
            "ghostless",
            metrics={"cpu_request_cores": 1.0, "memory_request_gib": 2.0},
            autoscaling=AutoscalingStatus(has_vpa=True),
        )
        self.assertIsNone(vpa_morph_target(pod))

    def test_matching_recommendation_no_target(self):
        # Recommendation equals current requests -> no ghost hull, no morph.
        pod = _pod(
            "satisfied",
            metrics={"cpu_request_cores": 2.0, "memory_request_gib": 4.0},
            autoscaling=AutoscalingStatus(
                has_vpa=True, vpa_target_cpu="2", vpa_target_memory="4Gi"
            ),
        )
        self.assertIsNone(vpa_morph_target(pod))
        self.assertIsNone(vpa_morph_dimensions(pod))

    def test_differing_recommendation_resolves_target(self):
        pod = _pod(
            "starving",
            metrics={"cpu_request_cores": 0.5, "memory_request_gib": 1.0},
            autoscaling=AutoscalingStatus(
                has_vpa=True, vpa_target_cpu="2", vpa_target_memory="8Gi"
            ),
        )
        target = vpa_morph_target(pod)
        self.assertIsNotNone(target)
        assert target is not None
        self.assertAlmostEqual(target[0], 2.0, delta=EPS)
        self.assertAlmostEqual(target[1], 8.0, delta=EPS)

    def test_partial_recommendation_keeps_other_axis(self):
        pod = _pod(
            "cpu-only",
            metrics={"cpu_request_cores": 0.5, "memory_request_gib": 4.0},
            autoscaling=AutoscalingStatus(has_vpa=True, vpa_target_cpu="1"),
        )
        target = vpa_morph_target(pod)
        self.assertIsNotNone(target)
        assert target is not None
        self.assertAlmostEqual(target[0], 1.0, delta=EPS)
        self.assertAlmostEqual(target[1], 4.0, delta=EPS)  # memory unchanged

    def test_morph_dimensions_tween_endpoints(self):
        # 0.5 core / 1 GiB -> H=0.647, R=0.200; target 8 cores / 32 GiB.
        pod = _pod(
            "morpher",
            metrics={"cpu_request_cores": 0.5, "memory_request_gib": 1.0},
            autoscaling=AutoscalingStatus(
                has_vpa=True, vpa_target_cpu="8", vpa_target_memory="32Gi"
            ),
        )
        dims = vpa_morph_dimensions(pod)
        self.assertIsNotNone(dims)
        assert dims is not None
        self.assertAlmostEqual(dims["current_height"], 0.647, delta=1e-3)
        self.assertAlmostEqual(dims["current_radius"], 0.200, delta=1e-3)
        self.assertAlmostEqual(dims["target_height"], 1.390, delta=1e-3)
        self.assertAlmostEqual(dims["target_radius"], 0.800, delta=1e-3)
        # Expansion: tween grows both axes.
        self.assertGreater(dims["target_height"], dims["current_height"])
        self.assertGreater(dims["target_radius"], dims["current_radius"])

    def test_shrink_morph(self):
        pod = _pod(
            "bloated",
            metrics={"cpu_request_cores": 8.0, "memory_request_gib": 32.0},
            autoscaling=AutoscalingStatus(
                has_vpa=True, vpa_target_cpu="500m", vpa_target_memory="512Mi"
            ),
        )
        dims = vpa_morph_dimensions(pod)
        assert dims is not None
        self.assertLess(dims["target_height"], dims["current_height"])
        self.assertLess(dims["target_radius"], dims["current_radius"])


# ---------------------------------------------------------------------------
# 3. HPA lateral dynamics (SPEC-09 §3.3)
# ---------------------------------------------------------------------------

class TestHpaLateralDynamics(unittest.TestCase):

    def test_scale_out_delta(self):
        self.assertEqual(hpa_scale_out_delta(2, 5), 3)
        self.assertEqual(hpa_scale_out_delta(1, 1), 0)
        # Scale-in is not a lateral spawn event.
        self.assertEqual(hpa_scale_out_delta(5, 2), 0)

    def test_scale_out_delta_garbage(self):
        self.assertEqual(hpa_scale_out_delta("x", 3), 0)
        self.assertEqual(hpa_scale_out_delta(None, None), 0)  # type: ignore[arg-type]
        self.assertEqual(hpa_scale_out_delta("2", "4"), 2)

    def test_constants_match_spec(self):
        self.assertEqual(SUPERVISOR_FLOOR_Y, 4.5)
        self.assertEqual(CENTRAL_RISER_X, 0.0)
        self.assertEqual(CENTRAL_RISER_Z, 0.0)
        self.assertEqual(VPA_MORPH_DURATION_MS, 1200)
        self.assertEqual(HPA_DISPATCH_PULSE_MS, 700)
        self.assertEqual(HPA_LATERAL_SLIDE_MS, 900)

    def test_lateral_path_geometry(self):
        path = hpa_lateral_path(chassis_x=-6.0, slot_offset_x=POD_X_STAGGER)
        intake = path["intake"]
        slot = path["slot"]
        # Intake sits at the tray outer edge; slot at the designated position.
        self.assertAlmostEqual(intake[0], -6.0 + DECK_INTAKE_OFFSET_X, delta=EPS)
        self.assertAlmostEqual(slot[0], -6.0 + POD_X_STAGGER, delta=EPS)
        # Both ride the pod deck height, slide is purely lateral (X).
        self.assertEqual(intake[1], slot[1])
        self.assertEqual(intake[2], slot[2])
        self.assertGreater(abs(intake[0] - slot[0]), 0.5)

    def test_lateral_path_roundtrips_through_json(self):
        import json
        path = hpa_lateral_path(3.0, -0.6)
        blob = json.dumps({k: list(v) for k, v in path.items()})
        restored = json.loads(blob)
        self.assertEqual(len(restored["intake"]), 3)
        self.assertEqual(len(restored["slot"]), 3)


# ---------------------------------------------------------------------------
# 4. Controller event wiring: autoscaling_updated fan-out
# ---------------------------------------------------------------------------

class TestControllerAutoscalingEvents(unittest.TestCase):

    def setUp(self):
        self.ctrl = TopologyController(cluster_name="test-vpa")
        self.q: queue.Queue = queue.Queue(maxsize=100)
        self.ctrl.add_listener(self.q)
        base = _pod(
            "api-7d9",
            metrics={"cpu_request_cores": 0.5, "memory_request_gib": 1.0},
        )
        apply_spatial_layout([base])
        self.ctrl.nodes[base.id] = base
        self._drain()

    def _drain(self):
        while not self.q.empty():
            self.q.get_nowait()

    def _collect(self):
        events = []
        while not self.q.empty():
            events.append(self.q.get_nowait())
        return events

    def test_vpa_recommendation_event_emitted(self):
        self.ctrl.inject_mutation("autoscaling_updated", {
            "node_id": "ns/api-7d9",
            "autoscaling": {
                "has_vpa": True,
                "vpa_target_cpu": "2",
                "vpa_target_memory": "8Gi",
            },
        })
        events = dict(self._collect())
        self.assertIn("vpa_recommendation", events)
        payload = events["vpa_recommendation"]
        self.assertEqual(payload["node_id"], "ns/api-7d9")
        dims = payload["dimensions"]
        self.assertAlmostEqual(dims["current_height"], 0.647, delta=1e-3)
        # 2 cores -> 0.40 + 0.35*sqrt(2) = 0.895
        self.assertAlmostEqual(dims["target_height"], 0.895, delta=1e-3)
        self.assertAlmostEqual(dims["target_radius"], 0.56, delta=1e-3)  # 8 GiB
        # No resize commit, no HPA pulse.
        self.assertNotIn("vpa_resize_committed", events)
        self.assertNotIn("hpa_scale_out", events)

    def test_vpa_resize_commit_updates_geometry(self):
        self.ctrl.inject_mutation("autoscaling_updated", {
            "node_id": "ns/api-7d9",
            "autoscaling": {
                "has_vpa": True,
                "vpa_target_cpu": "2",
                "vpa_target_memory": "8Gi",
                "is_resizing_in_place": True,
            },
        })
        events = dict(self._collect())
        self.assertIn("vpa_resize_committed", events)
        payload = events["vpa_resize_committed"]
        self.assertEqual(payload["duration_ms"], 1200)
        geo = payload["geometry"]
        self.assertIsNotNone(geo)
        # 2 cores / 8 GiB proportional dims landed on the model.
        self.assertAlmostEqual(geo["height"], 0.895, delta=1e-3)
        self.assertAlmostEqual(geo["radius"], 0.56, delta=1e-3)
        # Requests rewritten in-place (in-place resize semantics).
        node = self.ctrl.nodes["ns/api-7d9"]
        self.assertEqual(node.metrics["cpu_request_cores"], 2.0)
        self.assertEqual(node.metrics["memory_request_gib"], 8.0)

    def test_hpa_scale_out_dispatch_payload(self):
        self.ctrl.inject_mutation("autoscaling_updated", {
            "node_id": "ns/api-7d9",
            "autoscaling": {
                "has_hpa": True,
                "current_replicas": 2,
                "desired_replicas": 5,
                "target_metric": "cpu: 70%",
            },
        })
        events = dict(self._collect())
        self.assertIn("hpa_scale_out", events)
        payload = events["hpa_scale_out"]
        self.assertEqual(payload["delta"], 3)
        self.assertEqual(payload["target_metric"], "cpu: 70%")
        # Pulse originates on the Supervisor Floor down the central riser.
        dispatch = payload["dispatch_from"]
        self.assertEqual(dispatch["y"], SUPERVISOR_FLOOR_Y)
        self.assertEqual(dispatch["x"], CENTRAL_RISER_X)
        self.assertEqual(dispatch["z"], CENTRAL_RISER_Z)
        # Lateral conveyor path intake -> slot present and lateral.
        path = payload["lateral_path"]
        self.assertEqual(len(path["intake"]), 3)
        self.assertEqual(len(path["slot"]), 3)
        self.assertNotEqual(path["intake"][0], path["slot"][0])

    def test_hpa_scale_in_emits_nothing(self):
        self.ctrl.inject_mutation("autoscaling_updated", {
            "node_id": "ns/api-7d9",
            "autoscaling": {
                "has_hpa": True,
                "current_replicas": 5,
                "desired_replicas": 2,
            },
        })
        events = dict(self._collect())
        self.assertNotIn("hpa_scale_out", events)

    def test_unknown_node_is_noop(self):
        self.ctrl.inject_mutation("autoscaling_updated", {
            "node_id": "ns/does-not-exist",
            "autoscaling": {"has_vpa": True, "vpa_target_cpu": "2"},
        })
        self.assertEqual(self._collect(), [])

    def test_snapshot_carries_autoscaling_status(self):
        self.ctrl.inject_mutation("autoscaling_updated", {
            "node_id": "ns/api-7d9",
            "autoscaling": {
                "has_hpa": True,
                "current_replicas": 1,
                "desired_replicas": 3,
                "target_metric": "cpu: 60%",
            },
        })
        self._drain()
        snap = self.ctrl.get_snapshot()
        node = next(n for n in snap["nodes"] if n["id"] == "ns/api-7d9")
        self.assertIsNotNone(node["autoscaling"])
        self.assertTrue(node["autoscaling"]["has_hpa"])
        self.assertEqual(node["autoscaling"]["desired_replicas"], 3)

    def test_mock_seed_seeds_autoscaling_pods(self):
        # Fresh controller with no pre-populated nodes so get_snapshot()
        # triggers the mock seeding path (setUp's node would skip it).
        fresh = TopologyController(cluster_name="seed-check")
        snap = fresh.get_snapshot()
        autoscaled = [
            n for n in snap["nodes"]
            if n.get("autoscaling") and (
                n["autoscaling"]["has_vpa"] or n["autoscaling"]["has_hpa"]
            )
        ]
        self.assertGreaterEqual(len(autoscaled), 2)


# ---------------------------------------------------------------------------
# 5. AutoscalingStatus model contract
# ---------------------------------------------------------------------------

class TestAutoscalingStatusContract(unittest.TestCase):

    def test_controller_accepts_model_instance(self):
        ctrl = TopologyController(cluster_name="m")
        q: queue.Queue = queue.Queue(maxsize=50)
        ctrl.add_listener(q)
        base = _pod("m-pod", metrics={"cpu_request_cores": 1.0, "memory_request_gib": 2.0})
        apply_spatial_layout([base])
        ctrl.nodes[base.id] = base
        ctrl.inject_mutation("autoscaling_updated", {
            "node_id": base.id,
            "autoscaling": AutoscalingStatus(
                has_vpa=True, vpa_target_cpu="4", vpa_target_memory="16Gi",
            ),
        })
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        names = [name for name, _ in events]
        self.assertIn("vpa_recommendation", names)

    def test_model_dump_wire_shape(self):
        status = AutoscalingStatus(
            has_vpa=True, vpa_target_cpu="2", vpa_target_memory="4Gi",
            is_resizing_in_place=True,
            has_hpa=True, current_replicas=2, desired_replicas=4,
            target_metric="cpu: 70%",
        )
        blob = status.model_dump()
        for key in (
            "has_vpa", "vpa_target_cpu", "vpa_target_memory",
            "is_resizing_in_place", "has_hpa", "current_replicas",
            "desired_replicas", "target_metric",
        ):
            self.assertIn(key, blob)


if __name__ == "__main__":
    unittest.main()
