/**
 * TrafficControlDeck — SPEC-10 §6 / TASK-CV-1105
 *
 * Dockable bottom HUD for the ⚡ AUTOSCALING TRAFFIC SIMULATION HARNESS.
 * Translucent dark-glass panel (`rgba(17, 24, 39, 0.95)` + blur(12px) +
 * `#1f2937` hairline) owning a TrafficSimulatorEngine (Engine A, §4.2) and
 * projecting its state onto every attached ClusterViewport:
 *
 *   • Target Workload / Target Cluster selectors discovered from the live
 *     cluster graphs loaded in each viewport slot (frontend, cartservice,
 *     raycluster workers, bench lanes, …).
 *   • Traffic Pattern pills (Step Spike / Sine Wave / Ramp-Up / Chaos Flap)
 *     + 50–2500 RPS concurrency slider (default 850, baseline 100).
 *   • Engine toggles: HPA (Horizontal), VPA Morphing, Simulate Node
 *     Provisioning Latency.
 *   • Real-time comparative telemetry cards per active viewport: latency
 *     with [STABLE] / [ELEVATED] / [SATURATED] badges, Replicas N (+M),
 *     Pending in Staging, CPU %, Sched Delay, Error Rate.
 *   • Action buttons: ▶ INJECT TRAFFIC / ⏸ PAUSE / ↺ RESET BASELINE /
 *     ⚡ BURST 2000 RPS.
 *
 * SPEC-10 §6.3 visual manifestations:
 *   • `viewport.flowSystem` streams: speed + surge-particle density scale
 *     with RPS; tranquil cyan `#38bdf8` (< 30 ms) → warning amber
 *     `#f59e0b` (30–200 ms) → blazing crimson `#ef4444` (> 200 ms).
 *   • Simulator triggers land through `TrafficSimulator.attachViewport`,
 *     which drives `applyHpaScaleOut`, `applyVpaRecommendation`,
 *     `applyVpaResize`, `applyKarpenterClaim` and `applyKarpenterTractorBeam`
 *     on every matching viewport (SPEC-09 pipelines).
 */

import type { ClusterGraphData, ClusterViewport } from '../scene/cluster_viewport.js';
import { TrafficSimulator } from '../scene/traffic_simulator.js';
import type {
  ComputeClassType,
  TrafficHarnessConfig,
  TrafficPattern,
  WorkloadScalingState,
} from '../scene/traffic_simulator.js';

// ---------------------------------------------------------------------------
// Public surface
// ---------------------------------------------------------------------------

export interface TrafficDeckViewportSlot {
  /** Slot id used as the simulator cluster key ('a', 'b', 'c', 'd'). */
  id: string;
  /** Short HUD label, e.g. "Viewport A". */
  label: string;
  /** Human cluster title, e.g. "Cluster Alpha". */
  title: string;
  viewport: ClusterViewport;
}

export interface TrafficControlDeckOptions {
  slots: TrafficDeckViewportSlot[];
  /** Dock host element (index.html `#traffic-deck-dock`); created if absent. */
  dockContainer?: HTMLElement | null;
  /** HPA evaluation cadence for UI demos (default 1 s, SPEC §5.2). */
  hpaIntervalSeconds?: number;
}

const RPS_MIN = 50;
const RPS_MAX = 2500;
const RPS_DEFAULT = 850;
const RPS_BASELINE = 100;
const BURST_RPS = 2000;

/** SPEC-10 §6.3 latency band colors. */
const FLOW_CYAN = 0x38bdf8;
const FLOW_AMBER = 0xf59e0b;
const FLOW_CRIMSON = 0xef4444;

const PATTERN_OPTIONS: Array<{ value: TrafficPattern; label: string }> = [
  { value: 'step', label: 'Step Spike' },
  { value: 'sine', label: 'Sine Wave' },
  { value: 'ramp', label: 'Ramp-Up' },
  { value: 'chaos', label: 'Chaos Flap' },
];

const COMPUTE_CLASS_LABEL: Record<ComputeClassType, string> = {
  'gke-compute-class': 'GKE COMPUTE CLASS',
  karpenter: 'KARPENTER / STANDARD',
  'static-nodepool': 'STATIC NODEPOOL',
};

// ---------------------------------------------------------------------------
// Workload discovery from loaded cluster graphs
// ---------------------------------------------------------------------------

/** Shape-tolerant view of the wire node (raw_labels is untyped upstream). */
interface WireNode {
  id: string;
  name: string;
  namespace: string;
  layer: string;
  kind: string;
  metrics?: Record<string, unknown> | null;
  autoscaling?: {
    has_hpa?: boolean;
    has_vpa?: boolean;
    target_metric?: string | null;
  } | null;
  raw_labels?: Record<string, string> | null;
}

const SYSTEM_NAMESPACES = new Set(['kube-system', 'kube-public', 'kube-node-lease', 'karpenter']);
const INFRA_NAME_RE = /(-operator|-controller|-autoscaler|loadgenerator|apiserver|scheduler|controller-manager|\betcd\b)/;

/** Trailing random/hash segment splitter for generated pod suffixes. */
const POD_SEG_RE = /^(.*)-([a-z0-9]+)$/;

function hasDigit(s: string): boolean {
  return /\d/.test(s);
}

/** ReplicaSet template-hash shape: 8–10 alphanumerics carrying a digit. */
function isTemplateHash(s: string): boolean {
  return s.length >= 8 && s.length <= 10 && hasDigit(s);
}

