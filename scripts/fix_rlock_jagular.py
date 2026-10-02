#!/usr/bin/env python3
"""
Escalate to Jagular to use threading.RLock() in src/operator/controller.py.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    print("--- Escalating to Jagular to fix Lock reentrancy in src/operator/controller.py ---")
    system_prompt = """You are Jagular (177B Big Iron on Chunkito). You fix concurrency bugs."""
    
    with open(os.path.join(REPO_ROOT, "src/operator/controller.py")) as f:
        content = f.read()

    # Jagular prompt to fix Lock to RLock
    user_prompt = f"""In `src/operator/controller.py`, `inject_mutation` holds `with self.lock:` and then calls `self.broadcast_event(...)` which also acquires `with self.lock:`.
Because `self.lock = threading.Lock()` was used, it creates a reentrant deadlock!
Please replace `threading.Lock()` with `threading.RLock()` and ensure `RLock` is imported from `threading`.

Current code:
```python
{content}
```

Output ONLY the corrected Python code in ```python ```.
"""

    code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=3000)
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        code = match.group(1)

    out_path = os.path.join(REPO_ROOT, "src/operator/controller.py")
    with open(out_path, "w") as f:
        f.write(code.strip() + "\n")
    print(f"Updated {out_path}")

if __name__ == "__main__":
    run()
