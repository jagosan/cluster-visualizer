/**
 * SPEC-10 / TASK-CV-1103: Client-Side Direct Kubernetes API Extractor.
 *
 * Zero-operator, zero-install cluster visualization for read-only bearer
 * tokens (SPEC-10 §2.1.2): the browser fetches the standard Kubernetes
 * discovery + resource endpoints directly —
 *
 *   GET /version
 *   GET /api/v1/nodes                                          (NodeList)
 *   GET /api/v1/pods                                           (PodList)
 *   GET /api/v1/services                                       (ServiceList)
 *   GET /apis/autoscaling/v2/horizontalpodautoscalers          (HPAList)
 *   GET /apis/autoscaling.k8s.io/v1/verticalpodautoscalers     (VPAList, optional)
 *
 * — and this module transforms the raw API JSON into the normalized
 * `ClusterGraphData` schema consumed by `ClusterViewport.setClusterData()`,
 * computing Skyscraper-convention spatial coordinates entirely in browser
 * memory.
 *
 * Layout conventions mirrored from src/ingestion/layout.py (elevation tiers,
 * worker-deck chassis math, pod capsule dimensions, staging-yard routing):
 *
 *   Elevation tiers: client 12.0 · aggregation 9.5 · apiserver 7.0 ·
 *     etcd vault 5.5 · supervisor 4.5 · framework 2.5 · worker deck 0.5 ·
 *     pod capsules ride the deck at Y = 0.75 · daemonset bays at Y = 0.65.
 *   Worker chassis: N nodes spaced WORKER_SPACING_X = 6.0 centered on X = 0;
 *     child bays offset relative to chassis center (kubelet -1.8,
 *     containerd -0.8, daemonset +1.2 / +2.0, pods ±0.6 stagger,
 *     Z front 0.2 / back 1.2).
 *   Pod capsule geometry (SPEC-09 §3.1): height = clamp(0.40 + 0.35√vCPU,
 *     0.40, 2.60); radius = clamp(0.20 + 0.12·log2(max(1,GiB)), 0.20, 0.90).
 *   Pending pods (phase=Pending / PodScheduled=False, SPEC-09 §4.2 ADR-02)
 *     never reach the deck: they hover in the exterior staging yard
 *     (X < -12.0, Y = 1.0) on the deterministic 4-column grid.
 *
 * Security (SPEC-10 §5 matrix): the bearer token is attached only to
 * same-request `Authorization` headers from the browser sandbox; nothing is
 * persisted, logged, or echoed into the produced graph.
 */

import type { ClusterGraphData, ClusterNodeData } from '../scene/cluster_viewport.js';
import { calculatePodDimensions } from '../scene/pod_capsules.js';
import { parseResourceQuantity } from '../scene/autoscaling_fx.js';
import type { AutoscalingStatusData } from '../scene/autoscaling_fx.js';
import type { MachineShapeData } from '../scene/layer_trays.js';

// ---------------------------------------------------------------------------
// Raw Kubernetes API response shapes (minimal structural subsets)
// ---------------------------------------------------------------------------

export interface K8sRawObjectMeta {
  name?: string;
  namespace?: string;
  uid?: string;
  labels?: Record<string, string>;
  annotations?: Record<string, string>;
  ownerReferences?: Array<{ kind?: string; name?: string; uid?: string }>;
  creationTimestamp?: string;
}

export interface K8sRawNode {
  metadata?: K8sRawObjectMeta;
  spec?: {
    podCIDR?: string;
    unschedulable?: boolean;
    taints?: Array<{ key?: string; value?: string; effect?: string }>;
    providerID?: string;
  };
  status?: {
    nodeInfo?: Record<string, string>;
    capacity?: Record<string, string>;
    allocatable?: Record<string, string>;
    addresses?: Array<{ type?: string; address?: string }>;
    conditions?: Array<{ type?: string; status?: string; reason?: string; message?: string }>;
    images?: Array<{ names?: string[]; sizeBytes?: number }>;
  };
}

export interface K8sRawContainer {
  name?: string;
  image?: string;
  resources?: {
    requests?: Record<string, string | number>;
    limits?: Record<string, string | number>;
  };
}

export interface K8sRawPod {
  metadata?: K8sRawObjectMeta;
  spec?: {
    nodeName?: string;
    phase?: string;
    serviceAccountName?: string;
    containers?: K8sRawContainer[];
    initContainers?: K8sRawContainer[];
  };
  status?: {
    phase?: string;
    hostIP?: string;
    podIP?: string;
    startTime?: string;
    containerStatuses?: Array<{
      name?: string;
      ready?: boolean;
      restartCount?: number;
      state?: Record<string, unknown>;
    }>;
    conditions?: Array<{ type?: string; status?: string; reason?: string }>;
  };
}

export interface K8sRawService {
  metadata?: K8sRawObjectMeta;
  spec?: {
    type?: string;
    clusterIP?: string;
    selector?: Record<string, string>;
    ports?: Array<{ name?: string; protocol?: string; port?: number; nodePort?: number }>;
    loadBalancerIP?: string;
    externalIPs?: string[];
  };
}

export interface K8sRawHPA {
  metadata?: K8sRawObjectMeta;
  spec?: {
    scaleTargetRef?: { kind?: string; name?: string };
    minReplicas?: number;
    maxReplicas?: number;
    targetCPUUtilizationPercentage?: number;
    metrics?: Array<{
      type?: string;
      resource?: {
        name?: string;
        target?: {
          type?: string;
          averageUtilization?: number;
          averageValue?: string;
        };
      };
    }>;
  };
  status?: {
    currentReplicas?: number;
    desiredReplicas?: number;
    currentCPUUtilizationPercentage?: number;
  };
}

/** autoscaling.k8s.io/v1 VerticalPodAutoscaler (optional endpoint). */
export interface K8sRawVPA {
  metadata?: K8sRawObjectMeta;
  spec?: {
    targetRef?: { kind?: string; name?: string };
    updatePolicy?: { updateMode?: string };
  };
  status?: {
    recommendation?: {
      containerRecommendations?: Array<{
        containerName?: string;
        target?: Record<string, string>;
        lowerBound?: Record<string, string>;
      }>;
    };
  };
}

