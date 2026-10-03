#!/usr/bin/env python3
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

def run():
    print("\nRegenerating src/testbed/drivers/k3d.py with concise mock kubeconfig ...")
    system_prompt = "You are Jagular (177B Big Iron on Chunkito), lead Python systems architect. Output ONLY valid, executable Python code with no markdown commentary."
    user_prompt = """SPEC-06 / TASK-CV-702:
Author `src/testbed/drivers/k3d.py`: Concrete K3dDriver implementing ClusterDriver.

CRITICAL REQUIREMENT:
For mock kubeconfig in `get_kubeconfig(self, cluster_name: str)`, DO NOT generate a huge 10KB base64 blob! Use a short string like:
certificate-authority-data: "LS0tLS1tb2NrLWNlcnQtZGF0YS0tLS0tCg=="
and keep the yaml template under 15 lines.

Full Requirements:
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
         Executes locally or via SSH. Returns returncode == 0.

   - `delete_cluster(self, cluster_name: str) -> bool`:
     If mock_mode: removes from `_mock_clusters`, returns True.
     Else: runs `k3d cluster delete {cluster_name}`.

   - `get_cluster_status(self, cluster_name: str) -> ClusterStatus`:
     If mock_mode:
         if cluster_name in self._mock_clusters:
             return ClusterStatus(name=cluster_name, driver="k3d", status="running", api_endpoint=f"https://{self.tailscale_ip}:6443", server_count=1, agent_count=2, operator_stream_url=f"http://{self.tailscale_ip}:8081/api/v1/topology/stream")
         else:
             return ClusterStatus(name=cluster_name, driver="k3d", status="not_found", api_endpoint="")
     Else:
         runs `k3d cluster list {cluster_name} -o json`. Parses JSON. Returns ClusterStatus.

   - `get_kubeconfig(self, cluster_name: str) -> str`:
     If mock_mode:
         return short valid YAML kubeconfig with clusters, contexts, users.
     Else:
         runs `k3d kubeconfig get {cluster_name}`. Replaces `0.0.0.0` or `127.0.0.1` with `self.tailscale_ip`.

   - `apply_manifest(self, cluster_name: str, manifest_path_or_yaml: str) -> bool`:
     If mock_mode: return True.
     Else: applies manifest via `kubectl apply`.

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

if __name__ == "__main__":
    run()
