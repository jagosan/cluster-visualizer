"""Tests for the star-topology probe re-architecture (TASK-CV-1404 / SPEC-13 §3.5)."""

import unittest
from typing import Optional

from src.probe.main import (
    MAX_STAR_TARGETS,
    ProbeDaemon,
    ProbeTarget,
    LatencyStore,
    parse_az_bridges,
    parse_single_target,
    resolve_star_targets,
)


class ParseSingleTargetTest(unittest.TestCase):
    def test_unset_returns_none(self) -> None:
        self.assertIsNone(parse_single_target(""))

    def test_valid_host_port(self) -> None:
        self.assertEqual(parse_single_target("ingress.svc:443"), ("ingress.svc", 443))

    def test_malformed_returns_none(self) -> None:
        self.assertIsNone(parse_single_target("no-port-here"))
        self.assertIsNone(parse_single_target("host:notaport"))


class ParseAzBridgesTest(unittest.TestCase):
    def test_host_port_form(self) -> None:
        targets = parse_az_bridges("10.0.1.5:6443")
        self.assertEqual(len(targets), 1)
        t = targets[0]
        self.assertEqual(t.target_type, "az_bridge")
        self.assertEqual((t.host, t.port), ("10.0.1.5", 6443))
        self.assertIsNone(t.az)

    def test_az_host_port_form(self) -> None:
        targets = parse_az_bridges("us-east-1a:10.0.2.7:443")
        self.assertEqual(len(targets), 1)
        t = targets[0]
        self.assertEqual(t.target_type, "az_bridge")
        self.assertEqual((t.host, t.port), ("10.0.2.7", 443))
        self.assertEqual(t.az, "us-east-1a")

    def test_mixed_and_skips(self) -> None:
        targets = parse_az_bridges("us-east-1a:10.0.2.7:443,10.0.3.9:6443,bad")
        self.assertEqual(len(targets), 2)
        self.assertEqual([t.target_type for t in targets], ["az_bridge", "az_bridge"])


class ResolveStarTargetsTest(unittest.TestCase):
    def test_ordered_and_capped(self) -> None:
        bridges = ",".join(f"az{i}:10.0.{i}.1:443" for i in range(10))
        targets = resolve_star_targets(
            "ingress.svc:80", "kubernetes.default.svc:443", bridges
        )
        # ingress, api, then az_bridge - capped at MAX_STAR_TARGETS (K <= 5)
        self.assertLessEqual(len(targets), MAX_STAR_TARGETS)
        self.assertEqual([t.target_type for t in targets[:2]], ["ingress", "api"])
        self.assertEqual(targets[0].target_type, "ingress")
        self.assertEqual(targets[1].target_type, "api")
        self.assertTrue(all(t.target_type == "az_bridge" for t in targets[2:]))

    def test_empty_input(self) -> None:
        self.assertEqual(resolve_star_targets("", "", ""), [])


class ProbeTargetRecordTest(unittest.TestCase):
    def test_record_fields(self) -> None:
        t = ProbeTarget("ingress", "ingress.svc", 80)
        rec = t.as_record(1.25, True)
        self.assertEqual(
            {
                "target": "ingress.svc:80",
                "target_type": "ingress",
                "latency_ms": 1.25,
                "reachable": True,
                "rtt_ms": 1.25,
            },
            rec,
        )

    def test_record_includes_az(self) -> None:
        t = ProbeTarget("az_bridge", "10.0.2.7", 443, az="us-east-1a")
        rec = t.as_record(None, False)
        self.assertEqual(rec["target_type"], "az_bridge")
        self.assertEqual(rec["az"], "us-east-1a")
        self.assertIsNone(rec["latency_ms"])
        self.assertFalse(rec["reachable"])


class StarCycleProbeTest(unittest.TestCase):
    def _daemon(self, targets: list) -> ProbeDaemon:
        store = LatencyStore()
        d = ProbeDaemon(
            node_name="node-1",
            host_ip="10.0.0.2",
            pod_ip="10.244.0.5",
            interval_seconds=3.0,
            timeout_ms=200,
            sample_target_limit=20,
            store=store,
            topology="star",
            star_targets=targets,
        )
        return d

    def test_star_cycle_produces_target_type_records(self) -> None:
        targets = [
            ProbeTarget("ingress", "127.0.0.1", 9),  # closed port
            ProbeTarget("api", "127.0.0.1", 8),
        ]
        d = self._daemon(targets)
        result = d.run_cycle()
        latencies = result["latencies"]
        self.assertEqual(len(latencies), 2)
        types = {rec["target_type"] for rec in latencies}
        self.assertEqual(types, {"ingress", "api"})
        # unreachable targets still carry latency_ms=None and target_type
        for rec in latencies:
            self.assertIn("latency_ms", rec)
            self.assertFalse(rec["reachable"])
        self.assertEqual(d.store.snapshot()["node"], "node-1")

    def test_star_cycle_caps_at_five(self) -> None:
        targets = [
            ProbeTarget("az_bridge", "127.0.0.1", 9, az=f"az{i}") for i in range(8)
        ]
        d = self._daemon(targets)
        result = d.run_cycle()
        self.assertLessEqual(len(result["latencies"]), MAX_STAR_TARGETS)

    def test_mesh_mode_still_works(self) -> None:
        store = LatencyStore()
        d = ProbeDaemon(
            node_name="node-1",
            host_ip="127.0.0.1",
            pod_ip="10.244.0.5",
            interval_seconds=3.0,
            timeout_ms=200,
            sample_target_limit=20,
            store=store,
            explicit_targets=[("127.0.0.1", 9)],
            topology="mesh",
        )
        result = d.run_cycle()
        self.assertEqual(len(result["latencies"]), 1)
        rec = result["latencies"][0]
        self.assertIn("reachable", rec)
        self.assertNotIn("target_type", rec)


if __name__ == "__main__":
    unittest.main()