export interface K8sListKind {
  apiVersion?: string;
  kind?: string;
  metadata?: { continue?: string; resourceVersion?: string };
  items?: unknown[];
}

/** Raw multi-endpoint response bundle handed to `extractClusterGraph`. */
export interface K8sApiRawBundle {
  nodes?: K8sRawNode[] | null;
  pods?: K8sRawPod[] | null;
  services?: K8sRawService[] | null;
  hpas?: K8sRawHPA[] | null;
  /** VPA objects from /apis/autoscaling.k8s.io/v1 (absent → no VPA layer). */
  vpas?: K8sRawVPA[] | null;
  /** Payload of GET /version (`{ major, minor, gitVersion, ... }`). */
  version?: { gitVersion?: string; major?: string; minor?: string } | null;
  /** Optional human label for metadata.cluster_name. */
  clusterName?: string;
  /** Cap on emitted graph edges (default 400) — guards huge fleets. */
  maxEdgesHint?: number;
}

/** Options accepted by `fetchAndExtractClusterGraph`. */
export interface ClientExtractorFetchOptions {
  /** Override the default 12 s per-request timeout. */
  timeoutMs?: number;
  /** Page NodeList/PodList via the `?continue=` token (default: true). */
  paginate?: boolean;
  /** Hard cap on graph edges emitted for huge clusters (default: 400). */
  maxEdges?: number;
}

// ---------------------------------------------------------------------------
// Skyscraper layout constants (mirror of src/ingestion/layout.py)
// ---------------------------------------------------------------------------

export const ELEVATION_TIERS = {
  client: 12.0,
  aggregation: 9.5,
  apiserver: 7.0,
  vault: 5.5,
  supervisor: 4.5,
  framework: 2.5,
  workerDeck: 0.5,
  computeChassis: -2.5,
  kroManifold: -4.8,
  cloudVault: -6.5,
  bedrockEgress: -10.5,
} as const;

export const WORKER_DECK_Y = ELEVATION_TIERS.workerDeck; // Y = 0.5
export const WORKER_SPACING_X = 6.0;
export const RUNTIME_BAY_OFFSET_X = -1.8;
export const CONTAINERD_OFFSET_X = -0.8;
export const DAEMONSET_BASE_OFFSET_X = 1.2;
export const DAEMONSET_SECOND_OFFSET_X = 2.0;
export const RUNTIME_Z = -1.5;
export const DAEMONSET_Z = -1.5;
export const DAEMONSET_Z_ALT = -0.5;
export const POD_Z_FRONT = 0.2;
export const POD_Z_BACK = 1.2;
export const POD_X_STAGGER = 0.6;
export const POD_Y = 0.75;
export const POD_DEFAULT_CPU_CORES = 0.5;
export const POD_DEFAULT_MEMORY_GIB = 1.0;

// Staging yard hover band (SPEC-09 §4.2 / ADR-02) — X < -12.0 exterior.
export const PENDING_HOVER_Y = 1.0;
export const PENDING_HOVER_X_MIN = -22.0;
export const PENDING_HOVER_X_MAX = -14.0;
export const PENDING_HOVER_Z_MIN = -6.0;
export const PENDING_HOVER_Z_MAX = 6.0;
export const PENDING_HOVER_COLS = 4;
export const PENDING_HOVER_SPACING = 2.0;

// Control-plane component X anchors (layout.py supervisor / framework rows).
const SCHEDULER_X_START = -2.8;
const SCHEDULER_X_STEP = 1.5;
const CONTROLLER_X_START = 2.8;
const CONTROLLER_X_STEP = 1.5;
const CONTROL_PLANE_ETCD_Z = -3.5;
const SUPERVISOR_Z = 0.8;

/** Fallback requests for pods without explicit resource.requests. */
export const CLIENT_CLIENT_HORIZON_ID = 'client/client-kubectl';

// ---------------------------------------------------------------------------
// Pure helpers (exported for TASK-CV-1106 unit tests)
// ---------------------------------------------------------------------------

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
}

/** Centered worker-deck chassis X positions for N nodes (layout.py §7). */
export function computeWorkerChassisPositions(count: number): number[] {
  const n = Math.max(Math.floor(count), 1);
  const positions: number[] = [];
  for (let i = 0; i < n; i++) {
    positions.push(-((n - 1) * WORKER_SPACING_X) / 2 + i * WORKER_SPACING_X);
  }
  return positions;
}

/**
 * Stage a pending pod into the exterior staging yard hover band
 * (mirror of layout.stage_pending_pod): deterministic 4-column grid inside
 * X in [-22, -14], Z in [-6, +6], Y = 1.0. Mutates `node.spatial` and its
 * pod_geometry.staging_track_x in place.
 */
export function stagePendingPod(node: ClusterNodeData, index: number): { x: number; y: number; z: number } {
  const col = index % PENDING_HOVER_COLS;
  const row = Math.floor(index / PENDING_HOVER_COLS);
  const x = clamp(PENDING_HOVER_X_MIN + col * PENDING_HOVER_SPACING, PENDING_HOVER_X_MIN, PENDING_HOVER_X_MAX);
  const z = clamp(PENDING_HOVER_Z_MIN + (row % 7) * PENDING_HOVER_SPACING, PENDING_HOVER_Z_MIN, PENDING_HOVER_Z_MAX);
  node.spatial.x = Math.round(x * 1000) / 1000;
  node.spatial.y = PENDING_HOVER_Y;
  node.spatial.z = Math.round(z * 1000) / 1000;
  if (node.pod_geometry) node.pod_geometry.staging_track_x = node.spatial.x;
  return { x: node.spatial.x, y: node.spatial.y, z: node.spatial.z };
}

/** Sum container CPU requests (cores) for a raw pod. */
export function sumPodCpuRequests(pod: K8sRawPod): number {
  const containers = [...(pod.spec?.containers ?? []), ...(pod.spec?.initContainers ?? [])];
  let cpu = 0;
  for (const c of containers) {
    const v = parseResourceQuantity(c.resources?.requests?.cpu ?? null, 'cpu');
    if (v !== null) cpu = Math.max(cpu, v); // effective request ≈ max(init, app) like K8s scheduling
  }
  return cpu;
}

