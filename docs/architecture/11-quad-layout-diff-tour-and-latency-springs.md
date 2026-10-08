# Architectural Blueprint: SPEC-11 Quad-Pane Layout Alignment, Diff & Delta Inspection Sequence, and Load-Driven Latency Spring Dynamics

**Document Reference:** `docs/architecture/11-quad-layout-diff-tour-and-latency-springs.md`  
**Companion Specification:** `specs/11-quad-layout-diff-tour-and-latency-springs.md`  
**Target System:** `cluster-vis`  
**Status:** Approved Architecture Blueprint  
**Author:** 🦉 Owl (Architectural Synthesizer & Swarm Orchestrator)

---

## 1. High-Level Architecture & System Topography

```
 ┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                                 BROWSER CLIENT (ClusterVis UI)                                  │
 │                                                                                                 │
 │  ┌────────────────────────┐      ┌─────────────────────────────┐      ┌──────────────────────┐  │
 │  │ Diff Tour Media Deck   │      │ Grid Controller             │      │ Traffic Control Deck │  │
 │  │ (src/ui/diff_media_    │      │ (src/scene/grid_            │      │ (src/ui/traffic_     │  │
 │  │  deck.ts)              │      │  controller.ts)             │      │  deck.ts)            │  │
 │  └──────────┬─────────────┘      └──────────────┬──────────────┘      └──────────┬───────────┘  │
 │             │                                   │                                │              │
 │             ▼                                   ▼                                ▼              │
 │  ┌───────────────────────────────────────────────────────────────────────────────────────────┐  │
 │  │ DiffSequenceEngine (src/scene/diff_sequence.ts)                                           │  │
 │  │ - Extracted queue of added/deleted/modified/latency-skew items                            │  │
 │  │ - Playback state (playing, paused, current index, dwell timer, scrub pin metadata)        │  │
 │  └──────────────────────────────┬───────────────────────────┬────────────────────────────────┘  │
 │                                 │                           │                                   │
 │             ┌───────────────────┴──────────┐     ┌──────────┴──────────────────┐                │
 │             ▼                              ▼     ▼                             ▼                │
 │  ┌─────────────────────────┐   ┌───────────────────────────┐   ┌─────────────────────────────┐  │
 │  │ ClusterViewport Slot A  │   │ ClusterViewport Slot B    │   │ LatencySpringEngine         │  │
 │  │ (Top-Left: Alpha)       │   │ (Top-Right: Beta)         │   │ (src/scene/latency_spring_  │  │
 │  │ - LayerTrayManager      │   │ - LayerTrayManager        │   │  engine.ts)                 │  │
 │  │ - Synchronized Highlight│   │ - Synchronized Highlight  │   │ - Damped harmonic springs   │  │
 │  │ - PlungeConduitManager  │   │ - PlungeConduitManager    │   │ - Floor displacement ΔY     │  │
 │  └─────────────────────────┘   └───────────────────────────┘   │ - Thermal color lerp        │  │
 │             ▲                              ▲                   └──────────────┬──────────────┘  │
 │             │                              │                                  │                 │
 │  ┌──────────┴──────────────┐   ┌───────────┴───────────────┐                  │                 │
 │  │ ClusterViewport Slot C  │   │ ClusterViewport Slot D    │◄─────────────────┘                 │
 │  │ (Bottom-Left: Gamma)    │   │ (Bottom-Right: Delta)     │                                    │
 │  └─────────────────────────┘   └───────────────────────────┘                                    │
 └─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Design & Functional Contracts

### 2.1 Viewport Grid Management & Quad DOM Rectification

#### Problem Statement
In `index.html`, `#viewports-wrapper` has the DOM structure:
```html
<main id="viewports-wrapper">
  <div class="viewport-pane" id="viewport-a"></div>
  <div class="viewport-divider"></div>
  <div class="viewport-pane" id="viewport-b"></div>
  <div class="viewport-pane" id="viewport-c" style="display: none;"></div>
  <div class="viewport-pane" id="viewport-d" style="display: none;"></div>
</main>
```
When `GridController.setMode('quad')` activates CSS Grid with `repeat(2, 1fr)`, `.viewport-divider` is an unmanaged DOM sibling placed in Grid Cell (Row 1, Column 2). This displaces `viewport-b` to Row 2 Column 1, `viewport-c` to Row 2 Column 2, and hides `viewport-d` outside the grid.

#### Solution Contract
1. **Dynamic Divider Toggling:**
   - In `dual` mode: `.viewport-divider { display: block; }`.
   - In `single` and `quad` modes: `.viewport-divider { display: none !important; }`.
