# SPEC-08: Subterranean Strata — Hardware Shapes, Karpenter Compute Classes & Managed Cloud Vaults (GCP KCC & kro)

**Status:** Proposed  
**Author:** Christopher Robin (Lead Architect) & 🦉 Owl (Architectural Synthesizer)  
**Date:** 2026-10-03  
**Target:** `cluster-vis`  
**Extends:** `specs/01-architectural-skyscraper-topology.md`, `specs/02-layered-rectangular-architecture.md`, `specs/03-horizontal-node-peers-and-diff-engine.md`, `specs/07-portable-helm-packaging-and-latency-topology.md`  
**Companion:** `specs/09-pod-autoscaling-morphing-and-kueue-staging.md`  

---

## 1. Executive Summary & Design Vision

ClusterVis has represented Kubernetes as a stylized architectural skyscraper: clients float along the distant horizon, the control plane and API aggregation sit in the penthouse executive suites ($Y > +4.5$), and worker nodes house workloads along the ground deck ($Y = +0.5$).

In real production cloud environments, a Kubernetes cluster does not terminate at the node operating system. Workloads depend deeply on:
1. **Underlying physical/virtual machine shapes:** Heterogeneous hardware profiles managed by Karpenter or GKE NodePools (high-memory, compute-optimized, GPU/TPU accelerator trays, Spot vs. On-Demand lifecycles).
2. **Declarative managed cloud infrastructure:** Managed services provisioned declaratively via **Google Cloud Config Connector (KCC)** or **Kube Resource Orchestrator (kro)** (Cloud SQL, Spanner, Cloud Storage buckets, Pub/Sub topics, Memorystore Redis).
3. **Deep transit & WAN egress:** NAT gateways, interconnects, and third-party SaaS APIs.

SPEC-08 extends the highrise building metaphor **downward into subterranean foundation levels ($Y \le 0.0$)**, visualizing infrastructure as the building's structural bedrock, mechanical plant, and utility vaults:
* **Ground Datum ($Y = 0.0$):** A switchable translucent smoked-glass datum separating above-ground application execution from subterranean infrastructure.
* **Sub-Level B1 ($Y = -2.5$) — Compute Chassis & Machine Shapes:** Node slabs dimensioned proportionally to vCPU and RAM, with modular accelerator power bays (GPUs/TPUs) and distinct Spot vs. On-Demand materials.
* **Sub-Level B2 ($Y = -6.0$) — Managed Cloud Service Vaults:** `kro` composite resource manifolds routing into heavy industrial vaults representing KCC-managed cloud resources.
* **Sub-Level B3 ($Y = -10.0$) — Bedrock & WAN Egress:** Deep transit boreholes routing traffic through egress gateways into external SaaS/internet bedrock.
* **Cloud-Agnostic Abstraction (GCP First, AWS Ready):** Implemented using a vendor-neutral intermediate data model that seamlessly maps GCP (KCC `*.cnrm.cloud.google.com`) today, while maintaining 100% structural drop-in parity for AWS (ACK `*.services.k8s.aws` and `EC2NodeClass`) in future releases.
* **Live Latency & Reachability Mechanics:** Vertical plunge conduits carrying animated pulses whose velocity and color map to measured network RTT, with real-time visual degradation (pipe fracturing, particle leakage, and warning strobes) when dependencies degrade or become unreachable.

---

## 2. Subterranean Spatial Topology & Elevation Matrix

