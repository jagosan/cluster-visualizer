#!/usr/bin/env python3
"""
TASK-CV-406: Jagular runner to author src/ingestion/exporter.py (Universal Cluster Exporter).
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    print("--- Summoning Jagular for TASK-CV-406 (src/ingestion/exporter.py) ---")
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Kubernetes infrastructure and Python backend architect.
You author production-grade, secure, zero-dependency Python tools."""

    user_prompt = """SPEC-03 / TASK-CV-406:
Author `src/ingestion/exporter.py`: Universal Kubernetes Cluster Topology Exporter CLI.

Requirements:
1. Command Line Interface:
   - Invocation: `python3 -m src.ingestion.exporter --context <context> [--kubeconfig <path>] [--output <filename.json>]`
   - Use `argparse` with standard options:
     --context: Kubeconfig context name (e.g. kind-cluster-alpha, or default to current context)
     --kubeconfig: Optional path to kubeconfig file
     --output: Path to write JSON file (defaults to stdout or dist/data/<context>.json)
     --mock: Boolean flag to generate synthetic mock cluster graph for testing without live cluster
2. Zero-dependency Resource Harvesting:
   - Uses `subprocess.run(["kubectl", ...])` to query live cluster (or mock generator if --mock is passed or kubectl fails).
   - Resources harvested:
     - Nodes: `kubectl get nodes -o json`
     - Namespaces: `kubectl get ns -o json`
     - Pods: `kubectl get pods -A -o json`
     - DaemonSets: `kubectl get daemonsets -A -o json`
     - Deployments & StatefulSets: `kubectl get deploy,sts -A -o json`
     - Services: `kubectl get svc -A -o json`
     - CRDs: `kubectl get crd -o json`
3. Secret Scrubbing & Hashing:
   - NEVER export plaintext secret values or sensitive environment variables.
   - For environment variables matching password/token/key/secret/auth, scrub to `[REDACTED]` or `sha256:...`.
   - Extract exact container image strings and image digests (from `containerStatuses[*].imageID`).
4. Graph Assembly & Normalization:
   - Assemble `NodeComponent` objects for:
     - Distant Client (kubectl / browser watcher)
     - Penthouse / Ingress / Aggregator
     - Control plane: kube-apiserver, etcd, kube-scheduler, kube-controller-manager
     - Frameworks: Ray, Spark, Postgres, Redis
     - Nodes: Worker nodes (Kind = Node, layer = node)
     - DaemonSets: kube-proxy, cilium/cni, node-exporter (kind = DaemonSet, asset_type = Cuboid_DaemonSet)
     - Workload Pods (layer = workload)
   - Call `enrich_framework_components(nodes, edges)` from `src.ingestion.frameworks` if available.
   - Call `apply_spatial_layout(nodes)` from `src.ingestion.layout`.
   - Call `generate_skyscraper_edges(nodes)` from `src.ingestion.layout`.
   - Wrap into `ClusterGraph` from `src.ingestion.models` and serialize with `model_dump_json(indent=2)` or `.json()`.
5. Error Handling & Robustness:
   - Provide clear stderr messages if kubectl is missing or context is unreachable.
   - Fall back gracefully to mock cluster generation if --mock is passed or if testing in disconnected environment.

Write the complete `src/ingestion/exporter.py`.
Output ONLY Python code inside ```python ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=4000)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "src/ingestion/exporter.py")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Successfully generated {out_path}!")

if __name__ == "__main__":
    run()
