"""Unit tests for SPEC-09 Exterior Staging Yard & Karpenter Tractor Beams (TASK-CV-1003).

Covers:
1. Staging constants match SPEC-09 §4.1 / §4.2 (tarmac, hover band, B1 ghost).
2. stage_pending_pod: pending pod routing into the hover band coordinates.
3. apply_spatial_layout: pending pods (metrics pending / scheduled=False) are
   diverted to the staging yard, scheduled pods stay on the worker deck.
4. ghost_node_positions: B1 chassis row docking math.
5. karpenter_tractor_beam: amber beam endpoints from pod hover down to ghost.
6. TopologyController: karpenter_claim_updated fan-out into
   karpenter_claim_updated / karpenter_tractor_beam SSE events, snapshot
   carriage of claims + staging coordinates, mock seeding.
7. KarpenterNodeClaim model round-trip.
"""

import queue
import json
import unittest

from src.ingestion.layout import (
    GHOST_CHASSIS_SPACING_X,
    GHOST_NODE_X_MAX,
    GHOST_NODE_X_MIN,
    GHOST_NODE_Y,
    PENDING_HOVER_X_MAX,
    PENDING_HOVER_X_MIN,
    PENDING_HOVER_Y,
    PENDING_HOVER_Z_MAX,
    PENDING_HOVER_Z_MIN,
    STAGING_TARMAC_X_MAX,
    STAGING_TARMAC_X_MIN,
    STAGING_TARMAC_Y,
    STAGING_TARMAC_Z_MAX,
    STAGING_TARMAC_Z_MIN,
    STAGING_YARD_FOCUS_X,
    apply_spatial_layout,
    ghost_node_positions,
    karpenter_tractor_beam,
    stage_pending_pod,
)
from src.ingestion.models import KarpenterNodeClaim, NodeComponent
from src.operator.controller import TopologyController

EPS = 1e-6


def _xyz(v: object) -> tuple:
    """Coerce a JSON-ish 3-tuple payload into floats for assertions."""
    assert isinstance(v, (list, tuple)) and len(v) == 3
    return (float(v[0]), float(v[1]), float(v[2]))


def _pod(name: str, metrics=None, namespace="default") -> NodeComponent:
    return NodeComponent(
        id=f"ns/{name}",
        layer="workload",
        kind="Pod",
        name=name,
        namespace=namespace,
        status="Pending" if (metrics or {}).get("pending") or (metrics or {}).get("scheduled") is False else "Healthy",
        metrics=dict(metrics or {}),
    )


# ---------------------------------------------------------------------------
# 1. Spatial constants (SPEC-09 §4.1 / §4.2 coordinate table)
# ---------------------------------------------------------------------------

class TestStagingConstants(unittest.TestCase):

    def test_tarmac_domain(self):
        self.assertEqual(STAGING_TARMAC_Y, 0.2)
        self.assertEqual(STAGING_TARMAC_X_MIN, -24.0)
        self.assertEqual(STAGING_TARMAC_X_MAX, -12.0)
        self.assertEqual(STAGING_TARMAC_Z_MIN, -8.0)
        self.assertEqual(STAGING_TARMAC_Z_MAX, 8.0)
        # Entire tarmac sits strictly outside the tower footprint (X < -12).
        self.assertLess(STAGING_TARMAC_X_MAX, -10.0)

    def test_pending_hover_band(self):
        self.assertEqual(PENDING_HOVER_Y, 1.0)
        self.assertEqual(PENDING_HOVER_X_MIN, -22.0)
        self.assertEqual(PENDING_HOVER_X_MAX, -14.0)
        self.assertEqual(PENDING_HOVER_Z_MIN, -6.0)
        self.assertEqual(PENDING_HOVER_Z_MAX, 6.0)
        # Hover band nests inside the tarmac X span.
        self.assertGreater(PENDING_HOVER_X_MIN, STAGING_TARMAC_X_MIN)
        self.assertLess(PENDING_HOVER_X_MAX, STAGING_TARMAC_X_MAX)

    def test_ghost_b1_domain(self):
        self.assertEqual(GHOST_NODE_Y, -2.5)
        self.assertEqual(GHOST_NODE_X_MIN, -10.0)
        self.assertEqual(GHOST_NODE_X_MAX, 10.0)
        self.assertEqual(GHOST_CHASSIS_SPACING_X, 2.4)

    def test_focus_anchor(self):
        self.assertEqual(STAGING_YARD_FOCUS_X, -18.0)


