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
from .models import NodeComponent, DataFlowEdge, MachineShape, RemoteServiceResource, ManagedServiceCategory, PodGeometrySpec, KueueWorkloadStatus

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

# SPEC-09 §3.1: proportional pod capsule scaling clamps
POD_HEIGHT_MIN = 0.40
POD_HEIGHT_MAX = 2.60
POD_RADIUS_MIN = 0.20
POD_RADIUS_MAX = 0.90
# Fallback resource requests when a snapshot carries no explicit requests
POD_DEFAULT_CPU_CORES = 0.5
POD_DEFAULT_MEMORY_GIB = 1.0


def calculate_pod_dimensions(cpu_cores: float, memory_gib: float) -> Tuple[float, float]:
    """Proportional pod capsule dimensions per SPEC-09 §3.1.

        Height (Y) = clamp(0.40 + 0.35 * sqrt(vCPU),        0.40, 2.60)
        Radius (R) = clamp(0.20 + 0.12 * log2(max(1, RAM)), 0.20, 0.90)

    Returns (height, radius) rounded to 3 decimals.
    """
    cpu = max(float(cpu_cores), 0.0)
    mem = max(float(memory_gib), 0.0)
    height = min(POD_HEIGHT_MAX, max(POD_HEIGHT_MIN, 0.40 + 0.35 * math.sqrt(cpu)))
    radius = min(POD_RADIUS_MAX, max(POD_RADIUS_MIN, 0.20 + 0.12 * math.log2(max(1.0, mem))))
    return (round(height, 3), round(radius, 3))


