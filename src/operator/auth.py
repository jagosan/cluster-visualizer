"""
ClusterVis Operator Authentication Layer (TASK-CV-803 / SPEC-07 Section 5).

Pluggable browser authentication for the operator's topology APIs:

  Mode 1  "token"       — Kubernetes ServiceAccount bearer tokens validated
                          via authentication.k8s.io/v1 TokenReview, followed
                          by an authorization.k8s.io/v1 SubjectAccessReview.
  Mode 2  "oauth2-proxy" — Trust X-Forwarded-User / X-Forwarded-Email headers
                          injected by an OAuth2/OIDC ingress proxy
                          (oauth2-proxy, Cloudflare Access, Google IAP, Keycloak).
  Mode 3  "none"        — Local dev / headless sandbox: every request is
                          accepted as a synthetic anonymous user.

Zero third-party dependencies (urllib only).
"""

import base64
import json
import logging
import os
import ssl
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Optional as Opt

logger = logging.getLogger("operator.auth")

# TokenReview cache TTL (seconds) — avoids hammering the API server on SSE
# reconnects and per-request validation bursts.
DEFAULT_CACHE_TTL_SECONDS = 30.0

DEFAULT_AUDIENCE = "clustervis"
DEFAULT_K8S_CA_CERT = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
DEFAULT_K8S_TOKEN_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/token"

# The pseudo-identity used in "none" mode.
ANONYMOUS_USER = "system:anonymous"

VALID_AUTH_TYPES = ("token", "oauth2-proxy", "none")


@dataclass
class AuthResult:
    """Outcome of an authentication attempt."""

    authenticated: bool
    user: str = ""
    groups: list = field(default_factory=list)
    error: Opt[str] = None


