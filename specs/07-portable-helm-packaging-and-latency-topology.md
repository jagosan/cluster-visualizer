# SPEC-07: Portable In-Cluster Helm Packaging, Latency-Distance Topology & Federated Security

**Status:** Proposed  
**Author:** Christopher Robin (Lead Architect) & 🦉 Owl (Architectural Synthesizer)  
**Date:** 2026-10-03  
**Target:** `cluster-vis`  
**Extends:** `specs/02-layered-rectangular-architecture.md`, `specs/03-horizontal-node-peers-and-diff-engine.md`, `specs/04-in-cluster-streaming-operator.md`, `specs/05-time-travel-topology-scrubber.md`, `specs/06-ephemeral-multi-cluster-testbed-and-live-streaming.md`  

---

## 1. Executive Summary & Design Vision

ClusterVis has evolved through several iterations: procedural 3D skyscraper layouts (SPEC-01/02), horizontal worker chassis decks with 3D git-diffing (SPEC-03), real-time SSE in-cluster operators (SPEC-04), time-travel historical scrubbing (SPEC-05), and multi-cluster testbeds on Chunkito (SPEC-06).

SPEC-07 establishes an **additive, self-contained, and highly portable evolutionary step**:
1. **Single-Command Portable Deployment (`helm install clustervis`):** Package the visualizer, operator, and telemetry into a self-contained Helm chart. The operator hosts the in-cluster informer engine, an embedded lightweight graph model, and directly serves the compiled Three.js WebGL client. No external databases, no cloud dependencies, and zero mandatory external services.
2. **Latency-as-Distance Force Field Mode:** An alternative 3D layout mode where spatial distance between nodes directly represents measured network latency (RTT / request duration), while edge stiffness represents throughput. Nodes snap closer together when latency shrinks during time-travel playback or live rollouts.
3. **Additive Layout Coexistence:** Preserves the foundational Skyscraper and Worker Deck layouts (SPEC-02/03) as the default architectural view. Users can smoothly transition (`lerp`) between the structured Skyscraper layout and the dynamic Latency Distance Field with a single HUD toggle.
4. **Zero-Dependency Latency Telemetry (`clustervis-probe`):** A microscopic, unprivileged DaemonSet measuring inter-node and inter-service TCP RTT out of the box, with automated fallback connectors for Cilium Hubble eBPF and Prometheus when present.
5. **Federated Multi-Cluster Browser Client:** A client-side aggregation model where a single browser session connects to 1, 2, or 4 independent cluster endpoints simultaneously over SSE, diffing topologies and comparing cross-cluster latencies in real time without requiring cross-cluster network bridges.
6. **Enterprise Security & Authentication:** Pluggable browser authentication using Kubernetes TokenReviews (native ServiceAccount bearer tokens), OAuth2/OIDC Ingress proxies, strict read-only RBAC, and automated secret scrubbing.

---

## 2. In-Cluster Packaging Architecture (`charts/clustervis`)

### 2.1 Helm Chart Component Topology

The Helm chart installs into the `clustervis-system` namespace with a predictable, lightweight footprint:

```
                    ┌────────────────────────────────────────────────────────┐
                    │               Kubernetes Cluster Target                │
                    │                                                        │
                    │   ┌────────────────────────────────────────────────┐   │
                    │   │  clustervis-operator (Deployment, 1 Replica)    │   │
                    │   │  - K8s Watch Informers (Pods, Services, Nodes) │   │
                    │   │  - In-Memory Graph & Force Embedder            │   │
                    │   │  - Embedded Static Web Server (Three.js UI)    │   │
                    │   │  - SSE Streaming & Snapshot API (:8080)        │   │
                    │   └───────────────────────▲────────────────────────┘   │
                    │                           │                            │
                    │             Local Latency Matrix Ingest                │
                    │                           │                            │
                    │   ┌───────────────────────┴────────────────────────┐   │
                    │   │  clustervis-probe (DaemonSet, 1 per Node)      │   │
                    │   │  - Unprivileged TCP Round-Robin Ping Probe     │   │
                    │   │  - Inter-node & Service Endpoint RTT Collector │   │
                    │   │  - Memory: <15MB RSS | CPU: <0.01 Cores        │   │
                    │   └────────────────────────────────────────────────┘   │
                    │                                                        │
                    │   ┌────────────────────────────────────────────────┐   │
                    │   │  Service: clustervis (ClusterIP / NodePort)    │   │
                    │   │  Ingress: optional OAuth2 / TLS Proxy          │   │
                    │   └────────────────────────────────────────────────┘   │
                    └────────────────────────────────────────────────────────┘
```

