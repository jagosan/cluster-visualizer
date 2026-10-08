import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { ClusterViewport } from './cluster_viewport.js';

export type GridMode = 'single' | 'dual' | 'quad';

export interface ViewportSlot {
  id: string;
  viewport: ClusterViewport;
  container: HTMLElement;
  title: string;
  clusterName: string;
  k8sVersion?: string;
  channel?: string;
  streamUrl?: string;
}

export interface GridControllerOptions {
  wrapperElement: HTMLElement;
  hudContainer?: HTMLElement | null;
  onModeChange?: (mode: GridMode) => void;
}

export class GridController {
  public mode: GridMode = 'dual';
  public syncCameras: boolean = true;
  private wrapper: HTMLElement;
  private slots: ViewportSlot[] = [];
  private isSyncing: boolean = false;
  private hudContainer: HTMLElement | null = null;
  private onModeChangeCb?: (mode: GridMode) => void;
  private boundKeyHandler: (event: KeyboardEvent) => void;

  constructor(options: GridControllerOptions, initialSlots: ViewportSlot[] = []) {
    this.wrapper = options.wrapperElement;
    this.hudContainer = options.hudContainer ?? null;
    this.onModeChangeCb = options.onModeChange;

    this.boundKeyHandler = this.handleKeyDown.bind(this);
    window.addEventListener('keydown', this.boundKeyHandler);

    for (const slot of initialSlots) {
      this.addSlot(slot);
    }

    this.setMode('dual');
  }

  public addSlot(slot: ViewportSlot): void {
    this.slots.push(slot);
    this.setupCameraSync(slot);
    this.applyGridStyles();
  }

  public getSlots(): ViewportSlot[] {
    return [...this.slots];
  }

  public getActiveSlots(): ViewportSlot[] {
    if (this.mode === 'single') {
      return this.slots.slice(0, 1);
    }
    if (this.mode === 'dual') {
      return this.slots.slice(0, 2);
    }
    // quad
    return this.slots.slice(0, 4);
  }

  public setMode(mode: GridMode): void {
    this.mode = mode;
    this.applyGridStyles();

    const activeSlots = this.getActiveSlots();
    for (const slot of activeSlots) {
      slot.viewport.onResize();
    }

    this.updateSkewMatrixHUD();
    this.onModeChangeCb?.(mode);
  }

  public toggleCameraSync(enable?: boolean): boolean {
    if (enable !== undefined) {
      this.syncCameras = enable;
    } else {
      this.syncCameras = !this.syncCameras;
    }
    return this.syncCameras;
  }

  private setupCameraSync(slot: ViewportSlot): void {
    const controls = slot.viewport.controls;
    if (!controls) {
      return;
    }

    controls.addEventListener('change', () => {
      if (this.syncCameras && !this.isSyncing) {
        this.isSyncing = true;
        this.syncCamerasFrom(controls);
        this.isSyncing = false;
      }
    });
  }

  private syncCamerasFrom(sourceControls: OrbitControls): void {
    const activeSlots = this.getActiveSlots();
    const sourceObject = sourceControls.object;
    const sourceTarget = sourceControls.target;

    for (const slot of activeSlots) {
      const targetControls = slot.viewport.controls;
      if (!targetControls || targetControls === sourceControls) {
        continue;
      }

      const targetObject = targetControls.object;

      // Copy position
      targetObject.position.copy(sourceObject.position);

      // Copy rotation
      targetObject.rotation.copy(sourceObject.rotation);

      // Copy zoom (for orthographic cameras)
      if ('zoom' in targetObject && 'zoom' in sourceObject) {
        (targetObject as any).zoom = (sourceObject as any).zoom;
      }

      // Copy projection matrix if needed (usually handled by update(), but explicit copy ensures sync)
      if ('projectionMatrix' in targetObject && 'projectionMatrix' in sourceObject) {
        (targetObject as any).projectionMatrix.copy((sourceObject as any).projectionMatrix);
      }

      // Copy target
      targetControls.target.copy(sourceTarget);

      // Update controls to apply changes
      targetControls.update();
    }
  }

  public renderAll(delta: number, speedMultiplier: number = 1.0): void {
    const activeSlots = this.getActiveSlots();
    for (const slot of activeSlots) {
      slot.viewport.render(delta, speedMultiplier);
    }
  }

