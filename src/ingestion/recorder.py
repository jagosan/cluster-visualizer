import argparse
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.ingestion.models import ClusterGraph, ClusterMetadata, NodeComponent, Spatial
from src.ingestion.timeline_models import (
    ClusterTimeline,
    ClusterTimelineKeyframe,
    TimelineEvent,
    TimelineEventType,
)
from src.ingestion.exporter import export_cluster, generate_mock_cluster_graph

logger = logging.getLogger(__name__)


def compute_topology_hash(graph: ClusterGraph) -> str:
    """
    Creates sha256 hex digest of sorted tuple representation of nodes.
    """
    node_tuples = [
        (n.namespace, n.kind, n.name, n.version, n.image, n.status)
        for n in graph.nodes
    ]
    # Sort to ensure deterministic hashing regardless of node order
    sorted_tuples = sorted(node_tuples)
    # Create a stable string representation
    hash_input = json.dumps(sorted_tuples, sort_keys=True).encode("utf-8")
    return hashlib.sha256(hash_input).hexdigest()


def detect_frame_events(
    prev_graph: ClusterGraph, curr_graph: ClusterGraph, timestamp: str
) -> List[TimelineEvent]:
    """
    Compares nodes between prev_graph and curr_graph and detects events.
    """
    events: List[TimelineEvent] = []

    # Build maps for quick lookup
    prev_map: Dict[str, NodeComponent] = {}
    for n in prev_graph.nodes:
        key = f"{n.namespace}/{n.kind}/{n.name}"
        prev_map[key] = n

    curr_map: Dict[str, NodeComponent] = {}
    for n in curr_graph.nodes:
        key = f"{n.namespace}/{n.kind}/{n.name}"
        curr_map[key] = n

    prev_keys = set(prev_map.keys())
    curr_keys = set(curr_map.keys())

    # Added nodes
    for key in curr_keys - prev_keys:
        node = curr_map[key]
        event = TimelineEvent(
            timestamp=timestamp,
            event_type="pod_scheduled",
            summary=f"Scheduled {node.name}",
            affected_node_ids=[node.id],
            metadata={
                "kind": node.kind,
                "namespace": node.namespace,
                "image": node.image,
            },
        )
        events.append(event)

    # Removed nodes
    for key in prev_keys - curr_keys:
        node = prev_map[key]
        event = TimelineEvent(
            timestamp=timestamp,
            event_type="pod_evicted",
            summary=f"Evicted {node.name}",
            affected_node_ids=[node.id],
            metadata={
                "kind": node.kind,
                "namespace": node.namespace,
            },
        )
        events.append(event)

    # Changed nodes
    for key in prev_keys & curr_keys:
        prev_node = prev_map[key]
        curr_node = curr_map[key]

        # Check image/version change
        if prev_node.image != curr_node.image or prev_node.version != curr_node.version:
            event = TimelineEvent(
                timestamp=timestamp,
                event_type="image_updated",
                summary=f"Updated {curr_node.name} image to {curr_node.image}",
                affected_node_ids=[curr_node.id],
                metadata={
                    "old_image": prev_node.image,
                    "new_image": curr_node.image,
                },
            )
            events.append(event)

        # Check status change
        if prev_node.status != curr_node.status:
            event = TimelineEvent(
                timestamp=timestamp,
                event_type="config_drift",
                summary=f"Status of {curr_node.name} changed to {curr_node.status}",
                affected_node_ids=[curr_node.id],
                metadata={
                    "status": curr_node.status,
                },
            )
            events.append(event)

    return events