# ---------------------------------------------------------------------------
# 2. stage_pending_pod routing math
# ---------------------------------------------------------------------------

class TestStagePendingPod(unittest.TestCase):

    def test_first_pending_pod_hovers_at_band_origin(self):
        pod = _pod("pending-0", metrics={"scheduled": False})
        x, y, z = stage_pending_pod(pod, 0)
        self.assertEqual(y, PENDING_HOVER_Y)
        self.assertAlmostEqual(x, PENDING_HOVER_X_MIN, delta=EPS)
        self.assertAlmostEqual(z, PENDING_HOVER_Z_MIN, delta=EPS)
        # Spatial mutation landed on the model itself.
        self.assertEqual(pod.spatial.y, PENDING_HOVER_Y)
        self.assertEqual(pod.spatial.x, x)
        self.assertEqual(pod.spatial.z, z)

    def test_coordinates_stay_inside_hover_band(self):
        for index in range(32):
            pod = _pod(f"pending-{index}", metrics={"pending": True})
            x, y, z = stage_pending_pod(pod, index)
            self.assertEqual(y, PENDING_HOVER_Y)
            self.assertGreaterEqual(x, PENDING_HOVER_X_MIN)
            self.assertLessEqual(x, PENDING_HOVER_X_MAX)
            self.assertGreaterEqual(z, PENDING_HOVER_Z_MIN)
            self.assertLessEqual(z, PENDING_HOVER_Z_MAX)

    def test_staging_track_x_recorded_on_geometry(self):
        pod = _pod("tracked", metrics={"pending": True})
        x, _, _ = stage_pending_pod(pod, 2)
        self.assertIsNotNone(pod.pod_geometry)
        assert pod.pod_geometry is not None
        self.assertEqual(pod.pod_geometry.staging_track_x, x)
        self.assertTrue(pod.pod_geometry.is_pending)

    def test_staging_is_deterministic(self):
        a = _pod("same", metrics={"pending": True})
        b = _pod("same", metrics={"pending": True})
        self.assertEqual(stage_pending_pod(a, 5), stage_pending_pod(b, 5))
        # Different slots for different queue indices.
        self.assertNotEqual(stage_pending_pod(a, 0), stage_pending_pod(b, 1))


# ---------------------------------------------------------------------------
# 3. apply_spatial_layout diversion of pending pods
# ---------------------------------------------------------------------------

