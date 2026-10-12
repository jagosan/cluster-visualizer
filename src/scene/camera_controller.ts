import * as THREE from 'three';

/**
 * SPEC-13 §3.6 / ADR-1304 (TASK-CV-1405): Dual-Projection CAD Mode.
 *
 * `DualProjectionState` describes the live state of the perspective ⇄ orthographic
 * camera transition used by the 2.5D Orthographic Floor-Cut view (`KeyF`).
 */
export interface DualProjectionState {
  /** True once the transition has fully settled into orthographic CAD mode. */
  isOrthographic: boolean;
  /** 0.0 (Perspective) → 1.0 (Orthographic CAD), eased over 600ms. */
  transitionProgress: number;
  perspectiveCamera: THREE.PerspectiveCamera;
  orthographicCamera: THREE.OrthographicCamera;
  activeCamera: THREE.Camera;
  /** Whether the CAD architectural floor-strata grid is currently visible. */
  cadGridVisible: boolean;
}

/** Smooth (600ms) transition duration between projection modes, per SPEC-13 §3.6.1. */
const TRANSITION_DURATION = 0.6;

/** Default perspective orbit pose (matches `ClusterViewport` defaults). */
const DEFAULT_POSITION = new THREE.Vector3(16, 7, 20);
const DEFAULT_TARGET = new THREE.Vector3(0, 3.5, 0);

/** Orthographic CAD plan-view camera altitude above the floor datum. */
const CAD_CAMERA_HEIGHT = 40;

/** Architectural grid extents (world units) for the floor strata cross-sections. */
const GRID_HALF_EXTENT = 20;
const GRID_MINOR_STEP = 1;
const GRID_MAJOR_EVERY = 5;

/**
 * SPEC-13 §3.6 / ADR-1304 (TASK-CV-1405): Dual-Projection CameraController.
 *
 * Holds both a `PerspectiveCamera` (3D Isometric Elevation) and an
 * `OrthographicCamera` (2.5D CAD Floor-Cut). Pressing `KeyF` triggers a smooth
 * 600ms transition between the two projections, synchronizing position, target, and
 * view frustum bounds at every frame so the switch never produces a camera jump.
 *
 * The orthographic frustum is continuously recomputed to match the perspective
 * camera's vertical field of view at the distance-to-target, making the two cameras
 * visually interchangeable at any point in the transition. Both cameras share a single
 * interpolated position/target/up triple, so there is never a geometric discontinuity.
 */
export class CameraController {
  private scene: THREE.Scene | null = null;

  private perspectiveCamera: THREE.PerspectiveCamera;
  private orthographicCamera: THREE.OrthographicCamera;

  /** Shared interpolated camera pose (both cameras mirror this every frame). */
  private position = DEFAULT_POSITION.clone();
  private target = DEFAULT_TARGET.clone();
  private up = new THREE.Vector3(0, 1, 0);

  /** CAD plan-view pose derived from the default orbit pose. */
  private readonly cadPosition = new THREE.Vector3(
    DEFAULT_TARGET.x,
    CAD_CAMERA_HEIGHT,
    DEFAULT_TARGET.z,
  );
  private readonly cadTarget = DEFAULT_TARGET.clone();
  /** In CAD mode we look straight down with -Z as screen-up (architectural plan). */
  private readonly cadUp = new THREE.Vector3(0, 0, -1);

  /** 0.0 → 1.0; eased and used for both pose interpolation and visibility. */
  private progress = 0;
  private progressTarget = 0;

  private initialized = false;
  private aspect = 1;

  /** CAD architectural floor-strata grid lines (plan + cross-section strata). */
  private cadGrid: THREE.Group | null = null;
  private readonly gridMaterials: THREE.LineBasicMaterial[] = [];

  private readonly boundKeyHandler: (event: KeyboardEvent) => void;

