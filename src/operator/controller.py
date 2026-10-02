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
    NodeComponent,
)
from src.ingestion.frameworks import enrich_framework_components
from src.ingestion.layout import apply_spatial_layout, generate_skyscraper_edges
from src.ingestion.exporter import generate_mock_cluster_graph


class TopologyController:
    """Kubernetes topology informer controller with real-time mutation injection."""

    def __init__(self, cluster_name: str = "in-cluster"):
        self.cluster_name = cluster_name
        self.nodes: Dict[str, NodeComponent] = {}
        self.edges: List[DataFlowEdge] = []
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

    def _seed_mock_data(self) -> None:
        g = generate_mock_cluster_graph()
        self.nodes = {n.id: n for n in g.nodes}
        self.edges = g.edges

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
