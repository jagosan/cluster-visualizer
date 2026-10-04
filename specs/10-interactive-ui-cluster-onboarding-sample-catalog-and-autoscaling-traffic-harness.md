# SPEC-10: Interactive UI Cluster Onboarding, Simulated Sample Catalog & Autoscaling Traffic Simulation Harness

**Status:** Proposed  
**Author:** Christopher Robin (Lead Architect) & 🦉 Owl (Architectural Synthesizer)  
**Date:** 2026-10-04  
**Target:** `cluster-vis`  
**Extends:** `specs/00-system-architecture.md`, `specs/06-ephemeral-multi-cluster-testbed-and-live-streaming.md`, `specs/07-portable-helm-packaging-and-latency-topology.md`, `specs/08-subterranean-dependencies-and-compute-classes.md`, `specs/09-pod-autoscaling-morphing-and-kueue-staging.md`  

---

## 1. Executive Summary & Design Vision

ClusterVis has evolved from a static JSON visualizer into a multi-tiered 3D architectural engine featuring subterranean cloud vaults (SPEC-08), proportional pod capsule geometries, VPA morphing, HPA lateral replication, and the Kueue gang-scheduling staging yard (SPEC-09). However, testing and demonstrating these advanced architectural behaviors has previously required either manual JSON fixture manipulation or pre-provisioned ephemeral K3d testbeds via CLI commands.

SPEC-10 brings **interactive cluster onboarding**, a **zero-friction simulated sample catalog**, and an **in-browser traffic simulation and autoscaling test harness** directly into the ClusterVis user interface:

1. **Interactive Cluster Onboarding (`+ Add Cluster`):**
   * A persistent topbar action opening an onboarding modal supporting two distinct operational models:
     * **In-Cluster Operator Mode (Helm Deploy):** For users with cluster-admin access, generating copyable Helm install commands or executing automated deployment of the `clustervis` Helm chart (SPEC-07), backed by least-privilege RBAC, Kubernetes `TokenReview` bearer authentication, and automatic in-cluster secret scrubbing.
     * **Client-Side / Direct Agent Mode:** For read-only users or ephemeral environments without Helm deployment rights, connecting directly via browser-managed credentials in `sessionStorage` and client-side topology parsing.
2. **Instant Simulated Sample Catalog (Zero-Latency Load):**
   * A built-in catalog of pre-packaged, production-grade cluster topologies that load instantly (<100ms) without cloud credentials or running daemons:
     * **OSS Upstream Kubernetes Baseline (v1.36 vanilla):** Clean reference control plane, CoreDNS, kube-proxy, CNI, and dual containerd worker nodes.
     * **Microservices E-Commerce Application:** Google Online Boutique ("gshoe" / Hipster Shop) and AWS Retail Store sample apps with 11 microservices, Redis backing, and pre-configured HPA/VPA definitions.
     * **AI / ML Workload Cluster (Ray & KubeRay):** KubeRay operator, `RayCluster` CRD with Ray Head, CPU/GPU worker groups (with NVIDIA L4/A100 accelerator bays per SPEC-08), Kueue gang-scheduling LocalQueues, and vLLM batch distributed inference.
     * **GKE Autopilot Compute Class vs. Standard Cluster:** A benchmark comparison pair pre-wired to demonstrate compute class autoscaling differences.
3. **Autoscaling Traffic Simulation Test Harness:**
   * A dockable HUD control deck in the UI allowing operators to inject synthetic request traffic against target workloads (e.g. `frontend`, `cartservice`, `ray-worker-cpu`).
   * **Comparative Autoscaling & Scheduling Latency Demonstration:**
     * Contrasts **Google Cloud GKE Autopilot Compute Classes** (rapid pod scheduling onto pre-warmed compute slices $\tau_{\text{sched}} \approx 3 - 6\text{s}$ and in-place VPA morphing without node rescheduling $\tau_{\text{vpa}} \approx 1.2\text{s}$) against **Standard Node Pools / Karpenter Cold Provisioning** ($\tau_{\text{node}} \approx 90 - 150\text{s}$ cold VM boot delay).
     * Pods in cold-provisioning clusters back up into the **Exterior Staging Yard ($X < -12.0$, SPEC-09)**, queue lengths surge, and real-time response latency jumps from $15\text{ms} \to 650\text{ms}+$ while the Autopilot cluster absorbs the spike smoothly.

