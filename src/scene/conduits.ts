import * as THREE from 'three';

export type ConduitType =
  | 'heartbeat-riser'
  | 'etcd-backing'
  | 'client-stream'
  | 'api-bridge'
  | 'framework-bypass';

export interface ConduitEdge {
  id: string;
  type: ConduitType;
  source: THREE.Vector3;
  target: THREE.Vector3;
  sourceType?: string;
  targetType?: string;
}

export interface ConduitRecord {
  id: string;
  type: ConduitType;
  curve: THREE.Curve<THREE.Vector3>;
  mesh: THREE.Mesh;
  radius: number;
}

const STANDARD_RADIUS = 0.06;
const MAIN_RADIUS = 0.09;

const TYPE_COLORS: Record<ConduitType, number> = {
  'heartbeat-riser': 0x00ffcc,
  'etcd-backing': 0xff6600,
  'client-stream': 0x4488ff,
  'api-bridge': 0x88ff44,
  'framework-bypass': 0xcc44ff,
};

function createMaterial(type: ConduitType): THREE.MeshStandardMaterial {
  const color = TYPE_COLORS[type];
  return new THREE.MeshStandardMaterial({
    color,
    roughness: 0.2,
    metalness: 0.8,
    transparent: true,
    opacity: 0.45,
    emissive: color,
    emissiveIntensity: 0.2,
  });
}

function buildHeartbeatRiserCurve(src: THREE.Vector3, tgt: THREE.Vector3): THREE.Curve<THREE.Vector3> {
  const path = new THREE.CurvePath<THREE.Vector3>();
  const p0 = src.clone();
  const p1 = new THREE.Vector3(src.x - 0.6, src.y, src.z);
  const p2 = new THREE.Vector3(src.x - 0.6, tgt.y, tgt.z);
  const p3 = tgt.clone();

  path.add(new THREE.LineCurve3(p0, p1));
  path.add(new THREE.LineCurve3(p1, p2));
  path.add(new THREE.LineCurve3(p2, p3));

  return path;
}

function buildEtcdBackingCurve(src: THREE.Vector3, tgt: THREE.Vector3): THREE.Curve<THREE.Vector3> {
  // Drops backward from API server down to etcd vault behind it.
  const dropOffset = 0.8;
  const backOffset = 1.2;

  const p0 = src.clone();
  const p1 = new THREE.Vector3(src.x, src.y - dropOffset, src.z);
  const p2 = new THREE.Vector3(src.x, src.y - dropOffset, src.z - backOffset);
  const p3 = new THREE.Vector3(tgt.x, tgt.y, tgt.z);

  const curve = new THREE.CatmullRomCurve3([p0, p1, p2, p3], false, 'catmullrom', 0.5);
  return curve;
}

function buildClientStreamCurve(src: THREE.Vector3, tgt: THREE.Vector3): THREE.Curve<THREE.Vector3> {
  // Sweeping arch from distant high slab down into the penthouse canopy.
  const midY = Math.max(src.y, tgt.y) + 2.0;
  const midX = (src.x + tgt.x) / 2;
  const midZ = (src.z + tgt.z) / 2;

  const p0 = src.clone();
  const p1 = new THREE.Vector3(midX, midY, midZ);
  const p2 = tgt.clone();

  const curve = new THREE.CatmullRomCurve3([p0, p1, p2], false, 'catmullrom', 0.5);
  return curve;
}

function buildApiBridgeCurve(src: THREE.Vector3, tgt: THREE.Vector3): THREE.Curve<THREE.Vector3> {
  // Straight horizontal connector pipe.
  const p0 = src.clone();
  const p1 = tgt.clone();
  return new THREE.LineCurve3(p0, p1);
}