### 2.2 Helm Chart Values Contract (`charts/clustervis/values.yaml`)

```yaml
# Default values for clustervis
image:
  repository: ghcr.io/jagosan/clustervis-operator
  tag: "v1.0.0"
  pullPolicy: IfNotPresent

operator:
  replicaCount: 1
  resources:
    limits:
      cpu: 250m
      memory: 128Mi
    requests:
      cpu: 20m
      memory: 48Mi
  config:
    exportIntervalSeconds: 5
    defaultLayoutMode: "skyscraper" # "skyscraper" | "latency-force"
    scrubSecrets: true
    scrubConfigMaps: true
    excludedNamespaces:
      - kube-system
      - clustervis-system
      - cert-manager
      - local-path-storage

probe:
  enabled: true
  repository: ghcr.io/jagosan/clustervis-probe
  tag: "v1.0.0"
  probeIntervalSeconds: 3
  probeTimeoutMs: 500
  sampleTargetLimit: 20
  resources:
    limits:
      cpu: 50m
      memory: 32Mi
    requests:
      cpu: 5m
      memory: 12Mi

telemetry:
  mode: "probe" # "probe" | "cilium" | "prometheus" | "synthetic"
  prometheus:
    url: "http://prometheus-k8s.monitoring.svc:9090"
    latencyQuery: 'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[2m])) by (le, source_workload, destination_workload))'
  cilium:
    hubbleRelayAddress: "hubble-relay.kube-system.svc:4245"

auth:
  enabled: true
  type: "token" # "token" (K8s Bearer Token) | "oauth2-proxy" | "none"
  tokenValidation:
    audience: "clustervis"
    requireClusterAdmin: false

service:
  type: ClusterIP
  port: 8080
  nodePort: 30080

ingress:
  enabled: false
  className: ""
  annotations: {}
  hosts:
    - host: clustervis.local
      paths:
        - path: /
          pathType: Prefix
  tls: []
```

---

## 3. Latency-as-Distance Force Field Engine

### 3.1 Mathematical Formulation of Latency Distance

To translate abstract network latency into intuitive physical spatial dimensions, the graph engine assigns dynamic spring lengths between interconnected components.

#### 1. Rest Length Function ($L_0$)
Linear scaling over-stretches wide-area edges ($>100\text{ms}$) while collapsing micro-service edges ($<1\text{ms}$). A logarithmic-damped transfer function is applied:

$$L_0(u, v) = L_{\text{min}} + S \cdot \log_{10}\left(1 + \frac{\text{latency}_{\text{ms}}(u, v)}{\tau_0}\right)$$

Where:
- $L_{\text{min}} = 1.8\text{ units}$ (minimum collision spacing preventing asset overlap).
- $S = 6.0$ (spatial scaling coefficient).
- $\tau_0 = 1.0\text{ms}$ (baseline reference latency).

*Example Distances:*
- Same Pod / Localhost ($0.05\text{ms}$): $L_0 \approx 1.9\text{ units}$
- Same Node / Inter-Pod ($0.8\text{ms}$): $L_0 \approx 3.3\text{ units}$
- Cross-Node LAN ($2.5\text{ms}$): $L_0 \approx 5.1\text{ units}$
- Cross-Zone / Cloud VPC ($18.0\text{ms}$): $L_0 \approx 9.5\text{ units}$
- Degraded / WAN ($120.0\text{ms}$): $L_0 \approx 14.3\text{ units}$

