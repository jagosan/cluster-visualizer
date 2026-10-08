/**
 * TASK-CV-1205: SPEC-11 Load-Driven Latency Spring Physics Engine.
 *
 * Implements the load-dependent dynamic floor separation model from
 * `specs/11-quad-layout-diff-tour-and-latency-springs.md` §3.3,
 * blueprint §2.5, and ADR-03 (logarithmic damped spring representation):
 *
 *   Baseline latency:        tau_base = 5.0 ms
 *   Max vertical displacement: delta_Y_max = 1.8 units
 *   Load scale coefficient:  C_load = 0.45
 *
 *   Target displacement:
 *     delta_Y_target = min(
 *       delta_Y_max,
 *       C_load * ln(1 + max(0, (tau - tau_base) / tau_base))
 *     )
 *
 *   Damped harmonic spring dynamics (semi-implicit Euler integration):
 *     zeta    = 0.85  (damping ratio — critically-damped feel)
 *     omega_n = 3.5   (natural frequency, rad/s)
 *     a = -2 * zeta * omega_n * v - omega_n^2 * (x - target)
 *     v += a * dt
 *     x += v * dt
 *
 * With zeta = 0.85 and omega_n = 3.5 the 2%-settling time is
 * approximately 4 / (zeta * omega_n) ≈ 1.35 s, matching the spec's
 * t_relax ≈ 1.2 s damped relaxation requirement: when load sheds and
 * latency returns to baseline, floors snap back to structural datum.
 *
 * ADR-03 guarantees: the logarithmic compression plus the strict
 * delta_Y_max clamp mean even a 1000 ms latency spike can never rip
 * building floors out of camera framing.
 *
 * This module is deliberately dependency-free (pure TypeScript math —
 * no THREE import) so it is unit-testable without a WebGL context and
 * can be driven by TrafficControlDeck simulations, SSE telemetry, or
 * LayerTrayManager itself (blueprint §4 decoupling principle).
 */

/** Tunable configuration overrides for the spring/latency model. */
export interface LatencySpringConfig {
  /** Baseline quiescent round-trip latency in ms (tau_base). Default 5.0. */
  tauBaseMs?: number;
  /** Maximum vertical displacement per floor in scene units. Default 1.8. */
  deltaYMax?: number;
  /** Logarithmic load repulsion scale coefficient. Default 0.45. */
  cLoad?: number;
  /** Damping ratio zeta. Default 0.85. */
  zeta?: number;
  /** Natural frequency omega_n in rad/s. Default 3.5. */
  omegaN?: number;
  /** Integration sub-step cap in seconds. Default 1/60. */
  maxStepDt?: number;
  /** Position epsilon for settling snap. Default 1e-4 units. */
  settleEpsilon?: number;
  /** Velocity epsilon for settling snap. Default 1e-3 units/s. */
  settleVelocityEpsilon?: number;
}

/** Thermal band classification for a latency sample (spec §3.3 color rules). */
export type ThermalBand = 'calm' | 'warm' | 'hot';

/** Full thermal FX profile derived from a latency sample. */
export interface ThermalProfile {
  band: ThermalBand;
  /** CSS hex color for conduit/edge materials. */
  color: string;
  /** Emissive intensity multiplier multiplier (1x calm / 2.5x hot per spec). */
  emissiveBoost: number;
  /** Particle drift speed multiplier (1x / 1.5x / 3x per blueprint §2.5). */
  particleSpeedMultiplier: number;
  /** Pulse/strobe frequency in Hz (12 Hz crimson strobe when hot). */
  strobeHz: number;
}

/** Snapshot of a single damped spring's state. */
export interface SpringState {
  /** Current displacement value (scene units). */
  current: number;
  /** Current velocity (scene units / s). */
  velocity: number;
  /** Current target displacement the spring is chasing (scene units). */
  target: number;
  /** Last latency sample that fed this spring (ms). */
  latencyMs: number;
  /** True when the spring has settled onto its target. */
  settled: boolean;
}

/**
 * Canonical SPEC-11 constants (§3.3 formula + blueprint §2.5 dynamics).
 * Frozen so call sites (thermal FX, traffic deck, tests) share one source.
 */
export const LATENCY_SPRING_CONSTANTS = Object.freeze({
  TAU_BASE_MS: 5.0,
  DELTA_Y_MAX: 1.8,
  C_LOAD: 0.45,
  ZETA: 0.85,
  OMEGA_N: 3.5,
  /** tau <= 15 ms -> calm cyan. */
  THERMAL_CALM_MS: 15,
  /** tau > 60 ms -> hot crimson. */
  THERMAL_HOT_MS: 60,
  COLOR_CALM: '#06b6d4',
  COLOR_WARM: '#f59e0b',
  COLOR_HOT: '#ef4444',
});

