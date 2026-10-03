import * as THREE from 'three';

/**
 * TASK-CV-903: Physical machine / Karpenter compute-class chassis data.
 * Mirrors src/ingestion/models.py MachineShape emitted on the ClusterGraph
 * snapshot `machine_shapes` field.
 */
export interface MachineShapeData {
  node_name: string;
  instance_type: string;
  compute_class?: string;
  vcpus: number;
  memory_gib: number;
  capacity_type: 'spot' | 'on-demand';
  zone: string;
  accelerator_type?: string;
  accelerator_count: number;
  chassis_width?: number;
  chassis_depth?: number;
}

/** Internal normalized chassis placement spec. */
interface ChassisSpec {
  name: string;
  width: number;
  depth: number;
  capacityType: 'spot' | 'on-demand';
  acceleratorType?: string;
  acceleratorCount: number;
}

const clamp = (v: number, lo: number, hi: number): number =>
  Math.min(hi, Math.max(lo, v));

/**
 * Footprint formulas matching src/ingestion/layout.py
 * calculate_chassis_dimensions (explicit chassis_width/depth win when set).
 */
export function chassisFootprint(m: MachineShapeData): { width: number; depth: number } {
  const width =
    m.chassis_width ?? clamp(3.2 + 0.35 * Math.sqrt(Math.max(m.vcpus, 0)), 3.2, 8.0);
  const depth =
    m.chassis_depth ?? clamp(2.4 + 0.3 * Math.sqrt(Math.max(m.memory_gib, 0)), 2.4, 7.5);
  return { width, depth };
}

/** Accelerator core glow colour: nvidia green, TPU cyan, fallback cyan-blue. */
function acceleratorCoreColor(acceleratorType?: string): number {
  const t = (acceleratorType || '').toLowerCase();
  if (t.includes('nvidia') || t.includes('gpu')) return 0x22c55e;
  if (t.includes('tpu')) return 0x22d3ee;
  return 0x38bdf8;
}

/**
 * SPEC-02: LayerTrayManager
 * Manages 3D semi-transparent rectangular layer trays and outer structural tower cages
 * matching the Peter Gostev Transformer vs DeepSeek architectural visual aesthetic.
 *
 * TASK-CV-903: when machineShapes are provided, worker-deck chassis footprints are
 * dimensioned per machine (with capacity-type materials and accelerator power bays),
 * and a smoked-glass Ground Datum at Y = 0.0 can be faded for cutaway views (KeyG).
 */
export class LayerTrayManager {
  private readonly scene: THREE.Scene;
  private trays: THREE.Group[] = [];
  private cage: THREE.Group | null = null;
  private machineShapes: MachineShapeData[];

  // TASK-CV-903: Ground Datum (Y = 0.0) + accelerator core pulse state
  private readonly groundGroup = new THREE.Group();
  private readonly groundPlaneMat: THREE.MeshStandardMaterial;
  private readonly groundGridMat: THREE.LineBasicMaterial;
  private groundOpacity = 1.0;
  private groundTargetOpacity = 1.0;
  private coreMaterials: THREE.MeshStandardMaterial[] = [];
  private static readonly GROUND_GRID_BASE_OPACITY = 0.6;

