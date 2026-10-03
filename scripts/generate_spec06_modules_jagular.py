#!/usr/bin/env python3
"""
Jagular Generator for SPEC-06 Testbed Modules.
Leverages Jagular (177B Big Iron on Chunkito) with 8k+ output budget per module
and strict fence sanitation.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def clean_code(raw: str) -> str:
    raw = raw.strip()
    match = re.search(r"```(?:python)?\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    lines = raw.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()

def run_base_driver():
    print("\n[1/5] Generating src/testbed/drivers/base.py ...")
    system_prompt = "You are Jagular (177B Big Iron on Chunkito), lead Python systems architect. Output ONLY valid, executable Python code with no markdown commentary."
    user_prompt = """SPEC-06 / TASK-CV-702:
Author `src/testbed/drivers/base.py`: Abstract Base Class for Cluster Drivers.

Requirements:
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from ..models import ClusterSpec, ClusterStatus

class ClusterDriver(ABC):
    def __init__(self, host: str = "chunkito", mock_mode: bool = False):
        self.host = host
        self.mock_mode = mock_mode

    @abstractmethod
    def create_cluster(self, spec: ClusterSpec) -> bool:
        pass

    @abstractmethod
    def delete_cluster(self, cluster_name: str) -> bool:
        pass

    @abstractmethod
    def get_cluster_status(self, cluster_name: str) -> ClusterStatus:
        pass

    @abstractmethod
    def get_kubeconfig(self, cluster_name: str) -> str:
        pass

    @abstractmethod
    def apply_manifest(self, cluster_name: str, manifest_path_or_yaml: str) -> bool:
        pass

    @abstractmethod
    def execute_command(self, cmd: List[str] | str) -> tuple[int, str, str]:
        pass
"""
    raw = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=4096)
    code = clean_code(raw)
    path = os.path.join(REPO_ROOT, "src", "testbed", "drivers", "base.py")
    with open(path, "w") as f:
        f.write(code + "\n")
    print(f"Authored {path}")

def run_k3d_driver():
    print("\n[2/5] Generating src/testbed/drivers/k3d.py ...")
    system_prompt = "You are Jagular (177B Big Iron on Chunkito), lead Python systems architect. Output ONLY valid, executable Python code with no markdown commentary."
    user_prompt = """SPEC-06 / TASK-CV-702:
Author `src/testbed/drivers/k3d.py`: Concrete K3dDriver implementing ClusterDriver.

Requirements:
1. Imports:
from __future__ import annotations
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .base import ClusterDriver
from ..models import ClusterSpec, ClusterStatus

logger = logging.getLogger(__name__)

2. Class `K3dDriver(ClusterDriver)`:
   - Inherits from `ClusterDriver`.
   - `__init__(self, host: str = "chunkito", mock_mode: bool = False, tailscale_ip: str = "100.71.183.123")`
   - State for mock mode: internal dictionary `_mock_clusters: Dict[str, Dict[str, Any]]`.
   - `create_cluster(self, spec: ClusterSpec) -> bool`:
     If mock_mode or os.environ.get("K3D_MOCK") == "1":
         registers cluster in `_mock_clusters` as "running" with api_endpoint `f"https://{self.tailscale_ip}:{spec.api_port}"`.
         Returns True.
     Else:
         Builds k3d command:
         `k3d cluster create {spec.name} --servers {spec.servers} --agents {spec.agents} --port "{spec.api_port}:6443@loadbalancer" --image rancher/k3s:{spec.kubernetes_version} --no-lb=false --wait`
         If spec.operator.enabled and spec.operator.host_port:
             adds `--port "{spec.operator.host_port}:8080@loadbalancer"`
         Executes either via local subprocess (if host in ("localhost", "127.0.0.1") or already on chunkito) or via SSH (`ssh {self.host} ...`).
         Returns returncode == 0.

   - `delete_cluster(self, cluster_name: str) -> bool`:
     If mock_mode: removes from `_mock_clusters`, returns True.
     Else: runs `k3d cluster delete {cluster_name}`.

   - `get_cluster_status(self, cluster_name: str) -> ClusterStatus`:
     If mock_mode:
         if cluster in _mock_clusters:
             returns ClusterStatus(name=cluster_name, driver="k3d", status="running", api_endpoint=f"https://{self.tailscale_ip}:6443", server_count=1, agent_count=2, operator_stream_url=f"http://{self.tailscale_ip}:8081/api/v1/topology/stream")
         else:
             returns ClusterStatus(name=cluster_name, driver="k3d", status="not_found", api_endpoint="")
     Else:
         runs `k3d cluster list {cluster_name} -o json`. Parses JSON. Returns ClusterStatus.

   - `get_kubeconfig(self, cluster_name: str) -> str`:
     If mock_mode: returns mock YAML kubeconfig pointing to `https://{self.tailscale_ip}:64431`.
     Else: runs `k3d kubeconfig get {cluster_name}`. Replaces `0.0.0.0` or `127.0.0.1` with `self.tailscale_ip`.

   - `apply_manifest(self, cluster_name: str, manifest_path_or_yaml: str) -> bool`:
     Applies manifest via `kubectl --kubeconfig <path> apply -f <manifest>` or mock True.

   - `execute_command(self, cmd: List[str] | str) -> tuple[int, str, str]`:
     Executes locally or via SSH, or simulates if mock_mode.

