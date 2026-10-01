# SPEC-03: Horizontal Node Peers, 3D Graph Diff Engine & Universal Cluster Exporter

**Status:** Proposed  
**Author:** Christopher Robin (Lead Architect) & Jagular (Chunkito 177B Big Iron)  
**Date:** 2026-10-01  
**Target:** `cluster-vis`  
**Supersedes/Extends:** `specs/02-layered-rectangular-architecture.md`

---

## 1. Executive Summary & Design Goals

Feedback on SPEC-02 identified three critical architectural requirements:
1. **Horizontal Node Peers (Same Layer = Same Floor):** Components belonging to the same architectural tier (such as physical/virtual worker nodes, their kubelets, container runtimes, and node daemonsets) must reside on the **same horizontal floor tray** as lateral peers, rather than being stacked vertically like floors in a building. Vertical elevation in the skyscraper strictly signifies hierarchical layers of control and execution (Clients $\rightarrow$ Gateway $\rightarrow$ API Server/etcd $\rightarrow$ Supervisors $\rightarrow$ Frameworks $\rightarrow$ Worker Deck).
2. **3D Graph Semantic Git-Diff:** Moving beyond simple colored dots to a full 3D spatial expression of a "git diff":
   - **Added (+):** Glowing emerald cuboids with pulsing holographic edge brackets.
   - **Removed / Missing (-):** Semi-transparent wireframe "hollow ghosts" with dashed red contour lines.
   - **Modified / Skewed (~):** Dual-split housing or animated amber caution stripes indicating drift in container image tag, image sha256 digest, or mounted ConfigMap/Secret data hashes.
   - **Interactive 3D Hunk Inspection:** Selecting a drifted component reveals a side-by-side YAML diff card directly anchored in the 3D scene.
3. **Universal Cluster Exporter (Deployable to Arbitrary Kubernetes Clusters):**
   - Provide a zero-dependency discovery CLI (`cluster-vis dump` / `src/ingestion/exporter.py`) that queries any target kubeconfig via the Kubernetes Dynamic API, walking all standard resources, daemonsets, and custom resource definitions (CRDs), scrubbing secrets, computing configuration hashes, and exporting a normalized JSON topology graph.
   - Specify an optional in-cluster CRD operator (`clustervis.io/v1alpha1 ClusterTopologySnapshot`) for continuous real-time topology streaming.

---

## 2. Horizontal Node Peer Architecture (The Worker Deck)

### 2.1 Vertical Layer Stack Hierarchy
The skyscraper maintains vertical tiers exclusively for hierarchical control-plane stages:
- **Tier 5 (Y = +12.0):** Distant Client Horizon (`kubectl`, browser users, CRD watchers).
- **Tier 4 (Y = +9.5):** API Aggregation & Ingress Gateway Tray (`ingress-controller`, `kube-aggregator`).
- **Tier 3 (Y = +7.0):** Kube-API Server Executive Array (2–3 horizontal peer cuboids).
- **Tier 3b (Y = +5.5, Z = -3.5):** etcd Consensus Vault (amber glass tray directly behind/below API servers).
- **Tier 2 (Y = +4.5):** Control Plane Supervisors (`kube-controller-manager`, `kube-scheduler`).
- **Tier 1 (Y = +2.5):** Distributed Framework Operators (KubeRay operator, Ray Head node, Spark driver).
- **Tier 0 (Y = +0.5):** **The Worker Node Deck (Single Wide Architectural Floor Tray)**.

