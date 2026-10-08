/**
 * SPEC-11 / TASK-CV-1202 — Diff & Delta Inspection Sequence Engine.
 *
 * Per blueprint ADR-02 (`docs/architecture/11-quad-layout-diff-tour-and-latency-springs.md`),
 * `DiffSequenceEngine` is a **pure event-emitting model**: it owns no DOM and no
 * Three.js references. It extracts the ordered walk-through queue from a
 * `DiffReportData` report plus the comparative Alpha/Beta graphs (positions and
 * latency telemetry), runs the playback state machine (play / pause / next /
 * prev / seek / speed), and broadcasts `onStep` / `onStateChange` events that
 * `src/ui/diff_media_deck.ts` (TASK-CV-1203) and the viewport highlight layer
 * (TASK-CV-1204) subscribe to.
 *
 * Sequence ordering follows blueprint §2.2 deterministically:
 *   1. Control Plane & Foundational Services (etcd, apiserver, kube-system)
 *   2. Core / Shared Infrastructure (ingress, istio, DNS, cert-manager)
 *   3. Application Microservices (frontend, cart, checkout, catalog, payment…)
 *   4. Data Vaults & Subterranean Storage (CloudSQL, Redis, PubSub, GCS…)
 *   5. High-Latency Pathways / Bottlenecks (|Δτ| ≥ 15 ms or > 25% skew)
 */

/* ========================================================================== *
 * §A — Contract types (blueprint §2.2)
 * ========================================================================== */

export type DiffKind = 'added' | 'deleted' | 'modified' | 'latency_delta';

export interface DiffSequenceItem {
  id: string;
  index: number;
  kind: DiffKind;
  componentName: string;
  namespace?: string;
  tier?: string;
  alphaVersion?: string;
  betaVersion?: string;
  alphaLatencyMs?: number;
  betaLatencyMs?: number;
  latencyDeltaMs?: number;
  alphaPosition?: { x: number; y: number; z: number };
  betaPosition?: { x: number; y: number; z: number };
  diffDetails: string[];
  description: string;
}

export interface DiffSequenceState {
  items: DiffSequenceItem[];
  currentIndex: number;
  isPlaying: boolean;
  /** Playback rate multiplier: 0.5x, 1x, 2x … */
  speed: number;
  /** Per-component dwell time in ms at 1x (default 3500 ms, spec §3.2). */
  dwellDurationMs: number;
}

/* ========================================================================== *
 * §B — Input contracts
 *
 * Structurally compatible with `DiffReportData` (src/main.ts),
 * `ClusterGraphData` / `ClusterNodeData` (src/scene/cluster_viewport.ts), so
 * callers pass live viewport data straight in without importing those heavy
 * (Three.js-coupled) modules here.
 * ========================================================================== */

export interface DiffReportNodeEntry {
  node_id: string;
  status: 'identical' | 'version_skew' | 'missing' | 'added';
  source_version?: string;
  target_version?: string;
  source_image?: string;
  target_image?: string;
  source_digest?: string;
  target_digest?: string;
  diff_details: string[];
}

export interface DiffReportData {
  source_cluster: string;
  target_cluster: string;
  summary?: {
    identical_nodes?: number;
    version_skew_nodes?: number;
    missing_in_target?: number;
    added_in_target?: number;
  };
  nodes: DiffReportNodeEntry[];
}

export interface DiffSourceNodeData {
  id: string;
  layer: string;
  kind: string;
  name: string;
  namespace: string;
  version: string;
  status?: string;
  metrics?: Record<string, unknown>;
  spatial: { x: number; y: number; z: number; asset_type?: string };
}

export interface DiffSourceEdgeData {
  source: string;
  target: string;
  flow_type?: string;
  protocol?: string;
  direction?: string;
  volume_label?: string;
  /** Optional probe/telemetry latency on the wire (SPEC-08 probe, SPEC-11 tour). */
  latency_ms?: number;
  latencyMs?: number;
}

