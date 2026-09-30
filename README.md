# Cluster Visualizer (`cluster-vis`)

Interactive 3D Kubernetes cluster comparison, topology, and data-flow visualization engine. Inspired by high-fidelity 3D architectural explorers, this tool renders side-by-side Kubernetes clusters in interactive 3D, highlights semantic version skews down to container image digests, visualizes distributed frameworks (Ray, Spark) and stateful workloads (PostgreSQL, Redis), and animates dynamic traffic/replication flows.

## Architecture & Specifications

- **Specification:** [`specs/00-system-architecture.md`](specs/00-system-architecture.md)
- **Architecture Blueprint:** [`docs/architecture/00-system-architecture.md`](docs/architecture/00-system-architecture.md)
- **Symbol & File Map:** [`docs/MAP.md`](docs/MAP.md)
- **Project Kanban:** Dedicated board at `Kanban-Cluster-Visualizer.md` in Obsidian vault.

## Tech Stack

- **3D Modeling & Asset Pipeline:** Headless Blender (`bpy` 4.2) procedural asset generator exporting binary glTF (`.glb`).
- **Frontend / 3D Visualization:** Vite, TypeScript, Three.js dual-viewport renderer with linked OrbitControls.
- **Topology & Diff Engine:** Python 3 (Pydantic, PyYAML) with Kubernetes manifest/API extractor and semver diff classifier.