/** Sum container memory requests (GiB) for a raw pod. */
export function sumPodMemoryRequests(pod: K8sRawPod): number {
  const containers = [...(pod.spec?.containers ?? []), ...(pod.spec?.initContainers ?? [])];
  let mem = 0;
  for (const c of containers) {
    const v = parseResourceQuantity(c.resources?.requests?.memory ?? null, 'memory');
    if (v !== null) mem = Math.max(mem, v);
  }
  return mem;
}

/** True when a raw pod is unscheduled (SPEC-09 §4.2 pending definition). */
export function isRawPodPending(pod: K8sRawPod): boolean {
  const phase = (pod.status?.phase ?? pod.spec?.phase ?? '').toLowerCase();
  if (phase === 'pending') return true;
  const cond = (pod.status?.conditions ?? []).find((c) => c.type === 'PodScheduled');
  return cond !== undefined && cond.status === 'False';
}

/** Map a raw pod onto the Healthy / Degraded / Failed status taxonomy. */
export function podStatusFromPhase(pod: K8sRawPod): string {
  const phase = (pod.status?.phase ?? '').toLowerCase();
  if (phase === 'failed' || phase === 'succeeded') return phase === 'failed' ? 'Failed' : 'Healthy';
  const restarts = (pod.status?.containerStatuses ?? []).reduce((a, c) => a + (c.restartCount ?? 0), 0);
  const waitingCrash = (pod.status?.containerStatuses ?? []).some((c) => {
    const state = c.state as Record<string, unknown> | undefined;
    const reason = String((state?.['waiting'] as Record<string, unknown> | undefined)?.reason ?? '');
    return /crash|backoff|error/i.test(reason);
  });
  if (waitingCrash || restarts >= 5) return 'Failed';
  if (phase !== 'running' || restarts > 0) return 'Degraded';
  return 'Healthy';
}

/** Detect the distribution flavor from node labels (SPEC-10 §3 metadata). */
export function detectDistribution(nodes: K8sRawNode[]): string {
  const labels = nodes.flatMap((n) => Object.keys(n.metadata?.labels ?? {}));
  const joined = labels.join(',');
  if (joined.includes('cloud.google.com/gke-nodepool') || joined.includes('cloud.google.com/gke-compute-class')) return 'gke';
  if (joined.includes('eks.amazonaws.com')) return 'eks';
  if (joined.includes('kubernetes.azure.com')) return 'aks';
  if (joined.includes('karpenter.sh')) return 'karpenter-managed';
  if (joined.length === 0) return 'unknown';
  return 'upstream-oss';
}

/** True when a name denotes a DaemonSet-style node agent (layout.py §_is_daemonset). */
export function isDaemonAgentName(name: string): boolean {
  const lower = name.toLowerCase();
  return ['proxy', 'cilium', 'calico', 'flannel', 'weave', 'node-exporter', 'agent'].some((kw) => lower.includes(kw));
}

/** Match a Service selector map against pod labels (subset semantics). */
export function selectorMatchesPod(selector: Record<string, string> | undefined, podLabels: Record<string, string>): boolean {
  if (!selector) return false;
  const entries = Object.entries(selector);
  if (entries.length === 0) return false;
  return entries.every(([k, v]) => podLabels[k] === v);
}

/** HPA target CPU utilization percent (v2 metrics[] or v1 legacy field). */
export function hpaTargetCpuPercent(hpa: K8sRawHPA): number | null {
  const resourceMetric = (hpa.spec?.metrics ?? []).find(
    (m) => (m.type ?? '').toLowerCase() === 'resource' && (m.resource?.name ?? '') === 'cpu',
  );
  const util = resourceMetric?.resource?.target?.averageUtilization;
  if (typeof util === 'number' && Number.isFinite(util)) return util;
  const legacy = hpa.spec?.targetCPUUtilizationPercentage;
  return typeof legacy === 'number' && Number.isFinite(legacy) ? legacy : null;
}

/** Aggregate VPA recommendation target (cpu cores, memory GiB) or null. */
export function vpaRecommendation(vpa: K8sRawVPA): { cpu: number | null; memory: number | null } | null {
  const recs = vpa.status?.recommendation?.containerRecommendations ?? [];
  if (recs.length === 0) return null;
  let cpu: number | null = null;
  let memory: number | null = null;
  for (const rec of recs) {
    const c = parseResourceQuantity(rec.target?.cpu ?? null, 'cpu');
    const m = parseResourceQuantity(rec.target?.memory ?? null, 'memory');
    if (c !== null) cpu = (cpu ?? 0) + c;
    if (m !== null) memory = (memory ?? 0) + m;
  }
  if (cpu === null && memory === null) return null;
  return { cpu, memory };
}

// ---------------------------------------------------------------------------
// Categorization helpers
// ---------------------------------------------------------------------------

interface CategorizedPod {
  node: ClusterNodeData;
  raw: K8sRawPod;
}

type PodCategory =
  | 'apiserver'
  | 'etcd'
  | 'scheduler'
  | 'controller'
  | 'framework'
  | 'daemonset'
  | 'workload';

/**
 * Name-based categorization mirroring layout.apply_spatial_layout's
 * classifier order (apiserver before etcd before scheduler before
 * controller before framework ray/spark before DaemonSet agents).
 */
function categorizePod(node: ClusterNodeData): PodCategory {
  const name = node.name.toLowerCase();
  if (name.includes('apiserver') || name.includes('api-server')) return 'apiserver';
  if (name.includes('etcd')) return 'etcd';
  if (name.includes('scheduler') || name.includes('kube-scheduler')) return 'scheduler';
  if (name.includes('controller-manager') || name.includes('controllermanager')) return 'controller';
  if (name.includes('ray') || name.includes('spark')) return 'framework';
  if (isDaemonAgentName(node.name)) return 'daemonset';
  return 'workload';
}

/** Deployment-family name of a pod (`frontend-abc12-x2z` -> `frontend`). */
function deploymentFamilyName(name: string): string {
  let base = name;
  // strip pod replica-set suffix `-(hash)-(suffix)` chunks conservatively
  const match = base.match(/^(.*?)-(?:[0-9a-f]{8,10}|[0-9]+)(?:-[0-9a-z]{4,5})?$/i);
  if (match?.[1]) base = match[1];
  return base.toLowerCase();
}

// ---------------------------------------------------------------------------
// Core transformation
// ---------------------------------------------------------------------------