/**
 * Default nominal structural elevations Y0(k) for the canonical four-tier
 * tower stack (spec §3.3: Y ∈ [0.5, 2.5, 5.0, 7.0]). Extra tiers can be
 * registered at any elevation via `registerTier`.
 */
export const DEFAULT_TIER_ELEVATIONS: Readonly<Record<string, number>> =
  Object.freeze({
    worker: 0.5,
    subterranean: 0.5,
    framework: 2.5,
    services: 5.0,
    ingress: 7.0,
  });

/** Internal mutable spring record. */
interface SpringRecord {
  x: number;
  v: number;
  target: number;
  latencyMs: number;
  settled: boolean;
}

const sanitizeLatency = (latencyMs: number): number =>
  Number.isFinite(latencyMs) ? Math.max(0, latencyMs) : 0;

/**
 * Load-Driven Latency Spring Engine.
 *
 * Maintains per-tier and per-edge damped-spring state. Edge springs may be
 * bound to a tier via `setEdgeLatency(id, ms, tierId)` or
 * `bindEdgeToTier()`; a tier's target displacement is the clamped sum of
 * its direct latency contribution plus every bound edge contribution
 * (spec §3.3: `Y_floor(t) = Y0 + Σ delta_Y_ij(t)`, clamped per floor to
 * delta_Y_max by ADR-03).
 */
export class LatencySpringEngine {
  private readonly tauBaseMs: number;
  private readonly deltaYMax: number;
  private readonly cLoad: number;
  private readonly zeta: number;
  private readonly omegaN: number;
  private readonly maxStepDt: number;
  private readonly settleEpsilon: number;
  private readonly settleVelocityEpsilon: number;

  /** Per-tier spring state, keyed by tierId. */
  private readonly tiers = new Map<string, SpringRecord>();
  /** Per-edge spring state, keyed by edgeId. */
  private readonly edges = new Map<string, SpringRecord>();
  /** Edge -> tier binding for aggregate floor displacement. */
  private readonly tierOfEdge = new Map<string, string>();
  /** Nominal structural elevation Y0 per registered tier. */
  private readonly tierElevations = new Map<string, number>();

  constructor(config?: LatencySpringConfig) {
    this.tauBaseMs = config?.tauBaseMs ?? LATENCY_SPRING_CONSTANTS.TAU_BASE_MS;
    this.deltaYMax = config?.deltaYMax ?? LATENCY_SPRING_CONSTANTS.DELTA_Y_MAX;
    this.cLoad = config?.cLoad ?? LATENCY_SPRING_CONSTANTS.C_LOAD;
    this.zeta = config?.zeta ?? LATENCY_SPRING_CONSTANTS.ZETA;
    this.omegaN = config?.omegaN ?? LATENCY_SPRING_CONSTANTS.OMEGA_N;
    this.maxStepDt = config?.maxStepDt ?? 1 / 60;
    this.settleEpsilon = config?.settleEpsilon ?? 1e-4;
    this.settleVelocityEpsilon = config?.settleVelocityEpsilon ?? 1e-3;
  }

  // ─── Tier management ─────────────────────────────────────────────────────

  /**
   * Register (or re-elevate) a tier. Displacement state is created lazily;
   * re-registering preserves any in-flight spring state.
   */
  public registerTier(tierId: string, baseElevation?: number): void {
    const elevation =
      baseElevation ?? DEFAULT_TIER_ELEVATIONS[tierId] ?? 0;
    this.tierElevations.set(tierId, elevation);
    if (!this.tiers.has(tierId)) {
      this.tiers.set(tierId, {
        x: 0,
        v: 0,
        target: 0,
        latencyMs: 0,
        settled: true,
      });
    }
  }

  /** True when the tier is registered with the engine. */
  public hasTier(tierId: string): boolean {
    return this.tiers.has(tierId);
  }

  /** Nominal structural elevation Y0 of a tier (0 when unknown). */
  public getBaseElevation(tierId: string): number {
    return this.tierElevations.get(tierId) ?? 0;
  }

  /** Registered tier ids in registration order. */
  public getTierIds(): string[] {
    return [...this.tiers.keys()];
  }

  // ─── Latency inputs ──────────────────────────────────────────────────────

