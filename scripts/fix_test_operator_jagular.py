#!/usr/bin/env python3
"""
Escalate to Jagular to fix method names and imports in tests/test_operator_and_stream.py.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    print("--- Escalating to Jagular to fix tests/test_operator_and_stream.py ---")
    system_prompt = """You are Jagular (177B Big Iron on Chunkito). You align test suites to exact module APIs."""
    
    with open(os.path.join(REPO_ROOT, "tests/test_operator_and_stream.py")) as f:
        existing = f.read()

    user_prompt = """In `tests/test_operator_and_stream.py`:
1. Change `from src.models.graph import ClusterGraph` to:
   `from src.ingestion.models import ClusterGraph, NodeComponent, Spatial`
2. Change `controller.register_listener(q)` to:
   `controller.add_listener(q)`
3. In `test_event_broadcasting_node_added`:
   `test_payload = {'node': {'id': 'pod-test-1', 'layer': 'workload', 'kind': 'Pod', 'name': 'test-pod-1', 'spatial': {'x': 1.0, 'y': 0.75, 'z': 0.5}}}`
   `controller.inject_mutation('node_added', test_payload)`
   The event tuple from `q.get()` is `('node_added', payload)` where `payload['node']['id'] == 'pod-test-1'`.
4. In `test_event_broadcasting_node_modified`:
   `controller.inject_mutation('node_modified', {'node_id': 'pod-test-1', 'status': 'version_skew'})`
   The event tuple from `q.get()` is `('node_modified', payload)` where `payload['node_id'] == 'pod-test-1'`.
5. In `test_event_broadcasting_node_removed`:
   `controller.inject_mutation('node_removed', {'node_id': 'pod-test-1'})`
   The event tuple from `q.get()` is `('node_removed', payload)` where `payload['node_id'] == 'pod-test-1'`.

Here is the existing file:
```python
""" + existing + """
```

Output ONLY the complete, updated `tests/test_operator_and_stream.py` inside ```python ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3500)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "tests/test_operator_and_stream.py")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Updated {out_path}")

if __name__ == "__main__":
    run()
