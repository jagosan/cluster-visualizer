import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { FlowParticleSystem } from './flow_particles.js';
import { ConduitManager } from './conduits.js';
import type { ConduitEdge, ConduitType } from './conduits.js';
import { LayerTrayManager } from './layer_trays.js';
import type { MachineShapeData } from './layer_trays.js';
import { SubterraneanVaultManager } from './subterranean_vaults.js';
import type { RemoteServiceResourceData, VaultBlastState } from './subterranean_vaults.js';
import { PlungeConduitManager, estimateVaultLatencyMs, reachabilityFromPhase } from './plunge_conduits.js';
import type { PlungeConduitSpec } from './plunge_conduits.js';
import { FlankLabelManager } from './flank_labels.js';
import { DiffCardManager } from './diff_card.js';
import { LayoutTransitionController } from './layout_transition.js';
// SPEC-09 / TASK-CV-1001: procedural proportional pod capsules (ADR-01).
import { PodCapsuleManager } from './pod_capsules.js';
import type { PodGeometryData } from './pod_capsules.js';

export interface ClusterNodeData {
  id: string;
  layer: string;
  kind: string;
  name: string;
  namespace: string;
  version: string;
  image?: string;
  digest?: string;
  status: string;
  metrics?: Record<string, any>;
  spatial: {
    x: number;
    y: number;
    z: number;
    asset_type: string;
  };
  diffStatus?: 'identical' | 'version_skew' | 'missing' | 'added';
  diffDetails?: string[];
  // SPEC-09: proportional capsule dimensions computed by the ingestion layout.
  pod_geometry?: PodGeometryData | null;
}

/**
 * SPEC-09 §3: pod components render as procedural proportional capsules
 * instead of cloning the static `Cuboid_Pod` GLB prototype.
 */
export function isPodComponent(node: ClusterNodeData): boolean {
  const assetKey = node.spatial?.asset_type ?? '';
  return (
    assetKey === 'Cuboid_Pod' ||
    assetKey === 'Pod_Cylinder' ||
    assetKey === 'Module_PodCapsule' ||
    assetKey === 'Database_Postgres' ||
    assetKey === 'Cache_Redis' ||
    (node.layer === 'workload' && node.kind === 'Pod')
  );
}

export interface ClusterGraphData {
  metadata: {
    cluster_name: string;
    kubernetes_version: string;
    distribution: string;
    node_count: number;
    pod_count: number;
  };
  nodes: ClusterNodeData[];
  edges: {
    source: string;
    target: string;
    flow_type: string;
    protocol: string;
    direction: string;
    volume_label?: string;
  }[];
  diff_summary?: {
    identical_nodes: number;
    version_skew_nodes: number;
    missing_in_target: number;
    added_in_target: number;
  };
  // SPEC-08 / TASK-CV-903: physical machine chassis shapes (optional on the wire)
  machine_shapes?: MachineShapeData[];
  // SPEC-08 / TASK-CV-904: managed cloud service vaults (optional on the wire)
  subterranean_resources?: RemoteServiceResourceData[];
}

export class ClusterViewport {
  public container: HTMLElement;
  public scene: THREE.Scene;
  public camera: THREE.PerspectiveCamera;
  public renderer: THREE.WebGLRenderer;
  public controls: OrbitControls;
  public flowSystem: FlowParticleSystem;
  public conduitManager: ConduitManager;
  public layerTrayManager: LayerTrayManager;
  public flankLabelManager: FlankLabelManager;
  public diffCard: DiffCardManager;
  // TASK-CV-904: Sub-Level B2 managed cloud vaults + vertical plunge conduits.
  public vaultManager: SubterraneanVaultManager;
  public plungeConduitManager: PlungeConduitManager;
  public onVaultSelected?: (state: VaultBlastState | null) => void;
  // TASK-CV-904: KeyB subterranean camera preset tween state.
  private subterraneanTween: {
    elapsed: number;
    duration: number;
    fromPos: THREE.Vector3;
    toPos: THREE.Vector3;
    fromTarget: THREE.Vector3;
    toTarget: THREE.Vector3;
  } | null = null;
  private subterraneanFocused = false;
  private assetPrototypes: Map<string, THREE.Object3D> = new Map();
  private nodeMeshes: Map<string, THREE.Object3D> = new Map();
  // SPEC-09: shared capsule material cache + emissive pulse driver.
  public podCapsuleManager = new PodCapsuleManager();
  private raycaster = new THREE.Raycaster();
  private mouse = new THREE.Vector2(-1000, -1000);
  public onNodeSelected?: (node: ClusterNodeData | null) => void;
  public onNodeHovered?: (node: ClusterNodeData | null, clientX: number, clientY: number) => void;
  public clusterData: ClusterGraphData | null = null;
  private selectedNodeId: string | null = null;