def extract_pod_requests(metrics: Dict[str, object]) -> Tuple[float, float]:
    """Pull (cpu_cores, memory_gib) requests out of a component metrics dict.

    Prefers explicit request keys (``cpu_request_cores`` /
    ``memory_request_gib``), falls back to bare capacity keys
    (``cpu_cores`` / ``memory_gib``), then to SPEC-09 ADR "Note to Future
    Self" defaults (0.5 cores / 1.0 GiB) for pods without requests.
    """
    def _pick(*keys: str, default: float) -> float:
        for key in keys:
            raw = metrics.get(key)
            if raw is None:
                continue
            try:
                return float(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
        return default

    cpu = _pick("cpu_request_cores", "cpu_cores", default=POD_DEFAULT_CPU_CORES)
    mem = _pick("memory_request_gib", "memory_gib", default=POD_DEFAULT_MEMORY_GIB)
    return (cpu, mem)


def assign_pod_geometry(node: NodeComponent) -> PodGeometrySpec:
    """Compute and attach a PodGeometrySpec to a pod-like component.

    ``is_pending`` reflects ``metrics['scheduled'] is False`` (the
    PodScheduled=False condition of SPEC-09 §4.2) or an explicit
    ``metrics['pending']`` flag.
    """
    metrics = node.metrics or {}
    cpu, mem = extract_pod_requests(metrics)
    height, radius = calculate_pod_dimensions(cpu, mem)
    scheduled = metrics.get("scheduled", True)
    is_pending = bool(metrics.get("pending", False)) or scheduled is False
    # SPEC-09 §4.2: pods targeting a Karpenter NodeClaim link to a ghost chassis
    claim = metrics.get("karpenter_target_node_claim")
    if claim is None:
        claim = (getattr(node, "raw_labels", None) or {}).get("karpenter_target_node_claim")
    geometry = PodGeometrySpec(
        height=height,
        radius=radius,
        is_pending=is_pending,
        karpenter_target_node_claim=str(claim) if claim else None,
    )
    node.pod_geometry = geometry
    return geometry


# ---------------------------------------------------------------------------
# SPEC-09 §4.1 / §4.2 (ADR-02): Exterior Pre-Admission Staging Yard
# ---------------------------------------------------------------------------

# Reinforced industrial tarmac plane (SPEC-09 §4.1)
STAGING_TARMAC_Y = 0.2
STAGING_TARMAC_X_MIN = -24.0
STAGING_TARMAC_X_MAX = -12.0
STAGING_TARMAC_Z_MIN = -8.0
STAGING_TARMAC_Z_MAX = 8.0

# Raw pending-pod low anti-gravity hover band (SPEC-09 §4.2)
PENDING_HOVER_Y = 1.0
PENDING_HOVER_X_MIN = -22.0
PENDING_HOVER_X_MAX = -14.0
PENDING_HOVER_Z_MIN = -6.0
PENDING_HOVER_Z_MAX = 6.0
PENDING_HOVER_COLS = 4
PENDING_HOVER_SPACING = 2.0

# Sub-Level B1 holographic ghost-node chassis row (SPEC-09 §4.2, ADR-02)
GHOST_NODE_Y = ELEVATION_TIERS["compute_chassis"]  # Y = -2.5
GHOST_NODE_X_MIN = -10.0
GHOST_NODE_X_MAX = 10.0
GHOST_NODE_Z_MIN = -4.0
GHOST_NODE_Z_MAX = 4.0
GHOST_CHASSIS_SPACING_X = 2.4

# Camera focus anchor for the Staging Apron Focus control (SPEC-09 §7.1)
STAGING_YARD_FOCUS_X = -18.0


def stage_pending_pod(pod: NodeComponent, index: int) -> Tuple[float, float, float]:
    """Route a pending pod (PodScheduled=False) into the exterior staging yard.

    Pending pods leave the worker deck entirely: they hover in low suspension
    at Y = 1.0 inside the hover band X in [-22.0, -14.0], Z in [-6.0, +6.0]
    (SPEC-09 §4.2 / ADR-02), parked on a deterministic 4-column grid so the
    staging layout is stable across snapshot refreshes. The pod's geometry
    records the staging track X for the client's tractor-beam wiring.
    """
    geometry = pod.pod_geometry if pod.pod_geometry is not None else assign_pod_geometry(pod)
    col = index % PENDING_HOVER_COLS
    row = index // PENDING_HOVER_COLS
    x = _clamp(
        PENDING_HOVER_X_MIN + col * PENDING_HOVER_SPACING,
        PENDING_HOVER_X_MIN,
        PENDING_HOVER_X_MAX,
    )
    z = _clamp(
        PENDING_HOVER_Z_MIN + (row % 7) * PENDING_HOVER_SPACING,
        PENDING_HOVER_Z_MIN,
        PENDING_HOVER_Z_MAX,
    )
    pod.spatial.x = round(x, 3)
    pod.spatial.y = PENDING_HOVER_Y
    pod.spatial.z = round(z, 3)
    geometry.staging_track_x = round(x, 3)
    return (pod.spatial.x, pod.spatial.y, pod.spatial.z)


def ghost_node_positions(count: int) -> List[Tuple[float, float, float]]:
    """Dock holographic Karpenter ghost-node chassis on Sub-Level B1.

    Returns ``count`` positions at Y = -2.5 docked left-to-right along X with
    GHOST_CHASSIS_SPACING_X spacing, clamped to the B1 domain
    X in [-10.0, +10.0], Z in [-4.0, +4.0] (SPEC-09 §4.2).
    """
    if count <= 0:
        return []
    span = GHOST_CHASSIS_SPACING_X * count
    start = -span / 2.0 + GHOST_CHASSIS_SPACING_X / 2.0
    positions: List[Tuple[float, float, float]] = []
    for i in range(count):
        x = _clamp(start + i * GHOST_CHASSIS_SPACING_X, GHOST_NODE_X_MIN, GHOST_NODE_X_MAX)
        positions.append((round(x, 2), GHOST_NODE_Y, 0.0))
    return positions


def karpenter_tractor_beam(
    pod_position: Tuple[float, float, float],
    ghost_position: Tuple[float, float, float],
    bottom_y: Optional[float] = None,
) -> Dict[str, object]:
    """Endpoints of the luminous amber Karpenter provisioning tractor beam.

    The beam projects from a pending pod hovering over the staging tarmac
    (top) down into the ghost-node chassis on Sub-Level B1 (bottom). The top
    anchors exactly on the pod's hover position; the bottom snaps to the
    ghost's X/Z footprint at the B1 stratum elevation (Y = -2.5 unless
    overridden), so client renderers always draw a beam terminating on the
    chassis (SPEC-09 §4.2).
    """
    top = (
        round(float(pod_position[0]), 3),
        round(float(pod_position[1]), 3),
        round(float(pod_position[2]), 3),
    )
    bottom = (
        round(float(ghost_position[0]), 3),
        round(float(bottom_y if bottom_y is not None else ghost_position[1]), 3),
        round(float(ghost_position[2]), 3),
    )
    return {
        "top": top,
        "bottom": bottom,
        "span_y": round(top[1] - bottom[1], 3),
    }


# ---------------------------------------------------------------------------
# SPEC-09 §5.2 / §5.3 (ADR-03, TASK-CV-1004): Kueue gang cargo pallets
# ---------------------------------------------------------------------------

# Modular cargo containment frame domain (docs/architecture/09 §2.1).
KUEUE_PALLET_X_MIN = -21.0
KUEUE_PALLET_X_MAX = -15.0
KUEUE_PALLET_Y_MIN = 0.4
KUEUE_PALLET_Y_MAX = 1.8
KUEUE_PALLET_Z_MIN = -6.0
KUEUE_PALLET_Z_MAX = 6.0

# Staging-track rail centerline the pallets dock along (also the mag-rail
# transit start X — SPEC-09 §5.3 "Admitted" row, transit from X = -18).
KUEUE_PALLET_RAIL_X = -18.0
# Row pitch: successive pallets dock along Z along the rail.
KUEUE_PALLET_ROW_SPACING_Z = 5.6

# Structured grid slot packing inside the containment frame.
KUEUE_GRID_COLS = 4
KUEUE_SLOT_SPACING_X = 1.3
KUEUE_SLOT_SPACING_Z = 1.5
# Constituent pods ride at hover height inside the frame (Y = 1.0 sits
# inside the pallet volume Y in [0.4, 1.8] and matches the staging hover).
KUEUE_SLOT_Y = 1.0
KUEUE_FRAME_HEIGHT = KUEUE_PALLET_Y_MAX - KUEUE_PALLET_Y_MIN  # 1.4
KUEUE_FRAME_MARGIN = 0.6

# High-speed mag-rail intake (SPEC-09 §2.1 / §5.3): admitted pallets glide
# from the staging rail (X = -18) into the tower intake bay (X = -8).
MAGRAIL_INTAKE_X = -8.0
MAGRAIL_INTAKE_Y = 1.2
MAGRAIL_INTAKE_Z = 0.0
MAGRAIL_TRANSIT_DURATION_MS = 2600
GANG_DEPLOY_BURST_MS = 900

# Canonical tween durations consumed by the Kueue client pipelines.
KUEUE_RESERVE_LOCK_MS = 800


def kueue_pallet_dimensions(pod_count: int) -> Tuple[float, float, float]:
    """Bounding-frame dimensions (width X, height Y, depth Z) for a gang.

    Slots pack in a ``KUEUE_GRID_COLS``-column grid; the industrial frame is
    sized to the grid plus a structural margin, clamped inside the freight
    pallet domain (SPEC-09 §5.2 / docs/architecture/09 §2.1).
    """
    count = max(int(pod_count), 1)
    rows = (count + KUEUE_GRID_COLS - 1) // KUEUE_GRID_COLS
    cols = min(KUEUE_GRID_COLS, count)
    width = _clamp(
        cols * KUEUE_SLOT_SPACING_X + KUEUE_FRAME_MARGIN,
        KUEUE_SLOT_SPACING_X + KUEUE_FRAME_MARGIN,
        KUEUE_PALLET_X_MAX - KUEUE_PALLET_X_MIN,  # 6.0
    )
    depth = _clamp(
        rows * KUEUE_SLOT_SPACING_Z + KUEUE_FRAME_MARGIN,
        KUEUE_SLOT_SPACING_Z + KUEUE_FRAME_MARGIN,
        KUEUE_PALLET_Z_MAX - KUEUE_PALLET_Z_MIN,  # 12.0
    )
    return (round(width, 3), round(KUEUE_FRAME_HEIGHT, 3), round(depth, 3))


def kueue_pallet_anchor(index: int) -> Tuple[float, float, float]:
    """Dock the ``index``-th cargo pallet on the staging-track rail.

    Pallets center-line on X = -18.0 (the rail / transit start anchor) and
    step along Z with KUEUE_PALLET_ROW_SPACING_Z, clamped inside the freight
    domain (SPEC-09 §5.3).
    """
    z = _clamp(
        KUEUE_PALLET_Z_MAX - 2.8 - index * KUEUE_PALLET_ROW_SPACING_Z,
        KUEUE_PALLET_Z_MIN,
        KUEUE_PALLET_Z_MAX,
    )
    y = (KUEUE_PALLET_Y_MIN + KUEUE_PALLET_Y_MAX) / 2.0  # 1.1
    return (KUEUE_PALLET_RAIL_X, y, round(z, 3))


def pack_kueue_workload(
    workload: object,
    pods: List[NodeComponent],
    anchor: Optional[Tuple[float, float, float]] = None,
) -> Dict[str, object]:
    """Route a Kueue Workload's constituent pods into structured pallet slots.

    Every pod belonging to the Workload CRD is parked inside the cargo
    containment bounding volume on the staging-track rail (ADR-03): a
    deterministic column-major grid at Y = 1.0 inside
    ``X in [-21, -15], Y in [0.4, 1.8], Z in [-6, +6]``. Queued /
    inadmissible pods carry ``is_pending`` geometry so the client renders
    them inside the frame under cold-blue standby lighting; admitted
    workloads keep their geometry live (the client animates the mag-rail
    transit and gang-deployment burst before the next snapshot lands).

    Mutates each pod's ``spatial`` + ``pod_geometry`` and returns the pallet
    wire payload ``{anchor, width, height, depth, slots}`` where ``slots``
    maps pod uid -> [x, y, z].
    """
    pallet_x, pallet_y, pallet_z = anchor if anchor is not None else kueue_pallet_anchor(0)
    width, height, depth = kueue_pallet_dimensions(len(pods))
    # Keep the whole frame inside the freight Z domain.
    pallet_z = _clamp(pallet_z, KUEUE_PALLET_Z_MIN + depth / 2.0, KUEUE_PALLET_Z_MAX - depth / 2.0)

    rows = (max(len(pods), 1) + KUEUE_GRID_COLS - 1) // KUEUE_GRID_COLS
    admitted = bool(getattr(workload, "is_admitted", False))
    workload_uid = str(getattr(workload, "workload_uid", "")) or None
    slots: Dict[str, List[float]] = {}
    for i, pod in enumerate(pods):
        col = i % KUEUE_GRID_COLS
        row = i // KUEUE_GRID_COLS
        cols_in_row = min(
            KUEUE_GRID_COLS,
            max(len(pods) - row * KUEUE_GRID_COLS, 1),
        )
        x = pallet_x + (col - (cols_in_row - 1) / 2.0) * KUEUE_SLOT_SPACING_X
        z = pallet_z + (row - (rows - 1) / 2.0) * KUEUE_SLOT_SPACING_Z
        x = round(_clamp(x, KUEUE_PALLET_X_MIN, KUEUE_PALLET_X_MAX), 3)
        z = round(_clamp(z, KUEUE_PALLET_Z_MIN, KUEUE_PALLET_Z_MAX), 3)

        geometry = pod.pod_geometry if pod.pod_geometry is not None else assign_pod_geometry(pod)
        pod.spatial.x = x
        pod.spatial.y = KUEUE_SLOT_Y
        pod.spatial.z = z
        pod.spatial.asset_type = ""
        geometry.is_pending = not admitted
        geometry.staging_track_x = x
        geometry.kueue_workload = workload_uid
        slots[pod.id] = [x, KUEUE_SLOT_Y, z]

    return {
        "anchor": [round(pallet_x, 3), round(pallet_y, 3), round(pallet_z, 3)],
        "width": width,
        "height": height,
        "depth": depth,
        "slots": slots,
    }


def sum_kueue_quota(pods: List[NodeComponent]) -> Tuple[float, float, int]:
    """Sum required quota (vCPU cores, RAM GiB, GPU count) over gang pods."""
    cpu = mem = 0.0
    gpus = 0
    for pod in pods:
        c, m = extract_pod_requests(pod.metrics or {})
        cpu += c
        mem += m
        raw_gpu = (pod.metrics or {}).get("gpu_request", (pod.metrics or {}).get("gpu_count"))
        try:
            gpus += int(raw_gpu) if raw_gpu is not None else 0
        except (TypeError, ValueError):
            pass
    return (round(cpu, 3), round(mem, 3), gpus)


def kueue_magrail_path(
    anchor: Tuple[float, float, float],
) -> Dict[str, List[float]]:
    """Endpoints of the high-speed mag-rail transit (SPEC-09 §5.3).

    The admitted pallet accelerates from its staging-rail anchor (X = -18)
    into the tower intake bay (X = -8.0, Y = 1.2, Z = 0.0).
    """
    return {
        "from": [round(float(anchor[0]), 3), round(float(anchor[1]), 3), round(float(anchor[2]), 3)],
        "to": [MAGRAIL_INTAKE_X, MAGRAIL_INTAKE_Y, MAGRAIL_INTAKE_Z],
    }


def gang_deployment_targets(count: int) -> List[Tuple[float, float, float]]:
    """Worker-deck target slots for a coordinated gang-deployment burst.

    All constituent pods deploy simultaneously onto the worker deck
    (Y = 0.75, X in [-9.6, +9.6], front / back pod rows alternating) so the
    whole gang lands in a single coordinated burst (SPEC-09 §5.3).
    """
    targets: List[Tuple[float, float, float]] = []
    for i in range(max(int(count), 0)):
        if count == 1:
            x = 0.0
        else:
            x = -9.6 + (19.2 * i) / (count - 1)
        z = POD_Z_FRONT if i % 2 == 0 else POD_Z_BACK
        targets.append((round(_clamp(x, -10.0, 10.0), 3), POD_Y, z))
    return targets


def quota_deficit_reason(workload: object) -> Optional[str]:
    """Human-readable quota-deficit indicator for an inadmissible workload.

    Kueue reports quota shortfalls through ``admission_checks`` entries of
    type ``QuotaCheck`` / ``Capacity``; the staging HUD overlays this reason
    on the pallet under cold-blue standby lighting (SPEC-09 §5.3).
    """
    if getattr(workload, "is_admitted", False):
        return None
    for check in list(getattr(workload, "admission_checks", []) or []):
        if not isinstance(check, dict):
            continue
        ctype = str(check.get("type", "")).lower()
        status = str(check.get("status", "")).lower()
        if status in ("false", "failed", "inadmissible") and "quota" in ctype:
            return str(check.get("reason") or "QuotaExceeded")
    for check in list(getattr(workload, "admission_checks", []) or []):
        if isinstance(check, dict) and str(check.get("status", "")).lower() in ("false", "failed"):
            return str(check.get("reason") or check.get("type") or "Inadmissible")
    if str(getattr(workload, "phase", "")) == "Inadmissible" and not getattr(workload, "is_admitted", False):
        return "QuotaExceeded"
    return None


def kueue_hud_summary(workload: object) -> Dict[str, object]:
    """Holographic HUD badge payload for a cargo pallet (SPEC-09 §5.2).

    Carries the Workload name, LocalQueue, constituent pod count
    (``X/Y Pods``), and required quota (vCPU / RAM GiB / GPUs) plus the
    quota-deficit indicator when the workload is queued / inadmissible.
    """
    pod_count = len(list(getattr(workload, "pod_uids", []) or []))
    deficit = quota_deficit_reason(workload)
    return {
        "workload_name": str(getattr(workload, "workload_name", "")),
        "local_queue": str(getattr(workload, "local_queue", "")),
        "cluster_queue": str(getattr(workload, "cluster_queue", "")),
        "pod_count": pod_count,
        "pod_count_label": f"{pod_count}/{pod_count} Pods",
        "cpu": float(getattr(workload, "total_cpu_requested", 0.0)),
        "memory_gib": float(getattr(workload, "total_memory_gib_requested", 0.0)),
        "gpus": int(getattr(workload, "total_gpu_requested", 0)),
        "phase": str(getattr(workload, "phase", "Admissible")),
        "is_admitted": bool(getattr(workload, "is_admitted", False)),
        "quota_deficit": deficit,
    }


# ---------------------------------------------------------------------------
# SPEC-09 §3.2 / §3.3: VPA morph & HPA lateral dynamics math
# ---------------------------------------------------------------------------

# Supervisor Floor (kube-scheduler / controller-manager tray) elevation from
# which HPA scale-out dispatch pulses are fired down the central riser.
SUPERVISOR_FLOOR_Y = ELEVATION_TIERS["supervisor"]  # Y = +4.5
CENTRAL_RISER_X = 0.0
CENTRAL_RISER_Z = 0.0
# Node deck chassis-tray intake port: pods materialize at the tray's outer
# edge and slide laterally into their designated slot (SPEC-09 §3.3.2).
DECK_INTAKE_OFFSET_X = 2.6
# Canonical tween durations consumed by the Three.js animation pipelines.
VPA_MORPH_DURATION_MS = 1200
HPA_DISPATCH_PULSE_MS = 700
HPA_LATERAL_SLIDE_MS = 900

# Kubernetes memory suffix multipliers normalized to GiB.
_MEMORY_SUFFIX_GIB: Dict[str, float] = {
    "Ki": 1.0 / (1024.0 ** 2),
    "Mi": 1.0 / 1024.0,
    "Gi": 1.0,
    "Ti": 1024.0,
    "K": 1000.0 / (1024.0 ** 3),
    "M": 1e6 / (1024.0 ** 3),
    "G": 1e9 / (1024.0 ** 3),
    "T": 1e12 / (1024.0 ** 3),
}


def parse_resource_quantity(
    quantity: Optional[object], kind: str = "cpu"
) -> Optional[float]:
    """Parse a Kubernetes resource quantity into a comparable float.

    ``kind='cpu'``   -> cores ("500m" -> 0.5, "2" -> 2.0)
    ``kind='memory'``-> GiB   ("512Mi" -> 0.5, "4Gi" -> 4.0, bare "4" -> 4.0)

    Returns ``None`` for absent or unparseable values so callers can treat
    missing VPA recommendation fields as "no change" instead of zero.
    """
    if quantity is None:
        return None
    text = str(quantity).strip()
    if not text:
        return None
    if kind == "cpu":
        if text.endswith("m"):
            try:
                return float(text[:-1]) / 1000.0
            except ValueError:
                return None
        try:
            return float(text)
        except ValueError:
            return None
    # memory -> GiB
    for suffix in sorted(_MEMORY_SUFFIX_GIB, key=len, reverse=True):
        if text.endswith(suffix):
            try:
                return float(text[: -len(suffix)]) * _MEMORY_SUFFIX_GIB[suffix]
            except ValueError:
                return None
    try:
        return float(text)  # bare number is interpreted as GiB
    except ValueError:
        return None


def vpa_morph_target(node: NodeComponent) -> Optional[Tuple[float, float]]:
    """Resolve the VPA in-place morph target (cpu_cores, memory_gib).

    Returns ``None`` when the pod has no VPA, the recommendation is absent,
    or the recommended dimensions equal the current requests (no ghost hull
    and no morph needed — SPEC-09 §3.2.1).
    """
    status = getattr(node, "autoscaling", None)
    if status is None or not status.has_vpa:
        return None
    cur_cpu, cur_mem = extract_pod_requests(node.metrics or {})
    tgt_cpu = parse_resource_quantity(status.vpa_target_cpu, "cpu")
    tgt_mem = parse_resource_quantity(status.vpa_target_memory, "memory")
    if tgt_cpu is None and tgt_mem is None:
        return None
    new_cpu = cur_cpu if tgt_cpu is None else tgt_cpu
    new_mem = cur_mem if tgt_mem is None else tgt_mem
    if math.isclose(new_cpu, cur_cpu, rel_tol=1e-6, abs_tol=1e-9) and math.isclose(
        new_mem, cur_mem, rel_tol=1e-6, abs_tol=1e-9
    ):
        return None
    return (new_cpu, new_mem)


def vpa_morph_dimensions(node: NodeComponent) -> Optional[Dict[str, float]]:
    """Current vs target capsule dimensions for a VPA-managed pod.

    Returns ``{current_height, current_radius, target_height, target_radius}``
    (the tween endpoints the Three.js geometry lerp consumes), or ``None``
    when no morph is pending.
    """
    target = vpa_morph_target(node)
    if target is None:
        return None
    cur_cpu, cur_mem = extract_pod_requests(node.metrics or {})
    cur_h, cur_r = calculate_pod_dimensions(cur_cpu, cur_mem)
    tgt_h, tgt_r = calculate_pod_dimensions(target[0], target[1])
    return {
        "current_height": cur_h,
        "current_radius": cur_r,
        "target_height": tgt_h,
        "target_radius": tgt_r,
    }


def hpa_scale_out_delta(current_replicas: int, desired_replicas: int) -> int:
    """Number of lateral replicas a scale-out event must spawn (SPEC-09 §3.3)."""
    try:
        cur = int(current_replicas)
        des = int(desired_replicas)
    except (TypeError, ValueError):
        return 0
    return max(0, des - cur)


def hpa_lateral_path(
    chassis_x: float, slot_offset_x: float, z: float = POD_Z_FRONT
) -> Dict[str, Tuple[float, float, float]]:
    """Conveyor endpoints for an HPA replica entering a node chassis tray.

    ``intake`` is the tray edge port (chassis_x + DECK_INTAKE_OFFSET_X) where
    the new pod materializes; ``slot`` is its designated lateral slot.
    """
    return {
        "intake": (round(chassis_x + DECK_INTAKE_OFFSET_X, 3), POD_Y, round(z, 3)),
        "slot": (round(chassis_x + slot_offset_x, 3), POD_Y, round(z, 3)),
    }


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


def apply_spatial_layout(
    nodes: List[NodeComponent],
    kueue_workloads: Optional[List[KueueWorkloadStatus]] = None,
) -> List[NodeComponent]:
    """Calculate and assign (X, Y, Z) spatial positions and asset_type to all nodes.

    SPEC-09 §5.2 / ADR-03 (TASK-CV-1004): when ``kueue_workloads`` is
    supplied, every pod that is a constituent of a Kueue ``Workload`` CRD is
    grouped into its cargo containment pallet — structured grid slots inside
    the freight bounding volume on the staging-track rail — before the
    generic pending-pod hover routing runs. Unaffiliated pending pods keep
    the SPEC-09 §4.2 hover band behaviour.
    """
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

    # SPEC-09 §5.2 / ADR-03 (TASK-CV-1004): group Kueue Workload constituents
    # into cargo containment pallets on the staging-track rail BEFORE generic
    # categorization so gang pods never scatter onto the hover band or deck.
    # Admitted workloads have already completed their gang-deployment burst —
    # their pods land on worker-deck targets instead of staying in the frame.
    pallet_pod_ids: set = set()
    if kueue_workloads:
        by_id = {n.id: n for n in nodes}
        ordered = sorted(kueue_workloads, key=lambda w: str(getattr(w, "workload_name", "")))
        for slot_index, workload in enumerate(ordered):
            member_uids = [str(u) for u in (getattr(workload, "pod_uids", []) or [])]
            members = [by_id[u] for u in member_uids if u in by_id]
            if not members:
                continue
            workload_uid = str(getattr(workload, "workload_uid", "")) or None
            if getattr(workload, "is_admitted", False):
                targets = gang_deployment_targets(len(members))
                for pod, (x, y, z) in zip(members, targets):
                    geometry = (
                        pod.pod_geometry
                        if pod.pod_geometry is not None
                        else assign_pod_geometry(pod)
                    )
                    pod.spatial.x = x
                    pod.spatial.y = y
                    pod.spatial.z = z
                    geometry.is_pending = False
                    geometry.staging_track_x = None
                    geometry.kueue_workload = workload_uid
            else:
                pack_kueue_workload(workload, members, kueue_pallet_anchor(slot_index))
            pallet_pod_ids.update(m.id for m in members)

    # Categorize nodes
    for n in nodes:
        # SPEC-09 / ADR-03: palletized gang pods already hold their slots.
        if n.id in pallet_pod_ids:
            continue
        name_lower = n.name.lower()
        kind_lower = n.kind.lower()

        # SPEC-09 §4.2 / ADR-02 (TASK-CV-1003): a PodScheduled=False pod is a
        # pending pod first and a framework member second — divert it before
        # name-based framework/deck categorization so it lands on the staging
        # yard hover band instead of the tower interior.
        n_metrics = n.metrics or {}
        n_pending = bool(n_metrics.get("pending", False)) or n_metrics.get("scheduled", True) is False
        if n_pending and kind_lower != "node" and not _is_daemonset(n):
            workload_pods.append(n)
            continue

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
    staged_pending_count = 0

    for i, pod in enumerate(workload_pods):
        chassis_idx = i % N
        slot_count = pod_slots_per_chassis[chassis_idx]

        # SPEC-09 §4.2 / ADR-02 (TASK-CV-1003): pods with PodScheduled=False
        # never reach the worker deck — they hover in the exterior staging
        # yard at Y = 1.0 awaiting admission / Karpenter provisioning.
        geometry = assign_pod_geometry(pod)
        if geometry.is_pending:
            stage_pending_pod(pod, staged_pending_count)
            staged_pending_count += 1
            continue
        
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
            
        # SPEC-09: proportional capsule dimensions from resource requests
        assign_pod_geometry(pod)

        pod_slots_per_chassis[chassis_idx] += 1

    # SPEC-09: any pod-like component that bypassed the worker-deck pod loop
    # (e.g. framework-layer Pods) still receives proportional dimensions,
    # and pending ones are routed to the exterior staging yard (ADR-02).
    for n in nodes:
        if n.pod_geometry is None and (n.layer == "workload" or n.kind.lower() == "pod"):
            swept = assign_pod_geometry(n)
            if swept.is_pending:
                stage_pending_pod(n, staged_pending_count)
                staged_pending_count += 1

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