export interface DiffSourceGraphData {
  nodes: DiffSourceNodeData[];
  edges?: DiffSourceEdgeData[];
  metadata?: { cluster_name?: string; [key: string]: unknown };
}

/** Everything the engine needs to build one Alpha→Beta walk-through queue. */
export interface DiffSequenceSource {
  report: DiffReportData;
  alphaGraph?: DiffSourceGraphData;
  betaGraph?: DiffSourceGraphData;
}

/* ========================================================================== *
 * §C — Tunables & event types
 * ========================================================================== */

/** Spec §3.2: an edge/pathway delta is tour-worthy at |Δτ| ≥ 15 ms … */
export const LATENCY_DELTA_THRESHOLD_MS = 15;
/** … or when baseline skew exceeds 25%. */
export const LATENCY_SKEW_RATIO_THRESHOLD = 0.25;
/** Spec §3.2 default dwell: 3.5 seconds per component. */
export const DEFAULT_DIFF_DWELL_DURATION_MS = 3500;

/** Blueprint §2.3 / §2.4 scrub-pin & badge palette per diff kind. */
export const DIFF_KIND_COLORS: Record<DiffKind, string> = {
  added: '#10b981',
  deleted: '#ef4444',
  modified: '#f59e0b',
  latency_delta: '#a855f7',
};

/** Deterministic intra-group ordering: added → deleted → modified → latency. */
const KIND_RANK: Record<DiffKind, number> = {
  added: 0,
  deleted: 1,
  modified: 2,
  latency_delta: 3,
};

/** Blueprint §2.2 architectural journey buckets. */
export enum DiffSequenceGroup {
  ControlPlane = 0,
  CoreShared = 1,
  Application = 2,
  DataVaults = 3,
  LatencyBottlenecks = 4,
}

export type DiffSequenceStepListener = (
  item: DiffSequenceItem,
  state: DiffSequenceState,
) => void;

export type DiffSequenceStateListener = (state: DiffSequenceState) => void;

export type DiffSequenceUnsubscribe = () => void;