2. **Explicit Grid Placement via Data Attributes & Inline Styles:**
   - Assign deterministic CSS grid column/row placements:
     - Slot 0 (`#viewport-a`): `grid-column: 1; grid-row: 1;` (Top-Left)
     - Slot 1 (`#viewport-b`): `grid-column: 2; grid-row: 1;` (Top-Right)
     - Slot 2 (`#viewport-c`): `grid-column: 1; grid-row: 2;` (Bottom-Left)
     - Slot 3 (`#viewport-d`): `grid-column: 2; grid-row: 2;` (Bottom-Right)
3. **Resize Observer & Aspect Recalibration:**
   - Trigger `slot.viewport.onResize()` for each active slot upon mode change and container geometry mutations.

---

### 2.2 Diff Sequence Engine (`src/scene/diff_sequence.ts`)

#### Contract & Data Model
```typescript
export type DiffKind = 'added' | 'deleted' | 'modified' | 'latency_delta';

export interface DiffSequenceItem {
  id: string;
  index: number;
  kind: DiffKind;
  componentName: string;
  namespace?: string;
  tier?: string;
  alphaVersion?: string;
  betaVersion?: string;
  alphaLatencyMs?: number;
  betaLatencyMs?: number;
  latencyDeltaMs?: number;
  alphaPosition?: { x: number; y: number; z: number };
  betaPosition?: { x: number; y: number; z: number };
  diffDetails: string[];
  description: string;
}

export interface DiffSequenceState {
  items: DiffSequenceItem[];
  currentIndex: number;
  isPlaying: boolean;
  speed: number; // 0.5x, 1x, 2x
  dwellDurationMs: number; // default 3500ms
}
```

#### Order of Inspection
Sequence items are grouped and ordered deterministically to provide an intuitive architectural journey:
1. **Control Plane & Foundational Services** (etcd, apiserver, kube-system).
2. **Core / Shared Infrastructure** (Ingress, Istio, DNS, Cert Manager).
3. **Application Microservices** (Frontend, Cart, Checkout, Catalog, Payment).
4. **Data Vaults & Subterranean Storage** (CloudSQL, Redis, PubSub, GCS).
5. **High-Latency Pathways / Bottlenecks** ($|\Delta \tau| \ge 15\text{ms}$).

---

### 2.3 Diff Media Control Deck (`src/ui/diff_media_deck.ts`)

#### UI Layout & DOM Specifications
Docked translucent floating bar anchored above the bottom viewport edge:
- **Container:** `#diff-media-deck` with high blur backdrop (`backdrop-filter: blur(16px)`), dark zinc aesthetic (`#111827ee`), and neon accent borders.
- **Header:** Diff category counts (Green Added, Wireframe Red Missing, Amber Modified, Purple Latency Skew).
- **Control Bar:**
  - `⏮ PREV` (KeyLeft / KeyJ)
  - `▶ PLAY` / `⏸ PAUSE` (Spacebar)
  - `⏭ NEXT` (KeyRight / KeyL)
  - Speed multipliers: `0.5x`, `1.0x`, `2.0x`.
- **Interactive Scrubber Bar:**
  - Progress track with percentage fill.
  - Numbered pin markers color-coded by `DiffKind`.
  - Scrub thumb with drag/click seek listeners.
- **Active Event Banner HUD:**
  - Displays component name, diff kind badge, image tag/digest skew, and latency delta `[Δ +36ms]`.

---

### 2.4 Synchronized Dual-Viewport Volumetric Highlighting (`ClusterViewport`)

When `DiffSequenceEngine` selects item $i$:
1. **Camera Framing:**
   - Calculate bounding coordinates for item in Alpha and Beta scenes.
   - Smoothly tween camera target and orbital position with damping ($\tau_{\text{tween}} \approx 800\text{ms}$).
2. **Volumetric 3D Highlighting:**
   - **Added:** Intense neon-green wireframe/glow (`#10b981`) on Beta.
   - **Deleted:** Ghosted wireframe red (`#ef4444`) on Alpha.
   - **Modified:** Amber hazard pulse (`#f59e0b`) on both Alpha and Beta.
   - **Latency Delta:** Glowing purple/crimson beacon on connecting conduits.
3. **Floating Billboarding 3D Card:**
   - Anchor `DiffCard` in billboard orientation above the highlighted component with comparison metrics.

---

### 2.5 Latency Spring Physics Engine (`src/scene/latency_spring_engine.ts`)

#### Mathematical Formulation
Network latency under high traffic load is modeled as a repulsive vertical expansion and elastic harmonic spring strain between architectural floor levels:

