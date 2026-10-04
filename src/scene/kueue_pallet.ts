/**
 * SPEC-09 / TASK-CV-1004: Kueue Gang Cargo Containment Pallets (ADR-03).
 *
 * Groups the constituent pods of a Kueue `Workload` CRD into a modular
 * industrial cargo containment frame parked on the staging-track rail
 * (X in [-21.0, -15.0], Y in [0.4, 1.8], Z in [-6.0, +6.0]) with a
 * holographic HUD badge showing Workload Name, LocalQueue, constituent pod
 * count (`X/Y Pods`) and required quota (vCPU / RAM / GPUs).
 *
 * Lifecycle visuals per SPEC-09 §5.3:
 *   Queued / Inadmissible  -> cold blue standby lighting + quota deficit
 *                             indicator overlay; static position.
 *   Quota Reserved         -> pallet engages the magnetic intake rail:
 *                             amber spinning beacons + gantry crane lock.
 *   Admitted               -> vivid green lighting; high-speed mag-rail
 *                             transit from the staging rail (X = -18) into
 *                             the tower intake bay (X = -8).
 *   Gang Deployment        -> the frame unlatches / dissolves and every
 *                             constituent pod bursts to its worker-deck
 *                             target simultaneously.
 *
 * All coordinate constants mirror src/ingestion/layout.py (single source of
 * truth on the Python side; SSE events carry explicit anchors so any drift
 * is visible).
 */

import * as THREE from 'three';

// ---------------------------------------------------------------------------
// Wire types (mirror of src/ingestion/models.py KueueWorkloadStatus)
// ---------------------------------------------------------------------------

export interface KueueWorkloadData {
  workload_uid: string;
  workload_name: string;
  namespace?: string;
  local_queue: string;
  cluster_queue: string;
  is_admitted?: boolean;
  admission_checks?: Array<Record<string, string>>;
  pod_uids?: string[];
  total_cpu_requested?: number;
  total_memory_gib_requested?: number;
  total_gpu_requested?: number;
  phase?: 'Inadmissible' | 'Admissible' | 'Admitted' | 'Finished';
}

/** Bounding volume of the containment frame (mirror of pack_kueue_workload). */
export interface KueuePalletVolume {
  anchor?: number[] | null;
  width?: number;
  height?: number;
  depth?: number;
  slots?: Record<string, number[]>;
}

/** HUD badge payload (mirror of layout.kueue_hud_summary). */
export interface KueueHudData {
  workload_name?: string;
  local_queue?: string;
  cluster_queue?: string;
  pod_count?: number;
  pod_count_label?: string;
  cpu?: number;
  memory_gib?: number;
  gpus?: number;
  phase?: string;
  is_admitted?: boolean;
  quota_deficit?: string | null;
}

/** SSE `kueue_workload_updated` payload (mirror of controller.py). */
export interface KueueWorkloadUpdatedPayload {
  workload: KueueWorkloadData;
  hud?: KueueHudData;
  pallet?: KueuePalletVolume;
  staging_focus_x?: number;
  timestamp?: string;
}

/** SSE `kueue_quota_deficit` payload. */
export interface KueueQuotaDeficitPayload {
  workload_uid: string;
  workload_name?: string;
  reason?: string;
  required?: { cpu?: number; memory_gib?: number; gpus?: number };
  anchor?: number[] | null;
  timestamp?: string;
}

/** SSE `kueue_quota_reserved` payload. */
export interface KueueQuotaReservedPayload {
  workload_uid: string;
  workload_name?: string;
  anchor?: number[] | null;
  lock_duration_ms?: number;
  timestamp?: string;
}

/** SSE `kueue_admission_admitted` payload. */
export interface KueueAdmissionAdmittedPayload {
  workload_uid: string;
  workload_name?: string;
  local_queue?: string;
  cluster_queue?: string;
  magrail?: { from?: number[]; to?: number[] };
  transit_duration_ms?: number;
  pod_uids?: string[];
  timestamp?: string;
}

/** SSE `kueue_gang_deployed` payload. */
export interface KueueGangDeployedPayload {
  workload_uid: string;
  workload_name?: string;
  pod_uids?: string[];
  targets?: number[][];
  burst_duration_ms?: number;
  timestamp?: string;
}

// ---------------------------------------------------------------------------
// Spatial constants (mirror of src/ingestion/layout.py)
// ---------------------------------------------------------------------------

export const KUEUE_PALLET_X_MIN = -21.0;
export const KUEUE_PALLET_X_MAX = -15.0;
export const KUEUE_PALLET_Y_MIN = 0.4;
export const KUEUE_PALLET_Y_MAX = 1.8;
export const KUEUE_PALLET_Z_MIN = -6.0;
export const KUEUE_PALLET_Z_MAX = 6.0;

export const KUEUE_PALLET_RAIL_X = -18.0;
export const KUEUE_PALLET_ROW_SPACING_Z = 5.6;
export const KUEUE_GRID_COLS = 4;
export const KUEUE_SLOT_SPACING_X = 1.3;
export const KUEUE_SLOT_SPACING_Z = 1.5;
export const KUEUE_SLOT_Y = 1.0;
export const KUEUE_FRAME_HEIGHT = KUEUE_PALLET_Y_MAX - KUEUE_PALLET_Y_MIN;
export const KUEUE_FRAME_MARGIN = 0.6;

export const MAGRAIL_INTAKE_X = -8.0;
export const MAGRAIL_INTAKE_Y = 1.2;
export const MAGRAIL_INTAKE_Z = 0.0;
export const MAGRAIL_TRANSIT_DURATION_MS = 2600;
export const GANG_DEPLOY_BURST_MS = 900;
export const KUEUE_RESERVE_LOCK_MS = 800;

/** Lifecycle states of a cargo pallet (SPEC-09 §5.3 rows). */
export type KueuePalletState =
  | 'queued'      // cold blue standby + quota deficit overlay
  | 'reserved'    // amber beacons spin, gantry cranes lock the frame
  | 'transit'     // vivid green, high-speed mag-rail glide into the tower
  | 'deploying'   // frame unlatching / dissolving, pods bursting out
  | 'deployed';   // frame gone, pods landed on the worker deck