  constructor(scene: THREE.Scene, machineShapes?: MachineShapeData[]) {
    this.scene = scene;
    this.machineShapes = machineShapes ?? [];

    // Smoked-glass horizontal datum plane at Y = 0.0
    const planeGeo = new THREE.PlaneGeometry(72, 44);
    this.groundPlaneMat = new THREE.MeshStandardMaterial({
      color: 0x0b1220,
      roughness: 0.12,
      metalness: 0.55,
      transparent: true,
      opacity: 1.0,
      depthWrite: false,
    });
    const plane = new THREE.Mesh(planeGeo, this.groundPlaneMat);
    plane.rotation.x = -Math.PI / 2;
    plane.position.y = 0.0;
    this.groundGroup.add(plane);

    // Cyan-tinted grid overlay riding just above the datum
    const grid = new THREE.GridHelper(72, 72, 0x38bdf8, 0x1f2937);
    grid.position.y = 0.002;
    this.groundGridMat = grid.material as THREE.LineBasicMaterial;
    this.groundGridMat.transparent = true;
    this.groundGridMat.opacity = LayerTrayManager.GROUND_GRID_BASE_OPACITY;
    this.groundGroup.add(grid);

    // Faint cyan perimeter outline marking the datum extent
    const outlineGeo = new THREE.EdgesGeometry(new THREE.PlaneGeometry(72, 44));
    const outlineMat = new THREE.LineBasicMaterial({
      color: 0x22d3ee,
      transparent: true,
      opacity: 0.35,
    });
    const outline = new THREE.LineSegments(outlineGeo, outlineMat);
    outline.rotation.x = -Math.PI / 2;
    outline.position.y = 0.004;
    this.groundGroup.add(outline);

    this.scene.add(this.groundGroup);
  }

