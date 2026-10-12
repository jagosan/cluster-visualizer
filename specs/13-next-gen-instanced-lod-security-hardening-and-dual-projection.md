# SPEC-13: Next-Gen Instanced GPU Pipeline, Semantic LOD, Zero-Trust Hardening & Dual-Projection

**Status:** Proposed  
**Author:** Hermes (Cognitive Systems Architect) & Christopher Robin (Lead Architect)  
**Date:** 2026-10-11  
**Target:** `cluster-vis`  
**Extends:** `specs/00-system-architecture.md`, `specs/04-in-cluster-streaming-operator.md`, `specs/07-portable-helm-packaging-and-latency-topology.md`, `specs/09-pod-autoscaling-morphing-and-kueue-staging.md`, `specs/11-quad-layout-diff-tour-and-latency-springs.md`, `specs/12-viewport-pane-zoom-and-restore.md`

---

## 1. Executive Summary & Design Vision

The fundamental objective of the **Cluster Visualizer (`cluster-vis`)** project is:
> *"To give humans a way to understand cluster topology in a more physical way, by representing complex distributed systems in 3D space."*

While previous specifications established spatial stratification (Skyscraper elevation $Y = -8.5 \dots 12.0$), dynamic conduits, autoscaling queuing harnesses, and quad viewports, rigorous architectural review (Heffalump/DeepSeek-V4 & Hermes, validated by Gemini 3.1 Pro) revealed four critical systemic barriers to large-scale production deployment:
1. **WebGL Rendering Ceiling:** Procedural individual mesh generation (`PodCapsuleManager`, `ConduitManager`) creates 20,000–30,000 draw calls and ~12M duplicated vertices at scale (500+ nodes, 10,000+ pods), degrading rendering performance to 5–15 FPS on standard laptops and causing garbage collection stutter.
2. **Operator Concurrency & Broadcasting Bottleneck:** Python's synchronous `ThreadingHTTPServer` blocks on the Global Interpreter Lock (GIL) when serializing JSON-over-SSE during high pod churn to multiple clients. Furthermore, the round-robin TCP SYN network probe scales as $O(N^2)$, risking conntrack exhaustion on large clusters.
3. **Security & Session Vulnerabilities:** In-browser bearer token retention in `sessionStorage`, wildcard CORS (`*`), and lack of strict whitelist schemas for custom CRD arguments and environment variables risk sensitive credential exfiltration.
4. **Cognitive Occlusion in Incident Triage:** While 3D spatial elevation provides unmatched architectural intuition during capacity planning and topology design, perspective foreshortening and 3D occlusion introduce navigation friction when an on-call SRE needs to isolate a crashing pod instantly.

**SPEC-13 addresses these challenges through four foundational architectural pillars:**
- **Pillar 1: Instanced GPU Rendering & Semantic LOD:** Single-draw-call `THREE.InstancedMesh` pipelines driven by dynamic vertex buffer attributes (`vec4 aInstanceData`), combined with an innovative **Anomaly Outlier Ejection** mechanism (compact aggregated slabs for healthy pods, with autonomous glowing 3D capsules physically ejected only for anomalous/morphing workloads).
- **Pillar 2: Zero-Trust Security & Ingress Hardening:** Complete removal of bearer token entry in the browser, mandatory **OAuth2-Proxy / OIDC Gateway** cookie sessions with HMAC header verification, and strict whitelist-only manifest extraction schemas.
- **Pillar 3: Async Concurrency & Delta Streaming:** Migration of the in-cluster operator to an `asyncio` streaming server with Protobuf-over-WebSocket delta encoding and viewport frustum subscriptions, backed by a scalable **Star-Topology Network Probe** ($O(N)$).
- **Pillar 4: Dual-Projection CAD Mode & Blast Radius Focal Lens:** Keyboard-driven (`KeyF`) smooth camera transition between 3D Isometric Elevation and **2.5D Orthographic Floor-Cut Mode** (zero perspective distortion, CAD architectural gridlines, crisp SVG text overlays), alongside automated dependency blast radius focus.

