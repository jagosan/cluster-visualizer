"""3D Spatial Layout Generator for Cluster Visualizer.

Assigns (X, Y, Z) coordinates to cluster components across vertical elevation
tiers (Y-axis) and horizontal spatial layouts (X-Z planes) according to the
architecture specification in docs/architecture/00-system-architecture.md.
"""

from __future__ import annotations
import math
from typing import Dict, List
from .models import NodeComponent

# Vertical elevation tiers per layer
ELEVATION_TIERS: Dict[str, float] = {
    "ingress": 4.0,
    "control-plane": 2.5,
    "framework": 1.0,
    "workload": 0.0,
    "node": -1.5,
}


def apply_spatial_layout(nodes: List[NodeComponent]) -> List[NodeComponent]:
    """Calculate and assign (X, Y, Z) spatial positions to all nodes."""
    # Partition nodes by layer
    by_layer: Dict[str, List[NodeComponent]] = {
        "ingress": [],
        "control-plane": [],
        "framework": [],
        "workload": [],
        "node": [],
    }

    for n in nodes:
        layer = n.layer if n.layer in by_layer else "workload"
        by_layer[layer].append(n)

    # 1. Node Layer (Y = -1.5): Center tray or grid
    node_items = by_layer["node"]
    for i, n in enumerate(node_items):
        n.spatial.x = (i - (len(node_items) - 1) / 2.0) * 8.0
        n.spatial.y = ELEVATION_TIERS["node"]
        n.spatial.z = 0.0

    # 2. Control Plane Layer (Y = 2.5): Compact centered circle/grid
    cp_items = by_layer["control-plane"]
    cp_count = len(cp_items)
    for i, n in enumerate(cp_items):
        n.spatial.y = ELEVATION_TIERS["control-plane"]
        if cp_count == 1:
            n.spatial.x = 0.0
            n.spatial.z = 0.0
        else:
            angle = (2.0 * math.pi * i) / cp_count
            radius = 2.8
            n.spatial.x = round(radius * math.cos(angle), 2)
            n.spatial.z = round(radius * math.sin(angle), 2)

    # 3. Framework Layer (Y = 1.0): Hexagonal / structured spread
    fw_items = by_layer["framework"]
    fw_count = len(fw_items)
    for i, n in enumerate(fw_items):
        n.spatial.y = ELEVATION_TIERS["framework"]
        if fw_count == 1:
            n.spatial.x = 0.0
            n.spatial.z = 2.0
        else:
            angle = (2.0 * math.pi * i) / fw_count
            radius = 3.8
            n.spatial.x = round(radius * math.cos(angle), 2)
            n.spatial.z = round(radius * math.sin(angle), 2)

    # 4. Workloads Layer (Y = 0.0): Grouped by workload kind (Postgres on left, Redis on right, others in center)
    wl_items = by_layer["workload"]
    pg_group = [n for n in wl_items if "Postgres" in n.kind]
    redis_group = [n for n in wl_items if "Redis" in n.kind]
    other_group = [n for n in wl_items if n not in pg_group and n not in redis_group]

    def layout_row(items: List[NodeComponent], base_x: float, base_z: float, spacing: float = 1.4):
        for idx, item in enumerate(items):
            item.spatial.y = ELEVATION_TIERS["workload"]
            item.spatial.x = round(base_x + (idx % 3) * spacing, 2)
            item.spatial.z = round(base_z + (idx // 3) * spacing, 2)

    layout_row(pg_group, base_x=-4.5, base_z=-1.5)
    layout_row(redis_group, base_x=2.5, base_z=-1.5)
    layout_row(other_group, base_x=-1.0, base_z=3.0)

    # 5. Ingress Layer (Y = 4.0)
    ing_items = by_layer["ingress"]
    for i, n in enumerate(ing_items):
        n.spatial.y = ELEVATION_TIERS["ingress"]
        n.spatial.x = (i - (len(ing_items) - 1) / 2.0) * 3.0
        n.spatial.z = -4.0

    return nodes
