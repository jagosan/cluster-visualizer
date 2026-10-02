#!/usr/bin/env python3
"""
Connect src/operator/server.py to use TopologyController from src.operator.controller.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    print("--- Escalating to Jagular to wire controller into src/operator/server.py ---")
    system_prompt = """You are Jagular (177B Big Iron on Chunkito). You wire server components cleanly."""
    
    with open(os.path.join(REPO_ROOT, "src/operator/server.py")) as f:
        existing = f.read()

    user_prompt = f"""In `src/operator/server.py`, instead of defining a duplicate mock TopologyController class inline, import the real one from `.controller`:
```python
from .controller import TopologyController
```
(or `from src.operator.controller import TopologyController` with fallback `from .controller import TopologyController`).

Update `create_server`:
```python
def create_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    controller: Optional[TopologyController] = None,
) -> ThreadingHTTPServer:
    if controller is None:
        controller = TopologyController()
        controller.start(mock=True)
    ...
```
And in `main()`:
```python
    controller = TopologyController()
    controller.start(mock=args.mock, poll_interval=args.interval)
```

Here is the existing `src/operator/server.py`:
```python
{existing}
```

Please output the complete, clean, updated `src/operator/server.py`.
Output ONLY Python code inside ```python ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3500)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "src/operator/server.py")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Updated {out_path}")

if __name__ == "__main__":
    run()