/** Inject so unit tests can run the dwell timer without real wall-clock waits. */
export interface DiffSequenceTimerBackend {
  setTimeout(callback: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

export interface DiffSequenceOptions {
  dwellDurationMs?: number;
  speed?: number;
  /** Auto-advance wraps back to item 0 after the last item (default false). */
  loop?: boolean;
  timers?: DiffSequenceTimerBackend;
}

/* ========================================================================== *
 * §D — Pure helpers (exported for TASK-CV-1208 unit tests)
 * ========================================================================== */

const CONTROL_PLANE_KEYWORDS = [
  'etcd', 'kube-apiserver', 'apiserver', 'kube-scheduler', 'scheduler',
  'kube-controller-manager', 'controller-manager', 'kubelet', 'containerd',
  'control-plane',
];

const CORE_SHARED_KEYWORDS = [
  'coredns', 'dns', 'ingress', 'istio', 'envoy', 'cilium', 'flannel', 'kindnet',
  'cert-manager', 'certmanager', 'gateway', 'gateway-api', 'kube-proxy', 'kubeproxy',
];

const DATA_VAULT_KEYWORDS = [
  'postgres', 'postgresql', 'sql', 'redis', 'redis-node', 'cloudsql', 'mysql', 'mariadb',
  'pubsub', 'pub-sub', 'gcs', 'bucket', 's3', 'dynamodb', 'kafka', 'zookeeper', 'clickhouse',
  'clickhouse', 'mongodb', 'memcached', 'vault', 'subterranean',
];

/** Node metric keys interpreted as response-time / latency telemetry (ms). */
const NODE_LATENCY_METRIC_KEYS = [
  'latency_ms', 'latency_p99_ms', 'p99_latency_ms', 'response_time_ms', 'rtt_ms',
];

/** True when a Δτ is tour-worthy per spec §3.2 (≥15ms absolute or >25% skew). */
export function isSignificantLatencyDelta(alphaMs: number, betaMs: number): boolean {
  const delta = Math.abs(betaMs - alphaMs);
  if (delta >= LATENCY_DELTA_THRESHOLD_MS) return true;
  const baseline = Math.min(alphaMs, betaMs);
  // Ratio-based flag needs a ≥1ms floor so sub-millisecond jitter stays quiet.
  if (baseline > 0 && delta >= 1 && delta / baseline > LATENCY_SKEW_RATIO_THRESHOLD) return true;
  return false;
}

/** Map an item onto its blueprint §2.2 inspection bucket.
 *
 * Priority: latency kind → explicit Core/Shared keywords (blueprint calls DNS,
 * Ingress, Istio, cert-manager out by name even when they physically sit in
 * `kube-system` / the control-plane tier) → explicit Control-Plane keywords →
 * explicit Data-Vault keywords → generic tier/namespace fallbacks.
 */
export function classifyDiffGroup(
  kind: DiffKind,
  info: { componentName: string; namespace?: string; tier?: string },
): DiffSequenceGroup {
  if (kind === 'latency_delta') return DiffSequenceGroup.LatencyBottlenecks;

  const haystack = `${info.componentName} ${info.namespace ?? ''} ${info.tier ?? ''}`.toLowerCase();
  const has = (keywords: readonly string[]): boolean =>
    keywords.some((k) => haystack.includes(k));

  if (has(CORE_SHARED_KEYWORDS)) return DiffSequenceGroup.CoreShared;
  if (has(CONTROL_PLANE_KEYWORDS)) return DiffSequenceGroup.ControlPlane;
  if (has(DATA_VAULT_KEYWORDS)) return DiffSequenceGroup.DataVaults;

  const tier = (info.tier ?? '').toLowerCase();
  if (tier === 'control-plane' || tier === 'node') return DiffSequenceGroup.ControlPlane;
  if ((info.namespace ?? '').toLowerCase() === 'kube-system') return DiffSequenceGroup.ControlPlane;
  if (tier === 'ingress') return DiffSequenceGroup.CoreShared;
  return DiffSequenceGroup.Application;
}

/** Parse the `layer/namespace/name` wire id into its parts defensively. */
export function parseDiffNodeId(id: string): { tier?: string; namespace?: string; name: string } {
  const parts = id.split('/');
  const name = parts[parts.length - 1];
  if (parts.length >= 3) {
    return { tier: parts[0], namespace: parts[1], name: name ?? id };
  }
  if (parts.length === 2) {
    return { tier: parts[0], name: name ?? id };
  }
  return { name: name ?? id };
}

/**
 * Collapse Alpha/Beta identity out of a wire id so the same logical component
 * matches across the two graphs (`...cluster-alpha-control-plane` ↔
 * `...cluster-beta-control-plane`).
 *
 * Cluster names are only collapsed when they are ≥ 3 chars (single-letter
 * report labels like 'A'/'B' must not shred every occurrence of that letter),
 * and `alpha`/`beta` are collapsed only as whole `-`/`_`/`/`-delimited tokens
 * so `redis-a` never matches `redis-b`.
 */
export function normalizeCrossClusterId(id: string, clusterNames: readonly string[]): string {
  let s = id.toLowerCase();
  for (const name of clusterNames) {
    if (name.length >= 3) s = s.split(name.toLowerCase()).join('~');
  }
  return s
    .split(/([-/ _])/)
    .map((token) => (token === 'alpha' || token === 'beta' ? '~' : token))
    .join('');
}

function formatMs(value: number): string {
  return `${Math.round(value)}ms`;
}

function formatSignedMs(value: number): string {
  const rounded = Math.round(value);
  return `${rounded >= 0 ? '+' : ''}${rounded}ms`;
}

/* ========================================================================== *
 * §E — Queue extraction (pure)
 * ========================================================================== */

interface GraphIndex {
  byId: Map<string, DiffSourceNodeData>;
  byBase: Map<string, DiffSourceNodeData>;
  clusterNames: string[];
}

function indexGraph(graph: DiffSourceGraphData | undefined): GraphIndex | null {
  if (!graph) return null;
  const clusterNames: string[] = [];
  if (graph.metadata && typeof graph.metadata.cluster_name === 'string') {
    clusterNames.push(graph.metadata.cluster_name);
  }
  const byId = new Map<string, DiffSourceNodeData>();
  const byBase = new Map<string, DiffSourceNodeData>();
  for (const node of graph.nodes) {
    byId.set(node.id, node);
    const base = normalizeCrossClusterId(node.id, clusterNames);
    if (!byBase.has(base)) byBase.set(base, node);
  }
  return { byId, byBase, clusterNames };
}

function lookupNode(index: GraphIndex | null, id: string): DiffSourceNodeData | null {
  if (!index) return null;
  const direct = index.byId.get(id);
  if (direct) return direct;
  return index.byBase.get(normalizeCrossClusterId(id, index.clusterNames)) ?? null;
}

function positionOf(node: DiffSourceNodeData | null): { x: number; y: number; z: number } | undefined {
  if (!node || !node.spatial) return undefined;
  return { x: node.spatial.x, y: node.spatial.y, z: node.spatial.z };
}

function lastSegment(id: string): string {
  const parts = id.split('/');
  return parts[parts.length - 1] ?? id;
}

function readEdgeLatencyMs(edge: DiffSourceEdgeData): number | null {
  const raw = edge.latency_ms ?? edge.latencyMs;
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : null;
}

function readNodeLatencyMs(node: DiffSourceNodeData): number | null {
  const metrics = node.metrics;
  if (!metrics) return null;
  for (const key of NODE_LATENCY_METRIC_KEYS) {
    const raw = metrics[key];
    if (typeof raw === 'number' && Number.isFinite(raw)) return raw;
  }
  return null;
}

const REPORT_STATUS_TO_KIND: Partial<Record<DiffReportNodeEntry['status'], DiffKind>> = {
  added: 'added',
  missing: 'deleted',
  version_skew: 'modified',
};

function describeReportItem(
  kind: DiffKind,
  entry: DiffReportNodeEntry,
  sourceCluster: string,
  targetCluster: string,
): string {
  const src = sourceCluster || 'Alpha';
  const tgt = targetCluster || 'Beta';
  switch (kind) {
    case 'added':
      return entry.target_version
        ? `Present in ${tgt} but absent in ${src} (${entry.target_version})`
        : `Present in ${tgt} but absent in ${src}`;
    case 'deleted':
      return entry.source_version
        ? `Present in ${src} but removed in ${tgt} (was ${entry.source_version})`
        : `Present in ${src} but removed in ${tgt}`;
    case 'modified': {
      const aVer = entry.source_version ?? '?';
      const bVer = entry.target_version ?? '?';
      if (aVer !== bVer) return `Version skew across clusters: ${aVer} ➔ ${bVer}`;
      return `Configuration / digest skew across clusters: ${aVer}`;
    }
    default:
      return `Latency delta for ${entry.node_id}`;
  }
}

/** Extract added / deleted / modified items from the diff report. */
function extractReportItems(source: DiffSequenceSource): DiffSequenceItem[] {
  const { report, alphaGraph, betaGraph } = source;
  const alphaIndex = indexGraph(alphaGraph);
  const betaIndex = indexGraph(betaGraph);
  const items: DiffSequenceItem[] = [];

  for (const entry of report.nodes) {
    const kind = REPORT_STATUS_TO_KIND[entry.status];
    if (!kind) continue; // identical (and anything unknown) stays out of the tour

    const parsed = parseDiffNodeId(entry.node_id);
    const nodeA = kind === 'added' ? null : lookupNode(alphaIndex, entry.node_id);
    const nodeB = kind === 'deleted' ? null : lookupNode(betaIndex, entry.node_id);

    const diffDetails = [...entry.diff_details];
    if (kind === 'modified' && entry.source_digest && entry.target_digest &&
        entry.source_digest !== entry.target_digest) {
      diffDetails.push(`Image digest skew: ${entry.source_digest.slice(0, 19)}… vs ${entry.target_digest.slice(0, 19)}…`);
    }

    const item: DiffSequenceItem = {
      id: entry.node_id,
      index: -1, // assigned after deterministic sort
      kind,
      componentName: nodeA?.name ?? nodeB?.name ?? parsed.name,
      namespace: nodeA?.namespace ?? nodeB?.namespace ?? parsed.namespace,
      tier: nodeA?.layer ?? nodeB?.layer ?? parsed.tier,
      alphaVersion: entry.source_version,
      betaVersion: entry.target_version,
      alphaPosition: positionOf(nodeA),
      betaPosition: positionOf(nodeB),
      diffDetails,
      description: describeReportItem(kind, entry, report.source_cluster, report.target_cluster),
    };
    items.push(item);
  }
  return items;
}

/**
 * Extract latency-delta items (§3.2 step 5) from:
 *   a) paired Alpha/Beta edges carrying numeric latency telemetry, and
 *   b) paired nodes whose response-time metrics moved significantly.
 */
function extractLatencyItems(source: DiffSequenceSource): DiffSequenceItem[] {
  const { alphaGraph, betaGraph } = source;
  if (!alphaGraph || !betaGraph) return [];

  const alphaIndex = indexGraph(alphaGraph);
  const betaIndex = indexGraph(betaGraph);
  const clusterNames = [
    ...(alphaIndex?.clusterNames ?? []),
    ...(betaIndex?.clusterNames ?? []),
    source.report.source_cluster,
    source.report.target_cluster,
  ];
  const items: DiffSequenceItem[] = [];
  const seen = new Set<string>();

  // (a) Edge pathway deltas.
  const alphaEdges = new Map<string, { edge: DiffSourceEdgeData; latencyMs: number }>();
  for (const edge of alphaGraph.edges ?? []) {
    const latencyMs = readEdgeLatencyMs(edge);
    if (latencyMs === null) continue;
    const key = `${normalizeCrossClusterId(edge.source, clusterNames)}|${normalizeCrossClusterId(edge.target, clusterNames)}`;
    alphaEdges.set(key, { edge, latencyMs });
  }
  for (const edge of betaGraph.edges ?? []) {
    const betaLatency = readEdgeLatencyMs(edge);
    if (betaLatency === null) continue;
    const key = `${normalizeCrossClusterId(edge.source, clusterNames)}|${normalizeCrossClusterId(edge.target, clusterNames)}`;
    const alpha = alphaEdges.get(key);
    if (!alpha) continue;
    if (!isSignificantLatencyDelta(alpha.latencyMs, betaLatency)) continue;

    const delta = betaLatency - alpha.latencyMs;
    const aName = lastSegment(lookupNode(alphaIndex, edge.source)?.name ?? edge.source);
    const bName = lastSegment(lookupNode(betaIndex, edge.target)?.name ?? edge.target);
    const id = `latency|${key}`;
    if (seen.has(id)) continue;
    seen.add(id);

    const diffDetails = [
      `Alpha τ: ${formatMs(alpha.latencyMs)} ➔ Beta τ: ${formatMs(betaLatency)} (Δ ${formatSignedMs(delta)})`,
    ];
    if (edge.flow_type) diffDetails.push(`Flow type: ${edge.flow_type}`);
    if (edge.protocol) diffDetails.push(`Protocol: ${edge.protocol}`);
    if (edge.volume_label) diffDetails.push(`Channel: ${edge.volume_label}`);

    items.push({
      id,
      index: -1,
      kind: 'latency_delta',
      componentName: `${aName} → ${bName}`,
      alphaLatencyMs: alpha.latencyMs,
      betaLatencyMs: betaLatency,
      latencyDeltaMs: delta,
      alphaPosition: positionOf(lookupNode(alphaIndex, edge.source)),
      betaPosition: positionOf(lookupNode(betaIndex, edge.target)),
      diffDetails,
      description: `Pathway latency skew ${formatMs(alpha.latencyMs)} ➔ ${formatMs(betaLatency)} [Δ ${formatSignedMs(delta)}]`,
    });
  }

  // (b) Node-level response-time deltas (comparative telemetry bag).
  for (const nodeB of betaGraph.nodes) {
    const betaLatency = readNodeLatencyMs(nodeB);
    if (betaLatency === null) continue;
    const alphaMatch =
      alphaIndex?.byId.get(nodeB.id) ??
      alphaIndex?.byBase.get(normalizeCrossClusterId(nodeB.id, clusterNames)) ??
      null;
    if (!alphaMatch) continue;
    const alphaLatency = readNodeLatencyMs(alphaMatch);
    if (alphaLatency === null) continue;
    if (!isSignificantLatencyDelta(alphaLatency, betaLatency)) continue;

    const delta = betaLatency - alphaLatency;
    const id = `latency-node|${nodeB.id}`;
    if (seen.has(id)) continue;
    seen.add(id);

    items.push({
      id,
      index: -1,
      kind: 'latency_delta',
      componentName: nodeB.name,
      namespace: nodeB.namespace,
      tier: nodeB.layer,
      alphaLatencyMs: alphaLatency,
      betaLatencyMs: betaLatency,
      latencyDeltaMs: delta,
      alphaPosition: positionOf(alphaMatch),
      betaPosition: positionOf(nodeB),
      diffDetails: [
        `Response-time skew: ${formatMs(alphaLatency)} ➔ ${formatMs(betaLatency)} (Δ ${formatSignedMs(delta)})`,
      ],
      description: `Component latency skew ${formatMs(alphaLatency)} ➔ ${formatMs(betaLatency)} [Δ ${formatSignedMs(delta)}]`,
    });
  }

  return items;
}

/**
 * Build the fully-ordered, index-assigned walk-through queue (blueprint §2.2).
 * Deterministic: same source in ⇒ identical queue out (stable tie-breaks:
 * group → kind rank → component name → id; latency bucket sorts by |Δτ| desc).
 */
export function buildDiffSequence(source: DiffSequenceSource): DiffSequenceItem[] {
  const items = [...extractReportItems(source), ...extractLatencyItems(source)];

  const groupOf = new Map<string, DiffSequenceGroup>();
  for (const item of items) {
    groupOf.set(
      item.id,
      classifyDiffGroup(item.kind, {
        componentName: item.componentName,
        namespace: item.namespace,
        tier: item.tier,
      }),
    );
  }

  items.sort((a, b) => {
    const ga = groupOf.get(a.id) ?? DiffSequenceGroup.Application;
    const gb = groupOf.get(b.id) ?? DiffSequenceGroup.Application;
    if (ga !== gb) return ga - gb;

    if (a.kind === 'latency_delta' && b.kind === 'latency_delta') {
      const byDelta = Math.abs(b.latencyDeltaMs ?? 0) - Math.abs(a.latencyDeltaMs ?? 0);
      if (byDelta !== 0) return byDelta;
    } else {
      const kindDelta = KIND_RANK[a.kind] - KIND_RANK[b.kind];
      if (kindDelta !== 0) return kindDelta;
      if (a.componentName !== b.componentName) {
        return a.componentName < b.componentName ? -1 : 1;
      }
    }
    if (a.id !== b.id) return a.id < b.id ? -1 : 1;
    return 0;
  });

  return items.map((item, index) => ({ ...item, index }));
}

/* ========================================================================== *
 * §F — Playback state machine
 * ========================================================================== */

const defaultTimers: DiffSequenceTimerBackend = {
  setTimeout: (callback: () => void, ms: number) => globalThis.setTimeout(callback, ms),
  clearTimeout: (handle: unknown) => globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>),
};

/**
 * Pure event-emitting diff walk-through model (ADR-02).
 *
 * Lifecycle:
 *  - `setSequenceSource()` loads the report + comparative graphs and rebuilds
 *    the queue (selection resets to head).
 *  - `start()` arms the sequence at item 0 (emits an initial `onStep`).
 *  - `play()` / `pause()` toggle the auto-dwell timer (interval =
 *    `dwellDurationMs / speed`).
 *  - `next()` / `prev()` / `seek()` jump manually; a manual jump while playing
 *    restarts the dwell window for the newly focused item.
 *
 * Event order for a selection change: `onStep(item, state)` fires first, then
 * `onStateChange(state)` — banners paint before the progress bar.
 */
export class DiffSequenceEngine {
  private items: DiffSequenceItem[] = [];
  private currentIndex: number = -1;
  private isPlaying: boolean = false;
  private speed: number;
  private dwellDurationMs: number;
  private loop: boolean;
  private timers: DiffSequenceTimerBackend;
  private timerHandle: unknown = null;
  private source: DiffSequenceSource | null = null;
  private readonly stepListeners = new Set<DiffSequenceStepListener>();
  private readonly stateListeners = new Set<DiffSequenceStateListener>();