class Authenticator:
    """
    Pluggable authenticator supporting three modes (SPEC-07 §5.1).

    Args:
        mode: "token" | "oauth2-proxy" | "none".
        audience: Audience to embed in the TokenReview spec (default "clustervis").
        api_server_url: Kubernetes API server base URL. In-cluster defaults
            are derived from KUBERNETES_SERVICE_HOST/PORT.
        ca_cert_path: Path to the API server CA bundle.
        proxy_shared_secret: Optional shared secret (X-Forwarded-Access-Token)
            required from the oauth2-proxy sidecar to trust its headers.
        require_cluster_admin: If True, the SubjectAccessReview checks the
            cluster-admin binding instead of the clustervis viewer verb set.
        cache_ttl_seconds: TokenReview result cache TTL.
    """

    def __init__(
        self,
        mode: str = "token",
        audience: str = DEFAULT_AUDIENCE,
        api_server_url: Optional[str] = None,
        ca_cert_path: Optional[str] = None,
        proxy_shared_secret: Optional[str] = None,
        require_cluster_admin: bool = False,
        cache_ttl_seconds: float = DEFAULT_CACHE_TEXLTTL if False else DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        if mode not in VALID_AUTH_TYPES:
            raise ValueError(
                f"invalid auth mode {mode!r}; expected one of {VALID_AUTH_TYPES}"
            )
        self.mode = mode
        self.audience = audience
        self.api_server_url = (api_server_url or self._default_api_server()).rstrip("/")
        self.ca_cert_path = ca_cert_path or self._default_ca_cert()
        self.proxy_shared_secret = proxy_shared_secret or os.environ.get(
            "CLUSTERVIS_PROXY_SHARED_SECRET", ""
        )
        self.require_cluster_admin = require_cluster_admin
        self.cache_ttl_seconds = float(cache_ttl_seconds)

        # token -> (expires_at, AuthResult)
        self._cache: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Environment defaults (in-cluster)
    # ------------------------------------------------------------------

    @staticmethod
    def _default_api_server() -> str:
        host = os.environ.get("KUBERNETES_SERVICE_HOST")
        port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        if host:
            return f"https://{host}:{port}"
        # Local dev fallback (kubectl proxy / local kind server)
        return os.environ.get("CLUSTERVIS_K8S_API_URL", "https://127.0.0.1:6443")

    @staticmethod
    def _default_ca_cert() -> str:
        if os.path.exists(DEFAULT_K8S_CA_CERT):
            return DEFAULT_K8S_CA_CERT
        return ""  # Empty -> system default SSL context

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def authenticate_request(
        self, headers: dict
    ) -> "tuple[bool, str, Opt[str]]":
        """
        Authenticate an inbound HTTP request.

        Args:
            headers: Case-insensitive-insensitive mapping of HTTP headers
                (raw header names as sent by the client).

        Returns:
            (is_authenticated, user, error)
              - is_authenticated: True when the request may proceed.
              - user: authenticated username (or pseudo-user in "none" mode).
              - error: human-readable reason on failure, else None.
        """
        h = {k.lower(): v for k, v in headers.items() if k}

        if self.mode == "none":
            return True, ANONYMOUS_USER, None

        if self.mode == "oauth2-proxy":
            return self._authenticate_oauth2_proxy(h)

        # mode == "token"
        token = self._extract_bearer_token(h)
        if not token:
            return False, "", "missing Authorization bearer token"

        result = self.validate_token(token)
        if not result.authenticated:
            return False, "", result.error
        return True, result.user, None

    def validate_token(self, token: str) -> AuthResult:
        """Validate a bearer token via TokenReview (+ cached SAR)."""
        now = time.time()
        with self._cache_lock:
            entry = self._cache.get(token)
            if entry and entry[0] > now:
                return entry[1]

        tr = self.token_review(token)
        if not tr.authenticated:
            result = tr
        else:
            sar = self.subject_access_review(tr.user, tr.groups)
            if not sar[0]:
                result = AuthResult(
                    False, tr.user, tr.groups,
                    f"user {tr.user!r} lacks access: {sar[1]}",
                )
            else:
                result = AuthResult(True, tr.user, tr.groups, None)

        with self._cache_lock:
            # Negative results cache for a shorter window than positive ones.
            ttl = self.cache_ttl_seconds if result.authenticated else min(
                self.cache_ttl_seconds, 5.0
            )
            self._cache[token] = (time.time() + ttl, result)
        return result

    # ------------------------------------------------------------------
    # Mode 2: oauth2-proxy trusted headers
    # ------------------------------------------------------------------

    def _authenticate_oauth2_proxy(self, h: Dict[str, str]) -> "tuple[bool, str, Opt[str]]":
        if self.proxy_shared_secret:
            provided = h.get("x-forwarded-access-token", "")
            if provided != self.proxy_shared_secret:
                return False, "", "invalid or missing proxy shared secret"

        user = (h.get("x-forwarded-user") or "").strip()
        email = (h.get("x-forwarded-email") or "").strip()
        if not user and email:
            user = email.split("@", 1)[0]
        if not user:
            return False, "", "missing X-Forwarded-User / X-Forwarded-Email headers"

        groups = [g for g in (h.get("x-forwarded-groups", "") or "").split(",") if g]
        return True, user, None

    # ------------------------------------------------------------------
    # Kubernetes TokenReview
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_bearer_token(h: Dict[str, str]) -> str:
        authz = h.get("authorization", "") or ""
        parts = authz.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        # Some clients (EventSource) cannot set headers; allow ?token= override.
        return ""

    def token_review(self, token: str) -> AuthResult:
        """
        POST /apis/authentication.k8s.io/v1/tokenreviews.

        Returns AuthResult with authenticated/user/groups from the API server.
        """
        body = {
            "apiVersion": "authentication.k8s.io/v1",
            "kind": "TokenReview",
            "spec": {
                "token": token,
                "audiences": [self.audience] if self.audience else [],
            },
        }
        status, resp = self._post_k8s(
            "/apis/authentication.k8s.io/v1/tokenreviews", body
        )
        if status is None:
            return AuthResult(False, error=f"token review unavailable: {resp}")
        if status not in (200, 201):
            return AuthResult(False, error=f"token review rejected: HTTP {status}")

        tr_status = (resp or {}).get("status", {}) if isinstance(resp, dict) else {}
        authenticated = bool(tr_status.get("authenticated", False))
        user_info = tr_status.get("user", {}) or {}
        username = user_info.get("username", "") or ""
        groups = user_info.get("groups", []) or []
        audiences = tr_status.get("audiences", []) or []

        if not authenticated:
            return AuthResult(False, username, groups, "token rejected by TokenReview (invalid or expired)")
        if self.audience and audiences and self.audience not in audiences:
            return AuthResult(
                False, username, groups,
                f"token not minted for audience {self.audience!r} (got {audiences})",
            )
        return AuthResult(True, username, list(groups), None)

    # ------------------------------------------------------------------
    # Kubernetes SubjectAccessReview
    # ------------------------------------------------------------------

    def subject_access_review(
        self, username: str, groups: Optional[list] = None
    ) -> "tuple[bool, str]":
        """
        POST /apis/authorization.k8s.io/v1/subjectaccessreviews.

        Checks the viewer permission (get on clustervis.io/topologies, or
        cluster-admin when require_cluster_admin is set).

        Returns (allowed, reason).
        """
        if self.require_cluster_admin:
            resource_attr: Dict[str, str] = {}
            non_resource_attr = "/cluster-admin"
        else:
            resource_attr = {
                "verb": "get",
                "group": "clustervis.io",
                "resource": "topologies",
            }
            non_resource_attr = ""

        body = {
            "apiVersion": "authorization.k8s.io/v1",
            "kind": "SubjectAccessReview",
            "spec": {
                "user": username,
                "groups": groups or [],
                "resourceAttributes": resource_attr,
                "nonResourceAttributes": (
                    {"verb": "get", "path": non_resource_attr}
                    if non_resource_attr
                    else {}
                ),
            },
        }
        status, resp = self._post_k8s(
            "/apis/authorization.k8s.io/v1/subjectaccessreviews", body
        )
        if status is None:
            return False, f"access review unavailable: {resp}"
        if status not in (200, 201):
            return False, f"access review error: HTTP {status}"

        sar_status = (resp or {}).get("status", {}) if isinstance(resp, dict) else {}
        allowed = bool(sar_status.get("allowed", False))
        reason = sar_status.get("reason", "") or ""
        return allowed, reason

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _post_k8s(
        self, path: str, body: Dict[str, Any]
    ) -> "tuple[Optional[int], Any]":
        """
        POST a JSON body to the Kubernetes API server using the operator's
        own ServiceAccount credentials.

        Returns (status_code, parsed_json) on transport success, or
        (None, error_message) on transport failure.
        """
        op_token = self._operator_token()
        if not op_token:
            return None, "operator service account token not found"

        ctx = ssl.create_default_context()
        if self.ca_cert_path and os.path.exists(self.ca_cert_path):
            ctx.load_verify_locations(cafile=self.ca_cert_path)
        else:
            # No CA bundle available (local dev against self-signed certs).
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            self.api_server_url + path,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {op_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0, context=ctx) as resp:
                raw = resp.read()
                try:
                    return resp.status, json.loads(raw.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return resp.status, None
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read().decode("utf-8"))
            except Exception:
                payload = None
            return e.code, payload
        except Exception as e:  # noqa: BLE001 — surface as auth-unavailable
            return None, str(e)

    @staticmethod
    def _operator_token() -> str:
        token = os.environ.get("CLUSTERVIS_OPERATOR_TOKEN", "")
        if token:
            return token
        try:
            with open(DEFAULT_K8S_TOKEN_FILE, "r", encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            return ""

    def invalidate_cache(self) -> None:
        """Drop all cached TokenReview results."""
        with self._cache_lock:
            self._cache.clear()


def build_authenticator_from_config(config: Optional[dict] = None) -> Authenticator:
    """
    Build an Authenticator from a values.yaml-style auth config block:

        auth:
          enabled: true
          type: "token"
          tokenValidation:
            audience: "clustervis"
            requireClusterAdmin: false
    """
    config = config or {}
    if not config.get("enabled", True):
        return Authenticator(mode="none")

    tv = config.get("tokenValidation", {}) or {}
    return Authenticator(
        mode=config.get("type", "token"),
        audience=tv.get("audience", DEFAULT_AUDIENCE),
        require_cluster_admin=bool(tv.get("requireClusterAdmin", False)),
    )
