"""
ClusterVis Synthetic Probe Daemon (clustervis-probe).

TASK-CV-802 / SPEC-07 Section 4.1.

A lightweight, unprivileged, zero-dependency TCP round-robin probe daemon.
It performs non-blocking TCP connect handshakes against discovered peer
targets (adjacent node IPs, workload ports) and measures connection
round-trip time in milliseconds, exposing the results on a local JSON
endpoint consumed by clustervis-operator.

Endpoints:
  GET /metrics/latency  -> {"timestamp": ..., "node": ..., "latencies": [...]}
  GET /healthz          -> {"status": "ok"}

Environment:
  NODE_NAME               Name of the node this probe runs on (Downward API).
  HOST_IP                 Host IP of the node (Downward API).
  POD_IP                  IP of the probe pod (Downward API).
  PROBE_INTERVAL_SECONDS  Round-robin cycle interval (default 3).
  PROBE_TIMEOUT_MS        TCP connect timeout in milliseconds (default 500).
  SAMPLE_TARGET_LIMIT     Max targets probed per cycle (default 20).
  PROBE_PORT              HTTP listen port (default 9102).
  PROBE_TARGETS           Optional comma-separated "host:port" list. When set,
                          the probe runs standalone against these targets and
                          skips in-cluster peer discovery.
  PROBE_WORKLOAD_PORTS    Comma-separated ports tried per discovered peer IP
                          (default 80,443,8080,50051,6379).
"""

import json
import logging
import os
import random
import select
import signal
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [clustervis-probe] %(levelname)s %(message)s",
)
log = logging.getLogger("clustervis-probe")

DEFAULT_PORT = 9102
DEFAULT_INTERVAL_SECONDS = 3.0
DEFAULT_TIMEOUT_MS = 500
DEFAULT_SAMPLE_TARGET_LIMIT = 20
DEFAULT_WORKLOAD_PORTS = (80, 443, 8080, 50051, 6379)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
        return value if value > 0 else default
    except ValueError:
        log.warning("invalid %s=%r, falling back to %s", name, raw, default)
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except ValueError:
        log.warning("invalid %s=%r, falling back to %s", name, raw, default)
        return default


def parse_target_list(raw: str) -> List[Tuple[str, int]]:
    """Parse a comma-separated 'host:port[,host:port...]' target string."""
    targets: List[Tuple[str, int]] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        host, sep, port_str = item.rpartition(":")
        if not sep or not host:
            log.warning("ignoring malformed target %r (want host:port)", item)
            continue
        try:
            targets.append((host, int(port_str)))
        except ValueError:
            log.warning("ignoring malformed target %r (bad port)", item)
    return targets


def discover_peer_targets(
    host_ip: str,
    pod_ip: str,
    ports: Tuple[int, ...] = DEFAULT_WORKLOAD_PORTS,
    neighbor_subnet: Optional[str] = None,
) -> List[Tuple[str, int]]:
    """Best-effort discovery of adjacent node/workload targets.

    Without RBAC (the probe runs unprivileged with no service account
    token), discovery is limited to what the Downward API and local DNS
    reveal: the node's own host IP, the pod gateway derived from the
    route, and any hosts listed in PROBE_TARGETS. A /24 neighbor sweep
    candidate range is generated when a subnet prefix is supplied.
    """
    targets: List[Tuple[str, int]] = []
    seen = set()

    def add(host: str, port: int) -> None:
        key = (host, port)
        if host and key not in seen:
            seen.add(key)
            targets.append(key)

    for port in ports:
        add(host_ip, port)

    # Pod default gateway (kube-proxy / CNI bridge) as a lateral hop.
    gw = _default_gateway()
    if gw:
        for port in ports:
            add(gw, port)

    if neighbor_subnet:
        for last in range(1, 25):
            for port in ports[:1]:
                add(f"{neighbor_subnet}.{last}", port)

    random.shuffle(targets)
    return targets


def _default_gateway() -> str:
    """Read the default gateway IPv4 from /proc/net/route (Linux only)."""
    try:
        with open("/proc/net/route", "r", encoding="ascii") as fh:
            header = fh.readline()  # noqa: F841
            for line in fh:
                fields = line.strip().split()
                if len(fields) >= 3 and fields[1] == "00000000":
                    packed = int(fields[2], 16)
                    return socket.inet_ntoa(packed.to_bytes(4, "little"))
    except OSError:
        pass
    return ""


