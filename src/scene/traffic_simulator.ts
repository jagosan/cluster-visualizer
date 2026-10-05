/**
 * SPEC-10 / TASK-CV-1104: Client-Side Queuing Simulation & Autoscaling Engine.
 *
 * Deterministic, discrete-event-flavoured M/M/c/K traffic harness driving
 * the 3D viewport (Engine A of the SPEC-10 §4.2 hybrid dual-engine design).
 * Runs identically on live-connected clusters, sample-catalog clusters, and
 * fully offline demos — zero cloud cost, millisecond-reproducible.
 *
 * ---------------------------------------------------------------------------
 * Queuing physics (SPEC-10 §5.1)
 * ---------------------------------------------------------------------------
 * Each workload unit is an M/M/c/K multiserver queue:
 *   c = N(t) ready pod replicas · K = finite ingress buffer (default 4096)
 *   λ(t) = pattern-shaped aggregate arrival rate (step | sine | ramp | chaos)
 *   μ    = per-replica service rate (120 req/s Go/C# microservices default,
 *          25 req/s Python ML inference)
 *   ρ(t) = λ(t) / (N(t)·μ)
 *
 * Latency transfer function:
 *   ρ < 1:   L(t) = L_base + ErlangC-Wq(c, a)·1000   (bounded; 10–40 ms for
 *            ρ < 0.7, transient ~48 ms peaks under pre-warmed fabric)
 *   ρ ≥ 1:   W_q(t) relaxes toward a deficit-proportional plateau
 *            dW_q/dt = (target(deficit) − W_q)/τ_approach   (ms per second)
 *            with target = clamp(deficitFrac·180 ms, 120, 3800 ms) —
 *            latency spikes 500–800 ms+ and error rate climbs to ~18–23%
 *            L(t) = L_base + 1000/μ + W_q(t)                 (150–800 ms+)
 *   W_q drains exponentially (τ = 3 s) once capacity recovers, matching the
 *   "recovers to 12 ms baseline in < 8 s" acceptance behaviour.
 *   L > 2000 ms → HTTP 504/503 timeout losses; buffer overflow (Q > K)
 *   sheds requests; error rate is an EWMA of both pressure sources, clamped
 *   to the SPEC-10 §5.3 benchmark band (≤ 25%, ~15–20% under a cold-VM
 *   provisioning stall).
 *
 * ---------------------------------------------------------------------------
 * Kubernetes autoscaling (SPEC-10 §5.2)
 * ---------------------------------------------------------------------------
 *   HPA: sampled every hpaIntervalSeconds (15 s production default, 1 s for
 *     rapid UI demos): CPU% = min(100, ρ·100);
 *     desired = ceil(N · cpu / targetCpu), clamped to [min, max] and the
 *     per-evaluation burst cap max(2N, N+4); scale-down only after a
 *     stabilization window of quiet lower demand.
 *   VPA (Auto): CPU > 80% sustained for 3 s → recommendation (ghost hull),
 *     committed after the in-place morph delay (τ_vpa = 1.2 s on GKE
 *     Compute Class fabric; 45 s eviction-reschedule elsewhere), scaling the
 *     pod's effective μ.
 *
 * ---------------------------------------------------------------------------
 * Comparative scheduling-latency skew (SPEC-10 §5.3)
 * ---------------------------------------------------------------------------
 *   gke-compute-class : pre-warmed compute slices — τ_sched ≈ 3.0–6.0 s,
 *     transient deficit largely absorbed by the elastic fabric (peak ≈ 42 ms,
 *     0% error).
 *   karpenter         : cold EC2/Azure VM provisioning — τ_node ≈ 50–140 s
 *     (default 95 s); pods hover `Pending` in the exterior staging yard
 *     (X < −12.0, SPEC-09 §4.2) under amber tractor beams while the queue
 *     saturates (500–750 ms, 15–20% errors).
 *   static-nodepool   : traditional cluster-autoscaler cadence, default
 *     τ_node = 120 s, same staging behaviour.
 *
 * Time advances only through `update(deltaSeconds)` — the engine owns no
 * wall-clock timers, so playback is deterministic under rAF or a Web Worker.
 */

import type { HpaScaleOutEvent } from './autoscaling_fx.js';
import { capsuleDims } from './autoscaling_fx.js';
import type { ClusterViewport } from './cluster_viewport.js';

// ---------------------------------------------------------------------------
// Data contracts (SPEC-10 §7.2)
// ---------------------------------------------------------------------------

export type TrafficPattern = 'step' | 'sine' | 'ramp' | 'chaos';

export type ComputeClassType = 'gke-compute-class' | 'karpenter' | 'static-nodepool';

export interface TrafficHarnessConfig {
  targetWorkloadId: string;
  pattern: TrafficPattern;
  baseRps: number;
  peakRps: number;
  durationSeconds: number;
  enableHpa: boolean;
  enableVpa: boolean;
  simulateProvisioningSkew: boolean;
}

export interface WorkloadScalingState {
  clusterId: string;
  workloadName: string;
  currentReplicas: number;
  desiredReplicas: number;
  pendingReplicas: number;
  currentCpuUtilization: number;
  targetCpuUtilization: number;
  latencyMs: number;
  errorRate: number;
  computeClassType: ComputeClassType;
  provisioningTimeRemainingMs: number;
}

// ---------------------------------------------------------------------------
// Spec extension types
// ---------------------------------------------------------------------------

