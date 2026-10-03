#!/usr/bin/env python3
"""
Generate tests/test_latency_layout.py using Jagular.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    print("--- Invoking Jagular to generate tests/test_latency_layout.py ---")
    system_prompt = (
        "You are Jagular (177B Big Iron on Chunkito). You author comprehensive unittest test cases "
        "validating mathematical formulas and convergence."
    )
    user_prompt = """
Write the complete Python test suite `tests/test_latency_layout.py` using `unittest` for `src.ingestion.latency_layout` (TASK-CV-804 / SPEC-07 §3.1).

Requirements to test:
1. `test_rest_length_scaling`:
   - Same Pod / Localhost (0.05ms): L_0 ~ 1.9 (within 0.1 tolerance)
   - Same Node / Inter-Pod (0.8ms): L_0 ~ 3.3 (within 0.2 tolerance)
   - Cross-Node LAN (2.5ms): L_0 ~ 5.1 (within 0.2 tolerance)
   - Cross-Zone / Cloud VPC (18.0ms): L_0 ~ 9.5 (within 0.3 tolerance)
   - Degraded / WAN (120.0ms): L_0 ~ 14.3 (within 0.3 tolerance)
   - Negative / zero / boundary latencies: does not crash, returns >= 1.8.

2. `test_spring_stiffness_scaling`:
   - RPS = 0: stiffness == 0.5 (K_base)
   - RPS = 9: stiffness == 0.5 * (1 + 1.0) = 1.0
   - High RPS (e.g. 10000): stiffness capped at 4.0 * K_base = 2.0.

3. `test_simulation_convergence`:
   - Run LatencyForceSimulation with 3-4 nodes and edges.
   - Verify positions are finite (no NaN, no inf).
   - Verify step() decreases max movement over iterations.

4. `test_latency_separation`:
   - Node A connected to Node B with 1ms latency.
   - Node A connected to Node C with 100ms latency.
   - Verify that after simulation, distance(A, B) < distance(A, C).

5. `test_compute_latency_layout_empty_and_single`:
   - Empty input returns empty dict.
   - Single node returns valid position dict.

Output ONLY the complete Python code for `tests/test_latency_layout.py` inside ```python ```.
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