  constructor(options: DiffSequenceOptions = {}) {
    this.dwellDurationMs =
      options.dwellDurationMs !== undefined && options.dwellDurationMs > 0
        ? options.dwellDurationMs
        : DEFAULT_DIFF_DWELL_DURATION_MS;
    this.speed =
      options.speed !== undefined && Number.isFinite(options.speed) && options.speed > 0
        ? options.speed
        : 1;
    this.loop = options.loop ?? false;
    this.timers = options.timers ?? defaultTimers;
  }

  /* ------------------------------ subscriptions --------------------------- */

  onStep(listener: DiffSequenceStepListener): DiffSequenceUnsubscribe {
    this.stepListeners.add(listener);
    return () => {
      this.stepListeners.delete(listener);
    };
  }

  onStateChange(listener: DiffSequenceStateListener): DiffSequenceUnsubscribe {
    this.stateListeners.add(listener);
    return () => {
      this.stateListeners.delete(listener);
    };
  }

  /* ------------------------------ queue loading --------------------------- */

  /** Load (or replace) the diff source and rebuild the ordered queue. */
  setSequenceSource(source: DiffSequenceSource): DiffSequenceItem[] {
    this.stopTimer();
    this.isPlaying = false;
    this.source = source;
    this.items = buildDiffSequence(source);
    this.currentIndex = this.items.length > 0 ? 0 : -1;
    this.emitState();
    return this.getState().items;
  }

