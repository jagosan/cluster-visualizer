/**
 * SPEC-13 / TASK-CV-1401: Instanced GPU Pod Renderer.
 *
 * Replaces the individual procedural pod meshes (`PodCapsuleManager`) with a
 * single pre-allocated `THREE.InstancedMesh` pipeline driven by custom vertex
 * buffer attributes (ADR-1301). Status color tints, alert pulse emission and VPA
 * scale tweens are computed directly inside custom GLSL chunks injected via
 * `onBeforeCompile`, eliminating per-frame JavaScript object allocations.
 *
 * Memory layout (SPEC-13 §3.1):
 *   - instanceMatrix : 16 floats per instance (4x4 matrix)
 *   - aInstanceData : 4 floats per instance
 *       x: status_code (0=Healthy, 1=CrashLoop, 2=OOM, 3=Pending)
 *       y: cpu_utilization_ratio (0.0 - 2.0)
 *       z: mem_utilization_ratio (0.0 - 2.0)
 *       w: diff_state (0=identical, 1=skew, 2=missing, 3=added)
 */

import * as THREE from 'three';

// ---------------------------------------------------------------------------
// Public contracts (SPEC-13 §3.1)
// ---------------------------------------------------------------------------

/** Dynamic GPU instance attributes backing the shared InstancedMesh. */
export interface InstanceDataBuffer {
  /** 16 floats per instance (4x4 matrix) — the InstancedMesh transform attribute. */
  instanceMatrix: THREE.InstancedBufferAttribute;
  /** 4 floats per instance:
   *    x: status_code (0=Healthy, 1=CrashLoop, 2=OOM, 3=Pending)
   *    y: cpu_utilization_ratio (0.0 - 2.0)
   *    z: mem_utilization_ratio (0.0 - 2.0)
   *    w: diff_state (0=identical, 1=skew, 2=missing, 3=added)
   */
  aInstanceData: THREE.InstancedBufferAttribute;
}

/** One pod's CPU-side record; mirrored into the GPU buffers by the renderer. */
export interface PodInstanceRecord {
  id: string;
  podName: string;
  namespace: string;
  nodeName: string;
  /** 0=Healthy, 1=CrashLoop, 2=OOM, 3=Pending. */
  statusCode: number;
  /** CPU actual/request utilization ratio (0.0 - 2.0). */
  cpuRatio: number;
  /** Mem actual/request utilization ratio (0.0 - 2.0). */
  memRatio: number;
  /** 0=identical, 1=skew, 2=missing, 3=added. */
  diffState: number;
  position: [number, number, number];
  scale: [number, number, number];
  quaternion: [number, number, number, number];
  isEjectedOutlier: boolean;
}

/** Renderer contract consumed by the Semantic LOD engine (TASK-CV-1402). */
export interface IInstancedPodRenderer {
  initialize(maxPods?: number): void;
  syncPods(pods: PodInstanceRecord[]): void;
  updatePod(podId: string, updates: Partial<PodInstanceRecord>): void;
  removePod(podId: string): void;
  setEjectionState(podId: string, ejected: boolean): void;
  updateAnimation(deltaTime: number): void;
  dispose(): void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Default pre-allocation budget (SPEC-13 §3.1: up to 30,000 pods). */
const DEFAULT_MAX_PODS = 30_000;

/** Capsule geometry parameters per SPEC-13 §3.1 (radius=0.35, length=0.8, 16, 16). */
const CAPSULE_RADIUS = 0.35;
const CAPSULE_LENGTH = 0.8;
const CAPSULE_CAP_SEGMENTS = 16;
const CAPSULE_RADIAL_SEGMENTS = 16;

/** Status codes (aInstanceData.x) per SPEC-13 §3.1. */
export const POD_STATUS_CODE = {
  HEALTHY: 0,
  CRASH_LOOP: 1,
  OOM: 2,
  PENDING: 3,
} as const;

/** Diff states (aInstanceData.w) per SPEC-13 §3.1. */
export const POD_DIFF_STATE = {
  IDENTICAL: 0,
  SKEW: 1,
  MISSING: 2,
  ADDED: 3,
} as const;

// ---------------------------------------------------------------------------
// InstancedPodRenderer
// ---------------------------------------------------------------------------

/**
 * Owns a single pre-allocated `THREE.InstancedMesh` of capsule geometry whose
 * per-instance status, utilization and diff data live in GPU attributes. The mesh
 * renders only `activeCount` instances; slots are compacted on removal so the
 * instance index range stays contiguous.
 */
export class InstancedPodRenderer implements IInstancedPodRenderer {
  private readonly scene: THREE.Scene;

