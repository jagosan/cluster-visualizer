"""Zero-Trust Security Audit tests for TASK-CV-1407 (SPEC-13 §3.3 / §6.2 & ADR-1303).

Audits:
  1. HMAC signature enforcement in oauth2-proxy mode (missing / forged / expired).
  2. Whitelist-only extraction: 100% sha256:8 hash redaction, zero plaintext leak.
  3. SecretScrubber gaps on workload templates (env leakage) — the production path.
  4. CORS wildcard elimination under auth modes.
"""
import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.operator.auth import Authenticator, HMACAuthenticator
from src.operator.graph_engine import WhitelistExtractor, SecretScrubber


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
SHARED_SECRET = "test-shared-secret-value"
DRIFT_MAX = 300  # SPEC-13 §6.2 / task: >300s drift must be rejected


def _valid_headers(secret=SHARED_SECRET, user="alice@example.com",
                  groups="viewers", ts=None, email="alice@example.com"):
    ts = ts if ts is not None else time.time()
    sig = HMACAuthenticator(secret).compute_signature(
        user, groups, email, str(int(ts)))
    return {
        "X-Forwarded-User": user,
        "X-Forwarded-Groups": groups,
        "X-Forwarded-Email": email,
        "X-Forwarded-Timestamp": str(int(ts)),
        "X-Forwarded-Access-Signature": sig,
    }


class TestHMACEnforcement(unittest.TestCase):
    """Objective 3: HMAC signature enforcement in oauth2-proxy mode."""

    def setUp(self):
        self.auth = Authenticator(
            mode="oauth2-proxy",
            proxy_shared_secret=SHARED_SECRET,
        )

    def test_valid_signature_accepted(self):
        ok, user, err = self.auth.authenticate_request(_valid_headers())
        self.assertTrue(ok, f"valid request rejected: {err}")
        self.assertEqual(user, "alice@example.com")

    def test_missing_signature_rejected(self):
        h = _valid_headers()
        del h["X-Forwarded-Access-Signature"]
        ok, _, err = self.auth.authenticate_request(h)
        self.assertFalse(ok)
        self.assertIn("missing", (err or "").lower())

    def test_empty_signature_rejected(self):
        h = _valid_headers()
        h["X-Forwarded-Access-Signature"] = ""
        ok, _, err = self.auth.authenticate_request(h)
        self.assertFalse(ok)

    def test_forged_signature_rejected(self):
        h = _valid_headers()
        h["X-Forwarded-Access-Signature"] = "deadbeef" * 8
        ok, _, err = self.auth.authenticate_request(h)
        self.assertFalse(ok)
        self.assertIn("invalid", (err or "").lower())

    def test_forged_user_with_valid_signature_rejected(self):
        """Tampering with the user while keeping an old signature must fail."""
        # Compute a valid signature over alice, then swap in mallory's identity
        h = _valid_headers(user="alice@example.com")
        sig = h["X-Forwarded-Access-Signature"]
        h["X-Forwarded-User"] = "mallory@evil.com"
        h["X-Forwarded-Email"] = "mallory@evil.com"
        h["X-Forwarded-Access-Signature"] = sig  # stale signature
        ok, _, err = self.auth.authenticate_request(h)
        self.assertFalse(ok)

    def test_oauth2_proxy_without_secret_fails_closed(self):
        """CRITICAL fix (SPEC-13 §3.3.2): in oauth2-proxy mode with NO shared
        secret configured, forged X-Forwarded-* headers must be REJECTED — the
        operator fails closed instead of trusting raw spoofable plaintext."""
        auth = Authenticator(mode="oauth2-proxy", proxy_shared_secret=None)
        h = {
            "X-Forwarded-User": "mallory@evil.com",
            # no signature at all
        }
        ok, _user, err = auth.authenticate_request(h)
        self.assertFalse(ok, "spoofed identity must be rejected without HMAC")
        self.assertIn("shared secret", (err or "").lower())

    def test_expired_timestamp_rejected(self):
        """Drift > 300s must be rejected (SPEC-13 §6.2)."""
        old_ts = time.time() - DRIFT_MAX - 1
        h = _valid_headers(ts=old_ts)
        ok, _, err = self.auth.authenticate_request(h)
        self.assertFalse(ok)
        self.assertIn("drift", (err or "").lower())

    def test_drift_within_limit_accepted(self):
        near_ts = time.time() - DRIFT_MAX + 10
        h = _valid_headers(ts=near_ts)
        ok, _, err = self.auth.authenticate_request(h)
        self.assertTrue(ok, f"request within drift window rejected: {err}")

    def test_malformed_timestamp_rejected(self):
        h = _valid_headers()
        h["X-Forwarded-Timestamp"] = "not-a-number"
        ok, _, err = self.auth.authenticate_request(h)
        self.assertFalse(ok)

    def test_oauth2_proxy_without_shared_secret_rejects_forged_identity(self):
        """CRITICAL fix: without a shared secret, unsigned headers are never
        trusted — the operator refuses to authenticate in oauth2-proxy mode."""
        auth = Authenticator(mode="oauth2-proxy", proxy_shared_secret=None)
        h = {
            "X-Forwarded-User": "mallory@evil.com",
            # NO signature at all
        }
        ok, _user, err = auth.authenticate_request(h)
        self.assertFalse(ok, "forged identity must be rejected under zero-trust")
        self.assertIn("shared secret", (err or "").lower())