  /**
   * Builds the stacked rectangular trays and outer structural cage for a cluster tower.
   */
  public buildTowerTrays(workerCount: number, hasRay: boolean): void {
    this.clear();

    const createTray = (
      width: number,
      depth: number,
      height: number,
      color: number,
      rimColor: number,
      y: number,
      z: number = 0
    ): THREE.Group => {
      const group = new THREE.Group();
      group.position.set(0, y, z);

      // Translucent Tray Base Slab
      const baseGeo = new THREE.BoxGeometry(width, height, depth);
      const baseMat = new THREE.MeshStandardMaterial({
        color,
        roughness: 0.2,
        metalness: 0.1,
        transparent: true,
        opacity: 0.28,
        depthWrite: false,
      });
      const base = new THREE.Mesh(baseGeo, baseMat);
      group.add(base);

      // Subtle Rim Lip Walls
      const rimThickness = 0.08;
      const rimHeight = height * 0.8;
      const rimMat = new THREE.MeshStandardMaterial({
        color: rimColor,
        roughness: 0.3,
        metalness: 0.5,
        transparent: true,
        opacity: 0.7,
      });

      // Front & Back Rims
      const fbGeo = new THREE.BoxGeometry(width, rimHeight, rimThickness);
      const frontRim = new THREE.Mesh(fbGeo, rimMat);
      frontRim.position.set(0, height / 2 + rimHeight / 2, depth / 2 - rimThickness / 2);
      group.add(frontRim);

      const backRim = new THREE.Mesh(fbGeo, rimMat);
      backRim.position.set(0, height / 2 + rimHeight / 2, -depth / 2 + rimThickness / 2);
      group.add(backRim);

      // Left & Right Rims
      const lrGeo = new THREE.BoxGeometry(rimThickness, rimHeight, depth - rimThickness * 2);
      const leftRim = new THREE.Mesh(lrGeo, rimMat);
      leftRim.position.set(-width / 2 + rimThickness / 2, height / 2 + rimHeight / 2, 0);
      group.add(leftRim);

      const rightRim = new THREE.Mesh(lrGeo, rimMat);
      rightRim.position.set(width / 2 - rimThickness / 2, height / 2 + rimHeight / 2, 0);
      group.add(rightRim);

      // Glowing Neon Contour Edges
      const edgesGeo = new THREE.EdgesGeometry(baseGeo);
      const edgeMat = new THREE.LineBasicMaterial({
        color: rimColor,
        transparent: true,
        opacity: 0.85,
      });
      const edgeLines = new THREE.LineSegments(edgesGeo, edgeMat);
      group.add(edgeLines);

      this.scene.add(group);
      this.trays.push(group);
      return group;
    };

    // 1. Distant Clients Horizon Pad (Y=12.0)
    createTray(8.0, 5.0, 0.20, 0x38bdf8, 0x0284c7, 12.0);

    // 2. API Gateway & Aggregator Floor (Y=9.5)
    createTray(7.2, 4.6, 0.30, 0x0284c7, 0x38bdf8, 9.5);

    // 3. Kube-API Server Executive Core (Y=7.0)
    createTray(7.2, 4.6, 0.30, 0x0369a1, 0x38bdf8, 7.0);

    // 4. etcd Consensus Vault (Y=5.5, Z=-3.5 - behind API servers)
    createTray(4.8, 3.2, 0.28, 0xd97706, 0xfbbf24, 5.5, -3.5);

    // 5. Control Plane Supervisors Floor (Y=4.5)
    createTray(7.2, 4.6, 0.30, 0x6d28d9, 0xa78bfa, 4.5);

    // 6. Optional Framework Floor for Ray / Spark (Y=2.5)
    if (hasRay) {
      createTray(7.2, 4.6, 0.30, 0x9333ea, 0xc084fc, 2.5);
    }

    // 7. Worker Node Floor Trays (Tier 0 at Y = 0.5)
    // SPEC-03: Replace loop of vertical worker trays with a SINGLE wide Worker Deck tray
    const actualWorkers = Math.max(workerCount, 1);
    const deckWidth = 10.0 + (actualWorkers - 1) * 6.0;
    const deckDepth = 6.5;
    const deckHeight = 0.35;
    
    // Create the main wide deck
    createTray(deckWidth, deckDepth, deckHeight, 0x047857, 0x34d399, 0.5, 0.0);

    // Create individual chassis plates on top of the wide deck.
    // TASK-CV-903: when machineShapes are provided, dimension each node chassis
    // footprint proportionally and style by capacity type / accelerators.
    const specs = this.buildChassisSpecs(actualWorkers);
    const maxChassisDepth = specs.reduce((m, s) => Math.max(m, s.depth), 4.8);
    const chassisHeight = 0.08;
    const chassisY = 0.5 + deckHeight / 2 + chassisHeight / 2;

    // Lay chassis out left-to-right, centered, sized by footprint
    const CHASSIS_GAP = 0.8;
    const totalSpan =
      specs.reduce((sum, s) => sum + s.width, 0) + CHASSIS_GAP * Math.max(specs.length - 1, 0);
    // Widen the deck if the machine shapes demand more room than the default
    if (totalSpan + 1.5 > deckWidth && this.trays.length > 0) {
      const deckGroup = this.trays[this.trays.length - 1];
      if (deckGroup) {
        const scale = (totalSpan + 1.5) / deckWidth;
        deckGroup.scale.x = scale;
      }
    }

    let cursorX = -totalSpan / 2.0;
    for (const spec of specs) {
      const cx = cursorX + spec.width / 2.0;
      cursorX += spec.width + CHASSIS_GAP;

      const chassisGroup = new THREE.Group();
      chassisGroup.position.set(cx, chassisY, 0.0);
      chassisGroup.userData = { machineShapeName: spec.name };

      const isSpot = spec.capacityType === 'spot';

      // Chassis Base Slab:
      //  - On-Demand: dark brushed titanium (high metalness, low roughness)
      //  - Spot: translucent smoked acrylic (low metalness, high transparency)
      const chassisBaseGeo = new THREE.BoxGeometry(spec.width, chassisHeight, spec.depth);
      const chassisBaseMat = new THREE.MeshStandardMaterial(
        isSpot
          ? {
              color: 0x1c1917,
              roughness: 0.6,
              metalness: 0.05,
              transparent: true,
              opacity: 0.38,
              depthWrite: false,
            }
          : {
              color: 0x2b333a,
              roughness: 0.28,
              metalness: 0.92,
              transparent: true,
              opacity: 0.85,
            }
      );
      const chassisBase = new THREE.Mesh(chassisBaseGeo, chassisBaseMat);
      chassisGroup.add(chassisBase);

      // Rim colour: cyan for on-demand, hazard amber for spot
      const cRimColor = isSpot ? 0xf59e0b : 0x22d3ee;
      const cRimThickness = isSpot ? 0.10 : 0.05;
      const cRimHeight = chassisHeight * (isSpot ? 1.4 : 0.6);
      const cRimMat = new THREE.MeshStandardMaterial({
        color: cRimColor,
        roughness: 0.2,
        metalness: isSpot ? 0.3 : 0.6,
        emissive: new THREE.Color(cRimColor),
        emissiveIntensity: isSpot ? 0.55 : 0.25,
        transparent: true,
        opacity: isSpot ? 0.95 : 0.8,
      });

      // Front & Back Rims for Chassis
      const cFbGeo = new THREE.BoxGeometry(spec.width, cRimHeight, cRimThickness);
      const cFrontRim = new THREE.Mesh(cFbGeo, cRimMat);
      cFrontRim.position.set(0, chassisHeight / 2 + cRimHeight / 2, spec.depth / 2 - cRimThickness / 2);
      chassisGroup.add(cFrontRim);

      const cBackRim = new THREE.Mesh(cFbGeo, cRimMat);
      cBackRim.position.set(0, chassisHeight / 2 + cRimHeight / 2, -spec.depth / 2 + cRimThickness / 2);
      chassisGroup.add(cBackRim);

      // Left & Right Rims for Chassis
      const cLrGeo = new THREE.BoxGeometry(cRimThickness, cRimHeight, spec.depth - cRimThickness * 2);
      const cLeftRim = new THREE.Mesh(cLrGeo, cRimMat);
      cLeftRim.position.set(-spec.width / 2 + cRimThickness / 2, chassisHeight / 2 + cRimHeight / 2, 0);
      chassisGroup.add(cLeftRim);

      const cRightRim = new THREE.Mesh(cLrGeo, cRimMat);
      cRightRim.position.set(spec.width / 2 - cRimThickness / 2, chassisHeight / 2 + cRimHeight / 2, 0);
      chassisGroup.add(cRightRim);

      if (isSpot) {
        // Hazard hazard-strip band around the top edge of the chassis
        const hazard = this.createHazardBand(spec.width, spec.depth);
        hazard.position.y = chassisHeight / 2 + 0.005;
        chassisGroup.add(hazard);
      } else {
        // On-Demand: cyan power rail edge glow along the front edge
        const railGeo = new THREE.BoxGeometry(spec.width * 0.92, 0.025, 0.045);
        const railMat = new THREE.MeshStandardMaterial({
          color: 0x67e8f9,
          emissive: new THREE.Color(0x22d3ee),
          emissiveIntensity: 1.4,
          roughness: 0.1,
          metalness: 0.2,
          transparent: true,
          opacity: 0.95,
        });
        const rail = new THREE.Mesh(railGeo, railMat);
        rail.position.set(0, chassisHeight / 2 + 0.02, spec.depth / 2 + 0.01);
        chassisGroup.add(rail);
      }

      // Chassis Edges
      const cEdgesGeo = new THREE.EdgesGeometry(chassisBaseGeo);
      const cEdgeMat = new THREE.LineBasicMaterial({
        color: cRimColor,
        transparent: true,
        opacity: 0.9,
      });
      const cEdgeLines = new THREE.LineSegments(cEdgesGeo, cEdgeMat);
      chassisGroup.add(cEdgeLines);

      // Accelerated machines: docked power bay / heatsink manifold on rear face
      if (spec.acceleratorCount > 0) {
        const bay = this.createPowerBay(spec.width, spec.depth, spec.acceleratorCount, spec.acceleratorType);
        chassisGroup.add(bay);
      }

      this.scene.add(chassisGroup);
      this.trays.push(chassisGroup);
    }

    // ── TowerCage: Structural Corner Columns and Nx Bracket Frame ──
    // SPEC-03: Adjust outer structural tower cage to accommodate wide worker deck
    // The cage width must be at least as wide as the worker deck plus some margin
    const cageWidth = Math.max(8.6, deckWidth + 1.0);
    const cageDepth = Math.max(5.6, Math.max(deckDepth, maxChassisDepth) + 1.6);
    
    // The bottom of the cage should be below the worker deck
    // Worker deck is at Y=0.5, height 0.35. Bottom of deck is 0.5 - 0.35/2 = 0.325
    // Let's set bottomY slightly below that
    const bottomY = 0.5 - deckHeight / 2 - 0.6;
    const topY = 12.6;
    const cageHeight = topY - bottomY;
    const centerY = bottomY + cageHeight / 2;

    const cageGroup = new THREE.Group();
    cageGroup.position.set(0, centerY, 0);

    const postColor = 0x334155;
    const bracketColor = 0x1e293b;
    const postSize = 0.08;
    const bracketThickness = 0.04;

    const postMat = new THREE.MeshStandardMaterial({
      color: postColor,
      roughness: 0.4,
      metalness: 0.8,
      transparent: true,
      opacity: 0.5,
    });
    const bracketMat = new THREE.MeshStandardMaterial({
      color: bracketColor,
      roughness: 0.5,
      metalness: 0.6,
      transparent: true,
      opacity: 0.4,
    });

    // 4 Vertical Corner Structural Posts
    const postGeo = new THREE.BoxGeometry(postSize, cageHeight, postSize);
    const hw = cageWidth / 2;
    const hd = cageDepth / 2;

    const posts = [
      new THREE.Vector3(-hw, 0, -hd),
      new THREE.Vector3(hw, 0, -hd),
      new THREE.Vector3(-hw, 0, hd),
      new THREE.Vector3(hw, 0, hd),
    ];

    posts.forEach((pos) => {
      const post = new THREE.Mesh(postGeo, postMat);
      post.position.copy(pos);
      cageGroup.add(post);
    });

    // Horizontal Structural Brackets
    const hBracketGeoX = new THREE.BoxGeometry(cageWidth, bracketThickness, bracketThickness);
    const hBracketGeoZ = new THREE.BoxGeometry(bracketThickness, bracketThickness, cageDepth);

    const addBrackets = (yOffset: number) => {
      const front = new THREE.Mesh(hBracketGeoX, bracketMat);
      front.position.set(0, yOffset, hd);
      cageGroup.add(front);

      const back = new THREE.Mesh(hBracketGeoX, bracketMat);
      back.position.set(0, yOffset, -hd);
      cageGroup.add(back);

      const left = new THREE.Mesh(hBracketGeoZ, bracketMat);
      left.position.set(-hw, yOffset, 0);
      cageGroup.add(left);

      const right = new THREE.Mesh(hBracketGeoZ, bracketMat);
      right.position.set(hw, yOffset, 0);
      cageGroup.add(right);
    };

    addBrackets(cageHeight / 2);  // Penthouse top
    addBrackets(-cageHeight / 2); // Foundation bottom

    // Subtle bracket lines for key floors
    // We add brackets for the main structural floors above the worker deck
    const keyFloorsY = [2.5, 4.5, 5.5, 7.0, 9.5, 12.0];
    keyFloorsY.forEach((fy) => {
      const wy = fy - centerY;
      addBrackets(wy);
    });

    // Add a bracket specifically at the worker deck level for visual anchoring
    const workerDeckBracketY = 0.5 - centerY;
    addBrackets(workerDeckBracketY);

    this.scene.add(cageGroup);
    this.cage = cageGroup;
  }

