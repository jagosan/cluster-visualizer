"""Framework and workload detection engine for Cluster Visualizer.

Specialized detectors for Ray, Apache Spark, PostgreSQL (primary/replica replication),
and Redis clusters. Enriches NodeComponent instances with custom 3D asset types
and adds data flow / control edges to the ClusterGraph.
"""

from __future__ import annotations
from typing import List, Tuple
from .models import DataFlowEdge, NodeComponent


def enrich_framework_components(
    nodes: List[NodeComponent],
    edges: List[DataFlowEdge]
) -> Tuple[List[NodeComponent], List[DataFlowEdge]]:
    """Detect frameworks and stateful patterns, update asset types, and inject edges."""
    enriched_nodes: List[NodeComponent] = []
    ray_heads: List[NodeComponent] = []
    ray_workers: List[NodeComponent] = []
    spark_drivers: List[NodeComponent] = []
    spark_executors: List[NodeComponent] = []
    pg_primaries: List[NodeComponent] = []
    pg_replicas: List[NodeComponent] = []

    for node in nodes:
        labels = node.raw_labels
        name = node.name.lower()
        image = (node.image or "").lower()

        # Ray Detection
        is_ray = "ray" in name or "rayproject/ray" in image or labels.get("app.kubernetes.io/name") == "ray"
        if is_ray:
            node.layer = "framework"
            node.spatial.asset_type = "Framework_Ray"
            if labels.get("ray.io/node-type") == "head" or "head" in name:
                node.kind = "RayHead"
                ray_heads.append(node)
            else:
                node.kind = "RayWorker"
                ray_workers.append(node)
            enriched_nodes.append(node)
            continue

        # Spark Detection
        is_spark = "spark" in name or "apache/spark" in image or labels.get("app.kubernetes.io/name") == "spark"
        if is_spark:
            node.layer = "framework"
            node.spatial.asset_type = "Framework_Spark"
            if labels.get("spark-role") == "driver" or "driver" in name:
                node.kind = "SparkDriver"
                spark_drivers.append(node)
            else:
                node.kind = "SparkExecutor"
                spark_executors.append(node)
            enriched_nodes.append(node)
            continue

        # PostgreSQL Detection
        is_pg = "postgres" in name or "postgres" in image or labels.get("app.kubernetes.io/name") == "postgresql"
        if is_pg:
            node.spatial.asset_type = "Database_Postgres"
            if labels.get("app.kubernetes.io/component") == "primary" or "primary" in name:
                node.kind = "PostgresPrimary"
                pg_primaries.append(node)
            else:
                node.kind = "PostgresReplica"
                pg_replicas.append(node)
            enriched_nodes.append(node)
            continue

        # Redis Detection
        is_redis = "redis" in name or "redis" in image or labels.get("app.kubernetes.io/name") == "redis"
        if is_redis:
            node.spatial.asset_type = "Cache_Redis"
            node.kind = "RedisNode"
            enriched_nodes.append(node)
            continue

        # Control Plane & Node asset assignment
        if node.layer == "control-plane":
            node.spatial.asset_type = "ControlPlane_Cube"
        elif node.layer == "node":
            node.spatial.asset_type = "NodeTray"
        else:
            node.spatial.asset_type = "Pod_Cylinder"

        enriched_nodes.append(node)

    # Inject Framework & Stateful Data Flow Edges
    new_edges = list(edges)

    # Ray head <-> workers (framework_control, bidirectional)
    for head in ray_heads:
        for worker in ray_workers:
            new_edges.append(DataFlowEdge(
                source=head.id,
                target=worker.id,
                flow_type="framework_control",
                protocol="gRPC/10001",
                direction="bidirectional",
                animated=True,
                volume_label="Raylet Task Stream"
            ))

    # Spark driver <-> executors (framework_control, bidirectional)
    for driver in spark_drivers:
        for executor in spark_executors:
            new_edges.append(DataFlowEdge(
                source=driver.id,
                target=executor.id,
                flow_type="framework_control",
                protocol="Spark/7077",
                direction="bidirectional",
                animated=True,
                volume_label="Shuffle / Task Scheduling"
            ))

    # PostgreSQL primary -> replicas (data_replication, unidirectional)
    for primary in pg_primaries:
        for replica in pg_replicas:
            new_edges.append(DataFlowEdge(
                source=primary.id,
                target=replica.id,
                flow_type="data_replication",
                protocol="WAL/5432",
                direction="unidirectional",
                animated=True,
                volume_label="Async Streaming Replication"
            ))

    return enriched_nodes, new_edges
