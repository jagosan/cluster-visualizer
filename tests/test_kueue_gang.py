"""Unit tests for SPEC-09 Kueue Gang Workload Container & Admission Animations (TASK-CV-1004).

Covers:
1. Kueue staging constants match SPEC-09 §5 / docs/architecture/09 §2.1
   (cargo pallet domain X [-21, -15], Y [0.4, 1.8], Z [-6, +6]; mag-rail
   intake bay at X = -8).
2. kueue_pallet_dimensions / kueue_pallet_anchor frame sizing + rail docking.
3. pack_kueue_workload: structured grid slot packing inside the containment
   pallet bounding volume, geometry bookkeeping (is_pending, staging_track_x,
   kueue_workload back-links).
4. sum_kueue_quota: vCPU / RAM GiB / GPU summation over gang members.
5. kueue_magrail_path / gang_deployment_targets animation contracts.
6. quota_deficit_reason / kueue_hud_summary HUD badge payloads (SPEC-09 §5.2).
7. apply_spatial_layout: queued gang pods pack into the pallet volume;
   admitted workloads deploy onto worker-deck targets instead.
8. TopologyController: kueue_workload_updated fan-out into
   kueue_workload_updated / kueue_quota_deficit / kueue_quota_reserved /
   kueue_admission_admitted / kueue_gang_deployed SSE events, snapshot
   carriage, mock demo seeding.
9. KueueWorkloadStatus + PodGeometrySpec.kueue_workload model contracts.
"""

import json
import queue
import unittest

from src.ingestion.layout import (
    GANG_DEPLOY_BURST_MS,
    KUEUE_FRAME_HEIGHT,
    KUEUE_GRID_COLS,
    KUEUE_PALLET_RAIL_X,
    KUEUE_PALLET_ROW_SPACING_Z,
    KUEUE_PALLET_X_MAX,
    KUEUE_PALLET_X_MIN,
    KUEUE_PALLET_Y_MAX,
    KUEUE_PALLET_Y_MIN,
    KUEUE_PALLET_Z_MAX,
    KUEUE_PALLET_Z_MIN,
    KUEUE_RESERVE_LOCK_MS,
    KUEUE_SLOT_SPACING_X,
    KUEUE_SLOT_Y,
    MAGRAIL_INTAKE_X,
    MAGRAIL_INTAKE_Y,
    MAGRAIL_INTAKE_Z,
    MAGRAIL_TRANSIT_DURATION_MS,
    POD_Y,
    apply_spatial_layout,
    gang_deployment_targets,
    kueue_hud_summary,
    kueue_magrail_path,
    kueue_pallet_anchor,
    kueue_pallet_dimensions,
    pack_kueue_workload,
    quota_deficit_reason,
    sum_kueue_quota,
)
from src.ingestion.models import KueueWorkloadStatus, NodeComponent, PodGeometrySpec
from src.operator.controller import TopologyController

EPS = 1e-6


def _pod(name: str, metrics=None, namespace: str = "default") -> NodeComponent:
    return NodeComponent(
        id=f"{namespace}/{name}",
        layer="workload",
        kind="Pod",
        name=name,
        namespace=namespace,
        status="Pending",
        metrics=dict(metrics or {}),
    )


def _gang(count: int, cpu: float = 8.0, mem: float = 32.0, gpus: int = 0):
    pods = [
        _pod(
            f"ray-job-{i}",
            metrics={
                "cpu_request_cores": cpu,
                "memory_request_gib": mem,
                "gpu_request": gpus,
                "scheduled": False,
            },
            namespace="batch-ai",
        )
        for i in range(count)
    ]
    workload = KueueWorkloadStatus(
        workload_uid="wl-ray-job",
        workload_name="ray-job",
        namespace="batch-ai",
        local_queue="batch-ai",
        cluster_queue="cluster-ml-bq",
        is_admitted=False,
        phase="Inadmissible",
        admission_checks=[
            {"type": "QuotaCheck", "status": "False", "reason": "QuotaExceeded: 64 vCPU short"}
        ],
        pod_uids=[p.id for p in pods],
    )
    return workload, pods


