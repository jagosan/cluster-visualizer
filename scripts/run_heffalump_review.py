#!/usr/bin/env python3
"""
Run Heffalump (DeepSeek-V4 on Chunkito) review of Cluster Visualizer with streaming and token tracking.
"""

import json
import os
import sys
import time
import urllib.request

REPO_ROOT = "/home/jagosan/repos/cluster-vis"

# High-density distillation of the system
prompt_content = """# CLUSTER VISUALIZER (cluster-vis) ARCHITECTURE & CODEBASE OVERVIEW

## Objective
To give humans a way to understand cluster topology in a more physical way, by representing complex distributed systems in 3D space.

## Architecture Blueprint & Stack
1. Frontend Client: Vite 7 + TypeScript 5.9 + Three.js r180. WebGL canvas with:
   - Layered Skyscraper Elevation:
     * External Ingress / DNS (Y = 12.0)
     * API Gateways / L7 Mesh (Y = 8.5)
     * Control Plane Supervisors (Y = 5.0)
     * Horizontal Worker Decks (Y = 0.5, X/Z planar layout with machine chassis)
     * Subterranean Cloud Vaults (Sub-Level B1-B3, Y = -2.5 to -8.5: CloudSQL, Pub/Sub, Redis, Kro/KCC)
   - Dynamic Bezier Conduits: Curved 3D pipes with GPU instanced particle flows (`FlowParticleSystem`), speed scaled by RPS, color-coded by latency (cyan <30ms, amber 30-200ms, crimson >200ms).
   - Latency Force Field Mode: Spring-mass graph layout (`latency_layout.py` & `latency_spring_engine.ts`) where physical 3D distance between nodes reflects measured network latency. Smooth lerp transition between Skyscraper and Force modes.
   - Multi-Cluster Comparison: Dual split-screen (2-viewport) and Quad grid (4-viewport matrix) with synchronized OrbitControls camera pitch/yaw/zoom, visual git-style diff badges (identical, version_skew, missing, added), and SHA256 digest skews.
   - Autoscaling & Staging Yard (SPEC-09/10):
     * Proportional Pod Capsules: procedural capsule geometry sized dynamically by CPU/Memory requests.
     * VPA In-Place Morphing: 1200ms procedural geometry morph tween with energy ripple pulse.
     * HPA Lateral Conveyor: Dispatch pulse down central riser and lateral conveyor slide into node tray slots.
     * Exterior Pre-Admission Staging Yard (X in [-24, -12], Y = 0.2): Pending pods hover with anti-gravity bobbing, Karpenter NodeClaim ghost chassis on B1 with amber tractor beams.
     * Kueue Gang Cargo Pallets: Industrial frame encasing constituent pods, HUD badges with quota, mag-rail transit tween ($X: -18 -> -8$) and gang deployment burst.
   - Traffic Simulation Harness (SPEC-10): Dockable HUD running discrete-event M/M/c/K queuing physics, step/sine/ramp/chaos load injection, comparing GKE Autopilot Compute Class (sub-second scheduling onto pre-warmed slices) vs Karpenter/static cold VM delays (60-150s pending in staging yard).

2. In-Cluster Operator & Streaming Server (`src/operator/`):
   - Python HTTP + SSE streaming server (zero third-party dependencies):
     * `GET /healthz`
     * `GET /snapshot` (single-shot sanitized topology graph)
     * `GET /api/v1/topology/stream` (SSE event stream of live pod/node/CRD mutations)
   - Controller (`controller.py`): In-cluster Kubernetes watch informers tracking Pods, Nodes, Services, HPAs, and CRDs (KCC, Kro, KubeRay, Patroni).
   - Secret Scrubber (`graph_engine.py`): Zero-trust in-memory redaction. Replaces secrets, passwords, certificates, and auth tokens with `sha256:` fingerprints.
   - Auth Layer (`auth.py`): Pluggable modes:
     * Mode 1 "token": Kubernetes ServiceAccount bearer token validated via `authentication.k8s.io/v1` `TokenReview` and `authorization.k8s.io/v1` `SubjectAccessReview` (30s TTL cache).
     * Mode 2 "oauth2-proxy": Trusts `X-Forwarded-User` / `X-Forwarded-Email` headers from ingress sidecar (optional shared secret).
     * Mode 3 "none": Headless sandbox anonymous user.
   - CORS: Configurable, defaults to wildcard `*`.
   - Client-side token storage: In-browser `sessionStorage`.

3. Network Probe DaemonSet (`src/probe/main.py`):
   - Microscopic unprivileged Python daemon measuring TCP SYN round-trip times between nodes in a round-robin mesh.
   - Aggregated by the operator's `LatencyEdgeAggregator` to drive edge latency metrics and force-field physics.

4. Client-Side Ingestion & CLI Tools:
   - `src/ingestion/client_extractor.ts`: In-browser manifest parser converting raw K8s API responses directly into 3D Skyscraper graphs with zero cluster footprint.
   - `src/ingestion/exporter.py` / `cluster-vis dump`: Zero-dependency CLI dumping live kubeconfig graphs into standalone JSON.
   - `src/ingestion/differ.py`: AST/digest diff classifier.

---
YOUR MISSION AS HEFFALUMP:
Perform an exhaustive, top-tier architectural and technical review of Cluster Visualizer.
Structure your output into two comprehensive parts:

### PART I: DETAILED ARCHITECTURAL & TECHNICAL ANALYSIS
1. Performance & Scalability:
   - WebGL / Three.js limits: Draw calls, geometry instancing, material overhead, GC pressure from particle systems and morph tweens. Behavior at scale (500+ nodes, 10,000+ pods, dense conduit meshes).
   - In-cluster Operator & SSE broadcasting: Memory footprint of in-memory graph, client fan-out under high pod churn (watch informer storms), network probe mesh scaling ($O(N^2)$ SYN ping overhead).
   - Ingestion & Diff scaling bottlenecks.
2. Security & Hardening:
   - Operator RBAC permissions and attack surface: ClusterRole requirements for cluster-wide watches, blast radius if operator is compromised.
   - Secret scrubbing leaks: Edge cases in env vars, configmaps, container args, downward API, and custom CRDs.
   - Auth & Session Hygiene: Bearer token in browser `sessionStorage`, CORS wildcard, CSRF/SSE hijacking risks, TokenReview caching trade-offs.
   - Probe security: TCP SYN scanning implications in zero-trust VPCs and firewalled clusters.
3. Usability & Objective Alignment:
   - Does 3D spatial representation genuinely enhance human understanding of distributed systems, or does it suffer from cognitive overload, 3D occlusion, camera disorientation, and low information density compared to 2D DAGs (e.g. Backstage, Argo, Datadog)?
   - Diagnostic actionability: Can an on-call SRE resolve an outage faster using this tool? Where does the 3D metaphor succeed and where does it fail?

### PART II: TECHNICAL SPECIFICATION & ROADMAP (Next-Gen Architecture)
1. Performance Spec:
   - Level-of-Detail (LOD) and Hierarchical Clustering (Pod grouping into Workload/Namespace aggregate bounding volumes).
   - WebGL InstancedMesh migration for capsules, trays, and conduits to achieve 60 FPS at 25,000+ pods.
   - Operator delta compression & binary streaming (Protocol Buffers or CBOR over WebSocket/SSE).
2. Security Hardening Spec:
   - Zero-permission read-only sidecar / eBPF passive capture replacing active TCP SYN probes.
   - WebAuthn / OIDC PKCE flow replacing raw bearer token entry; strict CSP & origin pinning.
   - Dynamic redaction policy engine.
3. Usability & Hybrid Viewport Spec:
   - Dual-mode 2D Orthographic Schematic vs 3D Isometric elevation.
   - Incident triage "Blast Radius & Root Cause" focal lens.
"""