def probe_tcp_rtt(host: str, port: int, timeout_ms: int) -> Optional[float]:
    """Measure TCP connection handshake RTT in milliseconds.

    Uses a non-blocking socket connect plus select() so the probe never
    blocks the probe loop for longer than timeout_ms. Returns None when
    the connection fails, is refused, or times out.
    """
    timeout_s = timeout_ms / 1000.0
    sock = None
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        if not infos:
            return None
        family, socktype, proto, _, sockaddr = infos[0]
        sock = socket.socket(family, socktype, proto)
        sock.setblocking(False)
        start = time.perf_counter()
        err = sock.connect_ex(sockaddr)
        if err not in (0,):
            # EINPROGRESS (115 on Linux) means handshake still in flight.
            if err != 115:  # noqa: SIM111 - explicit for clarity
                return None
            _, writable, _ = select.select([], [sock], [], timeout_s)
            if not writable:
                return None
            err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if err != 0:
                return None
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if elapsed_ms > timeout_ms:
            return None
        return round(elapsed_ms, 3)
    except OSError:
        return None
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


class LatencyStore:
    """Thread-safe container for the latest probe cycle results."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: Dict[str, object] = {
            "timestamp": 0.0,
            "node": "",
            "latencies": [],
        }
        self._cycles = 0

    def publish(self, node: str, latencies: List[Dict[str, object]]) -> None:
        with self._lock:
            self._latest = {
                "timestamp": time.time(),
                "node": node,
                "latencies": latencies,
            }
            self._cycles += 1

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return json.loads(json.dumps(self._latest))

    @property
    def cycles(self) -> int:
        with self._lock:
            return self._cycles


class ProbeDaemon:
    """Round-robin TCP probe loop driving a LatencyStore."""

    def __init__(
        self,
        node_name: str,
        host_ip: str,
        pod_ip: str,
        interval_seconds: float,
        timeout_ms: int,
        sample_target_limit: int,
        store: LatencyStore,
        explicit_targets: Optional[List[Tuple[str, int]]] = None,
        workload_ports: Tuple[int, ...] = DEFAULT_WORKLOAD_PORTS,
    ) -> None:
        self.node_name = node_name
        self.host_ip = host_ip
        self.pod_ip = pod_ip
        self.interval_seconds = interval_seconds
        self.timeout_ms = timeout_ms
        self.sample_target_limit = sample_target_limit
        self.store = store
        self.explicit_targets = explicit_targets or []
        self.workload_ports = workload_ports
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._cursor = 0
        self._targets_cache: List[Tuple[str, int]] = []
        self._targets_cached_at = 0.0

    def start(self) -> None:
        self.running = True
        self._thread = threading.Thread(target=self._run, name="probe-loop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        if self._thread is not None:
            self._thread.join(timeout=self.interval_seconds + 2.0)

    def current_targets(self) -> List[Tuple[str, int]]:
        """Explicit targets win; otherwise refresh discovered peers every 5 cycles."""
        if self.explicit_targets:
            return self.explicit_targets
        if (time.time() - self._targets_cached_at) > max(
            self.interval_seconds * 5, 15.0
        ):
            self._targets_cache = discover_peer_targets(
                self.host_ip, self.pod_ip, ports=self.workload_ports
            )
            self._targets_cached_at = time.time()
            log.info("discovered %d peer targets", len(self._targets_cache))
        return self._targets_cache

    def run_cycle(self) -> Dict[str, List[Dict[str, object]]]:
        targets = self.current_targets()
        latencies: List[Dict[str, object]] = []
        if targets:
            # Round-robin: rotate the window so every target is covered
            # over successive cycles while capping per-cycle fan-out.
            window = [
                targets[(self._cursor + i) % len(targets)]
                for i in range(min(self.sample_target_limit, len(targets)))
            ]
            self._cursor = (self._cursor + len(window)) % len(targets)
            for host, port in window:
                rtt = probe_tcp_rtt(host, port, self.timeout_ms)
                latencies.append(
                    {
                        "target": f"{host}:{port}",
                        "reachable": rtt is not None,
                        "rtt_ms": rtt,
                    }
                )
        result = {"node": self.node_name, "latencies": latencies}
        self.store.publish(**result)
        return result

    def _run(self) -> None:
        log.info(
            "probe loop starting: node=%s interval=%.1fs timeout=%dms limit=%d",
            self.node_name,
            self.interval_seconds,
            self.timeout_ms,
            self.sample_target_limit,
        )
        while self.running:
            cycle_start = time.monotonic()
            try:
                result = self.run_cycle()
                reachable = sum(1 for l in result["latencies"] if l["reachable"])
                log.debug(
                    "cycle: %d/%d reachable", reachable, len(result["latencies"])
                )
            except Exception:  # noqa: BLE001 - probe loop must never die
                log.exception("probe cycle failed")
            elapsed = time.monotonic() - cycle_start
            # Sleep in small increments so shutdown stays responsive.
            deadline = cycle_start + self.interval_seconds
            while self.running and time.monotonic() < deadline:
                time.sleep(min(0.25, deadline - time.monotonic()))
        log.info("probe loop stopped")


class ProbeHTTPHandler(BaseHTTPRequestHandler):
    store: LatencyStore  # injected on the server class
    server_version = "clustervis-probe/1.0"

    def _respond(self, status: int, payload: Dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path == "/metrics/latency":
            self._respond(200, self.store.snapshot())
        elif path == "/healthz":
            self._respond(200, {"status": "ok"})
        else:
            self._respond(404, {"error": "not found", "paths": ["/metrics/latency", "/healthz"]})

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        log.debug("http %s - %s", self.address_string(), format % args)


def build_server(port: int, store: LatencyStore) -> ThreadingHTTPServer:
    class BoundHandler(ProbeHTTPHandler):
        pass

    BoundHandler.store = store
    server = ThreadingHTTPServer(("0.0.0.0", port), BoundHandler)
    server.daemon_threads = True
    return server


def main() -> int:
    node_name = os.environ.get("NODE_NAME", "").strip() or socket.gethostname()
    host_ip = os.environ.get("HOST_IP", "").strip()
    pod_ip = os.environ.get("POD_IP", "").strip()
    interval = _env_float("PROBE_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS)
    timeout_ms = _env_int("PROBE_TIMEOUT_MS", DEFAULT_TIMEOUT_MS)
    limit = _env_int("SAMPLE_TARGET_LIMIT", DEFAULT_SAMPLE_TARGET_LIMIT)
    port = _env_int("PROBE_PORT", DEFAULT_PORT)

    raw_targets = os.environ.get("PROBE_TARGETS", "").strip()
    explicit = parse_target_list(raw_targets) if raw_targets else []
    if raw_targets and not explicit:
        log.error("PROBE_TARGETS set but no valid targets parsed from %r", raw_targets)
        return 2

    ports_raw = os.environ.get("PROBE_WORKLOAD_PORTS", "").strip()
    workload_ports = DEFAULT_WORKLOAD_PORTS
    if ports_raw:
        parsed_ports = []
        for p in ports_raw.split(","):
            try:
                parsed_ports.append(int(p.strip()))
            except ValueError:
                log.warning("ignoring bad PROBE_WORKLOAD_PORTS entry %r", p)
        if parsed_ports:
            workload_ports = tuple(parsed_ports)

    store = LatencyStore()
    daemon = ProbeDaemon(
        node_name=node_name,
        host_ip=host_ip,
        pod_ip=pod_ip,
        interval_seconds=interval,
        timeout_ms=timeout_ms,
        sample_target_limit=limit,
        store=store,
        explicit_targets=explicit,
        workload_ports=workload_ports,
    )
    daemon.run_cycle()  # Prime metrics before serving traffic.
    daemon.start()

    httpd = build_server(port, store)
    log.info(
        "serving /metrics/latency and /healthz on :%d (node=%s, mode=%s)",
        port,
        node_name,
        "static-targets" if explicit else "peer-discovery",
    )

    def _shutdown(signum, _frame) -> None:  # noqa: ANN001
        log.info("signal %s received, shutting down", signum)
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        httpd.serve_forever(poll_interval=0.25)
    finally:
        daemon.stop()
        httpd.server_close()
        log.info("shutdown complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