const MAX_EDGES_DEFAULT = 400;

/**
 * Transform a raw Kubernetes API response bundle into a fully-laid-out
 * `ClusterGraphData` (SPEC-10 §2.1.2, TASK-CV-1103).
 *
 * Deterministic: identical bundles always produce identical coordinates so
 * snapshot refreshes don't scatter the scene.
 */
export function extractClusterGraph(apiResponses: K8sApiRawBundle): ClusterGraphData {
  const maxEdges = apiResponses.maxEdgesHint ?? MAX_EDGES_DEFAULT;
  const rawNodes = apiResponses.nodes ?? [];
  const rawPods = apiResponses.pods ?? [];
  const rawServices = apiResponses.services ?? [];
  const rawHpas = apiResponses.hpas ?? [];
  const rawVpas = apiResponses.vpas ?? [];

  const edges: ClusterGraphData['edges'] = [];
  let edgesTruncated = false;
  const addEdge = (edge: ClusterGraphData['edges'][number]): void => {
    if (edges.length >= maxEdges) {
      edgesTruncated = true;
      return;
    }
    edges.push(edge);
  };

  // -- 1. Node chassis -----------------------------------------------------
  const workerNodes: ClusterNodeData[] = [];
  const graphNodes: ClusterNodeData[] = [];

  for (const raw of rawNodes) {
    const name = raw.metadata?.name ?? 'unknown-node';
    const conditions = raw.status?.conditions ?? [];
    const ready = conditions.find((c) => c.type === 'Ready');
    const status = ready?.status === 'True' ? 'Healthy' : ready ? 'Degraded' : 'Unknown';
    const labels = raw.metadata?.labels ?? {};
    const isControlPlane =
      Object.keys(labels).some((k) => k.endsWith('/master') || k.endsWith('/control-plane')) ||
      (raw.spec?.taints ?? []).some((t) => (t.key ?? '') === 'node-role.kubernetes.io/control-plane');

    const node: ClusterNodeData = {
      id: `node/${name}`,
      layer: 'node',
      kind: 'Node',
      name,
      namespace: 'cluster',
      version: raw.status?.nodeInfo?.kubeletVersion ?? apiResponses.version?.gitVersion ?? 'v1.0.0',
      image: raw.status?.nodeInfo?.osImage,
      digest: undefined,
      status,
      metrics: {
        cpu_capacity: raw.status?.capacity?.cpu ?? null,
        memory_capacity: raw.status?.capacity?.memory ?? null,
        cpu_allocatable: raw.status?.allocatable?.cpu ?? null,
        memory_allocatable: raw.status?.allocatable?.memory ?? null,
        os_image: raw.status?.nodeInfo?.osImage ?? null,
        internal_ip: (raw.status?.addresses ?? []).find((a) => a.type === 'InternalIP')?.address ?? null,
        unschedulable: raw.spec?.unschedulable === true,
        control_plane: isControlPlane,
      },
      // Provisional — real chassis X assigned in step 4.
      spatial: { x: 0, y: WORKER_DECK_Y, z: 0, asset_type: 'LayerTray_Worker' },
      pod_geometry: null,
    };
    workerNodes.push(node);
    graphNodes.push(node);
  }

  // -- 2. Synthetic kubelet + containerd bays per worker chassis ------------
  // The raw API exposes no Kubelet/Containerd objects (they are processes,
  // not resources); synthesize them exactly like the exporter fixtures so
  // heartbeat conduits and runtime bays render identically client-side.
  for (const host of workerNodes) {
    const kubeletId = `node/${host.name}/kubelet`;
    graphNodes.push({
      id: kubeletId,
      layer: 'node',
      kind: 'Kubelet',
      name: `kubelet-${host.name}`,
      namespace: 'cluster',
      version: host.version,
      status: host.status,
      metrics: { parent_node: host.name },
      spatial: { x: 0, y: 0.7, z: RUNTIME_Z, asset_type: 'Cuboid_Kubelet' },
    });
    graphNodes.push({
      id: `node/${host.name}/containerd`,
      layer: 'node',
      kind: 'Containerd',
      name: `containerd-${host.name}`,
      namespace: 'cluster',
      version: host.version,
      status: host.status,
      metrics: { parent_node: host.name },
      spatial: { x: 0, y: 0.7, z: RUNTIME_Z, asset_type: 'Cuboid_Containerd' },
    });
  }

  // -- 3. Pods → proportional capsules, control-plane tiers, staging yard ---
  const categorised: CategorizedPod[] = [];

  const sortedPods = [...rawPods].sort(
    (a, b) =>
      `${a.metadata?.namespace ?? ''}/${a.metadata?.name ?? ''}`.localeCompare(
        `${b.metadata?.namespace ?? ''}/${b.metadata?.name ?? ''}`,
      ),
  );

  for (const raw of sortedPods) {
    const name = raw.metadata?.name ?? 'unknown-pod';
    const namespace = raw.metadata?.namespace ?? 'default';
    const cpuCores = Math.max(sumPodCpuRequests(raw), 0) || POD_DEFAULT_CPU_CORES;
    const memoryGib = Math.max(sumPodMemoryRequests(raw), 0) || POD_DEFAULT_MEMORY_GIB;
    const dims = calculatePodDimensions(cpuCores, memoryGib);
    // Round to 3 decimals so browser-side coordinates are byte-identical to
    // the Python ingestion mirror (layout.calculate_pod_dimensions).
    const height = Math.round(dims.height * 1000) / 1000;
    const radius = Math.round(dims.radius * 1000) / 1000;
    const isPending = isRawPodPending(raw);
    const hostName = raw.spec?.nodeName ?? '';

    const node: ClusterNodeData = {
      id: `pod/${namespace}/${name}`,
      layer: 'workload',
      kind: 'Pod',
      name,
      namespace,
      version: apiResponses.version?.gitVersion ?? 'v1.0.0',
      image: raw.spec?.containers?.[0]?.image,
      status: podStatusFromPhase(raw),
      metrics: {
        cpu_request_cores: Math.round(cpuCores * 1000) / 1000,
        memory_request_gib: Math.round(memoryGib * 1000) / 1000,
        phase: raw.status?.phase ?? 'Unknown',
        pending: isPending,
        scheduled: !isPending,
        host_node: hostName || null,
        pod_ip: raw.status?.podIP ?? null,
        restart_count: (raw.status?.containerStatuses ?? []).reduce((a, c) => a + (c.restartCount ?? 0), 0),
      },
      spatial: { x: 0, y: POD_Y, z: POD_Z_FRONT, asset_type: 'Cuboid_Pod' },
      pod_geometry: {
        height,
        radius,
        is_pending: isPending,
        staging_track_x: null,
        karpenter_target_node_claim: null,
        kueue_workload: null,
      },
    };

    categorised.push({ node, raw });
    graphNodes.push(node);
  }

  // -- 4. Worker deck placement (chassis row + child bays) ------------------
  const chassisX = computeWorkerChassisPositions(workerNodes.length);
  for (let i = 0; i < workerNodes.length; i++) {
    const x = chassisX[i] ?? 0;
    const host = workerNodes[i]!;
    host.spatial.x = Math.round(x * 1000) / 1000;
    host.spatial.y = WORKER_DECK_Y;
    host.spatial.z = 0;
    // Child bays follow their chassis.
    const kubelet = graphNodes.find((n) => n.id === `node/${host.name}/kubelet` && n.kind === 'Kubelet');
    const containerd = graphNodes.find((n) => n.id === `node/${host.name}/containerd` && n.kind === 'Containerd');
    if (kubelet) {
      kubelet.spatial.x = Math.round((x + RUNTIME_BAY_OFFSET_X) * 1000) / 1000;
    }
    if (containerd) {
      containerd.spatial.x = Math.round((x + CONTAINERD_OFFSET_X) * 1000) / 1000;
    }
  }

  // Categorize pods and place by tier.
  const byCategory = new Map<PodCategory, CategorizedPod[]>();
  for (const entry of categorised) {
    const cat = categorizePod(entry.node);
    const bucket = byCategory.get(cat);
    if (bucket) bucket.push(entry);
    else byCategory.set(cat, [entry]);
  }

  const apiservers = byCategory.get('apiserver') ?? [];
  const etcds = byCategory.get('etcd') ?? [];
  const schedulers = byCategory.get('scheduler') ?? [];
  const controllers = byCategory.get('controller') ?? [];
  const frameworks = byCategory.get('framework') ?? [];
  const daemonsets = byCategory.get('daemonset') ?? [];
  const workloadPodsAll = byCategory.get('workload') ?? [];

  // Control-plane tiers.
  placeRow(apiservers.map((c) => entryNode(c)), ELEVATION_TIERS.apiserver, 0.0, 2.4, 'Cuboid_APIServer');
  placeRow(etcds.map((c) => entryNode(c)), ELEVATION_TIERS.vault, CONTROL_PLANE_ETCD_Z, 2.2, 'Cuboid_etcd');
  schedulers.forEach((c, i) => {
    const n = entryNode(c);
    n.spatial.x = Math.round((SCHEDULER_X_START - i * SCHEDULER_X_STEP) * 1000) / 1000;
    n.spatial.y = ELEVATION_TIERS.supervisor;
    n.spatial.z = SUPERVISOR_Z;
    n.spatial.asset_type = 'Cuboid_Supervisor';
  });
  controllers.forEach((c, i) => {
    const n = entryNode(c);
    n.spatial.x = Math.round((CONTROLLER_X_START + i * CONTROLLER_X_STEP) * 1000) / 1000;
    n.spatial.y = ELEVATION_TIERS.supervisor;
    n.spatial.z = SUPERVISOR_Z;
    n.spatial.asset_type = 'Cuboid_Supervisor';
  });

  // Framework extension floor (Ray head row left, workers right — layout.py §6).
  const rayHeads = frameworks.filter((c) => entryNode(c).name.toLowerCase().includes('head'));
  const rayWorkers = frameworks.filter((c) => !entryNode(c).name.toLowerCase().includes('head'));
  rayHeads.forEach((c, i) => {
    const n = entryNode(c);
    n.spatial.x = Math.round((-2.0 - i * 1.6) * 1000) / 1000;
    n.spatial.y = ELEVATION_TIERS.framework;
    n.spatial.z = 0;
    n.spatial.asset_type = 'Cuboid_Ray';
  });
  rayWorkers.forEach((c, i) => {
    const n = entryNode(c);
    n.spatial.x = Math.round((0.2 + i * 1.6) * 1000) / 1000;
    n.spatial.y = ELEVATION_TIERS.framework;
    n.spatial.z = 0;
    n.spatial.asset_type = n.name.toLowerCase().includes('ray') ? 'Cuboid_Ray' : 'Framework_Spark';
  });

  // DaemonSet bays: round-robin across chassis, 0/1/2+ slot stacking.
  const N = chassisX.length;
  const dsCounts = new Map<number, number>();
  daemonsets.forEach((c, i) => {
    const n = entryNode(c);
    const chassisIdx = i % N;
    const count = dsCounts.get(chassisIdx) ?? 0;
    let offsetX: number;
    let z: number;
    if (count === 0) {
      offsetX = DAEMONSET_BASE_OFFSET_X;
      z = DAEMONSET_Z;
    } else if (count === 1) {
      offsetX = DAEMONSET_SECOND_OFFSET_X;
      z = DAEMONSET_Z;
    } else {
      offsetX = DAEMONSET_BASE_OFFSET_X;
      z = DAEMONSET_Z_ALT;
    }
    dsCounts.set(chassisIdx, count + 1);
    const cx = chassisX[chassisIdx] ?? 0;
    n.spatial.x = Math.round((cx + offsetX) * 1000) / 1000;
    n.spatial.y = 0.65;
    n.spatial.z = z;
    n.spatial.asset_type = 'Cuboid_DaemonSet';
  });

  // Workload pods: pending → staging yard hover band; running → 4-slot
  // front/back grid on the parent chassis (or round-robin when unassigned).
  const podSlotsPerChassis = new Map<number, number>();
  let stagedPendingCount = 0;
  const scheduledWorkload = workloadPodsAll.filter((c) => entryNode(c).pod_geometry?.is_pending !== true);
  const pendingWorkload = workloadPodsAll.filter((c) => entryNode(c).pod_geometry?.is_pending === true);

  // Preserve parent-node affinity: pods pinned to a known worker chassis on
  // that chassis; unassigned pods round-robin across the deck.
  let unassignedCursor = 0;
  scheduledWorkload.forEach((c) => {
    const n = entryNode(c);
    const host = String(n.metrics?.host_node ?? '');
    const hostIndex = workerNodes.findIndex((w) => w.name === host);
    const chassisIdx = hostIndex >= 0 ? hostIndex : unassignedCursor++ % N;
    const slot = podSlotsPerChassis.get(chassisIdx) ?? 0;
    podSlotsPerChassis.set(chassisIdx, slot + 1);
    const slotIdx = slot % 4;
    const offsetX = slotIdx % 2 === 0 ? -POD_X_STAGGER : POD_X_STAGGER;
    const z = slotIdx < 2 ? POD_Z_FRONT : POD_Z_BACK;
    const cx = chassisX[chassisIdx] ?? 0;
    n.spatial.x = Math.round((cx + offsetX) * 1000) / 1000;
    n.spatial.y = POD_Y;
    n.spatial.z = z;
    n.spatial.asset_type = podAssetType(n.name);
  });

  for (const c of pendingWorkload) {
    stagePendingPod(entryNode(c), stagedPendingCount);
    stagedPendingCount += 1;
  }

  // -- 5. Service endpoint nodes + selector edges ---------------------------
  const serviceNodes: ClusterNodeData[] = [];
  const cappedServices = rawServices
    .filter((s) => (s.metadata?.name ?? '') !== 'kubernetes')
    .slice(0, 24);
  cappedServices.forEach((svc, i) => {
    const name = svc.metadata?.name ?? 'service';
    const namespace = svc.metadata?.namespace ?? 'default';
    const node: ClusterNodeData = {
      id: `svc/${namespace}/${name}`,
      layer: 'aggregation',
      kind: 'Service',
      name,
      namespace,
      version: svc.spec?.type ?? 'ClusterIP',
      status: 'Healthy',
      metrics: {
        service_type: svc.spec?.type ?? 'ClusterIP',
        cluster_ip: svc.spec?.clusterIP ?? null,
        ports: (svc.spec?.ports ?? []).map((p) => p.port).filter((p): p is number => typeof p === 'number'),
      },
      spatial: {
        x: Math.round(((i - (cappedServices.length - 1) / 2) * 2.5) * 1000) / 1000,
        y: ELEVATION_TIERS.aggregation,
        z: 2.4,
        asset_type: 'LayerTray_Control',
      },
    };
    serviceNodes.push(node);
    graphNodes.push(node);
  });

  // -- 6. Autoscaling metadata (HPA + VPA) ----------------------------------
  applyHpaMetadata(categorised, rawHpas);
  applyVpaMetadata(categorised, rawVpas);

  // -- 7. Edges --------------------------------------------------------------
  const apiserverIds = apiservers.map((c) => entryNode(c).id);
  const etcdIds = etcds.map((c) => entryNode(c).id);
  const firstApiserver = apiserverIds[0] ?? null;

  // Synthetic client-horizon anchor (kubectl / this extraction session).
  const clientNode: ClusterNodeData = {
    id: CLIENT_CLIENT_HORIZON_ID,
    layer: 'ingress',
    kind: 'Client',
    name: 'kubectl-cli',
    namespace: 'client',
    version: apiResponses.version?.gitVersion ?? 'v1.0.0',
    status: 'Healthy',
    metrics: { source: 'client-side-extractor' },
    spatial: { x: 0, y: ELEVATION_TIERS.client, z: 6.0, asset_type: 'Client_Slab' },
  };
  graphNodes.push(clientNode);
  if (firstApiserver) {
    addEdge({
      source: clientNode.id,
      target: firstApiserver,
      flow_type: 'traffic',
      protocol: 'HTTPS/443',
      direction: 'unidirectional',
      volume_label: 'client-direct extraction',
    });
  }

  // apiserver <-> etcd raft KV
  for (const a of apiserverIds.slice(0, 3)) {
    for (const e of etcdIds.slice(0, 3)) {
      addEdge({ source: a, target: e, flow_type: 'control_plane', protocol: 'gRPC/2379', direction: 'bidirectional', volume_label: 'raft KV' });
    }
  }

  // scheduler / controller reconcile loops
  for (const c of [...schedulers, ...controllers]) {
    if (!firstApiserver) break;
    addEdge({
      source: entryNode(c).id,
      target: firstApiserver,
      flow_type: 'control_plane',
      protocol: 'HTTPS/6443',
      direction: 'bidirectional',
      volume_label: 'reconcile loop',
    });
  }

  // kubelet lease heartbeats
  if (firstApiserver) {
    for (const host of workerNodes) {
      addEdge({
        source: `node/${host.name}/kubelet`,
        target: firstApiserver,
        flow_type: 'control_plane',
        protocol: 'HTTPS/6443/Heartbeat',
        direction: 'unidirectional',
        volume_label: 'lease heartbeat',
      });
    }
  }

  // Service selector → backend pod edges (capped 6 per service).
  if (serviceNodes.length > 0) {
    const podEntries = categorised;
    for (let i = 0; i < cappedServices.length; i++) {
      const svc = cappedServices[i];
      const svcNode = serviceNodes[i];
      if (!svc || !svcNode) continue;
      const selector = svc.spec?.selector;
      if (!selector) continue;
      let attached = 0;
      for (const entry of podEntries) {
        if (attached >= 6) break;
        const n = entryNode(entry);
        if (n.namespace !== (svc.metadata?.namespace ?? 'default')) continue;
        const podLabels = entry.raw.metadata?.labels ?? {};
        if (!selectorMatchesPod(selector, podLabels)) continue;
        attached += 1;
        const port = svc.spec?.ports?.[0]?.port;
        addEdge({
          source: svcNode.id,
          target: n.id,
          flow_type: 'traffic',
          protocol: port ? `TCP/${port}` : 'TCP',
          direction: 'unidirectional',
          volume_label: `${svc.spec?.type ?? 'ClusterIP'} backend`,
        });
      }
    }
  }

  // HPA → target pod control edges.
  for (const hpa of rawHpas.slice(0, 12)) {
    const targetName = (hpa.spec?.scaleTargetRef?.name ?? '').toLowerCase();
    if (!targetName) continue;
    const targets = categorised
      .map((c) => entryNode(c))
      .filter((n) => n.kind === 'Pod' && n.name.toLowerCase().includes(targetName))
      .slice(0, 3);
    if (!firstApiserver || targets.length === 0) continue;
    for (const t of targets) {
      addEdge({
        source: firstApiserver,
        target: t.id,
        flow_type: 'control_plane',
        protocol: 'HTTPS/6443',
        direction: 'unidirectional',
        volume_label: `hpa ${hpa.metadata?.name ?? ''}`.trim(),
      });
    }
  }

  // Lateral CNI mesh among DaemonSet agents (full mesh while small).
  const dsIds = daemonsets.map((c) => entryNode(c).id);
  if (dsIds.length > 1 && dsIds.length <= 10) {
    for (let i = 0; i < dsIds.length; i++) {
      for (let j = i + 1; j < dsIds.length; j++) {
        addEdge({
          source: dsIds[i]!,
          target: dsIds[j]!,
          flow_type: 'traffic',
          protocol: 'eBPF/Mesh',
          direction: 'bidirectional',
          volume_label: 'lateral CNI mesh',
        });
      }
    }
  }

  // -- 8. SPEC-08 machine shapes from node capacity + labels -----------------
  const machineShapes: MachineShapeData[] = workerNodes.map((n) => {
    const raw = rawNodes.find((r) => (r.metadata?.name ?? '') === n.name);
    const labels = raw?.metadata?.labels ?? {};
    const gpuCount = Number(labels['aliyun.com/gpu-count'] ?? raw?.status?.capacity?.['nvidia.com/gpu'] ?? 0) || 0;
    return {
      node_name: n.name,
      instance_type:
        labels['node.kubernetes.io/instance-type'] ??
        labels['cloud.gardener.cn/ccloud/instance-type'] ??
        labels['beta.kubernetes.io/instance-type'] ??
        'unknown',
      compute_class:
        labels['cloud.google.com/gke-compute-class'] ??
        labels['karpenter.sh/nodepool'] ??
        labels['cloud.google.com/gke-nodepool'] ??
        undefined,
      vcpus: Math.round(parseResourceQuantity(raw?.status?.capacity?.cpu ?? '0', 'cpu') ?? 0),
      memory_gib: Math.round(parseResourceQuantity(raw?.status?.capacity?.memory ?? '0', 'memory') ?? 0),
      capacity_type: (labels['cloud.google.com/spot'] ?? labels['karpenter.sh/capacity-type'] ?? '') === 'spot' ? 'spot' : 'on-demand',
      zone: labels['topology.kubernetes.io/zone'] ?? labels['failure-domain.beta.kubernetes.io/zone'] ?? 'unknown',
      accelerator_type: gpuCount > 0 ? 'nvidia-gpu' : undefined,
      accelerator_count: gpuCount,
    };
  });

  // -- 9. Metadata ------------------------------------------------------------
  const versionString =
    apiResponses.version?.gitVersion ??
    workerNodes[0]?.version ??
    'v1.0.0';

  const graph: ClusterGraphData = {
    metadata: {
      cluster_name: apiResponses.clusterName?.trim() || deriveClusterName(apiResponses),
      kubernetes_version: versionString,
      distribution: detectDistribution(rawNodes),
      node_count: workerNodes.length,
      pod_count: sortedPods.length,
    },
    nodes: graphNodes,
    edges,
    machine_shapes: machineShapes.length > 0 ? machineShapes : undefined,
  };

  if (edgesTruncated) {
    (graph.metadata as Record<string, unknown>)['edges_truncated'] = true;
  }
  return graph;
}

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

