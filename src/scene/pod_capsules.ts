/**
 * SPEC-09 / TASK-CV-1001: Proportional Pod Capsules.
 *
 * Replaces the static cloned `Cuboid_Pod` GLB prototype with procedural
 * `THREE.CapsuleGeometry` whose dimensions map directly to Kubernetes
 * resource requests (ADR-01):
 *
 *   Height (Y) = clamp(0.40 + 0.35 * sqrt(vCPU),        0.40, 2.60)
 *   Radius (R) = clamp(0.20 + 0.12 * log2(max(1, RAM)), 0.20, 0.90)
 *
 * CapsuleGeometry(radius, length, 16, 16) spans `length + 2 * radius`
 * end-to-end, so `length = max(0.02, height - 2 * radius)`.
 *
 * Materials are shared through a cache indexed by container status
 * (Healthy / Degraded / Failed) so hundreds of capsules remain cheap.
 * `PodCapsuleManager.update()` drives the emissive pulse/glow.
 */

import * as THREE from 'three';

// ---------------------------------------------------------------------------
// Types (structurally compatible with ClusterNodeData in cluster_viewport.ts)
// ---------------------------------------------------------------------------

export interface PodGeometryData {
  height: number;
  radius: number;
  color_tint?: string;
  is_pending?: boolean;
  staging_track_x?: number | null;
  karpenter_target_node_claim?: string | null;
}

export interface PodNodeComponent {
  id: string;
  layer: string;
  kind: string;
  name: string;
  namespace?: string;
  status: string;
  metrics?: Record<string, unknown>;
  pod_geometry?: PodGeometryData | null;
  spatial?: { x: number; y: number; z: number; asset_type?: string };
}

export type PodStatus = 'healthy' | 'degraded' | 'failed';

// ---------------------------------------------------------------------------
// Scaling constants (mirror of src/ingestion/layout.py, SPEC-09 §3.1)
// ---------------------------------------------------------------------------

export const POD_HEIGHT_MIN = 0.4;
export const POD_HEIGHT_MAX = 2.6;
export const POD_RADIUS_MIN = 0.2;
export const POD_RADIUS_MAX = 0.9;
export const POD_DEFAULT_CPU_CORES = 0.5;
export const POD_DEFAULT_MEMORY_GIB = 1.0;

/** Status palette per SPEC-09 requirement. */
export const POD_STATUS_COLORS: Record<PodStatus, number> = {
  healthy: 0x4fc3f7,
  degraded: 0xffa726,
  failed: 0xef5350,
};

/** Diff accent colors used for the containment brackets. */
const DIFF_BRACKET_COLORS: Record<string, number> = {
  identical: 0x06b6d4,
  version_skew: 0xfbbf24,
  missing: 0xef4444,
  added: 0x34d399,
};

const CAPSULE_RADIAL_SEGMENTS = 16;
const CAPSULE_CAP_SEGMENTS = 16;

// ---------------------------------------------------------------------------
// Pure math helpers (exported for tests / VPA morph targets)
// ---------------------------------------------------------------------------

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
}

/**
 * Proportional pod capsule dimensions per SPEC-09 §3.1.
 * Returns { height, radius, length } where `length` is the cylindrical
 * segment passed to THREE.CapsuleGeometry (total span = length + 2*radius).
 */
export function calculatePodDimensions(
  cpuCores: number,
  memoryGib: number,
): { height: number; radius: number; length: number } {
  const cpu = Math.max(Number.isFinite(cpuCores) ? cpuCores : 0, 0);
  const mem = Math.max(Number.isFinite(memoryGib) ? memoryGib : 0, 0);
  const height = clamp(0.4 + 0.35 * Math.sqrt(cpu), POD_HEIGHT_MIN, POD_HEIGHT_MAX);
  const radius = clamp(0.2 + 0.12 * Math.log2(Math.max(1, mem)), POD_RADIUS_MIN, POD_RADIUS_MAX);
  const length = Math.max(0.02, height - 2 * radius);
  return { height, radius, length };
}

/** Map a free-form status string onto the three-color taxonomy. */
export function podStatusFromStatusString(status: string | undefined): PodStatus {
  const s = (status || '').toLowerCase();
  if (s.includes('fail') || s.includes('crash') || s.includes('error') || s.includes('backoff')) {
    return 'failed';
  }
  if (
    s.includes('degrad') ||
    s.includes('warn') ||
    s.includes('pending') ||
    s.includes('notready') ||
    s.includes('unknown')
  ) {
    return 'degraded';
  }
  return 'healthy';
}

/**
 * Extract (cpuCores, memoryGib) requests from a node metrics bag, mirroring
 * `layout.extract_pod_requests`: explicit request keys win, then bare
 * capacity keys, then SPEC-09 fallback defaults (0.5 / 1.0).
 */