class TestWhitelistExtraction(unittest.TestCase):
    """Objective 4: 100% sha256:8 hash redaction, zero plaintext leak."""

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
                                 "value": "postgres://admin:hunter2@db/prod"},
                                {"name": "API_KEY", "value": "AKIAXXXXXXXXXXXXXXXX"},
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

    def test_env_values_hashed_to_sha256(self):
        out = WhitelistExtractor.extract_workload(self.WORKLOAD)
        env = out["spec"]["template"]["spec"]["containers"][0]["env"]
        for var in env:
            if "value" in var:
                self.assertTrue(
                    var["value"].startswith("sha256:"),
                    f"env value not hashed: {var['value']!r}",
                )
                self.assertEqual(len(var["value"]), len("sha256:") + 8,
                               "hash must be sha256:<hex[:8]>")

    def test_no_plaintext_secret_in_output(self):
        raw = json.dumps(self.WORKLOAD)
        out = WhitelistExtractor.extract_workload(self.WORKLOAD)
        blob = json.dumps(out)
        for secret in ("hunter2", "AKIAXXXXXXXXXXXXXXXX"):
            self.assertNotIn(secret, blob,
                            f"plaintext secret leaked: {secret}")

    def test_args_credentials_redacted(self):
        out = WhitelistExtractor.extract_workload(self.WORKLOAD)
        args = out["spec"]["template"]["spec"]["containers"][0]["args"]
        self.assertNotIn("hunter2", json.dumps(args))

    def test_sensitive_env_name_value_still_hashed(self):
        """Even env whose NAME is benign must have its VALUE hashed."""
        out = WhitelistExtractor.extract_workload(self.WORKLOAD)
        env = out["spec"]["template"]["spec"]["containers"][0]["env"]
        by_name = {v["name"]: v for v in env}
        self.assertNotIn("hunter2", json.dumps(by_name))

    def test_secret_and_configmap_data_stripped(self):
        secret = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "db-creds", "namespace": "prod"},
            "data": {"password": base64_b("hunter2")},
            "stringData": {"token": "plaintext-token"},
        }
        out = WhitelistExtractor.extract_secret_or_configmap(secret)
        blob = json.dumps(out)
        self.assertNotIn("hunter2", blob)
        self.assertNotIn("plaintext-token", blob)

    def test_annotations_not_in_whitelist_output(self):
        out = WhitelistExtractor.extract_workload(self.WORKLOAD)
        meta = out.get("metadata", {})
        self.assertNotIn("annotations", meta,
                        "annotations are outside the whitelist and must be dropped")
        self.assertNotIn("super-secret-annotation", json.dumps(out))


def base64_b(s):
    import base64
    return base64.b64encode(s.encode()).decode()


