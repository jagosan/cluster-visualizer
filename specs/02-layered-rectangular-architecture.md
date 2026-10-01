# SPEC-02: 3D Layered Rectangular Architectural Visualizer (Transformer/DeepSeek Reference)

**Status:** Proposed  
**Author:** Christopher Robin (Lead System Architect) & Jagular (Chunkito 177B Big Iron)  
**Date:** 2026-10-01  
**Target:** `cluster-vis`  
**Reference Art:** [Transformer Architecture vs DeepSeek](https://transformer-architecture.petergostev.chatgpt.site/)

---

## 1. Visual Design Philosophy & Reference Analysis

The goal of this specification is to replace all legacy spherical/radial shapes with a stylized, high-fidelity **3D layered architectural diagram** identical in visual aesthetic to the interactive Peter Gostev *Transformer vs DeepSeek* architecture model.

### 1.1 Key Architectural Elements from Reference Art
1. **Semi-Transparent Rectangular Layer Containers (Trays / Floors):**
   - Each architectural tier is enclosed in a semi-transparent, tinted rectangular open tray (glass floor with low rim walls and subtle edge highlights).
   - Definite, clean vertical spacing (air gaps) between layers.
   - Light pastel/neon glass tints corresponding to functional zones (e.g. soft amber for state/etcd, cool cyan for API servers, violet for supervisors, emerald for worker runtimes).
2. **Component Cuboids (No Circles or Spheres):**
   - Every Kubernetes component is a distinct **rectangular cube / cuboid** (chamfered rectangular blocks) neatly docked inside its respective layer tray.
   - No spheres, cylinders, or circular rings.
3. **Wireframe Bounding Enclosure & Structural Rails:**
   - A subtle wireframe structural cage / corner vertical rails and bracket lines bounding the building stack, matching the Transformer encoder/decoder `Nx` brackets.
4. **Architectural Flank Labels:**
   - Crisp typographic annotations floating on the left and right flanks of the tower, indicating tier names (`Clients`, `API Aggregator`, `API Servers`, `etcd Vault`, `Supervisors`, `Worker Floor 1`, `Worker Floor 2`, etc.).
5. **Vertical & Lateral Conduit Piping with Data Pulses:**
   - Crisp conduit pipes routing between floors:
     - Vertical riser conduits along the building edge carrying Kubelet heartbeats.
     - Drop conduits connecting API servers backward and downward into the etcd vault.
     - Sweeping client request lines arching from distant client slabs into the top API gateway.
     - Inter-API horizontal sync bridges.
     - Direct horizontal tensor bypass pipes connecting Ray Head & Workers (Plasma object store bypass).
6. **Vanilla Kubernetes vs Extended DeepSeek/Ray Analogy:**
   - **Vanilla Kubernetes (Left Tower / Original Paper):** The clean, balanced reference stack (Clients -> Ingress -> API Servers -> etcd -> Supervisors -> Worker Floors).
   - **Extended Kubernetes + Ray (Right Tower / DeepSeek Analogy):** The taller, augmented tower featuring KubeRay operator, Ray Head tray, Ray Worker trays, Plasma shared object stores, and direct lateral high-bandwidth bypass pipes.

---

## 2. Layer Hierarchy & Spatial Layout Matrix

The visualizer represents each cluster as an upright architectural tower centered along the $Y$ axis (elevation):

```
       [ Distant Clients (kubectl / crd-watcher / browser) ]  Y = +12.0
                             │
                             ▼  (Gold Client Conduit)
    ┌─────────────────────────────────────────────────────┐
    │  API Aggregation & Ingress Gateway (Tray)           │  Y = +9.5
    │  [ kube-aggregator ]  [ ingress-controller ]        │
    └─────────────────────────────────────────────────────┘
                             │
                             ▼  (HTTPS / 6443)
    ┌─────────────────────────────────────────────────────┐   ┌──────────────────────────┐
    │  Kube-API Server Level (Cyan Tray)                  │   │ etcd Consensus Vault     │
    │  [ apiserver-1 ] <=======> [ apiserver-2 ]          │==>│ (Amber Glass Tray Behind)│
    └─────────────────────────────────────────────────────┘   │ [etcd-0] [etcd-1] [etcd-2]│  Y = +6.0, Z = -3.5
                             │                                └──────────────────────────┘
                             ▼
    ┌─────────────────────────────────────────────────────┐
    │  Control Plane Supervisors (Violet Tray)            │  Y = +4.5
    │  [ kube-controller-manager ]  [ kube-scheduler ]    │
    └─────────────────────────────────────────────────────┘
                             │
                             ▼
    ┌─────────────────────────────────────────────────────┐
    │  Worker Floor 1 (Emerald Tray)                      │  Y = +1.5
    │  [ Kubelet ]  [ Containerd ]  [ Workload Pods... ]  │
    └─────────────────────────────────────────────────────┘
                             │
                             ▼  (Vertical Heartbeat Riser Pipe)
    ┌─────────────────────────────────────────────────────┐
    │  Worker Floor 2 (Emerald Tray)                      │  Y = -1.5
    │  [ Kubelet ]  [ Containerd ]  [ Workload Pods... ]  │
    └─────────────────────────────────────────────────────┘
                             │
                             ▼
    ┌─────────────────────────────────────────────────────┐
    │  Worker Floor 3 (Emerald Tray)                      │  Y = -4.5
    │  [ Kubelet ]  [ Containerd ]  [ Workload Pods... ]  │
    └─────────────────────────────────────────────────────┘
```

### In Cluster Beta (Extended / DeepSeek Analogy):
Between Supervisors and Worker Floors, or stacked as dedicated execution wings:
- **KubeRay Supervisor Level ($Y = +3.5$)**: KubeRay operator and custom resource definitions.
- **Ray Head Node Tray ($Y = +2.5$)**: GCS server, Dashboard, Ray head process cuboids.
- **Ray Worker Trays ($Y = 0.0, -2.5$)**: Raylet runtime, Plasma Shared Memory object store, and worker actor cuboids.
- **Direct Lateral Bypass Conduits**: Purple conduits connecting Plasma memory stores directly across floors and nodes without traversing the API server.

---

## 3. Component Geometry & Materials Specification

### 3.1 Semi-Transparent Layer Trays (`LayerTray`)
- **Geometry:** Rectangular open tray with beveled edges and low walls:
  - Width: `7.0`, Depth: `4.5`, Height: `0.4`, Wall thickness: `0.1`.
- **Material:**
  - `MeshPhysicalMaterial`:
    - `transmission`: `0.85`
    - `roughness`: `0.15`
    - `ior`: `1.45`
    - `transparent`: `true`, `opacity`: `0.65`
    - `color`: Tinted per zone (Cyan for API, Amber for etcd, Violet for Control, Emerald for Workers, Purple for Ray).
  - Emissive wire rim along top border for glowing architectural contour.

### 3.2 Component Cuboids (`ComponentBox`)
- **Geometry:** Chamfered rectangular box (`BoxGeometry` with dimensions `0.9 x 0.5 x 0.7` for standard pods; `1.1 x 0.6 x 0.8` for API servers and etcd; `0.6 x 0.4 x 0.5` for Kubelet/Containerd modules).
- **Materials:**
  - Standard metallic/roughness PBR materials with subtle top-face emission and micro-chamfer lines.
  - Colors:
    - **APIServer**: Cool metallic cyan (`#0284c7`, emissive `#38bdf8`)
    - **etcd**: Amber gold (`#d97706`, emissive `#fbbf24`)
    - **Supervisors**: Violet (`#7c3aed`, emissive `#a78bfa`)
    - **Kubelet**: Emerald green (`#059669`, emissive `#34d399`)
    - **Containerd**: Dark teal (`#0f766e`, emissive `#2dd4bf`)
    - **Workload Pods**: Database (Postgres indigo `#4338ca`), Cache (Redis crimson `#dc2626`), Frontend (Sky blue `#0284c7`)
    - **Ray Head / Worker**: Electric purple (`#9333ea`, emissive `#c084fc`)
    - **Plasma Store**: Magenta glass cube (`#db2777`, emissive `#f472b6`)

### 3.3 Structural Bounding Frames (`TowerCage`)
- Thin wireframe lines and corner uprights surrounding each tower with subtle repeater brackets (`Nx`) marking the worker node layers, echoing the Transformer encoder/decoder brackets.

### 3.4 Flank Typographic Labels
- Floating HTML/CSS2D text labels or high-res 3D text billboards placed directly beside each layer tray:
  - Left flank: `Distant Clients`, `API Aggregation`, `Kube-API Servers`, `etcd Vault`, `Supervisors`, `Worker Node 1`, `Worker Node 2`...
  - Right flank (Extended): `Ray Cluster`, `Ray Head`, `Plasma Memory`, `Raylet Workers`.

### 3.5 Rigid & Curved Conduits (`ConduitPipes`)
- Clean rectangular or round extruded conduits with 90-degree elbows and smooth Bezier curves:
  - **Heartbeat Risers:** Vertical emerald pipes along the outer edge with periodic pulsing green spheres.
  - **etcd Storage Conduits:** Backward-dropping amber pipes connecting API servers to etcd behind them.
  - **Client Request Streams:** Gold sweeping arches from the high client slab into the API gateway.
  - **Inter-API Bridges:** Horizontal cyan connector tubes.
  - **Plasma Tensor Bypass:** Direct lateral purple conduit connecting Ray worker nodes.

---

## 4. Work Breakdown & Implementation Plan (Swarm Tasks)

- **[TASK-CV-301]** [Procedural Tray & Cuboid Models] Update `blender/build_cluster_assets.py` to produce clean rectangular layer trays (`LayerTray_Control`, `LayerTray_Worker`, `LayerTray_Vault`, `LayerTray_Framework`), rectangular component cuboids (`Cuboid_APIServer`, `Cuboid_etcd`, `Cuboid_Kubelet`, `Cuboid_Containerd`, `Cuboid_Pod`, `Cuboid_Ray`), and export to `cluster-kit.glb`.
- **[TASK-CV-302]** [Skyscraper Layout & Coordinates] Refactor `src/ingestion/layout.py` to place components neatly in grid slots inside each floor tray, with explicit etcd positioning behind/below the API tray and client slabs above.
- **[TASK-CV-303]** [Three.js Layer Trays & Tower Cage] Implement procedural `LayerTrayMesh` and `TowerCage` wireframe brackets in `src/scene/layer_trays.ts` and integrate into `cluster_viewport.ts`.
- **[TASK-CV-304]** [Architectural Flank Labels] Implement flank typographic labels in `src/scene/flank_labels.ts` showing tier names aligned to layer elevations.
- **[TASK-CV-305]** [Conduits & Pulsing Streams] Update `src/scene/conduits.ts` and `src/scene/flow_particles.ts` to route along rectangular and curved architectural channels.
- **[TASK-CV-306]** [Testbed & Workload Ingestion] Re-extract and update `cluster-alpha.json` (vanilla) and `cluster-beta.json` (extended Ray/Spark).
- **[TASK-CV-307]** [Automated QA & Unit Tests] Add unit tests in `tests/test_ingestion_and_diff.py` verifying tray bounds, cuboid coordinates, and conduit routes.
- **[TASK-CV-308]** [Visual Verification & Documentation] Verify via `browser_vision` against the reference image, update `docs/MAP.md`, Kanban, and commit/push.