  constructor() {
    // Create both cameras up-front; they are positioned/synced in initialize().
    this.perspectiveCamera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000);
    this.orthographicCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 500);

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
      if (event.code === 'KeyF' || event.key === 'f' || event.key === 'F') {
        event.preventDefault();
        this.toggleProjection();
      }
    };
  }

  /**
   * Initialize the controller against a host container and scene. Creates the CAD
   * architectural grid, seeds both cameras to the default orbit pose, and registers
   * the `KeyF` keyboard listener.
   */
  initialize(container: HTMLElement, scene: THREE.Scene): void {
    this.scene = scene;

    const width = Math.max(1, container.clientWidth);
    const height = Math.max(1, container.clientHeight);
    this.aspect = width / height;

    // Seed both cameras to the shared default pose.
    this.syncCameraPose();

    // Build and attach the CAD floor-strata grid (hidden until CAD mode).
    this.buildCadGrid();
    scene.add(this.cadGrid as THREE.Group);
    this.setCadGridVisible(false);

    window.addEventListener('keydown', this.boundKeyHandler);
    this.initialized = true;
  }

  /**
   * Advance the projection transition and re-sync both cameras. Call once per frame
   * from the render loop.
   */
  update(deltaTime: number): void {
    if (!this.initialized) return;

    // Advance progress toward its target over TRANSITION_DURATION seconds.
    const step = deltaTime / TRANSITION_DURATION;
    if (this.progress < this.progressTarget) {
      this.progress = Math.min(this.progressTarget, this.progress + step);
    } else if (this.progress > this.progressTarget) {
      this.progress = Math.max(this.progressTarget, this.progress - step);
    }

    // Smooth-step the raw progress for eased pose interpolation.
    const eased = THREE.MathUtils.smoothstep(this.progress, 0, 1);

    // Interpolate the shared camera pose between orbit and CAD plan views.
    this.position.lerpVectors(DEFAULT_POSITION, this.cadPosition, eased);
    this.target.lerpVectors(DEFAULT_TARGET, this.cadTarget, eased);
    this.up.lerpVectors(new THREE.Vector3(0, 1, 0), this.cadUp, eased);

    // Sync both cameras to the shared pose and matched frustum (no jump cuts).
    this.syncCameraPose();

    // Reveal the CAD grid once we're meaningfully into orthographic mode.
    this.setCadGridVisible(this.progress > 0.5);
  }

  /** Toggle between 3D Perspective and 2.5D Orthographic CAD floor-cut view. */
  toggleProjection(): void {
    this.setProjection(!this.isOrthographic());
  }

  /**
   * Explicitly set the projection mode. `ortho === true` targets orthographic CAD,
   * `false` targets perspective.
   */
  setProjection(ortho: boolean): void {
    this.progressTarget = ortho ? 1 : 0;
  }

  /** Whether the controller has fully settled into orthographic CAD mode. */
  isOrthographic(): boolean {
    return this.progress >= 1;
  }

  /** The camera that should currently drive rendering (perspective until fully CAD). */
  getActiveCamera(): THREE.Camera {
    return this.isOrthographic() ? this.orthographicCamera : this.perspectiveCamera;
  }

  /** Snapshot of the current dual-projection state. */
  getState(): DualProjectionState {
    return {
      isOrthographic: this.isOrthographic(),
      transitionProgress: this.progress,
      perspectiveCamera: this.perspectiveCamera,
      orthographicCamera: this.orthographicCamera,
      activeCamera: this.getActiveCamera(),
      cadGridVisible: (this.cadGrid?.visible ?? false) && this.progress > 0.5,
    };
  }

  /**
   * Sync both cameras to the shared pose and re-derive the orthographic frustum so
   * it matches the perspective camera's vertical FOV at the distance-to-target.
   */
  private syncCameraPose(): void {
    const persp = this.perspectiveCamera;
    const ortho = this.orthographicCamera;

    // Position + orientation (shared by both cameras).
    persp.position.copy(this.position);
    persp.up.copy(this.up);
    persp.lookAt(this.target);

    ortho.position.copy(this.position);
    ortho.up.copy(this.up);
    ortho.lookAt(this.target);

    // Perspective projection.
    persp.aspect = this.aspect;
    persp.updateProjectionMatrix();

    // Orthographic frustum matched to the perspective FOV at current distance, so
    // swapping between the two cameras mid-transition is visually seamless.
    const dist = Math.max(0.001, this.position.distanceTo(this.target));
    const halfHeight =
      Math.tan(THREE.MathUtils.degToRad(persp.fov / 2)) * dist;
    const halfWidth = halfHeight * this.aspect;

    ortho.left = -halfWidth;
    ortho.right = halfWidth;
    ortho.top = halfHeight;
    ortho.bottom = -halfHeight;
    ortho.updateProjectionMatrix();
  }

  /** Build the CAD architectural floor-strata grid (plan + cross-section lines). */
  private buildCadGrid(): void {
    const group = new THREE.Group();
    group.name = 'cad-architectural-grid';

    const minorMat = new THREE.LineBasicMaterial({
      color: 0x334155,
      transparent: true,
      opacity: 0.5,
    });
    const majorMat = new THREE.LineBasicMaterial({
      color: 0x475569,
      transparent: true,
      opacity: 0.9,
    });

    // Plan grid lines in the XZ plane at floor datum y = 0.
    const minorPts: number[] = [];
    const majorPts: number[] = [];

    for (let i = -GRID_HALF_EXTENT; i <= GRID_HALF_EXTENT; i += GRID_MINOR_STEP) {
      const isMajor = Math.abs(i) % (GRID_MAJOR_EVERY * GRID_MINOR_STEP) === 0;
      const bucket = isMajor ? majorPts : minorPts;
      // Line along Z at x = i
      bucket.push(i, 0, -GRID_HALF_EXTENT, i, 0, GRID_HALF_EXTENT);
      // Line along X at z = i
      bucket.push(-GRID_HALF_EXTENT, 0, i, GRID_HALF_EXTENT, 0, i);
    }

    const minorGeo = new THREE.BufferGeometry();
    minorGeo.setAttribute('position', new THREE.Float32BufferAttribute(minorPts, 3));
    group.add(new THREE.LineSegments(minorGeo, minorMat));

    const majorGeo = new THREE.BufferGeometry();
    majorGeo.setAttribute('position', new THREE.Float32BufferAttribute(majorPts, 3));
    group.add(new THREE.LineSegments(majorGeo, majorMat));

    // Floor-strata cross-section datum lines at key elevations (vertical strata).
    const strataPts: number[] = [];
    for (const y of [0, 1.5, 3.5]) {
      strataPts.push(
        -GRID_HALF_EXTENT,
        y,
        -GRID_HALF_EXTENT,
        GRID_HALF_EXTENT,
        y,
        GRID_HALF_EXTENT,
      );
    }
    const strataMat = new THREE.LineBasicMaterial({
      color: 0x0ea5e9,
      transparent: true,
      opacity: 0.35,
    });
    const strataGeo = new THREE.BufferGeometry();
    strataGeo.setAttribute('position', new THREE.Float32BufferAttribute(strataPts, 3));
    group.add(new THREE.LineSegments(strataGeo, strataMat));

    this.gridMaterials.push(minorMat, majorMat, strataMat);
    this.cadGrid = group;
  }

  private setCadGridVisible(visible: boolean): void {
    if (this.cadGrid) {
      this.cadGrid.visible = visible;
    }
  }

  /** Remove the `KeyF` listener and release grid geometry/materials from the scene. */
  dispose(): void {
    window.removeEventListener('keydown', this.boundKeyHandler);

    if (this.scene && this.cadGrid) {
      this.scene.remove(this.cadGrid);
      this.cadGrid.traverse((child) => {
        const mesh = child as THREE.LineSegments;
        if (mesh.isLineSegments && mesh.geometry) {
          mesh.geometry.dispose();
        }
      });
    }

    for (const mat of this.gridMaterials) {
      mat.dispose();
    }
    this.gridMaterials.length = 0;

    this.cadGrid = null;
    this.perspectiveCamera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000);
    this.orthographicCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 500);
    this.progress = 0;
    this.progressTarget = 0;
    this.position.copy(DEFAULT_POSITION);
    this.target.copy(DEFAULT_TARGET);
    this.up.set(0, 1, 0);
    this.scene = null;
    this.initialized = false;
  }
}