  public updateSkewMatrixHUD(): void {
    if (!this.hudContainer) {
      return;
    }

    const activeSlots = this.getActiveSlots();
    this.hudContainer.innerHTML = '';

    for (const slot of activeSlots) {
      const card = document.createElement('div');
      card.className = 'skew-matrix-card';
      card.style.cssText = `
        background: rgba(0, 0, 0, 0.8);
        border: 1px solid #333;
        border-radius: 4px;
        padding: 8px;
        margin: 4px;
        color: #fff;
        font-family: monospace;
        font-size: 12px;
        min-width: 150px;
      `;

      const titleDiv = document.createElement('div');
      titleDiv.style.cssText = 'font-weight: bold; margin-bottom: 4px;';
      titleDiv.textContent = slot.title;

      const channelBadge = document.createElement('span');
      channelBadge.style.cssText = `
        display: inline-block;
        padding: 2px 6px;
        border-radius: 3px;
        font-size: 10px;
        margin-left: 4px;
        background: ${slot.channel === 'Rapid' ? '#ff9800' : slot.channel === 'Regular' ? '#4caf50' : '#9e9e9e'};
        color: #000;
      `;
      channelBadge.textContent = slot.channel ?? 'Unknown';

      const versionDiv = document.createElement('div');
      versionDiv.style.cssText = 'margin-bottom: 4px;';
      versionDiv.textContent = `v${slot.k8sVersion ?? 'unknown'}`;

      const deprecatedDiv = document.createElement('div');
      deprecatedDiv.style.cssText = 'margin-bottom: 4px; color: #ff5252;';
      if (slot.k8sVersion === '1.37') {
        deprecatedDiv.textContent = '⚠ flowcontrol.apiserver.k8s.io/v1beta2';
      } else {
        deprecatedDiv.textContent = '✓ No deprecated APIs';
        deprecatedDiv.style.color = '#4caf50';
      }

      const streamPill = document.createElement('div');
      const isLive = !!slot.streamUrl;
      streamPill.style.cssText = `
        display: inline-block;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 10px;
        background: ${isLive ? '#2196f3' : '#616161'};
        color: #fff;
      `;
      streamPill.textContent = isLive ? 'Live SSE' : 'Static';

      card.appendChild(titleDiv);
      card.appendChild(channelBadge);
      card.appendChild(versionDiv);
      card.appendChild(deprecatedDiv);
      card.appendChild(streamPill);

      this.hudContainer.appendChild(card);
    }
  }

  private applyGridStyles(): void {
    const allSlots = this.slots;
    const divider = this.wrapper.querySelector('.viewport-divider') as HTMLElement | null;

    if (this.mode === 'single') {
      if (divider) divider.style.display = 'none';
      this.wrapper.style.display = 'block';
      this.wrapper.style.flexDirection = '';
      this.wrapper.style.gridTemplateColumns = '';
      this.wrapper.style.gridTemplateRows = '';
      this.wrapper.style.gap = '';
      this.wrapper.style.height = '100%';

      for (let i = 0; i < allSlots.length; i++) {
        const slot = allSlots[i];
        if (!slot) continue;
        if (i === 0) {
          slot.container.style.display = 'block';
          slot.container.style.width = '100%';
          slot.container.style.height = '100%';
          slot.container.style.flex = '';
          slot.container.style.gridColumn = '';
          slot.container.style.gridRow = '';
        } else {
          slot.container.style.display = 'none';
        }
      }
    } else if (this.mode === 'dual') {
      if (divider) divider.style.display = 'block';
      this.wrapper.style.display = 'flex';
      this.wrapper.style.flexDirection = 'row';
      this.wrapper.style.gridTemplateColumns = '';
      this.wrapper.style.gridTemplateRows = '';
      this.wrapper.style.gap = '';
      this.wrapper.style.height = '100%';

      for (let i = 0; i < allSlots.length; i++) {
        const slot = allSlots[i];
        if (!slot) continue;
        if (i < 2) {
          slot.container.style.display = 'block';
          slot.container.style.flex = '1 1 50%';
          slot.container.style.height = '100%';
          slot.container.style.width = '';
          slot.container.style.gridColumn = '';
          slot.container.style.gridRow = '';
        } else {
          slot.container.style.display = 'none';
        }
      }
    } else if (this.mode === 'quad') {
      if (divider) {
        divider.style.display = 'none';
        divider.style.setProperty('display', 'none', 'important');
      }
      this.wrapper.style.display = 'grid';
      this.wrapper.style.flexDirection = '';
      this.wrapper.style.gridTemplateColumns = '1fr 1fr';
      this.wrapper.style.gridTemplateRows = '1fr 1fr';
      this.wrapper.style.gap = '2px';
      this.wrapper.style.height = '100%';

      const gridPositions = [
        { col: '1', row: '1', pos: 'tl' },
        { col: '2', row: '1', pos: 'tr' },
        { col: '1', row: '2', pos: 'bl' },
        { col: '2', row: '2', pos: 'br' },
      ];

      for (let i = 0; i < allSlots.length; i++) {
        const slot = allSlots[i];
        if (!slot) continue;
        if (i < 4) {
          slot.container.style.display = 'block';
          slot.container.style.width = '100%';
          slot.container.style.height = '100%';
          slot.container.style.flex = '';
          const gp = gridPositions[i];
          if (gp) {
            slot.container.style.gridColumn = gp.col;
            slot.container.style.gridRow = gp.row;
            slot.container.setAttribute('data-grid-pos', gp.pos);
          }
        } else {
          slot.container.style.display = 'none';
        }
      }
    }
  }

  private handleKeyDown(event: KeyboardEvent): void {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
      return;
    }

    switch (event.key) {
      case '1':
        this.setMode('single');
        break;
      case '2':
        this.setMode('dual');
        break;
      case '4':
        this.setMode('quad');
        break;
      default:
        break;
    }
  }
}
