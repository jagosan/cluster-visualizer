"""Unit tests for SPEC-08 subterranean models and layout.

Covers:
1. CloudProvider / ManagedServiceCategory enums and
   RemoteServiceResource / MachineShape / ClusterGraph (de)serialization.
2. calculate_chassis_dimensions formulas and clamping.
3. ELEVATION_TIERS subterranean constants.
4. apply_subterranean_layout positioning logic.
"""

import json
import math
import unittest

from src.ingestion.models import (
    CloudProvider,
    ManagedServiceCategory,
    RemoteServiceResource,
    MachineShape,
    ClusterGraph,
    ClusterMetadata,
)
from src.ingestion.layout import (
    ELEVATION_TIERS,
    KRO_MANIFOLD_ANCHOR,
    COMPUTE_CHASSIS_SPACING_X,
    VAULT_GRID_COLS,
    VAULT_SPACING_X,
    VAULT_SPACING_Z,
    BEDROCK_SPACING_X,
    calculate_chassis_dimensions,
    apply_subterranean_layout,
)


def _vault(vid: str, category: ManagedServiceCategory = ManagedServiceCategory.OBJECT_STORAGE,
           provider: CloudProvider = CloudProvider.GCP) -> RemoteServiceResource:
    return RemoteServiceResource(
        id=vid,
        provider=provider,
        category=category,
        cr_group="storage.cnrm.cloud.google.com",
        cr_kind="StorageBucket",
        name=vid,
        display_name=vid.upper(),
    )


# ---------------------------------------------------------------------------
# 1. Models: enums and (de)serialization
# ---------------------------------------------------------------------------

class TestEnums(unittest.TestCase):

    def test_cloud_provider_values(self):
        self.assertEqual(CloudProvider.GCP.value, "gcp")
        self.assertEqual(CloudProvider.AWS.value, "aws")
        self.assertEqual(CloudProvider.AZURE.value, "azure")
        self.assertEqual(CloudProvider.GENERIC.value, "generic")

    def test_cloud_provider_is_str_enum(self):
        self.assertIsInstance(CloudProvider.GCP, str)
        self.assertEqual(CloudProvider.AWS, "aws")
        self.assertEqual(CloudProvider("azure"), CloudProvider.AZURE)

    def test_managed_service_category_values(self):
        expected = {
            "database_relational", "database_nosql", "object_storage",
            "messaging_eventing", "cache_in_memory", "security_secret",
            "networking_gateway",
        }
        self.assertEqual({c.value for c in ManagedServiceCategory}, expected)
        self.assertIs(
            ManagedServiceCategory("cache_in_memory"),
            ManagedServiceCategory.CACHE_IN_MEMORY,
        )


class TestRemoteServiceResource(unittest.TestCase):

    def test_defaults(self):
        r = _vault("bucket-a")
        self.assertEqual(r.provider, CloudProvider.GCP)
        self.assertEqual(r.namespace, "default")
        self.assertEqual(r.status_phase, "Ready")
        self.assertEqual(r.managed_by, "kcc")
        self.assertIsNone(r.endpoint)
        self.assertIsNone(r.kro_parent_id)
        self.assertIsNone(r.spatial)

    def test_serialization_roundtrip(self):
        r = RemoteServiceResource(
            id="pg-1",
            provider=CloudProvider.AWS,
            category=ManagedServiceCategory.DATABASE_RELATIONAL,
            cr_group="rds.services.k8s.aws",
            cr_kind="DBInstance",
            name="pg-1",
            namespace="infra",
            display_name="Aurora PG",
            status_phase="Reconciling",
            endpoint="pg-1.abc123.us-east-1.rds.amazonaws.com",
            vpc_network="vpc-42",
            managed_by="ack",
            kro_parent_id="composite-db",
            spatial={"x": 1.5, "y": -6.5, "z": -3.0},
        )
        data = json.loads(r.model_dump_json())
        self.assertEqual(data["provider"], "aws")
        self.assertEqual(data["category"], "database_relational")
        self.assertEqual(data["spatial"], {"x": 1.5, "y": -6.5, "z": -3.0})

        back = RemoteServiceResource.model_validate(data)
        self.assertEqual(back, r)
        self.assertIsInstance(back.provider, CloudProvider)
        self.assertIsInstance(back.category, ManagedServiceCategory)

    def test_invalid_category_rejected(self):
        with self.assertRaises(Exception):
            RemoteServiceResource(
                id="bad", category="not_a_category", cr_group="g", cr_kind="K",
                name="bad", display_name="Bad",
            )