```
  Y = +0.5  ═════════════════════ [ WORKER FLOOR / DECK ] ═════════════════════
                            Workload Pods & Container Runtimes
  ─────────────────────────────────────────────────────────────────────────────  ◄── Surface Datum (Y = 0.0)
  Y = -2.5  ┌────────────────────────────────────────────────────────────────┐
            │  SUB-LEVEL B1: COMPUTE CHASSIS & MACHINE SHAPES                │
            │  Karpenter / GKE NodePools & Custom Compute Classes             │
            │  - Footprint (X × Z) scaled to vCPU cores × RAM GiB            │
            │  - Accelerator Modular Slabs (NVIDIA L4/H100, TPU v5e/v6)      │
            │  - Material: Solid Slate (On-Demand) vs Hazard-Striped (Spot)  │
            └───────────────────────────────┬────────────────────────────────┘
                                            │ (Vertical Plunge Conduits)
  Y = -6.0  ┌───────────────────────────────▼────────────────────────────────┐
            │  SUB-LEVEL B2: MANAGED CLOUD SERVICE VAULTS                    │
            │  [kro ResourceGraphDefinition Manifold Hub]                    │
            │     ├──> KCC: Google Cloud SQL (Pressurized DB Cylinders)      │
            │     ├──> KCC: Google Cloud Spanner (Multi-cell Vault Slabs)    │
            │     ├──> KCC: Google Cloud Storage (Layered Cryptographic Safe)│
            │     └──> KCC: Google Pub/Sub & Redis (Looping Raceways)        │
            │     └──> [Future Drop-in: AWS ACK RDS, S3, DynamoDB]           │
            └───────────────────────────────┬────────────────────────────────┘
                                            │ (Deep Borehole Transit Pipes)
  Y = -10.0 ┌───────────────────────────────▼────────────────────────────────┐
            │  SUB-LEVEL B3: BEDROCK & WAN EGRESS                            │
            │  NAT Gateways, Cloudflare Interconnect, External SaaS Bedrock  │
            └────────────────────────────────────────────────────────────────┘
```

### 2.1 Elevation Constants (`src/ingestion/layout.py`)

```python
ELEVATION_TIERS: Dict[str, float] = {
    # Existing Above-Ground Tiers
    "client": 12.0,
    "aggregation": 9.5,
    "apiserver": 7.0,
    "vault": 5.5,
    "supervisor": 4.5,
    "framework": 2.5,
    "worker_deck": 0.5,
    
    # Subterranean Strata Tiers (SPEC-08)
    "surface_datum": 0.0,       # Ground reference plane / cutaway glass
    "compute_chassis": -2.5,    # Sub-Level B1: Karpenter / GKE Machine Shapes
    "kro_manifold": -4.8,       # Sub-Level B2 Upper: kro composition routing hub
    "cloud_vault": -6.5,        # Sub-Level B2 Lower: KCC / ACK managed services
    "bedrock_egress": -10.5,    # Sub-Level B3: External SaaS, WAN, NAT gateways
}
```

---

## 3. Sub-Level B1: Machine Shapes & Compute Classes

### 3.1 Proportional Chassis Dimensioning
Worker nodes in vanilla ClusterVis were uniform bounding boxes. In SPEC-08, each node chassis reflects its underlying hardware shape:

$$\text{Chassis Width } (X) = \text{clamp}\left(3.2 + 0.35 \times \sqrt{\text{vCPU}}, \ 3.2, \ 8.0\right)$$
$$\text{Chassis Depth } (Z) = \text{clamp}\left(2.4 + 0.30 \times \sqrt{\text{RAM GiB}}, \ 2.4, \ 7.5\right)$$
$$\text{Chassis Height } (Y) = 0.6$$

* **Compute-Optimized (e.g. `c3-highcpu-16`):** Elongated along $X$ axis, shallow along $Z$ axis.
* **Memory-Optimized (e.g. `m3-ultramem-32`):** Broad, deep platform foundation.
* **General Purpose (e.g. `n2-standard-8`):** Balanced rectangular pedestal.

### 3.2 Accelerator Modular Bays (GPU & TPU)
When a node reports accelerator capacity (`nvidia.com/gpu`, `google.com/tpu`):
* An auxiliary **docked power bay / heatsink manifold** is attached to the rear face ($Z_{\text{local}} = -Z/2 - 0.4$).
* The bay houses discrete illuminated cylindrical/hexagonal core meshes corresponding to the accelerator count (e.g., 4 glowing cores for a 4x NVIDIA L4 or TPU v5e pod slice).
* Accelerator activity (from DCGM/metrics) modulates core glow intensity and heat shimmer particle emitters.

### 3.3 Lifecycle Material Shaders
* **On-Demand Capacity:** Dark brushed titanium slab with bevelled gunmetal chamfers and continuous cyan power rail illumination.
* **Spot / Preemptible Capacity:** Translucent smoked-acrylic chassis with diagonal yellow-and-black hazard warning borders along the deck perimeter. When a Karpenter preemption notice or GKE termination notice arrives, the hazard borders pulse in rapid strobe red.

---

## 4. Sub-Level B2: kro Manifolds & KCC Managed Cloud Vaults

