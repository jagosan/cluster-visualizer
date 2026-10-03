"""3D Spatial Layout Generator for Cluster Visualizer (SPEC-03 Horizontal Node Peer Worker Deck).

Assigns (X, Y, Z) coordinates and asset types to cluster components across vertical elevation
tiers (Y-axis) and horizontal spatial layouts (X-Z planes) according to the
skyscraper architectural blueprint in docs/architecture/01-architectural-skyscraper-topology.md.

SPEC-03 Update:
- Workers are no longer stacked vertically. They form a single horizontal deck at Y=0.5.
- Kubelets, Containerd, DaemonSets, and Workload Pods are placed relative to their parent Worker Node chassis.
- CNI mesh edges are added between DaemonSets on different nodes.
"""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple
from .models import NodeComponent, DataFlowEdge, MachineShape, RemoteServiceResource, ManagedServiceCategory

# Vertical elevation tiers per skyscraper layer (SPEC-03)
ELEVATION_TIERS: Dict[str, float] = {
    "client": 12.0,          # Distant Horizon (kubectl, browser, crd-watcher)
    "aggregation": 9.5,      # Ingress & API Aggregator Tray
    "apiserver": 7.0,        # Executive Core: kube-apiserver horizontal array
    "vault": 5.5,            # etcd Vault: logically BEHIND (Z = -3.5) and below API server
    "supervisor": 4.5,       # Kube-scheduler & Controller Manager Tray
    "framework": 2.5,        # Framework extension floor (Ray, Spark CRD operators)
    "worker_deck": 0.5,      # Single horizontal worker deck floor at Y = 0.5
    "worker_base": 0.5,      # Maintain for backward compatibility
    "worker_pitch": -2.8,    # Deprecated for layout, kept for compat

    # Subterranean Strata Tiers (SPEC-08)
    "surface_datum": 0.0,    # Ground reference plane / cutaway glass (KeyG X-ray toggle)
    "compute_chassis": -2.5, # Sub-Level B1: Karpenter NodePools / GKE Machine Shapes
    "kro_manifold": -4.8,    # Sub-Level B2 Upper: kro composition routing hub
    "cloud_vault": -6.5,     # Sub-Level B2 Lower: KCC / ACK managed service vaults
    "bedrock_egress": -10.5, # Sub-Level B3: External SaaS, WAN, NAT gateways
}

# Z-offsets for specific control plane components
CONTROL_PLANE_Z_OFFSETS: Dict[str, float] = {
    "etcd": -3.5,
    "scheduler": 0.8,
    "controller-manager": 0.8,
    "apiserver": 0.0,
}

# Constants for Worker Deck Layout
WORKER_DECK_Y = ELEVATION_TIERS["worker_deck"]
WORKER_SPACING_X = 6.0
RUNTIME_BAY_OFFSET_X = -1.8  # Relative to chassis center
CONTAINERD_OFFSET_X = -0.8   # Relative to chassis center
DAEMONSET_BASE_OFFSET_X = 1.2
DAEMONSET_SECOND_OFFSET_X = 2.0
RUNTIME_Z = -1.5
DAEMONSET_Z = -1.5
DAEMONSET_Z_ALT = -0.5
POD_Z_FRONT = 0.2
POD_Z_BACK = 1.2
POD_X_STAGGER = 0.6
POD_Y = 0.75