  /**
   * TASK-CV-903: Swap in machine shapes from a fresh ClusterGraph snapshot
   * without rebuilding the Ground Datum (cutaway opacity state is preserved).
   */
  public setMachineShapes(machineShapes: MachineShapeData[] | undefined): void {
    this.machineShapes = machineShapes ?? [];
  }

  /**
   * TASK-CV-903: Normalize the provided machine shapes into chassis placement
   * specs. Falls back to `workerCount` generic on-demand chassis (legacy deck
   * look) when no machine shapes are present on the snapshot.
   */
  private buildChassisSpecs(workerCount: number): ChassisSpec[] {
    if (this.machineShapes.length === 0) {
      const specs: ChassisSpec[] = [];
      for (let i = 0; i < workerCount; i++) {
        specs.push({
          name: `worker-${i}`,
          width: 5.2,
          depth: 4.8,
          capacityType: 'on-demand',
          acceleratorCount: 0,
        });
      }
      return specs;
    }
    return this.machineShapes.map((m) => {
      const { width, depth } = chassisFootprint(m);
      return {
        name: m.node_name,
        width,
        depth,
        capacityType: m.capacity_type === 'spot' ? 'spot' : 'on-demand',
        acceleratorType: m.accelerator_type,
        acceleratorCount: Math.max(m.accelerator_count ?? 0, 0),
      };
    });
  }

