import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

export class CameraSyncController {
  private controlsA: OrbitControls;
  private controlsB: OrbitControls;
  public enabled: boolean = true;
  private isSyncing: boolean = false;

  constructor(controlsA: OrbitControls, controlsB: OrbitControls) {
    this.controlsA = controlsA;
    this.controlsB = controlsB;

    this.controlsA.addEventListener('change', () => {
      if (!this.enabled || this.isSyncing) return;
      this.isSyncing = true;
      this.syncControls(this.controlsA, this.controlsB);
      this.isSyncing = false;
    });

    this.controlsB.addEventListener('change', () => {
      if (!this.enabled || this.isSyncing) return;
      this.isSyncing = true;
      this.syncControls(this.controlsB, this.controlsA);
      this.isSyncing = false;
    });
  }

  private syncControls(source: OrbitControls, target: OrbitControls) {
    target.object.position.copy(source.object.position);
    target.object.rotation.copy(source.object.rotation);
    if ('zoom' in source.object && 'zoom' in target.object) {
      (target.object as any).zoom = (source.object as any).zoom;
    }
    if ('updateProjectionMatrix' in target.object) {
      (target.object as any).updateProjectionMatrix();
    }
    target.target.copy(source.target);
    target.update();
  }
}