function entryNode(entry: CategorizedPod): ClusterNodeData {
  return entry.node;
}

function placeRow(nodes: ClusterNodeData[], y: number, z: number, spacing: number, assetType: string): void {
  const n = nodes.length;
  if (n === 0) return;
  nodes.forEach((node, i) => {
    node.spatial.x = Math.round(((i - (n - 1) / 2) * spacing) * 1000) / 1000;
    node.spatial.y = y;
    node.spatial.z = z;
    node.spatial.asset_type = assetType;
  });
}

function podAssetType(name: string): string {
  const lower = name.toLowerCase();
  if (lower.includes('postgres')) return 'Database_Postgres';
  if (lower.includes('redis') || lower.includes('memcached')) return 'Cache_Redis';
  if (lower.includes('ray')) return 'Cuboid_Ray';
  if (lower.includes('spark')) return 'Framework_Spark';
  return 'Cuboid_Pod';
}

function deriveClusterName(bundle: K8sApiRawBundle): string {
  const firstZone = (bundle.nodes ?? [])
    .flatMap((n) => Object.entries(n.metadata?.labels ?? {}))
    .find(([k]) => k === 'topology.kubernetes.io/zone');
  if (firstZone) return `k8s-${firstZone[1]}`;
  const firstNode = bundle.nodes?.[0]?.metadata?.name;
  if (firstNode) return `k8s-${firstNode}`;
  return 'client-side-cluster';
}

