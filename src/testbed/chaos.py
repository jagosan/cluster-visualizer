from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .models import ChaosScenario
from .drivers.base import ClusterDriver
from .drivers.k3d import K3dDriver

logger = logging.getLogger(__name__)


class ChaosInjector:
    def __init__(self, driver: Optional[ClusterDriver] = None, mock_mode: bool = False):
        if driver is None:
            self.driver = K3dDriver(mock_mode=mock_mode)
        else:
            self.driver = driver
        self.mock_mode = mock_mode or getattr(self.driver, 'mock_mode', False)

    def inject(self, scenario: ChaosScenario) -> Dict[str, Any]:
        scenario_type = scenario.scenario_type.lower().replace("-", "_")
        
        if scenario_type == "rollout_restart":
            return self._rollout_restart(scenario)
        elif scenario_type == "node_drain":
            return self._node_drain(scenario)
        elif scenario_type == "pod_kill":
            return self._pod_kill(scenario)
        elif scenario_type == "canary_weight_shift":
            return self._canary_weight_shift(scenario)
        else:
            raise ValueError(f"Unknown scenario type: {scenario.scenario_type}")

    def _rollout_restart(self, scenario: ChaosScenario) -> Dict[str, Any]:
        if self.mock_mode:
            return self._generate_mock_response(scenario)
        
        cmd = f"kubectl rollout restart deployment/{scenario.target_resource} -n {scenario.namespace}"
        result = self.driver.execute_command(cmd)
        return self._build_result(scenario, result)

    def _node_drain(self, scenario: ChaosScenario) -> Dict[str, Any]:
        if self.mock_mode:
            return self._generate_mock_response(scenario)
        
        cmd = f"kubectl drain {scenario.target_resource} --ignore-daemonsets --delete-emptydir-data --force"
        result = self.driver.execute_command(cmd)
        return self._build_result(scenario, result)

    def _pod_kill(self, scenario: ChaosScenario) -> Dict[str, Any]:
        if self.mock_mode:
            return self._generate_mock_response(scenario)
        
        cmd = f"kubectl delete pod {scenario.target_resource} -n {scenario.namespace} --grace-period=0 --force"
        result = self.driver.execute_command(cmd)
        return self._build_result(scenario, result)

    def _canary_weight_shift(self, scenario: ChaosScenario) -> Dict[str, Any]:
        if self.mock_mode:
            return self._generate_mock_response(scenario)
        
        # For canary weight shift, we might update replicas or annotations
        # This is a simplified implementation
        params = scenario.params if hasattr(scenario, 'params') and scenario.params else {}
        weight = params.get('weight', 50)
        
        # Example: update deployment annotations for canary weight
        cmd = f"kubectl annotate deployment/{scenario.target_resource} -n {scenario.namespace} canary-weight={weight} --overwrite"
        result = self.driver.execute_command(cmd)
        return self._build_result(scenario, result)

    def _generate_mock_response(self, scenario: ChaosScenario) -> Dict[str, Any]:
        return {
            "scenario_id": str(uuid.uuid4()),
            "scenario_type": scenario.scenario_type,
            "cluster": scenario.cluster,
            "target": scenario.target_resource,
            "namespace": scenario.namespace,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "success",
            "events_generated": [
                {"event": "pod_scheduled", "pod": f"{scenario.target_resource}-canary-xyz", "phase": "Pending"},
                {"event": "node_modified", "node": scenario.target_resource, "status": "SchedulingDisabled"}
            ]
        }

    def _build_result(self, scenario: ChaosScenario, driver_result: Any) -> Dict[str, Any]:
        if isinstance(driver_result, dict):
            result = driver_result.copy()
        else:
            result = {"raw_output": str(driver_result)}
        
        result.update({
            "scenario_id": str(uuid.uuid4()),
            "scenario_type": scenario.scenario_type,
            "cluster": scenario.cluster,
            "target": scenario.target_resource,
            "namespace": scenario.namespace,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "success" if result.get("status", "success") == "success" else "failed"
        })
        
        if "events_generated" not in result:
            result["events_generated"] = []
            
        return result


def run_chaos_scenario(
    scenario_type: str,
    cluster: str,
    target: str,
    namespace: str = "default",
    params: Optional[Dict[str, Any]] = None,
    mock_mode: bool = False
) -> Dict[str, Any]:
    scenario = ChaosScenario(
        scenario_type=scenario_type,
        cluster=cluster,
        target_resource=target,
        namespace=namespace,
        params=params or {}
    )
    injector = ChaosInjector(mock_mode=mock_mode)
    return injector.inject(scenario)
