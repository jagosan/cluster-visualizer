import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

system_prompt = """You are Jagular (177B Big Iron on Chunkito).
Write clean, concise Python for `generate_skyscraper_edges` using:
from .models import NodeComponent, DataFlowEdge
"""

user_prompt = """Write:
def generate_skyscraper_edges(nodes: List[NodeComponent]) -> List[DataFlowEdge]:
    # Returns architectural data flow edges for SPEC-01:
    # 1. Distant Client -> Ingress/API Aggregator (traffic / HTTPS/443)
    # 2. Ingress/Aggregator -> API Server (traffic / HTTPS/6443)
    # 3. API Server -> etcd (control_plane / gRPC/2379)
    # 4. Kubelet -> API Server periodic heartbeat (control_plane / HTTPS/6443/Heartbeat)
    # 5. Controller/Scheduler <-> API Server (control_plane / HTTPS/6443)
    # 6. Inter-API server sync (control_plane / HTTPS/6443)
    # 7. Framework direct bypass pipes (Ray head <-> Ray workers) (framework_control / gRPC/10001)

Output only the Python function.
"""

code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=1500)
import re
match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
if match:
    code = match.group(1)

with open("/tmp/jagular_edges.py", "w") as f:
    f.write(code)

print("Saved /tmp/jagular_edges.py (%d bytes)" % len(code))
