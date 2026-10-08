# SPEC-12: Viewport Pane Zoom-In Focus and Previous View Restoration

**Status:** Proposed  
**Author:** Christopher Robin (Lead Architect) & 🦉 Owl (Architectural Synthesizer)  
**Date:** 2026-10-07  
**Target:** `cluster-vis`  
**Extends:** `specs/00-system-architecture.md`, `specs/06-ephemeral-multi-cluster-testbed-and-live-streaming.md`, `specs/11-quad-layout-diff-tour-and-latency-springs.md`

---

## 1. Executive Summary & Design Vision

In Kubernetes cluster exploration and telemetry inspection, operators frequently view multiple clusters simultaneously in dual-split (2-pane) or quad-grid (4-pane) fleet matrix mode. However, when an anomaly, version drift, or autoscaling event occurs in a specific cluster, the operator needs to rapidly zoom in on that specific pane into a full-screen, single-viewport inspection view without losing their place in the broader fleet topology.

Currently:
1. `GridController`'s single mode (`mode === 'single'`) hardcodes viewport slot `0` (Cluster Alpha / `viewport-a`), making it impossible to focus on Cluster Beta, Gamma, or Delta in single-pane view.
2. Viewport panes lack contextual in-pane navigation controls to toggle between multi-pane grid arrangements and single-pane maximized focus.
3. Once in single mode, there is no historical memory of whether the visualizer was previously in dual-split (`dual`) or quad-grid (`quad`) mode, forcing manual re-selection from the global topbar.

This specification introduces:
1. **In-Pane Magnifying Glass Zoom Icon (`🔍`):** An intuitive, translucent HUD icon button on each viewport pane title/header that immediately maximizes *that specific pane* into full single-pane view.
2. **Dynamic Slot Targeting in Single Mode:** Updating `GridController` to track `focusedSlotId` (supporting any slot `a`, `b`, `c`, or `d` as the active single viewport) and hiding inactive slots while resizing the focused canvas to 100% dimensions.
3. **Return / Exit Arrow Icon (`↩` / `↙`):** When a pane is maximized into single view, the magnifying glass icon transitions into a return/exit icon. Clicking this icon or pressing `Escape` immediately restores the previous layout mode (`dual` or `quad`) and camera arrangements.
4. **History & State Resilience:** Preservation of previous grid modes (`previousMode`), smooth WebGL canvas resizing via `viewport.onResize()`, synchronized orbit controls continuity, and synchronization with topbar grid toggle buttons (`#btn-grid-single`, `#btn-grid-dual`, `#btn-grid-quad`).

---

## 2. Interaction Architecture & Wireframe

```
══════════════════════════════════════════════════════════════════════════════════════════════
 1. DUAL / QUAD MULTI-PANE VIEW (Normal State)
══════════════════════════════════════════════════════════════════════════════════════════════
 ┌───────────────────────────────────────┬───────────────────────────────────────┐
 │ [Cluster Alpha (v1.36.4)]        [🔍] │ [Cluster Beta (v1.35.8)]         [🔍] │
 │                                       │                                  ▲    │
 │               3D Scene                │               3D Scene           │    │
 │                                       │                          Click   │    │
 │                                       │                         Zoom-In  │    │
 ├───────────────────────────────────────┼───────────────────────────────────────┤
 │ [Cluster Gamma (v1.37.0)]        [🔍] │ [Cluster Delta (v1.36.4)]        [🔍] │
 │                                       │                                       │
 │               3D Scene                │               3D Scene                │
 └───────────────────────────────────────┴───────────────────────────────────────┘

                                   ▼ CLICK [🔍] ON CLUSTER BETA

══════════════════════════════════════════════════════════════════════════════════════════════
 2. SINGLE PANE MAXIMIZED VIEW (Zoomed on Beta, Return Icon Active)
══════════════════════════════════════════════════════════════════════════════════════════════
 ┌───────────────────────────────────────────────────────────────────────────────┐
 │ [Cluster Beta (v1.35.8)]                                                 [↩]  │
 │                                                                           ▲   │
 │                                                                           │   │
 │                          FULL 100% SINGLE VIEWPORT                        │   │
 │                                                                    Return │   │
 │                                                                   to Quad │   │
 │                                                                   (or Esc)│   │
 └───────────────────────────────────────────────────────────────────────────────┘

                                   ▼ CLICK [↩] OR PRESS ESC

══════════════════════════════════════════════════════════════════════════════════════════════
 3. RESTORED PREVIOUS VIEW (Quad 2x2 Fleet Matrix Restored)
══════════════════════════════════════════════════════════════════════════════════════════════
```

---

## 3. Technical Requirements & Contract

### 3.1 `GridController` Zoom & Focus Extensions (`src/scene/grid_controller.ts`)

1. **State Tracking:**
   * `focusedSlotId: string`: ID of the slot currently focused in single mode (defaults to `'a'`).
   * `previousMode: GridMode | null`: The layout mode (`'dual'` or `'quad'`) that was active prior to entering single zoom mode. When user manually selects single mode via topbar button or key '1', `previousMode` defaults to `'dual'`.
   * `isZoomed: boolean`: Flag indicating whether the visualizer entered single mode via pane zoom-in.

