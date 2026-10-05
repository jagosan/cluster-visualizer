/**
 * SampleCatalogRegistry — SPEC-10 §3 / TASK-CV-1102
 *
 * Zero-friction instant simulated sample catalog. Pre-compiled ClusterGraph
 * fixtures are bundled with the client under `public/data/samples/` and
 * hydrate in < 100 ms with zero cloud credentials, zero daemons, and zero
 * network egress beyond the static same-origin JSON fetch (SPEC-10 §2.1.3).
 *
 * The four launch presets (SPEC-10 §3.1–§3.4):
 *   1. `sample-upstream-k8s`          — OSS vanilla Kubernetes v1.36.4 baseline
 *   2. `sample-microservices-retail`  — Google Online Boutique ("gshoe") retail store
 *   3. `sample-ray-kuberay-cluster`   — Ray & KubeRay AI/ML cluster (L4/A100 + Kueue)
 *   4. `sample-compute-class-benchmark` — GKE Compute Class vs Karpenter / Static NodePool
 *
 * First-fetch responses are memoized in-memory so repeat loads from the
 * onboarding modal skip the network round-trip entirely.
 */

import type { ClusterGraphData } from '../scene/cluster_viewport.js';

/** SPEC-10 §7.1 catalog registry entry. */
export interface SampleClusterCatalogItem {
  id: string;
  title: string;
  description: string;
  category: 'oss' | 'microservices' | 'ai-ml' | 'benchmark';
  k8sVersion: string;
  nodeCount: number;
  podCount: number;
  dataFile: string;
  diffTargetFile?: string;
  highlightFeatures: string[];
}

/**
 * Canonical launch catalog. `dataFile` paths are relative to the site root
 * exactly as served by Vite (`public/` is merged into the web root).
 */
const SAMPLE_CATALOG: SampleClusterCatalogItem[] = [
  {
    id: 'sample-upstream-k8s',
    title: 'OSS Vanilla Kubernetes v1.36.4',
    description:
      'Clean upstream-oss reference cluster: penthouse kube-apiserver over a clustered etcd vault, CoreDNS, kube-proxy + Cilium CNI daemonsets on every chassis, and baseline ingress-nginx / cert-manager deployments on two dual-containerd workers.',
    category: 'oss',
    k8sVersion: 'v1.36.4',
    nodeCount: 3,
    podCount: 15,
    dataFile: './data/samples/sample-upstream-k8s.json',
    highlightFeatures: [
      'Control plane Y = 7.0 with clustered etcd vault (Y = 5.5)',
      'CoreDNS ×2, kube-proxy + Cilium CNI routing agents (DaemonSet bays)',
      'Baseline nginx-ingress-controller ×2 + cert-manager deployments',
      '2 worker nodes (16 vCPU / 64 GiB) with kubelet + containerd runtime bays',
    ],
  },
  {
    id: 'sample-microservices-retail',
    title: 'Online Boutique — "gshoe" Retail Store',
    description:
      'Google Cloud Online Boutique (Hipster Shop) with all 11 microservices and the redis-cart cart store on heterogeneous GKE pools. frontend carries an HPA (2→10 @ 65% CPU), cartservice an in-place VPA morph candidate, recommendationservice mixed HPA + VPA; KCC-managed Memorystore and GCS vaults plunge to Sub-Level B2.',
    category: 'microservices',
    k8sVersion: 'v1.36.4',
    nodeCount: 4,
    podCount: 19,
    dataFile: './data/samples/sample-online-boutique.json',
    highlightFeatures: [
      '11 microservices: frontend → checkout/ads/reco/carts + redis-cart backing',
      'HPA on frontend (min 2 / max 10 @ 65% CPU), VPA "Auto" morph on cartservice',
      'Mixed HPA + VPA autoscaling on recommendationservice',
      'Heterogeneous pools: 2× c3-standard-4 (Performance) + 2× e2-standard-4',
      'SPEC-08 strata: redis-cart plunge conduit to B2 Memorystore vault',
    ],
  },
  {
    id: 'sample-ray-kuberay-cluster',
    title: 'Ray & KubeRay AI/ML Cluster',
    description:
      'KubeRay v1.2.0 operator driving a Ray v2.35.0 cluster: head node (GCS server, dashboard, autoscaler, Prometheus exporter), 4 CPU preprocessing workers, and 2 fat GPU workers seated in NVIDIA L4 / A100 accelerator bays. Kueue v0.9.0 LocalQueues hold an unadmitted PyTorch gang in a cargo containment pallet on the exterior staging rail (X = -18.0, KeyK admission).',
    category: 'ai-ml',
    k8sVersion: 'v1.36.4',
    nodeCount: 5,
    podCount: 17,
    dataFile: './data/samples/sample-ray-kuberay.json',
    highlightFeatures: [
      'Ray Head: GCS + dashboard + cluster autoscaler + metrics exporter',
      'GPU group in NVIDIA L4 (g2) / A100-80gb (a2) accelerator bays (SPEC-08 §3.2)',
      'Kueue LocalQueue / ClusterQueue with Inadmissible PyTorch gang pallet (SPEC-09 §5)',
      'vLLM distributed tensor-parallel batch inference lanes',
    ],
  },
  {
    id: 'sample-compute-class-benchmark',
    title: 'GKE Compute Class vs Karpenter Benchmark',
    description:
      'Comparative declarative auto-provisioning benchmark: GKE Autopilot-style Compute Classes (cloud.google.com/compute-class Scale-Up / Performance / General-Purpose) with ~3–6 s scheduling and 1.2 s in-place VPA morphs, contrasted against Karpenter NodeClaims (cold-VM pods stranded in the exterior staging yard under amber tractor beams) and a static node pool behind the cluster-autoscaler.',
    category: 'benchmark',
    k8sVersion: 'v1.36.4',
    nodeCount: 5,
    podCount: 15,
    dataFile: './data/samples/sample-compute-class-bench.json',
    highlightFeatures: [
      'cloud.google.com/compute-class "Scale-Up" annotated workload pods',
      'τ_sched ≈ 3–6 s pre-warmed slices + τ_vpa ≈ 1.2 s in-place resize morphs',
      'Karpenter NodeClaims: pending pods hover at X < -12.0 over B1 ghost chassis',
      'Static NodePool + cluster-autoscaler contrast lane (τ_node ≈ 95–150 s)',
    ],
  },
];

