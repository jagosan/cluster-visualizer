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


class K3dDriver(ClusterDriver):
    def __init__(self, host: str = "chunkito", mock_mode: bool = False, tailscale_ip: str = "100.71.183.123"):
        self.host = host
        self.mock_mode = mock_mode
        self.tailscale_ip = tailscale_ip
        self._mock_clusters: Dict[str, Dict[str, Any]] = {}

    def create_cluster(self, spec: ClusterSpec) -> bool:
        if self.mock_mode or os.environ.get("K3D_MOCK") == "1":
            self._mock_clusters[spec.name] = {
                "status": "running",
                "api_endpoint": f"https://{self.tailscale_ip}:{spec.api_port}",
                "servers": spec.servers,
                "agents": spec.agents,
                "kubernetes_version": spec.kubernetes_version,
            }
            logger.info(f"Mock cluster {spec.name} created")
            return True

        cmd = [
            "k3d", "cluster", "create", spec.name,
            "--servers", str(spec.servers),
            "--agents", str(spec.agents),
            "--port", f"{spec.api_port}:6443@loadbalancer",
            "--image", f"rancher/k3s:{spec.kubernetes_version}",
            "--no-lb=false",
            "--wait",
        ]

        if spec.operator.enabled and spec.operator.host_port:
            cmd.extend(["--port", f"{spec.operator.host_port}:8080@loadbalancer"])

        returncode, stdout, stderr = self.execute_command(cmd)
        if returncode != 0:
            logger.error(f"Failed to create cluster {spec.name}: {stderr}")
            return False
        logger.info(f"Cluster {spec.name} created successfully")
        return True

    def delete_cluster(self, cluster_name: str) -> bool:
        if self.mock_mode:
            if cluster_name in self._mock_clusters:
                del self._mock_clusters[cluster_name]
                logger.info(f"Mock cluster {cluster_name} deleted")
                return True
            logger.warning(f"Mock cluster {cluster_name} not found for deletion")
            return False

        cmd = ["k3d", "cluster", "delete", cluster_name]
        returncode, stdout, stderr = self.execute_command(cmd)
        if returncode != 0:
            logger.error(f"Failed to delete cluster {cluster_name}: {stderr}")
            return False
        logger.info(f"Cluster {cluster_name} deleted successfully")
        return True

    def get_cluster_status(self, cluster_name: str) -> ClusterStatus:
        if self.mock_mode:
            if cluster_name in self._mock_clusters:
                cluster_data = self._mock_clusters[cluster_name]
                return ClusterStatus(
                    name=cluster_name,
                    driver="k3d",
                    status="running",
                    api_endpoint=f"https://{self.tailscale_ip}:6443",
                    server_count=cluster_data.get("servers", 1),
                    agent_count=cluster_data.get("agents", 2),
                    operator_stream_url=f"http://{self.tailscale_ip}:8081/api/v1/topology/stream",
                )
            else:
                return ClusterStatus(
                    name=cluster_name,
                    driver="k3d",
                    status="not_found",
                    api_endpoint="",
                )

        cmd = ["k3d", "cluster", "list", cluster_name, "-o", "json"]
        returncode, stdout, stderr = self.execute_command(cmd)
        if returncode != 0:
            logger.error(f"Failed to get status for cluster {cluster_name}: {stderr}")
            return ClusterStatus(
                name=cluster_name,
                driver="k3d",
                status="error",
                api_endpoint="",
            )

        try:
            data = json.loads(stdout)
            if not data:
                return ClusterStatus(
                    name=cluster_name,
                    driver="k3d",
                    status="not_found",
                    api_endpoint="",
                )
            cluster_info = data[0]
            nodes = cluster_info.get("nodes", [])
            server_count = sum(1 for n in nodes if "server" in n.get("role", []))
            agent_count = sum(1 for n in nodes if "agent" in n.get("role", []))
            api_endpoint = f"https://{self.tailscale_ip}:6443"
            return ClusterStatus(
                name=cluster_name,
                driver="k3d",
                status="running",
                api_endpoint=api_endpoint,
                server_count=server_count,
                agent_count=agent_count,
                operator_stream_url=f"http://{self.tailscale_ip}:8081/api/v1/topology/stream",
            )
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error(f"Failed to parse cluster status JSON: {e}")
            return ClusterStatus(
                name=cluster_name,
                driver="k3d",
                status="error",
                api_endpoint="",
            )

    def get_kubeconfig(self, cluster_name: str) -> str:
        if self.mock_mode:
            return f"""apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority-data: "LS0tLS1tb2NrLWNlcnQtZGF0YS0tLS0tCg=="
    server: https://{self.tailscale_ip}:6443
  name: {cluster_name}
contexts:
- context:
    cluster: {cluster_name}
    user: {cluster_name}-user
  name: {cluster_name}
current-context: {cluster_name}
users:
- name: {cluster_name}-user
  user:
    client-certificate-data: "LS0tLS1tb2NrLWNsaWVudC1jZXJ0LS0tLS0tCg=="
    client-key-data: "LS0tLS1tb2NrLWNsaWVudC1rZXktLS0tLS0tCg=="
"""

        cmd = ["k3d", "kubeconfig", "get", cluster_name]
        returncode, stdout, stderr = self.execute_command(cmd)
        if returncode != 0:
            logger.error(f"Failed to get kubeconfig for cluster {cluster_name}: {stderr}")
            return ""

        kubeconfig = stdout
        kubeconfig = kubeconfig.replace("0.0.0.0", self.tailscale_ip)
        kubeconfig = kubeconfig.replace("127.0.0.1", self.tailscale_ip)
        return kubeconfig

    def apply_manifest(self, cluster_name: str, manifest_path_or_yaml: str) -> bool:
        if self.mock_mode:
            logger.info(f"Mock apply manifest for cluster {cluster_name}")
            return True

        kubeconfig_path = None
        try:
            kubeconfig_content = self.get_kubeconfig(cluster_name)
            if not kubeconfig_content:
                logger.error(f"Could not retrieve kubeconfig for cluster {cluster_name}")
                return False

            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                f.write(kubeconfig_content)
                kubeconfig_path = f.name

            if Path(manifest_path_or_yaml).exists():
                cmd = [
                    "kubectl",
                    "--kubeconfig", kubeconfig_path,
                    "apply",
                    "-f", manifest_path_or_yaml,
                ]
            else:
                import tempfile
                with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                    f.write(manifest_path_or_yaml)
                    manifest_temp_path = f.name
                cmd = [
                    "kubectl",
                    "--kubeconfig", kubeconfig_path,
                    "apply",
                    "-f", manifest_temp_path,
                ]

            returncode, stdout, stderr = self.execute_command(cmd)
            if returncode != 0:
                logger.error(f"Failed to apply manifest for cluster {cluster_name}: {stderr}")
                return False
            logger.info(f"Manifest applied successfully for cluster {cluster_name}")
            return True
        finally:
            if kubeconfig_path and Path(kubeconfig_path).exists():
                try:
                    os.unlink(kubeconfig_path)
                except OSError:
                    pass

    def execute_command(self, cmd: List[str] | str) -> tuple[int, str, str]:
        if self.mock_mode:
            logger.debug(f"Mock executing command: {cmd}")
            return (0, "", "")

        if isinstance(cmd, str):
            cmd_list = cmd.split()
        else:
            cmd_list = list(cmd)

        try:
            result = subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return (result.returncode, result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {cmd}")
            return (1, "", "Command timed out")
        except Exception as e:
            logger.error(f"Error executing command {cmd}: {e}")
            return (1, "", str(e))