/** Attach HPA status to every pod of the target deployment family. */
function applyHpaMetadata(pods: CategorizedPod[], hpas: K8sRawHPA[]): void {
  if (hpas.length === 0) return;
  for (const entry of pods) {
    const n = entryNode(entry);
    if (n.kind !== 'Pod') continue;
    const family = deploymentFamilyName(n.name);
    const podLabels = entry.raw.metadata?.labels ?? {};
    for (const hpa of hpas) {
      const target = (hpa.spec?.scaleTargetRef?.name ?? '').toLowerCase();
      if (!target) continue;
      const matches =
        family === target ||
        family.startsWith(`${target}-`) ||
        n.name.toLowerCase().startsWith(target) ||
        selectorMatchesPod(
          (hpa.spec as unknown as { selector?: Record<string, string> } | undefined)?.selector,
          podLabels,
        );
      if (!matches) continue;
      const cpuPct = hpaTargetCpuPercent(hpa);
      const current = hpa.status?.currentReplicas ?? hpa.spec?.minReplicas ?? 1;
      const desired = hpa.status?.desiredReplicas ?? current;
      const as: AutoscalingStatusData = {
        ...(n.autoscaling ?? {}),
        has_hpa: true,
        current_replicas: current,
        desired_replicas: desired,
        target_metric: cpuPct !== null ? `cpu:${cpuPct}` : null,
      };
      n.autoscaling = as;
      break;
    }
  }
}

