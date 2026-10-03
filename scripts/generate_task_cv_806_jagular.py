#!/usr/bin/env python3
"""
Generate TASK-CV-806 (Multi-Cluster Federation HUD & Token Dialog) using Jagular.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def generate_federation_ts():
    print("--- Invoking Jagular to generate src/ui/cluster_federation.ts ---")
    system_prompt = (
        "You are Jagular (177B Big Iron on Chunkito). You write strict TypeScript code with "
        "verbatimModuleSyntax ('import type'), strict: true, and explicit handling of noUncheckedIndexedAccess."
    )
    user_prompt = """
Write the complete TypeScript module `src/ui/cluster_federation.ts` (TASK-CV-806 / SPEC-07 §7.1 & §7.2).

Requirements:
1. Strict TypeScript:
   - Use `import type` for type-only imports.
   - Guard DOM lookups and array indices with `??` or checks (`noUncheckedIndexedAccess`).
2. Export interfaces:
   ```typescript
   export interface ClusterEndpoint {
     id: string;
     name: string;
     url: string;
     token?: string;
     status: 'connected' | 'connecting' | 'error' | 'offline';
     latencyMs: number;
     kubernetesVersion: string;
   }

   export interface WorkloadComparison {
     clusterId: string;
     clusterName: string;
     workloadName: string;
     version: string;
     latencyMs: number;
     rps: number;
   }
   ```
3. Export class `ClusterFederationManager`:
   - Stores endpoints in a `Map<string, ClusterEndpoint>`.
   - Persists tokens securely in `sessionStorage` (never `localStorage` per SPEC-07 §5.1):
     `sessionStorage.getItem('clustervis_token_' + endpointId)`.
   - Methods:
     - `addEndpoint(endpoint: Omit<ClusterEndpoint, 'status' | 'latencyMs' | 'kubernetesVersion'>): ClusterEndpoint`
     - `removeEndpoint(id: string): void`
     - `getEndpoints(): ClusterEndpoint[]`
     - `getEndpoint(id: string): ClusterEndpoint | undefined`
     - `setToken(id: string, token: string): void`
     - `getToken(id: string): string | undefined`
     - `connectEndpoint(id: string): Promise<boolean>` (performs test fetch to `/api/v1/healthz` or `/api/v1/topology` with Bearer token header)
     - `compareWorkload(workloadName: string): WorkloadComparison[]`
4. Export function `createFederationManager(): ClusterFederationManager`

Output ONLY the complete TypeScript code inside ```typescript ```.
"""
    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3000)
    match = re.search(r"```typescript\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "src/ui/cluster_federation.ts")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Wrote {out_path}")

def generate_auth_modal_ts():
    print("--- Invoking Jagular to generate src/ui/auth_modal.ts ---")
    system_prompt = (
        "You are Jagular (177B Big Iron on Chunkito). You write strict TypeScript code with "
        "verbatimModuleSyntax ('import type'), strict: true, and explicit handling of noUncheckedIndexedAccess."
    )
    user_prompt = """
Write the complete TypeScript module `src/ui/auth_modal.ts` (TASK-CV-806 / SPEC-07 §5.1).

Requirements:
1. Strict TypeScript:
   - Use `import type` for type-only imports.
   - All DOM operations and array accesses must be safe (`noUncheckedIndexedAccess`).
2. Export class `AuthModal`:
   - `constructor()`
   - `open(clusterName: string, clusterUrl: string, onConnect: (token: string) => void): void`
     - Displays a modal overlay dialog requesting a Kubernetes ServiceAccount Bearer Token.
     - Displays security explanation: "Tokens are stored in browser sessionStorage for this tab only, never persisted to disk or localStorage."
     - Form includes:
       - Cluster URL (read-only or editable)
       - Token textarea / password input
       - "Connect" button and "Cancel" button
   - `close(): void`
     - Hides and removes the modal overlay.

Output ONLY the complete TypeScript code inside ```typescript ```.
"""
    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3000)
    match = re.search(r"```typescript\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "src/ui/auth_modal.ts")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Wrote {out_path}")

def generate_federation_tests():
    print("--- Invoking Jagular to generate tests/test_federation.py ---")
    system_prompt = (
        "You are Jagular (177B Big Iron on Chunkito). You write comprehensive Python unittest suites."
    )
    user_prompt = """
Write the complete Python test suite `tests/test_federation.py` using `unittest` (TASK-CV-806 / SPEC-07 §7).

Test requirements:
1. Test multi-cluster endpoint schema validation:
   - Required fields: id, name, url, status, latency_ms, kubernetes_version.
2. Test token auth verification flow:
   - Ingesting Bearer token header in HTTP request.
   - 401 response on missing or invalid token.
   - 200 response on valid token.
3. Test cross-cluster latency comparison logic:
   - Given two clusters with workload 'postgres-ha', compare latencies:
     Cluster A (2.1ms) vs Cluster B (14.8ms).
   - Validates diff report generation.

Output ONLY the complete Python code inside ```python ```.
"""
    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3000)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "tests/test_federation.py")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Wrote {out_path}")

if __name__ == "__main__":
    generate_federation_ts()
    generate_auth_modal_ts()
    generate_federation_tests()
