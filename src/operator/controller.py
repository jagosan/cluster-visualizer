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
    KueueWorkloadStatus,
    MachineShape,
    NodeComponent,
    RemoteServiceResource,
)
from src.ingestion.frameworks import enrich_framework_components
from src.ingestion.layout import (
    CENTRAL_RISER_X,
    CENTRAL_RISER_Z,
    GANG_DEPLOY_BURST_MS,
    KUEUE_RESERVE_LOCK_MS,
    MAGRAIL_TRANSIT_DURATION_MS,
    POD_X_STAGGER,
    STAGING_YARD_FOCUS_X,
    SUPERVISOR_FLOOR_Y,
    apply_spatial_layout,
    apply_subterranean_layout,
    gang_deployment_targets,
    generate_skyscraper_edges,
    ghost_node_positions,
    hpa_lateral_path,
    hpa_scale_out_delta,
    karpenter_tractor_beam,
    kueue_hud_summary,
    kueue_magrail_path,
    kueue_pallet_anchor,
    pack_kueue_workload,
    parse_resource_quantity,
    quota_deficit_reason,
    sum_kueue_quota,
    vpa_morph_dimensions,
)
from src.ingestion.exporter import generate_mock_cluster_graph
from src.operator.kcc_mapper import parse_kcc_resource, parse_node_machine_shape