/** Attach VPA recommendation + in-place-resize flag to matching pods. */
function applyVpaMetadata(pods: CategorizedPod[], vpas: K8sRawVPA[]): void {
  if (vpas.length === 0) return;
  for (const entry of pods) {
    const n = entryNode(entry);
    if (n.kind !== 'Pod') continue;
    const family = deploymentFamilyName(n.name);
    const podLabels = entry.raw.metadata?.labels ?? {};
    for (const vpa of vpas) {
      const target = (vpa.spec?.targetRef?.name ?? '').toLowerCase();
      if (!target) continue;
      const matches =
        family === target ||
        family.startsWith(`${target}-`) ||
        n.name.toLowerCase().startsWith(target) ||
        selectorMatchesPod(
          (vpa.spec as unknown as { selector?: Record<string, string> } | undefined)?.selector,
          podLabels,
        );
      if (!matches) continue;
      const rec = vpaRecommendation(vpa);
      const autoMode = (vpa.spec?.updatePolicy?.updateMode ?? '').toLowerCase() === 'auto';
      const curCpu = Number(n.metrics?.cpu_request_cores ?? 0);
      const curMem = Number(n.metrics?.memory_request_gib ?? 0);
      const differs =
        rec !== null &&
        ((rec.cpu !== null && Math.abs(rec.cpu - curCpu) > 1e-9) ||
          (rec.memory !== null && Math.abs(rec.memory - curMem) > 1e-9));
      const as: AutoscalingStatusData = {
        ...(n.autoscaling ?? {}),
        has_vpa: true,
        vpa_target_cpu: rec?.cpu !== null && rec?.cpu !== undefined ? String(rec.cpu) : null,
        vpa_target_memory: rec?.memory !== null && rec?.memory !== undefined ? `${rec.memory}Gi` : null,
        is_resizing_in_place: autoMode && differs,
      };
      n.autoscaling = as;
      break;
    }
  }
}

