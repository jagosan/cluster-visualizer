import * as THREE from 'three';
import type { RemoteServiceResourceData } from './subterranean_vaults.js';
import { LatencySpringEngine } from './latency_spring_engine.js';

/**
 * TASK-CV-904 / SPEC-08 §6: Vertical subterranean plunge conduits.
 *
 * Bezier pipelines routing from worker-deck pods, through the kro hydraulic
 * manifold hub (Y = -4.8), down into the managed cloud service vaults on
 * Sub-Level B2/B3, with a live latency spectrum driving particle colour and
 * velocity, plus procedural degradation states (Degraded arcing / Failed
 * fractured pipe + red hazard strobe cone illuminating the endpoint vault).
 */

export type PlungeReachability = 'healthy' | 'degraded' | 'failed';

export interface PlungeConduitSpec {
  id: string;
  /** Worker deck pod (or any upper-deck component) the conduit starts at. */
  source: THREE.Vector3;
  /** Managed vault world position the plunge terminates in. */
  target: THREE.Vector3;
  /** Measured network RTT in milliseconds. */
  latencyMs: number;
  reachability: PlungeReachability;
  /** Vault resource id this plunge feeds (for blast-radius coordination). */
  vaultId?: string;
}

interface LatencyProfile {
  color: number;
  velocity: number; // curve-units per second along the conduit
}

// SPEC-08 §6.1 latency spectrum anchors.
export const LATENCY_CYAN_MS = 3;
export const LATENCY_AMBER_MS = 20;
export const LATENCY_MAGENTA_MS = 60;

const CYAN: LatencyProfile = { color: 0x00f0ff, velocity: 4.0 }; // electric cyan, high velocity
const AMBER: LatencyProfile = { color: 0xf59e0b, velocity: 2.0 }; // warm amber, medium velocity
const MAGENTA: LatencyProfile = { color: 0xec4899, velocity: 0.5 }; // sluggish magenta

const tmpColorA = new THREE.Color();
const tmpColorB = new THREE.Color();

/** Map RTT (ms) to the SPEC-08 latency spectrum colour + flow velocity. */
export function latencyProfile(latencyMs: number): LatencyProfile {
  if (latencyMs < LATENCY_CYAN_MS) return CYAN;
  if (latencyMs <= LATENCY_AMBER_MS) return AMBER;
  if (latencyMs >= LATENCY_MAGENTA_MS) return MAGENTA;
  // 20–60ms gap between the spec's amber and magenta bands: interpolate.
  const t = (latencyMs - LATENCY_AMBER_MS) / (LATENCY_MAGENTA_MS - LATENCY_AMBER_MS);
  tmpColorA.setHex(AMBER.color);
  tmpColorB.setHex(MAGENTA.color);
  const blended = tmpColorA.lerp(tmpColorB, t).getHex();
  return { color: blended, velocity: THREE.MathUtils.lerp(AMBER.velocity, MAGENTA.velocity, t) };
}

/** Derive reachability from a vault's status_phase string. */
export function reachabilityFromPhase(phase: string): PlungeReachability {
  const p = phase.toLowerCase();
  if (p.includes('fail') || p.includes('unreachable') || p.includes('timeout') || p.includes('refused')) {
    return 'failed';
  }
  if (p.includes('degrad') || p.includes('jitter') || p.includes('loss')) return 'degraded';
  return 'healthy';
}

/**
 * Heuristic RTT for a managed vault when the snapshot carries no explicit
 * latency telemetry: cross-cloud providers land in the magenta tier,
 * messaging raceways run sub-millisecond, everything else sits cross-zone.
 */
export function estimateVaultLatencyMs(resource: RemoteServiceResourceData): number {
  switch (resource.category) {
    case 'messaging_eventing':
      return 1.4;
    case 'cache_in_memory':
      return 0.8;
    case 'networking_gateway':
      return 68;
    default:
      return resource.provider === 'gcp' ? 6.5 : 75;
  }
}

