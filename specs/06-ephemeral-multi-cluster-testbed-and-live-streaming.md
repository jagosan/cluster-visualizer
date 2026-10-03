# SPEC-06: Ephemeral Multi-Cluster Testbed & Live Streaming Topology Matrix

**Status:** Proposed  
**Author:** Christopher Robin (Lead Architect) & 🦉 Owl (Architectural Synthesizer)  
**Date:** 2026-10-02  
**Target:** `cluster-vis`  
**Extends:** `specs/03-horizontal-node-peers-and-diff-engine.md`, `specs/04-in-cluster-streaming-operator.md`, `specs/05-time-travel-topology-scrubber.md`  

---

## 1. Executive Summary & Design Vision

With the 3D Skyscraper layout (SPEC-02/03), the In-Cluster Streaming Operator (SPEC-04), and the Time-Travel Historical Scrubber (SPEC-05) in place, `cluster-vis` needs real-world operational proving grounds. Static JSON bundles and synthetic fixtures allow UI experimentation, but testing live streaming behavior, failovers, dynamic mutations, and multi-version fleet diffing requires **real Kubernetes clusters**.

SPEC-06 defines the **Ephemeral Multi-Cluster Testbed & Live Streaming Topology Matrix**:
1. **Lightweight Ephemeral Cluster Orchestration on Chunkito:** A zero-cloud, multi-cluster management CLI (`cluster-vis testbed`) that leverages Docker on `chunkito` (Ryzen AI Max+ 395 32-core, 128GB unified RAM @ `100.71.183.123`) to stand up, populate, and tear down clusters on demand.
2. **K3d (k3s in Docker) Primary Substrate:** Boots multi-node clusters in 5–8 seconds consuming $<100\text{MB}$ RAM per node without root/KVM requirements, coexisting harmlessly alongside resident big-iron LLM inference.
3. **Live Streaming In-Cluster Operator Integration:** Automated injection of the SPEC-04 `clustervis.io` operator into each ephemeral cluster, streaming live cluster mutation events over SSE directly into the Three.js viewport across Tailscale.
4. **Dual Exploration Modalities:**
   - **Temporal Exploration (Single Cluster Over Time):** Live streaming visualization of rolling deployments, canary split routing, node cordoning/draining, and chaos failure injection with real-time smooth 3D transitions.
   - **Fleet Matrix Exploration (Multiple Clusters Across Versions):** Simultaneous multi-cluster side-by-side or quad-grid visual comparison across Kubernetes minor versions (e.g. `v1.36` Regular vs. `v1.37` Rapid / Edge) to inspect API deprecations, resource allocation differences, and configuration drifts.

---

## 2. Homelab Environment & Substrate Selection

### 2.1 Hardware & Network Topology

| Node | Hardware & OS | Role in Cluster-Vis | Constraints & Isolation |
| :--- | :--- | :--- | :--- |
| **`beehive`** (`100.99.188.15`) | SER8 Mini PC, 14GB RAM, Ubuntu 24.04 | Visualizer Host, Vite dev/preview server (:5180), Hermes Orchestrator | Memory-constrained (14GB total). Avoid running heavy clusters locally. |
| **`chunkito`** (`100.71.183.123`) | Minisforum MS-S1 Max, AMD Ryzen AI Max+ 395 (32 cores), 128GB Unified RAM, 600GB free NVMe | **Cluster Host:** Hosts ephemeral K3d/Kind cluster fleet, workloads, and streaming operators | Docker group accessible without sudo (`docker: ok`). Runs resident llama-server. Zero memory pressure up to 20+ nodes. |

### 2.2 Substrate Evaluation: K3d vs. Kind vs. MicroVMs (Incus/KVM)