class TestSecretScrubberGaps(unittest.TestCase):
    """The PRODUCTION path (server.py) uses SecretScrubber, not WhitelistExtractor."""

    DEPLOYMENT = {
        "kind": "Deployment",
        "metadata": {"name": "pay", "namespace": "prod"},
        "spec": {
            "replicas": 3,
            "template": {
                "spec": {
                    "containers": [{
                        "name": "pay",
                        "image": "repo/pay:1.2.3",
                        "env": [
                            {"name": "DATABASE_URL",
                             "value": "postgres://admin:hunter2@db/prod"},
                        ],
                    }]
                }
            },
        },
    }

    def test_deployment_template_env_scrubbed(self):
        """A Deployment's env lives under spec.template.spec.containers.
        SecretScrubber._scrub_pod_spec_inner only handles top-level 'containers',
        so nested template env may leak."""
        scrubbed = SecretScrubber.scrub_pod_spec(self.DEPLOYMENT)
        blob = json.dumps(scrubbed)
        self.assertNotIn("hunter2", blob,
                        "SecretScrubber leaked deployment env value")

    def test_manifest_list_deployment_leaks_env(self):
        """CRITICAL: full Deployment manifests in the graph 'manifests' list are
        passed to _scrub_manifest, whose non-Pod/ConfigMap branch keeps spec
        verbatim — plaintext env values leak."""
        graph = {"manifests": [self.DEPLOYMENT]}
        scrubbed = SecretScrubber.scrub_graph(graph)
        blob = json.dumps(scrubbed)
        self.assertNotIn("hunter2", blob,
                        "SecretScrubber leaked deployment env via manifests list")

    def test_whitelist_extractor_does_not_leak_deployment_env(self):
        """The SPEC-mandated WhitelistExtractor must hash the same Deployment env."""
        out = WhitelistExtractor.extract_manifest(self.DEPLOYMENT)
        blob = json.dumps(out)
        self.assertNotIn("hunter2", blob,
                        "WhitelistExtractor leaked deployment env value")
        env = out["spec"]["template"]["spec"]["containers"][0]["env"]
        self.assertTrue(env[0]["value"].startswith("sha256:"),
                       "whitelist env must be sha256:8 hashed")


class TestCORSWildcardElimination(unittest.TestCase):
    """Objective 2: wildcard '*' must never be emitted when auth is enabled."""

    def _cors_headers(self, auth_mode, origin=None):
        from src.operator.server import ClusterVisualizerHandler
        # Plain stub object (no BaseHTTPRequestHandler plumbing needed) exposing
        # exactly what _set_cors_headers touches.
        class Stub:
            pass
        stub = Stub()
        stub.headers = {}
        if origin:
            stub.headers["Origin"] = origin
        stub.captured = []
        stub.send_header = lambda k, v: stub.captured.append((k, v))
        stub.auth_mode = auth_mode
        stub.cors_allowed_origins = ["*"]
        # Invoke the unbound method against our stub.
        ClusterVisualizerHandler._set_cors_headers(stub)
        return dict(stub.captured)

    def test_wildcard_suppressed_in_token_mode(self):
        headers = self._cors_headers("token", origin="https://evil.example")
        aao = [v for k, v in headers.items() if k == "Access-Control-Allow-Origin"]
        self.assertNotIn("*", aao, "wildcard '*' must be suppressed under token auth")

    def test_wildcard_suppressed_in_oauth2_proxy_mode(self):
        headers = self._cors_headers("oauth2-proxy", origin="https://evil.example")
        aao = [v for k, v in headers.items() if k == "Access-Control-Allow-Origin"]
        self.assertNotIn("*", aao, "wildcard '*' must be suppressed under oauth2-proxy")

    def test_wildcard_allowed_only_in_none_mode(self):
        headers = self._cors_headers("none")
        aao = [v for k, v in headers.items() if k == "Access-Control-Allow-Origin"]
        self.assertIn("*", aao, "wildcard '*' acceptable only with auth disabled")

    def test_unlisted_origin_blocked_under_auth(self):
        from src.operator.server import ClusterVisualizerHandler
        ClusterVisualizerHandler.auth_mode = "token"
        ClusterVisualizerHandler.cors_allowed_origins = ["https://allowed.example"]
        class Stub:
            pass
        stub = Stub()
        stub.headers = {"Origin": "https://evil.example"}
        stub.captured = []
        stub.send_header = lambda k, v: stub.captured.append((k, v))
        stub.auth_mode = "token"
        stub.cors_allowed_origins = ["https://allowed.example"]
        ClusterVisualizerHandler._set_cors_headers(stub)
        aao = [v for k, v in stub.captured if k == "Access-Control-Allow-Origin"]
        self.assertEqual(aao, [], "unlisted origin must receive NO CORS header")