  /**
   * TASK-CV-903: Yellow-black hazard warning border band ringing the chassis
   * top edge (used for Spot capacity nodes).
   */
  private createHazardBand(width: number, depth: number): THREE.Group {
    const band = new THREE.Group();
    const t = 0.12; // band thickness
    const h = 0.02;

    const amber = new THREE.MeshStandardMaterial({
      color: 0xfacc15,
      emissive: new THREE.Color(0xf59e0b),
      emissiveIntensity: 0.7,
      roughness: 0.4,
      metalness: 0.1,
      transparent: true,
      opacity: 0.95,
    });
    const black = new THREE.MeshStandardMaterial({
      color: 0x0a0a0a,
      roughness: 0.8,
      metalness: 0.1,
      transparent: true,
      opacity: 0.95,
    });

    // Alternate amber/black segments along front and back edges
    const longSegs = Math.max(4, Math.round(width / 0.5));
    const segLen = width / longSegs;
    for (let i = 0; i < longSegs; i++) {
      const mat = i % 2 === 0 ? amber : black;
      const gx = -width / 2 + segLen / 2 + i * segLen;

      const front = new THREE.Mesh(new THREE.BoxGeometry(segLen, h, t), mat);
      front.position.set(gx, 0, depth / 2 - t / 2);
      band.add(front);

      const back = new THREE.Mesh(new THREE.BoxGeometry(segLen, h, t), mat);
      back.position.set(gx, 0, -depth / 2 + t / 2);
      band.add(back);
    }

    // Short edges (single alternating colour each)
    const leftMat = longSegs % 2 === 0 ? black : amber;
    const rightMat = amber;
    const left = new THREE.Mesh(new THREE.BoxGeometry(t, h, depth - 2 * t), leftMat);
    left.position.set(-width / 2 + t / 2, 0, 0);
    band.add(left);

    const right = new THREE.Mesh(new THREE.BoxGeometry(t, h, depth - 2 * t), rightMat);
    right.position.set(width / 2 - t / 2, 0, 0);
    band.add(right);

    return band;
  }