### 2.2 The Worker Node Deck Layout ($Y = +0.5$)
All worker nodes are arranged horizontally along the $X$-axis on a wide rectangular tray (dimensions: width = $10.0 + (N-1) \times 6.0$, depth = $6.5$, height = $0.35$):

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ WORKER NODE DECK (Y = 0.5)                                                                       │
│                                                                                                  │
│  ┌────────────────────────────────────┐             ┌────────────────────────────────────┐       │
│  │ NODE CHASSIS 1 (worker-01)         │             │ NODE CHASSIS 2 (worker-02)         │       │
│  │ X = -4.5                           │             │ X = +4.5                           │       │
│  │                                    │             │                                    │       │
│  │ [ Kubelet ]    [ Containerd ]      │             │ [ Kubelet ]    [ Containerd ]      │       │
│  │                                    │             │                                    │       │
│  │ ── Infrastructure DaemonSets ──    │             │ ── Infrastructure DaemonSets ──    │       │
│  │ [ kube-proxy ] [ cilium/cni ]      │             │ [ kube-proxy ] [ cilium/cni ]      │       │
│  │ [ node-exporter ]                  │             │ [ node-exporter ]                  │       │
│  │                                    │             │                                    │       │
│  │ ── Scheduled Workload Pods ──────  │             │ ── Scheduled Workload Pods ──────  │       │
│  │ [ postgres-primary ] [ redis ]     │             │ [ postgres-replica ] [ ray-worker ]│       │
│  └────────────────────────────────────┘             └────────────────────────────────────┘       │
│                                                                                                  │
│  ◄═════════════════════ CNI / eBPF Lateral Inter-Node Packet Mesh ════════════════════════►      │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Component Sub-Placements within Each Node Chassis
Each node chassis is a beveled sub-tray ($5.2 \times 4.8 \times 0.2$):
1. **Runtime Perimeter (Left Slot):**
   - `Cuboid_Kubelet` at $(-1.8, Y_{node} + 0.2, -1.5)$
   - `Cuboid_Containerd` at $(-0.8, Y_{node} + 0.2, -1.5)$
2. **Infrastructure DaemonSet Bay (Right Slot):**
   - Low-profile cuboids representing daemonsets that run on every node:
     - `kube-proxy` (networking rule sync)
     - `cilium` / `calico` (CNI eBPF packet routing)
     - `node-exporter` (telemetry probe)
3. **Workload Pod Bay (Center/Front Slots):**
   - Scheduled container pods docked in clean slots ($Z = 0.2, 1.2$).
4. **Node Heartbeat Conduits:**
   - From each node's `Kubelet`, an emerald green vertical conduit riser routes directly out the rear edge of the tray, ascending vertically to $Y = 7.0$ and elbowing into the primary API server.
5. **Lateral Inter-Node CNI Conduits:**
   - A low-level horizontal conduit connects the CNI daemonsets across Node 1 and Node 2, visualizing inter-node pod network traffic without going through the control plane.

---

## 3. 3D Semantic Git-Diff Engine

When comparing two clusters (e.g. Cluster Alpha vs Cluster Beta, or Production vs Staging):

### 3.1 Volumetric Shading & Diff Status Tokens
1. **Unchanged / Identical (`identical`):**
   - Standard dark slate PBR material (`#1e293b`) with clean cyan architectural edges.
   - Low visual noise so that changed elements pop immediately.
2. **Added in Peer (`added` / `+`):**
   - Vibrant emerald green cuboid (`#10b981`, emission `#34d399` at $0.8$).
   - Pulsing holographic corner brackets framing the component.
   - Flank label tagged with `+ ADDED`.
3. **Removed / Missing in Peer (`missing` / `-`):**
   - "Ghost Cuboid": Semi-transparent wireframe cage with dashed red edge lines (`#ef4444`, opacity $0.35$).
   - Shows the structural absence of the component in the target cluster.
4. **Modified / Skewed (`version_skew` / `~`):**
   - Amber/gold metallic housing (`#f59e0b`, emission `#fbbf24`).
   - Pulsing yellow hazard stripes along top chamfer edges.
   - Status indicators distinguish the drift category:
     - **Image Tag Drift:** e.g. `v1.36.4` vs `v1.35.8`.
     - **Image Digest Drift:** Different sha256 hashes for the same semantic tag.
     - **Configuration / Env Drift:** Modified `ConfigMap` or `Secret` data hash.