---

## 2. System Architecture & Component Diagram

```
══════════════════════════════════════════════════════════════════════════════════════════════════════
 1. BROWSER CLIENT GRAPHICS PIPELINE (Vite + TypeScript + Three.js r180)
══════════════════════════════════════════════════════════════════════════════════════════════════════
 ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                                   VIEWPORT DISPLAY & INTERACTION                                 │
 │  ┌──────────────────────────────────────────────────┐  ┌──────────────────────────────────────┐  │
 │  │ 3D PERSPECTIVE ELEVATION                         │  │ 2.5D ORTHOGRAPHIC FLOOR-CUT (KeyF)  │  │
 │  │ (Architectural Review / Capacity / Diff Tour)   │  │ (CAD Planar Grid / SRE Incident Triage)│ │
 │  └──────────────────────────────────────────────────┘  └──────────────────────────────────────┘  │
 ├──────────────────────────────────────────────────────────────────────────────────────────────────┤
 │                                  SEMANTIC LEVEL-OF-DETAIL (LOD)                                  │
 │  ┌──────────────────────────────────────────────────┐  ┌──────────────────────────────────────┐  │
 │  │ HEALTHY WORKLOADS: Aggregated Floor Slabs        │  │ ANOMALY OUTLIER EJECTION:            │  │
 │  │ (1 Instanced Box per Deployment / Namespace)    │  │ (CrashLoop / OOM / Pending / Morph)   │  │
 │  │ Holographic Workload Counter Badge               │  │ Ejected as Autonomous 3D Capsule    │  │
 │  └──────────────────────────────────────────────────┘  └──────────────────────────────────────┘  │
 ├──────────────────────────────────────────────────────────────────────────────────────────────────┤
 │                                 GPU INSTANCED BUFFER PIPELINE                                    │
 │  ┌───────────────────────────────────────────────┐  ┌─────────────────────────────────────────┐  │
 │  │ InstancedPodRenderer:                         │  │ Custom Vertex & Fragment Shaders:       │  │
 │  │ - instanceMatrix (Float32Array transforms)   │  │ - Color & Pulse from aInstanceData.x     │  │
 │  │ - vec4 aInstanceData (Status/CPU/Mem/Diff)   │  │ - VPA Morph Tweens directly on GPU       │  │
 │  └───────────────────────────────────────────────┘  └─────────────────────────────────────────┘  │
 └──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                   ▲
                                     Protobuf / WebSocket Delta Stream
                                                   │
══════════════════════════════════════════════════════════════════════════════════════════════════════
 2. SECURE IN-CLUSTER OPERATOR & INGRESS ARCHITECTURE (clustervis-system)
══════════════════════════════════════════════════════════════════════════════════════════════════════
 ┌─────────────────────────────────────────────┐        ┌───────────────────────────────────────────┐
 │ INGRESS / OAUTH2-PROXY SIDECAR             │        │ OPERATOR ASYNC ENGINE (asyncio/Uvicorn)   │
 │ - OIDC / SSO Session Cookie (HttpOnly)     │───────▶│ - Validates HMAC Signature on Headers     │
 │ - Pins Origin, strict CSP, No Bearer in JS │        │ - Watch Informers (Pods/Nodes/CRDs)       │
 └─────────────────────────────────────────────┘        │ - Whitelist-Only Secret Sanitization      │
                                                        │ - Protobuf Delta Delta Compression Engine │
                                                        └───────────────────────────────────────────┘
                                                                           ▲
                                                         Targeted Probes   │ O(N) Network Telemetry
                                                                           │
                                                        ┌───────────────────────────────────────────┐
                                                        │ STAR-TOPOLOGY PROBE DAEMONSET             │
                                                        │ - Probes Ingress, API Server & AZ Bridges │
                                                        │ - (Optional eBPF passive TCP RTT capture) │
                                                        └───────────────────────────────────────────┘
```

---

## 3. Detailed Technical Requirements & Specifications

### 3.1 GPU Instanced Mesh Architecture (`src/scene/instanced_pod_renderer.ts`)