/** Declarative description of a workload the harness may drive. */
export interface SimulatedWorkloadSpec {
  id: string;
  clusterId: string;
  workloadName: string;
  namespace?: string;
  computeClassType: ComputeClassType;
  initialReplicas?: number;
  minReplicas?: number;
  maxReplicas?: number;
  /** HPA target CPU utilization percent (default 60). */
  targetCpuUtilization?: number;
  /** μ per pod replica in req/s — 120 microservice / 25 AI-ML (default 120). */
  serviceRatePerPod?: number;
  /** L_base in ms (default 12). */
  baselineLatencyMs?: number;
  hasVpa?: boolean;
  /** Pod resource footprint for VPA capsule-dim morphs. */
  podCpuCores?: number;
  podMemoryGib?: number;
  /** Node chassis node-id used as the HPA lateral conveyor anchor. */
  anchorNodeId?: string;
}

export interface PendingPodStagedEvent {
  clusterId: string;
  workloadName: string;
  podId: string;
  /** Exterior staging yard hover coordinates (X < -12.0). */
  position: { x: number; y: number; z: number };
  /** Ghost chassis for the amber tractor beam (karpenter only). */
  claimName?: string | null;
  estimatedReadyMs: number;
}

/** Chaos-pattern internal regime state (public for determinism tests). */
export interface ChaosTrafficState {
  chaosValue: number;
  chaosNextFlipAt: number;
  chaosUp: boolean;
}

export interface TrafficSimulatorCallbacks {
  /** Fired every update tick with a fresh snapshot of all unit states. */
  onStateUpdate?: (states: WorkloadScalingState[], simTimeSeconds: number) => void;
  /** HPA scale-out landed: new replicas transitioned Pending → Running. */
  onHpaScaleOut?: (clusterId: string, workloadName: string, event: HpaScaleOutEvent) => void;
  /** VPA recommendation published (ghost hull target dims). */
  onVpaRecommendation?: (
    clusterId: string,
    workloadName: string,
    nodeId: string,
    height: number,
    radius: number,
  ) => void;
  /** VPA resize committed — morph the capsule over durationMs. */
  onVpaResize?: (
    clusterId: string,
    workloadName: string,
    nodeId: string,
    height: number,
    radius: number,
    durationMs: number,
  ) => void;
  /** A replica parked in the exterior staging yard awaiting a node. */
  onPendingStaged?: (event: PendingPodStagedEvent) => void;
  /** A staged replica finally scheduled (remove hover / tractor beam). */
  onPodScheduled?: (clusterId: string, workloadName: string, podId: string) => void;
}

export interface TrafficSimulatorOptions {
  /** HPA evaluation period in seconds (SPEC-10 §5.2: 15 s, 1 s for demos). */
  hpaIntervalSeconds?: number;
  /** Scale-down stabilization window (default 30 s; 300 s in production). */
  scaleDownStabilizationSeconds?: number;
  /** Deterministic PRNG seed for chaos flapping (default 1337). */
  seed?: number;
  callbacks?: TrafficSimulatorCallbacks;
}

// ---------------------------------------------------------------------------
// Tuned physics constants (SPEC-10 §5.3 benchmark calibration)
// ---------------------------------------------------------------------------

/** Approach time-constant for the saturated-regime queue delay W_q. */
const WQ_APPROACH_TAU_S = 6.0;
/** Exponential W_q drain time-constant once λ < N·μ. */
const WQ_DRAIN_TAU_S = 3.0;
/** Queue-delay target: ms per unit of relative deficit (λ−cμ)/cμ. */
const WQ_TARGET_GAIN_MS = 180;
const WQ_TARGET_MIN_MS = 120;
const WQ_TARGET_MAX_MS = 3800;
/** Nominal saturation queue depth (ms) mapped to the §5.3 18.4% error row:
 *  13.4% timeout pressure at the 720 ms plateau + 5.0% ingress-buffer drops. */
const ERROR_WQ_NOMINAL_MS = 720;
const ERROR_WQ_RATE = 0.134;
/** Request timeout threshold (ms) above which 504/503 losses accrue. */
const LATENCY_TIMEOUT_MS = 2000;
/** Finite ingress buffer K (requests) before shedding begins. */
const INGRESS_BUFFER_K = 4096;
/** Error-rate ceiling for the benchmark band. */
const ERROR_RATE_MAX = 0.25;
/** CPU band where VPA in-place morphing engages (SPEC-10 §5.2). */
const VPA_SUSTAINED_CPU_PCT = 80;
const VPA_SUSTAIN_SECONDS = 3;

/** Per-compute-class scheduling latency profile (SPEC-10 §5.3). */
interface SchedProfile {
  /** Pod scheduling delay base in seconds. */
  schedDelayS: number;
  /** Jitter half-width on the scheduling delay. */
  schedJitterS: number;
  /** Cold node provisioning delay base (0 = fabric pre-warmed, no VM boot). */
  nodeProvisionS: number;
  /** VPA in-place morph / eviction delay. */
  vpaDelayS: number;
  /** Fraction of transient deficit the pre-warmed fabric absorbs (0..1). */
  deficitAbsorb: number;
  /** Buffer multiplier: elastic fabric admits far more before shedding. */
  bufferScale: number;
}

