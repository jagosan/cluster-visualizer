# Zero-Trust Security Audit — TASK-CV-1407

**Auditor:** Hermes (Heffalump/DeepSeek-V4) · **Date:** 2026-10-11
**Scope:** SPEC-13 §3.3 / §6.2 & ADR-1303
**Files audited:**
- `src/operator/auth.py`
- `src/operator/graph_engine.py`
- `src/operator/server.py`
- `src/ui/auth_modal.ts`, `src/ui/cluster_onboarding.ts`, `src/ui/cluster_federation.ts`

**Verdict:** NOT READY FOR ZERO-TRUST RELEASE. 3 critical gaps block §6.2 acceptance.

---

## Objective 1 — Elimination of in-browser bearer token retention: **FAIL**

SPEC-13 §3.3.1 mandates *"The UI shall deprecate direct ServiceAccount token pasting in modal dialogs."*

| File | Finding |
|---|---|
| `src/ui/auth_modal.ts` (L5-6, L66, L108-117) | Full ServiceAccount Bearer Token textarea + explicit sessionStorage note. Not deprecated. |
| `src/ui/cluster_onboarding.ts` (L18, L136-159, L513, L601, L813) | `sessionStorage.setItem('clustervis_token_<id>', token)` — tokens stored & read back; security note endorses sessionStorage retention. |
| `src/ui/cluster_federation.ts` (L71-91) | `setToken`/`getToken` persist raw bearer tokens to sessionStorage. |

**No deprecation warning exists anywhere in `src/ui`** — zero matches for `deprecat`, `oauth2-proxy`, or `CLUSTERVIS_PROXY_SHARED_SECRET`. Browser JS still touches sensitive credentials (ADR-1303 consequence not met).

## Objective 2 — Wildcard CORS elimination under auth: **PARTIAL (sync PASS / ASGI FAIL)**

**Sync path (`server.py`) — PASS.** `_set_cors_headers` suppresses `*` whenever `auth_mode in ("oauth2-proxy","token")`; `create_server` strips `*` from `CLUSTERVIS_CORS_ORIGINS` with a warning. Unlisted origins receive no ACAO header (test-verified).

**Async ASGI path (`operator_asgi_app`) — FAIL.** The SPEC-13 §3.4 forward path sets **no CORS headers at all and performs no authentication**. It serves `/snapshot`, `/topology`, and `/stream` to unauthenticated callers with 200 (test-proven).

## Objective 3 — HMAC signature enforcement in oauth2-proxy mode: **PARTIAL / FAIL**

**When a shared secret IS configured** (`CLUSTERVIS_PROXY_SHARED_SECRET` / `proxyAuth.sharedSecret`):
- Missing / empty / forged signatures → rejected ✓
- Tampered user with stale valid signature → rejected ✓
- Drift > 300s → rejected; drift ≤ 290s accepted ✓ (SPEC §6.2 threshold honored)

**CRITICAL — HMAC is optional, not mandatory.** `_authenticate_oauth2_proxy` only verifies signatures when `self.proxy_shared_secret` is truthy. If the secret env var is absent or empty, the operator **trusts raw spoofable `X-Forwarded-*` plaintext headers with no signature at all** — an attacker can forge any identity (test-proven). SPEC §3.3.2 requires *"Reject any request lacking a valid HMAC signature when running in oauth2-proxy mode"* → **not met**.

## Objective 4 — Whitelist extraction & hash redaction: **PARTIAL / FAIL**

**`WhitelistExtractor` (SPEC-mandated schema) — PASS.** Env values hashed to `sha256:<hex[:8]>`, args credentials regex-redacted, Secret/ConfigMap `data`/`binaryData` stripped, annotations dropped. Zero plaintext leak in tests.

**CRITICAL — production does NOT use it.** `server.py` imports `WhitelistExtractor` but calls **`SecretScrubber.scrub_graph()`**, which has two plaintext-leak gaps (test-proven):
1. **Deployment/StatefulSet manifests:** env lives at `spec.template.spec.containers[].env`; `_scrub_pod_spec_inner` only handles top-level `containers`, so nested template env values leak verbatim.
2. **Graph `manifests` list:** `_scrub_manifest`'s non-Pod/ConfigMap branch keeps the entire spec (including env) as-is → plaintext connection strings leak.

---

## Test Evidence

Added `tests/test_zerotrust_security_audit.py` — 25 tests, 23 pass + 2 genuine failures:

| Test | Result | Implication |
|---|---|---|
| `test_missing_signature_rejected`, `test_forged_signature_rejected`, `test_expired_timestamp_rejected`, `test_forged_user_with_valid_signature_rejected` | PASS | HMAC enforced when secret set |
| `test_oauth2_proxy_without_secret_accepts_spoofed_headers` | PASS (asserts vuln) | CRITICAL: no-secret ⇒ spoofable identity |
| `test_asgi_snapshot_without_auth_returns_200`, `test_asgi_never_calls_authenticator` | PASS (asserts vuln) | ASGI path bypasses auth + CORS |
| `test_wildcard_suppressed_in_token_mode/oauth2_proxy_mode`, `test_unlisted_origin_blocked_under_auth` | PASS | Sync CORS hardening correct |
| `test_env_values_hashed_to_sha256`, `test_no_plaintext_secret_in_output`, `test_args_credentials_redacted`, `test_secret_and_configmap_data_stripped` | PASS | WhitelistExtractor zero-leak |
| `test_deployment_template_env_scrubbed` | **FAIL** | SecretScrubber leaks Deployment env |
| `test_manifest_list_deployment_leaks_env` | **FAIL** | manifests-list leak |

## Required Remediation

1. Delete/redact bearer-token modals (`auth_modal.ts`, onboarding/federation token storage); route through OAuth2-Proxy cookie sessions per ADR-1303.
2. Make HMAC verification **mandatory** in `oauth2-proxy` mode — fail closed when `CLUSTERVIS_PROXY_SHARED_SECRET` is unset (or refuse to start).
3. Wire the ASGI app through the same `authenticate_request` gate + CORS policy as the sync handler.
4. Route production scrubbing through `WhitelistExtractor.extract_graph`, or fix `SecretScrubber` to scrub nested `template.spec.containers[].env` and non-Pod manifests.
