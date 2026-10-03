export type LayoutMode = 'skyscraper' | 'latency-force';

export class ModeToggle {
  private container: HTMLElement;
  private currentMode: LayoutMode = 'skyscraper';
  private currentAlpha: number = 0.0;
  private onModeChangeCallback?: (mode: LayoutMode, alpha: number) => void;

  private toggleButton: HTMLButtonElement;
  private slider: HTMLInputElement;
  private keydownHandler: (event: KeyboardEvent) => void;

  constructor(parentContainer?: HTMLElement) {
    // Create the main floating HUD pill container
    this.container = document.createElement('div');
    this.container.className = 'mode-toggle-hud';
    this.container.style.position = 'fixed';
    this.container.style.bottom = '20px';
    this.container.style.right = '20px';
    this.container.style.zIndex = '1000';
    this.container.style.display = 'flex';
    this.container.style.flexDirection = 'column';
    this.container.style.gap = '8px';
    this.container.style.padding = '12px';
    this.container.style.borderRadius = '12px';
    this.container.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
    this.container.style.backdropFilter = 'blur(10px)';
    this.container.style.border = '1px solid rgba(255, 255, 255, 0.2)';
    this.container.style.boxShadow = '0 4px 6px rgba(0, 0, 0, 0.1)';
    this.container.style.color = '#fff';
    this.container.style.fontFamily = 'sans-serif';
    this.container.style.fontSize = '12px';

    // Create toggle button
    this.toggleButton = document.createElement('button');
    this.toggleButton.textContent = 'Mode: Skyscraper ⇄ Latency Field';
    this.toggleButton.style.cursor = 'pointer';
    this.toggleButton.style.padding = '6px 12px';
    this.toggleButton.style.borderRadius = '6px';
    this.toggleButton.style.border = '1px solid rgba(255, 255, 255, 0.3)';
    this.toggleButton.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
    this.toggleButton.style.color = '#fff';
    this.toggleButton.style.transition = 'background-color 0.2s';
    this.toggleButton.addEventListener('click', () => {
      const newMode: LayoutMode = this.currentMode === 'skyscraper' ? 'latency-force' : 'skyscraper';
      this.setMode(newMode);
    });

    // Create range slider
    this.slider = document.createElement('input');
    this.slider.type = 'range';
    this.slider.min = '0';
    this.slider.max = '1';
    this.slider.step = '0.01';
    this.slider.value = '0';
    this.slider.style.width = '100%';
    this.slider.style.cursor = 'pointer';
    this.slider.addEventListener('input', () => {
      const val = parseFloat(this.slider.value);
      if (!isNaN(val)) {
        this.setAlpha(val);
      }
    });

    // Append elements to container
    this.container.appendChild(this.toggleButton);
    this.container.appendChild(this.slider);

    // Mount to parent or body
    const targetParent = parentContainer ?? document.body;
    targetParent.appendChild(this.container);

    // Keyboard shortcut handler
    this.keydownHandler = (event: KeyboardEvent) => {
      // Only trigger if not typing in an input/textarea
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        return;
      }

      if (event.key === 'l' || event.key === 'L') {
        event.preventDefault();
        const newMode: LayoutMode = this.currentMode === 'skyscraper' ? 'latency-force' : 'skyscraper';
        this.setMode(newMode);
      }
    };
    window.addEventListener('keydown', this.keydownHandler);
  }

  onModeChange(callback: (mode: LayoutMode, alpha: number) => void): void {
    this.onModeChangeCallback = callback;
  }

  setAlpha(alpha: number): void {
    // Clamp alpha between 0.0 and 1.0
    const clampedAlpha = Math.max(0.0, Math.min(1.0, alpha));
    this.currentAlpha = clampedAlpha;

    // Update slider UI
    this.slider.value = clampedAlpha.toString();

    // Determine mode based on alpha if needed, but primarily alpha drives the visual state
    // If alpha is exactly 0, mode is skyscraper. If exactly 1, mode is latency-force.
    // For intermediate values, we keep the current mode unless explicitly set.
    // However, the spec implies alpha is the lerp factor. 
    // Let's assume setting alpha directly updates the state and notifies.
    
    if (this.onModeChangeCallback) {
      this.onModeChangeCallback(this.currentMode, this.currentAlpha);
    }
  }

  setMode(mode: LayoutMode): void {
    this.currentMode = mode;
    
    // Set alpha to 0 for skyscraper, 1 for latency-force
    if (mode === 'skyscraper') {
      this.currentAlpha = 0.0;
    } else {
      this.currentAlpha = 1.0;
    }

    // Update UI
    this.slider.value = this.currentAlpha.toString();
    this.toggleButton.textContent = `Mode: ${mode === 'skyscraper' ? 'Skyscraper' : 'Latency Field'} ⇄ ${mode === 'skyscraper' ? 'Latency Field' : 'Skyscraper'}`;

    if (this.onModeChangeCallback) {
      this.onModeChangeCallback(this.currentMode, this.currentAlpha);
    }
  }

  destroy(): void {
    window.removeEventListener('keydown', this.keydownHandler);
    if (this.container.parentNode) {
      this.container.parentNode.removeChild(this.container);
    }
    this.onModeChangeCallback = undefined;
  }
}