  /**
   * TASK-CV-903: Docked power bay / heatsink manifold on the rear face
   * (z = -depth/2 - 0.35) with N illuminated accelerator core meshes.
   * Core glow: green for nvidia, cyan for TPU.
   */
  private createPowerBay(
    chassisWidth: number,
    chassisDepth: number,
    coreCount: number,
    acceleratorType?: string
  ): THREE.Group {
    const bay = new THREE.Group();
    const coreColor = acceleratorCoreColor(acceleratorType);

    const bayDepth = 0.5;
    const bayHeight = 0.34;
    const bayWidth = Math.min(chassisWidth * 0.85, 5.0);

    // Manifold housing block
    const housingGeo = new THREE.BoxGeometry(bayWidth, bayHeight, bayDepth);
    const housingMat = new THREE.MeshStandardMaterial({
      color: 0x111827,
      roughness: 0.35,
      metalness: 0.85,
      transparent: true,
      opacity: 0.9,
    });
    const housing = new THREE.Mesh(housingGeo, housingMat);
    housing.position.set(0, 0.1, -chassisDepth / 2 - 0.35);
    bay.add(housing);

    // Manifold spine / conduit running along the bay top
    const spineGeo = new THREE.BoxGeometry(bayWidth * 0.95, 0.05, 0.08);
    const spineMat = new THREE.MeshStandardMaterial({
      color: 0x334155,
      roughness: 0.25,
      metalness: 0.9,
    });
    const spine = new THREE.Mesh(spineGeo, spineMat);
    spine.position.set(0, 0.1 + bayHeight / 2 + 0.02, -chassisDepth / 2 - 0.35);
    bay.add(spine);

    // N illuminated accelerator core cores on the rear face of the housing
    const n = Math.min(coreCount, 8);
    const coreRadius = 0.06;
    const coreGeo = new THREE.SphereGeometry(coreRadius, 12, 12);
    const spacing = Math.min(0.42, (bayWidth - 0.3) / Math.max(n, 1));
    const startZ = -chassisDepth / 2 - 0.35 - bayDepth / 2 - 0.01;
    const startX = -((n - 1) * spacing) / 2;

    for (let i = 0; i < n; i++) {
      const coreMat = new THREE.MeshStandardMaterial({
        color: coreColor,
        emissive: new THREE.Color(coreColor),
        emissiveIntensity: 1.6,
        roughness: 0.1,
        metalness: 0.0,
      });
      const core = new THREE.Mesh(coreGeo, coreMat);
      core.position.set(startX + i * spacing, 0.1, startZ);
      bay.add(core);
      this.coreMaterials.push(coreMat);
    }

    return bay;
  }

