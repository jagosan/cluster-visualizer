#!/usr/bin/env python3
"""
Align tests/test_latency_layout.py with src/ingestion/latency_layout.py using Jagular.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    print("--- Invoking Jagular to align tests/test_latency_layout.py ---")
    system_prompt = (
        "You are Jagular (177B Big Iron on Chunkito). You author clean, zero-dependency Python unittest suites."
    )
    user_prompt = """
Align `tests/test_latency_layout.py` with the exact API of `src/ingestion/latency_layout.py`:

In `src/ingestion/latency_layout.py`:
- `compute_rest_length(latency_ms: float, l_min: float = 1.8, s: float = 6.0, tau_0: float = 1.0) -> float`
- `compute_spring_stiffness(rps: float, k_base: float = 0.5) -> float`
- `LatencyForceSimulation`:
  - `__init__(nodes: List[str], edges: List[Dict[str, Any]], initial_positions: Optional[Dict[str, Dict[str, float]]] = None)`
    (edges are dicts with 'source', 'target', 'latency_ms', 'rps')
  - `step(dt: float = 0.1) -> float` (returns max_movement float)
  - `run(iterations: int = 60) -> Dict[str, Dict[str, float]]` (returns {node: {'x': float, 'y': float, 'z': float}})
  - `positions: Dict[str, Dict[str, float]]`
- `compute_latency_layout(components: List[Dict[str, Any]], edges: List[Dict[str, Any]], iterations: int = 60) -> Dict[str, Dict[str, float]]`

Write the complete `tests/test_latency_layout.py` without external dependencies like numpy (use math module only):
1. `test_rest_length_scaling`: tests 0.05ms (~1.9), 0.8ms (~3.3), 2.5ms (~5.1), 18.0ms (~9.5), 120.0ms (~14.3), and edge cases (<=0).
2. `test_spring_stiffness_scaling`: tests rps=0 (0.5), rps=9 (1.0), rps=10000 (2.0 cap).
3. `test_simulation_convergence`: runs 60 iterations, verifies max_movement decreases and all coordinates are finite.
4. `test_latency_separation`:
   - A -> B with latency_ms=1.0
   - A -> C with latency_ms=100.0
   - Distance(A, B) < Distance(A, C).
5. `test_compute_latency_layout`:
   - Empty input returns empty dict.
   - Single component [{'id': 'c1'}] returns valid {'c1': {'x': ..., 'y': ..., 'z': ...}}.

Output ONLY the complete Python code inside ```python ```.
"""
    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=4096)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "tests/test_latency_layout.py")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