export function extractPodRequests(
  metrics: Record<string, unknown> | undefined,
): { cpuCores: number; memoryGib: number } {
  const pick = (...keys: string[]): number | null => {
    if (!metrics) return null;
    for (const key of keys) {
      const raw = metrics[key];
      if (raw === undefined || raw === null) continue;
      const n = Number(raw);
      if (Number.isFinite(n)) return n;
    }
    return null;
  };
  const cpuCores = pick('cpu_request_cores', 'cpu_cores') ?? POD_DEFAULT_CPU_CORES;
  const memoryGib = pick('memory_request_gib', 'memory_gib') ?? POD_DEFAULT_MEMORY_GIB;
  return { cpuCores, memoryGib };
}

/** Resolve the final dimensions for a node: explicit pod_geometry wins. */
export function resolvePodDimensions(node: PodNodeComponent): {
  height: number;
  radius: number;
  length: number;
} {
  const geo = node.pod_geometry;
  if (geo && Number.isFinite(geo.height) && Number.isFinite(geo.radius)) {
    const height = clamp(geo.height, POD_HEIGHT_MIN, POD_HEIGHT_MAX);
    const radius = clamp(geo.radius, POD_RADIUS_MIN, POD_RADIUS_MAX);
    return { height, radius, length: Math.max(0.02, height - 2 * radius) };
  }
  const { cpuCores, memoryGib } = extractPodRequests(node.metrics);
  return calculatePodDimensions(cpuCores, memoryGib);
}

// ---------------------------------------------------------------------------
// Shared material cache
// ---------------------------------------------------------------------------

type CapsuleMaterialKey = `${PodStatus}:${string}`;

function materialCacheKey(status: PodStatus, tint: string | undefined): CapsuleMaterialKey {
  return `${status}:${tint ?? ''}` as CapsuleMaterialKey;
}

function buildCapsuleMaterial(status: PodStatus, tint?: string): THREE.MeshStandardMaterial {
  const baseHex = POD_STATUS_COLORS[status];
  const color = new THREE.Color(tint && tint.length > 0 ? tint : baseHex);
  const emissive = new THREE.Color(baseHex);
  return new THREE.MeshStandardMaterial({
    color,
    emissive,
    emissiveIntensity: status === 'failed' ? 0.85 : status === 'degraded' ? 0.55 : 0.35,
    roughness: status === 'healthy' ? 0.32 : 0.45,
    metalness: 0.25,
  });
}

// ---------------------------------------------------------------------------
// Diff accent containment brackets
// ---------------------------------------------------------------------------