  /**
   * TASK-CV-903: Set the Ground Datum opacity target (clamped 0.05..1.0).
   * The fade is animated smoothly towards the target in update().
   */
  public setGroundOpacity(opacity: number): void {
    this.groundTargetOpacity = clamp(opacity, 0.05, 1.0);
  }

  /**
   * TASK-CV-903: Flip the ground cutaway state: fully solid (1.0) <-> faded
   * ghost (0.1). Returns the new target opacity.
   */
  public toggleGroundCutaway(): number {
    const faded = this.groundTargetOpacity <= 0.5;
    this.setGroundOpacity(faded ? 1.0 : 0.1);
    return this.groundTargetOpacity;
  }

  public get groundCutawayActive(): boolean {
    return this.groundTargetOpacity <= 0.5;
  }

  /**
   * Per-frame animation tick: smooth ground fade + accelerator core pulse.
   */
  public update(delta: number, time: number): void {
    // Exponential smoothing towards the ground opacity target
    if (this.groundOpacity !== this.groundTargetOpacity) {
      const k = 1.0 - Math.exp(-6.0 * Math.max(delta, 0));
      this.groundOpacity += (this.groundTargetOpacity - this.groundOpacity) * k;
      if (Math.abs(this.groundOpacity - this.groundTargetOpacity) < 0.003) {
        this.groundOpacity = this.groundTargetOpacity;
      }
      this.groundPlaneMat.opacity = this.groundOpacity;
      this.groundGridMat.opacity =
        LayerTrayManager.GROUND_GRID_BASE_OPACITY * this.groundOpacity;
    }

    // Subtle breathing pulse on accelerator cores
    if (this.coreMaterials.length > 0) {
      const pulse = 1.3 + 0.5 * Math.sin(time * 3.2);
      for (const mat of this.coreMaterials) {
        mat.emissiveIntensity = pulse;
      }
    }
  }

  /**
   * Cleanly disposes all geometries, materials, and groups.
   */
  public clear(): void {
    this.coreMaterials = [];
    this.trays.forEach((tray) => {
      tray.traverse((child) => {
        if (child instanceof THREE.Mesh || child instanceof THREE.LineSegments || child instanceof THREE.Line) {
          child.geometry.dispose();
          if (Array.isArray(child.material)) {
            child.material.forEach((m) => m.dispose());
          } else {
            child.material.dispose();
          }
        }
      });
      if (tray.parent) {
        tray.parent.remove(tray);
      }
    });
    this.trays = [];

    if (this.cage) {
      this.cage.traverse((child) => {
        if (child instanceof THREE.Mesh || child instanceof THREE.LineSegments || child instanceof THREE.Line) {
          child.geometry.dispose();
          if (Array.isArray(child.material)) {
            child.material.forEach((m) => m.dispose());
          } else {
            child.material.dispose();
          }
        }
      });
      if (this.cage.parent) {
        this.cage.parent.remove(this.cage);
      }
      this.cage = null;
    }
  }
}