// ---------------------------------------------------------------------------
// Fetch helper
// ---------------------------------------------------------------------------

/** Normalized API base: trims trailing slashes and a trailing `/api` segment. */
function normalizeApiBase(apiBaseUrl: string): string {
  let base = apiBaseUrl.trim().replace(/\s+$/, '');
  base = base.replace(/\/+$/, '');
  // Tolerate users pasting ".../api" or "http://host:8001/api/v1" prefixes.
  base = base.replace(/\/api\/v1$/, '');
  base = base.replace(/\/api$/, '');
  base = base.replace(/\/+$/, '');
  return base;
}

async function fetchJson<T>(url: string, token: string | undefined, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(url, { method: 'GET', headers, signal: controller.signal, credentials: 'omit' });
    if (!res.ok) {
      const detail =
        res.status === 401 || res.status === 403
          ? `HTTP ${res.status} — token rejected or forbidden for ${new URL(url).pathname}`
          : `HTTP ${res.status} from ${new URL(url).pathname}`;
      throw new Error(detail);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

async function fetchList<T>(base: string, path: string, token: string | undefined, opts: Required<ClientExtractorFetchOptions>): Promise<T[]> {
  const items: T[] = [];
  let url: string | null = `${base}${path}${path.includes('?') ? '&' : '?'}limit=500`;
  let guard = 0;
  while (url && guard < 40) {
    guard += 1;
    let page: K8sListKind;
    try {
      page = await fetchJson<K8sListKind>(url, token, opts.timeoutMs);
    } catch (err) {
      // Non-fatal endpoints (services / HPAs / VPAs) degrade to empty lists.
      if (path.startsWith('/api/v1/nodes') || path.startsWith('/api/v1/pods')) throw err;
      return items;
    }
    for (const item of page.items ?? []) items.push(item as T);
    const cont = opts.paginate ? page.metadata?.continue : undefined;
    url = cont ? `${base}${path}${path.includes('?') ? '&' : '?'}limit=500&continue=${encodeURIComponent(cont)}` : null;
  }
  return items;
}

/**
 * Fetch the standard endpoint set from a live Kubernetes API (or a local
 * `kubectl proxy --port=8001`) and transform it into `ClusterGraphData`
 * (SPEC-10 §2.1.2). `nodes` and `pods` are required; `services`, HPAs, and
 * VPAs degrade gracefully when forbidden or absent (RBAC-varied tokens).
 *
 * Throws a descriptive Error on unreachable endpoints / rejected tokens —
 * callers surface it inline without crashing the visualizer (SPEC-10 §9.1).
 */
export async function fetchAndExtractClusterGraph(
  apiBaseUrl: string,
  token?: string,
  options?: ClientExtractorFetchOptions,
): Promise<ClusterGraphData> {
  const base = normalizeApiBase(apiBaseUrl);
  if (!/^https?:\/\//i.test(base)) {
    throw new Error('Kubernetes API URL must start with http:// or https://');
  }
  const opts: Required<ClientExtractorFetchOptions> = {
    timeoutMs: options?.timeoutMs ?? 12000,
    paginate: options?.paginate ?? true,
    maxEdges: options?.maxEdges ?? MAX_EDGES_DEFAULT,
  };

  const [version, nodes, pods, services, hpas, vpas] = await Promise.all([
    fetchJson<{ gitVersion?: string; major?: string; minor?: string }>(`${base}/version`, token, opts.timeoutMs).catch(() => null),
    fetchList<K8sRawNode>(base, '/api/v1/nodes', token, opts),
    fetchList<K8sRawPod>(base, '/api/v1/pods', token, opts),
    fetchList<K8sRawService>(base, '/api/v1/services', token, opts),
    fetchList<K8sRawHPA>(base, '/apis/autoscaling/v2/horizontalpodautoscalers', token, opts),
    fetchList<K8sRawVPA>(base, '/apis/autoscaling.k8s.io/v1/verticalpodautoscalers', token, opts),
  ]);

  if (nodes.length === 0 && pods.length === 0) {
    throw new Error('API responded but returned no nodes or pods — check RBAC (get/list on nodes, pods)');
  }

  return extractClusterGraph({
    nodes,
    pods,
    services,
    hpas,
    vpas,
    version,
    maxEdgesHint: opts.maxEdges,
  });
}