/**
 * Bounding-frame dimensions for a gang of `podCount` pods — mirror of
 * `layout.kueue_pallet_dimensions`.
 */
export function kueuePalletDimensions(podCount: number): {
  width: number;
  height: number;
  depth: number;
} {
  const count = Math.max(Math.trunc(podCount), 1);
  const rows = Math.ceil(count / KUEUE_GRID_COLS);
  const cols = Math.min(KUEUE_GRID_COLS, count);
  const width = Math.min(
    KUEUE_PALLET_X_MAX - KUEUE_PALLET_X_MIN,
    Math.max(KUEUE_SLOT_SPACING_X + KUEUE_FRAME_MARGIN, cols * KUEUE_SLOT_SPACING_X + KUEUE_FRAME_MARGIN),
  );
  const depth = Math.min(
    KUEUE_PALLET_Z_MAX - KUEUE_PALLET_Z_MIN,
    Math.max(KUEUE_SLOT_SPACING_Z + KUEUE_FRAME_MARGIN, rows * KUEUE_SLOT_SPACING_Z + KUEUE_FRAME_MARGIN),
  );
  return { width, height: KUEUE_FRAME_HEIGHT, depth };
}

/** Rail dock anchor of the `index`-th pallet — mirror of the Python helper. */
export function kueuePalletAnchor(index: number): THREE.Vector3 {
  const z = Math.min(
    KUEUE_PALLET_Z_MAX,
    Math.max(KUEUE_PALLET_Z_MIN, KUEUE_PALLET_Z_MAX - 2.8 - index * KUEUE_PALLET_ROW_SPACING_Z),
  );
  return new THREE.Vector3(KUEUE_PALLET_RAIL_X, (KUEUE_PALLET_Y_MIN + KUEUE_PALLET_Y_MAX) / 2, z);
}

// ---------------------------------------------------------------------------
// Lighting palettes per lifecycle state
// ---------------------------------------------------------------------------

const STANDBY_COLD_BLUE = 0x4f8ff7;   // queued / inadmissible standby
const RESERVE_AMBER = 0xffb020;       // intake-rail engagement beacons
const ADMITTED_GREEN = 0x2eff9a;      // Admitted=true vivid green
const FRAME_STEEL = 0x6b7683;         // industrial cargo frame members
const DEFICIT_RED = 0xff4d4d;         // quota deficit indicator overlay

function frameColorFor(state: KueuePalletState): number {
  switch (state) {
    case 'queued':
      return STANDBY_COLD_BLUE;
    case 'reserved':
      return RESERVE_AMBER;
    case 'transit':
      return ADMITTED_GREEN;
    default:
      return FRAME_STEEL;
  }
}

// ---------------------------------------------------------------------------
// HUD badge (canvas sprite)
// ---------------------------------------------------------------------------

const HUD_CANVAS_W = 640;
const HUD_CANVAS_H = 256;
const HUD_SPRITE_W = 5.6;
const HUD_SPRITE_H = HUD_SPRITE_W * (HUD_CANVAS_H / HUD_CANVAS_W);

interface HudRenderInfo {
  workloadName: string;
  localQueue: string;
  clusterQueue: string;
  podCountLabel: string;
  quotaLine: string;
  phaseLine: string;
  deficit: string | null;
  state: KueuePalletState;
}

function drawHudBadge(canvas: HTMLCanvasElement, info: HudRenderInfo): void {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.clearRect(0, 0, HUD_CANVAS_W, HUD_CANVAS_H);

  const accent =
    info.state === 'queued'
      ? '#4f8ff7'
      : info.state === 'reserved'
        ? '#ffb020'
        : info.state === 'transit'
          ? '#2eff9a'
          : '#9aa7a5';

  // Translucent holo panel + accent border.
  ctx.fillStyle = 'rgba(6, 14, 16, 0.78)';
  ctx.fillRect(6, 6, HUD_CANVAS_W - 12, HUD_CANVAS_H - 12);
  ctx.strokeStyle = accent;
  ctx.lineWidth = 3;
  ctx.strokeRect(6, 6, HUD_CANVAS_W - 12, HUD_CANVAS_H - 12);
  // Corner brackets.
  ctx.lineWidth = 5;
  const cLen = 26;
  for (const [cx, cy, dx, dy] of [
    [6, 6, 1, 1],
    [HUD_CANVAS_W - 6, 6, -1, 1],
    [6, HUD_CANVAS_H - 6, 1, -1],
    [HUD_CANVAS_W - 6, HUD_CANVAS_H - 6, -1, -1],
  ] as Array<[number, number, number, number]>) {
    ctx.beginPath();
    ctx.moveTo(cx, cy + dy * cLen);
    ctx.lineTo(cx, cy);
    ctx.lineTo(cx + dx * cLen, cy);
    ctx.stroke();
  }

  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillStyle = accent;
  ctx.font = 'bold 30px monospace';
  ctx.fillText(`KUEUE WORKLOAD FRAME: ${info.workloadName}`, 24, 20);

  ctx.fillStyle = '#c9d6d5';
  ctx.font = '24px monospace';
  ctx.fillText(`Queue: ${info.localQueue}  |  CQ: ${info.clusterQueue}`, 24, 62);
  ctx.fillText(`${info.podCountLabel}   ${info.phaseLine}`, 24, 96);
  ctx.fillStyle = '#8fd3ff';
  ctx.fillText(`Quota: ${info.quotaLine}`, 24, 130);

  if (info.deficit) {
    ctx.fillStyle = '#ff6b6b';
    ctx.font = 'bold 22px monospace';
    const reason =
      info.deficit.length > 44 ? `${info.deficit.slice(0, 43)}…` : info.deficit;
    ctx.fillText(`⚠ QUOTA DEFICIT: ${reason}`, 24, 168);
  } else if (info.state === 'reserved') {
    ctx.fillStyle = '#ffb020';
    ctx.font = 'bold 22px monospace';
    ctx.fillText('⚓ INTAKE RAIL ENGAGED — GANTRY LOCK', 24, 168);
  } else if (info.state === 'transit') {
    ctx.fillStyle = '#2eff9a';
    ctx.font = 'bold 22px monospace';
    ctx.fillText('▶ HIGH-SPEED MAG-RAIL TRANSIT', 24, 168);
  }
}