Ensure complete, clean code with NO truncation and valid syntax.
"""
    raw = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=8192)
    code = clean_code(raw)
    path = os.path.join(REPO_ROOT, "src", "testbed", "drivers", "k3d.py")
    with open(path, "w") as f:
        f.write(code + "\n")
    print(f"Authored {path}")

def run_manager():
    print("\n[3/5] Generating src/testbed/manager.py ...")
    system_prompt = "You are Jagular (177B Big Iron on Chunkito), lead Python systems architect. Output ONLY valid, executable Python code with no markdown commentary."
    user_prompt = """SPEC-06 / TASK-CV-703:
Author `src/testbed/manager.py`: TestbedManager coordinating fleet lifecycle and operator deployment.

Requirements:
1. Imports:
from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    ClusterSpec,
    ClusterStatus,
    FleetSpec,
    FleetStatusReport,
    OperatorConfig,
)
from .drivers.base import ClusterDriver
from .drivers.k3d import K3dDriver

logger = logging.getLogger(__name__)

2. Helper functions:
   `load_fleet_spec(path: str | Path) -> FleetSpec`: parses yaml or json into FleetSpec.

3. Class `TestbedManager`:
   - `def __init__(self, fleet_spec: FleetSpec, mock_mode: bool = False, driver: Optional[ClusterDriver] = None)`:
     initializes driver (defaults to K3dDriver with fleet_spec.host and mock_mode).
     Creates output directory `testbeds/` if needed.
     Kubeconfig target: `testbeds/kubeconfig.yaml`.
   - `def up(self) -> FleetStatusReport`:
     Loops through `self.fleet_spec.clusters`:
       Calls `self.driver.create_cluster(cluster_spec)`.
       Fetches kubeconfig, appends/merges to `testbeds/kubeconfig.yaml`.
       If cluster_spec.workloads: calls `self.apply_workloads(cluster_spec.name, cluster_spec.workloads)`.
       If cluster_spec.operator.enabled: calls `self.deploy_operator(cluster_spec.name)`.
     Returns `self.status()`.
   - `def down(self) -> bool`:
     Loops through `self.fleet_spec.clusters`:
       Calls `self.driver.delete_cluster(cluster_spec.name)`.
     Cleans up `testbeds/kubeconfig.yaml`.
     Returns True.
   - `def status(self) -> FleetStatusReport`:
     Queries status for all clusters in `self.fleet_spec.clusters`.
     Aggregates into `FleetStatusReport` (timestamp in ISO 8601 UTC).
     Returns the report.
   - `def deploy_operator(self, cluster_name: Optional[str] = None) -> Dict[str, bool]`:
     If cluster_name is None, targets all clusters in fleet.
     For each target:
       Applies `deploy/crd/clustervis.io_clustertopologysnapshots.yaml`
       Applies `deploy/operator/operator.yaml` (or mock equivalent).
       Returns dict of `{cluster_name: success_bool}`.
   - `def apply_workloads(self, cluster_name: str, workload_paths: List[str]) -> bool`:
     Applies each workload YAML path using `self.driver.apply_manifest`. Returns True if all succeed.

Ensure complete, clean code with NO truncation and valid syntax.
"""
    raw = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=8192)
    code = clean_code(raw)
    path = os.path.join(REPO_ROOT, "src", "testbed", "manager.py")
    with open(path, "w") as f:
        f.write(code + "\n")
    print(f"Authored {path}")

def run_chaos():
    print("\n[4/5] Generating src/testbed/chaos.py ...")
    system_prompt = "You are Jagular (177B Big Iron on Chunkito), lead Python systems architect. Output ONLY valid, executable Python code with no markdown commentary."
    user_prompt = """SPEC-06 / TASK-CV-704:
Author `src/testbed/chaos.py`: Chaos and operational event injector.

Requirements:
1. Imports:
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

2. Class `ChaosInjector`:
   - `def __init__(self, driver: Optional[ClusterDriver] = None, mock_mode: bool = False)`:
     Defaults driver to K3dDriver(mock_mode=mock_mode).
   - `def inject(self, scenario: ChaosScenario) -> Dict[str, Any]`:
     Dispatches to:
     - `_rollout_restart(scenario)`: `kubectl rollout restart deployment/{scenario.target_resource} -n {scenario.namespace}`
     - `_node_drain(scenario)`: `kubectl drain {scenario.target_resource} --ignore-daemonsets --delete-emptydir-data --force`
     - `_pod_kill(scenario)`: `kubectl delete pod {scenario.target_resource} -n {scenario.namespace} --grace-period=0 --force`
     - `_canary_weight_shift(scenario)`: updates replicas or annotations
     In mock mode or if driver.mock_mode:
       Returns dictionary with:
       {
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
     In real mode:
       Executes command via `self.driver.execute_command(...)` and returns result dict.

3. Helper function:
   `run_chaos_scenario(scenario_type: str, cluster: str, target: str, namespace: str = "default", params: Optional[Dict[str, Any]] = None, mock_mode: bool = False) -> Dict[str, Any]`

Ensure complete, clean code with NO truncation and valid syntax.
"""
    raw = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=8192)
    code = clean_code(raw)
    path = os.path.join(REPO_ROOT, "src", "testbed", "chaos.py")
    with open(path, "w") as f:
        f.write(code + "\n")
    print(f"Authored {path}")

def run_cli():
    print("\n[5/5] Generating src/testbed/cli.py ...")
    system_prompt = "You are Jagular (177B Big Iron on Chunkito), lead Python systems architect. Output ONLY valid, executable Python code with no markdown commentary."
    user_prompt = """SPEC-06 / Testbed CLI:
Author `src/testbed/cli.py`: Unified CLI for `cluster-vis testbed` commands.

Requirements:
1. Imports:
from __future__ import annotations
import argparse
import json
import logging
import sys
from pathlib import Path

from .models import ChaosScenario, FleetSpec
from .manager import TestbedManager, load_fleet_spec
from .chaos import ChaosInjector

logger = logging.getLogger(__name__)

2. Handlers:
   - `handle_up(args: argparse.Namespace) -> int`:
     Loads fleet spec from `args.config` (default "testbeds/fleet-spec.yaml").
     Instantiates TestbedManager(fleet_spec, mock_mode=args.mock).
     Calls manager.up(). Prints JSON or formatted status summary. Returns 0 on success.
   - `handle_down(args: argparse.Namespace) -> int`:
     Loads fleet spec from `args.config`.
     Instantiates TestbedManager(fleet_spec, mock_mode=args.mock).
     Calls manager.down(). Returns 0.
   - `handle_status(args: argparse.Namespace) -> int`:
     Loads fleet spec from `args.config`.
     Instantiates TestbedManager(fleet_spec, mock_mode=args.mock).
     report = manager.status(). Prints report as formatted JSON. Returns 0.
   - `handle_deploy_operator(args: argparse.Namespace) -> int`:
     Loads fleet spec from `args.config`.
     Instantiates TestbedManager(fleet_spec, mock_mode=args.mock).
     results = manager.deploy_operator(cluster_name=args.cluster). Prints results. Returns 0.
   - `handle_inject(args: argparse.Namespace) -> int`:
     Builds ChaosScenario(scenario_type=args.scenario, cluster=args.cluster, target_resource=args.target, namespace=args.namespace).
     injector = ChaosInjector(mock_mode=args.mock).
     result = injector.inject(scenario). Prints JSON result. Returns 0.

3. Subparser registration:
   `register_testbed_subcommands(subparsers: argparse._SubParsersAction) -> None`:
     Adds 'testbed' subcommand parser with nested subcommands: `up`, `down`, `status`, `deploy-operator`, `inject`.
   `main(argv=None) -> int`:
     Stand-alone entrypoint if run directly as `python3 -m src.testbed.cli ...`.

Ensure complete, clean code with NO truncation and valid syntax.
"""
    raw = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=8192)
    code = clean_code(raw)
    path = os.path.join(REPO_ROOT, "src", "testbed", "cli.py")
    with open(path, "w") as f:
        f.write(code + "\n")
    print(f"Authored {path}")

if __name__ == "__main__":
    run_base_driver()
    run_k3d_driver()
    run_manager()
    run_chaos()
    run_cli()
