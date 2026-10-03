import * as THREE from 'three';

/**
 * TASK-CV-904 / SPEC-08: Sub-Level B2+ Managed Cloud Service Vaults.
 *
 * Renders procedural industrial vault meshes for RemoteServiceResource
 * entries carried on the ClusterGraph snapshot `subterranean_resources`
 * field (mirrors src/ingestion/models.py RemoteServiceResource), manages
 * vault click raycasting with blast-radius highlighting, and animates the
 * Pub/Sub raceway particles and glowing status rings.
 */

/** Mirrors models.ManagedServiceCategory (SPEC-08 ADR-01). */
export type ManagedServiceCategory =
  | 'database_relational'
  | 'database_nosql'
  | 'object_storage'
  | 'messaging_eventing'
  | 'cache_in_memory'
  | 'security_secret'
  | 'networking_gateway';

/**
 * Scene-side mirror of models.RemoteServiceResource. `spatial` is required
 * here because layout.apply_subterranean_layout always stamps it before the
 * snapshot reaches the renderer.
 */
export interface RemoteServiceResourceData {
  id: string;
  provider: string;
  category: ManagedServiceCategory;
  cr_kind: string;
  name: string;
  namespace: string;
  display_name: string;
  status_phase: string; // Ready, Reconciling, Degraded, Failed
  endpoint?: string;
  managed_by: string; // kcc, kro, ack, crossplane
  kro_parent_id?: string;
  spatial: { x: number; y: number; z: number };
}

/** Result of a vault click: the vault hit plus its dependency blast radius. */
export interface VaultBlastState {
  vaultId: string;
  connectedIds: string[];
}

// Elevation tiers, matching src/ingestion/layout.py ELEVATION_TIERS.
export const VAULT_Y = -6.5; // Sub-Level B2 Lower: managed service vaults
export const KRO_MANIFOLD_Y = -4.8; // Sub-Level B2 Upper: kro routing hub
export const BEDROCK_Y = -10.5; // Sub-Level B3: external egress bedrock
export const KRO_MANIFOLD_HUB_ID = 'kro_manifold_hub';

const AMBER = 0xf59e0b;
const RUBY = 0xe11d48;

interface RingPulse {
  material: THREE.MeshStandardMaterial;
  baseIntensity: number;
  rate: number;
  phase: number;
}

interface RacewayParticles {
  points: THREE.Points;
  positions: Float32Array;
  angles: Float32Array;
  angularSpeed: number;
  center: THREE.Vector3;
  radius: number;
  count: number;
}

interface VaultRecord {
  id: string;
  resource: RemoteServiceResourceData;
  group: THREE.Group;
  statusMaterial: THREE.MeshStandardMaterial;
  statusPhase: string;
  materials: THREE.MeshStandardMaterial[];
  baseOpacities: Map<THREE.Material, number>;
  baseEmissiveIntensities: Map<THREE.MeshStandardMaterial, number>;
  raceway: RacewayParticles | null;
}

function statusRingColor(phase: string): number {
  const p = phase.toLowerCase();
  if (p.includes('fail')) return 0xef4444;
  if (p.includes('degrad')) return 0xf97316;
  if (p.includes('reconcil')) return 0x38bdf8;
  return AMBER; // Ready
}

function statusPulseRate(phase: string): number {
  const p = phase.toLowerCase();
  if (p.includes('fail')) return 8.0; // hazard strobe
  if (p.includes('degrad')) return 5.0;
  return 2.2; // calm breathing
}

function vaultMaterial(
  color: number,
  opts: Partial<{
    emissive: number;
    emissiveIntensity: number;
    metalness: number;
    roughness: number;
    opacity: number;
  }> = {},
): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color,
    emissive: opts.emissive ?? 0x000000,
    emissiveIntensity: opts.emissiveIntensity ?? 0.0,
    metalness: opts.metalness ?? 0.7,
    roughness: opts.roughness ?? 0.45,
    transparent: true,
    opacity: opts.opacity ?? 1.0,
  });
}