| Dimension | **K3d (k3s-in-Docker)** *(Recommended)* | **Kind (k8s-in-Docker)** | **MicroVMs (Incus / Firecracker)** |
| :--- | :--- | :--- | :--- |
| **Startup Velocity** | **5–8 seconds** per 3-node cluster | 30–45 seconds per cluster | 15–30 seconds + cloud-init |
| **RAM Footprint** | **~80–120MB** per node | ~600–900MB per node | 1–2GB per VM (fixed allocation) |
| **Root / Privilege** | **Zero sudo needed** (`docker` group) | Zero sudo needed | Requires `/dev/kvm` + root/sudo |
| **Multi-Node Support** | Native: `--servers 1 --agents 3` | Native via multi-node YAML | Requires bridge setup & storage pools |
| **Version Skew** | Trivially swapped via image tag | Image tag swapped (watch kubeadm API) | Full OS/distro image needed |
| **Teardown** | Clean instant deletion: `k3d cluster delete` | `kind delete cluster` | `incus delete --force` |

**Decision:** **K3d** is the primary driver for rapid spin-up/teardown and multi-cluster matrices. The CLI architecture will include a pluggable driver interface (`ClusterDriver` ABC) so `kind` remains supported for upstream `kubeadm`/`etcd` parity checks.

---

## 3. Ephemeral Testbed Configuration Contract

### 3.1 Declarative Fleet Topology Schema (`testbeds/fleet-spec.yaml`)

```yaml
version: "clustervis.io/v1alpha1"
fleet_name: "homelab-canary-matrix"
host: "chunkito" # Target execution host (via SSH or local)
clusters:
  - name: "stage-regular"
    driver: "k3d"
    kubernetes_version: "v1.36.4-k3s1"
    servers: 1
    agents: 2
    api_port: 64431
    operator:
      enabled: true
      export_interval_seconds: 5
    workloads:
      - "testbeds/workloads/base-monitoring.yaml"
      - "testbeds/workloads/postgres-ha.yaml"

  - name: "prod-regular"
    driver: "k3d"
    kubernetes_version: "v1.36.4-k3s1"
    servers: 1
    agents: 3
    api_port: 64432
    operator:
      enabled: true
      export_interval_seconds: 5
    workloads:
      - "testbeds/workloads/base-monitoring.yaml"
      - "testbeds/workloads/ray-cluster.yaml"
      - "testbeds/workloads/microservices-app.yaml"

  - name: "edge-rapid"
    driver: "k3d"
    kubernetes_version: "v1.37.0-k3s1"
    servers: 1
    agents: 2
    api_port: 64433
    operator:
      enabled: true
      export_interval_seconds: 5
    workloads:
      - "testbeds/workloads/canary-service.yaml"
```

---

## 4. Testbed Manager CLI: `cluster-vis testbed`

Implemented in `src/testbed/manager.py` and exposed via the main CLI entrypoint:

```bash
# Spin up the declared cluster fleet on chunkito
cluster-vis testbed up --config testbeds/fleet-spec.yaml

# Inspect live health, port bindings, and operator stream URLs
cluster-vis testbed status

# Deploy or restart the in-cluster streaming operator across all clusters
cluster-vis testbed deploy-operator --fleet homelab-canary-matrix

# Inject live operational chaos/events to test real-time visualization transitions
cluster-vis testbed inject \
  --cluster stage-alpha \
  --scenario rollout-restart \
  --deployment postgres-master

cluster-vis testbed inject \
  --cluster prod-beta \
  --scenario drain-node \
  --node k3d-prod-beta-agent-1

# Tear down all testbed clusters and prune docker networks
cluster-vis testbed down --config testbeds/fleet-spec.yaml
```

### 4.1 Automated Kubeconfig & Port Mapping
- Each cluster binds its API server to `0.0.0.0:<port>` on Chunkito.
- The manager merges kubeconfig contexts into `~/.kube/config` (or a dedicated `testbeds/kubeconfig.yaml`), replacing `0.0.0.0` with Chunkito's Tailscale IP (`100.71.183.123`).
- Streaming operator endpoints are mapped to predictable ports (e.g. `8081`, `8082`, `8083`) or reverse-proxied via a lightweight SSE router on Chunkito.

---

## 5. Live Streaming Integration & Visualization Iteration

