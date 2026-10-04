/**
 * SPEC-09 / TASK-CV-1002: VPA Morphing & HPA Lateral Spawning effects.
 *
 * Owns the three autoscaling animation pipelines on the worker deck:
 *
 *  1. VPA recommendation ghost hull (SPEC-09 §3.2.1): a holographic golden
 *     wireframe capsule projecting the future target dimensions around any
 *     pod whose VPA recommendation differs from its current request.
 *  2. VPA in-place morph (SPEC-09 §3.2.2): a ~1200ms animated geometry
 *     tween (per-frame capsule rebuild with lerped height/radius) plus
 *     energy-emission ripples rippling from the capsule base to its crown.
 *  3. HPA lateral dynamics (SPEC-09 §3.3): a golden dispatch pulse fired
 *     from the Supervisor Floor (Y = +4.5) down the central riser pipe,
 *     followed by lateral conveyor slides of new replicas from the node
 *     deck intake port into their designated lateral slots.
 *
 * Also maintains the Autoscaling Radar aura rings (SPEC-09 §7.2) toggled
 * via KeyU — pulsating golden rings under every VPA/HPA-managed pod.
 *
 * All constants mirror src/ingestion/layout.py (single source of truth on
 * the Python side; events carry explicit coordinates so drift is visible).
 */

import * as THREE from 'three';

// ---------------------------------------------------------------------------
// Shared types & constants (mirror of src/ingestion/layout.py)
// ---------------------------------------------------------------------------

export interface AutoscalingStatusData {
  has_vpa?: boolean;
  vpa_target_cpu?: string | null;
  vpa_target_memory?: string | null;
  is_resizing_in_place?: boolean;
  has_hpa?: boolean;
  current_replicas?: number;
  desired_replicas?: number;
  target_metric?: string | null;
}

export interface MorphDimensions {
  current_height: number;
  current_radius: number;
  target_height: number;
  target_radius: number;
}

export interface HpaScaleOutEvent {
  node_id: string;
  delta: number;
  current_replicas?: number;
  desired_replicas?: number;
  target_metric?: string | null;
  dispatch_from?: { x: number; y: number; z: number };
  riser_bottom?: { x: number; y: number; z: number };
  lateral_path?: { intake?: number[]; slot?: number[] };
  timestamp?: string;
}

export interface VpaRecommendationEvent {
  node_id: string;
  dimensions?: MorphDimensions | null;
  target_cpu?: string | null;
  target_memory?: string | null;
  timestamp?: string;
}

export interface VpaResizeCommittedEvent {
  node_id: string;
  geometry?: { height?: number; radius?: number } | null;
  duration_ms?: number;
  timestamp?: string;
}

export const SUPERVISOR_FLOOR_Y = 4.5;
export const CENTRAL_RISER_X = 0.0;
export const CENTRAL_RISER_Z = 0.0;
export const DECK_INTAKE_OFFSET_X = 2.6;
export const VPA_MORPH_DURATION_MS = 1200;
export const HPA_DISPATCH_PULSE_MS = 700;
export const HPA_LATERAL_SLIDE_MS = 900;

/** Autoscaling theme: golden (dispatch pulses, auras, ghost hulls). */
export const AUTOSCALING_GOLD = 0xffd700;
/** Slightly amber-shifted gold used for the ghost hull wireframe. */
const GHOST_HULL_COLOR = 0xfbbf24;

const CAPSULE_RADIAL_SEGMENTS = 16;
const CAPSULE_CAP_SEGMENTS = 16;
const POD_HEIGHT_MIN = 0.4;
const POD_HEIGHT_MAX = 2.6;
const POD_RADIUS_MIN = 0.2;
const POD_RADIUS_MAX = 0.9;

// ---------------------------------------------------------------------------
// Pure helpers (mirrors of the Python layout math)
// ---------------------------------------------------------------------------

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
}

