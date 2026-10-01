import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jagular_agent import call_jagular

system_prompt = """You are Jagular (177B Big Iron on Chunkito), lead systems architect for the Pantheon Swarm.
Write complete, verified Python code with no placeholders or stubs.
"""

user_prompt = """Implement TASK-CV-202: Rewrite `src/ingestion/layout.py` for cluster-vis to implement the Skyscraper / Layered Building Topology per SPEC-01.

SPECIFICATION:
The cluster components must be placed into a vertical skyscraper/building structure:

1. Vertical Elevation Tiers (Y-axis):
   ELEVATION_TIERS = {
       "client": 11.0,          # Distant Horizon (kubectl, browser, crd-watcher)
       "aggregation": 8.0,      # Penthouse / Ingress & API Aggregator
       "apiserver": 6.0,        # Executive Core: kube-apiserver horizontal array
       "vault": 4.5,            # etcd Vault: logically BEHIND (Z = -3.5) and below API server
       "supervisor": 4.5,       # Kube-scheduler (left X=-3.0) & Controller Manager (right X=+3.0), Z=0.8
       "framework": 2.0,        # Framework extension floor (Ray, Spark CRD operators)
       "worker_base": 0.0,      # First worker node floor
       "worker_pitch": -2.6,    # Spacing between successive worker floors
   }

2. Component Placement Logic in `apply_spatial_layout(nodes: List[NodeComponent], is_extended: bool = False) -> List[NodeComponent]`:
   - Detect component type and role from `n.kind`, `n.name`, `n.layer`:
     - Clients (`kubectl`, `client-browser`, `client-crd-watcher` or kind == "Client"):
       Y = ELEVATION_TIERS["client"], Z = 6.0. Spaced along X (-3.0, 0.0, 3.0). asset_type = "Client_Slab".
     - Ingress & Aggregation (`kube-aggregator`, ingress, gateway):
       Y = ELEVATION_TIERS["aggregation"], Z = 0.0. asset_type = "Skyscraper_Penthouse".
     - API Server (`kube-apiserver`):
       Y = ELEVATION_TIERS["apiserver"], Z = 0.0. Arrayed along X (e.g. cp-0 at -1.2, cp-1 at +1.2). asset_type = "ControlPlane_Cube".
     - etcd (`etcd`):
       Y = ELEVATION_TIERS["vault"], Z = -3.5 (BEHIND). Arrayed along X (-1.5, 0.0, 1.5). asset_type = "ControlPlane_Vault".
     - Supervisors (`kube-scheduler`, `kube-controller-manager`):
       Y = ELEVATION_TIERS["supervisor"], Z = 0.8 (in front). Scheduler at X = -3.0, Controller Manager at X = +3.0. asset_type = "ControlPlane_Cube".
     - Framework components (Ray, Spark, operators):
       Y = ELEVATION_TIERS["framework"], Z = 0.0. Ray head at X=-2.0, Ray workers at X=0.0, 2.0. asset_type = "Framework_Ray" or "Framework_Spark".
     - Worker Nodes & their workloads:
       Extract unique worker node hosts or partition pods across worker floors (Floor 0 at Y=0.0, Floor 1 at Y=-2.6, etc.).
       For each worker floor:
         - Generate a Floor Tray node at (0, Y_floor, 0) with asset_type = "Skyscraper_FloorTray".
         - Place a Kubelet node on that floor at (X = -1.5, Y = Y_floor + 0.35, Z = 0.0) with asset_type = "Module_Kubelet".
         - Place a Containerd node at (X = -0.7, Y = Y_floor + 0.35, Z = 0.0) with asset_type = "Module_Containerd".
         - Workload pods assigned to this worker node are placed along the tray at X = 0.2, 1.0, 1.8, Z = -0.5 to +0.5, Y = Y_floor + 0.45.
           Asset types: "Database_Postgres" for Postgres, "Cache_Redis" for Redis, "Module_PodCapsule" for standard pods.

3. Export helper `generate_skyscraper_edges(nodes: List[NodeComponent]) -> List[DataFlowEdge]`:
   - Adds the required SPEC-01 architectural data flows:
     - Distant Client -> API Aggregator / API Server (flow_type="traffic", protocol="HTTPS/443")
     - API Server -> etcd (flow_type="control_plane", protocol="gRPC/2379")
     - API Server -> API Server inter-server sync (flow_type="control_plane", protocol="HTTPS/6443")
     - Kubelet -> API Server periodic heartbeat (flow_type="control_plane", protocol="HTTPS/6443/Heartbeat")
     - Controller/Scheduler <-> API Server (flow_type="control_plane", protocol="HTTPS/6443")
     - Worker <-> Worker lateral bypass pipes for Ray/Spark (flow_type="framework_control", protocol="gRPC/10001")

Output ONLY the full Python code for `src/ingestion/layout.py`.
"""

print("[Querying Jagular for Skyscraper Spatial Layout Engine...]")
code = call_jagular(system_prompt, user_prompt, temperature=0.1, max_tokens=4096)
import re
match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
if match:
    code = match.group(1)

with open("src/ingestion/layout.py", "w") as f:
    f.write(code)

print("Saved src/ingestion/layout.py (%d bytes)" % len(code))