class TestMachineShape(unittest.TestCase):

    def test_defaults(self):
        m = MachineShape(node_name="node-1", instance_type="e2-standard-4")
        self.assertEqual(m.provider, CloudProvider.GCP)
        self.assertEqual(m.vcpus, 4)
        self.assertAlmostEqual(m.memory_gib, 16.0)
        self.assertEqual(m.capacity_type, "on-demand")
        self.assertEqual(m.zone, "us-central1-a")
        self.assertEqual(m.accelerator_count, 0)
        self.assertIsNone(m.accelerator_type)
        self.assertAlmostEqual(m.chassis_width, 3.9)
        self.assertAlmostEqual(m.chassis_depth, 3.6)

    def test_serialization_roundtrip(self):
        m = MachineShape(
            node_name="ip-10-0-3-7",
            provider=CloudProvider.AWS,
            instance_type="m6g.2xlarge",
            compute_class="karpenter-general",
            vcpus=8,
            memory_gib=32.0,
            capacity_type="spot",
            zone="us-east-1b",
            accelerator_type="nvidia-l4",
            accelerator_count=2,
            chassis_width=4.19,
            chassis_depth=4.1,
        )
        data = json.loads(m.model_dump_json())
        self.assertEqual(data["capacity_type"], "spot")
        self.assertEqual(data["provider"], "aws")
        back = MachineShape.model_validate(data)
        self.assertEqual(back, m)

    def test_invalid_capacity_type_rejected(self):
        with self.assertRaises(Exception):
            MachineShape(node_name="n", instance_type="t", capacity_type="preemptible-lite")


class TestClusterGraph(unittest.TestCase):

    def _graph(self):
        return ClusterGraph(
            metadata=ClusterMetadata(
                cluster_name="subterra-demo",
                kubernetes_version="v1.30.2",
                timestamp="2026-10-03T00:00:00Z",
                node_count=3,
                pod_count=17,
            ),
            subterranean_resources=[_vault("v1"), _vault("v2")],
            machine_shapes=[
                MachineShape(node_name="n1", instance_type="e2-standard-4"),
                MachineShape(node_name="n2", instance_type="n2-highmem-8", vcpus=8, memory_gib=64.0),
            ],
        )

    def test_schema_url_default_and_alias(self):
        g = self._graph()
        self.assertEqual(
            g.schema_url,
            "https://cluster-vis.jagosan.com/schemas/cluster-graph-v1.json",
        )
        dumped = g.model_dump(by_alias=True)
        self.assertIn("$schema", dumped)
        self.assertNotIn("schema_url", dumped)

    def test_serialization_roundtrip_with_subterranean(self):
        g = self._graph()
        data = json.loads(g.model_dump_json(by_alias=True))
        self.assertEqual(len(data["subterranean_resources"]), 2)
        self.assertEqual(len(data["machine_shapes"]), 2)
        self.assertEqual(data["metadata"]["cluster_name"], "subterra-demo")

        back = ClusterGraph.model_validate(data)
        self.assertEqual(back, g)
        self.assertIsInstance(back.machine_shapes[0], MachineShape)
        self.assertIsInstance(
            back.subterranean_resources[0].category, ManagedServiceCategory
        )

    def test_populate_by_name(self):
        # Field name (not just alias) must be accepted on input.
        g = ClusterGraph(
            schema_url="https://example.com/schema.json",
            metadata=ClusterMetadata(
                cluster_name="c", kubernetes_version="v1", timestamp="t",
            ),
        )
        self.assertEqual(g.schema_url, "https://example.com/schema.json")

    def test_empty_list_defaults(self):
        g = ClusterGraph(
            metadata=ClusterMetadata(
                cluster_name="c", kubernetes_version="v1", timestamp="t",
            ),
        )
        self.assertEqual(g.subterranean_resources, [])
        self.assertEqual(g.machine_shapes, [])
        self.assertIsNone(g.diff_summary)


# ---------------------------------------------------------------------------
# 2. calculate_chassis_dimensions
# ---------------------------------------------------------------------------