  /**
   * Feed an instantaneous latency sample for an entire architectural tier.
   * The spring target becomes delta_Y(tau) per the spec §3.3 formula.
   */
  public setTierLatency(tierId: string, latencyMs: number): void {
    this.ensureTier(tierId);
    const record = this.tiers.get(tierId);
    if (!record) return;
    const tau = sanitizeLatency(latencyMs);
    record.latencyMs = tau;
    record.settled = false;
    this.resolveTierTargets();
  }

  /**
   * Feed an instantaneous latency sample for a dependency edge (i, j).
   * Optionally binds the edge to a tier so its displacement contributes to
   * that tier's aggregate floor separation.
   */
  public setEdgeLatency(edgeId: string, latencyMs: number, tierId?: string): void {
    if (tierId !== undefined) {
      this.bindEdgeToTier(edgeId, tierId);
    }
    let record = this.edges.get(edgeId);
    if (!record) {
      record = { x: 0, v: 0, target: 0, latencyMs: 0, settled: true };
      this.edges.set(edgeId, record);
    }
    const tau = sanitizeLatency(latencyMs);
    record.latencyMs = tau;
    record.target = this.targetDisplacement(tau);
    record.settled = false;
    this.resolveTierTargets();
  }

  /** Bind an edge spring to a tier for aggregate floor displacement. */
  public bindEdgeToTier(edgeId: string, tierId: string): void {
    this.ensureTier(tierId);
    this.tierOfEdge.set(edgeId, tierId);
    if (!this.edges.has(edgeId)) {
      this.edges.set(edgeId, {
        x: 0,
        v: 0,
        target: 0,
        latencyMs: 0,
        settled: true,
      });
    }
    this.resolveTierTargets();
  }

  /** Remove an edge spring and its tier binding. */
  public removeEdge(edgeId: string): void {
    this.edges.delete(edgeId);
    this.tierOfEdge.delete(edgeId);
    this.resolveTierTargets();
  }

  // ─── Simulation ──────────────────────────────────────────────────────────

  /**
   * Advance all tier and edge springs towards their targets by `dt` seconds.
   * Large frames are sub-stepped at `maxStepDt` so the semi-implicit Euler
   * integrator stays stable (omega_n = 3.5 rad/s).
   */
  public update(dt: number): void {
    if (!Number.isFinite(dt) || dt <= 0) return;
    this.resolveTierTargets();

    let remaining = dt;
    while (remaining > 0) {
      const h = Math.min(remaining, this.maxStepDt);
      for (const record of this.edges.values()) this.stepSpring(record, h);
      for (const record of this.tiers.values()) this.stepSpring(record, h);
      remaining -= h;
    }
  }

  /**
   * Settles all springs back to 0 displacement immediately (structural
   * datum) and drops all latency samples and edge bindings. For a smooth
   * animated relaxation, instead feed baseline latency (<= tau_base) and
   * keep calling update(dt) — the damped spring itself provides the
   * ≈1.2 s relaxation.
   */
  public reset(): void {
    this.edges.clear();
    this.tierOfEdge.clear();
    for (const record of this.tiers.values()) {
      record.x = 0;
      record.v = 0;
      record.target = 0;
      record.latencyMs = 0;
      record.settled = true;
    }
  }

  // ─── Displacement outputs ────────────────────────────────────────────────

  /**
   * Current vertical displacement delta_Y of a tier (0 when unknown).
   * Slightly negative transient values are possible mid-oscillation as a
   * spring snaps back through its datum.
   */
  public getDisplacement(tierId: string): number {
    return this.tiers.get(tierId)?.x ?? 0;
  }

  /** Structural datum elevation plus current spring displacement. */
  public getDisplacedElevation(tierId: string, baseElevation: number): number {
    return baseElevation + this.getDisplacement(tierId);
  }

  /** Current displacement of an individual edge spring (0 when unknown). */
  public getEdgeDisplacement(edgeId: string): number {
    return this.edges.get(edgeId)?.x ?? 0;
  }

  /** Read-only snapshot of a tier's spring state. */
  public getTierState(tierId: string): SpringState | null {
    const record = this.tiers.get(tierId);
    return record ? this.toSpringState(record) : null;
  }

  /** Read-only snapshot of an edge's spring state. */
  public getEdgeState(edgeId: string): SpringState | null {
    const record = this.edges.get(edgeId);
    return record ? this.toSpringState(record) : null;
  }

  /** True when every spring has settled onto its target. */
  public isSettled(): boolean {
    for (const record of this.edges.values()) if (!record.settled) return false;
    for (const record of this.tiers.values()) if (!record.settled) return false;
    return true;
  }

  // ─── Thermal FX helpers (spec §3.3 color rules, blueprint §2.5) ─────────

