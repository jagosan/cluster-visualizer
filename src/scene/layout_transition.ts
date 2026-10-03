export interface Vector3D {
  x: number;
  y: number;
  z: number;
}

export interface SpatialCoordinates {
  arch: Vector3D;
  latency: Vector3D;
}

export class LayoutTransitionController {
  private coordinates: Map<string, SpatialCoordinates> = new Map();
  private currentAlpha: number = 0.0;
  private targetAlpha: number = 0.0;
  private transitionDurationMs: number = 800;
  private elapsedMs: number = 0;
  private isTransitioning: boolean = false;

  registerNode(id: string, arch: Vector3D, latency?: Vector3D): void {
    const lat = latency ?? { x: arch.x, y: arch.y, z: arch.z };
    this.coordinates.set(id, { arch, latency: lat });
  }

  setLatencyCoordinate(id: string, latency: Vector3D): void {
    const coords = this.coordinates.get(id);
    if (coords) {
      coords.latency = latency;
    }
  }

  setTargetAlpha(alpha: number, durationMs?: number): void {
    this.targetAlpha = alpha;
    this.startAlpha = this.currentAlpha;
    if (durationMs !== undefined) {
      this.transitionDurationMs = durationMs;
    }
    this.elapsedMs = 0;
    this.isTransitioning = true;
  }

  setImmediateAlpha(alpha: number): void {
    this.currentAlpha = alpha;
    this.targetAlpha = alpha;
    this.isTransitioning = false;
    this.elapsedMs = 0;
  }

  getAlpha(): number {
    return this.currentAlpha;
  }

  isAnimating(): boolean {
    return this.isTransitioning;
  }

  update(deltaSeconds: number): boolean {
    if (!this.isTransitioning) {
      return false;
    }

    const deltaMs = deltaSeconds * 1000;
    this.elapsedMs += deltaMs;

    if (this.elapsedMs >= this.transitionDurationMs) {
      this.currentAlpha = this.targetAlpha;
      this.isTransitioning = false;
      this.elapsedMs = 0;
      return false;
    }

    const t = this.elapsedMs / this.transitionDurationMs;
    const easedT = this.easeInOutCubic(t);
    const startAlpha = this.startAlpha;
    this.currentAlpha = startAlpha + (this.targetAlpha - startAlpha) * easedT;

    return true;
  }

  private startAlpha: number = 0.0;

  private easeInOutCubic(t: number): number {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  getPosition(id: string): Vector3D | undefined {
    const coords = this.coordinates.get(id);
    if (!coords) {
      return undefined;
    }

    const a = this.currentAlpha;
    const arch = coords.arch;
    const latency = coords.latency;

    return {
      x: (1 - a) * arch.x + a * latency.x,
      y: (1 - a) * arch.y + a * latency.y,
      z: (1 - a) * arch.z + a * latency.z,
    };
  }

  getAllCurrentPositions(): Map<string, Vector3D> {
    const result = new Map<string, Vector3D>();
    for (const [id, coords] of this.coordinates.entries()) {
      const a = this.currentAlpha;
      const arch = coords.arch;
      const latency = coords.latency;
      
      result.set(id, {
        x: (1 - a) * arch.x + a * latency.x,
        y: (1 - a) * arch.y + a * latency.y,
        z: (1 - a) * arch.z + a * latency.z,
      });
    }
    return result;
  }
}