def _is_daemonset(node: NodeComponent) -> bool:
    """Detect if a node/component represents a DaemonSet or CNI plugin."""
    name_lower = node.name.lower()
    kind_lower = node.kind.lower()
    labels = getattr(node, 'labels', {}) or {}
    
    # Check kind
    if kind_lower == "daemonset":
        return True
        
    # Check name patterns for common CNI/monitoring agents
    cni_keywords = ["proxy", "cilium", "calico", "flannel", "weave", "node-exporter", "agent"]
    if any(kw in name_lower for kw in cni_keywords):
        return True
        
    # Check labels
    if "daemonset" in str(labels).lower():
        return True
        
    return False


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
    daemonsets: List[NodeComponent] = []
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
        elif _is_daemonset(n):
            daemonsets.append(n)
        elif n.layer == "node" or kind_lower == "node":
            worker_nodes.append(n)
        else:
            workload_pods.append(n)

    # 1. Distant Client Layer (Y = 12.0, Z = 6.0)
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

    # 7. Worker Deck Placement (SPEC-03: Horizontal Peers at Y = 0.5)
    N = max(len(worker_nodes), 1)
    
    # Map worker nodes to their chassis index for child component placement
    # We assume kubelets/containerd/daemonsets/pods are associated with worker nodes by index or name matching
    # For simplicity in this refactor, we distribute children round-robin across the N worker chassis
    
    worker_chassis_positions: List[float] = []
    
    for i in range(N):
        X_i = -((N - 1) * WORKER_SPACING_X) / 2.0 + i * WORKER_SPACING_X
        worker_chassis_positions.append(X_i)
        
        if i < len(worker_nodes):
            node = worker_nodes[i]
            node.spatial.x = X_i
            node.spatial.y = WORKER_DECK_Y
            node.spatial.z = 0.0
            node.spatial.asset_type = "LayerTray_Worker"

    # Helper to assign position relative to chassis
    def place_on_chassis(child: NodeComponent, chassis_idx: int, offset_x: float, y: float, z: float, asset_type: str):
        if chassis_idx >= len(worker_chassis_positions):
            return
        X_i = worker_chassis_positions[chassis_idx]
        child.spatial.x = X_i + offset_x
        child.spatial.y = y
        child.spatial.z = z
        child.spatial.asset_type = asset_type

    # Place Kubelets (Runtime Bay Left)
    for i, k in enumerate(kubelets):
        chassis_idx = i % N
        place_on_chassis(k, chassis_idx, RUNTIME_BAY_OFFSET_X, 0.7, RUNTIME_Z, "Cuboid_Kubelet")

    # Place Containerd (Runtime Bay Left, next to Kubelet)
    for i, c in enumerate(containerds):
        chassis_idx = i % N
        place_on_chassis(c, chassis_idx, CONTAINERD_OFFSET_X, 0.7, RUNTIME_Z, "Cuboid_Containerd")

    # Place DaemonSets (DaemonSet Bay Right)
    # Track how many daemonsets are placed per chassis to handle stacking
    daemonset_counts_per_chassis: Dict[int, int] = {i: 0 for i in range(N)}
    
    for i, d in enumerate(daemonsets):
        chassis_idx = i % N
        count = daemonset_counts_per_chassis[chassis_idx]
        
        if count == 0:
            offset_x = DAEMONSET_BASE_OFFSET_X
            z = DAEMONSET_Z
        elif count == 1:
            offset_x = DAEMONSET_SECOND_OFFSET_X
            z = DAEMONSET_Z
        else:
            # Stack vertically or shift Z for 3rd+
            offset_x = DAEMONSET_BASE_OFFSET_X
            z = DAEMONSET_Z_ALT
            
        place_on_chassis(d, chassis_idx, offset_x, 0.65, z, "Cuboid_DaemonSet")
        daemonset_counts_per_chassis[chassis_idx] += 1

    # Place Workload Pods (Center/Front)
    # Distribute workload pods among the N worker chassis (round robin)
    # In chassis i, position pods in front slots at Z = 0.2 and Z = 1.2, with X staggered
    
    pod_slots_per_chassis: Dict[int, int] = {i: 0 for i in range(N)}
    
    for i, pod in enumerate(workload_pods):
        chassis_idx = i % N
        slot_count = pod_slots_per_chassis[chassis_idx]
        
        # Determine slot position within the chassis
        # Slots: 
        # 0: X_i - 0.6, Z = 0.2
        # 1: X_i + 0.6, Z = 0.2
        # 2: X_i - 0.6, Z = 1.2
        # 3: X_i + 0.6, Z = 1.2
        # Then repeat with Y offset? Spec says Y=0.75 for all. 
        # If more than 4 pods per chassis, we might need to stack or just overlap. 
        # For now, cycle through the 4 slots.
        
        slot_idx = slot_count % 4
        
        if slot_idx == 0:
            offset_x = -POD_X_STAGGER
            z = POD_Z_FRONT
        elif slot_idx == 1:
            offset_x = POD_X_STAGGER
            z = POD_Z_FRONT
        elif slot_idx == 2:
            offset_x = -POD_X_STAGGER
            z = POD_Z_BACK
        else: # slot_idx == 3
            offset_x = POD_X_STAGGER
            z = POD_Z_BACK
            
        place_on_chassis(pod, chassis_idx, offset_x, POD_Y, z, "") # Asset type set below
        
        # Assign specific asset type based on name/kind
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
            
        pod_slots_per_chassis[chassis_idx] += 1

    return nodes


# ---------------------------------------------------------------------------
# SPEC-08: Subterranean Strata Layout (Machine Shapes & Managed Cloud Vaults)
# ---------------------------------------------------------------------------

# Horizontal spacing between docked B1 chassis footprints
COMPUTE_CHASSIS_SPACING_X = 1.6
# Vault grid arrangement on Sub-Level B2 Lower
VAULT_GRID_COLS = 3
VAULT_SPACING_X = 3.0
VAULT_SPACING_Z = 3.0
# Bedrock egress row spacing on Sub-Level B3
BEDROCK_SPACING_X = 3.0

