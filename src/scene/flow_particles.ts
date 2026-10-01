import * as THREE from 'three';

export interface FlowEdgeData {
  sourcePos: THREE.Vector3;
  targetPos: THREE.Vector3;
  flowType: string;
  volumeLabel?: string;
}

export class FlowParticleSystem {
  public group: THREE.Group = new THREE.Group();
  private curves: THREE.QuadraticBezierCurve3[] = [];
  private particles: {
    mesh: THREE.Mesh;
    curve: THREE.QuadraticBezierCurve3;
    progress: number;
    speed: number;
  }[] = [];

  constructor() {
    this.group.name = 'FlowParticleSystem';
  }

  public clear() {
    while (this.group.children.length > 0) {
      const obj = this.group.children[0];
      if (!obj) break;
      if (obj instanceof THREE.Mesh) {
        obj.geometry.dispose();
        if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose());
        else obj.material.dispose();
      } else if (obj instanceof THREE.Line) {
        obj.geometry.dispose();
        if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose());
        else obj.material.dispose();
      }
      this.group.remove(obj);
    }
    this.curves = [];
    this.particles = [];
  }

  public addFlowEdge(edge: FlowEdgeData) {
    const mid = new THREE.Vector3()
      .addVectors(edge.sourcePos, edge.targetPos)
      .multiplyScalar(0.5);
    // Arch upward based on distance
    const dist = edge.sourcePos.distanceTo(edge.targetPos);
    mid.y += Math.max(0.6, dist * 0.25);

    const curve = new THREE.QuadraticBezierCurve3(edge.sourcePos, mid, edge.targetPos);
    this.curves.push(curve);

    // Color selection based on flowType
    let colorHex = 0x00ffcc; // Default cyan
    if (edge.flowType === 'data_replication') colorHex = 0xffa500; // Amber WAL
    else if (edge.flowType === 'framework_control') colorHex = 0xff00ff; // Magenta RPC
    else if (edge.flowType === 'control_plane') colorHex = 0x00ff88; // Emerald heartbeat

    // 1. Draw conduit trajectory curve
    const points = curve.getPoints(32);
    const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
    const lineMat = new THREE.LineBasicMaterial({
      color: colorHex,
      transparent: true,
      opacity: 0.25,
      blending: THREE.AdditiveBlending,
    });
    const line = new THREE.Line(lineGeo, lineMat);
    this.group.add(line);

    // 2. Pulse particle along curve
    const particleGeo = new THREE.SphereGeometry(0.09, 8, 8);
    const particleMat = new THREE.MeshBasicMaterial({
      color: colorHex,
      transparent: true,
      opacity: 0.9,
      blending: THREE.AdditiveBlending,
    });
    const particleMesh = new THREE.Mesh(particleGeo, particleMat);
    this.group.add(particleMesh);

    this.particles.push({
      mesh: particleMesh,
      curve,
      progress: Math.random(),
      speed: 0.15 + Math.random() * 0.1,
    });
  }

  public update(delta: number, speedMultiplier: number = 1.0) {
    for (const p of this.particles) {
      p.progress += delta * p.speed * speedMultiplier;
      if (p.progress > 1.0) p.progress -= 1.0;
      const pt = p.curve.getPoint(p.progress);
      p.mesh.position.copy(pt);
    }
  }
}