class TestLayoutPendingRouting(unittest.TestCase):

    def test_pending_pods_routed_to_yard_scheduled_stay_on_deck(self):
        pending = _pod("unschedulable", metrics={"scheduled": False})
        flagged = _pod("flagged", metrics={"pending": True})
        healthy = _pod("web-1", metrics={"cpu_request_cores": 1.0})
        nodes = apply_spatial_layout([pending, flagged, healthy])

        by_name = {n.name: n for n in nodes}
        for name in ("unschedulable", "flagged"):
            n = by_name[name]
            assert n.pod_geometry is not None
            self.assertTrue(n.pod_geometry.is_pending)
            self.assertEqual(n.spatial.y, PENDING_HOVER_Y)
            self.assertLess(n.spatial.x, -12.0)
            self.assertGreaterEqual(n.spatial.x, PENDING_HOVER_X_MIN)
            self.assertLessEqual(n.spatial.x, PENDING_HOVER_X_MAX)
            self.assertEqual(n.pod_geometry.staging_track_x, n.spatial.x)

        # The scheduled pod keeps its worker-deck placement inside the tower.
        web = by_name["web-1"]
        self.assertFalse(web.pod_geometry.is_pending)
        self.assertNotEqual(web.spatial.y, PENDING_HOVER_Y)
        self.assertGreater(web.spatial.x, -12.0)

    def test_pending_pods_get_distinct_slots(self):
        pods = [_pod(f"gang-{i}", metrics={"pending": True}) for i in range(6)]
        nodes = apply_spatial_layout(pods)
        coords = {(n.spatial.x, n.spatial.y, n.spatial.z) for n in nodes}
        self.assertEqual(len(coords), 6)

    def test_karpenter_claim_label_propagates_to_geometry(self):
        pod = _pod("claimed", metrics={
            "pending": True,
            "karpenter_target_node_claim": "nc-spot-42",
        })
        nodes = apply_spatial_layout([pod])
        n = nodes[0]
        assert n.pod_geometry is not None
        self.assertEqual(n.pod_geometry.karpenter_target_node_claim, "nc-spot-42")

    def test_pending_ray_pod_leaves_tower_interior(self):
        # A pending pod whose *name* matches framework detection must still
        # stage outside the tower (ADR-02 pre-empts name-based placement).
        pod = _pod("ray-trainer-9x", metrics={"scheduled": False})
        nodes = apply_spatial_layout([pod])
        n = nodes[0]
        self.assertTrue(n.pod_geometry.is_pending)
        self.assertEqual(n.spatial.y, PENDING_HOVER_Y)
        self.assertLess(n.spatial.x, -12.0)

    def test_non_pod_kinds_are_not_staged(self):
        node = NodeComponent(id="n/w-1", layer="node", kind="Node", name="worker-1")
        nodes = apply_spatial_layout([node])
        self.assertNotEqual(nodes[0].spatial.y, PENDING_HOVER_Y)


# ---------------------------------------------------------------------------
# 4. Ghost node chassis docking (Sub-Level B1)
# ---------------------------------------------------------------------------

class TestGhostNodePositions(unittest.TestCase):

    def test_zero_claims_empty_row(self):
        self.assertEqual(ghost_node_positions(0), [])
        self.assertEqual(ghost_node_positions(-3), [])

    def test_row_docks_centered_on_b1(self):
        positions = ghost_node_positions(4)
        self.assertEqual(len(positions), 4)
        for (x, y, z) in positions:
            self.assertEqual(y, -2.5)
            self.assertEqual(z, 0.0)
            self.assertGreaterEqual(x, GHOST_NODE_X_MIN)
            self.assertLessEqual(x, GHOST_NODE_X_MAX)
        xs = [p[0] for p in positions]
        self.assertAlmostEqual(sum(xs) / len(xs), 0.0, delta=EPS)
        # Monotone left-to-right docking with the canonical spacing.
        self.assertAlmostEqual(xs[1] - xs[0], GHOST_CHASSIS_SPACING_X, delta=EPS)

    def test_large_row_clamps_inside_domain(self):
        for (x, _, _) in ghost_node_positions(40):
            self.assertGreaterEqual(x, GHOST_NODE_X_MIN)
            self.assertLessEqual(x, GHOST_NODE_X_MAX)


# ---------------------------------------------------------------------------
# 5. Karpenter tractor beam endpoints (SPEC-09 §4.2)
# ---------------------------------------------------------------------------

class TestKarpenterTractorBeam(unittest.TestCase):

    def test_beam_from_hover_pod_into_ghost(self):
        beam = karpenter_tractor_beam((-22.0, 1.0, -6.0), (-1.2, -2.5, 0.0))
        top = _xyz(beam["top"])
        bottom = _xyz(beam["bottom"])
        # Top anchors exactly on the pending pod's hover position.
        self.assertAlmostEqual(top[0], -22.0, delta=EPS)
        self.assertAlmostEqual(top[1], PENDING_HOVER_Y, delta=EPS)
        self.assertAlmostEqual(top[2], -6.0, delta=EPS)
        # Bottom lands on the ghost chassis footprint at the B1 stratum.
        self.assertAlmostEqual(bottom[0], -1.2, delta=EPS)
        self.assertAlmostEqual(bottom[1], -2.5, delta=EPS)
        self.assertAlmostEqual(bottom[2], 0.0, delta=EPS)
        # The beam projects downward.
        self.assertGreater(top[1], bottom[1])
        self.assertAlmostEqual(float(beam["span_y"]), top[1] - bottom[1], delta=EPS)

    def test_bottom_y_override(self):
        beam = karpenter_tractor_beam((-18.0, 1.0, 0.0), (0.0, -2.5, 0.0), bottom_y=-1.0)
        self.assertAlmostEqual(_xyz(beam["bottom"])[1], -1.0, delta=EPS)
        self.assertAlmostEqual(float(beam["span_y"]), 2.0, delta=EPS)

    def test_beam_json_serializable(self):
        beam = karpenter_tractor_beam((-22.0, 1.0, -6.0), (0.0, -2.5, 0.0))
        blob = json.loads(json.dumps(beam))
        self.assertEqual(len(blob["top"]), 3)
        self.assertEqual(len(blob["bottom"]), 3)


