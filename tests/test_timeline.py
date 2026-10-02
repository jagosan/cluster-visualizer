"""
Unit tests for Time-Travel Cluster Topology Playback & Historical Scrubber Engine.
SPEC-05 / TASK-CV-606
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from src.ingestion.models import ClusterGraph, ClusterMetadata, NodeComponent, Spatial
from src.ingestion.recorder import (
    compute_topology_hash,
    detect_frame_events,
    parse_duration,
    record_timeline,
)
from src.ingestion.timeline_models import (
    ClusterTimeline,
    ClusterTimelineKeyframe,
    TimelineEvent,
)


class TestTimelineEngine(unittest.TestCase):
    """Test suite for SPEC-05 timeline contracts, recorder, and testbeds."""

    def setUp(self):
        self.base_dir = Path(__file__).parent.parent
        self.synthetic_timeline_path = self.base_dir / "public" / "data" / "timelines" / "synthetic_rollout.json"

        # Create sample base nodes
        self.node_a = NodeComponent(
            id="workload/default/postgres-0",
            layer="workload",
            kind="Database",
            name="postgres-0",
            namespace="default",
            version="v15.2",
            image="postgres:15.2",
            status="Healthy",
            spatial=Spatial(x=2.0, y=0.5, z=0.0, asset_type="Database_Postgres"),
        )
        self.node_b = NodeComponent(
            id="workload/default/redis-0",
            layer="workload",
            kind="Cache",
            name="redis-0",
            namespace="default",
            version="v7.0",
            image="redis:7.0",
            status="Healthy",
            spatial=Spatial(x=4.0, y=0.5, z=0.0, asset_type="Cache_Redis"),
        )

        self.base_graph = ClusterGraph(
            metadata=ClusterMetadata(
                cluster_name="cluster-test",
                kubernetes_version="v1.36.4",
                distribution="kind",
                timestamp="2026-10-02T14:00:00Z",
                node_count=2,
                pod_count=2,
            ),
            nodes=[self.node_a, self.node_b],
            edges=[],
        )

    def test_timeline_models_serialization(self):
        """Verify TimelineEvent, Keyframe, and ClusterTimeline Pydantic v2 serialization."""
        event = TimelineEvent(
            timestamp="2026-10-02T14:00:15Z",
            event_type="pod_scheduled",
            summary="Scheduled canary pod",
            affected_node_ids=["workload/default/canary-0"],
            metadata={"canary": True},
        )
        keyframe = ClusterTimelineKeyframe(
            timestamp="2026-10-02T14:00:15Z",
            snapshot_index=1,
            time_offset_seconds=15.0,
            graph=self.base_graph,
            events=[event],
        )
        timeline = ClusterTimeline(
            cluster_name="cluster-test",
            start_time="2026-10-02T14:00:00Z",
            end_time="2026-10-02T14:00:15Z",
            duration_seconds=15.0,
            keyframes=[keyframe],
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            timeline.to_json_file(tmp_path)
            loaded = ClusterTimeline.from_json_file(tmp_path)

            self.assertEqual(loaded.cluster_name, "cluster-test")
            self.assertEqual(len(loaded.keyframes), 1)
            self.assertEqual(loaded.keyframes[0].snapshot_index, 1)
            self.assertEqual(len(loaded.keyframes[0].events), 1)
            self.assertEqual(loaded.keyframes[0].events[0].event_type, "pod_scheduled")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_compute_topology_hash(self):
        """Verify deterministic hashing and sensitivity to mutations."""
        hash_1 = compute_topology_hash(self.base_graph)

        # Inverted order should produce identical hash due to deterministic sorting
        inverted_graph = ClusterGraph(
            metadata=self.base_graph.metadata,
            nodes=[self.node_b, self.node_a],
            edges=[],
        )
        hash_inverted = compute_topology_hash(inverted_graph)
        self.assertEqual(hash_1, hash_inverted, "Topology hash must be order-invariant")

        # Mutate an image
        mutated_node = self.node_a.model_copy(update={"image": "postgres:16.1"})
        mutated_graph = ClusterGraph(
            metadata=self.base_graph.metadata,
            nodes=[mutated_node, self.node_b],
            edges=[],
        )
        hash_mutated = compute_topology_hash(mutated_graph)
        self.assertNotEqual(hash_1, hash_mutated, "Hash must change when container image shifts")

    def test_detect_frame_events(self):
        """Verify delta classification for additions, evictions, image updates, and drift."""
        node_c = NodeComponent(
            id="workload/default/canary-0",
            layer="workload",
            kind="Database",
            name="canary-0",
            namespace="default",
            version="v16.1",
            image="postgres:16.1",
            status="Healthy",
        )

        # 1. Pod Scheduled
        graph_with_c = ClusterGraph(
            metadata=self.base_graph.metadata,
            nodes=[self.node_a, self.node_b, node_c],
            edges=[],
        )
        events_add = detect_frame_events(self.base_graph, graph_with_c, "2026-10-02T14:00:15Z")
        self.assertEqual(len(events_add), 1)
        self.assertEqual(events_add[0].event_type, "pod_scheduled")
        self.assertIn("canary-0", events_add[0].affected_node_ids[0])

        # 2. Pod Evicted
        events_evict = detect_frame_events(graph_with_c, self.base_graph, "2026-10-02T14:00:30Z")
        self.assertEqual(len(events_evict), 1)
        self.assertEqual(events_evict[0].event_type, "pod_evicted")

        # 3. Image Updated
        mutated_node = self.node_a.model_copy(update={"image": "postgres:16.1"})
        graph_img = ClusterGraph(
            metadata=self.base_graph.metadata,
            nodes=[mutated_node, self.node_b],
            edges=[],
        )
        events_img = detect_frame_events(self.base_graph, graph_img, "2026-10-02T14:00:45Z")
        self.assertEqual(len(events_img), 1)
        self.assertEqual(events_img[0].event_type, "image_updated")

        # 4. Config Drift (status changed)
        drifted_node = self.node_a.model_copy(update={"status": "Terminating"})
        graph_drift = ClusterGraph(
            metadata=self.base_graph.metadata,
            nodes=[drifted_node, self.node_b],
            edges=[],
        )
        events_drift = detect_frame_events(self.base_graph, graph_drift, "2026-10-02T14:01:00Z")
        self.assertEqual(len(events_drift), 1)
        self.assertEqual(events_drift[0].event_type, "config_drift")

    def test_parse_duration(self):
        """Verify parsing of human duration strings."""
        self.assertEqual(parse_duration("30s"), 30.0)
        self.assertEqual(parse_duration("5m"), 300.0)
        self.assertEqual(parse_duration("1h"), 3600.0)
        self.assertEqual(parse_duration("15"), 15.0)

    def test_synthetic_timeline_artifact_valid(self):
        """Verify the synthetic rollout testbed artifact adheres to schema and contains 5 frames."""
        self.assertTrue(
            self.synthetic_timeline_path.exists(),
            f"Expected {self.synthetic_timeline_path} to exist",
        )
        timeline = ClusterTimeline.from_json_file(self.synthetic_timeline_path)
        self.assertEqual(timeline.cluster_name, "cluster-alpha")
        self.assertEqual(len(timeline.keyframes), 5)
        self.assertEqual(timeline.duration_seconds, 60.0)

        # Check event sequence
        event_types = [kf.events[0].event_type for kf in timeline.keyframes if kf.events]
        self.assertIn("pod_scheduled", event_types)
        self.assertIn("image_updated", event_types)
        self.assertIn("pod_evicted", event_types)
        self.assertIn("node_scaled", event_types)

    def test_record_timeline_mock_mode(self):
        """Verify recorder CLI runs and outputs valid ClusterTimeline in mock mode."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            timeline = record_timeline(
                interval_seconds=1.0,
                duration_seconds=3.0,
                output_path=tmp_path,
                mock=True,
            )
            self.assertIsInstance(timeline, ClusterTimeline)
            self.assertGreaterEqual(len(timeline.keyframes), 1)
            self.assertTrue(os.path.exists(tmp_path))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