const PLUNGE_PIPE_RADIUS = 0.07;
const PARTICLES_PER_CONDUIT = 6;

/** SPEC-11 §2.5: quiescent core emissive intensity before thermal boost. */
const THERMAL_BASE_EMISSIVE = 0.6;
/** Exponential rate (1/s) for cyan → amber → crimson colour/speed lerping. */
const THERMAL_LERP_RATE = 6.0;

interface PlungeParticle {
  mesh: THREE.Mesh;
  progress: number; // [0, 1) along the curve
}

interface Spark {
  points: THREE.Points;
  basePositions: Float32Array;
  phase: number;
}

interface PlungeConduitRecord {
  spec: PlungeConduitSpec;
  curve: THREE.Curve<THREE.Vector3>;
  pipes: THREE.Object3D[];
  pipeMaterial: THREE.MeshStandardMaterial | null; // null on fractured conduits
  coreMaterial: THREE.MeshStandardMaterial | null;
  /** Shared material for this conduit's flow particles (null when failed). */
  particleMaterial: THREE.MeshStandardMaterial | null;
  particles: PlungeParticle[];
  sparks: Spark | null;
  hazardCone: THREE.Mesh | null;
  velocity: number;
  baseEmissive: number;
  highlighted: boolean;

  // ─── TASK-CV-1206: SPEC-11 §3.3 / blueprint §2.5 thermal FX state ──────
  /** Latency sample (ms) currently driving the thermal FX. */
  thermalMs: number;
  /** True once a latency/spring hook has claimed this conduit's FX. */
  thermalActive: boolean;
  /** Smoothed core/particle colour (lerps toward thermalTargetColor). */
  thermalColor: THREE.Color;
  /** Target colour from the latest ThermalProfile band. */
  thermalTargetColor: THREE.Color;
  /** Smoothed emissive multiplier (1x calm / 1.5x warm / 2.5x hot). */
  thermalEmissive: number;
  thermalEmissiveTarget: number;
  /** Smoothed / target flow velocity under thermal modulation. */
  thermalVelocity: number;
  thermalVelocityTarget: number;
  /** Particle/core pulse frequency in Hz (12 Hz crimson strobe when hot). */
  strobeHz: number;
  /** Build-time SPEC-08 flow velocity (thermal multiplier baseline). */
  baseVelocity: number;
}

/**
 * Vertical plunge Bezier: steep drop from the pod deck, hydraulic sweep
 * through the manifold plane, then a second plunge into the vault.
 */
export function buildPlungeCurve(
  source: THREE.Vector3,
  target: THREE.Vector3,
  manifoldY: number,
): THREE.Curve<THREE.Vector3> {
  const p0 = source.clone();
  const p3 = target.clone();

  // Clamp the manifold plane between the two endpoints so a plunge that
  // doesn't straddle it still forms a readable S.
  const lo = Math.min(source.y, target.y);
  const hi = Math.max(source.y, target.y);
  const midY = THREE.MathUtils.clamp(manifoldY, lo + 0.4 * (hi - lo) - 0.4, hi - 0.25);

  const drop1 = new THREE.Vector3(source.x, midY, source.z);
  const swing = new THREE.Vector3(
    THREE.MathUtils.lerp(source.x, target.x, 0.5),
    midY,
    THREE.MathUtils.lerp(source.z, target.z, 0.5),
  );
  const approach = new THREE.Vector3(target.x, midY, target.z);

  const path = new THREE.CurvePath<THREE.Vector3>();

  const seg1 = new THREE.CubicBezierCurve3(
    p0,
    new THREE.Vector3(p0.x, p0.y - (p0.y - midY) * 0.55, p0.z),
    new THREE.Vector3(p0.x, midY, p0.z),
    drop1,
  );
  const seg2 = new THREE.CubicBezierCurve3(drop1, swing, swing.clone(), approach);
  const seg3 = new THREE.CubicBezierCurve3(
    approach,
    new THREE.Vector3(approach.x, approach.y - (midY - p3.y) * 0.45, approach.z),
    new THREE.Vector3(p3.x, p3.y + (midY - p3.y) * 0.45, p3.z),
    p3,
  );

  path.add(seg1);
  path.add(seg2);
  path.add(seg3);
  return path;
}