  /** Rebuild the queue from the previously loaded source (e.g. after a re-diff). */
  refresh(): DiffSequenceItem[] {
    if (!this.source) return this.getState().items;
    return this.setSequenceSource(this.source);
  }

  getSequenceSource(): DiffSequenceSource | null {
    return this.source;
  }

  getItemCount(): number {
    return this.items.length;
  }

  getCurrentItem(): DiffSequenceItem | null {
    if (this.currentIndex < 0 || this.currentIndex >= this.items.length) return null;
    return this.items[this.currentIndex] ?? null;
  }

  /* ------------------------------ playback -------------------------------- */

  /** Arm the tour at the first item (does not start the auto-dwell timer). */
  start(): void {
    if (this.items.length === 0 && this.source) {
      this.items = buildDiffSequence(this.source);
    }
    this.isPlaying = false;
    this.stopTimer();
    if (this.items.length > 0) {
      this.selectIndex(0);
    } else {
      this.currentIndex = -1;
      this.emitState();
    }
  }

  /** Stop the tour: pause, clear selection, emit final state. */
  stop(): void {
    this.isPlaying = false;
    this.stopTimer();
    this.currentIndex = -1;
    this.emitState();
  }

  play(): void {
    if (this.items.length === 0) return;
    if (this.currentIndex < 0) {
      this.selectIndex(0);
    }
    this.isPlaying = true;
    this.scheduleDwell();
    this.emitState();
  }

