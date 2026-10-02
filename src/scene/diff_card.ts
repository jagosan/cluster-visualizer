import * as THREE from 'three';

export interface ClusterNodeData {
  id: string;
  name: string;
  namespace?: string;
  cluster?: string;
  diffStatus?: 'version_skew' | 'missing' | 'added' | 'unchanged' | 'removed' | 'identical';
  diffDetails?: any[];
  sourceCluster?: string;
  targetCluster?: string;
}

export class DiffCardManager {
  private cardElement: HTMLDivElement | null = null;
  private container: HTMLElement;
  private isVisible: boolean = false;
  private currentWorldPos: THREE.Vector3 | null = null;

  constructor(container: HTMLElement) {
    this.container = container;
    this.createCardElement();
  }

  private createCardElement(): void {
    this.cardElement = document.createElement('div');
    this.cardElement.className = 'diff-card-overlay';
    this.cardElement.style.cssText = `
      background: rgba(15, 23, 42, 0.92);
      backdrop-filter: blur(8px);
      border: 1px solid #334155;
      border-radius: 6px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      font-family: 'Courier New', Courier, monospace;
      font-size: 11px;
      color: #e2e8f0;
      pointer-events: auto;
      padding: 10px;
      max-width: 360px;
      z-index: 1000;
      position: absolute;
      display: none;
      overflow: hidden;
      transition: opacity 0.15s ease, transform 0.15s ease;
    `;

    // Close button
    const closeBtn = document.createElement('button');
    closeBtn.textContent = '×';
    closeBtn.style.cssText = `
      position: absolute;
      top: 4px;
      right: 6px;
      background: transparent;
      border: none;
      color: #94a3b8;
      font-size: 16px;
      cursor: pointer;
      padding: 2px 6px;
      line-height: 1;
      border-radius: 3px;
      transition: background 0.1s, color 0.1s;
    `;
    closeBtn.addEventListener('mouseenter', () => {
      closeBtn.style.background = 'rgba(255,255,255,0.1)';
      closeBtn.style.color = '#e2e8f0';
    });
    closeBtn.addEventListener('mouseleave', () => {
      closeBtn.style.background = 'transparent';
      closeBtn.style.color = '#94a3b8';
    });
    closeBtn.addEventListener('click', () => {
      this.hide();
    });

    this.cardElement.appendChild(closeBtn);

    // Content container
    const contentDiv = document.createElement('div');
    contentDiv.className = 'diff-card-content';
    contentDiv.style.cssText = `
      margin-top: 4px;
      max-height: 300px;
      overflow-y: auto;
      overflow-x: hidden;
    `;
    this.cardElement.appendChild(contentDiv);

    this.container.appendChild(this.cardElement);
  }

  private getDiffContent(node: ClusterNodeData, clusterName: string, peerClusterName?: string): string {
    const sourceCluster = node.sourceCluster || clusterName;
    const targetCluster = node.targetCluster || peerClusterName || clusterName;
    const namespace = node.namespace || 'default';
    const name = node.name || 'unknown';

    let html = '';

    // Header
    html += `<div style="margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid #334155;">`;
    html += `<div style="color: #94a3b8; font-size: 10px; margin-bottom: 2px;">Diff Status: <span style="color: ${this.getStatusColor(node.diffStatus)};">${node.diffStatus || 'unknown'}</span></div>`;
    html += `</div>`;

    // Git-style diff header
    html += `<div style="color: #94a3b8; margin-bottom: 4px;">`;
    html += `<div style="color: #ef4444;">--- ${sourceCluster}/${namespace}/${name}</div>`;
    html += `<div style="color: #22c55e;">+++ ${targetCluster}/${namespace}/${name}</div>`;
    html += `<div style="color: #06b6d4;">@@ diff @@</div>`;
    html += `</div>`;

    // Diff details
    if (node.diffDetails && node.diffDetails.length > 0) {
      html += `<div style="margin-top: 6px; border-top: 1px solid #1e293b; padding-top: 4px;">`;
      for (const detail of node.diffDetails) {
        if (typeof detail === 'string') {
          html += `<div style="color: #f59e0b; white-space: pre-wrap; word-break: break-all;">~ ${this.escapeHtml(detail)}</div>`;
        } else if (typeof detail === 'object' && detail !== null) {
          if (detail.type === 'removed' || detail.type === 'modified') {
            const oldVal = detail.oldValue !== undefined ? detail.oldValue : '';
            html += `<div style="color: #ef4444; white-space: pre-wrap; word-break: break-all;">- ${this.escapeHtml(detail.path)}: ${this.escapeHtml(oldVal)}</div>`;
          }
          if (detail.type === 'added' || detail.type === 'modified') {
            const newVal = detail.newValue !== undefined ? detail.newValue : '';
            html += `<div style="color: #22c55e; white-space: pre-wrap; word-break: break-all;">+ ${this.escapeHtml(detail.path)}: ${this.escapeHtml(newVal)}</div>`;
          }
        }
      }
      html += `</div>`;
    } else {
      // Fallback: show basic info if no details
      html += `<div style="margin-top: 6px; border-top: 1px solid #1e293b; padding-top: 4px; color: #94a3b8;">`;
      html += `<div>No detailed diff available.</div>`;
      html += `<div style="margin-top: 4px; color: #64748b;">Node: ${this.escapeHtml(name)}</div>`;
      html += `<div style="color: #64748b;">Namespace: ${this.escapeHtml(namespace)}</div>`;
      html += `<div style="color: #64748b;">Cluster: ${this.escapeHtml(clusterName)}</div>`;
      if (peerClusterName) {
        html += `<div style="color: #64748b;">Peer Cluster: ${this.escapeHtml(peerClusterName)}</div>`;
      }
      html += `</div>`;
    }

    return html;
  }