### 4.1 `kro` (Kube Resource Orchestrator) Composition Manifold
`kro` enables defining high-level composite resources (e.g., `ApplicationService`) that orchestrate both in-cluster workloads and external managed services via a directed acyclic graph (DAG).
* In the 3D scene, a `kro` instance renders as a **subterranean hydraulic manifold hub** ($Y = -4.8$).
* Conduits drop vertically from the consuming Pods on the Worker Deck into the `kro` manifold.
* The manifold fans out into branch conduits feeding the respective KCC managed cloud vaults on Sub-Level B2.

### 4.2 KCC Managed Cloud Vault Visual Geometries
Each Google Cloud Config Connector resource kind is rendered with a distinct industrial vault geometry:

| KCC Resource Kind | Visual Representation | Visual Aesthetics |
| :--- | :--- | :--- |
| `SQLInstance` (`sql.cnrm.cloud.google.com`) | Pressurized Database Cylinders | Dual vertical cylindrical vessels with reinforced steel bands, liquid level sight-glass, and amber status rings. |
| `SpannerInstance` (`spanner.cnrm.cloud.google.com`) | Multi-Cell Monolith Vault | Monolithic block divided into synchronized vibrating multi-region cells with sapphire blue energy conduits. |
| `StorageBucket` (`storage.cnrm.cloud.google.com`) | Cryptographic Vault Safe | Heavy cube with interlocking circular vault door geometry and sliding data-block indicators. |
| `PubSubTopic` (`pubsub.cnrm.cloud.google.com`) | High-Velocity Torus Raceway | Continuous circular tubular raceway with orbiting high-speed particle streams representing active messages. |
| `RedisInstance` (`redis.cnrm.cloud.google.com`) | Lattice Crystal Slab | Low hexagonal crystalline platform glowing with low-latency ruby red luminescence. |

---

## 5. Vendor-Agnostic Data Model (GCP-First, AWS-Ready)

To ensure GCP implementation is completely compatible with future AWS support, the ingestion layer decouples the raw CRDs from the visual representation via an abstract data model in `src/ingestion/models.py`.

```python
from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

class CloudProvider(str, Enum):
    GCP = "gcp"
    AWS = "aws"
    AZURE = "azure"
    GENERIC = "generic"

class ManagedServiceCategory(str, Enum):
    DATABASE_RELATIONAL = "database_relational"     # CloudSQL, Spanner <-> RDS, Aurora
    DATABASE_NOSQL = "database_nosql"               # Firestore, Bigtable <-> DynamoDB
    OBJECT_STORAGE = "object_storage"               # GCS <-> S3
    MESSAGING_EVENTING = "messaging_eventing"       # Pub/Sub <-> SQS, SNS, Kinesis
    CACHE_IN_MEMORY = "cache_in_memory"             # Memorystore <-> ElastiCache
    SECURITY_SECRET = "security_secret"             # Secret Manager <-> SecretsManager
    NETWORKING_GATEWAY = "networking_gateway"       # Cloud NAT, Interconnect <-> NAT GW

class RemoteServiceResource(BaseModel):
    id: str                                         # Unique resource ID or GCP URI / AWS ARN
    provider: CloudProvider = CloudProvider.GCP
    category: ManagedServiceCategory
    cr_group: str                                   # "sql.cnrm.cloud.google.com" or "rds.services.k8s.aws"
    cr_kind: str                                    # "SQLInstance" or "DBInstance"
    name: str                                       # K8s metadata.name
    namespace: str                                  # K8s metadata.namespace
    display_name: str                               # Resource label/name
    status_phase: str                               # "Ready", "Reconciling", "Degraded", "Failed"
    endpoint: Optional[str] = None                  # Hostname or IP
    vpc_network: Optional[str] = None
    managed_by: str = "kcc"                         # "kcc", "kro", "ack", "crossplane"
    kro_parent_id: Optional[str] = None             # kro composition ID if managed via kro

class MachineShape(BaseModel):
    node_name: str
    provider: CloudProvider = CloudProvider.GCP
    instance_type: str                              # "c3-standard-8" or "g5.xlarge"
    compute_class: Optional[str] = None             # GKE Compute Class / Karpenter NodePool
    vcpus: int
    memory_gib: float
    capacity_type: str = "on-demand"                # "spot" or "on-demand"
    zone: str
    accelerator_type: Optional[str] = None          # "nvidia-l4", "tpu-v5e", "none"
    accelerator_count: int = 0
```