---

## 2. Cluster Onboarding Architecture & Security Model

```
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                      CLUSTERVIS UI (Browser / Vite)                         │
 │                                                                             │
 │  [+ Add Cluster Button]                                                     │
 │         │                                                                   │
 │         ▼                                                                   │
 │  ┌───────────────────────────────────────────────────────────────────────┐  │
 │  │                  CLUSTER ONBOARDING MODAL DIALOG                      │  │
 │  │  ┌─────────────────────────┬───────────────────────────────────────┐  │  │
 │  │  │ TAB 1: LIVE CLUSTER     │ TAB 2: SIMULATED SAMPLE CATALOG       │  │  │
 │  │  ├─────────────────────────┼───────────────────────────────────────┤  │  │
 │  │  │ [A] Helm Operator Mode  │  (1) OSS Vanilla K8s v1.36.4          │  │  │
 │  │  │     - Target API URL    │  (2) Online Boutique ("gshoe" Retail) │  │  │
 │  │  │     - Bearer Token Auth │  (3) Ray & KubeRay AI Cluster         │  │  │
 │  │  │     - Generate Helm Cmd │  (4) GKE Autopilot vs Standard Bench  │  │  │
 │  │  │ [B] Client-Side Connect │                                       │  │  │
 │  │  │     - Read-Only Token   │                                       │  │  │
 │  │  │     - Client-side Parse │                                       │  │  │
 │  │  └─────────────────────────┴───────────────────────────────────────┘  │  │
 └─────────┬───────────────────────────────────────────────┬───────────────────┘
           │ (Helm Deployment / SSE Stream)                │ (Instant Load <100ms)
           ▼                                               ▼
 ┌───────────────────────────────────────┐   ┌─────────────────────────────────┐
 │ LIVE TARGET KUBERNETES CLUSTER        │   │ IN-MEMORY TOPOLOGY CACHE        │
 │  Namespace: clustervis-system         │   │ (Deterministic ClusterGraphData)│
 │  ├── Operator (Deployment)            │   │                                 │
 │  ├── RBAC: Least-Privilege Read-Only  │   │ - Instant slot binding          │
 │  ├── Synthetic Probe (DaemonSet)      │   │ - Complete 3D scene hydration   │
 │  └── TokenReview Bearer Verification  │   │ - Zero cloud credentials req.   │
 └───────────────────────────────────────┘   └─────────────────────────────────┘
```

### 2.1 Onboarding Modalities

#### 1. In-Cluster Operator Mode (Helm Packaging)
* **Target User:** Cluster administrators who want full real-time topology streaming, synthetic latency probes (SPEC-07), subterranean resource mapping (SPEC-08), and live pod autoscaling informers (SPEC-09).
* **Assisted Helm Installation:**
  The modal dynamically generates copyable CLI commands tailored to the user's cluster:
  ```bash
  # Option A: Direct Helm OCI install
  helm upgrade --install clustervis oci://ghcr.io/jagosan/charts/clustervis \
    --namespace clustervis-system \
    --create-namespace \
    --set auth.type=token \
    --set service.type=LoadBalancer

  # Option B: Local Repository Checkout
  helm upgrade --install clustervis ./charts/clustervis \
    --namespace clustervis-system \
    --create-namespace \
    --set auth.type=token \
    --set service.type=NodePort \
    --set service.nodePort=30080
  ```
* **Security & Invariants:**
  * **RBAC:** Strictly read-only cluster role. Grants `get`, `list`, `watch` on `pods`, `nodes`, `services`, `endpointslices`, `horizontalpodautoscalers`, `verticalpodautoscalers`, and custom resource definitions. Explicitly **denies** access to `secrets` and `configmaps`.
  * **Secret Scrubbing:** Even within pod environment variables or annotations, all values containing `*KEY*`, `*TOKEN*`, `*PASS*`, `*AUTH*`, or `*SECRET*` are sanitized by the operator before serialization.
  * **Authentication:** Authenticated via the Kubernetes `TokenReview` API (SPEC-07 §5.1). Browser stores bearer tokens strictly in `sessionStorage` keyed to the endpoint ID; tokens are never persisted to disk, `localStorage`, or external servers.