  pause(): void {
    if (!this.isPlaying) return;
    this.isPlaying = false;
    this.stopTimer();
    this.emitState();
  }

  togglePlay(): void {
    if (this.isPlaying) {
      this.pause();
    } else {
      this.play();
    }
  }

  next(): void {
    if (this.items.length === 0) return;
    const last = this.items.length - 1;
    const target = this.loop
      ? (this.currentIndex + 1) % this.items.length
      : Math.min(this.currentIndex + 1, last);
    if (target === this.currentIndex) {
      if (this.isPlaying) this.scheduleDwell(); // dwell restart at the tail
      return;
    }
    this.selectIndex(target);
  }

  prev(): void {
    if (this.items.length === 0) return;
    const target = this.loop
      ? (this.currentIndex - 1 + this.items.length) % this.items.length
      : Math.max(this.currentIndex - 1, 0);
    if (target === this.currentIndex) return;
    this.selectIndex(target);
  }

  /** Jump to an arbitrary sequence position (clamped into range). */
  seek(index: number): void {
    if (this.items.length === 0 || !Number.isFinite(index)) return;
    const clamped = Math.max(0, Math.min(Math.trunc(index), this.items.length - 1));
    if (clamped === this.currentIndex) return;
    this.selectIndex(clamped);
  }

