/**
 * SPEC-09 / TASK-CV-1003: Exterior Pre-Admission Staging Yard (ADR-02).
 *
 * Owns everything the operator sees at X < -12.0 outside the skyscraper:
 *
 *  1. Reinforced industrial tarmac (SPEC-09 §4.1): Y = 0.2,
 *     X in [-24.0, -12.0], Z in [-8.0, +8.0], with directional runway
 *     lighting, taxiway centerline markers, and cargo rail tracks leading
 *     into the tower intake bays at X = -12.0.
 *  2. Pending-pod low anti-gravity hover (SPEC-09 §4.2): pods with
 *     PodScheduled=False bob gently above the tarmac at Y = 1.0.
 *  3. Karpenter correlation (SPEC-09 §4.2): for every NodeClaim, a
 *     holographic amber wireframe "Ghost Node" chassis docks on Sub-Level
 *     B1 (Y = -2.5) while compute is provisioned; luminous amber tractor
 *     beams project from the pending pods down into their ghost chassis.
 *
 * Coordinate constants mirror src/ingestion/layout.py (single source of
 * truth on the Python side; events carry explicit endpoints so any drift
 * is visible).
 */

import * as THREE from 'three';

// ---------------------------------------------------------------------------
// Wire types (mirror of src/ingestion/models.py KarpenterNodeClaim)
// ---------------------------------------------------------------------------

export interface KarpenterNodeClaimData {
  claim_name: string;
  namespace?: string;
  nodepool?: string;
  instance_type?: string | null;
  capacity_type?: 'spot' | 'on-demand';
  requested_cpu_cores?: number;
  requested_memory_gib?: number;
  requested_gpu_count?: number;
  pending_pod_uids?: string[];
  is_provisioned?: boolean;
  created_at?: string | null;
}

/** SSE `karpenter_tractor_beam` payload (mirror of controller.py). */
export interface KarpenterTractorBeamCoords {
  top?: number[] | null;
  bottom?: number[] | null;
  span_y?: number;
}

export interface KarpenterTractorBeamPayload {
  node_id: string;
  claim_name: string;
  beam: KarpenterTractorBeamCoords;
  timestamp?: string;
}

/** SSE `karpenter_claim_updated` payload. */
export interface KarpenterClaimUpdatedPayload {
  claim: KarpenterNodeClaimData;
  ghost_position?: { x: number; y: number; z: number } | null;
  staging_focus_x?: number;
  timestamp?: string;
}

// ---------------------------------------------------------------------------
// Spatial constants (mirror of src/ingestion/layout.py)
// ---------------------------------------------------------------------------

export const STAGING_TARMAC_Y = 0.2;
export const STAGING_TARMAC_X_MIN = -24.0;
export const STAGING_TARMAC_X_MAX = -12.0;
export const STAGING_TARMAC_Z_MIN = -8.0;
export const STAGING_TARMAC_Z_MAX = 8.0;

export const PENDING_HOVER_Y = 1.0;
export const GHOST_NODE_Y = -2.5;
export const GHOST_CHASSIS_SPACING_X = 2.4;
export const STAGING_YARD_FOCUS_X = -18.0;

/** Luminous amber for tractor beams / ghost chassis (SPEC-09 §4.2). */
export const TRACTOR_BEAM_AMBER = 0xffb020;

// Hover bob tuning: gentle anti-gravity suspension feel.
const HOVER_BOB_AMPLITUDE = 0.09;
const HOVER_BOB_RATE = 1.6;

// ---------------------------------------------------------------------------
// Internal records
// ---------------------------------------------------------------------------

interface HoveringPod {
  object: THREE.Object3D;
  baseY: number;
  phase: number;
}

interface TractorBeam {
  key: string;
  group: THREE.Group;
  shaft: THREE.Mesh;
  shaftMat: THREE.MeshBasicMaterial;
  pulseMat: THREE.MeshBasicMaterial;
  pulse: THREE.Mesh;
  top: THREE.Vector3;
  bottom: THREE.Vector3;
}

interface GhostChassis {
  claimName: string;
  group: THREE.Group;
  wireMat: THREE.MeshBasicMaterial;
  provisioned: boolean;
}

// ---------------------------------------------------------------------------
// Tarmac construction
// ---------------------------------------------------------------------------

