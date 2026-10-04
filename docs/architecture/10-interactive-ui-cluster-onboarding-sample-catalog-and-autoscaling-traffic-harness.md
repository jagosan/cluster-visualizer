# Architectural Blueprint: SPEC-10 Interactive UI Cluster Onboarding, Simulated Sample Catalog & Autoscaling Traffic Simulation Harness

**Document Reference:** `docs/architecture/10-interactive-ui-cluster-onboarding-sample-catalog-and-autoscaling-traffic-harness.md`  
**Companion Specification:** `specs/10-interactive-ui-cluster-onboarding-sample-catalog-and-autoscaling-traffic-harness.md`  
**Target System:** `cluster-vis`  
**Status:** Approved Architecture Blueprint  

---

## 1. High-Level Architecture & Component Interaction

```
 ┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                                 BROWSER CLIENT (ClusterVis UI)                                  │
 │                                                                                                 │
 │  ┌──────────────────────┐      ┌─────────────────────────────┐      ┌────────────────────────┐  │
 │  │ + Add Cluster Modal  │      │ Sample Catalog Registry     │      │ Traffic Control Deck   │  │
 │  │ (src/ui/cluster_     │      │ (src/ui/sample_catalog.ts)  │      │ (src/ui/traffic_deck.  │  │
 │  │  onboarding.ts)      │      │                             │      │  ts)                   │  │
 │  └──────────┬───────────┘      └──────────────┬──────────────┘      └───────────┬────────────┘  │
 │             │                                 │                                 │               │
 │             ├─────────────────────────────────┼─────────────────────────────────┤               │
 │             ▼                                 ▼                                 ▼               │
 │  ┌───────────────────────────────────────────────────────────────────────────────────────────┐  │
 │  │                                   GRID CONTROLLER                                         │  │
 │  │                  (Manages Viewport Slots: Alpha, Beta, Gamma, Delta)                      │  │
 │  └──────────────────────────────┬───────────────────────────┬────────────────────────────────┘  │
 │                                 │                           │                                   │
 │             ┌───────────────────┴──────────┐     ┌──────────┴──────────────────┐                │
 │             ▼                              ▼     ▼                             ▼                │
 │  ┌─────────────────────────┐   ┌───────────────────────────┐   ┌─────────────────────────────┐  │
 │  │ ClusterViewport Slot A  │   │ ClusterViewport Slot B    │   │ TrafficSimulator Engine     │  │
 │  │ (Three.js 3D Scene)     │   │ (Three.js 3D Scene)       │   │ (src/scene/traffic_         │  │
 │  │ - PodCapsuleManager     │   │ - PodCapsuleManager       │   │  simulator.ts)              │  │
 │  │ - AutoscalingFxManager  │   │ - AutoscalingFxManager    │   │ - M/M/c/K Queuing Physics   │  │
 │  │ - StagingYardManager    │   │ - StagingYardManager      │   │ - HPA / VPA Controllers     │  │
 │  │ - FlowParticleSystem    │   │ - FlowParticleSystem      │   │ - Sched Latency Skew Model  │  │
 │  └─────────────────────────┘   └───────────────────────────┘   └─────────────────────────────┘  │
 └─────────────────────────┬───────────────────────────────────────────────────────────────────────┘
                           │
             ┌─────────────┴─────────────────────────────┐
             ▼                                           ▼
 ┌───────────────────────────────────────┐   ┌─────────────────────────────────────────────────────┐
 │ OPTION 1: IN-CLUSTER OPERATOR STREAM  │   │ OPTION 2: CLIENT-SIDE DIRECT FETCH / PROXY          │
 │ (Remote Helm Deployment)              │   │ (Zero in-cluster deployment)                        │
 │ - TokenReview Bearer Authentication   │   │ - Standard Kubernetes API (/api/v1/pods, /nodes)   │
 │ - Server-Sent Events (SSE) Stream     │   │ - Client-Side Extractor (src/ingestion/client_      │
 │ - Synthetic Probe DaemonSet           │   │   extractor.ts) parses directly into ClusterGraph   │
 └───────────────────────────────────────┘   └─────────────────────────────────────────────────────┘
```

---

## 2. Onboarding Workflow & State Machine

```
                            [ User Clicks "+ ADD CLUSTER" ]
                                           │
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │    Cluster Onboarding Modal Dialog      │
                      │  Select Mode: Live Cluster vs Sample    │
                      └────────────────────┬────────────────────┘
                                           │
                  ┌────────────────────────┴────────────────────────┐
                  ▼                                                 ▼
       [ Mode 1: Live Cluster ]                         [ Mode 2: Sample Catalog ]
                  │                                                 │
        ┌─────────┴─────────┐                           ┌───────────┴───────────┐
        ▼                   ▼                           ▼                       ▼
 [ Helm Operator ]  [ Client Direct ]            [ Select Preset ]       [ Select Slot ]
 - Enter Target URL  - Enter Kube API URL        - Upstream K8s v1.36    - Slot A (Left)
 - Enter Bearer Tok  - Enter Read Token          - Online Boutique       - Slot B (Right)
 - Copy Helm Cmd /   - Local proxy port          - Ray & KubeRay Cluster - Slot C / Slot D
   Automated Deploy  - Zero install              - Compute Class Bench          │
        │                   │                           │                       │
        ▼                   ▼                           └───────────┬───────────┘
   [ Test Health ]     [ Client Fetch ]                             │
   /api/v1/healthz     /api/v1/pods                                 ▼
        │                   │                           [ Hydrate In-Memory ]
        └─────────┬─────────┘                           JSON Fetch (<100ms)
                  │                                                 │
                  ▼                                                 ▼
        [ Connect Live Stream ] ────────────────────────► [ Render 3D Scene ]
        SSE EventSource                                   Three.js Viewport
```