class TestChassisDimensions(unittest.TestCase):

    def _expected(self, vcpus, memory_gib):
        w = max(3.2, min(8.0, 3.2 + 0.35 * math.sqrt(vcpus)))
        d = max(2.4, min(7.5, 2.4 + 0.30 * math.sqrt(memory_gib)))
        return (round(w, 2), 0.6, round(d, 2))

    def test_zero_resources_hits_min_bounds(self):
        self.assertEqual(calculate_chassis_dimensions(0, 0.0), (3.2, 0.6, 2.4))

    def test_formula_mid_range(self):
        # 4 vCPU, 16 GiB -> w = 3.2 + 0.35*2 = 3.9 ; d = 2.4 + 0.30*4 = 3.6
        self.assertEqual(calculate_chassis_dimensions(4, 16.0), (3.9, 0.6, 3.6))
        # 9 vCPU, 25 GiB -> w = 3.2 + 1.05 = 4.25 ; d = 2.4 + 1.5 = 3.9
        self.assertEqual(calculate_chassis_dimensions(9, 25.0), (4.25, 0.6, 3.9))

    def test_clamped_at_max_bounds(self):
        w, h, d = calculate_chassis_dimensions(10_000, 10_000.0)
        self.assertAlmostEqual(w, 8.0, places=2)
        self.assertAlmostEqual(d, 7.5, places=2)
        self.assertEqual(h, 0.6)

    def test_negative_inputs_do_not_crash_and_clamp_to_min(self):
        self.assertEqual(calculate_chassis_dimensions(-8, -64.0), (3.2, 0.6, 2.4))

    def test_height_always_0_6(self):
        for v, mem in [(0, 0.0), (1, 1.0), (64, 512.0), (9999, 99999.0)]:
            self.assertEqual(calculate_chassis_dimensions(v, mem)[1], 0.6)

    def test_matches_reference_formula_over_grid(self):
        for v in (0, 1, 2, 8, 16, 32, 96, 192, 4096):
            for mem in (0.0, 0.5, 4.0, 32.0, 128.0, 4096.0):
                self.assertEqual(
                    calculate_chassis_dimensions(v, mem), self._expected(v, mem),
                    msg=f"mismatch at vcpus={v} memory_gib={mem}",
                )


# ---------------------------------------------------------------------------
# 3. ELEVATION_TIERS subterranean constants
# ---------------------------------------------------------------------------

class TestElevationTiers(unittest.TestCase):

    def test_subterranean_values(self):
        self.assertEqual(ELEVATION_TIERS["surface_datum"], 0.0)
        self.assertEqual(ELEVATION_TIERS["compute_chassis"], -2.5)
        self.assertEqual(ELEVATION_TIERS["kro_manifold"], -4.8)
        self.assertEqual(ELEVATION_TIERS["cloud_vault"], -6.5)
        self.assertEqual(ELEVATION_TIERS["bedrock_egress"], -10.5)

    def test_strata_are_strictly_ordered_below_surface(self):
        strata = ["surface_datum", "compute_chassis", "kro_manifold",
                  "cloud_vault", "bedrock_egress"]
        ys = [ELEVATION_TIERS[k] for k in strata]
        for a, b in zip(ys, ys[1:]):
            self.assertGreater(a, b)
        self.assertGreaterEqual(ys[0], 0.0)
        self.assertLess(ys[-1], 0.0)

    def test_kro_anchor_on_manifold_tier(self):
        self.assertEqual(KRO_MANIFOLD_ANCHOR, (0.0, -4.8, 0.0))
        self.assertEqual(KRO_MANIFOLD_ANCHOR[1], ELEVATION_TIERS["kro_manifold"])


# ---------------------------------------------------------------------------
# 4. apply_subterranean_layout
# ---------------------------------------------------------------------------

