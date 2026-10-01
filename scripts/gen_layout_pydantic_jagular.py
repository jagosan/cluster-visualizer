import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

system_prompt = """You are Jagular (177B Big Iron on Chunkito).
Write clean, concise Python for `src/ingestion/layout.py` using:
from .models import NodeComponent, DataFlowEdge
where `n.spatial.x`, `n.spatial.y`, `n.spatial.z`, `n.spatial.asset_type` are assigned.
"""

user_prompt = """Write `src/ingestion/layout.py` with:
ELEVATION_TIERS = {
    "client": 11.0,
    "aggregation": 8.0,
    "apiserver": 6.0,
    "vault": 4.5,
    "supervisor": 4.5,
    "framework": 2.0,
    "worker_base": 0.0,
    "worker_pitch": -2.6,
}

def apply_spatial_layout(nodes: List[NodeComponent]) -> List[NodeComponent]:
    # assign n.spatial.x, n.spatial.y, n.spatial.z, n.spatial.asset_type
    # according to SPEC-01 skyscraper tiers:
    # client: Y=11.0, Z=6.0, asset_type='Client_Slab'
    # aggregation/ingress: Y=8.0, Z=0.0, asset_type='Skyscraper_Penthouse'
    # apiserver: Y=6.0, Z=0.0, asset_type='ControlPlane_Cube'
    # etcd: Y=4.5, Z=-3.5, asset_type='ControlPlane_Vault'
    # scheduler / controller-manager: Y=4.5, Z=0.8, asset_type='ControlPlane_Cube'
    # framework (ray/spark): Y=2.0, Z=0.0
    # worker nodes & workloads:
    # partition across worker floors (Y=0.0, -2.6, -5.2...).
    # for each floor, place node tray ('Skyscraper_FloorTray') at (0, Y, 0),
    # kubelet ('Module_Kubelet') at (-1.5, Y+0.35, 0),
    # containerd ('Module_Containerd') at (-0.7, Y+0.35, 0),
    # pods at X in [0.2, 1.0, 1.8], Z in [-0.5, 0.5], Y=Y+0.45.
    # asset_types: Database_Postgres, Cache_Redis, Module_PodCapsule.

def generate_skyscraper_edges(nodes: List[NodeComponent]) -> List[DataFlowEdge]:
    # add heartbeat edges (kubelet -> apiserver)
    # apiserver <-> etcd edges
    # apiserver <-> apiserver inter-sync
    # client -> apiserver request edges

Output ONLY the code for layout.py.
"""

code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=2500)
import re
match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
if match:
    code = match.group(1)

with open("src/ingestion/layout.py", "w") as f:
    f.write(code)

print("Saved layout.py (%d bytes)" % len(code))