  /** Playback rate multiplier (0.5 / 1 / 2 …); restarts the dwell window. */
  setSpeed(speed: number): void {
    if (!Number.isFinite(speed) || speed <= 0) return;
    if (speed === this.speed) return;
    this.speed = speed;
    if (this.isPlaying) this.scheduleDwell();
    this.emitState();
  }

  getSpeed(): number {
    return this.speed;
  }

  setDwellDuration(ms: number): void {
    if (!Number.isFinite(ms) || ms <= 0) return;
    if (ms === this.dwellDurationMs) return;
    this.dwellDurationMs = ms;
    if (this.isPlaying) this.scheduleDwell();
    this.emitState();
  }

  getDwellDuration(): number {
    return this.dwellDurationMs;
  }

  /** Effective auto-advance interval: dwellDurationMs / speed (spec §3.2). */
  getEffectiveIntervalMs(): number {
    return Math.max(1, this.dwellDurationMs / this.speed);
  }

  setLoop(loop: boolean): void {
    this.loop = loop;
  }

  getIsPlaying(): boolean {
    return this.isPlaying;
  }

  getState(): DiffSequenceState {
    return {
      items: [...this.items],
      currentIndex: this.currentIndex,
      isPlaying: this.isPlaying,
      speed: this.speed,
      dwellDurationMs: this.dwellDurationMs,
    };
  }

