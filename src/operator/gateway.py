"""Unified HTTP Gateway for Cluster Visualizer (GKE LoadBalancer & Cloud Run).

Serves:
  - Compiled Vite static frontend from dist/ (/, /index.html, /assets/*, /data/*)
  - Live GKE SSE stream + snapshot API for clustervis-vanilla under /clusters/vanilla/api/v1/*
  - Live GKE SSE stream + snapshot API for clustervis-kuberay under /clusters/kuberay/api/v1/*
  - Default /api/v1/* and /healthz endpoints
"""

import argparse
import json
import logging
import mimetypes
import os
import queue
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from src.operator.controller import TopologyController

logger = logging.getLogger("operator.gateway")

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("model/gltf-binary", ".glb")


class GatewayServer(ThreadingHTTPServer):
    """Multi-threaded HTTP server holding vanilla + kuberay TopologyControllers."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address,
        RequestHandlerClass,
        controller_vanilla: TopologyController,
        controller_kuberay: TopologyController,
        dist_dir: Path,
    ):
        super().__init__(server_address, RequestHandlerClass)
        self.controller_vanilla = controller_vanilla
        self.controller_kuberay = controller_kuberay
        self.dist_dir = dist_dir
        self.start_time = time.time()


class GatewayRequestHandler(BaseHTTPRequestHandler):
    """Serves both dual-cluster SSE/REST APIs and static Vite assets."""

    protocol_version = "HTTP/1.1"

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Accept")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _resolve_controller_and_subpath(self, raw_path: str) -> tuple[Optional[TopologyController], str]:
        srv: GatewayServer = self.server  # type: ignore[assignment]
        for pfx in ("/clusters/cv-kuberay-kueue", "/clusters/kuberay"):
            if raw_path.startswith(pfx):
                sub = raw_path[len(pfx):] or "/"
                return srv.controller_kuberay, sub
        for pfx in ("/clusters/cv-kuberay", "/clusters/vanilla"):
            if raw_path.startswith(pfx):
                sub = raw_path[len(pfx):] or "/"
                return srv.controller_vanilla, sub
        if raw_path.startswith("/api/v1/") or raw_path == "/healthz":
            return srv.controller_kuberay, raw_path
        return None, raw_path

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        raw_path = parsed.path
        ctrl, subpath = self._resolve_controller_and_subpath(raw_path)

        if ctrl is not None:
            if subpath in ("/healthz", "/api/v1/healthz"):
                self._handle_healthz(ctrl)
                return
            if subpath in ("/api/v1/topology", "/api/v1/topology/snapshot"):
                self._handle_snapshot(ctrl)
                return
            if subpath == "/api/v1/topology/stream":
                self._handle_sse_stream(ctrl)
                return

        self._handle_static(raw_path)

    def _handle_healthz(self, ctrl: TopologyController) -> None:
        srv: GatewayServer = self.server  # type: ignore[assignment]
        body = json.dumps({
            "status": "ok",
            "cluster_name": ctrl.cluster_name,
            "uptime_seconds": round(time.time() - srv.start_time, 2),
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self._send_cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_snapshot(self, ctrl: TopologyController) -> None:
        snap = ctrl.get_snapshot()
        body = json.dumps(snap).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self._send_cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_sse_stream(self, ctrl: TopologyController) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self._send_cors_headers()
        self.end_headers()

        q: queue.Queue = queue.Queue(maxsize=256)
        ctrl.add_listener(q)
        try:
            initial = ctrl.get_snapshot()
            init_msg = f"event: initial_snapshot\ndata: {json.dumps(initial)}\n\n"
            self.wfile.write(init_msg.encode("utf-8"))
            self.wfile.flush()

            while True:
                try:
                    event_name, payload = q.get(timeout=10.0)
                    msg = f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            ctrl.remove_listener(q)

    def _handle_static(self, raw_path: str) -> None:
        srv: GatewayServer = self.server  # type: ignore[assignment]
        clean_rel = raw_path.lstrip("/")
        if not clean_rel or clean_rel == "/":
            clean_rel = "index.html"

        target = (srv.dist_dir / clean_rel).resolve()
        dist_root = srv.dist_dir.resolve()
        if not str(target).startswith(str(dist_root)) or not target.is_file():
            # SPA fallback to index.html for unknown non-asset paths
            if "." not in Path(clean_rel).name:
                target = dist_root / "index.html"
            if not target.is_file():
                body = b"Not Found"
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self._send_cors_headers()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

        data = target.read_bytes()
        ctype, _ = mimetypes.guess_type(str(target))
        if not ctype:
            ctype = "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype = f"{ctype}; charset=utf-8"

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self._send_cors_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        pass


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Cluster Visualizer Unified Gateway")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    parser.add_argument("--dist-dir", default=os.environ.get("CLUSTERVIS_DIST_DIR", "dist"))
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()

    vanilla_url = os.environ.get("VANILLA_API_URL", "")
    vanilla_token = os.environ.get("VANILLA_BEARER_TOKEN", "")
    vanilla_ctx = os.environ.get("VANILLA_CONTEXT", "")

    kuberay_url = os.environ.get("KUBERAY_API_URL", "")
    kuberay_token = os.environ.get("KUBERAY_BEARER_TOKEN", "")
    kuberay_ctx = os.environ.get("KUBERAY_CONTEXT", "")

    ctrl_vanilla = TopologyController(
        cluster_name="cv-kuberay",
        context_name=vanilla_ctx,
        api_url=vanilla_url,
        bearer_token=vanilla_token,
    )
    ctrl_kuberay = TopologyController(
        cluster_name="cv-kuberay-kueue",
        context_name=kuberay_ctx,
        api_url=kuberay_url,
        bearer_token=kuberay_token,
    )

    ctrl_vanilla.start(mock=False, poll_interval=args.poll_interval)
    ctrl_kuberay.start(mock=False, poll_interval=args.poll_interval)

    dist_path = Path(args.dist_dir)
    srv = GatewayServer(
        (args.host, args.port),
        GatewayRequestHandler,
        controller_vanilla=ctrl_vanilla,
        controller_kuberay=ctrl_kuberay,
        dist_dir=dist_path,
    )
    logger.info("Cluster Visualizer Gateway listening on http://%s:%d (dist=%s)", args.host, args.port, dist_path)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        ctrl_vanilla.stop()
        ctrl_kuberay.stop()
        srv.server_close()


if __name__ == "__main__":
    main()