export const SCHED_PROFILES: Record<ComputeClassType, SchedProfile> = {
  'gke-compute-class': {
    schedDelayS: 3.5,
    schedJitterS: 1.25, // τ_sched ∈ [3.0, 6.0] s (in practice clamped below)
    nodeProvisionS: 0,
    vpaDelayS: 1.2,
    deficitAbsorb: 0.82, // pre-warmed slices soak transients → ~42 ms peak
    bufferScale: 16,
  },
  karpenter: {
    schedDelayS: 95,
    schedJitterS: 45, // τ_node ≈ 50–140 s ≈ the 60–150 s cold-VM band
    nodeProvisionS: 95,
    vpaDelayS: 45, // eviction + reschedule — no in-place resize
    deficitAbsorb: 0,
    bufferScale: 1,
  },
  'static-nodepool': {
    schedDelayS: 120,
    schedJitterS: 30, // τ_node ∈ [90, 150] s
    nodeProvisionS: 120,
    vpaDelayS: 45,
    deficitAbsorb: 0,
    bufferScale: 1,
  },
};

// Staging-yard hover grid (mirror of layout.stage_pending_pod, SPEC-09 §4.2).
const PENDING_HOVER_Y = 1.0;
const PENDING_HOVER_X_MIN = -22.0;
const PENDING_HOVER_X_MAX = -14.0;
const PENDING_HOVER_Z_MIN = -6.0;
const PENDING_HOVER_Z_MAX = 6.0;
const PENDING_HOVER_COLS = 4;
const PENDING_HOVER_SPACING = 2.0;

// ---------------------------------------------------------------------------
// Deterministic PRNG (mulberry32)
// ---------------------------------------------------------------------------

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

// ---------------------------------------------------------------------------
// Traffic pattern generators (SPEC-10 §6.2 radio row)
// ---------------------------------------------------------------------------

/**
 * Pure pattern shapes over [baseRps, peakRps]:
 *   step  — base until t = 2 s, then hard spike to peak and hold;
 *   sine  — raised cosine anchored at base, period = max(8, dur/2);
 *   ramp  — linear climb to peak over the first 80% of the duration;
 *   chaos — regime-flapping random walk (4–12 s regimes, PRNG-driven).
 * `dt` shapes the chaos pull; `state` carries the chaos regime across ticks.
 */
export function patternRps(
  pattern: TrafficPattern,
  t: number,
  dt: number,
  baseRps: number,
  peakRps: number,
  durationSeconds: number,
  rng: () => number,
  state: ChaosTrafficState,
): number {
  const lo = Math.max(0, baseRps);
  const hi = Math.max(lo, peakRps);
  switch (pattern) {
    case 'step': {
      // Step spike fires at t = 2 s and holds at peak (HUD "Inject Traffic").
      return t < 2 ? lo : hi;
    }
    case 'sine': {
      // Raised cosine anchored at base: lo at t=0, peak at period/2.
      const period = Math.max(8, durationSeconds / 2);
      return lo + (hi - lo) * (0.5 - 0.5 * Math.cos((2 * Math.PI * t) / period));
    }
    case 'ramp': {
      const ramp = Math.max(1, durationSeconds * 0.8);
      return lo + (hi - lo) * clamp(t / ramp, 0, 1);
    }
    case 'chaos': {
      if (t >= state.chaosNextFlipAt) {
        state.chaosUp = rng() < 0.5;
        state.chaosNextFlipAt = t + 4 + rng() * 8;
      }
      const target = state.chaosUp ? hi : lo * 1.2;
      const pull = 1 - Math.exp(-clamp(dt, 0, 1) / 1.5);
      state.chaosValue = state.chaosValue + (target - state.chaosValue) * clamp(pull, 0, 1);
      const jitter = (rng() - 0.5) * (hi - lo) * 0.08;
      return clamp(state.chaosValue + jitter, lo * 0.5, hi * 1.05);
    }
    default: {
      const never: never = pattern;
      return never;
    }
  }
}

/**
 * Erlang-C mean waiting time (ms) for an M/M/c queue in the stable regime.
 * `servers` = replica count c, `offeredErlangs` a = λ/μ, and
 * `spareCapacityPerSec` = c·μ − λ (> 0). Returns 0 when the queue would be
 * unstable (callers handle ρ ≥ 1 via the integrated W_q deficit instead).
 */
export function erlangCWaitMs(
  servers: number,
  offeredErlangs: number,
  spareCapacityPerSec: number,
): number {
  const c = Math.max(1, Math.floor(servers));
  const a = Math.max(0, offeredErlangs);
  if (a >= c || spareCapacityPerSec <= 0) return 0;
  // a^k/k! iteratively; sum the k < c series, keep the k = c term.
  let term = 1;
  let sum = 1;
  for (let k = 1; k <= c; k++) {
    term = (term * a) / k;
    if (k < c) sum += term;
  }
  const erlangB = term / (sum + term);
  // C(c,a) = c·B / (c − a·(1−B))
  const denom = c - a * (1 - erlangB);
  const erlangC = denom > 1e-9 ? (c * erlangB) / denom : 0;
  return (erlangC / spareCapacityPerSec) * 1000;
}

