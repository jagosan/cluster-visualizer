#!/usr/bin/env python3
"""
Generate TASK-CV-804 (Latency Force Layout Engine and tests) using Jagular.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    print("--- Invoking Jagular to generate src/ingestion/latency_layout.py ---")
    system_prompt = (
        "You are Jagular (177B Big Iron on Chunkito). You write high-performance, exact mathematical "
        "algorithms in Python with zero third-party dependencies (math and random/collections only)."
    )
    user_prompt = """
Write the complete Python module `src/ingestion/latency_layout.py` (TASK-CV-804 / SPEC-07 §3.1).

Mathematical formulation from SPEC-07:
1. Rest Length function:
   L_0(u, v) = L_min + S * log10(1 + latency_ms / tau_0)
   Where:
   L_min = 1.8
   S = 6.0
   tau_0 = 1.0 (ms)

2. Spring stiffness function:
   K(u, v) = K_base * min(4.0, 1.0 + log10(1 + RPS(u, v)))
   Where:
   K_base = 0.5

3. Spring-mass relaxation / MDS simulation:
   - Calculate repulsive forces between all pairs of nodes (Coulomb-like: F_rep = k_rep / (d^2 + epsilon) directed away from each other).
   - Calculate attractive spring forces along edges (Hooke's law: F_spring = K * (d - L_0) directed toward each other).
   - Apply damping factor (e.g. 0.85) each iteration.
   - Run relaxation loop (default 60 iterations) to settle positions in 3D space (primarily X-Z plane, with subtle Y elevation based on component layer).
   - Guard against divide-by-zero, NaNs, and infinite coordinates.

4. Public Functions & Classes:
   - compute_rest_length(latency_ms: float, l_min: float = 1.8, s: float = 6.0, tau_0: float = 1.0) -> float
   - compute_spring_stiffness(rps: float, k_base: float = 0.5) -> float
   - class LatencyForceSimulation:
     - __init__(nodes: List[str], edges: List[Dict[str, Any]], initial_positions: Optional[Dict[str, Dict[str, float]]] = None)
     - step(dt: float = 0.1) -> float (returns max movement)
     - run(iterations: int = 60) -> Dict[str, Dict[str, float]]
   - compute_latency_layout(components: List[Dict[str, Any]], edges: List[Dict[str, Any]], iterations: int = 60) -> Dict[str, Dict[str, float]]:
     Returns a mapping of {component_id: {"x": float, "y": float, "z": float}}.

Output ONLY the complete Python code for `src/ingestion/latency_layout.py` inside ```python ```.
"""
    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=4096)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "src/ingestion/latency_layout.py")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
