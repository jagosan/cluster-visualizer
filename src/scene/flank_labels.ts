import * as THREE from 'three';

/**
 * TASK-CV-304: FlankLabelManager
 * Creates crisp typographic billboard sprites floating on the left and right flanks
 * of the skyscraper tower, matching Transformer reference art.
 */

interface LabelConfig {
  text: string;
  subtitle?: string;
  accentColor: string;
  side: 'left' | 'right';
  y: number;
  z?: number;
}

const ACCENT_COLORS = {
  cyan: '#06b6d4',
  amber: '#f59e0b',
  violet: '#8b5cf6',
  emerald: '#10b981',
  purple: '#a855f7',
  blue: '#3b82f6',
  red: '#ef4444',
} as const;

const CANVAS_WIDTH = 512;
const CANVAS_HEIGHT = 128;
const SPRITE_WIDTH = 4.0;
const SPRITE_HEIGHT = 1.0;
const LEFT_FLANK_X = -7.2;
const RIGHT_FLANK_X = 7.2;

export class FlankLabelManager {
  private readonly scene: THREE.Scene;
  private readonly sprites: THREE.Sprite[] = [];
  private readonly textures: THREE.CanvasTexture[] = [];
  private readonly materials: THREE.SpriteMaterial[] = [];

  constructor(scene: THREE.Scene) {
    this.scene = scene;
  }

  /**
   * Builds all flank labels based on worker count and extended cluster flag.
   */
  buildLabels(workerCount: number, isExtended: boolean, hasRayCluster: boolean = isExtended): void {
    this.clear();

    const configs: LabelConfig[] = [];

    // Left flank labels (common to all clusters)
    configs.push({
      text: 'Clients (kubectl / watchers)',
      subtitle: 'HTTPS/6443',
      accentColor: ACCENT_COLORS.cyan,
      side: 'left',
      y: 12.0,
    });

    configs.push({
      text: 'API Gateway / Aggregator',
      subtitle: 'gRPC/2379',
      accentColor: ACCENT_COLORS.amber,
      side: 'left',
      y: 9.5,
    });

    configs.push({
      text: 'Kube-API Servers',
      subtitle: 'HTTPS/6443',
      accentColor: ACCENT_COLORS.violet,
      side: 'left',
      y: 7.0,
    });

    configs.push({
      text: 'etcd Consensus Vault',
      subtitle: 'gRPC/2379',
      accentColor: ACCENT_COLORS.emerald,
      side: 'left',
      y: 5.5,
      z: -3.5,
    });

    configs.push({
      text: 'Control Plane Supervisors',
      subtitle: 'systemd',
      accentColor: ACCENT_COLORS.purple,
      side: 'left',
      y: 4.5,
    });

    // Worker floors on left flank
    for (let i = 0; i < workerCount; i++) {
      const y = 0.5 - i * 2.3;
      configs.push({
        text: `Worker Floor ${i + 1}`,
        subtitle: `kubelet`,
        accentColor: ACCENT_COLORS.blue,
        side: 'left',
        y,
      });
    }

    // Right flank labels (extended cluster only)
    if (isExtended) {
      configs.push({
        text: 'KubeRay Operator',
        subtitle: 'CRD/Operator',
        accentColor: ACCENT_COLORS.violet,
        side: 'right',
        y: 4.5,
      });
    }
    if (hasRayCluster) {
      configs.push({
        text: 'Plasma Shared Object Store',
        subtitle: 'IPC/SharedMem',
        accentColor: ACCENT_COLORS.amber,
        side: 'right',
        y: 2.5,
      });

      configs.push({
        text: 'Raylet & GPU Workers',
        subtitle: 'gRPC/10001',
        accentColor: ACCENT_COLORS.emerald,
        side: 'right',
        y: 0.5,
      });
    }

    // Create sprites for each config
    for (const config of configs) {
      const sprite = this.createLabelSprite(config);
      this.sprites.push(sprite);
      this.scene.add(sprite);
    }
  }