/** Deterministic staging-yard hover grid position (X always < -12.0). */
export function stagingHoverPosition(index: number): { x: number; y: number; z: number } {
  const i = Math.abs(Math.floor(index));
  const col = i % PENDING_HOVER_COLS;
  const row = Math.floor(i / PENDING_HOVER_COLS);
  const x = clamp(PENDING_HOVER_X_MIN + col * PENDING_HOVER_SPACING, PENDING_HOVER_X_MIN, PENDING_HOVER_X_MAX);
  const z = clamp(PENDING_HOVER_Z_MIN + (row % 7) * PENDING_HOVER_SPACING, PENDING_HOVER_Z_MIN, PENDING_HOVER_Z_MAX);
  return { x: Math.round(x * 1000) / 1000, y: PENDING_HOVER_Y, z: Math.round(z * 1000) / 1000 };
}

// ---------------------------------------------------------------------------
// Internal per-workload simulation unit
// ---------------------------------------------------------------------------

interface PendingReplica {
  podId: string;
  readyAt: number; // sim seconds
  stagedIndex: number;
  claimName: string | null;
}

interface UnitRuntime extends ChaosTrafficState {
  spec: SimulatedWorkloadSpec;
  config: TrafficHarnessConfig;
  currentReplicas: number;
  desiredReplicas: number;
  pending: PendingReplica[];
  cpuUtilization: number;
  latencyMs: number;
  errorRate: number;
  wqMs: number;
  queueLength: number;
  vpaCpuFactor: number;
  vpaCpuHighSince: number | null;
  vpaPendingCommitAt: number | null;
  vpaPendingFactor: number | null;
  lastHpaEval: number;
  scaleDownCandidateSince: number | null;
  lastScaleUpAt: number;
  stagedCounter: number;
  burstUntil: number;
  burstRps: number;
  currentLambda: number;
}

// ---------------------------------------------------------------------------
// TrafficSimulator
// ---------------------------------------------------------------------------

/**
 * Drives every SPEC-10 traffic unit and dispatches viewport animation
 * triggers. Register workloads with `addWorkload`, shape demand with
 * `configure`, then run `start()` and pump `update(dt)` from the render loop.
 * Attached viewports (SPEC-09 pipelines: `applyHpaScaleOut`,
 * `applyVpaResize`, `applyKarpenterClaim` / `applyKarpenterTractorBeam`)
 * receive the matching 3D animations automatically.
 */
export class TrafficSimulator {
  private readonly units = new Map<string, UnitRuntime>();
  private readonly callbacks: TrafficSimulatorCallbacks;
  private readonly hpaIntervalSeconds: number;
  private readonly scaleDownStabilizationSeconds: number;
  private readonly rng: () => number;

  private simTime = 0;
  private running = false;
  private paused = false;

  /** clusterId ('*' = linked/all) -> viewports reacting to the triggers. */
  private readonly viewports: Array<{ clusterId: string; viewport: ClusterViewport }> = [];

  constructor(options: TrafficSimulatorOptions = {}) {
    this.callbacks = options.callbacks ?? {};
    this.hpaIntervalSeconds = Math.max(0.25, options.hpaIntervalSeconds ?? 1.0);
    this.scaleDownStabilizationSeconds = Math.max(0, options.scaleDownStabilizationSeconds ?? 30);
    this.rng = mulberry32(options.seed ?? 1337);
  }

  // -- Registration ----------------------------------------------------------

  public addWorkload(spec: SimulatedWorkloadSpec, config?: Partial<TrafficHarnessConfig>): void {
    if (this.units.has(spec.id)) this.removeWorkload(spec.id);
    const initial = Math.max(1, Math.floor(spec.initialReplicas ?? 2));
    const fullConfig: TrafficHarnessConfig = {
      targetWorkloadId: spec.id,
      pattern: 'step',
      baseRps: 100,
      peakRps: 850,
      durationSeconds: 120,
      enableHpa: true,
      enableVpa: spec.hasVpa === true,
      simulateProvisioningSkew: true,
      ...config,
      // targetWorkloadId always tracks the owning unit.
    };
    fullConfig.targetWorkloadId = spec.id;
    const mu = spec.serviceRatePerPod ?? 120;
    this.units.set(spec.id, {
      spec,
      config: fullConfig,
      currentReplicas: initial,
      desiredReplicas: initial,
      pending: [],
      cpuUtilization: clamp((fullConfig.baseRps / Math.max(initial * mu, 1)) * 100, 0, 100),
      latencyMs: spec.baselineLatencyMs ?? 12,
      errorRate: 0,
      wqMs: 0,
      queueLength: 0,
      vpaCpuFactor: 1,
      vpaCpuHighSince: null,
      vpaPendingCommitAt: null,
      vpaPendingFactor: null,
      lastHpaEval: 0,
      scaleDownCandidateSince: null,
      lastScaleUpAt: -Infinity,
      stagedCounter: 0,
      burstUntil: 0,
      burstRps: 0,
      chaosValue: fullConfig.baseRps,
      chaosNextFlipAt: 0,
      chaosUp: true,
      currentLambda: fullConfig.baseRps,
    });
  }

  public removeWorkload(id: string): void {
    this.units.delete(id);
  }

  /** Apply a §7.2 harness config to its target workload ('all' = every unit). */
  public configure(config: TrafficHarnessConfig): void {
    for (const unit of this.units.values()) {
      if (config.targetWorkloadId !== 'all' && config.targetWorkloadId !== unit.spec.id) continue;
      unit.config = { ...config, targetWorkloadId: unit.spec.id };
      unit.chaosValue = config.baseRps;
      unit.chaosNextFlipAt = 0;
    }
  }

  // -- Lifecycle ---------------------------------------------------------------

  public start(): void {
    this.running = true;
    this.paused = false;
  }