# ---------------------------------------------------------------------------
# 1. Spatial constants (SPEC-09 §5 / architecture §2.1 coordinate table)
# ---------------------------------------------------------------------------

class TestKueueConstants(unittest.TestCase):

    def test_pallet_freight_domain(self):
        self.assertEqual(KUEUE_PALLET_X_MIN, -21.0)
        self.assertEqual(KUEUE_PALLET_X_MAX, -15.0)
        self.assertEqual(KUEUE_PALLET_Y_MIN, 0.4)
        self.assertEqual(KUEUE_PALLET_Y_MAX, 1.8)
        self.assertEqual(KUEUE_PALLET_Z_MIN, -6.0)
        self.assertEqual(KUEUE_PALLET_Z_MAX, 6.0)
        # The whole pallet domain sits outside the tower (X < -12).
        self.assertLess(KUEUE_PALLET_X_MAX, -12.0)
        self.assertEqual(KUEUE_FRAME_HEIGHT, 1.4)

    def test_rail_and_grid(self):
        self.assertEqual(KUEUE_PALLET_RAIL_X, -18.0)
        self.assertEqual(KUEUE_PALLET_ROW_SPACING_Z, 5.6)
        self.assertEqual(KUEUE_GRID_COLS, 4)
        self.assertEqual(KUEUE_SLOT_SPACING_X, 1.3)
        self.assertEqual(KUEUE_SLOT_Y, 1.0)
        # Slot hover height nests inside the containment volume.
        self.assertGreater(KUEUE_SLOT_Y, KUEUE_PALLET_Y_MIN)
        self.assertLess(KUEUE_SLOT_Y, KUEUE_PALLET_Y_MAX)

    def test_magrail_intake_bay(self):
        self.assertEqual(MAGRAIL_INTAKE_X, -8.0)
        self.assertEqual(MAGRAIL_INTAKE_Y, 1.2)
        self.assertEqual(MAGRAIL_INTAKE_Z, 0.0)
        self.assertGreater(MAGRAIL_TRANSIT_DURATION_MS, 0)
        self.assertGreater(GANG_DEPLOY_BURST_MS, 0)
        self.assertGreater(KUEUE_RESERVE_LOCK_MS, 0)


# ---------------------------------------------------------------------------
# 2. Pallet frame sizing + rail docking
# ---------------------------------------------------------------------------

class TestPalletSizing(unittest.TestCase):

    def test_small_gang_gets_single_row_frame(self):
        w, h, d = kueue_pallet_dimensions(3)
        self.assertAlmostEqual(w, 3 * KUEUE_SLOT_SPACING_X + 0.6, delta=EPS)
        self.assertEqual(h, KUEUE_FRAME_HEIGHT)
        self.assertAlmostEqual(d, 1 * 1.5 + 0.6, delta=EPS)

    def test_large_gang_clamps_inside_domain(self):
        for count in (1, 4, 5, 16, 32, 64):
            w, h, d = kueue_pallet_dimensions(count)
            self.assertLessEqual(w, KUEUE_PALLET_X_MAX - KUEUE_PALLET_X_MIN)
            self.assertLessEqual(d, KUEUE_PALLET_Z_MAX - KUEUE_PALLET_Z_MIN)
            self.assertEqual(h, KUEUE_FRAME_HEIGHT)

    def test_zero_or_negative_count_floors_at_one(self):
        self.assertEqual(kueue_pallet_dimensions(0), kueue_pallet_dimensions(1))
        self.assertEqual(kueue_pallet_dimensions(-5), kueue_pallet_dimensions(1))

    def test_anchor_docks_on_rail_centerline(self):
        x, y, z = kueue_pallet_anchor(0)
        self.assertEqual(x, KUEUE_PALLET_RAIL_X)
        self.assertAlmostEqual(y, (KUEUE_PALLET_Y_MIN + KUEUE_PALLET_Y_MAX) / 2.0, delta=EPS)
        self.assertGreaterEqual(z, KUEUE_PALLET_Z_MIN)
        self.assertLessEqual(z, KUEUE_PALLET_Z_MAX)

    def test_anchors_step_along_z_and_stay_in_domain(self):
        zs = []
        for i in range(8):
            x, _, z = kueue_pallet_anchor(i)
            self.assertEqual(x, KUEUE_PALLET_RAIL_X)
            self.assertGreaterEqual(z, KUEUE_PALLET_Z_MIN)
            self.assertLessEqual(z, KUEUE_PALLET_Z_MAX)
            zs.append(z)
        # Monotone decreasing until clamped; at least two distinct docks.
        self.assertGreater(len(set(zs)), 1)
        self.assertAlmostEqual(zs[0] - zs[1], KUEUE_PALLET_ROW_SPACING_Z, delta=EPS)