function buildFrameworkBypassCurve(src: THREE.Vector3, tgt: THREE.Vector3): THREE.Curve<THREE.Vector3> {
  // Lateral connector between framework nodes.
  const midX = (src.x + tgt.x) / 2;
  const midY = (src.y + tgt.y) / 2;
  const midZ = (src.z + tgt.z) / 2;
  const lateralOffset = 0.5;

  const p0 = src.clone();
  const p1 = new THREE.Vector3(midX, midY, midZ + lateralOffset);
  const p2 = tgt.clone();

  const curve = new THREE.CatmullRomCurve3([p0, p1, p2], false, 'catmullrom', 0.5);
  return curve;
}

function buildCurve(edge: ConduitEdge): THREE.Curve<THREE.Vector3> {
  switch (edge.type) {
    case 'heartbeat-riser':
      return buildHeartbeatRiserCurve(edge.source, edge.target);
    case 'etcd-backing':
      return buildEtcdBackingCurve(edge.source, edge.target);
    case 'client-stream':
      return buildClientStreamCurve(edge.source, edge.target);
    case 'api-bridge':
      return buildApiBridgeCurve(edge.source, edge.target);
    case 'framework-bypass':
      return buildFrameworkBypassCurve(edge.source, edge.target);
    default:
      return new THREE.LineCurve3(edge.source.clone(), edge.target.clone());
  }
}

function getRadiusForType(type: ConduitType): number {
  if (type === 'heartbeat-riser' || type === 'etcd-backing') {
    return MAIN_RADIUS;
  }
  return STANDARD_RADIUS;
}

export class ConduitManager {
  private scene: THREE.Scene;
  private conduits: Map<string, ConduitRecord> = new Map();
  private group: THREE.Group;

  constructor(scene: THREE.Scene) {
    this.scene = scene;
    this.group = new THREE.Group();
    this.group.name = 'ConduitGroup';
    this.scene.add(this.group);
  }

  /**
   * Generate conduit meshes for all provided edges.
   * Existing conduits with the same ID are replaced.
   */
  public generate(edges: ConduitEdge[]): void {
    // Remove existing conduits that are not in the new edge list
    const newIds = new Set(edges.map((e) => e.id));
    for (const [id] of this.conduits.entries()) {
      if (!newIds.has(id)) {
        this.removeConduit(id);
      }
    }

    for (const edge of edges) {
      // If conduit already exists, dispose old one and recreate
      if (this.conduits.has(edge.id)) {
        this.removeConduit(edge.id);
      }

      const curve = buildCurve(edge);
      const radius = getRadiusForType(edge.type);
      const geometry = new THREE.TubeGeometry(curve, 40, radius, 12, false);
      const material = createMaterial(edge.type);
      const mesh = new THREE.Mesh(geometry, material);
      mesh.name = `conduit-${edge.id}`;
      mesh.castShadow = false;
      mesh.receiveShadow = false;

      this.group.add(mesh);

      const record: ConduitRecord = {
        id: edge.id,
        type: edge.type,
        curve,
        mesh,
        radius,
      };

      this.conduits.set(edge.id, record);
    }
  }

  /**
   * Returns all conduit curves for use by FlowParticleSystem.
   */
  public getConduitCurves(): ConduitRecord[] {
    return Array.from(this.conduits.values());
  }

  /**
   * Get a specific conduit record by ID.
   */
  public getConduit(id: string): ConduitRecord | undefined {
    return this.conduits.get(id);
  }

  /**
   * Remove a single conduit by ID.
   */
  private removeConduit(id: string): void {
    const record = this.conduits.get(id);
    if (!record) return;

    this.group.remove(record.mesh);
    record.mesh.geometry.dispose();
    if (Array.isArray(record.mesh.material)) {
      record.mesh.material.forEach((m) => m.dispose());
    } else {
      record.mesh.material.dispose();
    }
    this.conduits.delete(id);
  }

  /**
   * Clear all conduits from the scene and internal state.
   */
  public clear(): void {
    for (const id of Array.from(this.conduits.keys())) {
      this.removeConduit(id);
    }
  }

  /**
   * Dispose all resources and remove the group from the scene.
   */
  public dispose(): void {
    this.clear();
    this.scene.remove(this.group);
    this.group.clear();
  }
}