  public stop(): void {
    this.running = false;
    this.paused = false;
  }

  public pause(): void {
    if (this.running) this.paused = true;
  }

  public resume(): void {
    if (this.running) this.paused = false;
  }

  public isRunning(): boolean {
    return this.running && !this.paused;
  }

  public getSimTime(): number {
    return this.simTime;
  }

  /**
   * Reset every unit to its initial replica count and clean queue state.
   * Also un-pauses a paused engine so the HUD "↺ RESET BASELINE" button
   * immediately resumes from a clean slate.
   */
  public reset(): void {
    this.paused = false;
    this.simTime = 0;
    for (const unit of this.units.values()) {
      const initial = Math.max(1, Math.floor(unit.spec.initialReplicas ?? 2));
      unit.currentReplicas = initial;
      unit.desiredReplicas = initial;
      for (const p of unit.pending) {
        this.notifyPodScheduled(unit.spec.clusterId, unit.spec.workloadName, p.podId);
      }
      unit.pending = [];
      unit.cpuUtilization = 0;
      unit.latencyMs = unit.spec.baselineLatencyMs ?? 12;
      unit.errorRate = 0;
      unit.wqMs = 0;
      unit.queueLength = 0;
      unit.vpaCpuFactor = 1;
      unit.vpaCpuHighSince = null;
      unit.vpaPendingCommitAt = null;
      unit.vpaPendingFactor = null;
      unit.lastHpaEval = 0;
      unit.scaleDownCandidateSince = null;
      unit.burstUntil = 0;
      unit.burstRps = 0;
      unit.chaosValue = unit.config.baseRps;
      unit.chaosNextFlipAt = 0;
      unit.currentLambda = unit.config.baseRps;
    }
    this.emitState();
  }

  /** Instantaneous injection override ("⚡ BURST 2000 RPS" HUD button). */
  public burst(rps: number, durationSeconds = 6): void {
    const target = Math.max(0, rps);
    for (const unit of this.units.values()) {
      unit.burstRps = target;
      unit.burstUntil = this.simTime + Math.max(0.25, durationSeconds);
    }
  }

  // -- Main tick ---------------------------------------------------------------

  /**
   * Advance the simulation by deltaSeconds (rAF delta or fixed step). The
   * engine is inert until `start()`; `pause()` freezes physics but state
   * snapshots remain queryable for HUD repaint.
   */
  public update(deltaSeconds: number): void {
    if (!this.running || this.units.size === 0) return;
    const dt = clamp(deltaSeconds, 0, 0.25); // rAF spike guard
    if (!this.paused && dt > 0) {
      this.simTime += dt;
      for (const unit of this.units.values()) {
        this.stepUnit(unit, dt);
      }
    }
    this.emitState();
  }

  private stepUnit(unit: UnitRuntime, dt: number): void {
    const t = this.simTime;
    const cfg = unit.config;
    const profile = SCHED_PROFILES[unit.spec.computeClassType];

    // 1. Arrival rate λ(t) -----------------------------------------------------
    let lambda = patternRps(cfg.pattern, t, dt, cfg.baseRps, cfg.peakRps, cfg.durationSeconds, this.rng, unit);
    if (t < unit.burstUntil) lambda = Math.max(lambda, unit.burstRps);
    lambda = Math.max(0, lambda);
    unit.currentLambda = lambda;

    // 2. Resolve staged pending replicas coming online --------------------------
    for (let i = unit.pending.length - 1; i >= 0; i--) {
      const p = unit.pending[i];
      if (!p || p.readyAt > t) continue;
      unit.pending.splice(i, 1);
      unit.currentReplicas += 1;
      this.notifyPodScheduled(unit.spec.clusterId, unit.spec.workloadName, p.podId);
      this.fireHpaLanding(unit, p);
    }

    // 3. Queue physics -----------------------------------------------------------
    // Pre-warmed compute fabric (GKE Compute Class) admits a fraction of the
    // offered load onto elastic slices while pods schedule — modelled as a
    // λ reduction so the small residual stays inside the Erlang-C regime and
    // peaks near the §5.3 ~42–48 ms transient. Cold-VM classes (karpenter /
    // static-nodepool) admit everything onto the saturated deck.
    const muPerPod = (unit.spec.serviceRatePerPod ?? 120) * unit.vpaCpuFactor;
    const capacity = unit.currentReplicas * muPerPod;
    const rho = capacity > 0 ? lambda / capacity : 4; // reported utilization is raw ρ
    const baseLatency = unit.spec.baselineLatencyMs ?? 12;
    const fabricFactor = unit.config.simulateProvisioningSkew ? 1 - profile.deficitAbsorb : 1;
    const offered = lambda * fabricFactor;
    unit.cpuUtilization = clamp(rho * 100, 0, 100);

    const saturated = capacity <= 0 || offered >= capacity;
    if (!saturated) {
      // Stable regime: Erlang-C mean sojourn — L = L_base + Wq(c, a).
      const waitMs = erlangCWaitMs(unit.currentReplicas, offered / muPerPod, capacity - offered);
      unit.latencyMs = baseLatency + waitMs;
      // Residual queue drains exponentially toward zero.
      unit.wqMs *= Math.exp(-dt / WQ_DRAIN_TAU_S);
      unit.queueLength = Math.max(0, unit.queueLength - capacity * dt);
    } else {
      // Saturated regime: the unserved deficit (SPEC-10 §5.1 ∫max(0, λ−Nμ)ds)
      // drives W_q toward a deficit-proportional plateau with first-order
      // approach dynamics (bounded, monotone — the visual queue "fills").
      const deficitFrac = Math.max(0, (offered - capacity) / Math.max(capacity, 1));
      const targetWq = clamp(deficitFrac * WQ_TARGET_GAIN_MS, WQ_TARGET_MIN_MS, WQ_TARGET_MAX_MS);
      unit.wqMs += (targetWq - unit.wqMs) * clamp(dt / WQ_APPROACH_TAU_S, 0, 1);
      unit.latencyMs = baseLatency + 1000 / Math.max(muPerPod, 1) + unit.wqMs;
      unit.queueLength += (offered - capacity) * dt;
    }
    unit.latencyMs = clamp(unit.latencyMs, baseLatency, 5000);

    // 4. Error accrual -------------------------------------------------------------
    // Saturation queue depth maps linearly onto the HTTP error band: the
    // §5.3 benchmark's 720 ms plateau ≈ 18.4% timeouts/drops; the pre-warmed
    // fabric never accumulates queue and reads back ≈ 0%.
    const bufferLimit = INGRESS_BUFFER_K * profile.bufferScale;
    let errSample = 0;
    if (saturated) {
      errSample = clamp(ERROR_WQ_RATE * (unit.wqMs / ERROR_WQ_NOMINAL_MS), 0, ERROR_RATE_MAX);
      if (unit.queueLength > bufferLimit) {
        errSample = clamp(errSample + 0.05, 0, ERROR_RATE_MAX);
      }
    }
    if (unit.latencyMs > LATENCY_TIMEOUT_MS) {
      errSample = clamp(
        errSample + clamp((unit.latencyMs - LATENCY_TIMEOUT_MS) / LATENCY_TIMEOUT_MS, 0, 1) * 0.4,
        0,
        ERROR_RATE_MAX,
      );
    }
    unit.errorRate += (errSample - unit.errorRate) * clamp(dt * 0.8, 0, 0.3); // EWMA

    // 5. HPA evaluation loop (SPEC-10 §5.2) ---------------------------------------
    if (cfg.enableHpa && t - unit.lastHpaEval >= this.hpaIntervalSeconds) {
      unit.lastHpaEval = t;
      this.evaluateHpa(unit, t);
    }

    // 6. VPA evaluation loop (SPEC-10 §5.2) ----------------------------------------
    if (cfg.enableVpa) {
      this.evaluateVpa(unit, t);
    }
  }