# ---------------------------------------------------------------------------
# 6. Controller event wiring: karpenter_claim_updated fan-out
# ---------------------------------------------------------------------------

class TestControllerKarpenterEvents(unittest.TestCase):

    def setUp(self):
        self.ctrl = TopologyController(cluster_name="test-karpenter")
        self.q: queue.Queue = queue.Queue(maxsize=100)
        self.ctrl.add_listener(self.q)
        pending = _pod("batch-gpu-0", metrics={
            "pending": True,
            "cpu_request_cores": 8.0,
            "memory_request_gib": 32.0,
        })
        apply_spatial_layout([pending])
        self.ctrl.nodes[pending.id] = pending
        self._drain()

    def _drain(self):
        while not self.q.empty():
            self.q.get_nowait()

    def _collect(self):
        events = []
        while not self.q.empty():
            events.append(self.q.get_nowait())
        return events

    def _claim_payload(self, **overrides):
        base = {
            "claim_name": "nc-gpu-l4-7d",
            "namespace": "batch-ai",
            "nodepool": "gpu-pool",
            "instance_type": "g2-standard-16",
            "capacity_type": "spot",
            "requested_cpu_cores": 16.0,
            "requested_memory_gib": 64.0,
            "pending_pod_uids": ["ns/batch-gpu-0"],
        }
        base.update(overrides)
        return base

    def test_claim_event_emits_ghost_dock_and_tractor_beam(self):
        self.ctrl.inject_mutation("karpenter_claim_updated", {
            "claim": self._claim_payload(),
        })
        events = self._collect()
        names = [name for name, _ in events]
        self.assertIn("karpenter_claim_updated", names)
        self.assertIn("karpenter_tractor_beam", names)

        claim_ev = dict(events)[ "karpenter_claim_updated"]
        dock = claim_ev["ghost_position"]
        self.assertEqual(dock["y"], GHOST_NODE_Y)
        self.assertGreaterEqual(dock["x"], GHOST_NODE_X_MIN)
        self.assertLessEqual(dock["x"], GHOST_NODE_X_MAX)
        self.assertEqual(claim_ev["staging_focus_x"], STAGING_YARD_FOCUS_X)
        self.assertEqual(claim_ev["claim"]["claim_name"], "nc-gpu-l4-7d")

    def test_tractor_beam_terminals_match_pod_and_ghost(self):
        self.ctrl.inject_mutation("karpenter_claim_updated", {
            "claim": self._claim_payload(),
        })
        events = self._collect()
        beams = [p for name, p in events if name == "karpenter_tractor_beam"]
        self.assertEqual(len(beams), 1)
        beam = beams[0]["beam"]
        pod = self.ctrl.nodes["ns/batch-gpu-0"]
        # Top = pending pod hover position on the staging yard.
        self.assertAlmostEqual(beam["top"][0], pod.spatial.x, delta=EPS)
        self.assertAlmostEqual(beam["top"][1], PENDING_HOVER_Y, delta=EPS)
        self.assertAlmostEqual(beam["top"][2], pod.spatial.z, delta=EPS)
        # Bottom = B1 ghost chassis stratum.
        self.assertAlmostEqual(beam["bottom"][1], GHOST_NODE_Y, delta=EPS)
        self.assertGreater(beam["top"][1], beam["bottom"][1])
        # Claim back-links on the pod geometry.
        assert pod.pod_geometry is not None
        self.assertEqual(pod.pod_geometry.karpenter_target_node_claim, "nc-gpu-l4-7d")

    def test_claim_registered_and_carried_in_snapshot(self):
        self.ctrl.inject_mutation("karpenter_claim_updated", {
            "claim": self._claim_payload(),
        })
        self._drain()
        self.assertIn("nc-gpu-l4-7d", self.ctrl.karpenter_node_claims)
        snap = self.ctrl.get_snapshot()
        claims = {c["claim_name"] for c in snap["karpenter_node_claims"]}
        self.assertIn("nc-gpu-l4-7d", claims)
        pod = next(n for n in snap["nodes"] if n["id"] == "ns/batch-gpu-0")
        self.assertTrue(pod["pod_geometry"]["is_pending"])
        self.assertEqual(pod["spatial"]["y"], PENDING_HOVER_Y)
        self.assertLess(pod["spatial"]["x"], -12.0)

    def test_multiple_claims_get_distinct_ghost_docks(self):
        self.ctrl.inject_mutation("karpenter_claim_updated", {
            "claim": self._claim_payload(claim_name="nc-a"),
        })
        self.ctrl.inject_mutation("karpenter_claim_updated", {
            "claim": self._claim_payload(claim_name="nc-b"),
        })
        docks = sorted(
            c.claim_name for c in self.ctrl.karpenter_node_claims.values()
        )
        self.assertEqual(docks, ["nc-a", "nc-b"])
        xs = [ghost_node_positions(2)[i][0] for i in range(2)]
        self.assertNotEqual(xs[0], xs[1])

    def test_missing_claim_payload_is_noop(self):
        self.ctrl.inject_mutation("karpenter_claim_updated", {})
        self.assertEqual(self._collect(), [])
        self.assertEqual(len(self.ctrl.karpenter_node_claims), 0)

    def test_beam_for_unknown_pod_is_skipped(self):
        self.ctrl.inject_mutation("karpenter_claim_updated", {
            "claim": self._claim_payload(pending_pod_uids=["ns/ghost-pod"]),
        })
        names = [name for name, _ in self._collect()]
        self.assertIn("karpenter_claim_updated", names)
        self.assertNotIn("karpenter_tractor_beam", names)

    def test_mock_seed_includes_staging_yard(self):
        snap = TopologyController(cluster_name="seed-check").get_snapshot()
        pending = [
            n for n in snap["nodes"]
            if n.get("pod_geometry") and n["pod_geometry"]["is_pending"]
        ]
        self.assertGreaterEqual(len(pending), 1)
        for p in pending:
            self.assertEqual(p["spatial"]["y"], PENDING_HOVER_Y)
            self.assertLess(p["spatial"]["x"], -12.0)
        self.assertGreaterEqual(len(snap["karpenter_node_claims"]), 1)