/**
 * Registry + in-memory topology cache. UI code (onboarding modal, traffic
 * deck target pickers) reads exclusively through this surface.
 */
export class SampleCatalogRegistry {
  private readonly items: SampleClusterCatalogItem[];
  private readonly cache = new Map<string, ClusterGraphData>();

  constructor(items: SampleClusterCatalogItem[] = SAMPLE_CATALOG) {
    this.items = [...items];
  }

  /** List every catalog entry (defensive copy; SPEC-10 §3). */
  listItems(): SampleClusterCatalogItem[] {
    return [...this.items];
  }

  /** Retrieve a catalog entry by id, or undefined when unknown. */
  getItem(id: string): SampleClusterCatalogItem | undefined {
    return this.items.find((item) => item.id === id);
  }

  /** Synchronous access to an already-hydrated topology (cache hit). */
  getCachedData(id: string): ClusterGraphData | undefined {
    return this.cache.get(id);
  }

  /**
   * Fetch (and memoize) the sample's full ClusterGraph JSON. First call
   * pays one same-origin static fetch; every subsequent call resolves from
   * the in-memory cache well inside the SPEC-10 §1 < 100 ms budget.
   */
  async fetchSampleData(id: string): Promise<ClusterGraphData> {
    const cached = this.cache.get(id);
    if (cached) return cached;

    const item = this.getItem(id);
    if (!item) {
      throw new Error(`Unknown sample catalog id: "${id}"`);
    }

    const response = await fetch(item.dataFile, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'omit',
    });
    if (!response.ok) {
      throw new Error(
        `Failed to fetch sample "${id}" (${response.status} ${response.statusText}) from ${item.dataFile}`,
      );
    }
    const data = (await response.json()) as ClusterGraphData;
    this.cache.set(id, data);
    return data;
  }

  /**
   * Warm the cache for the given ids (defaults to all samples) so the first
   * interactive load is instant. Failures are swallowed — the catalog must
   * never break bootstrapping.
   */
  async preload(ids?: string[]): Promise<void> {
    const targets = ids
      ? this.items.filter((item) => ids.includes(item.id))
      : this.items;
    await Promise.allSettled(targets.map((item) => this.fetchSampleData(item.id)));
  }
}

/** Shared process-wide catalog instance used by the onboarding modal. */
export const defaultSampleCatalog = new SampleCatalogRegistry();
