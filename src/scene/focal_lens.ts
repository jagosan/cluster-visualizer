/**
 * SPEC-13 / TASK-CV-1406: Incident Focal Lens (Blast Radius Focus Mode).
 *
 * Implements the dependency blast-radius focal lens described in SPEC-13 §3.6.2
 * and ADR-1304. Triggered by clicking a failed workload or pressing `KeyB`, the
 * lens:
 *   - dims unrelated cluster components to 15% opacity (0.15);
 *   - illuminates upstream ingress conduits, downstream database connections and
 *     hosting node chassis with an amber/red energy aura;
 *   - smoothly restores normal opacity on deactivation (`deactivateLens()`, `Esc`,
 *     or a second `KeyB` toggle).
 *
 * The blast radius is computed by traversing the supplied dependency graph in both
 * directions from the focused target: upstream dependencies (ingress / callers),
 * downstream dependencies (databases / subterranean vaults / callees), and the
 * hosting node chassis — i.e. the full connected component reachable from the
 * incident.
 */

import * as THREE from 'three';

// ---------------------------------------------------------------------------
// Public contracts (SPEC-13 §3.5 `FocalLensState`)
// ---------------------------------------------------------------------------

/** Live snapshot of the focal lens state (SPEC-13 §3.5). */
export interface FocalLensState {
  /** Whether the lens is currently dimming unrelated components. */
  isActive: boolean;
  /** Id of the workload under focus, or null while deactivated. */
  focusedTargetId: string | null;
  /** Opacity applied to unrelated components while active (default 0.15). */
  dimmedOpacity: number;
  /** Node ids within the blast radius (focused target + reachable dependencies). */
  blastRadiusNodeIds: Set<string>;
  /** Edge ids connecting two blast-radius nodes (illuminated conduits). */
  blastRadiusEdgeIds: Set<string>;
}

/** Minimal node descriptor accepted by `setGraph`. */
export interface FocalLensNode {
  id: string;
  name?: string;
  layer?: string;
  kind?: string;
}

/** Minimal edge descriptor accepted by `setGraph` (source/target are node ids). */
export interface FocalLensEdge {
  id?: string;
  source: string;
  target: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Default dim opacity for unrelated components (SPEC-13 §3.6.2: 15%). */
const DEFAULT_DIM_OPACITY = 0.15;

/** Amber energy aura used to illuminate blast-radius components. */
const AURA_AMBER = 0xffb020;
/** Red energy aura accent blended into the amber pulse. */
const AURA_RED = 0xff4444;

/** Node sphere radius (world units). */
const NODE_RADIUS = 0.45;
/** Horizontal spacing between graph nodes in the auto-layout grid. */
const GRID_SPACING = 2.6;

/** Exponential smoothing rate for opacity transitions (per second). */
const OPACITY_SMOOTHING = 6;

// ---------------------------------------------------------------------------
// IncidentFocalLens
// ---------------------------------------------------------------------------

/**
 * Owns the dependency blast-radius focal lens: a lightweight overlay of graph nodes
 * and conduit edges that dims unrelated components to `dimmedOpacity` while
 * illuminating everything within the focused target's blast radius.
 */
export class IncidentFocalLens {
  private readonly scene: THREE.Scene;

  // Graph topology (set via setGraph).
  private nodes: FocalLensNode[] = [];
  private edges: FocalLensEdge[] = [];
  /** nodeId -> neighbour node ids (undirected adjacency for blast traversal). */
  private readonly adjacency: Map<string, Set<string>> = new Map();

  // Overlay visuals.
  private readonly lensGroup = new THREE.Group();
  private readonly nodeMeshes: Map<string, THREE.Mesh> = new Map();
  private readonly nodeMaterials: Map<string, THREE.MeshStandardMaterial> = new Map();
  private readonly edgeLines: Map<string, THREE.Line> = new Map();
  private readonly edgeMaterials: Map<string, THREE.LineBasicMaterial> = new Map();

