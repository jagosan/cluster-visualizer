"""Unit tests for SPEC-06 Ephemeral Multi-Cluster Testbed & Chaos Injector."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from src.testbed.models import (
    ChaosScenario,
    ClusterSpec,
    ClusterStatus,
    FleetSpec,
    FleetStatusReport,
    OperatorConfig,
)
from src.testbed.drivers.k3d import K3dDriver
from src.testbed.manager import TestbedManager, load_fleet_spec
from src.testbed.chaos import ChaosInjector, run_chaos_scenario


class TestTestbedSubsystem(unittest.TestCase):
    """Test suite for SPEC-06 Testbed models, K3d driver, manager, and chaos injection."""

    def setUp(self):
        self.fleet_yaml_path = Path("testbeds/fleet-spec.yaml")

    def test_fleet_spec_models_and_yaml_serialization(self):
        """Verify FleetSpec, ClusterSpec, and OperatorConfig validate and parse correctly."""
        self.assertTrue(self.fleet_yaml_path.exists(), "testbeds/fleet-spec.yaml must exist")
        fleet = load_fleet_spec(self.fleet_yaml_path)
        self.assertEqual(fleet.fleet_name, "homelab-canary-matrix")
        self.assertEqual(fleet.host, "chunkito")
        self.assertGreaterEqual(len(fleet.clusters), 3)

        cluster_stage = fleet.get_cluster("stage-regular")
        self.assertIsNotNone(cluster_stage)
        assert cluster_stage is not None
        self.assertEqual(cluster_stage.kubernetes_version, "v1.36.4-k3s1")
        self.assertEqual(cluster_stage.api_port, 64431)
        self.assertTrue(cluster_stage.operator.enabled)

        # Test dump and reload
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            fleet.to_yaml_file(tmp_path)
            reloaded = FleetSpec.from_yaml_file(tmp_path)
            self.assertEqual(reloaded.fleet_name, fleet.fleet_name)
            self.assertEqual(len(reloaded.clusters), len(fleet.clusters))
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_k3d_driver_mock_lifecycle(self):
        """Verify K3dDriver create, status, kubeconfig, and delete lifecycle in mock mode."""
        driver = K3dDriver(host="chunkito", mock_mode=True)
        spec = ClusterSpec(
            name="test-cluster-1",
            driver="k3d",
            kubernetes_version="v1.36.4-k3s1",
            servers=1,
            agents=2,
            api_port=64435,
            operator=OperatorConfig(enabled=True, host_port=8085),
        )

        # 1. Create cluster
        created = driver.create_cluster(spec)
        self.assertTrue(created)

        # 2. Status check
        status = driver.get_cluster_status("test-cluster-1")
        self.assertEqual(status.name, "test-cluster-1")
        self.assertEqual(status.status, "running")
        self.assertIn("100.71.183.123", status.api_endpoint)

        # 3. Kubeconfig retrieval
        kubeconfig = driver.get_kubeconfig("test-cluster-1")
        self.assertIn("apiVersion: v1", kubeconfig)
        self.assertIn("test-cluster-1", kubeconfig)
        self.assertIn("100.71.183.123", kubeconfig)

        # 4. Apply manifest mock
        applied = driver.apply_manifest("test-cluster-1", "apiVersion: v1\nkind: Namespace\nmetadata:\n  name: test")
        self.assertTrue(applied)

        # 5. Delete cluster
        deleted = driver.delete_cluster("test-cluster-1")
        self.assertTrue(deleted)

        # 6. Status after delete
        status_after = driver.get_cluster_status("test-cluster-1")
        self.assertEqual(status_after.status, "not_found")

    def test_testbed_manager_mock_flow(self):
        """Verify TestbedManager up, status, operator deploy, and down workflow."""
        fleet = load_fleet_spec(self.fleet_yaml_path)
        manager = TestbedManager(fleet, mock_mode=True)

        # 1. Up
        report_up = manager.up()
        self.assertIsInstance(report_up, FleetStatusReport)
        self.assertEqual(report_up.total_clusters, len(fleet.clusters))
        self.assertEqual(report_up.running_clusters, len(fleet.clusters))

        # 2. Status
        status_report = manager.status()
        self.assertEqual(status_report.fleet_name, "homelab-canary-matrix")
        self.assertEqual(len(status_report.clusters), len(fleet.clusters))

        # 3. Deploy Operator
        operator_results = manager.deploy_operator()
        self.assertIsInstance(operator_results, dict)
        for cluster_name in ["stage-regular", "prod-regular", "edge-rapid"]:
            self.assertIn(cluster_name, operator_results)
            self.assertTrue(operator_results[cluster_name])

        # 4. Down
        down_success = manager.down()
        self.assertTrue(down_success)

    def test_chaos_injector_scenarios(self):
        """Verify ChaosInjector supports rollout-restart, node-drain, pod-kill, and canary-weight-shift."""
        injector = ChaosInjector(mock_mode=True)

        # Scenario 1: Rollout Restart
        res_rollout = injector.inject(
            ChaosScenario(
                scenario_type="rollout-restart",
                cluster="stage-regular",
                target_resource="postgres-ha",
                namespace="database",
            )
        )
        self.assertEqual(res_rollout["status"], "success")
        self.assertEqual(res_rollout["target"], "postgres-ha")
        self.assertIn("events_generated", res_rollout)

        # Scenario 2: Node Drain
        res_drain = injector.inject(
            ChaosScenario(
                scenario_type="node-drain",
                cluster="prod-regular",
                target_resource="k3d-prod-regular-agent-1",
            )
        )
        self.assertEqual(res_drain["status"], "success")

        # Scenario 3: Pod Kill
        res_kill = injector.inject(
            ChaosScenario(
                scenario_type="pod-kill",
                cluster="stage-regular",
                target_resource="postgres-ha-0",
                namespace="database",
            )
        )
        self.assertEqual(res_kill["status"], "success")

        # Scenario 4: Canary Weight Shift
        res_weight = run_chaos_scenario(
            scenario_type="canary-weight-shift",
            cluster="edge-rapid",
            target="payment-service-canary",
            namespace="finance",
            params={"weight": 80},
            mock_mode=True,
        )
        self.assertEqual(res_weight["status"], "success")


if __name__ == "__main__":
    unittest.main()