  public getSelectedNodeId(): string | null {
    return this.selectedNodeId;
  }
  private hoveredObject: THREE.Object3D | null = null;
  
  // References for animation of diff visuals
  private pulsingMaterials: THREE.Material[] = [];
  private clock = new THREE.Clock();

  // Dynamic mutation animation maps
  private animatingEntrances: Map<string, { mesh: THREE.Object3D; startTime: number; duration: number }> = new Map();
  private animatingDecays: Map<string, { mesh: THREE.Object3D; startTime: number; duration: number }> = new Map();

  // Dual-mode layout controller (Skyscraper <-> Latency Field)
  public layoutController: LayoutTransitionController = new LayoutTransitionController();

  constructor(container: HTMLElement, label: string) {
    this.container = container;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0c1117);

    this.camera = new THREE.PerspectiveCamera(
      45,
      container.clientWidth / container.clientHeight,
      0.1,
      1000
    );
    this.camera.position.set(16, 7, 20);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.1;
    container.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.05;
    this.controls.target.set(0, 3.5, 0);
    this.controls.update();

    this.setupLighting();
    this.setupGrid();

    this.flowSystem = new FlowParticleSystem();
    this.scene.add(this.flowSystem.group);

    this.conduitManager = new ConduitManager(this.scene);
    this.layerTrayManager = new LayerTrayManager(this.scene);
    this.flankLabelManager = new FlankLabelManager(this.scene);
    this.vaultManager = new SubterraneanVaultManager(this.scene);
    this.plungeConduitManager = new PlungeConduitManager(this.scene);
    
    // Initialize DiffCardManager
    this.diffCard = new DiffCardManager(this.container);

    // Label overlay
    const titleTag = document.createElement('div');
    titleTag.className = 'viewport-title';
    titleTag.innerText = label;
    container.appendChild(titleTag);

