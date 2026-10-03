#!/usr/bin/env python3
"""
Update src/operator/server.py using Jagular.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    print("--- Invoking Jagular to update src/operator/server.py ---")
    system_prompt = "You are Jagular (177B Big Iron on Chunkito). You write clean, production-grade Python code."
    
    with open(os.path.join(REPO_ROOT, "src/operator/server.py")) as f:
        existing = f.read()

    user_prompt = """
Update `src/operator/server.py` to integrate Authentication, Latency Telemetry Ingestion, and Secret Scrubbing (TASK-CV-803 / SPEC-07 §5 & §6.1).

Requirements:
1. Import `Authenticator` from `.auth` (or `src.operator.auth`), and `SecretScrubber`, `LatencyEdgeAggregator` from `.graph_engine` (or `src.operator.graph_engine`).
2. Add class-level attributes or instance attributes to `ClusterVisualizerHandler`:
   - `authenticator: Optional[Authenticator] = None`
   - `edge_aggregator: Optional[LatencyEdgeAggregator] = None`
   - `scrub_secrets: bool = True`
   - `cors_allowed_origins: List[str] = field/list`
3. Update `_set_cors_headers`:
   - If origin in headers matches allowed origins or if '*' is configured, set Access-Control-Allow-Origin appropriately.
   - Allow headers: Content-Type, Authorization, X-Forwarded-User, X-Forwarded-Email.
   - Allow methods: GET, POST, OPTIONS.
4. Update `do_GET`:
   - Check authentication for `/api/v1/topology`, `/api/v1/topology/snapshot`, and `/api/v1/topology/stream`.
   - If auth fails, return 401 Unauthorized with header `WWW-Authenticate: Bearer realm="clustervis"` and JSON `{"error": "Unauthorized", "detail": error}`.
   - Route `/api/v1/topology` to `_handle_topology_snapshot`.
5. Update `_handle_topology_snapshot`:
   - If `scrub_secrets` is True, scrub the snapshot before returning via `SecretScrubber.scrub_graph(snapshot)`.
6. Add `do_POST`:
   - Route `/api/v1/telemetry/latency`:
     - Read request body JSON.
     - Ingest probe report into `self.edge_aggregator.ingest_probe_report(data)`.
     - Return 200 OK `{"status": "ingested"}`.
7. Update `create_server`:
   - Initialize `authenticator = Authenticator(mode=os.environ.get("CLUSTERVIS_AUTH_TYPE", "none"))`.
   - Initialize `edge_aggregator = LatencyEdgeAggregator()`.
   - Pass references to `ClusterVisualizerHandler`.

Here is the existing `src/operator/server.py`:
```python
""" + existing + """
```

Output ONLY the complete, updated `src/operator/server.py` inside ```python ```.
"""
    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=4096)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "src/operator/server.py")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Updated {out_path}")

if __name__ == "__main__":
    main()