#### 2. Client-Side / Direct Agent Mode (Zero In-Cluster Footprint)
* **Target User:** Developers or observers with read-only cluster credentials who do not possess permissions to create namespaces, CRDs, or DaemonSets in the target cluster.
* **Mechanism:**
  * The user provides the cluster API endpoint URL and a read-only bearer token (or connects via a local kubeconfig proxy, e.g. `kubectl proxy --port=8001`).
  * The browser directly fetches `/api/v1/nodes`, `/api/v1/pods`, `/api/v1/services`, and `/apis/autoscaling/v2/horizontalpodautoscalers`.
  * A client-side TypeScript extractor (`src/ingestion/client_extractor.ts`) parses the raw Kubernetes API responses directly into the normalized `ClusterGraphData` schema in the browser memory, enabling full 3D Skyscraper exploration with zero server-side installation.

#### 3. Instant Simulated Sample Catalog
* **Target User:** Users evaluating ClusterVis, running offline presentations, or performing comparative benchmarks without access to live cloud infrastructure.
* **Latency Guarantee:** Pre-compiled into static JSON manifests bundled with the client; hydrates and renders in Three.js in $< 100\text{ ms}$.

---

## 3. Simulated Sample Cluster Catalog Specifications

### 3.1 Catalog Entry 1: Vanilla Upstream OSS Kubernetes (v1.36.4)
* **Identifier:** `sample-upstream-k8s`
* **Metadata:** 
  * Kubernetes Version: `v1.36.4`
  * Distribution: `upstream-oss`
  * Nodes: 3 (1 control-plane, 2 worker nodes)
* **Workload Topology:**
  * **Control Plane Tier ($Y = 7.0$):** `kube-apiserver`, `kube-controller-manager`, `kube-scheduler`, backed by clustered `etcd` ($Y = 5.5$).
  * **System Infrastructure Tier ($Y = 0.5$):** `coredns` (2 replicas), `kube-proxy` (DaemonSet), Cilium CNI routing agents.
  * **Workload Plane:** Baseline sleep/demo deployments (`nginx-ingress-controller`, `cert-manager`).

### 3.2 Catalog Entry 2: Microservices Retail Application (Online Boutique / AWS Retail)
* **Identifier:** `sample-microservices-retail`
* **Metadata:**
  * Application: Google Cloud Online Boutique ("gshoe" / Hipster Shop) & AWS Retail Store
  * Kubernetes Version: `v1.36.4`
  * Nodes: 4 worker nodes (Heterogeneous: 2x `c3-standard-4`, 2x `e2-standard-4`)
