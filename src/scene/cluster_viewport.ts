import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { FlowParticleSystem } from './flow_particles.js';
import { ConduitManager } from './conduits.js';
import type { ConduitEdge, ConduitType } from './conduits.js';

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
}

export class ClusterViewport {
  public container: HTMLElement;
  public scene: THREE.Scene;
  public camera: THREE.PerspectiveCamera;
  public renderer: THREE.WebGLRenderer;
  public controls: OrbitControls;
  public flowSystem: FlowParticleSystem;
  public conduitManager: ConduitManager;
  private assetPrototypes: Map<string, THREE.Object3D> = new Map();
  private nodeMeshes: Map<string, THREE.Object3D> = new Map();
  private raycaster = new THREE.Raycaster();
  private mouse = new THREE.Vector2(-1000, -1000);
  public onNodeSelected?: (node: ClusterNodeData | null) => void;
  public onNodeHovered?: (node: ClusterNodeData | null, clientX: number, clientY: number) => void;
  public clusterData: ClusterGraphData | null = null;
  private selectedNodeId: string | null = null;

  public getSelectedNodeId(): string | null {
    return this.selectedNodeId;
  }
  private hoveredNodeId: string | null = null;
  private selectionGlow: THREE.Mesh | null = null;

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

  public setClusterData(data: ClusterGraphData, diffMap?: Map<string, { status: any; diffDetails: string[] }>) {
    this.clusterData = data;
    // Clear existing nodes and conduits
    this.nodeMeshes.forEach((mesh) => this.scene.remove(mesh));
    this.nodeMeshes.clear();
    this.flowSystem.clear();
    this.conduitManager.clear();

    const nodePositions = new Map<string, THREE.Vector3>();

    // Spawn nodes
    for (const node of data.nodes) {
      if (diffMap && diffMap.has(node.id)) {
        const d = diffMap.get(node.id)!;
        node.diffStatus = d.status;
        node.diffDetails = d.diffDetails;
      }

      const proto = this.assetPrototypes.get(node.spatial.asset_type) || this.createFallbackMesh(node);
      const instance = proto.clone(true);
      instance.position.set(node.spatial.x, node.spatial.y, node.spatial.z);
      instance.userData = { nodeData: node };

      // Apply diff color accent rings / glow
      this.applyDiffVisuals(instance, node.diffStatus);

      this.scene.add(instance);
      this.nodeMeshes.set(node.id, instance);
      nodePositions.set(node.id, new THREE.Vector3(node.spatial.x, node.spatial.y, node.spatial.z));
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
  }

  private applyDiffVisuals(mesh: THREE.Object3D, status?: string) {
    if (!status) return;

    let ringColor = 0x3b82f6; // Identical: subtle blue
    let glowOpacity = 0.2;

    if (status === 'version_skew') {
      ringColor = 0xf59e0b; // Amber: version drift
      glowOpacity = 0.75;
    } else if (status === 'missing') {
      ringColor = 0xef4444; // Red: absent in peer
      glowOpacity = 0.6;
    } else if (status === 'added') {
      ringColor = 0x10b981; // Green: newly added
      glowOpacity = 0.6;
    }

    const beaconGeo = new THREE.TorusGeometry(0.8, 0.04, 8, 32);
    const beaconMat = new THREE.MeshBasicMaterial({
      color: ringColor,
      transparent: true,
      opacity: glowOpacity,
      blending: THREE.AdditiveBlending,
    });
    const ring = new THREE.Mesh(beaconGeo, beaconMat);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = -0.15;
    mesh.add(ring);
  }

  private createFallbackMesh(node: ClusterNodeData): THREE.Object3D {
    const geo = new THREE.CylinderGeometry(0.5, 0.5, 0.8, 16);
    const mat = new THREE.MeshStandardMaterial({ color: 0x475569 });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.name = node.id;
    return mesh;
  }

  private onMouseMove(e: MouseEvent) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const meshes = Array.from(this.nodeMeshes.values());
    const intersects = this.raycaster.intersectObjects(meshes, true);

    if (intersects.length > 0) {
      let topObj: THREE.Object3D | null = intersects[0]!.object;
      while (topObj && !topObj.userData.nodeData && topObj.parent) {
        topObj = topObj.parent;
      }
      if (topObj && topObj.userData.nodeData) {
        const node = topObj.userData.nodeData as ClusterNodeData;
        if (this.hoveredNodeId !== node.id) {
          this.hoveredNodeId = node.id;
          if (this.onNodeHovered) this.onNodeHovered(node, e.clientX, e.clientY);
        }
        return;
      }
    }

    if (this.hoveredNodeId !== null) {
      this.hoveredNodeId = null;
      if (this.onNodeHovered) this.onNodeHovered(null, 0, 0);
    }
  }

  private onClick(e: MouseEvent) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const meshes = Array.from(this.nodeMeshes.values());
    const intersects = this.raycaster.intersectObjects(meshes, true);

    if (intersects.length > 0) {
      let topObj: THREE.Object3D | null = intersects[0]!.object;
      while (topObj && !topObj.userData.nodeData && topObj.parent) {
        topObj = topObj.parent;
      }
      if (topObj && topObj.userData.nodeData) {
        const node = topObj.userData.nodeData as ClusterNodeData;
        this.selectedNodeId = node.id;
        this.highlightSelected(topObj);
        if (this.onNodeSelected) this.onNodeSelected(node);
        return;
      }
    }

    this.selectedNodeId = null;
    this.highlightSelected(null);
    if (this.onNodeSelected) this.onNodeSelected(null);
  }

  private highlightSelected(target: THREE.Object3D | null) {
    if (this.selectionGlow) {
      if (this.selectionGlow.parent) this.selectionGlow.parent.remove(this.selectionGlow);
      this.selectionGlow.geometry.dispose();
      (this.selectionGlow.material as THREE.Material).dispose();
      this.selectionGlow = null;
    }

    if (target) {
      const geo = new THREE.TorusGeometry(1.05, 0.08, 16, 48);
      const mat = new THREE.MeshBasicMaterial({
        color: 0x38bdf8,
        wireframe: true,
        transparent: true,
        opacity: 0.9,
      });
      this.selectionGlow = new THREE.Mesh(geo, mat);
      this.selectionGlow.rotation.x = Math.PI / 2;
      target.add(this.selectionGlow);
    }
  }

  public onResize() {
    const w = this.container.clientWidth;
    const h = this.container.clientHeight;
    if (w === 0 || h === 0) return;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
  }

  public render(delta: number, speedMultiplier: number = 1.0) {
    this.controls.update();
    this.flowSystem.update(delta, speedMultiplier);
    this.renderer.render(this.scene, this.camera);
  }
}
