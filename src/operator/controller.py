"""In-cluster Kubernetes topology informer controller."""

import queue
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.ingestion.models import (
    AutoscalingStatus,
    ClusterGraph,
    ClusterMetadata,
    DataFlowEdge,
    KarpenterNodeClaim,
    MachineShape,
    NodeComponent,
    RemoteServiceResource,
)
from src.ingestion.frameworks import enrich_framework_components
from src.ingestion.layout import (
    CENTRAL_RISER_X,
    CENTRAL_RISER_Z,
    POD_X_STAGGER,
    STAGING_YARD_FOCUS_X,
    SUPERVISOR_FLOOR_Y,
    apply_spatial_layout,
    apply_subterranean_layout,
    generate_skyscraper_edges,
    ghost_node_positions,
    hpa_lateral_path,
    hpa_scale_out_delta,
    karpenter_tractor_beam,
    parse_resource_quantity,
    vpa_morph_dimensions,
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
        # SPEC-09 §4.2: Karpenter NodeClaims -> Sub-Level B1 ghost chassis
        self.karpenter_node_claims: Dict[str, KarpenterNodeClaim] = {}
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
                karpenter_node_claims=list(self.karpenter_node_claims.values()),
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
            elif event_name == "autoscaling_updated":
                self._apply_autoscaling_update(payload, ts)
            elif event_name == "karpenter_claim_updated":
                self._apply_karpenter_claim_update(payload, ts)

    # -----------------------------------------------------------------
    # SPEC-09 §4.2 / ADR-02 (TASK-CV-1003): Karpenter NodeClaim events
    # -----------------------------------------------------------------

    def _apply_karpenter_claim_update(self, payload: dict, ts: str) -> None:
        """Register/refresh a Karpenter NodeClaim and fan out staging events.

        Emits:
        - ``karpenter_claim_updated``  -> claim snapshot + ghost-chassis dock
          position on Sub-Level B1 (Y = -2.5)
        - ``karpenter_tractor_beam``   -> per pending pod, amber beam
          endpoints from the staging-yard hover position down to the ghost
          chassis (SPEC-09 §4.2)
        """
        raw = payload.get("claim", payload.get("node_claim"))
        if raw is None:
            return
        claim = raw if isinstance(raw, KarpenterNodeClaim) else KarpenterNodeClaim(**raw)
        self.karpenter_node_claims[claim.claim_name] = claim

        # Dock this claim's ghost chassis on Sub-Level B1 alongside the
        # already-provisioned claims.
        names = sorted(self.karpenter_node_claims.keys())
        idx = names.index(claim.claim_name)
        dock = ghost_node_positions(len(names))[idx]

        # Staging focus anchor + tractor beams for every pending pod this
        # claim is provisioning compute for.
        beams = []
        for uid in claim.pending_pod_uids:
            pod = self.nodes.get(uid)
            if pod is None:
                continue
            if pod.pod_geometry is not None:
                pod.pod_geometry.karpenter_target_node_claim = claim.claim_name
            beams.append({
                "node_id": uid,
                "claim_name": claim.claim_name,
                "beam": karpenter_tractor_beam(
                    (pod.spatial.x, pod.spatial.y, pod.spatial.z), dock
                ),
            })

        self.broadcast_event("karpenter_claim_updated", {
            "claim": claim.model_dump(),
            "ghost_position": {"x": dock[0], "y": dock[1], "z": dock[2]},
            "staging_focus_x": STAGING_YARD_FOCUS_X,
            "timestamp": ts,
        })
        for beam in beams:
            self.broadcast_event("karpenter_tractor_beam", {
                **beam, "timestamp": ts,
            })

    # -----------------------------------------------------------------
    # SPEC-09 §3.2 / §3.3: VPA morph + HPA lateral dispatch events
    # -----------------------------------------------------------------

    def _apply_autoscaling_update(self, payload: dict, ts: str) -> None:
        """Apply an AutoscalingStatus to a pod and fan out VPA/HPA events.

        Emits:
        - ``vpa_recommendation``  -> ghost-hull dimensions (SPEC-09 §3.2.1)
        - ``vpa_resize_committed``-> in-place resize geometry tween (SPEC-09 §3.2.2)
        - ``hpa_scale_out``       -> supervisor dispatch pulse + lateral path
          (SPEC-09 §3.3)
        """
        nid = str(payload.get("node_id") or "")
        raw = payload.get("autoscaling", payload.get("status"))
        node = self.nodes.get(nid) if nid else None
        if node is None or raw is None:
            return
        status = raw if isinstance(raw, AutoscalingStatus) else AutoscalingStatus(**raw)
        node.autoscaling = status

        # --- VPA recommendation ghost hull --------------------------------
        dims = vpa_morph_dimensions(node)
        if dims is not None:
            self.broadcast_event("vpa_recommendation", {
                "node_id": nid,
                "dimensions": dims,
                "target_cpu": status.vpa_target_cpu,
                "target_memory": status.vpa_target_memory,
                "timestamp": ts,
            })

        # --- VPA in-place resize commit ------------------------------------
        if status.is_resizing_in_place:
            cpu = parse_resource_quantity(status.vpa_target_cpu, "cpu")
            mem = parse_resource_quantity(status.vpa_target_memory, "memory")
            if cpu is not None:
                node.metrics["cpu_request_cores"] = cpu
            if mem is not None:
                node.metrics["memory_request_gib"] = mem
            nodes_list = apply_spatial_layout(list(self.nodes.values()))
            self.nodes = {n.id: n for n in nodes_list}
            resized = self.nodes.get(nid)
            if resized is not None:
                node = resized
            self.broadcast_event("vpa_resize_committed", {
                "node_id": nid,
                "geometry": node.pod_geometry.model_dump() if node.pod_geometry else None,
                "duration_ms": 1200,
                "timestamp": ts,
            })

        # --- HPA scale-out lateral dispatch --------------------------------
        if status.has_hpa:
            delta = hpa_scale_out_delta(status.current_replicas, status.desired_replicas)
            if delta > 0:
                path = hpa_lateral_path(node.spatial.x, POD_X_STAGGER)
                self.broadcast_event("hpa_scale_out", {
                    "node_id": nid,
                    "delta": delta,
                    "current_replicas": int(status.current_replicas),
                    "desired_replicas": int(status.desired_replicas),
                    "target_metric": status.target_metric,
                    "dispatch_from": {
                        "x": CENTRAL_RISER_X,
                        "y": SUPERVISOR_FLOOR_Y,
                        "z": CENTRAL_RISER_Z,
                    },
                    "riser_bottom": {
                        "x": CENTRAL_RISER_X,
                        "y": node.spatial.y,
                        "z": CENTRAL_RISER_Z,
                    },
                    "lateral_path": {
                        "intake": list(path["intake"]),
                        "slot": list(path["slot"]),
                    },
                    "timestamp": ts,
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

        # SPEC-09 §3.2/§3.3: seed autoscaling metadata so the demo renders
        # a VPA recommendation ghost hull and an HPA-managed replica set.
        redis = self.nodes.get("mock/redis-0")
        if redis is not None:
            redis.autoscaling = AutoscalingStatus(
                has_vpa=True,
                vpa_target_cpu="1",
                vpa_target_memory="16Gi",
            )
        postgres = self.nodes.get("mock/postgres-0")
        if postgres is not None:
            postgres.autoscaling = AutoscalingStatus(
                has_hpa=True,
                current_replicas=2,
                desired_replicas=2,
                target_metric="cpu: 70%",
            )

        # SPEC-09 §4.1/§4.2: seed the exterior staging yard — two pending
        # pods hovering over the tarmac with a Karpenter NodeClaim ghost
        # chassis provisioning on Sub-Level B1.
        pending_ray = NodeComponent(
            id="mock/ray-train-7f8c-pending",
            layer="workload",
            kind="Pod",
            name="ray-train-7f8c",
            namespace="batch-ai",
            version="v2.9.0",
            status="Pending",
            metrics={
                "cpu_request_cores": 8.0,
                "memory_request_gib": 32.0,
                "scheduled": False,
                "karpenter_target_node_claim": "karpenter-general-9x2k",
            },
        )
        pending_cache = NodeComponent(
            id="mock/cache-warm-4d1a-pending",
            layer="workload",
            kind="Pod",
            name="cache-warm-4d1a",
            namespace="default",
            version="v7.2.0",
            status="Pending",
            metrics={"pending": True},
        )
        self.nodes[pending_ray.id] = pending_ray
        self.nodes[pending_cache.id] = pending_cache
        self.karpenter_node_claims["karpenter-general-9x2k"] = KarpenterNodeClaim(
            claim_name="karpenter-general-9x2k",
            namespace="default",
            nodepool="general-pool",
            instance_type="c3-standard-8",
            requested_cpu_cores=8.0,
            requested_memory_gib=32.0,
            pending_pod_uids=[pending_ray.id],
        )

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

            # SPEC-09 §3.2/§3.3: drive the VPA morph / HPA lateral pipelines
            # roughly every 9 ticks against the seeded mock pods.
            if counter % 9 == 4:
                self.inject_mutation("autoscaling_updated", {
                    "node_id": "mock/redis-0",
                    "autoscaling": {
                        "has_vpa": True,
                        "vpa_target_cpu": "4",
                        "vpa_target_memory": "32Gi",
                        "is_resizing_in_place": True,
                    },
                })
            elif counter % 9 == 7:
                hpa = getattr(self.nodes.get("mock/postgres-0", None), "autoscaling", None)
                current = hpa.current_replicas if hpa else 2
                self.inject_mutation("autoscaling_updated", {
                    "node_id": "mock/postgres-0",
                    "autoscaling": {
                        "has_hpa": True,
                        "current_replicas": current,
                        "desired_replicas": current + 1,
                        "target_metric": "cpu: 70%",
                    },
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
