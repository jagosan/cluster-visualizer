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
// SPEC-11 / TASK-CV-1205: Load-driven latency spring physics engine.
import { LatencySpringEngine } from './latency_spring_engine.js';
import type { DiffKind } from './diff_sequence.js';
// SPEC-09 / TASK-CV-1001: procedural proportional pod capsules (ADR-01).
import { PodCapsuleManager, resolvePodDimensions } from './pod_capsules.js';
import type { PodGeometryData } from './pod_capsules.js';
// SPEC-09 / TASK-CV-1002: VPA ghost hulls, in-place morph tweens, HPA
// dispatch pulses, lateral conveyor slides, and KeyU radar auras.
import {
  AutoscalingFxManager,
  capsuleDims,
  parseResourceQuantity,
} from './autoscaling_fx.js';
import type {
  AutoscalingStatusData,
  HpaScaleOutEvent,
  MorphDimensions,
} from './autoscaling_fx.js';
// SPEC-09 / TASK-CV-1003: exterior staging yard — tarmac, pending-pod hover,
// Karpenter ghost chassis, tractor beams, and the KeyY apron focus control.
import { StagingYardManager } from './staging_yard.js';
import type {
  KarpenterClaimUpdatedPayload,
  KarpenterNodeClaimData,
  KarpenterTractorBeamPayload,
} from './staging_yard.js';
// SPEC-09 / TASK-CV-1004: Kueue gang cargo containment pallets — HUD
// badges, quota-deficit standby, mag-rail transit, gang deployment bursts.
import { KueuePalletManager } from './kueue_pallet.js';
import type {
  KueueAdmissionAdmittedPayload,
  KueueGangDeployedPayload,
  KueueQuotaDeficitPayload,
  KueueQuotaReservedPayload,
  KueueWorkloadData,
  KueueWorkloadUpdatedPayload,
} from './kueue_pallet.js';

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
  // SPEC-09 §3.2/§3.3: VPA/HPA autoscaling metadata (optional on the wire).
  autoscaling?: AutoscalingStatusData | null;
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

/**
 * SPEC-09 §3.2: resolve ghost-hull target dimensions for a VPA-managed pod.
 * Compares the recommended target dimensions against the pod's current
 * proportional geometry; returns null when they already agree (no ghost).
 */
function vpaGhostDimensions(
  node: ClusterNodeData,
): { height: number; radius: number } | null {
  const as = node.autoscaling;
  if (!as?.has_vpa) return null;
  const current = resolvePodDimensions(node);
  const tgtCpu = parseResourceQuantity(as.vpa_target_cpu ?? null, 'cpu');
  const tgtMem = parseResourceQuantity(as.vpa_target_memory ?? null, 'memory');
  if (tgtCpu === null && tgtMem === null) return null;
  const target = capsuleDims(
    tgtCpu ?? dimsToCpu(current.height),
    tgtMem ?? dimsToMemoryGib(current.radius),
  );
  if (
    Math.abs(target.height - current.height) < 1e-6 &&
    Math.abs(target.radius - current.radius) < 1e-6
  ) {
    return null;
  }
  return target;
}

/** Invert the §3.1 height formula to recover vCPU from a capsule height. */
function dimsToCpu(height: number): number {
  return Math.max(0, (Math.max(height, 0.4) - 0.4) / 0.35) ** 2;
}

/** Invert the §3.1 radius formula to recover GiB from a capsule radius. */
function dimsToMemoryGib(radius: number): number {
  return Math.pow(2, Math.max(0, (radius - 0.2) / 0.12));
}

/** Find the capsule Mesh inside a pod instance (bare Mesh or Group+brackets). */
function findCapsuleMesh(obj: THREE.Object3D): THREE.Mesh | null {
  const direct = obj as THREE.Mesh;
  if (direct.isMesh && obj.userData.podCapsule) return direct;
  let found: THREE.Mesh | null = null;
  obj.traverse((child) => {
    const m = child as THREE.Mesh;
    if (!found && m.isMesh && child.userData.podCapsule) found = m;
  });
  return found;
}

