"""
Cluster Visualizer Operator Server

Lightweight HTTP and Server-Sent Events (SSE) server for Cluster Visualizer.
Zero third-party dependencies.
"""

import argparse
import asyncio
import json
import logging
import os
import queue
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("operator.server")

try:
    from .controller import TopologyController
except ImportError:
    try:
        from src.operator.controller import TopologyController
    except ImportError:
        raise ImportError("Could not import TopologyController from .controller or src.operator.controller")

try:
    from .auth import Authenticator
except ImportError:
    try:
        from src.operator.auth import Authenticator
    except ImportError:
        Authenticator = None

try:
    from .graph_engine import SecretScrubber, LatencyEdgeAggregator, WhitelistExtractor
except ImportError:
    try:
        from src.operator.graph_engine import (
            SecretScrubber,
            LatencyEdgeAggregator,
            WhitelistExtractor,
        )
    except ImportError:
        SecretScrubber = None
        LatencyEdgeAggregator = None
        WhitelistExtractor = None


class AsyncFanoutBroadcast:
    """
    Event-loop non-blocking fan-out broadcast queue (SPEC-13 §3.4).

    Informer churn publishes once and fans out to every subscriber without ever
    blocking the event loop: slow consumers have their oldest queued event dropped
    rather than stalling the whole broadcast.
    """

    def __init__(self, maxsize: int = 100) -> None:
        self._subscribers: set = set()
        self.maxsize = int(maxsize)

    async def publish(self, event_name: str, payload: dict) -> None:
        """Fan out an (event_name, payload) tuple to all subscribers."""
        if not self._subscribers:
            return
        stale = []
        for sub in list(self._subscribers):
            try:
                sub.put_nowait((event_name, payload))
            except asyncio.QueueFull:
                # Slow consumer: evict the oldest event so we never block.
                try:
                    sub.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    sub.put_nowait((event_name, payload))
                except asyncio.QueueFull:
                    stale.append(sub)
        for s in stale:
            self._subscribers.discard(s)

    def subscribe(self) -> "asyncio.Queue":
        q: asyncio.Queue = asyncio.Queue(maxsize=self.maxsize)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: "asyncio.Queue") -> None:
        self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


class ClusterVisualizerHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Cluster Visualizer."""

    # Class-level references set by create_server
    controller: Optional[TopologyController] = None
    start_time: float = 0.0
    authenticator: Optional[Any] = None
    edge_aggregator: Optional[Any] = None
    scrub_secrets: bool = True
    cors_allowed_origins: List[str] = ["*"]
    # Active auth mode ("none" | "token" | "oauth2-proxy") — used to decide
    # whether the wildcard CORS origin is acceptable (SPEC-13 §3.3 / ADR-1303).
    auth_mode: str = "none"

    def log_message(self, format: str, *args: Any) -> None:
        """Override to use our logger."""
        logger.info(f"{self.address_string()} - {format % args}")

    def _set_cors_headers(self) -> None:
        """Set CORS headers for all responses (strict when auth is enabled)."""
        origin = self.headers.get("Origin")
        allow_wildcard = "*" in self.cors_allowed_origins

        # SPEC-13 §3.3 / ADR-1303: deprecate the wildcard '*' whenever a real
        # auth mode (oauth2-proxy or token) is active — never echo credentials to
        # an arbitrary origin.
        if allow_wildcard and self.auth_mode in ("oauth2-proxy", "token"):
            allow_wildcard = False

        if allow_wildcard:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin and origin in self.cors_allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        else:
            # Origin not allowed → omit the header, effectively blocking CORS.
            pass

        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-Forwarded-User, X-Forwarded-Email, "
            "X-Forwarded-Groups, X-Forwarded-Access-Signature",
        )

    def _send_json_response(self, status_code: int, data: Dict[str, Any]) -> None:
        """Send a JSON response."""
        self.send_response(status_code)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _check_auth(self) -> bool:
        """Check authentication for protected endpoints (SPEC-13 §3.3)."""
        if self.authenticator is None:
            return True

        headers = {k: v for k, v in self.headers.items()}
        try:
            ok, _user, err = self.authenticator.authenticate_request(headers)
        except Exception as e:  # noqa: BLE001 — fail closed on auth errors
            logger.error(f"Authentication error: {e}")
            return False
        if not ok:
            logger.info(f"Auth rejected: {err}")
        return ok

    def do_OPTIONS(self) -> None:
        """Handle OPTIONS requests for CORS preflight."""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        """Route GET requests."""
        path = self.path.split("?")[0]  # Strip query params

        if path in ("/api/v1/healthz", "/healthz"):
            self._handle_healthz()
        elif path in ["/api/v1/topology", "/api/v1/topology/snapshot", "/api/v1/topology/stream"]:
            if not self._check_auth():
                self.send_response(401)
                self._set_cors_headers()
                self.send_header("WWW-Authenticate", 'Bearer realm="clustervis"')
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Unauthorized", "detail": "Invalid or missing token"}).encode("utf-8"))
                return
            
            if path == "/api/v1/topology/stream":
                self._handle_topology_stream()
            else:
                self._handle_topology_snapshot()
        else:
            self._send_json_response(404, {"error": "Not Found", "path": path})

    def do_POST(self) -> None:
        """Route POST requests."""
        path = self.path.split("?")[0]

        if path == "/api/v1/telemetry/latency":
            self._handle_telemetry_latency()
        else:
            self._send_json_response(404, {"error": "Not Found", "path": path})

    def _handle_healthz(self) -> None:
        """Handle health check endpoint."""
        uptime = time.time() - self.start_time
        self._send_json_response(200, {"status": "ok", "uptime_seconds": uptime})

    def _handle_topology_snapshot(self) -> None:
        """Handle topology snapshot endpoint."""
        if self.controller is None:
            self._send_json_response(503, {"error": "Controller not available"})
            return
        try:
            snapshot = self.controller.get_snapshot()
            
            if self.scrub_secrets and SecretScrubber is not None:
                try:
                    snapshot = SecretScrubber.scrub_graph(snapshot)
                except Exception as e:
                    logger.error(f"Error scrubbing secrets: {e}")
                    # Decide whether to fail or return unscrubbed. 
                    # Security best practice: fail closed if scrubbing fails.
                    self._send_json_response(500, {"error": "Internal Server Error", "detail": "Secret scrubbing failed"})
                    return

            self._send_json_response(200, snapshot)
        except Exception as e:
            logger.error(f"Error getting snapshot: {e}")
            self._send_json_response(500, {"error": "Internal Server Error"})

    def _handle_topology_stream(self) -> None:
        """Handle SSE stream endpoint."""
        if self.controller is None:
            self._send_json_response(503, {"error": "Controller not available"})
            return

        # Set SSE headers
        self.send_response(200)
        self._set_cors_headers()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        # Create a queue for this client
        client_queue: queue.Queue = queue.Queue(maxsize=100)
        self.controller.add_listener(client_queue)

        try:
            # Send initial snapshot
            initial_snapshot = self.controller.get_snapshot()
            
            if self.scrub_secrets and SecretScrubber is not None:
                try:
                    initial_snapshot = SecretScrubber.scrub_graph(initial_snapshot)
                except Exception as e:
                    logger.error(f"Error scrubbing secrets in stream init: {e}")
                    # Send error event and close
                    error_event = f"event: error\ndata: {json.dumps({'error': 'Scrubbing failed'})}\n\n"
                    self.wfile.write(error_event.encode("utf-8"))
                    self.wfile.flush()
                    return

            initial_event = f"event: initial_snapshot\ndata: {json.dumps(initial_snapshot)}\n\n"
            self.wfile.write(initial_event.encode("utf-8"))
            self.wfile.flush()

            last_heartbeat = time.time()
            heartbeat_interval = 15.0

            while True:
                try:
                    # Wait for event with timeout
                    event_name, payload = client_queue.get(timeout=1.0)

                    # Scrub payload if needed
                    if self.scrub_secrets and SecretScrubber is not None:
                        try:
                            # Assuming payload is a dict that can be scrubbed
                            # If payload structure is different, adjust accordingly
                            if isinstance(payload, dict):
                                payload = SecretScrubber.scrub_graph(payload)
                        except Exception as e:
                            logger.error(f"Error scrubbing secrets in stream event: {e}")
                            # Skip event or send error? Skipping is safer for stream continuity
                            continue

                    # Send event
                    event_str = f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"
                    self.wfile.write(event_str.encode("utf-8"))
                    self.wfile.flush()
                    last_heartbeat = time.time()

                except queue.Empty:
                    # Check if heartbeat is needed
                    now = time.time()
                    if now - last_heartbeat >= heartbeat_interval:
                        heartbeat_data = {
                            "timestamp": now,
                            "active_clients": len(self.controller.listeners),
                        }
                        heartbeat_event = f"event: heartbeat\ndata: {json.dumps(heartbeat_data)}\n\n"
                        self.wfile.write(heartbeat_event.encode("utf-8"))
                        self.wfile.flush()
                        last_heartbeat = now

        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            logger.info(f"Client disconnected: {e}")
        except Exception as e:
            logger.error(f"Error in SSE stream: {e}")
        finally:
            self.controller.remove_listener(client_queue)
            logger.info("SSE stream closed.")

    def _handle_telemetry_latency(self) -> None:
        """Handle latency telemetry ingestion."""
        if self.edge_aggregator is None:
            self._send_json_response(503, {"error": "Telemetry aggregator not available"})
            return

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._send_json_response(400, {"error": "Empty request body"})
                return
            
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            self.edge_aggregator.ingest_probe_report(data)
            self._send_json_response(200, {"status": "ingested"})
        except json.JSONDecodeError:
            self._send_json_response(400, {"error": "Invalid JSON"})
        except Exception as e:
            logger.error(f"Error ingesting telemetry: {e}")
            self._send_json_response(500, {"error": "Internal Server Error"})


# ---------------------------------------------------------------------------
# Async streaming layer (SPEC-13 §3.4): asyncio + non-blocking fan-out.
#
# The synchronous ThreadingHTTPServer above remains for backward compatibility;
# this ASGI-style app is the forward path that never blocks the event loop while
# broadcasting informer churn to many SSE/WebSocket clients.
# ---------------------------------------------------------------------------


async def _sse_frames(
    broadcast: AsyncFanoutBroadcast,
    controller: Optional[TopologyController],
    scrub_secrets: bool = True,
    heartbeat_interval: float = 15.0,
):
    """Yield ``event: <name>\\ndata: {...}\\n\\n`` frames from the fan-out queue."""
    queue_: "asyncio.Queue" = broadcast.subscribe()
    try:
        if controller is not None:
            snapshot = controller.get_snapshot()
            if scrub_secrets and SecretScrubber is not None:
                snapshot = SecretScrubber.scrub_graph(snapshot)
            yield f"event: initial_snapshot\ndata: {json.dumps(snapshot)}\n\n"

        while True:
            try:
                event_name, payload = await asyncio.wait_for(
                    queue_.get(), timeout=heartbeat_interval
                )
            except asyncio.TimeoutError:
                now = time.time()
                yield f"event: heartbeat\ndata: {json.dumps({'timestamp': now})}\n\n"
                continue

            if scrub_secrets and SecretScrubber is not None and isinstance(payload, dict):
                try:
                    payload = SecretScrubber.scrub_graph(payload)
                except Exception as e:  # noqa: BLE001 — keep stream alive
                    logger.error(f"Error scrubbing async stream event: {e}")
                    continue
            yield f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"
    finally:
        broadcast.unsubscribe(queue_)


def _asgi_headers(scope: dict) -> Dict[str, str]:
    """Normalise the ASGI ``scope["headers"]`` list into a header mapping."""
    headers: Dict[str, str] = {}
    for k, v in scope.get("headers", []):
        try:
            key = k.decode("utf-8")
            val = v.decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            continue
        headers[key] = val
    return headers


def _asgi_cors_headers(scope: dict) -> List[tuple]:
    """Mirror the sync handler's ``_set_cors_headers`` policy for ASGI responses.

    The wildcard '*' is suppressed whenever a real auth mode (oauth2-proxy or
    token) is active, and unlisted origins receive no ACAO header at all.
    """
    headers: List[tuple] = []
    origin = None
    for k, v in scope.get("headers", []):
        try:
            if k.decode("utf-8").lower() == "origin":
                origin = v.decode("utf-8")
                break
        except (UnicodeDecodeError, AttributeError):
            continue

    allow_wildcard = "*" in ClusterVisualizerHandler.cors_allowed_origins
    if (
        allow_wildcard
        and ClusterVisualizerHandler.auth_mode in ("oauth2-proxy", "token")
    ):
        allow_wildcard = False

    if allow_wildcard:
        headers.append((b"access-control-allow-origin", b"*"))
    elif origin and origin in ClusterVisualizerHandler.cors_allowed_origins:
        headers.append((b"access-control-allow-origin", origin.encode("utf-8")))
        headers.append((b"vary", b"Origin"))

    headers.append((b"access-control-allow-methods", b"GET, POST, OPTIONS"))
    headers.append((
        b"access-control-allow-headers",
        b"Content-Type, Authorization, X-Forwarded-User, X-Forwarded-Email, "
        b"X-Forwarded-Groups, X-Forwarded-Access-Signature",
    ))
    return headers


def _asgi_check_auth(scope: dict) -> "tuple[bool, str, Optional[str]]":
    """Gate an ASGI request through the same authenticator as the sync handler."""
    auth = ClusterVisualizerHandler.authenticator
    if auth is None:
        return True, "", None
    headers = _asgi_headers(scope)
    try:
        ok, user, err = auth.authenticate_request(headers)
    except Exception as e:  # noqa: BLE001 — fail closed on auth errors
        logger.error(f"Authentication error: {e}")
        return False, "", str(e)
    if not ok:
        logger.info(f"Auth rejected: {err}")
    return ok, user, err


async def _asgi_deny(scope, send, status: int) -> None:
    """Send an authenticated-required 401/403 response with CORS headers."""
    body = json.dumps(
        {"error": "Unauthorized", "detail": "Invalid or missing credentials"}
    ).encode("utf-8")
    headers = _asgi_cors_headers(scope)
    headers.append((b"content-type", b"application/json"))
    headers.append((b"www-authenticate", b'Bearer realm="clustervis"'))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def operator_asgi_app(scope, receive, send):
    """Minimal ASGI app: /api/v1/healthz, /snapshot and SSE /stream.

    Protected endpoints (/snapshot, /topology, /stream) are gated through the
    same ``authenticate_request`` HMAC/bearer check as the sync handler, and every
    response carries the same CORS policy (SPEC-13 §3.3/§3.4, ADR-1303).
    """
    if scope["type"] != "http":
        await send({"type": "websocket.close"})
        return

    path = scope.get("path", "")
    if path in ("/api/v1/topology/snapshot", "/api/v1/topology", "/"):
        ok, _user, _err = _asgi_check_auth(scope)
        if not ok:
            await _asgi_deny(scope, send, 401)
            return
        controller = ClusterVisualizerHandler.controller
        snapshot: Any = {}
        if controller is not None:
            try:
                snapshot = controller.get_snapshot()
                if (
                    ClusterVisualizerHandler.scrub_secrets
                    and SecretScrubber is not None
                ):
                    snapshot = SecretScrubber.scrub_graph(snapshot)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Error building async snapshot: {e}")
        body = json.dumps(snapshot).encode("utf-8")
        headers = _asgi_cors_headers(scope)
        headers.append((b"content-type", b"application/json"))
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": headers,
        })
        await send({"type": "http.response.body", "body": body})
        return

    if path == "/api/v1/healthz":
        body = json.dumps(
            {"status": "ok", "uptime_seconds": time.time() - ClusterVisualizerHandler.start_time}
        ).encode("utf-8")
        headers = _asgi_cors_headers(scope)
        headers.append((b"content-type", b"application/json"))
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": headers,
        })
        await send({"type": "http.response.body", "body": body})
        return

    if path == "/api/v1/topology/stream":
        ok, _user, _err = _asgi_check_auth(scope)
        if not ok:
            await _asgi_deny(scope, send, 401)
            return
        broadcast = AsyncFanoutBroadcast()
        headers = _asgi_cors_headers(scope)
        headers.extend([
            (b"content-type", b"text/event-stream"),
            (b"cache-control", b"no-cache"),
            (b"x-accel-buffering", b"no"),
        ])
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": headers,
        })
        async for frame in _sse_frames(
            broadcast, ClusterVisualizerHandler.controller, ClusterVisualizerHandler.scrub_secrets
        ):
            await send({"type": "http.response.body", "body": frame.encode("utf-8"), "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        return

    headers = _asgi_cors_headers(scope)
    headers.append((b"content-type", b"application/json"))
    await send({
        "type": "http.response.start",
        "status": 404,
        "headers": headers,
    })
    await send({"type": "http.response.body", "body": json.dumps({"error": "Not Found"}).encode("utf-8")})


def create_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    controller: Optional[TopologyController] = None,
) -> ThreadingHTTPServer:
    """
    Create and configure the HTTP server.

    Args:
        host: Host to bind to.
        port: Port to bind to.
        controller: TopologyController instance. If None, a mock one is created.

    Returns:
        Configured ThreadingHTTPServer instance.
    """
    if controller is None:
        controller = TopologyController()
        controller.start(mock=True)

    # Initialize Authenticator
    auth_type = os.environ.get("CLUSTERVIS_AUTH_TYPE", "none")
    authenticator = None
    if Authenticator is not None and auth_type.lower() not in ("", "none", "disabled", "false"):
        try:
            authenticator = Authenticator(mode=auth_type)
        except Exception as e:
            logger.error(f"Failed to initialize Authenticator: {e}")
    
    # Initialize LatencyEdgeAggregator
    edge_aggregator = None
    if LatencyEdgeAggregator is not None:
        try:
            edge_aggregator = LatencyEdgeAggregator()
        except Exception as e:
            logger.error(f"Failed to initialize LatencyEdgeAggregator: {e}")

    # Set class-level attributes
    ClusterVisualizerHandler.controller = controller
    ClusterVisualizerHandler.start_time = time.time()
    ClusterVisualizerHandler.authenticator = authenticator
    ClusterVisualizerHandler.edge_aggregator = edge_aggregator
    ClusterVisualizerHandler.scrub_secrets = os.environ.get("CLUSTERVIS_SCRUB_SECRETS", "true").lower() == "true"
    # SPEC-13 §3.3 / ADR-1303: expose the active auth mode so CORS handling can
    # deprecate the wildcard '*' origin whenever credentials are involved.
    ClusterVisualizerHandler.auth_mode = auth_type

    # Parse CORS origins from env, default to ["*"]
    cors_origins_env = os.environ.get("CLUSTERVIS_CORS_ORIGINS", "*")
    allowed_origins = [o.strip() for o in cors_origins_env.split(",")]

    # SPEC-13 §3.3 / ADR-1303: with a real auth mode the wildcard '*' is
    # deprecated — an explicit origin allow-list must be configured instead.
    if "*" in allowed_origins and auth_type in ("oauth2-proxy", "token"):
        logger.warning(
            f"CORS wildcard '*' is deprecated under auth mode {auth_type!r}; "
            "restricting to explicitly configured origins (CLUSTERVIS_CORS_ORIGINS)."
        )
        allowed_origins = [o for o in allowed_origins if o != "*"]

    ClusterVisualizerHandler.cors_allowed_origins = allowed_origins

    server = ThreadingHTTPServer((host, port), ClusterVisualizerHandler)
    server.daemon_threads = True

    logger.info(f"Server created on {host}:{port}")
    return server


def main() -> None:
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="Cluster Visualizer Operator Server"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind to (default: 8080)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=True,
        help="Use mock topology data (default: True)",
    )
    parser.add_argument(
        "--no-mock",
        action="store_false",
        dest="mock",
        help="Disable mock topology data",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("CLUSTERVIS_EXPORT_INTERVAL_SECONDS", "2.0")),
        help="Poll interval for topology updates in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--context",
        type=str,
        default=os.environ.get("CLUSTERVIS_CONTEXT", ""),
        help="Kubernetes context name to poll (empty for in-cluster ServiceAccount)",
    )
    parser.add_argument(
        "--cluster-name",
        type=str,
        default=os.environ.get("CLUSTERVIS_CLUSTER_NAME", "in-cluster"),
        help="Cluster display name in metadata",
    )

    args = parser.parse_args()
    if args.context or os.environ.get("CLUSTERVIS_REAL_MODE", "").lower() in ("1", "true", "yes"):
        args.mock = False

    # Create controller
    controller = TopologyController(cluster_name=args.cluster_name, context_name=args.context)
    controller.start(mock=args.mock, poll_interval=args.interval)

    # Create server
    server = create_server(host=args.host, port=args.port, controller=controller)

    # Graceful shutdown handling
    shutdown_event = threading.Event()

    def signal_handler(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}, shutting down...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start server in a separate thread
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    logger.info(f"Server listening on http://{args.host}:{args.port}")
    logger.info("Press Ctrl+C to stop.")

    # Wait for shutdown signal
    try:
        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=1.0)
    except KeyboardInterrupt:
        pass

    logger.info("Shutting down server...")
    server.shutdown()
    server.server_close()
    controller.stop()
    logger.info("Server stopped.")


if __name__ == "__main__":
    main()
