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


def load_fleet_spec(path: str | Path) -> FleetSpec:
    """Parses yaml or json into FleetSpec."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Fleet spec file not found: {path}")

    content = path.read_text()
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
            data = yaml.safe_load(content)
        except ImportError:
            raise ImportError("PyYAML is required to load YAML fleet specs")
    elif path.suffix.lower() == ".json":
        data = json.loads(content)
    else:
        raise ValueError(f"Unsupported file extension: {path.suffix}")

    return FleetSpec(**data)


class TestbedManager:
    def __init__(
        self,
        fleet_spec: FleetSpec,
        mock_mode: bool = False,
        driver: Optional[ClusterDriver] = None,
    ):
        self.fleet_spec = fleet_spec
        self.mock_mode = mock_mode
        if driver is not None:
            self.driver = driver
        else:
            self.driver = K3dDriver(host=fleet_spec.host, mock_mode=mock_mode)

        self.output_dir = Path("testbeds")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.kubeconfig_path = self.output_dir / "kubeconfig.yaml"

    def up(self) -> FleetStatusReport:
        """Brings up all clusters in the fleet."""
        for cluster_spec in self.fleet_spec.clusters:
            logger.info(f"Creating cluster: {cluster_spec.name}")
            self.driver.create_cluster(cluster_spec)

            # Fetch kubeconfig and merge
            kubeconfig_content = self.driver.get_kubeconfig(cluster_spec.name)
            if kubeconfig_content:
                self._merge_kubeconfig(kubeconfig_content)

            # Apply workloads if specified
            if cluster_spec.workloads:
                logger.info(f"Applying workloads to cluster: {cluster_spec.name}")
                self.apply_workloads(cluster_spec.name, cluster_spec.workloads)

            # Deploy operator if enabled
            if cluster_spec.operator and cluster_spec.operator.enabled:
                logger.info(f"Deploying operator to cluster: {cluster_spec.name}")
                self.deploy_operator(cluster_spec.name)

        return self.status()

    def down(self) -> bool:
        """Tears down all clusters in the fleet."""
        for cluster_spec in self.fleet_spec.clusters:
            logger.info(f"Deleting cluster: {cluster_spec.name}")
            self.driver.delete_cluster(cluster_spec.name)

        # Clean up kubeconfig
        if self.kubeconfig_path.exists():
            self.kubeconfig_path.unlink()
            logger.info(f"Removed kubeconfig: {self.kubeconfig_path}")

        return True

    def status(self) -> FleetStatusReport:
        """Queries status for all clusters and aggregates into FleetStatusReport."""
        cluster_statuses: List[ClusterStatus] = []
        for cluster_spec in self.fleet_spec.clusters:
            try:
                status = self.driver.get_cluster_status(cluster_spec.name)
                cluster_statuses.append(status)
            except Exception as e:
                logger.error(f"Failed to get status for cluster {cluster_spec.name}: {e}")
                cluster_statuses.append(
                    ClusterStatus(
                        name=cluster_spec.name,
                        driver="k3d",
                        status="error",
                        api_endpoint="",
                        raw_info={"error": str(e)},
                    )
                )

        timestamp = datetime.now(timezone.utc).isoformat()
        total_clusters = len(self.fleet_spec.clusters)
        running_clusters = sum(1 for s in cluster_statuses if s.status == "running")
        return FleetStatusReport(
            fleet_name=self.fleet_spec.fleet_name,
            host=self.fleet_spec.host,
            timestamp=timestamp,
            total_clusters=total_clusters,
            running_clusters=running_clusters,
            clusters=cluster_statuses,
        )

    def deploy_operator(self, cluster_name: Optional[str] = None) -> Dict[str, bool]:
        """Deploys the operator to specified cluster(s)."""
        results: Dict[str, bool] = {}

        if cluster_name is not None:
            target_clusters = [c for c in self.fleet_spec.clusters if c.name == cluster_name]
        else:
            target_clusters = self.fleet_spec.clusters

        crd_path = Path("deploy/crd/clustervis.io_clustertopologysnapshots.yaml")
        operator_path = Path("deploy/operator/operator.yaml")

        for cluster_spec in target_clusters:
            name = cluster_spec.name
            success = True

            # Apply CRD
            if crd_path.exists():
                try:
                    crd_content = crd_path.read_text()
                    self.driver.apply_manifest(name, crd_content)
                except Exception as e:
                    logger.error(f"Failed to apply CRD to {name}: {e}")
                    success = False
            else:
                logger.warning(f"CRD file not found: {crd_path}")
                success = False

            # Apply operator
            if operator_path.exists():
                try:
                    operator_content = operator_path.read_text()
                    self.driver.apply_manifest(name, operator_content)
                except Exception as e:
                    logger.error(f"Failed to apply operator to {name}: {e}")
                    success = False
            else:
                logger.warning(f"Operator file not found: {operator_path}")
                success = False

            results[name] = success

        return results

    def apply_workloads(self, cluster_name: str, workload_paths: List[str]) -> bool:
        """Applies each workload YAML path using driver.apply_manifest."""
        all_success = True
        for workload_path in workload_paths:
            path = Path(workload_path)
            if not path.exists():
                logger.error(f"Workload file not found: {workload_path}")
                all_success = False
                continue

            try:
                content = path.read_text()
                self.driver.apply_manifest(cluster_name, content)
                logger.info(f"Applied workload {workload_path} to {cluster_name}")
            except Exception as e:
                logger.error(f"Failed to apply workload {workload_path} to {cluster_name}: {e}")
                all_success = False

        return all_success

    def _merge_kubeconfig(self, kubeconfig_content: str) -> None:
        """Merges new kubeconfig content into the aggregated kubeconfig file."""
        if not kubeconfig_content:
            return

        try:
            import yaml
        except ImportError:
            logger.error("PyYAML is required for kubeconfig merging")
            return

        new_config = yaml.safe_load(kubeconfig_content)
        if not new_config:
            return

        # Load existing config if present
        existing_config = None
        if self.kubeconfig_path.exists():
            try:
                existing_content = self.kubeconfig_path.read_text()
                existing_config = yaml.safe_load(existing_content)
            except Exception:
                existing_config = None

        if existing_config is None:
            existing_config = {
                "apiVersion": "v1",
                "kind": "Config",
                "clusters": [],
                "contexts": [],
                "users": [],
            }

        # Merge clusters
        existing_clusters = {c["name"]: c for c in existing_config.get("clusters", [])}
        for cluster in new_config.get("clusters", []):
            existing_clusters[cluster["name"]] = cluster
        existing_config["clusters"] = list(existing_clusters.values())

        # Merge contexts
        existing_contexts = {c["name"]: c for c in existing_config.get("contexts", [])}
        for context in new_config.get("contexts", []):
            existing_contexts[context["name"]] = context
        existing_config["contexts"] = list(existing_contexts.values())

        # Merge users
        existing_users = {u["name"]: u for u in existing_config.get("users", [])}
        for user in new_config.get("users", []):
            existing_users[user["name"]] = user
        existing_config["users"] = list(existing_users.values())

        # Set current context to the first context if not set
        if "current-context" not in existing_config and existing_config["contexts"]:
            existing_config["current-context"] = existing_config["contexts"][0]["name"]

        # Write back
        self.kubeconfig_path.write_text(yaml.dump(existing_config, default_flow_style=False))
        logger.info(f"Updated kubeconfig: {self.kubeconfig_path}")
