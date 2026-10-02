#!/usr/bin/env python3
"""
TASK-CV-503: Jagular runner for HTTP and SSE Streaming Server.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    print("--- Summoning Jagular for TASK-CV-503 (src/operator/server.py) ---")
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead systems architect.
You author production-grade, zero-dependency Python HTTP and SSE servers using standard library `http.server`."""

    user_prompt = """SPEC-04 / TASK-CV-503:
Author `src/operator/server.py`: Lightweight HTTP and Server-Sent Events (SSE) server for Cluster Visualizer.

Requirements:
1. Zero third-party dependencies: use Python stdlib `http.server`, `socketserver`, `threading`, `queue`, `json`, `time`, `argparse`.
2. Architecture:
   - Server handler inherits from `http.server.BaseHTTPRequestHandler`.
   - Uses `ThreadingHTTPServer` from `http.server` (Python 3.7+) to support concurrent long-lived SSE connections and regular HTTP requests.
   - Handlers:
     - `GET /api/v1/healthz`:
       Returns 200 JSON `{"status": "ok", "uptime_seconds": time.time() - start_time}`.
       CORS: `Access-Control-Allow-Origin: *`.
     - `GET /api/v1/topology/snapshot`:
       Calls `controller.get_snapshot()`, returns 200 JSON.
       CORS: `Access-Control-Allow-Origin: *`.
     - `GET /api/v1/topology/stream`:
       SSE endpoint emitting `text/event-stream`.
       Headers:
         `Content-Type: text/event-stream`
         `Cache-Control: no-cache`
         `Connection: keep-alive`
         `Access-Control-Allow-Origin: *`
         `X-Accel-Buffering: no`
       Sends initial frame:
         `event: initial_snapshot\ndata: <json>\n\n`
       Registers a `queue.Queue` with `controller.add_listener(client_queue)`.
       Enters loop while connected:
         Check queue with timeout (e.g. 1.0s).
         If event available:
           `event: {event_name}\ndata: {json.dumps(payload)}\n\n`
           Flush wfile.
         Every 15s without events, emit heartbeat:
           `event: heartbeat\ndata: {"timestamp": ..., "active_clients": len(controller.listeners)}\n\n`
           Flush wfile.
       On client disconnect (`BrokenPipeError`, `ConnectionResetError`, etc.):
         `controller.remove_listener(client_queue)`.
     - `OPTIONS` method:
       Returns 200 with CORS headers (`Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: GET, OPTIONS`, `Access-Control-Allow-Headers: Content-Type`).
3. Factory & CLI:
   - `def create_server(host: str = "0.0.0.0", port: int = 8080, controller: Optional[TopologyController] = None) -> ThreadingHTTPServer`:
     Creates, configures, and returns the server.
   - CLI via `main()`:
     `--host`, `--port` (default 8080), `--mock` (flag, default True), `--interval` (poll interval, default 10.0).
     Starts controller and server, handles SIGINT/SIGTERM gracefully.

Write the complete `src/operator/server.py`.
Output ONLY Python code inside ```python ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3500)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "src/operator/server.py")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Authored {out_path}")

if __name__ == "__main__":
    run()
