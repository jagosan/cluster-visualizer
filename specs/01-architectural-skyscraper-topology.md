# SPEC-01: Architectural Skyscraper Topology & Procedural Conduit Stack

## 1. Executive Summary & Vision
This specification re-architects Cluster Visualizer (`cluster-vis`) from radial/circular node arrangements into a **stylized architectural "skyscraper" / layered apartment-building topology**, directly mirroring the visual language of Peter Gostev's Transformer vs. DeepSeek 3D comparison explorer.

Instead of floating circles in space:
- **Left Tower (Vanilla Kubernetes / "Original Paper")**: Represents a classic base Kubernetes cluster as an elegant vertical architectural tower with distinct modular floors, conduits, and housings:
  1. **Top / Distant Horizon (Client Layer)**: External clients (`kubectl`, user browser, external microservices) issuing queries (e.g. `list pods`, `watch CRDs`).
  2. **Penthouse / Roof (API Aggregation Layer)**: The `kube-aggregator` and fronting ingress proxies routing requests to corresponding API groups.
  3. **Executive Floor (API Server Tier)**: Replicated `kube-apiserver` instances with horizontal inter-server coordination and sync conduits.
  4. **Sub-Floor / Vault (etcd Backing Tier)**: Logically positioned directly *below or behind* the API servers with dedicated bidirectional state-persistence conduits.
  5. **Orchestration Floor (Supervisors)**: `kube-controller-manager` and `kube-scheduler` running continuous control loops against the API servers.
  6. **Compute Floors / Trays (Worker Nodes)**: Vertical stack of node trays, each housing a `kubelet` control station, `containerd` runtime box, `kube-proxy`, and workload pod capsules.
  7. **Vertical Conduits & Pipes**: Glass/metallic pipes routing between floors:
     - Kubelet $\rightarrow$ API Server periodic node lease heartbeats (`NodeStatus`).
     - API Server $\rightarrow$ Kubelet pod specification and execution streaming.
     - Controller Manager $\rightarrow$ API Server reconciliation loops.
- **Right Tower (Extended Cluster / "DeepSeek Additions")**: Represents the modernized / extended cluster (e.g. with Ray, Spark, custom operators):
  - Extends and builds upon the vanilla skyscraper architecture:
    - Extra operator penthouse housing (e.g. KubeRay Operator watching RayCluster CRDs via client-to-API server watch streams).
    - Dedicated distributed framework floors: Ray Head pod, Ray Worker pods with Raylet agents and Plasma Shared Memory Object Store slabs.
    - High-throughput direct lateral/bypass conduits: worker-to-worker point-to-point tensor transfers and distributed shuffle channels bypassing the control plane.
- **Visual Design**: Sleek beveled rectangular trays, semi-translucent glass housings, vertical conduit pipes running along the facade and core shafts, and glowing animated particle pulses traveling through pipes.

---

## 2. Layer & Elevation Architecture

### 2.1 Vertical Elevation Coordinates ($Y$-axis)
Both towers share a consistent vertical spatial scale, allowing direct horizontal alignment during side-by-side comparison:

| Elevation ($Y$) | Level Name | Component Description | Visual Housing |
| :--- | :--- | :--- | :--- |
| **+10.0 to +12.0** | **Client Layer (Distant Horizon)** | `kubectl CLI`, Web Browsers, External Integrations (`watch pods`, `list crds`) | Floating holographic console slabs |
| **+7.5 to +8.5** | **Ingress & API Aggregation** | `kube-aggregator`, Ingress Controllers, Gateway API | Glass canopy / penthouse roof tray |
| **+5.5 to +6.5** | **API Server Core** | `kube-apiserver` (horizontal replicated array: cp-0, cp-1, cp-2) | Central control floor with inter-server sync pipes |
| **+4.0 to +4.8** | **Control Plane Vault (etcd)** | `etcd-0`, `etcd-1`, `etcd-2` (raft consensus quorum) | Reinforced vault boxes positioned *behind/below* API servers ($Z = -3.5$) |
| **+3.0 to +4.0** | **Controller & Scheduler Suite** | `kube-controller-manager`, `kube-scheduler`, Cloud Controller | Lateral wings connected via core control conduits |
| **+1.5** | **Framework Extension Floor** *(Extended Tower only)* | KubeRay Operator, Spark Operator, CRD Controllers | Added intermediate extension floor with CRD watch conduits |
| **0.0 to -4.0** | **Worker Node Skyscraper Floors** | Node Trays (`worker-0`, `worker-1`, ...). Each floor contains `kubelet`, `containerd`, pod capsules | Stacked modular trays with glass balustrades & vertical risers |
| **-5.0** | **Foundation / Physical Infra** | Physical / Virtual Node Hardware substrate & CNI Underlay | Heavy brushed slate foundation slab |

---

## 3. Conduits, Piping & Data Flow Specifications

### 3.1 Conduit Geometries & Routing
Conduits are 3D cylindrical pipes (or multi-pipe bundles) connecting functional components:
1. **Heartbeat Riser (Kubelet $\rightarrow$ API Server)**:
   - Originates from each worker node's `kubelet` module.
   - Runs along the external vertical conduit shaft up to the API Server core floor.
   - Flow: Animated teal/green pulses pulsing every 10s (or accelerated in simulation) representing node lease renewals.