# Canonical world anchor of the kro hydraulic manifold hub (Sub-Level B2 Upper)
KRO_MANIFOLD_ANCHOR: Tuple[float, float, float] = (0.0, ELEVATION_TIERS["kro_manifold"], 0.0)


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value into the closed interval [lo, hi]."""
    return max(lo, min(hi, value))


def calculate_chassis_dimensions(vcpus: int, memory_gib: float) -> Tuple[float, float, float]:
    """Proportional chassis sizing per SPEC-08 §2.2.

        Width  (X) = clamp(3.2 + 0.35 * sqrt(vCPU),      3.2, 8.0)
        Depth  (Z) = clamp(2.4 + 0.30 * sqrt(RAM GiB),   2.4, 7.5)
        Height (Y) = 0.6

    Returns (width, height, depth) rounded to 2 decimals.
    """
    width = _clamp(3.2 + 0.35 * math.sqrt(max(vcpus, 0)), 3.2, 8.0)
    depth = _clamp(2.4 + 0.30 * math.sqrt(max(memory_gib, 0.0)), 2.4, 7.5)
    height = 0.6
    return (round(width, 2), round(height, 2), round(depth, 2))


def apply_subterranean_layout(
    machine_shapes: List[MachineShape],
    subterranean_resources: List[RemoteServiceResource],
) -> Dict[str, Tuple[float, float, float]]:
    """Position SPEC-08 subterranean strata objects below the surface datum.

    - MachineShape chassis (Sub-Level B1, Y = -2.5): footprints are recomputed
      with calculate_chassis_dimensions and docked left-to-right along X.
    - Managed service vaults (Sub-Level B2 Lower, Y = -6.5): centered grid on
      the X-Z plane (VAULT_GRID_COLS per row).
    - NETWORKING_GATEWAY vaults (Sub-Level B3, Y = -10.5): bedrock egress row.

    Mutates MachineShape chassis dimensions and RemoteServiceResource.spatial,
    and returns {object_key: (x, y, z)} for every placed object, including the
    canonical 'kro_manifold_hub' anchor at Y = -4.8.
    """
    positions: Dict[str, Tuple[float, float, float]] = {}
    positions["kro_manifold_hub"] = KRO_MANIFOLD_ANCHOR

    # --- Sub-Level B1: Compute chassis row (Y = -2.5) -----------------------
    dims: List[Tuple[float, float, float]] = []
    for m in machine_shapes:
        w, h, d = calculate_chassis_dimensions(m.vcpus, m.memory_gib)
        m.chassis_width = w
        m.chassis_depth = d
        dims.append((w, h, d))

    total_span = sum(w for w, _, _ in dims) + COMPUTE_CHASSIS_SPACING_X * max(len(dims) - 1, 0)
    cursor = -total_span / 2.0
    for m, (w, _, d) in zip(machine_shapes, dims):
        x = cursor + w / 2.0
        cursor += w + COMPUTE_CHASSIS_SPACING_X
        positions[m.node_name] = (round(x, 2), ELEVATION_TIERS["compute_chassis"], 0.0)

    # --- Sub-Level B2/B3: Managed service vaults ----------------------------
    vaults = [r for r in subterranean_resources
              if r.category != ManagedServiceCategory.NETWORKING_GATEWAY]
    bedrock = [r for r in subterranean_resources
               if r.category == ManagedServiceCategory.NETWORKING_GATEWAY]

    # Vault grid on X-Z plane, centered, VAULT_GRID_COLS per row
    n_rows = (len(vaults) + VAULT_GRID_COLS - 1) // VAULT_GRID_COLS
    for i, r in enumerate(vaults):
        row = i // VAULT_GRID_COLS
        cols_in_row = min(VAULT_GRID_COLS, len(vaults) - row * VAULT_GRID_COLS)
        col = i % VAULT_GRID_COLS
        x = (col - (cols_in_row - 1) / 2.0) * VAULT_SPACING_X
        z = (row - (n_rows - 1) / 2.0) * VAULT_SPACING_Z
        r.spatial = {"x": round(x, 2), "y": ELEVATION_TIERS["cloud_vault"], "z": round(z, 2)}
        positions[r.id] = (r.spatial["x"], r.spatial["y"], r.spatial["z"])

    # Bedrock egress row (Y = -10.5)
    for i, r in enumerate(bedrock):
        x = (i - (len(bedrock) - 1) / 2.0) * BEDROCK_SPACING_X
        r.spatial = {"x": round(x, 2), "y": ELEVATION_TIERS["bedrock_egress"], "z": 0.0}
        positions[r.id] = (r.spatial["x"], r.spatial["y"], r.spatial["z"])

    return positions


from typing import List
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any

# Assuming these models are defined in models.py as per spec
# We will define minimal stubs here to make the function self-contained if needed,
# but the prompt implies we just write the function. 
# However, to be safe and executable, I will assume the imports exist in the environment.
# The prompt asks for ONLY the function.

def generate_skyscraper_edges(nodes: List[NodeComponent]) -> List[DataFlowEdge]:
    """
    Generates data flow edges based on the skyscraper architecture specification.
    """
    edges: List[DataFlowEdge] = []

    # Categorize nodes based on asset_type, name, or kind
    clients = [n for n in nodes if n.spatial.asset_type == "Client_Slab"]
    penthouse = [n for n in nodes if n.spatial.asset_type in ("LayerTray_Control", "Skyscraper_Penthouse")]
    apiservers = [n for n in nodes if "apiserver" in n.name.lower() or n.kind.lower() == "apiserver"]
    etcds = [n for n in nodes if "etcd" in n.name.lower() or n.kind.lower() == "etcd"]
    supervisors = [n for n in nodes if "scheduler" in n.name.lower() or "controller" in n.name.lower()]
    kubelets = [n for n in nodes if n.spatial.asset_type in ("Cuboid_Kubelet", "Module_Kubelet")]
    daemonsets = [n for n in nodes if n.spatial.asset_type == "Cuboid_DaemonSet"]
    ray_heads = [n for n in nodes if "head" in n.name.lower() and "ray" in n.name.lower()]
    ray_workers = [n for n in nodes if "head" not in n.name.lower() and "ray" in n.name.lower()]

    # Helper to create an edge
    def create_edge(src: NodeComponent, dst: NodeComponent, flow_type: str, protocol: str, direction: str, volume_label: str = "") -> DataFlowEdge:
        return DataFlowEdge(
            source=src.id,
            target=dst.id,
            flow_type=flow_type,
            protocol=protocol,
            direction=direction,
            volume_label=volume_label
        )

    # 1. Client -> Ingress / API Server
    # "Ingress" is not explicitly categorized, but spec says Client -> Ingress / API Server.
    # We assume clients connect to API Servers directly or via an ingress component if present.
    # Given the categories, we connect Clients to API Servers.
    for client in clients:
        for apiserver in apiservers:
            edges.append(create_edge(
                src=client,
                dst=apiserver,
                flow_type="traffic",
                protocol="HTTPS/443",
                direction="unidirectional",
                volume_label="list pods"
            ))

    # 2. Penthouse / Aggregator -> API Server Core
    for ph in penthouse:
        for apiserver in apiservers:
            edges.append(create_edge(
                src=ph,
                dst=apiserver,
                flow_type="traffic",
                protocol="HTTPS/6443",
                direction="unidirectional",
                volume_label=""
            ))

    # 3. Inter-API Server Sync Conduits
    # Bidirectional between all pairs of API Servers
    for i in range(len(apiservers)):
        for j in range(i + 1, len(apiservers)):
            edges.append(create_edge(
                src=apiservers[i],
                dst=apiservers[j],
                flow_type="control_plane",
                protocol="HTTPS/6443",
                direction="bidirectional",
                volume_label="peer sync"
            ))

    # 4. API Server <-> etcd Vault
    for apiserver in apiservers:
        for etcd in etcds:
            edges.append(create_edge(
                src=apiserver,
                dst=etcd,
                flow_type="control_plane",
                protocol="gRPC/2379",
                direction="bidirectional",
                volume_label="raft KV"
            ))

    # 5. Supervisors <-> API Server
    for sup in supervisors:
        for apiserver in apiservers:
            edges.append(create_edge(
                src=sup,
                dst=apiserver,
                flow_type="control_plane",
                protocol="HTTPS/6443",
                direction="bidirectional",
                volume_label="reconcile loop"
            ))

    # 6. Kubelet -> API Server
    for kubelet in kubelets:
        for apiserver in apiservers:
            edges.append(create_edge(
                src=kubelet,
                dst=apiserver,
                flow_type="control_plane",
                protocol="HTTPS/6443/Heartbeat",
                direction="unidirectional",
                volume_label="lease heartbeat"
            ))

    # 7. Ray Head <-> Ray Workers
    for head in ray_heads:
        for worker in ray_workers:
            edges.append(create_edge(
                src=head,
                dst=worker,
                flow_type="framework_control",
                protocol="gRPC/10001",
                direction="bidirectional",
                volume_label="tensor bypass"
            ))

    # 8. Lateral CNI Mesh between adjacent daemonsets
    # "Adjacent" is ambiguous without spatial coordinates. 
    # In a mesh, typically all daemonsets connect to each other, or we assume a full mesh among daemonsets.
    # Given "Lateral CNI Mesh", a full mesh among daemonsets is the standard interpretation for CNI meshes like Calico/Flannel in this context.
    for i in range(len(daemonsets)):
        for j in range(i + 1, len(daemonsets)):
            edges.append(create_edge(
                src=daemonsets[i],
                dst=daemonsets[j],
                flow_type="traffic",
                protocol="eBPF/Mesh",
                direction="bidirectional",
                volume_label="lateral CNI mesh"
            ))

    return edges