---

## 3. Traffic Simulation Engine & Queuing Dynamics

### 3.1 Mathematical State Machine per Workload

```
       [ Request Arrival Stream λ(t) ]
                      │
                      ▼
         ┌─────────────────────────┐
         │ Ingress Buffer / Queue  │ ◄────── Backpressure / Overflow (HTTP 503 / 504)
         │       Length Q(t)       │
         └────────────┬────────────┘
                      │
                      ▼
    ┌───────────────────────────────────┐
    │ Running Pod Replicas: N(t)        │
    │ Total Capacity: C(t) = N(t) × μ   │
    └─────────────────┬─────────────────┘
                      │
                      ▼
             [ Response Latency ]
             L(t) = L_base + 1/μ + W_q(t)
                      │
                      ├──────────────────────────┐
                      ▼                          ▼
            [ Low Load: ρ < 0.7 ]      [ Overloaded: ρ ≥ 1.0 ]
            - Latency: 10 - 25ms       - Latency: 150 - 800ms+
            - Particles: Cyan          - Particles: Amber / Crimson
            - Pods: Normal height      - Queue: Accumulates
                      │                          │
                      │                          ▼
                      │                [ HPA Triggered ]
                      │                N_desired = ceil(N_curr × (ρ / 0.60))
                      │                          │
                      │                          ▼
                      │             ┌─────────────────────────┐
                      │             │ Check Cluster Category  │
                      │             └────────────┬────────────┘
                      │                          │
                      │        ┌─────────────────┴─────────────────┐
                      │        ▼                                   ▼
                      │  [ GKE Compute Class ]           [ Karpenter / Standard ]
                      │  - Slices Available              - Node Capacity Full
                      │  - τ_sched ≈ 3.5s                - Cold VM Boot Required
                      │  - Fast Pod Schedule             - τ_node ≈ 60 - 150s
                      │        │                                   │
                      │        │                                   ▼
                      │        │                         [ Exterior Staging Yard ]
                      │        │                         - Pods hover as PENDING
                      │        │                         - Amber tractor beams fire
                      │        │                         - Latency remains high
                      │        │                                   │
                      │        ▼                                   ▼
                      └───────►[ Pods Transition to Running: N(t) Increases ]
                               Capacity Expands: C(t) > λ(t)
                               Queue Drains: Q(t) ──► 0
                               Latency Recovers to Baseline (12ms)
```

---

## 4. UI Layout & Component Docking

```
 ┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
 │ TOPBAR: [CLUSTERVIS] [Diff Pills]   [1][2][4] [📡 LIVE] [⏱ TIME] [➕ ADD CLUSTER] [⚡ TRAFFIC] │
 ├────────────────────────────────────────────────┬────────────────────────────────────────────────┤
 │ VIEWPORT A (Split Left)                        │ VIEWPORT B (Split Right)                       │
 │ [Cluster Alpha: GKE Autopilot Compute Class]   │ [Cluster Beta: Karpenter / Standard NodePool]  │
 │                                                │                                                │
 │                  (Penthouse)                   │                  (Penthouse)                   │
 │                API Server / etcd               │                API Server / etcd               │
 │                                                │                                                │
 │            ┌──────────────────────┐            │            ┌──────────────────────┐            │
 │            │      Worker Deck     │            │            │      Worker Deck     │            │
 │            │  [Pods Scaling Out]  │            │            │  [Node Saturated]    │            │
 │            └──────────────────────┘            │            └──────────────────────┘            │
 │                                                │     [Pending Pods in Staging Yard]             │
 │                                                │         (·) (·) (·)  (X < -12.0)               │
 │ ────────────────────────────────────────────── │ ────────────────────────────────────────────── │
 │ Subterranean B1: Pre-warmed Compute Class Slabs│ Subterranean B1: Ghost Chassis & Tractor Beams │
 ├────────────────────────────────────────────────┴────────────────────────────────────────────────┤
 │ DOCKABLE TRAFFIC HARNESS CONTROL DECK (#traffic-deck-dock)                                      │
 │ [Target: frontend] [Pattern: Step Spike] [Load: 850 RPS] [Inject Traffic] [Reset] [Burst 2k]   │
 │ Viewport A Latency: 14ms (Healthy)  │ Viewport B Latency: 620ms (Saturated / 4 Pending Pods)    │
 └─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Security & Isolation Matrix

| Layer | Mechanism | Security Guarantee |
| :--- | :--- | :--- |
| **Browser Token Storage** | `sessionStorage.setItem('clustervis_token_' + id, token)` | Kept strictly in tab memory. Cleared upon tab close. Never written to disk, cookies, or `localStorage`. |
| **In-Cluster Operator RBAC** | `ClusterRole` with Read-Only Verbs (`get`, `list`, `watch`) | Cannot create, modify, or delete any user workloads or configurations. |
| **Secret Sanitization** | `sanitize_manifest()` in `src/operator/graph_engine.py` | Eliminates tokens, certificates, and passwords before transmission over SSE. |
| **Client-Side Mode** | Native browser `fetch()` | Respects browser CORS; credentials stay within browser sandbox. |
| **Simulated Samples** | Bundled static JSON | Zero network access, zero credentials, zero tracking. |