class TestASGIAuthBypass(unittest.TestCase):
    """Objective 3/2: the async ASGI forward path (SPEC-13 §3.4) must enforce
    the same HMAC auth + CORS restrictions as the sync handler."""

    def setUp(self):
        from src.operator.server import ClusterVisualizerHandler
        self._orig_auth = ClusterVisualizerHandler.authenticator
        # Wire a real authenticator so unauthenticated ASGI callers are denied.
        self.auth = Authenticator(
            mode="oauth2-proxy", proxy_shared_secret=SHARED_SECRET
        )
        ClusterVisualizerHandler.authenticator = self.auth

    def tearDown(self):
        from src.operator.server import ClusterVisualizerHandler
        ClusterVisualizerHandler.authenticator = self._orig_auth

    def _run_asgi(self, app, scope):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            responses = []
            async def receive():
                return {"type": "http.request", "body": b""}
            async def send(msg):
                responses.append(msg)
            loop.run_until_complete(app(scope, receive, send))
        finally:
            loop.close()
        return responses

    @staticmethod
    def _asgi_scope_with_headers(headers: dict) -> dict:
        """Encode a header mapping as an ASGI ``scope``."""
        return {
            "type": "http",
            "path": "/api/v1/topology/snapshot",
            "headers": [
                (k.lower().encode("utf-8"), v.encode("utf-8"))
                for k, v in headers.items()
            ],
        }

    def test_asgi_snapshot_without_auth_returns_401(self):
        """CRITICAL fix: an unauthenticated ASGI /snapshot caller must be
        denied (fail closed) — no HMAC verification, no bearer check ⇒ 401."""
        from src.operator.server import operator_asgi_app
        responses = self._run_asgi(operator_asgi_app, {
            "type": "http",
            "path": "/api/v1/topology/snapshot",
        })
        start = [r for r in responses if r["type"] == "http.response.start"]
        self.assertTrue(start, "no response emitted")
        self.assertEqual(
            start[0]["status"], 401,
            "ASGI snapshot must require auth (zero-trust)",
        )

    def test_asgi_snapshot_with_valid_auth_returns_200(self):
        """A properly HMAC-signed ASGI caller is served the snapshot."""
        from src.operator.server import operator_asgi_app
        scope = self._asgi_scope_with_headers(_valid_headers())
        responses = self._run_asgi(operator_asgi_app, scope)
        start = [r for r in responses if r["type"] == "http.response.start"]
        self.assertEqual(start[0]["status"], 200,
                       "signed ASGI caller must be served the snapshot")

    def test_asgi_gates_through_authenticate_request(self):
        """The ASGI app must wire every protected endpoint through the same
        ``authenticate_request`` gate as the sync handler."""
        import inspect
        from src.operator.server import operator_asgi_app
        src = inspect.getsource(operator_asgi_app)
        self.assertIn("authenticate_request", src,
                     "ASGI app must gate every endpoint through auth")
        # And an unauthenticated snapshot is actually denied end-to-end.
        responses = self._run_asgi(operator_asgi_app, {
            "type": "http",
            "path": "/api/v1/topology/snapshot",
        })
        start = [r for r in responses if r["type"] == "http.response.start"]
        self.assertEqual(start[0]["status"], 401)


if __name__ == "__main__":
    unittest.main()
