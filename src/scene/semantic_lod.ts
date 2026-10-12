/**
 * SPEC-13 / TASK-CV-1402: Semantic Level-of-Detail & Anomaly Outlier Ejection.
 *
 * Implements the semantic LOD engine (ADR-1302) that keeps scene draw calls near
 * constant (<500 objects) while guaranteeing zero visual latency on critical alerts:
 *
 *   - FLEET     (camera dist > 120): namespaces collapse to volumetric boundary
 *               hulls with summary health counters.
 *   - STRATUM   (40 <= dist <= 120): healthy workloads render as unified compact
 *               Workload Aggregation Slabs with top-face status-pill badges.
 *   - INSPECTION(dist < 40): pods dissolve into 1:1 discrete capsules rendered
 *               through the shared InstancedPodRenderer pipeline.
 *
 * Anomaly Outlier Ejection (SPEC-13 §3.2) is LOD-independent: any pod in an
 * abnormal condition (`CrashLoopBackOff`, `ImagePullBackOff`, `OOMKilled`,
 * `Pending`, or an active VPA/HPA morph) is physically ejected as an autonomous,
 * pulsating 3D capsule at its node slot, linked to its parent workload by a
 * luminous tractor line.
 */

import * as THREE from 'three';
// SPEC-13 §3.1: the shared instanced pod pipeline consumed in INSPECTION mode.
import type { IInstancedPodRenderer, PodInstanceRecord } from './instanced_pod_renderer.js';

// ---------------------------------------------------------------------------
// Public contracts (SPEC-13 §3.2)
// ---------------------------------------------------------------------------

/** Semantic zoom tiers keyed off camera distance to the cluster bounding volume. */
export enum LodTier {
  /** Camera dist > 120: namespace boundary hulls & summary counters. */
  FLEET = 0,
  /** Camera dist 40 - 120: Workload Aggregation Slabs + Anomaly Ejection. */
  STRATUM = 1,
  /** Camera dist < 40: 1:1 discrete instanced capsules. */
  INSPECTION = 2,
}

/** A compact unified slab aggregating a healthy workload (STRATUM tier). */
export interface WorkloadSlabAggregate {
  namespace: string;
  workloadName: string;
  kind: string;
  podCount: number;
  healthyCount: number;
  anomalousCount: number;
  /** World-space center of the aggregated workload. */
  centroid: [number, number, number];
  /** Slab extents in world units (x, y, z). */
  dimensions: [number, number, number];
  /** Holographic counter pill rendered on the slab top face. */
  statusPillText: string;
}

/** Abnormal condition of a pod triggering physical ejection (SPEC-13 §3.2). */
export type AnomalyReason =
  | 'CrashLoopBackOff'
  | 'ImagePullBackOff'
  | 'OOMKilled'
  | 'Pending'
  | 'Morphing';

/** An autonomously ejected anomalous pod capsule + its luminous tractor line. */
export interface AnomalyOutlierPod {
  podId: string;
  workloadName: string;
  namespace: string;
  reason: AnomalyReason;
  /** Ejected capsule world position (designated node slot). */
  nodeSlotPosition: [number, number, number];
  /** Parent workload slab center the tractor line anchors to. */
  parentSlabPosition: [number, number, number];
  /** 0..1 traction strength driving the capsule pulse / line luminosity. */
  tractorTension: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Camera distance above which namespaces collapse into fleet hulls (LOD 0). */
const FLEET_DISTANCE = 120;
/** Camera distance below which slabs dissolve into 1:1 pods (LOD 2). */
const STRATUM_DISTANCE = 40;

/** Healthy workload slab body color (teal) — SPEC-13 §3.2. */
const SLAB_COLOR = 0x22d3ee;
/** FLEET namespace hull fill (translucent indigo). */
const HULL_COLOR = 0x6366f1;
/** Anomalous capsule emissive amber used for crash/OOM/pending ejection. */
const ANOMALY_AMBER = 0xffb020;
/** Morphing capsules emit a distinct golden hue. */
const MORPH_GOLD = 0xffd700;
/** Tractor line luminous amber. */
const TRACTOR_COLOR = 0xffa040;

const CAPSULE_RADIUS = 0.35;
const CAPSULE_LENGTH = 0.8;
const CAPSULE_SEGMENTS = 12;

/** Badge sprite world size (billboard). */
const BADGE_WIDTH = 3.4;
const BADGE_HEIGHT = 1.2;
const CANVAS_W = 256;
const CANVAS_H = 96;

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
}

