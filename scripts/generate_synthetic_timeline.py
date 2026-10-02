import os
import shutil
from pathlib import Path
from src.ingestion.models import ClusterGraph, ClusterMetadata, NodeComponent, Spatial, DataFlowEdge
from src.ingestion.timeline_models import ClusterTimeline, ClusterTimelineKeyframe, TimelineEvent


def make_node(nid, layer, kind, name, version, image, status, x, y, z, asset_type):
    return NodeComponent(
        id=nid,
        layer=layer,
        kind=kind,
        name=name,
        version=version,
        image=image,
        status=status,
        spatial=Spatial(x=x, y=y, z=z, asset_type=asset_type)
    )


def generate_synthetic_timeline():
    # Base common nodes
    kube_apiserver = make_node(
        nid="control-plane/default/kube-apiserver",
        layer="control-plane",
        kind="APIServer",
        name="kube-apiserver",
        version="v1.28.0",
        image="k8s.gcr.io/kube-apiserver:v1.28.0",
        status="Healthy",
        x=0,
        y=2.5,
        z=-2,
        asset_type="Cuboid_APIServer"
    )

    etcd_0 = make_node(
        nid="control-plane/default/etcd-0",
        layer="control-plane",
        kind="etcd",
        name="etcd-0",
        version="v3.5.9",
        image="quay.io/coreos/etcd:v3.5.9",
        status="Healthy",
        x=0,
        y=1.5,
        z=-3,
        asset_type="Cuboid_etcd"
    )

    worker_1 = make_node(
        nid="node/default/worker-1",
        layer="node",
        kind="WorkerNode",
        name="worker-1",
        version="v1.28.0",
        image="k8s.gcr.io/kubelet:v1.28.0",
        status="Healthy",
        x=-3,
        y=0.5,
        z=0,
        asset_type="LayerTray_WorkerDeck"
    )

    worker_2 = make_node(
        nid="node/default/worker-2",
        layer="node",
        kind="WorkerNode",
        name="worker-2",
        version="v1.28.0",
        image="k8s.gcr.io/kubelet:v1.28.0",
        status="Healthy",
        x=3,
        y=0.5,
        z=0,
        asset_type="LayerTray_WorkerDeck"
    )

    redis_cache = make_node(
        nid="workload/default/redis-cache",
        layer="workload",
        kind="Cache",
        name="redis-cache",
        version="v7.0",
        image="redis:7.0",
        status="Healthy",
        x=4,
        y=0.5,
        z=0,
        asset_type="Cache_Redis"
    )

    common_nodes = [kube_apiserver, etcd_0, worker_1, worker_2, redis_cache]

    keyframes = []

    # Keyframe 0 (t=0s, snapshot_index=0)
    postgres_primary_kf0 = make_node(
        nid="workload/default/postgres-primary",
        layer="workload",
        kind="Database",
        name="postgres-primary",
        version="v15.2",
        image="postgres:15.2",
        status="Healthy",
        x=-2,
        y=0.5,
        z=0,
        asset_type="Database_Postgres"
    )
    nodes_kf0 = common_nodes + [postgres_primary_kf0]
    events_kf0 = [
        TimelineEvent(
            timestamp="2026-10-02T14:00:00Z",
            event_type="custom",
            summary="Baseline healthy cluster state initialized",
            affected_node_ids=[]
        )
    ]
    kf0 = ClusterTimelineKeyframe(
        snapshot_index=0,
        time_offset_seconds=0.0,
        nodes=nodes_kf0,
        edges=[],
        events=events_kf0
    )
    keyframes.append(kf0)

    # Keyframe 1 (t=15s, snapshot_index=1)
    postgres_primary_kf1 = make_node(
        nid="workload/default/postgres-primary",
        layer="workload",
        kind="Database",
        name="postgres-primary",
        version="v15.2",
        image="postgres:15.2",
        status="Healthy",
        x=-2,
        y=0.5,
        z=0,
        asset_type="Database_Postgres"
    )
    postgres_canary_kf1 = make_node(
        nid="workload/default/postgres-primary-canary",
        layer="workload",
        kind="Database",
        name="postgres-primary-canary",
        version="v16.1",
        image="postgres:16.1",
        status="Pending",
        x=2,
        y=0.5,
        z=0,
        asset_type="Database_Postgres"
    )
    nodes_kf1 = common_nodes + [postgres_primary_kf1, postgres_canary_kf1]
    events_kf1 = [
        TimelineEvent(
            timestamp="2026-10-02T14:00:15Z",
            event_type="pod_scheduled",
            summary="Canary pod postgres-primary-canary scheduled on worker-2",
            affected_node_ids=["workload/default/postgres-primary-canary"]
        )
    ]
    kf1 = ClusterTimelineKeyframe(
        snapshot_index=1,
        time_offset_seconds=15.0,
        nodes=nodes_kf1,
        edges=[],
        events=events_kf1
    )
    keyframes.append(kf1)

    # Keyframe 2 (t=30s, snapshot_index=2)
    postgres_primary_kf2 = make_node(
        nid="workload/default/postgres-primary",
        layer="workload",
        kind="Database",
        name="postgres-primary",
        version="v15.2",
        image="postgres:15.2",
        status="Terminating",
        x=-2,
        y=0.5,
        z=0,
        asset_type="Database_Postgres"
    )
    postgres_canary_kf2 = make_node(
        nid="workload/default/postgres-primary-canary",
        layer="workload",
        kind="Database",
        name="postgres-primary-canary",
        version="v16.1",
        image="postgres:16.1",
        status="Healthy",
        x=2,
        y=0.5,
        z=0,
        asset_type="Database_Postgres"
    )
    nodes_kf2 = common_nodes + [postgres_primary_kf2, postgres_canary_kf2]
    events_kf2 = [
        TimelineEvent(
            timestamp="2026-10-02T14:00:30Z",
            event_type="image_updated",
            summary="Canary validated; shifting traffic to postgres:16.1",
            affected_node_ids=["workload/default/postgres-primary-canary"]
        )
    ]
    kf2 = ClusterTimelineKeyframe(
        snapshot_index=2,
        time_offset_seconds=30.0,
        nodes=nodes_kf2,
        edges=[],
        events=events_kf2
    )
    keyframes.append(kf2)

    # Keyframe 3 (t=45s, snapshot_index=3)
    # Old postgres evicted! postgres-primary is promoted canary
    postgres_primary_kf3 = make_node(
        nid="workload/default/postgres-primary",
        layer="workload",
        kind="Database",
        name="postgres-primary",
        version="v16.1",
        image="postgres:16.1",
        status="Healthy",
        x=-2,
        y=0.5,
        z=0,
        asset_type="Database_Postgres"
    )
    nodes_kf3 = common_nodes + [postgres_primary_kf3]
    events_kf3 = [
        TimelineEvent(
            timestamp="2026-10-02T14:00:45Z",
            event_type="pod_evicted",
            summary="Old postgres-primary pod evicted from worker-1",
            affected_node_ids=["workload/default/postgres-primary"]
        )
    ]
    kf3 = ClusterTimelineKeyframe(
        snapshot_index=3,
        time_offset_seconds=45.0,
        nodes=nodes_kf3,
        edges=[],
        events=events_kf3
    )
    keyframes.append(kf3)

    # Keyframe 4 (t=60s, snapshot_index=4)
    postgres_primary_kf4 = make_node(
        nid="workload/default/postgres-primary",
        layer="workload",
        kind="Database",
        name="postgres-primary",
        version="v16.1",
        image="postgres:16.1",
        status="Healthy",
        x=-2,
        y=0.5,
        z=0,
        asset_type="Database_Postgres"
    )
    frontend_web_scale = make_node(
        nid="workload/default/frontend-web-scale",
        layer="workload",
        kind="DaemonSet",
        name="frontend-web-scale",
        version="v1.25",
        image="nginx:1.25",
        status="Healthy",
        x=6,
        y=0.5,
        z=0,
        asset_type="Cuboid_DaemonSet"
    )
    nodes_kf4 = common_nodes + [postgres_primary_kf4, frontend_web_scale]
    events_kf4 = [
        TimelineEvent(
            timestamp="2026-10-02T14:01:00Z",
            event_type="node_scaled",
            summary="Horizontal autoscaler deployed replica frontend-web-scale",
            affected_node_ids=["workload/default/frontend-web-scale"]
        )
    ]
    kf4 = ClusterTimelineKeyframe(
        snapshot_index=4,
        time_offset_seconds=60.0,
        nodes=nodes_kf4,
        edges=[],
        events=events_kf4
    )
    keyframes.append(kf4)

    timeline = ClusterTimeline(
        cluster_name="cluster-alpha",
        start_time="2026-10-02T14:00:00Z",
        end_time="2026-10-02T14:01:00Z",
        duration_seconds=60.0,
        keyframes=keyframes
    )

    # Save to public/data/timelines/synthetic_rollout.json
    out_path = Path("public/data/timelines/synthetic_rollout.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    timeline.to_json_file(out_path)

    # If dist/data/timelines/ exists, copy there too
    dist_dir = Path("dist/data/timelines")
    if dist_dir.exists():
        dist_out_path = dist_dir / "synthetic_rollout.json"
        shutil.copy2(out_path, dist_out_path)

    print(f"Generated synthetic timeline with {len(keyframes)} keyframes.")
    print(f"Saved to: {out_path.resolve()}")


if __name__ == "__main__":
    generate_synthetic_timeline()