function makeParticleMaterial(color: number): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color,
    emissive: color,
    emissiveIntensity: 2.0,
    roughness: 0.1,
    metalness: 0.0,
    transparent: true,
    opacity: 0.95,
  });
}

export class PlungeConduitManager {
  private readonly scene: THREE.Scene;
  private readonly group: THREE.Group;
  private conduits: Map<string, PlungeConduitRecord> = new Map();
  private particleGeometry = new THREE.SphereGeometry(0.055, 10, 10);

  constructor(scene: THREE.Scene) {
    this.scene = scene;
    this.group = new THREE.Group();
    this.group.name = 'PlungeConduitGroup';
    this.scene.add(this.group);
  }

  /** Rebuild all plunge conduits from specs (idempotent per id). */
  public generate(specs: PlungeConduitSpec[]): void {
    const keep = new Set(specs.map((s) => specKey(s)));
    for (const id of Array.from(this.conduits.keys())) {
      if (!keep.has(id)) this.removeConduit(id);
    }

    for (const spec of specs) {
      const id = specKey(spec);
      if (this.conduits.has(id)) this.removeConduit(id);
      this.buildConduit(id, spec);
    }
  }

  private buildConduit(id: string, spec: PlungeConduitSpec): void {
    const curve = buildPlungeCurve(spec.source, spec.target, -4.8);
    const profile = latencyProfile(spec.latencyMs);
    // TASK-CV-1206: SPEC-11 §3.3 thermal band (≤15 calm / ≤60 warm / >60 hot)
    // takes over colour + pulse whenever latency telemetry is being driven.
    const thermal = LatencySpringEngine.computeThermalProfile(spec.latencyMs);
    const thermalHex = parseInt(thermal.color.slice(1), 16);
    const record: PlungeConduitRecord = {
      spec,
      curve,
      pipes: [],
      pipeMaterial: null,
      coreMaterial: null,
      particleMaterial: null,
      particles: [],
      sparks: null,
      hazardCone: null,
      velocity: profile.velocity,
      baseEmissive: THERMAL_BASE_EMISSIVE,
      highlighted: false,
      thermalMs: spec.latencyMs,
      thermalActive: false,
      thermalColor: new THREE.Color(thermalHex),
      thermalTargetColor: new THREE.Color(thermalHex),
      thermalEmissive: thermal.emissiveBoost,
      thermalEmissiveTarget: thermal.emissiveBoost,
      thermalVelocity: profile.velocity * thermal.particleSpeedMultiplier,
      thermalVelocityTarget: profile.velocity * thermal.particleSpeedMultiplier,
      strobeHz: thermal.strobeHz,
      baseVelocity: profile.velocity,
    };

    if (spec.reachability === 'failed') {
      this.buildFractured(record, profile.color);
    } else {
      this.buildHealthyPipe(record, profile);
      if (spec.reachability === 'degraded') this.buildSparks(record);
    }

    this.group.add(...record.pipes);
    this.conduits.set(id, record);
  }

