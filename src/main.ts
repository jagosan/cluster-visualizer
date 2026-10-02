import { ClusterViewport } from './scene/cluster_viewport.js';
import type { ClusterGraphData } from './scene/cluster_viewport.js';
import { CameraSyncController } from './scene/camera_sync.js';
import { DiffInspectorDrawer } from './ui/diff_inspector.js';

interface DiffReportData {
  source_cluster: string;
  target_cluster: string;
  summary: {
    identical_nodes: number;
    version_skew_nodes: number;
    missing_in_target: number;
    added_in_target: number;
  };
  nodes: {
    node_id: string;
    status: 'identical' | 'version_skew' | 'missing' | 'added';
    source_version?: string;
    target_version?: string;
    source_image?: string;
    target_image?: string;
    source_digest?: string;
    target_digest?: string;
    diff_details: string[];
  }[];
}

async function bootstrap() {
  const containerA = document.getElementById('viewport-a');
  const containerB = document.getElementById('viewport-b');
  if (!containerA || !containerB) {
    throw new Error('Viewport container panes not found in DOM');
  }

  // 1. Initialize Dual Viewports
  const viewportA = new ClusterViewport(containerA, 'Cluster Alpha (v1.36.4)');
  const viewportB = new ClusterViewport(containerB, 'Cluster Beta (v1.35.8)');

  // 2. Load 3D Asset Kit
  const assetKitUrl = './assets/cluster-kit.glb';
  await Promise.all([
    viewportA.loadAssets(assetKitUrl),
    viewportB.loadAssets(assetKitUrl),
  ]);

  // 3. Load Cluster Data & Diff Report
  const [dataA, dataB, diffReport]: [ClusterGraphData, ClusterGraphData, DiffReportData] =
    await Promise.all([
      fetch('./data/cluster-alpha.json').then((r) => r.json()),
      fetch('./data/cluster-beta.json').then((r) => r.json()),
      fetch('./data/cluster-diff.json').then((r) => r.json()),
    ]);

  // Build diff lookups
  const diffMapA = new Map<string, { status: any; diffDetails: string[] }>();
  const diffMapB = new Map<string, { status: any; diffDetails: string[] }>();

  for (const match of diffReport.nodes) {
    diffMapA.set(match.node_id, {
      status: match.status,
      diffDetails: match.diff_details,
    });
    if (match.status === 'added') {
      diffMapB.set(match.node_id, {
        status: match.status,
        diffDetails: match.diff_details,
      });
    }
  }

  // Also map version skews and identical nodes to cluster B nodes
  for (const nodeB of dataB.nodes) {
    if (diffMapB.has(nodeB.id)) continue;
    const matchA = dataA.nodes.find((nA) => {
      if (nA.id === nodeB.id) return true;
      if (nA.name === nodeB.name && nA.namespace === nodeB.namespace) return true;
      const baseA = nA.name.split('-')[0];
      const baseB = nodeB.name.split('-')[0];
      return nA.kind === nodeB.kind && baseA === baseB && nA.namespace === nodeB.namespace;
    });
    if (matchA && diffMapA.has(matchA.id)) {
      diffMapB.set(nodeB.id, diffMapA.get(matchA.id)!);
    }
  }

  // Populate viewports
  viewportA.setClusterData(dataA, diffMapA);
  viewportB.setClusterData(dataB, diffMapB);

  // 4. Populate Topbar Summary Pills
  const pillsContainer = document.getElementById('summary-pills');
  if (pillsContainer) {
    const s = diffReport.summary;
    pillsContainer.innerHTML = `
      <div class="pill pill-identical">✓ ${s.identical_nodes} Identical</div>
      <div class="pill pill-skew">⚠ ${s.version_skew_nodes} Version Skews</div>
      <div class="pill pill-missing">✕ ${s.missing_in_target} Missing in Beta</div>
      <div class="pill pill-added">+ ${s.added_in_target} Added in Beta</div>
    `;
  }

  // 5. Camera Synchronization
  const cameraSync = new CameraSyncController(viewportA.controls, viewportB.controls);

  // 6. Inspection Drawer & Hover Tooltip
  const inspector = new DiffInspectorDrawer();

  viewportA.onNodeHovered = (node, x, y) => inspector.showTooltip(node, x, y);
  viewportB.onNodeHovered = (node, x, y) => inspector.showTooltip(node, x, y);

  viewportA.onNodeSelected = (node) => {
    if (!node) {
      inspector.close();
      return;
    }
    // Find matching peer node in Cluster B
    const peer = dataB.nodes.find((n) => n.kind === node.kind && n.name === node.name) || null;
    inspector.inspectNode(node, peer);
  };

  viewportB.onNodeSelected = (node) => {
    if (!node) {
      inspector.close();
      return;
    }
    // Find matching peer node in Cluster A
    const peer = dataA.nodes.find((n) => n.kind === node.kind && n.name === node.name) || null;
    inspector.inspectNode(node, peer);
  };

  // 7. Wire UI Controls
  const btnSyncCam = document.getElementById('btn-sync-cam');
  if (btnSyncCam) {
    btnSyncCam.addEventListener('click', () => {
      cameraSync.enabled = !cameraSync.enabled;
      btnSyncCam.classList.toggle('active', cameraSync.enabled);
    });
  }

  let flowsEnabled = true;
  const btnToggleFlows = document.getElementById('btn-toggle-flows');
  if (btnToggleFlows) {
    btnToggleFlows.addEventListener('click', () => {
      flowsEnabled = !flowsEnabled;
      btnToggleFlows.classList.toggle('active', flowsEnabled);
      viewportA.flowSystem.group.visible = flowsEnabled;
      viewportB.flowSystem.group.visible = flowsEnabled;
    });
  }

  const btnResetCam = document.getElementById('btn-reset-cam');
  if (btnResetCam) {
    btnResetCam.addEventListener('click', () => {
      viewportA.camera.position.set(12, 10, 15);
      viewportA.controls.target.set(0, 1.0, 0);
      viewportA.controls.update();

      viewportB.camera.position.set(12, 10, 15);
      viewportB.controls.target.set(0, 1.0, 0);
      viewportB.controls.update();
    });
  }

  // 8. Expose globals for debugging and testing
  (window as any).__viewportA = viewportA;
  (window as any).__viewportB = viewportB;
  (window as any).__inspector = inspector;
  (window as any).__dataA = dataA;
  (window as any).__dataB = dataB;

  // 9. Animation Loop
  let lastTime = performance.now();
  function animate(now: number) {
    requestAnimationFrame(animate);
    const delta = (now - lastTime) / 1000;
    lastTime = now;

    viewportA.render(delta);
    viewportB.render(delta);
  }
  requestAnimationFrame(animate);
}

window.addEventListener('DOMContentLoaded', () => {
  bootstrap().catch((err) => {
    console.error('Failed to bootstrap Cluster Visualizer:', err);
  });
});
