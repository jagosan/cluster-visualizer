# Symbol & File Map: Cluster Visualizer (`cluster-vis`)

## Specifications & Architecture
- `specs/00-system-architecture.md`: Master specification, data contracts, and acceptance criteria.
- `docs/architecture/00-system-architecture.md`: Architecture blueprint, spatial layout, data flows, and hosting portability.
- `specs/01-architectural-skyscraper-topology.md`: Skyscraper topology, layered building levels, client horizon, and procedural conduits.
- `docs/architecture/01-architectural-skyscraper-topology.md`: Skyscraper architectural blueprint, spatial elevation matrix, and conduit ADRs.
- `specs/02-layered-rectangular-architecture.md`: Master specification for Transformer/DeepSeek-style 3D layered rectangular architecture.
- `docs/architecture/02-layered-rectangular-architecture.md`: Blueprint and design specifications for layer trays and component cuboids.
- `specs/03-horizontal-node-peers-and-diff-engine.md`: Master specification for horizontal node peers, 3D semantic git-diff engine, and universal cluster exporter.
- `docs/architecture/03-horizontal-node-peers-and-diff-engine.md`: Blueprint for single worker deck layout, volumetric diffing, and export CLI.
- `specs/04-in-cluster-streaming-operator.md`: Optional in-cluster CRD (`clustervis.io/v1alpha1`) & real-time SSE topology streaming operator.
- `specs/05-time-travel-topology-scrubber.md`: Time-travel cluster topology playback, delta recording, and HUD scrubber controls.
- `docs/MAP.md`: This symbol and directory reference map.

## 3D Asset Pipeline (Blender `bpy`)
- `blender/build_cluster_assets.py`: Headless Blender script generating procedural models with PBR materials.
- `public/assets/cluster-kit.glb`: Exported binary glTF asset library containing:
  - `LayerTray_WorkerDeck`: Wide horizontal base tray for N worker node peers.
  - `Cuboid_DaemonSet`: Infrastructure daemonset module (kube-proxy, cilium, node-exporter).
  - `Cuboid_APIServer` / `Cuboid_etcd` / `Cuboid_Supervisor`: Control plane cuboids.
  - `Framework_Ray` / `Framework_Spark`: Distributed framework operator and worker meshes.
  - `Database_Postgres` / `Cache_Redis`: Data layer workload meshes.

## Ingestion & Graph Engine (Python)
- `src/ingestion/models.py`: Pydantic models for `ClusterGraph`, `NodeComponent`, `DataFlowEdge`, `DiffReport`.
- `src/ingestion/extractor.py`: Static Kubernetes manifest topology extractor.
- `src/ingestion/exporter.py`: Universal dynamic cluster exporter CLI (`cluster-vis dump`) querying live kubeconfigs.
- `src/ingestion/frameworks.py`: Specialized detectors for Ray, Spark, PostgreSQL, and Redis CRDs and workloads.
- `src/ingestion/differ.py`: Side-by-side graph diff classifier comparing two clusters.
- `src/ingestion/layout.py`: Spatial layout generator for horizontal worker deck ($Y = 0.5$) and control plane tiers.

## In-Cluster Operator & Streaming Server (Python)
- `deploy/crd/clustervis.io_clustertopologysnapshots.yaml`: CRD manifest for `ClusterTopologySnapshot` (`clustervis.io/v1alpha1`).
- `deploy/operator/operator.yaml`: Kubernetes Deployment, ServiceAccount, ClusterRole, and ClusterRoleBinding for in-cluster operator.
- `src/operator/controller.py`: In-cluster Kubernetes watch informer loop reconciling pods, nodes, and CRDs.
- `src/operator/server.py`: Lightweight HTTP & SSE streaming server (`/api/v1/topology/stream`, `/snapshot`, `/healthz`).

## Frontend WebGL Client (Vite + TypeScript + Three.js)
- `index.html`: Entry HTML with dual viewport split-screen canvas and HUD overlay.
- `src/main.ts`: Application bootstrap, event listeners, and viewport layout controller.
- `src/scene/cluster_viewport.ts`: `ClusterViewport` Three.js scene manager, camera, lighting, and raycaster.
- `src/scene/live_stream.ts`: `LiveStreamManager` SSE client handling reconnection, heartbeat, and real-time topology mutation events.
- `src/scene/layer_trays.ts`: `LayerTrayManager` procedural semi-transparent floor trays and structural tower cage.
- `src/scene/flank_labels.ts`: `FlankLabelManager` typographic billboard sprites floating on tower flanks.
- `src/scene/conduits.ts`: 3D procedural conduit pipe mesh generator and route splines.
- `src/scene/camera_sync.ts`: Synchronous dual-orbit camera controller.
- `src/scene/flow_particles.ts`: GPU / instanced particle system animating traffic and replication streams.
- `src/scene/diff_card.ts`: 3D floating billboarding HTML diff card anchored to drifted components.
- `src/ui/diff_inspector.ts`: Side-by-side comparison drawer, version mismatch highlights, and metric bars.
- `src/ui/cluster_selector.ts`: Dropdown / file loader for switching active clusters.