  private getStatusColor(status?: string): string {
    switch (status) {
      case 'version_skew':
        return '#f59e0b';
      case 'missing':
        return '#ef4444';
      case 'added':
        return '#22c55e';
      case 'removed':
        return '#ef4444';
      case 'unchanged':
        return '#64748b';
      default:
        return '#94a3b8';
    }
  }

  private escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  show(node: ClusterNodeData, worldPos: THREE.Vector3, clusterName: string, peerClusterName?: string): void {
    if (!this.cardElement) return;

    // Check if node should show diff card
    const shouldShow = node.diffStatus === 'version_skew' || node.diffStatus === 'missing' || node.diffStatus === 'added';
    if (!shouldShow) {
      this.hide();
      return;
    }

    this.currentWorldPos = worldPos.clone();

    const contentDiv = this.cardElement.querySelector('.diff-card-content') as HTMLDivElement;
    if (contentDiv) {
      contentDiv.innerHTML = this.getDiffContent(node, clusterName, peerClusterName);
    }

    this.cardElement.style.display = 'block';
    this.cardElement.style.opacity = '0';
    this.cardElement.style.transform = 'translateY(5px)';

    // Trigger reflow
    void this.cardElement.offsetHeight;

    this.cardElement.style.opacity = '1';
    this.cardElement.style.transform = 'translateY(0)';

    this.isVisible = true;
  }

  hide(): void {
    if (!this.cardElement) return;

    this.cardElement.style.opacity = '0';
    this.cardElement.style.transform = 'translateY(5px)';

    setTimeout(() => {
      if (this.cardElement && !this.isVisible) {
        this.cardElement.style.display = 'none';
      }
    }, 150);

    this.isVisible = false;
    this.currentWorldPos = null;
  }

  updatePosition(camera: THREE.Camera, renderer: THREE.WebGLRenderer): void {
    if (!this.cardElement || !this.isVisible || !this.currentWorldPos) return;

    const canvas = renderer.domElement;
    const rect = canvas.getBoundingClientRect();

    // Project world position to normalized device coordinates
    const projected = this.currentWorldPos.clone().project(camera);

    // Check if behind camera
    if (projected.z > 1) {
      this.cardElement.style.display = 'none';
      return;
    }

    // Convert NDC to screen coordinates
    const x = (projected.x * 0.5 + 0.5) * rect.width;
    const y = (-projected.y * 0.5 + 0.5) * rect.height;

    // Offset card to appear adjacent to the 3D object (right side, slightly above)
    const offsetX = 20;
    const offsetY = -10;

    let cardX = x + offsetX;
    let cardY = y + offsetY;

    // Keep card within viewport bounds
    const cardWidth = this.cardElement.offsetWidth || 360;
    const cardHeight = this.cardElement.offsetHeight || 200;

    if (cardX + cardWidth > rect.width) {
      cardX = x - cardWidth - offsetX;
    }
    if (cardY + cardHeight > rect.height) {
      cardY = rect.height - cardHeight - 10;
    }
    if (cardY < 10) {
      cardY = 10;
    }
    if (cardX < 10) {
      cardX = 10;
    }

    this.cardElement.style.left = `${cardX}px`;
    this.cardElement.style.top = `${cardY}px`;
  }

  dispose(): void {
    if (this.cardElement && this.cardElement.parentNode) {
      this.cardElement.parentNode.removeChild(this.cardElement);
    }
    this.cardElement = null;
    this.isVisible = false;
    this.currentWorldPos = null;
  }
}
