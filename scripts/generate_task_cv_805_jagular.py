#!/usr/bin/env python3
"""
Generate TASK-CV-805 (Three.js Dual-Mode Lerp & Edge Compression) using Jagular.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    print("--- Invoking Jagular to generate src/scene/layout_transition.ts ---")
    system_prompt = (
        "You are Jagular (177B Big Iron on Chunkito). You write strict TypeScript code with "
        "verbatimModuleSyntax ('import type'), strict: true, and explicit handling of noUncheckedIndexedAccess."
    )
    user_prompt = """
Write the complete TypeScript module `src/scene/layout_transition.ts` (TASK-CV-805 / SPEC-07 §3.2).

Requirements:
1. Strict TypeScript:
   - Use `import type` for type-only imports.
   - All array accesses must handle undefined with `??` or guards (`noUncheckedIndexedAccess`).
2. Export interfaces:
   ```typescript
   export interface Vector3D {
     x: number;
     y: number;
     z: number;
   }

   export interface SpatialCoordinates {
     arch: Vector3D;
     latency: Vector3D;
   }
   ```
3. Export class `LayoutTransitionController`:
   - `private coordinates: Map<string, SpatialCoordinates> = new Map();`
   - `private currentAlpha: number = 0.0;`
   - `private targetAlpha: number = 0.0;`
   - `private transitionDurationMs: number = 800;`
   - `private elapsedMs: number = 0;`
   - `private isTransitioning: boolean = false;`
   - `registerNode(id: string, arch: Vector3D, latency?: Vector3D): void`
   - `setLatencyCoordinate(id: string, latency: Vector3D): void`
   - `setTargetAlpha(alpha: number, durationMs?: number): void`
   - `setImmediateAlpha(alpha: number): void`
   - `getAlpha(): number`
   - `isAnimating(): boolean`
   - `update(deltaSeconds: number): boolean`
     - Advances transition using cubic ease-in-out easing:
       `t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2`
     - Returns true if actively transitioning, false if settled.
   - `getPosition(id: string): Vector3D | undefined`
     - Returns linearly interpolated coordinate:
       `(1 - a) * arch + a * latency`
   - `getAllCurrentPositions(): Map<string, Vector3D>`

Output ONLY the complete TypeScript code inside ```typescript ```.
"""
    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3000)
    match = re.search(r"```typescript\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "src/scene/layout_transition.ts")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