#### 2. Spring Stiffness ($K$)
High-frequency traffic flows (e.g. database replica streams, ingress front-doors) form rigid structural spines, while rare or idle connections are soft:

$$K(u, v) = K_{\text{base}} \cdot \min\left(4.0, \; 1.0 + \log_{10}(1 + \text{RPS}(u, v))\right)$$

### 3.2 Dual-Mode Layout & Spatial Lerping

The visualizer must not abandon the clear architectural hierarchy of the Skyscraper view. Both models are maintained simultaneously in client memory:

```typescript
export interface SpatialCoordinates {
  // Architectural Skyscraper coordinates (rigid tiers Y=0.5 to 12.0)
  arch: { x: number; y: number; z: number };
  // Dynamic Latency Force Field coordinates (spring-mass relaxation)
  latency: { x: number; y: number; z: number };
}
```

#### Transition Mechanism:
A HUD slider or toggle button (`Mode: Skyscraper ⇄ Latency Field`) drives a normalized interpolation factor $\alpha \in [0.0, 1.0]$:

$$\vec{P}(t) = (1 - \alpha) \cdot \vec{P}_{\text{arch}} + \alpha \cdot \vec{P}_{\text{latency}}$$

- $\alpha = 0.0$: Strict Skyscraper View (Tier trays, horizontal worker deck, structured conduits).
- $\alpha = 1.0$: Pure Latency Gravitational Field (Components cluster strictly by network proximity).
- $0.0 < \alpha < 1.0$: Smooth 60 FPS cubic Bezier transition, allowing the user to watch components pull out of their architectural shelves into latency clusters.

### 3.3 Time-Travel Latency Shrink Animation

During historical scrubber playback or live rollout streaming:
1. **Version Change Detection:** Component image tag changes (e.g., `redis:6.2` $\to$ `redis:7.4`). Node mesh flashes green diff halo and adopts updated material color.
2. **Edge Metric Update:** Telemetry feed indicates edge latency between App and Cache drops from $24\text{ms} \to 1.1\text{ms}$ due to connection multiplexing.
3. **Mesh Relocation:** In Latency Field mode, the spring solver updates $L_0$. The two cuboids smoothly glide across the floor toward each other over an $800\text{ms}$ ease-out curve.
4. **Conduit Compression:** The connecting 3D Bezier conduit pipe contracts, thickening slightly and increasing its particle pulse frequency to reflect the enhanced performance.

---

## 4. Telemetry Collection & Probe Subsystem

### 4.1 In-Cluster Synthetic Probe (`clustervis-probe`)

To guarantee zero external dependencies on fresh clusters (Kind, K3d, bare-metal), the chart includes `clustervis-probe`:
- **Architecture:** Unprivileged Go/Rust binary packaged in a `scratch` container ($<10\text{MB}$).
- **Target Selection:** Discovers local peer pods and adjacent node IP addresses using downward API and local endpoints.
- **Probe Technique:** Executes non-blocking TCP SYN/connect handshakes to open workload ports (e.g., HTTP 80/8080, gRPC 50051, Redis 6379) and computes round-trip connection time.
- **Overhead Guard:** Limits probes to a round-robin cycle of maximum 20 targets every 3 seconds, ensuring CPU usage stays $<0.01$ cores and network bandwidth is $<15\text{KB/s}$.
- **Metrics Export:** Exposes a local JSON endpoint `/metrics/latency` consumed periodically by `clustervis-operator`.

### 4.2 Pluggable External Connectors

If the cluster already possesses observability infrastructure, the operator automatically disables or supplements the synthetic probe:
1. **Cilium Hubble:** Connects to `hubble-relay.kube-system.svc:4245` via gRPC. Reads L4 TCP RTT and L7 request duration without sending any synthetic packets.
2. **Prometheus:** Queries PromQL histogram quantiles every $N$ seconds to extract p95/p99 service-to-service latencies.

---

## 5. Security & Authentication Architecture

When exposing ClusterVis via browser or connecting across multiple clusters, strict security controls must govern access.