/** Coerce an unknown centroid/dimension field into a 3-tuple with fallbacks. */
function toTriple(
  value: unknown,
  fallbackX = 0,
  fallbackY = 1,
  fallbackZ = 0,
): [number, number, number] {
  if (Array.isArray(value)) {
    const n = Number(value[0]);
    const m = Number(value[1]);
    const k = Number(value[2]);
    return [
      Number.isFinite(n) ? n : fallbackX,
      Number.isFinite(m) ? m : fallbackY,
      Number.isFinite(k) ? k : fallbackZ,
    ];
  }
  if (value && typeof value === 'object') {
    const o = value as Record<string, unknown>;
    const x = Number(o.x ?? o[0]);
    const y = Number(o.y ?? o[1]);
    const z = Number(o.z ?? o[2]);
    return [
      Number.isFinite(x) ? x : fallbackX,
      Number.isFinite(y) ? y : fallbackY,
      Number.isFinite(z) ? z : fallbackZ,
    ];
  }
  return [fallbackX, fallbackY, fallbackZ];
}

function asNumber(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

/** Map an anomalous reason onto the shared status-code space (aInstanceData.x). */
function anomalyStatusCode(reason: AnomalyReason): number {
  switch (reason) {
    case 'CrashLoopBackOff':
    case 'ImagePullBackOff':
      return 1; // CRASH_LOOP
    case 'OOMKilled':
      return 2; // OOM
    case 'Pending':
      return 3; // PENDING
    case 'Morphing':
      return 0; // healthy-but-morphing keeps the neutral body tint
  }
}

/** Normalize an arbitrary wire workload into a slab aggregate (or null). */
function toSlab(input: unknown): WorkloadSlabAggregate | null {
  if (!input || typeof input !== 'object') return null;
  const w = input as Record<string, unknown>;
  const meta = (w.metadata && typeof w.metadata === 'object' ? w.metadata : {}) as Record<
    string,
    unknown
  >;

  const namespace = String(w.namespace ?? meta.namespace ?? 'default');
  const workloadName = String(w.workloadName ?? w.name ?? meta.name ?? 'unknown');
  const kind = String(w.kind ?? 'Workload');

  const podCount = Math.max(0, Math.floor(asNumber(w.podCount ?? w.replicas)));
  const healthyCount = clamp(Math.floor(asNumber(w.healthyCount)), 0, podCount);
  const anomalousCount = Math.max(0, podCount - healthyCount);

  // Prefer explicit spatial fields; fall back to averaging any inline pod positions.
  let centroid: [number, number, number] | null = null;
  if (w.centroid !== undefined || w.position !== undefined) {
    centroid = toTriple(w.centroid ?? w.position);
  } else if (Array.isArray(w.pods)) {
    const pts: Array<[number, number, number]> = [];
    for (const p of w.pods) {
      if (!p || typeof p !== 'object') continue;
      const rec = p as Record<string, unknown>;
      const pos = toTriple(rec.position ?? rec.spatial);
      pts.push(pos);
    }
    if (pts.length > 0) {
      let sx = 0;
      let sy = 0;
      let sz = 0;
      for (const [x, y, z] of pts) {
        sx += x;
        sy += y;
        sz += z;
      }
      centroid = [
        sx / pts.length,
        sy / pts.length,
        sz / pts.length,
      ];
    }
  }
  if (!centroid) centroid = toTriple(undefined, 0, 2, 0);

  let dimensions: [number, number, number] | null = null;
  if (w.dimensions !== undefined || w.scale !== undefined) {
    const d = toTriple(w.dimensions ?? w.scale, 1.6, 0.5, 1.2);
    dimensions = [
      Math.max(0.3, d[0]),
      Math.max(0.16, d[1]),
      Math.max(0.4, d[2]),
    ];
  } else {
    dimensions = [1.8, 0.55, 1.6];
  }

  const statusPillText =
    `${podCount} pod${podCount === 1 ? '' : 's'} · ` +
    `${healthyCount} healthy` +
    (anomalousCount > 0 ? ` · ${anomalousCount} anom` : '');

  return {
    namespace,
    workloadName,
    kind,
    podCount,
    healthyCount,
    anomalousCount,
    centroid,
    dimensions,
    statusPillText,
  };
}

/** Detect whether a raw pod object is in an abnormal condition. */
function podAnomalyReason(pod: unknown): AnomalyReason | null {
  if (!pod || typeof pod !== 'object') return null;
  const p = pod as Record<string, unknown>;

  // Morphing (VPA/HPA active transit) is signaled by explicit flags.
  const autoscaling =
    p.autoscaling && typeof p.autoscaling === 'object'
      ? (p.autoscaling as Record<string, unknown>)
      : null;
  if (
    autoscaling &&
    (autoscaling.is_resizing_in_place === true || autoscaling.morphing === true)
  ) {
    return 'Morphing';
  }

  // phase === 'Pending' is the coarse abnormal signal.
  const status =
    p.status && typeof p.status === 'object'
      ? (p.status as Record<string, unknown>)
      : null;
  const phase = String(p.phase ?? status?.phase ?? '');
  if (phase === 'Pending') return 'Pending';

  // waiting.reason carries the crash/OOM classification.
  let reason = String(p.reason ?? p.waitingReason ?? '');
  if (!reason) {
    const containerStatuses = Array.isArray(p.containerStatuses)
      ? (p.containerStatuses as unknown[])
      : [];
    const first = containerStatuses[0];
    const state =
      first && typeof first === 'object'
        ? ((first as Record<string, unknown>).state as Record<string, unknown> | null)
        : null;
    const waiting =
      state && typeof state === 'object' ? (state.waiting as Record<string, unknown> | null) : null;
    reason = String(waiting?.reason ?? '');
  }
  if (reason === 'CrashLoopBackOff') return 'CrashLoopBackOff';
  if (reason === 'ImagePullBackOff') return 'ImagePullBackOff';
  if (reason === 'OOMKilled') return 'OOMKilled';
  return null;
}

// ---------------------------------------------------------------------------
// SemanticLodManager
// ---------------------------------------------------------------------------

/**
 * Owns the three semantic zoom tiers and the Anomaly Outlier Ejection pipeline.
 * Healthy workloads collapse into slabs/hulls; anomalous pods are physically ejected
 * as autonomous glowing capsules linked to their parent by luminous tractor lines.
 */
export class SemanticLodManager {
  private readonly scene: THREE.Scene;
  private podRenderer: IInstancedPodRenderer | null = null;

  private currentTier: LodTier = LodTier.FLEET;
  /** World-space cluster center used for distance-based tier evaluation. */
  private readonly clusterCenter = new THREE.Vector3(0, 2, 0);
  private elapsed = 0;

  /** namespace/workloadName -> aggregate (STRATUM slabs + FLEET hulls). */
  private readonly aggregates: Map<string, WorkloadSlabAggregate> = new Map();
  /** podId -> anomaly record driving the ejection visuals. */
  private readonly anomalies: Map<string, AnomalyOutlierPod> = new Map();

  // Scene groups (visibility toggled per tier).
  private readonly fleetGroup = new THREE.Group();
  private readonly stratumGroup = new THREE.Group();
  private readonly anomalyGroup = new THREE.Group();

  // STRATUM slab instanced mesh + top-face badges.
  private slabMesh: THREE.InstancedMesh | null = null;
  private slabGeometry: THREE.BoxGeometry | null = null;
  private slabMaterial: THREE.MeshStandardMaterial | null = null;
  private readonly slabBadges: THREE.Sprite[] = [];
  private readonly slabBadgeMaterials: THREE.SpriteMaterial[] = [];
  private readonly slabBadgeTextures: THREE.CanvasTexture[] = [];

  // FLEET namespace hulls + summary counters.
  private readonly namespaceHulls: THREE.Mesh[] = [];
  private readonly namespaceHullMaterials: THREE.MeshBasicMaterial[] = [];
  private readonly namespaceBadges: THREE.Sprite[] = [];
  private readonly namespaceBadgeMaterials: THREE.SpriteMaterial[] = [];
  private readonly namespaceBadgeTextures: THREE.CanvasTexture[] = [];

  // Ejected anomaly capsules + tractor lines.
  private readonly anomalyCapsules: Map<string, THREE.Mesh> = new Map();
  private readonly anomalyLineGeometries: Map<string, THREE.BufferGeometry> = new Map();
  private readonly anomalyLineMaterials: Map<string, THREE.LineBasicMaterial> = new Map();

  /** Pod records mirrored to the InstancedPodRenderer while in INSPECTION. */
  private podRecords: PodInstanceRecord[] = [];

  constructor(scene: THREE.Scene) {
    this.scene = scene;
    this.fleetGroup.name = 'semantic_lod_fleet';
    this.stratumGroup.name = 'semantic_lod_stratum';
    this.anomalyGroup.name = 'semantic_lod_anomalies';
    this.scene.add(this.fleetGroup, this.stratumGroup, this.anomalyGroup);
  }

  // -------------------------------------------------------------------------
  // Lifecycle
  // -------------------------------------------------------------------------

  /** Bind the scene and the shared instanced pod renderer (SPEC-13 §3.2). */
  public initialize(_scene: THREE.Scene, podRenderer: IInstancedPodRenderer): void {
    this.podRenderer = podRenderer;
    this.setTier(LodTier.FLEET);
  }

  /** Release every owned mesh, geometry, material and texture from the scene. */
  public dispose(): void {
    this.clearSlabs();
    this.clearNamespaceHulls();
    this.clearAnomalies();

    this.scene.remove(this.fleetGroup, this.stratumGroup, this.anomalyGroup);
    this.podRenderer?.syncPods([]);
    this.podRenderer = null;
    this.aggregates.clear();
    this.anomalies.clear();
  }

  // -------------------------------------------------------------------------
  // Frame update & tier evaluation
  // -------------------------------------------------------------------------

  /**
   * Evaluate the camera distance to the cluster bounding volume, switch tiers when
   * thresholds are crossed, and advance anomaly pulse / tractor-line animation.
   */
  public update(camera: THREE.Camera, deltaTime: number): void {
    const dt = Number.isFinite(deltaTime) ? deltaTime : 0;
    this.elapsed += dt;

    const dist = camera.position.distanceTo(this.clusterCenter);
    const tier =
      dist > FLEET_DISTANCE
        ? LodTier.FLEET
        : dist < STRATUM_DISTANCE
          ? LodTier.INSPECTION
          : LodTier.STRATUM;
    this.setTier(tier);

    // Advance the shared instanced pod pipeline's pulse uniform.
    this.podRenderer?.updateAnimation(dt);

    // Animate ejected anomaly capsules + luminous tractor lines.
    for (const [podId, anomaly] of this.anomalies) {
      const capsule = this.anomalyCapsules.get(podId);
      if (capsule) {
        const tension = clamp(anomaly.tractorTension, 0, 1);
        const rate = anomaly.reason === 'Morphing' ? 2.6 : 5.4;
        const pulse = 0.12 * Math.sin(this.elapsed * rate + podId.length) * (0.35 + tension);
        capsule.scale.setScalar(1 + pulse);
      }
      const lineMat = this.anomalyLineMaterials.get(podId);
      if (lineMat) {
        const tension = clamp(anomaly.tractorTension, 0, 1);
        lineMat.opacity =
          0.35 +
          (0.45 + 0.2 * Math.sin(this.elapsed * 6.2)) *
            (0.25 + 0.75 * tension);
      }
    }
  }

  // -------------------------------------------------------------------------
  // Workload synchronization
  // -------------------------------------------------------------------------

  /**
   * Rebuild slab aggregates, FLEET namespace hulls and the INSPECTION pod records
   * from an arbitrary workload payload, auto-ejecting any abnormal pods found.
   */
  public syncWorkloads(workloads: unknown[]): void {
    const list = Array.isArray(workloads) ? workloads : [];
    this.aggregates.clear();
    this.podRecords = [];

    for (const w of list) {
      const slab = toSlab(w);
      if (!slab) continue;
      const key = `${slab.namespace}/${slab.workloadName}`;
      this.aggregates.set(key, slab);

      // Extract 1:1 pod records for the INSPECTION tier.
      this.podRecords.push(...this.extractPodRecords(w));

      // Auto-eject any abnormal pods carried inline (SPEC-13 §3.2 contract).
      this.detectAnomaliesInWorkload(w, slab);
    }

    this.rebuildSlabs();
    this.rebuildNamespaceHulls();

    if (this.currentTier === LodTier.INSPECTION) {
      this.podRenderer?.syncPods(this.podRecords);
    }
  }

  /** Register / refresh an anomalous pod ejection (capsule + tractor line). */
  public registerAnomaly(anomaly: AnomalyOutlierPod): void {
    this.anomalies.set(anomaly.podId, anomaly);
    this.buildAnomalyVisuals(anomaly);
    // If the pod is rendered 1:1 (INSPECTION), flag its GPU ejection tween.
    this.podRenderer?.setEjectionState(anomaly.podId, true);
  }

  /** Current semantic tier (useful for HUD / debug readouts). */
  public getTier(): LodTier {
    return this.currentTier;
  }

  // -------------------------------------------------------------------------
  // Tier switching
  // -------------------------------------------------------------------------

  private setTier(tier: LodTier): void {
    if (tier === this.currentTier) return;
    const prev = this.currentTier;
    this.currentTier = tier;

    this.fleetGroup.visible = tier === LodTier.FLEET;
    this.stratumGroup.visible = tier === LodTier.STRATUM;
    // Ejected anomalies remain visible while pods are aggregated (FLEET/STRATUM).
    this.anomalyGroup.visible = tier !== LodTier.INSPECTION;

    if (tier === LodTier.INSPECTION) {
      this.podRenderer?.syncPods(this.podRecords);
    } else if (prev === LodTier.INSPECTION) {
      // Release the 1:1 instanced pipeline when zooming back out to slabs.
      this.podRenderer?.syncPods([]);
    }
  }

  // -------------------------------------------------------------------------
  // STRATUM slab construction
  // -------------------------------------------------------------------------

  private rebuildSlabs(): void {
    this.clearSlabs();
    if (this.aggregates.size === 0) return;

    const geometry = new THREE.BoxGeometry(1, 1, 1);
    const material = new THREE.MeshStandardMaterial({
      color: SLAB_COLOR,
      transparent: true,
      opacity: 0.82,
      roughness: 0.4,
      metalness: 0.15,
      emissive: SLAB_COLOR,
      emissiveIntensity: 0.18,
    });
    const mesh = new THREE.InstancedMesh(geometry, material, this.aggregates.size);
    mesh.name = 'SemanticLodSlabs';
    mesh.frustumCulled = false;

    const m4 = new THREE.Matrix4();
    let index = 0;
    for (const slab of this.aggregates.values()) {
      const [cx, cy, cz] = slab.centroid;
      const [sx, sy, sz] = slab.dimensions;
      m4.compose(
        new THREE.Vector3(cx, cy, cz),
        new THREE.Quaternion(),
        new THREE.Vector3(Math.max(0.2, sx), Math.max(0.16, sy), Math.max(0.25, sz)),
      );
      mesh.setMatrixAt(index, m4);

      // Top-face holographic status pill badge.
      const badge = this.makeBadge(slab.statusPillText, SLAB_COLOR);
      badge.position.set(cx, cy + Math.max(0.6, sy / 2) + 0.5, cz);
      this.slabBadges.push(badge);
      this.stratumGroup.add(badge);

      index += 1;
    }
    mesh.instanceMatrix.needsUpdate = true;

    this.slabMesh = mesh;
    this.slabGeometry = geometry;
    this.slabMaterial = material;
    this.stratumGroup.add(mesh);
  }

  private clearSlabs(): void {
    if (this.slabMesh) {
      this.stratumGroup.remove(this.slabMesh);
      this.slabMesh.dispose();
    }
    this.slabGeometry?.dispose();
    this.slabMaterial?.dispose();

    for (const badge of this.slabBadges) this.stratumGroup.remove(badge);
    for (const mat of this.slabBadgeMaterials) mat.dispose();
    for (const tex of this.slabBadgeTextures) tex.dispose();

    this.slabMesh = null;
    this.slabGeometry = null;
    this.slabMaterial = null;
    this.slabBadges.length = 0;
    this.slabBadgeMaterials.length = 0;
    this.slabBadgeTextures.length = 0;
  }

  // -------------------------------------------------------------------------
  // FLEET namespace hull construction
  // -------------------------------------------------------------------------

  private rebuildNamespaceHulls(): void {
    this.clearNamespaceHulls();
    if (this.aggregates.size === 0) return;

    const byNamespace = new Map<string, WorkloadSlabAggregate[]>();
    for (const slab of this.aggregates.values()) {
      const list = byNamespace.get(slab.namespace);
      if (list) list.push(slab);
      else byNamespace.set(slab.namespace, [slab]);
    }

    for (const [namespace, slabs] of byNamespace) {
      let minX = Infinity;
      let maxX = -Infinity;
      let minY = Infinity;
      let maxY = -Infinity;
      let minZ = Infinity;
      let maxZ = -Infinity;
      for (const s of slabs) {
        const [x, y, z] = s.centroid;
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
        if (z < minZ) minZ = z;
        if (z > maxZ) maxZ = z;
      }
      const pad = 2.2;
      const cx = (minX + maxX) / 2;
      const cy = (minY + maxY) / 2;
      const cz = (minZ + maxZ) / 2;
      const sx = Math.max(3, maxX - minX + pad);
      const sy = Math.max(1.6, maxY - minY + pad * 0.8);
      const sz = Math.max(3, maxZ - minZ + pad);

      const geometry = new THREE.BoxGeometry(sx, sy, sz);
      const material = new THREE.MeshBasicMaterial({
        color: HULL_COLOR,
        transparent: true,
        opacity: 0.16,
        depthWrite: false,
        side: THREE.DoubleSide,
      });
      const hull = new THREE.Mesh(geometry, material);
      hull.name = `namespace_hull_${namespace}`;
      hull.position.set(cx, cy, cz);

      // Summary counter billboard (workload / pod totals).
      let workloadTotal = 0;
      let podTotal = 0;
      for (const s of slabs) {
        workloadTotal += 1;
        podTotal += s.podCount;
      }
      const badge = this.makeBadge(
        `${namespace} · ${workloadTotal} workloads / ${podTotal} pods`,
        HULL_COLOR,
      );
      badge.position.set(cx, cy + sy / 2 + 0.7, cz);

      this.namespaceHulls.push(hull);
      this.namespaceHullMaterials.push(material);
      this.namespaceBadges.push(badge);
      this.namespaceBadgeMaterials.push(badge.material as THREE.SpriteMaterial);
      this.fleetGroup.add(hull, badge);
    }
  }

  private clearNamespaceHulls(): void {
    for (const hull of this.namespaceHulls) {
      this.fleetGroup.remove(hull);
      hull.geometry.dispose();
    }
    for (const mat of this.namespaceHullMaterials) mat.dispose();
    for (const badge of this.namespaceBadges) this.fleetGroup.remove(badge);
    for (const mat of this.namespaceBadgeMaterials) mat.dispose();
    for (const tex of this.namespaceBadgeTextures) tex.dispose();

    this.namespaceHulls.length = 0;
    this.namespaceHullMaterials.length = 0;
    this.namespaceBadges.length = 0;
    this.namespaceBadgeMaterials.length = 0;
    this.namespaceBadgeTextures.length = 0;
  }

  // -------------------------------------------------------------------------
  // Anomaly ejection visuals
  // -------------------------------------------------------------------------

  private buildAnomalyVisuals(anomaly: AnomalyOutlierPod): void {
    const existingCapsule = this.anomalyCapsules.get(anomaly.podId);
    if (existingCapsule) {
      this.disposeAnomalyVisuals(anomaly.podId);
    }

    const isMorph = anomaly.reason === 'Morphing';
    const emissiveColor = isMorph ? MORPH_GOLD : ANOMALY_AMBER;

    // Autonomous pulsating capsule at its designated node slot.
    const geometry = new THREE.CapsuleGeometry(
      CAPSULE_RADIUS,
      CAPSULE_LENGTH,
      CAPSULE_SEGMENTS,
      CAPSULE_SEGMENTS,
    );
    const material = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      emissive: emissiveColor,
      emissiveIntensity: isMorph ? 0.9 : 1.5,
      roughness: 0.3,
      metalness: 0.2,
    });
    const capsule = new THREE.Mesh(geometry, material);
    capsule.name = `anomaly_capsule_${anomaly.podId}`;
    const [px, py, pz] = anomaly.nodeSlotPosition;
    capsule.position.set(px, py, pz);

    // Luminous tractor line anchoring the ejected pod to its parent slab.
    const start = new THREE.Vector3(...anomaly.nodeSlotPosition);
    const end = new THREE.Vector3(...anomaly.parentSlabPosition);
    const lineGeometry = new THREE.BufferGeometry().setFromPoints([start, end]);
    const lineMaterial = new THREE.LineBasicMaterial({
      color: TRACTOR_COLOR,
      transparent: true,
      opacity: 0.6,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const line = new THREE.Line(lineGeometry, lineMaterial);
    line.name = `tractor_line_${anomaly.podId}`;
    // Store the Line on the material so disposal can detach it from the group.
    lineMaterial.userData.line = line;

    this.anomalyGroup.add(capsule, line);
    this.anomalyCapsules.set(anomaly.podId, capsule);
    this.anomalyLineGeometries.set(anomaly.podId, lineGeometry);
    this.anomalyLineMaterials.set(anomaly.podId, lineMaterial);
  }

  private disposeAnomalyVisuals(podId: string): void {
    const capsule = this.anomalyCapsules.get(podId);
    if (capsule) {
      this.anomalyGroup.remove(capsule);
      capsule.geometry.dispose();
      (capsule.material as THREE.Material).dispose();
      this.anomalyCapsules.delete(podId);
    }
    const lineGeo = this.anomalyLineGeometries.get(podId);
    if (lineGeo) {
      // Detach the linked Line object before disposing its geometry/material.
      const lineMat = this.anomalyLineMaterials.get(podId);
      if (lineMat && lineMat.userData?.line instanceof THREE.Line) {
        this.anomalyGroup.remove(lineMat.userData.line as THREE.Line);
      }
      lineGeo.dispose();
      this.anomalyLineGeometries.delete(podId);
    }
    const lineMat = this.anomalyLineMaterials.get(podId);
    if (lineMat) {
      lineMat.dispose();
      this.anomalyLineMaterials.delete(podId);
    }
  }

  private clearAnomalies(): void {
    for (const podId of Array.from(this.anomalies.keys())) {
      this.disposeAnomalyVisuals(podId);
    }
    this.anomalies.clear();
  }

  // -------------------------------------------------------------------------
  // Pod record extraction & anomaly auto-detection
  // -------------------------------------------------------------------------

  private extractPodRecords(workload: unknown): PodInstanceRecord[] {
    const w = (workload && typeof workload === 'object' ? workload : {}) as Record<
      string,
      unknown
    >;
    const meta =
      w.metadata && typeof w.metadata === 'object'
        ? (w.metadata as Record<string, unknown>)
        : {};
    const namespace = String(w.namespace ?? meta.namespace ?? 'default');
    const workloadName = String(w.workloadName ?? w.name ?? meta.name ?? 'unknown');
    const pods = Array.isArray(w.pods) ? (w.pods as unknown[]) : [];
    const records: PodInstanceRecord[] = [];

    for (const p of pods) {
      if (!p || typeof p !== 'object') continue;
      const rec = p as Record<string, unknown>;
      const id = String(rec.id ?? rec.name ?? `${namespace}/${workloadName}`);
      const reason = podAnomalyReason(p);
      const statusCode =
        reason !== null
          ? anomalyStatusCode(reason)
          : (() => {
              const phase = String(rec.phase ?? '');
              return phase === 'Running' || phase === 'Succeeded' ? 0 : 0;
            })();
      const [px, py, pz] = toTriple(rec.position ?? rec.spatial, 0, 1, 0);

      records.push({
        id,
        podName: String(rec.name ?? id),
        namespace,
        nodeName: String(rec.nodeName ?? rec.node ?? ''),
        statusCode,
        cpuRatio: clamp(asNumber(rec.cpuRatio ?? rec.cpu), 0, 2),
        memRatio: clamp(asNumber(rec.memRatio ?? rec.memory), 0, 2),
        diffState: Math.max(0, Math.floor(asNumber(rec.diffState))),
        position: [px, py, pz],
        scale: [1, 1, 1],
        quaternion: [0, 0, 0, 1],
        isEjectedOutlier: reason !== null,
      });
    }
    return records;
  }

  private detectAnomaliesInWorkload(
    workload: unknown,
    parentSlab: WorkloadSlabAggregate,
  ): void {
    const w = (workload && typeof workload === 'object' ? workload : {}) as Record<
      string,
      unknown
    >;
    const meta =
      w.metadata && typeof w.metadata === 'object'
        ? (w.metadata as Record<string, unknown>)
        : {};
    const namespace = String(w.namespace ?? meta.namespace ?? 'default');
    const workloadName = String(w.workloadName ?? w.name ?? meta.name ?? 'unknown');
    const pods = Array.isArray(w.pods) ? (w.pods as unknown[]) : [];

    for (const p of pods) {
      if (!p || typeof p !== 'object') continue;
      const rec = p as Record<string, unknown>;
      const reason = podAnomalyReason(p);
      if (!reason) continue;

      const id = String(rec.id ?? rec.name ?? `${namespace}/${workloadName}`);
      const nodeSlot = toTriple(rec.position ?? rec.spatial, 0, 1, 0);
      this.registerAnomaly({
        podId: id,
        workloadName,
        namespace,
        reason,
        nodeSlotPosition: nodeSlot,
        parentSlabPosition: parentSlab.centroid,
        tractorTension: clamp(asNumber(rec.tractorTension ?? rec.ejection, 0.7), 0, 1),
      });
    }
  }

  // -------------------------------------------------------------------------
  // Billboard badge helper
  // -------------------------------------------------------------------------

  private makeBadge(text: string, accentColor: number): THREE.Sprite {
    const canvas = document.createElement('canvas');
    canvas.width = CANVAS_W;
    canvas.height = CANVAS_H;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Failed to get 2D context for LOD badge');

    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);
    const pad = 10;
    const radius = 20;
    ctx.fillStyle = 'rgba(15, 23, 42, 0.78)';
    ctx.strokeStyle = `#${accentColor.toString(16).padStart(6, '0')}`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(pad + radius, pad);
    ctx.lineTo(CANVAS_W - pad - radius, pad);
    ctx.quadraticCurveTo(CANVAS_W - pad, pad, CANVAS_W - pad, pad + radius);
    ctx.lineTo(CANVAS_W - pad, CANVAS_H - pad - radius);
    ctx.quadraticCurveTo(
      CANVAS_W - pad,
      CANVAS_H - pad,
      CANVAS_W - pad - radius,
      CANVAS_H - pad,
    );
    ctx.lineTo(pad + radius, CANVAS_H - pad);
    ctx.quadraticCurveTo(pad, CANVAS_H - pad, pad, CANVAS_H - pad - radius);
    ctx.lineTo(pad, pad + radius);
    ctx.quadraticCurveTo(pad, pad, pad + radius, pad);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    ctx.font = 'bold 26px Inter, system-ui, sans-serif';
    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.shadowColor = 'rgba(255,255,255,0.35)';
    ctx.shadowBlur = 6;
    ctx.fillText(text, CANVAS_W / 2, CANVAS_H / 2);
    ctx.shadowBlur = 0;

    const texture = new THREE.CanvasTexture(canvas);
    texture.needsUpdate = true;
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;
    texture.generateMipmaps = false;

    const material = new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      depthWrite: false,
      depthTest: true,
    });
    this.slabBadgeTextures.push(texture);
    this.slabBadgeMaterials.push(material);

    const sprite = new THREE.Sprite(material);
    sprite.scale.set(BADGE_WIDTH, BADGE_HEIGHT, 1);
    return sprite;
  }
}