payload = {
    "model": "deepseek-v4",
    "messages": [
        {"role": "system", "content": "You are Heffalump, an elite distributed systems architect, Kubernetes core authority, and high-performance WebGL systems engineer. Write a deeply technical, authoritative, rigorous review and specification."},
        {"role": "user", "content": prompt_content}
    ],
    "temperature": 0.2,
    "max_tokens": 4000,
    "stream": True
}

req_data = json.dumps(payload).encode("utf-8")
url = "http://100.71.183.123:11434/v1/chat/completions"

print(f"Connecting to Heffalump (DeepSeek-V4 on Chunkito)...")
start_time = time.time()
req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})

full_content = []
prompt_tokens = 0
completion_tokens = 0
first_token_time = None

with urllib.request.urlopen(req, timeout=600) as resp:
    print("Stream connected. Waiting for first token...")
    for line in resp:
        line = line.decode("utf-8").strip()
        if not line:
            continue
        if line.startswith("data: "):
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                if first_token_time is None:
                    first_token_time = time.time()
                    ttft = first_token_time - start_time
                    print(f"Time to first token (TTFT): {ttft:.2f}s")
                
                delta = chunk["choices"][0].get("delta", {})
                content_piece = delta.get("content", "")
                if content_piece:
                    full_content.append(content_piece)
                
                # Check for usage if returned in stream
                if "usage" in chunk and chunk["usage"]:
                    prompt_tokens = chunk["usage"].get("prompt_tokens", prompt_tokens)
                    completion_tokens = chunk["usage"].get("completion_tokens", completion_tokens)
            except Exception:
                pass

total_time = time.time() - start_time
output_text = "".join(full_content)
print(f"Generation completed in {total_time:.2f}s!")
print(f"Total characters: {len(output_text)}")

# If usage was not emitted in stream chunks, estimate or query
if completion_tokens == 0:
    completion_tokens = len(output_text) // 4
if prompt_tokens == 0:
    prompt_tokens = len(prompt_content) // 4

out_file = "/home/jagosan/repos/cluster-vis/docs/heffalump_review.md"
with open(out_file, "w", encoding="utf-8") as f:
    f.write(output_text)

meta_file = "/home/jagosan/repos/cluster-vis/docs/heffalump_review_meta.json"
with open(meta_file, "w", encoding="utf-8") as f:
    json.dump({
        "elapsed_seconds": total_time,
        "ttft_seconds": first_token_time - start_time if first_token_time else 0,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "model": "deepseek-v4"
    }, f, indent=2)

print(f"Saved review to {out_file}")