### 5.1 Browser-to-Cluster Authentication Flow

```
   ┌────────────────┐          ┌───────────────────────┐          ┌───────────────────────┐
   │ Browser Client │          │  clustervis-operator  │          │ Kubernetes API Server │
   └───────┬────────┘          └──────────┬────────────┘          └───────────┬───────────┘
           │                              │                                   │
           │ 1. GET /api/v1/topology      │                                   │
           │    Authorization: Bearer <T> │                                   │
           │─────────────────────────────>│                                   │
           │                              │ 2. TokenReview Request            │
           │                              │    (Token = <T>, Audience = CV)   │
           │                              │──────────────────────────────────>│
           │                              │                                   │
           │                              │ 3. TokenReview Status: Valid      │
           │                              │    User: dev-jago, Groups: [...]  │
           │                              │<──────────────────────────────────│
           │                              │                                   │
           │                              │ 4. SubjectAccessReview            │
           │                              │    Verb: get, Group: clustervis.io│
           │                              │──────────────────────────────────>│
           │                              │                                   │
           │                              │ 5. Allowed: true                  │
           │                              │<──────────────────────────────────│
           │ 6. 200 OK + Topology JSON    │                                   │
           │<─────────────────────────────│                                   │
```

#### Authentication Options:
1. **Mode 1: Kubernetes ServiceAccount Bearer Token (Direct / Default):**
   - The user creates or extracts a short-lived token: `kubectl create token clustervis-viewer --duration=8h`.
   - The ClusterVis browser UI provides a secure token dialog on first load, cached in browser `sessionStorage` (never in `localStorage`).
   - The operator validates the token on every HTTP request and SSE connection against the Kubernetes API via `authentication.k8s.io/v1 TokenReview`.
2. **Mode 2: Ingress OAuth2 / OIDC Proxy:**
   - In enterprise deployments, an `oauth2-proxy` sidecar or Ingress annotation (e.g. Cloudflare Access, Google IAP, Keycloak) handles OpenID Connect.
   - The operator trusts the `X-Forwarded-User` and `X-Forwarded-Email` headers when `auth.type="oauth2-proxy"`.
3. **Mode 3: Local Dev / Headless Sandbox:**
   - In ephemeral testbeds (K3d on Chunkito), auth can be set to `auth.type="none"` for instant zero-token access over private Tailscale.

### 5.2 Least-Privilege RBAC Matrix

The operator requires strictly read-only visibility into cluster topology:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: clustervis-operator
rules:
  # Core discovery resources
  - apiGroups: [""]
    resources: ["nodes", "namespaces", "pods", "services", "endpoints"]
    verbs: ["get", "list", "watch"]
  # Workload controllers for hierarchy resolution
  - apiGroups: ["apps"]
    resources: ["daemonsets", "deployments", "statefulsets", "replicasets"]
    verbs: ["get", "list", "watch"]
  # Ingress routing topology
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses"]
    verbs: ["get", "list", "watch"]
  # CRD discovery
  - apiGroups: ["apiextensions.k8s.io"]
    resources: ["customresourcedefinitions"]
    verbs: ["get", "list", "watch"]
  # Authentication verification
  - apiGroups: ["authentication.k8s.io"]
    resources: ["tokenreviews"]
    verbs: ["create"]
  - apiGroups: ["authorization.k8s.io"]
    resources: ["subjectaccessreviews"]
    verbs: ["create"]