1. **Draw Call Budget:**
   - Under single, dual, or quad viewport modes, the total draw call count per viewport shall not exceed **30 draw calls** ($\le 120$ draw calls total across a 4-pane matrix).
   - Supports up to **30,000 pods at 60 FPS** on Apple Silicon (M-series) and Intel/AMD integrated GPUs (Radeon 780M/8060S).

2. **Memory Layout & Buffer Attributes:**
   - Pod capsules and node trays shall share a single pre-allocated `THREE.InstancedMesh` per class.
   - Dynamic instance attributes:
     ```ts
     export interface InstanceDataBuffer {
       instanceMatrix: THREE.InstancedBufferAttribute; // 16 floats (4x4 matrix)
       aInstanceData: THREE.InstancedBufferAttribute;  // 4 floats:
                                                       // x: status_code (0=Healthy, 1=CrashLoop, 2=OOM, 3=Pending)
                                                       // y: cpu_utilization_ratio (0.0 - 2.0)
                                                       // z: mem_utilization_ratio (0.0 - 2.0)
                                                       // w: diff_state (0=identical, 1=skew, 2=missing, 3=added)
     }
     ```
   - Status color transitions, glowing alert pulses, and VPA size interpolations are computed directly inside custom vertex/fragment shader chunks (`onBeforeCompile`), eliminating per-frame JavaScript `THREE.Vector3` object allocations.

### 3.2 Semantic Level-of-Detail (LOD) & Anomaly Outlier Ejection (`src/scene/semantic_lod.ts`)

1. **LOD Zoom Levels:**
   - **Level 0 (Global Fleet Zoom-Out, Camera Dist $> 120$):** Namespaces rendered as single volumetric boundary zones; summary health counters displayed via HTML billboard sprites.
   - **Level 1 (Cluster Stratum Zoom, Camera Dist $40 \dots 120$):** Workloads (Deployments, StatefulSets, RayClusters) rendered as unified **Workload Aggregation Slabs**. Pod count, aggregate CPU/memory requests, and status pill badges render on top face.
   - **Level 2 (Inspection Zoom, Camera Dist $< 40$):** Workload slabs dissolve into discrete proportional capsules arranged on node tray slots.

2. **Anomaly Outlier Ejection Contract:**
   - Regardless of current LOD level, if a pod enters an abnormal condition:
     - `pod.status.phase === 'Pending'`
     - `containerStatus.waiting.reason in ['CrashLoopBackOff', 'ImagePullBackOff', 'OOMKilled']`
     - Pod undergoing active VPA resize morph or HPA lateral conveyor transit
   - **Behavior:** The anomalous pod is *physically ejected* from the aggregate slab, rendered as an autonomous, pulsating 3D capsule at its designated spatial node slot with a luminous tractor line connecting to its parent workload.
   - **Guarantees:** SREs immediately perceive single-pod failures in a 10,000-pod cluster without requiring full-scene 1:1 geometry allocation.

### 3.3 Zero-Trust Security & Tiered Ingress Architecture (`src/operator/auth.py`, `charts/clustervis`)

1. **Elimination of Browser Bearer Token Retention:**
   - The UI shall deprecate direct ServiceAccount token pasting in modal dialogs.
   - Authentication must use an upstream **OAuth2-Proxy** sidecar or Ingress controller (Cloudflare Access, Google IAP, Dex, Keycloak).
   - Session tokens are stored in `HttpOnly; Secure; SameSite=Strict` cookies. JavaScript never touches or exposes the token.

2. **Operator Header Authentication Contract:**
   - The operator validates upstream identity headers:
     - `X-Forwarded-User`: Username / email of authenticated operator.
     - `X-Forwarded-Groups`: RBAC groups assigned to the user.
     - `X-Forwarded-Access-Signature`: HMAC-SHA256 signature calculated over the headers using `CLUSTERVIS_PROXY_SHARED_SECRET`.
   - Reject any request lacking a valid HMAC signature when running in `oauth2-proxy` mode.