  /**
   * Thermal color for a latency sample:
   *  - tau <= 15 ms   -> calm cyan  '#06b6d4'
   *  - tau <= 60 ms   -> amber      '#f59e0b'
   *  - tau >  60 ms   -> crimson    '#ef4444'
   */
  public getThermalColor(latencyMs: number): string {
    return LatencySpringEngine.computeThermalProfile(latencyMs).color;
  }

  /** Thermal band classification for a latency sample. */
  public getThermalBand(latencyMs: number): ThermalBand {
    return LatencySpringEngine.computeThermalProfile(latencyMs).band;
  }

  /**
   * Full thermal FX profile (color, emissive boost, particle speed,
   * strobe rate) — consumed by TASK-CV-1206 edge conduit FX.
   */
  public getThermalProfile(latencyMs: number): ThermalProfile {
    return LatencySpringEngine.computeThermalProfile(latencyMs);
  }

  /** Static form of the thermal profile for call sites without an engine. */
  public static computeThermalProfile(latencyMs: number): ThermalProfile {
    const tau = sanitizeLatency(latencyMs);
    if (tau <= LATENCY_SPRING_CONSTANTS.THERMAL_CALM_MS) {
      return {
        band: 'calm',
        color: LATENCY_SPRING_CONSTANTS.COLOR_CALM,
        emissiveBoost: 1.0,
        particleSpeedMultiplier: 1.0,
        strobeHz: 0,
      };
    }
    if (tau <= LATENCY_SPRING_CONSTANTS.THERMAL_HOT_MS) {
      return {
        band: 'warm',
        color: LATENCY_SPRING_CONSTANTS.COLOR_WARM,
        emissiveBoost: 1.5,
        particleSpeedMultiplier: 1.5,
        strobeHz: 0,
      };
    }
    return {
      band: 'hot',
      color: LATENCY_SPRING_CONSTANTS.COLOR_HOT,
      emissiveBoost: 2.5,
      particleSpeedMultiplier: 3.0,
      strobeHz: 12,
    };
  }

  // ─── Internals ───────────────────────────────────────────────────────────

  private ensureTier(tierId: string): void {
    if (!this.tiers.has(tierId)) this.registerTier(tierId);
  }

  /**
   * Spec §3.3 / ADR-03 target:
   *   delta_Y_target = min(delta_Y_max,
   *     C_load * ln(1 + max(0, (tau - tau_base) / tau_base)))
   */
  private targetDisplacement(latencyMs: number): number {
    const tau = sanitizeLatency(latencyMs);
    const strain = Math.max(0, (tau - this.tauBaseMs) / this.tauBaseMs);
    return Math.min(this.deltaYMax, this.cLoad * Math.log(1 + strain));
  }

  /**
   * Tier target = clamp(delta_Y_max, direct tier latency target +
   * Σ bound edge edge targets) — the discrete form of
   * Y_floor(t) = Y0 + Σ delta_Y_ij(t) with the per-floor ADR-03 clamp.
   */
  private resolveTierTargets(): void {
    const edgeSumByTier = new Map<string, number>();
    for (const [edgeId, record] of this.edges.entries()) {
      const tierId = this.tierOfEdge.get(edgeId);
      if (tierId === undefined) continue;
      edgeSumByTier.set(tierId, (edgeSumByTier.get(tierId) ?? 0) + record.target);
    }
    for (const [tierId, record] of this.tiers.entries()) {
      const direct = this.targetDisplacement(record.latencyMs);
      const aggregate = direct + (edgeSumByTier.get(tierId) ?? 0);
      const clamped = Math.min(this.deltaYMax, aggregate);
      if (record.target !== clamped) {
        record.target = clamped;
        record.settled = false;
      }
    }
  }

  /**
   * Semi-implicit (symplectic) Euler step of the damped harmonic oscillator:
   *   a = -2 zeta omega_n v - omega_n^2 (x - target)
   */
  private stepSpring(record: SpringRecord, dt: number): void {
    if (record.settled) return;
    const acceleration =
      -2 * this.zeta * this.omegaN * record.v -
      this.omegaN * this.omegaN * (record.x - record.target);
    record.v += acceleration * dt;
    record.x += record.v * dt;

    if (
      Math.abs(record.x - record.target) < this.settleEpsilon &&
      Math.abs(record.v) < this.settleVelocityEpsilon
    ) {
      record.x = record.target;
      record.v = 0;
      record.settled = true;
    }
  }

  private toSpringState(record: SpringRecord): SpringState {
    return {
      current: record.x,
      velocity: record.v,
      target: record.target,
      latencyMs: record.latencyMs,
      settled: record.settled,
    };
  }
}
