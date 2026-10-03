# SPEC-09: Workload Lifecycle — Proportional Pod Sizing, VPA/HPA Morphing & The Pre-Admission Staging Yard (Kueue Gang Scheduling)

**Status:** Proposed  
**Author:** Christopher Robin (Lead Architect) & 🦉 Owl (Architectural Synthesizer)  
**Date:** 2026-10-03  
**Target:** `cluster-vis`  
**Extends:** `specs/01-architectural-skyscraper-topology.md`, `specs/02-layered-rectangular-architecture.md`, `specs/03-horizontal-node-peers-and-diff-engine.md`  
**Companion:** `specs/08-subterranean-dependencies-and-compute-classes.md`  

---

## 1. Executive Summary & Design Vision

In SPEC-01 through SPEC-03, Kubernetes pods were rendered as uniform capsule meshes slotted into fixed grid coordinates atop worker node chassis. In production clusters, however, pods vary widely in resource commitments, scale dynamically both vertically and horizontally, and spend critical phases of their lifecycle outside the running node plane:

1. **Resource Heterogeneity:** A microscopic sidecar proxy (10m CPU, 32MiB RAM) looks visually identical to a massive distributed inference container (8 cores, 32GiB RAM).
2. **Dynamic Autoscaling Dynamics:**
   * **Vertical Pod Autoscaling (VPA):** Containers change resource sizes in-place. Static visualization cannot convey resource starvation, VPA recommendations, or in-place resource mutation.
   * **Horizontal Pod Autoscaling (HPA):** Pod replicas scale horizontally, redistributing load across nodes.
3. **Pre-Admission & Scheduling Bottlenecks:**
   * Pods pending due to resource exhaustion, Karpenter node provisioning delays, or quota constraints have historically floated ambiguously or disappeared entirely from topology graphs.
4. **Batch & AI Gang Scheduling (Kueue):**
   * High-performance workloads (distributed PyTorch, Ray clusters, MPI jobs) must be admitted and scheduled as an atomic **all-or-nothing unit** (gang scheduling). Rendering 32 pending pods as isolated dots obscures their unified workload lifecycle.

SPEC-09 introduces **proportional pod geometry**, **real-time autoscaling morphing**, and the **Pre-Admission Staging Yard**:
* **Proportional Capsule Geometry:** Pod dimensions map directly to CPU requests (height $Y$) and Memory requests (footprint $X \times Z$).
* **VPA In-Place Morphing:** Visualizes vertical expansion via animated geometry tweens, featuring holographic ghost bounding frames previewing VPA target recommendations.
* **HPA Lateral Spawning:** Visualizes replica expansion through lateral conveyor animations across node trays, linked by supervisory controller pulses.
* **The External Staging Yard ($X < -12.0$):** An exterior freight tarmac outside the skyscraper where pending pods await scheduling. When Karpenter provisions new compute, a vertical tractor beam projects from the tarmac down to holographic ghost nodes on Sub-Level B1.
* **Kueue Gang Cargo Units:** Unadmitted batch workloads are secured inside illuminated **Kueue Cargo Containment Pallets**. When Kueue admits the workload, a high-speed magnetic rail crane guides the unit into the tower, deploying all constituent pods simultaneously onto the worker deck.

---

## 2. Spatial Floorplan: The Staging Yard & The Skyscraper Interior

```
  ╔═══════════════════════════════════════╦═════════════════════════════════════════════════════╗
  ║ EXTERIOR STAGING YARD (X < -12.0)     ║ TOWER INTERIOR (X: -10.0 to +10.0)                  ║
  ║                                       ║                                                     ║
  ║  [Kueue Freight Terminal]             ║  [Worker Deck: Node Chassis c3-standard-8]          ║
  ║  LocalQueue: "batch-ai"               ║                                                     ║
  ║  ┌──────────────────────────────────┐ ║   [VPA Pod]              [HPA Replicas]             ║
  ║  │ Kueue Cargo Pallet (RayCluster)  │ ║    ┌────────┐             ┌──┐  ┌──┐  ┌──┐          ║
  ║  │  ┌────┐ ┌────┐ ┌────┐ ┌────┐     │ ║    │ Expands│ (Height)    │  │  │  │  │  │          ║
  ║  │  │Pod1│ │Pod2│ │Pod3│ │Pod4│     │ ║    │ Upward │             └──┘  └──┘  └──┘          ║
  ║  │  └────┘ └────┘ └────┘ └────┘     │ ║    └────────┘           (Lateral Expansion Along X) ║
  ║  └──────────────────┬───────────────┘ ║                                                     ║
  ║                     │                 ║                                                     ║
  ║  [Raw Pending Pods] │                 ║                                                     ║
  ║      (·)   (·)      │ (Mag-Rail Crane)║                                                     ║
  ║       │     │       └────────────────►║ (Gang Admission Deploy)                             ║
  ╚═══════╪═════╪═════════════════════════╩═════════════════════════════════════════════════════╝
  ────────┼─────┼──────────────────────────────────────────────────────────────────────────────── ◄── Ground Datum (Y = 0.0)
          │     │ (Karpenter Provisioning Tractor Beam)
          ▼     ▼
  ┌───────────────────────────────────────┐
  │ SUB-LEVEL B1: COMPUTE BASEMENT        │
  │ [ Holographic Ghost Node Chassis ]    │
  │ Provisioning in progress via Karpenter│
  └───────────────────────────────────────┘
```