/**
 * Collapse pod instance names onto their workload base name, peeling up to
 * two generated segments: StatefulSet ordinals (`-0`), random pod suffixes
 * (`-xq7qk`, `-a1x`, and digit-free `-rshcr` when the previous segment is a
 * template hash), and 8–10-char ReplicaSet template hashes.
 * `frontend-bc4d8f7f9-xq7qk` and `bench-frontend-scaleup-6d7c8f9a-a1x` both
 * land on their app base; genuine hyphenated names survive intact.
 */
export function workloadBaseName(name: string): string {
  let base = name.replace(/-\d+$/, ''); // StatefulSet ordinal (-0, -1)
  for (let i = 0; i < 2; i++) {
    const m = POD_SEG_RE.exec(base);
    if (!m) break;
    const head = m[1] ?? '';
    const seg = m[2] ?? '';
    if (head.length < 3) break;
    const generated = (seg.length >= 4 && seg.length <= 10 && hasDigit(seg)) || isTemplateHash(seg);
    if (generated) {
      base = head;
      continue;
    }
    // Digit-free random token sitting behind a template hash is still the
    // Deployment's generated pod suffix — strip it so the hash peel follows.
    const prev = POD_SEG_RE.exec(head);
    if (prev && isTemplateHash(prev[2] ?? '')) {
      base = head;
      continue;
    }
    break;
  }
  return base.length > 0 ? base : name;
}

/** Derive the dominant auto-provisioning fabric for a cluster graph. */
export function detectComputeClass(data: ClusterGraphData): ComputeClassType {
  let sawKarpenter = (data.karpenter_node_claims?.length ?? 0) > 0;
  let sawGkeClass = false;
  for (const raw of data.nodes as unknown as WireNode[]) {
    for (const key of Object.keys(raw.raw_labels ?? {})) {
      if (key.includes('karpenter')) sawKarpenter = true;
      if (key.includes('compute-class')) sawGkeClass = true;
    }
  }
  if (sawKarpenter) return 'karpenter';
  if (sawGkeClass) return 'gke-compute-class';
  return 'static-nodepool';
}

/** One discovered workload group inside one viewport slot. */
interface DiscoveredWorkload {
  unitId: string;
  base: string;
  slotId: string;
  namespace: string;
  replicas: number;
  targetCpu: number;
  hasVpa: boolean;
  cpuCores: number;
  memGib: number;
}

/** AI/ML-flavoured workloads get the 25 req/s μ (SPEC-10 §5.1). */
function serviceRateFor(base: string): number {
  return /(inference|vllm|torch|torch|train|ray|gpu|ml\b)/i.test(base) ? 25 : 120;
}