### 3.2 In-Scene 3D Diff Hunk Inspection Cards
Clicking any skewed component displays a floating 3D billboarding HTML diff card:
```diff
--- cluster-alpha/workloads/postgres
+++ cluster-beta/workloads/postgres
@@ spec.template.spec.containers[0] @@
- image: postgres:18.6@sha256:d8a2...
+ image: postgres:18.7@sha256:e4f1...
- env: MAX_CONNECTIONS=100
+ env: MAX_CONNECTIONS=250
```

---

## 4. Universal Cluster Exporter Architecture

To allow `cluster-vis` to visualize any arbitrary live Kubernetes cluster:

### 4.1 Zero-Install CLI Mode: `cluster-vis dump`
A standalone Python module (`src/ingestion/exporter.py`) with CLI invocation:
```bash
python3 -m src.ingestion.exporter --context <kubeconfig-context> --output <filename.json>
```
1. **Discovery & Permissions Check:**
   - Calls `kubectl.api_client.DiscoveryClient` or `api-resources --verbs=list` to discover all installed resource types.
2. **Resource Harvesting:**
   - **Cluster Scoped:** `nodes`, `customresourcedefinitions`, `namespaces`.
   - **Control Plane Status:** Node leases (`coordination.k8s.io`), APIService status, webhooks.
   - **Namespaced Resources:** `pods`, `services`, `daemonsets`, `deployments`, `statefulsets`, `configmaps` (keys & SHA-256 value hashes only; secret contents scrubbed).
   - **CRD Instances:** Dynamically lists instances of known distributed frameworks (`RayCluster`, `SparkApplication`, `PostgresCluster`, `VirtualService`, etc.).
3. **Graph Assembly & Sanitization:**
   - Resolves owner references, pod scheduling bindings (`pod.spec.nodeName`), and service-to-pod endpoint mappings.
   - Computes deterministic node IDs and digests.
   - Sanitizes sensitive environment variables, passwords, and tokens.
4. **Normalization Contract:**
   - Emits a standardized `ClusterGraph` JSON matching `src/ingestion/models.py`.

### 4.2 Optional In-Cluster CRD / Operator Mode (`clustervis.io/v1alpha1`)
For continuous real-time topology streaming:
- CRD: `ClusterTopologySnapshot`
- Controller: Watches K8s API events and maintains an in-memory Cytoscape/Three.js topology graph.
- API: Exposes `GET /api/v1/topology` and a Server-Sent Events (SSE) stream for live updates.

---

## 5. Swarm Work Breakdown (Pantheon Swarm Tasks)

- **[TASK-CV-401]** [Layout: Horizontal Node Deck] Refactor `src/ingestion/layout.py` to position all worker nodes as horizontal peers along $X$ on Tier 0 ($Y = 0.5$), with distinct bays for Kubelet, Containerd, DaemonSets, and Pods.
- **[TASK-CV-402]** [Three.js: Wide Worker Deck Tray] Update `src/scene/layer_trays.ts` to dynamically size the Worker Deck tray to fit $N$ horizontal node chassis.
- **[TASK-CV-403]** [Models & Assets: DaemonSets] Add `Cuboid_DaemonSet` (for `kube-proxy`, `cilium`) in `blender/build_cluster_assets.py` and register in `cluster-kit.glb`.
- **[TASK-CV-404]** [3D Git-Diff Engine] Implement volumetric ghosting (wireframe red for deleted), pulsing green for added, and hazard stripes for modified in `src/scene/cluster_viewport.ts`.
- **[TASK-CV-405]** [Interactive 3D Diff Hunk Card] Build floating 3D billboarding diff card on component click displaying side-by-side YAML changes.
- **[TASK-CV-406]** [Universal Cluster Exporter] Author `src/ingestion/exporter.py` supporting dynamic resource extraction from any live cluster context.
- **[TASK-CV-407]** [QA: Automated Tests] Add unit tests verifying horizontal node peer layout, diff classification, and exporter contracts in `tests/`.
- **[TASK-CV-408]** [Visual Verification & Docs] Verify via `browser_vision` on port 5180, update `docs/MAP.md`, Kanban, and commit/push to `origin/main`.
