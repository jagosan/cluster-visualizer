import * as THREE from 'three';

export interface FlowEdgeData {
  sourcePos: THREE.Vector3;
  targetPos: THREE.Vector3;
  flowType: string;
  volumeLabel?: string;
}

/**
 * SPEC-10 §6.3 / TASK-CV-1105: live traffic-harness modulation of the
 * conduit particle streams. The TrafficControlDeck drives these knobs from
 * the simulator's per-viewport RPS + latency every frame:
 *   speedGain    — stream speed multiplier stacked on `update()`'s arg,
 *                  scaling directly with RPS;
 *   tint         — hex the tranquil base colors blend toward (cyan < 30 ms,
 *                  amber 30–150 ms, crimson > 200 ms); null restores base;
 *   tintStrength — 0..1 blend fraction toward the tint;
 *   surgeCount   — extra "congestion surge" particles spawned on random
 *                  conduit curves (particle density ∝ RPS); idempotent,
 *                  cheap to call every frame.
 */
export interface FlowModulationOptions {
  speedGain?: number;
  tint?: number | null;
  tintStrength?: number;
  surgeCount?: number;
  surgeColor?: number;
}

export class FlowParticleSystem {
  public group: THREE.Group = new THREE.Group();
  private curves: THREE.Curve<THREE.Vector3>[] = [];
  private particles: {
    mesh: THREE.Mesh;
    curve: THREE.Curve<THREE.Vector3>;
    progress: number;
    speed: number;
    baseColor: THREE.Color;
    isSurge?: boolean;
  }[] = [];
  private decor: { mat: THREE.LineBasicMaterial; baseColor: THREE.Color }[] = [];

  // SPEC-10 §6.3 modulation state (identity until the traffic harness drives it)
  private speedGain = 1;
  private tint: THREE.Color | null = null;
  private tintStrength = 0;
  private surgeTarget = 0;
  private surgeColor = 0x38bdf8;

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
    this.decor = [];
    // SPEC-10 §6.3: rebuilding the graph restores tranquil modulation.
    this.speedGain = 1;
    this.tint = null;
    this.tintStrength = 0;
    this.surgeTarget = 0;
  }

  public addCurveParticle(
    curve: THREE.Curve<THREE.Vector3>,
    colorHex: number = 0x00ffcc,
    speed: number = 0.25,
    size: number = 0.12
  ) {
    this.curves.push(curve);

    const particleGeo = new THREE.SphereGeometry(size, 8, 8);
    const particleMat = new THREE.MeshBasicMaterial({
      color: colorHex,
      transparent: true,
      opacity: 0.95,
      blending: THREE.AdditiveBlending,
    });
    const particleMesh = new THREE.Mesh(particleGeo, particleMat);
    this.group.add(particleMesh);

    this.particles.push({
      mesh: particleMesh,
      curve,
      progress: Math.random(),
      speed: speed + Math.random() * 0.05,
      baseColor: new THREE.Color(colorHex),
    });
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
    this.decor.push({ mat: lineMat, baseColor: new THREE.Color(colorHex) });

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
      baseColor: new THREE.Color(colorHex),
    });
  }

  /**
   * SPEC-10 §6.3 / TASK-CV-1105: drive the live traffic-harness modulation.
   * Idempotent — safe to call every frame with the current RPS/latency.
   */
  public setModulation(opts: FlowModulationOptions): void {
    if (opts.speedGain !== undefined) {
      this.speedGain = THREE.MathUtils.clamp(opts.speedGain, 0, 4);
    }
    if (opts.surgeColor !== undefined) this.surgeColor = opts.surgeColor;
    if (opts.tint !== undefined) {
      this.tint = opts.tint === null ? null : new THREE.Color(opts.tint);
    }
    if (opts.tintStrength !== undefined) {
      this.tintStrength = THREE.MathUtils.clamp(opts.tintStrength, 0, 1);
    }
    if (opts.surgeCount !== undefined) {
      this.surgeTarget = Math.max(0, Math.floor(opts.surgeCount));
    }
    this.reconcileSurge();
    this.recolor();
  }

  /** Restore tranquil base colors, speed, and drop surge particles. */
  public clearModulation(): void {
    this.speedGain = 1;
    this.tint = null;
    this.tintStrength = 0;
    this.surgeTarget = 0;
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      if (p?.isSurge) {
        p.mesh.geometry.dispose();
        (p.mesh.material as THREE.Material).dispose();
        this.group.remove(p.mesh);
        this.particles.splice(i, 1);
      }
    }
    this.recolor();
  }

  /** Spawn/remove surge particles so `particles.filter(isSurge)` == surgeTarget. */
  private reconcileSurge(): void {
    if (this.curves.length === 0) return;
    let surge = 0;
    for (const p of this.particles) if (p.isSurge) surge++;
    while (surge < this.surgeTarget) {
      const curve = this.curves[Math.floor(Math.random() * this.curves.length)];
      if (!curve) break;
      const geo = new THREE.SphereGeometry(0.07, 6, 8);
      const mat = new THREE.MeshBasicMaterial({
        color: this.surgeColor,
        transparent: true,
        opacity: 0.85,
        blending: THREE.AdditiveBlending,
      });
      const mesh = new THREE.Mesh(geo, mat);
      this.group.add(mesh);
      this.particles.push({
        mesh,
        curve,
        progress: Math.random(),
        speed: 0.35 + Math.random() * 0.35,
        baseColor: new THREE.Color(this.surgeColor),
        isSurge: true,
      });
      surge++;
    }
    while (surge > this.surgeTarget) {
      for (let i = this.particles.length - 1; i >= 0; i--) {
        const p = this.particles[i];
        if (p?.isSurge) {
          p.mesh.geometry.dispose();
          (p.mesh.material as THREE.Material).dispose();
          this.group.remove(p.mesh);
          this.particles.splice(i, 1);
          surge--;
          break;
        }
      }
      if (surge <= this.surgeTarget) break;
    }
  }

  /** Blend particle + conduit-line colors toward the live latency tint. */
  private recolor(): void {
    const strength = this.tint && this.tintStrength > 0 ? this.tintStrength : 0;
    for (const p of this.particles) {
      const mat = p.mesh.material as THREE.MeshBasicMaterial;
      if (strength > 0) mat.color.copy(p.baseColor).lerp(this.tint!, strength);
      else mat.color.copy(p.baseColor);
    }
    for (const d of this.decor) {
      if (strength > 0) d.mat.color.copy(d.baseColor).lerp(this.tint!, strength);
      else d.mat.color.copy(d.baseColor);
    }
  }

  public update(delta: number, speedMultiplier: number = 1.0) {
    const gain = speedMultiplier * this.speedGain;
    for (const p of this.particles) {
      p.progress += delta * p.speed * gain;
      if (p.progress > 1.0) p.progress -= 1.0;
      const pt = p.curve.getPoint(p.progress);
      p.mesh.position.copy(pt);
    }
  }
}
