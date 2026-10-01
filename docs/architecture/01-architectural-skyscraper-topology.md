# Architectural Blueprint: Skyscraper Topology & Procedural Conduit Stack

## 1. System Overview & Aesthetic Model
This blueprint defines the transformation of the Kubernetes 3D visualization model from radial polar clusters into a **hierarchical architectural skyscraper / layered building structure**, directly inspired by the Peter Gostev Transformer vs. DeepSeek 3D comparison explorer.

```
                           [ Distant Clients: kubectl, web, crd-watchers ]
                                                │ (HTTPS/gRPC)
                                                ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │                                    PENTHOUSE ROOF                                      │
  │                  API Aggregation Layer (kube-aggregator & Ingress Gateways)            │
  └─────────────────────────────────────────────┬──────────────────────────────────────────┘
                                                │
                                                ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │                                EXECUTIVE CONTROL FLOOR                                 │
  │                kube-apiserver [0] <─────────> kube-apiserver [1]                        │
  │                                 (Inter-Server Peering)                                 │
  └───────────────┬─────────────────────────────┬──────────────────────────┬───────────────┘
                  │                             │ (Consensus Pipes)        │
                  │ (Supervision)               ▼                          │ (Supervision)
                  │                  ┌──────────────────────┐              │
                  ▼                  │  CONTROL PLANE VAULT │              ▼
      ┌───────────────────────┐      │    etcd [0..2]       │   ┌─────────────────────┐
      │ kube-scheduler        │      │ (Logically Behind /  │   │ kube-controller-mgr │
      │ (Leader-elected loop) │      │  Below API Servers)  │   │ (Reconcile loops)   │
      └───────────────────────┘      └──────────────────────┘   └─────────────────────┘
                  │                                                        │
                  └─────────────────────────────┬──────────────────────────┘
                                                │
                    (Vertical Heartbeat & Spec Conduit Riser)
                                                │
                                                ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │                           WORKER FLOOR 1 (node-worker-0)                               │
  │   [Kubelet Module] ──────> [Containerd Runtime] ──────> [Pod Capsules: PG, App, CNI]   │
  │          │                                                                             │
  │          └───(Heartbeat Pipe Riser to API Server)───────────────────────────────────────┤
  └────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │                           WORKER FLOOR 2 (node-worker-1)                               │
  │   [Kubelet Module] ──────> [Containerd Runtime] ──────> [Pod Capsules: Redis, App]      │
  │          │                                                                             │
  │          └───(Heartbeat Pipe Riser to API Server)───────────────────────────────────────┤
  └────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │                         FRAMEWORK EXTENSION FLOOR (Extended Tower)                     │
  │   [KubeRay Operator] ────> [Ray Head Pod] <====(Tensor Direct Pipes)====> [Ray Workers]│
  │   [Plasma Memory Store] ─> [Object Store Slabs]                                        │
  └────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Spatial Floorplan & Elevation Matrix

The vertical coordinate ($Y$) anchors each floor, while the depth coordinate ($Z$) separates foreground operations (workloads and controllers) from background vaults (`etcd`).

```
Y = +11.0 ─ Remote Clients Slab (Z = +10.0, elevated and set back)
             │
Y = +8.0  ─ API Aggregation & Ingress Penthouse (Z = 0.0)
             │
Y = +6.0  ─ kube-apiserver Core Floor (X = -2.0 to +2.0, Z = 0.0)
             └───> etcd Vault (Y = +4.5, Z = -3.8) [Logically Behind / Below]
             │
Y = +4.5  ─ Supervisors (Scheduler at X = -4.5, Controller Manager at X = +4.5)
             │
Y = +2.0  ─ Framework Floor (Ray Head / Workers / CRD Operator) [Extended Tower]
             │
Y =  0.0  ─ Worker Node Floor 0 (Kubelet, Containerd, Workloads)
             │
Y = -2.5  ─ Worker Node Floor 1 (Kubelet, Containerd, Workloads)
             │
Y = -5.0  ─ Substrate / Foundation (Physical / VM Host & CNI Fabric)
```

---

## 3. Conduit & Pipe Routing Mechanics

Conduits are rendered as 3D tubular glass-metallic geometries using Three.js `TubeGeometry` driven by 3D cubic Bezier spline curves (`CubicBezierCurve3`):

1. **Riser Pipe (Heartbeat)**:
   - Starts at `Kubelet` on Floor $k$ ($X = -3.0, Y = Y_k, Z = 0.0$).
   - Extends outward to the external vertical pipe chase ($X = -4.2, Y = Y_k, Z = 0.0$).
   - Runs vertically straight up to API server floor ($Y = 6.0$).
   - 90-degree bend into `kube-apiserver` intake port ($X = -1.5, Y = 6.0, Z = 0.0$).
2. **etcd Backing Conduits**:
   - Drops vertically from each API server box ($Y = 6.0, Z = 0.0$) down and back to the etcd vault ($Y = 4.5, Z = -3.8$).
   - Continuous rapid amber pulses visualize persistent key-value write transactions and raft sync.
3. **Distant Client Streams**:
   - Long curved spline originating from floating remote client slabs ($Y = 11.0, Z = 12.0$) arching down into the penthouse roof aggregation funnel ($Y = 8.0, Z = 0.0$).
   - Golden particle streams fire when client operations (e.g. `kubectl get pods`, `watch CRDs`) occur.

---

## 4. Architectural Decision Records (ADRs)

### ADR-01: Orthogonal Skyscraper vs. Radial Topology
- **Context:** The initial prototype laid nodes out in circular concentric rings (polar coordinates), which appeared as "weird circles" and lacked intuitive understanding of Kubernetes control hierarchy.
- **Decision:** Adopt an architectural skyscraper model where height corresponds directly to control plane privilege/supervision, with modular floor trays and visible piping.
- **Consequences:** Eliminates circular ambiguity; matches Peter Gostev's Transformer vs DeepSeek visualization paradigm; provides clean visual distinction between vanilla K8s and framework-extended clusters.

### ADR-02: Placement of etcd Behind and Below API Server
- **Context:** Kubernetes architectural purity dictates that no component talks to etcd except `kube-apiserver`. Putting etcd on the same plane or floating randomly confuses the dependency topology.
- **Decision:** Place `etcd` in a dedicated heavy vault directly *behind* ($Z = -3.8$) and slightly *below* ($Y = 4.5$) the API server core ($Y = 6.0$), with explicit bidirectional storage conduits connecting them exclusively.
- **Consequences:** Enforces the strict rule that etcd is the private backing store of the API server, with zero direct access from workers or clients.

---

## 5. 💡 Note to Future Self: Hosting Portability
- The 3D procedural meshes are authored headlessly in Blender via `bpy` and exported to standard `.glb` format.
- The Three.js WebGL client loads assets via standard HTTP GET, requiring no backend runtime dependency during visualization.
- The spatial layout engine runs both client-side in TypeScript (for instant browser rendering) and server-side in Python (for static JSON graph bundle generation).
- This decoupled design enables static hosting on Cloudflare Pages, S3/CloudFront, or any standard web server without a running Python backend.