// ---------------------------------------------------------------------------
// Industrial cargo containment frame
// ---------------------------------------------------------------------------

interface FrameParts {
  group: THREE.Group;
  postMats: THREE.MeshStandardMaterial[];
  beamMats: THREE.MeshStandardMaterial[];
  panelMat: THREE.MeshBasicMaterial;
}

function buildCargoFrame(width: number, height: number, depth: number): FrameParts {
  const group = new THREE.Group();
  group.name = 'kueue_cargo_frame';
  const postMats: THREE.MeshStandardMaterial[] = [];
  const beamMats: THREE.MeshStandardMaterial[] = [];

  const makeSteelMat = (): THREE.MeshStandardMaterial =>
    new THREE.MeshStandardMaterial({
      color: FRAME_STEEL,
      roughness: 0.42,
      metalness: 0.85,
      emissive: STANDBY_COLD_BLUE,
      emissiveIntensity: 0.35,
    });

  const postGeo = new THREE.BoxGeometry(0.16, height, 0.16);
  const beamXGeo = new THREE.BoxGeometry(width, 0.12, 0.12);
  const beamZGeo = new THREE.BoxGeometry(0.12, 0.12, depth);
  const w2 = width / 2;
  const d2 = depth / 2;

  // Four corner posts.
  const postPositions: Array<[number, number]> = [
    [-w2, -d2],
    [w2, -d2],
    [-w2, d2],
    [w2, d2],
  ];
  for (const [px, pz] of postPositions) {
    const postMat = makeSteelMat();
    postMats.push(postMat);
    const post = new THREE.Mesh(postGeo, postMat);
    post.position.set(px, 0, pz);
    group.add(post);
  }
  // Top + bottom rails along X and Z.
  for (const ry of [-height / 2 + 0.06, height / 2 - 0.06]) {
    for (const rz of [-d2, d2]) {
      const mat = makeSteelMat();
      beamMats.push(mat);
      const beam = new THREE.Mesh(beamXGeo, mat);
      beam.position.set(0, ry, rz);
      group.add(beam);
    }
    for (const rx of [-w2, w2]) {
      const mat = makeSteelMat();
      beamMats.push(mat);
      const beam = new THREE.Mesh(beamZGeo, mat);
      beam.position.set(rx, ry, 0);
      group.add(beam);
    }
  }
  // Skid skids under the pallet floor (freight-handling detail).
  const skidGeo = new THREE.BoxGeometry(width + 0.3, 0.1, 0.22);
  for (const sz of [-d2 + 0.15, d2 - 0.15]) {
    const mat = makeSteelMat();
    beamMats.push(mat);
    const skid = new THREE.Mesh(skidGeo, mat);
    skid.position.set(0, -height / 2 - 0.04, sz);
    group.add(skid);
  }

  // Translucent containment membrane sealing the frame around the gang.
  const panelMat = new THREE.MeshBasicMaterial({
    color: STANDBY_COLD_BLUE,
    transparent: true,
    opacity: 0.1,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const membrane = new THREE.Mesh(new THREE.BoxGeometry(width - 0.05, height - 0.05, depth - 0.05), panelMat);
  group.add(membrane);

  return { group, postMats, beamMats, panelMat };
}

interface Beacon {
  mesh: THREE.Mesh;
  mat: THREE.MeshBasicMaterial;
  light: THREE.PointLight;
  phase: number;
}

function buildBeacon(position: THREE.Vector3): Beacon {
  const mat = new THREE.MeshBasicMaterial({
    color: RESERVE_AMBER,
    transparent: true,
    opacity: 0.0,
  });
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(0.12, 12, 10), mat);
  mesh.position.copy(position);
  const light = new THREE.PointLight(RESERVE_AMBER, 0, 4.5);
  light.position.copy(position);
  return { mesh, mat, light, phase: Math.random() * Math.PI * 2 };
}

interface GantryRig {
  group: THREE.Group;
  bridgeMat: THREE.MeshStandardMaterial;
  clawMats: THREE.MeshStandardMaterial[];
  claws: THREE.Mesh[];
  width: number;
  depth: number;
}

/** Overhead overhead gantry crane that locks onto the cargo frame. */
function buildGantryRig(width: number, height: number, depth: number): GantryRig {
  const group = new THREE.Group();
  group.name = 'kueue_gantry_crane';
  group.visible = false;

  const bridgeMat = new THREE.MeshStandardMaterial({
    color: 0x8a9490,
    roughness: 0.35,
    metalness: 0.9,
    emissive: RESERVE_AMBER,
    emissiveIntensity: 0.45,
  });
  const bridge = new THREE.Mesh(new THREE.BoxGeometry(width + 1.0, 0.18, 0.3), bridgeMat);
  bridge.position.set(0, height / 2 + 0.7, 0);
  group.add(bridge);

  const clawMats: THREE.MeshStandardMaterial[] = [];
  const claws: THREE.Mesh[] = [];
  const clawGeo = new THREE.BoxGeometry(0.28, 0.5, 0.28);
  const clawPositions: Array<[number, number]> = [
    [-width / 2, -depth / 2],
    [width / 2, -depth / 2],
    [-width / 2, depth / 2],
    [width / 2, depth / 2],
  ];
  for (const [cx, cz] of clawPositions) {
    const mat = new THREE.MeshStandardMaterial({
      color: 0xb0b8b4,
      roughness: 0.3,
      metalness: 0.9,
      emissive: RESERVE_AMBER,
      emissiveIntensity: 0.7,
    });
    clawMats.push(mat);
    const claw = new THREE.Mesh(clawGeo, mat);
    claw.position.set(cx, height / 2 + 0.4, cz);
    group.add(claw);
    claws.push(claw);
  }
  return { group, bridgeMat, clawMats, claws, width, depth };
}

// ---------------------------------------------------------------------------
// Internal pallet record
// ---------------------------------------------------------------------------

interface PalletRecord {
  workload: KueueWorkloadData;
  hud: KueueHudData;
  state: KueuePalletState;
  anchor: THREE.Vector3;
  group: THREE.Group;
  frame: FrameParts;
  hudSprite: THREE.Sprite;
  hudCanvas: HTMLCanvasElement;
  hudMat: THREE.SpriteMaterial;
  beacons: Beacon[];
  gantry: GantryRig;
  deficitCage: THREE.LineSegments;
  /** Member pod objects registered by the viewport for the deploy burst. */
  members: THREE.Object3D[];
  /** Transit tween: from -> to anchor positions (world space). */
  transit: {
    elapsed: number;
    duration: number;
    from: THREE.Vector3;
    to: THREE.Vector3;
    onDone?: () => void;
  } | null;
  deployTween: {
    elapsed: number;
    duration: number;
  } | null;
  pendingDeployment: KueueGangDeployedPayload | null;
  demoSynthetic: boolean;
}

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function easeOutBack(t: number): number {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
}

// ---------------------------------------------------------------------------
// Manager
// ---------------------------------------------------------------------------

/**
 * Kueue cargo pallet scene manager. The viewport builds it, feeds it
 * snapshot `kueue_workloads` + the Kueue lifecycle SSE events, registers the
 * constituent pod meshes, and calls `update(delta, time)` from the render
 * loop for standby pulses, spinning beacons, gantry lock, mag-rail transit
 * tweens, and the gang-deployment burst.
 */
export class KueuePalletManager {
  private readonly scene: THREE.Scene;
  private readonly root = new THREE.Group();
  private readonly pallets = new Map<string, PalletRecord>();
  /** pod uid -> workload uid routing table for member lookups. */
  private readonly podRoutes = new Map<string, string>();
  /** Pod objects awaiting registration (arrived before the workload). */
  private readonly lateMembers = new Map<string, THREE.Object3D>();

  constructor(scene: THREE.Scene) {
    this.scene = scene;
    this.root.name = 'kueue_cargo_pallets';
    scene.add(this.root);
  }

  public palletCount(): number {
    return this.pallets.size;
  }

  public stateOf(workloadUid: string): KueuePalletState | null {
    return this.pallets.get(workloadUid)?.state ?? null;
  }

  /** True while any pallet is mid-transit or mid-deployment. */
  public isAnimating(): boolean {
    for (const p of this.pallets.values()) {
      if (p.state === 'transit' || p.state === 'deploying') return true;
    }
    return false;
  }

  // -- Construction -----------------------------------------------------------

  private buildPallet(
    workload: KueueWorkloadData,
    hud: KueueHudData,
    anchor: THREE.Vector3,
    volume?: KueuePalletVolume,
    demoSynthetic = false,
  ): PalletRecord {
    const podCount = Math.max(workload.pod_uids?.length ?? 1, 1);
    const dims = kueuePalletDimensions(podCount);
    const width = volume?.width && volume.width > 0 ? volume.width : dims.width;
    const height = volume?.height && volume.height > 0 ? volume.height : dims.height;
    const depth = volume?.depth && volume.depth > 0 ? volume.depth : dims.depth;

    const group = new THREE.Group();
    group.name = `kueue_pallet_${workload.workload_name}`;
    group.position.copy(anchor);

    const frame = buildCargoFrame(width, height, depth);
    group.add(frame.group);

    // HUD badge sprite floating above the containment frame.
    const hudCanvas = document.createElement('canvas');
    hudCanvas.width = HUD_CANVAS_W;
    hudCanvas.height = HUD_CANVAS_H;
    const hudMat = new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(hudCanvas),
      transparent: true,
      depthWrite: false,
    });
    const hudSprite = new THREE.Sprite(hudMat);
    hudSprite.scale.set(HUD_SPRITE_W, HUD_SPRITE_H, 1);
    hudSprite.position.set(0, height / 2 + HUD_SPRITE_H / 2 + 0.35, 0);
    group.add(hudSprite);

    // Spinning amber intake beacons on the two rail-side top corners.
    const beacons = [
      buildBeacon(new THREE.Vector3(-width / 2, height / 2 + 0.16, -depth / 2)),
      buildBeacon(new THREE.Vector3(width / 2, height / 2 + 0.16, -depth / 2)),
    ];
    for (const b of beacons) {
      group.add(b.mesh);
      group.add(b.light);
    }

    const gantry = buildGantryRig(width, height, depth);
    group.add(gantry.group);

    // Quota-deficit indicator overlay cage (visible while inadmissible).
    const deficitCage = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(width + 0.25, height + 0.25, depth + 0.25)),
      new THREE.LineBasicMaterial({ color: DEFICIT_RED, transparent: true, opacity: 0 }),
    );
    group.add(deficitCage);

    const record: PalletRecord = {
      workload: { ...workload },
      hud: { ...hud },
      state: 'queued',
      anchor: anchor.clone(),
      group,
      frame,
      hudSprite,
      hudCanvas,
      hudMat,
      beacons,
      gantry,
      deficitCage,
      members: [],
      transit: null,
      deployTween: null,
      pendingDeployment: null,
      demoSynthetic,
    };

    this.pallets.set(workload.workload_uid, record);
    for (const uid of workload.pod_uids ?? []) {
      this.podRoutes.set(uid, workload.workload_uid);
      const late = this.lateMembers.get(uid);
      if (late) {
        record.members.push(late);
        this.lateMembers.delete(uid);
      }
    }
    this.applyStateLighting(record);
    this.renderHud(record);
    this.root.add(group);
    return record;
  }

  /** Resolve the rail dock index for a workload name (sorted, Python parity). */
  private dockIndexFor(workloadName: string): number {
    const names = [...this.pallets.values()]
      .filter((p) => !p.demoSynthetic || p.workload.workload_name !== workloadName)
      .map((p) => p.workload.workload_name)
      .sort();
    const idx = names.indexOf(workloadName);
    return idx >= 0 ? idx : names.length;
  }

  // -- Snapshot + event application -------------------------------------------

  /** Rebuild all pallets from a snapshot's `kueue_workloads` list. */
  public applySnapshot(workloads: KueueWorkloadData[] | undefined): void {
    this.clearAll();
    if (!workloads || workloads.length === 0) return;
    const ordered = [...workloads].sort((a, b) =>
      (a.workload_name ?? '').localeCompare(b.workload_name ?? ''),
    );
    ordered.forEach((workload, index) => {
      const anchor = kueuePalletAnchor(index);
      const record = this.buildPallet(workload, this.hudFromWorkload(workload), anchor);
      this.settleStateForWorkload(record);
    });
    // Re-attach pods whose meshes were registered before this snapshot.
    for (const [uid, object] of [...this.lateMembers.entries()]) {
      const target = this.findPalletByPodName(object);
      if (target) {
        target.members.push(object);
        this.podRoutes.set(uid, target.workload.workload_uid);
        this.lateMembers.delete(uid);
      }
    }
  }

  /** SSE `kueue_workload_updated`: create or refresh a cargo pallet. */
  public applyWorkloadUpdated(payload: KueueWorkloadUpdatedPayload): void {
    const workload = payload.workload;
    if (!workload || !workload.workload_uid) return;
    const hud = payload.hud ?? this.hudFromWorkload(workload);
    let record = this.pallets.get(workload.workload_uid);
    if (!record) {
      const anchor =
        payload.pallet?.anchor && payload.pallet.anchor.length === 3
          ? new THREE.Vector3(
              payload.pallet.anchor[0] ?? KUEUE_PALLET_RAIL_X,
              payload.pallet.anchor[1] ?? (KUEUE_PALLET_Y_MIN + KUEUE_PALLET_Y_MAX) / 2,
              payload.pallet.anchor[2] ?? 0,
            )
          : kueuePalletAnchor(this.dockIndexFor(workload.workload_name));
      record = this.buildPallet(workload, hud, anchor, payload.pallet);
    } else {
      record.workload = { ...workload };
      record.hud = { ...hud };
      for (const uid of workload.pod_uids ?? []) {
        this.podRoutes.set(uid, workload.workload_uid);
        const late = this.lateMembers.get(uid);
        if (late) {
          record.members.push(late);
          this.lateMembers.delete(uid);
        }
      }
    }
    // Don't regress an in-flight animation back to standby on refresh.
    if (record.state !== 'transit' && record.state !== 'deploying') {
      this.settleStateForWorkload(record);
    }
    this.renderHud(record);
  }

  /** SSE `kueue_quota_deficit`: cold-blue standby + deficit overlay. */
  public applyQuotaDeficit(payload: KueueQuotaDeficitPayload): void {
    const record = this.pallets.get(payload.workload_uid);
    if (!record) return;
    record.hud.quota_deficit = payload.reason ?? 'QuotaExceeded';
    if (record.state !== 'transit' && record.state !== 'deploying') {
      record.state = 'queued';
    }
    this.applyStateLighting(record);
    this.renderHud(record);
  }

  /** SSE `kueue_quota_reserved`: engage intake rail, spin beacons, gantry lock. */
  public applyQuotaReserved(payload: KueueQuotaReservedPayload): void {
    const record = this.pallets.get(payload.workload_uid);
    if (!record || record.state === 'transit' || record.state === 'deploying') return;
    record.state = 'reserved';
    this.applyStateLighting(record);
    this.renderHud(record);
  }

  /** SSE `kueue_admission_admitted`: high-speed mag-rail transit. */
  public applyAdmissionAdmitted(payload: KueueAdmissionAdmittedPayload): void {
    const record = this.pallets.get(payload.workload_uid);
    if (!record || record.state === 'transit' || record.state === 'deploying') return;
    const from =
      payload.magrail?.from && payload.magrail.from.length === 3
        ? new THREE.Vector3(
            payload.magrail.from[0] ?? record.anchor.x,
            payload.magrail.from[1] ?? record.anchor.y,
            payload.magrail.from[2] ?? record.anchor.z,
          )
        : record.anchor.clone();
    const to =
      payload.magrail?.to && payload.magrail.to.length === 3
        ? new THREE.Vector3(
            payload.magrail.to[0] ?? MAGRAIL_INTAKE_X,
            payload.magrail.to[1] ?? MAGRAIL_INTAKE_Y,
            payload.magrail.to[2] ?? MAGRAIL_INTAKE_Z,
          )
        : new THREE.Vector3(MAGRAIL_INTAKE_X, MAGRAIL_INTAKE_Y, MAGRAIL_INTAKE_Z);

    record.state = 'transit';
    record.workload.is_admitted = true;
    record.workload.phase = 'Admitted';
    record.hud.is_admitted = true;
    record.hud.phase = 'Admitted';
    record.hud.quota_deficit = null;
    record.transit = {
      elapsed: 0,
      duration: Math.max(0.2, (payload.transit_duration_ms ?? MAGRAIL_TRANSIT_DURATION_MS) / 1000),
      from,
      to,
    };
    // Snap the frame to the transit start anchor first (may hop from the
    // dock dock to the rail centerline).
    const hop = from.clone().sub(record.group.position);
    this.translatePallet(record, hop);
    this.applyStateLighting(record);
    this.renderHud(record);
  }

  /** SSE `kueue_gang_deployed`: frame unlatch/dissolve + simultaneous burst. */
  public applyGangDeployed(payload: KueueGangDeployedPayload): void {
    const record = this.pallets.get(payload.workload_uid);
    if (!record) return;
    const startBurst = (): void => {
      const targets: THREE.Vector3[] = (payload.targets ?? [])
        .filter((t) => Array.isArray(t) && t.length === 3)
        .map((t) => new THREE.Vector3(t[0] ?? 0, t[1] ?? 0.75, t[2] ?? 0));
      record.pendingDeployment = { ...payload, targets: undefined };
      record.state = 'deploying';
      record.deployTween = {
        elapsed: 0,
        duration: Math.max(0.2, (payload.burst_duration_ms ?? GANG_DEPLOY_BURST_MS) / 1000),
      };
      // Stash per-member burst destinations (fall back to a spread fan).
      record.members.forEach((obj, i) => {
        const target =
          targets[i] ??
          new THREE.Vector3(
            -9.6 + (record.members.length > 1 ? (19.2 * i) / (record.members.length - 1) : 0),
            0.75,
            i % 2 === 0 ? 0.2 : 1.2,
          );
        obj.userData.kueueDeployFrom = obj.position.clone();
        obj.userData.kueueDeployTo = target;
      });
      this.applyStateLighting(record);
    };
    if (record.transit) {
      // Queue the burst to fire the moment the transit lands.
      const previousDone = record.transit.onDone;
      record.transit.onDone = () => {
        previousDone?.();
        startBurst();
      };
    } else {
      startBurst();
    }
  }

  /**
   * Simulated Gang Admission trigger (SPEC-09 §7.3, testbed/demo mode).
   * Admits the first queued pallet; when no live workload exists (static
   * offline mode), synthesizes a demo gang, runs the full reserved ->
   * admitted -> deployed lifecycle, and cleans it up afterwards.
   */
  public simulateGangAdmission(): boolean {
    for (const record of this.pallets.values()) {
      if (record.state === 'queued' || record.state === 'reserved') {
        record.state = 'reserved';
        this.applyStateLighting(record);
        this.renderHud(record);
        const uid = record.workload.workload_uid;
        window.setTimeout(() => {
          this.applyAdmissionAdmitted({
            workload_uid: uid,
            workload_name: record.workload.workload_name,
            transit_duration_ms: MAGRAIL_TRANSIT_DURATION_MS,
          });
        }, 1200);
        window.setTimeout(() => {
          this.applyGangDeployed({
            workload_uid: uid,
            workload_name: record.workload.workload_name,
            pod_uids: record.workload.pod_uids ?? [],
            burst_duration_ms: GANG_DEPLOY_BURST_MS,
          });
        }, 1200 + MAGRAIL_TRANSIT_DURATION_MS + 300);
        return true;
      }
    }
    return this.simulateSyntheticDemoGang();
  }

  /** Build a synthetic demo pallet + gang pods and run the full lifecycle. */
  private simulateSyntheticDemoGang(): boolean {
    const uid = `demo-kueue-${Date.now().toString(36)}`;
    const workload: KueueWorkloadData = {
      workload_uid: uid,
      workload_name: 'demo-gang-admission',
      namespace: 'batch-ai',
      local_queue: 'batch-ai',
      cluster_queue: 'cluster-ml-bq',
      is_admitted: false,
      phase: 'Inadmissible',
      pod_uids: [0, 1, 2, 2 + 1].slice(0, 4).map((n) => `${uid}-pod-${n}`),
      total_cpu_requested: 64,
      total_memory_gib_requested: 256,
      total_gpu_requested: 8,
    };
    const anchor = kueuePalletAnchor(0);
    const record = this.buildPallet(
      workload,
      {
        workload_name: workload.workload_name,
        local_queue: workload.local_queue,
        cluster_queue: workload.cluster_queue,
        pod_count: 4,
        pod_count_label: '4/4 Pods',
        cpu: 64,
        memory_gib: 256,
        gpus: 8,
        phase: 'Inadmissible',
        is_admitted: false,
        quota_deficit: 'QuotaExceeded: simulated admission trigger',
      },
      anchor,
      undefined,
      true,
    );
    // Synthetic capsules inside the frame slots (mirrors pack_kueue_workload).
    record.members = [];
    const rows = Math.ceil(4 / KUEUE_GRID_COLS);
    for (let i = 0; i < 4; i++) {
      const col = i % KUEUE_GRID_COLS;
      const row = Math.floor(i / KUEUE_GRID_COLS);
      const colsInRow = Math.min(KUEUE_GRID_COLS, 4 - row * KUEUE_GRID_COLS);
      const x = anchor.x + (col - (colsInRow - 1) / 2) * KUEUE_SLOT_SPACING_X;
      const z = anchor.z + (row - (rows - 1) / 2) * KUEUE_SLOT_SPACING_Z;
      const capsule = new THREE.Mesh(
        new THREE.CapsuleGeometry(0.3, 0.4, 16, 16),
        new THREE.MeshStandardMaterial({
          color: 0x4fc3f7,
          emissive: 0x1a7fc4,
          emissiveIntensity: 0.5,
          roughness: 0.35,
          metalness: 0.25,
        }),
      );
      capsule.position.set(x, KUEUE_SLOT_Y, z);
      this.scene.add(capsule);
      record.members.push(capsule);
    }
    this.applyQuotaReserved({ workload_uid: uid, lock_duration_ms: KUEUE_RESERVE_LOCK_MS });
    window.setTimeout(() => {
      this.applyAdmissionAdmitted({
        workload_uid: uid,
        workload_name: workload.workload_name,
        transit_duration_ms: MAGRAIL_TRANSIT_DURATION_MS,
      });
    }, 1400);
    window.setTimeout(() => {
      this.applyGangDeployed({
        workload_uid: uid,
        workload_name: workload.workload_name,
        pod_uids: workload.pod_uids,
        burst_duration_ms: GANG_DEPLOY_BURST_MS,
      });
    }, 1400 + MAGRAIL_TRANSIT_DURATION_MS + 350);
    // Clean up the synthetic demo ~4s after the burst lands.
    window.setTimeout(() => {
      this.removePallet(uid, true);
    }, 1400 + MAGRAIL_TRANSIT_DURATION_MS + GANG_DEPLOY_BURST_MS + 4000);
    return true;
  }

  // -- Member pod registration -------------------------------------------------

  /** Register a constituent pod mesh for its workload's deploy burst. */
  public registerGangPod(podUid: string, object: THREE.Object3D): void {
    const workloadUid = this.podRoutes.get(podUid);
    if (!workloadUid) {
      this.lateMembers.set(podUid, object);
      return;
    }
    const record = this.pallets.get(workloadUid);
    if (!record) {
      this.lateMembers.set(podUid, object);
      return;
    }
    if (!record.members.includes(object)) record.members.push(object);
  }

  /** Drop hover/deploy bookkeeping for a removed pod. */
  public removePod(podUid: string): void {
    this.lateMembers.delete(podUid);
    const workloadUid = this.podRoutes.get(podUid);
    if (!workloadUid) return;
    const record = this.pallets.get(workloadUid);
    if (!record) return;
    record.members = record.members.filter((obj) => {
      const data = obj.userData.nodeData as { id?: string } | undefined;
      return data?.id !== podUid;
    });
  }

  /** Find which pallet a pod object belongs to via its nodeData name prefix. */
  private findPalletByPodName(object: THREE.Object3D): PalletRecord | null {
    const data = object.userData.nodeData as
      | { id?: string; pod_geometry?: { kueue_workload?: string } }
      | undefined;
    if (!data?.id) return null;
    const uid = this.podRoutes.get(data.id);
    return uid ? this.pallets.get(uid) ?? null : null;
  }

  /** True if the pod uid belongs to any known Kueue workload. */
  public isKueuePod(podUid: string): boolean {
    return this.podRoutes.has(podUid);
  }

  // -- State / lighting ----------------------------------------------------------

  private settleStateForWorkload(record: PalletRecord): void {
    const w = record.workload;
    if (w.is_admitted || w.phase === 'Admitted') {
      record.state = 'deployed';
      record.group.visible = false; // landed: pods belong to the worker deck
      return;
    }
    const deficit = record.hud.quota_deficit ?? quotaDeficitFromChecks(w);
    if (deficit) {
      record.hud.quota_deficit = deficit;
      record.state = 'queued';
    } else {
      record.state = 'queued';
    }
    record.group.visible = true;
    this.applyStateLighting(record);
  }

  private applyStateLighting(record: PalletRecord): void {
    const color = frameColorFor(record.state);
    const steelEmissive =
      record.state === 'queued'
        ? STANDBY_COLD_BLUE
        : record.state === 'reserved'
          ? RESERVE_AMBER
          : record.state === 'transit'
            ? ADMITTED_GREEN
            : FRAME_STEEL;
    const intensity = record.state === 'queued' ? 0.35 : record.state === 'reserved' ? 0.6 : 0.75;
    for (const mat of record.frame.postMats) {
      mat.emissive.setHex(steelEmissive);
      mat.emissiveIntensity = intensity;
    }
    for (const mat of record.frame.beamMats) {
      mat.emissive.setHex(steelEmissive);
      mat.emissiveIntensity = intensity * 0.8;
    }
    record.frame.panelMat.color.setHex(color);
    record.frame.panelMat.opacity = record.state === 'transit' ? 0.16 : 0.1;
    record.gantry.group.visible = record.state === 'reserved' || record.state === 'transit';
    record.deficitCage.visible = record.state === 'queued' && record.hud.quota_deficit != null;
  }

  private hudFromWorkload(workload: KueueWorkloadData): KueueHudData {
    const count = workload.pod_uids?.length ?? 0;
    return {
      workload_name: workload.workload_name,
      local_queue: workload.local_queue,
      cluster_queue: workload.cluster_queue,
      pod_count: count,
      pod_count_label: `${count}/${count} Pods`,
      cpu: workload.total_cpu_requested ?? 0,
      memory_gib: workload.total_memory_gib_requested ?? 0,
      gpus: workload.total_gpu_requested ?? 0,
      phase: workload.phase ?? 'Admissible',
      is_admitted: workload.is_admitted === true,
      quota_deficit: quotaDeficitFromChecks(workload),
    };
  }

  private renderHud(record: PalletRecord): void {
    const hud = record.hud;
    const cpu = hud.cpu ?? 0;
    const mem = hud.memory_gib ?? 0;
    const gpus = hud.gpus ?? 0;
    drawHudBadge(record.hudCanvas, {
      workloadName: hud.workload_name ?? record.workload.workload_name,
      localQueue: hud.local_queue ?? record.workload.local_queue,
      clusterQueue: hud.cluster_queue ?? record.workload.cluster_queue,
      podCountLabel: hud.pod_count_label ?? `${hud.pod_count ?? 0}/${hud.pod_count ?? 0} Pods`,
      quotaLine: `${Number.isInteger(cpu) ? cpu : cpu.toFixed(1)} vCPU | ${
        Number.isInteger(mem) ? mem : mem.toFixed(1)
      } GiB RAM | ${gpus}x GPU`,
      phaseLine: hud.is_admitted || hud.phase === 'Admitted' ? 'ADMITTED' : `Phase: ${(hud.phase ?? 'Admissible').toUpperCase()}`,
      deficit: hud.quota_deficit ?? null,
      state: record.state,
    });
    if (record.hudMat.map) record.hudMat.map.needsUpdate = true;
  }

  // -- Motion bookkeeping ---------------------------------------------------------

  private translatePallet(record: PalletRecord, delta: THREE.Vector3): void {
    if (delta.lengthSq() === 0) return;
    record.group.position.add(delta);
    record.anchor.copy(record.group.position);
    for (const member of record.members) {
      member.position.add(delta);
    }
  }

  // -- Frame update -----------------------------------------------------------------

  public update(delta: number, time: number): void {
    for (const record of [...this.pallets.values()]) {
      // Cold-blue standby breathing + deficit flicker.
      if (record.state === 'queued') {
        const breathe = 0.28 + 0.14 * (0.5 + 0.5 * Math.sin(time * 1.8));
        for (const mat of record.frame.postMats) mat.emissiveIntensity = breathe;
        const cageMat = record.deficitCage.material as THREE.LineBasicMaterial;
        record.deficitCage.visible = record.hud.quota_deficit != null;
        cageMat.opacity = Math.sin(time * 6) > 0 ? 0.85 : 0.25;
        for (const beacon of record.beacons) {
          beacon.mat.opacity = 0;
          beacon.light.intensity = 0;
        }
      }

      // Reserved: amber spinning beacons + gantry crane descending lock.
      if (record.state === 'reserved') {
        const flash = Math.sin(time * 9) > 0 ? 0.95 : 0.15;
        for (const beacon of record.beacons) {
          beacon.mat.opacity = flash;
          beacon.light.intensity = flash * 2.6;
          beacon.mesh.rotation.y = time * 7 + beacon.phase;
          beacon.mesh.position.x += Math.sin(time * 7 + beacon.phase) * 0.0004;
        }
        const dip = 0.06 * (0.5 + 0.5 * Math.sin(time * 2.4));
        record.gantry.claws.forEach((claw, i) => {
          claw.position.y = record.frame.group.position.y + KUEUE_FRAME_HEIGHT / 2 + 0.28 - dip;
          const mat = record.gantry.clawMats[i];
          if (mat) mat.emissiveIntensity = 0.5 + 0.5 * Math.sin(time * 5 + i);
        });
      } else if (record.state !== 'transit') {
        for (const beacon of record.beacons) {
          beacon.mat.opacity = 0;
          beacon.light.intensity = 0;
        }
      }

      // High-speed mag-rail transit tween (frame + members glide together).
      if (record.transit) {
        const tw = record.transit;
        tw.elapsed += delta;
        const t = clamp01(tw.elapsed / tw.duration);
        const eased = easeInOutCubic(t);
        const target = tw.from.clone().lerp(tw.to, eased);
        const deltaMove = target.clone().sub(record.group.position);
        this.translatePallet(record, deltaMove);
        // Green standby beacons ride along as transit running lights.
        const beaconFlash = Math.sin(time * 14) > 0 ? 0.9 : 0.3;
        for (const beacon of record.beacons) {
          beacon.mat.color.setHex(ADMITTED_GREEN);
          beacon.mat.opacity = beaconFlash;
          beacon.light.color.setHex(ADMITTED_GREEN);
          beacon.light.intensity = beaconFlash * 1.6;
        }
        const dip = 0.04 * (0.5 + 0.5 * Math.sin(time * 6));
        record.gantry.claws.forEach((claw) => {
          claw.position.y = KUEUE_FRAME_HEIGHT / 2 + 0.22 - dip;
        });
        if (t >= 1) {
          record.transit = null;
          tw.onDone?.();
          if (record.state === 'transit' && !record.pendingDeployment) {
            // Arrived at the intake bay, awaiting the gang-deploy event.
            record.state = 'transit';
          }
        }
      }

      // Gang deployment: frame unlatch/dissolve + simultaneous pod burst.
      if (record.deployTween) {
        const tw = record.deployTween;
        tw.elapsed += delta;
        const t = clamp01(tw.elapsed / tw.duration);

        // Pods burst outward with an overshoot ease; frame dissolves.
        for (const member of record.members) {
          const from = member.userData.kueueDeployFrom as THREE.Vector3 | undefined;
          const to = member.userData.kueueDeployTo as THREE.Vector3 | undefined;
          if (!from || !to) continue;
          const eased = easeOutBack(t);
          member.position.lerpVectors(from, to, Math.min(1.15, eased));
        }
        const dissolve = 1 - t;
        record.frame.panelMat.opacity = 0.1 * dissolve;
        for (const mat of record.frame.postMats) {
          mat.transparent = true;
          mat.opacity = dissolve;
        }
        for (const mat of record.frame.beamMats) {
          mat.transparent = true;
          mat.opacity = dissolve;
        }
        record.hudMat.opacity = dissolve;
        record.gantry.group.visible = t < 0.5;

        if (t >= 1) {
          record.deployTween = null;
          record.state = 'deployed';
          record.group.visible = false;
          if (record.demoSynthetic) {
            // Synthetic pods stay on the deck briefly, then fade with the
            // pallet cleanup timer.
            for (const member of record.members) {
              const mesh = member as THREE.Mesh;
              const mat = mesh.material as THREE.MeshStandardMaterial;
              if (mat && mat.isMeshStandardMaterial) {
                mat.emissive.setHex(ADMITTED_GREEN);
                mat.emissiveIntensity = 0.9;
              }
            }
          } else {
            // Real pods: hand ownership back to the deck (clear burst tags).
            for (const member of record.members) {
              delete member.userData.kueueDeployFrom;
              delete member.userData.kueueDeployTo;
              const data = member.userData.nodeData as
                | { pod_geometry?: { is_pending?: boolean } }
                | undefined;
              if (data?.pod_geometry) data.pod_geometry.is_pending = false;
            }
            record.members.length = 0;
          }
        }
      }
    }
  }

  // -- Teardown ---------------------------------------------------------------------

  private removePallet(workloadUid: string, alsoMembers = false): void {
    const record = this.pallets.get(workloadUid);
    if (!record) return;
    this.root.remove(record.group);
    disposeObject(record.group);
    record.hudMat.map?.dispose();
    for (const uid of record.workload.pod_uids ?? []) this.podRoutes.delete(uid);
    if (alsoMembers) {
      for (const member of record.members) {
        this.scene.remove(member);
        disposeObject(member);
      }
    }
    record.members.length = 0;
    this.pallets.delete(workloadUid);
  }

  public clearAll(): void {
    for (const uid of [...this.pallets.keys()]) {
      const record = this.pallets.get(uid);
      if (record?.demoSynthetic) {
        this.removePallet(uid, true);
      } else {
        this.removePallet(uid, false);
      }
    }
    this.podRoutes.clear();
  }

  public dispose(): void {
    this.clearAll();
    this.scene.remove(this.root);
  }
}

