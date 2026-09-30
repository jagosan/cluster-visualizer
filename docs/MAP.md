# Symbol & File Map: Cluster Visualizer (`cluster-vis`)

## Specifications & Architecture
- `specs/00-system-architecture.md`: Master specification, data contracts, and acceptance criteria.
- `docs/architecture/00-system-architecture.md`: Architecture blueprint, spatial layout, data flows, and hosting portability.
- `docs/MAP.md`: This symbol and directory reference map.

## 3D Asset Pipeline (Blender `bpy`)
- `blender/build_cluster_assets.py`: Headless Blender script generating procedural models with PBR materials.
- `public/assets/cluster-kit.glb`: Exported binary glTF asset library containing:
  - `NodeTray`: Base physical / VM node platform.
  - `ControlPlane_Cube`: API server / etcd high-density core.
  - `Pod_Cylinder`: Standard container pod capsule.
  - `Framework_Ray`: Hexagonal Ray head / worker node.
  - `Framework_Spark`: Gear-shaped Spark driver / executor.
  - `Database_Postgres`: Tiered database drum with replication indicator.
  - `Cache_Redis`: Segmented memory cylinder.
  - `Conduit_Link`: Flow pipeline connector.

## Ingestion & Graph Engine (Python)
- `src/ingestion/models.py`: Pydantic models for `ClusterGraph`, `NodeComponent`, `DataFlowEdge`, `DiffReport`.
- `src/ingestion/extractor.py`: Kubernetes manifest / API extractor extracting exact images, tags, and sha256 digests.
- `src/ingestion/frameworks.py`: Specialized detectors for Ray, Spark, PostgreSQL, and Redis CRDs and workloads.
- `src/ingestion/differ.py`: Side-by-side graph diff classifier comparing two clusters.
- `src/ingestion/layout.py`: Spatial layout generator assigning $(X, Y, Z)$ coordinates based on architectural tiers.

## Frontend WebGL Client (Vite + TypeScript + Three.js)
- `index.html`: Entry HTML with dual viewport split-screen canvas and HUD overlay.
- `src/main.ts`: Application bootstrap, event listeners, and viewport layout controller.
- `src/scene/cluster_viewport.ts`: `ClusterViewport` Three.js scene manager, camera, lighting, and raycaster.
- `src/scene/camera_sync.ts`: Synchronous dual-orbit camera controller.
- `src/scene/flow_particles.ts`: GPU / instanced particle system animating traffic and replication streams.
- `src/ui/diff_inspector.ts`: Side-by-side comparison drawer, version mismatch highlights, and metric bars.
- `src/ui/cluster_selector.ts`: Dropdown / file loader for switching active clusters.
