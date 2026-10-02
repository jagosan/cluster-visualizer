#!/usr/bin/env python3
"""
TASK-CV-502 & TASK-CV-503: Jagular runner for Topology Controller & SSE Streaming Server.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    print("--- Summoning Jagular for TASK-CV-502 & TASK-CV-503 (src/operator/) ---")
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead systems and Kubernetes architect.
You author production-grade, zero-dependency, asynchronous Python server and controller modules."""

    # 1. TASK-CV-502: src/operator/controller.py
    user_prompt_controller = """SPEC-04 / TASK-CV-502:
Author `src/operator/controller.py`: The in-cluster Kubernetes topology informer controller.

Requirements:
1. Class `TopologyController`:
   - Maintains live in-memory cluster topology state: nodes, pods, daemonsets, control plane, frameworks.
   - Secret scrubbing:
     Scrub any passwords, keys, tokens to `[REDACTED]` or `sha256:...`.
   - Layout calculation:
     Uses `from src.ingestion.layout import apply_spatial_layout, generate_skyscraper_edges`
     Uses `from src.ingestion.models import ClusterGraph, NodeComponent, DataFlowEdge, ClusterMetadata, Spatial`
     Uses `from src.ingestion.frameworks import enrich_framework_components`
   - State & Event Emission:
     Maintains registered client listener queues: `add_listener(queue)` and `remove_listener(queue)`.
     When changes occur, broadcasts events to all listeners:
     - `event: initial_snapshot` -> Full `ClusterGraph` dict/json.
     - `event: node_added` -> `{"node": <NodeComponent dict>, "timestamp": ...}`
     - `event: node_removed` -> `{"node_id": "...", "timestamp": ...}`
     - `event: node_modified` -> `{"node_id": "...", "diffDetails": [...], "status": "version_skew"}`
     - `event: edge_updated` -> `{"edges": [<DataFlowEdge dict>, ...]}`
   - Support `inject_mock_mutation(mutation_type: str, data: dict)` or synthetic testbed mode:
     Allows tests or standalone demo runs to inject `node_added`, `node_removed`, `node_modified` dynamically.
   - Informer / Watch loop:
     Provides `start()` (runs watch/poll worker in background thread or loop) and `stop()` methods.
     In live mode, uses `kubectl` or direct API queries with graceful fallbacks if disconnected or in test environments.
   - Method `get_snapshot() -> dict`:
     Returns full current `ClusterGraph` serialized to Python dict.

Write the complete `src/operator/controller.py`.
Output ONLY Python code inside ```python ```.
"""

    code_controller = call_jagular(system_prompt, user_prompt_controller, temperature=0.1, max_tokens=4000)
    match_ctrl = re.search(r"```python\s*(.*?)\s*```", code_controller, re.DOTALL)
    if match_ctrl:
        code_controller = match_ctrl.group(1)

    os.makedirs(os.path.join(REPO_ROOT, "src/operator"), exist_ok=True)
    out_ctrl_path = os.path.join(REPO_ROOT, "src/operator/controller.py")
    with open(out_ctrl_path, "w") as f:
        f.write(code_controller.strip() + "\n")
    print(f"Authored {out_ctrl_path}")

    # 2. TASK-CV-503: src/operator/server.py
    user_prompt_server = """SPEC-04 / TASK-CV-503:
Author `src/operator/server.py`: Lightweight HTTP and Server-Sent Events (SSE) server.

Requirements:
1. Zero third-party dependencies (use Python standard library `http.server`, `threading`, `queue`, `json`, `time`, `argparse`).
2. Endpoints:
   - `GET /api/v1/healthz`:
     Returns HTTP 200 with JSON: `{"status": "ok", "uptime_seconds": <float>}`.
     Headers: `Content-Type: application/json`, `Access-Control-Allow-Origin: *`.
   - `GET /api/v1/topology/snapshot`:
     Returns HTTP 200 with current full `ClusterGraph` JSON from `controller.get_snapshot()`.
     Headers: `Content-Type: application/json`, `Access-Control-Allow-Origin: *`.
   - `GET /api/v1/topology/stream`:
     SSE endpoint emitting `text/event-stream`.
     Headers:
       `Content-Type: text/event-stream`
       `Cache-Control: no-cache`
       `Connection: keep-alive`
       `Access-Control-Allow-Origin: *`
       `X-Accel-Buffering: no`
     Protocol:
       1. Immediately sends `event: initial_snapshot\ndata: <JSON>\n\n`
       2. Creates a subscriber queue in `controller.add_listener(q)`.
       3. Streams new events as they arrive from `q`:
          `event: <event_name>\ndata: <json_string>\n\n`
       4. Sends periodic heartbeat every 15 seconds:
          `event: heartbeat\ndata: {"timestamp": "<iso>", "active_clients": <int>}\n\n`
       5. Cleanly removes listener when client disconnects (`controller.remove_listener(q)`).
   - `OPTIONS` request handling for CORS preflight on all routes.
3. Server Lifecycle & CLI:
   - Command line options via `argparse`:
     `--port`: Port to listen on (default 8080)
     `--host`: Host to bind (default "0.0.0.0")
     `--mock`: Enable mock/simulation mode with periodic simulated workload changes
     `--context`: Kubernetes context name
   - Clean shutdown on SIGINT/SIGTERM.
   - Provides a `create_server(host, port, controller)` function so unit tests can instantiate and stop it programmatically.

Write the complete `src/operator/server.py`.
Output ONLY Python code inside ```python ```.
"""

    code_server = call_jagular(system_prompt, user_prompt_server, temperature=0.1, max_tokens=4000)
    match_srv = re.search(r"```python\s*(.*?)\s*```", code_server, re.DOTALL)
    if match_srv:
        code_server = match_srv.group(1)

    out_srv_path = os.path.join(REPO_ROOT, "src/operator/server.py")
    with open(out_srv_path, "w") as f:
        f.write(code_server.strip() + "\n")
    print(f"Authored {out_srv_path}")

    # Ensure __init__.py exists
    init_path = os.path.join(REPO_ROOT, "src/operator/__init__.py")
    with open(init_path, "w") as f:
        f.write('"""Cluster Visualizer In-Cluster Streaming Operator."""\n')
    print(f"Ensured {init_path}")

if __name__ == "__main__":
    run()