/** Mirror of layout.quota_deficit_reason for the client wire model. */
export function quotaDeficitFromChecks(workload: KueueWorkloadData): string | null {
  const checks = workload.admission_checks ?? [];
  for (const check of checks) {
    const type = String(check['type'] ?? '').toLowerCase();
    const status = String(check['status'] ?? '').toLowerCase();
    if ((status === 'false' || status === 'failed') && type.includes('quota')) {
      return String(check['reason'] ?? 'QuotaExceeded');
    }
  }
  for (const check of checks) {
    const status = String(check['status'] ?? '').toLowerCase();
    if (status === 'false' || status === 'failed') {
      return String(check['reason'] ?? check['type'] ?? 'Inadmissible');
    }
  }
  if (workload.phase === 'Inadmissible' && workload.is_admitted !== true) {
    return 'QuotaExceeded';
  }
  return null;
}

function disposeObject(obj: THREE.Object3D): void {
  obj.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (!mesh.isMesh && !(child as THREE.LineSegments).isLineSegments) return;
    const anyObj = child as THREE.Mesh | THREE.LineSegments;
    anyObj.geometry?.dispose();
    const mats = Array.isArray(anyObj.material) ? anyObj.material : [anyObj.material];
    for (const m of mats) if (m) m.dispose();
  });
}
