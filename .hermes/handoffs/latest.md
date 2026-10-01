# Milestone Handoff: Cluster Visualizer (`cluster-vis`)

**Date:** 2026-09-30  
**Active Branch / Commit:** `main` (`6c15839`)  
**Status:** Live & Verified  

---

## 1. What Was Delivered & Verified

1. **Dual Kind Kubernetes Testbed:**
   - `kind-cluster-alpha`: Kubernetes v1.36.4 with PostgreSQL 18.6 StatefulSet (primary + 2 replicas), Redis 8.10.2 (3 replicas), and Ray 2.58.0 (head + 3 workers).
   - `kind-cluster-beta`: Kubernetes v1.35.8 with PostgreSQL 17.11 StatefulSet (primary), Redis 7.4.2 (2 replicas), and Apache Spark 4.2.0 (driver + 2 executors).

2. **Headless Blender Procedural Asset Pipeline (`bpy` 4.2):**
   - Procedural 3D model generator: `blender/build_cluster_assets.py` (executed via `/home/jagosan/.hermes/toolchains/bpy_env/bin/python`).
   - Exported binary glTF asset library: `public/assets/cluster-kit.glb` (28.6 KB) with clean PBR materials and 8 distinct named components (`NodeTray`, `ControlPlane_Cube`, `Pod_Cylinder`, `Framework_Ray`, `Framework_Spark`, `Database_Postgres`, `Cache_Redis`, `Conduit_Link`).

3. **Topology Ingestion, Framework Detection & Diff Engine:**
   - `src/ingestion/models.py`: Pydantic models for `ClusterGraph`, `NodeComponent`, `DataFlowEdge`, `DiffReport`.
   - `src/ingestion/extractor.py`: Live `kubectl` JSON extractor capturing exact images, tags, and sha256 digests.
   - `src/ingestion/frameworks.py`: Specialized detectors for Ray, Spark, PostgreSQL, and Redis.
   - `src/ingestion/differ.py`: Precise semantic version skew, image tag drift, digest drift, and topology diff classifier.
   - `src/ingestion/layout.py`: 3D spatial layout generator placing nodes across elevation tiers ($Y=4.0$ Ingress, $Y=2.5$ Control Plane, $Y=1.0$ Frameworks, $Y=0.0$ Workloads/DB, $Y=-1.5$ Node Tray).
   - `src/ingestion/cli.py`: Ingestion orchestrator exporting `public/data/cluster-alpha.json`, `cluster-beta.json`, and `cluster-diff.json`.

4. **Synchronized Dual-Viewport 3D WebGL Client (Three.js):**
   - Side-by-side interactive viewports with linked OrbitControls camera synchronization.
   - Dynamic curved Bezier data flow streams with animated pulse particles (Postgres WAL replication in amber, Raylet RPC in magenta, Spark shuffle in cyan, etcd writes in emerald).
   - Glowing diff accent rings on meshes (amber for version skew, crimson for missing in peer, emerald for added).
   - Interactive Raycast picking and Component Inspector drawer showing side-by-side version/image/digest comparison tables.
   - Built with Vite and served live at `http://localhost:5180`.

5. **QA & Documentation:**
   - 4/4 passing unit tests in `tests/test_ingestion_and_diff.py`.
   - Operational runbook at `/home/jagosan/obsidian/vault/runbooks/cluster-visualizer-operations.md`.
   - Dedicated Obsidian Kanban board at `/home/jagosan/obsidian/vault/boards/Kanban-Cluster-Visualizer.md` with all 13 tasks marked completed.
   - Remote repository up to date on `origin/main`.