const MEMORY_SUFFIX_GIB: Array<[string, number]> = [
  ['Ki', 1 / 1024 / 1024 / 1024],
  ['Mi', 1 / 1024 / 1024],
  ['Gi', 1],
  ['Ti', 1024],
  ['K', 1000 / 1024 / 1024 / 1024],
  ['M', 1e6 / 1024 / 1024 / 1024],
  ['G', 1e9 / 1024 / 1024 / 1024],
  ['T', 1e12 / 1024 / 1024 / 1024],
];

/** Parse a Kubernetes quantity: cpu -> cores, memory -> GiB. null if absent. */
export function parseResourceQuantity(
  quantity: string | number | null | undefined,
  kind: 'cpu' | 'memory',
): number | null {
  if (quantity === null || quantity === undefined) return null;
  const text = String(quantity).trim();
  if (text.length === 0) return null;
  if (kind === 'cpu') {
    if (text.endsWith('m')) {
      const n = Number(text.slice(0, -1));
      return Number.isFinite(n) ? n / 1000 : null;
    }
    const n = Number(text);
    return Number.isFinite(n) ? n : null;
  }
  for (const [suffix, mult] of MEMORY_SUFFIX_GIB) {
    if (text.endsWith(suffix)) {
      const n = Number(text.slice(0, -suffix.length));
      return Number.isFinite(n) ? n * mult : null;
    }
  }
  const n = Number(text);
  return Number.isFinite(n) ? n : null; // bare number interpreted as GiB
}