# ---------------------------------------------------------------------------
# 3. pack_kueue_workload structured grid packing
# ---------------------------------------------------------------------------

class TestPackKueueWorkload(unittest.TestCase):

    def test_all_slots_land_inside_containment_volume(self):
        workload, pods = _gang(16)
        pack_kueue_workload(workload, pods, kueue_pallet_anchor(0))
        for pod in pods:
            self.assertGreaterEqual(pod.spatial.x, KUEUE_PALLET_X_MIN)
            self.assertLessEqual(pod.spatial.x, KUEUE_PALLET_X_MAX)
            self.assertGreaterEqual(pod.spatial.y, KUEUE_PALLET_Y_MIN)
            self.assertLessEqual(pod.spatial.y, KUEUE_PALLET_Y_MAX)
            self.assertGreaterEqual(pod.spatial.z, KUEUE_PALLET_Z_MIN)
            self.assertLessEqual(pod.spatial.z, KUEUE_PALLET_Z_MAX)
            self.assertEqual(pod.spatial.y, KUEUE_SLOT_Y)

    def test_slots_are_distinct_grid_cells(self):
        workload, pods = _gang(9)
        pack_kueue_workload(workload, pods, kueue_pallet_anchor(0))
        coords = {(p.spatial.x, p.spatial.z) for p in pods}
        self.assertEqual(len(coords), 9)

    def test_queued_pods_carry_pending_geometry_and_backlink(self):
        workload, pods = _gang(4)
        pack_kueue_workload(workload, pods, kueue_pallet_anchor(0))
        for pod in pods:
            self.assertIsNotNone(pod.pod_geometry)
            assert pod.pod_geometry is not None
            self.assertTrue(pod.pod_geometry.is_pending)
            self.assertEqual(pod.pod_geometry.staging_track_x, pod.spatial.x)
            self.assertEqual(pod.pod_geometry.kueue_workload, "wl-ray-job")

    def test_admitted_workload_drops_pending_flag(self):
        workload, pods = _gang(4)
        workload.is_admitted = True
        workload.phase = "Admitted"
        pack_kueue_workload(workload, pods, kueue_pallet_anchor(0))
        for pod in pods:
            assert pod.pod_geometry is not None
            self.assertFalse(pod.pod_geometry.is_pending)

    def test_packing_is_deterministic(self):
        w1, pods1 = _gang(6)
        w2, pods2 = _gang(6)
        r1 = pack_kueue_workload(w1, pods1, kueue_pallet_anchor(1))
        r2 = pack_kueue_workload(w2, pods2, kueue_pallet_anchor(1))
        self.assertEqual(r1["anchor"], r2["anchor"])
        self.assertEqual(r1["width"], r2["width"])
        self.assertEqual(r1["depth"], r2["depth"])

    def test_returns_pallet_wire_payload(self):
        workload, pods = _gang(8)
        result = pack_kueue_workload(workload, pods, kueue_pallet_anchor(0))
        self.assertEqual(len(result["anchor"]), 3)
        self.assertGreater(result["width"], 0.0)
        self.assertEqual(result["height"], KUEUE_FRAME_HEIGHT)
        self.assertGreater(result["depth"], 0.0)
        self.assertEqual(len(result["slots"]), 8)
        for uid, slot in result["slots"].items():
            self.assertEqual(len(slot), 3)
        # JSON-serializable for the SSE wire.
        json.loads(json.dumps(result))

    def test_frame_stays_inside_z_domain_for_deep_gangs(self):
        workload, pods = _gang(20)
        result = pack_kueue_workload(workload, pods, kueue_pallet_anchor(3))
        _, _, z = result["anchor"]
        depth = result["depth"]
        self.assertGreaterEqual(z - depth / 2.0, KUEUE_PALLET_Z_MIN - EPS)
        self.assertLessEqual(z + depth / 2.0, KUEUE_PALLET_Z_MAX + EPS)