2. **Public Methods:**
   * `zoomSlot(slotId: string): void`:
     - Sets `previousMode = this.mode === 'single' ? (this.previousMode ?? 'dual') : this.mode`.
     - Sets `focusedSlotId = slotId`.
     - Sets `isZoomed = true`.
     - Invokes `setMode('single')`.
   * `restorePreviousMode(): void`:
     - Retrieves target mode: `const target = this.previousMode ?? 'dual'`.
     - Sets `isZoomed = false`.
     - Invokes `setMode(target)`.
   * `getFocusedSlotId(): string`: Returns current `focusedSlotId`.
   * `getPreviousMode(): GridMode | null`: Returns `previousMode`.
   * `isZoomActive(): boolean`: Returns `this.mode === 'single' && this.isZoomed`.

3. **Active Slots Resolution (`getActiveSlots()`):**
   * In `'single'` mode:
     ```ts
     const slot = this.slots.find(s => s.id === this.focusedSlotId) ?? this.slots[0];
     return slot ? [slot] : [];
     ```
   * In `'dual'` mode: `this.slots.slice(0, 2)`.
   * In `'quad'` mode: `this.slots.slice(0, 4)`.

4. **DOM & CSS Grid Styling (`applyGridStyles()`):**
   * In `'single'` mode:
     - `#viewports-wrapper` display set to `'block'`.
     - `.viewport-divider` display set to `'none'`.
     - All slot containers set to `display: 'none'` EXCEPT the container corresponding to `focusedSlotId`, which is set to `display: 'block'`, `width: '100%'`, `height: '100%'`.
   * In `'dual'` mode:
     - `.viewport-divider` display set to `'block'`.
     - Slots 0 and 1 displayed `flex: 1 1 50%`, remaining hidden.
   * In `'quad'` mode:
     - `.viewport-divider` suppressed (`display: 'none' !important`).
     - Slots 0–3 mapped to 2x2 grid positions (`tl`, `tr`, `bl`, `br`).

5. **Resize Triggering:**
   * When `setMode(...)` or `zoomSlot(...)` executes, `viewport.onResize()` MUST be triggered on all active slots after DOM layout update to prevent canvas distortion.

---

### 3.2 Viewport Pane UI Controls (`src/scene/cluster_viewport.ts` & `src/main.ts`)

1. **In-Pane Zoom Button Element:**
   * Each viewport pane container will contain a dedicated zoom/restore control:
     ```html
     <button class="viewport-zoom-btn" title="Zoom in on this viewport (Single view)" aria-label="Maximize viewport">
       <svg class="icon-zoom" ...>...</svg>
     </button>
     ```
   * Styled cleanly in `index.html` or inline CSS matching the dark glass theme:
     - Positioned absolute in the top-right corner of each viewport pane (`top: 14px; right: 16px;`).
     - Translucent dark glass background: `rgba(17, 24, 39, 0.85)`.
     - Subtle border: `1px solid var(--border-subtle)`.
     - Hover background: `rgba(55, 65, 81, 0.9)`.
     - Accent glow on hover: border color `var(--accent-blue)`.
     - Cursor: pointer; z-index: 50.

2. **Icon & Tooltip Dynamic State:**
   * When in `dual` or `quad` mode:
     - Icon: Magnifying Glass (`🔍` / SVG search/zoom icon).
     - Tooltip: `Maximize [Title] (Zoom In)`.
   * When in `single` mode:
     - On the focused slot:
       - Icon: Return / Exit Arrow (`↩` / `↙` / SVG exit-fullscreen/arrow-left icon).
       - Tooltip: `Return to [previousMode] View (Exit Zoom)`.
     - On inactive slots (hidden in DOM): icon updated to magnifying glass.

3. **Event Wiring:**
   * Clicking the button when not in single mode (or on a different slot) triggers `gridController.zoomSlot(slot.id)`.
   * Clicking the button when in zoomed single mode triggers `gridController.restorePreviousMode()`.
   * Keyboard shortcut `Escape`: If in zoomed single mode, restores `previousMode`.
   * Keyboard shortcut `KeyZ`: Toggles zoom on the currently hovered or active viewport pane.

---

### 3.3 Topbar & HUD Synchronization

1. **Topbar Grid Pills:**
   * When zooming into single mode, the `#btn-grid-single` button gains `.active` class, while `#btn-grid-dual` and `#btn-grid-quad` lose it.
   * When restoring from single mode, the corresponding topbar button (`#btn-grid-dual` or `#btn-grid-quad`) regains `.active` class.
2. **Version Skew Matrix HUD:**
   * `updateSkewMatrixHUD()` continues to display metadata cards for all active slots (`getActiveSlots()`), correctly reflecting the focused slot during single mode.

---

## 4. Acceptance Criteria

1. **Any Pane Zoom:**
   - From Dual mode (2 panes), clicking `🔍` on either Pane A or Pane B immediately zooms into that pane alone at 100% viewport width/height.
   - From Quad mode (4 panes), clicking `🔍` on Pane A, Pane B, Pane C, or Pane D immediately zooms into that specific pane alone.
2. **Return to Previous View:**
   - In zoomed Single mode, clicking the return/exit icon (`↩`) on the maximized pane restores the visualizer to the previous mode (`dual` if came from dual, `quad` if came from quad).
   - Pressing `Escape` while in zoomed Single mode also restores the previous mode.
3. **Canvas Resizing & Orbit Synchronization:**
   - Canvas elements resize smoothly with no WebGL aspect-ratio distortion or viewport clipping.
   - Orbit controls continue operating without camera jump or misalignment.
4. **Build & Test Suite:**
   - `npm run build` (`tsc --noEmit && vite build`) passes with zero errors.
   - Unit tests in `tests/test_spec12_pane_zoom_and_restore.py` verify all state transitions, zoom targeting, return mechanics, and DOM/CSS contracts.