function buildTarmacPlane(): THREE.Group {
  const group = new THREE.Group();
  group.name = 'staging_tarmac';

  const width = STAGING_TARMAC_X_MAX - STAGING_TARMAC_X_MIN;   // 12.0
  const depth = STAGING_TARMAC_Z_MAX - STAGING_TARMAC_Z_MIN;    // 16.0
  const centerX = (STAGING_TARMAC_X_MIN + STAGING_TARMAC_X_MAX) / 2; // -18.0
  const centerZ = (STAGING_TARMAC_Z_MIN + STAGING_TARMAC_Z_MAX) / 2; // 0.0

  // Reinforced concrete slab.
  const slab = new THREE.Mesh(
    new THREE.BoxGeometry(width, 0.1, depth),
    new THREE.MeshStandardMaterial({
      color: 0x2a3033,
      roughness: 0.92,
      metalness: 0.15,
    }),
  );
  slab.position.set(centerX, STAGING_TARMAC_Y - 0.05, centerZ);
  group.add(slab);

  // Directional runway edge lighting: amber beacons along both Z edges.
  const beaconGeo = new THREE.SphereGeometry(0.07, 8, 8);
  const beaconMat = new THREE.MeshBasicMaterial({
    color: TRACTOR_BEAM_AMBER,
    transparent: true,
    opacity: 0.95,
  });
  for (const edgeX of [STAGING_TARMAC_X_MIN + 0.3, STAGING_TARMAC_X_MAX - 0.3]) {
    for (let z = STAGING_TARMAC_Z_MIN + 0.5; z <= STAGING_TARMAC_Z_MAX - 0.4; z += 1.5) {
      const beacon = new THREE.Mesh(beaconGeo, beaconMat);
      beacon.position.set(edgeX, STAGING_TARMAC_Y + 0.06, z);
      beacon.userData.runwayBeacon = true;
      group.add(beacon);
    }
  }

  // Taxiway centerline markers: dashed white dashes along X at Z = 0.
  const dashGeo = new THREE.BoxGeometry(0.7, 0.012, 0.12);
  const dashMat = new THREE.MeshBasicMaterial({
    color: 0xe8eef0,
    transparent: true,
    opacity: 0.55,
  });
  for (let x = STAGING_TARMAC_X_MIN + 0.8; x < STAGING_TARMAC_X_MAX - 0.4; x += 1.4) {
    const dash = new THREE.Mesh(dashGeo, dashMat);
    dash.position.set(x, STAGING_TARMAC_Y + 0.055, centerZ);
    group.add(dash);
  }

  // Cargo rail tracks leading into the tower intake bays at X = -12.0.
  const railMat = new THREE.MeshStandardMaterial({
    color: 0x8a9490,
    roughness: 0.35,
    metalness: 0.85,
    emissive: 0x0e3a30,
    emissiveIntensity: 0.35,
  });
  for (const railZ of [-4.0, 4.0]) {
    for (const offset of [-0.25, 0.25]) {
      const rail = new THREE.Mesh(
        new THREE.BoxGeometry(width - 0.6, 0.05, 0.08),
        railMat,
      );
      rail.position.set(centerX, STAGING_TARMAC_Y + 0.075, railZ + offset);
      group.add(rail);
    }
    // Intake-bay threshold gate at the tower boundary.
    const gate = new THREE.Mesh(
      new THREE.BoxGeometry(0.12, 1.4, 2.2),
      new THREE.MeshStandardMaterial({
        color: 0x1f6f5c,
        emissive: 0x22d3ee,
        emissiveIntensity: 0.3,
        transparent: true,
        opacity: 0.5,
      }),
    );
    gate.position.set(STAGING_TARMAC_X_MAX - 0.1, STAGING_TARMAC_Y + 0.7, railZ);
    group.add(gate);
  }

  // Apron boundary hatching along the outer edge (X = -24).
  const hatchMat = new THREE.MeshBasicMaterial({
    color: 0xfbbf24,
    transparent: true,
    opacity: 0.35,
  });
  for (let z = STAGING_TARMAC_Z_MIN; z < STAGING_TARMAC_Z_MAX; z += 0.8) {
    const hatch = new THREE.Mesh(new THREE.BoxGeometry(0.45, 0.012, 0.28), hatchMat);
    hatch.position.set(STAGING_TARMAC_X_MIN + 0.3, STAGING_TARMAC_Y + 0.056, z);
    hatch.rotation.y = Math.PI / 5;
    group.add(hatch);
  }

  return group;
}

