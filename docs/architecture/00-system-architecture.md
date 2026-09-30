# Architecture Blueprint: Cluster Visualizer (3D Kubernetes Comparison Engine)

## 1. System Overview & Component Diagram

```mermaid
graph TD
    subgraph Data Sources
        K1[Cluster A: Live kubeconfig / Manifests]
        K2[Cluster B: Live kubeconfig / Manifests]
    end

    subgraph Ingestion & Diff Engine
        IE[K8s Topology Extractor]
        FD[Framework Detector: Ray / Spark / PG / Redis]
        DE[Semantic Version & Digest Diff Engine]
        LG[Layered Spatial 3D Layout Generator]
    end

    subgraph Asset Generation (Blender bpy)
        BL[Headless bpy Pipeline: blender/build_cluster_assets.py]
        GLB[Binary glTF Package: public/assets/cluster-kit.glb]
    end

    subgraph WebGL Client (Three.js / Vite)
        V1[Viewport A: Cluster A 3D Scene]
        V2[Viewport B: Cluster B 3D Scene]
        Sync[Linked OrbitControls & Raycaster]
        DiffHUD[Side-by-Side Diff Inspector & Flow Animator]
    end

    K1 --> IE
    K2 --> IE
    IE --> FD
    FD --> DE
    DE --> LG
    LG --> DiffHUD

    BL --> GLB
    GLB --> V1
    GLB --> V2
    V1 <--> Sync
    V2 <--> Sync
    Sync --> DiffHUD
```

---

## 2. 3D Spatial Layout Convention

To make differences immediately obvious when viewing side by side or overlaid, the 3D scene organizes components across standard vertical elevation tiers (Y-axis) and spatial grids (X-Z planes):

| Elevation Tier ($Y$) | Functional Layer | Components & Representation |
| :--- | :--- | :--- |
| $Y = 4.0\text{m}$ | **Ingress & External Edge** | Cloud LoadBalancers, Ingress Controllers, Gateway API |
| $Y = 2.5\text{m}$ | **Control Plane** | `kube-apiserver`, `etcd`, `coredns`, CNI DaemonSet |
| $Y = 1.0\text{m}$ | **Distributed Frameworks** | RayCluster (Head/Workers), SparkApplication (Driver/Executors) |
| $Y = 0.0\text{m}$ | **Workloads & State** | Deployments, StatefulSets (PostgreSQL primary/replica, Redis) |
| $Y = -1.5\text{m}$ | **Node Infrastructure** | Physical/Virtual Worker Nodes (Tray meshes, CPU/RAM/GPU bars) |

---

## 3. Data Flow & Animation Subsystem

Data flows and operational dependencies are visualized using animated particle curves:
- **Client Traffic (Cyan pulses):** Ingress $\rightarrow$ Service $\rightarrow$ Pod.
- **Framework RPC (Magenta pulses):** Ray Driver $\leftrightarrow$ Raylet Workers; Spark Driver $\leftrightarrow$ Spark Executors.
- **State Replication (Amber streams):** Postgres Primary $\rightarrow$ Replicas; Redis Sentinel heartbeat.
- **Control Plane Heartbeat (Emerald subtle glow):** Node Kubelet $\rightarrow$ API Server.

---

## 4. 💡 Note to Future Self: Hosting Portability

- **Decoupled Architecture:** The Blender 3D asset generation is strictly an offline / build-time pipeline that yields static `.glb` files. The frontend is a static Three.js / Vite bundle that can be hosted on Cloudflare Pages, S3/CloudFront, or any standard static web server without requiring runtime Blender or GPU servers.
- **Ingestion Decoupling:** Cluster snapshots can be pre-generated as standalone `cluster-graph-*.json` files. The frontend can run completely client-side in air-gapped or read-only environments without direct connectivity to Kubernetes API servers.
- **Local vs Cloud Kubernetes Access:** When running locally, a lightweight Python CLI or backend server reads kubeconfigs and writes snapshot JSONs. In remote deployments, Kubernetes in-cluster ServiceAccounts with read-only RBAC can stream cluster state via WebSockets.
