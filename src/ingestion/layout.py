"""3D Spatial Layout Generator for Cluster Visualizer (SPEC-01 Skyscraper Topology).

Assigns (X, Y, Z) coordinates and asset types to cluster components across vertical elevation
tiers (Y-axis) and horizontal spatial layouts (X-Z planes) according to the
skyscraper architectural blueprint in docs/architecture/01-architectural-skyscraper-topology.md.
"""

from __future__ import annotations
import math
from typing import Dict, List, Optional
from .models import NodeComponent, DataFlowEdge

# Vertical elevation tiers per skyscraper layer (SPEC-02)
ELEVATION_TIERS: Dict[str, float] = {
    "client": 12.0,          # Distant Horizon (kubectl, browser, crd-watcher)
    "aggregation": 9.5,      # Ingress & API Aggregator Tray
    "apiserver": 7.0,        # Executive Core: kube-apiserver horizontal array
    "vault": 5.5,            # etcd Vault: logically BEHIND (Z = -3.5) and below API server
    "supervisor": 4.5,       # Kube-scheduler & Controller Manager Tray
    "framework": 2.5,        # Framework extension floor (Ray, Spark CRD operators)
    "worker_base": 0.5,      # First worker node floor
    "worker_pitch": -2.8,    # Spacing between successive worker floors
}

# Z-offsets for specific control plane components
CONTROL_PLANE_Z_OFFSETS: Dict[str, float] = {
    "etcd": -3.5,
    "scheduler": 0.8,
    "controller-manager": 0.8,
    "apiserver": 0.0,
}