function buildGhostChassis(position: THREE.Vector3, provisioned: boolean): GhostChassis {
  const group = new THREE.Group();
  group.name = `ghost_node_${position.x.toFixed(2)}`;
  group.position.copy(position);

  const wireMat = new THREE.MeshBasicMaterial({
    color: TRACTOR_BEAM_AMBER,
    wireframe: true,
    transparent: true,
    opacity: provisioned ? 0.5 : 0.3,
    depthWrite: false,
  });
  const chassis = new THREE.Mesh(new THREE.BoxGeometry(2.0, 0.6, 1.5), wireMat);
  group.add(chassis);

  // Landing footprint ring on the B1 stratum.
  const ringMat = new THREE.MeshBasicMaterial({
    color: TRACTOR_BEAM_AMBER,
    transparent: true,
    opacity: 0.4,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const ring = new THREE.Mesh(new THREE.RingGeometry(1.15, 1.3, 40), ringMat);
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = -0.32;
  group.add(ring);

  return { claimName: '', group, wireMat, provisioned };
}

function buildTractorBeam(
  top: THREE.Vector3,
  bottom: THREE.Vector3,
  radius: number,
): TractorBeam {
  const group = new THREE.Group();
  const height = Math.max(0.2, top.y - bottom.y);
  const midX = (top.x + bottom.x) / 2;
  const midZ = (top.z + bottom.z) / 2;
  const midY = (top.y + bottom.y) / 2;

  const shaftMat = new THREE.MeshBasicMaterial({
    color: TRACTOR_BEAM_AMBER,
    transparent: true,
    opacity: 0.28,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const shaft = new THREE.Mesh(
    new THREE.CylinderGeometry(radius * 0.65, radius * 1.15, height, 20, 1, true),
    shaftMat,
  );
  shaft.position.set(midX, midY, midZ);
  group.add(shaft);

  // Lifting-platform disc that pulses up the shaft (provisioning in progress).
  const pulseMat = new THREE.MeshBasicMaterial({
    color: TRACTOR_BEAM_AMBER,
    transparent: true,
    opacity: 0.7,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const pulse = new THREE.Mesh(new THREE.RingGeometry(radius * 0.5, radius * 1.3, 28), pulseMat);
  pulse.rotation.x = -Math.PI / 2;
  pulse.position.set(midX, bottom.y, midZ);
  group.add(pulse);

  // Impact flare where the beam meets the ghost chassis.
  const flare = new THREE.Mesh(
    new THREE.RingGeometry(radius * 1.1, radius * 1.6, 28),
    new THREE.MeshBasicMaterial({
      color: TRACTOR_BEAM_AMBER,
      transparent: true,
      opacity: 0.45,
      side: THREE.DoubleSide,
      depthWrite: false,
    }),
  );
  flare.rotation.x = -Math.PI / 2;
  flare.position.set(bottom.x, bottom.y + 0.34, bottom.z);
  group.add(flare);

  return {
    key: '',
    group,
    shaft,
    shaftMat,
    pulseMat,
    pulse,
    top: top.clone(),
    bottom: bottom.clone(),
  };
}

// ---------------------------------------------------------------------------
// Manager
// ---------------------------------------------------------------------------

/**
 * Staging-yard scene manager. The viewport builds it, feeds it the
 * snapshot's `karpenter_node_claims` plus its pending-pod meshes, and calls
 * `update(delta, time)` from the render loop for hover bobbing, beam
 * pulses, and runway beacon beacons.
 */
export class StagingYardManager {
  private readonly scene: THREE.Scene;
  private tarmac: THREE.Group | null = null;
  private readonly ghostRoot = new THREE.Group();
  private readonly beamRoot = new THREE.Group();
  private readonly hovering: HoveringPod[] = [];
  private readonly ghosts = new Map<string, GhostChassis>();
  private readonly beams = new Map<string, TractorBeam>();
  /** nodeId -> ghost chassis key so each pod's beam can be re-anchored. */
  private readonly podBeamKeys = new Map<string, string[]>();

  constructor(scene: THREE.Scene) {
    this.scene = scene;
    this.ghostRoot.name = 'staging_ghost_nodes';
    this.beamRoot.name = 'staging_tractor_beams';
    scene.add(this.ghostRoot);
    scene.add(this.beamRoot);
    this.buildTarmac();
  }

  /** (Re)build the reinforced tarmac apron. Idempotent. */
  public buildTarmac(): void {
    if (this.tarmac) {
      this.scene.remove(this.tarmac);
      disposeObject(this.tarmac);
    }
    this.tarmac = buildTarmacPlane();
    this.scene.add(this.tarmac);
  }

  /** Register a pending-pod object for the anti-gravity hover animation. */
  public registerPendingPod(object: THREE.Object3D): void {
    if (object.userData.stagingHover) return;
    object.userData.stagingHover = true;
    this.hovering.push({
      object,
      baseY: object.position.y,
      phase: Math.random() * Math.PI * 2,
    });
  }

  /** Register a ghost chassis for a NodeClaim on Sub-Level B1. */
  public upsertGhostChassis(
    claimName: string,
    position: THREE.Vector3,
    provisioned = false,
  ): void {
    const existing = this.ghosts.get(claimName);
    if (existing) {
      existing.group.position.copy(position);
      existing.provisioned = provisioned;
      existing.wireMat.opacity = provisioned ? 0.5 : 0.3;
      return;
    }
    const ghost = buildGhostChassis(position, provisioned);
    ghost.claimName = claimName;
    this.ghosts.set(claimName, ghost);
    this.ghostRoot.add(ghost.group);
  }

  /** Anchor an amber tractor beam from a pending pod into a ghost chassis. */
  public setTractorBeam(
    nodeId: string,
    claimName: string,
    top: THREE.Vector3,
    bottom: THREE.Vector3,
    radius = 0.4,
  ): void {
    const key = `${nodeId}->${claimName}`;
    const existing = this.beams.get(key);
    if (existing) {
      this.beamRoot.remove(existing.group);
      disposeObject(existing.group);
      this.beams.delete(key);
    }
    const beam = buildTractorBeam(top, bottom, radius);
    beam.key = key;
    this.beams.set(key, beam);
    this.beamRoot.add(beam.group);

    const keys = this.podBeamKeys.get(nodeId) ?? [];
    keys.push(key);
    this.podBeamKeys.set(nodeId, keys);
  }

  /**
   * Consume a snapshot's Karpenter claims: dock one ghost chassis per claim
   * at the canonical B1 row and wire beams from the given pending-pod
   * positions down into their target chassis.
   */
  public applyClaims(
    claims: KarpenterNodeClaimData[] | undefined,
    pendingPositions: Map<string, THREE.Vector3>,
  ): void {
    this.clearGhostsAndBeams();
    if (!claims || claims.length === 0) return;
    const span = GHOST_CHASSIS_SPACING_X * claims.length;
    const startX = -span / 2 + GHOST_CHASSIS_SPACING_X / 2;
    claims.forEach((claim, i) => {
      const x = Math.min(10.0, Math.max(-10.0, startX + i * GHOST_CHASSIS_SPACING_X));
      const dock = new THREE.Vector3(x, GHOST_NODE_Y, 0.0);
      this.upsertGhostChassis(claim.claim_name, dock, claim.is_provisioned === true);
      for (const podId of claim.pending_pod_uids ?? []) {
        const pos = pendingPositions.get(podId);
        if (!pos) continue;
        this.setTractorBeam(podId, claim.claim_name, pos.clone(), dock.clone());
      }
    });
  }

  /** Camera targets for the Staging Apron Focus control (SPEC-09 §7.1). */
  public static stagingFocusTargets(): {
    camera: THREE.Vector3;
    target: THREE.Vector3;
  } {
    return {
      camera: new THREE.Vector3(
        STAGING_YARD_FOCUS_X + 10.5,
        6.2,
        13.5,
      ),
      target: new THREE.Vector3(STAGING_YARD_FOCUS_X, 0.8, 0.0),
    };
  }

  public beamCount(): number {
    return this.beams.size;
  }

  public ghostCount(): number {
    return this.ghosts.size;
  }

  // -- Frame update ----------------------------------------------------------

  public update(_delta: number, time: number): void {
    // Pending pods: gentle anti-gravity hover/bobbing around their hover Y.
    for (const pod of this.hovering) {
      const bob = HOVER_BOB_AMPLITUDE * Math.sin(time * HOVER_BOB_RATE + pod.phase);
      pod.object.position.y = pod.baseY + bob;
    }

    // Runway beacon chase along the tarmac edges.
    if (this.tarmac) {
      const chaseOn = Math.floor(time * 4) % 2 === 0;
      this.tarmac.traverse((child) => {
        if (child.userData.runwayBeacon) {
          const mat = (child as THREE.Mesh).material as THREE.MeshBasicMaterial;
          if (mat && mat.isMeshBasicMaterial) mat.opacity = chaseOn ? 0.95 : 0.35;
        }
      });
    }

    // Ghost chassis shimmer; solidifying chassis fade the wire out.
    const shimmer = 0.22 + 0.12 * (0.5 + 0.5 * Math.sin(time * 2.6));
    for (const ghost of this.ghosts.values()) {
      ghost.wireMat.opacity = ghost.provisioned
        ? Math.max(0.08, 0.5 - 0.3 * (0.5 + 0.5 * Math.sin(time * 1.2)))
        : shimmer + 0.08;
    }

    // Tractor beams: shaft breathing + lifting-platform pulse climbing shaft.
    for (const beam of this.beams.values()) {
      const cycle = (time * 0.65) % 1;
      beam.pulse.position.y = beam.bottom.y + 0.35 + (beam.top.y - beam.bottom.y - 0.5) * cycle;
      beam.pulseMat.opacity = 0.75 * Math.sin(cycle * Math.PI);
      beam.shaftMat.opacity = 0.2 + 0.12 * (0.5 + 0.5 * Math.sin(time * 3.4));
      // Follow the pod's hover bob so the beam top stays attached: rescale
      // the shaft about its bottom cap to the pod's live hover height.
      const podId = beam.key.split('->')[0] ?? '';
      const pod = this.hovering.find((h) => {
        const data = h.object.userData.nodeData as { id?: string } | undefined;
        return data?.id === podId;
      });
      if (pod) {
        const nominal = Math.max(0.2, beam.top.y - beam.bottom.y);
        const live = Math.max(0.2, pod.object.position.y - beam.bottom.y);
        beam.shaft.scale.y = live / nominal;
        beam.shaft.position.y = beam.bottom.y + (nominal * beam.shaft.scale.y) / 2;
      }
    }
  }

  // -- Teardown ----------------------------------------------------------------

  public clearGhostsAndBeams(): void {
    for (const ghost of this.ghosts.values()) {
      this.ghostRoot.remove(ghost.group);
      disposeObject(ghost.group);
    }
    this.ghosts.clear();
    for (const beam of this.beams.values()) {
      this.beamRoot.remove(beam.group);
      disposeObject(beam.group);
    }
    this.beams.clear();
    this.podBeamKeys.clear();
  }

  /** Remove hover bobbing and any tractor beams tied to a deleted pod. */
  public removePendingPod(nodeId: string): void {
    for (let i = this.hovering.length - 1; i >= 0; i--) {
      const entry = this.hovering[i];
      if (!entry) continue;
      const data = entry.object.userData.nodeData as { id?: string } | undefined;
      if (data?.id !== nodeId) continue;
      entry.object.userData.stagingHover = false;
      entry.object.position.y = entry.baseY;
      this.hovering.splice(i, 1);
    }
    const keys = this.podBeamKeys.get(nodeId) ?? [];
    for (const key of keys) {
      const beam = this.beams.get(key);
      if (!beam) continue;
      this.beamRoot.remove(beam.group);
      disposeObject(beam.group);
      this.beams.delete(key);
    }
    this.podBeamKeys.delete(nodeId);
  }

  public clearHovering(): void {
    for (const pod of this.hovering) {
      pod.object.userData.stagingHover = false;
      pod.object.position.y = pod.baseY;
    }
    this.hovering.length = 0;
  }

  /** Full teardown (viewport dispose). Keeps nothing in the scene. */
  public dispose(): void {
    this.clearGhostsAndBeams();
    this.clearHovering();
    if (this.tarmac) {
      this.scene.remove(this.tarmac);
      disposeObject(this.tarmac);
      this.tarmac = null;
    }
    this.scene.remove(this.ghostRoot);
    this.scene.remove(this.beamRoot);
  }
}

function disposeObject(obj: THREE.Object3D): void {
  obj.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.geometry.dispose();
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const m of mats) m.dispose();
  });
}
