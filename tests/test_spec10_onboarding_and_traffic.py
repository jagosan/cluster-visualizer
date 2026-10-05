"""Unit tests for SPEC-10 Interactive UI Cluster Onboarding, Sample Catalog
& Autoscaling Traffic Simulation Harness (TASK-CV-1106).

Covers:
1. Schema conformance of the four simulated sample catalog fixtures
   (`public/data/samples/*.json`) against the pydantic ClusterGraph models
   (src/ingestion/models.py) plus SPEC-10 §3 topology requirements:
     * sample-upstream-k8s        — 3 nodes, control plane Y=7.0 elevation,
       clustered etcd Y=5.5, CoreDNS ×2, kube-proxy DaemonSet bays, Cilium CNI.
     * sample-online-boutique     — 11 microservices + redis-cart, HPA on
       frontend (2→10 @ 65% CPU), VPA Auto morph on cartservice, mixed
       HPA+VPA on recommendationservice, SPEC-08 subterranean vaults.
     * sample-ray-kuberay         — Ray Head (GCS/dashboard), 4 CPU workers,
       2 GPU workers in NVIDIA L4 / A100 accelerator bays, Kueue Inadmissible
       PyTorch gang containment pallet in the exterior staging yard.
     * sample-compute-class-bench — GKE Scale-Up compute class lanes vs
       Karpenter NodeClaims (unprovisioned ghosts) with exterior staging-yard
       Pending pods (X < -12.0) and the static-nodepool contrast lane.
2. Mathematical formulas of the M/M/c/K queuing + autoscaling engine
   (src/scene/traffic_simulator.ts), exercised through an esbuild bridge:
     * Arrival-rate patterns: step spike, raised-cosine sine, ramp, chaos
       (deterministic, bounded).
     * Traffic intensity ρ(t) = λ(t)/(N(t)·μ) readout, Erlang-C stable-regime
       latency cross-checked against an independent lgamma reference, and the
       saturated-regime W_q latency growth L = L_base + 1/μ + W_q(t).
     * HPA desired-replica formula ceil(N·cpu/target) with min/max bounds and
       scale-down stabilization; VPA 80%-sustained-3s trigger, τ_vpa morph,
       μ-restoration, and the below-threshold negative case.
     * Comparative scheduling latency skew bands (SPEC-10 §5.3): GKE Compute
       Class τ_sched ≈ 3–6 s vs Karpenter τ_node ≈ 60–150 s and static
       nodepool 90–150 s; 10× spike absorption (≤ 60 ms, 0% err) vs staging
       saturation (> 500 ms, ~18% err, recovery after cold-VM landing).
3. Secret scrubbing guarantees in ingestion/export paths (SPEC-10 §2.1.1 /
   SPEC-07 §5): SecretScrubber env/volume/metadata stripping, exporter value
   hashing/redaction, and the fixture/token hygiene scans (no bearer JWTs,
   AWS keys, or private keys in shipped samples; tokens sessionStorage-only).
4. End-to-end execution of the TypeScript verification harnesses
   scripts/verify_spec10_engine.ts and scripts/verify_spec10_deck.ts.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from src.ingestion.exporter import scrub_sensitive_string
from src.ingestion.models import ClusterGraph
from src.operator.graph_engine import SecretScrubber

REPO = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO / "public" / "data" / "samples"
SRC_DIR = REPO / "src"
SCRIPTS_DIR = REPO / "scripts"

NODE_BIN = shutil.which("node")
ESBUILD_BIN = REPO / "node_modules" / ".bin" / "esbuild"

EPS = 1e-6

# SPEC-10 §5.3 benchmark bands -------------------------------------------------
GKE_TAU_SCHED_MIN, GKE_TAU_SCHED_MAX = 3.0, 6.0
KARPENTER_TAU_NODE_MIN, KARPENTER_TAU_NODE_MAX = 60.0, 150.0
STATIC_TAU_NODE_MIN, STATIC_TAU_NODE_MAX = 90.0, 150.0


def load_raw(name: str) -> dict:
    with open(SAMPLE_DIR / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_graph(name: str) -> ClusterGraph:
    return ClusterGraph.model_validate(load_raw(name))


def by_id(graph: ClusterGraph, node_id: str):
    for n in graph.nodes:
        if n.id == node_id:
            return n
    raise AssertionError(f"node {node_id!r} missing from fixture")


def find_one(graph: ClusterGraph, pred, what: str):
    hits = [n for n in graph.nodes if pred(n)]
    assert hits, f"no node matching {what} in {graph.metadata.cluster_name}"
    return hits


def podlike(graph: ClusterGraph):
    """Nodes counted toward metadata.pod_count (pods + control-plane pods)."""
    return [n for n in graph.nodes if n.id.startswith(("pod/", "control-plane/"))]


# ---------------------------------------------------------------------------
# 1. ClusterGraph schema conformance (all four fixtures)
# ---------------------------------------------------------------------------

SAMPLE_FIXTURES = [
    "sample-upstream-k8s.json",
    "sample-online-boutique.json",
    "sample-ray-kuberay.json",
    "sample-compute-class-bench.json",
]


class TestSampleFixtureSchema(unittest.TestCase):
    """Every catalog fixture must deserialize into the ClusterGraph v1 model."""

    def test_all_four_fixtures_present(self):
        for name in SAMPLE_FIXTURES:
            self.assertTrue((SAMPLE_DIR / name).is_file(), f"{name} missing")

    def test_pydantic_validation(self):
        for name in SAMPLE_FIXTURES:
            try:
                graph = load_graph(name)
            except ValidationError as exc:  # pragma: no cover - failure path
                self.fail(f"{name} failed ClusterGraph validation: {exc}")
            self.assertEqual(graph.schema_url,
                             "https://cluster-vis.jagosan.com/schemas/cluster-graph-v1.json")

    def test_metadata_counts_match_payload(self):
        for name in SAMPLE_FIXTURES:
            graph = load_graph(name)
            chassis = [n for n in graph.nodes if n.kind == "Node"]
            self.assertEqual(len(chassis), graph.metadata.node_count,
                             f"{name}: node_count mismatch")
            self.assertEqual(len(podlike(graph)), graph.metadata.pod_count,
                             f"{name}: pod_count mismatch")

    def test_edge_referential_integrity(self):
        for name in SAMPLE_FIXTURES:
            graph = load_graph(name)
            known = {n.id for n in graph.nodes}
            known |= {r.id for r in graph.subterranean_resources}
            for e in graph.edges:
                self.assertIn(e.source, known, f"{name}: edge source {e.source}")
                self.assertIn(e.target, known, f"{name}: edge target {e.target}")

    def test_catalog_registry_matches_fixtures(self):
        """sample_catalog.ts registry ids/files agree with on-disk fixtures."""
        src = (SRC_DIR / "ui" / "sample_catalog.ts").read_text(encoding="utf-8")
        ids = re.findall(r"id:\s*'(sample-[a-z0-9-]+)'", src)
        self.assertEqual(
            sorted(ids),
            sorted(["sample-upstream-k8s", "sample-microservices-retail",
                    "sample-ray-kuberay-cluster", "sample-compute-class-benchmark"]),
        )
        data_files = re.findall(r"dataFile:\s*'\./([^']+)'", src)
        self.assertEqual(len(data_files), 4)
        for rel in data_files:
            self.assertTrue((REPO / "public" / rel).is_file(),
                            f"catalog dataFile {rel} not served under public/")

    def test_upstream_k8s_baseline(self):
        """SPEC-10 §3.1: 3 nodes, control-plane tier Y=7.0, etcd Y=5.5."""
        g = load_graph("sample-upstream-k8s.json")
        self.assertEqual(g.metadata.distribution, "upstream-oss")
        self.assertEqual(g.metadata.kubernetes_version, "v1.36.4")
        self.assertEqual(g.metadata.node_count, 3)
        chassis = sorted((n.name for n in g.nodes if n.kind == "Node"))
        self.assertEqual(chassis, ["upstream-cp", "upstream-worker-01", "upstream-worker-02"])

        api = find_one(g, lambda n: "kube-apiserver" in n.name, "apiserver")[0]
        self.assertEqual(api.spatial.y, 7.0)
        self.assertEqual(api.spatial.asset_type, "Cuboid_APIServer")
        etcd = find_one(g, lambda n: n.name.startswith("etcd-"), "etcd")[0]
        self.assertEqual(etcd.spatial.y, 5.5)
        self.assertEqual(etcd.spatial.asset_type, "Cuboid_etcd")
        for comp in ("kube-scheduler", "kube-controller-manager"):
            node = find_one(g, lambda n, c=comp: c in n.name, comp)[0]
            self.assertEqual(node.spatial.y, 4.5)

        raft = [e for e in g.edges if e.volume_label == "raft KV" and e.target == etcd.id]
        self.assertEqual(len(raft), 1)

    def test_upstream_system_infrastructure(self):
        """SPEC-10 §3.1: CoreDNS ×2, kube-proxy DaemonSet, Cilium CNI agents."""
        g = load_graph("sample-upstream-k8s.json")
        coredns = find_one(g, lambda n: "coredns" in n.name, "coredns")
        self.assertEqual(len(coredns), 2)
        for pod in coredns:
            self.assertEqual(pod.raw_labels.get("k8s-app"), "kube-dns")

        kube_proxy = find_one(g, lambda n: n.name.startswith("kube-proxy-"), "kube-proxy")
        self.assertEqual(len(kube_proxy), 3)  # every chassis runs the DaemonSet
        for pod in kube_proxy:
            self.assertEqual(pod.spatial.asset_type, "Cuboid_DaemonSet")
            self.assertEqual(pod.spatial.y, 0.65)

        cni = find_one(g, lambda n: n.name.startswith("cilium-"), "cilium CNI")
        self.assertEqual(len(cni), 3)
        for pod in cni:
            self.assertEqual(pod.spatial.asset_type, "Cuboid_DaemonSet")

        self.assertTrue(any("nginx-ingress-controller" in n.name for n in g.nodes))
        self.assertTrue(any(n.name.startswith("cert-manager") for n in g.nodes))

    def test_online_boutique_microservices(self):
        """SPEC-10 §3.2: all 11 microservices plus redis-cart present."""
        g = load_graph("sample-online-boutique.json")
        self.assertEqual(g.metadata.node_count, 4)
        svc_names = {
            "frontend", "cartservice", "productcatalogservice", "currencyservice",
            "paymentservice", "shippingservice", "emailservice", "checkoutservice",
            "recommendationservice", "adservice", "loadgenerator",
        }
        present = set()
        for n in g.nodes:
            for svc in svc_names:
                if n.id.startswith(f"pod/boutique/{svc}-") or n.id == f"pod/boutique/{svc}":
                    present.add(svc)
        missing = svc_names - present
        self.assertFalse(missing, f"microservices missing: {missing}")
        self.assertEqual(len(svc_names), 11)

        redis = find_one(g, lambda n: n.id.startswith("pod/boutique/redis-cart-"), "redis-cart")[0]
        self.assertEqual(redis.kind, "RedisNode")
        self.assertEqual(redis.spatial.asset_type, "Cache_Redis")

        # frontend → cartservice cart state and cartservice → redis-cart KV edges
        edge_pairs = {(e.source, e.target) for e in g.edges}
        self.assertTrue(any(s.endswith("cartservice-bc4d8f7f9-xq7qk") and t == redis.id
                            for s, t in edge_pairs), "cartservice→redis-cart edge missing")

    def test_online_boutique_autoscaling(self):
        """SPEC-10 §3.2: HPA frontend 2→10 @65%, VPA Auto cartservice, mixed reco."""
        g = load_graph("sample-online-boutique.json")
        frontends = find_one(g, lambda n: n.id.startswith("pod/boutique/frontend-"), "frontend")
        for pod in frontends:
            self.assertIsNotNone(pod.autoscaling, "frontend pod lacks autoscaling block")
            self.assertTrue(pod.autoscaling.has_hpa)
            self.assertEqual(pod.autoscaling.target_metric, "cpu:65")
            self.assertGreaterEqual(pod.autoscaling.current_replicas, 2)
            self.assertGreater(pod.autoscaling.desired_replicas, pod.autoscaling.current_replicas)
            self.assertFalse(pod.autoscaling.has_vpa)

        carts = find_one(g, lambda n: n.id.startswith("pod/boutique/cartservice-"), "cartservice")
        for pod in carts:
            self.assertIsNotNone(pod.autoscaling)
            self.assertTrue(pod.autoscaling.has_vpa, "cartservice must carry VPA")
            self.assertTrue(pod.autoscaling.is_resizing_in_place,
                            "VPA Auto mode ⇒ in-place morph candidate")
            self.assertEqual(pod.autoscaling.vpa_target_cpu, "0.4")
            self.assertEqual(pod.autoscaling.vpa_target_memory, "800Mi")

        recos = find_one(g, lambda n: n.id.startswith("pod/boutique/recommendationservice-"), "reco")
        for pod in recos:
            self.assertTrue(pod.autoscaling.has_hpa and pod.autoscaling.has_vpa,
                            "recommendationservice is mixed HPA + VPA")

    def test_online_boutique_subterranean_strata(self):
        """SPEC-08 strata: redis plunge conduit to a B2 vault + chassis shapes."""
        g = load_graph("sample-online-boutique.json")
        self.assertEqual(len(g.subterranean_resources), 2)
        vault_ids = {r.id for r in g.subterranean_resources}
        self.assertIn("kcc/memstore/boutique-redis-backplane", vault_ids)
        for res in g.subterranean_resources:
            self.assertIsNotNone(res.spatial)
            self.assertLess(res.spatial["y"], 0.0, "vaults live on sub-levels")
        # redis-cart → vault data_replication edge exists
        self.assertTrue(any(
            e.source.startswith("pod/boutique/redis-cart-") and e.target ==
            "kcc/memstore/boutique-redis-backplane" and e.flow_type == "data_replication"
            for e in g.edges))
        # 4 heterogeneous machine shapes (2× c3-standard-4 + 2× e2-standard-4)
        shapes = {s.instance_type for s in g.machine_shapes}
        self.assertEqual(len(g.machine_shapes), 4)
        self.assertEqual(shapes, {"c3-standard-4", "e2-standard-4"})

    def test_ray_kuberay_topology(self):
        """SPEC-10 §3.3: Ray head, 4 CPU workers, 2 GPU workers with bays."""
        g = load_graph("sample-ray-kuberay.json")
        self.assertEqual(g.metadata.node_count, 5)

        head = find_one(g, lambda n: n.kind == "RayHead", "Ray head")[0]
        self.assertEqual(head.spatial.y, 2.5)
        self.assertEqual(head.spatial.asset_type, "Cuboid_Ray")

        op = find_one(g, lambda n: "kuberay-operator" in n.name, "kuberay operator")[0]
        self.assertEqual(op.layer, "framework")
        kmc = find_one(g, lambda n: "kueue-controller-manager" in n.name, "kueue controller")[0]
        self.assertEqual(kmc.layer, "framework")

        cpu_workers = find_one(g, lambda n: n.kind == "RayWorker" and "cpu-workers" in n.name,
                               "ray cpu workers")
        self.assertEqual(len(cpu_workers), 4)
        gpu_workers = find_one(g, lambda n: n.kind == "RayWorker" and "gpu-workers" in n.name,
                               "ray gpu workers")
        self.assertEqual(len(gpu_workers), 2)
        # GPU workers are physically fatter capsules (SPEC-09 §3.1)
        for pod in gpu_workers:
            self.assertGreaterEqual(pod.pod_geometry.height, 1.8)
            self.assertGreaterEqual(pod.pod_geometry.radius, 0.9)
        # every worker heartbeats the head
        hb = [e for e in g.edges if e.volume_label == "ray heartbeat"]
        self.assertGreaterEqual(len(hb), 6)

    def test_ray_kuberay_accelerator_bays(self):
        """SPEC-08 §3.2: NVIDIA L4 / A100 accelerator bays on the GPU chassis."""
        g = load_graph("sample-ray-kuberay.json")
        shapes = {s.node_name: s for s in g.machine_shapes}
        l4 = shapes["ray-gpu-worker-l4"]
        self.assertEqual(l4.accelerator_type, "nvidia-l4")
        self.assertEqual(l4.accelerator_count, 2)
        a100 = shapes["ray-gpu-worker-a100"]
        self.assertEqual(a100.accelerator_type, "nvidia-a100-80gb")
        self.assertEqual(a100.accelerator_count, 1)
        for node_name, acc in (("ray-gpu-worker-l4", "nvidia-l4"),
                               ("ray-gpu-worker-a100", "nvidia-a100-80gb")):
            node = by_id(g, f"node/{node_name}")
            self.assertEqual(node.raw_labels.get("cloud.google.com/gke-accelerator"), acc)

    def test_ray_kuberay_kueue_gang_pallet(self):
        """SPEC-09 §5: Inadmissible PyTorch gang pallet in the staging yard."""
        g = load_graph("sample-ray-kuberay.json")
        self.assertEqual(len(g.kueue_workloads), 1)
        wl = g.kueue_workloads[0]
        self.assertEqual(wl.phase, "Inadmissible")
        self.assertFalse(wl.is_admitted)
        self.assertEqual(wl.local_queue, "team-training-lq")
        self.assertEqual(wl.cluster_queue, "gpu-cluster-queue")
        self.assertEqual(wl.total_cpu_requested, 32)
        self.assertEqual(wl.total_memory_gib_requested, 128)
        self.assertEqual(wl.total_gpu_requested, 4)
        self.assertTrue(wl.admission_checks)

        self.assertEqual(len(wl.pod_uids), 4)
        xs = []
        for uid in wl.pod_uids:
            pod = by_id(g, uid)
            self.assertEqual(pod.status, "Pending")
            self.assertTrue(pod.pod_geometry.is_pending)
            self.assertEqual(pod.pod_geometry.kueue_workload, wl.workload_uid)
            x = pod.spatial.x
            self.assertLess(x, -12.0, "gang pods must sit in the exterior staging yard")
            self.assertGreaterEqual(x, -21.0, "pallet dock domain X ∈ [-21, -15]")
            self.assertEqual(pod.spatial.y, 1.0)
            xs.append(x)
        # Pallet centered on the staging rail at X = -18.0 (SPEC-10 §3.3)
        self.assertAlmostEqual(sum(xs) / len(xs), -18.0, places=6)

    def test_compute_class_benchmark(self):
        """SPEC-10 §3.4: Scale-Up class lanes, Karpenter claims, staging pods."""
        g = load_graph("sample-compute-class-bench.json")
        self.assertEqual(g.metadata.node_count, 5)
        chassis = {n.name for n in g.nodes if n.kind == "Node"}
        self.assertEqual(chassis, {"gke-scaleup-pool-a", "gke-scaleup-pool-b",
                                   "gke-performance-pool", "static-nodepool-a",
                                   "karpenter-nodepool-a"})

        # GKE Scale-Up compute class labelling (SPEC-10 §3.4)
        scaleup_nodes = find_one(g, lambda n: n.name.startswith("gke-scaleup-pool"), "scaleup")
        for node in scaleup_nodes:
            self.assertEqual(node.raw_labels.get("cloud.google.com/compute-class"), "Scale-Up")
        scaleup_pods = find_one(g, lambda n: n.id.startswith("pod/bench-scaleup/bench-frontend-scaleup-"),
                                "scaleup pods")
        self.assertEqual(len(scaleup_pods), 4)
        for pod in scaleup_pods:
            self.assertEqual(pod.raw_labels.get("cloud.google.com/compute-class"), "Scale-Up")
            self.assertEqual(pod.status, "Healthy")
            self.assertEqual(pod.spatial.y, 0.75)  # scheduled onto the deck
            self.assertTrue(pod.autoscaling.has_hpa)
            self.assertEqual(pod.autoscaling.target_metric, "cpu:60")
            self.assertGreater(pod.autoscaling.desired_replicas, pod.autoscaling.current_replicas)

    def test_compute_class_karpenter_claims_and_staging(self):
        """Karpenter NodeClaims + exterior staging-yard Pending pods (X < -12)."""
        g = load_graph("sample-compute-class-bench.json")
        self.assertEqual(len(g.karpenter_node_claims), 2)
        claim_names = set()
        claimed_pods = set()
        for claim in g.karpenter_node_claims:
            self.assertFalse(claim.is_provisioned, "ghost chassis still provisioning")
            self.assertEqual(claim.capacity_type, "spot")
            self.assertGreater(claim.requested_cpu_cores, 0)
            claim_names.add(claim.claim_name)
            claimed_pods |= set(claim.pending_pod_uids)

        pending = find_one(g, lambda n: n.status == "Pending", "pending pods")
        self.assertEqual(len(pending), 4)
        for pod in pending:
            self.assertLess(pod.spatial.x, -12.0)
            self.assertEqual(pod.spatial.y, 1.0)
            self.assertTrue(pod.pod_geometry.is_pending)
            self.assertIn(pod.pod_geometry.karpenter_target_node_claim, claim_names)
        self.assertEqual(claimed_pods, {p.id for p in pending})

        # contrast lanes exist: static pool behind cluster-autoscaler, karpenter ctrl
        self.assertTrue(any("cluster-autoscaler" in n.name for n in g.nodes))
        self.assertTrue(any("karpenter-controller" in n.name for n in g.nodes))
        static_pods = find_one(g, lambda n: n.id.startswith("pod/bench-static/bench-frontend-static-"),
                               "static lane pods")
        self.assertEqual(len(static_pods), 4)


# ---------------------------------------------------------------------------
# 2. Queuing / autoscaling engine math via esbuild bridge
# ---------------------------------------------------------------------------

BRIDGE_TS = """
export {
  TrafficSimulator,
  patternRps,
  erlangCWaitMs,
  stagingHoverPosition,
  SCHED_PROFILES,
  mulberry32,
} from '__SIM_PATH__';
"""


class TrafficEngineBridgeTestCase(unittest.TestCase):
    """Base class exposing the TS traffic simulator through node."""

    bridge_path: Path | None = None

    @classmethod
    def setUpClass(cls):
        if not NODE_BIN or not ESBUILD_BIN.is_file():
            raise unittest.SkipTest("node / local esbuild required for engine bridge")
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="spec10_bridge_"))
        entry = cls.tmpdir / "bridge.ts"
        entry.write_text(
            BRIDGE_TS.replace("__SIM_PATH__", str(REPO / "src" / "scene" / "traffic_simulator.ts")),
            encoding="utf-8",
        )
        out = cls.tmpdir / "bridge.mjs"
        proc = subprocess.run(
            [str(ESBUILD_BIN), str(entry), "--bundle", "--platform=node",
             "--format=esm", f"--outfile={out}", "--log-level=warning"],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            raise unittest.SkipTest(f"esbuild bridge bundle failed: {proc.stderr[:400]}")
        cls.bridge_path = out

    def run_js(self, body: str, timeout: int = 120):
        script = (
            f"const M = await import({json.dumps(self.bridge_path.as_uri())});\n"
            f"{body}\n"
        )
        proc = subprocess.run(
            [NODE_BIN, "--input-type=module", "-e", script],
            capture_output=True, text=True, timeout=timeout, cwd=str(REPO),
        )
        if proc.returncode != 0:
            self.fail(f"node scenario failed rc={proc.returncode}\n{proc.stderr[:1200]}")
        return json.loads(proc.stdout.strip().splitlines()[-1])


class TestTrafficPatterns(TrafficEngineBridgeTestCase):
    """SPEC-10 §6.2 arrival-rate profile generators λ(t)."""

    def _pattern(self, pattern, t, dt=0.016, base=100, peak=850, dur=120, rng="0.5",
                 state="{ chaosValue: 100, chaosNextFlipAt: 0, chaosUp: true }"):
        js = f"""
          const rng = () => {rng};
          const st = {state};
          const v = M.patternRps('{pattern}', {t}, {dt}, {base}, {peak}, {dur}, rng, st);
          console.log(JSON.stringify(v));
        """
        return self.run_js(js)

    def test_step_spike(self):
        """Step pattern holds base until the t = 2 s spike, then holds peak."""
        self.assertEqual(self._pattern("step", 0), 100)
        self.assertEqual(self._pattern("step", 1.984), 100)
        self.assertEqual(self._pattern("step", 2.0), 850)
        self.assertEqual(self._pattern("step", 120), 850)

    def test_sine_wave(self):
        """Raised cosine anchored at base; peaks at period/2, period = max(8, dur/2)."""
        self.assertAlmostEqual(self._pattern("sine", 0), 100, places=6)
        self.assertAlmostEqual(self._pattern("sine", 30), 850, places=6)   # period 60 / 2
        self.assertAlmostEqual(self._pattern("sine", 60), 100, places=6)   # full period
        mid = self._pattern("sine", 15)
        self.assertGreater(mid, 100)
        self.assertLess(mid, 850)

    def test_ramp(self):
        """Linear ramp reaching peak across the first 80 % of the duration."""
        self.assertAlmostEqual(self._pattern("ramp", 0), 100, places=6)
        self.assertAlmostEqual(self._pattern("ramp", 48), 475, places=6)   # 96/2 midpoint
        self.assertAlmostEqual(self._pattern("ramp", 96), 850, places=6)
        self.assertEqual(self._pattern("ramp", 500), 850)                  # clamped

    def test_chaos_deterministic_and_bounded(self):
        """Chaos flap is PRNG-deterministic and stays inside [0.5·base, 1.05·peak]."""
        js = """
          function trace(seed) {
            const rng = M.mulberry32(seed);
            const st = { chaosValue: 100, chaosNextFlipAt: 0, chaosUp: true };
            const out = [];
            for (let i = 0; i < 3000; i++) {
              out.push(M.patternRps('chaos', i / 30, 1 / 30, 100, 850, 120, rng, st));
            }
            return out;
          }
          const a = trace(1337), b = trace(1337), c = trace(99);
          console.log(JSON.stringify({
            deterministic: JSON.stringify(a) === JSON.stringify(b),
            differs: JSON.stringify(a) !== JSON.stringify(c),
            min: Math.min(...a), max: Math.max(...a),
          }));
        """
        res = self.run_js(js)
        self.assertTrue(res["deterministic"], "chaos must be reproducible per seed")
        self.assertTrue(res["differs"], "distinct seeds must diverge")
        self.assertGreaterEqual(res["min"], 50 - EPS)
        self.assertLessEqual(res["max"], 892.5 + EPS)


class TestQueuingMath(TrafficEngineBridgeTestCase):
    """SPEC-10 §5.1 M/M/c/K intensity ρ(t) and latency transfer functions."""

    @staticmethod
    def erlang_c_reference(c: int, a: float) -> float:
        """Erlang-C probability P(wait) for an M/M/c queue (lgamma-free, exact)."""
        if a <= 0:
            return 0.0
        term = 1.0
        total = 0.0
        for k in range(1, c + 1):
            term *= a / k  # term == a^k / k!
            total += term
        # B = (a^c/c!) / Σ_{k=0..c} a^k/k!   (total + 1 includes the k=0 term)
        b = term / (total + 1.0)
        denom = c - a * (1 - b)
        if denom <= 0:
            return float("inf")
        return (c * b) / denom

    def test_erlang_c_stable_regime_matches_reference(self):
        for c, a in ((4, 1.5), (4, 3.5), (8, 6.4), (12, 7.2), (2, 0.5)):
            spare = c * 120 - a * 120  # cμ − λ with μ = 120
            js = f"""
              console.log(JSON.stringify(M.erlangCWaitMs({c}, {a}, {spare})));
            """
            got = self.run_js(js)
            p_wait = self.erlang_c_reference(c, a)
            expected = p_wait / spare * 1000.0
            self.assertAlmostEqual(got, expected, delta=max(1e-6, abs(expected) * 1e-6),
                                   msg=f"Erlang-C mismatch c={c} a={a}")
            self.assertGreater(got, 0.0)

    def test_erlang_c_unstable_returns_zero(self):
        """a ≥ c (ρ ≥ 1) defers to the integrated W_q deficit, not Erlang-C."""
        self.assertEqual(self.run_js("console.log(JSON.stringify(M.erlangCWaitMs(2, 2.0, 0)));"), 0)
        self.assertEqual(self.run_js("console.log(JSON.stringify(M.erlangCWaitMs(2, 3.0, -120)));"), 0)

    def test_traffic_intensity_rho_readout(self):
        """ρ(t) = λ(t)/(N(t)·μ): CPU % readout = min(100, 100ρ)."""
        js = """
          const sim = new M.TrafficSimulator({ hpaIntervalSeconds: 1, seed: 11 });
          sim.addWorkload(
            { id: 'w', clusterId: 'c', workloadName: 'w', computeClassType: 'gke-compute-class',
              initialReplicas: 5, maxReplicas: 5, serviceRatePerPod: 120 },
            { pattern: 'step', baseRps: 300, peakRps: 300, durationSeconds: 30,
              enableHpa: false, enableVpa: false, simulateProvisioningSkew: false });
          sim.start();
          for (let i = 0; i < 60; i++) sim.update(1 / 30);
          const s = sim.getState('w');
          console.log(JSON.stringify({ rps: sim.getCurrentRps('w'), cpu: s.currentCpuUtilization }));
        """
        res = self.run_js(js)
        self.assertAlmostEqual(res["rps"], 300, places=6)
        # λ/(N·μ) = 300/(5·120) = 0.5 → 50 %
        self.assertAlmostEqual(res["cpu"], 50.0, places=6)

    def test_low_load_latency_stays_near_baseline(self):
        """ρ < 0.7: L(t) = L_base + ErlangC-Wq — bounded, far from saturation."""
        js = """
          const sim = new M.TrafficSimulator({ hpaIntervalSeconds: 1, seed: 5 });
          sim.addWorkload(
            { id: 'w', clusterId: 'c', workloadName: 'w', computeClassType: 'gke-compute-class',
              initialReplicas: 10, maxReplicas: 10, serviceRatePerPod: 120,
              baselineLatencyMs: 12 },
            { pattern: 'step', baseRps: 600, peakRps: 600, durationSeconds: 20,
              enableHpa: false, enableVpa: false, simulateProvisioningSkew: false });
          sim.start();
          for (let i = 0; i < 400; i++) sim.update(1 / 30);
          console.log(JSON.stringify(sim.getState('w').latencyMs));
        """
        lat = self.run_js(js)
        self.assertGreater(lat, 12 - EPS)
        self.assertLess(lat, 30, f"ρ=0.5 latency {lat} ms should sit in the 10–30 ms band")

    def test_saturated_latency_integrates_deficit(self):
        """ρ ≥ 1: L(t) = L_base + 1/μ + W_q(t) with W_q growing over seconds."""
        js = """
          const sim = new M.TrafficSimulator({ hpaIntervalSeconds: 30, seed: 9 });
          sim.addWorkload(
            { id: 'w', clusterId: 'c', workloadName: 'w', computeClassType: 'karpenter',
              initialReplicas: 1, maxReplicas: 1, serviceRatePerPod: 120,
              baselineLatencyMs: 12 },
            { pattern: 'step', baseRps: 100, peakRps: 1200, durationSeconds: 60,
              enableHpa: false, enableVpa: false, simulateProvisioningSkew: false });
          sim.start();
          const curve = [];
          // sample only the post-spike saturated regime (t ≥ 2)
          for (let i = 0; i < 900; i++) {
            sim.update(1 / 30);
            if (i >= 60 && i % 30 === 0) curve.push(sim.getState('w').latencyMs);
          }
          console.log(JSON.stringify(curve));
        """
        curve = self.run_js(js)
        self.assertGreaterEqual(len(curve), 10)
        self.assertGreater(curve[0], 12 + 1000 / 120 - EPS)  # ≥ L_base + 1/μ
        self.assertGreater(curve[-1], curve[5], "queue delay must grow while λ > Nμ")
        self.assertGreater(curve[-1], 500, "deficit plateau should pass 500 ms")
        # monotonically increasing through the saturation run
        for a, b in zip(curve, curve[1:]):
            self.assertGreaterEqual(b, a - 1)

    def test_burst_override(self):
        """HUD ⚡ BURST injects λ ≥ 2000 immediately and decays after the window."""
        js = """
          const sim = new M.TrafficSimulator({ hpaIntervalSeconds: 1, seed: 2 });
          sim.addWorkload(
            { id: 'w', clusterId: 'c', workloadName: 'w', computeClassType: 'static-nodepool',
              initialReplicas: 2, serviceRatePerPod: 120 },
            { pattern: 'ramp', baseRps: 50, peakRps: 500, durationSeconds: 60 });
          sim.start();
          for (let i = 0; i < 30; i++) sim.update(1 / 30);
          sim.burst(2000, 2);
          sim.update(0.05);
          const peak = sim.getCurrentRps('w');
          for (let i = 0; i < 100; i++) sim.update(0.05);
          console.log(JSON.stringify({ peak, after: sim.getCurrentRps('w') }));
        """
        res = self.run_js(js)
        self.assertGreaterEqual(res["peak"], 2000)
        self.assertLess(res["after"], 2000)


class TestAutoscalingRules(TrafficEngineBridgeTestCase):
    """SPEC-10 §5.2 HPA replica bounds and VPA resize thresholds."""

    def test_hpa_desired_replicas_formula(self):
        """desired = ceil(N · CPU% / target) on the first evaluation after a spike."""
        js = """
          const sim = new M.TrafficSimulator({ hpaIntervalSeconds: 1, seed: 21 });
          sim.addWorkload(
            { id: 'w', clusterId: 'c', workloadName: 'w', computeClassType: 'gke-compute-class',
              initialReplicas: 2, minReplicas: 2, maxReplicas: 10, targetCpuUtilization: 60,
              serviceRatePerPod: 120 },
            { pattern: 'step', baseRps: 100, peakRps: 1560, durationSeconds: 60 });
          sim.start();
          // spike fires at t=2; the first post-spike HPA eval lands ≈ t=2.03 —
          // sample inside that same 1 s window (before any compounding eval).
          for (let i = 0; i < 75; i++) sim.update(1 / 30);   // t ≈ 2.5
          const s = sim.getState('w');
          console.log(JSON.stringify({
            desired: s.desiredReplicas, cpu: s.currentCpuUtilization,
            live: s.currentReplicas + s.pendingReplicas, t: sim.getSimTime() }));
        """
        res = self.run_js(js)
        self.assertGreaterEqual(res["t"], 2.0)
        self.assertLess(res["t"], 3.0, "must stay inside the first eval window")
        # cpu pegged at 100 % ⇒ desired = ceil(2 × 100/60) = 4
        self.assertEqual(res["cpu"], 100)
        self.assertEqual(res["live"], 2 + 2, "first eval spawned ceil(2·100/60)−2 replicas")
        self.assertEqual(res["desired"], math.ceil(2 * 100 / 60))

    def test_hpa_max_replicas_bound(self):
        js = """
          const sim = new M.TrafficSimulator({ hpaIntervalSeconds: 1, seed: 33 });
          sim.addWorkload(
            { id: 'w', clusterId: 'c', workloadName: 'w', computeClassType: 'gke-compute-class',
              initialReplicas: 1, minReplicas: 1, maxReplicas: 3, targetCpuUtilization: 60,
              serviceRatePerPod: 120 },
            { pattern: 'step', baseRps: 5000, peakRps: 5000, durationSeconds: 30 });
          sim.start();
          let maxLive = 0;
          for (let i = 0; i < 600; i++) {
            sim.update(1 / 30);
            const s = sim.getState('w');
            maxLive = Math.max(maxLive, s.currentReplicas + s.pendingReplicas);
          }
          const s = sim.getState('w');
          console.log(JSON.stringify({ maxLive, desired: s.desiredReplicas, current: s.currentReplicas }));
        """
        res = self.run_js(js)
        self.assertLessEqual(res["maxLive"], 3, "never exceeds maxReplicas incl. pending")
        self.assertLessEqual(res["desired"], 3)
        self.assertEqual(res["current"], 3, "maxReplicas fully reached")

    def test_hpa_min_replicas_and_stabilization(self):
        """Scale-down honours minReplicas and the stabilization window."""
        js = """
          const sim = new M.TrafficSimulator({
            hpaIntervalSeconds: 1, scaleDownStabilizationSeconds: 1, seed: 44 });
          sim.addWorkload(
            { id: 'w', clusterId: 'c', workloadName: 'w', computeClassType: 'gke-compute-class',
              initialReplicas: 4, minReplicas: 2, maxReplicas: 8, targetCpuUtilization: 60,
              serviceRatePerPod: 120 },
            { pattern: 'step', baseRps: 1, peakRps: 1, durationSeconds: 30 });
          sim.start();
          for (let i = 0; i < 300; i++) sim.update(1 / 30);
          console.log(JSON.stringify(sim.getState('w').currentReplicas));
        """
        replicas = self.run_js(js)
        self.assertEqual(replicas, 2, "scales down to minReplicas but never below")

    def test_vpa_sustained_trigger_and_morph(self):
        """CPU > 80 % for 3 s ⇒ recommendation, then resize commit after τ_vpa."""
        js = """
          let recoAt = null, resizeAt = null;
          const sim = new M.TrafficSimulator({ hpaIntervalSeconds: 1, seed: 3, callbacks: {
            onVpaRecommendation: () => { if (recoAt === null) recoAt = sim.getSimTime(); },
            onVpaResize: () => { if (resizeAt === null) resizeAt = sim.getSimTime(); },
          } });
          sim.addWorkload(
            { id: 'cart', clusterId: 'c', workloadName: 'cartservice',
              computeClassType: 'gke-compute-class', initialReplicas: 1, maxReplicas: 1,
              targetCpuUtilization: 60, serviceRatePerPod: 100, hasVpa: true,
              podCpuCores: 0.4, podMemoryGib: 1 },
            { pattern: 'step', baseRps: 50, peakRps: 500, durationSeconds: 30,
              enableHpa: false, enableVpa: true });
          sim.start();
          let peakCpu = 0;
          for (let i = 0; i < 900; i++) {
            sim.update(1 / 30);
            peakCpu = Math.max(peakCpu, sim.getState('cart').currentCpuUtilization);
          }
          const s = sim.getState('cart');
          console.log(JSON.stringify({ recoAt, resizeAt, peakCpu, lat: s.latencyMs }));
        """
        res = self.run_js(js)
        self.assertIsNotNone(res["recoAt"], "VPA recommendation must fire under >80% CPU")
        self.assertIsNotNone(res["resizeAt"], "VPA resize must commit after τ_vpa = 1.2 s")
        self.assertGreater(res["peakCpu"], 80)
        # recommendation is only valid after 3 s of sustained pressure
        self.assertGreaterEqual(res["recoAt"], 3 - 1e-6 - 2 / 30)
        self.assertGreaterEqual(res["resizeAt"], res["recoAt"])
        # committed morph grows effective μ: latency back under control
        self.assertLess(res["lat"], 100)

    def test_vpa_below_threshold_does_not_fire(self):
        """CPU pegged at 50 % (< 80 % threshold) must not trigger VPA."""
        js = """
          let fires = 0;
          const sim = new M.TrafficSimulator({ hpaIntervalSeconds: 1, seed: 8, callbacks: {
            onVpaResize: () => fires++, onVpaRecommendation: () => fires++,
          } });
          sim.addWorkload(
            { id: 'w', clusterId: 'c', workloadName: 'w', computeClassType: 'gke-compute-class',
              initialReplicas: 4, maxReplicas: 4, serviceRatePerPod: 100, hasVpa: true },
            { pattern: 'step', baseRps: 200, peakRps: 200, durationSeconds: 60,
              enableHpa: false, enableVpa: true });
          sim.start();
          let maxCpu = 0;
          for (let i = 0; i < 1800; i++) {
            sim.update(1 / 30);
            maxCpu = Math.max(maxCpu, sim.getState('w').currentCpuUtilization);
          }
          console.log(JSON.stringify({ fires, maxCpu }));
        """
        res = self.run_js(js)
        self.assertAlmostEqual(res["maxCpu"], 50.0, places=3)
        self.assertEqual(res["fires"], 0, "50% CPU must never trip the 80% VPA gate")


class TestSchedulingLatencySkew(TrafficEngineBridgeTestCase):
    """SPEC-10 §5.3 comparative GKE Compute Class vs Karpenter / static bands."""

    def test_sched_profiles_bands(self):
        profiles = self.run_js("console.log(JSON.stringify(M.SCHED_PROFILES));")
        gke, kar, st = profiles["gke-compute-class"], profiles["karpenter"], profiles["static-nodepool"]
        self.assertGreaterEqual(gke["schedDelayS"], GKE_TAU_SCHED_MIN)
        self.assertLessEqual(gke["schedDelayS"], GKE_TAU_SCHED_MAX)
        self.assertEqual(gke["nodeProvisionS"], 0, "pre-warmed fabric: no cold VM boot")
        self.assertAlmostEqual(gke["vpaDelayS"], 1.2, places=6)
        self.assertGreater(gke["deficitAbsorb"], 0.5, "fabric soaks most transient deficit")

        self.assertGreaterEqual(kar["nodeProvisionS"], KARPENTER_TAU_NODE_MIN)
        self.assertLessEqual(kar["nodeProvisionS"], KARPENTER_TAU_NODE_MAX)
        self.assertAlmostEqual(kar["vpaDelayS"], 45.0, places=6)
        self.assertEqual(kar["deficitAbsorb"], 0)

        self.assertGreaterEqual(st["nodeProvisionS"], STATIC_TAU_NODE_MIN)
        self.assertLessEqual(st["nodeProvisionS"], STATIC_TAU_NODE_MAX)
        self.assertGreater(kar["schedDelayS"], gke["schedDelayS"] * 10,
                           "cold-VM τ must dominate pre-warmed τ_sched by ≥ 10×")

    def test_staging_hover_geometry(self):
        """Every staging hover sits in the exterior yard (X < −12.0, Y = 1.0)."""
        pts = self.run_js(
            "console.log(JSON.stringify(Array.from({length: 16}, (_, i) => M.stagingHoverPosition(i))));"
        )
        self.assertEqual(len(pts), 16)
        for p in pts:
            self.assertLess(p["x"], -12.0)
            self.assertEqual(p["y"], 1.0)
        self.assertEqual(pts[0], {"x": -22.0, "y": 1.0, "z": -6.0})
        self.assertEqual(pts[1]["x"], -20.0)

    def _spike_scenario(self, compute_class: str, seed: int):
        js = f"""
          let staged = 0, scheduled = 0;
          const sim = new M.TrafficSimulator({{ hpaIntervalSeconds: 1, seed: {seed}, callbacks: {{
            onPodScheduled: () => scheduled++,
            onPendingStaged: () => staged++,
          }} }});
          sim.addWorkload(
            {{ id: 'fe', clusterId: '{compute_class}', workloadName: 'frontend',
               computeClassType: '{compute_class}', initialReplicas: 2, minReplicas: 2,
               maxReplicas: 12, targetCpuUtilization: 60, serviceRatePerPod: 120 }},
            {{ pattern: 'step', baseRps: 100, peakRps: 1200, durationSeconds: 180 }});
          sim.start();
          let maxLat = 0, maxErr = 0, tAt500 = null;
          for (let i = 0; i < 180 * 30; i++) {{
            sim.update(1 / 30);
            const s = sim.getState('fe');
            maxLat = Math.max(maxLat, s.latencyMs);
            maxErr = Math.max(maxErr, s.errorRate);
            if (tAt500 === null && s.latencyMs >= 500) tAt500 = Math.round(i / 30 * 10) / 10;
          }}
          const s = sim.getState('fe');
          console.log(JSON.stringify({{ maxLat, maxErr, tAt500, staged, scheduled,
            finalLat: s.latencyMs, finalErr: s.errorRate, replicas: s.currentReplicas }}));
        """
        return self.run_js(js)

    def test_gke_compute_class_absorbs_spike(self):
        """SPEC-10 §9.3: 10× spike → ≤ 60 ms transient, 0 % errors, fast scheduling."""
        gke = self._spike_scenario("gke-compute-class", 42)
        self.assertLessEqual(gke["maxLat"], 60, f'peak {gke["maxLat"]} ms')
        self.assertLess(gke["maxErr"], 0.01)
        self.assertEqual(gke["staged"], 0, "fast-path pods never strand in the yard")
        self.assertGreaterEqual(gke["scheduled"], 8)
        self.assertLess(gke["finalLat"], 30, "recovers to baseline latency")
        self.assertGreaterEqual(gke["replicas"], 8)

    def test_karpenter_spike_saturates_then_recovers(self):
        """Cold-VM lane: >500 ms latency, ~18 % errors, staging, recovery on land."""
        kar = self._spike_scenario("karpenter", 42)
        self.assertGreater(kar["maxLat"], 500, f'peak {kar["maxLat"]} ms')
        self.assertIsNotNone(kar["tAt500"])
        self.assertLessEqual(kar["tAt500"], 30, "saturation onset within ~30 s of spike")
        # SPEC-10 §5.3 benchmark row: 18.4 % HTTP error band
        self.assertGreater(kar["maxErr"], 0.15)
        self.assertLessEqual(kar["maxErr"], 0.21)
        self.assertGreaterEqual(kar["staged"], 4, "pending pods hover in the exterior yard")
        self.assertGreaterEqual(kar["scheduled"], 4)
        self.assertGreaterEqual(kar["replicas"], 6, "cold-VM pods land after τ_node")
        self.assertLess(kar["finalErr"], 0.02, "queue drains once capacity arrives")
        self.assertLess(kar["finalLat"], 100)

    def test_comparative_skew_latency_ratio(self):
        """Under the identical spike the cold lane must hurt ≥ 5× more than GKE."""
        gke = self._spike_scenario("gke-compute-class", 77)
        kar = self._spike_scenario("karpenter", 77)
        self.assertGreater(kar["maxLat"], gke["maxLat"] * 5)
        self.assertGreater(kar["maxErr"], gke["maxErr"] + 0.10)


# ---------------------------------------------------------------------------
# 3. Secret scrubbing guarantees (SPEC-10 §2.1.1, SPEC-07 §5.1)
# ---------------------------------------------------------------------------


class TestSecretScrubbing(unittest.TestCase):

    def _dirty_pod(self) -> dict:
        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "frontend-7d9d-f2k2l",
                "namespace": "boutique",
                "annotations": {
                    "kubectl.kubernetes.io/last-applied-configuration": '{"spec":...}',
                    "cloud.yandex.ru/service-account-oauth-token": "ya29.SECRETVAL",
                    "example.com/owner": "team-a",
                    "note": "rotated auth rotation pending",
                },
                "labels": {"app": "frontend", "api-key-label": "nope"},
            },
            "spec": {
                "volumes": [
                    {"name": "config", "configMap": {"name": "app-config"}},
                    {"name": "tls", "secret": {"secretName": "frontend-tls"}},
                ],
                "containers": [{
                    "name": "frontend",
                    "env": [
                        {"name": "APP_ENV", "value": "prod"},
                        {"name": "DB_PASSWORD", "value": "hunter2"},
                        {"name": "GITHUB_TOKEN", "value": "ghp_supersecret"},
                        {"name": "API_KEY", "value": "AKIA1234"},
                        {"name": "AUTH_HEADER", "value": "Bearer eyJhbGciOi..."},
                        {"name": "PASSPHRASE", "value": "let-me-in"},
                        {"name": "OTEL_EXPORTER", "valueFrom": {"fieldRef": {"fieldPath": "status.hostIP"}}},
                    ],
                    "envFrom": [
                        {"configMapRef": {"name": "app-config"}},
                        {"secretRef": {"name": "frontend-secrets"}},
                    ],
                }],
            },
        }

    def test_pod_env_secrets_dropped(self):
        scrubbed = SecretScrubber.scrub_pod_spec(self._dirty_pod())
        env = scrubbed["spec"]["containers"][0]["env"]
        names = {e["name"] for e in env}
        # Sensitive names (*KEY* *TOKEN* *PASS* *SECRET*) vanish entirely
        self.assertNotIn("DB_PASSWORD", names)
        self.assertNotIn("GITHUB_TOKEN", names)
        self.assertNotIn("API_KEY", names)
        self.assertNotIn("PASSPHRASE", names)  # *PASS* substring match
        # SPEC-10 §2.1.1: *AUTH* values are also sanitized — the scrubber drops
        # every `value`/`valueFrom`, so no AUTH payload survives serialization.
        auth = next(e for e in env if e["name"] == "AUTH_HEADER")
        self.assertEqual(auth, {"name": "AUTH_HEADER"})
        # Benign names survive with ONLY the name kept (values dropped)
        app_env = next(e for e in env if e["name"] == "APP_ENV")
        self.assertEqual(app_env, {"name": "APP_ENV"})
        otel = next(e for e in env if e["name"] == "OTEL_EXPORTER")
        self.assertNotIn("valueFrom", otel)
        # every surviving env entry is name-only — no `value` anywhere
        self.assertTrue(all("value" not in e and "valueFrom" not in e for e in env))
        # Nothing in the scrubbed payload leaks the raw secret strings
        blob = json.dumps(scrubbed)
        for secret in ("hunter2", "ghp_supersecret", "AKIA1234", "Bearer eyJ", "let-me-in"):
            self.assertNotIn(secret, blob)

    def test_secret_volumes_and_envfrom_stripped(self):
        scrubbed = SecretScrubber.scrub_pod_spec(self._dirty_pod())
        vols = scrubbed["spec"]["volumes"]
        self.assertTrue(all("secret" not in v for v in vols))
        self.assertTrue(any(v.get("configMap") for v in vols), "non-secret volumes survive")
        env_from = scrubbed["spec"]["containers"][0]["envFrom"]
        self.assertTrue(all("secretRef" not in r for r in env_from))
        self.assertTrue(any("configMapRef" in r for r in env_from))

    def test_metadata_annotations_scrubbed(self):
        scrubbed = SecretScrubber.scrub_pod_spec(self._dirty_pod())
        ann = scrubbed["metadata"]["annotations"]
        self.assertNotIn("kubectl.kubernetes.io/last-applied-configuration", ann)
        self.assertNotIn("cloud.yandex.ru/service-account-oauth-token", ann)
        # value-level match ("auth rotation pending") also stripped
        self.assertNotIn("note", ann)
        self.assertEqual(ann.get("example.com/owner"), "team-a")
        labels = scrubbed["metadata"]["labels"]
        self.assertNotIn("api-key-label", labels)
        self.assertEqual(labels.get("app"), "frontend")

    def test_configmap_data_omitted(self):
        scrubbed = SecretScrubber.scrub_configmap({
            "metadata": {"name": "app-config"},
            "data": {"database_url": "postgres://user:pw@host/db"},
            "binaryData": {"blob": "AAAA"},
        })
        self.assertNotIn("data", scrubbed)
        self.assertNotIn("binaryData", scrubbed)
        self.assertEqual(scrubbed["metadata"]["name"], "app-config")

    def test_exporter_scrub_sensitive_string(self):
        """exporter.scrub_sensitive_string: empty → [REDACTED]; long → sha256 digest."""
        self.assertEqual(scrub_sensitive_string(""), "[REDACTED]")
        hashed = scrub_sensitive_string("super-secret-token-value-longer-than-32-chars")
        self.assertTrue(hashed.startswith("sha256:"))
        self.assertNotIn("super-secret", hashed)
        expected = hashlib.sha256(
            "super-secret-token-value-longer-than-32-chars".encode()).hexdigest()[:16]
        self.assertEqual(hashed, f"sha256:{expected}")
        self.assertEqual(scrub_sensitive_string("short"), "[REDACTED]")

    def test_exporter_sensitive_key_pattern(self):
        from src.ingestion.exporter import SENSITIVE_KEY_PATTERN
        for word in ("DB_PASSWORD", "TOKEN", "SecretKey", "auth_url", "credential",
                     "private_key", "cert_pem", "TLS_CA", "APIKEY", "access_key"):
            self.assertTrue(SENSITIVE_KEY_PATTERN.search(word), word)
        for word in ("APP_ENV", "region", "LOGLEVEL"):
            self.assertFalse(SENSITIVE_KEY_PATTERN.search(word), word)


class TestFixtureSecretHygiene(unittest.TestCase):
    """Shipped sample fixtures must never carry credential-shaped values."""

    CREDENTIAL_PATTERNS = [
        re.compile(r"Bearer\s+eyJ"),                      # JWT bearer tokens
        re.compile(r"AKIA[0-9A-Z]{16}"),                  # AWS access key ids
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),  # PEM private keys
        re.compile(r"ghp_[A-Za-z0-9]{30,}"),              # GitHub PATs
        re.compile(r"xox[baprs]-[A-Za-z0-9-]+"),          # Slack tokens
        re.compile(r"(?i)\"[a-z_]*(password|passwd|secret|apikey|api_key|access_token|private_key)[a-z_]*\"\s*:\s*\"[^\"]+\""),
    ]

    def test_no_credentials_in_samples(self):
        for name in SAMPLE_FIXTURES:
            raw = (SAMPLE_DIR / name).read_text(encoding="utf-8")
            for pat in self.CREDENTIAL_PATTERNS:
                m = pat.search(raw)
                self.assertIsNone(m, f"{name}: credential-shaped value {m.group(0)[:40]!r}"
                                     if m else None)

    def test_onboarding_tokens_session_storage_only(self):
        """SPEC-07 §5.1 / SPEC-10: tokens sessionStorage-only, never localStorage."""
        text = (SRC_DIR / "ui" / "cluster_onboarding.ts").read_text(encoding="utf-8")
        self.assertIn("const TOKEN_STORAGE_PREFIX = 'clustervis_token_';", text)
        self.assertIn("sessionStorage.setItem(TOKEN_STORAGE_PREFIX + endpointId, token)", text)
        self.assertIn("sessionStorage.removeItem(TOKEN_STORAGE_PREFIX + endpointId)", text)
        self.assertNotIn("localStorage.setItem", text)
        self.assertNotIn("localStorage.getItem", text)

    def test_client_extractor_token_header_only(self):
        """Extractor attaches the token strictly to Authorization headers."""
        text = (SRC_DIR / "ingestion" / "client_extractor.ts").read_text(encoding="utf-8")
        self.assertIn("headers['Authorization'] = `Bearer ${token}`", text)
        self.assertNotIn("localStorage", text)
        self.assertNotIn("sessionStorage", text)
        self.assertNotIn("document.cookie", text)
        # extractClusterGraph takes only raw API responses — no token parameter,
        # so nothing credential-shaped can be echoed into the produced graph.
        m = re.search(r"export function extractClusterGraph\(([^)]*)\)", text)
        assert m is not None, "extractClusterGraph signature not found"
        self.assertNotIn("token", m.group(1).lower())

    def test_onboarding_generates_token_auth_helm_cmd(self):
        text = (SRC_DIR / "ui" / "cluster_onboarding.ts").read_text(encoding="utf-8")
        self.assertIn("--set auth.type=token", text)
        self.assertIn("clustervis-system", text)


# ---------------------------------------------------------------------------
# 4. End-to-end TypeScript verification harnesses
# ---------------------------------------------------------------------------

class TestSpec10VerificationScripts(unittest.TestCase):
    """scripts/verify_spec10_engine.ts + verify_spec10_deck.ts must pass clean."""

    def _run_harness(self, script: str):
        if not NODE_BIN or not ESBUILD_BIN.is_file():
            self.skipTest("node / local esbuild required")
        outdir = Path(tempfile.mkdtemp(prefix="spec10_verify_"))
        out = outdir / f"{script}.mjs"
        bundle = subprocess.run(
            [str(ESBUILD_BIN), str(SCRIPTS_DIR / script), "--bundle", "--platform=node",
             "--format=esm", f"--outfile={out}", "--log-level=warning"],
            capture_output=True, text=True, timeout=120, cwd=str(REPO),
        )
        self.assertEqual(bundle.returncode, 0, f"esbuild failed: {bundle.stderr[:400]}")
        proc = subprocess.run([NODE_BIN, str(out)], capture_output=True, text=True,
                              timeout=300, cwd=str(REPO))
        return proc

    def test_verify_spec10_engine(self):
        proc = self._run_harness("verify_spec10_engine.ts")
        self.assertEqual(proc.returncode, 0,
                         f"engine harness failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-800:]}")
        self.assertIn("ALL CHECKS PASSED", proc.stdout)
        self.assertNotIn("FAIL", proc.stdout)

    def test_verify_spec10_deck(self):
        proc = self._run_harness("verify_spec10_deck.ts")
        self.assertEqual(proc.returncode, 0,
                         f"deck harness failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-800:]}")
        self.assertIn("ALL CHECKS PASSED", proc.stdout)
        self.assertNotIn("FAIL", proc.stdout)


if __name__ == "__main__":
    unittest.main()