def apply_spatial_layout(nodes: List[NodeComponent]) -> List[NodeComponent]:
    """Calculate and assign (X, Y, Z) spatial positions and asset_type to all nodes."""
    clients: List[NodeComponent] = []
    aggregations: List[NodeComponent] = []
    apiservers: List[NodeComponent] = []
    etcds: List[NodeComponent] = []
    schedulers: List[NodeComponent] = []
    controllers: List[NodeComponent] = []
    frameworks: List[NodeComponent] = []
    worker_nodes: List[NodeComponent] = []
    kubelets: List[NodeComponent] = []
    containerds: List[NodeComponent] = []
    workload_pods: List[NodeComponent] = []

    # Categorize nodes
    for n in nodes:
        name_lower = n.name.lower()
        kind_lower = n.kind.lower()

        if "client" in name_lower or "kubectl" in name_lower or kind_lower == "client":
            clients.append(n)
        elif "aggregator" in name_lower or "ingress" in name_lower or kind_lower in ("ingress", "apiaggregator"):
            aggregations.append(n)
        elif "apiserver" in name_lower or "api-server" in name_lower or kind_lower == "apiserver":
            apiservers.append(n)
        elif "etcd" in name_lower or kind_lower == "etcd":
            etcds.append(n)
        elif "scheduler" in name_lower or kind_lower == "scheduler":
            schedulers.append(n)
        elif "controller" in name_lower or kind_lower == "controllermanager":
            controllers.append(n)
        elif "ray" in name_lower or "spark" in name_lower or n.layer == "framework":
            frameworks.append(n)
        elif "kubelet" in name_lower or kind_lower == "kubelet":
            kubelets.append(n)
        elif "containerd" in name_lower or kind_lower == "containerd":
            containerds.append(n)
        elif n.layer == "node" or kind_lower == "node":
            worker_nodes.append(n)
        else:
            workload_pods.append(n)

    # 1. Distant Client Layer (Y = 11.0, Z = 6.0)
    for i, n in enumerate(clients):
        n.spatial.y = ELEVATION_TIERS["client"]
        n.spatial.z = 6.0
        n.spatial.x = (i - (len(clients) - 1) / 2.0) * 2.8 if len(clients) > 1 else 0.0
        n.spatial.asset_type = "Client_Slab"

    # 2. Penthouse / API Aggregation Layer (Y = 9.5, Z = 0.0)
    for i, n in enumerate(aggregations):
        n.spatial.y = ELEVATION_TIERS["aggregation"]
        n.spatial.z = 0.0
        n.spatial.x = (i - (len(aggregations) - 1) / 2.0) * 2.5 if len(aggregations) > 1 else 0.0
        n.spatial.asset_type = "LayerTray_Control"

    # 3. API Server Core Layer (Y = 7.0, Z = 0.0)
    for i, n in enumerate(apiservers):
        n.spatial.y = ELEVATION_TIERS["apiserver"]
        n.spatial.z = 0.0
        n.spatial.x = (i - (len(apiservers) - 1) / 2.0) * 2.4 if len(apiservers) > 1 else 0.0
        n.spatial.asset_type = "Cuboid_APIServer"

    # 4. etcd Vault Tier (Y = 5.5, Z = -3.5) [Logically Behind / Below API Server]
    for i, n in enumerate(etcds):
        n.spatial.y = ELEVATION_TIERS["vault"]
        n.spatial.z = -3.5
        n.spatial.x = (i - (len(etcds) - 1) / 2.0) * 2.2 if len(etcds) > 1 else 0.0
        n.spatial.asset_type = "Cuboid_etcd"

    # 5. Supervisors (Y = 4.5, Z = 0.8) [In front of vault]
    for i, n in enumerate(schedulers):
        n.spatial.y = ELEVATION_TIERS["supervisor"]
        n.spatial.z = 0.8
        n.spatial.x = -2.8 - i * 1.5
        n.spatial.asset_type = "Cuboid_Supervisor"

    for i, n in enumerate(controllers):
        n.spatial.y = ELEVATION_TIERS["supervisor"]
        n.spatial.z = 0.8
        n.spatial.x = 2.8 + i * 1.5
        n.spatial.asset_type = "Cuboid_Supervisor"

    # 6. Framework Extension Floor (Y = 2.5, Z = 0.0)
    ray_heads = [n for n in frameworks if "head" in n.name.lower()]
    ray_workers = [n for n in frameworks if "head" not in n.name.lower()]
    for i, n in enumerate(ray_heads):
        n.spatial.y = ELEVATION_TIERS["framework"]
        n.spatial.z = 0.0
        n.spatial.x = -2.0 - i * 1.6
        n.spatial.asset_type = "Cuboid_Ray"

    for i, n in enumerate(ray_workers):
        n.spatial.y = ELEVATION_TIERS["framework"]
        n.spatial.z = 0.0
        n.spatial.x = 0.2 + i * 1.6
        n.spatial.asset_type = "Cuboid_Ray" if "ray" in n.name.lower() else "Framework_Spark"

    # 7. Worker Node Floors (Y = 0.5, -2.3, -5.1...)
    floor_count = max(len(worker_nodes), 1)
    for floor_idx, node in enumerate(worker_nodes):
        y_floor = ELEVATION_TIERS["worker_base"] + floor_idx * ELEVATION_TIERS["worker_pitch"]
        node.spatial.x = 0.0
        node.spatial.y = y_floor
        node.spatial.z = 0.0
        node.spatial.asset_type = "LayerTray_Worker"

    # Place Kubelets & Containerds on respective floors
    for i, k in enumerate(kubelets):
        floor_idx = i % floor_count
        y_floor = ELEVATION_TIERS["worker_base"] + floor_idx * ELEVATION_TIERS["worker_pitch"]
        k.spatial.x = -2.2
        k.spatial.y = y_floor + 0.25
        k.spatial.z = 0.0
        k.spatial.asset_type = "Cuboid_Kubelet"

    for i, c in enumerate(containerds):
        floor_idx = i % floor_count
        y_floor = ELEVATION_TIERS["worker_base"] + floor_idx * ELEVATION_TIERS["worker_pitch"]
        c.spatial.x = -1.2
        c.spatial.y = y_floor + 0.25
        c.spatial.z = 0.0
        c.spatial.asset_type = "Cuboid_Containerd"

    # Place Workload Pods along the floor trays
    pod_x_slots = [0.0, 1.1, 2.2]
    for i, pod in enumerate(workload_pods):
        floor_idx = i % floor_count
        slot_idx = (i // floor_count) % len(pod_x_slots)
        z_offset = -0.5 if (i // (floor_count * len(pod_x_slots))) % 2 == 1 else 0.5
        y_floor = ELEVATION_TIERS["worker_base"] + floor_idx * ELEVATION_TIERS["worker_pitch"]
        
        pod.spatial.x = pod_x_slots[slot_idx]
        pod.spatial.y = y_floor + 0.25
        pod.spatial.z = z_offset

        pname = pod.name.lower()
        pkind = pod.kind.lower()
        if "postgres" in pname or "postgres" in pkind:
            pod.spatial.asset_type = "Database_Postgres"
        elif "redis" in pname or "redis" in pkind:
            pod.spatial.asset_type = "Cache_Redis"
        elif "ray" in pname or "ray" in pkind:
            pod.spatial.asset_type = "Cuboid_Ray"
        elif "spark" in pname or "spark" in pkind:
            pod.spatial.asset_type = "Framework_Spark"
        else:
            pod.spatial.asset_type = "Cuboid_Pod"

    return nodes


def generate_skyscraper_edges(nodes: List[NodeComponent]) -> List[DataFlowEdge]:
    """Generate architectural data flow conduits between components per SPEC-01 & SPEC-02."""
    edges: List[DataFlowEdge] = []
    
    clients = [n for n in nodes if n.spatial.asset_type == "Client_Slab"]
    penthouse = [n for n in nodes if n.spatial.asset_type in ("LayerTray_Control", "Skyscraper_Penthouse")]
    apiservers = [n for n in nodes if "apiserver" in n.name.lower() or n.kind.lower() == "apiserver"]
    etcds = [n for n in nodes if "etcd" in n.name.lower() or n.kind.lower() == "etcd"]
    supervisors = [n for n in nodes if "scheduler" in n.name.lower() or "controller" in n.name.lower()]
    kubelets = [n for n in nodes if n.spatial.asset_type in ("Cuboid_Kubelet", "Module_Kubelet")]
    ray_heads = [n for n in nodes if "head" in n.name.lower() and "ray" in n.name.lower()]
    ray_workers = [n for n in nodes if "head" not in n.name.lower() and "ray" in n.name.lower()]

    # 1. Distant Client -> Penthouse / Ingress (traffic / HTTPS/443)
    target_entry = penthouse[0].id if penthouse else (apiservers[0].id if apiservers else None)
    if target_entry:
        for c in clients:
            edges.append(DataFlowEdge(
                source=c.id,
                target=target_entry,
                flow_type="traffic",
                protocol="HTTPS/443",
                direction="unidirectional",
                animated=True,
                volume_label="watch CRDs" if "crd" in c.name.lower() else "list pods"
            ))

    # 2. Penthouse / Aggregator -> API Server Core
    if penthouse and apiservers:
        for p in penthouse:
            for api in apiservers:
                edges.append(DataFlowEdge(
                    source=p.id,
                    target=api.id,
                    flow_type="traffic",
                    protocol="HTTPS/6443",
                    direction="unidirectional",
                    animated=True
                ))

    # 3. Inter-API Server Sync Conduits
    if len(apiservers) > 1:
        for i in range(len(apiservers) - 1):
            edges.append(DataFlowEdge(
                source=apiservers[i].id,
                target=apiservers[i + 1].id,
                flow_type="control_plane",
                protocol="HTTPS/6443",
                direction="bidirectional",
                animated=True,
                volume_label="peer sync"
            ))

    # 4. API Server <-> etcd Vault (Dedicated storage consensus pipes)
    if apiservers and etcds:
        for api in apiservers:
            for e in etcds:
                edges.append(DataFlowEdge(
                    source=api.id,
                    target=e.id,
                    flow_type="control_plane",
                    protocol="gRPC/2379",
                    direction="bidirectional",
                    animated=True,
                    volume_label="raft KV"
                ))

    # 5. Supervisors (Scheduler/Controller) <-> API Server
    if apiservers:
        primary_api = apiservers[0].id
        for s in supervisors:
            edges.append(DataFlowEdge(
                source=s.id,
                target=primary_api,
                flow_type="control_plane",
                protocol="HTTPS/6443",
                direction="bidirectional",
                animated=True,
                volume_label="reconcile loop"
            ))

    # 6. Kubelet -> API Server Vertical Heartbeat Risers
    if apiservers:
        primary_api = apiservers[0].id
        for k in kubelets:
            edges.append(DataFlowEdge(
                source=k.id,
                target=primary_api,
                flow_type="control_plane",
                protocol="HTTPS/6443/Heartbeat",
                direction="unidirectional",
                animated=True,
                volume_label="lease heartbeat"
            ))

    # 7. Framework Worker Direct Lateral Bypass Conduits (Ray Head <-> Ray Workers)
    if ray_heads and ray_workers:
        for h in ray_heads:
            for w in ray_workers:
                edges.append(DataFlowEdge(
                    source=h.id,
                    target=w.id,
                    flow_type="framework_control",
                    protocol="gRPC/10001",
                    direction="bidirectional",
                    animated=True,
                    volume_label="tensor bypass"
                ))

    return edges
