#!/usr/bin/env python3
"""
Generate src/operator/graph_engine.py using Jagular (177B on Chunkito).
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    print("--- Invoking Jagular to generate src/operator/graph_engine.py ---")
    system_prompt = (
        "You are Jagular (177B Big Iron on Chunkito). You write clean, production-grade Python "
        "modules with zero third-party dependencies (stdlib only) adhering strictly to specifications."
    )
    user_prompt = """
Write the complete Python module `src/operator/graph_engine.py` for ClusterVis (TASK-CV-803 / SPEC-07 §5.3 & §6.1).

Requirements:
1. SecretScrubber:
   - Sanitizes Kubernetes manifests and topology snapshots before transmission or serialization.
   - scrub_pod_spec(pod_dict: dict) -> dict:
     - Strips secret volumes (volumes where 'secret' is present).
     - Sanitizes container env list: drop 'value' and 'valueFrom' fields. Only keep the variable name if it does NOT match any pattern containing KEY, TOKEN, SECRET, PASSWORD, or PASS (case-insensitive). If it matches, drop the env var entry entirely.
     - Strips envFrom references targeting Secret resources.
   - scrub_configmap(cm_dict: dict) -> dict:
     - Omit 'data' and 'binaryData', retaining only metadata and volume mount references.
   - scrub_metadata(metadata_dict: dict) -> dict:
     - Strips 'kubectl.kubernetes.io/last-applied-configuration'.
     - Strips any annotation or label key/value containing 'token', 'cert', 'key', 'auth', or 'secret'.
   - scrub_graph(graph_dict: dict) -> dict:
     - Runs scrubber across all nodes, manifests, and components in the cluster graph.

2. LatencyEdgeAggregator:
   - In-memory thread-safe metric store and hierarchical edge aggregator.
   - Maintains node-to-node latency matrix and service-to-service aggregated metrics.
   - ingest_probe_report(report: dict) -> None:
     - Ingests report from clustervis-probe (/metrics/latency) with node name, timestamp, and measurements list.
     - Stores latest RTT latency (ms) and status per target.
   - ingest_telemetry_event(source: str, target: str, latency_ms: float, rps: float = 0.0) -> None:
     - Updates link latency and RPS.
   - get_latency(src_node: str, dst_node: str, default_ms: float = 1.0) -> float:
     - Returns latest measured latency between nodes, or default_ms.
   - aggregate_service_edges(components: list, raw_edges: list) -> list:
     - Groups pod-to-pod connections by logical Service or Deployment workload (SPEC-07 §6.1).
     - Combines parallel edges into a single logical conduit with mean latency_ms and summed RPS.
     - Prunes idle micro-edges where RPS == 0 and traffic is below threshold.

3. Module exports:
   - SecretScrubber
   - LatencyEdgeAggregator
   - scrub_cluster_graph(graph: dict) -> dict

Output ONLY the complete, syntactically valid Python code inside ```python ```.
"""
    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=4096)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)
    
    out_path = os.path.join(REPO_ROOT, "src/operator/graph_engine.py")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