2. **Control Loop Shaft (Controller/Scheduler $\leftrightarrow$ API Server)**:
   - Direct short-run high-frequency conduits between supervisors and API server.
   - Flow: Rapid bi-directional cyan particle pulses.
3. **etcd Raft & Storage Core (API Server $\leftrightarrow$ etcd)**:
   - Heavy industrial conduits dropping vertically and backward from API servers into the `etcd` vault below/behind.
   - Inter-etcd horizontal consensus rings connecting etcd peers.
4. **API Server Horizontal Peering (API Server $\leftrightarrow$ API Server)**:
   - Lateral bridge pipes syncing watch broadcasts, aggregator dispatch, and endpoint routing.
5. **Distant Client Query Streams (Client Horizon $\rightarrow$ API Aggregation $\rightarrow$ API Server)**:
   - Long-span elevated optic beams/conduits dropping down from the distant client horizon into the top aggregation penthouse.
   - Flow: Amber/gold pulses representing requests (`GET /api/v1/pods`, `WATCH /apis/ray.io/v1/rayclusters`).
6. **Distributed Framework High-Speed Bypass (Worker $\leftrightarrow$ Worker)** *(Extended Tower only)*:
   - Lateral external conduits running between Ray worker pods or Plasma object stores for node-to-node tensor streaming, bypassing the control plane entirely.

---

## 4. Blender 3D Procedural Assets Update (`cluster-kit.glb`)
The procedural asset generator (`blender/build_cluster_assets.py`) must be upgraded to generate the skyscraper components:
- `Skyscraper_FloorTray`: Sleek beveled rectangular node platform with LED perimeter rim.
- `Skyscraper_Penthouse`: Glass-paneled top enclosure for API aggregation.
- `ControlPlane_Vault`: Heavy metallic enclosure with cooling ribs for `etcd` storage.
- `Module_Kubelet`: Compact control terminal box with pulse transmitter antenna.
- `Module_Containerd`: Precision container runtime housing with socket ports.
- `Module_PodCapsule`: Pill/capsule container with workload status glow.
- `Conduit_VerticalShaft`: Modular vertical pipe riser section.
- `Conduit_Elbow`: 90-degree curved conduit connector for architectural routing.
- `Client_Slab`: Floating minimalist terminal pad representing remote client tooling.

---

## 5. Ingestion & Layout Engine Redesign (`src/ingestion/layout.py`)
- Replace the legacy radial/polar coordinates with a **Skyscraper Floor & Conduit Matrix**:
  - Assign components strictly to vertical levels ($Y$) and structured grid cells ($X, Z$).
  - Calculate 3D bezier waypoints for all conduit pipes (origin, elbow turn, vertical shaft, destination).
  - Compute distinct left-tower vs. right-tower lateral offsets ($X_{\text{base}} = -14.0$ for Left, $+14.0$ for Right).

---

## 6. Implementation Phasing & Task Graph
- **Phase 1: 3D Procedural Building Assets** (`TASK-CV-201`): Update Blender script to generate skyscraper floor trays, etcd vault, client slabs, and modular conduit geometry into `cluster-kit.glb`.
- **Phase 2: Skyscraper Spatial Layout Engine** (`TASK-CV-202`): Overhaul `src/ingestion/layout.py` to assign skyscraper floors, behind/below etcd coordinates, and conduit bezier spline paths.
- **Phase 3: Control Plane Core & Conduit Mesh Riser** (`TASK-CV-203`): Build Three.js conduit renderer in `src/scene/` supporting rigid/curved piping with glowing shaders.
- **Phase 4: Remote Clients & Heartbeat Pulse Streams** (`TASK-CV-204`): Implement distant client holographic slabs and animated heartbeat/watch particle streams along conduits.
- **Phase 5: Extended Tower (Ray / Spark) Integration** (`TASK-CV-205`): Implement framework extension floor, Raylet/Plasma object store layers, and direct bypass conduits.
- **Phase 6: Verification & Dual-Viewport Polish** (`TASK-CV-206`): Ensure synchronized camera orbit framing captures both skyscrapers, inspection drawer accurately selects floor modules, and automated tests pass.

---

## 7. Acceptance Criteria & Quality Gates
1. **Architectural Form Factor**: The 3D scene renders as two distinct, upright architectural towers/skyscrapers, not scattered circles.
2. **Control Plane Fidelity**:
   - `kube-apiserver` sits on a dedicated executive tier with visible inter-server horizontal peering conduits.
   - `etcd` sits logically *below or behind* the API servers with dedicated storage conduits.
   - API aggregation server (`kube-aggregator`) sits at the penthouse/top level.
3. **Worker Node Internal Hierarchy**:
   - Each worker node is a distinct building floor/tray.
   - Within each tray, `kubelet` and `containerd` are cleanly separated modular assets.
   - Workload pods reside within the floor boundary.
4. **Conduit & Flow Fidelity**:
   - Vertical conduit pipes connect `kubelet` on worker floors back up to the API servers with visible periodic heartbeat pulses.
   - Distant client slabs at the top horizon fire request pulses (`list pods`, `watch CRDs`) down into the aggregation server.
5. **Vanilla vs. Extended Contrast**:
   - Left tower reflects the clean vanilla Kubernetes stack.
   - Right tower extends the building with the Ray/Spark extension floor, operator penthouse, and direct bypass data pipes.
6. **No Regressions**:
   - Dual-viewport camera sync, hover tooltips, click-to-diff inspection drawer, and testbed data bundles continue to work flawlessly.
