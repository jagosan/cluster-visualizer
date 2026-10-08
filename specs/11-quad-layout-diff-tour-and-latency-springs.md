# SPEC-11: Quad-Pane Layout Alignment, Diff & Delta Inspection Sequence, and Load-Driven Latency Spring Dynamics

**Status:** Proposed  
**Author:** Christopher Robin (Lead Architect) & 🦉 Owl (Architectural Synthesizer)  
**Date:** 2026-10-06  
**Target:** `cluster-vis`  
**Extends:** `specs/00-system-architecture.md`, `specs/03-horizontal-node-peers-and-diff-engine.md`, `specs/06-ephemeral-multi-cluster-testbed-and-live-streaming.md`, `specs/07-portable-helm-packaging-and-latency-topology.md`, `specs/10-interactive-ui-cluster-onboarding-sample-catalog-and-autoscaling-traffic-harness.md`

---

## 1. Executive Summary & Design Vision

ClusterVis provides an interactive 3D architectural representation of Kubernetes clusters, complete with live streaming, autoscaling simulations, and comparative diff exploration. However, several operational gaps have been identified in the visualizer's comparative workflow, layout orchestration, and physical latency representation:

1. **Quad Grid (2x2) Viewport Mapping Defect:**
   * In the 4-pane (`quad`) layout, the top-right pane (`viewport-b`) fails to render a cluster properly. In the DOM, `#viewports-wrapper` contains an inline divider element (`.viewport-divider`) sandwiched between `viewport-a` and `viewport-b`, along with CSS flex/grid layout conflicts. In CSS grid `repeat(2, 1fr)`, child elements are positioned sequentially: item 1 is `viewport-a` (top-left), item 2 is `.viewport-divider` (top-right), item 3 is `viewport-b` (bottom-left), and item 4 is `viewport-c` (bottom-right), pushing `viewport-d` off the screen.
2. **Extended Diff / Comparison Sequence & Media Controls:**
   * While static diff pills and basic raycast inspection exist, users lack a guided, automated comparison walk-through. Users need a persistent **"DIFF"** button that kicks off an automated inspection sequence across all new (added), modified (version/config skew), and deleted (missing) components, as well as latency deltas.
   * This walk-through must reuse the media controls pattern established in `TimelineScrubber` (`⏮ Prev`, `▶ Play / ⏸ Pause`, `⏭ Next`, speed multipliers, progress scrub bar, and event banner) to step through each diffed component with synchronized camera focusing and volumetric 3D highlighting.
3. **Load-Driven Latency Springs & Floor-Tension Magnetism:**
   * The visualizer currently lacks an intuitive physical expression of latency under load. In this specification, increased traffic and load dynamically intensify the spring/magnetism forces between interacting tiers and architectural components:
     * High latency pathways turn progressively red (`#ef4444`) with heightened emissive pulse rates.
     * Floor levels and dependent components experience repulsive expansion and spring displacement along the vertical $Y$-axis (and localized $XZ$ planar drift), physically expanding the distance between architectural floors under contention and snapping back as traffic settles.

---

