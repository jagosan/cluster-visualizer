import * as THREE from 'three';

/**
 * SPEC-02: LayerTrayManager
 * Manages 3D semi-transparent rectangular layer trays and outer structural tower cages
 * matching the Peter Gostev Transformer vs DeepSeek architectural visual aesthetic.
 */
export class LayerTrayManager {
  private readonly scene: THREE.Scene;
  private trays: THREE.Group[] = [];
  private cage: THREE.Group | null = null;

  constructor(scene: THREE.Scene) {
    this.scene = scene;
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

    // Create individual sub-tray beveled chassis plates/outlines on top of the wide deck
    const chassisWidth = 5.2;
    const chassisDepth = 4.8;
    const chassisHeight = 0.08;
    const chassisY = 0.5 + deckHeight / 2 + chassisHeight / 2;
    const chassisBaseColor = 0x064e3b;
    const chassisRimColor = 0x10b981;

    for (let i = 0; i < actualWorkers; i++) {
      const x_i = -((actualWorkers - 1) * 6.0) / 2.0 + i * 6.0;
      
      const chassisGroup = new THREE.Group();
      chassisGroup.position.set(x_i, chassisY, 0.0);

      // Chassis Base Slab
      const chassisBaseGeo = new THREE.BoxGeometry(chassisWidth, chassisHeight, chassisDepth);
      const chassisBaseMat = new THREE.MeshStandardMaterial({
        color: chassisBaseColor,
        roughness: 0.3,
        metalness: 0.4,
        transparent: true,
        opacity: 0.6,
      });
      const chassisBase = new THREE.Mesh(chassisBaseGeo, chassisBaseMat);
      chassisGroup.add(chassisBase);

      // Chassis Rim/Rim Lip
      const cRimThickness = 0.05;
      const cRimHeight = chassisHeight * 0.6;
      const cRimMat = new THREE.MeshStandardMaterial({
        color: chassisRimColor,
        roughness: 0.2,
        metalness: 0.6,
        transparent: true,
        opacity: 0.8,
      });

      // Front & Back Rims for Chassis
      const cFbGeo = new THREE.BoxGeometry(chassisWidth, cRimHeight, cRimThickness);
      const cFrontRim = new THREE.Mesh(cFbGeo, cRimMat);
      cFrontRim.position.set(0, chassisHeight / 2 + cRimHeight / 2, chassisDepth / 2 - cRimThickness / 2);
      chassisGroup.add(cFrontRim);

      const cBackRim = new THREE.Mesh(cFbGeo, cRimMat);
      cBackRim.position.set(0, chassisHeight / 2 + cRimHeight / 2, -chassisDepth / 2 + cRimThickness / 2);
      chassisGroup.add(cBackRim);

      // Left & Right Rims for Chassis
      const cLrGeo = new THREE.BoxGeometry(cRimThickness, cRimHeight, chassisDepth - cRimThickness * 2);
      const cLeftRim = new THREE.Mesh(cLrGeo, cRimMat);
      cLeftRim.position.set(-chassisWidth / 2 + cRimThickness / 2, chassisHeight / 2 + cRimHeight / 2, 0);
      chassisGroup.add(cLeftRim);

      const cRightRim = new THREE.Mesh(cLrGeo, cRimMat);
      cRightRim.position.set(chassisWidth / 2 - cRimThickness / 2, chassisHeight / 2 + cRimHeight / 2, 0);
      chassisGroup.add(cRightRim);

      // Chassis Edges
      const cEdgesGeo = new THREE.EdgesGeometry(chassisBaseGeo);
      const cEdgeMat = new THREE.LineBasicMaterial({
        color: chassisRimColor,
        transparent: true,
        opacity: 0.9,
      });
      const cEdgeLines = new THREE.LineSegments(cEdgesGeo, cEdgeMat);
      chassisGroup.add(cEdgeLines);

      this.scene.add(chassisGroup);
      this.trays.push(chassisGroup);
    }

    // ── TowerCage: Structural Corner Columns and Nx Bracket Frame ──
    // SPEC-03: Adjust outer structural tower cage to accommodate wide worker deck
    // The cage width must be at least as wide as the worker deck plus some margin
    const cageWidth = Math.max(8.6, deckWidth + 1.0);
    const cageDepth = Math.max(5.6, deckDepth + 1.0);
    
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
   * Cleanly disposes all geometries, materials, and groups.
   */
  public clear(): void {
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