/** Recover (height, radius) from a capsule geometry's bounding dimensions. */
function capsuleDimensionsOf(mesh: THREE.Mesh): { height: number; radius: number } {
  const height = (mesh.userData.podHeight as number | undefined) ?? 0.6;
  mesh.geometry.computeBoundingBox();
  const bb = mesh.geometry.boundingBox;
  if (!bb) return { height, radius: 0.3 };
  const spanX = bb.max.x - bb.min.x;
  const spanY = bb.max.y - bb.min.y;
  return { height: spanY, radius: spanX / 2 };
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
  // SPEC-09 / TASK-CV-1003: Karpenter NodeClaims provisioning B1 ghost nodes
  karpenter_node_claims?: KarpenterNodeClaimData[];
  // SPEC-09 / TASK-CV-1004: Kueue Workload CRDs -> cargo containment pallets
  kueue_workloads?: KueueWorkloadData[];
}

/**
 * SPEC-09 §4.2 (ADR-02): a pod is pending when the ingestion layout flagged
 * its geometry or the metrics bag carries pending / PodScheduled=False.
 */
export function isPendingPod(node: ClusterNodeData): boolean {
  if (node.pod_geometry?.is_pending === true) return true;
  const metrics = node.metrics as Record<string, unknown> | undefined;
  if (!metrics) return false;
  return metrics['pending'] === true || metrics['scheduled'] === false;
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
  // SPEC-09 / TASK-CV-1002: VPA ghost hulls, morph tweens, HPA dispatch
  // pulses / lateral conveyor slides, and the KeyU autoscaling radar.
  public autoscalingFx: AutoscalingFxManager;
  // SPEC-09 / TASK-CV-1003: exterior pre-admission staging yard (tarmac,
  // pending-pod hover, Karpenter ghost chassis + amber tractor beams).
  public stagingYard: StagingYardManager;
  // SPEC-09 / TASK-CV-1004: Kueue gang cargo containment pallets on the
  // staging-track rail (HUD badges, mag-rail transit, deployment bursts).
  public kueuePallets: KueuePalletManager;
  // SPEC-09 §7.1: Staging Apron Focus (KeyY) camera tween state.
  private stagingFocused = false;
  private cameraTween: {
    elapsed: number;
    duration: number;
    fromPos: THREE.Vector3;
    toPos: THREE.Vector3;
    fromTarget: THREE.Vector3;
    toTarget: THREE.Vector3;
  } | null = null;
  // HPA replica capsules spawned by scale-out events (viewport-owned cleanup).
  private hpaReplicas: THREE.Object3D[] = [];
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

  // SPEC-11 / TASK-CV-1205: Load-driven latency spring engine for floor separation.
  public springEngine: LatencySpringEngine = new LatencySpringEngine();
  
  // Diff focus tween state for highlighting component differences.
  private diffFocusTween: {
    fromPos: THREE.Vector3;
    toPos: THREE.Vector3;
    fromTarget: THREE.Vector3;
    toTarget: THREE.Vector3;
    duration: number;
    elapsed: number;
  } | null = null;
  
  // Diff highlight state - used by setDiffHighlight/clearDiffHighlight methods
  private activeDiffMesh: THREE.Object3D | null = null; /* used by setDiffHighlight/clearDiffHighlight */
  private activeDiffOriginalMaterial: THREE.Material | THREE.Material[] | null = null; /* used by setDiffHighlight/clearDiffHighlight */

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
    this.autoscalingFx = new AutoscalingFxManager(this.scene);
    this.stagingYard = new StagingYardManager(this.scene);
    this.kueuePallets = new KueuePalletManager(this.scene);
    
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
    const hasRayCluster = data.nodes.some((n) => {
      const nm = n.name.toLowerCase();
      const kd = n.kind.toLowerCase();
      return (nm.includes('ray') || kd.includes('ray')) && !nm.includes('operator') && kd !== 'kuberayoperator';
    });

    // Build layered architectural trays and outer structural cage.
    // TASK-CV-903: feed the snapshot's machine_shapes so chassis footprints,
    // capacity materials, and accelerator power bays render per machine.
    this.layerTrayManager.setMachineShapes(data.machine_shapes);
    this.layerTrayManager.buildTowerTrays(workerCount, hasRay);

    // Build flank typographic billboard labels
    this.flankLabelManager.buildLabels(workerCount, hasRay, hasRayCluster);

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

    // TASK-CV-1002: VPA recommendation ghost hulls + autoscaling radar auras
    // for every pod carrying `autoscaling` metadata in the snapshot.
    this.buildAutoscalingLayer(data);

    // TASK-CV-1003: exterior staging yard — pending-pod hover registration
    // plus Karpenter ghost chassis docking and amber tractor beams.
    this.buildStagingLayer(data, nodePositions);
  }

  // -------------------------------------------------------------------------
  // TASK-CV-1003 / SPEC-09 §4.1-§4.2, §7.1: staging yard pipelines
  // -------------------------------------------------------------------------

  /**
   * Refresh the staging yard from snapshot metadata: every pending pod
   * (PodScheduled=False) hovering over the tarmac joins the anti-gravity
   * bob, and every Karpenter NodeClaim docks a wireframe ghost chassis on
   * Sub-Level B1 with beams lancing down from its pending pods.
   */
  private buildStagingLayer(
    data: ClusterGraphData,
    nodePositions: Map<string, THREE.Vector3>,
  ): void {
    this.stagingYard.clearGhostsAndBeams();
    this.stagingYard.clearHovering();

    const pendingPositions = new Map<string, THREE.Vector3>();
    for (const node of data.nodes) {
      if (!isPendingPod(node)) continue;
      const mesh = this.nodeMeshes.get(node.id);
      if (mesh && mesh.position.y > 0.5) {
        this.stagingYard.registerPendingPod(mesh);
        pendingPositions.set(node.id, mesh.position.clone());
      } else {
        // Layout already parked it on the hover band; trust the wire coords.
        pendingPositions.set(node.id, nodePositions.get(node.id)?.clone()
          ?? new THREE.Vector3(node.spatial.x, node.spatial.y, node.spatial.z));
      }
    }

    this.stagingYard.applyClaims(data.karpenter_node_claims, pendingPositions);

    // TASK-CV-1004: build cargo containment pallets from the snapshot's
    // Kueue workloads and register their constituent pod meshes so the
    // deployment burst can grab them.
    this.kueuePallets.applySnapshot(data.kueue_workloads);
    for (const node of data.nodes) {
      const workloadUid = node.pod_geometry?.kueue_workload;
      if (!workloadUid) continue;
      const mesh = this.nodeMeshes.get(node.id);
      if (mesh) this.kueuePallets.registerGangPod(node.id, mesh);
    }
  }

  // -------------------------------------------------------------------------
  // TASK-CV-1004 / SPEC-09 §5.2-§5.3, §7.3: Kueue gang pallet pipelines
  // -------------------------------------------------------------------------

  /**
   * SSE `kueue_workload_updated`: create/refresh a cargo containment pallet
   * with its HUD badge (Workload, LocalQueue, X/Y Pods, quota) on the
   * staging-track rail (SPEC-09 §5.2).
   */
  public applyKueueWorkloadUpdated(payload: KueueWorkloadUpdatedPayload): void {
    this.kueuePallets.applyWorkloadUpdated(payload);
  }

  /** SSE `kueue_quota_deficit`: cold-blue standby + deficit overlay. */
  public applyKueueQuotaDeficit(payload: KueueQuotaDeficitPayload): void {
    this.kueuePallets.applyQuotaDeficit(payload);
  }

  /** SSE `kueue_quota_reserved`: intake-rail engagement + gantry crane lock. */
  public applyKueueQuotaReserved(payload: KueueQuotaReservedPayload): void {
    this.kueuePallets.applyQuotaReserved(payload);
  }

  /** SSE `kueue_admission_admitted`: vivid green mag-rail transit. */
  public applyKueueAdmissionAdmitted(payload: KueueAdmissionAdmittedPayload): void {
    this.kueuePallets.applyAdmissionAdmitted(payload);
  }

  /** SSE `kueue_gang_deployed`: frame dissolve + simultaneous pod burst. */
  public applyKueueGangDeployed(payload: KueueGangDeployedPayload): void {
    this.kueuePallets.applyGangDeployed(payload);
  }

  /**
   * SPEC-09 §7.3: Simulated Gang Admission trigger (KeyK / HUD button).
   * Fires the full reserved -> admitted -> deployed animation chain; in
   * static offline mode with no live workload it synthesizes a demo gang.
   */
  public simulateGangAdmission(): boolean {
    return this.kueuePallets.simulateGangAdmission();
  }

  /**
   * SSE `karpenter_claim_updated`: dock/refresh a NodeClaim's ghost chassis
   * on Sub-Level B1 (SPEC-09 §4.2).
   */
  public applyKarpenterClaim(payload: KarpenterClaimUpdatedPayload): void {
    const claim = payload.claim;
    const pos = payload.ghost_position
      ? new THREE.Vector3(payload.ghost_position.x, payload.ghost_position.y, payload.ghost_position.z)
      : new THREE.Vector3(0, -2.5, 0);
    this.stagingYard.upsertGhostChassis(
      claim.claim_name,
      pos,
      claim.is_provisioned === true,
    );
  }

  /**
   * SSE `karpenter_tractor_beam`: project the luminous amber provisioning
   * beam from a pending pod down into its ghost chassis (SPEC-09 §4.2).
   */
  public applyKarpenterTractorBeam(payload: KarpenterTractorBeamPayload): void {
    const top = payload.beam.top;
    const bottom = payload.beam.bottom;
    if (!top || top.length < 3 || !bottom || bottom.length < 3) return;
    this.stagingYard.setTractorBeam(
      payload.node_id,
      payload.claim_name,
      new THREE.Vector3(top[0] ?? 0, top[1] ?? 1, top[2] ?? 0),
      new THREE.Vector3(bottom[0] ?? 0, bottom[1] ?? -2.5, bottom[2] ?? 0),
    );
  }

  /**
   * SPEC-09 §7.1: Staging Apron Focus (KeyY) — smoothly pans/orbits the
   * camera to frame the pre-admission staging yard at X = -18.0. Toggles
   * back to the tower preset. Returns true when focused on the apron.
   */
  public toggleStagingFocus(durationMs = 1200): boolean {
    this.stagingFocused = !this.stagingFocused;
    const focus = StagingYardManager.stagingFocusTargets();
    const toPos = this.stagingFocused
      ? focus.camera
      : new THREE.Vector3(16, 7, 20);
    const toTarget = this.stagingFocused
      ? focus.target
      : new THREE.Vector3(0, 3.5, 0);

    this.cameraTween = {
      elapsed: 0,
      duration: Math.max(0.05, durationMs / 1000),
      fromPos: this.camera.position.clone(),
      toPos,
      fromTarget: this.controls.target.clone(),
      toTarget,
    };
    return this.stagingFocused;
  }

  public isStagingFocus(): boolean {
    return this.stagingFocused;
  }

  // -------------------------------------------------------------------------
  // TASK-CV-1002 / SPEC-09 §3.2-§3.3, §7.2: autoscaling animation pipelines
  // -------------------------------------------------------------------------

  /**
   * Refresh ghost hulls + radar auras from snapshot metadata. Pods whose
   * VPA recommendation matches their current request get no ghost hull.
   */
  private buildAutoscalingLayer(data: ClusterGraphData): void {
    this.autoscalingFx.clear();
    this.clearHpaReplicas();

    for (const node of data.nodes) {
      const as = node.autoscaling;
      if (!as) continue;
      const pos = new THREE.Vector3(node.spatial.x, node.spatial.y, node.spatial.z);
      const managedVpa = as.has_vpa === true;
      const managedHpa = as.has_hpa === true;
      if (!managedVpa && !managedHpa) continue;

      if (managedVpa) {
        const dims = vpaGhostDimensions(node);
        if (dims) {
          this.autoscalingFx.setGhost(node.id, pos, dims.height, dims.radius);
        }
        this.autoscalingFx.addAura(node.id, pos.clone().setY(pos.y - 0.32), 'vpa');
      } else if (managedHpa) {
        this.autoscalingFx.addAura(node.id, pos.clone().setY(pos.y - 0.32), 'hpa');
      }
    }
    this.autoscalingFx.setRadarVisible(this.autoscalingFx.isRadarVisible());
  }

  /**
   * SSE `vpa_recommendation`: (re)draw the holographic wireframe ghost hull
   * projecting the target dimensions around the pod (SPEC-09 §3.2.1).
   */
  public applyVpaRecommendation(
    nodeId: string,
    dimensions: MorphDimensions | null,
  ): void {
    const mesh = this.nodeMeshes.get(nodeId);
    if (!mesh) return;
    const node = mesh.userData.nodeData as ClusterNodeData | undefined;
    if (!node) return;
    if (!dimensions) {
      this.autoscalingFx.clearGhost(nodeId);
      return;
    }
    const pos = new THREE.Vector3(node.spatial.x, node.spatial.y, node.spatial.z);
    this.autoscalingFx.setGhost(
      nodeId,
      pos,
      dimensions.target_height,
      dimensions.target_radius,
    );
    this.autoscalingFx.addAura(nodeId, pos.clone().setY(pos.y - 0.32), 'vpa');
  }

  /**
   * SSE `vpa_resize_committed`: run the in-place ~1200ms animated geometry
   * tween to the new dimensions with energy emission ripples (SPEC-09 §3.2.2).
   */
  public applyVpaResize(
    nodeId: string,
    height: number,
    radius: number,
    durationMs = 1200,
  ): void {
    const obj = this.nodeMeshes.get(nodeId);
    if (!obj) return;
    const mesh = findCapsuleMesh(obj);
    if (!mesh) return;

    const from = capsuleDimensionsOf(mesh);
    const node = obj.userData.nodeData as ClusterNodeData | undefined;
    if (node?.pod_geometry) {
      node.pod_geometry.height = height;
      node.pod_geometry.radius = radius;
    }
    this.autoscalingFx.startMorph(
      mesh,
      from.height,
      from.radius,
      height,
      radius,
      durationMs,
      () => this.autoscalingFx.clearGhost(nodeId),
    );
  }

  /**
   * SSE `hpa_scale_out`: golden dispatch pulse from the Supervisor Floor
   * down the central riser; when it lands, new replica capsules materialize
   * at the node deck intake and slide laterally into their slots
   * (SPEC-09 §3.3).
   */
  public applyHpaScaleOut(event: HpaScaleOutEvent): void {
    const mesh = this.nodeMeshes.get(event.node_id);
    const node = mesh?.userData.nodeData as ClusterNodeData | undefined;
    const deckY = node?.spatial.y ?? 0.75;

    const dispatchFrom = event.dispatch_from ?? { x: 0.0, y: 4.5, z: 0.0 };
    const riserBottom = event.riser_bottom ?? { x: 0.0, y: deckY, z: 0.0 };

    const replicas = Math.max(0, Math.min(8, event.delta ?? 1));
    this.autoscalingFx.fireDispatchPulse(dispatchFrom, riserBottom, 700, () => {
      for (let i = 0; i < replicas; i++) {
        const slotIndex = i % 4;
        const offsetX = slotIndex % 2 === 0 ? -0.6 + i * 0.15 : 0.6 + i * 0.15;
        const z = slotIndex < 2 ? 0.2 : 1.2;
        const chassisX = node?.spatial.x ?? 0.0;
        const intake =
          event.lateral_path?.intake && event.lateral_path.intake.length === 3
            ? new THREE.Vector3(...(event.lateral_path.intake as [number, number, number]))
            : new THREE.Vector3(chassisX + 2.6, deckY, z);
        const slot =
          event.lateral_path?.slot && i === 0 && event.lateral_path.slot.length === 3
            ? new THREE.Vector3(...(event.lateral_path.slot as [number, number, number]))
            : new THREE.Vector3(chassisX + offsetX, deckY, z);

        const replicaName = `${node?.name ?? 'pod'}-hpa-${Date.now().toString(36)}-${i}`;
        const replica: ClusterNodeData = {
          id: replicaName,
          layer: node?.layer ?? 'workload',
          kind: 'Pod',
          name: replicaName,
          namespace: node?.namespace ?? 'default',
          version: node?.version ?? 'v1.0.0',
          status: 'Healthy',
          metrics: { ...(node?.metrics ?? {}) },
          spatial: { x: slot.x, y: slot.y, z: slot.z, asset_type: 'Cuboid_Pod' },
          pod_geometry: node?.pod_geometry ? { ...node.pod_geometry } : null,
        };
        const capsule = this.podCapsuleManager.create(replica, 'added');
        capsule.userData.nodeData = replica;
        this.scene.add(capsule);
        this.nodeMeshes.set(replicaName, capsule);
        this.hpaReplicas.push(capsule);
        this.autoscalingFx.slideIntoSlot(capsule, intake, slot, 900 + i * 150);
      }
    });
  }

  /**
   * SPEC-09 §7.2: Autoscaling Radar Overlay (KeyU) — pulsating golden aura
   * rings over every VPA/HPA-managed pod. Returns the new visibility.
   */
  public toggleAutoscalingRadar(): boolean {
    const visible = !this.autoscalingFx.isRadarVisible();
    this.autoscalingFx.setRadarVisible(visible);
    return visible;
  }

  public isAutoscalingRadarVisible(): boolean {
    return this.autoscalingFx.isRadarVisible();
  }

  /** Remove HPA replica capsules from a previous scale-out burst. */
  private clearHpaReplicas(): void {
    for (const replica of this.hpaReplicas) {
      this.podCapsuleManager.untrack(replica);
      const id = (replica.userData.nodeData as ClusterNodeData | undefined)?.id;
      if (id) this.nodeMeshes.delete(id);
      this.scene.remove(replica);
    }
    this.hpaReplicas.length = 0;
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

    // TASK-CV-1002: newly observed VPA-managed pods get a ghost hull too.
    if (node.autoscaling?.has_vpa) {
      const dims = vpaGhostDimensions(node);
      if (dims) {
        this.autoscalingFx.setGhost(
          node.id,
          new THREE.Vector3(sx, sy, sz),
          dims.height,
          dims.radius,
        );
      }
      this.autoscalingFx.addAura(
        node.id,
        new THREE.Vector3(sx, sy - 0.32, sz),
        node.autoscaling.has_hpa ? 'hpa' : 'vpa',
      );
    } else if (node.autoscaling?.has_hpa) {
      this.autoscalingFx.addAura(
        node.id,
        new THREE.Vector3(sx, sy - 0.32, sz),
        'hpa',
      );
    }

    this.scene.add(instance);
    this.nodeMeshes.set(node.id, instance);

    // TASK-CV-1003: a live pod that arrives PodScheduled=False hovers over
    // the staging tarmac until Karpenter/admission lands it inside the tower.
    if (isPendingPod(node)) {
      this.stagingYard.registerPendingPod(instance);
    }
    // TASK-CV-1004: pods belonging to a Kueue Workload join its cargo
    // containment pallet for the gang-deployment burst.
    if (node.pod_geometry?.kueue_workload) {
      this.kueuePallets.registerGangPod(node.id, instance);
    }

    this.animatingEntrances.set(node.id, {
      mesh: instance,
      startTime: this.clock.getElapsedTime(),
      duration: 0.6,
    });

    if (this.clusterData?.nodes) {
      this.clusterData.nodes.push(node);
      const hasRayCluster = this.clusterData.nodes.some(
        (n) => n.kind === 'RayHead' || n.kind === 'RayWorker',
      );
      this.flankLabelManager.setRaySubLabelsVisible(hasRayCluster);
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
    // TASK-CV-1002: drop any ghost hull / radar aura tied to the removed pod.
    this.autoscalingFx.clearGhost(nodeId);
    this.autoscalingFx.removeAura(nodeId);
    // TASK-CV-1003: stop hover bobbing / tractor beams for the removed pod.
    this.stagingYard.removePendingPod(nodeId);
    // TASK-CV-1004: drop the pod from any Kueue cargo pallet member list.
    this.kueuePallets.removePod(nodeId);

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
      const hasRayCluster = this.clusterData.nodes.some(
        (n) => n.kind === 'RayHead' || n.kind === 'RayWorker',
      );
      this.flankLabelManager.setRaySubLabelsVisible(hasRayCluster);
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
    // TASK-CV-1002: VPA morph tweens, HPA dispatch pulses, lateral conveyor
    // slides, ghost-hull shimmer, and KeyU radar auras.
    this.autoscalingFx.update(delta, time);
    // TASK-CV-1003: pending-pod hover bobbing, Karpenter ghost-chassis
    // shimmer, and amber tractor-beam pulses in the exterior staging yard.
    this.stagingYard.update(delta, time);
    // TASK-CV-1004: Kueue cargo pallet standby lighting, spinning intake
    // beacons, gantry lock, mag-rail transit tweens, gang deployment bursts.
    this.kueuePallets.update(delta, time);

    // SPEC-09 §7.1: KeyY staging apron focus camera tween.
    if (this.cameraTween) {
      const tw = this.cameraTween;
      tw.elapsed += delta;
      const t = THREE.MathUtils.clamp(tw.elapsed / tw.duration, 0, 1);
      const ease = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      this.camera.position.lerpVectors(tw.fromPos, tw.toPos, ease);
      this.controls.target.lerpVectors(tw.fromTarget, tw.toTarget, ease);
      this.controls.update();
      if (t >= 1) this.cameraTween = null;
    }

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

    // SPEC-11 / TASK-CV-1205: Diff focus tween for highlighting component differences.
    if (this.diffFocusTween) {
      const tw = this.diffFocusTween;
      tw.elapsed += delta;
      const t = THREE.MathUtils.clamp(tw.elapsed / tw.duration, 0, 1);
      const ease = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      this.camera.position.lerpVectors(tw.fromPos, tw.toPos, ease);
      this.controls.target.lerpVectors(tw.fromTarget, tw.toTarget, ease);
      this.controls.update();
      if (t >= 1) this.diffFocusTween = null;
    }

    // SPEC-11 / TASK-CV-1205: Diff highlight state - update emissive intensity for active diff
    if (this.activeDiffMesh && 'material' in this.activeDiffMesh) {
      const mat = (this.activeDiffMesh as any).material;
      if (mat && 'emissiveIntensity' in mat) {
        mat.emissiveIntensity = 1.2 + 0.8 * Math.sin(time * 6.0);
      }
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

  /** Set the latency for a specific conduit and activate its thermal state. */
  public setConduitLatency(id: string, latencyMs: number): void {
    this.plungeConduitManager.setConduitLatency(id, latencyMs);
  }

  /** Reset all conduit latencies to their baseline values. */
  public resetConduitLatencies(): void {
    this.plungeConduitManager.resetConduitLatencies();
  }

  /**
   * Focus on a specific component and highlight its difference state.
   * @param componentId - The ID of the component to focus on
   * @param customPosition - Optional custom position for the camera target
   */
  public focusComponent(componentId: string, customPosition?: { x: number; y: number; z: number }): void {
    let targetPos: THREE.Vector3 | null = null;
    
    if (customPosition) {
      targetPos = new THREE.Vector3(customPosition.x, customPosition.y, customPosition.z);
    } else {
      const mesh = this.nodeMeshes.get(componentId);
      if (mesh) {
        targetPos = mesh.position.clone();
      }
    }
    
    if (!targetPos) return;

    const orbitOffset = new THREE.Vector3(5, 4, 7);
    
    this.diffFocusTween = {
      fromPos: this.camera.position.clone(),
      toPos: targetPos.clone().add(orbitOffset),
      fromTarget: this.controls.target.clone(),
      toTarget: targetPos.clone(),
      duration: 0.8,
      elapsed: 0,
    };
  }

  /**
   * Set highlight on a component based on its diff kind (added, deleted, modified).
   * @param componentId - The ID of the component to highlight
   * @param kind - The type of difference (added, deleted, modified)
   */
  public setDiffHighlight(componentId: string, kind: DiffKind): void {
    if (!componentId) {
      this.clearDiffHighlight();
      return;
    }

    this.clearDiffHighlight();

    const mesh = this.nodeMeshes.get(componentId);
    if (!mesh || !('material' in mesh)) return;

    this.activeDiffMesh = mesh;
    this.activeDiffOriginalMaterial = (mesh as any).material;

    const highlightMat = new THREE.MeshStandardMaterial({
      roughness: 0.2,
      metalness: 0.5,
    });

    switch (kind) {
      case 'added':
        highlightMat.color.setHex(0x10b981);
        highlightMat.emissive.setHex(0x10b981);
        highlightMat.emissiveIntensity = 1.6;
        break;
      case 'deleted':
        highlightMat.color.setHex(0xef4444);
        highlightMat.wireframe = true;
        highlightMat.transparent = true;
        highlightMat.opacity = 0.65;
        break;
      case 'modified':
      default:
        highlightMat.color.setHex(0xf59e0b);
        highlightMat.emissive.setHex(0xf59e0b);
        highlightMat.emissiveIntensity = 1.4;
        break;
    }

    (mesh as any).material = highlightMat;
  }

  /**
   * Clear the current diff highlight on a component.
   */
  public clearDiffHighlight(): void {
    if (this.activeDiffMesh && this.activeDiffOriginalMaterial) {
      if ('material' in this.activeDiffMesh) {
        (this.activeDiffMesh as any).material = this.activeDiffOriginalMaterial;
      }
    }

    this.activeDiffMesh = null;
    this.activeDiffOriginalMaterial = null;
  }

  /**
   * Set the latency for a specific tier or edge in the spring engine.
   * @param tierOrEdge - The ID of the tier or edge
   * @param latencyMs - The latency in milliseconds
   */
  public setLoadLatency(tierOrEdge: string, latencyMs: number): void {
    this.springEngine.setTierLatency(tierOrEdge, latencyMs);
  }

  /**
   * Reset all latencies in the spring engine to their baseline values.
   */
  public resetLoadLatencies(): void {
    this.springEngine.reset();
  }
}