---

## 3. Proportional Pod Geometry & Autoscaling Mechanics

### 3.1 Mathematical Scaling Formulae
Pods are modeled as rounded pill capsules (`CapsuleGeometry` in Three.js). Their dimensions scale smoothly with Kubernetes resource requests:

$$\text{Pod Height } (Y) = \text{clamp}\left(0.40 + 0.35 \times \sqrt{\text{vCPU Request}}, \ 0.40, \ 2.60\right)$$
$$\text{Pod Radius } (R) = \text{clamp}\left(0.20 + 0.12 \times \log_2(\max(1, \ \text{Memory GiB Request})), \ 0.20, \ 0.90\right)$$

* **Micro-Containers (Sidecars / Exporters):** Slender, compact capsules ($H \approx 0.45, R \approx 0.20$).
* **Heavy Compute Workloads (Compilers / ML Workers):** Tall, commanding cylindrical towers ($H \approx 1.80, R \approx 0.50$).
* **In-Memory Engines (Redis / Cache):** Broad, squat canisters ($H \approx 0.80, R \approx 0.85$).

```
   Micro-Sidecar          Heavy ML Worker          In-Memory Cache
     ┌──┐                     ┌──────┐                ┌────────────┐
     │  │ H=0.45              │      │                │            │ H=0.80
     └──┘ R=0.20              │      │ H=1.80         └────────────┘ R=0.85
                              │      │ R=0.50
                              └──────┘
```

### 3.2 Vertical Pod Autoscaling (VPA) Morphing Pipeline
1. **Recommendation Ghost Hull:**
   * When a VPA object (`autoscaling.k8s.io/v1`) emits a target recommendation differing from the current pod's request, a **holographic wireframe hull** renders around the pod, projecting the future target dimension.
2. **In-Place Resource Morph:**
   * When an in-place resource update commits (Kubernetes in-place resize without restart), the capsule mesh smoothly interpolates (`lerp` over 1200ms) to the target dimensions using a custom vertex shader expansion or Three.js scale animation.
   * Energy emission ripples vertically from the capsule base to its crown during the expansion.

### 3.3 Horizontal Pod Autoscaling (HPA) Lateral Dynamics
1. **Scale-Out Trigger:**
   * When HPA increments replica count (`spec.replicas`), the parent controller on the Supervisor Floor ($Y = +4.5$) fires a golden dispatch pulse down the central riser pipe.
2. **Lateral Conveyor Animation:**
   * The new pod instance materializes at the node deck intake port and slides smoothly along the node chassis tray into its designated lateral slot.
   * If the replica is placed on a newly Karpenter-provisioned node, it enters via the Pre-Admission Staging Yard.

---

## 4. The Pre-Admission Staging Yard ($X < -12.0$)

### 4.1 Yard Spatial Layout
The staging yard sits to the left of the main highrise tower:
* **Tarmac Plane ($Y = 0.2, X \in [-24.0, -12.0], Z \in [-8.0, +8.0]$):** A reinforced industrial tarmac with directional runway lighting, taxiway markers, and cargo rail tracks leading directly into the building's intake bays.

### 4.2 Raw Pending Pods & Karpenter Provisioning Beams
* Pods with `PodScheduled=False` hover in low suspension above the tarmac ($Y = 1.0$).
* **Karpenter Correlation:**
  * When Karpenter creates a `NodeClaim` to satisfy pending pods, a **holographic wireframe "Ghost Node"** materializes in the corresponding empty slot on Sub-Level B1 ($Y = -2.5$).
  * A luminous amber tractor beam projects from the pending pods down into the ghost node, visually establishing why the pods are waiting and confirming that compute hardware is actively being provisioned.
  * Once the node joins the cluster (`NodeReady=True`), the ghost chassis solidifies into a physical chassis, and the pending pods are lowered into their slots.

---

## 5. Kueue Gang & Cohort Scheduling Integration

### 5.1 Kueue Resource Informers (`kueue.x-k8s.io/v1beta1`)
The operator watches three core Kueue CRDs:
1. `ClusterQueue`: Defines resource quotas and borrowing cohorts across the cluster.
2. `LocalQueue`: Namespace-scoped entry point routing workloads to a `ClusterQueue`.
3. `Workload`: The atomic scheduling unit wrapping batch pods (Jobs, RayClusters, JobSets).