/**
 * SQLInstance / DATABASE_RELATIONAL: dual pressurized database cylinders
 * with reinforced reinforcement bands and an amber status ring (SPEC-08 §4.2).
 */
function buildRelationalVault(group: THREE.Group): void {
  const base = new THREE.Mesh(
    new THREE.BoxGeometry(2.6, 0.14, 1.7),
    vaultMaterial(0x334155, { roughness: 0.8, metalness: 0.3 }),
  );
  base.position.y = 0.07;
  group.add(base);

  const tanks: Array<[number, number, number, number]> = [
    [0.55, 0.0, 1.3, 0.65], // radius, x-offset, height, y-center
    [0.38, 1.2, 0.95, 0.475],
  ];
  for (const [radius, offX, height, cy] of tanks) {
    const tank = new THREE.Mesh(
      new THREE.CylinderGeometry(radius, radius * 1.05, height, 24),
      vaultMaterial(0x475569, { emissive: 0x0a2540, emissiveIntensity: 0.25 }),
    );
    tank.position.set(offX, cy, 0);
    group.add(tank);

    // Reinforced bands wrapping each pressure cylinder.
    for (const bandY of [cy - height * 0.32, cy, cy + height * 0.32]) {
      const band = new THREE.Mesh(
        new THREE.TorusGeometry(radius + 0.04, 0.045, 8, 24),
        vaultMaterial(0x94a3b8, { metalness: 0.9, roughness: 0.25 }),
      );
      band.rotation.x = Math.PI / 2;
      band.position.set(offX, bandY, 0);
      group.add(band);
    }
  }

  // Cross-coupling manifold pipe between the twin cells.
  const coupling = new THREE.Mesh(
    new THREE.CylinderGeometry(0.08, 0.08, 0.75, 12),
    vaultMaterial(0x64748b, { emissive: 0x155e75, emissiveIntensity: 0.4 }),
  );
  coupling.rotation.z = Math.PI / 2;
  coupling.position.set(0.78, 0.7, 0);
  group.add(coupling);
}

/**
 * StorageBucket / OBJECT_STORAGE: cryptographic vault safe cube with
 * interlocking circular door geometry and sliding data-block indicators.
 */
function buildObjectStorageVault(group: THREE.Group): void {
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(1.4, 1.4, 1.4),
    vaultMaterial(0x3f4c5e, { roughness: 0.55, metalness: 0.75 }),
  );
  body.position.y = 0.78;
  group.add(body);

  // Interlocking circular vault door on the +Z face.
  const door = new THREE.Mesh(
    new THREE.CylinderGeometry(0.48, 0.48, 0.14, 32),
    vaultMaterial(0x8fa3a8, { metalness: 0.95, roughness: 0.2 }),
  );
  door.rotation.x = Math.PI / 2;
  door.position.set(0, 0.78, 0.72);
  group.add(door);

  const interlockRing = new THREE.Mesh(
    new THREE.TorusGeometry(0.32, 0.05, 8, 24),
    vaultMaterial(0xd97706, { metalness: 0.9, roughness: 0.3 }),
  );
  interlockRing.position.set(0, 0.78, 0.8);
  group.add(interlockRing);

  // Spokes of the locking wheel.
  for (let i = 0; i < 4; i++) {
    const spoke = new THREE.Mesh(
      new THREE.BoxGeometry(0.6, 0.06, 0.06),
      vaultMaterial(0xcbd5e1, { metalness: 0.9, roughness: 0.25 }),
    );
    spoke.rotation.z = (i * Math.PI) / 4;
    spoke.position.set(0, 0.78, 0.82);
    group.add(spoke);
  }

  // Sliding data-block block indicators on the side face.
  for (let i = 0; i < 3; i++) {
    const block = new THREE.Mesh(
      new THREE.BoxGeometry(0.08, 0.16, 0.4),
      vaultMaterial(0x22d3ee, {
        emissive: 0x0891b2,
        emissiveIntensity: 0.9,
        roughness: 0.3,
      }),
    );
    block.position.set(0.74, 0.4 + i * 0.28, -0.35);
    group.add(block);
  }
}