Let:
- $Y_0(k)$: Nominal structural elevation of floor/tier $k$ ($Y \in [0.5, 2.5, 5.0, 7.0]$).
- $\tau_{ij}(t)$: Instantaneous latency between tier $i$ and tier $j$ in milliseconds.
- $\tau_{\text{base}} = 5.0\text{ ms}$: Baseline quiescent latency.
- $\Delta Y_{\max} = 1.8\text{ units}$: Maximum floor distension.
- $C_{\text{load}} = 0.45$: Logarithmic scaling coefficient.

$$\Delta Y_{ij}(t) = \min\left(\Delta Y_{\max},\; C_{\text{load}} \cdot \ln\left(1 + \max\left(0, \frac{\tau_{ij}(t) - \tau_{\text{base}}}{\tau_{\text{base}}}\right)\right)\right)$$

#### Spring Dynamics & Relaxation
The vertical displacement $\Delta Y(t)$ obeys a damped spring equation:
$$\frac{d^2 \Delta Y}{dt^2} + 2\zeta \omega_n \frac{d\Delta Y}{dt} + \omega_n^2 (\Delta Y - \Delta Y_{\text{target}}) = 0$$
where $\zeta \approx 0.85$ (critically damped feel) and $\omega_n \approx 3.5\text{ rad/s}$.
When traffic returns to baseline, the floors smoothly settle back to structural datum within $t_{\text{settle}} \approx 1.2\text{s}$.

#### Thermal Conduit FX
- $\tau \le 15\text{ms}$: Cool cyan (`#06b6d4`), baseline particle drift speed.
- $15\text{ms} < \tau \le 60\text{ms}$: Vibrant amber (`#f59e0b`), $+0.4$ vertical expansion, $1.5\times$ particle speed.
- $\tau > 60\text{ms}$: Crimson red (`#ef4444`), hot emissive strobe, $+1.2\text{ to }+1.8$ vertical floor expansion, $3.0\times$ particle speed.

---

## 3. Architectural Decision Records (ADRs)

### ADR-01: CSS Grid Deterministic Placement over Absolute Canvases
- **Context:** Viewport panes in Quad mode suffered layout collisions due to the intermediary `.viewport-divider` element in the DOM.
- **Decision:** Use explicit CSS grid placement rules (`grid-column` / `grid-row`) on `.viewport-pane` and toggle `.viewport-divider` to `display: none` in quad and single modes.
- **Consequences:** Eliminates DOM order dependency, guarantees top-right pane is always `viewport-b`, and preserves clean split-resizing in dual mode.

### ADR-02: Decoupled DiffSequenceEngine Model from UI Deck
- **Context:** Diff tour playback requires state transitions (play, pause, next, prev, seek, speed change) that must coordinate with both UI controls and 3D Three.js camera framing.
- **Decision:** Implement `DiffSequenceEngine` as a pure TypeScript event-emitting model in `src/scene/diff_sequence.ts`, while `DiffMediaDeck` handles DOM rendering and keyboard bindings in `src/ui/diff_media_deck.ts`.
- **Consequences:** Clean separation of concerns, testable without full DOM or WebGL context, and reusable across single, dual, or quad viewport modes.

### ADR-03: Logarithmic Damped Spring Latency Representation
- **Context:** Linear displacement for high latencies (e.g. 1000ms spikes) would rip building floors hundreds of units into outer space, disorienting the camera.
- **Decision:** Apply logarithmic damping $\ln(1 + \Delta \tau / \tau_{\text{base}})$ with a strict clamp $\Delta Y_{\max} = 1.8\text{ units}$.
- **Consequences:** Clear physical exaggeration of contention and backpressure while preserving building proportions and camera framing stability.

---

## 4. 💡 Note to Future Self: Hosting Portability

ClusterVis is engineered to operate seamlessly across three operational deployment targets:
1. **Air-Gapped / Static Client Mode:** Runs entirely within the browser via static JSON topology fixtures (`cluster-alpha.json`, `cluster-beta.json`, sample catalog). Zero backend, zero Kubernetes cluster required.
2. **Homelab Edge Deployment (Tailscale + K3d / Chunkito):** Connects directly to SSE endpoints and synthetic TCP ping probes running on local edge nodes without cloud dependencies.
3. **Cloud Enterprise / Production Ingress:** Deploys via Helm chart (`charts/clustervis`) into GKE/EKS with Kubernetes TokenReview and RBAC SubjectAccessReview authentication.

**Decoupling Principle:** The 3D rendering pipeline, diff tour engine, and spring physics MUST NEVER assume the presence of a live network connection or cloud APIs. All dynamic behaviors accept local simulation inputs (e.g. `TrafficControlDeck`) and fall back cleanly when live telemetry is absent.
