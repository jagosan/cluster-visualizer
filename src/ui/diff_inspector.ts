import type { ClusterNodeData } from '../scene/cluster_viewport.js';

export class DiffInspectorDrawer {
  private drawerElem: HTMLElement;
  private tooltipElem: HTMLElement;

  constructor() {
    // 1. Tooltip
    this.tooltipElem = document.createElement('div');
    this.tooltipElem.className = 'node-tooltip';
    this.tooltipElem.style.display = 'none';
    document.body.appendChild(this.tooltipElem);

    // 2. Inspection Drawer
    this.drawerElem = document.createElement('div');
    this.drawerElem.className = 'diff-drawer';
    this.drawerElem.innerHTML = `
      <div class="diff-header">
        <span class="diff-title">COMPONENT INSPECTOR</span>
        <button class="close-btn" id="drawer-close">&times;</button>
      </div>
      <div class="diff-body" id="drawer-content">
        <div class="empty-state">Click any 3D component to inspect versions and diffs.</div>
      </div>
    `;
    document.body.appendChild(this.drawerElem);

    const closeBtn = document.getElementById('drawer-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => this.close());
    }
  }

  public showTooltip(node: ClusterNodeData | null, x: number, y: number) {
    if (!node) {
      this.tooltipElem.style.display = 'none';
      return;
    }

    const badgeClass = node.diffStatus ? `badge-${node.diffStatus}` : 'badge-identical';
    const statusText = node.diffStatus ? node.diffStatus.replace('_', ' ').toUpperCase() : 'IDENTICAL';

    this.tooltipElem.innerHTML = `
      <div class="tooltip-header">
        <span class="tooltip-name">${node.name}</span>
        <span class="tooltip-badge ${badgeClass}">${statusText}</span>
      </div>
      <div class="tooltip-meta">${node.kind} • ${node.layer} • ${node.version}</div>
    `;
    this.tooltipElem.style.left = `${x + 16}px`;
    this.tooltipElem.style.top = `${y + 16}px`;
    this.tooltipElem.style.display = 'block';
  }

  public inspectNode(node: ClusterNodeData | null, peerNode: ClusterNodeData | null = null) {
    if (!node) {
      this.close();
      return;
    }

    this.drawerElem.classList.add('open');
    const content = document.getElementById('drawer-content');
    if (!content) return;

    const badgeClass = node.diffStatus ? `badge-${node.diffStatus}` : 'badge-identical';
    const statusText = node.diffStatus ? node.diffStatus.replace('_', ' ').toUpperCase() : 'IDENTICAL';

    let diffSectionHtml = '';
    if (node.diffDetails && node.diffDetails.length > 0) {
      diffSectionHtml = `
        <div class="diff-alert">
          <div class="alert-title">⚠ Detected Skews / Differences:</div>
          <ul>
            ${node.diffDetails.map((d) => `<li>${d}</li>`).join('')}
          </ul>
        </div>
      `;
    }

    let peerComparisonHtml = '';
    if (peerNode) {
      peerComparisonHtml = `
        <div class="comparison-block">
          <div class="block-title">Comparative Analysis (Peer Node)</div>
          <table class="diff-table">
            <thead>
              <tr><th>Attribute</th><th>This Cluster</th><th>Peer Cluster</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>Version</td>
                <td class="${node.version !== peerNode.version ? 'skew-val' : ''}">${node.version}</td>
                <td class="${node.version !== peerNode.version ? 'skew-val' : ''}">${peerNode.version}</td>
              </tr>
              <tr>
                <td>Image</td>
                <td class="${node.image !== peerNode.image ? 'skew-val' : ''}">${node.image || 'N/A'}</td>
                <td class="${node.image !== peerNode.image ? 'skew-val' : ''}">${peerNode.image || 'N/A'}</td>
              </tr>
              <tr>
                <td>Digest</td>
                <td class="${node.digest !== peerNode.digest ? 'skew-val' : ''}">${node.digest ? node.digest.slice(0, 18) + '...' : 'None'}</td>
                <td class="${node.digest !== peerNode.digest ? 'skew-val' : ''}">${peerNode.digest ? peerNode.digest.slice(0, 18) + '...' : 'None'}</td>
              </tr>
            </tbody>
          </table>
        </div>
      `;
    }

    content.innerHTML = `
      <div class="node-overview">
        <div class="overview-top">
          <span class="node-kind-badge">${node.kind}</span>
          <span class="node-status-badge ${badgeClass}">${statusText}</span>
        </div>
        <h2 class="node-name">${node.name}</h2>
        <div class="meta-row"><span>Namespace:</span> <strong>${node.namespace}</strong></div>
        <div class="meta-row"><span>Elevation Layer:</span> <strong>${node.layer}</strong></div>
        <div class="meta-row"><span>Semantic Version:</span> <code class="code-tag">${node.version}</code></div>
        <div class="meta-row"><span>Container Image:</span> <code class="code-tag">${node.image || 'N/A'}</code></div>
        <div class="meta-row"><span>SHA-256 Digest:</span> <code class="code-tag">${node.digest || 'Verified via image tag'}</code></div>
      </div>

      ${diffSectionHtml}
      ${peerComparisonHtml}

      <div class="raw-section">
        <div class="raw-title">3D Spatial & Coordinates</div>
        <pre class="json-preview">${JSON.stringify(node.spatial, null, 2)}</pre>
      </div>
    `;
  }

  public close() {
    this.drawerElem.classList.remove('open');
  }
}