def record_timeline(
    context: Optional[str] = None,
    interval_seconds: float = 5.0,
    duration_seconds: float = 30.0,
    output_path: str = "public/data/timelines/cluster-timeline.json",
    mock: bool = False,
    max_frames: Optional[int] = None,
) -> ClusterTimeline:
    """
    Runs sampling loop and records timeline.
    """
    start_time = datetime.now(timezone.utc)
    keyframes: List[ClusterTimelineKeyframe] = []
    prev_graph: Optional[ClusterGraph] = None
    prev_hash: Optional[str] = None
    frame_count = 0

    logger.info(
        f"Starting timeline recording: context={context}, interval={interval_seconds}s, "
        f"duration={duration_seconds}s, mock={mock}"
    )

    while True:
        current_time = datetime.now(timezone.utc)
        elapsed = (current_time - start_time).total_seconds()

        if elapsed >= duration_seconds:
            break

        if max_frames is not None and frame_count >= max_frames:
            break

        # Get current graph
        if mock:
            graph = generate_mock_cluster_graph()
            # Simulate mutations for successive frames
            if prev_graph is not None and len(graph.nodes) > 0:
                import random

                # Randomly mutate an existing node or add a new one
                if random.random() < 0.5 and len(graph.nodes) > 0:
                    # Mutate an existing node
                    idx = random.randint(0, len(graph.nodes) - 1)
                    node = graph.nodes[idx]
                    if random.random() < 0.5 and node.image:
                        # Change image
                        node.image = f"{node.image.split(':')[0]}:v{random.randint(1, 10)}"
                    else:
                        # Change status
                        statuses = ["Running", "Pending", "Pending", "Running"]
                        node.status = random.choice(statuses)
                else:
                    # Add a new simulated node
                    new_node = NodeComponent(
                        id=f"node-{frame_count}-{random.randint(1000, 9999)}",
                        layer="workload",
                        namespace="default",
                        kind="Pod",
                        name=f"simulated-pod-{frame_count}",
                        version="1.0.0",
                        image="nginx:latest",
                        status="Running",
                        spatial=Spatial(x=0.0, y=0.0, z=0.0),
                    )
                    graph.nodes.append(new_node)
        else:
            graph = export_cluster(context=context)

        timestamp = current_time.isoformat()
        current_hash = compute_topology_hash(graph)

        # Detect events if we have a previous graph
        events: List[TimelineEvent] = []
        if prev_graph is not None:
            events = detect_frame_events(prev_graph, graph, timestamp)

        # Create keyframe on first frame or hash change
        if prev_hash is None or current_hash != prev_hash:
            keyframe = ClusterTimelineKeyframe(
                timestamp=timestamp,
                snapshot_index=len(keyframes),
                graph=graph,
                events=events,
            )
            keyframes.append(keyframe)
            logger.info(
                f"Keyframe {len(keyframes)} recorded at {timestamp} with {len(events)} events"
            )

        prev_graph = graph
        prev_hash = current_hash
        frame_count += 1

        # Sleep for interval
        time.sleep(interval_seconds)

    end_time = datetime.now(timezone.utc)
    actual_duration = (end_time - start_time).total_seconds()

    timeline = ClusterTimeline(
        cluster_name=context or "cluster-alpha",
        start_time=start_time.isoformat(),
        end_time=end_time.isoformat(),
        duration_seconds=actual_duration,
        keyframes=keyframes,
    )

    # Ensure output directory exists
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Export timeline
    timeline.to_json_file(output_path)
    logger.info(f"Timeline saved to {output_path}")

    return timeline


def parse_duration(val: str) -> float:
    """
    Parses duration strings like '10s', '5m', '1h' or plain float.
    """
    val = val.strip().lower()
    if val.endswith("s"):
        return float(val[:-1])
    elif val.endswith("m"):
        return float(val[:-1]) * 60
    elif val.endswith("h"):
        return float(val[:-1]) * 3600
    else:
        return float(val)


def main():
    parser = argparse.ArgumentParser(
        description="Record cluster timeline events"
    )
    parser.add_argument(
        "--context",
        type=str,
        default=None,
        help="Kubernetes context to monitor",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default="5s",
        help="Sampling interval (e.g., 5s, 1m)",
    )
    parser.add_argument(
        "--duration",
        type=str,
        default="30s",
        help="Total recording duration (e.g., 30s, 5m, 1h)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="public/data/timelines/cluster-timeline.json",
        help="Output path for timeline JSON",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock data instead of live cluster",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    interval_seconds = parse_duration(args.interval)
    duration_seconds = parse_duration(args.duration)

    record_timeline(
        context=args.context,
        interval_seconds=interval_seconds,
        duration_seconds=duration_seconds,
        output_path=args.output,
        mock=args.mock,
    )


if __name__ == "__main__":
    main()