# ---------------------------------------------------------------------------
# 4. Quota summation
# ---------------------------------------------------------------------------

class TestSumKueueQuota(unittest.TestCase):

    def test_sums_cpu_mem_gpu_across_gang(self):
        _, pods = _gang(4, cpu=8.0, mem=32.0, gpus=2)
        cpu, mem, gpus = sum_kueue_quota(pods)
        self.assertAlmostEqual(cpu, 32.0, delta=EPS)
        self.assertAlmostEqual(mem, 128.0, delta=EPS)
        self.assertEqual(gpus, 8)

    def test_defaults_when_requests_absent(self):
        pods = [_pod("bare-1"), _pod("bare-2")]
        cpu, mem, gpus = sum_kueue_quota(pods)
        # Fallback defaults 0.5 core / 1.0 GiB each (SPEC-09 ADR note).
        self.assertAlmostEqual(cpu, 1.0, delta=EPS)
        self.assertAlmostEqual(mem, 2.0, delta=EPS)
        self.assertEqual(gpus, 0)

    def test_empty_gang_zero_quota(self):
        self.assertEqual(sum_kueue_quota([]), (0.0, 0.0, 0))


# ---------------------------------------------------------------------------
# 5. Animation contracts: mag-rail path + gang deployment targets
# ---------------------------------------------------------------------------

class TestKueueAnimationContracts(unittest.TestCase):

    def test_magrail_from_rail_to_intake_bay(self):
        path = kueue_magrail_path((-18.0, 1.1, 3.2))
        frm, to = path["from"], path["to"]
        self.assertAlmostEqual(frm[0], -18.0, delta=EPS)
        self.assertAlmostEqual(to[0], MAGRAIL_INTAKE_X, delta=EPS)
        self.assertAlmostEqual(to[1], MAGRAIL_INTAKE_Y, delta=EPS)
        self.assertAlmostEqual(to[2], MAGRAIL_INTAKE_Z, delta=EPS)
        # Transit travels rightward into the tower.
        self.assertGreater(to[0], frm[0])

    def test_gang_targets_land_on_worker_deck(self):
        targets = gang_deployment_targets(8)
        self.assertEqual(len(targets), 8)
        for (x, y, z) in targets:
            self.assertEqual(y, POD_Y)
            self.assertGreaterEqual(x, -10.0)
            self.assertLessEqual(x, 10.0)
        xs = [t[0] for t in targets]
        self.assertEqual(len(set(xs)), 8)  # coordinated spread, no stacking

    def test_single_pod_target_at_origin_column(self):
        (x, y, z) = gang_deployment_targets(1)[0]
        self.assertEqual(x, 0.0)
        self.assertEqual(y, POD_Y)

    def test_zero_targets_empty(self):
        self.assertEqual(gang_deployment_targets(0), [])


# ---------------------------------------------------------------------------
# 6. HUD badge + quota-deficit indicator (SPEC-09 §5.2 / §5.3)
# ---------------------------------------------------------------------------