    // Event listeners
    this.renderer.domElement.addEventListener('mousemove', this.onMouseMove.bind(this));
    this.renderer.domElement.addEventListener('click', this.onClick.bind(this));
    window.addEventListener('resize', this.onResize.bind(this));
  }

  private setupLighting() {
    const ambient = new THREE.AmbientLight(0xddeeff, 0.7);
    this.scene.add(ambient);

    const dirLight = new THREE.DirectionalLight(0xffffff, 1.4);
    dirLight.position.set(10, 20, 10);
    this.scene.add(dirLight);

    const blueRim = new THREE.DirectionalLight(0x0088ff, 0.8);
    blueRim.position.set(-10, -5, -10);
    this.scene.add(blueRim);
  }

  private setupGrid() {
    const grid = new THREE.GridHelper(40, 40, 0x1f2937, 0x111827);
    grid.position.y = -5.0; // Base foundation level
    this.scene.add(grid);
  }

  public async loadAssets(glbUrl: string): Promise<void> {
    const loader = new GLTFLoader();
    const gltf = await loader.loadAsync(glbUrl);
    gltf.scene.traverse((child) => {
      if (child.name) {
        this.assetPrototypes.set(child.name, child);
      }
    });
  }

  public loadGraph(data: ClusterGraphData): void {
    this.setClusterData(data);
  }

  public setClusterData(data: ClusterGraphData, diffMap?: Map<string, { status: any; diffDetails: string[] }>) {
    this.clusterData = data;
    // Clear existing nodes, conduits, trays, and flank labels
    this.nodeMeshes.forEach((mesh) => this.scene.remove(mesh));
    this.nodeMeshes.clear();
    this.flowSystem.clear();
    this.conduitManager.clear();
    this.layerTrayManager.clear();
    this.flankLabelManager.clear();
    this.vaultManager.clearBlastHighlight();
    this.podCapsuleManager.clear(); // SPEC-09: drop stale capsule refs
    this.pulsingMaterials = []; // Reset animation refs

    // Determine cluster characteristics for tower trays and flank labels
    const workerCount = data.nodes.filter(
      (n) => n.layer === 'node' || n.kind.toLowerCase() === 'node'
    ).length || 3;
    const hasRay = data.nodes.some(
      (n) => n.name.toLowerCase().includes('ray') || n.kind.toLowerCase().includes('ray')
    );

    // Build layered architectural trays and outer structural cage.
    // TASK-CV-903: feed the snapshot's machine_shapes so chassis footprints,
    // capacity materials, and accelerator power bays render per machine.
    this.layerTrayManager.setMachineShapes(data.machine_shapes);
    this.layerTrayManager.buildTowerTrays(workerCount, hasRay);

    // Build flank typographic billboard labels
    this.flankLabelManager.buildLabels(workerCount, hasRay);

    const nodePositions = new Map<string, THREE.Vector3>();

    // Spawn nodes
    for (const node of data.nodes) {
      if (diffMap && diffMap.has(node.id)) {
        const d = diffMap.get(node.id)!;
        node.diffStatus = d.status;
        node.diffDetails = d.diffDetails;
      }

      // SPEC-09 / TASK-CV-1001: pods are procedural proportional capsules
      // (CapsuleGeometry sized from CPU/Memory requests) instead of clones
      // of the static Cuboid_Pod prototype. Diff accents come from the
      // capsule's own containment brackets, not applyDiffVisuals.
      let instance: THREE.Object3D;
      if (isPodComponent(node)) {
        instance = this.podCapsuleManager.create(node, node.diffStatus);
      } else {
        const proto = this.assetPrototypes.get(node.spatial.asset_type) || this.createFallbackMesh(node);
        instance = proto.clone(true);
        // Apply diff color accent rectangular brackets / glow
        this.applyDiffVisuals(instance, node.diffStatus);
      }
      instance.position.set(node.spatial.x, node.spatial.y, node.spatial.z);
      instance.userData = { ...instance.userData, nodeData: node };

      this.scene.add(instance);
      this.nodeMeshes.set(node.id, instance);
      nodePositions.set(node.id, new THREE.Vector3(node.spatial.x, node.spatial.y, node.spatial.z));

      // Register dual coordinates for layout transitions
      const arch = { x: node.spatial.x, y: node.spatial.y, z: node.spatial.z };
      const rawLat = (node as Record<string, any>).latency_spatial;
      const latency = rawLat ? { x: Number(rawLat.x ?? 0), y: Number(rawLat.y ?? 0), z: Number(rawLat.z ?? 0) } : {
        x: arch.x * 0.7,
        y: Math.max(0.5, arch.y * 0.4),
        z: arch.z * 0.7,
      };
      this.layoutController.registerNode(node.id, arch, latency);
    }

    // Connect conduits and animated flow pulses
    const conduitEdges: ConduitEdge[] = [];
    for (let i = 0; i < data.edges.length; i++) {
      const edge = data.edges[i]!;
      const srcPos = nodePositions.get(edge.source);
      const tgtPos = nodePositions.get(edge.target);
      if (!srcPos || !tgtPos) continue;

      let ctype: ConduitType = 'heartbeat-riser';
      const p = edge.protocol.toLowerCase();
      const v = (edge.volume_label || '').toLowerCase();
      const s = edge.source.toLowerCase();

      if (p.includes('heartbeat') || v.includes('heartbeat') || s.includes('kubelet')) {
        ctype = 'heartbeat-riser';
      } else if (p.includes('2379') || v.includes('raft') || s.includes('apiserver') && edge.target.includes('etcd')) {
        ctype = 'etcd-backing';
      } else if (s.includes('client') || v.includes('watch') || v.includes('list')) {
        ctype = 'client-stream';
      } else if (v.includes('peer') || (s.includes('apiserver') && edge.target.includes('apiserver'))) {
        ctype = 'api-bridge';
      } else if (edge.flow_type === 'framework_control' || v.includes('tensor') || s.includes('ray')) {
        ctype = 'framework-bypass';
      }

      conduitEdges.push({
        id: `conduit-${i}-${edge.source}-${edge.target}`,
        type: ctype,
        source: srcPos,
        target: tgtPos,
      });
    }

    // Build 3D conduit pipes
    this.conduitManager.generate(conduitEdges);

    // Pulse particles along exact conduit curves
    const records = this.conduitManager.getConduitCurves();
    for (const rec of records) {
      let colorHex = 0x00ffcc;
      let speed = 0.25;
      if (rec.type === 'heartbeat-riser') {
        colorHex = 0x10b981; // Emerald green heartbeat pulse
        speed = 0.35;
      } else if (rec.type === 'etcd-backing') {
        colorHex = 0xf59e0b; // Amber etcd write pulse
        speed = 0.40;
      } else if (rec.type === 'client-stream') {
        colorHex = 0xffd700; // Gold client query stream
        speed = 0.50;
      } else if (rec.type === 'api-bridge') {
        colorHex = 0x06b6d4; // Cyan inter-server sync
        speed = 0.30;
      } else if (rec.type === 'framework-bypass') {
        colorHex = 0xa855f7; // Purple tensor bypass stream
        speed = 0.60;
      }

      this.flowSystem.addCurveParticle(rec.curve, colorHex, speed, 0.12);
    }

    // TASK-CV-904: Sub-Level B2/B3 managed cloud vaults + vertical plunge
    // conduits routed from worker-deck pods through the kro manifold.
    this.buildSubterraneanLayer(data, nodePositions);
  }

  /**
   * TASK-CV-904: Spawn the vault strata from `subterranean_resources` and
   * wire plunge conduits from worker-deck pods (preferring real snapshot
   * edges into vault ids, falling back to manifold fan-out) down through
   * the kro manifold hub at Y = -4.8.
   */
  private buildSubterraneanLayer(
    data: ClusterGraphData,
    nodePositions: Map<string, THREE.Vector3>,
  ): void {
    const resources = data.subterranean_resources ?? [];
    this.vaultManager.setResources(resources);
    this.subterraneanFocused = false;

    const specs: PlungeConduitSpec[] = [];
    if (resources.length === 0) {
      this.plungeConduitManager.generate(specs);
      return;
    }

    const resourceById = new Map(resources.map((r) => [r.id, r]));

    // Conduits declared as edges into vault ids carry real telemetry labels.
    const explicit = new Set<string>();
    for (const edge of data.edges) {
      const vault = resourceById.get(edge.target) ?? resourceById.get(edge.source);
      if (!vault) continue;
      const podId = resourceById.has(edge.target) ? edge.source : edge.target;
      const podPos = nodePositions.get(podId);
      const vaultPos = this.vaultManager.getVaultWorldPosition(vault.id);
      if (!podPos || !vaultPos) continue;
      explicit.add(vault.id);
      specs.push({
        id: `plunge-${podId}-${vault.id}`,
        source: podPos.clone(),
        target: vaultPos,
        latencyMs: estimateVaultLatencyMs(vault),
        reachability: reachabilityFromPhase(vault.status_phase),
        vaultId: vault.id,
      });
    }

    // Fan-out: every vault without an explicit edge gets fed from a
    // round-robin worker-deck pod so the manifold plumbing reads complete.
    const workerPods = data.nodes.filter(
      (n) => n.layer === 'node' || n.layer === 'workload' || n.kind.toLowerCase() === 'node',
    );
    let podCursor = 0;
    for (const vault of resources) {
      if (explicit.has(vault.id)) continue;
      const vaultPos = this.vaultManager.getVaultWorldPosition(vault.id);
      if (!vaultPos) continue;

      let sourcePos: THREE.Vector3 | null = null;
      if (workerPods.length > 0) {
        const pod = workerPods[podCursor % workerPods.length];
        podCursor++;
        sourcePos = pod ? nodePositions.get(pod.id) ?? null : null;
        if (!sourcePos && pod) {
          sourcePos = new THREE.Vector3(pod.spatial.x, Math.max(pod.spatial.y, 1.0), pod.spatial.z);
        }
      }
      if (!sourcePos) sourcePos = new THREE.Vector3(vaultPos.x + 2.0, 2.5, vaultPos.z);

      specs.push({
        id: `plunge-manifold-${vault.id}`,
        source: sourcePos.clone(),
        target: vaultPos,
        latencyMs: estimateVaultLatencyMs(vault),
        reachability: reachabilityFromPhase(vault.status_phase),
        vaultId: vault.id,
      });
    }

    this.plungeConduitManager.generate(specs);
  }

  /**
   * TASK-CV-904 / SPEC-08 §7.2: Subterranean camera preset (KeyB).
   * Smoothly tweens the orbit orbit to re-center on Y = -5.0 with a slight
   * upward tilt framing the foundational root system. Toggles back to the
   * surface preset. Returns true when diving down, false when surfacing.
   */
  public toggleSubterraneanView(durationMs = 1200): boolean {
    this.subterraneanFocused = !this.subterraneanFocused;
    const toPos = this.subterraneanFocused
      ? new THREE.Vector3(14.5, -1.2, 18.5)
      : new THREE.Vector3(16, 7, 20);
    const toTarget = this.subterraneanFocused
      ? new THREE.Vector3(0, -5.0, 0)
      : new THREE.Vector3(0, 3.5, 0);

    this.subterraneanTween = {
      elapsed: 0,
      duration: Math.max(0.05, durationMs / 1000),
      fromPos: this.camera.position.clone(),
      toPos,
      fromTarget: this.controls.target.clone(),
      toTarget,
    };
    return this.subterraneanFocused;
  }

  public isSubterraneanView(): boolean {
    return this.subterraneanFocused;
  }

  public addNode(node: ClusterNodeData): void {
    // SPEC-09 / TASK-CV-1001 (handleTopologyMutation path): newly observed
    // pods materialize as procedural proportional capsules.
    let instance: THREE.Object3D;
    if (isPodComponent(node)) {
      instance = this.podCapsuleManager.create(node, 'added');
    } else {
      const proto =
        this.assetPrototypes.get(node.spatial?.asset_type || 'Cuboid_Pod') ||
        this.createFallbackMesh(node);
      instance = proto.clone(true);
      this.applyDiffVisuals(instance, 'added');
    }
    const sx = node.spatial?.x ?? 0;
    const sy = node.spatial?.y ?? 0.75;
    const sz = node.spatial?.z ?? 0;
    instance.position.set(sx, sy, sz);
    instance.scale.set(0.1, 0.1, 0.1);
    instance.userData = { ...instance.userData, nodeData: node };

    this.scene.add(instance);
    this.nodeMeshes.set(node.id, instance);

    this.animatingEntrances.set(node.id, {
      mesh: instance,
      startTime: this.clock.getElapsedTime(),
      duration: 0.6,
    });

    if (this.clusterData?.nodes) {
      this.clusterData.nodes.push(node);
    }
  }

  public removeNode(nodeId: string): void {
    const mesh = this.nodeMeshes.get(nodeId);
    if (!mesh) return;

    // SPEC-09: capsule materials are shared via the PodCapsuleManager cache;
    // clone before applying the decay wireframe so siblings stay intact.
    if (mesh.userData.podCapsule) {
      this.podCapsuleManager.untrack(mesh);
      this.isolatePodMaterials(mesh);
    }

    mesh.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        const meshChild = child as THREE.Mesh;
        const materials = Array.isArray(meshChild.material) ? meshChild.material : [meshChild.material];
        materials.forEach((mat) => {
          mat.transparent = true;
          mat.opacity = 0.45;
          mat.depthWrite = false;
          if ((mat as THREE.MeshStandardMaterial).isMeshStandardMaterial) {
            const std = mat as THREE.MeshStandardMaterial;
            std.color.setHex(0xef4444);
            std.wireframe = true;
          }
        });
      }
    });

    this.animatingDecays.set(nodeId, {
      mesh,
      startTime: this.clock.getElapsedTime(),
      duration: 3.0,
    });

    if (this.clusterData?.nodes) {
      const idx = this.clusterData.nodes.findIndex((n) => n.id === nodeId);
      if (idx !== -1) {
        this.clusterData.nodes.splice(idx, 1);
      }
    }
  }

  public modifyNode(nodeId: string, diffDetails?: string[], status?: string): void {
    const mesh = this.nodeMeshes.get(nodeId);
    if (!mesh) return;

    const node = mesh.userData.nodeData as ClusterNodeData;
    if (!node) return;

    node.diffStatus = (status as any) || 'version_skew';
    node.diffDetails = diffDetails;

    // SPEC-09: for proportional capsules, swap in a cloned material (and the
    // capsule's own accent bracket) instead of mutating the shared material.
    if (mesh.userData.podCapsule) {
      this.isolatePodMaterials(mesh);
      const bracket = new THREE.Group();
      bracket.name = 'pod_skew_accent';
      const stripeMat = new THREE.MeshBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.85 });
      let h = (mesh.userData.podHeight as number | undefined) ?? 0;
      if (!h) {
        mesh.traverse((c) => {
          const ph = c.userData.podHeight as number | undefined;
          if (ph) h = ph;
        });
      }
      const crown = h || 0.7;
      for (let i = -1; i <= 1; i++) {
        const stripe = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.02, 0.14), stripeMat);
        stripe.position.set(i * 0.22, crown / 2 + 0.06, 0);
        bracket.add(stripe);
      }
      mesh.add(bracket);
      this.pulsingMaterials.push(stripeMat);
      return;
    }

    this.applyDiffVisuals(mesh, node.diffStatus);
  }

  /**
   * SPEC-09: deep-clone shared capsule materials on a pod object so that
   * per-node decay/diff mutations don't leak into the material cache.
   */
  private isolatePodMaterials(obj: THREE.Object3D): void {
    obj.traverse((child) => {
      const m = child as THREE.Mesh;
      if (!m.isMesh) return;
      if (Array.isArray(m.material)) {
        m.material = m.material.map((mat) => mat.clone());
      } else if (m.material) {
        m.material = m.material.clone();
      }
    });
  }

  private applyDiffVisuals(mesh: THREE.Object3D, status?: string) {
    if (!status) return;

    // Helper to traverse and modify materials
    const traverseAndModify = (obj: THREE.Object3D, modifier: (mat: THREE.Material) => void) => {
      obj.traverse((child) => {
        if ((child as THREE.Mesh).isMesh) {
          const meshChild = child as THREE.Mesh;
          if (Array.isArray(meshChild.material)) {
            meshChild.material.forEach(modifier);
          } else {
            modifier(meshChild.material);
          }
        }
      });
    };

    if (status === 'identical') {
      // Slate tone, roughness 0.4, subtle cyan contour brackets
      traverseAndModify(mesh, (mat) => {
        if ((mat as THREE.MeshStandardMaterial).isMeshStandardMaterial) {
          const stdMat = mat as THREE.MeshStandardMaterial;
          stdMat.color.setHex(0x1e293b);
          stdMat.roughness = 0.4;
          stdMat.metalness = 0.1;
          stdMat.emissive.setHex(0x000000);
        }
      });

      // Add subtle cyan contour brackets
      const bracketGeo = new THREE.EdgesGeometry(new THREE.BoxGeometry(1.2, 0.04, 0.9));
      const bracketMat = new THREE.LineBasicMaterial({
        color: 0x06b6d4, // Cyan
        transparent: true,
        opacity: 0.3,
      });
      const bracket = new THREE.LineSegments(bracketGeo, bracketMat);
      bracket.position.y = -0.15;
      mesh.add(bracket);

    } else if (status === 'added') {
      // Vibrant emerald tint / emission
      traverseAndModify(mesh, (mat) => {
        if ((mat as THREE.MeshStandardMaterial).isMeshStandardMaterial) {
          const stdMat = mat as THREE.MeshStandardMaterial;
          stdMat.color.setHex(0x10b981);
          stdMat.emissive.setHex(0x34d399);
          stdMat.emissiveIntensity = 0.6;
          stdMat.roughness = 0.3;
          stdMat.metalness = 0.2;
        }
      });

      // Holographic corner brackets: 8 corner line brackets with glowing green material
      const bracketMat = new THREE.LineBasicMaterial({
        color: 0x34d399,
        transparent: true,
        opacity: 0.8,
      });
      
      // Create a group for the brackets to animate them together
      const bracketGroup = new THREE.Group();
      bracketGroup.name = 'added_brackets';
      
      const size = 1.2;
      const h = 0.6;
      const d = 0.9;
      const cornerLen = 0.2;

      // Define 8 corners and their bracket lines
      const corners = [
        { x: -size/2, y: -h/2, z: -d/2, dx: 1, dy: 1, dz: 1 },
        { x: size/2, y: -h/2, z: -d/2, dx: -1, dy: 1, dz: 1 },
        { x: -size/2, y: h/2, z: -d/2, dx: 1, dy: -1, dz: 1 },
        { x: size/2, y: h/2, z: -d/2, dx: -1, dy: -1, dz: 1 },
        { x: -size/2, y: -h/2, z: d/2, dx: 1, dy: 1, dz: -1 },
        { x: size/2, y: -h/2, z: d/2, dx: -1, dy: 1, dz: -1 },
        { x: -size/2, y: h/2, z: d/2, dx: 1, dy: -1, dz: -1 },
        { x: size/2, y: h/2, z: d/2, dx: -1, dy: -1, dz: -1 },
      ];

      corners.forEach(c => {
        // Line along X
        const geoX = new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(c.x, c.y, c.z),
          new THREE.Vector3(c.x + c.dx * cornerLen, c.y, c.z)
        ]);
        const lineX = new THREE.Line(geoX, bracketMat);
        bracketGroup.add(lineX);

        // Line along Y
        const geoY = new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(c.x, c.y, c.z),
          new THREE.Vector3(c.x, c.y + c.dy * cornerLen, c.z)
        ]);
        const lineY = new THREE.Line(geoY, bracketMat);
        bracketGroup.add(lineY);

        // Line along Z
        const geoZ = new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(c.x, c.y, c.z),
          new THREE.Vector3(c.x, c.y, c.z + c.dz * cornerLen)
        ]);
        const lineZ = new THREE.Line(geoZ, bracketMat);
        bracketGroup.add(lineZ);
      });

      mesh.add(bracketGroup);
      this.pulsingMaterials.push(bracketMat);

    } else if (status === 'missing') {
      // Ghost Cuboid: Transparent, low opacity, no depth write
      traverseAndModify(mesh, (mat) => {
        mat.transparent = true;
        mat.opacity = 0.20;
        mat.depthWrite = false;
        if ((mat as THREE.MeshStandardMaterial).isMeshStandardMaterial) {
          const stdMat = mat as THREE.MeshStandardMaterial;
          stdMat.color.setHex(0x475569);
          stdMat.emissive.setHex(0x000000);
        }
      });

      // Add bright red dashed or wireframe contour cage
      const cageGeo = new THREE.EdgesGeometry(new THREE.BoxGeometry(1.3, 0.7, 1.0));
      const cageMat = new THREE.LineBasicMaterial({
        color: 0xef4444,
        transparent: true,
        opacity: 0.85,
      });
      const cage = new THREE.LineSegments(cageGeo, cageMat);
      mesh.add(cage);

    } else if (status === 'version_skew') {
      // Metallic amber housing
      traverseAndModify(mesh, (mat) => {
        if ((mat as THREE.MeshStandardMaterial).isMeshStandardMaterial) {
          const stdMat = mat as THREE.MeshStandardMaterial;
          stdMat.color.setHex(0xf59e0b);
          stdMat.emissive.setHex(0xfbbf24);
          stdMat.emissiveIntensity = 0.5;
          stdMat.roughness = 0.2;
          stdMat.metalness = 0.8;
        }
      });

      // Hazard stripes on top face: Overlay planar mesh with amber/black caution stripes
      const stripeGroup = new THREE.Group();
    const stripeCount = 5;
    const stripeWidth = 0.15;
    const stripeHeight = 0.02;
    const stripeDepth = 0.8;
    const stripeSpacing = 0.2;
    const totalWidth = stripeCount * stripeWidth + (stripeCount - 1) * stripeSpacing;
    const startX = -totalWidth / 2 + stripeWidth / 2;

    for (let i = 0; i < stripeCount; i++) {
      const stripeGeo = new THREE.BoxGeometry(stripeWidth, stripeHeight, stripeDepth);
      const stripeMat = new THREE.MeshBasicMaterial({
        color: 0xffaa00,
        transparent: true,
        opacity: 0.8,
      });
      const stripe = new THREE.Mesh(stripeGeo, stripeMat);
      stripe.position.set(startX + i * (stripeWidth + stripeSpacing), 0.51, 0);
      stripeGroup.add(stripe);
    }
    mesh.add(stripeGroup);
    }
  }

  private createFallbackMesh(node: ClusterNodeData): THREE.Object3D {
    const geometry = new THREE.BoxGeometry(0.8, 0.8, 0.8);
    const material = new THREE.MeshStandardMaterial({
      color: 0x888888,
      roughness: 0.7,
      metalness: 0.3,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData.nodeData = node;
    return mesh;
  }

  private onMouseMove(e: MouseEvent) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster.intersectObjects(this.scene.children, true);

    let hoveredNode: THREE.Object3D | null = null;
    for (const intersect of intersects) {
      let obj: THREE.Object3D | null = intersect.object;
      while (obj) {
        if (obj.userData.nodeData) {
          hoveredNode = obj;
          break;
        }
        obj = obj.parent;
      }
      if (hoveredNode) break;
    }

    if (hoveredNode !== this.hoveredObject) {
      if (this.hoveredObject) {
        this.hoveredObject.scale.set(1, 1, 1);
      }
      this.hoveredObject = hoveredNode;
      if (this.hoveredObject) {
        this.hoveredObject.scale.set(1.1, 1.1, 1.1);
        this.renderer.domElement.style.cursor = 'pointer';
      } else {
        this.renderer.domElement.style.cursor = 'default';
      }
    }
  }

  private onClick(e: MouseEvent) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);

    // TASK-CV-904: Vault clicks take priority — blast radius spotlighting
    // highlights the vaults fed through the same kro manifold parent.
    const vaultId = this.vaultManager.pickVault(this.raycaster);
    if (vaultId) {
      const state = this.vaultManager.computeBlastRadius(vaultId);
      this.vaultManager.applyBlastHighlight(state);
      const vaultSet = new Set<string>([state.vaultId, ...state.connectedIds]);
      this.plungeConduitManager.applyBlastHighlight(vaultSet);

      // Darken unrelated upper-deck components.
      const inBlast = vaultSet;
      for (const [nodeId, mesh] of this.nodeMeshes.entries()) {
        const lit = inBlast.has(nodeId);
        mesh.traverse((child) => {
          const m = child as THREE.Mesh;
          if (!m.isMesh) return;
          const mats = Array.isArray(m.material) ? m.material : [m.material];
          for (const mat of mats) {
            mat.transparent = true;
            mat.opacity = lit ? 1.0 : 0.12;
          }
        });
      }
      this.selectedNodeId = vaultId;
      if (this.onVaultSelected) this.onVaultSelected(state);
      return;
    }

    const intersects = this.raycaster.intersectObjects(this.scene.children, true);

    let topObj: THREE.Object3D | null = null;
    for (const intersect of intersects) {
      let obj: THREE.Object3D | null = intersect.object;
      while (obj) {
        if (obj.userData.nodeData) {
          topObj = obj;
          break;
        }
        obj = obj.parent;
      }
      if (topObj) break;
    }

    if (topObj) {
      const node = topObj.userData.nodeData as ClusterNodeData;
      this.selectedNodeId = node.id;
      this.highlightSelected(topObj);
      const worldPos = new THREE.Vector3();
      topObj.getWorldPosition(worldPos);
      this.diffCard.show(node, worldPos, this.clusterData?.metadata.cluster_name || 'Cluster');
      if (this.onNodeSelected) this.onNodeSelected(node);
    } else {
      this.diffCard.hide();
      this.selectedNodeId = null;
      this.highlightSelected(null);
      // TASK-CV-904: background click clears the vault blast-radius spotlight.
      this.vaultManager.clearBlastHighlight();
      this.plungeConduitManager.applyBlastHighlight(null);
      this.restoreNodeOpacities();
    }
  }

  /** TASK-CV-904: Restore upper-deck node materials after a blast dim. */
  private restoreNodeOpacities(): void {
    for (const mesh of this.nodeMeshes.values()) {
      mesh.traverse((child) => {
        const m = child as THREE.Mesh;
        if (!m.isMesh) return;
        const mats = Array.isArray(m.material) ? m.material : [m.material];
        for (const mat of mats) {
          mat.opacity = 1.0;
        }
      });
    }
  }

  private highlightSelected(target: THREE.Object3D | null) {
    // Reset previous highlights
    this.scene.traverse((obj) => {
      if (obj.userData.isHighlighted) {
        const mesh = obj as THREE.Mesh;
        if (mesh.material && (mesh.material as THREE.MeshStandardMaterial).emissive) {
          (mesh.material as THREE.MeshStandardMaterial).emissive.setHex(0x000000);
        }
        obj.userData.isHighlighted = false;
      }
    });

    if (target) {
      const mesh = target as THREE.Mesh;
      if (mesh.material && (mesh.material as THREE.MeshStandardMaterial).emissive) {
        (mesh.material as THREE.MeshStandardMaterial).emissive.setHex(0x004400);
      }
      target.userData.isHighlighted = true;
    }
  }

  public onResize() {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  public render(delta: number, speedMultiplier: number = 1.0) {
    const time = this.clock.getElapsedTime();
    const pulse = 0.4 + 0.4 * Math.sin(time * 4.0);

    for (const mat of this.pulsingMaterials) {
      mat.opacity = pulse;
    }

    // Process Entrances
    for (const [nodeId, entry] of this.animatingEntrances.entries()) {
      const elapsed = time - entry.startTime;
      const progress = Math.min(1.0, elapsed / entry.duration);
      const scale = THREE.MathUtils.lerp(0.1, 1.0, progress);
      entry.mesh.scale.set(scale, scale, scale);

      if (progress >= 1.0) {
        this.animatingEntrances.delete(nodeId);
      }
    }

    // Process Decays
    for (const [nodeId, entry] of this.animatingDecays.entries()) {
      const elapsed = time - entry.startTime;
      const progress = Math.min(1.0, elapsed / entry.duration);
      const scale = THREE.MathUtils.lerp(1.0, 0.0, progress);
      entry.mesh.scale.set(scale, scale, scale);

      if (progress >= 1.0) {
        this.scene.remove(entry.mesh);
        this.nodeMeshes.delete(nodeId);
        this.animatingDecays.delete(nodeId);
      }
    }

    this.diffCard.updatePosition(this.camera, this.renderer);
    this.controls.update();
    this.flowSystem.update(delta, speedMultiplier);
    this.layerTrayManager.update(delta, time);
    // SPEC-09: proportional pod capsule emissive pulse/glow.
    this.podCapsuleManager.update(time);

    // TASK-CV-904: animate vault rings / raceway particles and plunge flows.
    this.vaultManager.update(delta, time);
    this.plungeConduitManager.update(delta, time);

    // TASK-CV-904: KeyB subterranean camera preset orbit tween.
    if (this.subterraneanTween) {
      const tw = this.subterraneanTween;
      tw.elapsed += delta;
      const t = THREE.MathUtils.clamp(tw.elapsed / tw.duration, 0, 1);
      const ease = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      this.camera.position.lerpVectors(tw.fromPos, tw.toPos, ease);
      this.controls.target.lerpVectors(tw.fromTarget, tw.toTarget, ease);
      this.controls.update();
      if (t >= 1) this.subterraneanTween = null;
    }

    // Update layout transitions
    if (this.layoutController.isAnimating()) {
      this.layoutController.update(delta);
      for (const [nodeId, pos] of this.layoutController.getAllCurrentPositions().entries()) {
        const mesh = this.nodeMeshes.get(nodeId);
        if (mesh) {
          mesh.position.set(pos.x, pos.y, pos.z);
        }
      }
    }

    this.renderer.render(this.scene, this.camera);
  }

  public setLayoutAlpha(alpha: number, durationMs: number = 800): void {
    this.layoutController.setTargetAlpha(alpha, durationMs);
  }

  public setLayoutMode(mode: 'skyscraper' | 'latency-force'): void {
    this.layoutController.setTargetAlpha(mode === 'skyscraper' ? 0.0 : 1.0, 800);
  }

  /**
   * TASK-CV-903: Toggle the Ground Datum cutaway on this viewport
   * (solid 1.0 <-> ghost 0.1, smoothly animated). Returns the new target.
   */
  public toggleGroundCutaway(): number {
    return this.layerTrayManager.toggleGroundCutaway();
  }
}