3. **Whitelist-Only Data Extraction Schema:**
   - The operator's graph serializer (`src/operator/graph_engine.py`) strictly enforces a whitelist schema:
     - **Allowed:** `.metadata.name`, `.metadata.namespace`, `.metadata.labels`, `.spec.replicas`, `.spec.template.spec.containers[].image`, `.spec.template.spec.containers[].resources`, `.status`.
     - **Blocked:** `.spec.template.spec.containers[].env` (all raw values redacted to `sha256:` fingerprints), `.spec.template.spec.containers[].args` (regex redacted for credentials), all `.data` fields in Secrets or ConfigMaps.

### 3.4 Concurrency & Scalable Streaming (`src/operator/server.py`)

1. **Async Server Migration:**
   - Replace Python's synchronous `ThreadingHTTPServer` with an asynchronous ASGI architecture (`asyncio` + `uvicorn`).
   - Broadcasting uses an event-loop non-blocking fan-out queue, preventing the GIL from blocking SSE/WebSocket connections during informer churn.

2. **Frustum & Namespace Subscriptions:**
   - Clients send active subscription filters over WebSocket:
     ```json
     {
       "action": "subscribe",
       "namespaces": ["production", "ml-serving"],
       "lod": "HIGH",
       "viewportFrustum": { "minX": -20, "maxX": 20, "minZ": -15, "maxZ": 15 }
     }
     ```
   - The operator filters mutation events before serialization, reducing network egress bandwidth by $>80\%$.

### 3.5 Network Probe Scaling ($O(N)$ Star-Topology) (`src/probe/main.py`)

1. **Star-Topology Probe Mesh:**
   - Discontinue the unconstrained $O(N^2)$ all-to-all TCP SYN mesh.
   - Adopt a **Star-Topology Network Probe**:
     - Each node probe daemon measures RTT against:
       1. Local Ingress Controller endpoints (Edge ingress latency).
       2. Kubernetes Control Plane API server (Cluster supervisory latency).
       3. One designated bridgehead node per Availability Zone (Cross-AZ transit latency).
   - Complexity is reduced from $O(N^2)$ to $O(N \cdot K)$ where $K \le 5$, scaling smoothly to 5,000+ nodes.

### 3.6 Dual-Projection CAD Mode & Incident Focal Lens (`src/scene/camera_controller.ts`)

1. **Orthographic Floor-Cut Mode (`KeyF`):**
   - Pressing **`KeyF`** toggles between 3D Perspective and 2.5D Orthographic projection:
     - Camera transitions smoothly over 600ms via `THREE.OrthographicCamera`.
     - Flattens perspective foreshortening; renders CAD-style architectural datum lines and floor strata cross-sections.
     - 3D billboard text switches to crisp, non-occluded SVG DOM overlay tags.
2. **Blast Radius Focal Lens:**
   - Clicking any failed workload or pressing `KeyB` activates the Focal Lens:
     - Unrelated cluster components dim to 15% opacity.
     - Upstream ingress conduits, downstream database connections, and hosting node chassis illuminate with an amber/red energy aura.

---

## 4. Architectural Decision Records (ADRs)

### ADR-1301: GPU InstancedMesh vs Individual Procedural Meshes
- **Context:** At 10,000 pods, procedural mesh instantiation results in ~25,000 draw calls and 500MB VRAM footprint.
- **Decision:** Migrate to a unified `InstancedPodRenderer` using `THREE.InstancedMesh` with GPU-side shader attributes (`aInstanceData`).
- **Consequences:** Limits total scene draw calls to $\le 30$ per viewport. Requires custom shader chunks for status colors and VPA morphing, but enables 60 FPS locked performance.

### ADR-1302: Semantic LOD with Anomaly Outlier Ejection
- **Context:** Rendering 1:1 pods chokes WebGL; global bounding boxes hide individual crashing pods.
- **Decision:** Group normal workloads into aggregate slabs, but physically eject anomalous pods (`CrashLoopBackOff`, pending, morphing) as discrete 3D capsules.
- **Consequences:** Best of both worlds: extreme scalability (rendering <500 objects at any time) while guaranteeing zero visual latency on critical alerts.