  private evaluateHpa(unit: UnitRuntime, t: number): void {
    const target = clamp(unit.spec.targetCpuUtilization ?? 60, 5, 95);
    const currentMetric = clamp(unit.cpuUtilization, 0, 100); // min(100%, ρ·100)
    const liveTotal = unit.currentReplicas + unit.pending.length;

    let desired = liveTotal;
    if (currentMetric > target) {
      desired = Math.ceil((liveTotal * currentMetric) / target);
    } else if (currentMetric < target * 0.5) {
      desired = Math.max(1, Math.floor((liveTotal * currentMetric) / target));
    }
    const minR = Math.max(1, unit.spec.minReplicas ?? 1);
    const maxR = Math.max(minR, unit.spec.maxReplicas ?? 10);
    desired = clamp(desired, minR, maxR);
    // Per-evaluation burst cap (K8s horizontal scaling rule max(2N, N+4)).
    const burstCap = Math.max(2 * liveTotal, unit.currentReplicas + 4);
    desired = Math.min(desired, Math.max(liveTotal, burstCap));

    if (desired > liveTotal) {
      // Scale-out: spawn pending replicas with compute-class scheduling skew.
      this.spawnPending(unit, desired - liveTotal, t);
      unit.scaleDownCandidateSince = null;
      unit.lastScaleUpAt = t;
    } else if (desired < unit.currentReplicas && unit.pending.length === 0) {
      // Scale-down: honor the stabilization window of quiet demand.
      if (unit.scaleDownCandidateSince === null) {
        unit.scaleDownCandidateSince = t;
      } else if (t - unit.scaleDownCandidateSince >= this.scaleDownStabilizationSeconds) {
        unit.currentReplicas = desired;
        unit.scaleDownCandidateSince = null;
      }
    } else {
      unit.scaleDownCandidateSince = null;
    }
    unit.desiredReplicas = Math.max(desired, unit.currentReplicas);
  }