  private mesh: THREE.InstancedMesh | null = null;
  private material: THREE.MeshStandardMaterial | null = null;
  private geometry: THREE.CapsuleGeometry | null = null;
  private buffer: InstanceDataBuffer | null = null;

  /** Internal instanced flag (0/1) driving the outlier ejection GPU tween. */
  private aEjectionState: THREE.InstancedBufferAttribute | null = null;

  // Raw typed-array views (cast from BufferAttribute.array) for fast writes.
  private matrixArray: Float32Array | null = null;
  private dataArray: Float32Array | null = null;
  private ejectionArray: Float32Array | null = null;

  private capacity = 0;
  private activeCount = 0;

  /** podId -> slot index (packed into [0, activeCount)). */
  private readonly podToSlot: Map<string, number> = new Map();
  /** slot index -> podId (undefined when the slot is free). */
  private readonly slotToPod: Array<string | undefined> = [];
  /** CPU-side record cache so partial updates can merge against last state. */
  private readonly records: Map<string, PodInstanceRecord> = new Map();

  /** Shared uniform object mutated each frame — no per-frame allocations. */
  private readonly pulseTimeUniform: { value: number } = { value: 0 };

  constructor(scene: THREE.Scene) {
    this.scene = scene;
  }

  // -------------------------------------------------------------------------
  // Lifecycle
  // -------------------------------------------------------------------------

  /** (Re)build the instanced capsule pipeline with a pre-allocated budget. */
  public initialize(maxPods?: number): void {
    if (this.mesh) this.dispose();
    const capacity = Math.max(1, Math.floor(maxPods ?? DEFAULT_MAX_PODS));
    this.capacity = capacity;
    this.activeCount = 0;
    this.podToSlot.clear();
    this.records.clear();
    this.slotToPod.length = capacity;

    // Single shared capsule geometry; custom instanced attributes attach to it.
    const geometry = new THREE.CapsuleGeometry(
      CAPSULE_RADIUS,
      CAPSULE_LENGTH,
      CAPSULE_CAP_SEGMENTS,
      CAPSULE_RADIAL_SEGMENTS,
    );
    this.geometry = geometry;

    const aInstanceData = new THREE.InstancedBufferAttribute(new Float32Array(capacity * 4), 4);
    aInstanceData.setUsage(THREE.DynamicDrawUsage);
    geometry.setAttribute('aInstanceData', aInstanceData);

    const aEjectionState = new THREE.InstancedBufferAttribute(new Float32Array(capacity), 1);
    aEjectionState.setUsage(THREE.DynamicDrawUsage);
    geometry.setAttribute('aEjectionState', aEjectionState);

    const material = new THREE.MeshStandardMaterial({
      color: 0x4fc3f7,
      emissive: 0x16283c,
      emissiveIntensity: 0.35,
      roughness: 0.32,
      metalness: 0.25,
    });
    this.configureShader(material);
    this.material = material;

    // InstancedMesh pre-allocates instanceMatrix sized to `count` (= capacity).
    const mesh = new THREE.InstancedMesh(geometry, material, capacity);
    mesh.name = 'InstancedPodRenderer';
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    mesh.count = 0;
    mesh.frustumCulled = false;
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    this.mesh = mesh;

    this.buffer = {
      instanceMatrix: mesh.instanceMatrix,
      aInstanceData,
    };
    this.aEjectionState = aEjectionState;

    this.matrixArray = mesh.instanceMatrix.array as Float32Array;
    this.dataArray = aInstanceData.array as Float32Array;
    this.ejectionArray = aEjectionState.array as Float32Array;

    this.scene.add(mesh);
  }

  /** Release all GPU and CPU resources and detach the mesh from the scene. */
  public dispose(): void {
    const mesh = this.mesh;
    if (mesh) {
      this.scene.remove(mesh);
      mesh.dispose();
    }
    this.geometry?.dispose();
    this.material?.dispose();

    this.mesh = null;
    this.material = null;
    this.geometry = null;
    this.buffer = null;
    this.aEjectionState = null;
    this.matrixArray = null;
    this.dataArray = null;
    this.ejectionArray = null;

    this.capacity = 0;
    this.activeCount = 0;
    this.podToSlot.clear();
    this.slotToPod.length = 0;
    this.records.clear();
  }

  // -------------------------------------------------------------------------
  // Data synchronization
  // -------------------------------------------------------------------------