class TestApplySubterraneanLayout(unittest.TestCase):

    def test_empty_inputs_returns_only_kro_anchor(self):
        positions = apply_subterranean_layout([], [])
        self.assertEqual(positions, {"kro_manifold_hub": KRO_MANIFOLD_ANCHOR})

    def test_chassis_row_positioning_and_mutation(self):
        m1 = MachineShape(node_name="big", instance_type="x", vcpus=100, memory_gib=100.0)
        m2 = MachineShape(node_name="small", instance_type="y", vcpus=0, memory_gib=0.0)
        positions = apply_subterranean_layout([m1, m2], [])

        # Footprints recomputed in place.
        self.assertEqual((m1.chassis_width, m1.chassis_depth),
                         calculate_chassis_dimensions(100, 100.0)[:1:2] + (calculate_chassis_dimensions(100, 100.0)[2],))
        self.assertEqual((m2.chassis_width, m2.chassis_depth), (3.2, 2.4))

        w1 = calculate_chassis_dimensions(100, 100.0)[0]
        total_span = w1 + 3.2 + COMPUTE_CHASSIS_SPACING_X
        self.assertAlmostEqual(positions["big"][0], round(-total_span / 2.0 + w1 / 2.0, 2))
        self.assertAlmostEqual(positions["small"][0],
                               round(-total_span / 2.0 + w1 + COMPUTE_CHASSIS_SPACING_X + 3.2 / 2.0, 2))
        # Both docked on B1, z = 0
        self.assertEqual(positions["big"][1], ELEVATION_TIERS["compute_chassis"])
        self.assertEqual(positions["small"][1], ELEVATION_TIERS["compute_chassis"])
        self.assertEqual(positions["big"][2], 0.0)
        self.assertEqual(positions["small"][2], 0.0)
        # Left-to-right ordering preserved.
        self.assertLess(positions["big"][0], positions["small"][0])

    def test_single_chassis_centered_on_origin(self):
        m = MachineShape(node_name="solo", instance_type="x", vcpus=4, memory_gib=16.0)
        positions = apply_subterranean_layout([m], [])
        self.assertAlmostEqual(positions["solo"][0], 0.0, places=2)

    def test_vault_grid_positioning(self):
        vaults = [_vault(f"v{i}") for i in range(4)]
        apply_subterranean_layout([], vaults)

        # All non-gateway vaults sit on cloud_vault level.
        for v in vaults:
            self.assertEqual(v.spatial["y"], ELEVATION_TIERS["cloud_vault"])

        # 4 vaults, 3 cols -> rows z = -1.5 (row 0), +1.5 (row 1),
        # since (row - 0.5) * 3.0 gives -1.5 for row 0 and +1.5 for row 1.
        self.assertEqual(vaults[0].spatial, {"x": -3.0, "y": -6.5, "z": -1.5})
        self.assertEqual(vaults[1].spatial, {"x": 0.0, "y": -6.5, "z": -1.5})
        self.assertEqual(vaults[2].spatial, {"x": 3.0, "y": -6.5, "z": -1.5})
        # Second row has 1 col -> centered on X.
        self.assertEqual(vaults[3].spatial, {"x": 0.0, "y": -6.5, "z": 1.5})

    def test_gateway_vaults_go_to_bedrock_row(self):
        nat = _vault("nat-gw", category=ManagedServiceCategory.NETWORKING_GATEWAY)
        gw2 = _vault("gw2", category=ManagedServiceCategory.NETWORKING_GATEWAY)
        db = _vault("db", category=ManagedServiceCategory.DATABASE_RELATIONAL)
        positions = apply_subterranean_layout([], [nat, gw2, db])

        self.assertEqual(nat.spatial["y"], ELEVATION_TIERS["bedrock_egress"])
        self.assertEqual(gw2.spatial["y"], ELEVATION_TIERS["bedrock_egress"])
        self.assertEqual(db.spatial["y"], ELEVATION_TIERS["cloud_vault"])
        # Bedrock row centered on X, spacing BEDROCK_SPACING_X, z = 0.
        self.assertAlmostEqual(nat.spatial["x"], -BEDROCK_SPACING_X / 2.0)
        self.assertAlmostEqual(gw2.spatial["x"], BEDROCK_SPACING_X / 2.0)
        self.assertEqual(nat.spatial["z"], 0.0)
        self.assertEqual(positions["nat-gw"], (nat.spatial["x"], -10.5, 0.0))

    def test_returned_positions_cover_every_object(self):
        shapes = [MachineShape(node_name=f"n{i}", instance_type="x") for i in range(3)]
        vaults = [_vault(f"v{i}") for i in range(5)] + [
            _vault("egress", category=ManagedServiceCategory.NETWORKING_GATEWAY)
        ]
        positions = apply_subterranean_layout(shapes, vaults)

        keys = {"kro_manifold_hub"} | {m.node_name for m in shapes} | {r.id for r in vaults}
        self.assertEqual(set(positions), keys)
        # Returned tuples agree with mutated spatial on vaults.
        for r in vaults:
            self.assertEqual(positions[r.id], (r.spatial["x"], r.spatial["y"], r.spatial["z"]))
        # Every subterranean object is strictly below the surface datum.
        for k, pos in positions.items():
            self.assertLessEqual(pos[1], 0.0, msg=f"{k} above surface")


if __name__ == "__main__":
    unittest.main()
