"""In-cluster Kubernetes topology informer controller."""

import queue
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.ingestion.models import (
    ClusterGraph,
    ClusterMetadata,
    DataFlowEdge,
    MachineShape,
    NodeComponent,
    RemoteServiceResource,
)
from src.ingestion.frameworks import enrich_framework_components
from src.ingestion.layout import (
    apply_spatial_layout,
    apply_subterranean_layout,
    generate_skyscraper_edges,
)
from src.ingestion.exporter import generate_mock_cluster_graph
from src.operator.kcc_mapper import parse_kcc_resource, parse_node_machine_shape


class TopologyController:
    """Kubernetes topology informer controller with real-time mutation injection."""

    def __init__(self, cluster_name: str = "in-cluster"):
        self.cluster_name = cluster_name
        self.nodes: Dict[str, NodeComponent] = {}
        self.edges: List[DataFlowEdge] = []
        self.subterranean_resources: Dict[str, RemoteServiceResource] = {}
        self.machine_shapes: Dict[str, MachineShape] = {}
        self.listeners: List[queue.Queue] = []
        self.lock = threading.RLock()
        self.running = False
        self.worker_thread: Optional[threading.Thread] = None

    def add_listener(self, q: queue.Queue) -> None:
        with self.lock:
            self.listeners.append(q)

    def remove_listener(self, q: queue.Queue) -> None:
        with self.lock:
            if q in self.listeners:
                self.listeners.remove(q)

    def broadcast_event(self, event_name: str, payload: dict) -> None:
        with self.lock:
            for q in self.listeners:
                try:
                    q.put_nowait((event_name, payload))
                except (queue.Full, BrokenPipeError):
                    pass

    def get_snapshot(self) -> dict:
        with self.lock:
            if not self.nodes:
                self._seed_mock_data()
            nodes_list = list(self.nodes.values())
            nodes_list, edges_list = enrich_framework_components(nodes_list, list(self.edges))
            nodes_list = apply_spatial_layout(nodes_list)
            self.edges = generate_skyscraper_edges(nodes_list)
            for n in nodes_list:
                self.nodes[n.id] = n

            apply_subterranean_layout(
                list(self.machine_shapes.values()),
                list(self.subterranean_resources.values()),
            )

            meta = ClusterMetadata(
                cluster_name=self.cluster_name,
                kubernetes_version="v1.36.4",
                distribution="in-cluster",
                timestamp=datetime.now(timezone.utc).isoformat(),
                node_count=len([n for n in nodes_list if n.kind == "Node"]),
                pod_count=len([n for n in nodes_list if n.kind == "Pod"]),
            )
            graph = ClusterGraph(
                metadata=meta,
                nodes=nodes_list,
                edges=self.edges,
                subterranean_resources=list(self.subterranean_resources.values()),
                machine_shapes=list(self.machine_shapes.values()),
            )
            return graph.model_dump()

    def inject_mutation(self, event_name: str, payload: dict) -> None:
        with self.lock:
            ts = datetime.now(timezone.utc).isoformat()
            if event_name == "node_added":
                node_data = payload.get("node")
                node = NodeComponent(**node_data) if isinstance(node_data, dict) else node_data
                self.nodes[node.id] = node
                nodes_list = list(self.nodes.values())
                nodes_list, _ = enrich_framework_components(nodes_list, list(self.edges))
                nodes_list = apply_spatial_layout(nodes_list)
                self.edges = generate_skyscraper_edges(nodes_list)
                for n in nodes_list:
                    self.nodes[n.id] = n
                placed_node = next(n for n in nodes_list if n.id == node.id)
                self.broadcast_event("node_added", {"node": placed_node.model_dump(), "timestamp": ts})
            elif event_name == "node_removed":
                nid = payload.get("node_id")
                if nid in self.nodes:
                    del self.nodes[nid]
                    nodes_list = list(self.nodes.values())
                    nodes_list = apply_spatial_layout(nodes_list)
                    self.edges = generate_skyscraper_edges(nodes_list)
                    for n in nodes_list:
                        self.nodes[n.id] = n
                self.broadcast_event("node_removed", {"node_id": nid, "timestamp": ts})
            elif event_name == "node_modified":
                nid = payload.get("node_id")
                if nid in self.nodes:
                    node = self.nodes[nid]
                    if "status" in payload:
                        node.status = payload["status"]
                self.broadcast_event("node_modified", payload)
            elif event_name == "edge_updated":
                self.broadcast_event("edge_updated", payload)
            elif event_name == "subterranean_resource_added":
                raw = payload.get("resource")
                if raw is None:
                    return
                if isinstance(raw, RemoteServiceResource):
                    res = raw
                elif isinstance(raw, dict) and raw.get("apiVersion") and raw.get("kind"):
                    res = parse_kcc_resource(raw)
                else:
                    res = RemoteServiceResource(**raw)
                if res is None:
                    return
                self.subterranean_resources[res.id] = res
                self._reapply_subterranean_layout()
                self.broadcast_event("subterranean_resource_added", {
                    "resource": res.model_dump(), "timestamp": ts,
                })
            elif event_name == "subterranean_resource_removed":
                rid = payload.get("resource_id")
                if rid in self.subterranean_resources:
                    del self.subterranean_resources[rid]
                    self._reapply_subterranean_layout()
                self.broadcast_event("subterranean_resource_removed", {
                    "resource_id": rid, "timestamp": ts,
                })
            elif event_name == "subterranean_resource_modified":
                rid = str(payload.get("resource_id", ""))
                res = self.subterranean_resources.get(rid)
                if res is not None:
                    if "status_phase" in payload:
                        res.status_phase = str(payload["status_phase"])
                    fields = payload.get("fields")
                    if isinstance(fields, dict):
                        for key, value in fields.items():
                            if hasattr(res, key):
                                setattr(res, key, value)
                self.broadcast_event("subterranean_resource_modified", {
                    "resource_id": rid,
                    "resource": res.model_dump() if res is not None else None,
                    "timestamp": ts,
                })
            elif event_name == "machine_shape_updated":
                raw = payload.get("shape", payload.get("machine_shape"))
                if raw is None:
                    return
                if isinstance(raw, MachineShape):
                    shape = raw
                elif isinstance(raw, dict) and ("metadata" in raw or "apiVersion" in raw):
                    shape = parse_node_machine_shape(raw)
                else:
                    shape = MachineShape(**raw)
                self.machine_shapes[shape.node_name] = shape
                self._reapply_subterranean_layout()
                self.broadcast_event("machine_shape_updated", {
                    "shape": shape.model_dump(), "timestamp": ts,
                })

    def _reapply_subterranean_layout(self) -> None:
        """Re-dock chassis row and vault grid after a subterranean mutation.

        Caller must hold self.lock.
        """
        apply_subterranean_layout(
            list(self.machine_shapes.values()),
            list(self.subterranean_resources.values()),
        )

    def _seed_mock_data(self) -> None:
        g = generate_mock_cluster_graph()
        self.nodes = {n.id: n for n in g.nodes}
        self.edges = g.edges

        # SPEC-08: subterranean strata — managed cloud vaults + compute chassis.
        mock_crds = [
            {
                "apiVersion": "sql.cnrm.cloud.google.com/v1beta1",
                "kind": "SQLInstance",
                "metadata": {"name": "sql-prod", "namespace": "default"},
                "spec": {"tier": "db-custom-4-16384", "region": "us-central1"},
                "status": {"conditions": [{"type": "Ready", "status": "True"}],
                           "selfLink": "https://sqladmin.googleapis.com/sql/projects/demo/instances/sql-prod"},
            },
            {
                "apiVersion": "storage.cnrm.cloud.google.com/v1beta1",
                "kind": "StorageBucket",
                "metadata": {"name": "media-vault", "namespace": "default"},
                "spec": {"location": "US"},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            },
            {
                "apiVersion": "pubsub.cnrm.cloud.google.com/v1beta1",
                "kind": "PubSubTopic",
                "metadata": {"name": "events-feed", "namespace": "default"},
                "spec": {"messageStoragePolicy": {"allowedPersistenceRegions": ["us-central1"]}},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            },
            {
                "apiVersion": "redis.cnrm.cloud.google.com/v1beta1",
                "kind": "RedisInstance",
                "metadata": {"name": "session-cache", "namespace": "default"},
                "spec": {"tier": "STANDARD_HA", "memoryGb": 16},
                "status": {"phase": "Ready", "host": "10.0.42.72"},
            },
            {
                "apiVersion": "kro.run/v1alpha1",
                "kind": "AppManifold",
                "metadata": {
                    "name": "kro-app-manifold",
                    "namespace": "kro-system",
                    "annotations": {"kro.run/resource-graph-name": "app-manifold-graph"},
                },
                "spec": {},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            },
        ]
        for raw in mock_crds:
            vault = parse_kcc_resource(raw)
            if vault is not None:
                self.subterranean_resources[vault.id] = vault

        mock_nodes = [
            {
                "metadata": {
                    "name": "gpu-node-1",
                    "labels": {
                        "node.kubernetes.io/instance-type": "g2-standard-16",
                        "cloud.google.com/gke-accelerator": "nvidia-l4",
                        "cloud.google.com/gke-nodepool": "gpu-pool",
                        "topology.kubernetes.io/zone": "us-central1-c",
                    },
                },
                "status": {
                    "capacity": {"cpu": "16", "memory": "66724464Ki", "nvidia.com/gpu": "1"},
                    "allocatable": {"cpu": "15930m", "memory": "64536208Ki", "nvidia.com/gpu": "1"},
                },
            },
            {
                "metadata": {
                    "name": "spot-node-1",
                    "labels": {
                        "node.kubernetes.io/instance-type": "n2-standard-8",
                        "karpenter.sh/capacity-type": "spot",
                        "karpenter.sh/nodepool": "spot-pool",
                        "topology.kubernetes.io/zone": "us-central1-a",
                    },
                },
                "status": {
                    "capacity": {"cpu": "8", "memory": "32768Mi"},
                    "allocatable": {"cpu": "7910m", "memory": "31460Mi"},
                },
            },
        ]
        for raw in mock_nodes:
            shape = parse_node_machine_shape(raw)
            self.machine_shapes[shape.node_name] = shape

    def _run_mock_loop(self, interval: float) -> None:
        counter = 0
        while self.running:
            time.sleep(interval)
            if not self.running:
                break
            counter += 1
            if counter % 3 == 1:
                self.inject_mutation("node_added", {
                    "node": {
                        "id": f"pod-demo-{counter}",
                        "layer": "workload",
                        "kind": "Pod",
                        "name": f"demo-worker-{counter}",
                        "namespace": "default",
                        "version": "v1.0.0",
                    }
                })
            elif counter % 3 == 2:
                self.inject_mutation("node_modified", {
                    "node_id": f"pod-demo-{counter - 1}",
                    "status": "version_skew",
                })
            else:
                self.inject_mutation("node_removed", {
                    "node_id": f"pod-demo-{counter - 2}",
                })

    def _run_real_loop(self, interval: float) -> None:
        while self.running:
            time.sleep(interval)

    def start(self, mock: bool = False, poll_interval: float = 10.0) -> None:
        if self.running:
            return
        self.running = True
        target = self._run_mock_loop if mock else self._run_real_loop
        self.worker_thread = threading.Thread(target=target, args=(poll_interval,), daemon=True)
        self.worker_thread.start()

    def stop(self) -> None:
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5.0)