/** easeInOutCubic — the standard tween curve used across the viewport. */
function ease(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

/** Proportional capsule dims for (cpuCores, memoryGib) — SPEC-09 §3.1. */
export function capsuleDims(
  cpuCores: number,
  memoryGib: number,
): { height: number; radius: number } {
  const cpu = Math.max(Number.isFinite(cpuCores) ? cpuCores : 0, 0);
  const mem = Math.max(Number.isFinite(memoryGib) ? memoryGib : 0, 0);
  return {
    height: clamp(0.4 + 0.35 * Math.sqrt(cpu), POD_HEIGHT_MIN, POD_HEIGHT_MAX),
    radius: clamp(
      0.2 + 0.12 * Math.log2(Math.max(1, mem)),
      POD_RADIUS_MIN,
      POD_RADIUS_MAX,
    ),
  };
}

/** True when a VPA status recommends dimensions differing from current. */
export function vpaRecommendationDiffers(
  status: AutoscalingStatusData | null | undefined,
  currentCpuCores: number,
  currentMemoryGib: number,
): boolean {
  if (!status || !status.has_vpa) return false;
  const tgtCpu = parseResourceQuantity(status.vpa_target_cpu, 'cpu');
  const tgtMem = parseResourceQuantity(status.vpa_target_memory, 'memory');
  if (tgtCpu === null && tgtMem === null) return false;
  const newCpu = tgtCpu ?? currentCpuCores;
  const newMem = tgtMem ?? currentMemoryGib;
  return (
    Math.abs(newCpu - currentCpuCores) > 1e-9 ||
    Math.abs(newMem - currentMemoryGib) > 1e-9
  );
}

// ---------------------------------------------------------------------------
// Internal tween records
// ---------------------------------------------------------------------------

interface MorphTween {
  mesh: THREE.Mesh;
  fromHeight: number;
  fromRadius: number;
  toHeight: number;
  toRadius: number;
  elapsed: number; // seconds
  duration: number; // seconds
  rippleAccumulator: number;
  onDone?: () => void;
}

interface SlideTween {
  object: THREE.Object3D;
  from: THREE.Vector3;
  to: THREE.Vector3;
  elapsed: number;
  duration: number;
}

interface PulseTween {
  mesh: THREE.Mesh;
  from: THREE.Vector3;
  to: THREE.Vector3;
  elapsed: number;
  duration: number;
}

interface DelayedAction {
  remaining: number; // seconds
  run: () => void;
}

interface RippleRecord {
  ring: THREE.Mesh;
  material: THREE.MeshBasicMaterial;
  elapsed: number;
  duration: number;
  startY: number;
  travel: number;
}

interface AuraRing {
  nodeId: string;
  ring: THREE.Mesh;
  material: THREE.MeshBasicMaterial;
  baseScale: number;
  rate: number;
  phase: number;
}

// ---------------------------------------------------------------------------
// Manager
// ---------------------------------------------------------------------------

/**
 * Drives every SPEC-09 autoscaling visual. The viewport registers meshes and
 * events with it and calls `update(delta, time)` from the render loop.
 */
export class AutoscalingFxManager {
  private readonly scene: THREE.Scene;

  /** nodeId -> holographic ghost hull group. */
  private readonly ghosts = new Map<string, THREE.Group>();
  private readonly morphs: MorphTween[] = [];
  private readonly slides: SlideTween[] = [];
  private readonly pulses: PulseTween[] = [];
  private readonly ripples: RippleRecord[] = [];
  private readonly delayed: DelayedAction[] = [];
  private readonly auras: AuraRing[] = [];

  private radarVisible = false;

  constructor(scene: THREE.Scene) {
    this.scene = scene;
  }

  // -- VPA ghost hull -------------------------------------------------------

  /**
   * Render / refresh the golden wireframe recommendation hull around a pod.
   * `position` is the pod's world position (capsule center). Passing null
   * dimensions removes the hull (recommendation withdrawn or satisfied).
   */
  public setGhost(
    nodeId: string,
    position: THREE.Vector3,
    height: number,
    radius: number,
  ): void {
    const existing = this.ghosts.get(nodeId);
    if (existing) {
      this.disposeGhost(existing);
      this.ghosts.delete(nodeId);
    }
    const h = clamp(height, POD_HEIGHT_MIN, POD_HEIGHT_MAX);
    const r = clamp(radius * 1.12, POD_RADIUS_MIN, POD_RADIUS_MAX * 1.12);

    const group = new THREE.Group();
    group.name = 'vpa_ghost_hull';
    group.position.copy(position);

    const hullGeo = new THREE.CapsuleGeometry(
      r,
      Math.max(0.02, h - 2 * r + 0.12),
      CAPSULE_RADIAL_SEGMENTS,
      CAPSULE_CAP_SEGMENTS,
    );
    const hullMat = new THREE.MeshBasicMaterial({
      color: GHOST_HULL_COLOR,
      wireframe: true,
      transparent: true,
      opacity: 0.32,
      depthWrite: false,
    });
    const hull = new THREE.Mesh(hullGeo, hullMat);
    hull.userData.fxHull = true;
    group.add(hull);

    // Baseline halo marking where the expanded hull meets the deck.
    const baseGeo = new THREE.RingGeometry(r * 0.92, r * 1.06, 32);
    const baseMat = new THREE.MeshBasicMaterial({
      color: GHOST_HULL_COLOR,
      transparent: true,
      opacity: 0.4,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const base = new THREE.Mesh(baseGeo, baseMat);
    base.rotation.x = -Math.PI / 2;
    base.position.y = -h / 2 + 0.015;
    group.add(base);

    this.scene.add(group);
    this.ghosts.set(nodeId, group);
  }

  public clearGhost(nodeId: string): void {
    const g = this.ghosts.get(nodeId);
    if (g) {
      this.disposeGhost(g);
      this.ghosts.delete(nodeId);
    }
  }

  public hasGhost(nodeId: string): boolean {
    return this.ghosts.has(nodeId);
  }

  // -- VPA in-place morph ---------------------------------------------------

  /**
   * Animate a capsule mesh from its current dimensions to the target using a
   * per-frame geometry tween (SPEC-09 §3.2.2: lerp over ~1200ms) while
   * emitting golden energy ripples rising from base to crown.
   */
  public startMorph(
    mesh: THREE.Mesh,
    fromHeight: number,
    fromRadius: number,
    toHeight: number,
    toRadius: number,
    durationMs: number = VPA_MORPH_DURATION_MS,
    onDone?: () => void,
  ): void {
    // Replace any morph still running on the same mesh.
    for (let i = this.morphs.length - 1; i >= 0; i--) {
      if (this.morphs[i]?.mesh === mesh) this.morphs.splice(i, 1);
    }
    this.morphs.push({
      mesh,
      fromHeight: clamp(fromHeight, POD_HEIGHT_MIN, POD_HEIGHT_MAX),
      fromRadius: clamp(fromRadius, POD_RADIUS_MIN, POD_RADIUS_MAX),
      toHeight: clamp(toHeight, POD_HEIGHT_MIN, POD_HEIGHT_MAX),
      toRadius: clamp(toRadius, POD_RADIUS_MIN, POD_RADIUS_MAX),
      elapsed: 0,
      duration: Math.max(0.05, durationMs / 1000),
      rippleAccumulator: 0,
      onDone,
    });
  }

  private rebuildCapsule(mesh: THREE.Mesh, height: number, radius: number): void {
    const old = mesh.geometry;
    mesh.geometry = new THREE.CapsuleGeometry(
      radius,
      Math.max(0.02, height - 2 * radius),
      CAPSULE_RADIAL_SEGMENTS,
      CAPSULE_CAP_SEGMENTS,
    );
    old.dispose();
    mesh.userData.podHeight = height;
  }

  /**
   * Energy emission ripple: a golden ring expanding as it climbs from the
   * capsule base to its crown (SPEC-09 §3.2.2). Rings are owned by this
   * manager and advanced explicitly in `update()` — no scene scanning.
   */
  private spawnRipple(mesh: THREE.Mesh, height: number, radius: number): void {
    const parent = mesh.parent ?? this.scene;
    const local = parent === this.scene ? mesh.getWorldPosition(new THREE.Vector3()) : mesh.position;

    const geo = new THREE.RingGeometry(radius * 0.8, radius * 1.05, 32);
    const mat = new THREE.MeshBasicMaterial({
      color: AUTOSCALING_GOLD,
      transparent: true,
      opacity: 0.9,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const ring = new THREE.Mesh(geo, mat);
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(local.x, local.y - height / 2, local.z);
    parent.add(ring);
    this.ripples.push({
      ring,
      material: mat,
      elapsed: 0,
      duration: 0.8,
      startY: ring.position.y,
      travel: height,
    });
  }

  // -- HPA dispatch pulse & lateral conveyor --------------------------------

  /**
   * Fire the golden dispatch pulse (SPEC-09 §3.3.1) from the Supervisor
   * Floor down the central riser pipe to the worker deck.
   */
  public fireDispatchPulse(
    from?: { x: number; y: number; z: number },
    to?: { x: number; y: number; z: number },
    durationMs: number = HPA_DISPATCH_PULSE_MS,
    onArrived?: () => void,
  ): void {
    const fromV = from
      ? new THREE.Vector3(from.x, from.y, from.z)
      : new THREE.Vector3(CENTRAL_RISER_X, SUPERVISOR_FLOOR_Y, CENTRAL_RISER_Z);
    const toV = to
      ? new THREE.Vector3(to.x, to.y, to.z)
      : new THREE.Vector3(CENTRAL_RISER_X, 0.75, CENTRAL_RISER_Z);

    // Faint rail along the riser so the pulse path reads as a pipe.
    const railGeo = new THREE.BufferGeometry().setFromPoints([fromV, toV]);
    const railMat = new THREE.LineBasicMaterial({
      color: AUTOSCALING_GOLD,
      transparent: true,
      opacity: 0.22,
    });
    const rail = new THREE.Line(railGeo, railMat);
    this.scene.add(rail);

    const geo = new THREE.SphereGeometry(0.16, 16, 16);
    const mat = new THREE.MeshBasicMaterial({
      color: AUTOSCALING_GOLD,
      transparent: true,
      opacity: 0.95,
    });
    const orb = new THREE.Mesh(geo, mat);
    orb.position.copy(fromV);
    this.scene.add(orb);

    this.pulses.push({
      mesh: orb,
      from: fromV,
      to: toV,
      elapsed: 0,
      duration: Math.max(0.05, durationMs / 1000),
    });

    if (onArrived) {
      this.delayed.push({ remaining: Math.max(0.05, durationMs / 1000), run: onArrived });
    }
    this.delayed.push({
      remaining: Math.max(0.05, durationMs / 1000) + 1.6,
      run: () => {
        this.scene.remove(rail);
        railGeo.dispose();
        railMat.dispose();
      },
    });
  }

  /** Slide an object laterally along the node chassis tray (SPEC-09 §3.3.2). */
  public slideIntoSlot(
    object: THREE.Object3D,
    intake: THREE.Vector3,
    slot: THREE.Vector3,
    durationMs: number = HPA_LATERAL_SLIDE_MS,
  ): void {
    object.position.copy(intake);
    object.visible = true;
    this.slides.push({
      object,
      from: intake.clone(),
      to: slot.clone(),
      elapsed: 0,
      duration: Math.max(0.05, durationMs / 1000),
    });
  }

  // -- Autoscaling Radar auras (KeyU) ----------------------------------------

  /** Register a pulsating golden aura ring under a VPA/HPA-managed pod. */
  public addAura(nodeId: string, position: THREE.Vector3, kind: 'vpa' | 'hpa'): void {
    this.removeAura(nodeId);
    const r = kind === 'hpa' ? 0.62 : 0.52;
    const geo = new THREE.RingGeometry(r, r + 0.08, 48);
    const mat = new THREE.MeshBasicMaterial({
      color: AUTOSCALING_GOLD,
      transparent: true,
      opacity: 0,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const ring = new THREE.Mesh(geo, mat);
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(position.x, position.y, position.z);
    ring.visible = this.radarVisible;
    this.scene.add(ring);
    this.auras.push({
      nodeId,
      ring,
      material: mat,
      baseScale: 1.0,
      rate: kind === 'hpa' ? 4.2 : 2.8,
      phase: kind === 'hpa' ? Math.PI / 3 : 0,
    });
  }

  /** Remove the aura ring registered for a node (call on node removal). */
  public removeAura(nodeId: string): void {
    for (let i = this.auras.length - 1; i >= 0; i--) {
      const aura = this.auras[i];
      if (!aura || aura.nodeId !== nodeId) continue;
      this.scene.remove(aura.ring);
      aura.ring.geometry.dispose();
      aura.material.dispose();
      this.auras.splice(i, 1);
    }
  }

  public clearAuras(): void {
    for (const aura of this.auras) {
      this.scene.remove(aura.ring);
      aura.ring.geometry.dispose();
      aura.material.dispose();
    }
    this.auras.length = 0;
  }

  public setRadarVisible(visible: boolean): void {
    this.radarVisible = visible;
    for (const aura of this.auras) {
      aura.ring.visible = visible;
      if (!visible) aura.material.opacity = 0;
    }
  }

  public isRadarVisible(): boolean {
    return this.radarVisible;
  }

  // -- Frame update -----------------------------------------------------------

  public update(delta: number, time: number): void {
    // Delayed actions (post-arrival conveyor spawns, rail cleanup).
    for (let i = this.delayed.length - 1; i >= 0; i--) {
      const action = this.delayed[i];
      if (!action) continue;
      action.remaining -= delta;
      if (action.remaining <= 0) {
        this.delayed.splice(i, 1);
        action.run();
      }
    }

    // VPA geometry morphs.
    for (let i = this.morphs.length - 1; i >= 0; i--) {
      const tw = this.morphs[i];
      if (!tw) continue;
      tw.elapsed += delta;
      const t = Math.min(1, tw.elapsed / tw.duration);
      const k = ease(t);
      const h = THREE.MathUtils.lerp(tw.fromHeight, tw.toHeight, k);
      const r = THREE.MathUtils.lerp(tw.fromRadius, tw.toRadius, k);
      this.rebuildCapsule(tw.mesh, h, r);

      // Energy emission ripple every ~260ms while expanding.
      tw.rippleAccumulator += delta;
      if (tw.rippleAccumulator >= 0.26 && t < 1) {
        tw.rippleAccumulator = 0;
        this.spawnRipple(tw.mesh, h, r);
      }

      if (t >= 1) {
        this.morphs.splice(i, 1);
        if (tw.onDone) tw.onDone();
      }
    }

    // Lateral conveyor slides.
    for (let i = this.slides.length - 1; i >= 0; i--) {
      const tw = this.slides[i];
      if (!tw) continue;
      tw.elapsed += delta;
      const t = Math.min(1, tw.elapsed / tw.duration);
      tw.object.position.lerpVectors(tw.from, tw.to, ease(t));
      if (t >= 1) this.slides.splice(i, 1);
    }

    // Golden dispatch pulses down the riser.
    for (let i = this.pulses.length - 1; i >= 0; i--) {
      const tw = this.pulses[i];
      if (!tw) continue;
      tw.elapsed += delta;
      const t = Math.min(1, tw.elapsed / tw.duration);
      tw.mesh.position.lerpVectors(tw.from, tw.to, ease(t));
      tw.mesh.scale.setScalar(1 + 0.35 * Math.sin(t * Math.PI));
      if (t >= 1) {
        this.scene.remove(tw.mesh);
        tw.mesh.geometry.dispose();
        (tw.mesh.material as THREE.Material).dispose();
        this.pulses.splice(i, 1);
      }
    }

    // Energy ripples climbing morphing capsules.
    for (let i = this.ripples.length - 1; i >= 0; i--) {
      const ripple = this.ripples[i];
      if (!ripple) continue;
      ripple.elapsed += delta;
      const t = Math.min(1, ripple.elapsed / ripple.duration);
      ripple.ring.position.y = ripple.startY + ripple.travel * t;
      ripple.ring.scale.setScalar(1 + 1.6 * t);
      ripple.material.opacity = 0.9 * (1 - t);
      if (t >= 1) {
        ripple.ring.parent?.remove(ripple.ring);
        ripple.ring.geometry.dispose();
        ripple.material.dispose();
        this.ripples.splice(i, 1);
      }
    }

    // Ghost hull hologram shimmer + radar radar auras.
    const shimmer = 0.24 + 0.12 * (0.5 + 0.5 * Math.sin(time * 3.1));
    for (const ghost of this.ghosts.values()) {
      ghost.traverse((child) => {
        const mat = (child as THREE.Mesh).material as THREE.MeshBasicMaterial | undefined;
        if (mat && mat.isMeshBasicMaterial) {
          mat.opacity = child.userData.fxHull ? shimmer : shimmer + 0.12;
        }
      });
    }
    if (this.radarVisible) {
      for (const aura of this.auras) {
        const pulse = 0.5 + 0.5 * Math.sin(time * aura.rate + aura.phase);
        aura.material.opacity = 0.25 + 0.45 * pulse;
        aura.ring.scale.setScalar(aura.baseScale * (1 + 0.18 * pulse));
      }
    }
  }

  // -- Teardown -----------------------------------------------------------------

  private disposeGhost(group: THREE.Group): void {
    this.scene.remove(group);
    group.traverse((child) => {
      const mesh = child as THREE.Mesh;
      if (mesh.isMesh) {
        mesh.geometry.dispose();
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        for (const m of mats) m.dispose();
      }
    });
  }

  public clear(): void {
    for (const ghost of this.ghosts.values()) this.disposeGhost(ghost);
    this.ghosts.clear();
    this.morphs.length = 0;
    this.slides.length = 0;
    for (const tw of this.pulses) {
      this.scene.remove(tw.mesh);
      tw.mesh.geometry.dispose();
      (tw.mesh.material as THREE.Material).dispose();
    }
    this.pulses.length = 0;
    this.delayed.length = 0;
    this.clearAuras();
  }
}