  private spawnPending(unit: UnitRuntime, count: number, t: number): void {
    const profile = SCHED_PROFILES[unit.spec.computeClassType];
    const skew = unit.config.simulateProvisioningSkew;
    const maxReplicas = Math.max(unit.spec.maxReplicas ?? 10, unit.currentReplicas);
    const room = Math.max(0, maxReplicas - unit.currentReplicas - unit.pending.length);
    const spawnCount = Math.min(count, room, 8);
    for (let i = 0; i < spawnCount; i++) {
      const stagedIndex = unit.stagedCounter++;
      const jitter = (this.rng() - 0.5) * 2 * profile.schedJitterS;
      let delay: number;
      if (!skew) {
        delay = 1.5 + i * 0.2; // warm-fabric fast path
      } else if (profile.nodeProvisionS > 0) {
        delay = clamp(profile.schedDelayS + jitter, profile.schedDelayS - profile.schedJitterS, profile.schedDelayS + profile.schedJitterS);
      } else {
        delay = clamp(profile.schedDelayS + jitter * 0.4, 3.0, 6.0); // GKE: τ_sched ∈ [3, 6] s
      }
      const podId = `pod/${unit.spec.namespace ?? 'default'}/${unit.spec.workloadName}-sim-${stagedIndex}-${Math.floor(t).toString(36)}`;
      const claimName =
        skew && unit.spec.computeClassType === 'karpenter'
          ? `sim-${unit.spec.workloadName}-${stagedIndex}`
          : null;
      unit.pending.push({ podId, readyAt: t + delay, stagedIndex, claimName });

      // Cold-provisioning pods stage in the exterior yard (X < -12.0,
      // SPEC-09 §4.2); GKE fast-path pods only briefly hover (< 6 s) and the
      // viewport handles them through the HPA landing conveyor instead.
      if (delay > 6) {
        this.notifyPendingStaged({
          clusterId: unit.spec.clusterId,
          workloadName: unit.spec.workloadName,
          podId,
          position: stagingHoverPosition(stagedIndex),
          claimName,
          estimatedReadyMs: Math.round(delay * 1000),
        });
      }
    }
  }

  private fireHpaLanding(unit: UnitRuntime, landed: PendingReplica): void {
    const anchorX = 0.0;
    const slotOffsetX = 0.6 + (landed.stagedIndex % 4) * 0.15;
    const z = landed.stagedIndex % 2 === 0 ? 0.2 : 1.2;
    const event: HpaScaleOutEvent = {
      node_id: unit.spec.anchorNodeId ?? 'node/worker-01',
      delta: 1,
      current_replicas: Math.max(0, unit.currentReplicas - 1),
      desired_replicas: unit.desiredReplicas,
      target_metric: `cpu:${unit.spec.targetCpuUtilization ?? 60}`,
      dispatch_from: { x: 0.0, y: 4.5, z: 0.0 }, // Supervisor Floor (SPEC-09 §3.3.1)
      riser_bottom: { x: anchorX, y: 0.75, z: 0.0 },
      lateral_path: {
        intake: [anchorX + 2.6, 0.75, z], // DECK_INTAKE_OFFSET_X
        slot: [anchorX + slotOffsetX, 0.75, z],
      },
      timestamp: new Date().toISOString(),
    };
    this.notifyHpaScaleOut(unit.spec.clusterId, unit.spec.workloadName, event);
  }

  private evaluateVpa(unit: UnitRuntime, t: number): void {
    const profile = SCHED_PROFILES[unit.spec.computeClassType];

    // Commit a recommended resize once its morph delay has elapsed.
    if (unit.vpaPendingCommitAt !== null && t >= unit.vpaPendingCommitAt) {
      const factor = unit.vpaPendingFactor ?? 1;
      unit.vpaCpuFactor = clamp(unit.vpaCpuFactor * factor, 0.5, 4);
      unit.vpaPendingCommitAt = null;
      unit.vpaPendingFactor = null;
      unit.vpaCpuHighSince = null;

      const cpu = (unit.spec.podCpuCores ?? 0.5) * unit.vpaCpuFactor;
      const mem = (unit.spec.podMemoryGib ?? 1) * Math.sqrt(unit.vpaCpuFactor);
      const dims = capsuleDims(cpu, mem);
      const nodeId = unit.spec.anchorNodeId ?? `pod/${unit.spec.workloadName}`;
      this.notifyVpaResize(unit.spec.clusterId, unit.spec.workloadName, nodeId, dims.height, dims.radius, 1200);
      return;
    }

    // Sustained-CPU trigger: CPU > 80% for 3 continuous seconds (SPEC-10 §5.2).
    if (unit.cpuUtilization > VPA_SUSTAINED_CPU_PCT) {
      if (unit.vpaCpuHighSince === null) unit.vpaCpuHighSince = t;
      const sustained = t - unit.vpaCpuHighSince;
      if (sustained >= VPA_SUSTAIN_SECONDS && unit.vpaPendingCommitAt === null) {
        const factor = clamp(unit.cpuUtilization / Math.max(unit.spec.targetCpuUtilization ?? 60, 5), 1.05, 2);
        unit.vpaPendingFactor = factor;
        unit.vpaPendingCommitAt = t + (unit.config.simulateProvisioningSkew ? profile.vpaDelayS : 1.2);

        const cpu = (unit.spec.podCpuCores ?? 0.5) * unit.vpaCpuFactor * factor;
        const mem = (unit.spec.podMemoryGib ?? 1) * Math.sqrt(unit.vpaCpuFactor * factor);
        const dims = capsuleDims(cpu, mem);
        const nodeId = unit.spec.anchorNodeId ?? `pod/${unit.spec.workloadName}`;
        this.notifyVpaRecommendation(unit.spec.clusterId, unit.spec.workloadName, nodeId, dims.height, dims.radius);
      }
    } else if (unit.vpaPendingCommitAt === null) {
      unit.vpaCpuHighSince = null;
    }
  }

  // -- Introspection -------------------------------------------------------------

  public getState(workloadId: string): WorkloadScalingState | null {
    const unit = this.units.get(workloadId);
    if (!unit) return null;
    return this.snapshot(unit);
  }

  public getAllStates(): WorkloadScalingState[] {
    return [...this.units.values()].map((u) => this.snapshot(u));
  }