```

### 5.3 Secret Scrubbing & Data Sanitization

ClusterVis visualizes architecture, not confidential credentials. The operator strictly sanitizes all manifests before serializing graph nodes:
- **Secrets:** Never fetched or inspected (RBAC explicitly omits the `secrets` resource).
- **Environment Variables:** All `env` and `envFrom` values in pod containers are stripped. Keys are retained for structural display only if they do not match `*KEY*`, `*TOKEN*`, `*SECRET*`, `*PASSWORD*`, or `*PASS*`.
- **ConfigMaps:** Manifest content is omitted; only ConfigMap volume mount paths and names are recorded.
- **Annotations:** Strips `kubectl.kubernetes.io/last-applied-configuration` and any annotation containing certificates, private keys, or auth headers.

### 5.4 Cross-Origin Resource Sharing (CORS) Security

Because the visualizer supports federated multi-cluster connections (where a UI loaded from Cluster Alpha connects to Cluster Beta), the operator enforces configurable CORS origins:
- Default: Allows origin of the serving operator host and localhost (`http://localhost:*`, `http://127.0.0.1:*`).
- Configurable via `values.yaml` (`operator.config.corsAllowedOrigins: ["https://clustervis.jagosan.com"]`).
- Rejects wildcards (`*`) when bearer authentication credentials are used.

---

## 6. Performance, Scalability & Resource Optimization

Visualizing thousands of components in real time without lagging the browser or overloading the cluster requires strict algorithmic and rendering budgets.

### 6.1 Algorithmic Edge Pruning & Hierarchical Aggregation

In a 1,000-pod cluster, an all-pairs connectivity mesh would yield $1,000^2 = 1,000,000$ potential edges, crashing both the force simulation and the WebGL renderer.

#### Optimization Strategy:
1. **Hierarchical Service-Level Aggregation:** Edges are computed primarily at the **Service / Deployment level**, not pod-to-pod.
   - Example: 50 pods of `cart-service` talking to 10 pods of `redis` produce **one aggregate logical conduit** with average latency and aggregated RPS, rather than 500 individual line meshes.
2. **Micro-Edge Pruning:** Discard or hide idle edges with $\text{RPS} = 0$ or traffic volume $< 0.1\%$ of total cluster throughput unless specifically inspected.
3. **Proximity Culling:** In Latency Force mode, long idle conduits fade into transparent dashed lines to preserve visual clarity.

### 6.2 WebGL Rendering Optimization (Three.js)

1. **InstancedMesh Rendering:**
   - All component cuboids of the same archetype (Worker Pod, System Pod, DaemonSet) are drawn via single `THREE.InstancedMesh` draw calls.
   - Colors, version diff status (green/red/stripes), and matrix transforms are updated via instanced attribute buffers (`instanceMatrix`, `instanceColor`).
2. **Conduit Tube Instancing:**
   - 3D conduit pipes share procedural curve geometries. Flow particles use GPU instancing driven by custom vertex shaders (advancing along curve splines via time uniform `u_time`).
3. **Frustum & Occlusion Culling:**
   - Components outside the camera frustum or occluded in dense clusters are culled from draw passes.
4. **Adaptive Level of Detail (LOD):**
   - Distant nodes ($>50\text{ units}$ from camera) drop 3D labels and bevels, rendering as simple flat unshaded cuboids.

### 6.3 SSE Delta Streaming vs Full Snapshots

To minimize network bandwidth over Tailscale or WAN:
- **Connection Handshake:** On initial connection, the client receives one full `ClusterGraph` snapshot (`event: snapshot`).
- **Delta Events:** Subsequent updates transmit only micro-deltas (`event: delta`):
  ```json
  {
    "timestamp": 1775184920.12,
    "sequence": 4821,
    "delta_type": "MOD",
    "target_id": "pod/default/frontend-7b9f-x9kz2",
    "version": "v1.2.0",
    "metrics": {
      "latency_p99_ms": 3.4,
      "rps": 420
    }
  }
  ```
- **Bandwidth Consumption:** Full snapshot $\approx 80\text{KB}$ compressed. Streaming delta stream $\approx 1.2\text{KB/s}$ during heavy rollouts.

---

## 7. Federated Multi-Cluster Browser Connection

The visualizer frontend supports viewing and diffing multiple clusters simultaneously without requiring cross-cluster network peering.

### 7.1 Multi-Cluster Session Store (`src/ui/cluster_federation.ts`)

```typescript
export interface ClusterEndpoint {
  id: string;
  name: string;
  url: string;           // Base URL (e.g. "https://stage.k8s.jagosan.com")
  token?: string;        // Bearer token for TokenReview
  status: "connected" | "connecting" | "error" | "offline";
  latencyMs: number;
  kubernetesVersion: string;
}
```