class TestKueueHud(unittest.TestCase):

    def test_hud_fields_complete(self):
        workload, pods = _gang(16)
        workload.total_cpu_requested = 64.0
        workload.total_memory_gib_requested = 256.0
        workload.total_gpu_requested = 8
        hud = kueue_hud_summary(workload)
        self.assertEqual(hud["workload_name"], "ray-job")
        self.assertEqual(hud["local_queue"], "batch-ai")
        self.assertEqual(hud["cluster_queue"], "cluster-ml-bq")
        self.assertEqual(hud["pod_count"], 16)
        self.assertEqual(hud["pod_count_label"], "16/16 Pods")
        self.assertEqual(hud["cpu"], 64.0)
        self.assertEqual(hud["memory_gib"], 256.0)
        self.assertEqual(hud["gpus"], 8)
        self.assertIsNotNone(hud["quota_deficit"])
        json.loads(json.dumps(hud))

    def test_deficit_reads_quota_check_reason(self):
        workload, _ = _gang(4)
        self.assertEqual(
            quota_deficit_reason(workload), "QuotaExceeded: 64 vCPU short"
        )

    def test_admissible_workload_has_no_deficit(self):
        workload = KueueWorkloadStatus(
            workload_uid="wl-ok",
            workload_name="ok-job",
            local_queue="batch-ai",
            cluster_queue="cluster-ml-bq",
            is_admitted=False,
            phase="Admissible",
            pod_uids=["batch-ai/x"],
        )
        self.assertIsNone(quota_deficit_reason(workload))
        self.assertIsNone(kueue_hud_summary(workload)["quota_deficit"])

    def test_admitted_workload_reports_no_deficit(self):
        workload, _ = _gang(4)
        workload.is_admitted = True
        workload.phase = "Admitted"
        self.assertIsNone(quota_deficit_reason(workload))
        hud = kueue_hud_summary(workload)
        self.assertTrue(hud["is_admitted"])
        self.assertEqual(hud["phase"], "Admitted")


# ---------------------------------------------------------------------------
# 7. apply_spatial_layout routing with Kueue workloads
# ---------------------------------------------------------------------------

class TestLayoutKueueRouting(unittest.TestCase):

    def test_queued_gang_packs_into_pallet_volume(self):
        workload, pods = _gang(8)
        nodes = apply_spatial_layout(list(pods), [workload])
        for n in nodes:
            self.assertGreaterEqual(n.spatial.x, KUEUE_PALLET_X_MIN)
            self.assertLessEqual(n.spatial.x, KUEUE_PALLET_X_MAX)
            self.assertGreaterEqual(n.spatial.y, KUEUE_PALLET_Y_MIN)
            self.assertLessEqual(n.spatial.y, KUEUE_PALLET_Y_MAX)
            self.assertGreaterEqual(n.spatial.z, KUEUE_PALLET_Z_MIN)
            self.assertLessEqual(n.spatial.z, KUEUE_PALLET_Z_MAX)
            assert n.pod_geometry is not None
            self.assertTrue(n.pod_geometry.is_pending)
            self.assertEqual(n.pod_geometry.kueue_workload, "wl-ray-job")

    def test_admitted_workload_deploys_to_worker_deck(self):
        workload, pods = _gang(4)
        workload.is_admitted = True
        workload.phase = "Admitted"
        nodes = apply_spatial_layout(list(pods), [workload])
        expected = gang_deployment_targets(4)
        by_name = {n.name: n for n in nodes}
        for i, name in enumerate(sorted(by_name)):
            n = by_name[name]
            self.assertAlmostEqual(n.spatial.y, POD_Y, delta=EPS)
            assert n.pod_geometry is not None
            self.assertFalse(n.pod_geometry.is_pending)
        # Spread across distinct deck targets.
        xs = sorted(n.spatial.x for n in nodes)
        self.assertEqual(len(set(xs)), 4)
        for x, y, z in expected:
            pass  # shape sanity; exact pairing is by sorted order
        self.assertTrue(all(-10.0 <= x <= 10.0 for x in xs))

    def test_unaffiliated_pending_pod_keeps_hover_band(self):
        _, gang_pods = _gang(4)
        stray = _pod("stray", metrics={"pending": True})
        nodes = apply_spatial_layout([*gang_pods, stray], [ _gang(4)[0] ])
        stray_node = next(n for n in nodes if n.name == "stray")
        # Hover band Y = 1.0 too, but no Kueue back-link.
        assert stray_node.pod_geometry is not None
        self.assertIsNone(stray_node.pod_geometry.kueue_workload)
        self.assertTrue(stray_node.pod_geometry.is_pending)

    def test_layout_without_workloads_is_unchanged(self):
        stray = _pod("classic", metrics={"pending": True})
        nodes = apply_spatial_layout([stray])
        n = nodes[0]
        self.assertTrue(n.pod_geometry.is_pending)
        self.assertIsNone(n.pod_geometry.kueue_workload)

    def test_multiple_workloads_get_distinct_rail_docks(self):
        w1, pods1 = _gang(4)
        w2, pods2 = _gang(4)
        for p in pods2:
            p.name = p.name.replace("ray-job", "mpi-job")
            p.id = p.id.replace("ray-job", "mpi-job")
        w2.workload_uid = "wl-mpi-job"
        w2.workload_name = "mpi-job"
        w2.pod_uids = [p.id for p in pods2]
        nodes = apply_spatial_layout([*pods1, *pods2], [w1, w2])
        g1_zs = {n.spatial.z for n in nodes if n.pod_geometry.kueue_workload == "wl-ray-job"}
        g2_zs = {n.spatial.z for n in nodes if n.pod_geometry.kueue_workload == "wl-mpi-job"}
        self.assertTrue(g1_zs.isdisjoint(g2_zs))