### 5.2 The Kueue Cargo Pallet (Unified Gang Unit)
Instead of rendering pending gang-scheduled pods as disparate items, ClusterVis groups them into a **Kueue Cargo Containment Frame**:
* A modular industrial transport frame encasing all pods belonging to the `Workload`.
* The frame displays holographic HUD badges showing:
  * Workload Name & `LocalQueue` label.
  * Constituent Pod Count (e.g. `16/16 Pods`).
  * Required Quota (vCPU, RAM, GPUs).

```
  ┌────────────────────────────────────────────────────────┐
  │ [KUEUE WORKLOAD FRAME: ray-finetune-job]  Queue: ml-bq │
  │  Quota: 64 vCPU | 256 GiB RAM | 8x NVIDIA-L4           │
  ├──────────────┬──────────────┬──────────────┬───────────┤
  │ [Pod 0 (Head)│ [Pod 1 (Wkr)]│ [Pod 2 (Wkr)]│ [Pod 3]   │
  ├──────────────┼──────────────┼──────────────┼───────────┤
  │ [Pod 4]      │ [Pod 5]      │ [Pod 6]      │ [Pod 7]   │
  └──────────────┴──────────────┴──────────────┴───────────┘
```

### 5.3 Workload Lifecycle States & Transition Animations

| Kueue Phase | Visual State | Lighting / Animation |
| :--- | :--- | :--- |
| **Queued / Inadmissible** | Cargo Pallet parked on staging track rail | Cold blue standby lighting; static position; quota deficit indicator overlay. |
| **Quota Reserved** | Pallet engages magnetic intake rail | Amber warning beacons spin; overhead gantry cranes lock onto the cargo frame. |
| **Admitted (`Admitted=True`)** | High-Speed Mag-Rail Transit | Pallet lights turn vivid green; gantry crane accelerates the frame into the building intake bay. |
| **Gang Deployment** | Frame Disassembly on Worker Deck | The cargo frame unlatches and dissolves; all constituent pods are deployed simultaneously to their target nodes in a single coordinated burst. |

---

## 6. Ingestion Data Models (`src/ingestion/models.py`)

```python
from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

class AutoscalingStatus(BaseModel):
    has_vpa: bool = False
    vpa_target_cpu: Optional[str] = None
    vpa_target_memory: Optional[str] = None
    is_resizing_in_place: bool = False
    
    has_hpa: bool = False
    current_replicas: int = 1
    desired_replicas: int = 1
    target_metric: Optional[str] = None

class KueueWorkloadStatus(BaseModel):
    workload_uid: str
    workload_name: str
    local_queue: str
    cluster_queue: str
    is_admitted: bool = False
    admission_checks: List[Dict[str, str]] = Field(default_factory=list)
    pod_uids: List[str] = Field(default_factory=list)
    total_cpu_requested: float = 0.0
    total_memory_gib_requested: float = 0.0
    total_gpu_requested: int = 0

class PodGeometrySpec(BaseModel):
    height: float = 0.6
    radius: float = 0.3
    color_tint: str = "#4FC3F7"
    is_pending: bool = False
    staging_track_x: Optional[float] = None
    karpenter_target_node_claim: Optional[str] = None
```

---

## 7. Viewport Interaction & Controls

1. **Staging Apron Focus (`KeyY` / HUD Button):**
   * Smoothly pans the camera to focus on the pre-admission staging yard at $X = -18.0$, displaying queued Kueue workloads, pending pods, and admission queue depths.
2. **Autoscaling Radar Overlay (`KeyU`):**
   * Highlights all pods currently under VPA or HPA management with pulsating golden aura rings and displays real-time CPU/memory utilization vs. recommended requests.
3. **Gang Admission Simulation Trigger (Testbed Mode):**
   * In sandbox/demo modes, allows firing simulated Kueue admission events to demonstrate cargo pallet transit and gang deployment animations.

---

## 8. Implementation Steps & Acceptance Criteria

1. **Geometry Engine:**
   * Update `src/scene/` pod generation in Three.js to construct `CapsuleGeometry` with dynamic height and radius computed from pod resource requests.
2. **Autoscaling Informers:**
   * Add informers in `src/operator/controller.py` for `autoscaling/v2` (HPA) and `autoscaling.k8s.io/v1` (VPA).
   * Emit VPA recommendation deltas over the SSE stream.
3. **Kueue Informers:**
   * Add informers for `kueue.x-k8s.io/v1beta1` (`Workload`, `LocalQueue`, `ClusterQueue`).
   * Group pending pod nodes into `KueueWorkloadStatus` containers.
4. **Staging Yard Layout:**
   * Update `src/ingestion/layout.py` to route pending and Kueue workloads to $X < -12.0$.
5. **Animation Pipelines:**
   * Author Three.js tweening controller for VPA in-place morphing.
   * Implement Kueue cargo pallet assembly and mag-rail transit animation.