  private buildHealthyPipe(record: PlungeConduitRecord, profile: LatencyProfile): void {
    const pipeMaterial = new THREE.MeshStandardMaterial({
      color: 0x9fb8c8,
      roughness: 0.15,
      metalness: 0.6,
      transparent: true,
      opacity: 0.35,
    });
    const coreMaterial = new THREE.MeshStandardMaterial({
      color: profile.color,
      emissive: profile.color,
      emissiveIntensity: record.baseEmissive,
      roughness: 0.2,
      metalness: 0.0,
      transparent: true,
      opacity: 0.55,
    });
    record.pipeMaterial = pipeMaterial;
    record.coreMaterial = coreMaterial;

    const outer = new THREE.Mesh(
      new THREE.TubeGeometry(record.curve, 64, PLUNGE_PIPE_RADIUS, 10, false),
      pipeMaterial,
    );
    const core = new THREE.Mesh(
      new THREE.TubeGeometry(record.curve, 64, PLUNGE_PIPE_RADIUS * 0.45, 8, false),
      coreMaterial,
    );
    outer.name = `plunge-${record.spec.id}`;
    record.pipes.push(outer, core);

    // Flowing latency particles along the conduit (shared material so a
    // thermal retint touches one material, not six).
    const particleMat = makeParticleMaterial(profile.color);
    record.particleMaterial = particleMat;
    for (let i = 0; i < PARTICLES_PER_CONDUIT; i++) {
      const mesh = new THREE.Mesh(this.particleGeometry, particleMat);
      record.particles.push({ mesh, progress: i / PARTICLES_PER_CONDUIT });
      record.pipes.push(mesh);
    }
  }

