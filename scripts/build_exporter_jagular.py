#!/usr/bin/env python3
"""
Jagular runner to build src/ingestion/exporter.py leveraging cluster-vis models and layout.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    print("--- Summoning Jagular for TASK-CV-406 (src/ingestion/exporter.py) ---")
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Python infrastructure systems engineer.
Write complete, bug-free, production-grade Python code."""

    user_prompt = """SPEC-03 / TASK-CV-406:
Author `src/ingestion/exporter.py`: Universal Kubernetes Cluster Topology Exporter CLI.

Requirements:
1. Command Line Interface:
   - CLI invocation: `python3 -m src.ingestion.exporter [--context <context>] [--kubeconfig <path>] [--output <filename.json>] [--mock]`
   - Uses `argparse`
   - Default output: prints JSON to stdout if --output is not given, or writes to file if --output is given.
2. Resource Harvesting & Discovery:
   - Function `export_cluster(context: Optional[str] = None, kubeconfig: Optional[str] = None, mock: bool = False) -> ClusterGraph`:
   - If mock is True (or if kubectl fails / is absent):
     Generate a valid synthetic `ClusterGraph` with control-plane (apiserver, etcd, scheduler, controller), worker nodes, Kubelet/Containerd, daemonsets (kube-proxy, cilium), and workloads (postgres, redis, ray), layout applied, and edges generated.
   - If live:
     - Run `kubectl` with `--context` and `--kubeconfig` if specified.
     - Discover nodes (`kubectl get nodes -o json`), pods (`kubectl get pods -A -o json`), daemonsets (`kubectl get daemonsets -A -o json`), services (`kubectl get svc -A -o json`), CRDs (`kubectl get crd -o json`).
     - Secret scrubbing: Any environment variable or annotation matching password/token/key/secret/auth is scrubbed to sha256 or [REDACTED]. ConfigMap values hashed to sha256.
     - Extract exact container images and digests from `status.containerStatuses`.
     - Build `NodeComponent` entries.
     - Detect DaemonSets and assign `asset_type="Cuboid_DaemonSet"`.
     - Call `enrich_framework_components(nodes, edges)` from `src.ingestion.frameworks`.
     - Call `apply_spatial_layout(nodes)` from `src.ingestion.layout`.
     - Call `generate_skyscraper_edges(nodes)` from `src.ingestion.layout`.
     - Construct and return `ClusterGraph` from `src.ingestion.models`.
3. Self-Executable:
   - `if __name__ == '__main__': main()`
   - Writes valid, formatted JSON.

Output ONLY Python code inside ```python ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3800)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "src/ingestion/exporter.py")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Successfully generated {out_path}!")

if __name__ == "__main__":
    run()