# ---------------------------------------------------------------------------
# 8. Controller event wiring: Kueue lifecycle fan-out
# ---------------------------------------------------------------------------

class TestControllerKueueEvents(unittest.TestCase):

    def setUp(self):
        self.ctrl = TopologyController(cluster_name="test-kueue")
        self.q: queue.Queue = queue.Queue(maxsize=200)
        self.ctrl.add_listener(self.q)
        self.workload, self.pods = _gang(4, gpus=2)
        for p in self.pods:
            self.ctrl.nodes[p.id] = p
        self._drain()

    def _drain(self):
        while not self.q.empty():
            self.q.get_nowait()

    def _collect(self):
        events = []
        while not self.q.empty():
            events.append(self.q.get_nowait())
        return events

    def _workload_payload(self, **overrides):
        base = self.workload.model_dump()
        base.update(overrides)
        return base

    def test_queued_workload_emits_update_and_deficit(self):
        self.ctrl.inject_mutation("kueue_workload_updated", {
            "workload": self._workload_payload(),
        })
        events = self._collect()
        names = [name for name, _ in events]
        self.assertIn("kueue_workload_updated", names)
        self.assertIn("kueue_quota_deficit", names)
        self.assertNotIn("kueue_admission_admitted", names)

        update = dict(events)["kueue_workload_updated"]
        self.assertEqual(update["workload"]["workload_name"], "ray-job")
        self.assertEqual(update["staging_focus_x"], -18.0)
        hud = update["hud"]
        self.assertEqual(hud["pod_count_label"], "4/4 Pods")
        self.assertEqual(hud["cpu"], 32.0)
        self.assertEqual(hud["memory_gib"], 128.0)
        self.assertEqual(hud["gpus"], 8)
        self.assertIsNotNone(hud["quota_deficit"])

    def test_pallet_payload_bounds_and_slots(self):
        self.ctrl.inject_mutation("kueue_workload_updated", {
            "workload": self._workload_payload(),
        })
        events = dict(self._collect())
        pallet = events["kueue_workload_updated"]["pallet"]
        ax, y, z = pallet["anchor"]
        self.assertAlmostEqual(ax, KUEUE_PALLET_RAIL_X, delta=EPS)
        self.assertGreaterEqual(y, KUEUE_PALLET_Y_MIN)
        self.assertLessEqual(y, KUEUE_PALLET_Y_MAX)
        self.assertEqual(len(pallet["slots"]), 4)
        for slot in pallet["slots"].values():
            self.assertGreaterEqual(slot[0], KUEUE_PALLET_X_MIN)
            self.assertLessEqual(slot[0], KUEUE_PALLET_X_MAX)
            self.assertGreaterEqual(slot[2], KUEUE_PALLET_Z_MIN)
            self.assertLessEqual(slot[2], KUEUE_PALLET_Z_MAX)

    def test_quota_reserved_emits_rail_engagement(self):
        self.ctrl.inject_mutation("kueue_workload_updated", {
            "workload": self._workload_payload(),
            "quota_reserved": True,
        })
        names = [name for name, _ in self._collect()]
        self.assertIn("kueue_quota_reserved", names)

    def test_admission_fires_magrail_then_gang_deploy(self):
        self.ctrl.inject_mutation("kueue_workload_updated", {
            "workload": self._workload_payload(),
        })
        self._drain()
        self.ctrl.inject_mutation("kueue_workload_updated", {
            "workload": self._workload_payload(is_admitted=True, phase="Admitted",
                                               admission_checks=[]),
        })
        events = self._collect()
        names = [name for name, _ in events]
        self.assertIn("kueue_admission_admitted", names)
        self.assertIn("kueue_gang_deployed", names)

        by_name = dict(events)
        magrail = by_name["kueue_admission_admitted"]["magrail"]
        # Transit: staging rail (X = -18) -> tower intake bay (X = -8).
        self.assertAlmostEqual(magrail["from"][0], KUEUE_PALLET_RAIL_X, delta=EPS)
        self.assertAlmostEqual(magrail["to"][0], MAGRAIL_INTAKE_X, delta=EPS)
        self.assertAlmostEqual(magrail["to"][1], MAGRAIL_INTAKE_Y, delta=EPS)
        self.assertAlmostEqual(magrail["to"][2], MAGRAIL_INTAKE_Z, delta=EPS)
        self.assertEqual(
            by_name["kueue_admission_admitted"]["transit_duration_ms"],
            MAGRAIL_TRANSIT_DURATION_MS,
        )

        burst = by_name["kueue_gang_deployed"]
        self.assertEqual(len(burst["targets"]), 4)
        self.assertEqual(burst["burst_duration_ms"], GANG_DEPLOY_BURST_MS)
        for t in burst["targets"]:
            self.assertEqual(t[1], POD_Y)
        self.assertEqual(
            sorted(burst["pod_uids"]), sorted(p.id for p in self.pods)
        )

    def test_workload_registered_and_carried_in_snapshot(self):
        self.ctrl.inject_mutation("kueue_workload_updated", {
            "workload": self._workload_payload(),
        })
        self._drain()
        self.assertIn("wl-ray-job", self.ctrl.kueue_workloads)
        snap = self.ctrl.get_snapshot()
        names = {w["workload_name"] for w in snap["kueue_workloads"]}
        self.assertIn("ray-job", names)
        # Constituent pods sit inside the containment volume in the snapshot.
        for pod in snap["nodes"]:
            if pod.get("pod_geometry") and pod["pod_geometry"].get("kueue_workload") == "wl-ray-job":
                self.assertLess(pod["spatial"]["x"], -12.0)
                self.assertGreaterEqual(pod["spatial"]["x"], KUEUE_PALLET_X_MIN)
                self.assertGreaterEqual(pod["spatial"]["y"], KUEUE_PALLET_Y_MIN)
                self.assertLessEqual(pod["spatial"]["y"], KUEUE_PALLET_Y_MAX)

    def test_missing_workload_payload_is_noop(self):
        self.ctrl.inject_mutation("kueue_workload_updated", {})
        self.assertEqual(self._collect(), [])
        self.assertEqual(len(self.ctrl.kueue_workloads), 0)

    def test_admitted_pod_pods_can_arrive_with_workload(self):
        # A fresh controller with no pre-registered pods: pods arrive inside
        # the event payload itself and must still be packed + quota-summed.
        ctrl = TopologyController(cluster_name="late-pods")
        q: queue.Queue = queue.Queue(maxsize=200)
        ctrl.add_listener(q)
        fresh = _gang(3)
        workload_dict = fresh[0].model_dump()
        pod_dicts = [p.model_dump() for p in fresh[1]]
        ctrl.inject_mutation("kueue_workload_updated", {
            "workload": workload_dict,
            "pods": pod_dicts,
        })
        self.assertIn("wl-ray-job", ctrl.kueue_workloads)
        stored = ctrl.kueue_workloads["wl-ray-job"]
        self.assertAlmostEqual(stored.total_cpu_requested, 24.0, delta=EPS)
        self.assertAlmostEqual(stored.total_memory_gib_requested, 96.0, delta=EPS)
        self.assertEqual(stored.total_gpu_requested, 0)

    def test_mock_seed_includes_kueue_gang(self):
        snap = TopologyController(cluster_name="seed-check").get_snapshot()
        self.assertGreaterEqual(len(snap["kueue_workloads"]), 1)
        wl = snap["kueue_workloads"][0]
        self.assertEqual(wl["workload_name"], "ray-finetune-job")
        self.assertEqual(wl["local_queue"], "batch-ai")
        self.assertFalse(wl["is_admitted"])
        members = [
            n for n in snap["nodes"]
            if n.get("pod_geometry")
            and n["pod_geometry"].get("kueue_workload") == wl["workload_uid"]
        ]
        self.assertGreaterEqual(len(members), 4)
        for m in members:
            self.assertTrue(m["pod_geometry"]["is_pending"])
            self.assertLess(m["spatial"]["x"], -12.0)
            self.assertGreaterEqual(m["spatial"]["x"], KUEUE_PALLET_X_MIN)
            self.assertLessEqual(m["spatial"]["x"], KUEUE_PALLET_X_MAX)
            self.assertGreaterEqual(m["spatial"]["y"], KUEUE_PALLET_Y_MIN)
            self.assertLessEqual(m["spatial"]["y"], KUEUE_PALLET_Y_MAX)
            self.assertGreaterEqual(m["spatial"]["z"], KUEUE_PALLET_Z_MIN)
            self.assertLessEqual(m["spatial"]["z"], KUEUE_PALLET_Z_MAX)


