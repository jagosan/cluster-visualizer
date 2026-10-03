#!/usr/bin/env python3
"""
Generate src/ui/mode_toggle.ts using Jagular.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    print("--- Invoking Jagular to generate src/ui/mode_toggle.ts ---")
    system_prompt = (
        "You are Jagular (177B Big Iron on Chunkito). You write strict TypeScript code with "
        "verbatimModuleSyntax ('import type'), strict: true, and explicit handling of noUncheckedIndexedAccess."
    )
    user_prompt = """
Write the complete TypeScript module `src/ui/mode_toggle.ts` (TASK-CV-805 / SPEC-07 §3.2).

Requirements:
1. Strict TypeScript:
   - Use `import type` for type-only imports.
   - Guard DOM lookups and array indices (`noUncheckedIndexedAccess`).
2. Export type `LayoutMode = 'skyscraper' | 'latency-force';`
3. Export class `ModeToggle`:
   - `private container: HTMLElement;`
   - `private currentMode: LayoutMode = 'skyscraper';`
   - `private currentAlpha: number = 0.0;`
   - `private onModeChangeCallback?: (mode: LayoutMode, alpha: number) => void;`
   - `constructor(parentContainer?: HTMLElement)`
     - Creates/mounts a floating glassmorphic HUD pill in the UI.
     - Includes a toggle button: 'Mode: Skyscraper ⇄ Latency Field'.
     - Includes a range slider (0.0 to 1.0, step 0.01) for fine-grained manual lerp scrubbing.
     - Adds keyboard shortcut (key 'L' toggles between skyscraper alpha=0 and latency alpha=1).
   - `onModeChange(callback: (mode: LayoutMode, alpha: number) => void): void`
   - `setAlpha(alpha: number): void`
   - `setMode(mode: LayoutMode): void`
   - `destroy(): void` (cleans up DOM and listeners)

Output ONLY the complete TypeScript code inside ```typescript ```.
"""
    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3000)
    match = re.search(r"```typescript\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "src/ui/mode_toggle.ts")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