* **Workload Services (11 Microservices):**
  1. `frontend`: Web UI entrypoint (Go), exposed via LoadBalancer Service.
  2. `cartservice`: Shopping cart state store (C# / ASP.NET), backed by `redis-cart`.
  3. `productcatalogservice`: Product catalog search and details (Go).
  4. `currencyservice`: Exchange rate calculator (Node.js).
  5. `paymentservice`: Credit card processor (Node.js).
  6. `shippingservice`: Shipping quote generator (Go).
  7. `emailservice`: Order confirmation sender (Python).
  8. `checkoutservice`: Order aggregator and checkout coordinator (Go).
  9. `recommendationservice`: Product recommendation engine (Python).
  10. `adservice`: Contextual advertising engine (Java).
  11. `loadgenerator`: Locust-based background traffic generator.
* **Autoscaling Configuration:**
  * `frontend`: HPA configured with `minReplicas: 2`, `maxReplicas: 10`, `targetCPUUtilizationPercentage: 65%`.
  * `cartservice`: VPA configured with `updateMode: "Auto"` (In-place morphing candidate).
  * `recommendationservice`: HPA + VPA mixed autoscaling.
* **Subterranean Strata Mapping (SPEC-08):**
  * `redis-cart` connected via plunge conduit to Sub-Level B2 Managed Cloud Storage Vault.
  * Machine chassis on Sub-Level B1 mapped to real vCPU/RAM physical footprints.

### 3.3 Catalog Entry 3: AI / ML Distributed Cluster (Ray & KubeRay)
* **Identifier:** `sample-ray-kuberay-cluster`
* **Metadata:**
  * Workload: Distributed AI Training & LLM Batch Inference (vLLM)
  * Frameworks: KubeRay v1.2.0, Ray v2.35.0, Kueue v0.9.0
  * Nodes: 5 nodes (1 Head Node, 2 CPU Worker Nodes, 2 GPU Accelerator Nodes)
* **Topology:**
  * **Ray Head Node:** Hosts GCS server, Ray Dashboard, Ray Cluster Autoscaler, and Prometheus metrics exporter.
  * **Ray Worker CPU Group:** 4 worker pods executing feature preprocessing and data loading.
  * **Ray Worker GPU Group:** 2 massive worker pods assigned to NVIDIA L4 / A100 accelerator bays (SPEC-08 §3.2) executing distributed tensor parallelism.
  * **Kueue Integration (SPEC-09 §5):**
    * Pre-configured `LocalQueue` and `ClusterQueue` resources.
    * An unadmitted PyTorch gang training job held inside a **Kueue Cargo Containment Pallet** in the Exterior Staging Yard ($X = -18.0$, $Y = 0.4$), ready for interactive gang admission (KeyK).

### 3.4 Catalog Entry 4: GKE Autopilot Compute Class Benchmark Cluster
* **Identifier:** `sample-gke-autopilot-benchmark`
* **Metadata:**
  * Platform: Google Cloud GKE Autopilot
  * Compute Classes: `Scale-Up` (high burst), `Performance` (dedicated c3 core pin), `General-Purpose` (standard Autopilot slice).
* **Autoscaling Mechanics:**
  * Configured specifically for comparative split-screen benchmarking against a standard node-pool cluster.
  * Pods define `cloud.google.com/compute-class: "Scale-Up"` annotations.
  * Demonstrates sub-second VPA resize morphing and rapid pod admission without node provisioning latency.

---

## 4. Traffic Simulation & Autoscaling Test Harness: Research & Technical Recommendation

### 4.1 Evaluation of Common Traffic Generation Approaches

| Approach | Description | Strengths | Limitations | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **Approach 1: In-Cluster Load Pods (Fortio / k6 / Locust)** | Deploying ephemeral load generator pods inside the Kubernetes cluster via Job or Deployment. | Realistic in-cluster network transport; exercises real Service CIDRs, kube-proxy iptables, and CNI routing; high throughput. | Requires write permissions (`create deployment/job`) in target cluster; cannot run on offline or simulated sample clusters; adds resource overhead to target nodes. | **Essential for Live Cluster Mode** with Helm Operator. |
| **Approach 2: Pure Browser Fetch Flooding** | JavaScript in the browser fires concurrent `fetch()` loops directly against the cluster's ingress URL. | Zero server footprint; executes entirely from user's machine. | Constrained by browser connection limits (max 6 HTTP/1.1 connections per host); blocked by CORS on unconfigured ingresses; cannot target private ClusterIPs; vulnerable to client CPU throttling. | **Rejected as Primary Engine**; retained only as optional fallback. |
| **Approach 3: Discrete-Event Queuing Simulation Engine** | A deterministic queuing physics engine ($M/M/c/K$) running in TypeScript / Web Worker, simulating request arrivals, pod saturation, and autoscaling. | **100% universal**: Runs identically on live clusters, simulated samples, and offline demos; zero cloud cost; enables millisecond-level reproducible comparisons of Autopilot vs. Standard Karpenter latency curves. | Does not generate real HTTP packets across physical wires in live clusters unless paired with an operator. | **Recommended Core Solution** for visualizer UI harness. |

### 4.2 Recommended Solution: The "Hybrid Dual-Engine Traffic Harness"

ClusterVis shall implement a **Hybrid Dual-Engine Architecture**:
1. **Engine A: The Client-Side Queuing Simulation Engine (Universal Baseline):**
   * Built directly into the frontend (`src/scene/traffic_simulator.ts`).
   * Operates deterministically across all viewports (both live connected clusters and sample catalog clusters).
   * Models the full mathematical dynamics of Kubernetes HPA, VPA, and node scheduling latency.
   * Animates real-time 3D flow particles (SPEC-01 §6), triggers SPEC-09 VPA morphing and HPA lateral conveyor animations, and drives live HUD latency charts.
2. **Engine B: The In-Cluster Operator Load Dispatcher (Live Mode Add-on):**
   * When connected to a live cluster where the `clustervis` Helm chart is installed, the UI can optionally toggle **Live In-Cluster Injection**.
   * The UI issues `POST /api/v1/load/start` to the operator. The operator spawns an ephemeral scratch Fortio or k6 load pod, targeting the service endpoint, while streaming back live TCP SYN RTT from the synthetic probe daemonset (SPEC-07) and Prometheus metrics.

---

## 5. Mathematical Modeling of Autoscaling & Latency Differences

### 5.1 Queuing Theory Formulation ($M/M/c/K$ Model)

Each target workload (e.g. `frontend` or `recommendationservice`) is modeled as an $M/M/c$ multiserver queue where:
* $c = N(t)$: Number of running and ready pod replicas at time $t$.
* $\lambda(t)$: Aggregate request arrival rate (requests per second, RPS) governed by the user's selected traffic profile.
* $\mu$: Service rate per pod replica ($\approx 120\text{ req/sec/pod}$ for standard Go/C# microservices; $\approx 25\text{ req/sec/pod}$ for Python ML inference).
* System Traffic Intensity:
  $$\rho(t) = \frac{\lambda(t)}{N(t) \cdot \mu}$$

#### Latency Transfer Function
Under normal load ($\rho < 0.7$), average response latency $L(t)$ remains near baseline:
$$L(t) = L_{\text{base}} + \frac{1}{\mu - \frac{\lambda(t)}{N(t)}}$$

When load exceeds capacity ($\rho(t) \ge 1.0$), request queues build up in ingress buffers, adding queueing delay $W_q(t)$:
$$W_q(t) = \int_0^t \max\left(0, \frac{\lambda(s) - N(s)\mu}{c}\right) ds$$
$$L(t) = L_{\text{base}} + \frac{1}{\mu} + W_q(t)$$

If $L(t) > L_{\text{timeout}}$ ($2000\text{ ms}$), requests fail with HTTP 504 / 503, and the error rate rises proportionally.

### 5.2 Kubernetes Autoscaling Rules

#### Horizontal Pod Autoscaling (HPA)
The HPA controller samples pod CPU utilization every $15\text{s}$ (configurable in simulation to $1\text{s}$ for rapid UI demonstration).
$$\text{Current CPU \%} = \min(100\%, \rho(t) \times 100\%)$$
$$\text{Desired Replicas} = \left\lceil N_{\text{current}} \times \frac{\text{Current Metric Value}}{\text{Target Metric Value (e.g. 60\%)}}\right\rceil$$
Subject to $\min(N_{\text{max}}, \max(N_{\text{min}}, \text{Desired Replicas}))$.

#### Vertical Pod Autoscaling (VPA)
For workloads managed by VPA in `Auto` mode:
* If CPU utilization exceeds $80\%$ for more than $3\text{ seconds}$, VPA calculates an updated CPU/Memory target recommendation.
* In Kubernetes with in-place pod resizing, the pod requests are updated directly without restarting the container if the node has sufficient unallocated capacity.

### 5.3 Comparative Scheduling Latency: GKE Autopilot vs. Standard Karpenter / NodePools

When HPA triggers scale-out from $N_1 \to N_2$ replicas, the critical visual and operational difference lies in **how quickly new pods transition from `Pending` to `Running`**:

```
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                      TRAFFIC SPIKE (e.g. 100 RPS ──► 1200 RPS)              │
 └──────────────────────────────────────┬──────────────────────────────────────┘
                                        │
             ┌──────────────────────────┴──────────────────────────┐
             ▼                                                     ▼
 ┌───────────────────────────────────────┐   ┌─────────────────────────────────┐
 │ CLUSTER A: GKE AUTOPILOT COMPUTE CLASS│   │ CLUSTER B: STANDARD NODE POOL   │
 ├───────────────────────────────────────┤   ├─────────────────────────────────┤
 │ 1. Scale-Up compute class node slots  │   │ 1. Existing node capacity full  │
 │    available on pre-warmed fabric.    │   │ 2. Cluster Autoscaler / Karpent.│
 │ 2. Pod scheduled immediately:         │   │    detects unschedulable pods.  │
 │    τ_sched ≈ 3.5 seconds.             │   │ 3. Cloud Provider VM provision: │
 │ 3. VPA in-place morph: τ_vpa ≈ 1.2s.  │   │    - VM API launch: 35s         │
 │ 4. Pods transition to Running.        │   │    - OS boot & containerd: 25s  │
 │ 5. Latency transient: max 48ms;       │   │    - Kubelet join & CNI: 15s    │
 │    recovers to 12ms baseline in <8s.  │   │    - Image pull: 20s            │
 │                                       │   │    Total τ_provision ≈ 95-150s! │
 │                                       │   │ 4. Pods sit in EXTERIOR STAGING │
 │                                       │   │    YARD (X < -12) as PENDING.   │
 │                                       │   │ 5. Latency surges: 15ms ──►680ms│
 │                                       │   │ 6. Queue saturation / 503 drops │
 └───────────────────────────────────────┘   └─────────────────────────────────┘
```

#### Mathematical Latency Penalty Comparison

| Metric / Stage | GKE Autopilot (Compute Class) | Standard Karpenter / GKE NodePool |
| :--- | :--- | :--- |
| **Pod Scheduling Delay ($\tau_{\text{sched}}$)** | $\mathbf{3.0\text{ to }6.0\text{ s}}$ | $\mathbf{90.0\text{ to }150.0\text{ s}}$ |
| **In-Place VPA Morph Delay ($\tau_{\text{vpa}}$)** | $\mathbf{1.2\text{ s}}$ (In-place resize) | $\mathbf{45.0\text{ s}}$ (Requires eviction & reschedule) |
| **Peak Latency under $10\times$ Spike** | $\mathbf{42\text{ ms}}$ (Transient) | $\mathbf{720\text{ ms}}$ (Severe Queueing Saturation) |
| **HTTP Error Rate during Spike** | $\mathbf{0.0\%}$ | $\mathbf{18.4\%}$ (Timeouts / Drops) |
| **Exterior Staging Yard Behavior** | Pods briefly hover ($1.5\text{s}$) before moving to deck | Pods sit stranded in Staging Yard; Karpenter tractor beam pulses continuously |

---

## 6. UI & HUD Test Harness Deck Specification

### 6.1 Persistent Topbar Additions (`index.html`)

```html
<!-- Topbar Button Additions -->
<button class="btn" id="btn-add-cluster" title="Add Live Cluster or Load Simulated Sample">
  ➕ ADD CLUSTER
</button>
<button class="btn" id="btn-traffic-harness" title="Toggle Traffic Simulation & Autoscaling Test Harness (KeyT)">
  ⚡ TRAFFIC HARNESS
</button>
```

### 6.2 The Dockable Traffic Control Deck HUD (`#traffic-deck-dock`)

A sleek, bottom-docked control deck (toggleable via KeyT or topbar button) rendered using dark translucent glass (`rgba(17, 24, 39, 0.95)`, blur 12px):

```
 ╔═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗
 ║ ⚡ AUTOSCALING TRAFFIC SIMULATION HARNESS                                                       [✕ Close] [⛶ Dock]║
 ╠═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╣
 ║ TARGET WORKLOAD:     [ frontend ▼ ]        TARGET CLUSTER: [ All Viewports (Linked) ▼ ]                           ║
 ║ TRAFFIC PATTERN:     (•) Step Spike  ( ) Sine Wave  ( ) Ramp-Up  ( ) Chaos Flap                                   ║
 ║ CONCURRENCY / LOAD:  [════════════●══════════════════════]  850 RPS  (Baseline: 100 RPS)                          ║
 ║ AUTO-SCALING ENGINE: [✔] HPA (Horizontal)    [✔] VPA Morphing    [✔] Simulate Node Provisioning Latency           ║
 ║                                                                                                                   ║
 ║ ── REAL-TIME COMPARATIVE TELEMETRY ───────────────────────────────────────────────────────────────────────────── ║
 ║  VIEWPORT A (GKE Autopilot):   Latency: 14ms | Replicas: 6 (+4) | CPU: 64% | Sched Delay: 3.2s   [STABLE]        ║
 ║  VIEWPORT B (Standard Node):   Latency: 540ms| Replicas: 2 (4 Pending in Staging) | CPU: 100%   [SATURATED]     ║
 ║                                                                                                                   ║
 ║  [ ▶ INJECT TRAFFIC ]   [ ⏸ PAUSE ]   [ ↺ RESET BASELINE ]   [ ⚡ BURST 2000 RPS ]                                ║
 ╚═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝
```

### 6.3 3D Scene Visual Manifestations

1. **Traffic Flow Particles (SPEC-01 §6):**
   * Particle stream density and speed along the client horizon conduits scale directly with RPS.
   * Under low latency ($< 30\text{ms}$): Tranquil glowing cyan `#38bdf8`.
   * Under queuing pressure ($30\text{ms} - 150\text{ms}$): Warning amber `#f59e0b`.
   * Under saturation/timeout ($> 200\text{ms}$): Blazing crimson `#ef4444` with conduit sparking particles.
2. **Autoscaling Visualizations (SPEC-09):**
   * **VPA Morphing:** When VPA scales pods up, pod height and radius smoothly tween over 1200ms with energy ripple rings.
   * **HPA Lateral Spawning:** New pods spawn from the supervisor tier, slide down the central riser, and conveyor onto the worker deck slots.
   * **Staging Yard Queueing:** For standard clusters awaiting nodes, pods spawn in the **Exterior Staging Yard ($X < -12.0$)**, bobbing in anti-gravity hover while amber tractor beams shoot down to Sub-Level B1 ghost chassis.

---

## 7. Data Contracts & TypeScript Interfaces

### 7.1 Cluster Onboarding Models (`src/ui/cluster_onboarding.ts`)

```typescript
export type OnboardingMode = 'helm' | 'client' | 'sample';

export interface LiveClusterConfig {
  name: string;
  apiUrl: string;
  authType: 'token' | 'kubeconfig-proxy' | 'none';
  token?: string;
  namespace?: string;
  enableLatencyProbe: boolean;
}

export interface SampleClusterCatalogItem {
  id: string;
  title: string;
  description: string;
  category: 'oss' | 'microservices' | 'ai-ml' | 'benchmark';
  k8sVersion: string;
  nodeCount: number;
  podCount: number;
  dataFile: string;
  diffTargetFile?: string;
  highlightFeatures: string[];
}
```

### 7.2 Traffic Simulation Engine Models (`src/scene/traffic_simulator.ts`)

```typescript
export type TrafficPattern = 'step' | 'sine' | 'ramp' | 'chaos';

export interface TrafficHarnessConfig {
  targetWorkloadId: string;
  pattern: TrafficPattern;
  baseRps: number;
  peakRps: number;
  durationSeconds: number;
  enableHpa: boolean;
  enableVpa: boolean;
  simulateProvisioningSkew: boolean;
}

export interface WorkloadScalingState {
  clusterId: string;
  workloadName: string;
  currentReplicas: number;
  desiredReplicas: number;
  pendingReplicas: number;
  currentCpuUtilization: number;
  targetCpuUtilization: number;
  latencyMs: number;
  errorRate: number;
  isAutopilot: boolean;
  provisioningTimeRemainingMs: number;
}
```

---

## 8. Implementation Task Breakdown

### TASK-CV-1101: Interactive UI Cluster Onboarding Modal & Helm Generator
* **Scope:** Author `src/ui/cluster_onboarding.ts` and update `index.html` with persistent `+ Add Cluster` topbar trigger.
* **Deliverables:**
  * Modal dialog supporting Live Cluster (Helm command generator + token input) and Client-Side connect.
  * Direct integration with `sessionStorage` token management per SPEC-07 §5.1.
  * Connectivity test probe validating `/api/v1/healthz` or `/snapshot`.

### TASK-CV-1102: Instant Simulated Sample Catalog & Fixtures
* **Scope:** Author sample catalog registry and generate comprehensive JSON fixtures in `public/data/samples/`.
* **Deliverables:**
  * `sample-upstream-k8s.json`: Baseline OSS v1.36.4 with 3 nodes.
  * `sample-online-boutique.json`: 11-microservice Google Online Boutique / retail store with Redis and HPA/VPA.
  * `sample-ray-kuberay.json`: KubeRay cluster with Ray Head, CPU/GPU workers, and Kueue gang pallet.
  * `sample-autopilot-bench.json`: GKE Autopilot compute class cluster.
  * One-click catalog selector in onboarding modal instantly loading chosen sample into any viewport slot.

### TASK-CV-1103: Client-Side Direct Kubernetes API Extractor
* **Scope:** Author `src/ingestion/client_extractor.ts` in TypeScript.
* **Deliverables:**
  * In-browser parser transforming standard Kubernetes JSON responses (`/api/v1/pods`, `/nodes`, `/services`) directly into `ClusterGraphData`.
  * Enables zero-operator, zero-install cluster visualization for read-only user tokens.

### TASK-CV-1104: Client-Side Queuing Simulation & Autoscaling Engine
* **Scope:** Author `src/scene/traffic_simulator.ts` implementing $M/M/c/K$ queuing dynamics.
* **Deliverables:**
  * Traffic profile generators (Step, Spike, Sine, Chaos).
  * HPA replica calculation with scale-up rates and stabilization windows.
  * VPA in-place morph triggers.
  * Scheduling delay model contrasting GKE Autopilot ($\tau_{\text{sched}} \approx 3.5\text{s}$) vs Standard Karpenter NodePool ($\tau_{\text{node}} \approx 95\text{s}$).

### TASK-CV-1105: Traffic Simulation Control Deck HUD & Comparative Visuals
* **Scope:** Author `src/ui/traffic_deck.ts` and wire real-time particle and autoscaling animations.
* **Deliverables:**
  * Bottom-docked translucent glass control deck with slider, pattern selectors, and inject triggers.
  * Real-time comparative latency and replica metric bars across viewport slots.
  * Dynamic particle speed/color modulation (`flow_particles.ts`) reflecting queuing saturation.
  * Direct triggering of SPEC-09 VPA morphing and HPA lateral conveyor animations.

### TASK-CV-1106: Tests, Build Verification & End-to-End Visual Verification
* **Scope:** Comprehensive testing, TypeScript verification, and build validation.
* **Deliverables:**
  * Unit tests for queuing model and client extractor.
  * Clean `npm run build` with zero TypeScript errors.
  * Interactive smoke test loading samples and triggering traffic spikes.

---

## 9. Acceptance Criteria & Verification Protocol

1. **Interactive Cluster Onboarding:**
   * Clicking `➕ ADD CLUSTER` opens the modal cleanly with tabs for Live Cluster and Sample Catalog.
   * Entering invalid URLs or failing tokens gracefully displays an inline error without crashing the visualizer.
   * Tokens are strictly verified to exist in `sessionStorage` and never appear in `localStorage` or URL query strings.
2. **Instant Sample Loading:**
   * Selecting any of the 4 simulated samples loads the complete 3D Skyscraper scene into the active viewport in $< 100\text{ms}$.
   * Ray cluster sample correctly instantiates accelerator bays on Sub-Level B1 and Kueue cargo pallet in the staging yard.
   * Online Boutique sample correctly maps microservices, Redis cache, and HPA badges.
3. **Traffic Simulation & Latency Dynamics:**
   * Triggering a traffic spike ($850\text{ RPS}$) against `frontend` causes CPU utilization to rise and triggers HPA scale-out.
   * In GKE Autopilot mode, pods schedule and transition to Running within $4\text{ seconds}$, and latency stabilizes under $20\text{ms}$.
   * In Standard NodePool mode, pods sit in the Exterior Staging Yard in `Pending` state for the simulated node boot delay, while latency spikes above $500\text{ms}$ and particles turn warning amber/red.
4. **Code Quality & Build:**
   * `npm run build` succeeds with zero TypeScript warnings or errors.
   * `docs/MAP.md` and `Kanban-Cluster-Visualizer.md` accurately reflect SPEC-10.