function num(v: unknown, fallback: number): number {
  const n = typeof v === 'number' ? v : typeof v === 'string' ? Number.parseFloat(v) : NaN;
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

/** Aggregate every schedulable pod of a graph into workload groups. */
export function discoverWorkloads(
  slotId: string,
  data: ClusterGraphData,
): DiscoveredWorkload[] {
  const groups = new Map<string, DiscoveredWorkload>();
  for (const raw of data.nodes as unknown as WireNode[]) {
    if (raw.kind !== 'Pod' && raw.kind !== 'RayWorker') continue;
    if (raw.layer === 'control-plane') continue;
    if (SYSTEM_NAMESPACES.has(raw.namespace)) continue;
    if (INFRA_NAME_RE.test(raw.name)) continue;

    const base = workloadBaseName(raw.name);
    const existing = groups.get(base);
    if (existing) {
      existing.replicas += 1;
      existing.cpuCores += num(raw.metrics?.cpu_request_cores, 0.5);
      existing.memGib += num(raw.metrics?.memory_request_gib, 1);
      existing.hasVpa = existing.hasVpa || raw.autoscaling?.has_vpa === true;
      continue;
    }
    const targetMetric = raw.autoscaling?.target_metric ?? '';
    const cpuMatch = /cpu:(\d+(?:\.\d+)?)/.exec(targetMetric);
    groups.set(base, {
      unitId: `${slotId}/${base}`,
      base,
      slotId,
      namespace: raw.namespace || 'default',
      replicas: 1,
      targetCpu: cpuMatch ? Number.parseFloat(cpuMatch[1] ?? '60') : 60,
      hasVpa: raw.autoscaling?.has_vpa === true,
      cpuCores: num(raw.metrics?.cpu_request_cores, 0.5),
      memGib: num(raw.metrics?.memory_request_gib, 1),
    });
  }
  return [...groups.values()];
}

// ---------------------------------------------------------------------------
// Telemetry view model
// ---------------------------------------------------------------------------

type LatencyBand = 'stable' | 'elevated' | 'saturated';

interface ViewportTelemetry {
  latencies: number[];
  replicas: number;
  desired: number;
  pending: number;
  cpu: number[];
  errors: number[];
  provisioningMs: number;
}

function bandFor(latencyMs: number, pending: number, errorRate: number): LatencyBand {
  if (latencyMs > 200 || pending > 0 || errorRate > 0.1) return 'saturated';
  if (latencyMs >= 30 || errorRate > 0.01) return 'elevated';
  return 'stable';
}

// ---------------------------------------------------------------------------
// Styles (injected once)
// ---------------------------------------------------------------------------

const DECK_CSS = `
.traffic-deck-panel {
  background: rgba(17, 24, 39, 0.95);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid #1f2937;
  border-radius: 12px 12px 0 0;
  box-shadow: 0 -12px 36px rgba(0, 0, 0, 0.65);
  color: #e5e7eb;
  font-family: inherit;
  font-size: 11px;
  padding: 8px 18px 10px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
#traffic-deck-dock.undocked .traffic-deck-panel {
  border-radius: 12px;
  border-color: #38bdf8;
  box-shadow: 0 16px 44px rgba(0, 0, 0, 0.75), 0 0 0 1px rgba(56, 189, 248, 0.25);
}
.traffic-deck-panel * { box-sizing: border-box; }
.td-header { display: flex; align-items: center; gap: 12px; }
.td-title {
  font-size: 12px; font-weight: 700; letter-spacing: 0.08em; color: #f3f4f6;
  display: flex; align-items: center; gap: 6px;
}
.td-title .zap { color: #fbbf24; }
.td-engine-pill {
  font-size: 9.5px; font-weight: 700; letter-spacing: 0.09em;
  padding: 2px 8px; border-radius: 9999px;
  background: rgba(100, 116, 139, 0.2); color: #94a3b8; border: 1px solid #334155;
}
.td-engine-pill.running { background: rgba(16, 185, 129, 0.16); color: #34d399; border-color: rgba(16, 185, 129, 0.5); animation: td-pulse 1.6s ease-in-out infinite; }
.td-engine-pill.paused { background: rgba(245, 158, 11, 0.16); color: #fbbf24; border-color: rgba(245, 158, 11, 0.5); }
@keyframes td-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.55; } }
.td-spacer { flex: 1; }
.td-hdr-btn {
  background: transparent; color: #9ca3af; border: 1px solid #374151;
  border-radius: 5px; padding: 2px 8px; font-size: 10.5px; cursor: pointer;
}
.td-hdr-btn:hover { color: #f3f4f6; border-color: #4b5563; }
.td-row { display: flex; align-items: center; flex-wrap: wrap; gap: 14px; }
.td-label { font-size: 9.5px; font-weight: 700; letter-spacing: 0.11em; color: #6b7280; white-space: nowrap; }
.td-select {
  background: #1f2937; color: #e5e7eb; border: 1px solid #374151; border-radius: 5px;
  font-size: 11px; padding: 3px 8px; outline: none; cursor: pointer; max-width: 260px;
}
.td-select:focus { border-color: #38bdf8; }
.td-pill-group { display: flex; gap: 4px; background: rgba(0, 0, 0, 0.35); padding: 2px; border-radius: 7px; border: 1px solid #374151; }
.td-pill {
  background: transparent; border: none; color: #9ca3af; border-radius: 5px;
  padding: 3px 10px; font-size: 10.5px; font-weight: 600; cursor: pointer;
}
.td-pill:hover { color: #e5e7eb; }
.td-pill.active { background: rgba(56, 189, 248, 0.22); color: #38bdf8; box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.55); }
.td-slider { width: 240px; accent-color: #38bdf8; cursor: pointer; }
.td-rps-readout { font-weight: 700; color: #38bdf8; font-size: 12px; min-width: 84px; }
.td-rps-baseline { color: #6b7280; font-size: 10px; }
.td-check { display: flex; align-items: center; gap: 5px; cursor: pointer; color: #d1d5db; white-space: nowrap; }
.td-check input { accent-color: #38bdf8; cursor: pointer; }
.td-divider {
  display: flex; align-items: center; gap: 8px; color: #4b5563;
  font-size: 9px; font-weight: 700; letter-spacing: 0.14em;
}
.td-divider::before, .td-divider::after { content: ''; height: 1px; flex: 1; background: #1f2937; }
.td-telemetry { display: flex; gap: 10px; flex-wrap: wrap; }
.td-card {
  flex: 1 1 300px; min-width: 260px;
  background: rgba(0, 0, 0, 0.35); border: 1px solid #1f2937; border-radius: 8px;
  padding: 6px 12px 8px; display: flex; flex-direction: column; gap: 5px;
}
.td-card-head { display: flex; align-items: center; gap: 8px; }
.td-card-head b { font-size: 11px; color: #f3f4f6; letter-spacing: 0.04em; }
.td-class-chip {
  font-size: 8.5px; font-weight: 700; letter-spacing: 0.08em; padding: 1px 6px; border-radius: 4px;
  background: rgba(56, 189, 248, 0.14); color: #7dd3fc; border: 1px solid rgba(56, 189, 248, 0.35);
}
.td-class-chip.karpenter { background: rgba(217, 70, 239, 0.14); color: #e879f9; border-color: rgba(217, 70, 239, 0.4); }
.td-class-chip.static { background: rgba(148, 163, 187, 0.14); color: #cbd5e1; border-color: rgba(148, 163, 187, 0.35); }
.td-metrics { display: flex; flex-wrap: wrap; gap: 4px 12px; color: #9ca3af; }
.td-metrics b { color: #e5e7eb; font-weight: 600; }
.td-badge {
  font-size: 8.5px; font-weight: 800; letter-spacing: 0.08em; padding: 1px 6px; border-radius: 4px; margin-left: 4px;
}
.td-badge.stable { background: rgba(16, 185, 129, 0.18); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.45); }
.td-badge.elevated { background: rgba(245, 158, 11, 0.18); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.45); }
.td-badge.saturated { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.5); }
.td-lat-bar { height: 3px; border-radius: 2px; background: #1f2937; overflow: hidden; }
.td-lat-bar > div { height: 100%; border-radius: 2px; transition: width 0.25s ease, background-color 0.25s ease; }
.td-idle-note { color: #4b5563; font-style: italic; flex: 1; }
.td-actions { gap: 10px; margin-top: 1px; }
.td-btn {
  background: #1f2937; color: #e5e7eb; border: 1px solid #374151; border-radius: 6px;
  padding: 5px 14px; font-size: 11px; font-weight: 700; letter-spacing: 0.04em; cursor: pointer;
  transition: all 0.15s ease;
}
.td-btn:hover { background: #374151; border-color: #4b5563; }
.td-btn.inject { background: rgba(56, 189, 248, 0.22); color: #38bdf8; border-color: #38bdf8; }
.td-btn.inject.active { background: rgba(239, 68, 68, 0.22); color: #f87171; border-color: #ef4444; }
.td-btn.burst { color: #fbbf24; border-color: #78350f; }
.td-btn.burst:hover { background: rgba(245, 158, 11, 0.16); border-color: #f59e0b; }
`;

// ---------------------------------------------------------------------------
// TrafficControlDeck
// ---------------------------------------------------------------------------

export class TrafficControlDeck {
  public readonly simulator: TrafficSimulator;

  private readonly slots: TrafficDeckViewportSlot[];
  private readonly container: HTMLElement;
  private readonly panel: HTMLDivElement;
  private open_ = false;
  private injected = false;

  /** Latest engine snapshot per unit id (fed by onStateUpdate). */
  private readonly latestStates = new Map<string, WorkloadScalingState>();
  /** Discovered unit ids per slot id. */
  private readonly slotUnits = new Map<string, string[]>();
  private knownWorkloadBases: string[] = [];

  // Control handles
  private workloadSelect!: HTMLSelectElement;
  private clusterSelect!: HTMLSelectElement;
  private readonly patternButtons = new Map<TrafficPattern, HTMLButtonElement>();
  private slider!: HTMLRangeInputElementShim;
  private rpsReadout!: HTMLSpanElement;
  private hpaCheck!: HTMLInputElement;
  private vpaCheck!: HTMLInputElement;
  private skewCheck!: HTMLInputElement;
  private injectBtn!: HTMLButtonElement;
  private pauseBtn!: HTMLButtonElement;
  private telemetryEl!: HTMLDivElement;
  private enginePill!: HTMLSpanElement;

  private pattern: TrafficPattern = 'step';
  private peakRps = RPS_DEFAULT;
  private pausedFlag = false;

  /** Per-slot modulation key to avoid re-allocating particles every frame. */
  private readonly lastModKey = new Map<string, string>();
  private telemetryClock = 0;

  constructor(options: TrafficControlDeckOptions) {
    this.slots = [...options.slots];

    this.simulator = new TrafficSimulator({
      hpaIntervalSeconds: options.hpaIntervalSeconds ?? 1,
      scaleDownStabilizationSeconds: 10,
      seed: 1337,
      callbacks: {
        onStateUpdate: (states) => {
          for (const s of states) this.latestStates.set(`${s.clusterId}/${s.workloadName}`, s);
        },
      },
    });

    // SPEC-10 §6.3: engine triggers land on every viewport through the
    // simulator's own dispatch (applyHpaScaleOut / applyVpaResize /
    // applyVpaRecommendation / applyKarpenterClaim / applyKarpenterTractorBeam).
    for (const slot of this.slots) {
      this.simulator.attachViewport(slot.viewport, slot.id);
    }

    this.container = options.dockContainer ?? TrafficControlDeck.ensureDockContainer();
    TrafficControlDeck.ensureStyles();

    this.panel = document.createElement('div');
    this.panel.className = 'traffic-deck-panel';
    this.buildDom();
    this.container.appendChild(this.panel);

    this.refreshWorkloads();
    this.renderTelemetry();
  }

  // -- Public lifecycle -------------------------------------------------------

  public open(): void {
    this.open_ = true;
    this.container.style.display = 'block';
    this.refreshWorkloads();
  }

  public close(): void {
    this.open_ = false;
    this.container.style.display = 'none';
  }

  public toggle(): void {
    if (this.open_) this.close();
    else this.open();
  }

  public isOpen(): boolean {
    return this.open_;
  }

  /**
   * Re-discover workloads from every slot's currently loaded cluster graph.
   * Call after onboarding/sample loads swap `viewport.clusterData`.
   */
  public refreshWorkloads(): void {
    const bases = new Set<string>();
    for (const slot of this.slots) {
      const data = slot.viewport.clusterData;
      const discovered: DiscoveredWorkload[] = data ? discoverWorkloads(slot.id, data) : [];
      const computeClass = data ? detectComputeClass(data) : 'static-nodepool';

      const liveIds = new Set(discovered.map((d) => d.unitId));
      this.slotUnits.set(slot.id, [...liveIds]);

      // Drop units whose workloads vanished from the graph (cluster reload).
      const stalePrefix = `${slot.id}/`;
      for (const id of this.simulator.listWorkloadIds()) {
        if (id.startsWith(stalePrefix) && !liveIds.has(id)) {
          this.simulator.removeWorkload(id);
          this.latestStates.delete(id);
        }
      }

      for (const d of discovered) {
        bases.add(d.base);
        if (this.simulator.listWorkloadIds().includes(d.unitId)) continue;
        this.simulator.addWorkload({
          id: d.unitId,
          clusterId: slot.id,
          workloadName: d.base,
          namespace: d.namespace,
          computeClassType: computeClass,
          initialReplicas: d.replicas,
          minReplicas: 1,
          maxReplicas: Math.max(12, d.replicas * 2),
          targetCpuUtilization: d.targetCpu,
          serviceRatePerPod: serviceRateFor(d.base),
          baselineLatencyMs: 12,
          hasVpa: d.hasVpa,
          podCpuCores: d.cpuCores / d.replicas,
          podMemoryGib: d.memGib / d.replicas,
        });
      }
    }

    // Preserve the operator's selection across refreshes when still valid.
    this.knownWorkloadBases = [...bases].sort();
    this.repopulateWorkloadOptions();
  }

  /** rAF pump: advance Engine A, modulate 3D flows, refresh telemetry HUD. */
  public update(deltaSeconds: number): void {
    this.simulator.update(deltaSeconds);
    this.modulateFlows();

    this.telemetryClock += deltaSeconds;
    if (this.telemetryClock >= 0.15 || !this.simulator.isRunning()) {
      this.telemetryClock = 0;
      if (this.open_) {
        this.renderTelemetry();
        this.syncHeaderPill();
        this.syncActionButtons();
      }
    }
  }

  // -- Flow modulation (SPEC-10 §6.3) ------------------------------------------

  private modulateFlows(): void {
    const running = this.simulator.isRunning();
    for (const slot of this.slots) {
      const unitIds = this.slotUnits.get(slot.id) ?? [];
      let rps = 0;
      let worstLatency = 0;
      let pending = 0;
      for (const id of unitIds) {
        rps += this.simulator.getCurrentRps(id);
        const st = this.latestStates.get(id);
        if (st) {
          worstLatency = Math.max(worstLatency, st.latencyMs);
          pending += st.pendingReplicas;
        }
      }
      // Staging-yard backlog keeps the deck honest even at low instant λ:
      // pods pending on a cold VM mean the deck is still under saturation.
      if (pending > 0) worstLatency = Math.max(worstLatency, 210);

      const active = running && unitIds.length > 0;
      // Stream speed scales directly with RPS (SPEC-10 §6.3.1).
      const speedGain = active ? Math.min(3.2, 0.55 + rps / 900) : 1;
      // Cyan < 30 ms · amber 30–200 ms · crimson > 200 ms.
      const tint = !active ? null : worstLatency < 30 ? FLOW_CYAN : worstLatency <= 200 ? FLOW_AMBER : FLOW_CRIMSON;
      const tintStrength = !active ? 0 : worstLatency < 30 ? 0.45 : worstLatency <= 200 ? 0.72 : 0.95;
      // Congestion surge particles ≈ density ∝ RPS; crimson adds sparking.
      const surge = active ? Math.min(14, Math.round(rps / 220)) + (worstLatency > 200 ? 4 : 0) : 0;

      const key = `${active ? 1 : 0}|${tint ?? 'n'}|${speedGain.toFixed(2)}|${surge}`;
      if (this.lastModKey.get(slot.id) === key) continue;
      this.lastModKey.set(slot.id, key);

      if (tint === null) {
        slot.viewport.flowSystem.clearModulation();
      } else {
        slot.viewport.flowSystem.setModulation({
          speedGain,
          tint,
          tintStrength,
          surgeCount: surge,
          surgeColor: tint,
        });
      }
    }
  }

  // -- Harness config -----------------------------------------------------------

  /** Assemble the current HUD control state into a §7.2 harness config. */
  private currentConfig(): TrafficHarnessConfig {
    return {
      targetWorkloadId: this.workloadSelect.value,
      pattern: this.pattern,
      baseRps: RPS_BASELINE,
      peakRps: this.peakRps,
      durationSeconds: 120,
      enableHpa: this.hpaCheck.checked,
      enableVpa: this.vpaCheck.checked,
      simulateProvisioningSkew: this.skewCheck.checked,
    };
  }

  /** Unit ids addressed by the current workload + cluster selectors. */
  private addressedUnitIds(): string[] {
    const workload = this.workloadSelect.value;
    const cluster = this.clusterSelect.value;
    const ids: string[] = [];
    for (const id of this.simulator.listWorkloadIds()) {
      const sep = id.indexOf('/');
      if (sep < 0) continue;
      const slotId = id.slice(0, sep);
      const base = id.slice(sep + 1);
      if (cluster !== 'all' && slotId !== cluster) continue;
      if (workload !== 'all' && base !== workload) continue;
      ids.push(id);
    }
    return ids;
  }

  /** Push the current control state onto every addressed simulator unit. */
  private applyConfigToAddressedUnits(): void {
    const cfg = this.currentConfig();
    for (const id of this.addressedUnitIds()) {
      this.simulator.configure({ ...cfg, targetWorkloadId: id });
    }
  }

  private handleInject(): void {
    if (this.injected && this.simulator.isRunning()) {
      this.simulator.stop();
      this.injected = false;
      this.pausedFlag = false;
      for (const slot of this.slots) slot.viewport.flowSystem.clearModulation();
      for (const key of this.lastModKey.keys()) this.lastModKey.delete(key);
    } else {
      this.applyConfigToAddressedUnits();
      this.simulator.start();
      this.injected = true;
      this.pausedFlag = false;
    }
    this.syncActionButtons();
    this.syncHeaderPill();
    this.renderTelemetry();
  }

  private handlePause(): void {
    if (!this.simulator.isRunning() && !this.pausedFlag) return;
    if (this.pausedFlag) {
      this.simulator.resume();
      this.pausedFlag = false;
    } else {
      this.simulator.pause();
      this.pausedFlag = true;
    }
    this.syncActionButtons();
    this.syncHeaderPill();
  }

  private handleReset(): void {
    this.simulator.reset();
    this.simulator.stop();
    this.injected = false;
    this.pausedFlag = false;
    for (const slot of this.slots) slot.viewport.flowSystem.clearModulation();
    for (const key of this.lastModKey.keys()) this.lastModKey.delete(key);
    this.syncActionButtons();
    this.syncHeaderPill();
    this.renderTelemetry();
  }

  private handleBurst(): void {
    // Burst hammers the addressed units: raise peak + overlay a 6 s spike.
    this.applyConfigToAddressedUnits();
    this.simulator.burst(BURST_RPS, 6);
    if (!this.simulator.isRunning()) {
      this.simulator.start();
      this.injected = true;
      this.pausedFlag = false;
    }
    this.syncActionButtons();
    this.syncHeaderPill();
  }

  // -- DOM assembly --------------------------------------------------------------

  private buildDom(): void {
    const style = (el: HTMLElement, css: Partial<CSSStyleDeclaration>): void => {
      Object.assign(el.style, css);
    };

    // Header ------------------------------------------------------------------
    const header = document.createElement('div');
    header.className = 'td-header';

    const title = document.createElement('span');
    title.className = 'td-title';
    title.innerHTML = '<span class="zap">⚡</span> AUTOSCALING TRAFFIC SIMULATION HARNESS';

    this.enginePill = document.createElement('span');
    this.enginePill.className = 'td-engine-pill';
    this.enginePill.textContent = 'IDLE';

    const dockBtn = document.createElement('button');
    dockBtn.className = 'td-hdr-btn';
    dockBtn.title = 'Toggle docked / floating window';
    dockBtn.textContent = '⛶ DOCK';
    dockBtn.addEventListener('click', () => {
      const undocked = this.container.classList.toggle('undocked');
      dockBtn.textContent = undocked ? '📌 DOCK' : '⛶ DOCK';
    });

    const closeBtn = document.createElement('button');
    closeBtn.className = 'td-hdr-btn';
    closeBtn.title = 'Close traffic harness (KeyT)';
    closeBtn.textContent = '✕ CLOSE';
    closeBtn.addEventListener('click', () => this.close());

    const spacer = document.createElement('div');
    spacer.className = 'td-spacer';
    style(spacer, { flex: '1' });

    header.append(title, this.enginePill, spacer, dockBtn, closeBtn);
    this.panel.appendChild(header);

    // Row: selectors ------------------------------------------------------------
    const selRow = document.createElement('div');
    selRow.className = 'td-row';

    const wlLabel = document.createElement('span');
    wlLabel.className = 'td-label';
    wlLabel.textContent = 'TARGET WORKLOAD:';
    this.workloadSelect = document.createElement('select');
    this.workloadSelect.className = 'td-select';
    this.workloadSelect.title = 'Workload discovered from loaded cluster data';
    this.workloadSelect.addEventListener('change', () => {
      if (this.injected) this.applyConfigToAddressedUnits();
      this.renderTelemetry();
    });

    const clLabel = document.createElement('span');
    clLabel.className = 'td-label';
    clLabel.textContent = 'TARGET CLUSTER:';
    this.clusterSelect = document.createElement('select');
    this.clusterSelect.className = 'td-select';
    const optAll = document.createElement('option');
    optAll.value = 'all';
    optAll.textContent = 'All Viewports (Linked)';
    this.clusterSelect.appendChild(optAll);
    for (const slot of this.slots) {
      const opt = document.createElement('option');
      opt.value = slot.id;
      opt.textContent = `${slot.label} · ${slot.title}`;
      this.clusterSelect.appendChild(opt);
    }
    this.clusterSelect.addEventListener('change', () => {
      if (this.injected) this.applyConfigToAddressedUnits();
      this.renderTelemetry();
    });

    selRow.append(wlLabel, this.workloadSelect, clLabel, this.clusterSelect);
    this.panel.appendChild(selRow);

    // Row: pattern pills ----------------------------------------------------------
    const patRow = document.createElement('div');
    patRow.className = 'td-row';
    const patLabel = document.createElement('span');
    patLabel.className = 'td-label';
    patLabel.textContent = 'TRAFFIC PATTERN:';
    const patGroup = document.createElement('div');
    patGroup.className = 'td-pill-group';
    for (const p of PATTERN_OPTIONS) {
      const btn = document.createElement('button');
      btn.className = `td-pill${p.value === this.pattern ? ' active' : ''}`;
      btn.textContent = p.label;
      btn.title = `λ(t) shape: ${p.label}`;
      btn.addEventListener('click', () => {
        this.pattern = p.value;
        for (const [val, b] of this.patternButtons) b.classList.toggle('active', val === p.value);
        if (this.injected) this.applyConfigToAddressedUnits();
      });
      this.patternButtons.set(p.value, btn);
      patGroup.appendChild(btn);
    }
    patRow.append(patLabel, patGroup);
    this.panel.appendChild(patRow);

    // Row: load slider -------------------------------------------------------------
    const loadRow = document.createElement('div');
    loadRow.className = 'td-row';
    const loadLabel = document.createElement('span');
    loadLabel.className = 'td-label';
    loadLabel.textContent = 'CONCURRENCY / LOAD:';

    this.slider = document.createElement('input');
    this.slider.type = 'range';
    this.slider.min = String(RPS_MIN);
    this.slider.max = String(RPS_MAX);
    this.slider.step = '10';
    this.slider.value = String(RPS_DEFAULT);
    this.slider.className = 'td-slider';
    this.slider.title = `Peak λ from ${RPS_MIN} to ${RPS_MAX} RPS`;

    this.rpsReadout = document.createElement('span');
    this.rpsReadout.className = 'td-rps-readout';
    const baselineNote = document.createElement('span');
    baselineNote.className = 'td-rps-baseline';
    baselineNote.textContent = `(Baseline: ${RPS_BASELINE} RPS)`;

    const syncSliderReadout = (): void => {
      this.rpsReadout.textContent = `${this.peakRps} RPS`;
    };
    this.slider.addEventListener('input', () => {
      this.peakRps = Math.min(RPS_MAX, Math.max(RPS_MIN, Number.parseInt(this.slider.value, 10) || RPS_DEFAULT));
      syncSliderReadout();
      if (this.injected) this.applyConfigToAddressedUnits();
    });
    syncSliderReadout();

    loadRow.append(loadLabel, this.slider, this.rpsReadout, baselineNote);
    this.panel.appendChild(loadRow);

    // Row: engine checkboxes ----------------------------------------------------------
    const engRow = document.createElement('div');
    engRow.className = 'td-row';
    const engLabel = document.createElement('span');
    engLabel.className = 'td-label';
    engLabel.textContent = 'AUTO-SCALING ENGINE:';

    const mkCheck = (label: string, title: string): HTMLInputElement => {
      const wrap = document.createElement('label');
      wrap.className = 'td-check';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = true;
      cb.title = title;
      wrap.append(cb, document.createTextNode(label));
      engRow.appendChild(wrap);
      return cb;
    };
    this.hpaCheck = mkCheck('HPA (Horizontal)', 'Horizontal Pod Autoscaler: 1s demo sampling, ceil(N·cpu/target) with stabilization window');
    this.vpaCheck = mkCheck('VPA Morphing', 'Vertical Pod Autoscaler: CPU > 80% for 3s → in-place capsule morph');
    this.skewCheck = mkCheck('Simulate Node Provisioning Latency', 'GKE pre-warmed slices (3–6s) vs Karpenter / static cold-VM boot (50–140s) with staging-yard hover');
    for (const cb of [this.hpaCheck, this.vpaCheck, this.skewCheck]) {
      cb.addEventListener('change', () => {
        if (this.injected) this.applyConfigToAddressedUnits();
      });
    }
    engRow.insertBefore(engLabel, engRow.firstChild);
    this.panel.appendChild(engRow);

    // Telemetry --------------------------------------------------------------------------
    const divider = document.createElement('div');
    divider.className = 'td-divider';
    divider.textContent = 'REAL-TIME COMPARATIVE TELEMETRY';
    this.panel.appendChild(divider);

    this.telemetryEl = document.createElement('div');
    this.telemetryEl.className = 'td-telemetry';
    this.panel.appendChild(this.telemetryEl);

    // Actions ------------------------------------------------------------------------------
    const actRow = document.createElement('div');
    actRow.className = 'td-row td-actions';

    this.injectBtn = document.createElement('button');
    this.injectBtn.className = 'td-btn inject';
    this.injectBtn.textContent = '▶ INJECT TRAFFIC';
    this.injectBtn.title = 'Start / stop the queuing simulation against the addressed units';
    this.injectBtn.addEventListener('click', () => this.handleInject());

    this.pauseBtn = document.createElement('button');
    this.pauseBtn.className = 'td-btn';
    this.pauseBtn.textContent = '⏸ PAUSE';
    this.pauseBtn.title = 'Freeze / resume the engine mid-run';
    this.pauseBtn.addEventListener('click', () => this.handlePause());

    const resetBtn = document.createElement('button');
    resetBtn.className = 'td-btn';
    resetBtn.textContent = '↺ RESET BASELINE';
    resetBtn.title = 'Clear queues, restore initial replicas, stop the engine';
    resetBtn.addEventListener('click', () => this.handleReset());

    const burstBtn = document.createElement('button');
    burstBtn.className = 'td-btn burst';
    burstBtn.textContent = `⚡ BURST ${BURST_RPS} RPS`;
    burstBtn.title = `Instant ${BURST_RPS} RPS spike for 6 s against the addressed units`;
    burstBtn.addEventListener('click', () => this.handleBurst());

    actRow.append(this.injectBtn, this.pauseBtn, resetBtn, burstBtn);
    this.panel.appendChild(actRow);
  }

  private repopulateWorkloadOptions(): void {
    const previous = this.workloadSelect.value;
    this.workloadSelect.innerHTML = '';

    const optAll = document.createElement('option');
    optAll.value = 'all';
    optAll.textContent = 'All Discovered Workloads';
    this.workloadSelect.appendChild(optAll);

    for (const base of this.knownWorkloadBases) {
      const opt = document.createElement('option');
      opt.value = base;
      opt.textContent = base;
      this.workloadSelect.appendChild(opt);
    }
    if (this.knownWorkloadBases.length === 0) {
      const empty = document.createElement('option');
      empty.value = '';
      empty.textContent = '(no workloads loaded)';
      empty.disabled = true;
      this.workloadSelect.appendChild(empty);
    }

    if (this.knownWorkloadBases.includes(previous)) {
      this.workloadSelect.value = previous;
    } else if (this.knownWorkloadBases.includes('frontend')) {
      this.workloadSelect.value = 'frontend';
    } else if (this.knownWorkloadBases.length > 0) {
      this.workloadSelect.value = 'all';
    }
  }

  // -- Telemetry rendering ------------------------------------------------------------

  private aggregateTelemetry(slotId: string): ViewportTelemetry {
    const t: ViewportTelemetry = {
      latencies: [],
      replicas: 0,
      desired: 0,
      pending: 0,
      cpu: [],
      errors: [],
      provisioningMs: 0,
    };
    for (const id of this.slotUnits.get(slotId) ?? []) {
      const st = this.latestStates.get(id);
      if (!st) continue;
      t.latencies.push(st.latencyMs);
      t.replicas += st.currentReplicas;
      t.desired += st.desiredReplicas;
      t.pending += st.pendingReplicas;
      t.cpu.push(st.currentCpuUtilization);
      t.errors.push(st.errorRate);
      t.provisioningMs = Math.max(t.provisioningMs, st.provisioningTimeRemainingMs);
    }
    return t;
  }

  private renderTelemetry(): void {
    this.telemetryEl.innerHTML = '';
    const anyUnits = this.knownWorkloadBases.length > 0;

    for (const slot of this.slots) {
      const data = slot.viewport.clusterData;
      const computeClass = data ? detectComputeClass(data) : 'static-nodepool';
      const t = this.aggregateTelemetry(slot.id);

      const card = document.createElement('div');
      card.className = 'td-card';

      const head = document.createElement('div');
      head.className = 'td-card-head';
      const name = document.createElement('b');
      name.textContent = `${slot.label.toUpperCase()} (${slot.title})`;
      const chip = document.createElement('span');
      const chipMod = computeClass === 'karpenter' ? ' karpenter' : computeClass === 'static-nodepool' ? ' static' : '';
      chip.className = `td-class-chip${chipMod}`;
      chip.textContent = COMPUTE_CLASS_LABEL[computeClass];
      head.append(name, chip);
      card.appendChild(head);

      if (!anyUnits || t.latencies.length === 0) {
        const idle = document.createElement('span');
        idle.className = 'td-idle-note';
        idle.textContent = 'idle — inject traffic to begin telemetry';
        card.appendChild(idle);
        this.telemetryEl.appendChild(card);
        continue;
      }

      const latency = Math.max(...t.latencies);
      const errMax = Math.max(...t.errors);
      const cpuAvg = t.cpu.reduce((a, b) => a + b, 0) / Math.max(t.cpu.length, 1);
      const scaleOut = Math.max(0, t.desired - t.replicas - t.pending);
      const band = bandFor(latency, t.pending, errMax);
      const schedS = t.pending > 0 ? t.provisioningMs / 1000 : computeClass === 'gke-compute-class' ? 3.5 : computeClass === 'karpenter' ? 95 : 120;

      const metrics = document.createElement('div');
      metrics.className = 'td-metrics';
      metrics.innerHTML =
        `<span>Latency: <b>${Math.round(latency)}ms</b></span>` +
        `<span class="td-badge ${band}">${band.toUpperCase()}</span>` +
        `<span>Replicas: <b>${t.replicas}${scaleOut > 0 ? ` (+${scaleOut})` : ''}</b></span>` +
        `<span>Pending: <b>${t.pending} in Staging</b></span>` +
        `<span>CPU: <b>${Math.round(cpuAvg)}%</b></span>` +
        `<span>Sched Delay: <b>${schedS.toFixed(1)}s</b></span>` +
        `<span>Error Rate: <b>${(errMax * 100).toFixed(1)}%</b></span>`;
      card.appendChild(metrics);

      const bar = document.createElement('div');
      bar.className = 'td-lat-bar';
      const fill = document.createElement('div');
      const pct = Math.min(100, (latency / 1000) * 100);
      fill.style.width = `${pct.toFixed(1)}%`;
      fill.style.backgroundColor =
        band === 'saturated' ? '#ef4444' : band === 'elevated' ? '#f59e0b' : '#10b981';
      bar.appendChild(fill);
      card.appendChild(bar);

      this.telemetryEl.appendChild(card);
    }
  }

  private syncHeaderPill(): void {
    if (this.simulator.isRunning()) {
      this.enginePill.textContent = 'INJECTING';
      this.enginePill.className = 'td-engine-pill running';
    } else if (this.pausedFlag) {
      this.enginePill.textContent = 'PAUSED';
      this.enginePill.className = 'td-engine-pill paused';
    } else {
      this.enginePill.textContent = 'IDLE';
      this.enginePill.className = 'td-engine-pill';
    }
  }

  private syncActionButtons(): void {
    const live = this.injected && (this.simulator.isRunning() || this.pausedFlag);
    this.injectBtn.textContent = live ? '■ STOP TRAFFIC' : '▶ INJECT TRAFFIC';
    this.injectBtn.classList.toggle('active', live);
    this.pauseBtn.textContent = this.pausedFlag ? '▶ RESUME' : '⏸ PAUSE';
  }

  // -- Host plumbing ----------------------------------------------------------------------

  private static stylesInjected = false;

  private static ensureStyles(): void {
    if (TrafficControlDeck.stylesInjected) return;
    TrafficControlDeck.stylesInjected = true;
    const style = document.createElement('style');
    style.id = 'traffic-deck-styles';
    style.textContent = DECK_CSS;
    document.head.appendChild(style);
  }

  /** Fallback when index.html lacks `#traffic-deck-dock` (defensive). */
  private static ensureDockContainer(): HTMLElement {
    const existing = document.getElementById('traffic-deck-dock');
    if (existing) return existing;
    const el = document.createElement('div');
    el.id = 'traffic-deck-dock';
    el.style.cssText =
      'position:fixed;left:0;right:0;bottom:0;z-index:560;pointer-events:auto;';
    document.body.appendChild(el);
    return el;
  }
}

/** Narrow shim: `input[type=range]` is just HTMLInputElement. */
type HTMLRangeInputElementShim = HTMLInputElement;