### 5.1 Single Cluster Evolution (Temporal Mode)
When observing a single live cluster:
1. **Live SSE Channel:** Connects to `http://100.71.183.123:<port>/api/v1/topology/stream`.
2. **Pod Scheduling Transition:** When `pod_scheduled` arrives, a translucent green ghost cube spawns above the node and glides down to its exact slot on the Worker Deck tray.
3. **Pod Eviction / Deletion:** The pod turns red wireframe, emits small smoke particles, and collapses into the tray floor.
4. **Node Cordon & Drain:** When a worker chassis enters `SchedulingDisabled`, the worker deck tray for that chassis gains amber hazard stripes; migrating pods dynamically tween across the lateral CNI conduit pipes to adjacent worker chassis.
5. **Real-time Event Marquee:** The HUD event marquee banners each live K8s event with timestamp, reason, and affected component ID.

### 5.2 Multi-Cluster Version Matrix (Fleet Mode)
To iterate on comparing multiple clusters:
1. **Viewport Grid Controller (`src/scene/grid_controller.ts`):** Supports switching between:
   - `Single`: 1 large viewport with deep HUD metrics & live event stream.
   - `Dual Split`: 2 side-by-side synchronized viewports with active volumetric diff highlighting.
   - `Quad Grid (2x2)`: 4 simultaneous miniature viewports rendering 4 clusters across release channels (e.g. Regular v1.36, Rapid v1.37, Alpha/Dev branches).
2. **Synchronized Fleet Navigation:** Camera rotations and zoom orbit simultaneously across all active viewports so spatial orientation remains consistent.
3. **Version Skew Matrix HUD:** A floating header bar displaying:
   - Target K8s version per cluster.
   - Deprecated API flags (e.g. `flowcontrol.apiserver.k8s.io/v1beta2`).
   - Workload distribution balance across nodes.

---

## 6. Phased Implementation Roadmap & Acceptance Gates

### Phase 1: Testbed Driver & Declarative CLI Scaffold
- **[TASK-CV-701]** Data Models & Fleet Schema: Author `src/testbed/models.py` defining Pydantic schemas for `FleetSpec`, `ClusterSpec`, `WorkloadSpec`, and driver options.
- **[TASK-CV-702]** K3d / Docker Driver & Remote Execution: Implement `src/testbed/drivers/k3d.py` supporting remote execution over Tailscale SSH to Chunkito, cluster lifecycle (`create`, `delete`, `status`), and kubeconfig extraction.

### Phase 2: Operator Deployment & Stream Gateway
- **[TASK-CV-703]** Automated In-Cluster Operator Deployment: Implement `cluster-vis testbed deploy-operator` deploying the SPEC-04 operator and CRD into each target cluster, configuring node ports and health probes.
- **[TASK-CV-704]** Operational Event & Chaos Injector: Author `src/testbed/chaos.py` with scripted scenarios (`rollout-restart`, `node-drain`, `pod-kill`, `canary-weight-shift`).

### Phase 3: Frontend Multi-Cluster Grid & Live Stream Polish
- **[TASK-CV-705]** Viewport Grid Controller & Quad View: Implement `src/scene/grid_controller.ts` allowing 1, 2, or 4 viewport layouts in Three.js with synchronized orbit cameras.
- **[TASK-CV-706]** Live Streaming Delta Transitions & End-to-End Testbed Verification: Connect live SSE streams from Chunkito clusters into Three.js viewports, verify real-time pod animations, and document the runbook in Obsidian.

---

## 7. Acceptance Criteria & Safety Gates

1. **Host Safety on Chunkito:**
   - Testbed clusters MUST NOT consume $>4\text{GB}$ total RAM across all nodes, guaranteeing no interference with resident 100GB+ LLM models on Chunkito.
   - All cluster ports and networks must be cleanly namespaced (e.g. network `k3d-homelab-matrix`).
2. **Teardown Guarantee:**
   - Running `cluster-vis testbed down` must leave 0 orphaned docker containers, volumes, or lingering iptables entries.
3. **Additive Non-Breaking Interface:**
   - Static JSON fallback and offline demonstration mode must pass all existing 23 unit tests (`python3 -m unittest discover tests -v`) and TypeScript verification (`npx tsc --noEmit`).
4. **Sub-15s Cluster Boot:**
   - A 3-node K3d cluster must reach `Ready` state and respond to `kubectl get nodes` within 15 seconds of invocation.
5. **Real-time SSE Latency:**
   - Injected pod scheduling events must be received by the Three.js client and trigger visual animation within $<500\text{ms}$ of K8s API event emission.
