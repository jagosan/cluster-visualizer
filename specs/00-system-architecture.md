# SPEC-00: Cluster Visualizer (Kubernetes 3D Comparison & Dependency Engine)

## 1. Executive Summary & Vision
**Cluster Visualizer** (`cluster-vis`) is a high-fidelity interactive 3D topology and diff visualization engine inspired by modern architectural explorers (e.g., Peter Gostev's Transformer Architecture 3D explorer). It ingests live or static manifests/snapshots from any two arbitrary Kubernetes clusters (including local Kind testbeds `cluster-alpha` and `cluster-beta`), constructs a normalized directed dependency and data-flow graph across control plane, system components, custom resources, frameworks (Ray, Spark), and stateful workloads (PostgreSQL, Redis), renders them in 3D using programmatic Blender asset pipelines exported to binary glTF/GLB with Three.js WebGL client-side rendering, and provides synchronous dual-viewport side-by-side inspection, component version diffing, and animated traffic/data flow simulation.

---

## 2. Core Requirements & Non-Negotiable Contracts

1. **Arbitrary Dual-Cluster Comparison:**
   - Ingest any two cluster snapshots via live `kubeconfig` contexts or offline sanitized YAML/JSON snapshot bundles.
   - Support heterogeneous setups (e.g. EKS vs. GKE, On-prem K3s vs. Talos, v1.28 vs v1.31).
2. **Exact Semantic Version & Image Digest Tracking:**
   - Every single node, daemon, control plane binary (`kube-apiserver`, `etcd`, `coredns`, CNI), and workload container must extract precise semver, image tag, and sha256 digest.
   - Version diffing must distinguish: Match (identical version), Semantic Minor/Patch skew (yellow), Major breaking skew (orange), Missing/Added (green/red), and Container Drift.
3. **Workloads & Distributed Framework Ingestion:**
   - Deep inspection of standard workloads: Deployments, StatefulSets, DaemonSets, Services, Ingresses, PVCs.
   - First-class framework support:
     - **Ray:** RayCluster CRDs (head, workers, GCS, Raylet, object store memory).
     - **Spark:** SparkApplication CRDs (driver, executors, shuffle service).
     - **Data stores:** PostgreSQL (operator CRDs / StatefulSets, primary-replica replication streams), Redis (Sentinel, Cluster nodes, standalone).
4. **Data Flow & Dependency Graph Extraction:**
   - Dependency types:
     - Control Plane supervision (`API Server` -> `Kubelet`).
     - Network / Ingress routing (`Ingress` -> `Service` -> `Pods`).
     - State attachment (`Pod` -> `PVC` -> `PV` / `StorageClass`).
     - Distributed framework data flow (`Ray Driver` -> `Ray Workers`, `Spark Driver` -> `Executors`).
     - Database replication streams (`PG Primary` -> `PG Replica`).
5. **Headless Blender 3D Asset Pipeline (`bpy`):**
   - High-precision programmatic mesh generator authored in headless Python via `bpy` (running in `/home/jagosan/.hermes/toolchains/bpy_env`).
   - Clean PBR materials, distinct isometric visual language for Kubernetes layers (Control Plane, Compute Nodes, Network Plane, Frameworks, Workloads).
   - Export optimized binary `.glb` asset packages (`public/assets/cluster-kit.glb`) with verified node hierarchies and collision/pick bounds.
   - Enforce headless execution standards: `sys.stdout.flush()`, `sys.stderr.flush()`, and `os._exit(0)`.
6. **Side-by-Side Synchronous 3D WebGL Explorer:**
   - WebGL Three.js client with split-screen dual viewports (Cluster A vs Cluster B) or unified comparative overlay mode.
   - Synchronous camera orbit, pan, and zoom controls (toggleable link).
   - Component click inspection drawer showing YAML diffs, version deltas, resource allocation (CPU/Memory/GPU), and dependency traces.
   - Animated particle pulses showing active data flows and replication streams.

---

## 3. High-Level Architecture & Layer Decomposition

```
[ K8s Live API / kubeconfig ]        [ Sanitized Snapshot Bundles (JSON/YAML) ]
                 │                                        │
                 └──────────────┬─────────────────────────┘
                                ▼
         ┌──────────────────────────────────────────────┐
         │       K8s Cluster Ingestion Engine           │
         │   (Python / client-go / pyyaml / pydantic)   │
         │  - Discovery API & CRD Schema Introspection  │
         │  - Exact Semver / Digest Extraction         │
         │  - Ray / Spark / PG / Redis Graph Extractors │
         └──────────────────────┬───────────────────────┘
                                ▼
         ┌──────────────────────────────────────────────┐
         │        Unified Topology & Diff Graph         │
         │          (ClusterGraph Schema v1)            │
         │  - Nodes, Components, Workloads, Links       │
         │  - Graph Diffing Engine (Delta Classifier)   │
         └──────────────┬───────────────────────────────┘
                        │
       ┌────────────────┴──────────────────┐
       ▼                                   ▼
┌──────────────────────────────┐  ┌──────────────────────────────────┐
│  Headless Blender Pipeline   │  │   Interactive Three.js Client    │
│    (bpy 4.2 / EEVEE/Cycles)  │  │   (Vite + TypeScript + Three.js) │
│ - Procedural Mesh Generators │  │ - Dual Viewport Orbit Sync       │
│ - PBR Material Baking        │  │ - 3D Node & Pulse Instancing     │
│ - glTF/GLB Asset Exporter    │──► - Raycast Selection & Diff Drawer│
│   (`cluster-kit.glb`)        │  │ - Data-flow Particle Streams     │
└──────────────────────────────┘  └──────────────────────────────────┘
```

---

## 4. Graph Data Contract (`ClusterGraph` Schema v1)

```json
{
  "$schema": "https://cluster-vis.jagosan.com/schemas/cluster-graph-v1.json",
  "metadata": {
    "cluster_name": "prod-us-west-2",
    "kubernetes_version": "v1.31.1",
    "distribution": "EKS",
    "timestamp": "2026-09-30T19:00:00Z"
  },
  "nodes": [
    {
      "id": "cp-apiserver",
      "layer": "control-plane",
      "kind": "APIServer",
      "name": "kube-apiserver",
      "namespace": "kube-system",
      "version": "v1.31.1",
      "image": "registry.k8s.io/kube-apiserver:v1.31.1",
      "digest": "sha256:4a8b...",
      "status": "Healthy",
      "metrics": { "cpu_cores": 4, "memory_gb": 16 },
      "spatial": { "x": 0.0, "y": 2.5, "z": 0.0, "asset_type": "cube_control_plane" }
    }
  ],
  "edges": [
    {
      "source": "ingress-public",
      "target": "svc-frontend",
      "flow_type": "traffic",
      "protocol": "HTTPS/443",
      "direction": "unidirectional",
      "animated": true
    },
    {
      "source": "ray-head",
      "target": "ray-worker-0",
      "flow_type": "framework_control",
      "protocol": "gRPC/10001",
      "direction": "bidirectional",
      "animated": true
    },
    {
      "source": "pg-primary-0",
      "target": "pg-replica-0",
      "flow_type": "data_replication",
      "protocol": "PostgreSQL/5432",
      "direction": "unidirectional",
      "animated": true
    }
  ],
  "diff_summary": {
    "identical_nodes": 42,
    "version_skew_nodes": 5,
    "missing_in_target": 2,
    "added_in_target": 3
  }
}
```

---

## 5. Sub-Agent Implementation Phases (Pantheon Swarm)

1. **Phase 1: Project Scaffolding, Schemas & Mock Fixtures (`@tigger`):**
   - Repository structure, Vite + TypeScript setup, Python ingestion virtualenv, test fixtures for two distinct clusters (e.g., `prod-us-east` vs `staging-us-west`).
2. **Phase 2: Headless Blender Asset Pipeline (`@tigger` + `bpy`):**
   - Script `blender/build_cluster_assets.py` using `/home/jagosan/.hermes/toolchains/bpy_env/bin/python`.
   - Generates procedural 3D components: Control plane cubes, compute node trays, pod cylinders, framework badges (Ray hexagon, Spark gear, Postgres database drum, Redis cylinder stack), network conduits.
   - Exports `public/assets/cluster-kit.glb`.
3. **Phase 3: Topology Ingestion & Diff Engine (`@tigger`):**
   - Python parsing modules: `k8s_extractor.py`, `framework_detectors.py` (Ray, Spark, Postgres, Redis), and `diff_classifier.py`.
   - Graph layout generator (hierarchical layered isometric coordinates).
4. **Phase 4: Side-by-Side 3D WebGL Client (`@tigger`):**
   - Three.js dual-viewport renderer with linked orbit controls.
   - GLB mesh instancing and spatial node positioning.
   - Dynamic particle stream shader for data flows.
   - Interactive raycast hover, click selection, and comparative diff inspector overlay.
5. **Phase 5: Verification, Security & Runbook (`@piglet`, `@eeyore`, `@pooh`):**
   - Test matrices, headless render validations, security audits, and Obsidian runbook ingestion.

---

## 6. Acceptance Criteria

- [ ] Repository initialized cleanly with git remote tracking `origin/main`.
- [ ] Headless Blender script executes in `bpy_env` and outputs valid, non-zero `public/assets/cluster-kit.glb` with verified mesh objects.
- [ ] Ingestion engine successfully parses Kubernetes manifests / CRDs and produces valid `ClusterGraph` JSON with exact image tags and digest strings.
- [ ] Diff engine categorizes version skews, missing components, and framework status.
- [ ] Three.js WebGL application serves a responsive 60fps side-by-side interactive 3D viewport with synchronized rotation, camera framing, and click-to-inspect diff drawers.