  /** Release timers and listeners (deck teardown / page navigation). */
  dispose(): void {
    this.stopTimer();
    this.isPlaying = false;
    this.stepListeners.clear();
    this.stateListeners.clear();
  }

  /* ------------------------------ internals ------------------------------- */

  private selectIndex(index: number): void {
    this.currentIndex = index;
    const item = this.getCurrentItem();
    if (item) {
      const snapshot = this.getState();
      for (const listener of [...this.stepListeners]) {
        listener(item, snapshot);
      }
    }
    if (this.isPlaying) this.scheduleDwell();
    this.emitState();
  }

  private scheduleDwell(): void {
    this.stopTimer();
    const interval = this.getEffectiveIntervalMs();
    this.timerHandle = this.timers.setTimeout(() => {
      this.timerHandle = null;
      if (!this.isPlaying) return;
      this.autoAdvance();
    }, interval);
  }

  private autoAdvance(): void {
    const last = this.items.length - 1;
    if (this.currentIndex >= last) {
      if (this.loop) {
        this.selectIndex(0);
      } else {
        // Tour complete: rest on the final item with playback stopped.
        this.isPlaying = false;
        this.emitState();
      }
      return;
    }
    this.selectIndex(this.currentIndex + 1);
  }

  private stopTimer(): void {
    if (this.timerHandle !== null) {
      this.timers.clearTimeout(this.timerHandle);
      this.timerHandle = null;
    }
  }

  private emitState(): void {
    const snapshot = this.getState();
    for (const listener of [...this.stateListeners]) {
      listener(snapshot);
    }
  }
}