### 7.2 Cross-Cluster Diff Matrix & HUD

In Quad-Grid (2x2) or Split-Screen mode:
- **Viewport 1:** Cluster Alpha (`v1.36.4`, Local testbed).
- **Viewport 2:** Cluster Beta (`v1.35.8`, Remote testbed).
- **Synchronized Scrubber:** Scrubber advances both clusters in lockstep.
- **Cross-Cluster Latency Inspector:** Clicking an identical workload (e.g. `postgres-ha`) highlights the service across both viewports, displaying side-by-side metric cards:
  - Cluster Alpha: $2.1\text{ms}$ (Local NVMe / Host network)
  - Cluster Beta: $14.8\text{ms}$ (Virtual overlay network / CNI hop)

---

## 8. Implementation Task Breakdown & Kanban Mapping

The implementation of SPEC-07 is structured into 6 atomic phases mapped to project tasks:

| Task ID | Phase Name | Scope & Deliverables | Primary Deliverable Files |
| :--- | :--- | :--- | :--- |
| **`TASK-CV-801`** | **Helm Chart Scaffolding** | Author complete Helm chart structure (`Chart.yaml`, templates, RBAC, deployment, service, ingress) | `charts/clustervis/Chart.yaml`, `charts/clustervis/templates/*`, `charts/clustervis/values.yaml` |
| **`TASK-CV-802`** | **Synthetic Probe DaemonSet** | Author lightweight unprivileged TCP ping probe daemon in Python/Go, exposing `/metrics/latency` | `src/probe/main.py`, `src/probe/Dockerfile`, `charts/clustervis/templates/daemonset-probe.yaml` |
| **`TASK-CV-803`** | **Operator Graph & Auth Layer** | Implement TokenReview auth validator, secret scrubber, and in-memory latency edge aggregator | `src/operator/auth.py`, `src/operator/graph_engine.py`, `src/operator/server.py` |
| **`TASK-CV-804`** | **Latency Force Layout Engine** | Implement spring-mass MDS layout algorithm generating dynamic coordinates from edge latencies | `src/ingestion/latency_layout.py`, `tests/test_latency_layout.py` |
| **`TASK-CV-805`** | **Three.js Dual-Mode Lerp** | Add HUD layout toggle (`Skyscraper ⇄ Latency Field`), smooth coordinate tweening, and edge compression | `src/scene/cluster_viewport.ts`, `src/scene/layout_transition.ts`, `src/ui/mode_toggle.ts` |
| **`TASK-CV-806`** | **Multi-Cluster Federation HUD** | Implement endpoint connection manager, token auth modal, and cross-cluster latency comparison drawer | `src/ui/cluster_federation.ts`, `src/ui/auth_modal.ts`, `tests/test_federation.py` |

---

## 9. Verification & Acceptance Criteria

1. **Portable Install Acceptance:**
   - Executing `helm install clustervis charts/clustervis --set auth.type=none` on any stock K3d or Kind cluster succeeds in $<10\text{ seconds}$.
   - All pods enter `Running` state without crash loops, consuming $<80\text{MB}$ RAM total.
2. **Static & Legacy Compatibility:**
   - Existing workflows (`cluster-vis dump`, static JSON file loading, Skyscraper views) remain 100% operational with zero regressions (`npm test` and `pytest` pass).
3. **Latency-Distance Behavior:**
   - In Latency Field mode, lowering an edge latency from $20\text{ms} \to 2\text{ms}$ in a synthetic event stream visibly pulls the connected node meshes closer together within $800\text{ms}$.
4. **Security & Sanitization:**
   - Secret resources are rejected by RBAC; ConfigMap contents and container environment variables are confirmed omitted in exported JSON payloads.
   - Invalid or expired bearer tokens receive `401 Unauthorized` via TokenReview.
5. **Multi-Cluster Federation:**
   - A single browser window connects to two independent streaming operator endpoints simultaneously, displaying them in split view with synchronized orbit controls.