  /** Full resync: removes stale pods and upserts every provided record. */
  public syncPods(pods: PodInstanceRecord[]): void {
    if (!this.mesh) this.initialize();

    const incoming = new Set(pods.map((p) => p.id));
    for (const podId of Array.from(this.podToSlot.keys())) {
      if (!incoming.has(podId)) this.removePod(podId);
    }

    for (const pod of pods) {
      const slot = this.allocateSlot(pod.id);
      this.records.set(pod.id, pod);
      this.writePodToSlot(slot, pod);
    }

    this.markBuffersDirty();
  }

  /** Merge a partial update into an existing pod's GPU record. */
  public updatePod(podId: string, updates: Partial<PodInstanceRecord>): void {
    if (!this.mesh) this.initialize();
    const slot = this.podToSlot.get(podId);
    if (slot === undefined) return;
    const current = this.records.get(podId);
    if (!current) return;

    const merged: PodInstanceRecord = { ...current, ...updates };
    this.records.set(podId, merged);
    this.writePodToSlot(slot, merged);
    this.markBuffersDirty();
  }

  /** Remove a pod and compact the slot so instances stay contiguous. */
  public removePod(podId: string): void {
    if (!this.mesh) return;
    const slot = this.podToSlot.get(podId);
    if (slot === undefined) return;

    this.releaseSlot(slot);
    this.records.delete(podId);
    this.markBuffersDirty();
  }

  /** Toggle GPU-side outlier ejection tween for a pod (0/1 instanced flag). */
  public setEjectionState(podId: string, ejected: boolean): void {
    if (!this.mesh) return;
    const slot = this.podToSlot.get(podId);
    if (slot === undefined || !this.ejectionArray) return;

    this.ejectionArray[slot] = ejected ? 1 : 0;
    if (this.aEjectionState) this.aEjectionState.needsUpdate = true;

    const rec = this.records.get(podId);
    if (rec) rec.isEjectedOutlier = ejected;
  }

  /** Advance the shared pulse-time uniform used by the GPU tweens. */
  public updateAnimation(deltaTime: number): void {
    if (!this.material) return;
    const dt = Number.isFinite(deltaTime) ? deltaTime : 0;
    this.pulseTimeUniform.value += dt;
  }

  // -------------------------------------------------------------------------
  // Accessors
  // -------------------------------------------------------------------------

  /** The live InstancedMesh (null until initialize). */
  public getMesh(): THREE.InstancedMesh | null {
    return this.mesh;
  }

  /** The GPU attribute pair backing the mesh (null until initialize). */
  public getInstanceBuffer(): InstanceDataBuffer | null {
    return this.buffer;
  }

  /** Number of instances currently rendered. */
  public get instanceCount(): number {
    return this.activeCount;
  }

  // -------------------------------------------------------------------------
  // Slot management
  // -------------------------------------------------------------------------

  private allocateSlot(podId: string): number {
    const existing = this.podToSlot.get(podId);
    if (existing !== undefined) return existing;

    if (this.activeCount >= this.capacity) this.grow();

    const slot = this.activeCount;
    this.podToSlot.set(podId, slot);
    this.slotToPod[slot] = podId;
    this.activeCount += 1;
    return slot;
  }

  /** Compact-remove: move the tail instance into the freed slot. */
  private releaseSlot(slot: number): void {
    const lastIndex = this.activeCount - 1;
    if (lastIndex !== slot) {
      this.copySlot(lastIndex, slot);
      const movedPodId = this.slotToPod[lastIndex];
      if (movedPodId !== undefined) {
        this.podToSlot.set(movedPodId, slot);
        this.slotToPod[slot] = movedPodId;
      }
    }
    this.slotToPod[lastIndex] = undefined;
    this.activeCount -= 1;
  }

  /** Copy all per-instance GPU data from one packed slot to another. */
  private copySlot(from: number, to: number): void {
    const matrix = this.matrixArray;
    const data = this.dataArray;
    const ejection = this.ejectionArray;
    if (!matrix || !data || !ejection) return;

    matrix.copyWithin(to * 16, from * 16, from * 16 + 16);
    data.copyWithin(to * 4, from * 4, from * 4 + 4);
    const ejected = ejection[from];
    if (ejected !== undefined) ejection[to] = ejected;
  }