  private buildFractured(record: PlungeConduitRecord, coreColor: number): void {
    // Fractured translucent pipe: split the tube into segments with gaps,
    // zero particle flow (SPEC-08 §6.2 Unreachable).
    const fractures = [0.22, 0.48, 0.74];
    const gap = 0.04;
    const bounds: number[] = [0];
    for (const f of fractures) {
      bounds.push(Math.max(0, f - gap), Math.min(1, f + gap));
    }
    bounds.push(1);

    const glassMaterial = new THREE.MeshStandardMaterial({
      color: 0x67e8f9,
      roughness: 0.05,
      metalness: 0.3,
      transparent: true,
      opacity: 0.12,
      depthWrite: false,
    });

    for (let i = 0; i < bounds.length - 1; i++) {
      const t0 = bounds[i]!;
      const t1 = bounds[i + 1]!;
      if (t1 - t0 < 0.06) continue;
      const sub = subCurve(record.curve, t0, t1);
      const seg = new THREE.Mesh(
        new THREE.TubeGeometry(sub, 24, PLUNGE_PIPE_RADIUS * (0.8 + 0.3 * Math.random()), 8, false),
        glassMaterial,
      );
      seg.name = `plunge-fractured-${record.spec.id}`;
      record.pipes.push(seg);
    }
    record.pipeMaterial = glassMaterial;

    // Jagged shard shards at the fracture points.
    const shardMat = new THREE.MeshStandardMaterial({
      color: coreColor,
      emissive: 0xef4444,
      emissiveIntensity: 0.7,
      transparent: true,
      opacity: 0.6,
    });
    for (const t of fractures) {
      const p = record.curve.getPointAt(THREE.MathUtils.clamp(t, 0, 1));
      const shard = new THREE.Mesh(new THREE.TetrahedronGeometry(0.09, 0), shardMat);
      shard.position.copy(p);
      record.pipes.push(shard);
    }

    // Pulsing red hazard strobe cone illuminating the endpoint vault.
    const coneMat = new THREE.MeshBasicMaterial({
      color: 0xef4444,
      transparent: true,
      opacity: 0.35,
      side: THREE.DoubleSide,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const cone = new THREE.Mesh(new THREE.ConeGeometry(0.85, 2.4, 20, 1, true), coneMat);
    cone.position.set(record.spec.target.x, record.spec.target.y + 1.4, record.spec.target.z);
    cone.name = `plunge-hazard-${record.spec.id}`;
    record.hazardCone = cone;
    record.pipes.push(cone);
  }

  private buildSparks(record: PlungeConduitRecord): void {
    // Procedural electrical arcs / sparks leaking from coupling joints.
    const jointTs = [0.25, 0.5, 0.75];
    const perJoint = 10;
    const positions = new Float32Array(jointTs.length * perJoint * 3);
    let idx = 0;
    for (const t of jointTs) {
      const joint = record.curve.getPointAt(THREE.MathUtils.clamp(t, 0, 1));
      for (let i = 0; i < perJoint; i++) {
        positions[idx++] = joint.x + (Math.random() - 0.5) * 0.18;
        positions[idx++] = joint.y + (Math.random() - 0.5) * 0.18;
        positions[idx++] = joint.z + (Math.random() - 0.5) * 0.18;
      }
    }
    const basePositions = positions.slice();
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const material = new THREE.PointsMaterial({
      color: 0xffe08a,
      size: 0.07,
      transparent: true,
      opacity: 0.9,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const points = new THREE.Points(geometry, material);
    record.sparks = { points, basePositions, phase: Math.random() * 10 };
    record.pipes.push(points);

    // Coupling collars at the arcing joints.
    const collarMat = new THREE.MeshStandardMaterial({
      color: 0x78716c,
      metalness: 0.9,
      roughness: 0.35,
      transparent: true,
      opacity: 0.9,
    });
    for (const t of jointTs) {
      const p = record.curve.getPointAt(THREE.MathUtils.clamp(t, 0, 1));
      const tangent = record.curve.getTangentAt(THREE.MathUtils.clamp(t, 0, 1));
      const collar = new THREE.Mesh(new THREE.TorusGeometry(PLUNGE_PIPE_RADIUS + 0.03, 0.03, 8, 16), collarMat);
      collar.position.copy(p);
      collar.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), tangent);
      record.pipes.push(collar);
    }
  }

  /** Spotlight the conduits feeding the listed vault ids; dim the rest. */
  public applyBlastHighlight(vaultIds: Set<string> | null): void {
    for (const record of this.conduits.values()) {
      const dimmed = vaultIds !== null && !(record.spec.vaultId && vaultIds.has(record.spec.vaultId));
      record.highlighted = !dimmed && vaultIds !== null;
      if (record.pipeMaterial) {
        record.pipeMaterial.opacity = dimmed ? 0.06 : record.spec.reachability === 'failed' ? 0.12 : 0.35;
      }
      if (record.coreMaterial) {
        record.coreMaterial.opacity = dimmed ? 0.04 : 0.55;
      }
      for (const p of record.particles) {
        (p.mesh.material as THREE.Material).opacity = dimmed ? 0.04 : 0.95;
      }
      if (record.sparks) {
        (record.sparks.points.material as THREE.Material).opacity = dimmed ? 0.05 : 0.9;
      }
      if (record.hazardCone) {
        (record.hazardCone.material as THREE.Material).opacity = dimmed ? 0.05 : 0.35;
      }
    }
  }

  public update(delta: number, time: number): void {
    const lerpFactor = Math.min(1.0, THERMAL_LERP_RATE * delta);
    for (const record of this.conduits.values()) {
      const length = record.curve.getLength();

      // Thermal FX lerp (cyan → amber → crimson colour/speed)
      if (record.thermalActive) {
        record.thermalColor.lerp(record.thermalTargetColor, lerpFactor);
        record.thermalEmissive += (record.thermalEmissiveTarget - record.thermalEmissive) * lerpFactor;
        record.thermalVelocity += (record.thermalVelocityTarget - record.thermalVelocity) * lerpFactor;
      }

      // Flow particles (healthy + degraded only).
      if (record.spec.reachability !== 'failed') {
        const speed = record.velocity / Math.max(length, 0.001);
        for (const p of record.particles) {
          p.progress = (p.progress + speed * delta) % 1;
          const pos = record.curve.getPointAt(p.progress);
          p.mesh.position.copy(pos);
          const flicker = 0.75 + 0.25 * Math.sin(time * 12 + p.progress * 40);
          p.mesh.scale.setScalar(record.highlighted ? 1.5 : flicker);
        }
      }

      // Core emissive breathing.
      if (record.coreMaterial) {
        const wave = 0.5 + 0.5 * Math.sin(time * (2 + record.velocity) + record.spec.target.x);
        record.coreMaterial.emissiveIntensity =
          record.baseEmissive * (record.highlighted ? 2.4 : 1.0) * (0.6 + 0.6 * wave);
      }

      // Degraded: conduit body jitters and sparks crackle at the couplings.
      if (record.spec.reachability === 'degraded' && record.sparks) {
        const jitter = 0.012;
        record.sparks.points.position.set(
          Math.sin(time * 47 + record.sparks.phase) * jitter,
          Math.cos(time * 53 + record.sparks.phase) * jitter,
          Math.sin(time * 61 + record.sparks.phase) * jitter,
        );
        const sparkMat = record.sparks.points.material as THREE.PointsMaterial;
        sparkMat.opacity = Math.random() < 0.15 ? 0.15 : 0.9;
        sparkMat.size = 0.05 + Math.random() * 0.05;
      }

      // Failed: pulsing red hazard strobe cone over the endpoint vault.
      if (record.hazardCone) {
        const strobe = 0.5 + 0.5 * Math.sin(time * 6.0);
        const mat = record.hazardCone.material as THREE.MeshBasicMaterial;
        mat.opacity = record.highlighted ? 0.15 + 0.45 * strobe : 0.08 + 0.28 * strobe;
        record.hazardCone.scale.setScalar(0.92 + 0.12 * strobe);
      }
    }
  }

  private removeConduit(id: string): void {
    const record = this.conduits.get(id);
    if (!record) return;
    for (const obj of record.pipes) this.group.remove(obj);
    for (const obj of record.pipes) {
      if (obj instanceof THREE.Points) {
        obj.geometry.dispose();
        (obj.material as THREE.Material).dispose();
      } else if (obj instanceof THREE.Mesh) {
        if (obj.geometry !== this.particleGeometry) obj.geometry.dispose();
      }
    }
    record.pipeMaterial?.dispose();
    record.coreMaterial?.dispose();
    this.conduits.delete(id);
  }

  public clear(): void {
    for (const id of Array.from(this.conduits.keys())) this.removeConduit(id);
  }

  public dispose(): void {
    this.clear();
    this.particleGeometry.dispose();
    this.scene.remove(this.group);
    this.group.clear();
  }

  /** Set the latency for a specific conduit and activate its thermal state. */
  public setConduitLatency(id: string, latencyMs: number): void {
    const record = this.conduits.get(id);
    if (!record) return;
    record.thermalMs = latencyMs;
    record.thermalActive = true;
    const thermal = LatencySpringEngine.computeThermalProfile(latencyMs);
    record.thermalTargetColor.setStyle(thermal.color);
    record.thermalEmissiveTarget = thermal.emissiveBoost;
    record.thermalVelocityTarget = record.baseVelocity * thermal.particleSpeedMultiplier;
    record.strobeHz = thermal.strobeHz;
  }

  /** Reset all conduit latencies to their baseline values. */
  public resetConduitLatencies(): void {
    for (const record of this.conduits.values()) {
      if (record.thermalActive) continue;
      const thermal = LatencySpringEngine.computeThermalProfile(record.spec.latencyMs);
      record.thermalTargetColor.setStyle(thermal.color);
      record.thermalEmissiveTarget = thermal.emissiveBoost;
      record.thermalVelocityTarget = record.baseVelocity * thermal.particleSpeedMultiplier;
      record.strobeHz = thermal.strobeHz;
    }
  }
}

function specKey(spec: PlungeConduitSpec): string {
  return spec.id;
}

/** Sample a sub-curve of an arbitrary curve between t0..t1 as a CatmullRom. */
function subCurve(curve: THREE.Curve<THREE.Vector3>, t0: number, t1: number): THREE.Curve<THREE.Vector3> {
  const points: THREE.Vector3[] = [];
  const steps = 12;
  for (let i = 0; i <= steps; i++) {
    const t = THREE.MathUtils.lerp(t0, t1, i / steps);
    points.push(curve.getPointAt(THREE.MathUtils.clamp(t, 0, 1)));
  }
  return new THREE.CatmullRomCurve3(points, false, 'catmullrom', 0.3);
}
