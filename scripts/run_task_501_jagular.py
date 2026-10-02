#!/usr/bin/env python3
"""
TASK-CV-501: Jagular runner to author CRD & Operator deployment manifests in deploy/.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    print("--- Summoning Jagular for TASK-CV-501 (deploy/crd/ and deploy/operator/) ---")
    system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead Kubernetes infrastructure architect.
You author production-grade, secure, valid Kubernetes YAML manifests conforming to OpenAPI v3 and standard RBAC best practices."""

    user_prompt = """SPEC-04 / TASK-CV-501:
Author the Kubernetes CRD and Operator deployment manifests.

Files required:
1. `deploy/crd/clustervis.io_clustertopologysnapshots.yaml`
   - CustomResourceDefinition for `ClusterTopologySnapshot` (`clustervis.io/v1alpha1`).
   - Group: clustervis.io
   - Names: kind: ClusterTopologySnapshot, plural: clustertopologysnapshots, singular: clustertopologysnapshot, shortNames: [cts]
   - Scope: Cluster
   - OpenAPIV3Schema:
     - spec:
       - exportIntervalSeconds (integer, default 10)
       - excludedNamespaces (array of string)
       - scrubSecrets (boolean, default true)
       - trackImageDigests (boolean, default true)
     - status:
       - lastSnapshotTimestamp (string, date-time)
       - nodeCount (integer)
       - podCount (integer)
       - driftDetected (boolean)
       - activeHash (string)

2. `deploy/operator/operator.yaml`
   - Namespace: `clustervis-system`
   - ServiceAccount: `clustervis-operator` in `clustervis-system`
   - ClusterRole: `clustervis-operator` with read-only verbs (get, list, watch) on:
     - core resources: nodes, namespaces, pods, services
     - apps: daemonsets, deployments, statefulsets
     - apiextensions.k8s.io: customresourcedefinitions
     - and full verbs (get, list, watch, create, update, patch) on:
       - clustervis.io: clustertopologysnapshots, clustertopologysnapshots/status
   - ClusterRoleBinding: binding `clustervis-operator` ServiceAccount to `clustervis-operator` ClusterRole
   - Deployment: `clustervis-operator` in namespace `clustervis-system`
     - Replicas: 1
     - Container: `clustervis/operator:v0.1.0`
     - Command / args running `python3 -m src.operator.server --port 8080`
     - Ports: containerPort 8080 (name: http-stream)
     - Resources: requests (cpu: 50m, memory: 32Mi), limits (cpu: 200m, memory: 128Mi)
     - Liveness / Readiness probe on `/api/v1/healthz` port 8080
   - Service: `clustervis-operator` in namespace `clustervis-system` exposing port 8080 (targetPort 8080).

Format your output as two YAML code blocks, each labeled with its relative file path comment at the top:
```yaml
# deploy/crd/clustervis.io_clustertopologysnapshots.yaml
...
```
```yaml
# deploy/operator/operator.yaml
...
```
"""

    response = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=4000)

    # Extract YAML blocks
    yaml_blocks = re.findall(r"```ya?ml\s*(.*?)\s*```", response, re.DOTALL)
    if not yaml_blocks:
        print("Error: No YAML blocks returned from Jagular")
        sys.exit(1)

    crd_content = None
    operator_content = None

    for block in yaml_blocks:
        if "kind: CustomResourceDefinition" in block:
            crd_content = block
        elif "kind: Deployment" in block or "kind: ServiceAccount" in block:
            operator_content = block

    if not crd_content or not operator_content:
        # Fallback to positional if comments matched
        if len(yaml_blocks) >= 2:
            crd_content = yaml_blocks[0]
            operator_content = yaml_blocks[1]
        else:
            print("Error: Could not identify both CRD and operator YAML blocks")
            sys.exit(1)

    crd_path = os.path.join(REPO_ROOT, "deploy/crd/clustervis.io_clustertopologysnapshots.yaml")
    os.makedirs(os.path.dirname(crd_path), exist_ok=True)
    with open(crd_path, "w") as f:
        f.write(crd_content.strip() + "\n")
    print(f"Authored {crd_path}")

    operator_path = os.path.join(REPO_ROOT, "deploy/operator/operator.yaml")
    os.makedirs(os.path.dirname(operator_path), exist_ok=True)
    with open(operator_path, "w") as f:
        f.write(operator_content.strip() + "\n")
    print(f"Authored {operator_path}")

if __name__ == "__main__":
    run()