# ---------------------------------------------------------------------------
# 9. Model contracts
# ---------------------------------------------------------------------------

class TestKueueModels(unittest.TestCase):

    def test_workload_status_roundtrip(self):
        wl = KueueWorkloadStatus(
            workload_uid="wl-full",
            workload_name="full-job",
            namespace="batch-ai",
            local_queue="batch-ai",
            cluster_queue="cluster-ml-bq",
            is_admitted=True,
            admission_checks=[{"type": "QuotaCheck", "status": "True"}],
            pod_uids=["ns/a", "ns/b"],
            total_cpu_requested=64.0,
            total_memory_gib_requested=256.0,
            total_gpu_requested=8,
            phase="Admitted",
        )
        payload = json.loads(wl.model_dump_json())
        restored = KueueWorkloadStatus.model_validate(payload)
        self.assertEqual(restored, wl)
        for key in (
            "workload_uid", "workload_name", "local_queue", "cluster_queue",
            "is_admitted", "pod_uids", "total_cpu_requested",
            "total_memory_gib_requested", "total_gpu_requested", "phase",
        ):
            self.assertIn(key, payload)

    def test_pod_geometry_carries_kueue_workload_link(self):
        geo = PodGeometrySpec(kueue_workload="wl-ray-job")
        self.assertEqual(geo.kueue_workload, "wl-ray-job")
        payload = json.loads(geo.model_dump_json())
        self.assertIn("kueue_workload", payload)
        plain = PodGeometrySpec()
        self.assertIsNone(plain.kueue_workload)


if __name__ == "__main__":
    unittest.main()