  /**
   * Creates a single label sprite from configuration.
   */
  private createLabelSprite(config: LabelConfig): THREE.Sprite {
    const canvas = document.createElement('canvas');
    canvas.width = CANVAS_WIDTH;
    canvas.height = CANVAS_HEIGHT;
    const ctx = canvas.getContext('2d');

    if (!ctx) {
      throw new Error('Failed to get 2D context from canvas');
    }

    // Clear canvas
    ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);

    // Draw semi-transparent dark pill background with rounded corners
    const padding = 16;
    const cornerRadius = 24;
    const bgWidth = CANVAS_WIDTH - padding * 2;
    const bgHeight = CANVAS_HEIGHT - padding * 2;
    const bgX = padding;
    const bgY = padding;

    ctx.fillStyle = 'rgba(15, 23, 42, 0.75)';
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
    ctx.lineWidth = 2;

    // Rounded rectangle path
    ctx.beginPath();
    ctx.moveTo(bgX + cornerRadius, bgY);
    ctx.lineTo(bgX + bgWidth - cornerRadius, bgY);
    ctx.quadraticCurveTo(bgX + bgWidth, bgY, bgX + bgWidth, bgY + cornerRadius);
    ctx.lineTo(bgX + bgWidth, bgY + bgHeight - cornerRadius);
    ctx.quadraticCurveTo(bgX + bgWidth, bgY + bgHeight, bgX + bgWidth - cornerRadius, bgY + bgHeight);
    ctx.lineTo(bgX + cornerRadius, bgY + bgHeight);
    ctx.quadraticCurveTo(bgX, bgY + bgHeight, bgX, bgY + bgHeight - cornerRadius);
    ctx.lineTo(bgX, bgY + cornerRadius);
    ctx.quadraticCurveTo(bgX, bgY, bgX + cornerRadius, bgY);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    // Draw accent color dot
    const dotRadius = 8;
    const dotX = bgX + 24;
    const dotY = CANVAS_HEIGHT / 2;
    ctx.fillStyle = config.accentColor;
    ctx.beginPath();
    ctx.arc(dotX, dotY, dotRadius, 0, Math.PI * 2);
    ctx.fill();

    // Add subtle glow to dot
    ctx.shadowColor = config.accentColor;
    ctx.shadowBlur = 12;
    ctx.beginPath();
    ctx.arc(dotX, dotY, dotRadius, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;

    // Draw main text
    const textX = dotX + dotRadius + 16;
    const textY = CANVAS_HEIGHT / 2;

    ctx.font = 'bold 28px Inter, system-ui, sans-serif';
    ctx.fillStyle = '#ffffff';
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';

    // Add subtle text glow
    ctx.shadowColor = 'rgba(255, 255, 255, 0.3)';
    ctx.shadowBlur = 4;
    ctx.fillText(config.text, textX, textY - (config.subtitle ? 10 : 0));
    ctx.shadowBlur = 0;

    // Draw subtitle if present
    if (config.subtitle) {
      ctx.font = '20px Inter, system-ui, sans-serif';
      ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
      ctx.fillText(config.subtitle, textX, textY + 18);
    }

    // Create texture from canvas
    const texture = new THREE.CanvasTexture(canvas);
    texture.needsUpdate = true;
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;
    texture.generateMipmaps = false;
    this.textures.push(texture);

    // Create sprite material
    const material = new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      depthWrite: false,
      depthTest: true,
    });
    this.materials.push(material);

    // Create sprite
    const sprite = new THREE.Sprite(material);
    sprite.scale.set(SPRITE_WIDTH, SPRITE_HEIGHT, 1);

    // Position sprite
    const x = config.side === 'left' ? LEFT_FLANK_X : RIGHT_FLANK_X;
    const z = config.z ?? 0;
    sprite.position.set(x, config.y, z);

    return sprite;
  }

  /**
   * Disposes all textures, materials, and removes sprites from the scene.
   */
  clear(): void {
    for (const sprite of this.sprites) {
      this.scene.remove(sprite);
    }

    for (const texture of this.textures) {
      texture.dispose();
    }

    for (const material of this.materials) {
      material.dispose();
    }

    this.sprites.length = 0;
    this.textures.length = 0;
    this.materials.length = 0;
  }
}