---

## 6. Latency & Reachability Telemetry Mechanics

### 6.1 Telemetry Gathering Pipeline
Dependencies are monitored via two telemetry pathways:
1. **Passive Telemetry (Cilium Hubble eBPF / Envoy APM):**
   * Inspects external TCP flows originating from in-cluster Pod IPs toward remote service endpoints (Cloud SQL IPs, GCS endpoints, Pub/Sub endpoints).
   * Measures TCP handshake RTT, round-trip duration, and TCP retransmits.
2. **Active Telemetry (`clustervis-probe` DaemonSet):**
   * When passive eBPF telemetry is unavailable, the unprivileged `clustervis-probe` agent (established in SPEC-07) performs periodic non-intrusive TCP connect and TLS handshake probes against discovered endpoints.
   * Emits $p50$, $p95$, and reachability status flags (`reachable`, `degraded`, `unreachable`).

### 6.2 Visual Shader Encodings for Conduits

```
  Worker Pod (Y = +0.5)
         │
         │  (Vertical Subterranean Plunge Conduit)
         ▼
  KCC Cloud SQL Vault (Y = -6.5)
```

1. **Latency Spectrum & Flow Rate:**
   * **$< 3\text{ms}$ (Intra-Zone / Colocated):** Rapid, bright electric-cyan particle pulses moving at high frequency ($v = 4.0$, $\lambda = 480\text{nm}$).
   * **$3 - 20\text{ms}$ (Cross-Zone Cloud Service):** Steady warm amber flow ($v = 2.0$, $\lambda = 580\text{nm}$).
   * **$> 60\text{ms}$ (Cross-Region / Heavy Latency):** Sluggish, viscous deep magenta pulses ($v = 0.5$, $\lambda = 650\text{nm}$).
2. **Reachability & Degradation States:**
   * **Healthy (`Ready=True`):** Smooth, clean double-walled glass tube with fluid optical core.
   * **Degraded / High Jitter / Packet Loss:** Pipe geometry jitters slightly; procedural electrical arcs and sparks leak from coupling joints along the pipe.
   * **Unreachable / Connection Refused / Timeout:** The conduit breaks into a fractured translucent conduit with zero particle flow; a pulsing red hazard strobe cone illuminates the disconnected endpoint vault.

---

## 7. Viewport Controls & Interaction

1. **X-Ray Ground Cutaway Toggle (`KeyG` / HUD Button):**
   * Smoothly animates the opacity of the ground plane at $Y = 0.0$ from $1.0$ (solid ground terrace) down to $0.1$ (smoked transparent glass grid), revealing the glowing subterranean foundations and vaults beneath the building.
2. **Subterranean Camera Preset (`KeyB`):**
   * Re-anchors camera orbit to center on $Y = -5.0$, with a slight upward tilt framing the building's massive foundational root system anchoring into the bedrock.
3. **Blast Radius Highlighting:**
   * Clicking any KCC managed vault (e.g. Cloud SQL) immediately highlights all upward vertical plunge conduits feeding consuming pods on the upper decks, darkening unrelated cluster components to instantly spotlight downstream service dependencies.

---

## 8. Implementation Steps & Acceptance Criteria

1. **Schema & Models:**
   * Implement `RemoteServiceResource`, `MachineShape`, and subterranean edge schemas in `src/ingestion/models.py`.
2. **GCP Informers:**
   * Add watch informers for `*.cnrm.cloud.google.com` (KCC) and `kro.run/v1alpha1` in `src/operator/controller.py`.
   * Add Karpenter `NodePool`/`NodeClaim` and GKE Node metadata extraction.
3. **Subterranean Layout Engine:**
   * Extend `src/ingestion/layout.py` with negative elevation tiers and proportional node chassis dimensioning.
4. **Three.js WebGL Rendering:**
   * Author procedural vault meshes (cylinder DBs, storage safes, raceways) in `src/scene/`.
   * Implement dynamic Bezier plunge conduits with latency shader and reachability particle effects.
5. **Testing & Validation:**
   * Validate against GCP test manifests (KCC CloudSQL, GCS, PubSub + kro Application RGD).
   * Verify AWS ACK definitions can map directly to the same data structures without schema modifications.