  /** Current effective λ (rps) for a unit — HUD RPS readout. */
  public getCurrentRps(workloadId: string): number {
    return this.units.get(workloadId)?.currentLambda ?? 0;
  }

  /** Current queue length Q(t) at the ingress buffer. */
  public getQueueLength(workloadId: string): number {
    return Math.round(this.units.get(workloadId)?.queueLength ?? 0);
  }

  public listWorkloadIds(): string[] {
    return [...this.units.keys()];
  }

  private snapshot(unit: UnitRuntime): WorkloadScalingState {
    let nextReady = Infinity;
    for (const p of unit.pending) nextReady = Math.min(nextReady, p.readyAt);
    return {
      clusterId: unit.spec.clusterId,
      workloadName: unit.spec.workloadName,
      currentReplicas: unit.currentReplicas,
      desiredReplicas: Math.max(unit.desiredReplicas, unit.currentReplicas + unit.pending.length),
      pendingReplicas: unit.pending.length,
      currentCpuUtilization: Math.round(unit.cpuUtilization * 10) / 10,
      targetCpuUtilization: unit.spec.targetCpuUtilization ?? 60,
      latencyMs: Math.round(unit.latencyMs),
      errorRate: Math.round(unit.errorRate * 1000) / 1000,
      computeClassType: unit.spec.computeClassType,
      provisioningTimeRemainingMs:
        nextReady === Infinity ? 0 : Math.max(0, Math.round((nextReady - this.simTime) * 1000)),
    };
  }

  // -- Callback + viewport dispatch -------------------------------------------------

  private emitState(): void {
    if (!this.callbacks.onStateUpdate) return;
    this.callbacks.onStateUpdate(this.getAllStates(), this.simTime);
  }

  private matchingViewports(clusterId: string): Array<{ clusterId: string; viewport: ClusterViewport }> {
    return this.viewports.filter((entry) => entry.clusterId === '*' || entry.clusterId === clusterId);
  }

  private notifyHpaScaleOut(clusterId: string, workloadName: string, event: HpaScaleOutEvent): void {
    this.callbacks.onHpaScaleOut?.(clusterId, workloadName, event);
    for (const entry of this.matchingViewports(clusterId)) {
      entry.viewport.applyHpaScaleOut(event);
    }
  }

  private notifyVpaRecommendation(
    clusterId: string,
    workloadName: string,
    nodeId: string,
    height: number,
    radius: number,
  ): void {
    this.callbacks.onVpaRecommendation?.(clusterId, workloadName, nodeId, height, radius);
    for (const entry of this.matchingViewports(clusterId)) {
      entry.viewport.applyVpaRecommendation(nodeId, {
        current_height: 0.6,
        current_radius: 0.3,
        target_height: height,
        target_radius: radius,
      });
    }
  }

  private notifyVpaResize(
    clusterId: string,
    workloadName: string,
    nodeId: string,
    height: number,
    radius: number,
    durationMs: number,
  ): void {
    this.callbacks.onVpaResize?.(clusterId, workloadName, nodeId, height, radius, durationMs);
    for (const entry of this.matchingViewports(clusterId)) {
      entry.viewport.applyVpaResize(nodeId, height, radius, durationMs);
    }
  }

  private notifyPodScheduled(clusterId: string, workloadName: string, podId: string): void {
    this.callbacks.onPodScheduled?.(clusterId, workloadName, podId);
  }

  /** Project a staged pending pod onto attached viewports (ghost + beam). */
  private notifyPendingStaged(event: PendingPodStagedEvent): void {
    this.callbacks.onPendingStaged?.(event);
    for (const entry of this.matchingViewports(event.clusterId)) {
      if (event.claimName) {
        const ghostX = clamp(event.position.x + 8, -10, 10);
        entry.viewport.applyKarpenterClaim({
          claim: {
            claim_name: event.claimName,
            nodepool: `${event.clusterId}-pool`,
            is_provisioned: false,
          },
          ghost_position: { x: ghostX, y: -2.5, z: event.position.z },
        });
        entry.viewport.applyKarpenterTractorBeam({
          node_id: event.podId,
          claim_name: event.claimName,
          beam: {
            top: [event.position.x, event.position.y, event.position.z],
            bottom: [ghostX, -2.5, event.position.z],
          },
        });
      }
    }
  }

  /**
   * Attach a Three.js viewport to the animation triggers. `clusterId === '*'`
   * receives every cluster's events (split-screen linked mode); otherwise
   * only matching clusterIds animate on this viewport. Returns a detach fn.
   */
  public attachViewport(viewport: ClusterViewport, clusterId = '*'): () => void {
    const record = { clusterId, viewport };
    this.viewports.push(record);
    return () => {
      const idx = this.viewports.indexOf(record);
      if (idx >= 0) this.viewports.splice(idx, 1);
    };
  }

  /** Re-project current pending/staging state onto attached viewports. */
  public syncViewportStaging(clusterId?: string): void {
    for (const unit of this.units.values()) {
      if (clusterId && unit.spec.clusterId !== clusterId) continue;
      for (const p of unit.pending) {
        this.notifyPendingStaged({
          clusterId: unit.spec.clusterId,
          workloadName: unit.spec.workloadName,
          podId: p.podId,
          position: stagingHoverPosition(p.stagedIndex),
          claimName: p.claimName,
          estimatedReadyMs: Math.max(0, Math.round((p.readyAt - this.simTime) * 1000)),
        });
      }
    }
  }
}
