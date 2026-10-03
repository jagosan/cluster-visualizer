#!/usr/bin/env python3
"""
Jagular Delegator for TASK-CV-705:
Author src/scene/grid_controller.ts with strict TypeScript compliance.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def clean_code(raw: str) -> str:
    raw = raw.strip()
    match = re.search(r"```(?:typescript|ts)?\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    lines = raw.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()

def run():
    print("\n=======================================================")
    print("🐆 Summoning Jagular for TASK-CV-705 (src/scene/grid_controller.ts)")
    print("=======================================================")

    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Three.js and TypeScript frontend architect.
You author clean, robust, type-annotated production TypeScript conforming strictly to:
1. `verbatimModuleSyntax: true` (`import type` for types).
2. `strict: true` and `noUncheckedIndexedAccess: true` (always use guards or null-coalescing for array indexing like `arr[i] ?? fallback`).
3. Output ONLY valid TypeScript inside ```typescript ``` without markdown prose."""

    user_prompt = """SPEC-06 / TASK-CV-705:
Author `src/scene/grid_controller.ts`: Viewport Grid Controller & Quad View for Three.js.

Requirements:
1. Imports:
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { ClusterViewport } from './cluster_viewport.js';

2. Types:
export type GridMode = 'single' | 'dual' | 'quad';

export interface ViewportSlot {
  id: string;
  viewport: ClusterViewport;
  container: HTMLElement;
  title: string;
  clusterName: string;
  k8sVersion?: string;
  channel?: string;
  streamUrl?: string;
}

export interface GridControllerOptions {
  wrapperElement: HTMLElement;
  hudContainer?: HTMLElement | null;
  onModeChange?: (mode: GridMode) => void;
}

3. Class `GridController`:
   - Properties:
     - `public mode: GridMode = 'dual';`
     - `public syncCameras: boolean = true;`
     - `private wrapper: HTMLElement;`
     - `private slots: ViewportSlot[] = [];`
     - `private isSyncing: boolean = false;`
     - `private hudContainer: HTMLElement | null = null;`
     - `private onModeChangeCb?: (mode: GridMode) => void;`

   - Methods:
     - `constructor(options: GridControllerOptions, initialSlots: ViewportSlot[] = [])`:
       Initializes wrapper, hudContainer, slots. Sets up camera synchronization listeners on each slot's viewport.controls.
       Sets up keyboard shortcut listeners: '1' -> 'single', '2' -> 'dual', '4' -> 'quad'.
       Applies initial mode ('dual').

     - `public addSlot(slot: ViewportSlot): void`:
       Adds slot, wires camera sync listeners, updates grid styling.

     - `public getSlots(): ViewportSlot[]`:
       Returns `[...this.slots]`.

     - `public getActiveSlots(): ViewportSlot[]`:
       If mode === 'single', returns `this.slots.slice(0, 1)`.
       If mode === 'dual', returns `this.slots.slice(0, 2)`.
       If mode === 'quad', returns `this.slots.slice(0, 4)`.

     - `public setMode(mode: GridMode): void`:
       Updates `this.mode = mode`.
       Applies CSS classes and styles to wrapper and slot containers:
       - 'single':
         wrapper.style.display = 'block';
         First slot container: display = 'block', width = '100%', height = '100%'.
         Remaining slot containers: display = 'none'.
       - 'dual':
         wrapper.style.display = 'flex';
         wrapper.style.flexDirection = 'row';
         Slots 0 and 1: display = 'block', flex = '1 1 50%', height = '100%'.
         Remaining slots: display = 'none'.
       - 'quad':
         wrapper.style.display = 'grid';
         wrapper.style.gridTemplateColumns = '1fr 1fr';
         wrapper.style.gridTemplateRows = '1fr 1fr';
         wrapper.style.gap = '2px';
         wrapper.style.height = '100%';
         Slots 0, 1, 2, 3: display = 'block', width = '100%', height = '100%'.
       Triggers `onResize()` on active viewports so aspect ratio and render sizes update.
       Updates Skew Matrix HUD.
       Calls `this.onModeChangeCb?.(mode)`.

     - `public toggleCameraSync(enable?: boolean): boolean`:
       Toggles or sets `this.syncCameras`. Returns new state.

     - `private setupCameraSync(slot: ViewportSlot): void`:
       Listens to `change` event on `slot.viewport.controls`.
       If `this.syncCameras && !this.isSyncing`:
         `this.isSyncing = true;`
         Propagates camera position, rotation, zoom, and target to all other active slots in `this.getActiveSlots()`.
         `this.isSyncing = false;`

     - `private syncCamerasFrom(sourceControls: OrbitControls): void`:
       Iterates over `this.getActiveSlots()`:
       Copies object.position, object.rotation, zoom, projectionMatrix, target, and calls `controls.update()`.

     - `public renderAll(delta: number, speedMultiplier: number = 1.0): void`:
       Iterates over `this.getActiveSlots()` and calls `slot.viewport.render(delta, speedMultiplier)`.

     - `public updateSkewMatrixHUD(): void`:
       If `this.hudContainer` exists, renders floating or topbar version skew matrix cards:
       Cards show:
       - Cluster title and channel badge (e.g. Regular v1.36, Rapid v1.37)
       - Deprecated API flags (e.g. 'flowcontrol.apiserver.k8s.io/v1beta2' if v1.37)
       - Stream status pill (Live SSE / Static)

Ensure complete, robust TypeScript with NO truncation and valid syntax.
"""
    raw = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=8192)
    code = clean_code(raw)
    path = os.path.join(REPO_ROOT, "src", "scene", "grid_controller.ts")
    with open(path, "w") as f:
        f.write(code + "\n")
    print(f"Authored {path}")

if __name__ == "__main__":
    run()