## 2. Problem Analysis & Architecture Blueprint

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              VIEWPORT WRAPPER & GRID FIX                               │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ CURRENT (BROKEN):                                                                      │
│ DOM children: [ viewport-a (col1, row1) ] [ .viewport-divider (col2, row1) <--- BUG! ] │
│               [ viewport-b (col1, row2) ] [ viewport-c        (col2, row2) ]           │
│                                           [ viewport-d        (overflow / hidden) ]    │
│                                                                                        │
│ TARGET ARCHITECTURE:                                                                   │
│ Grid Mode 'quad': .viewport-divider { display: none !important; }                      │
│ Cell (1,1): viewport-a (Alpha)     │ Cell (1,2): viewport-b (Beta)    <-- Top-Right OK │
│ Cell (2,1): viewport-c (Gamma)     │ Cell (2,2): viewport-d (Delta)                    │
└────────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────────────────┐
│                      DIFF WALK-THROUGH MEDIA CONTROLLER DECK                           │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ [ ⚡ DIFF ] -> Opens Diff Inspection Player Bar                                         │
│   ├── [⏮ Prev] [▶ Play / ⏸ Pause] [⏭ Next] [Speed 1x/2x] [Scrub Slider: 07 / 24]       │
│   ├── Target Event Banner: "Component 7/24: cartservice [MODIFIED] — Latency Δ: +48ms" │
│   └── Multi-Viewport Camera Synchronized Framing + Dual-Sided Volumetric Highlight     │
└────────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────────────────┐
│                 DYNAMIC SPRING MAGNETISM & ARCHITECTURAL FLOOR EXPANSION               │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ High Load / Traffic Surge -> Latency $\tau$ Rises ($15\text{ms} \to 280\text{ms}$)    │
│                                                                                        │
│   [ Tier 3: Ingress / Frontend ]  Y = 7.0 + $\Delta Y_{\text{spring}}$                 │
│         │                                                                              │
│         ▲ Spring Tension / Repulsive Load Force ($F_{\text{rep}} \propto \tau$)        │
│         │ Pathway turns Crimson Red (#ef4444) + Hot Particle Beams                     │
│         ▼                                                                              │
│   [ Tier 2: Microservices Floor ] Y = 4.5 (Rest Length Expanded: $L_0(1 + \beta \tau)$)│
│         ▲                                                                              │
│         │ Subterranean DB Contention Gap                                               │
│         ▼                                                                              │
│   [ Tier 1: Storage / Cloud Vaults ] Y = 1.0 - $\Delta Y_{\text{sub}}$                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Specifications

### 3.1 Item 1: Top-Right Pane Cluster Restoration in 4-Pane (Quad) Mode

#### Root Cause
In `index.html`, `#viewports-wrapper` contains:
```html
<main id="viewports-wrapper">
  <div class="viewport-pane" id="viewport-a"></div>
  <div class="viewport-divider"></div>
  <div class="viewport-pane" id="viewport-b"></div>
  <div class="viewport-pane" id="viewport-c" style="display: none;"></div>
  <div class="viewport-pane" id="viewport-d" style="display: none;"></div>
</main>
```
When switching to `mode === 'quad'` in `src/scene/grid_controller.ts`:
1. `#viewports-wrapper` is set to `display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr;`.
2. The CSS selector loops over `allSlots` (`[viewportA, viewportB, viewportC, viewportD]`), setting `display: block` on the first 4 slots.
3. However, `.viewport-divider` is an unmanaged DOM sibling sitting at child index 1 between `viewport-a` (index 0) and `viewport-b` (index 2).
4. As a result, CSS Grid places `.viewport-divider` in row 1, col 2 (the top-right grid cell), pushing `viewport-b` into row 2, col 1 (bottom-left), `viewport-c` into row 2, col 2 (bottom-right), and entirely displacing `viewport-d`.

#### Required Solution
1. **Divider Management in `GridController.applyGridStyles()`:**
   * When `mode === 'quad'`, explicitly suppress `.viewport-divider` with `display: none`.
   * When `mode === 'dual'`, ensure `.viewport-divider` has `display: block`.
   * When `mode === 'single'`, set `.viewport-divider` to `display: none`.
2. **Explicit Grid Placement:**
   * Explicitly bind grid area or slot index attributes (`data-grid-pos="tl|tr|bl|br"`) to guarantee:
     * Slot 0 (`viewport-a`): Top-Left (Row 1, Col 1)
     * Slot 1 (`viewport-b`): Top-Right (Row 1, Col 2)
     * Slot 2 (`viewport-c`): Bottom-Left (Row 2, Col 1)
     * Slot 3 (`viewport-d`): Bottom-Right (Row 2, Col 2)
3. **Data Hydration Validation:**
   * Verify in `src/main.ts` that `viewportB.setClusterData()` receives valid topology data and that resizing triggers camera aspect ratio recalibration for slot 1.

---

### 3.2 Item 2: Extended Comparison / Diff Simulation Walk-Through & Media Controls

#### User Experience & Functional Workflow
1. **Persistent Topbar Action:**
   * Add a topbar control button: `🔍 DIFF INSPECTOR` or `⚡ DIFF TOUR`.
   * Keyboard shortcut: `KeyD`.
2. **Diff Sequence Extraction & Queue:**
   * Extract all semantic delta items from `DiffReportData` and comparative telemetry:
     * **Added Components:** Missing in Alpha, present in Beta (pulsing neon green).
     * **Deleted Components:** Present in Alpha, removed in Beta (wireframe red ghost).
     * **Modified Components:** Version mismatch, image tag differences, replica count skews (amber hazard pulse).
     * **Latency Deltas:** Edge pathways where response time $|\Delta \tau| \ge 15\text{ms}$ or baseline skew exceeds 25%.
   * Sequence items are ordered logically (Control Plane $\to$ Core Services $\to$ Application Services $\to$ Data Vaults $\to$ Inter-cluster Latency bottlenecks).
3. **Media Control Deck Integration:**
   * Provide a dedicated HUD dock (or mode in `TimelineScrubber`) with controls:
     * `⏮ PREV`: Focus previous diff component.
     * `▶ PLAY / ⏸ PAUSE`: Automatically advance through each diff item with configurable dwell time (default: 3.5 seconds per component).
     * `⏭ NEXT`: Advance to next diff item.
     * `1x / 2x / 0.5x`: Playback rate multiplier.
     * `Scrub Bar`: Horizontal interactive slider showing numbered pins for all diff items, color-coded by diff kind (`green` = added, `red` = deleted, `amber` = modified, `purple` = latency delta).
4. **Synchronized 3D Highlighting & Camera Action:**
   * For the active diff item:
     * **Camera Focus:** Smoothly tween both cameras (`viewportA` and `viewportB`) to focus on the component's coordinates using spherical orbit lerp (`controls.target` and `camera.position`).
     * **Volumetric Highlight:** Activate halo bounding box, high-emissive glow, and contextual connection lines on both Alpha and Beta sides.
     * **Diff HUD Banner:** Display an floating translucent HUD card with:
       * Component kind, name, and namespace.
       * Exact delta: `Alpha: v1.35.8 (12ms) ➔ Beta: v1.36.4 (48ms) [Δ +36ms]`.
       * Image digest comparison and environment variable changes.

---

### 3.3 Item 3: Load-Driven Spring Magnetism & Floor-Tension Physical Dynamics

#### Conceptual Model & Physical Metaphor
In standard visualization, architectural floors (trays) and pod tiers sit at fixed vertical elevations ($Y = 0.5, 2.5, 5.0, 7.0$). In physical networks, contention and queuing latency manifest as strain and separation. Under SPEC-11, **latency acts as repulsive vertical pressure and elastic spring strain**:
* As traffic load increases (e.g. from the `TrafficControlDeck` or live SSE metrics), the end-to-end and hop-by-hop latency between calling services increases.
* High latency between two architectural tiers pushes the floor trays apart vertically (increasing floor-to-floor clearance), visually communicating architectural friction and backpressure.
* The interconnect conduit/edge between them stretches elastically, turns from cool cyan/blue $\to$ warning amber $\to$ hot glowing crimson red (`#ef4444`), and pulses with high-frequency particle waves.

#### Mathematical Formulation
Let:
* $L_0$: Base structural floor pitch between tier $i$ and tier $j$ (nominal $Y$-distance, e.g. $\Delta Y_0 = 2.5$).
* $\tau_{ij}(t)$: Instantaneous round-trip latency in milliseconds along dependency edge $(i, j)$ at time $t$.
* $\tau_{\text{base}}$: Baseline nominal latency under zero load (e.g. $5.0\text{ ms}$).
* $k_{\text{spring}}$: Elastic structural stiffness constant.
* $C_{\text{load}}$: Load repulsion scale coefficient.

The dynamic vertical offset $\Delta Y_{ij}(t)$ follows a damped harmonic spring response:
$$\Delta Y_{ij}(t) = \min\left(\Delta Y_{\max},\; C_{\text{load}} \cdot \ln\left(1 + \max\left(0, \frac{\tau_{ij}(t) - \tau_{\text{base}}}{\tau_{\text{base}}}\right)\right)\right)$$

* **Floor Separation:**
  * Nominal elevation: $Y_{\text{floor}} = Y_0$
  * Distended elevation under contention: $Y_{\text{floor}}(t) = Y_0 + \sum \Delta Y_{ij}(t)$
  * Maximum allowable vertical stretching per floor: $\Delta Y_{\max} = 1.8\text{ units}$ (preserves overall building proportions while making strain visually unmistakable).
* **Color & Heat Shading:**
  * When $\tau_{ij} \le 15\text{ms}$: Color is calm cyan (`#06b6d4`), spring rest tension.
  * When $15\text{ms} < \tau_{ij} \le 60\text{ms}$: Color shifts to vibrant amber (`#f59e0b`), slight vertical stretching ($\approx +0.4\text{ units}$).
  * When $\tau_{ij} > 60\text{ms}$: Color shifts to hot crimson red (`#ef4444`), emissive boost ($2.5\times$), rapid particle strobe ($12\text{Hz}$), and maximum floor elongation ($\approx +1.5\text{ units}$).
* **Settling & Relaxation:**
  * When load sheds or traffic stabilizes, a damped spring relaxation lerp ($t_{\text{relax}} \approx 1.2\text{s}$) draws the floor back to its structural datum.

---

## 4. Implementation Work Breakdown & Target Files

| Task ID | Component / Area | Description | Target Files |
| :--- | :--- | :--- | :--- |
| **`TASK-CV-1201`** | **Quad Grid Layout Fix** | Hide `.viewport-divider` in quad mode; assign deterministic grid column/row placements to all 4 viewports; fix aspect-ratio resize hooks for top-right viewport B. | `src/scene/grid_controller.ts`, `index.html` |
| **`TASK-CV-1202`** | **Diff Sequence Engine** | Build `DiffSequencePlayer` model: extract ordered queue of added, deleted, modified, and latency-skewed components from `DiffReportData` and live diff lookups. | `src/scene/diff_sequence.ts` *(new)* |
| **`TASK-CV-1203`** | **Diff Media Deck UI** | Implement docked media control bar (`⏮`, `▶/⏸`, `⏭`, speed, timeline track with categorized color pins, and active diff detail card). | `src/ui/diff_media_deck.ts` *(new)*, `src/main.ts` |
| **`TASK-CV-1204`** | **Volumetric Diff Highlighting** | Add synchronized dual-viewport focus tweens and 3D wireframe / pulsing volumetric highlights for the active diff item in the tour. | `src/scene/cluster_viewport.ts`, `src/scene/diff_card.ts` |
| **`TASK-CV-1205`** | **Latency Spring Physics** | Implement load-dependent dynamic floor separation: calculate vertical displacement $\Delta Y$ from edge latency $\tau$; apply smooth damped spring relaxation. | `src/scene/latency_spring_engine.ts` *(new)*, `src/scene/layer_trays.ts` |
| **`TASK-CV-1206`** | **Edge Thermal Conduit FX** | Update dependency edge materials to dynamically lerp cyan $\to$ amber $\to$ crimson red with particle velocity and pulse frequency tied to spring displacement. | `src/scene/plunge_conduits.ts`, `src/scene/cluster_viewport.ts` |
| **`TASK-CV-1207`** | **Traffic Deck Integration** | Wire `TrafficControlDeck` load bursts to trigger spring expansion and the Diff Tour media controls in the main UI. | `src/ui/traffic_deck.ts`, `src/main.ts` |

---

## 5. Verification & Acceptance Criteria

1. **4-Pane Quad Mode:**
   * Pressing `4` or clicking `4-PANE` renders all four viewports (`viewport-a` top-left, `viewport-b` top-right, `viewport-c` bottom-left, `viewport-d` bottom-right) without blank areas or shifted viewports. Top-right pane displays Cluster Beta fully interactive with OrbitControls.
2. **Diff Sequence Playback:**
   * Clicking `DIFF` opens the media deck.
   * Pressing `PLAY` steps through each added, deleted, and modified component, auto-framing the camera in both Alpha and Beta viewports with synchronized highlighting.
   * Pressing `PREV` / `NEXT` jumps between diff items cleanly.
   * Active component details and latency delta are displayed in the HUD banner.
3. **Load-Driven Latency Springs:**
   * Triggering high load in the traffic harness increases latency along the target pathway.
   * As latency rises above $60\text{ms}$, the pathway turns crimson red and the vertical distance between connected building floors visibly expands.
   * Ceasing traffic smoothly relaxes the floor back to its structural resting position via damped spring interpolation.