function buildDiffBrackets(radius: number, height: number, diffStatus: string): THREE.Group {
  const group = new THREE.Group();
  group.name = 'pod_diff_brackets';

  const colorHex = DIFF_BRACKET_COLORS[diffStatus] ?? 0x06b6d4;
  const bracketMat = new THREE.LineBasicMaterial({
    color: colorHex,
    transparent: true,
    opacity: diffStatus === 'identical' ? 0.35 : 0.85,
  });

  // Bracket cage sized just outside the capsule footprint.
  const size = radius * 2 + 0.28;
  const h = height + 0.16;
  const cornerLen = Math.min(0.2, size * 0.35);

  const corners: Array<{ x: number; y: number; z: number; dx: number; dy: number; dz: number }> =
    [
      { x: -size / 2, y: -h / 2, z: -size / 2, dx: 1, dy: 1, dz: 1 },
      { x: size / 2, y: -h / 2, z: -size / 2, dx: -1, dy: 1, dz: 1 },
      { x: -size / 2, y: h / 2, z: -size / 2, dx: 1, dy: -1, dz: 1 },
      { x: size / 2, y: h / 2, z: -size / 2, dx: -1, dy: -1, dz: 1 },
      { x: -size / 2, y: -h / 2, z: size / 2, dx: 1, dy: 1, dz: -1 },
      { x: size / 2, y: -h / 2, z: size / 2, dx: -1, dy: 1, dz: -1 },
      { x: -size / 2, y: h / 2, z: size / 2, dx: 1, dy: -1, dz: -1 },
      { x: size / 2, y: h / 2, z: size / 2, dx: -1, dy: -1, dz: -1 },
    ];

  for (const c of corners) {
    const edges: Array<[THREE.Vector3, THREE.Vector3]> = [
      [new THREE.Vector3(c.x, c.y, c.z), new THREE.Vector3(c.x + c.dx * cornerLen, c.y, c.z)],
      [new THREE.Vector3(c.x, c.y, c.z), new THREE.Vector3(c.x, c.y + c.dy * cornerLen, c.z)],
      [new THREE.Vector3(c.x, c.y, c.z), new THREE.Vector3(c.x, c.y, c.z + c.dz * cornerLen)],
    ];
    for (const [a, b] of edges) {
      const geo = new THREE.BufferGeometry().setFromPoints([a, b]);
      group.add(new THREE.Line(geo, bracketMat));
    }
  }
  return group;
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/**
 * Build a proportional pod capsule for a node. Returns a THREE.Group when a
 * diff accent bracket is requested, otherwise the bare capsule Mesh. The
 * returned object carries `userData.nodeData` (raycast contract) and
 * `userData.podCapsule = true` (VPA morph handle).
 */
export function createPodCapsule(
  node: PodNodeComponent,
  diffStatus?: string,
  materialCache?: Map<string, THREE.MeshStandardMaterial>,
): THREE.Group | THREE.Mesh {
  const { radius, length, height } = resolvePodDimensions(node);
  const status = podStatusFromStatusString(node.status);

  const cache = materialCache ?? null;
  const key = materialCacheKey(status, node.pod_geometry?.color_tint);
  let material: THREE.MeshStandardMaterial | null = cache ? cache.get(key) ?? null : null;
  if (!material) {
    material = buildCapsuleMaterial(status, node.pod_geometry?.color_tint);
    if (cache) cache.set(key, material);
  }

  const geometry = new THREE.CapsuleGeometry(
    radius,
    length,
    CAPSULE_RADIAL_SEGMENTS,
    CAPSULE_CAP_SEGMENTS,
  );
  const capsule = new THREE.Mesh(geometry, material);
  capsule.userData.nodeData = node;
  capsule.userData.podCapsule = true;
  capsule.userData.podStatus = status;
  capsule.userData.podHeight = height;
  capsule.userData.baseEmissiveIntensity = material.emissiveIntensity;

  if (!diffStatus || diffStatus === 'identical') {
    // No accent cage needed for a clean match — the pulse alone conveys life.
    if (diffStatus === 'identical') {
      const group = new THREE.Group();
      group.add(capsule);
      group.add(buildDiffBrackets(radius, height, 'identical'));
      group.userData.nodeData = node;
      group.userData.podCapsule = true;
      return group;
    }
    return capsule;
  }

  const group = new THREE.Group();
  group.add(capsule);
  group.add(buildDiffBrackets(radius, height, diffStatus));
  group.userData.nodeData = node;
  group.userData.podCapsule = true;
  return group;
}

// ---------------------------------------------------------------------------
// Manager
// ---------------------------------------------------------------------------

/**
 * Owns the shared capsule material cache and the emissive pulse animation.
 * Register capsules (or call `track` on objects produced by
 * `createPodCapsule`) and drive `update(delta, time)` from the render loop.
 */
export class PodCapsuleManager {
  private materialCache: Map<string, THREE.MeshStandardMaterial> = new Map();
  private tracked: Set<THREE.Mesh> = new Set();

  /** Create a capsule and register it for the pulse animation. */
  public create(
    node: PodNodeComponent,
    diffStatus?: string,
  ): THREE.Group | THREE.Mesh {
    const obj = createPodCapsule(node, diffStatus, this.materialCache);
    this.track(obj);
    return obj;
  }

  /** Register an existing capsule (or group containing one) for animation. */
  public track(obj: THREE.Object3D): void {
    if ((obj as THREE.Mesh).isMesh && obj.userData.podCapsule) {
      this.tracked.add(obj as THREE.Mesh);
      return;
    }
    obj.traverse((child) => {
      const mesh = child as THREE.Mesh;
      if (mesh.isMesh && child.userData.podCapsule) {
        this.tracked.add(mesh);
      }
    });
  }

  /** Unregister every capsule owned by an object (call on node removal). */
  public untrack(obj: THREE.Object3D): void {
    if ((obj as THREE.Mesh).isMesh) this.tracked.delete(obj as THREE.Mesh);
    obj.traverse((child) => {
      const mesh = child as THREE.Mesh;
      if (mesh.isMesh) this.tracked.delete(mesh);
    });
  }

  /**
   * Emissive pulse/glow: healthy capsules breathe gently, failed capsules
   * strobe harder. `time` is seconds (THREE.Clock.getElapsedTime()).
   */
  public update(time: number): void {
    for (const mesh of this.tracked) {
      const base = (mesh.userData.baseEmissiveIntensity as number | undefined) ?? 0.35;
      const status = (mesh.userData.podStatus as PodStatus | undefined) ?? 'healthy';
      const amplitude = status === 'failed' ? 0.45 : status === 'degraded' ? 0.3 : 0.18;
      const rate = status === 'failed' ? 6.0 : 2.4;
      const mat = mesh.material as THREE.MeshStandardMaterial;
      if (mat.isMeshStandardMaterial) {
        mat.emissiveIntensity = base + amplitude * (0.5 + 0.5 * Math.sin(time * rate));
      }
    }
  }

  /** VPA in-place morph helper: retarget a tracked capsule's dimensions. */
  public resizeCapsule(mesh: THREE.Mesh, height: number, radius: number): void {
    const clamped = clamp(height, POD_HEIGHT_MIN, POD_HEIGHT_MAX);
    const r = clamp(radius, POD_RADIUS_MIN, POD_RADIUS_MAX);
    const old = mesh.geometry;
    mesh.geometry = new THREE.CapsuleGeometry(
      r,
      Math.max(0.02, clamped - 2 * r),
      CAPSULE_RADIAL_SEGMENTS,
      CAPSULE_CAP_SEGMENTS,
    );
    old.dispose();
    mesh.userData.baseEmissiveIntensity = 0.9; // brief flare while settling
  }

  public clear(): void {
    this.tracked.clear();
  }

  /** Dispose cached shared materials (teardown only; not per-refresh). */
  public dispose(): void {
    this.tracked.clear();
    for (const mat of this.materialCache.values()) mat.dispose();
    this.materialCache.clear();
  }
}