  /** Double the pre-allocated budget, preserving existing instance data. */
  private grow(): void {
    const mesh = this.mesh;
    const geometry = this.geometry;
    const oldMatrix = this.matrixArray;
    const oldData = this.dataArray;
    const oldEjection = this.ejectionArray;
    if (!mesh || !geometry || !oldMatrix || !oldData || !oldEjection) return;

    const newCapacity = this.capacity * 2;

    const newMatrixAttr = new THREE.InstancedBufferAttribute(new Float32Array(newCapacity * 16), 16);
    newMatrixAttr.setUsage(THREE.DynamicDrawUsage);
    (newMatrixAttr.array as Float32Array).set(oldMatrix);

    const newDataAttr = new THREE.InstancedBufferAttribute(new Float32Array(newCapacity * 4), 4);
    newDataAttr.setUsage(THREE.DynamicDrawUsage);
    (newDataAttr.array as Float32Array).set(oldData);

    const newEjectionAttr = new THREE.InstancedBufferAttribute(new Float32Array(newCapacity), 1);
    newEjectionAttr.setUsage(THREE.DynamicDrawUsage);
    (newEjectionAttr.array as Float32Array).set(oldEjection);

    mesh.instanceMatrix = newMatrixAttr;
    geometry.setAttribute('aInstanceData', newDataAttr);
    geometry.setAttribute('aEjectionState', newEjectionAttr);

    this.capacity = newCapacity;
    this.buffer = { instanceMatrix: newMatrixAttr, aInstanceData: newDataAttr };
    this.aEjectionState = newEjectionAttr;
    this.matrixArray = newMatrixAttr.array as Float32Array;
    this.dataArray = newDataAttr.array as Float32Array;
    this.ejectionArray = newEjectionAttr.array as Float32Array;
    this.slotToPod.length = newCapacity;
  }

  /** Flag every dirty attribute and clamp the rendered instance count. */
  private markBuffersDirty(): void {
    const mesh = this.mesh;
    if (!mesh) return;
    mesh.count = this.activeCount;
    mesh.instanceMatrix.needsUpdate = true;
    if (this.buffer) this.buffer.aInstanceData.needsUpdate = true;
    if (this.aEjectionState) this.aEjectionState.needsUpdate = true;
  }

  // -------------------------------------------------------------------------
  // GPU buffer writers
  // -------------------------------------------------------------------------

  private writePodToSlot(slot: number, pod: PodInstanceRecord): void {
    this.writeMatrix(slot, pod.position, pod.quaternion, pod.scale);
    this.writeData(slot, pod.statusCode, pod.cpuRatio, pod.memRatio, pod.diffState);
    if (this.ejectionArray) this.ejectionArray[slot] = pod.isEjectedOutlier ? 1 : 0;
  }

  /** Compose a 4x4 column-major matrix directly into the instance buffer. */
  private writeMatrix(
    slot: number,
    position: [number, number, number],
    quaternion: [number, number, number, number],
    scale: [number, number, number],
  ): void {
    const a = this.matrixArray;
    if (!a) return;
    const o = slot * 16;

    const [px, py, pz] = position;
    const [qx, qy, qz, qw] = quaternion;
    const [sx, sy, sz] = scale;

    const x2 = qx + qx;
    const y2 = qy + qy;
    const z2 = qz + qz;
    const xx = qx * x2;
    const xy = qx * y2;
    const xz = qx * z2;
    const yy = qy * y2;
    const yz = qy * z2;
    const zz = qz * z2;
    const wx = qw * x2;
    const wy = qw * y2;
    const wz = qw * z2;

    a[o + 0] = (1 - (yy + zz)) * sx;
    a[o + 1] = (xy + wz) * sx;
    a[o + 2] = (xz - wy) * sx;
    a[o + 3] = 0;
    a[o + 4] = (xy - wz) * sy;
    a[o + 5] = (1 - (xx + zz)) * sy;
    a[o + 6] = (yz + wx) * sy;
    a[o + 7] = 0;
    a[o + 8] = (xz + wy) * sz;
    a[o + 9] = (yz - wx) * sz;
    a[o + 10] = (1 - (xx + yy)) * sz;
    a[o + 11] = 0;
    a[o + 12] = px;
    a[o + 13] = py;
    a[o + 14] = pz;
    a[o + 15] = 1;
  }

  /** Pack status/utilization/diff into the vec4 aInstanceData attribute. */
  private writeData(
    slot: number,
    statusCode: number,
    cpuRatio: number,
    memRatio: number,
    diffState: number,
  ): void {
    const a = this.dataArray;
    if (!a) return;
    const o = slot * 4;
    a[o + 0] = statusCode;
    a[o + 1] = cpuRatio;
    a[o + 2] = memRatio;
    a[o + 3] = diffState;
  }

  // -------------------------------------------------------------------------
  // Custom shader injection (SPEC-13 §3.1)
  // -------------------------------------------------------------------------