class TopologyController:
    """Kubernetes topology informer controller with real-time mutation injection."""

    def __init__(
        self,
        cluster_name: str = "in-cluster",
        context_name: Optional[str] = None,
        api_url: Optional[str] = None,
        bearer_token: Optional[str] = None,
    ):
        import os
        self.cluster_name = cluster_name or os.environ.get("CLUSTERVIS_CLUSTER_NAME", "in-cluster")
        self.context_name = context_name if context_name is not None else os.environ.get("CLUSTERVIS_CONTEXT", "")
        self.api_url = (api_url or os.environ.get("CLUSTERVIS_API_URL", "")).rstrip("/")
        self.bearer_token = bearer_token or os.environ.get("CLUSTERVIS_BEARER_TOKEN", "")
        self.mock = True
        self.kube_version = "v1.36.4"
        self.distribution = "in-cluster"
        self.nodes: Dict[str, NodeComponent] = {}
        self.edges: List[DataFlowEdge] = []
        self.subterranean_resources: Dict[str, RemoteServiceResource] = {}
        self.machine_shapes: Dict[str, MachineShape] = {}
        # SPEC-09 §4.2: Karpenter NodeClaims -> Sub-Level B1 ghost chassis
        self.karpenter_node_claims: Dict[str, KarpenterNodeClaim] = {}
        # SPEC-09 §5.1-§5.3: Kueue Workload CRDs -> cargo containment pallets
        self.kueue_workloads: Dict[str, KueueWorkloadStatus] = {}
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
            if not self.nodes and getattr(self, 'mock', True):
                self._seed_mock_data()
            nodes_list = list(self.nodes.values())
            if getattr(self, 'mock', True):
                nodes_list, edges_list = enrich_framework_components(nodes_list, list(self.edges))
                nodes_list = apply_spatial_layout(nodes_list, list(self.kueue_workloads.values()))
                self.edges = generate_skyscraper_edges(nodes_list)
                for n in nodes_list:
                    self.nodes[n.id] = n

            apply_subterranean_layout(
                list(self.machine_shapes.values()),
                list(self.subterranean_resources.values()),
            )

            meta = ClusterMetadata(
                cluster_name=self.cluster_name,
                kubernetes_version=getattr(self, "kube_version", "v1.36.4"),
                distribution=getattr(self, "distribution", "in-cluster"),
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
                kueue_workloads=list(self.kueue_workloads.values()),
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
                nodes_list = apply_spatial_layout(nodes_list, list(self.kueue_workloads.values()))
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
                    nodes_list = apply_spatial_layout(
                        nodes_list, list(self.kueue_workloads.values())
                    )
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
            elif event_name == "kueue_workload_updated":
                self._apply_kueue_workload_update(payload, ts)

    # -----------------------------------------------------------------
    # SPEC-09 §5.1-§5.3 / ADR-03 (TASK-CV-1004): Kueue gang workload events
    # -----------------------------------------------------------------

    def _kueue_pallet_index(self, workload_name: str) -> int:
        """Dock index of a workload on the staging rail (sorted by name).

        Mirrors the ordering apply_spatial_layout uses so the client's
        pallet frames always land where the layout packed their pods.
        """
        names = sorted(
            str(getattr(w, "workload_name", "")) for w in self.kueue_workloads.values()
        )
        try:
            return names.index(workload_name)
        except ValueError:
            return 0

    def _apply_kueue_workload_update(self, payload: dict, ts: str) -> None:
        """Register/refresh a Kueue Workload and fan out staging events.

        Constituent pods carried alongside the workload (``pods``) are
        registered so the pallet can pack them. Emits:
        - ``kueue_workload_updated`` -> workload snapshot + HUD badge +
          pallet bounding volume + staging focus anchor
        - ``kueue_quota_deficit``    -> quota shortfall indicator while the
          workload sits queued / inadmissible (cold-blue standby)
        - ``kueue_quota_reserved``   -> magnetic intake-rail engagement:
          amber beacons spin, gantry cranes lock onto the frame
        - ``kueue_admission_admitted`` -> high-speed mag-rail transit
          endpoints (X = -18 rail -> X = -8 tower intake bay)
        - ``kueue_gang_deployed``    -> coordinated simultaneous worker-deck
          deployment targets for the frame disassembly burst
        """
        raw = payload.get("workload", payload.get("kueue_workload"))
        if raw is None:
            return
        workload = (
            raw if isinstance(raw, KueueWorkloadStatus) else KueueWorkloadStatus(**raw)
        )

        # Register any constituent pods the informer carries with the CRD.
        for pod_raw in payload.get("pods", []) or []:
            if isinstance(pod_raw, NodeComponent):
                self.nodes[pod_raw.id] = pod_raw
            elif isinstance(pod_raw, dict):
                pod = NodeComponent(**pod_raw)
                self.nodes[pod.id] = pod

        previous = self.kueue_workloads.get(workload.workload_uid)
        was_admitted = bool(previous.is_admitted) if previous is not None else False
        self.kueue_workloads[workload.workload_uid] = workload

        members = [
            self.nodes[str(uid)]
            for uid in workload.pod_uids
            if str(uid) in self.nodes
        ]
        anchor = kueue_pallet_anchor(self._kueue_pallet_index(workload.workload_name))
        pallet = pack_kueue_workload(workload, members, anchor) if members else None

        # Quota bookkeeping: recompute from live members when available so
        # the HUD always shows the summed gang request (SPEC-09 §5.2).
        if members:
            cpu, mem, gpus = sum_kueue_quota(members)
            workload.total_cpu_requested = cpu
            workload.total_memory_gib_requested = mem
            workload.total_gpu_requested = gpus

        hud = kueue_hud_summary(workload)
        event_pallet = {
            "anchor": pallet["anchor"] if pallet else list(anchor),
            "width": pallet["width"] if pallet else 0.0,
            "height": pallet["height"] if pallet else 0.0,
            "depth": pallet["depth"] if pallet else 0.0,
            "slots": pallet["slots"] if pallet else {},
        }
        self.broadcast_event("kueue_workload_updated", {
            "workload": workload.model_dump(),
            "hud": hud,
            "pallet": event_pallet,
            "staging_focus_x": STAGING_YARD_FOCUS_X,
            "timestamp": ts,
        })

        # --- Queued / Inadmissible: quota deficit indicator ----------------
        deficit = quota_deficit_reason(workload)
        if deficit is not None and not workload.is_admitted:
            self.broadcast_event("kueue_quota_deficit", {
                "workload_uid": workload.workload_uid,
                "workload_name": workload.workload_name,
                "reason": deficit,
                "required": {
                    "cpu": workload.total_cpu_requested,
                    "memory_gib": workload.total_memory_gib_requested,
                    "gpus": workload.total_gpu_requested,
                },
                "anchor": event_pallet["anchor"],
                "timestamp": ts,
            })

        # --- Quota Reserved: magnetic intake rail + gantry crane lock ------
        if payload.get("quota_reserved") and not workload.is_admitted:
            self.broadcast_event("kueue_quota_reserved", {
                "workload_uid": workload.workload_uid,
                "workload_name": workload.workload_name,
                "anchor": event_pallet["anchor"],
                "lock_duration_ms": KUEUE_RESERVE_LOCK_MS,
                "timestamp": ts,
            })

        # --- Admitted: high-speed mag-rail transit --------------------------
        if workload.is_admitted and (payload.get("force_admission") or not was_admitted):
            self.broadcast_event("kueue_admission_admitted", {
                "workload_uid": workload.workload_uid,
                "workload_name": workload.workload_name,
                "local_queue": workload.local_queue,
                "cluster_queue": workload.cluster_queue,
                "magrail": kueue_magrail_path(anchor),
                "transit_duration_ms": MAGRAIL_TRANSIT_DURATION_MS,
                "pod_uids": list(workload.pod_uids),
                "timestamp": ts,
            })
            # --- Gang Deployment: frame disassembly coordinated burst ------
            self.broadcast_event("kueue_gang_deployed", {
                "workload_uid": workload.workload_uid,
                "workload_name": workload.workload_name,
                "pod_uids": list(workload.pod_uids),
                "targets": [
                    list(t) for t in gang_deployment_targets(len(workload.pod_uids))
                ],
                "burst_duration_ms": GANG_DEPLOY_BURST_MS,
                "timestamp": ts,
            })

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
            nodes_list = apply_spatial_layout(
                list(self.nodes.values()), list(self.kueue_workloads.values())
            )
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

        # SPEC-09 §5.2/§5.3: seed a Kueue gang so demo mode renders a cargo
        # containment pallet — a queued RayCluster workload (cold-blue
        # standby + quota deficit) whose admission the demo loop replays.
        gang_pods: List[NodeComponent] = []
        for i in range(4):
            gang_pod = NodeComponent(
                id=f"batch-ai/ray-finetune-{i}",
                layer="workload",
                kind="Pod",
                name=f"ray-finetune-{i}",
                namespace="batch-ai",
                version="v2.9.0",
                status="Pending",
                metrics={
                    "cpu_request_cores": 8.0,
                    "memory_request_gib": 32.0,
                    "gpu_request": 2 if i == 0 else 0,
                    "scheduled": False,
                },
            )
            self.nodes[gang_pod.id] = gang_pod
            gang_pods.append(gang_pod)
        self.kueue_workloads["wl-ray-finetune-0001"] = KueueWorkloadStatus(
            workload_uid="wl-ray-finetune-0001",
            workload_name="ray-finetune-job",
            namespace="batch-ai",
            local_queue="batch-ai",
            cluster_queue="cluster-ml-bq",
            is_admitted=False,
            phase="Inadmissible",
            admission_checks=[{
                "type": "QuotaCheck",
                "status": "False",
                "reason": "QuotaExceeded: waiting for 64 vCPU / 256Gi in cohort ml-cohort",
            }],
            pod_uids=[p.id for p in gang_pods],
            total_cpu_requested=32.0,
            total_memory_gib_requested=128.0,
            total_gpu_requested=2,
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

            # SPEC-09 §5.3: replay the Kueue gang admission lifecycle
            # (queued -> quota reserved -> admitted -> gang deployed) against
            # the seeded ray-finetune workload roughly every 18 ticks so the
            # demo exercises mag-rail transit + deployment burst end to end.
            kueue_phase = counter % 18
            if kueue_phase == 10:
                self.inject_mutation("kueue_workload_updated", {
                    "workload": {
                        "workload_uid": "wl-ray-finetune-0001",
                        "workload_name": "ray-finetune-job",
                        "namespace": "batch-ai",
                        "local_queue": "batch-ai",
                        "cluster_queue": "cluster-ml-bq",
                        "is_admitted": False,
                        "phase": "Admissible",
                        "pod_uids": [f"batch-ai/ray-finetune-{i}" for i in range(4)],
                        "total_cpu_requested": 32.0,
                        "total_memory_gib_requested": 128.0,
                        "total_gpu_requested": 2,
                    },
                    "quota_reserved": True,
                })
            elif kueue_phase == 13:
                self.inject_mutation("kueue_workload_updated", {
                    "workload": {
                        "workload_uid": "wl-ray-finetune-0001",
                        "workload_name": "ray-finetune-job",
                        "namespace": "batch-ai",
                        "local_queue": "batch-ai",
                        "cluster_queue": "cluster-ml-bq",
                        "is_admitted": True,
                        "phase": "Admitted",
                        "pod_uids": [f"batch-ai/ray-finetune-{i}" for i in range(4)],
                        "total_cpu_requested": 32.0,
                        "total_memory_gib_requested": 128.0,
                        "total_gpu_requested": 2,
                    },
                })

    def _fetch_k8s_json(self, path: str, kubectl_args: List[str]) -> dict:
        import json, os, ssl, subprocess, urllib.request
        if getattr(self, "api_url", "") and getattr(self, "bearer_token", ""):
            ctx = ssl._create_unverified_context()
            req = urllib.request.Request(
                f"{self.api_url}{path}",
                headers={"Authorization": f"Bearer {self.bearer_token}", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        if self.context_name and self.context_name != "in-cluster":
            cmd = ["kubectl", "--context", self.context_name] + kubectl_args + ["-o", "json"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
            if res.returncode == 0 and res.stdout.strip():
                return json.loads(res.stdout)
            raise RuntimeError(f"kubectl failed ({res.returncode}): {res.stderr.strip()}")
        host = os.environ.get("KUBERNETES_SERVICE_HOST")
        port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        tok_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        if host and os.path.exists(tok_path):
            token = open(tok_path, "r", encoding="utf-8").read().strip()
            ctx = ssl.create_default_context(cafile=ca_path) if os.path.exists(ca_path) else ssl._create_unverified_context()
            req = urllib.request.Request(
                f"https://{host}:{port}{path}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        cmd = ["kubectl"] + kubectl_args + ["-o", "json"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
        raise RuntimeError(f"kubectl failed ({res.returncode}): {res.stderr.strip()}")

    def _poll_real_cluster(self, broadcast: bool = True) -> None:
        from src.ingestion.models import Spatial
        try:
            nodes_env = self._fetch_k8s_json("/api/v1/nodes", ["get", "nodes"])
            pods_env = self._fetch_k8s_json("/api/v1/pods", ["get", "pods", "-A"])
        except Exception:
            return

        raw_nodes = nodes_env.get("items", []) or []
        raw_pods = pods_env.get("items", []) or []

        new_nodes: Dict[str, NodeComponent] = {}
        new_shapes: Dict[str, MachineShape] = {}

        kube_ver = "v1.36.4"
        for idx, rn in enumerate(raw_nodes, 1):
            meta = rn.get("metadata", {}) or {}
            status = rn.get("status", {}) or {}
            nname = meta.get("name", f"worker-{idx}")
            kver = (status.get("nodeInfo", {}) or {}).get("kubeletVersion", "v1.36.4")
            kube_ver = kver
            ready = any(
                c.get("type") == "Ready" and c.get("status") == "True"
                for c in (status.get("conditions", []) or [])
            )
            cap = status.get("capacity", {}) or {}
            alloc = status.get("allocatable", {}) or {}
            comp = NodeComponent(
                id=f"node/worker-{idx}",
                layer="node",
                kind="Node",
                name=f"worker-{idx} ({nname[-12:]})",
                namespace="cluster",
                version=kver,
                status="Healthy" if ready else "Degraded",
                metrics={
                    "cpu_capacity": cap.get("cpu", "4"),
                    "memory_capacity": cap.get("memory", "16Gi"),
                    "cpu_allocatable": alloc.get("cpu", "4"),
                    "memory_allocatable": alloc.get("memory", "16Gi"),
                    "os_image": (status.get("nodeInfo", {}) or {}).get("osImage", "Container-Optimized OS"),
                    "gke_node_name": nname,
                },
                spatial=Spatial(asset_type="LayerTray_Worker"),
                raw_labels=dict(meta.get("labels", {}) or {}),
            )
            new_nodes[comp.id] = comp
            try:
                shape = parse_node_machine_shape(rn)
                if shape:
                    new_shapes[shape.node_name] = shape
            except Exception:
                pass

            kl = NodeComponent(
                id=f"node/worker-{idx}/kubelet",
                layer="node",
                kind="Kubelet",
                name=f"kubelet-worker-{idx}",
                namespace="kube-system",
                version=kver,
                status="Healthy" if ready else "Degraded",
                metrics={"component": "kubelet", "node": nname},
                spatial=Spatial(asset_type="Cuboid_Kubelet"),
            )
            ct = NodeComponent(
                id=f"node/worker-{idx}/containerd",
                layer="node",
                kind="Containerd",
                name=f"containerd-worker-{idx}",
                namespace="kube-system",
                version="v1.7.22",
                status="Healthy" if ready else "Degraded",
                metrics={"runtime": "containerd", "node": nname},
                spatial=Spatial(asset_type="Cuboid_Containerd"),
            )
            new_nodes[kl.id] = kl
            new_nodes[ct.id] = ct

        self.kube_version = kube_ver
        self.distribution = "gke"

        for cid, cname, cmd_label in [
            ("client/kubectl-cli", "kubectl-cli", "watch pods -A"),
            ("client/crd-watcher", "client-crd-watcher", "watch rayjobs.ray.io"),
        ]:
            new_nodes[cid] = NodeComponent(
                id=cid,
                layer="ingress",
                kind="Client",
                name=cname,
                namespace="external",
                version=kube_ver,
                status="Healthy",
                metrics={"tool": cname, "command": cmd_label},
                spatial=Spatial(asset_type="Client_Slab"),
            )

        for cpid, cpkind, cpname, cpasset, cpver in [
            ("control-plane/kube-apiserver-0", "APIServer", "kube-apiserver-gke", "Cuboid_APIServer", kube_ver),
            ("control-plane/etcd-0", "etcd", "etcd-gke-0", "Cuboid_etcd", "v3.5.15"),
            ("control-plane/kube-scheduler-0", "Scheduler", "kube-scheduler-gke", "Cuboid_Supervisor", kube_ver),
            ("control-plane/kube-controller-manager-0", "ControllerManager", "kube-controller-manager-gke", "Cuboid_Supervisor", kube_ver),
        ]:
            new_nodes[cpid] = NodeComponent(
                id=cpid,
                layer="control-plane",
                kind=cpkind,
                name=cpname,
                namespace="kube-system",
                version=cpver,
                image=f"registry.k8s.io/{cpkind.lower()}:{cpver}",
                status="Healthy",
                spatial=Spatial(asset_type=cpasset),
            )

        has_ai_stack = any(
            "llm-d" in ((rp.get("metadata") or {}).get("name") or "")
            or "kueue" in ((rp.get("metadata") or {}).get("name") or "")
            for rp in raw_pods
        )

        if has_ai_stack:
            from src.ingestion.models import KueueWorkloadStatus, PodGeometrySpec
            new_shapes = {
                "worker-1": MachineShape(
                    node_name="worker-1 (on-demand-gpu)",
                    instance_type="g2-standard-24",
                    vcpus=24,
                    memory_gib=96.0,
                    capacity_type="on-demand",
                    zone="us-central1-a",
                    accelerator_type="nvidia-l4",
                    accelerator_count=2,
                ),
                "worker-2": MachineShape(
                    node_name="worker-2 (spot-gpu)",
                    instance_type="g2-standard-24",
                    vcpus=24,
                    memory_gib=96.0,
                    capacity_type="spot",
                    zone="us-central1-a",
                    accelerator_type="nvidia-l4",
                    accelerator_count=2,
                ),
            }
            new_nodes["ingress/default/gke-inference-gateway"] = NodeComponent(
                id="ingress/default/gke-inference-gateway",
                layer="ingress",
                kind="InferenceGateway",
                name="gke-inference-gateway (llm-d)",
                namespace="default",
                version="v1.4.0",
                status="Healthy",
                metrics={"component": "gke-inference-gateway", "route": "/v1/chat/completions", "models": "gemma-2b-it, qwen-2.5-3b"},
                spatial=Spatial(x=0.0, y=9.6, z=1.6, asset_type="LoadBalancer_Ring"),
            )

        kube_proxy_idx = 0
        probe_idx = 0
        gemma_w_idx = 0
        qwen_od_idx = 0
        qwen_spot_idx = 0

        for rp in raw_pods:
            meta = rp.get("metadata", {}) or {}
            spec = rp.get("spec", {}) or {}
            status = rp.get("status", {}) or {}
            pns = meta.get("namespace", "default")
            pname = meta.get("name", "unknown")
            phase = status.get("phase", "Pending")
            labels = dict(meta.get("labels", {}) or {})

            if meta.get("deletionTimestamp"):
                continue

            if phase in ("Succeeded", "Failed") and "ray" not in pname.lower():
                continue

            if pns in ("kube-node-lease", "kube-public", "gmp-system", "gmp-public", "gke-managed-cim"):
                continue

            if pns == "kube-system":
                if not pname.startswith("kube-proxy"):
                    continue

            if pns == "clustervis-system" and "clustervis-web" in pname:
                continue

            containers = spec.get("containers", []) or []
            cstatuses = status.get("containerStatuses", []) or []
            image = containers[0].get("image", "") if containers else ""
            digest = None
            for cs in cstatuses:
                iid = cs.get("imageID", "") or ""
                if "@" in iid:
                    digest = iid.rsplit("@", 1)[1]
                    break

            cpu_req = 0.0
            mem_req = 0.0
            for c in containers:
                reqs = ((c.get("resources") or {}).get("requests")) or {}
                c_val = parse_resource_quantity(reqs.get("cpu"), "cpu")
                m_val = parse_resource_quantity(reqs.get("memory"), "memory")
                if c_val:
                    cpu_req += c_val
                if m_val:
                    mem_req += m_val
            if cpu_req <= 0:
                cpu_req = 0.5
            if mem_req <= 0:
                mem_req = 1.0

            ready_cond = any(
                c.get("type") == "Ready" and c.get("status") == "True"
                for c in (status.get("conditions", []) or [])
            )
            waiting_container = any(
                (cs.get("state") or {}).get("waiting") is not None
                for cs in cstatuses
            )
            is_pending = (phase == "Pending") or (not ready_cond and waiting_container and phase != "Succeeded")

            owners = meta.get("ownerReferences", []) or []
            is_ds = any(o.get("kind") == "DaemonSet" for o in owners) or pname.startswith("kube-proxy") or "probe" in pname.lower()
            is_ray = "ray" in pname.lower() or "kuberay" in pname.lower() or "vllm" in pname.lower() or "ray" in image.lower()

            ver = labels.get("clustervis.io/version") or (image.rsplit(":", 1)[1] if ":" in image else kube_ver)
            display_name = pname
            pid = f"pod/{pns}/{pname}"

            if "kuberay-operator" in pname:
                display_name = "kuberay-operator"
                pid = "pod/default/kuberay-operator"
                ver = "v1.3.0 / Ray 2.56" if has_ai_stack else "v1.3.0"
            elif "kueue-controller-manager" in pname:
                display_name = "kueue-controller-manager"
                pid = "pod/kueue-system/kueue-controller-manager"
                ver = "v0.10.2 (on-demand → spot-gpu)"
            elif "llm-d-body-based-router" in pname:
                display_name = "llm-d-body-based-router"
                pid = "pod/default/llm-d-body-based-router"
                ver = "v1.4.0 (ext-proc)"
            elif "llm-d-epp-gemma-2b-it" in pname:
                display_name = "llm-d-epp-gemma-2b-it"
                pid = "pod/default/llm-d-epp-gemma-2b-it"
                ver = "v1.4.0 (InferencePool: gemma-2b-it)"
            elif "llm-d-epp-qwen-2-5-3b" in pname:
                display_name = "llm-d-epp-qwen-2-5-3b"
                pid = "pod/default/llm-d-epp-qwen-2-5-3b"
                ver = "v1.4.0 (InferencePool: qwen-2.5-3b)"
            elif "rayservice-gemma-2b-it-head" in pname:
                display_name = "rayservice-gemma-2b-it-head"
                pid = "pod/default/rayservice-gemma-2b-it-head"
                ver = "ray-2.56.0 (K8s Events=ON)"
            elif "rayservice-qwen-2-5-3b-head" in pname:
                display_name = "rayservice-qwen-2-5-3b-head"
                pid = "pod/default/rayservice-qwen-2-5-3b-head"
                ver = "ray-2.56.0 (K8s Events=ON)"
            elif "vllm-gemma-2b-it-worker" in pname:
                gemma_w_idx += 1
                display_name = f"vllm-gemma-2b-it-worker-{gemma_w_idx}"
                pid = f"pod/default/vllm-gemma-2b-it-worker-{gemma_w_idx}"
                ver = "vllm-0.7.3 (gemma-2b-it / on-demand-gpu)"
                cpu_req, mem_req = 4.0, 16.0
            elif "vllm-qwen-2-5-3b-ondemand" in pname:
                qwen_od_idx += 1
                display_name = f"vllm-qwen-2-5-3b-ondemand-{qwen_od_idx}"
                pid = f"pod/default/vllm-qwen-2-5-3b-ondemand-{qwen_od_idx}"
                ver = "vllm-0.7.3 (qwen-2.5-3b / on-demand-gpu)"
                cpu_req, mem_req = 4.0, 16.0
            elif "vllm-qwen-2-5-3b-spot-burst" in pname:
                qwen_spot_idx += 1
                display_name = f"vllm-qwen-2-5-3b-spot-burst-{qwen_spot_idx}"
                pid = f"pod/default/vllm-qwen-2-5-3b-spot-burst-{qwen_spot_idx}"
                ver = "vllm-0.7.3 (qwen-2.5-3b / spot-gpu burst)"
                cpu_req, mem_req = 6.0, 24.0

            if is_ds:
                layer = "control-plane"
                kind = "DaemonSet"
                asset = "Cuboid_DaemonSet"
                pod_status = "Running"
                is_pending = False
                if pname.startswith("kube-proxy"):
                    kube_proxy_idx += 1
                    display_name = f"kube-proxy-w{kube_proxy_idx}"
                    pid = f"pod/{pns}/kube-proxy-w{kube_proxy_idx}"
                elif "probe" in pname.lower():
                    probe_idx += 1
                    display_name = f"clustervis-probe-w{probe_idx}"
                    pid = f"pod/{pns}/clustervis-probe-w{probe_idx}"
            elif "llm-d" in pname:
                layer = "ingress"
                kind = "BodyBasedRouter" if "router" in pname else "InferencePool"
                asset = "Cylinder_Service"
                pod_status = "Running"
            elif "kueue-controller-manager" in pname:
                layer = "framework"
                kind = "KueueOperator"
                asset = "Cuboid_Supervisor"
                pod_status = "Running"
            elif "kuberay-operator" in pname:
                layer = "framework"
                kind = "KubeRayOperator"
                asset = "Framework_Ray"
                pod_status = "Running"
            elif "rayservice-" in pname and "-head" in pname:
                layer = "framework"
                kind = "RayHead"
                asset = "Framework_Ray"
                pod_status = "Running"
            elif "vllm-" in pname:
                layer = "workload"
                kind = "RayWorker"
                asset = "Pod_Cylinder"
                pod_status = "Running"
            elif is_ray:
                layer = "framework"
                kind = "Pod"
                asset = "Cuboid_Ray"
                pod_status = "Pending" if is_pending else ("Completed" if phase == "Succeeded" else "Running")
            else:
                layer = "workload"
                kind = "Pod"
                asset = "Pod_Cylinder"
                pod_status = "Pending" if is_pending else "Running"
                if "clustervis-operator" in pname:
                    display_name = "clustervis-operator"
                    pid = f"pod/{pns}/clustervis-operator"

            new_nodes[pid] = NodeComponent(
                id=pid,
                layer=layer,
                kind=kind,
                name=display_name,
                namespace=pns,
                version=ver,
                image=image or None,
                digest=digest,
                status=pod_status,
                metrics={
                    "cpu_request_cores": round(cpu_req, 3),
                    "memory_request_gib": round(mem_req, 3),
                    "phase": phase,
                    "pending": is_pending,
                    "scheduled": not is_pending,
                    "host_node": spec.get("nodeName"),
                    "pod_ip": status.get("podIP"),
                    "kueue_flavor": labels.get("kueue.x-k8s.io/resource-flavor"),
                    "model": labels.get("llm-d.ai/model"),
                },
                spatial=Spatial(asset_type=asset),
                raw_labels=labels,
            )

        with self.lock:
            prev_ids = set(self.nodes.keys())
            new_ids = set(new_nodes.keys())
            added_ids = sorted(new_ids - prev_ids)
            removed_ids = sorted(prev_ids - new_ids)

            if has_ai_stack:
                self.kueue_workloads = {
                    "wl-gemma-2b-it-ondemand": KueueWorkloadStatus(
                        workload_uid="wl-gemma-2b-it-ondemand",
                        workload_name="gemma-2b-it-vllm (on-demand-gpu)",
                        namespace="default",
                        local_queue="llm-inference-queue",
                        cluster_queue="on-demand-gpu",
                        is_admitted=True,
                        pod_uids=[
                            "pod/default/vllm-gemma-2b-it-worker-1",
                            "pod/default/vllm-gemma-2b-it-worker-2",
                        ],
                        total_cpu_requested=8.0,
                        total_memory_gib_requested=32.0,
                        total_gpu_requested=2,
                        phase="Admitted",
                    ),
                    "wl-qwen-2-5-3b-ondemand": KueueWorkloadStatus(
                        workload_uid="wl-qwen-2-5-3b-ondemand",
                        workload_name="qwen-2.5-3b-vllm (on-demand FULL)",
                        namespace="default",
                        local_queue="llm-inference-queue",
                        cluster_queue="on-demand-gpu",
                        is_admitted=True,
                        pod_uids=[
                            "pod/default/vllm-qwen-2-5-3b-ondemand-1",
                            "pod/default/vllm-qwen-2-5-3b-ondemand-2",
                        ],
                        total_cpu_requested=8.0,
                        total_memory_gib_requested=32.0,
                        total_gpu_requested=2,
                        phase="Admitted",
                    ),
                    "wl-qwen-2-5-3b-spot-burst": KueueWorkloadStatus(
                        workload_uid="wl-qwen-2-5-3b-spot-burst",
                        workload_name="qwen-2.5-3b-burst (spot-gpu fallback)",
                        namespace="default",
                        local_queue="llm-inference-queue",
                        cluster_queue="spot-gpu",
                        is_admitted=True,
                        pod_uids=[
                            "pod/default/vllm-qwen-2-5-3b-spot-burst-1",
                            "pod/default/vllm-qwen-2-5-3b-spot-burst-2",
                        ],
                        total_cpu_requested=12.0,
                        total_memory_gib_requested=48.0,
                        total_gpu_requested=4,
                        phase="Admitted",
                    ),
                }
            else:
                self.kueue_workloads = {}

            nodes_list = list(new_nodes.values())
            nodes_list, _ = enrich_framework_components(nodes_list, [])
            nodes_list = apply_spatial_layout(nodes_list, list(self.kueue_workloads.values()))

            # Explicit architectural placement for Demo Jago/Ion stack components
            custom_coords = {
                "ingress/default/gke-inference-gateway": (0.0, 9.6, 1.6, "LoadBalancer_Ring"),
                "pod/default/llm-d-body-based-router": (0.0, 8.5, 1.8, "Cylinder_Service"),
                "pod/default/llm-d-epp-gemma-2b-it": (-3.0, 8.1, 2.0, "Cylinder_Service"),
                "pod/default/llm-d-epp-qwen-2-5-3b": (3.0, 8.1, 2.0, "Cylinder_Service"),
                "pod/kueue-system/kueue-controller-manager": (-4.0, 3.6, -1.2, "Cuboid_Supervisor"),
                "pod/default/kuberay-operator": (4.0, 3.6, -1.2, "Framework_Ray"),
                "pod/default/rayservice-gemma-2b-it-head": (-3.0, 2.5, 0.8, "Framework_Ray"),
                "pod/default/rayservice-qwen-2-5-3b-head": (3.0, 2.5, 0.8, "Framework_Ray"),
                "pod/default/vllm-gemma-2b-it-worker-1": (-4.2, 0.85, 0.6, "Pod_Cylinder"),
                "pod/default/vllm-gemma-2b-it-worker-2": (-2.8, 0.85, 0.6, "Pod_Cylinder"),
                "pod/default/vllm-qwen-2-5-3b-ondemand-1": (-4.2, 0.85, 1.8, "Pod_Cylinder"),
                "pod/default/vllm-qwen-2-5-3b-ondemand-2": (-2.8, 0.85, 1.8, "Pod_Cylinder"),
                "pod/default/vllm-qwen-2-5-3b-spot-burst-1": (2.2, 0.85, 1.2, "Pod_Cylinder"),
                "pod/default/vllm-qwen-2-5-3b-spot-burst-2": (3.8, 0.85, 1.2, "Pod_Cylinder"),
            }
            wl_map = {
                "pod/default/vllm-gemma-2b-it-worker-1": "wl-gemma-2b-it-ondemand",
                "pod/default/vllm-gemma-2b-it-worker-2": "wl-gemma-2b-it-ondemand",
                "pod/default/vllm-qwen-2-5-3b-ondemand-1": "wl-qwen-2-5-3b-ondemand",
                "pod/default/vllm-qwen-2-5-3b-ondemand-2": "wl-qwen-2-5-3b-ondemand",
                "pod/default/vllm-qwen-2-5-3b-spot-burst-1": "wl-qwen-2-5-3b-spot-burst",
                "pod/default/vllm-qwen-2-5-3b-spot-burst-2": "wl-qwen-2-5-3b-spot-burst",
            }
            for n in nodes_list:
                if n.id in custom_coords:
                    cx, cy, cz, casset = custom_coords[n.id]
                    n.spatial.x = cx
                    n.spatial.y = cy
                    n.spatial.z = cz
                    n.spatial.asset_type = casset
                    if n.id.startswith("pod/default/vllm-"):
                        n.kind = "RayWorker"
                        n.layer = "workload"
                        is_spot = "spot" in n.id
                        n.pod_geometry = PodGeometrySpec(
                            height=1.25 if is_spot else 1.1,
                            radius=0.68 if is_spot else 0.62,
                            is_pending=False,
                            kueue_workload=wl_map.get(n.id),
                        )

            new_edges = generate_skyscraper_edges(nodes_list)
            if has_ai_stack:
                # Replace broadcast Ray Head <-> all Ray Workers edges with model-specific conduits
                new_edges = [
                    e for e in new_edges
                    if not (e.source.startswith("pod/default/rayservice-") and e.target.startswith("pod/default/vllm-"))
                ]
                ai_edges = [
                    ("ingress/default/gke-inference-gateway", "pod/default/llm-d-body-based-router", "traffic", "HTTP/80", "unidirectional", "inference /v1/chat/completions"),
                    ("pod/default/llm-d-body-based-router", "pod/default/llm-d-epp-gemma-2b-it", "traffic", "gRPC/ext-proc", "unidirectional", "inference model=gemma-2b-it"),
                    ("pod/default/llm-d-body-based-router", "pod/default/llm-d-epp-qwen-2-5-3b", "traffic", "gRPC/ext-proc", "unidirectional", "inference model=qwen-2.5-3b"),
                    ("pod/default/llm-d-epp-gemma-2b-it", "pod/default/rayservice-gemma-2b-it-head", "traffic", "HTTP/8000", "unidirectional", "inference KV-aware route"),
                    ("pod/default/llm-d-epp-qwen-2-5-3b", "pod/default/rayservice-qwen-2-5-3b-head", "traffic", "HTTP/8000", "unidirectional", "inference KV-aware route"),
                    ("pod/default/rayservice-gemma-2b-it-head", "pod/default/vllm-gemma-2b-it-worker-1", "framework_control", "gRPC/10001", "bidirectional", "tensor vLLM gemma-2b-it"),
                    ("pod/default/rayservice-gemma-2b-it-head", "pod/default/vllm-gemma-2b-it-worker-2", "framework_control", "gRPC/10001", "bidirectional", "tensor vLLM gemma-2b-it"),
                    ("pod/default/rayservice-qwen-2-5-3b-head", "pod/default/vllm-qwen-2-5-3b-ondemand-1", "framework_control", "gRPC/10001", "bidirectional", "tensor vLLM qwen-2.5-3b on-demand"),
                    ("pod/default/rayservice-qwen-2-5-3b-head", "pod/default/vllm-qwen-2-5-3b-ondemand-2", "framework_control", "gRPC/10001", "bidirectional", "tensor vLLM qwen-2.5-3b on-demand"),
                    ("pod/default/rayservice-qwen-2-5-3b-head", "pod/default/vllm-qwen-2-5-3b-spot-burst-1", "framework_control", "gRPC/10001", "bidirectional", "tensor vLLM qwen-2.5-3b spot-gpu"),
                    ("pod/default/rayservice-qwen-2-5-3b-head", "pod/default/vllm-qwen-2-5-3b-spot-burst-2", "framework_control", "gRPC/10001", "bidirectional", "tensor vLLM qwen-2.5-3b spot-gpu"),
                    ("pod/kueue-system/kueue-controller-manager", "pod/default/vllm-qwen-2-5-3b-spot-burst-1", "control_plane", "Kueue/SpotFallback", "unidirectional", "kueue quota spot-gpu"),
                    ("pod/kueue-system/kueue-controller-manager", "pod/default/vllm-qwen-2-5-3b-spot-burst-2", "control_plane", "Kueue/SpotFallback", "unidirectional", "kueue quota spot-gpu"),
                    ("pod/default/kuberay-operator", "pod/default/rayservice-gemma-2b-it-head", "control_plane", "CRD/RayService", "unidirectional", "kueue ray reconcile"),
                    ("pod/default/kuberay-operator", "pod/default/rayservice-qwen-2-5-3b-head", "control_plane", "CRD/RayService", "unidirectional", "kueue ray reconcile"),
                ]
                present_ids = {n.id for n in nodes_list}
                for src, dst, ftype, proto, direc, vlabel in ai_edges:
                    if src in present_ids and dst in present_ids:
                        new_edges.append(
                            DataFlowEdge(
                                source=src,
                                target=dst,
                                flow_type=ftype,
                                protocol=proto,
                                direction=direc,
                                volume_label=vlabel,
                            )
                        )
            laid_out = {n.id: n for n in nodes_list}

            changed_ids = []
            for nid in sorted(new_ids & prev_ids):
                old_n = self.nodes[nid]
                cur_n = laid_out[nid]
                if (
                    old_n.status != cur_n.status
                    or round(old_n.spatial.x, 2) != round(cur_n.spatial.x, 2)
                    or round(old_n.spatial.y, 2) != round(cur_n.spatial.y, 2)
                    or round(old_n.spatial.z, 2) != round(cur_n.spatial.z, 2)
                ):
                    changed_ids.append(nid)

            self.nodes = laid_out
            self.edges = new_edges
            self.machine_shapes = new_shapes

            if broadcast and (added_ids or removed_ids or changed_ids):
                ts = datetime.now(timezone.utc).isoformat()
                for rid in removed_ids:
                    self.broadcast_event("node_removed", {"node_id": rid, "nodeId": rid, "timestamp": ts})
                snap = self.get_snapshot()
                self.broadcast_event("initial_snapshot", snap)

    def _run_real_loop(self, interval: float) -> None:
        self._poll_real_cluster(broadcast=False)
        while self.running:
            time.sleep(interval)
            if not self.running:
                break
            self._poll_real_cluster(broadcast=True)

    def start(self, mock: bool = False, poll_interval: float = 10.0) -> None:
        if self.running:
            return
        self.mock = mock
        if not mock:
            self._poll_real_cluster(broadcast=False)
        self.running = True
        target = self._run_mock_loop if mock else self._run_real_loop
        self.worker_thread = threading.Thread(target=target, args=(poll_interval,), daemon=True)
        self.worker_thread.start()

    def stop(self) -> None:
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5.0)
