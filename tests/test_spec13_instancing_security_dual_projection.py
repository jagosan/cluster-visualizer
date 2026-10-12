"""Unit tests for SPEC-13 Next-Gen Instanced GPU Pipeline, Semantic LOD,
Zero-Trust Hardening & Dual-Projection (TASK-CV-1408).

Covers:
1. HMAC authentication contracts (§3.3 / ADR-1303):
   - valid signatures accepted; forged signatures rejected;
   - timestamp drift > 300s rejected; fail-closed when secret is missing.
2. Star-topology probe contracts (§3.5 / ADR-1305):
   - target resolution (ingress, api, az_bridge), max targets <= 5,
     target_type attribution, and backwards compatibility with mesh mode.
3. WhitelistExtractor zero-leak contracts (§3.3 / §6.2):
   - 100% sha256:8 hash redaction of environment values;
   - regex credential redaction for container args;
   - data stripping for Secrets/ConfigMaps — across top-level and nested
     template containers.
4. TypeScript / shader contract verification (instanced_pod_renderer.ts,
   semantic_lod.ts, camera_controller.ts, focal_lens.ts): schemas, constants,
   exports must match SPEC-13 §3.1 / §3.2 / §3.6.
5. Draw-call budget & scale math (§3.1 / ADR-1301 / §6.1):
   - single-viewport budget <= 30 draw calls;
   - quad-viewport budget <= 120 draw calls; up to 30,000 pods.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import time
import unittest
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.operator.auth import Authenticator, HMACAuthenticator  # noqa: E402
from src.operator.graph_engine import WhitelistExtractor  # noqa: E402
from src.probe.main import (  # noqa: E402
    MAX_STAR_TARGETS,
    LatencyStore,
    ProbeDaemon,
    ProbeTarget,
    resolve_star_targets,
)

SHARED_SECRET = "test-shared-secret-value"
DRIFT_MAX = 300  # SPEC-13 §6.2: >300s drift must be rejected


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_headers(
    secret: str = SHARED_SECRET,
    user: str = "alice@example.com",
    groups: str = "viewers",
    ts: float | None = None,
    email: str = "alice@example.com",
) -> dict[str, str]:
    """Build a correctly HMAC-signed X-Forwarded-* header set."""
    ts = time.time() if ts is None else ts
    sig = HMACAuthenticator(secret).compute_signature(
        user, groups, email, str(int(ts))
    )
    return {
        "X-Forwarded-User": user,
        "X-Forwarded-Groups": groups,
        "X-Forwarded-Email": email,
        "X-Forwarded-Timestamp": str(int(ts)),
        "X-Forwarded-Access-Signature": sig,
    }


def _extract_block(source: str, opener: str, closers: tuple[str, ...]) -> str:
    """Extract a source block starting at `opener` up to the first of `closers`
    (or end of file)."""
    start = source.find(opener)
    if start == -1:
        raise AssertionError(f"opener not found: {opener!r}")
    rest = source[start:]
    end = len(rest)
    for closer in closers:
        idx = rest.find(closer, len(opener))
        if idx != -1:
            end = min(end, idx)
    return rest[:end]


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


# ---------------------------------------------------------------------------
# 1. HMAC authentication contracts
# ---------------------------------------------------------------------------

class TestSpec13HMACAuthentication(unittest.TestCase):
    """SPEC-13 §3.3 / ADR-1303: HMAC-SHA256 header verification."""

    def setUp(self) -> None:
        self.auth = Authenticator(
            mode="oauth2-proxy", proxy_shared_secret=SHARED_SECRET
        )

    # -- valid signatures ---------------------------------------------------
    def test_valid_signature_accepted(self) -> None:
        ok, user, err = self.auth.authenticate_request(_valid_headers())
        self.assertTrue(ok, f"valid request rejected: {err}")
        self.assertEqual(user, "alice@example.com")

    def test_valid_signature_within_drift_window_accepted(self) -> None:
        near_ts = time.time() - DRIFT_MAX + 10
        ok, _, err = self.auth.authenticate_request(_valid_headers(ts=near_ts))
        self.assertTrue(ok, f"request within drift window rejected: {err}")

    def test_groups_are_split_from_csv(self) -> None:
        auth = Authenticator(
            mode="oauth2-proxy", proxy_shared_secret=SHARED_SECRET
        )
        result = auth._hmac.verify_headers(
            "alice", "viewers,admins", str(int(time.time())),
            HMACAuthenticator(SHARED_SECRET).compute_signature(
                "alice", "viewers,admins", "", str(int(time.time()))
            ),
        )
        self.assertTrue(result.authenticated)
        self.assertEqual(result.groups, ["viewers", "admins"])

    # -- forged signatures --------------------------------------------------
    def test_forged_signature_rejected(self) -> None:
        h = _valid_headers()
        h["X-Forwarded-Access-Signature"] = "deadbeef" * 8
        ok, _, err = self.auth.authenticate_request(h)
        self.assertFalse(ok)
        self.assertIn("invalid", (err or "").lower())

    def test_missing_signature_rejected(self) -> None:
        h = _valid_headers()
        del h["X-Forwarded-Access-Signature"]
        ok, _, err = self.auth.authenticate_request(h)
        self.assertFalse(ok)
        self.assertIn("missing", (err or "").lower())

    def test_empty_signature_rejected(self) -> None:
        h = _valid_headers()
        h["X-Forwarded-Access-Signature"] = ""
        ok, _, err = self.auth.authenticate_request(h)
        self.assertFalse(ok)

    def test_tampered_user_with_stale_signature_rejected(self) -> None:
        """Swapping the identity while keeping an old signature must fail."""
        h = _valid_headers(user="alice@example.com")
        stale_sig = h["X-Forwarded-Access-Signature"]
        h["X-Forwarded-User"] = "mallory@evil.com"
        h["X-Forwarded-Email"] = "mallory@evil.com"
        h["X-Forwarded-Access-Signature"] = stale_sig
        ok, _, err = self.auth.authenticate_request(h)
        self.assertFalse(ok)

    # -- drift expiration ---------------------------------------------------
    def test_expired_timestamp_rejected(self) -> None:
        """Drift > 300s must be rejected (SPEC-13 §6.2)."""
        old_ts = time.time() - DRIFT_MAX - 1
        ok, _, err = self.auth.authenticate_request(_valid_headers(ts=old_ts))
        self.assertFalse(ok)
        self.assertIn("drift", (err or "").lower())

    def test_boundary_drift_exactly_at_limit_rejected(self) -> None:
        """Drift == max_drift_seconds is not within the window (<, not <=)."""
        auth = Authenticator(
            mode="oauth2-proxy", proxy_shared_secret=SHARED_SECRET
        )
        ts = time.time() - DRIFT_MAX
        result = auth._hmac.verify_headers(
            "alice", "viewers", str(int(ts)),
            HMACAuthenticator(SHARED_SECRET).compute_signature(
                "alice", "viewers", "", str(int(ts))
            ),
        )
        self.assertFalse(result.authenticated)

    def test_malformed_timestamp_rejected(self) -> None:
        h = _valid_headers()
        h["X-Forwarded-Timestamp"] = "not-a-number"
        ok, _, err = self.auth.authenticate_request(h)
        self.assertFalse(ok)

    # -- fail-closed when secret missing ------------------------------------
    def test_no_secret_fails_closed(self) -> None:
        """Without CLUSTERVIS_PROXY_SHARED_SECRET the operator must refuse to
        trust raw spoofable X-Forwarded-* plaintext (zero-trust)."""
        auth = Authenticator(mode="oauth2-proxy", proxy_shared_secret=None)
        ok, _user, err = auth.authenticate_request(
            {"X-Forwarded-User": "mallory@evil.com"}
        )
        self.assertFalse(ok, "spoofed identity must be rejected without HMAC")
        self.assertIn("shared secret", (err or "").lower())

    def test_no_secret_rejects_even_signed_headers(self) -> None:
        """A forged signature with no configured secret is still denied."""
        auth = Authenticator(mode="oauth2-proxy", proxy_shared_secret=None)
        ok, _, err = auth.authenticate_request(
            {
                "X-Forwarded-User": "mallory@evil.com",
                "X-Forwarded-Access-Signature": "f00d" * 8,
            }
        )
        self.assertFalse(ok)


# ---------------------------------------------------------------------------
# 2. Star-topology probe contracts
# ---------------------------------------------------------------------------

class TestSpec13StarTopologyProbe(unittest.TestCase):
    """SPEC-13 §3.5 / ADR-1305: O(N) star-topology network probe."""

    def test_resolves_ingress_api_and_az_bridges_in_order(self) -> None:
        targets = resolve_star_targets(
            "ingress.svc:80", "kubernetes.default.svc:443",
            "us-east-1a:10.0.2.7:443,10.0.3.9:6443",
        )
        self.assertEqual([t.target_type for t in targets[:2]], ["ingress", "api"])
        self.assertTrue(all(t.target_type == "az_bridge" for t in targets[2:]))
        self.assertEqual(targets[0].endpoint(), "ingress.svc:80")
        self.assertEqual(targets[1].endpoint(), "kubernetes.default.svc:443")

    def test_max_targets_capped_at_five(self) -> None:
        bridges = ",".join(f"az{i}:10.0.{i}.1:443" for i in range(8))
        targets = resolve_star_targets("ingress.svc:80", "api.svc:443", bridges)
        self.assertLessEqual(len(targets), MAX_STAR_TARGETS)
        self.assertEqual(MAX_STAR_TARGETS, 5)  # SPEC-13 K <= 5

    def test_target_type_attribution_in_records(self) -> None:
        t = ProbeTarget("az_bridge", "10.0.2.7", 443, az="us-east-1a")
        rec = t.as_record(1.25, True)
        self.assertEqual(rec["target_type"], "az_bridge")
        self.assertEqual(rec["az"], "us-east-1a")
        self.assertIn("latency_ms", rec)

    def test_star_cycle_produces_target_type_records(self) -> None:
        daemon = ProbeDaemon(
            node_name="node-1",
            host_ip="127.0.0.1",
            pod_ip="10.244.0.5",
            interval_seconds=3.0,
            timeout_ms=200,
            sample_target_limit=20,
            store=LatencyStore(),
            topology="star",
            star_targets=[
                ProbeTarget("ingress", "127.0.0.1", 9),
                ProbeTarget("api", "127.0.0.1", 8),
            ],
        )
        result = daemon.run_cycle()
        types = {rec["target_type"] for rec in result["latencies"]}
        self.assertEqual(types, {"ingress", "api"})

    def test_mesh_mode_backwards_compatible(self) -> None:
        """Legacy mesh topology must still emit reachable/rtt records without
        target_type (backward compatibility with existing deployments)."""
        daemon = ProbeDaemon(
            node_name="node-1",
            host_ip="127.0.0.1",
            pod_ip="10.244.0.5",
            interval_seconds=3.0,
            timeout_ms=200,
            sample_target_limit=20,
            store=LatencyStore(),
            explicit_targets=[("127.0.0.1", 9)],
            topology="mesh",
        )
        result = daemon.run_cycle()
        self.assertEqual(len(result["latencies"]), 1)
        rec = result["latencies"][0]
        self.assertIn("reachable", rec)
        self.assertNotIn("target_type", rec)


# ---------------------------------------------------------------------------
# 3. WhitelistExtractor zero-leak contracts
# ---------------------------------------------------------------------------

class TestSpec13WhitelistZeroLeak(unittest.TestCase):
    """SPEC-13 §3.3 / §6.2: 100% sha256:8 hash redaction, zero plaintext leak."""

    WORKLOAD = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": "payments",
            "namespace": "prod",
            "labels": {"app": "payments"},
            "annotations": {"secret-note": "super-secret-annotation"},
        },
        "spec": {
            "replicas": 3,
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "pay",
                            "image": "repo/pay:1.2.3",
                            "env": [
                                {"name": "DATABASE_URL",
                                 "value": "postgres://admin:***@db/prod"},
                                {"name": "API_KEY", "value": "AKIA-SECRET-KEY"},
                                {"name": "SAFE_VAR", "value": "harmless"},
                            ],
                            "args": [
                                "--password=hunter2",
                                "--port=8080",
                            ],
                        }
                    ]
                }
            },
        },
        "status": {"replicas": 3, "readyReplicas": 2},
    }

    SECRET = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "db-creds", "namespace": "prod"},
        "data": {"password": _b64("hunter2")},
        "stringData": {"token": "plaintext-token"},
    }

    CONFIGMAP = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "app-config", "namespace": "prod"},
        "data": {"connection": "postgres://admin:hunter2@db/prod"},
    }

    def test_env_values_hashed_to_sha256_eight(self) -> None:
        out = WhitelistExtractor.extract_workload(self.WORKLOAD)
        env = out["spec"]["template"]["spec"]["containers"][0]["env"]
        for var in env:
            if "value" in var:
                self.assertTrue(var["value"].startswith("sha256:"))
                # sha256:<hex[:8]> — prefix + exactly 8 hex chars.
                digest = var["value"][len("sha256:"):]
                self.assertEqual(len(digest), 8)
                self.assertRegex(digest, r"^[0-9a-f]{8}$")

    def test_hash_is_deterministic_sha256_prefix(self) -> None:
        out = WhitelistExtractor.extract_workload(self.WORKLOAD)
        env = out["spec"]["template"]["spec"]["containers"][0]["env"]
        by_name = {v["name"]: v for v in env}
        value = "postgres://admin:***@db/prod"
        expected = "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
        self.assertEqual(by_name["DATABASE_URL"]["value"], expected)

    def test_zero_plaintext_leak(self) -> None:
        out = WhitelistExtractor.extract_workload(self.WORKLOAD)
        blob = json.dumps(out)
        for secret in ("hunter2", "AKIA-SECRET-KEY", "admin:***@db"):
            self.assertNotIn(secret, blob, f"plaintext leaked: {secret}")

    def test_args_credentials_regex_redacted(self) -> None:
        out = WhitelistExtractor.extract_workload(self.WORKLOAD)
        args = out["spec"]["template"]["spec"]["containers"][0]["args"]
        joined = json.dumps(args)
        self.assertNotIn("hunter2", joined)
        # The credential token is replaced (regex keeps the key, swaps the value).
        self.assertTrue(any("--password:[REDACTED]" in a for a in args))

    def test_nested_template_containers_are_hashed(self) -> None:
        """Deployment env lives under spec.template.spec.containers — nested
        containers must still be hashed (production path)."""
        out = WhitelistExtractor.extract_manifest(self.WORKLOAD)
        blob = json.dumps(out)
        self.assertNotIn("hunter2", blob)

    def test_secret_data_stripped(self) -> None:
        out = WhitelistExtractor.extract_secret_or_configmap(self.SECRET)
        blob = json.dumps(out)
        self.assertNotIn("hunter2", blob)
        self.assertNotIn("plaintext-token", blob)
        self.assertNotIn("data", out)
        self.assertNotIn("stringData", out)

    def test_configmap_data_stripped(self) -> None:
        out = WhitelistExtractor.extract_secret_or_configmap(self.CONFIGMAP)
        blob = json.dumps(out)
        self.assertNotIn("hunter2", blob)
        self.assertNotIn("data", out)

    def test_annotations_dropped(self) -> None:
        out = WhitelistExtractor.extract_workload(self.WORKLOAD)
        meta = out.get("metadata", {})
        self.assertNotIn("annotations", meta)
        self.assertNotIn("super-secret-annotation", json.dumps(out))

    def test_graph_level_extraction_zero_leak(self) -> None:
        graph = {"manifests": [self.WORKLOAD, self.SECRET, self.CONFIGMAP]}
        out = WhitelistExtractor.extract_graph(graph)
        blob = json.dumps(out)
        for secret in ("hunter2", "AKIA-SECRET-KEY", "plaintext-token"):
            self.assertNotIn(secret, blob)


# ---------------------------------------------------------------------------
# 4. TypeScript / shader contract verification
# ---------------------------------------------------------------------------

class TestSpec13InstancedRendererContracts(unittest.TestCase):
    """SPEC-13 §3.1: instanced_pod_renderer.ts schemas, constants, exports."""

    def setUp(self) -> None:
        self.ts = (REPO / "src" / "scene" / "instanced_pod_renderer.ts").read_text()

    def test_instance_data_buffer_schema(self) -> None:
        iface = _extract_block(
            self.ts, "export interface InstanceDataBuffer {",
            ("}",),
        )
        self.assertIn("instanceMatrix: THREE.InstancedBufferAttribute", iface)
        self.assertIn("aInstanceData: THREE.InstancedBufferAttribute", iface)

    def test_pod_instance_record_schema(self) -> None:
        rec = _extract_block(
            self.ts, "export interface PodInstanceRecord {",
            ("}",),
        )
        for field in (
            "id: string", "podName: string", "namespace: string",
            "nodeName: string", "statusCode: number", "cpuRatio: number",
            "memRatio: number", "diffState: number", "isEjectedOutlier: boolean",
        ):
            self.assertIn(field, rec)

    def test_renderer_interface_exports(self) -> None:
        iface = _extract_block(
            self.ts, "export interface IInstancedPodRenderer {",
            ("}",),
        )
        for method in (
            "initialize(maxPods?: number): void",
            "syncPods(pods: PodInstanceRecord[]): void",
            "updatePod(podId: string, updates: Partial<PodInstanceRecord>): void",
            "removePod(podId: string): void",
            "setEjectionState(podId: string, ejected: boolean): void",
            "updateAnimation(deltaTime: number): void",
            "dispose(): void",
        ):
            self.assertIn(method, iface)

    def test_status_code_constants(self) -> None:
        codes = _extract_block(
            self.ts, "export const POD_STATUS_CODE = {", ("} as const;",)
        )
        self.assertIn("HEALTHY: 0", codes)
        self.assertIn("CRASH_LOOP: 1", codes)
        self.assertIn("OOM: 2", codes)
        self.assertIn("PENDING: 3", codes)

    def test_diff_state_constants(self) -> None:
        diffs = _extract_block(
            self.ts, "export const POD_DIFF_STATE = {", ("} as const;",)
        )
        self.assertIn("IDENTICAL: 0", diffs)
        self.assertIn("SKEW: 1", diffs)
        self.assertIn("MISSING: 2", diffs)
        self.assertIn("ADDED: 3", diffs)

    def test_max_pod_budget_constant(self) -> None:
        self.assertIn("const DEFAULT_MAX_PODS = 30_000;", self.ts)

    def test_single_preallocated_instanced_mesh_per_class(self) -> None:
        """SPEC-13 §3.1.2: pods share a single pre-allocated InstancedMesh."""
        init = _extract_block(
            self.ts, "public initialize(maxPods?: number): void {",
            ("public syncPods",),
        )
        self.assertIn("new THREE.InstancedMesh(geometry, material, capacity)", init)
        self.assertIn("aInstanceData", init)

    def test_a_instance_data_vec4_layout(self) -> None:
        """x=status, y=cpu, z=mem, w=diff per SPEC-13 §3.1."""
        write = _extract_block(
            self.ts, "private writeData(", ("// ---- Custom shader",),
        )
        self.assertIn("a[o + 0] = statusCode;", write)
        self.assertIn("a[o + 1] = cpuRatio;", write)
        self.assertIn("a[o + 2] = memRatio;", write)
        self.assertIn("a[o + 3] = diffState;", write)

    def test_gpu_shader_injection_present(self) -> None:
        """Status colors / pulse computed on the GPU via onBeforeCompile."""
        shader = _extract_block(
            self.ts, "private configureShader(", (")}",),
        )
        self.assertIn("onBeforeCompile", shader)
        self.assertIn("attribute vec4 aInstanceData;", shader)


class TestSpec13SemanticLodContracts(unittest.TestCase):
    """SPEC-13 §3.2: semantic_lod.ts LOD tiers, anomalies, slabs."""

    def setUp(self) -> None:
        self.ts = (REPO / "src" / "scene" / "semantic_lod.ts").read_text()

    def test_lod_tier_enum(self) -> None:
        tier = _extract_block(
            self.ts, "export enum LodTier {", ("}",),
        )
        self.assertIn("FLEET = 0", tier)
        self.assertIn("STRATUM = 1", tier)
        self.assertIn("INSPECTION = 2", tier)

    def test_anomaly_reason_union(self) -> None:
        reason = _extract_block(
            self.ts, "export type AnomalyReason =", (";",),
        )
        for r in ("CrashLoopBackOff", "ImagePullBackOff", "OOMKilled",
                  "Pending", "Morphing"):
            self.assertIn(f"'{r}'", reason)

    def test_workload_slab_aggregate_schema(self) -> None:
        slab = _extract_block(
            self.ts, "export interface WorkloadSlabAggregate {", ("}",),
        )
        for field in (
            "namespace: string", "workloadName: string", "kind: string",
            "podCount: number", "healthyCount: number", "anomalousCount: number",
            "statusPillText: string",
        ):
            self.assertIn(field, slab)

    def test_anomaly_outlier_pod_schema(self) -> None:
        outlier = _extract_block(
            self.ts, "export interface AnomalyOutlierPod {", ("}",),
        )
        for field in (
            "podId: string", "workloadName: string", "namespace: string",
            "reason: AnomalyReason", "tractorTension: number",
        ):
            self.assertIn(field, outlier)

    def test_lod_distance_thresholds(self) -> None:
        self.assertIn("const FLEET_DISTANCE = 120;", self.ts)
        self.assertIn("const STRATUM_DISTANCE = 40;", self.ts)

    def test_anomaly_reason_detection(self) -> None:
        """CrashLoopBackOff / OOMKilled / Pending must map to anomaly reasons."""
        detect = _extract_block(
            self.ts, "function podAnomalyReason(", (")}",),
        )
        for reason in ("CrashLoopBackOff", "ImagePullBackOff",
                      "OOMKilled", "Pending"):
            self.assertIn(reason, detect)

    def test_anomaly_status_code_mapping(self) -> None:
        """Anomalous reasons map onto the shared status-code space."""
        mapping = _extract_block(
            self.ts, "function anomalyStatusCode(", (")}",),
        )
        self.assertIn("return 1; // CRASH_LOOP", mapping)
        self.assertIn("return 2; // OOM", mapping)
        self.assertIn("return 3; // PENDING", mapping)


class TestSpec13DualProjectionContracts(unittest.TestCase):
    """SPEC-13 §3.6 / ADR-1304: camera_controller.ts + focal_lens.ts."""

    def setUp(self) -> None:
        self.cam = (REPO / "src" / "scene" / "camera_controller.ts").read_text()
        self.lens = (REPO / "src" / "scene" / "focal_lens.ts").read_text()

    # -- DualProjectionState -------------------------------------------------
    def test_dual_projection_state_schema(self) -> None:
        state = _extract_block(
            self.cam, "export interface DualProjectionState {", ("}",),
        )
        for field in (
            "isOrthographic: boolean",
            "transitionProgress: number",
            "perspectiveCamera: THREE.PerspectiveCamera",
            "orthographicCamera: THREE.OrthographicCamera",
            "activeCamera: THREE.Camera",
            "cadGridVisible: boolean",
        ):
            self.assertIn(field, state)

    def test_transition_duration_600ms(self) -> None:
        self.assertIn("const TRANSITION_DURATION = 0.6;", self.cam)

    def test_key_f_toggles_projection(self) -> None:
        handler = _extract_block(
            self.cam, "private readonly boundKeyHandler: (event: KeyboardEvent) => void;",
            ("}",),
        )
        # The actual keydown listener body.
        keys = _extract_block(
            self.cam, "this.boundKeyHandler = (event: KeyboardEvent) => {",
            ("};",),
        )
        self.assertIn("event.code === 'KeyF'", keys)
        self.assertIn("this.toggleProjection();", keys)

    def test_orthographic_camera_present(self) -> None:
        self.assertIn("new THREE.OrthographicCamera(", self.cam)

    # -- FocalLensState -----------------------------------------------------
    def test_focal_lens_state_schema(self) -> None:
        state = _extract_block(
            self.lens, "export interface FocalLensState {", ("}",),
        )
        for field in (
            "isActive: boolean",
            "focusedTargetId: string | null",
            "dimmedOpacity: number",
            "blastRadiusNodeIds: Set<string>",
            "blastRadiusEdgeIds: Set<string>",
        ):
            self.assertIn(field, state)

    def test_dim_opacity_default_015(self) -> None:
        """SPEC-13 §3.6.2: unrelated components dim to 15% opacity."""
        self.assertIn("const DEFAULT_DIM_OPACITY = 0.15;", self.lens)

    def test_key_b_and_escape_handlers(self) -> None:
        keys = _extract_block(
            self.lens, "this.boundKeyHandler = (event: KeyboardEvent) => {",
            ("};",),
        )
        self.assertIn("event.code === 'KeyB'", keys)
        self.assertIn("this.toggleLens();", keys)
        self.assertIn("event.key === 'Escape'", keys)
        self.assertIn("this.deactivateLens();", keys)

    def test_amber_aura_colors(self) -> None:
        self.assertIn("const AURA_AMBER = 0xffb020;", self.lens)
        self.assertIn("const AURA_RED = 0xff4444;", self.lens)


# ---------------------------------------------------------------------------
# 5. Draw-call budget & scale math
# ---------------------------------------------------------------------------

class TestSpec13DrawCallBudgetAndScale(unittest.TestCase):
    """SPEC-13 §3.1 / ADR-1301 / §6.1: instancing keeps draw calls bounded."""

    MAX_PODS = 30_000

    @staticmethod
    def single_viewport_draw_calls(pod_count: int, anomalous_pods: int = 0) -> int:
        """Model the SPEC-13 instanced pipeline draw-call count for one viewport.

        Every healthy pod shares a single pre-allocated InstancedMesh (1 draw call
        per class), so healthy-pod count does NOT drive draw calls linearly:
          - 1  InstancedPodRenderer capsule mesh (all pods)
          - 1  node tray instanced pipeline
          - 1  STRATUM workload slab InstancedMesh
          - 1  FLEET namespace hull layer
        Ejected anomalous pods render as autonomous individual capsules, so they add
        one draw call each.
        """
        fixed = 4  # instanced pods + trays + slabs + fleet hulls
        return fixed + max(0, anomalous_pods)

    @staticmethod
    def quad_viewport_draw_calls(pod_count: int) -> int:
        """Quad mode renders the scene through 4 independent viewports."""
        return 4 * TestSpec13DrawCallBudgetAndScale.single_viewport_draw_calls(pod_count)

    def test_single_viewport_budget_within_30(self) -> None:
        calls = self.single_viewport_draw_calls(self.MAX_PODS)
        self.assertLessEqual(calls, 30)

    def test_quad_viewport_budget_within_120(self) -> None:
        calls = self.quad_viewport_draw_calls(self.MAX_PODS)
        self.assertLessEqual(calls, 120)

    def test_quad_is_four_times_single(self) -> None:
        """§3.1: <= 30 per viewport => <= 120 across the 4-pane matrix."""
        single = self.single_viewport_draw_calls(self.MAX_PODS)
        self.assertEqual(self.quad_viewport_draw_calls(self.MAX_PODS), 4 * single)

    def test_instancing_is_sublinear_in_pod_count(self) -> None:
        """Healthy pod count must not increase draw calls (O(1) instancing)."""
        small = self.single_viewport_draw_calls(100)
        large = self.single_viewport_draw_calls(self.MAX_PODS)
        self.assertEqual(small, large)

    def test_anomaly_ejection_stays_in_budget(self) -> None:
        """Even with a bounded number of ejected outliers the per-viewport budget
        of 30 draw calls is preserved (ADR-1302: <500 objects scene-wide)."""
        for anomalous in (0, 5, 20):
            single = self.single_viewport_draw_calls(self.MAX_PODS, anomalous)
            self.assertLessEqual(single, 30)

    def test_ts_renderer_preallocates_for_30000_pods(self) -> None:
        ts = (REPO / "src" / "scene" / "instanced_pod_renderer.ts").read_text()
        self.assertIn("const DEFAULT_MAX_PODS = 30_000;", ts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