  /**
   * Inject the custom `aInstanceData` attribute plus status-color tinting, alert
   * pulse emission and GPU-driven scale tweens into the standard material.
   */
  private configureShader(material: THREE.MeshStandardMaterial): void {
    material.onBeforeCompile = (parameters) => {
      parameters.uniforms.uPulseTime = this.pulseTimeUniform;

      // ---- Vertex prefix: declare custom instanced attributes + varyings. ----
      const vertexPrefix =
        'attribute vec4 aInstanceData;\n' +
        'attribute float aEjectionState;\n' +
        'uniform float uPulseTime;\n' +
        'varying float vStatusCode;\n' +
        'varying float vCpuRatio;\n' +
        'varying float vMemRatio;\n' +
        'varying float vDiffState;\n' +
        'varying float vEjected;\n';

      parameters.vertexShader = parameters.vertexShader
        .replace('#include <common>', vertexPrefix + '#include <common>')
        .replace(
          '#include <project_vertex>',
          [
            '\t// GPU-driven scale tween (SPEC-13 §3.1): ejected outliers inflate with an alert strobe; anomalous statuses breathe.',
            '\tfloat instAnomalous = step( 0.5, aInstanceData.x );',
            '\tfloat instEjected = aEjectionState;',
            '\ttransformed *= 1.0 + 0.03 * sin( uPulseTime * 3.0 ) * instAnomalous;',
            '\ttransformed *= mix( 1.0, 1.18 + 0.10 * ( 0.5 + 0.5 * sin( uPulseTime * 8.0 ) ), instEjected );',
            '',
            '\tvStatusCode = aInstanceData.x;',
            '\tvCpuRatio = aInstanceData.y;',
            '\tvMemRatio = aInstanceData.z;',
            '\tvDiffState = aInstanceData.w;',
            '\tvEjected = aEjectionState;',
            '',
            '#include <project_vertex>',
          ].join('\n'),
        );

      // ---- Fragment prefix: varyings + pulse uniform. ----
      const fragmentPrefix =
        'uniform float uPulseTime;\n' +
        'varying float vStatusCode;\n' +
        'varying float vCpuRatio;\n' +
        'varying float vMemRatio;\n' +
        'varying float vDiffState;\n' +
        'varying float vEjected;\n';

      parameters.fragmentShader = parameters.fragmentShader
        .replace('#include <common>', fragmentPrefix + '#include <common>')
        .replace(
          '// accumulation',
          [
            '\t// Status color tint computed on the GPU from aInstanceData.x.',
            '\tvec3 statusTint = vec3( 1.0 );',
            '\tif ( vStatusCode < 0.5 ) {',
            '\t\tstatusTint = vec3( 0.85, 0.95, 1.05 ); // Healthy: cool blue lift',
            '\t} else if ( vStatusCode < 1.5 ) {',
            '\t\tstatusTint = vec3( 1.25, 0.55, 0.45 ); // CrashLoop: amber-red alert',
            '\t} else if ( vStatusCode < 2.5 ) {',
            '\t\tstatusTint = vec3( 1.35, 0.60, 0.50 ); // OOM: hot red',
            '\t} else {',
            '\t\tstatusTint = vec3( 1.15, 0.95, 0.65 ); // Pending: warm amber',
            '\t}',
            '',
            '\t// Utilization brightness: higher CPU/mem → brighter body.',
            '\tfloat utilFactor = clamp( 0.5 * vCpuRatio + 0.25 * vMemRatio, 0.6, 1.4 );',
            '\tdiffuseColor.rgb *= statusTint * utilFactor;',
            '',
            '\t// Diff-state accent tint (skew=amber, missing=red, added=green).',
            '\tif ( vDiffState > 2.5 ) {',
            '\t\tdiffuseColor.rgb *= vec3( 0.75, 1.15, 0.85 ); // added',
            '\t} else if ( vDiffState > 1.5 ) {',
            '\t\tdiffuseColor.rgb *= vec3( 1.25, 0.55, 0.45 ); // missing',
            '\t} else if ( vDiffState > 0.5 ) {',
            '\t\tdiffuseColor.rgb *= vec3( 1.15, 1.05, 0.60 ); // skew',
            '\t}',
            '',
            '\t// Alert pulse emission for anomalous / ejected outliers.',
            '\tfloat instAnomalous = step( 0.5, vStatusCode );',
            '\tfloat ejectionBoost = smoothstep( 0.1, 1.0, vEjected );',
            '\tfloat alertPulse = 0.35 + 0.25 * sin( uPulseTime * ( 4.0 + 3.0 * ejectionBoost ) );',
            '\ttotalEmissiveRadiance += vec3( 1.15, 0.42, 0.18 ) * instAnomalous * alertPulse;',
            '',
            '\t// accumulation',
          ].join('\n'),
        );
    };
  }
}
