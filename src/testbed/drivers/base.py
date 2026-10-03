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
