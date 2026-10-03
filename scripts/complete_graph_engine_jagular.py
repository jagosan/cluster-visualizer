#!/usr/bin/env python3
"""
Complete src/operator/graph_engine.py using Jagular.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    print("--- Invoking Jagular to complete src/operator/graph_engine.py ---")
    system_prompt = "You are Jagular (177B Big Iron on Chunkito). You write exact, clean Python code."
    user_prompt = """
Here is the end of `src/operator/graph_engine.py` that was cut off:
```python
        # Aggregate edges by workload pair
        # Key: (src_workload, dst_workload)
        # Value: {'latencies': [float], 'total_rps': float, 'count': int}
        aggregated: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(
            lambda: {'latencies': [], 'total_rps': 0.0, 'count': 0}
        )

        for edge in raw_edges:
            if not isinstance(edge, dict):
                continue

            src = edge.get('source', edge.get('src', ''))
            dst = edge.get('target', edge
```

Complete this method `aggregate_service_edges` and provide:
- The remainder of `aggregate_service_edges`:
  - maps src and dst to workload names (using pod_to_workload, falling back to original name)
  - extracts latency_ms and rps
  - aggregates into list of edge dicts: {'source': src_wl, 'target': dst_wl, 'latency_ms': mean_latency, 'rps': total_rps, 'count': count}
  - prunes micro-edges if rps == 0 and traffic below threshold (unless only edge)
  - returns the list of aggregated edge dicts
- The function `scrub_cluster_graph(graph: dict) -> dict`:
  - calls `SecretScrubber.scrub_graph(graph)`
  - returns the scrubbed graph
- `__all__ = ['SecretScrubber', 'LatencyEdgeAggregator', 'scrub_cluster_graph']`

Output ONLY the exact Python code to replace the cut-off part (from `# Aggregate edges by workload pair` to EOF) inside ```python ```.
"""
    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=1500)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    file_path = os.path.join(REPO_ROOT, "src/operator/graph_engine.py")
    with open(file_path, "r") as f:
        existing = f.read()

    # Cut off at "# Aggregate edges by workload pair"
    cut_idx = existing.rfind("        # Aggregate edges by workload pair")
    if cut_idx != -1:
        new_content = existing[:cut_idx] + code.strip() + "\n"
        with open(file_path, "w") as f:
            f.write(new_content)
        print("Updated src/operator/graph_engine.py")

if __name__ == "__main__":
    main()