  // Lens state.
  private isActive = false;
  private focusedTargetId: string | null = null;
  private dimmedOpacity = DEFAULT_DIM_OPACITY;
  private blastRadiusNodeIds = new Set<string>();
  private blastRadiusEdgeIds = new Set<string>();

  /** Accumulated time (seconds) driving the aura pulse. */
  private elapsed = 0;

  /** Reusable colors to avoid per-frame allocations during the aura pulse. */
  private readonly amberColor = new THREE.Color(AURA_AMBER);
  private readonly redColor = new THREE.Color(AURA_RED);

  private readonly boundKeyHandler: (event: KeyboardEvent) => void;

  constructor(scene: THREE.Scene) {
    this.scene = scene;

    this.boundKeyHandler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable)
      ) {
        return;
      }
      if (event.code === 'KeyB' || event.key === 'b' || event.key === 'B') {
        event.preventDefault();
        this.toggleLens();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        this.deactivateLens();
      }
    };
  }

  // -------------------------------------------------------------------------
  // Lifecycle
  // -------------------------------------------------------------------------

  /** Attach the overlay group to the scene and register the `KeyB`/`Esc` keys. */
  public initialize(_scene: THREE.Scene, _camera: THREE.Camera): void {
    this.lensGroup.name = 'incident_focal_lens';
    if (!this.lensGroup.parent) {
      this.scene.add(this.lensGroup);
    }
    window.addEventListener('keydown', this.boundKeyHandler);
  }

  /** Release every owned mesh, geometry and material and detach the overlay. */
  public dispose(): void {
    window.removeEventListener('keydown', this.boundKeyHandler);

    for (const mesh of this.nodeMeshes.values()) {
      this.lensGroup.remove(mesh);
      mesh.geometry.dispose();
    }
    for (const mat of this.nodeMaterials.values()) mat.dispose();

    for (const line of this.edgeLines.values()) {
      this.lensGroup.remove(line);
      line.geometry.dispose();
    }
    for (const mat of this.edgeMaterials.values()) mat.dispose();

    if (this.lensGroup.parent) {
      this.scene.remove(this.lensGroup);
    }

    this.nodeMeshes.clear();
    this.nodeMaterials.clear();
    this.edgeLines.clear();
    this.edgeMaterials.clear();
    this.adjacency.clear();
    this.nodes = [];
    this.edges = [];

    this.isActive = false;
    this.focusedTargetId = null;
    this.blastRadiusNodeIds.clear();
    this.blastRadiusEdgeIds.clear();
  }

  // -------------------------------------------------------------------------
  // Graph ingestion
  // -------------------------------------------------------------------------

  /**
   * Replace the dependency graph and rebuild the overlay visuals. Node positions are
   * derived from a deterministic grid layout (the lens owns its own lightweight
   * representation of the cluster topology).
   */
  public setGraph(
    nodes: Array<FocalLensNode>,
    edges: Array<FocalLensEdge>,
  ): void {
    this.clearVisuals();
    this.nodes = Array.isArray(nodes) ? nodes : [];
    this.edges = Array.isArray(edges) ? edges : [];

    // Build undirected adjacency for blast-radius traversal.
    this.adjacency.clear();
    const knownNodes = new Set(this.nodes.map((n) => n.id));
    for (const edge of this.edges) {
      if (!knownNodes.has(edge.source) || !knownNodes.has(edge.target)) continue;
      let srcSet = this.adjacency.get(edge.source);
      if (!srcSet) {
        srcSet = new Set<string>();
        this.adjacency.set(edge.source, srcSet);
      }
      srcSet.add(edge.target);

      let tgtSet = this.adjacency.get(edge.target);
      if (!tgtSet) {
        tgtSet = new Set<string>();
        this.adjacency.set(edge.target, tgtSet);
      }
      tgtSet.add(edge.source);
    }

    this.rebuildNodeMeshes();
    this.rebuildEdgeLines();

    // Reset to a fully-lit, non-dimmed state.
    this.deactivateLens();
  }

  // -------------------------------------------------------------------------
  // Lens activation / deactivation
  // -------------------------------------------------------------------------

  /**
   * Focus the lens on `targetId`: compute its blast radius and dim everything else
   * to `dimmedOpacity`. No-op if the target is not part of the graph.
   */
  public activateLens(targetId: string): void {
    if (!this.adjacency.has(targetId)) return;

    this.focusedTargetId = targetId;
    const radius = this.computeBlastRadius(targetId);
    this.blastRadiusNodeIds = radius.nodeIds;
    this.blastRadiusEdgeIds = radius.edgeIds;
    this.isActive = true;
  }

  /** Smoothly restore normal opacity and clear all highlights. */
  public deactivateLens(): void {
    this.isActive = false;
    this.focusedTargetId = null;
    this.blastRadiusNodeIds.clear();
    this.blastRadiusEdgeIds.clear();
  }

  /**
   * Toggle the lens. With a `targetId`, re-focus on it; without one, toggle the
   * existing focus off (or activate on the current target if not yet active).
   */
  public toggleLens(targetId?: string): void {
    if (this.isActive) {
      if (targetId === undefined || targetId === this.focusedTargetId) {
        this.deactivateLens();
      } else {
        this.activateLens(targetId);
      }
    } else if (targetId !== undefined && targetId !== '') {
      this.activateLens(targetId);
    }
  }

  // -------------------------------------------------------------------------
  // Frame update
  // -------------------------------------------------------------------------

  /**
   * Advance the aura pulse and smoothly interpolate every node/edge opacity toward
   * its target (1.0 when restored, `dimmedOpacity` when dimmed).
   */
  public update(deltaTime: number): void {
    const dt = Number.isFinite(deltaTime) ? deltaTime : 0;
    this.elapsed += dt;

    // Smoothing factor (exponential approach toward the target opacity).
    const k = dt > 0 ? 1 - Math.exp(-dt * OPACITY_SMOOTHING) : 1;
    const pulse = 0.5 + 0.5 * Math.sin(this.elapsed * 3.2);

    for (const [id, material] of this.nodeMaterials) {
      const inBlast = this.blastRadiusNodeIds.has(id);
      const targetOpacity = this.isActive ? (inBlast ? 1 : this.dimmedOpacity) : 1;
      material.opacity += (targetOpacity - material.opacity) * k;

      if (this.isActive && inBlast) {
        // Amber/red energy aura on blast-radius components.
        material.emissiveIntensity = 0.6 + 0.9 * pulse;
        this.amberColor.set(AURA_AMBER).lerp(this.redColor, pulse);
        material.emissive.copy(this.amberColor);
      } else {
        material.emissiveIntensity = 0;
      }
    }

    for (const [id, material] of this.edgeMaterials) {
      const inBlast = this.blastRadiusEdgeIds.has(id);
      const targetOpacity = this.isActive ? (inBlast ? 1 : this.dimmedOpacity) : 1;
      material.opacity += (targetOpacity - material.opacity) * k;

      if (this.isActive && inBlast) {
        // Illuminated conduit: amber→red energy aura with additive glow.
        this.amberColor.set(AURA_AMBER).lerp(this.redColor, pulse);
        material.color.copy(this.amberColor);
        material.linewidth = 1;
      } else {
        material.color.set(0xffffff);
        material.linewidth = 1;
      }
    }
  }

  // -------------------------------------------------------------------------
  // State accessor
  // -------------------------------------------------------------------------

  /** Snapshot of the current focal lens state. */
  public getState(): FocalLensState {
    return {
      isActive: this.isActive,
      focusedTargetId: this.focusedTargetId,
      dimmedOpacity: this.dimmedOpacity,
      blastRadiusNodeIds: this.blastRadiusNodeIds,
      blastRadiusEdgeIds: this.blastRadiusEdgeIds,
    };
  }

  // -------------------------------------------------------------------------
  // Blast radius computation
  // -------------------------------------------------------------------------

  /**
   * Breadth-first traversal from the focused target over the undirected adjacency:
   * upstream dependencies (ingress / callers), downstream dependencies (databases /
   * subterranean vaults / callees) and hosting node chassis all collapse into the
   * reachable component.
   */
  private computeBlastRadius(targetId: string): {
    nodeIds: Set<string>;
    edgeIds: Set<string>;
  } {
    const nodeIds = new Set<string>();
    nodeIds.add(targetId);

    const queue: string[] = [targetId];
    while (queue.length > 0) {
      const current = queue.shift();
      if (current === undefined) continue;
      const neighbours = this.adjacency.get(current);
      if (!neighbours) continue;
      for (const next of neighbours) {
        if (!nodeIds.has(next)) {
          nodeIds.add(next);
          queue.push(next);
        }
      }
    }

    // An edge is within the blast radius when both endpoints are reachable.
    const edgeIds = new Set<string>();
    for (const edge of this.edges) {
      const id = edge.id ?? `${edge.source}->${edge.target}`;
      if (nodeIds.has(edge.source) && nodeIds.has(edge.target)) {
        edgeIds.add(id);
      }
    }

    return { nodeIds, edgeIds };
  }

  // -------------------------------------------------------------------------
  // Visual construction
  // -------------------------------------------------------------------------

  /** Deterministic grid layout for the overlay nodes (XZ plane at y = 0). */
  private nodePosition(index: number): [number, number, number] {
    const cols = Math.max(1, Math.ceil(Math.sqrt(this.nodes.length)));
    const x = (index % cols) * GRID_SPACING;
    const z = Math.floor(index / cols) * GRID_SPACING;
    return [x - ((cols - 1) * GRID_SPACING) / 2, 0, z];
  }

  private rebuildNodeMeshes(): void {
    if (this.nodes.length === 0) return;

    const geometry = new THREE.SphereGeometry(NODE_RADIUS, 16, 12);
    for (let i = 0; i < this.nodes.length; i += 1) {
      const node = this.nodes[i];
      if (!node) continue;

      const material = new THREE.MeshStandardMaterial({
        color: 0x94a3b8,
        emissive: AURA_AMBER,
        emissiveIntensity: 0,
        transparent: true,
        opacity: 1,
        roughness: 0.35,
        metalness: 0.2,
      });

      const mesh = new THREE.Mesh(geometry, material);
      mesh.name = `focal_node_${node.id}`;
      const [px, py, pz] = this.nodePosition(i);
      mesh.position.set(px, py, pz);

      // Keep a reference to the node id for highlight lookups.
      mesh.userData.focalNodeId = node.id;

      this.lensGroup.add(mesh);
      this.nodeMeshes.set(node.id, mesh);
      this.nodeMaterials.set(node.id, material);
    }
  }

  private rebuildEdgeLines(): void {
    if (this.edges.length === 0) return;

    for (const edge of this.edges) {
      const sourceMesh = this.nodeMeshes.get(edge.source);
      const targetMesh = this.nodeMeshes.get(edge.target);
      if (!sourceMesh || !targetMesh) continue;

      const id = edge.id ?? `${edge.source}->${edge.target}`;
      const points: THREE.Vector3[] = [
        sourceMesh.position.clone(),
        targetMesh.position.clone(),
      ];
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      const material = new THREE.LineBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 1,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });

      const line = new THREE.Line(geometry, material);
      line.name = `focal_edge_${id}`;
      line.userData.focalEdgeId = id;

      this.lensGroup.add(line);
      this.edgeLines.set(id, line);
      this.edgeMaterials.set(id, material);
    }
  }

  private clearVisuals(): void {
    for (const mesh of this.nodeMeshes.values()) {
      this.lensGroup.remove(mesh);
      mesh.geometry.dispose();
    }
    for (const mat of this.nodeMaterials.values()) mat.dispose();

    for (const line of this.edgeLines.values()) {
      this.lensGroup.remove(line);
      line.geometry.dispose();
    }
    for (const mat of this.edgeMaterials.values()) mat.dispose();

    this.nodeMeshes.clear();
    this.nodeMaterials.clear();
    this.edgeLines.clear();
    this.edgeMaterials.clear();
  }
}