function buildRacewayParticles(center: THREE.Vector3, radius: number): RacewayParticles {
  const count = 48;
  const positions = new Float32Array(count * 3);
  const angles = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    const a = (i / count) * Math.PI * 2;
    angles[i] = a;
    positions[i * 3] = center.x + radius * Math.cos(a);
    positions[i * 3 + 1] = center.y;
    positions[i * 3 + 2] = center.z + radius * Math.sin(a);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const material = new THREE.PointsMaterial({
    color: 0x7dd3fc,
    size: 0.09,
    transparent: true,
    opacity: 0.95,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const points = new THREE.Points(geometry, material);
  return { points, positions, angles, angularSpeed: 2.2, center, radius, count };
}

/**
 * PubSubTopic / MESSAGING_EVENTING: high-velocity continuous torus raceway
 * with orbiting message particles circling the loop.
 */
function buildMessagingVault(group: THREE.Group): RacewayParticles {
  const center = new THREE.Vector3(0, 0.75, 0);

  const track = new THREE.Mesh(
    new THREE.TorusGeometry(1.05, 0.14, 12, 48),
    vaultMaterial(0x1e293b, { metalness: 0.8, roughness: 0.5 }),
  );
  track.rotation.x = Math.PI / 2;
  track.position.copy(center);
  group.add(track);

  const innerGlow = new THREE.Mesh(
    new THREE.TorusGeometry(1.05, 0.055, 8, 48),
    vaultMaterial(0x38bdf8, {
      emissive: 0x0ea5e9,
      emissiveIntensity: 1.2,
      roughness: 0.2,
    }),
  );
  innerGlow.rotation.x = Math.PI / 2;
  innerGlow.position.copy(center);
  group.add(innerGlow);

  // Support pylons holding the raceway loop.
  for (let i = 0; i < 3; i++) {
    const a = (i / 3) * Math.PI * 2;
    const pylon = new THREE.Mesh(
      new THREE.CylinderGeometry(0.06, 0.09, 0.75, 8),
      vaultMaterial(0x475569, { roughness: 0.7 }),
    );
    pylon.position.set(1.05 * Math.cos(a), 0.375, 1.05 * Math.sin(a));
    group.add(pylon);
  }

  const base = new THREE.Mesh(
    new THREE.CylinderGeometry(0.5, 0.6, 0.1, 16),
    vaultMaterial(0x334155, { roughness: 0.8, metalness: 0.3 }),
  );
  base.position.y = 0.05;
  group.add(base);

  return buildRacewayParticles(center, 1.05);
}

/**
 * RedisInstance / CACHE_IN_MEMORY: low hexagonal crystalline slab glowing
 * with low-latency ruby-red luminescence.
 */
function buildCacheVault(group: THREE.Group): void {
  const slab = new THREE.Mesh(
    new THREE.CylinderGeometry(0.95, 1.05, 0.32, 6),
    vaultMaterial(0x4c1d32, {
      emissive: RUBY,
      emissiveIntensity: 0.45,
      metalness: 0.4,
      roughness: 0.35,
    }),
  );
  slab.position.y = 0.2;
  group.add(slab);

  // Crystalline prisms rising from the lattice lattice platform.
  const crystalSpecs: Array<[number, number, number, number]> = [
    [0.16, 0.0, 0.55, 0.55], // radius, xz-distance, height, phase angle
    [0.1, 0.45, 0.34, 2.4],
    [0.08, 0.6, 0.26, 4.4],
  ];
  for (const [radius, dist, height, ang] of crystalSpecs) {
    const crystal = new THREE.Mesh(
      new THREE.CylinderGeometry(radius * 0.35, radius, height, 6),
      vaultMaterial(0x9f1239, {
        emissive: 0xfb7185,
        emissiveIntensity: 1.4,
        metalness: 0.2,
        roughness: 0.15,
        opacity: 0.9,
      }),
    );
    crystal.position.set(dist * Math.cos(ang), 0.36 + height / 2, dist * Math.sin(ang));
    group.add(crystal);
  }
}

/**
 * SecuritySecret / fallback: sealed monolith with a keyhole seam.
 */
function buildGenericVault(group: THREE.Group): void {
  const monolith = new THREE.Mesh(
    new THREE.BoxGeometry(1.0, 1.5, 0.7),
    vaultMaterial(0x334155, { roughness: 0.6, metalness: 0.6 }),
  );
  monolith.position.y = 0.75;
  group.add(monolith);

  const seam = new THREE.Mesh(
    new THREE.BoxGeometry(0.06, 1.3, 0.74),
    vaultMaterial(0x0f172a, { emissive: 0x6366f1, emissiveIntensity: 0.8 }),
  );
  seam.position.y = 0.75;
  group.add(seam);
}

/**
 * NETWORKING_GATEWAY (Sub-Level B3): deep transit borehole bedrock block —
 * a rough hewn rock mass bored through by a transit shaft with a glowing rim.
 */
function buildBedrockGatewayVault(group: THREE.Group): void {
  const bedrock = new THREE.Mesh(
    new THREE.BoxGeometry(2.7, 1.7, 2.3),
    vaultMaterial(0x44403c, { roughness: 0.95, metalness: 0.1 }),
  );
  bedrock.position.y = 0.85;
  group.add(bedrock);

  // Bored transit shaft through the front face.
  const bore = new THREE.Mesh(
    new THREE.CylinderGeometry(0.5, 0.5, 2.4, 20),
    vaultMaterial(0x0c0a09, { roughness: 1.0, metalness: 0.0 }),
  );
  bore.rotation.x = Math.PI / 2;
  bore.position.set(0, 0.85, 0.1);
  group.add(bore);

  const rim = new THREE.Mesh(
    new THREE.TorusGeometry(0.55, 0.08, 10, 28),
    vaultMaterial(0x22d3ee, {
      emissive: 0x0891b2,
      emissiveIntensity: 1.1,
      metalness: 0.8,
      roughness: 0.3,
    }),
  );
  rim.position.set(0, 0.85, 1.3);
  group.add(rim);

  // Rock strata shelves.
  for (let i = 0; i < 2; i++) {
    const shelf = new THREE.Mesh(
      new THREE.BoxGeometry(2.9, 0.12, 2.5),
      vaultMaterial(0x292524, { roughness: 1.0, metalness: 0.05 }),
    );
    shelf.position.y = i === 0 ? 0.04 : 1.72;
    group.add(shelf);
  }
}

/**
 * kro Manifold Hub (Sub-Level B2 Upper, Y = -4.8): hydraulic manifold
 * distribution hub — central column with a top intake riser and radial
 * branch ports fanning out to the vault strata below.
 */
function buildManifoldHub(group: THREE.Group): void {
  const column = new THREE.Mesh(
    new THREE.CylinderGeometry(0.6, 0.72, 1.4, 24),
    vaultMaterial(0x374151, { metalness: 0.85, roughness: 0.35 }),
  );
  column.position.y = 0.7;
  group.add(column);

  // Intake riser descending from the worker deck above.
  const intake = new THREE.Mesh(
    new THREE.CylinderGeometry(0.22, 0.22, 1.6, 16),
    vaultMaterial(0x64748b, { emissive: 0x155e75, emissiveIntensity: 0.5 }),
  );
  intake.position.y = 2.1;
  group.add(intake);

  const intakeFlange = new THREE.Mesh(
    new THREE.TorusGeometry(0.28, 0.06, 8, 20),
    vaultMaterial(0x94a3b8, { metalness: 0.9, roughness: 0.25 }),
  );
  intakeFlange.rotation.x = Math.PI / 2;
  intakeFlange.position.y = 2.85;
  group.add(intakeFlange);

  // Radial branch ports feeding the vault grid.
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2;
    const port = new THREE.Mesh(
      new THREE.CylinderGeometry(0.13, 0.13, 1.0, 12),
      vaultMaterial(0x475569, {
        emissive: 0x22d3ee,
        emissiveIntensity: 0.7,
        metalness: 0.8,
        roughness: 0.3,
      }),
    );
    port.rotation.z = Math.PI / 2;
    port.rotation.y = -a;
    port.position.set(1.1 * Math.cos(a), 0.55, 1.1 * Math.sin(a));
    group.add(port);
  }

  // Drip skirt anchoring the hub into the B2 floor.
  const skirt = new THREE.Mesh(
    new THREE.CylinderGeometry(1.0, 1.25, 0.18, 24),
    vaultMaterial(0x1f2937, { roughness: 0.85, metalness: 0.3 }),
  );
  skirt.position.y = 0.02;
  group.add(skirt);
}

export class SubterraneanVaultManager {
  private readonly scene: THREE.Scene;
  private readonly group: THREE.Group;
  private vaults: Map<string, VaultRecord> = new Map();
  private pulses: RingPulse[] = [];
  private blastState: VaultBlastState | null = null;

  constructor(scene: THREE.Scene) {
    this.scene = scene;
    this.group = new THREE.Group();
    this.group.name = 'SubterraneanVaultGroup';
    this.scene.add(this.group);
  }

  /** Rebuild every vault mesh from the snapshot's subterranean resources. */
  public setResources(resources: RemoteServiceResourceData[]): void {
    this.clear();

    for (const resource of resources) {
      const group = new THREE.Group();
      group.name = `vault-${resource.id}`;

      let raceway: RacewayParticles | null = null;
      switch (resource.category) {
        case 'database_relational':
          buildRelationalVault(group);
          break;
        case 'object_storage':
          buildObjectStorageVault(group);
          break;
        case 'messaging_eventing':
          raceway = buildMessagingVault(group);
          break;
        case 'cache_in_memory':
          buildCacheVault(group);
          break;
        case 'networking_gateway':
          buildBedrockGatewayVault(group);
          break;
        default:
          buildGenericVault(group);
          break;
      }

      // Glowing status ring at the vault base.
      const statusMaterial = new THREE.MeshStandardMaterial({
        color: statusRingColor(resource.status_phase),
        emissive: statusRingColor(resource.status_phase),
        emissiveIntensity: 0.8,
        metalness: 0.5,
        roughness: 0.3,
        transparent: true,
        opacity: 0.95,
      });
      const statusRing = new THREE.Mesh(
        new THREE.TorusGeometry(resource.category === 'networking_gateway' ? 1.5 : 1.25, 0.05, 8, 40),
        statusMaterial,
      );
      statusRing.rotation.x = Math.PI / 2;
      statusRing.position.y = 0.03;
      group.add(statusRing);

      const materials: THREE.MeshStandardMaterial[] = [];
      const baseOpacities = new Map<THREE.Material, number>();
      const baseEmissiveIntensities = new Map<THREE.MeshStandardMaterial, number>();
      group.traverse((child) => {
        const mesh = child as THREE.Mesh;
        if (!mesh.isMesh) return;
        mesh.castShadow = false;
        mesh.receiveShadow = false;
        const mat = mesh.material as THREE.MeshStandardMaterial;
        if (mat.isMeshStandardMaterial) {
          materials.push(mat);
          baseEmissiveIntensities.set(mat, mat.emissiveIntensity);
        }
        baseOpacities.set(mesh.material as THREE.Material, mat.opacity ?? 1.0);
      });
      if (raceway) baseOpacities.set(raceway.points.material as THREE.Material, 0.95);

      group.position.set(resource.spatial.x, resource.spatial.y, resource.spatial.z);
      group.userData = { vaultId: resource.id, vaultData: resource };
      this.group.add(group);
      if (raceway) group.add(raceway.points);

      const record: VaultRecord = {
        id: resource.id,
        resource,
        group,
        statusMaterial,
        statusPhase: resource.status_phase,
        materials,
        baseOpacities,
        baseEmissiveIntensities,
        raceway,
      };
      this.vaults.set(resource.id, record);

      this.pulses.push({
        material: statusMaterial,
        baseIntensity: 0.8,
        rate: statusPulseRate(resource.status_phase),
        phase: group.position.x + group.position.z,
      });
    }

    if (this.vaults.size > 0) this.ensureManifoldHub();
    this.applyBlastHighlight(this.blastState);
  }

  /**
   * The kro hydraulic manifold hub always anchors at (0, -4.8, 0) once any
   * managed vault stratum exists (layout.py KRO_MANIFOLD_ANCHOR). Clicking
   * it blast-radii every vault it distributes into.
   */
  private ensureManifoldHub(): void {
    if (this.vaults.has(KRO_MANIFOLD_HUB_ID)) return;

    const group = new THREE.Group();
    group.name = `vault-${KRO_MANIFOLD_HUB_ID}`;
    buildManifoldHub(group);

    const statusMaterial = new THREE.MeshStandardMaterial({
      color: 0x22d3ee,
      emissive: 0x0891b2,
      emissiveIntensity: 1.0,
      metalness: 0.6,
      roughness: 0.3,
      transparent: true,
      opacity: 0.95,
    });
    const hubRing = new THREE.Mesh(new THREE.TorusGeometry(1.35, 0.05, 8, 40), statusMaterial);
    hubRing.rotation.x = Math.PI / 2;
    hubRing.position.y = 0.06;
    group.add(hubRing);

    const materials: THREE.MeshStandardMaterial[] = [];
    const baseOpacities = new Map<THREE.Material, number>();
    const baseEmissiveIntensities = new Map<THREE.MeshStandardMaterial, number>();
    group.traverse((child) => {
      const mesh = child as THREE.Mesh;
      if (!mesh.isMesh) return;
      mesh.castShadow = false;
      mesh.receiveShadow = false;
      const mat = mesh.material as THREE.MeshStandardMaterial;
      if (mat.isMeshStandardMaterial) {
        materials.push(mat);
        baseEmissiveIntensities.set(mat, mat.emissiveIntensity);
      }
      baseOpacities.set(mesh.material as THREE.Material, mat.opacity ?? 1.0);
    });

    group.position.set(0, KRO_MANIFOLD_Y, 0);
    const synthetic: RemoteServiceResourceData = {
      id: KRO_MANIFOLD_HUB_ID,
      provider: 'gcp',
      category: 'database_nosql',
      cr_kind: 'Manifold',
      name: 'kro-manifold-hub',
      namespace: 'kro-system',
      display_name: 'kro Manifold Hub',
      status_phase: 'Ready',
      managed_by: 'kro',
      spatial: { x: 0, y: KRO_MANIFOLD_Y, z: 0 },
    };
    group.userData = { vaultId: KRO_MANIFOLD_HUB_ID, vaultData: synthetic };
    this.group.add(group);
    this.vaults.set(KRO_MANIFOLD_HUB_ID, {
      id: KRO_MANIFOLD_HUB_ID,
      resource: synthetic,
      group,
      statusMaterial,
      statusPhase: 'Ready',
      materials,
      baseOpacities,
      baseEmissiveIntensities,
      raceway: null,
    });
    this.pulses.push({
      material: statusMaterial,
      baseIntensity: 1.0,
      rate: 2.2,
      phase: 0,
    });
  }

  public hasVault(vaultId: string): boolean {
    return this.vaults.has(vaultId);
  }

  public getVaultWorldPosition(vaultId: string): THREE.Vector3 | null {
    const record = this.vaults.get(vaultId);
    if (!record) return null;
    const out = new THREE.Vector3();
    record.group.getWorldPosition(out);
    return out;
  }

  /** Raycast the vault strata; returns the vault id under the ray, if any. */
  public pickVault(raycaster: THREE.Raycaster): string | null {
    if (this.vaults.size === 0) return null;
    // Raycaster relies on matrixWorld; refresh it so picks stay correct even
    // outside the render loop (tests, deferred click handling).
    this.group.updateWorldMatrix(true, true);
    const intersects = raycaster.intersectObjects(this.group.children, true);
    for (const hit of intersects) {
      let obj: THREE.Object3D | null = hit.object;
      while (obj) {
        const vaultId = obj.userData.vaultId as string | undefined;
        if (vaultId) return vaultId;
        obj = obj.parent;
      }
    }
    return null;
  }

  /**
   * Blast radius: sibling vaults sharing the clicked vault's kro parent,
   * plus any vaults wired through the hub. Returned for the viewport to
   * spotlight downstream service dependencies.
   */
  public computeBlastRadius(vaultId: string): VaultBlastState {
    const record = this.vaults.get(vaultId);
    if (!record) return { vaultId, connectedIds: [] };

    if (vaultId === KRO_MANIFOLD_HUB_ID) {
      const connectedIds: string[] = [];
      for (const other of this.vaults.keys()) {
        if (other !== KRO_MANIFOLD_HUB_ID) connectedIds.push(other);
      }
      return { vaultId, connectedIds };
    }

    const parent = record.resource.kro_parent_id;
    const connectedIds: string[] = [];
    for (const other of this.vaults.values()) {
      if (other.id === vaultId || other.id === KRO_MANIFOLD_HUB_ID) continue;
      if (parent && (other.resource.kro_parent_id === parent || other.id === parent)) {
        connectedIds.push(other.id);
      }
    }
    if (parent) connectedIds.push(parent);
    return { vaultId, connectedIds };
  }

  /**
   * Dim every vault outside the blast radius; boost those inside. Pass null
   * to restore the neutral state.
   */
  public applyBlastHighlight(state: VaultBlastState | null): void {
    this.blastState = state;
    const inBlast = state ? new Set<string>([state.vaultId, ...state.connectedIds]) : null;

    for (const record of this.vaults.values()) {
      const dimmed = inBlast !== null && !inBlast.has(record.id);
      const boosted = state !== null && state.vaultId === record.id;

      for (const [material, base] of record.baseOpacities.entries()) {
        material.opacity = dimmed ? Math.min(base, 0.08) : base;
      }
      for (const material of record.materials) {
        const base = record.baseEmissiveIntensities.get(material) ?? material.emissiveIntensity;
        if (dimmed) material.emissiveIntensity = base * 0.06;
        else if (boosted) material.emissiveIntensity = Math.max(base, 0.4) * 2.2;
        else material.emissiveIntensity = base;
      }
      record.statusMaterial.opacity = dimmed ? 0.06 : 0.95;
      if (record.raceway) {
        const pm = record.raceway.points.material as THREE.PointsMaterial;
        pm.opacity = dimmed ? 0.05 : 0.95;
      }
    }
  }

  public clearBlastHighlight(): void {
    this.applyBlastHighlight(null);
  }

  /** Animate glowing status rings and raceway particles. */
  public update(delta: number, time: number): void {
    for (const pulse of this.pulses) {
      const wave = 0.5 + 0.5 * Math.sin(time * pulse.rate + pulse.phase);
      pulse.material.emissiveIntensity =
        pulse.baseIntensity * (0.45 + 0.75 * wave);
    }

    for (const record of this.vaults.values()) {
      const raceway = record.raceway;
      if (!raceway) continue;

      for (let i = 0; i < raceway.count; i++) {
        const prev = raceway.angles[i] ?? 0;
        const a = prev + raceway.angularSpeed * delta;
        raceway.angles[i] = a;
        raceway.positions[i * 3] = raceway.center.x + raceway.radius * Math.cos(a);
        raceway.positions[i * 3 + 1] =
          raceway.center.y + Math.sin(a * 4.0) * 0.06;
        raceway.positions[i * 3 + 2] = raceway.center.z + raceway.radius * Math.sin(a);
      }
      const attr = raceway.points.geometry.getAttribute('position');
      attr.needsUpdate = true;
    }
  }

  public clear(): void {
    for (const record of this.vaults.values()) {
      this.group.remove(record.group);
      record.group.traverse((child) => {
        const mesh = child as THREE.Mesh;
        if (mesh.isMesh) {
          mesh.geometry.dispose();
          const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
          mats.forEach((m) => m.dispose());
        }
      });
      if (record.raceway) {
        this.group.remove(record.raceway.points);
        record.raceway.points.geometry.dispose();
        (record.raceway.points.material as THREE.Material).dispose();
      }
    }
    this.vaults.clear();
    this.pulses = [];
  }

  public dispose(): void {
    this.clear();
    this.scene.remove(this.group);
    this.group.clear();
  }
}
