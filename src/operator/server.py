"""
Cluster Visualizer Operator Server

Lightweight HTTP and Server-Sent Events (SSE) server for Cluster Visualizer.
Zero third-party dependencies.
"""

import argparse
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
    from .graph_engine import SecretScrubber, LatencyEdgeAggregator
except ImportError:
    try:
        from src.operator.graph_engine import SecretScrubber, LatencyEdgeAggregator
    except ImportError:
        SecretScrubber = None
        LatencyEdgeAggregator = None


class ClusterVisualizerHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Cluster Visualizer."""

    # Class-level references set by create_server
    controller: Optional[TopologyController] = None
    start_time: float = 0.0
    authenticator: Optional[Any] = None
    edge_aggregator: Optional[Any] = None
    scrub_secrets: bool = True
    cors_allowed_origins: List[str] = ["*"]

    def log_message(self, format: str, *args: Any) -> None:
        """Override to use our logger."""
        logger.info(f"{self.address_string()} - {format % args}")

    def _set_cors_headers(self) -> None:
        """Set CORS headers for all responses."""
        origin = self.headers.get("Origin")
        
        if "*" in self.cors_allowed_origins:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin and origin in self.cors_allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        else:
            # If origin is not allowed, we don't set the header, effectively blocking CORS
            pass

        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Forwarded-User, X-Forwarded-Email")

    def _send_json_response(self, status_code: int, data: Dict[str, Any]) -> None:
        """Send a JSON response."""
        self.send_response(status_code)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _check_auth(self) -> bool:
        """Check authentication for protected endpoints."""
        if self.authenticator is None:
            return True
        
        auth_header = self.headers.get("Authorization")
        if not auth_header:
            return False
        
        # Assuming Authenticator has a method like authenticate(token) or similar
        # Based on typical patterns, we'll try to extract Bearer token
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                # Assuming Authenticator has an 'authenticate' method that returns bool or raises
                # If the interface is different, this might need adjustment.
                # Common pattern: auth.authenticate(token) -> bool
                if hasattr(self.authenticator, 'authenticate'):
                    return self.authenticator.authenticate(token)
                elif hasattr(self.authenticator, 'verify'):
                    return self.authenticator.verify(token)
                else:
                    logger.warning("Authenticator found but no authenticate/verify method")
                    return False
            except Exception as e:
                logger.error(f"Authentication error: {e}")
                return False
        
        return False

    def do_OPTIONS(self) -> None:
        """Handle OPTIONS requests for CORS preflight."""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        """Route GET requests."""
        path = self.path.split("?")[0]  # Strip query params

        if path == "/api/v1/healthz":
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
    if Authenticator is not None:
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
    
    # Parse CORS origins from env, default to ["*"]
    cors_origins_env = os.environ.get("CLUSTERVIS_CORS_ORIGINS", "*")
    ClusterVisualizerHandler.cors_allowed_origins = [o.strip() for o in cors_origins_env.split(",")]

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
        default=10.0,
        help="Poll interval for topology updates in seconds (default: 10.0)",
    )

    args = parser.parse_args()

    # Create controller
    controller = TopologyController()
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