# ---------------------------------------------------------------------------
# 7. KarpenterNodeClaim model contract
# ---------------------------------------------------------------------------

class TestKarpenterNodeClaimModel(unittest.TestCase):

    def test_defaults(self):
        claim = KarpenterNodeClaim(claim_name="nc-min")
        self.assertEqual(claim.namespace, "default")
        self.assertEqual(claim.capacity_type, "on-demand")
        self.assertFalse(claim.is_provisioned)
        self.assertEqual(claim.pending_pod_uids, [])

    def test_roundtrip(self):
        claim = KarpenterNodeClaim(
            claim_name="nc-full",
            namespace="batch-ai",
            nodepool="gpu-pool",
            instance_type="g2-standard-16",
            capacity_type="spot",
            requested_cpu_cores=16.0,
            requested_memory_gib=64.0,
            requested_gpu_count=1,
            pending_pod_uids=["ns/a", "ns/b"],
            is_provisioned=True,
        )
        payload = json.loads(claim.model_dump_json())
        restored = KarpenterNodeClaim.model_validate(payload)
        self.assertEqual(restored, claim)
        for key in (
            "claim_name", "nodepool", "capacity_type", "pending_pod_uids",
            "is_provisioned",
        ):
            self.assertIn(key, payload)


if __name__ == "__main__":
    unittest.main()