### ADR-1303: OAuth2-Proxy Sidecar vs Browser TokenReview
- **Context:** Storing raw Kubernetes bearer tokens in `sessionStorage` with CORS `*` is an XSS/reconnaissance vulnerability.
- **Decision:** Deprecate browser token storage. Mandate an OAuth2-Proxy sidecar with `HttpOnly` session cookies and HMAC header verification.
- **Consequences:** Browser JavaScript never touches sensitive credentials. Eliminates CORS risk and aligns with enterprise zero-trust standards.

### ADR-1304: Dual-Projection Perspective/Orthographic CAD Switch (`KeyF`)
- **Context:** Pure 3D excels at architectural depth and capacity planning, but suffers from occlusion during rapid incident triage.
- **Decision:** Provide an instantaneous camera transition to a 2.5D Orthographic architectural plan with CAD overlays.
- **Consequences:** SREs can toggle between spatial depth and planar clarity in one keystroke.

### ADR-1305: $O(N)$ Star-Topology Probe with Optional eBPF
- **Context:** Full-mesh $O(N^2)$ TCP SYN probes overwhelm conntrack tables and trigger IDS alerts.
- **Decision:** Restrict active probing to a star topology (Ingress + API + cross-AZ bridgeheads), with an optional eBPF plugin for deep packet inspection where supported.
- **Consequences:** Scales linearly up to 5,000 nodes without triggering network policy alerts.

---

## 5. Implementation Roadmap & Task Breakdown

| Task ID | Component | Description | Deliverables |
| :--- | :--- | :--- | :--- |
| **TASK-CV-1401** | `InstancedPodRenderer` | Implement `THREE.InstancedMesh` capsule & tray pipeline with `aInstanceData` GPU shader attributes. | `src/scene/instanced_pod_renderer.ts`, custom Three.js shader chunk. |
| **TASK-CV-1402** | `SemanticLodManager` | Build Semantic LOD engine with Anomaly Outlier Ejection for crashing/morphing workloads. | `src/scene/semantic_lod.ts`, LOD distance controller. |
| **TASK-CV-1403** | Operator Async & HMAC | Migrate operator to `asyncio`/Uvicorn, implement HMAC header verification and strict secret whitelist. | `src/operator/server.py`, `src/operator/auth.py`, `src/operator/graph_engine.py`. |
| **TASK-CV-1404** | Star-Topology Probe | Re-architect probe daemon to star-topology targeting Ingress, API, and cross-AZ bridgeheads. | `src/probe/main.py`, Helm chart values update. |
| **TASK-CV-1405** | Dual-Projection CAD Mode | Implement `OrthographicCamera` transition (`KeyF`) with CAD architectural grid and DOM text overlays. | `src/scene/camera_controller.ts`, `src/ui/cad_overlay.ts`. |
| **TASK-CV-1406** | Incident Focal Lens | Build dependency blast-radius focus mode with opacity dimming and illuminated dependency path. | `src/scene/focal_lens.ts`, `KeyB` shortcut. |

---

## 6. Verification & Acceptance Criteria

1. **Performance Validation:**
   - Running a synthetic testbed with 500 nodes and 20,000 pods maintains $\ge 55$ FPS on a reference mid-tier client (e.g. integrated GPU).
   - Total scene draw calls across Quad (4-pane) viewport mode do not exceed 120 draw calls.
2. **Security & Sanitization Verification:**
   - Manifests with sensitive environment variables, connection strings, or annotations verify 100% hash redaction (`sha256:8`) with zero plaintext leaks.
   - Operator rejects unauthenticated requests or requests with forged/missing HMAC proxy headers.
3. **Usability & Dual-Projection Verification:**
   - Pressing `KeyF` smoothly transitions between 3D Perspective and 2.5D Orthographic modes without clipping or camera jumps.
   - Inducing a `CrashLoopBackOff` on a single pod in an aggregated workload slab immediately ejects the pod into 3D space with an amber alert pulse within 500ms of the watch event.
